# Changelog

All notable changes to VigilantCore will be documented in this file.

## [0.6.0] - 2026-02-27

### Added

- **GGUF local summarizer integration**: Added `utils/gguf_summarizer.py` with optional GGUF-backed summarization for:
  - alert digest summaries
  - risk snapshot summaries
- **Risk snapshot API**: Added `/api/risk-snapshot` endpoint in the web app for local risk-summary output.
- **Config support for GGUF summarizer**: Added new configuration settings:
  - `enable_gguf_summarizer`
  - `gguf_model_path`
  - `gguf_n_ctx`
  - `gguf_max_tokens`
- **Summarizer unit tests**: Added `tests/test_gguf_summarizer.py`.

### Changed

- **Insight fallback behavior**: Web/Qt insight generation now falls back to local GGUF/heuristic summaries when Ollama is unavailable and GGUF summarizer is enabled.
- **Insight payload enrichment**: Insight responses now include `risk_snapshot`, `summary_engine`, and `summary_error` metadata.

## [0.4.0] - 2026-02-27

### Added

- **Unified event normalization layer**: Added a shared normalization schema for all ingested alerts with:
  - `severity`
  - `confidence`
  - normalized `timestamp_utc`
  - structured location fields (`name`, `zip_code`, `latitude`, `longitude`)
- **Normalization documentation**: Added `docs/event-normalization.md` describing schema and behavior.
- **Normalization unit tests**: Added `tests/test_event_normalization.py` to verify schema output and timestamp normalization.

### Changed

- **Ingestion pipeline normalization**: Monitoring now normalizes event payloads before database insert and live alert emission.
- **SQLite alert schema expansion**: Added persisted normalized columns (`severity`, `confidence`, `event_timestamp_utc`, `location_zip_code`, `location_latitude`, `location_longitude`) with backward-compatible migration checks.
- **Alerts API payload enrichment**: `/api/alerts` now includes normalized event fields in the JSON response.

## [0.3.0] - 2026-02-24

### Added

- **Expanded outage and infrastructure monitoring coverage**: Added context-aware source/query generation for power outages (including `poweroutage.us` searches), local utility signals (electric/water/gas), renewable infrastructure incidents (solar/wind), and transportation disruptions (traffic/transit/rail/airlines/airports).
- **Broader extreme event and crisis discovery**: Added subject-driven query/feed expansion for flooding, tornadoes, wildfires, winter storms, earthquakes, hazmat incidents, and global conflict/humanitarian crisis scenarios.
- **Curated signal source expansion**: Added additional curated source domains used for discovery/search seeding across outage, aviation, wildfire, disaster, and crisis contexts (e.g., FAA/NAS status, InciWeb, USGS earthquake, GDACS, ReliefWeb).
- **International regional source URL coverage**: Added curated regional source URL catalogs and localized news-query/feed generation for Canada, Europe, North Africa, China/Far East, Australia, South Africa, Central America, South America, plus broader Middle East/South Asia/Southeast Asia/Sub-Saharan Africa/global fallback coverage.
- **Regional source preview API/UI**: Added `/api/source-preview` and a setup-page preview panel to inspect inferred region and curated source URLs from location text or coordinates before saving.
- **Dedicated source discovery documentation**: Added `docs/source-discovery.md` documenting region inference, curated source catalogs, coordinate-driven behavior, and source preview API usage.
- **AI suggested actions toggle**: Added a settings toggle to enable/disable actionable suggestions shown next to the AI insight result in web and Qt views.

### Changed

- **Local feed generation**: Comprehensive local feed discovery now injects context-aware Google News RSS queries for likely outage/disaster/transport/conflict scenarios based on the monitored subject and location.
- **Emergency search coverage**: Emergency search now adds local utility and transportation domain-targeted searches (including `site:poweroutage.us`) and conflict-focused queries when the subject indicates war/conflict conditions.
- **Coordinate-driven discovery**: Region/source selection can now infer regional coverage directly from latitude/longitude when no ZIP code or location text is provided.
- **Network discovery performance**: Feed discovery now caches page HTML/feed validation results in-process and deduplicates repeated base-url scans to reduce startup/network request volume.
- **Low-bandwidth/tethered mode**: Added a settings toggle that reduces discovery/query budgets, caps contextual feeds and RSS breadth, and lowers emergency/DDG request sizes for constrained connections.

