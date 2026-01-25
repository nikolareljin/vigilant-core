#!/usr/bin/env bash
set -euo pipefail

REPO_URL_DEFAULT="https://github.com/nikolareljin/vigilant-core.git"
TARGET_DIR_DEFAULT="vigilant-core"

REPO_URL="${REPO_URL:-$REPO_URL_DEFAULT}"
TARGET_DIR="${TARGET_DIR:-$TARGET_DIR_DEFAULT}"

if [[ ! -d "$TARGET_DIR" ]]; then
  if ! command -v git >/dev/null 2>&1; then
    echo "git is required. Please install git and retry." >&2
    exit 1
  fi
  echo "Cloning $REPO_URL into $TARGET_DIR"
  git clone "$REPO_URL" "$TARGET_DIR"
fi

cd "$TARGET_DIR"

if [[ -f ./update ]]; then
  ./update
else
  git submodule update --init --recursive
fi

PYTHON_BIN=${PYTHON_BIN:-python3}
if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "Python 3 is required. Please install Python 3.10+ and retry." >&2
  exit 1
fi

if [[ ! -d venv ]]; then
  "$PYTHON_BIN" -m venv venv
fi

# shellcheck disable=SC1091
source venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt

python -m src.web_app
