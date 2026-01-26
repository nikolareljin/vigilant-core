# VigilantCore

<img src="./vigilant_core.png" />

VigilantCore is a local, cross-platform monitoring app that tracks **Impactful Events** for a specific subject, using a local LLM (Ollama) to score impact and generate predictive outcomes. It is designed to be simple for non-technical users while still offering an AI-driven, location-aware signal.

**All AI processing happens locally on your computer - no data is sent to external servers.**

## Key Features

- **AI-Powered Insights**: Ask specific monitoring questions and get AI-generated answers
- **Impact Scoring**: Every alert scored 1-10 for relevance and urgency
- **Location-Aware**: Filter alerts by ZIP code, coordinates, or radius
- **Multiple Data Sources**: NewsAPI, DuckDuckGo, Google CSE, RSS feeds, and 30+ curated sources
- **Cross-Platform**: Web dashboard and Qt desktop app
- **Privacy-First**: All processing done locally via Ollama

## User Journey
1. **First Run**: Open the app, enter your subject, location, and optional RSS feeds/API key.
2. **Set Monitoring Question**: Ask a specific question like "When is the peak risk of power outage?"
3. **Live Impact Feed**: The dashboard shows scored alerts with AI-generated insights.
4. **Impact Scoring**: Each alert is ranked from 1–10 based on relevance and urgency.
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

## Clone and Install

### Installation
1. Clone the repository
2. Run the launcher script:

**Linux/macOS:**
```bash
./run.sh          # Start web dashboard (default)
./run.sh qt       # Start Qt desktop app
./run.sh both     # Start both (web in background)
./run.sh stop     # Stop all instances
./run.sh status   # Check what's running
```

**Windows:**
```cmd
run.bat           # Start web dashboard
run.bat qt        # Start Qt desktop app
run.bat stop      # Stop all instances
```

The launcher will automatically create a virtual environment and install dependencies.

### Web Dashboard

Configure the dashboard:

<img width="1920" height="3375" alt="image" src="https://github.com/user-attachments/assets/807bd2fc-3312-4066-aef6-e3114c4cac1c" />

In the examples above, public location was defined with Longitude/Latitude. You can use your own location, ZIP code, address and longitude/latitude.

Open your browser to: **http://127.0.0.1:8765**

<img width="1920" height="1368" alt="image" src="https://github.com/user-attachments/assets/a2a34e87-6ce6-489b-a4d5-246500ab8243" />

Initial results of the search.

### Qt Desktop App

Launch with `./run.sh qt` (or `run.bat qt` on Windows).

<img width="616" height="742" alt="image" src="https://github.com/user-attachments/assets/ec3a8c6d-5c9b-409c-a63c-978680944faf" />

Results view with the AI generated content:

<img width="1100" height="735" alt="image" src="https://github.com/user-attachments/assets/83bbedc3-ecfa-4c91-b94b-26b8ccacb522" />

## Monitoring Question & AI Insights

The **Monitoring Question** feature lets you ask specific questions about your monitored subject. The AI analyzes recent alerts and generates focused insights.

**Example questions:**
- "What is the expected time of highest risk of power outage in my area?"
- "Should I clear my driveway now, or wait until the snow stops?"
- "Are there any travel advisories affecting I-95?"

The insight appears as an expandable card above the alerts list, showing:
- **Summary**: Brief answer to your question
- **Explanation**: Detailed analysis with supporting evidence

Configure refresh interval in Settings under "AI Settings".

## Web Dashboard

The web interface is available at: **http://127.0.0.1:8765**

Settings page prompts for:
- **Event/Subject** - What to monitor
- **Monitoring Question** - Specific question for AI insights
- **Location / ZIP / GPS** - Geographic filtering
- **Radius (km)** - Search area
- **AI Settings** - Model preferences, insight refresh rate
- **Data Sources** - RSS feeds, API keys

Additional data view: `http://127.0.0.1:8765/data`

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

## Documentation

Full documentation is available in the `docs/` folder:

- [Installation Guide](docs/installation.md) - Detailed setup instructions
- [Configuration Guide](docs/configuration.md) - All configuration options
- [Features](docs/features.md) - Complete feature documentation
- [Examples](docs/examples.md) - Real-world usage examples (winter storms, power outages, etc.)

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for release history and changes.
