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

foreach ($Port in @($InfoPort, $AgentPort)) {
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
        $Health = Invoke-RestMethod -Uri "http://localhost:$InfoPort/health" -TimeoutSec 2
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
Write-Host "[Info] Khởi động chatbot: http://localhost:$AgentPort" -ForegroundColor Green
$env:GEMINI_API_KEYS = $ApiKeys
$env:PORT = $AgentPort
$env:AGENT_STATIC_DIR = $StaticDir
$env:HOSPITAL_INFO_SERVICE_URL = "http://localhost:$InfoPort"

try {
    Push-Location "ai-agent"
    go run ./cmd/server -p $AgentPort
    Pop-Location
} finally {
    Stop-Job -Job $InfoJob -ErrorAction SilentlyContinue
    Remove-Job -Job $InfoJob -Force -ErrorAction SilentlyContinue
}
