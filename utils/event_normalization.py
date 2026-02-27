"""Event normalization helpers for a unified alert schema."""

from __future__ import annotations

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Mapping


SOURCE_BASELINE = {
    "news_api": 0.78,
    "google_cse": 0.72,
    "bing_search": 0.68,
    "duckduckgo": 0.64,
    "emergency_search": 0.74,
    "rss": 0.65,
}


def _to_utc_iso(value: str | None) -> str:
    now_utc = datetime.now(timezone.utc)
    if not value:
        return now_utc.isoformat().replace("+00:00", "Z")

    raw = str(value).strip()
    if not raw:
        return now_utc.isoformat().replace("+00:00", "Z")

    # 1) Native ISO timestamps.
    try:
        normalized = raw.replace("Z", "+00:00")
        dt = datetime.fromisoformat(normalized)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    except ValueError:
        pass

    # 2) RFC822-style feed timestamps.
    try:
        dt = parsedate_to_datetime(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    except (TypeError, ValueError):
        pass

    return now_utc.isoformat().replace("+00:00", "Z")


def _normalize_impact_score(impact_score: Any) -> int:
    try:
        score = int(impact_score)
    except (TypeError, ValueError):
        try:
            score = int(float(impact_score))
        except (TypeError, ValueError):
            score = 1
    return max(1, min(10, score))


def _severity_from_impact(impact_score: Any) -> str:
    score = _normalize_impact_score(impact_score)
    if score >= 9:
        return "critical"
    if score >= 7:
        return "high"
    if score >= 4:
        return "medium"
    return "low"


def _confidence_from_signal(
    source: str,
    impact_score: Any,
    is_relevant: bool,
    source_kind: str | None = None,
) -> float:
    source_key = (source or "").strip().lower()
    normalized_source_kind = (source_kind or "").strip().lower()
    source_aliases = {
        "news api": "news_api",
        "google cse": "google_cse",
        "bing search": "bing_search",
        "duckduckgo": "duckduckgo",
        "emergency search": "emergency_search",
        "rss": "rss",
    }
    if normalized_source_kind in SOURCE_BASELINE:
        baseline = SOURCE_BASELINE[normalized_source_kind]
    elif source_key in source_aliases:
        baseline = SOURCE_BASELINE[source_aliases[source_key]]
    else:
        baseline = 0.66
    impact_adjust = max(-0.08, min(0.14, ((_normalize_impact_score(impact_score) - 5) * 0.02)))
    relevance_adjust = 0.08 if is_relevant else -0.1
    confidence = baseline + impact_adjust + relevance_adjust
    return round(max(0.0, min(1.0, confidence)), 3)


def normalize_event_payload(
    *,
    source_event: Mapping[str, Any],
    impact_score: Any,
    is_relevant: bool,
    location_name: str,
    source_kind: str | None = None,
    zip_code: str | None = None,
    latitude: float | None = None,
    longitude: float | None = None,
) -> dict[str, Any]:
    """Return a normalized event object for persisted alerts and API consumers."""

    published_at = source_event.get("published_at")
    source = str(source_event.get("source") or "Unknown")
    normalized_timestamp = _to_utc_iso(str(published_at) if published_at else None)
    severity = _severity_from_impact(impact_score)
    confidence = _confidence_from_signal(source, impact_score, is_relevant, source_kind=source_kind)

    # Normalize location fields: empty strings for missing text, None for missing coordinates.
    normalized_location_name = location_name if location_name is not None else ""
    normalized_zip_code = zip_code if zip_code is not None else ""

    location = {
        "name": normalized_location_name,
        "zip_code": normalized_zip_code,
        "latitude": latitude,
        "longitude": longitude,
    }

    return {
        "schema_version": "1.0",
        "severity": severity,
        "confidence": confidence,
        "timestamp_utc": normalized_timestamp,
        "location": location,
    }
