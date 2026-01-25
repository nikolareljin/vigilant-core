#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

# Ensure Ollama is installed (model pull handled programmatically in app)
if ! command -v ollama >/dev/null 2>&1; then
  echo "Warning: ollama CLI not found. Install Ollama to enable LLM parsing." >&2
fi

if [ ! -d "venv" ]; then
  python3 -m venv venv
fi

# shellcheck disable=SC1091
source venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m src.web_app
