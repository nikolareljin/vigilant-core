# Features

VigilantCore provides comprehensive monitoring capabilities with local AI processing.

## Core Features

### Impact Scoring

Every alert is scored from 1-10 based on relevance and urgency:

| Score | Level | Description |
|-------|-------|-------------|
| 1-3 | Low | Low relevance or weak impact |
| 4-6 | Moderate | Moderate impact or early advisory signals |
| 7-10 | High | High-impact events, warnings, or imminent disruptions |

### Monitoring Question Insight

The Monitoring Question feature provides AI-generated summaries based on your specific question about the monitored subject.

**How it works:**
1. Enter a question in settings (e.g., "Is there any risk of flooding in my area?")
2. The AI analyzes recent alerts and generates a focused answer
3. An expandable insight card appears above the alerts list
4. The insight refreshes automatically based on your configured interval

**Insight Display:**
- **Summary**: A brief answer to your monitoring question
- **Explanation**: Detailed analysis with supporting evidence from recent alerts

### Location-Aware Filtering

VigilantCore prioritizes local events using multiple methods:
- ZIP/postal code matching
- GPS coordinates with configurable radius
- Location name keyword matching
- Optional relaxed filtering to include broader results

### Automatic Local Source Discovery

When you provide a ZIP code or coordinates, VigilantCore automatically discovers and monitors:

**Weather & Emergency Alerts:**
- NWS (National Weather Service) state-specific CAP alerts
- Severe weather warnings for your area
- National emergency broadcasts

**Local Emergency Services:**
- Police department alerts and news
- Sheriff's office announcements
- Fire department news and alerts
- Emergency management office updates
- Road closures and travel advisories

**Utility Information:**
- Power company outage maps and alerts
- Electric utility service notifications
- Gas and water utility alerts
- Power outage aggregator lookups (including `poweroutage.us` search coverage)
- Renewable energy infrastructure incidents (solar/wind) when relevant

**Local News:**
- County and city government news
- Local TV station news feeds
- Regional newspaper RSS feeds

**Transportation & Operations:**
- Traffic incidents and road closures
- Transit and rail disruption alerts
- Airport operations alerts and airline delay/cancellation signals

**Extreme Situations (Context-Aware):**
- Flooding / flash flood warnings
- Tornado and severe storm warnings
- Wildfire / evacuation alerts
- Winter storm / ice disruption signals
- Earthquake / seismic incident signals
- Conflict / war / humanitarian crisis updates (subject-driven global monitoring)

### International Region Coverage

When location text or coordinates are provided, VigilantCore can infer a region and prioritize matching sources and localized Google News feeds. Current curated regional URL coverage includes:

- Canada
- Europe (priority international baseline)
- North Africa
- China / Far East
- Australia
- South Africa
- Central America
- South America
- Additional fallback regions where sources are available: Middle East, South Asia, Southeast Asia, Sub-Saharan Africa, and global disaster/humanitarian sources

This discovery happens automatically based on your ZIP code - the app maps your ZIP to the correct state and searches for relevant local sources.

### Local AI Processing

All AI processing happens locally on your machine:
- No data sent to external servers
- Privacy-preserving by design
- Uses Ollama with qwen2.5 models
- Automatic model selection based on available RAM

## Data Sources

### Built-in Sources (Zero Configuration)

Without any API keys, VigilantCore provides:

1. **30+ Curated Global Sources** - Major news outlets worldwide
2. **Google News RSS** - Auto-generated queries for your subject
3. **Reddit Search RSS** - Social media monitoring
4. **Local Discovery** - Attempts to find local news and government RSS feeds
5. **Contextual Emergency Search** - Subject-aware outage/disaster/transport/conflict searches when location and context are provided

### Optional API Integrations

Enhance coverage with API keys:

| Source | Key Required | Description |
|--------|--------------|-------------|
| DuckDuckGo | No | Web search (enabled by default) |
| NewsAPI | Yes | 150,000+ news sources |
| Google CSE | Yes | Custom web search |
| Bing Search | Yes | Microsoft web search |

### Custom RSS Feeds

Add your own RSS/Atom feeds for specialized monitoring:
- Local news outlets
- Government alerts (weather, emergency)
- Industry-specific sources
- Social media feeds

## Interface Options

### Web Dashboard

Access at **http://127.0.0.1:8765**

Features:
- Responsive design for any screen size
- Real-time alert display
- Expandable insight card
- Settings page with grouped options
- Data view for browsing alerts

### Qt Desktop App

Native desktop experience:
- System tray integration
- Native look and feel
- Same functionality as web dashboard
- Can run alongside web dashboard

## Process Management

### Unified Launcher

The `vigilant.py` script provides centralized control:

```bash
python vigilant.py web      # Web dashboard only
python vigilant.py qt       # Qt app only
python vigilant.py both     # Both (web in background)
python vigilant.py stop     # Stop all
python vigilant.py status   # Check status
```

### PID Management

VigilantCore tracks running processes:
- Automatic PID file management
- Graceful shutdown with SIGTERM
- Force kill fallback after timeout
- Cross-platform support (Windows/Linux/macOS)

## Privacy & Security

### Local Processing

- **All AI processing is local** - Ollama runs on your machine
- **No telemetry** - No usage data sent anywhere
- **API keys stored locally** - In your config directory

### Data Storage

- SQLite database in your user data directory
- Configuration in platform-specific config directory
- No cloud sync or external storage

### Privacy Indicator

Both interfaces display a visible note:
> "Results processed locally by AI running on this computer"

## Database

### Storage Location

| Platform | Path |
|----------|------|
| Linux | `~/.local/share/VigilantCore/` |
| macOS | `~/Library/Application Support/VigilantCore/` |
| Windows | `%LOCALAPPDATA%\VigilantCore\` |

### Alert Data

Each alert contains:
- Title and description
- Source URL
- Publication date
- Impact score (1-10)
- AI-generated analysis
- Location relevance
