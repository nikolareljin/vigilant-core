# Configuration Guide

VigilantCore stores configuration in a platform-specific location and can also read settings from environment variables.

## Configuration Storage

### Config File Location

| Platform | Path |
|----------|------|
| Linux | `~/.config/VigilantCore/config.json` |
| macOS | `~/Library/Application Support/VigilantCore/config.json` |
| Windows | `%APPDATA%\VigilantCore\config.json` |

### Environment File

API keys are stored in a `.env` file in the same directory as `config.json`.
You can also set `DISPLAY_TIMEZONE` there to force a specific timezone for alert timestamps shown in the Live Impact Feed (web and Qt); otherwise the app uses the current host's local timezone.

## Configuration Options

### Monitoring Subject

| Option | Default | Description |
|--------|---------|-------------|
| `subject` | "Impactful Events" | Main topic to monitor (e.g., "Cybersecurity Threats", "Weather Events") |
| `question` | "" | Optional monitoring question for AI-generated insights |

### Location Settings

| Option | Default | Description |
|--------|---------|-------------|
| `location_name` | "Your Area" | Display name for your location |
| `zip_code` | null | ZIP/postal code for location matching |
| `latitude` | null | GPS latitude coordinate |
| `longitude` | null | GPS longitude coordinate |
| `radius_km` | 50 | Search radius in kilometers |
| `relax_location_filter` | false | Include results even if location matching fails |

### AI Settings

| Option | Default | Description |
|--------|---------|-------------|
| `prefer_light_model` | true | Use qwen2.5:3b instead of 7b (recommended for 8GB RAM or less) |
| `insight_refresh_minutes` | 5 | How often to refresh AI-generated insights |

### Timing Settings

| Option | Default | Description |
|--------|---------|-------------|
| `polling_minutes` | 5 | How often to check for new data |
| `news_time_window_hours` | 6 | How recent NewsAPI results should be |

### RSS Feed Settings

| Option | Default | Description |
|--------|---------|-------------|
| `rss_feeds` | [] | List of custom RSS feed URLs |
| `use_only_rss_feeds` | false | Only use provided RSS feeds, skip curated sources |
| `disable_rss_fetch` | false | Disable RSS fetching entirely |

### Web Search Settings

| Option | Default | Description |
|--------|---------|-------------|
| `enable_duckduckgo_search` | true | Enable DuckDuckGo web search (no API key needed) |

### NewsAPI Settings

| Option | Default | Description |
|--------|---------|-------------|
| `news_api_key` | null | NewsAPI.org API key |
| `news_time_window_hours` | 6 | How recent articles should be |
| `news_sort_by` | "popularity" | Sort order: popularity, publishedAt, relevancy |
| `display_timezone` | null | Optional IANA timezone for UI timestamps (defaults to host local time) |

### Google Custom Search

| Option | Default | Description |
|--------|---------|-------------|
| `google_cse_api_key` | null | Google API key for Custom Search |
| `google_cse_cx` | null | Google Custom Search Engine ID |

### Bing Search (Optional)

| Option | Default | Description |
|--------|---------|-------------|
| `bing_search_key` | null | Bing Search API key |
| `bing_search_endpoint` | null | Bing API endpoint URL |
| `bing_search_market` | null | Market code (e.g., "en-US") |
| `bing_search_safe` | null | Safe search setting |

## Environment Variables

You can also set configuration via environment variables:

```bash
# NewsAPI
export NEWS_API_KEY=your_key_here

# Optional UI timestamp timezone (defaults to this computer's local time)
export DISPLAY_TIMEZONE=America/New_York

# Google Custom Search
export GOOGLE_CSE_API_KEY=your_key_here
export GOOGLE_CSE_CX=your_search_engine_id

# Bing Search
export BING_SEARCH_KEY=your_key_here
export BING_SEARCH_ENDPOINT=https://api.bing.microsoft.com/v7.0/search
export BING_SEARCH_MARKET=en-US
export BING_SEARCH_SAFE=Moderate

# DuckDuckGo
export ENABLE_DUCKDUCKGO_SEARCH=true

# Ollama Model Override
export OLLAMA_MODEL=qwen2.5:7b
```

## Example config.json

```json
{
  "subject": "Local Weather Emergencies",
  "question": "Are there any severe weather warnings affecting my area?",
  "location_name": "San Francisco Bay Area",
  "zip_code": "94102",
  "latitude": 37.7749,
  "longitude": -122.4194,
  "radius_km": 100,
  "relax_location_filter": false,
  "prefer_light_model": false,
  "insight_refresh_minutes": 10,
  "rss_feeds": [
    "https://alerts.weather.gov/cap/ca.php?x=0",
    "https://www.sfgate.com/bayarea/feed/Bay-Area-News-702.php"
  ],
  "use_only_rss_feeds": false,
  "disable_rss_fetch": false,
  "polling_minutes": 5,
  "news_time_window_hours": 12,
  "news_sort_by": "publishedAt",
  "enable_duckduckgo_search": true
}
```

## Settings in the UI

Both the Qt desktop app and web dashboard provide a settings form to configure all options. Settings are organized into groups:

1. **Monitoring Subject** - What to monitor and the monitoring question
2. **Location** - Geographic filtering settings
3. **AI Settings** - Model preferences and insight refresh rate
4. **Timing** - Polling intervals
5. **RSS Feeds** - Custom feed configuration
6. **Web Search** - DuckDuckGo settings
7. **NewsAPI** - News API configuration
8. **Google Custom Search** - Google CSE settings
