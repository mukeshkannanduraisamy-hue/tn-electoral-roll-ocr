#!/usr/bin/env bash
# ==============================================================================
# OCR Workspace - One-Command Bootstrap (Linux / macOS / WSL)
#
# Idempotent -- safe to re-run. Performs:
#   1. Check / find Python 3.10+ (3.11 recommended)
#   2. Check system dependencies (libgl1, libgomp1, fonts)
#   3. Create backend virtualenv at apps/api/.venv
#   4. Install PaddleOCR stack and Python dependencies
#   5. Download and warm OCR models
#   6. Install Node / npm workspace dependencies
#   7. Set up .env and data directory
# ==============================================================================

set -euo pipefail

# Flags
SKIP_MODELS=false
SKIP_WEB=false
USE_GPU=false

for arg in "$@"; do
  case $arg in
    --skip-models) SKIP_MODELS=true ;;
    --skip-web)    SKIP_WEB=true ;;
    --gpu)         USE_GPU=true ;;
    -h|--help)
      echo "Usage: ./scripts/bootstrap.sh [--gpu] [--skip-models] [--skip-web]"
      exit 0
      ;;
  esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
API_DIR="$REPO_ROOT/apps/api"
WEB_DIR="$REPO_ROOT/apps/web"
VENV_DIR="$API_DIR/.venv"
VENV_PY="$VENV_DIR/bin/python"

step() { echo -e "\n\033[1;36m=== $1 ===\033[0m"; }
ok()   { echo -e "  \033[1;32m[ok]\033[0m $1"; }
warn() { echo -e "  \033[1;33m[!!]\033[0m $1"; }
err()  { echo -e "  \033[1;31m[error]\033[0m $1"; exit 1; }

# ------------------------------------------------------------------ 1. Python
step "Locating Python"

find_python() {
  for cmd in python3.11 python3.10 python3 python; do
    if command -v "$cmd" >/dev/null 2>&1; then
      ver=$("$cmd" -c "import sys; print(f'{sys.version_info[0]}.{sys.version_info[1]}')" 2>/dev/null || true)
      if [ "$ver" = "3.11" ] || [ "$ver" = "3.10" ] || [ "$ver" = "3.12" ]; then
        command -v "$cmd"
        return 0
      fi
    fi
  done
  return 1
}

SYSTEM_PYTHON=$(find_python || true)

if [ -z "$SYSTEM_PYTHON" ]; then
  err "Python 3.10, 3.11, or 3.12 is required but was not found. Please install Python 3.11:\n  Ubuntu/Debian: sudo apt update && sudo apt install -y python3.11 python3.11-venv python3-pip\n  macOS: brew install python@3.11"
fi

ok "Python: $SYSTEM_PYTHON ($($SYSTEM_PYTHON --version))"

# -------------------------------------------------------- 2. System libraries
step "Checking system prerequisites"

if [ "$(uname -s)" = "Linux" ]; then
  # Check for apt-get
  if command -v dpkg-query >/dev/null 2>&1; then
    MISSING_PKGS=()
    for pkg in libgl1 libgomp1 fonts-noto-core curl; do
      if ! dpkg-query -W -f='${Status}' "$pkg" 2>/dev/null | grep -q "ok installed"; then
        MISSING_PKGS+=("$pkg")
      fi
    done
    if [ ${#MISSING_PKGS[@]} -gt 0 ]; then
      warn "Some recommended packages are missing: ${MISSING_PKGS[*]}"
      warn "If you run into import errors with cv2 or paddle, install them with:"
      warn "  sudo apt update && sudo apt install -y ${MISSING_PKGS[*]}"
    else
      ok "System packages installed"
    fi
  fi
fi

# ------------------------------------------------------------------ 3. venv
step "Setting up virtual environment"

if [ ! -f "$VENV_PY" ]; then
  "$SYSTEM_PYTHON" -m venv "$VENV_DIR"
  ok "Created $VENV_DIR"
else
  ok "Virtual environment already exists"
fi

"$VENV_PY" -m pip install --upgrade pip setuptools wheel --quiet
ok "pip updated"

# ----------------------------------------------------------- 4. Dependencies
step "Installing Python dependencies"
echo "  Downloading dependencies (may take several minutes on cold cache)..."

if [ "$USE_GPU" = true ]; then
  echo "  [1/2] paddlepaddle-gpu (CUDA 12.6)..."
  "$VENV_PY" -m pip install paddlepaddle-gpu==3.1.0 -i https://www.paddlepaddle.org.cn/packages/stable/cu126/
else
  echo "  [1/2] paddlepaddle (CPU)..."
  "$VENV_PY" -m pip install paddlepaddle==3.1.0
fi

echo "  [2/2] application dependencies (from requirements-base.txt)..."
"$VENV_PY" -m pip install -r "$API_DIR/requirements-base.txt"
ok "Python dependencies installed"

step "Verifying imports"
"$VENV_PY" -c "
import paddle, cv2, fitz, rapidfuzz, fastapi, numpy, paddleocr, sqlalchemy, alembic, bcrypt
print(f'  paddle      {paddle.__version__}')
print(f'  paddleocr   {paddleocr.__version__}')
print(f'  opencv      {cv2.__version__}')
print(f'  fastapi     {fastapi.__version__}')
print(f'  sqlalchemy  {sqlalchemy.__version__}')
"
ok "All core imports resolve"

# ----------------------------------------------------------------- 5. Models
if [ "$SKIP_MODELS" = false ]; then
  step "Downloading and warming OCR models"
  echo "  Fetching model weights (~200 MB)..."
  (cd "$API_DIR" && "$VENV_PY" cli.py warmup) || warn "Warmup finished with warnings; models will load on first use."
  ok "Models cached"
else
  warn "Skipping model download (--skip-models)"
fi

# -------------------------------------------------------------------- 6. Web
if [ "$SKIP_WEB" = false ]; then
  step "Installing Node & workspace dependencies"
  if command -v npm >/dev/null 2>&1; then
    (cd "$REPO_ROOT" && npm install)
    ok "Node dependencies installed"
  else
    warn "npm not found. Please install Node.js 20+ to run the web frontend."
  fi
else
  warn "Skipping web install (--skip-web)"
fi

# ------------------------------------------------------------ 7. Config & Data
step "Configuration & Storage"
ENV_FILE="$REPO_ROOT/.env"
ENV_EXAMPLE="$REPO_ROOT/.env.example"
if [ ! -f "$ENV_FILE" ] && [ -f "$ENV_EXAMPLE" ]; then
  cp "$ENV_EXAMPLE" "$ENV_FILE"
  ok "Created .env from .env.example"
else
  ok ".env already present"
fi

DATA_DIR="$REPO_ROOT/data"
mkdir -p "$DATA_DIR"
ok "data/ directory ready"

echo -e "\n\033[1;32m=== Setup complete ===\033[0m"
echo -e "
  Start everything:      ./run.sh  or  npm run dev  or  bash scripts/dev.sh
  Backend only:          apps/api/.venv/bin/python -m uvicorn app.main:app --reload --port 8000
  Frontend only:         npm run dev --workspace @ocr-workspace/web
  CLI extraction:        apps/api/.venv/bin/python apps/api/cli.py extract \"<file.pdf>\"
"
