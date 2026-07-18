# Chạy HeartCare MVP trên host. Docker Compose vẫn là cách chạy khuyến nghị.

if (Test-Path ".env") {
    Get-Content -LiteralPath ".env" -Encoding UTF8 | ForEach-Object {
        $line = $_.Trim()
        if ($line -and -not $line.StartsWith("#") -and $line.Contains("=")) {
            $key, $value = $line.Split("=", 2)
            Set-Item "env:\$($key.Trim())" $value.Trim().Trim('"').Trim("'")
        }
    }
}

$FptKeys = $env:FPT_API_KEYS
if (-not $FptKeys) { $FptKeys = $env:FPT_API_KEY }
if (-not $FptKeys -or -not $env:FPT_MODEL) {
    Write-Host "[Error] Hãy cấu hình FPT_API_KEYS (hoặc FPT_API_KEY) và FPT_MODEL trong .env." -ForegroundColor Red
    Exit 1
}

$AgentPort = 6689
$RagPort = 6690
$InfoPort = 8081
$ProjectRoot = Get-Location
$StaticDir = Join-Path $ProjectRoot "ai-agent\static"
$RagArtifactDir = Join-Path $ProjectRoot "rag-core\artifacts\data-rag"

if (-not (Test-Path -LiteralPath "hospital-data\current_schedule.json")) {
    Write-Host "[Error] Không tìm thấy hospital-data\current_schedule.json." -ForegroundColor Red
    Exit 1
}

if (-not (Test-Path -LiteralPath (Join-Path $StaticDir "index.html"))) {
    Write-Host "[Info] Đang build giao diện..." -ForegroundColor Yellow
    Push-Location "ai-agent\web-interface"
    npm ci
    npm run build:static
    Pop-Location
}

foreach ($LocalPort in @($AgentPort, $RagPort, $InfoPort)) {
    $Connections = Get-NetTCPConnection -LocalPort $LocalPort -ErrorAction SilentlyContinue
    foreach ($ProcessId in ($Connections.OwningProcess | Sort-Object -Unique)) {
        if ($ProcessId) { Stop-Process -Id $ProcessId -Force -ErrorAction SilentlyContinue }
    }
}

Write-Host "[Info] Đang index tài liệu RAG..." -ForegroundColor Cyan
$env:PYTHONPATH = Join-Path $ProjectRoot "rag-core"
python -m rag_core.indexing --source-dir "docs\data_rag" --output-dir $RagArtifactDir
if ($LASTEXITCODE -ne 0) { Exit $LASTEXITCODE }

$RagJob = Start-Job -ScriptBlock {
    param($Root, $Port, $Artifact)
    Set-Location -LiteralPath $Root
    $env:PYTHONPATH = Join-Path $Root "rag-core"
    python -m rag_core.app --host 127.0.0.1 --port $Port --chunks (Join-Path $Artifact "chunks.jsonl")
} -ArgumentList $ProjectRoot, $RagPort, $RagArtifactDir

$InfoJob = Start-Job -ScriptBlock {
    param($Path, $Port)
    Set-Location -LiteralPath $Path
    go run ./cmd --port $Port --data ../hospital-data
} -ArgumentList (Join-Path $ProjectRoot "hospital-info-service"), $InfoPort

function Wait-Service($Uri, $Name) {
    for ($Attempt = 1; $Attempt -le 30; $Attempt++) {
        try {
            $Health = Invoke-RestMethod -Uri $Uri -TimeoutSec 2
            if ($Health.status -eq "ok" -or $Health.status -eq "degraded") { return $true }
        } catch {
            Start-Sleep -Seconds 1
        }
    }
    Write-Host "[Error] $Name không khởi động được." -ForegroundColor Red
    return $false
}

if (-not (Wait-Service "http://127.0.0.1:$RagPort/health" "RAG")) {
    Receive-Job -Job $RagJob
    Stop-Job -Job $RagJob, $InfoJob -ErrorAction SilentlyContinue
    Exit 1
}
if (-not (Wait-Service "http://127.0.0.1:$InfoPort/health" "API dữ liệu")) {
    Receive-Job -Job $InfoJob
    Stop-Job -Job $RagJob, $InfoJob -ErrorAction SilentlyContinue
    Exit 1
}

$env:LLM_PROVIDERS = "fpt"
$env:PORT = "$AgentPort"
$env:AGENT_STATIC_DIR = $StaticDir
$env:RAG_SERVICE_URL = "http://127.0.0.1:$RagPort"
$env:HOSPITAL_INFO_SERVICE_URL = "http://127.0.0.1:$InfoPort"

Write-Host "[Success] HeartCare MVP: http://localhost:$AgentPort" -ForegroundColor Green
try {
    Push-Location "ai-agent"
    go run ./cmd/server -p $AgentPort
    Pop-Location
} finally {
    Stop-Job -Job $RagJob, $InfoJob -ErrorAction SilentlyContinue
    Remove-Job -Job $RagJob, $InfoJob -Force -ErrorAction SilentlyContinue
}
