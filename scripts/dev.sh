#!/usr/bin/env bash
# ==============================================================================
# OCR Workspace - Dev Server Runner (Linux / macOS / WSL)
#
# Starts FastAPI backend on http://localhost:8000
# Starts Next.js frontend on http://localhost:3000
# Cleanly terminates both on Ctrl+C.
# ==============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
API_DIR="$REPO_ROOT/apps/api"
WEB_DIR="$REPO_ROOT/apps/web"
VENV_PY="$API_DIR/.venv/bin/python"

RELOAD=false
for arg in "$@"; do
  case $arg in
    --reload) RELOAD=true ;;
  esac
done

if [ ! -f "$VENV_PY" ]; then
  echo -e "\033[1;31m[ERROR]\033[0m Backend virtual environment not found at $VENV_PY."
  echo "Please run ./setup.sh (or bash scripts/bootstrap.sh) first."
  exit 1
fi

BACKEND_PORT="${BACKEND_PORT:-8080}"
WEB_PORT="${PORT:-3001}"

echo -e "\033[1;36m===================================================\033[0m"
echo -e "\033[1;36m    OCR Workspace - Starting Local Servers         \033[0m"
echo -e "\033[1;36m===================================================\033[0m\n"

# PIDs to cleanup
BACKEND_PID=""
FRONTEND_PID=""

cleanup() {
  echo -e "\n\033[1;33mShutting down servers...\033[0m"
  if [ -n "$BACKEND_PID" ] && kill -0 "$BACKEND_PID" 2>/dev/null; then
    kill "$BACKEND_PID" 2>/dev/null || true
  fi
  if [ -n "$FRONTEND_PID" ] && kill -0 "$FRONTEND_PID" 2>/dev/null; then
    kill "$FRONTEND_PID" 2>/dev/null || true
  fi
  wait 2>/dev/null || true
  echo -e "\033[1;32mAll servers stopped.\033[0m"
  exit 0
}

trap cleanup SIGINT SIGTERM EXIT

# 1. Start Backend
echo -e "\033[1;32m[backend]\033[0m  FastAPI running on http://localhost:$BACKEND_PORT (API Docs: http://localhost:$BACKEND_PORT/docs)"
UVICORN_ARGS=("-m" "uvicorn" "app.main:app" "--port" "$BACKEND_PORT" "--host" "0.0.0.0")
if [ "$RELOAD" = true ]; then
  UVICORN_ARGS+=("--reload")
  echo -e "\033[1;33mAuto-reload ON - editing a .py file will restart the backend.\033[0m"
fi

(cd "$API_DIR" && "$VENV_PY" "${UVICORN_ARGS[@]}") &
BACKEND_PID=$!

# 2. Start Frontend
if [ -f "$WEB_DIR/package.json" ]; then
  echo -e "\033[1;35m[frontend]\033[0m Next.js running on http://localhost:$WEB_PORT"
  (cd "$WEB_DIR" && BACKEND_URL="http://localhost:$BACKEND_PORT" npm run dev -- -p "$WEB_PORT") &
  FRONTEND_PID=$!
else
  echo -e "\033[1;33mapps/web/package.json not found. Running backend only.\033[0m"
fi

echo -e "\n\033[1;36mReady! Open \033[4mhttp://localhost:$WEB_PORT\033[0m in your browser.\033[0m"
echo -e "Press Ctrl+C in this terminal to stop all servers.\n"

# Wait for background processes
wait
