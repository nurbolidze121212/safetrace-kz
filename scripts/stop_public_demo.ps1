param([Parameter(Mandatory=$true)][string]$Record)
$ErrorActionPreference = 'Stop'
$demoRoot = Split-Path -Parent $PSScriptRoot
$recordPath = (Resolve-Path -LiteralPath $Record).Path
$logsRoot = [IO.Path]::GetFullPath((Join-Path $demoRoot 'logs')) + [IO.Path]::DirectorySeparatorChar
if (-not $recordPath.StartsWith($logsRoot, [StringComparison]::OrdinalIgnoreCase)) { throw 'Use a process record inside this project logs folder.' }
$recordData = Get-Content -LiteralPath $recordPath -Raw | ConvertFrom-Json
foreach ($item in $recordData.processes) {
    $running = Get-Process -Id $item.pid -ErrorAction SilentlyContinue
    if (-not $running) { continue }
    # PowerShell 7 parses ISO JSON dates into DateTime; Windows PowerShell keeps strings.
    $expectedStart = ([datetime]$item.startUtc).ToUniversalTime()
    if ($running.StartTime.ToUniversalTime().Ticks -ne $expectedStart.Ticks) { throw "PID $($item.pid) was reused; refusing to stop it." }
    Stop-Process -Id $item.pid -ErrorAction Stop
}
Write-Host 'Demo stopped. Its data and process record are preserved. The private workstation server is unchanged.'
