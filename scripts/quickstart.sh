#!/usr/bin/env bash
set -euo pipefail

REPO_URL_DEFAULT="https://github.com/nikolareljin/vigilant-core.git"
TARGET_DIR_DEFAULT="vigilant-core"

REPO_URL="${REPO_URL:-$REPO_URL_DEFAULT}"
TARGET_DIR="${TARGET_DIR:-$TARGET_DIR_DEFAULT}"

prompt_install() {
  local name="$1"
  read -r -p "Missing ${name}. Install now? [y/N]: " reply
  if [[ "$reply" != "y" && "$reply" != "Y" ]]; then
    echo "Cannot continue without ${name}."
    exit 1
  fi
}

install_deps() {
  local missing=("$@")
  if [[ "${#missing[@]}" -eq 0 ]]; then
    return
  fi
  prompt_install "${missing[*]}"
  if command -v apt-get >/dev/null 2>&1; then
    sudo apt-get update
    sudo apt-get install -y python3 python3-venv python3-pip git
  elif command -v dnf >/dev/null 2>&1; then
    sudo dnf install -y python3 python3-pip git
  elif command -v yum >/dev/null 2>&1; then
    sudo yum install -y python3 python3-pip git
  elif command -v pacman >/dev/null 2>&1; then
    sudo pacman -S --noconfirm python python-pip git
  elif command -v brew >/dev/null 2>&1; then
    brew install python git
  else
    echo "No supported package manager found. Please install: ${missing[*]}"
    exit 1
  fi
}

missing_deps=()
if ! command -v git >/dev/null 2>&1; then
  missing_deps+=("git")
fi

PYTHON_BIN=${PYTHON_BIN:-python3}
if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  missing_deps+=("python3")
fi

install_deps "${missing_deps[@]}"

if [[ ! -d "$TARGET_DIR" ]]; then
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

if [[ ! -d venv ]]; then
  "$PYTHON_BIN" -m venv venv
fi

# shellcheck disable=SC1091
source venv/bin/activate
python3 -m pip install --upgrade pip
pip3 install -r requirements.txt

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
      exit 1
    fi
  else
    echo "Unsupported OS. Please install Ollama manually from https://ollama.com"
    exit 1
  fi
fi

# Start Ollama service in background
if ! pgrep -x "ollama" >/dev/null; then
  echo "Starting Ollama service..."
  ollama serve >/dev/null 2>&1 &
  sleep 3
fi

# Download default model if not already present
DEFAULT_MODEL="llama3.2:1b"
if ! ollama list | grep -q "${DEFAULT_MODEL}"; then
  echo "Downloading Ollama model: ${DEFAULT_MODEL}..."
  ollama pull "${DEFAULT_MODEL}"
else
  echo "Ollama model ${DEFAULT_MODEL} already available."
fi

python3 -m src.web_app
