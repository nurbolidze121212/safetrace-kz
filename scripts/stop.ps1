param([int]$Port = 8765)
$ErrorActionPreference = "Stop"
if ($Port -lt 1024 -or $Port -gt 65535) { throw "Choose a port between 1024 and 65535." }
$projectRoot = Split-Path -Parent $PSScriptRoot
$runner = Join-Path $projectRoot "scripts\run_server.py"
$recordPath = Join-Path $projectRoot "logs\server-$Port.json"
if (-not (Test-Path -LiteralPath $recordPath)) { throw "No managed launch record for port $Port. Stop its original terminal with Ctrl+C." }
$record = Get-Content -LiteralPath $recordPath -Encoding UTF8 -Raw | ConvertFrom-Json
if ($record.schema -ne 'safetrace-server-1' -or $record.port -ne $Port -or $record.project -ne $projectRoot -or $record.run_id -notmatch '^[a-f0-9]{32}$') {
    throw "Invalid launch record. No process was stopped."
}
$serverProcess = Get-CimInstance Win32_Process -Filter "ProcessId = $([int]$record.pid)"
if (-not $serverProcess) { Write-Host "This server process is no longer running."; exit 0 }
$runnerPattern = [regex]::Escape($runner)
$runPattern = '--run-id\s+' + [regex]::Escape($record.run_id) + '(\s|$)'
if ($serverProcess.CommandLine -notmatch $runnerPattern -or $serverProcess.CommandLine -notmatch $runPattern -or $serverProcess.Name -notmatch '^python(w)?\.exe$') {
    throw "The PID does not match this SafeTrace launch. No process was stopped."
}
$listeners = @(Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue)
if ($listeners | Where-Object { $_.OwningProcess -ne [int]$record.pid }) {
    throw "Another process owns this port. No process was stopped."
}
if ($listeners.Count) {
    # Windows PowerShell emits a JSON array as one pipeline object. Do not wrap it again.
    $cases = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/cases" -TimeoutSec 5
    if ($cases -isnot [Array]) { throw "Unexpected queue response. No process was stopped." }
    $active = @($cases | Where-Object { $_.status -in @('pending', 'running') })
    if ($active.Count) { throw "$($active.Count) analyses are active. Wait for completion or cancel them in the app, then retry." }
}
Stop-Process -Id ([int]$record.pid) -Force
Wait-Process -Id ([int]$record.pid) -Timeout 10 -ErrorAction SilentlyContinue
$remaining = Get-Process -Id ([int]$record.pid) -ErrorAction SilentlyContinue
if ($remaining -and -not $remaining.HasExited) { throw "Server process has not stopped yet." }
if (Test-Path -LiteralPath $recordPath) {
    $latest = Get-Content -LiteralPath $recordPath -Encoding UTF8 -Raw | ConvertFrom-Json
    if ($latest.run_id -eq $record.run_id) { Remove-Item -LiteralPath $recordPath }
}
Write-Host "SafeTrace KZ on port $Port stopped. Saved data remains in place."
