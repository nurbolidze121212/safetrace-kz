param([int]$Port = 8770)
$ErrorActionPreference = 'Stop'
$demoRoot = Split-Path -Parent $PSScriptRoot
$runtime = Join-Path $demoRoot '.venv\Scripts\python.exe'
$tunnelCommand = Get-Command cloudflared.exe -ErrorAction SilentlyContinue
$tunnelExe = if ($tunnelCommand) { $tunnelCommand.Source } else { 'C:\Program Files (x86)\cloudflared\cloudflared.exe' }
if (-not (Test-Path -LiteralPath $tunnelExe)) { throw 'Install cloudflared from developers.cloudflare.com first.' }
if (-not (Test-Path -LiteralPath $runtime)) { throw 'Run scripts\setup.ps1 first.' }
if ($Port -lt 1024 -or $Port -gt 65535 -or $Port -eq 8765) { throw 'Choose a dedicated port, e.g. 8770.' }
if (Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue) { throw 'Port is occupied. Stop the previous demo or choose another port.' }
$runFolder = Join-Path $demoRoot ('logs\public-demo-' + [Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $runFolder | Out-Null
$tunnelLog = Join-Path $runFolder 'tunnel.err.log'
$configFile = Join-Path $runFolder 'config.json'
$tunnelProcess = $null
$serverProcess = $null
$ready = $false
try {
    $tunnelProcess = Start-Process -FilePath $tunnelExe -ArgumentList @('tunnel','--url',"http://127.0.0.1:$Port",'--protocol','http2','--no-autoupdate') -WorkingDirectory $demoRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $runFolder 'tunnel.out.log') -RedirectStandardError $tunnelLog
    $deadline = [DateTime]::UtcNow.AddSeconds(30)
    do {
        $tunnelProcess.Refresh()
        if ($tunnelProcess.HasExited) { throw "Tunnel stopped. See $tunnelLog" }
        $text = Get-Content -LiteralPath $tunnelLog -Raw -ErrorAction SilentlyContinue
        $origin = if ($text) { [regex]::Match($text, 'https://[a-z0-9-]+\.trycloudflare\.com').Value } else { '' }
        if ($origin) { break }
        Start-Sleep -Milliseconds 500
    } while ([DateTime]::UtcNow -lt $deadline)
    if (-not $origin) { throw "No tunnel URL. See $tunnelLog" }
    & $runtime (Join-Path $PSScriptRoot 'run_public_demo.py') --config $configFile --init-origin $origin --port $Port
    if ($LASTEXITCODE -ne 0) { throw 'Configuration failed.' }
    $config = Get-Content -LiteralPath $configFile -Raw | ConvertFrom-Json
    $serverProcess = Start-Process -FilePath $runtime -ArgumentList @('scripts/run_public_demo.py','--config',"`"$configFile`"") -WorkingDirectory $demoRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $runFolder 'server.out.log') -RedirectStandardError (Join-Path $runFolder 'server.err.log')
    $deadline = [DateTime]::UtcNow.AddSeconds(30)
    do {
        $serverProcess.Refresh()
        if ($serverProcess.HasExited) { throw "Server stopped. See $runFolder" }
        try {
            $page = Invoke-WebRequest -Uri "$origin/demo/login" -UseBasicParsing -TimeoutSec 5
            if ($page.StatusCode -eq 200 -and $page.Content -match 'SAFETRACE KZ / LIVE DEMO') { $ready = $true; break }
        } catch { }
        Start-Sleep -Milliseconds 500
    } while ([DateTime]::UtcNow -lt $deadline)
    if (-not $ready) { throw 'Public login page did not become ready.' }
    $record = @{ origin=$origin; config=$configFile; processes=@(
        @{ pid=$tunnelProcess.Id; startUtc=$tunnelProcess.StartTime.ToUniversalTime().ToString('o') },
        @{ pid=$serverProcess.Id; startUtc=$serverProcess.StartTime.ToUniversalTime().ToString('o') }
    ) }
    $record | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $runFolder 'processes.json') -Encoding UTF8
    Write-Host "Website: $origin"
    Write-Host "Access code: $($config.code)"
    Write-Host "Temporary shared demo. Keep this computer awake. No personal uploads."
    Write-Host "Stop: .\scripts\stop_public_demo.ps1 -Record '$runFolder\processes.json'"
} finally {
    if (-not $ready) {
        foreach ($started in @($serverProcess, $tunnelProcess)) {
            if ($started) { $started.Refresh(); if (-not $started.HasExited) { $started.Kill() } }
        }
    }
}
