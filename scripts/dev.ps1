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

# Load .env file if present
$envFile = Join-Path $RepoRoot '.env'
if (Test-Path $envFile) {
    Get-Content $envFile | ForEach-Object {
        $line = $_.Trim()
        if ($line -and -not $line.StartsWith("#") -and $line.Contains("=")) {
            $parts = $line.Split("=", 2)
            $k = $parts[0].Trim()
            $v = $parts[1].Trim().Trim('"').Trim("'")
            if (-not (Get-Item "env:$k" -ErrorAction SilentlyContinue)) {
                Set-Item "env:$k" $v
            }
        }
    }
}

$SerenaDir = Join-Path $RepoRoot 'apps\serena-ocr'
$serenaPort = if ($env:SERENA_PORT) { $env:SERENA_PORT } else { "3002" }

$backendHost = if ($env:BACKEND_HOST) { $env:BACKEND_HOST } else { "127.0.0.1" }
$backendPort = if ($env:BACKEND_PORT) { $env:BACKEND_PORT } else { "8080" }
$webHost     = if ($env:HOST) { $env:HOST } else { "127.0.0.1" }
$webPort     = if ($env:PORT) { $env:PORT } else { "3000" }
$backendUrl  = if ($env:BACKEND_URL) { $env:BACKEND_URL } else { "http://$($backendHost):$($backendPort)" }

Write-Host "===================================================" -ForegroundColor Cyan
Write-Host "    OCR Workspace - Starting Local Servers         " -ForegroundColor Cyan
Write-Host "===================================================" -ForegroundColor Cyan
Write-Host ""

if (-not (Test-Path $VenvPy)) {
    throw "Backend virtualenv not found at $VenvPy. Run setup.bat (or .\scripts\bootstrap.ps1) first."
}

$uvicornArgs = "-m uvicorn app.main:app --host $backendHost --port $backendPort"
if ($Reload) {
    $uvicornArgs += " --reload"
    Write-Host "Auto-reload ON - editing a .py file will restart the backend." -ForegroundColor Yellow
}

Write-Host "[backend]  FastAPI running on      http://$($backendHost):$($backendPort) (API Docs: http://$($backendHost):$($backendPort)/docs)" -ForegroundColor Green
$backendProcess = Start-Process -FilePath $VenvPy `
    -ArgumentList $uvicornArgs `
    -WorkingDirectory $ApiDir `
    -PassThru

if (Test-Path (Join-Path $WebDir "package.json")) {
    Write-Host "[web-ui]   Next.js running on     http://$($webHost):$($webPort)" -ForegroundColor Magenta
    $env:HOST = $webHost
    $env:PORT = $webPort
    $env:BACKEND_URL = $backendUrl
    $env:BACKEND_HOST = $backendHost
    $env:BACKEND_PORT = $backendPort
    $frontendProcess = Start-Process -FilePath "npm.cmd" `
        -ArgumentList "run dev -- -H $webHost -p $webPort" `
        -WorkingDirectory $WebDir `
        -PassThru
}

if (Test-Path (Join-Path $SerenaDir "package.json")) {
    Write-Host "[serena]   Serena OCR running on  http://$($webHost):$($serenaPort)" -ForegroundColor Cyan
    $env:HOST = $webHost
    $env:PORT = $serenaPort
    $env:BACKEND_URL = $backendUrl
    $env:BACKEND_HOST = $backendHost
    $env:BACKEND_PORT = $backendPort
    $serenaProcess = Start-Process -FilePath "npm.cmd" `
        -ArgumentList "run dev -- -H $webHost -p $serenaPort" `
        -WorkingDirectory $SerenaDir `
        -PassThru
}

$displayHost = if ($webHost -eq "0.0.0.0") { "localhost" } else { $webHost }
Write-Host "`n✨ Serena Batch OCR Ready: http://$($displayHost):$($serenaPort)" -ForegroundColor Cyan
Write-Host "📄 Main Electoral UI Ready: http://$($displayHost):$($webPort)" -ForegroundColor Magenta
Write-Host "Press Ctrl+C or close window to stop.`n" -ForegroundColor Gray
