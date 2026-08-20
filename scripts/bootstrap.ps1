<#
.SYNOPSIS
    One-command setup for the OCR workspace (Windows / PowerShell).

.DESCRIPTION
    Idempotent -- safe to re-run. Performs:
      1. Verify (or install) Python 3.11
      2. Create the backend virtualenv at apps/api/.venv
      3. Install the PaddleOCR stack in the correct order
      4. Download + warm the OCR models
      5. Install web dependencies

.PARAMETER SkipModels
    Skip the model download/warmup step (models download lazily on first OCR).

.PARAMETER SkipWeb
    Skip `npm install` for the frontend.

.PARAMETER Gpu
    Install the CUDA build of PaddlePaddle instead of the CPU build.

.EXAMPLE
    .\scripts\bootstrap.ps1
    .\scripts\bootstrap.ps1 -Gpu -SkipWeb
#>
[CmdletBinding()]
param(
    [switch]$SkipModels,
    [switch]$SkipWeb,
    [switch]$Gpu
)

$ErrorActionPreference = 'Stop'
$RepoRoot = Split-Path -Parent $PSScriptRoot
$ApiDir   = Join-Path $RepoRoot 'apps\api'
$WebDir   = Join-Path $RepoRoot 'apps\web'
$VenvDir  = Join-Path $ApiDir '.venv'
$VenvPy   = Join-Path $VenvDir 'Scripts\python.exe'

$PythonVersion   = '3.11.9'
$PythonInstaller = "python-$PythonVersion-amd64.exe"
$PythonUrl       = "https://www.python.org/ftp/python/$PythonVersion/$PythonInstaller"

function Write-Step($msg) { Write-Host "`n=== $msg ===" -ForegroundColor Cyan }
function Write-Ok($msg)   { Write-Host "  [ok] $msg" -ForegroundColor Green }
function Write-Warn($msg) { Write-Host "  [!!] $msg" -ForegroundColor Yellow }

# ---------------------------------------------------------------- 1. Python
Write-Step 'Locating Python 3.11'

function Find-Python311 {
    $candidates = @(
        "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe",
        "$env:ProgramFiles\Python311\python.exe",
        'C:\Python311\python.exe'
    )
    foreach ($c in $candidates) { if (Test-Path $c) { return $c } }

    # Try the py launcher.
    $py = Get-Command py -ErrorAction SilentlyContinue
    if ($py) {
        try {
            $path = (& py -3.11 -c "import sys; print(sys.executable)" 2>$null)
            if ($LASTEXITCODE -eq 0 -and $path -and (Test-Path $path)) { return $path }
        } catch { }
    }

    # Any python on PATH that reports 3.11.
    $p = Get-Command python -ErrorAction SilentlyContinue
    if ($p) {
        $v = (& $p.Source -c "import sys; print('%d.%d' % sys.version_info[:2])" 2>$null)
        if ($v -eq '3.11') { return $p.Source }
    }
    return $null
}

$SystemPython = Find-Python311

if (-not $SystemPython) {
    Write-Warn "Python 3.11 not found. Downloading $PythonInstaller (~25 MB)..."
    $tmp = Join-Path $env:TEMP $PythonInstaller
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    Invoke-WebRequest -Uri $PythonUrl -OutFile $tmp -UseBasicParsing

    Write-Host '  Installing (per-user, no admin required)...'
    $proc = Start-Process -FilePath $tmp -Wait -PassThru -ArgumentList `
        '/quiet', 'InstallAllUsers=0', 'PrependPath=1', 'Include_pip=1', `
        'Include_launcher=1', 'Include_test=0'
    if ($proc.ExitCode -ne 0) { throw "Python installer failed (exit $($proc.ExitCode))" }

    $SystemPython = Find-Python311
    if (-not $SystemPython) { throw 'Python 3.11 still not found after install.' }
}
Write-Ok "Python: $SystemPython ($(& $SystemPython --version))"

# ------------------------------------------------------------------ 2. venv
Write-Step 'Creating virtual environment'
if (-not (Test-Path $VenvPy)) {
    & $SystemPython -m venv $VenvDir
    Write-Ok "Created $VenvDir"
} else {
    Write-Ok 'Virtualenv already exists'
}

& $VenvPy -m pip install --upgrade pip setuptools wheel --quiet
Write-Ok "pip $((& $VenvPy -m pip --version).Split(' ')[1])"

# ------------------------------------------------------------ 3. Python deps
Write-Step 'Installing Python dependencies'
Write-Host '  This downloads ~2-3 GB and takes several minutes on a cold cache.'

