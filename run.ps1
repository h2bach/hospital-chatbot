# Chạy Hanoi Heart Hospital public-information chatbot tại máy local.

if (Test-Path ".env") {
    Get-Content -LiteralPath ".env" -Encoding UTF8 | ForEach-Object {
        $line = $_.Trim()
        if ($line -and -not $line.StartsWith("#") -and $line.Contains("=")) {
            $key, $value = $line.Split("=", 2)
            Set-Item "env:\$($key.Trim())" $value.Trim().Trim('"').Trim("'")
        }
    }
}

$ApiKeys = $env:GEMINI_API_KEYS
if (-not $ApiKeys -or $ApiKeys -eq "your_actual_gemini_api_key_here") {
    $ApiKeys = $env:GEMINI_API_KEY
}
if (-not $ApiKeys -or $ApiKeys -eq "your_actual_gemini_api_key_here") {
    Write-Host "[Error] Hãy cấu hình GEMINI_API_KEYS hoặc GEMINI_API_KEY trong .env." -ForegroundColor Red
    Exit 1
}

$InfoPort = 8081
$AgentPort = 8080
$DashboardPort = 8082
$StaticDir = Join-Path (Get-Location) "ai-agent\static"

if (-not (Test-Path -LiteralPath "hospital-data\current_schedule.json")) {
    Write-Host "[Error] Không tìm thấy hospital-data\current_schedule.json." -ForegroundColor Red
    Exit 1
}

if (-not (Test-Path -LiteralPath (Join-Path $StaticDir "index.html"))) {
    Write-Host "[Info] Đang build giao diện..." -ForegroundColor Yellow
    Push-Location "ai-agent\web-interface"
    npm install
    npm run build:static
    Pop-Location
}

if (-not (Test-Path -LiteralPath "hospital-data\web-dashboard\node_modules")) {
    Write-Host "[Info] Đang cài dependency cho dashboard dữ liệu..." -ForegroundColor Yellow
    Push-Location "hospital-data\web-dashboard"
    npm ci
    if ($LASTEXITCODE -ne 0) {
        Pop-Location
        Write-Host "[Error] Không cài được dependency cho dashboard dữ liệu." -ForegroundColor Red
        Exit 1
    }
    Pop-Location
}

Write-Host "[Info] Đang build dashboard dữ liệu thành file tĩnh..." -ForegroundColor Yellow
Push-Location "hospital-data\web-dashboard"
npm run build
if ($LASTEXITCODE -ne 0) {
    Pop-Location
    Write-Host "[Error] Không build được dashboard dữ liệu." -ForegroundColor Red
    Exit 1
}
Pop-Location

foreach ($Port in @($InfoPort, $AgentPort, $DashboardPort)) {
    $Connections = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue
    foreach ($ProcessId in ($Connections.OwningProcess | Sort-Object -Unique)) {
        if ($ProcessId) { Stop-Process -Id $ProcessId -Force -ErrorAction SilentlyContinue }
    }
}

Write-Host "[Info] Khởi động API dữ liệu công khai ở cổng $InfoPort..." -ForegroundColor Cyan
$InfoJob = Start-Job -ScriptBlock {
    param($Path)
    Set-Location -LiteralPath $Path
    go run ./cmd --port 8081 --data ../hospital-data
} -ArgumentList (Join-Path (Get-Location) "hospital-info-service")

$Ready = $false
for ($Attempt = 1; $Attempt -le 15; $Attempt++) {
    try {
        $Health = Invoke-RestMethod -Uri "http://127.0.0.1:$InfoPort/health" -TimeoutSec 2
        if ($Health.status -eq "ok" -or $Health.status -eq "degraded") {
            $Ready = $true
            break
        }
    } catch {
        Start-Sleep -Seconds 1
    }
}
if (-not $Ready) {
    Receive-Job -Job $InfoJob
    Stop-Job -Job $InfoJob -ErrorAction SilentlyContinue
    Write-Host "[Error] API dữ liệu không khởi động được." -ForegroundColor Red
    Exit 1
}

Write-Host "[Success] API dữ liệu: http://localhost:$InfoPort" -ForegroundColor Green
Write-Host "[Info] Khởi động dashboard dữ liệu ở cổng $DashboardPort..." -ForegroundColor Cyan
$DashboardJob = Start-Job -ScriptBlock {
    param($Path, $ApiTarget, $Port)
    Set-Location -LiteralPath $Path
    $env:VITE_ADMIN_API_TARGET = $ApiTarget
    npm run preview -- --host 127.0.0.1 --port $Port --strictPort
} -ArgumentList (Join-Path (Get-Location) "hospital-data\web-dashboard"), "http://127.0.0.1:$InfoPort", $DashboardPort

$DashboardReady = $false
for ($Attempt = 1; $Attempt -le 20; $Attempt++) {
    try {
        $Response = Invoke-WebRequest -Uri "http://127.0.0.1:$DashboardPort" -TimeoutSec 2 -UseBasicParsing
        if ($Response.StatusCode -eq 200) {
            $DashboardReady = $true
            break
        }
    } catch {
        Start-Sleep -Milliseconds 500
    }
}
if (-not $DashboardReady) {
    Receive-Job -Job $DashboardJob
    Stop-Job -Job $DashboardJob -ErrorAction SilentlyContinue
    Stop-Job -Job $InfoJob -ErrorAction SilentlyContinue
    Write-Host "[Error] Dashboard dữ liệu không khởi động được." -ForegroundColor Red
    Exit 1
}

Write-Host "[Success] Dashboard dữ liệu: http://localhost:$DashboardPort" -ForegroundColor Green
Write-Host "[Info] Khởi động chatbot: http://localhost:$AgentPort" -ForegroundColor Green
$env:GEMINI_API_KEYS = $ApiKeys
$env:PORT = $AgentPort
$env:AGENT_STATIC_DIR = $StaticDir
$env:HOSPITAL_INFO_SERVICE_URL = "http://127.0.0.1:$InfoPort"

try {
    Push-Location "ai-agent"
    go run ./cmd/server -p $AgentPort
    Pop-Location
} finally {
    foreach ($Job in @($DashboardJob, $InfoJob)) {
        Stop-Job -Job $Job -ErrorAction SilentlyContinue
        Remove-Job -Job $Job -Force -ErrorAction SilentlyContinue
    }
}
