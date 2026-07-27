<#
.SYNOPSIS
    Launch FastAPI backend and Next.js frontend concurrently.
#>
$ErrorActionPreference = 'Stop'
$RepoRoot = Split-Path -Parent $PSScriptRoot
$ApiDir   = Join-Path $RepoRoot 'apps\api'
$WebDir   = Join-Path $RepoRoot 'apps\web'
$VenvPy   = Join-Path $ApiDir '.venv\Scripts\python.exe'

Write-Host "=== Starting OCR Workspace Dev Servers ===" -ForegroundColor Cyan

if (-not (Test-Path $VenvPy)) {
    throw "Backend virtualenv not found at $VenvPy. Run scripts/bootstrap.ps1 first."
}

Write-Host "Starting FastAPI backend on http://localhost:8000 ..." -ForegroundColor Green
$backendProcess = Start-Process -FilePath $VenvPy `
    -ArgumentList "-m uvicorn app.main:app --reload --port 8000" `
    -WorkingDirectory $ApiDir `
    -PassThru

if (Test-Path (Join-Path $WebDir "package.json")) {
    Write-Host "Starting Next.js frontend on http://localhost:3000 ..." -ForegroundColor Green
    $frontendProcess = Start-Process -FilePath "npm.cmd" `
        -ArgumentList "run dev" `
        -WorkingDirectory $WebDir `
        -PassThru
} else {
    Write-Host "Web app package.json not found yet in apps/web. Backend is active." -ForegroundColor Yellow
}

Write-Host "`nDev environment started! Press Ctrl+C in this terminal or close window to stop." -ForegroundColor Cyan
