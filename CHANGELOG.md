# Changelog

All notable changes to VigilantCore will be documented in this file.

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
