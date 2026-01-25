#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT_HELPERS_DIR="${SCRIPT_HELPERS_DIR:-$SCRIPT_DIR/script-helpers}"
ALT_HELPERS_DIRS=(
  "$ROOT_DIR/vendor/script-helpers"
  "$ROOT_DIR/.github/ci-helpers/vendor/script-helpers"
)

if [[ ! -f "$SCRIPT_HELPERS_DIR/helpers.sh" ]]; then
  for alt in "${ALT_HELPERS_DIRS[@]}"; do
    if [[ -f "$alt/helpers.sh" ]]; then
      SCRIPT_HELPERS_DIR="$alt"
      break
    fi
  done
fi

if [[ ! -f "$SCRIPT_HELPERS_DIR/helpers.sh" ]]; then
  if [[ "${CI:-}" == "true" ]]; then
    echo "script-helpers not found in CI. Using fallback logging." >&2
    print_info() { echo "[info] $*"; }
    print_success() { echo "[ok] $*"; }
  else
    echo "script-helpers not found. Run ./update to initialize submodules." >&2
    exit 1
  fi
else
  # shellcheck disable=SC1091
  source "$SCRIPT_HELPERS_DIR/helpers.sh"
  shlib_import logging
fi

print_info "Deploy step placeholder for VigilantCore."
print_info "Use scripts/build.sh to produce release artifacts in dist/."
