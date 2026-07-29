<#
.SYNOPSIS
    Launch FastAPI backend and Next.js frontend concurrently.
.PARAMETER Reload
    Restart the backend whenever a .py file changes.

    OFF by default, and that default matters. Extraction runs in a worker pool
    *inside* the API process and a 12-page roll takes several minutes. The
    reloader kills that process on any source edit, so saving a file mid-run
    takes the job down with it -- the job row is left "running" with no process
    behind it, and the next boot marks it "Interrupted by a server restart;
    re-run the extraction." Nothing can resume it; the pages are simply lost.

    Killing a process with PaddleOCR's native threads mid-inference also faults
    on the way out (Windows 0xC0000005), so the crash that follows an edit
    looks like an OCR bug rather than the reload it actually is.

    Turn it on while working on request handlers; leave it off while extracting.
#>
param(
    [switch]$Reload
)
$ErrorActionPreference = 'Stop'
$RepoRoot = Split-Path -Parent $PSScriptRoot
$ApiDir   = Join-Path $RepoRoot 'apps\api'
$WebDir   = Join-Path $RepoRoot 'apps\web'
$VenvPy   = Join-Path $ApiDir '.venv\Scripts\python.exe'

Write-Host "=== Starting OCR Workspace Dev Servers ===" -ForegroundColor Cyan

if (-not (Test-Path $VenvPy)) {
    throw "Backend virtualenv not found at $VenvPy. Run scripts/bootstrap.ps1 first."
}

$uvicornArgs = "-m uvicorn app.main:app --port 8000"
if ($Reload) {
    $uvicornArgs += " --reload"
    Write-Host "Auto-reload ON - editing a .py file will kill any extraction in progress." -ForegroundColor Yellow
}

Write-Host "Starting FastAPI backend on http://localhost:8000 ..." -ForegroundColor Green
$backendProcess = Start-Process -FilePath $VenvPy `
    -ArgumentList $uvicornArgs `
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
