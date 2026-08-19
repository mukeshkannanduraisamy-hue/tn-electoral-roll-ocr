#!/usr/bin/env bash
# ==============================================================================
# OCR Workspace - 1-Click Run (Linux / macOS / WSL)
# ==============================================================================
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
bash "$SCRIPT_DIR/scripts/dev.sh" "$@"