### Fixed

- **US region inference fallback**: Plain US city inputs (for example `Dallas` / `Austin`) no longer fall through to the Europe profile when ZIP/coordinates are omitted.
- **North/Central America coordinate routing**: Refined Central America / Canada / US bounding-box precedence so southern US coordinates no longer route to Central America, northern US cities no longer route to Canada, and Hawaii routes to the US profile.
- **Conflict keyword false positives**: Conflict query expansion now uses token/phrase matching and avoids substring matches such as `hardware` triggering `war`.
- **AI suggestions toggle persistence**: Saving settings now removes a stale `.env` file when no env-backed overrides remain, so re-enabling AI suggestions is not overridden by an old `ENABLE_AI_SUGGESTIONS=false`.
- **Source preview safety/validation**: Web source preview now builds URL links via DOM APIs (no HTML interpolation) and validates latitude/longitude ranges before region inference.
- **DuckDuckGo toggle persistence**: `ENABLE_DUCKDUCKGO_SEARCH=false` now persists in `.env` when disabled.
- **Config `.env` preservation**: Saving settings now updates app-managed `.env` keys while preserving unknown/user-managed entries instead of deleting the entire file.
- **Shared insight helpers**: Suggestion normalization helpers are centralized in `utils/insight.py` to avoid web/Qt drift.
- **Region overlap precedence**: Region overlap behavior is explicitly documented and preserved with deterministic precedence for border regions.

### Details

- Added region profiles with localized Google News parameters (`gl`, `hl`, `ceid`) and region-specific utility/transport/emergency query terms.
- Added curated regional source URL catalogs for:
  - Canada
  - Europe (priority international baseline)
  - North Africa
  - China / Far East
  - Australia
  - South Africa
  - Central America
  - South America
  - Middle East / South Asia / Southeast Asia / Sub-Saharan Africa
  - Global fallback (disaster / humanitarian / aviation)
- Added coordinate-based region inference using broad geographic bounding boxes so regional source selection works with lat/lon-only configurations.
- Added setup-page source preview panel for validating inferred region and curated URLs before starting monitoring.

## [0.2.2] - 2026-02-23

### Added

- **Cross-platform compatibility test coverage**: Added `tests/test_platform_compat.py` to validate Windows/macOS/Linux-sensitive launcher and config path behavior (venv path resolution, background process launch flags, and platform config/data directories).
- **Dedicated compatibility GitHub Actions workflow**: Added `.github/workflows/compatibility.yml` with a Windows/macOS/Linux matrix to run install, compatibility tests, launcher status smoke checks, and Python syntax compilation.
- **README CI badges**: Added badges for the main CI workflow and the dedicated compatibility workflow, plus platform compatibility indicator badges (Linux/macOS/Windows).
- **Release auto-tagging CI**: Added the `ci-helpers` `auto-tag-release-push` workflow so merges of `release/*` branches into `main`/`master` automatically create and push the matching release tag.

### Changed

- **Test script coverage**: `scripts/test.sh` now runs the platform compatibility unit tests in addition to the existing smoke import check.
- **Dependencies**: Removed unused `crawl4ai` from `requirements.txt` to reduce install friction and improve cross-platform reliability.

## [0.2.1] - 2026-02-22

### Fixed

