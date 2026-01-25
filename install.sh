#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

PYTHON_BIN=${PYTHON_BIN:-python3}

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "Python 3 is required. Please install Python 3.10+ and retry."
  exit 1
fi

if ! command -v ollama >/dev/null 2>&1; then
  echo "Ollama not found. Installing in background..."
  case "$(uname -s)" in
    Linux)
      (curl -fsSL https://ollama.com/install.sh | sh) >/tmp/ollama_install.log 2>&1 &
      ;;
    Darwin)
      if command -v brew >/dev/null 2>&1; then
        (brew install ollama/tap/ollama) >/tmp/ollama_install.log 2>&1 &
      else
        echo "Homebrew not found. Install Ollama from https://ollama.com/download and re-run."
      fi
      ;;
    *)
      echo "Unsupported OS for automatic Ollama install. Install from https://ollama.com/download."
      ;;
  esac
fi

if [ ! -d "venv" ]; then
  "$PYTHON_BIN" -m venv venv
fi

# shellcheck disable=SC1091
source venv/bin/activate

python -m pip install --upgrade pip
pip install -r requirements.txt

python -m src.web_app
