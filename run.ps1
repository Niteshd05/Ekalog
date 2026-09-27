# EKALOG local launcher (Windows, no Docker needed).
#   .\run.ps1            -> build the UI if missing, start API + UI on http://localhost:8000
#   .\run.ps1 -Rebuild   -> force a fresh UI build
#   .\run.ps1 -Test      -> run the backend test suite
param([switch]$Rebuild, [switch]$Test)
$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
$py = Join-Path $root "backend\.venv\Scripts\python.exe"

if (-not (Test-Path $py)) {
    Write-Host "Creating Python venv..." -ForegroundColor Cyan
    py -m venv (Join-Path $root "backend\.venv")
    & $py -m pip install -q -r (Join-Path $root "backend\requirements.txt")
}
if ($Test) {
    Push-Location (Join-Path $root "backend"); & $py -m pytest -q tests; Pop-Location; exit $LASTEXITCODE
}
$out = Join-Path $root "web\out"
if ($Rebuild -or -not (Test-Path $out)) {
    Write-Host "Building UI (static export)..." -ForegroundColor Cyan
    Push-Location (Join-Path $root "web")
    if (-not (Test-Path "node_modules")) { npm install --no-audit --no-fund }
    $env:EKALOG_EXPORT = "1"; npx next build; Remove-Item Env:\EKALOG_EXPORT
    Pop-Location
}
try { Invoke-RestMethod http://127.0.0.1:11434/api/tags -TimeoutSec 2 | Out-Null; Write-Host "Ollama: up" -ForegroundColor Green }
catch { Write-Host "Ollama not reachable - EKALOG will run with rules-only labeling. Start it with: ollama serve" -ForegroundColor Yellow }
Write-Host "EKALOG -> http://localhost:8000" -ForegroundColor Green
Push-Location (Join-Path $root "backend")
& $py -m uvicorn app.main:app --host 127.0.0.1 --port 8000
Pop-Location
