"""Timestamp formatting helpers for UI display."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover - Python <3.9 fallback
    ZoneInfo = None  # type: ignore[assignment]


def _resolve_display_timezone(tz_name: Optional[str]):
    """Return the configured display tz, or the current host local tz."""
    if tz_name:
        if ZoneInfo is None:
            raise ValueError("Named timezones require zoneinfo support")
        return ZoneInfo(tz_name)
    return datetime.now().astimezone().tzinfo


def format_alert_timestamp(value: Optional[str], tz_name: Optional[str] = None) -> str:
    """Format stored alert timestamps for UI display in local/selected timezone.

    Stored `created_at` values are typically naive UTC ISO strings. If the input has
    no timezone info, we assume UTC before converting for display.
    """
    raw = (value or "").strip()
    if not raw:
        return ""

    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return raw

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)

    try:
        display_tz = _resolve_display_timezone(tz_name)
    except Exception:
        display_tz = datetime.now().astimezone().tzinfo

    if display_tz is None:
        return parsed.strftime("%Y-%m-%d %H:%M:%S")

    return parsed.astimezone(display_tz).strftime("%Y-%m-%d %H:%M:%S")
