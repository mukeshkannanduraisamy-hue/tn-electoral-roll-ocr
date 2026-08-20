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

$backendPort = if ($env:BACKEND_PORT) { $env:BACKEND_PORT } else { "8080" }
$webPort     = if ($env:PORT) { $env:PORT } else { "3001" }

Write-Host "===================================================" -ForegroundColor Cyan
Write-Host "    OCR Workspace - Starting Local Servers         " -ForegroundColor Cyan
Write-Host "===================================================" -ForegroundColor Cyan
Write-Host ""

if (-not (Test-Path $VenvPy)) {
    throw "Backend virtualenv not found at $VenvPy. Run setup.bat (or .\scripts\bootstrap.ps1) first."
}

$uvicornArgs = "-m uvicorn app.main:app --port $backendPort --host 0.0.0.0"
if ($Reload) {
    $uvicornArgs += " --reload"
    Write-Host "Auto-reload ON - editing a .py file will restart the backend." -ForegroundColor Yellow
}

Write-Host "[backend]  FastAPI running on http://localhost:$backendPort (API Docs: http://localhost:$backendPort/docs)" -ForegroundColor Green
$backendProcess = Start-Process -FilePath $VenvPy `
    -ArgumentList $uvicornArgs `
    -WorkingDirectory $ApiDir `
    -PassThru

if (Test-Path (Join-Path $WebDir "package.json")) {
    Write-Host "[frontend] Next.js running on http://localhost:$webPort" -ForegroundColor Magenta
    $env:BACKEND_URL = "http://localhost:$backendPort"
    $frontendProcess = Start-Process -FilePath "npm.cmd" `
        -ArgumentList "run dev -- -p $webPort" `
        -WorkingDirectory $WebDir `
        -PassThru
} else {
    Write-Host "Web app package.json not found in apps/web. Backend is active." -ForegroundColor Yellow
}

Write-Host "`nReady! Open http://localhost:$webPort in your browser." -ForegroundColor Cyan
Write-Host "Press Ctrl+C or close window to stop.`n" -ForegroundColor Gray
