#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

if [ ! -d "venv" ]; then
  python3 -m venv venv
fi

# shellcheck disable=SC1091
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# Install Ollama CLI if not present
if ! command -v ollama >/dev/null 2>&1; then
  echo "Installing Ollama CLI..."
  if [[ "$(uname)" == "Linux" ]]; then
    curl -fsSL https://ollama.com/install.sh | sh
  elif [[ "$(uname)" == "Darwin" ]]; then
    if command -v brew >/dev/null 2>&1; then
      brew install ollama
    else
      echo "Warning: Homebrew not found. Please install Ollama manually from https://ollama.com"
    fi
  fi
fi

# Start Ollama service in background if not running
if command -v ollama >/dev/null 2>&1 && ! pgrep -x "ollama" >/dev/null; then
  echo "Starting Ollama service..."
  ollama serve >/dev/null 2>&1 &
  sleep 2
fi

# Download default model if Ollama is available and model not present
if command -v ollama >/dev/null 2>&1; then
  DEFAULT_MODEL="llama3.2:1b"
  if ! ollama list 2>/dev/null | grep -q "${DEFAULT_MODEL}"; then
    echo "Downloading Ollama model: ${DEFAULT_MODEL}..."
    ollama pull "${DEFAULT_MODEL}" || echo "Warning: Failed to download model. You can download it later."
  fi
fi

python -m src.main
