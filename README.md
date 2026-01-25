# VigilantCore

VigilantCore is a local, cross-platform monitoring app that tracks **Impactful Events** for a specific subject, using a local LLM (Ollama) to score impact and generate predictive outcomes. It is designed to be simple for non-technical users while still offering an AI-driven, location-aware signal.

## User Journey (Spec-Driven)
1. **First Run**: Open the app, enter your subject, location, and optional RSS feeds/API key.
2. **Live Impact Feed**: The dashboard starts monitoring automatically and shows scored alerts.
3. **Impact Scoring**: Each alert is ranked from 1–10 based on relevance and urgency.
4. **Predictive Outcome**: For Watches/Warnings, the app predicts what happens next.
5. **Stay Informed**: New alerts appear in near real-time and are stored locally.

## Impact Score Logic (Overview)
- **1–3**: Low relevance or weak impact.
- **4–6**: Moderate impact or early advisory signals.
- **7–10**: High-impact events, warnings, or imminent disruptions.

## Location Matching
VigilantCore prefers local signals by combining:
- ZIP-based geocoding (offline) to a center point.
- Radius filtering (default 50km).
- Keyword matching on location name and ZIP.

## Requirements
- Python 3.10+
- Ollama installed and running locally

## Quick Start (Non-Technical)
1. Install Python.
2. Double-click `run.sh` (macOS/Linux) or `run.bat` (Windows).
3. Fill out the setup wizard and click **Save**.

## One-Command Bootstrap (curl/wget)
You can install and launch the web dashboard in a single command:

```bash
curl -fsSL https://raw.githubusercontent.com/nikolareljin/vigilant-core/main/scripts/quickstart.sh | bash
```

or with wget:

```bash
wget -qO- https://raw.githubusercontent.com/nikolareljin/vigilant-core/main/scripts/quickstart.sh | bash
```

This will:
- clone the repo (if missing),
- update submodules,
- create a venv,
- install dependencies,
- start the web dashboard at `http://127.0.0.1:8765`.

## Web Dashboard (Browser)
The local browser page prompts for:
- **Event/Subject**
- **Monitoring Question (optional)**
- **Location / ZIP / GPS**
- **Radius (km)**

You can reopen the same page any time by visiting:
`http://127.0.0.1:8765`

Additional data view:
`http://127.0.0.1:8765/data`

## Zero-Input Discovery
If you provide no RSS feeds or API keys, VigilantCore will still:
- Auto-detect your city/region + ZIP + coordinates (best effort).
- Seed from **30 curated global sources** and discover RSS/Atom feeds.
- Add a Google News RSS query built from your subject + location for broader coverage.

### Curated Global Sources (Initial 30)
BBC News, The Guardian, Al Jazeera, DW, France 24, NHK World, ABC News (AU), CBC, CNN, NBC News, CBS News, ABC News (US), Fox News, USA Today, NPR, Axios, Politico, The Washington Post, Financial Times, Bloomberg, The Economist, Reuters, AP News, Sky News, The Times of India, The Hindu, Japan Times, Sydney Morning Herald, The Globe and Mail, The Straits Times.

## Helper Scripts (script-helpers)
This repo uses the shared `script-helpers` library like other projects in this workspace.
Initialize submodules once before using `./scripts/*.sh`:
```bash
./update
```

## Single-Command Install & Run (All Major Platforms)
These commands create a local virtual environment, install dependencies, and launch the app.

### macOS / Linux
```bash
python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt && python src/main.py
```

### Windows (PowerShell)
```powershell
py -m venv venv; .\\venv\\Scripts\\Activate.ps1; pip install -r requirements.txt; python src\\main.py
```

### Windows (CMD)
```bat
py -m venv venv && call venv\\Scripts\\activate && pip install -r requirements.txt && python src\\main.py
```

## One-Command Install Scripts
For non-technical users, these scripts handle setup + launch:

### macOS / Linux
```bash
./install.sh
```

### Windows (PowerShell)
```powershell
./install.ps1
```

## One-Click Packaging (Executable)
Build a native app bundle so non-technical users can run without Python:
```bash
pyinstaller --onefile --windowed src/main.py --name VigilantCore
```

## CI Automation (ci-helpers)
GitHub Actions uses the reusable workflows from `ci-helpers` to lint, test, and build:
- Workflow file: `.github/workflows/ci.yml`
- Reusable workflow: `nikolareljin/ci-helpers/.github/workflows/python.yml@production`

## Developer Setup
```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python src/main.py
```

## Local LLM
By default, the app uses `llama3.1:8b` from Ollama. You can override with:
```bash
export OLLAMA_MODEL=llama3.1:8b
```

## Packaging (One-Click App)
```bash
pyinstaller --onefile --windowed src/main.py --name VigilantCore
```

## Repository Tips
- **Repo name**: `vigilant-core`
- **Branch protection**: Require PR reviews before merging into `main`.
