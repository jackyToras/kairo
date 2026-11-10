$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Test-Path ".venv")) {
    Write-Host "Creating Python virtual environment..." -ForegroundColor Cyan
    uv venv .venv
    uv pip install --python .venv\Scripts\python.exe -e ".[dev]"
}

if (-not (Test-Path "frontend\dist")) {
    Write-Host "Building frontend..." -ForegroundColor Cyan
    Push-Location frontend
    npm install
    npm run build
    Pop-Location
}

Write-Host "Starting Kairo on http://localhost:8000 ..." -ForegroundColor Green
.venv\Scripts\uvicorn.exe app.main:app --app-dir backend --host 0.0.0.0 --port 8000
