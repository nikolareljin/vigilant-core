"""Configuration management for VigilantCore."""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from dotenv import load_dotenv

APP_NAME = "VigilantCore"


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


def load_config() -> AppConfig:
    cfg_path = config_path()
    if not cfg_path.exists():
        load_dotenv(env_path())
        cfg = AppConfig()
        cfg.news_api_key = os.getenv("NEWS_API_KEY")
        cfg.display_timezone = os.getenv("DISPLAY_TIMEZONE") or os.getenv("TIMEZONE")
        cfg.google_cse_api_key = os.getenv("GOOGLE_CSE_API_KEY")
        cfg.google_cse_cx = os.getenv("GOOGLE_CSE_CX")
        cfg.bing_search_key = os.getenv("BING_SEARCH_KEY")
        cfg.bing_search_endpoint = os.getenv("BING_SEARCH_ENDPOINT")
        cfg.bing_search_market = os.getenv("BING_SEARCH_MARKET")
        cfg.bing_search_safe = os.getenv("BING_SEARCH_SAFE")
        cfg.enable_duckduckgo_search = bool(
            (os.getenv("ENABLE_DUCKDUCKGO_SEARCH") or "true").lower() in ("1", "true", "yes")
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
        relax_location_filter=bool(data.get("relax_location_filter", False)),
        prefer_light_model=bool(data.get("prefer_light_model", True)),
        insight_refresh_minutes=int(data.get("insight_refresh_minutes", 5)),
        rss_feeds=data.get("rss_feeds", []),
        use_only_rss_feeds=bool(data.get("use_only_rss_feeds", False)),
        disable_rss_fetch=bool(data.get("disable_rss_fetch", False)),
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
        enable_duckduckgo_search=bool(data.get("enable_duckduckgo_search", True)),
    )
    cfg.news_api_key = cfg.news_api_key or os.getenv("NEWS_API_KEY")
    cfg.display_timezone = cfg.display_timezone or os.getenv("DISPLAY_TIMEZONE") or os.getenv("TIMEZONE")
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
    if env_lines:
        env_path().write_text("\n".join(env_lines) + "\n", encoding="utf-8")
