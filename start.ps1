# Starts both servers for the MediShield demo.
#
#   powershell -ExecutionPolicy Bypass -File .\start.ps1
#
# The backend (FastAPI, port 8000) opens in its own window so you can watch the
# agent pipeline logs live; the frontend (Next.js, port 3000) runs here.
# Press Ctrl+C to stop the frontend, then close the backend window.

$root = $PSScriptRoot

Write-Host "Starting backend on http://127.0.0.1:8000 ..." -ForegroundColor Cyan
Start-Process powershell -ArgumentList @(
    "-NoExit",
    "-Command",
    "cd '$root'; uvicorn app.main:app --reload --app-dir backend"
)

Start-Sleep -Seconds 3

$frontend = Join-Path $root "frontend"
if (-not (Test-Path (Join-Path $frontend "node_modules"))) {
    Write-Host "Installing frontend dependencies (first run only) ..." -ForegroundColor Cyan
    Push-Location $frontend
    npm install
    Pop-Location
}

Write-Host "Starting frontend on http://localhost:3000 ..." -ForegroundColor Cyan
Set-Location $frontend
npm run dev
