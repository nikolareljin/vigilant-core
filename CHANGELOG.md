# Changelog

All notable changes to VigilantCore will be documented in this file.

## [0.9.0] - 2026-06-18

### Added

- **Relevance-aware reasoning context** (`utils/context_selection.py`): a deterministic, dependency-free selection layer that decides which stored alerts are injected into the AI insight prompt, replacing the previous "dump the most recent alerts" behaviour. It splits candidates into two clearly-labeled tiers:
  - **CURRENT & RELEVANT** — alerts within a freshness window *and* topically relevant to the monitoring question/subject (token coverage + aspect overlap).
  - **HISTORICAL CONTEXT** — older alerts that share an *infrastructure* aspect with the question (power grid, flooding, transport, structural, communications, water), retained as background about persistent structural risk. For example, a power-grid failure during a past snow storm is kept when reasoning about grid risk in a summer storm, while a stale "12 inches of snow expected" forecast is excluded.
- **Aspect taxonomy** mapping event keywords to event-type and infrastructure aspects, with `extract_aspects()` and `relevance_score()` helpers (reusing the shared `_tokenize`/`_jaccard` deduplication primitives).
- **Context selection settings** in `AppConfig`: `context_fresh_window_hours` (24), `context_min_relevance` (0.12), `context_max_current` (20), `context_max_historical` (6), and `context_enable_historical` (true), all persisted via config load/save.
- **Tests** (`tests/test_context_selection.py`) covering freshness filtering, off-topic exclusion, structural-history retention, the disabled-historical path, accurate `sources_used`, and timestamp edge cases.

### Changed

- **AI insight prompts** (`src/main.py`, `src/web_app.py`) now build context through the shared selector instead of a duplicated inline loop, widen the candidate pool to 200 so low-impact-but-structurally-relevant history can surface, and derive `sources_used` only from alerts actually used. The system prompt instructs the model to treat the HISTORICAL section strictly as background structural risk — never as current conditions — and to ignore data from a different season or event type than the question.

### Fixed

- **Stale-content pollution across runs**: alerts from a *previous* event no longer leak into the reasoning as current conditions on later runs; they only resurface as explicitly-labeled historical background when structurally relevant. Records are preserved in storage — irrelevant ones are simply not injected.

## [0.8.1] - 2026-03-02

### Fixed

- **Windows quickstart Python compatibility**: `scripts/quickstart.ps1` and `scripts/quickstart.bat` now explicitly target Python 3.12 for virtual environment creation to avoid unsupported interpreter selection on Windows.
- **Safer Windows Python bootstrap**: Python auto-install now uses per-user install mode (no admin shell required), validates installer signatures before execution, checks installer exit code, and removes temporary installer files after use.
- **Post-install shell behavior**: Windows quickstart now handles PATH propagation explicitly by prompting users to relaunch the terminal when needed after Python installation.
- **Windows documentation clarity**: Updated README requirements and troubleshooting guidance to document Python 3.12 as the required Windows version.

## [0.8.0] - 2026-02-28

### Added

- **Source health telemetry tracking**: Added per-source health indicators for RSS, NewsAPI, Google CSE, Bing Search, DuckDuckGo, and Emergency Search with:
  - last successful fetch timestamp
  - cumulative fetch error count
  - latest fetch latency (milliseconds)
- **Source health API endpoint**: Added `GET /api/source-health` to expose current source-health indicators as JSON.
- **Dashboard source health panel**: Added a live source-health table to the web dashboard for quick operational visibility into source fetch quality.
- **Source health tests**: Added `tests/test_source_health.py` to validate source-health initialization and success/failure metric updates.

### Changed

- **Fetch pipeline instrumentation**: Wrapped all monitor source fetch methods with source-health recording logic for attempts, successes, failures, item counts, and latencies.

## [0.7.0] - 2026-02-28

### Added

- **SQLite local cache tables**: Added dedicated `event_history` and `source_metadata` tables to persist normalized event snapshots and source attribution metadata per alert.
- **Cache persistence test coverage**: Added `tests/test_sqlite_local_cache.py` to validate insertion of normalized event history and source metadata records.

### Changed

- **Alert insert pipeline**: `database.insert_alert(...)` now records canonical alert data and inserts companion history/source metadata rows in one SQLite transaction.
- **Monitor persistence wiring**: Monitor processing now passes deduplicated source/URL metadata and normalized payloads into SQLite persistence.
- **Alert schema**: Added `source_kind` persistence to the `alerts` table with backward-compatible migration behavior.

### Fixed

- **SQLite foreign key enforcement**: Enabled `PRAGMA foreign_keys = ON` for every database connection so `event_history`/`source_metadata` cascade with alert deletion as designed.

## [0.5.0] - 2026-02-27

### Added

- **Event deduplication engine**: Added semantic overlap detection for alerts so duplicate/overlapping reports from multiple sources are merged into one canonical event.
- **Deduplication documentation**: Added `docs/event-deduplication.md` with merge rules, source-priority behavior, and pipeline placement.
- **Deduplication unit tests**: Added `tests/test_event_deduplication.py` for overlap merge and non-merge scenarios.

### Changed

- **Monitoring pipeline merge stage**: `MonitorEngine.gather_items()` now performs event-level deduplication after URL/location filtering and before parsing/persistence.
- **Merged source attribution**: Canonical merged events now combine source names (`source_a | source_b`) while retaining a priority source kind for downstream confidence scoring.

### Fixed

- **Untitled event false merges**: Missing-title alerts and common placeholders (for example `(no title)` / `untitled`) no longer create fingerprints that could merge unrelated events.
- **Dedup performance scaling**: Semantic dedup now uses lightweight fingerprint/token indexing to reduce full list scans on larger fetch batches.
- **Merged URL persistence safety**: Ingestion now carries merged URL metadata through processing and checks all merged URLs against SQLite before insert, preventing reinsertions when canonical URL selection differs across runs.
- **Timestamp-window semantics**: Semantic token-overlap merging now requires both events to have timestamps for the overlap window check.
- **Monitor DB lookup efficiency**: URL existence checks in `process_items()` now use per-cycle caches to avoid repeated SQLite connection churn for the same URLs.

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