# Order matters: the framework must land before the toolkit so pip does not
# resolve an incompatible paddlepaddle/paddleocr pair.
if ($Gpu) {
    Write-Host '  [1/2] paddlepaddle-gpu (CUDA 12.6)...'
    & $VenvPy -m pip install paddlepaddle-gpu==3.1.0 `
        -i https://www.paddlepaddle.org.cn/packages/stable/cu126/
} else {
    Write-Host '  [1/2] paddlepaddle (CPU)...'
    & $VenvPy -m pip install paddlepaddle==3.1.0
}
if ($LASTEXITCODE -ne 0) { throw 'paddlepaddle install failed' }

Write-Host '  [2/2] application dependencies (from requirements-base.txt)...'
$reqBase = Join-Path $ApiDir 'requirements-base.txt'
& $VenvPy -m pip install -r $reqBase
if ($LASTEXITCODE -ne 0) { throw 'application dependency install failed' }

Write-Step 'Verifying imports'
& $VenvPy -c @'
import paddle, cv2, fitz, rapidfuzz, fastapi, numpy, paddleocr, sqlalchemy, alembic, bcrypt
print(f"  paddle      {paddle.__version__}")
print(f"  paddleocr   {paddleocr.__version__}")
print(f"  opencv      {cv2.__version__}")
print(f"  numpy       {numpy.__version__}")
print(f"  fastapi     {fastapi.__version__}")
print(f"  sqlalchemy  {sqlalchemy.__version__}")
'@
if ($LASTEXITCODE -ne 0) { throw 'Import verification failed' }
Write-Ok 'All imports resolve'

# ----------------------------------------------------------------- 4. models
if (-not $SkipModels) {
    Write-Step 'Downloading and warming OCR models'
    Write-Host '  First run fetches ~200 MB of model weights.'
    Push-Location $ApiDir
    try {
        & $VenvPy cli.py warmup
        if ($LASTEXITCODE -ne 0) { Write-Warn 'Warmup failed; models will load on first use.' }
        else { Write-Ok 'Models cached' }
    } finally {
        Pop-Location
    }
} else {
    Write-Warn 'Skipping model download (-SkipModels)'
}

# -------------------------------------------------------------------- 5. web
if (-not $SkipWeb) {
    Write-Step 'Installing web & workspace dependencies'
    if (Test-Path (Join-Path $RepoRoot 'package.json')) {
        Push-Location $RepoRoot
        try {
            npm install
            if ($LASTEXITCODE -ne 0) { throw 'npm install failed' }
            Write-Ok 'Web and workspace dependencies installed'
        } finally {
            Pop-Location
        }
    } else {
        Write-Warn 'package.json not found; skipping'
    }
} else {
    Write-Warn 'Skipping web install (-SkipWeb)'
}

# ------------------------------------------------------------------ 6. .env & data
Write-Step 'Configuration & Storage'
$envFile    = Join-Path $RepoRoot '.env'
$envExample = Join-Path $RepoRoot '.env.example'
if ((Test-Path $envExample) -and (-not (Test-Path $envFile))) {
    Copy-Item $envExample $envFile
    Write-Ok 'Created .env from .env.example'
} else {
    Write-Ok '.env already present (or no template to copy)'
}

$dataDir = Join-Path $RepoRoot 'data'
if (-not (Test-Path $dataDir)) {
    New-Item -ItemType Directory -Path $dataDir -Force | Out-Null
    Write-Ok 'Created data/ directory'
} else {
    Write-Ok 'data/ directory exists'
}

# ------------------------------------------------------------------ 7. Database & Views
Write-Step 'Initializing Database & Schema Views'
Push-Location $ApiDir
try {
    & $VenvPy -c "from app.db import init_db; from app.services.sqlite_views import ensure_sqlite_views, engine; init_db(); ensure_sqlite_views(engine); print('  Database schema and SQL views initialized.')"
    Write-Ok 'Database & Views ready'
} catch {
    Write-Warn "Database init warning: $_"
} finally {
    Pop-Location
}

Write-Host "`n=== Setup complete ===" -ForegroundColor Green
Write-Host @"

  Start everything:      .\run.bat  or  npm run dev  or  .\scripts\dev.ps1
  Frontend Web UI:       http://localhost:3001 (or http://localhost:3000)
  Backend API Docs:      http://localhost:8080/docs (or http://localhost:8000/docs)
  Default Login:         admin / Admin@123456

"@ -ForegroundColor Gray
