"""Configuration management for VigilantCore."""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from dotenv import load_dotenv
try:
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
except ImportError:  # pragma: no cover - Python <3.9 fallback
    ZoneInfo = None  # type: ignore[assignment]
    ZoneInfoNotFoundError = ValueError  # type: ignore[assignment]

APP_NAME = "VigilantCore"


def _load_display_timezone_from_env() -> Optional[str]:
    """Read DISPLAY_TIMEZONE (preferred) or TIMEZONE (legacy fallback) and validate it."""
    tz_name = os.getenv("DISPLAY_TIMEZONE") or os.getenv("TIMEZONE")
    if not tz_name:
        return None
    if ZoneInfo is None:
        return tz_name
    try:
        ZoneInfo(tz_name)
    except (ZoneInfoNotFoundError, ValueError):
        print(
            f"Warning: Invalid timezone '{tz_name}' in DISPLAY_TIMEZONE/TIMEZONE; falling back to host local time.",
            file=sys.stderr,
        )
        return None
    return tz_name


@dataclass
class AppConfig:
    subject: str = "Impactful Events"
    question: str = ""
    location_name: str = "Your Area"
    zip_code: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    radius_km: int = 50
    relax_location_filter: bool = False
    prefer_light_model: bool = True
    insight_refresh_minutes: int = 5
    rss_feeds: List[str] = field(default_factory=list)
    use_only_rss_feeds: bool = False
    disable_rss_fetch: bool = False
    polling_minutes: int = 5
    news_api_key: Optional[str] = None
    news_time_window_hours: int = 6
    news_sort_by: str = "popularity"
    display_timezone: Optional[str] = None
    google_cse_api_key: Optional[str] = None
    google_cse_cx: Optional[str] = None
    bing_search_key: Optional[str] = None
    bing_search_endpoint: Optional[str] = None
    bing_search_market: Optional[str] = None
    bing_search_safe: Optional[str] = None
    enable_duckduckgo_search: bool = True
    enable_ai_suggestions: bool = True
    low_bandwidth_mode: bool = False
    # Relevance-aware reasoning context controls.
    context_fresh_window_hours: float = 24.0
    context_min_relevance: float = 0.12
    context_max_current: int = 20
    context_max_historical: int = 6
    context_enable_historical: bool = True
    # Mesh node identity (platform: emergency-services coordination).
    node_label: Optional[str] = None
    node_role: str = "hub"
    # Plugin kernel: list of {type, name, enabled, options} entries.
    plugins: List[dict] = field(default_factory=list)


