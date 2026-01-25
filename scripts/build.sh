#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
SCRIPT_HELPERS_DIR="${SCRIPT_HELPERS_DIR:-$SCRIPT_DIR/script-helpers}"

if [[ ! -f "$SCRIPT_HELPERS_DIR/helpers.sh" ]]; then
  echo "script-helpers not found. Run ./update to initialize submodules." >&2
  exit 1
fi

# shellcheck disable=SC1091
source "$SCRIPT_HELPERS_DIR/helpers.sh"
shlib_import logging os

print_info "Building VigilantCore executable (PyInstaller)."
cd "$ROOT_DIR"
python -m pip install --upgrade pip
pip install -r requirements.txt
pyinstaller --onefile --windowed src/main.py --name VigilantCore
print_success "Build complete. See dist/VigilantCore"
