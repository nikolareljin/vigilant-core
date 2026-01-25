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
    prefer_light_model: bool = True
    rss_feeds: List[str] = field(default_factory=list)
    polling_minutes: int = 15
    news_api_key: Optional[str] = None


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
        return AppConfig()
    data = json.loads(cfg_path.read_text(encoding="utf-8"))
    cfg = AppConfig(
        subject=data.get("subject", "Impactful Events"),
        question=data.get("question", ""),
        location_name=data.get("location_name", "Your Area"),
        zip_code=data.get("zip_code"),
        latitude=data.get("latitude"),
        longitude=data.get("longitude"),
        radius_km=int(data.get("radius_km", 50)),
        prefer_light_model=bool(data.get("prefer_light_model", True)),
        rss_feeds=data.get("rss_feeds", []),
        polling_minutes=int(data.get("polling_minutes", 15)),
        news_api_key=data.get("news_api_key"),
    )
    load_dotenv(env_path())
    cfg.news_api_key = cfg.news_api_key or os.getenv("NEWS_API_KEY")
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
        "prefer_light_model": config.prefer_light_model,
        "rss_feeds": config.rss_feeds,
        "polling_minutes": config.polling_minutes,
        "news_api_key": None,
    }
    config_path().write_text(json.dumps(data, indent=2), encoding="utf-8")
    if config.news_api_key:
        env_path().write_text(
            f"NEWS_API_KEY={config.news_api_key}\n", encoding="utf-8"
        )
