param([int]$Port = 8765, [switch]$Offline, [switch]$Background)
$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$runtime = Join-Path $projectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $runtime)) { throw "Run .\scripts\setup.ps1 first." }
if (-not (Test-Path -LiteralPath (Join-Path $projectRoot "frontend\dist\index.html"))) { throw "Frontend is missing. Run .\scripts\setup.ps1." }
if ($Port -lt 1024 -or $Port -gt 65535) { throw "Choose a port between 1024 and 65535." }
$existingListener = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue
if ($existingListener) { throw "Port $Port is already in use. Open the running app or choose -Port." }
$previousOffline = $env:SAFETRACE_OFFLINE
$previousEncoding = $env:PYTHONIOENCODING
if ($Offline) { $env:SAFETRACE_OFFLINE = "1" }
$env:PYTHONIOENCODING = "utf-8"
$runner = Join-Path $projectRoot "scripts\run_server.py"
$runId = [Guid]::NewGuid().ToString('N')
$argsList = @("`"$runner`"", "--port", "$Port", "--run-id", $runId)
Push-Location $projectRoot
try {
    if ($Background) {
        New-Item -ItemType Directory -Path (Join-Path $projectRoot "logs") -Force | Out-Null
        $outLog = Join-Path $projectRoot "logs\server-$Port.out.log"
        $errLog = Join-Path $projectRoot "logs\server-$Port.err.log"
        $recordPath = Join-Path $projectRoot "logs\server-$Port.json"
        $process = Start-Process -FilePath $runtime -ArgumentList $argsList -WorkingDirectory $projectRoot `
            -WindowStyle Hidden -RedirectStandardOutput $outLog -RedirectStandardError $errLog -PassThru
        $deadline = [DateTime]::UtcNow.AddSeconds(20)
        $ready = $false
        do {
            $process.Refresh()
            if ($process.HasExited) {
                $reason = (Get-Content -LiteralPath $errLog -Encoding UTF8 -Tail 5 -ErrorAction SilentlyContinue) -join "`n"
                throw "Server failed to start. $reason"
            }
            try {
                $record = Get-Content -LiteralPath $recordPath -Encoding UTF8 -Raw -ErrorAction Stop | ConvertFrom-Json
                if ($record.run_id -eq $runId) {
                    $health = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/health" -TimeoutSec 2
                    if ($health.status -eq "ok") { $ready = $true; break }
                }
            } catch { }
            Start-Sleep -Milliseconds 250
        } while ([DateTime]::UtcNow -lt $deadline)
        if (-not $ready) { throw "Readiness check timed out. Check $errLog; use scripts\stop.ps1 -Port $Port to stop this launch." }
        Write-Host "SafeTrace KZ is ready at http://127.0.0.1:$Port (PID $($record.pid))."
        Write-Host "Logs: $outLog / $errLog. Stop: .\scripts\stop.ps1 -Port $Port"
    } else {
        Write-Host "SafeTrace KZ: http://127.0.0.1:$Port . Stop with Ctrl+C."
        & $runtime $runner --port $Port --run-id $runId
        if ($LASTEXITCODE -ne 0) { throw "Server stopped with an error. Check the message above." }
    }
} finally {
    Pop-Location
    $env:SAFETRACE_OFFLINE = $previousOffline
    $env:PYTHONIOENCODING = $previousEncoding
}
