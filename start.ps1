# Launches unified backend (port 8000) and Vite frontend. Run from repo root, or double-click.
$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
$backend = Join-Path $root "backend"
$frontend = Join-Path $root "frontend"
$venvActivate = Join-Path $backend "lulc\.venv\Scripts\activate.bat"
if (-not (Test-Path $venvActivate)) {
    Write-Host "ERROR: Python venv not found at: $venvActivate" -ForegroundColor Red
    Write-Host "Create it:  cd backend && python -m venv lulc\.venv && lulc\.venv\Scripts\python -m pip install -r requirements.txt" -ForegroundColor Yellow
    exit 1
}

Write-Host "Starting GeoAI (root: $root)..." -ForegroundColor Green

# PYTHONUNBUFFERED: stream logs immediately in the backend CMD window
$backendCmd = "cd /d `"$backend`" & set PYTHONUNBUFFERED=1 & call `".\lulc\.venv\Scripts\activate.bat`" & python main.py"
Start-Process cmd -ArgumentList "/k", $backendCmd

$frontendCmd = "cd /d `"$frontend`" & npm run dev"
Start-Process cmd -ArgumentList "/k", $frontendCmd

Write-Host "All services launched (backend http://0.0.0.0:8000, frontend usually http://localhost:5173)." -ForegroundColor Green