def config_dir() -> Path:
    if sys.platform.startswith("win"):
        base = Path(os.getenv("APPDATA", Path.home() / "AppData" / "Roaming"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.getenv("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / APP_NAME


def data_dir() -> Path:
    if sys.platform.startswith("win"):
        base = Path(os.getenv("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.getenv("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return base / APP_NAME


def config_path() -> Path:
    return config_dir() / "config.json"


def env_path() -> Path:
    return config_dir() / ".env"


def _coerce_float(value: object, default: float) -> float:
    """Parse a config value as float, falling back to ``default`` if invalid."""
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def _coerce_int(value: object, default: int) -> int:
    """Parse a config value as int, falling back to ``default`` if invalid."""
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def _coerce_bool(value: object, default: bool) -> bool:
    """Parse a config value as bool, recognizing common JSON string forms.

    A bare ``bool("false")`` is ``True``, which is a footgun for user-edited
    config.json, so accept the usual string spellings explicitly.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in ("1", "true", "yes", "on"):
            return True
        if lowered in ("0", "false", "no", "off"):
            return False
    if isinstance(value, (int, float)):
        return bool(value)
    return default


def load_config() -> AppConfig:
    cfg_path = config_path()
    if not cfg_path.exists():
        load_dotenv(env_path())
        cfg = AppConfig()
        cfg.news_api_key = os.getenv("NEWS_API_KEY")
        cfg.display_timezone = _load_display_timezone_from_env()
        cfg.google_cse_api_key = os.getenv("GOOGLE_CSE_API_KEY")
        cfg.google_cse_cx = os.getenv("GOOGLE_CSE_CX")
        cfg.bing_search_key = os.getenv("BING_SEARCH_KEY")
        cfg.bing_search_endpoint = os.getenv("BING_SEARCH_ENDPOINT")
        cfg.bing_search_market = os.getenv("BING_SEARCH_MARKET")
        cfg.bing_search_safe = os.getenv("BING_SEARCH_SAFE")
        cfg.enable_duckduckgo_search = bool(
            (os.getenv("ENABLE_DUCKDUCKGO_SEARCH") or "true").lower() in ("1", "true", "yes")
        )
        cfg.enable_ai_suggestions = bool(
            (os.getenv("ENABLE_AI_SUGGESTIONS") or "true").lower() in ("1", "true", "yes")
        )
        cfg.low_bandwidth_mode = bool(
            (os.getenv("LOW_BANDWIDTH_MODE") or "false").lower() in ("1", "true", "yes")
        )
        return cfg
    data = json.loads(cfg_path.read_text(encoding="utf-8"))
    load_dotenv(env_path())
    cfg = AppConfig(
        subject=data.get("subject", "Impactful Events"),
        question=data.get("question", ""),
        location_name=data.get("location_name", "Your Area"),
        zip_code=data.get("zip_code"),
        latitude=data.get("latitude"),
        longitude=data.get("longitude"),
        radius_km=int(data.get("radius_km", 50)),
        relax_location_filter=_coerce_bool(data.get("relax_location_filter", False), False),
        prefer_light_model=_coerce_bool(data.get("prefer_light_model", True), True),
        insight_refresh_minutes=int(data.get("insight_refresh_minutes", 5)),
        rss_feeds=data.get("rss_feeds", []),
        use_only_rss_feeds=_coerce_bool(data.get("use_only_rss_feeds", False), False),
        disable_rss_fetch=_coerce_bool(data.get("disable_rss_fetch", False), False),
        polling_minutes=int(data.get("polling_minutes", 5)),
        news_api_key=data.get("news_api_key"),
        news_time_window_hours=int(data.get("news_time_window_hours", 6)),
        news_sort_by=data.get("news_sort_by", "popularity"),
        display_timezone=data.get("display_timezone"),
        google_cse_api_key=data.get("google_cse_api_key"),
        google_cse_cx=data.get("google_cse_cx"),
        bing_search_key=data.get("bing_search_key"),
        bing_search_endpoint=data.get("bing_search_endpoint"),
        bing_search_market=data.get("bing_search_market"),
        bing_search_safe=data.get("bing_search_safe"),
        enable_duckduckgo_search=_coerce_bool(data.get("enable_duckduckgo_search", True), True),
        enable_ai_suggestions=_coerce_bool(data.get("enable_ai_suggestions", True), True),
        low_bandwidth_mode=_coerce_bool(data.get("low_bandwidth_mode", False), False),
        context_fresh_window_hours=_coerce_float(
            data.get("context_fresh_window_hours", 24), 24.0
        ),
        context_min_relevance=_coerce_float(
            data.get("context_min_relevance", 0.12), 0.12
        ),
        context_max_current=_coerce_int(data.get("context_max_current", 20), 20),
        context_max_historical=_coerce_int(data.get("context_max_historical", 6), 6),
        context_enable_historical=_coerce_bool(
            data.get("context_enable_historical", True), True
        ),
        node_label=(
            str(data["node_label"]) if data.get("node_label") is not None else None
        ),
        node_role=str(data.get("node_role", "hub") or "hub"),
        plugins=list(data["plugins"]) if isinstance(data.get("plugins"), list) else [],
    )
    cfg.news_api_key = cfg.news_api_key or os.getenv("NEWS_API_KEY")
    cfg.display_timezone = cfg.display_timezone or _load_display_timezone_from_env()
    cfg.google_cse_api_key = cfg.google_cse_api_key or os.getenv("GOOGLE_CSE_API_KEY")
    cfg.google_cse_cx = cfg.google_cse_cx or os.getenv("GOOGLE_CSE_CX")
    cfg.bing_search_key = cfg.bing_search_key or os.getenv("BING_SEARCH_KEY")
    cfg.bing_search_endpoint = cfg.bing_search_endpoint or os.getenv("BING_SEARCH_ENDPOINT")
    cfg.bing_search_market = cfg.bing_search_market or os.getenv("BING_SEARCH_MARKET")
    cfg.bing_search_safe = cfg.bing_search_safe or os.getenv("BING_SEARCH_SAFE")
    if os.getenv("ENABLE_DUCKDUCKGO_SEARCH") is not None:
        cfg.enable_duckduckgo_search = (
            os.getenv("ENABLE_DUCKDUCKGO_SEARCH", "").lower() in ("1", "true", "yes")
        )
    if os.getenv("ENABLE_AI_SUGGESTIONS") is not None:
        cfg.enable_ai_suggestions = (
            os.getenv("ENABLE_AI_SUGGESTIONS", "").lower() in ("1", "true", "yes")
        )
    if os.getenv("LOW_BANDWIDTH_MODE") is not None:
        cfg.low_bandwidth_mode = (
            os.getenv("LOW_BANDWIDTH_MODE", "").lower() in ("1", "true", "yes")
        )
    return cfg


def save_config(config: AppConfig) -> None:
    cfg_dir = config_dir()
    cfg_dir.mkdir(parents=True, exist_ok=True)
    data = {
        "subject": config.subject,
        "question": config.question,
        "location_name": config.location_name,
        "zip_code": config.zip_code,
        "latitude": config.latitude,
        "longitude": config.longitude,
        "radius_km": config.radius_km,
        "relax_location_filter": config.relax_location_filter,
        "prefer_light_model": config.prefer_light_model,
        "insight_refresh_minutes": config.insight_refresh_minutes,
        "rss_feeds": config.rss_feeds,
        "use_only_rss_feeds": config.use_only_rss_feeds,
        "disable_rss_fetch": config.disable_rss_fetch,
        "polling_minutes": config.polling_minutes,
        "news_api_key": None,
        "news_time_window_hours": config.news_time_window_hours,
        "news_sort_by": config.news_sort_by,
        "display_timezone": config.display_timezone,
        "google_cse_api_key": None,
        "google_cse_cx": None,
        "enable_duckduckgo_search": config.enable_duckduckgo_search,
        "enable_ai_suggestions": config.enable_ai_suggestions,
        "low_bandwidth_mode": config.low_bandwidth_mode,
        "context_fresh_window_hours": config.context_fresh_window_hours,
        "context_min_relevance": config.context_min_relevance,
        "context_max_current": config.context_max_current,
        "context_max_historical": config.context_max_historical,
        "context_enable_historical": config.context_enable_historical,
        "node_label": config.node_label,
        "node_role": config.node_role,
        "plugins": config.plugins,
    }
    config_path().write_text(json.dumps(data, indent=2), encoding="utf-8")
    env_lines = []
    if config.news_api_key:
        env_lines.append(f"NEWS_API_KEY={config.news_api_key}")
    if config.display_timezone:
        env_lines.append(f"DISPLAY_TIMEZONE={config.display_timezone}")
    if config.google_cse_api_key:
        env_lines.append(f"GOOGLE_CSE_API_KEY={config.google_cse_api_key}")
    if config.google_cse_cx:
        env_lines.append(f"GOOGLE_CSE_CX={config.google_cse_cx}")
    if not config.enable_ai_suggestions:
        env_lines.append("ENABLE_AI_SUGGESTIONS=false")
    if not config.enable_duckduckgo_search:
        env_lines.append("ENABLE_DUCKDUCKGO_SEARCH=false")
    if config.low_bandwidth_mode:
        env_lines.append("LOW_BANDWIDTH_MODE=true")
    dot_env = env_path()
    managed_keys = {
        "NEWS_API_KEY",
        "DISPLAY_TIMEZONE",
        "GOOGLE_CSE_API_KEY",
        "GOOGLE_CSE_CX",
        "ENABLE_AI_SUGGESTIONS",
        "ENABLE_DUCKDUCKGO_SEARCH",
        "LOW_BANDWIDTH_MODE",
    }
    preserved_lines: list[str] = []
    if dot_env.exists():
        for line in dot_env.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in line:
                preserved_lines.append(line)
                continue
            key = line.split("=", 1)[0].strip()
            if key in managed_keys:
                continue
            preserved_lines.append(line)

    merged_lines = preserved_lines + env_lines
    if merged_lines:
        dot_env.write_text("\n".join(merged_lines) + "\n", encoding="utf-8")
    elif dot_env.exists():
        dot_env.unlink()
