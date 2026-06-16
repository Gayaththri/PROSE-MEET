# Start PROSE-MEET backend + frontend for a local interview demo (Windows PowerShell).
# Usage: from repo root →  .\scripts\start-interview-demo.ps1

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Backend = Join-Path $Root "backend"
$Frontend = Join-Path $Root "frontend\prose-meet-frontend"
$VenvActivate = Join-Path $Backend ".venv\Scripts\Activate.ps1"

function Test-Command($Name) {
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        Write-Host "ERROR: '$Name' not found on PATH." -ForegroundColor Red
        exit 1
    }
}

Write-Host "PROSE-MEET interview demo" -ForegroundColor Cyan
Write-Host "Repository: $Root`n"

Test-Command python
Test-Command npm
Test-Command ffmpeg

if (-not (Test-Path $VenvActivate)) {
    Write-Host "WARNING: backend\.venv not found. Create it first:" -ForegroundColor Yellow
    Write-Host "  cd backend; python -m venv .venv; .\.venv\Scripts\Activate.ps1; pip install -r requirements.txt"
}

$backendCmd = @"
Set-Location '$Backend'
if (Test-Path '$VenvActivate') { & '$VenvActivate' }
Write-Host 'Starting backend on http://127.0.0.1:8000' -ForegroundColor Green
python -m uvicorn main:app --reload
"@

$frontendCmd = @"
Set-Location '$Frontend'
Write-Host 'Starting frontend on http://localhost:5173' -ForegroundColor Green
npm run dev
"@

Start-Process powershell -ArgumentList "-NoExit", "-Command", $backendCmd
Start-Sleep -Seconds 2
Start-Process powershell -ArgumentList "-NoExit", "-Command", $frontendCmd

Write-Host ""
Write-Host "Two terminals opened." -ForegroundColor Green
Write-Host "  1. Wait for Uvicorn + Vite to finish starting"
Write-Host "  2. Open  http://localhost:5173"
Write-Host "  3. Health check:  http://127.0.0.1:8000/health"
Write-Host "  4. API docs:       http://127.0.0.1:8000/docs"
Write-Host ""
Write-Host "Full guide: INTERVIEW_DEMO.md" -ForegroundColor Cyan
