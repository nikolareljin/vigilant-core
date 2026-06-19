"""Minimal, dependency-free geohash encoder.

Geohashes turn a lat/lon into a short string where a shared prefix implies
spatial proximity. The platform uses them for cheap geo-routing and cross-node
spatial dedup (events about the same area share a geohash prefix) without
pulling in a geospatial library on low-power field nodes.
"""

from __future__ import annotations

from typing import Optional

_BASE32 = "0123456789bcdefghjkmnpqrstuvwxyz"


def encode(latitude: float, longitude: float, precision: int = 7) -> str:
    """Encode a coordinate to a geohash of the given precision (default 7 ~= 153m)."""

    lat_range = [-90.0, 90.0]
    lon_range = [-180.0, 180.0]
    geohash: list[str] = []
    bits = [16, 8, 4, 2, 1]
    bit = 0
    ch = 0
    even = True

    while len(geohash) < precision:
        if even:
            mid = (lon_range[0] + lon_range[1]) / 2
            if longitude > mid:
                ch |= bits[bit]
                lon_range[0] = mid
            else:
                lon_range[1] = mid
        else:
            mid = (lat_range[0] + lat_range[1]) / 2
            if latitude > mid:
                ch |= bits[bit]
                lat_range[0] = mid
            else:
                lat_range[1] = mid
        even = not even
        if bit < 4:
            bit += 1
        else:
            geohash.append(_BASE32[ch])
            bit = 0
            ch = 0

    return "".join(geohash)


def encode_optional(
    latitude: Optional[float], longitude: Optional[float], precision: int = 7
) -> Optional[str]:
    """Encode only when both coordinates are present; otherwise return ``None``."""

    if latitude is None or longitude is None:
        return None
    try:
        return encode(float(latitude), float(longitude), precision)
    except (TypeError, ValueError):
        return None
