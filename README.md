# VigilantCore

<img src="./vigilant_core.png" />

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

## Qt UI (Desktop)
Launch the desktop UI directly:
- macOS/Linux: `./run-qt.sh`
- Windows: `run-qt.bat`

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
- **Prefer lighter model on 8GB or less**
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
- Add local public-safety queries (police, sheriff, fire, emergency management).
- Attempt to discover local police/government and local news RSS feeds near your location.
- Pull social chatter via Reddit search RSS tied to your subject and location.

### RSS Feeds vs Curated Sources
By default, any RSS feeds you add are *merged* with the built-in curated sources.
If you want to use only the RSS feeds you provide, enable **"Only use RSS feeds listed above"** in Settings.
To skip RSS entirely and use only API/search providers, enable **"Disable RSS fetching"**.

### Polling Interval
You can control how often the app checks for new data (default **5 minutes**).
- Web UI: **Polling interval (minutes)**
- Qt UI: **Polling interval (minutes)**

## Optional Search API Keys (Better Coverage)
If you set any of the API keys below, VigilantCore will use them automatically. If not set, it falls back to RSS and the built-in discovery.

### Google Programmable Search Engine (CSE)
1. Create a Custom Search Engine and set it to **Search the entire web**:
   https://programmablesearchengine.google.com/
2. Enable the Custom Search JSON API and create an API key:
   https://developers.google.com/custom-search/v1/overview
3. Set:
```bash
GOOGLE_CSE_API_KEY=your_key
GOOGLE_CSE_CX=your_search_engine_id
```

### Bing Web Search API
1. Create a Bing Search v7 resource in Azure:
   https://learn.microsoft.com/en-us/bing/search-apis/bing-web-search/create-bing-search-service-resource
2. Set:
```bash
BING_SEARCH_KEY=your_key
# Optional overrides
BING_SEARCH_ENDPOINT=https://api.bing.microsoft.com/v7.0/search
BING_SEARCH_MARKET=en-US
BING_SEARCH_SAFE=Moderate
```

### DuckDuckGo Web Search (No Key Required)
DuckDuckGo HTML search is available without an API key. Enable/disable it in Settings:
- Web UI: **Enable DuckDuckGo web search**
- Qt UI: **Enable DuckDuckGo web search**

### Facebook & Instagram (Meta Graph API)
Meta does not provide a general public search API. Access typically requires:
- A Meta app with approved permissions
- A specific Page/IG Business account context
If you have a Page or IG Business and want targeted ingestion, open an issue and we can add a provider for specific page IDs.

### Curated Global Sources (Expanded)
The default list now includes major US, European, East European, Chinese, Australian, South American, and African outlets. See `vigilant-core/utils/sources.py` for the full list.

## Helper Scripts (script-helpers)
This repo can use the shared `script-helpers` library like other projects in this workspace.
If the submodule is not present (e.g., CI), scripts fall back to minimal logging.
To use full helpers locally, initialize submodules once:
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
By default, the app uses `qwen2.5:7b` from Ollama. If RAM is 8GB or less, it auto-falls back to `qwen2.5:3b` unless `OLLAMA_MODEL` is set. You can override with:
```bash
export OLLAMA_MODEL=qwen2.5:7b
```

## Packaging (One-Click App)
```bash
pyinstaller --onefile --windowed src/main.py --name VigilantCore
```

## Repository Tips
- **Repo name**: `vigilant-core`
- **Branch protection**: Require PR reviews before merging into `main`.
### NewsAPI Time Window
You can control how recent NewsAPI results should be. Default is **6 hours**.
- Web UI: **News time window (hours)**
- Qt UI: **News time window (hours)**

### NewsAPI Sort Order
Default is **popularity**. You can also choose **publishedAt** or **relevancy** from the Settings UI.
