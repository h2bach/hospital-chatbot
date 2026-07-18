# Powershell script to run HeartCare AI Project locally

# Load environment variables from .env file
if (Test-Path ".env") {
    Get-Content .env | ForEach-Object {
        $line = $_.Trim()
        if ($line -and -not $line.StartsWith("#") -and $line.Contains("=")) {
            $key, $value = $line.Split("=", 2)
            $key = $key.Trim()
            $value = $value.Trim().Trim('"').Trim("'")
            Set-Item "env:\$key" $value
        }
    }
}

$ApiKeys = $env:GEMINI_API_KEYS
if (-not $ApiKeys -or $ApiKeys -eq "your_actual_gemini_api_key_here") {
    $ApiKeys = $env:GEMINI_API_KEY
}
if (-not $ApiKeys -or $ApiKeys -eq "your_actual_gemini_api_key_here") {
    Write-Host "[Error] GEMINI_API_KEYS or GEMINI_API_KEY is not set. Add one or more Gemini API keys to the '.env' file." -ForegroundColor Red
    Exit 1
}

$MockPort = 8081
$AgentPort = 8080


Write-Host "=========================================" -ForegroundColor Green
Write-Host "HeartCare AI Hospital Chatbot Local runner" -ForegroundColor Green
Write-Host "=========================================" -ForegroundColor Green

# 1. Check if mock-data exists
if (-not (Test-Path "mock-data/output")) {
    Write-Host "[Error] mock-data/output directory not found. Please make sure you are running from the workspace root." -ForegroundColor Red
    Exit 1
}

# 2. Check for frontend build
$StaticDir = Join-Path (Get-Location) "ai-agent/static"
if (-not (Test-Path (Join-Path $StaticDir "index.html"))) {
    Write-Host "[Info] Frontend build not found, building static frontend..." -ForegroundColor Yellow
    Push-Location "ai-agent/web-interface"
    npm install
    npm run build:static
    Pop-Location
} else {
    Write-Host "[Info] Static frontend already built at $StaticDir." -ForegroundColor Cyan
    Write-Host "Do you want to rebuild the frontend static files? (y/N)"
    $rebuild = Read-Host
    if ($rebuild -eq 'y' -or $rebuild -eq 'Y') {
        Write-Host "Rebuilding static frontend..." -ForegroundColor Yellow
        Push-Location "ai-agent/web-interface"
        npm run build:static
        Pop-Location
    }
}

# 3. Terminate any process on ports 8080 or 8081 if active
Write-Host "[Info] Checking for active processes on ports $MockPort or $AgentPort..." -ForegroundColor Cyan
$MockProc = Get-NetTCPConnection -LocalPort $MockPort -ErrorAction SilentlyContinue
if ($MockProc) {
    $MockProc.OwningProcess | ForEach-Object {
        if ($_) {
            Write-Host "Stopping process on port $MockPort (PID $_)..." -ForegroundColor Yellow
            Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue
        }
    }
}
$AgentProc = Get-NetTCPConnection -LocalPort $AgentPort -ErrorAction SilentlyContinue
if ($AgentProc) {
    $AgentProc.OwningProcess | ForEach-Object {
        if ($_) {
            Write-Host "Stopping process on port $AgentPort (PID $_)..." -ForegroundColor Yellow
            Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue
        }
    }
}

# 4. Start Mock Info Service
Write-Host "[Info] Starting Mock Info Service on port $MockPort..." -ForegroundColor Cyan
$MockJob = Start-Job -ScriptBlock {
    param($Path)
    cd $Path
    go run ./cmd --port 8081 --data ../mock-data/output
} -ArgumentList (Join-Path (Get-Location) "mock-info-service")

# Wait for mock service to start (checking health with retries)
Write-Host "Waiting for Mock Info Service to start..." -ForegroundColor Yellow
$MaxRetries = 10
$HealthCheckOk = $false
for ($i = 1; $i -le $MaxRetries; $i++) {
    try {
        $response = Invoke-RestMethod -Uri "http://localhost:8081/health" -Method Get -TimeoutSec 2
        if ($response.status -eq "ok") {
            Write-Host "[Success] Mock Info Service is running at http://localhost:8081" -ForegroundColor Green
            $HealthCheckOk = $true
            break
        }
    } catch {
        Start-Sleep -Seconds 2
    }
}

if (-not $HealthCheckOk) {
    Write-Host "[Error] Failed to connect to Mock Info Service at http://localhost:8081 after several attempts." -ForegroundColor Red
}

# 5. Start AI Agent Server in the foreground
Write-Host "[Info] Starting AI Agent Server on port $AgentPort..." -ForegroundColor Cyan
Write-Host "Access the application at: http://localhost:$AgentPort" -ForegroundColor Green
Write-Host "Press Ctrl+C to stop the agent server." -ForegroundColor Yellow

$env:GEMINI_API_KEYS = $ApiKeys
$env:PORT = $AgentPort
$env:AGENT_STATIC_DIR = $StaticDir
$env:MOCK_INFO_SERVICE_URL = "http://localhost:$MockPort"

Push-Location "ai-agent"
go run ./cmd/server -p $AgentPort
Pop-Location
