param([int]$Port = 8765, [switch]$Offline, [switch]$Background)
$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$runtime = Join-Path $projectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $runtime)) { throw "Run .\scripts\setup.ps1 first." }
if (-not (Test-Path -LiteralPath (Join-Path $projectRoot "frontend\dist\index.html"))) { throw "Frontend is missing. Run .\scripts\setup.ps1." }
if ($Port -lt 1024 -or $Port -gt 65535) { throw "Choose a port between 1024 and 65535." }
$existingListener = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue
if ($existingListener) { throw "Port $Port is already in use. Open the running app or choose -Port." }
if ($Offline) { $env:SAFETRACE_OFFLINE = "1" }
$env:PYTHONIOENCODING = "utf-8"
Push-Location $projectRoot
try {
    if ($Background) {
        New-Item -ItemType Directory -Path (Join-Path $projectRoot "logs") -Force | Out-Null
        $argsList = @("-m", "uvicorn", "backend.app:app", "--host", "127.0.0.1", "--port", "$Port")
        $process = Start-Process -FilePath $runtime -ArgumentList $argsList -WorkingDirectory $projectRoot `
            -WindowStyle Hidden -RedirectStandardOutput (Join-Path $projectRoot "logs\server.out.log") `
            -RedirectStandardError (Join-Path $projectRoot "logs\server.err.log") -PassThru
        $process.Id | Set-Content -LiteralPath (Join-Path $projectRoot "logs\server.pid")
        Write-Host "Starting SafeTrace KZ at http://127.0.0.1:$Port (background). Logs: .\logs"
    } else {
        Write-Host "SafeTrace KZ: http://127.0.0.1:$Port . Stop with Ctrl+C."
        & $runtime -m uvicorn backend.app:app --host 127.0.0.1 --port $Port
        if ($LASTEXITCODE -ne 0) { throw "Server stopped with an error. Check the message above." }
    }
} finally { Pop-Location }
