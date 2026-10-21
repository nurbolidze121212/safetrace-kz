param(
    [string]$PythonPath,
    [string]$EnvironmentPath = ".venv"
)
$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
if ($projectRoot -match '[^\x00-\x7F]') {
    throw "Windows OCR requires an ASCII project path. Extract to a path such as C:\SafeTrace-KZ and run setup again. Spaces are supported."
}
Push-Location $projectRoot
try {
    if (-not $PythonPath) {
        $bundledPython = Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
        if (Test-Path -LiteralPath $bundledPython) { $PythonPath = $bundledPython }
        else {
            foreach ($version in @("3.12", "3.11")) {
                try {
                    $candidate = & py "-$version" -c "import sys; print(sys.executable)" 2>$null
                    if ($LASTEXITCODE -eq 0) { $PythonPath = $candidate; break }
                } catch {}
            }
        }
    }
    if (-not $PythonPath -or -not (Test-Path -LiteralPath $PythonPath)) {
        throw "Install Python 3.12 x64 from python.org and run: .\scripts\setup.ps1 -PythonPath 'C:\path\python.exe'"
    }
    & $PythonPath -c "import sys,struct; assert sys.version_info[:2] in ((3,11),(3,12)) and struct.calcsize('P')==8, 'Python 3.11/3.12 x64 required'; print(sys.version)"
    if ($LASTEXITCODE -ne 0) { throw "Use Python 3.11 or 3.12 x64, not system Python 3.14." }
    if (-not (Get-Command npm.cmd -ErrorAction SilentlyContinue)) { throw "Install Node.js 22.12+ or 24 LTS from nodejs.org." }
    & node -e "const v=process.versions.node.split('.').map(Number); if(v[0]<22||(v[0]===22&&v[1]<12))process.exit(1)"
    if ($LASTEXITCODE -ne 0) { throw "Node.js 22.12+ required." }
    $envPath = [IO.Path]::GetFullPath((Join-Path $projectRoot $EnvironmentPath))
    if (-not $envPath.StartsWith($projectRoot + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
        throw "EnvironmentPath must stay inside the project."
    }
    if (-not (Test-Path -LiteralPath (Join-Path $envPath "Scripts\python.exe"))) {
        & $PythonPath -m venv $envPath
        if ($LASTEXITCODE -ne 0) { throw "Could not create Python environment." }
    }
    $runtime = Join-Path $envPath "Scripts\python.exe"
    & $runtime -m pip install --disable-pip-version-check -r requirements.lock.txt
    if ($LASTEXITCODE -ne 0) { throw "Python dependency installation failed. See the pip error above." }
    & $runtime -m pip check
    if ($LASTEXITCODE -ne 0) { throw "Python dependency conflict." }
    & $runtime scripts/prepare_models.py
    if ($LASTEXITCODE -ne 0) { throw "OCR model preparation failed. Internet is needed for the first download." }
    & npm.cmd --prefix frontend ci --no-audit --no-fund
    if ($LASTEXITCODE -ne 0) { throw "Frontend dependency installation failed." }
    & npm.cmd --prefix frontend run build
    if ($LASTEXITCODE -ne 0) { throw "Frontend build failed." }
    Write-Host "Setup complete. Run .\scripts\start.ps1"
} finally { Pop-Location }
