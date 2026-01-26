# Installation Guide

VigilantCore is designed to be easy to install on any platform. Choose the method that works best for you.

## Requirements

- **Python 3.10+** (Python 3.11 or 3.12 recommended)
- **Ollama** installed and running locally
- **8GB+ RAM** recommended (can run on less with lighter model)

## Quick Start

### One-Command Install (Recommended)

**Linux/macOS:**
```bash
curl -fsSL https://raw.githubusercontent.com/nikolareljin/vigilant-core/main/scripts/quickstart.sh | bash
```

or with wget:
```bash
wget -qO- https://raw.githubusercontent.com/nikolareljin/vigilant-core/main/scripts/quickstart.sh | bash
```

**Windows (PowerShell):**
```powershell
git clone https://github.com/nikolareljin/vigilant-core.git
cd vigilant-core
.\run.ps1
```

### Manual Installation

1. **Clone the repository:**
   ```bash
   git clone https://github.com/nikolareljin/vigilant-core.git
   cd vigilant-core
   ```

2. **Run the launcher script:**

   **Linux/macOS:**
   ```bash
   ./run.sh
   ```

   **Windows CMD:**
   ```cmd
   run.bat
   ```

   **Windows PowerShell:**
   ```powershell
   .\run.ps1
   ```

The launcher will automatically:
- Create a Python virtual environment
- Install all dependencies
- Start the web dashboard

## Installing Ollama

VigilantCore requires Ollama for local AI processing.

### macOS
```bash
brew install ollama
ollama serve
```

### Linux
```bash
curl -fsSL https://ollama.ai/install.sh | sh
ollama serve
```

### Windows
Download from [ollama.ai](https://ollama.ai) and run the installer.

### Pull the Required Model

After installing Ollama, pull the model:
```bash
# For systems with 8GB+ RAM
ollama pull qwen2.5:7b

# For systems with less RAM
ollama pull qwen2.5:3b
```

## Running VigilantCore

### Available Commands

Use the unified launcher `vigilant.py`:

| Command | Description |
|---------|-------------|
| `python vigilant.py web` | Start web dashboard (default) |
| `python vigilant.py qt` | Start Qt desktop app |
| `python vigilant.py both` | Start both (web runs in background) |
| `python vigilant.py stop` | Stop all running instances |
| `python vigilant.py status` | Check what's running |

### Platform Scripts

For convenience, use the platform-specific scripts:

**Linux/macOS:**
```bash
./run.sh          # Start web (default)
./run.sh web      # Start web dashboard
./run.sh qt       # Start Qt desktop app
./run.sh both     # Start both
./run.sh stop     # Stop all
./run.sh status   # Check status
```

**Windows CMD:**
```cmd
run.bat           # Start web (default)
run.bat qt        # Start Qt app
run.bat stop      # Stop all
```

**Windows PowerShell:**
```powershell
.\run.ps1         # Start web (default)
.\run.ps1 qt      # Start Qt app
.\run.ps1 stop    # Stop all
```

## Accessing the Interface

### Web Dashboard
Open your browser to: **http://127.0.0.1:8765**

Additional views:
- Settings: http://127.0.0.1:8765 (main page)
- Data/Alerts: http://127.0.0.1:8765/data

### Qt Desktop App
The Qt app opens automatically when launched with the `qt` or `both` command.

## Troubleshooting

### "externally-managed-environment" Error
This occurs on modern Python installations (PEP 668). The launcher scripts handle this automatically by using `python -m pip` instead of `pip` directly.

### Ollama Model Not Found
Ensure Ollama is running and the model is pulled:
```bash
ollama serve  # Start Ollama if not running
ollama pull qwen2.5:7b
```

### Port Already in Use
If port 8765 is in use, stop any existing instance:
```bash
python vigilant.py stop
```

### Missing Dependencies
Force reinstall dependencies:
```bash
rm -rf venv
./run.sh  # Will recreate venv and install deps
```

## Developer Setup

For development, set up manually:

```bash
python -m venv venv
source venv/bin/activate  # Linux/macOS
# or: venv\Scripts\activate  # Windows

pip install -r requirements.txt
python vigilant.py web
```
