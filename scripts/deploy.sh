#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT_HELPERS_DIR="${SCRIPT_HELPERS_DIR:-$SCRIPT_DIR/script-helpers}"

if [[ ! -f "$SCRIPT_HELPERS_DIR/helpers.sh" ]]; then
  echo "script-helpers not found. Initializing submodules..." >&2
  git submodule update --init --recursive
fi

if [[ ! -f "$SCRIPT_HELPERS_DIR/helpers.sh" ]]; then
  echo "script-helpers not found after submodule init." >&2
  exit 1
fi

# shellcheck disable=SC1091
source "$SCRIPT_HELPERS_DIR/helpers.sh"
shlib_import logging

print_info "Deploy step placeholder for VigilantCore."
print_info "Use scripts/build.sh to produce release artifacts in dist/."
