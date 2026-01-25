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
shlib_import logging

print_info "No automated tests yet. Running smoke import check."
cd "$ROOT_DIR"
python -m pip install -r requirements.txt
python -c "import engine.monitor, engine.parser, utils.database, utils.config; print('smoke ok')"
print_success "Smoke check complete."
