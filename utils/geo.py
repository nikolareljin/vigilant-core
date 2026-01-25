"""Lightweight geo lookup for auto-population."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import httpx


@dataclass
class GeoInfo:
    city: str = ""
    region: str = ""
    postal: str = ""
    latitude: Optional[float] = None
    longitude: Optional[float] = None


def detect_geo() -> GeoInfo:
    services = [
        "https://ipapi.co/json/",
        "https://ipinfo.io/json",
    ]
    for url in services:
        try:
            resp = httpx.get(url, timeout=4.0)
            resp.raise_for_status()
            data = resp.json()
        except Exception:
            continue
        city = data.get("city") or ""
        region = data.get("region") or data.get("region_name") or ""
        postal = data.get("postal") or data.get("zip") or ""
        lat = data.get("latitude") or data.get("lat")
        lon = data.get("longitude") or data.get("lon")
        if not (lat and lon):
            loc = data.get("loc")
            if loc and "," in loc:
                lat_str, lon_str = loc.split(",", 1)
                lat = lat or lat_str
                lon = lon or lon_str
        try:
            lat_val = float(lat) if lat else None
        except ValueError:
            lat_val = None
        try:
            lon_val = float(lon) if lon else None
        except ValueError:
            lon_val = None
        return GeoInfo(
            city=city,
            region=region,
            postal=postal,
            latitude=lat_val,
            longitude=lon_val,
        )
    return GeoInfo()