- **Live Impact Feed timestamps**: Web and Qt Live Impact Feed timestamps now display in the current host's local timezone by default instead of raw stored UTC-like values.
- **Timezone override support**: Added optional `.env` setting `DISPLAY_TIMEZONE` (IANA timezone, e.g. `America/New_York`) to force a specific UI timezone for alert timestamps.
- **Qt live feed timestamp consistency**: New alerts inserted during active monitoring are now formatted with the same local/configured timezone conversion as rows loaded from SQLite.
- **Qt settings save timezone preservation**: Saving settings from the Qt dialog now preserves an existing `DISPLAY_TIMEZONE` override in the generated `.env` output instead of dropping it.
- **Timezone configuration validation**: Invalid `DISPLAY_TIMEZONE` / `TIMEZONE` values now warn and fall back to host local time instead of failing silently.
- **Launcher parity**: Windows launchers now perform the same best-effort stale web-listener cleanup as `run.sh` before starting `web`/`both`.

### Changed
- `TIMEZONE` remains supported as a legacy fallback when `DISPLAY_TIMEZONE` is unset (now documented).

## [0.2.0] - 2026-01-26

### Added

- **Location-Based Emergency Services Discovery**: Automatic discovery of local emergency services, utilities, and weather alerts based on ZIP code or coordinates
  - **NWS Weather Alerts**: State-specific National Weather Service CAP feeds automatically added
  - **Emergency Services Search**: Automatic searches for local police, fire, EMS alerts
  - **Utility Information**: Power outage maps, utility company alerts for the area
  - **County/State Resources**: Local government emergency management feeds
  - ZIP code to state mapping for all US states and territories
  - Comprehensive local feed builder combining weather, emergency, and local news sources
  - Emergency-specific search queries for subject + location context

- **Monitoring Question Insight Feature**: AI-generated insights displayed above alerts list
  - Expandable insight card showing summary and detailed explanation
  - Configurable refresh interval (`insight_refresh_minutes` setting)
  - Available in both Qt desktop and web dashboard interfaces

- **Unified Launcher** (`vigilant.py`): Single entry point for all operations
  - `python vigilant.py web` - Start web dashboard
  - `python vigilant.py qt` - Start Qt desktop app
  - `python vigilant.py both` - Start both (web in background)
  - `python vigilant.py stop` - Stop all running instances
  - `python vigilant.py status` - Check what's running
  - Cross-platform PID management for process control

- **Platform-specific launcher scripts**:
  - `run.sh` (Linux/macOS)
  - `run.bat` (Windows CMD)
  - `run.ps1` (Windows PowerShell)

- **App icons and branding**:
  - Favicon for web dashboard (favicon.ico)
  - Application icons in various sizes (16px to 256px)
  - Qt app window icon

- **Privacy note**: Visible indicator in both UIs that data is processed locally

- **Grouped settings sections**: Settings organized into logical groups:
  - Monitoring Subject
  - Location
  - AI Settings
  - Timing
  - RSS Feeds
  - Web Search
  - NewsAPI
  - Google Custom Search

### Fixed

- **Data fetching bug**: Fixed critical issue where `gather_items()` in `engine/monitor.py` was resetting the combined results list due to incorrect indentation

- **DuckDuckGo URL extraction**: Fixed handling of protocol-relative URLs (`//duckduckgo.com/...`) that were being silently skipped

- **Ollama model detection**: Updated to handle Pydantic objects returned by newer Ollama library versions (was previously expecting dicts)

- **PEP 668 compliance**: Fixed pip installation in run scripts to use `python -m pip` instead of direct `pip` calls, resolving "externally-managed-environment" errors on modern Python

### Changed

- Simplified launcher scripts - all now delegate to `vigilant.py`
- Improved settings form layout with grouped sections
- Enhanced insight display with purple gradient styling

## [0.1.0-rc] - Initial Release Candidate

### Features

- Qt desktop application with PySide6
- Web dashboard with Flask
- Ollama integration for local LLM processing (qwen2.5:7b/3b)
- NewsAPI integration
- DuckDuckGo web search
- Google Custom Search Engine support
- Bing Web Search API support
- RSS/Atom feed aggregation
- 30+ curated global news sources
- Impact scoring (1-10 scale)
- Location-aware filtering (ZIP code, coordinates, radius)
- SQLite database for alert storage
- Zero-input discovery mode
