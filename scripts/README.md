# Scripts

These scripts use the `script-helpers` submodule for consistent logging and helpers.

## Setup
```bash
./update
```

## Quickstart Scripts

One-command setup that handles everything: cloning/updating the repository, creating virtual environment, installing dependencies, installing Ollama CLI, downloading AI models, and launching the application.

### Linux/macOS
```bash
./scripts/quickstart.sh
```

### Windows

**PowerShell (Recommended):**
```powershell
.\scripts\quickstart.ps1
```

**Command Prompt:**
```cmd
.\scripts\quickstart.bat
```

**What it does:**
- ✅ Checks for Python and Git (installs if missing on some platforms)
- ✅ Clones repository if not present
- ✅ Updates repository if already cloned
- ✅ Creates and activates virtual environment
- ✅ Installs Python dependencies
- ✅ Installs Ollama CLI (via official installer or winget)
- ✅ Starts Ollama service
- ✅ Downloads default AI model (llama3.2:1b)
- ✅ Launches the web dashboard at http://127.0.0.1:8765

## Other Commands
- `./scripts/build.sh` — build a PyInstaller executable into `dist/`
- `./scripts/test.sh` — run a smoke import check
- `./scripts/deploy.sh` — placeholder for release automation
