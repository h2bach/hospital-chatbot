# Powershell script to run HeartCare AI Project locally

$ApiKey = "REMOVED_GOOGLE_API_KEY"
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
Get-Process -Id (Get-NetTCPConnection -LocalPort $MockPort -ErrorAction SilentlyContinue).OwningProcess -ErrorAction SilentlyContinue | ForEach-Object {
    Write-Host "Stopping process on port $MockPort..." -ForegroundColor Yellow
    Stop-Process -Id $_.Id -Force
}
Get-Process -Id (Get-NetTCPConnection -LocalPort $AgentPort -ErrorAction SilentlyContinue).OwningProcess -ErrorAction SilentlyContinue | ForEach-Object {
    Write-Host "Stopping process on port $AgentPort..." -ForegroundColor Yellow
    Stop-Process -Id $_.Id -Force
}

# 4. Start Mock Info Service
Write-Host "[Info] Starting Mock Info Service on port $MockPort..." -ForegroundColor Cyan
$MockJob = Start-Job -ScriptBlock {
    param($Path)
    cd $Path
    go run ./cmd --port 8081 --data ../mock-data/output
} -ArgumentList (Join-Path (Get-Location) "mock-info-service")

# Wait 3 seconds for mock service to start
Start-Sleep -Seconds 3

# Verify Mock service is healthy
try {
    $response = Invoke-RestMethod -Uri "http://localhost:8081/health" -Method Get -TimeoutSec 3
    if ($response.status -eq "ok") {
        Write-Host "[Success] Mock Info Service is running at http://localhost:8081" -ForegroundColor Green
    } else {
        Write-Host "[Warning] Mock Service started but health check returned: $response" -ForegroundColor Yellow
    }
} catch {
    Write-Host "[Error] Failed to connect to Mock Info Service at http://localhost:8081" -ForegroundColor Red
}

# 5. Start AI Agent Server in the foreground
Write-Host "[Info] Starting AI Agent Server on port $AgentPort..." -ForegroundColor Cyan
Write-Host "Access the application at: http://localhost:$AgentPort" -ForegroundColor Green
Write-Host "Press Ctrl+C to stop the agent server." -ForegroundColor Yellow

$env:GEMINI_API_KEY = $ApiKey
$env:PORT = $AgentPort
$env:AGENT_STATIC_DIR = $StaticDir
$env:MOCK_INFO_SERVICE_URL = "http://localhost:$MockPort"

Push-Location "ai-agent"
go run ./cmd/server -p $AgentPort
Pop-Location
