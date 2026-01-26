#!/usr/bin/env bash
#
# VigilantCore Launcher (Linux/macOS)
#
# Usage:
#   ./run.sh          # Start web dashboard (default)
#   ./run.sh web      # Start web dashboard
#   ./run.sh qt       # Start Qt desktop app
#   ./run.sh both     # Start both (web in background)
#   ./run.sh stop     # Stop all instances
#   ./run.sh status   # Check status
#

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

# Create venv if needed
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

# Activate and run
source venv/bin/activate
python -m pip install -q --upgrade pip 2>/dev/null || true

# Check if dependencies are installed
if ! python -c "import flask, PySide6, ollama" 2>/dev/null; then
    echo "Installing dependencies..."
    python -m pip install -q -r requirements.txt
fi

# Run the launcher
exec python vigilant.py "${1:-web}"
