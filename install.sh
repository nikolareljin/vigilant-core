#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

PYTHON_BIN=${PYTHON_BIN:-python3}

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "Python 3 is required. Please install Python 3.10+ and retry."
  exit 1
fi

# Install Ollama CLI if not present
if ! command -v ollama >/dev/null 2>&1; then
  echo "Installing Ollama CLI..."
  if [[ "$(uname)" == "Linux" ]]; then
    curl -fsSL https://ollama.com/install.sh | sh
  elif [[ "$(uname)" == "Darwin" ]]; then
    if command -v brew >/dev/null 2>&1; then
      brew install ollama
    else
      echo "Homebrew not found. Please install Ollama manually from https://ollama.com"
      echo "Download from: https://ollama.com/download"
      exit 1
    fi
  else
    echo "Unsupported OS. Please install Ollama manually from https://ollama.com"
    exit 1
  fi
fi

if [ ! -d "venv" ]; then
  "$PYTHON_BIN" -m venv venv
fi

# shellcheck disable=SC1091
source venv/bin/activate

python -m pip install --upgrade pip
pip install -r requirements.txt

# Start Ollama service in background if not running
if command -v ollama >/dev/null 2>&1 && ! pgrep -x "ollama" >/dev/null; then
  echo "Starting Ollama service..."
  ollama serve >/dev/null 2>&1 &
  sleep 3
fi

# Download default model if Ollama is available and model not present
if command -v ollama >/dev/null 2>&1; then
  DEFAULT_MODEL="llama3.2:1b"
  if ! ollama list 2>/dev/null | grep -q "${DEFAULT_MODEL}"; then
    echo "Downloading Ollama model: ${DEFAULT_MODEL}..."
    ollama pull "${DEFAULT_MODEL}" || echo "Warning: Failed to download model. You can download it later."
  else
    echo "Ollama model ${DEFAULT_MODEL} already available."
  fi
fi

python -m src.web_app
