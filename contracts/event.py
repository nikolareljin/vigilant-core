"""The canonical ``EmergencyEvent`` contract shared across the platform.

Every component — the ingest pipeline, the dashboard, the MQTT bus, and the
low-power Rust/Go edge daemons — agrees on this one shape. It is a strict
superset of the v1.0 normalized alert produced by
``utils.event_normalization.normalize_event_payload`` (see ``from_normalized``),
so existing alerts upgrade losslessly while new fields (stable ``event_id``,
``origin_node_id``, ``hazard_type``, ``trust``, mesh ``ttl_hops``/``seen_nodes``,
recommended ``actions``) enable cross-node propagation, routing, and trust.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping, Optional

from . import trust as trust_tiers
from .geohash import encode_optional
from .ids import new_ulid

SCHEMA_VERSION = "2.0"

# Canonical hazard taxonomy. ``other`` is the catch-all; callers should prefer a
# specific value so routing/geo-dedup can reason about event class.
HAZARD_TYPES: tuple[str, ...] = (
    "storm",
    "hurricane",
    "tornado",
    "fire",
    "flood",
    "earthquake",
    "outage",
    "hazmat",
    "conflict",
    "transport",
    "medical",
    "other",
)

SEVERITIES: tuple[str, ...] = ("low", "medium", "high", "critical")

# Fields a payload received from another node must carry explicitly. We refuse to
# mint these on decode (see ``from_dict(strict=True)``) because inventing an
# identity/timestamp/mesh-state would corrupt cross-node dedup and loop/storm
# protection (a missing ttl_hops/seen_nodes would otherwise default to a fresh,
# full-TTL, empty-path event and re-admit an exhausted or looping message).
REQUIRED_ON_DECODE: tuple[str, ...] = (
    "schema_version",
    "event_id",
    "title",
    "timestamp_utc",
    "hazard_type",
    "severity",
    "confidence",
    "impact_score",
    "ttl_hops",
    "seen_nodes",
)

# A ULID is 26 Crockford base32 chars (excludes I, L, O, U); accept either case.
_ULID_RE = re.compile(r"^[0-9A-HJKMNP-TV-Z]{26}$", re.IGNORECASE)


def _looks_like_ulid(value: Any) -> bool:
    return isinstance(value, str) and bool(_ULID_RE.match(value))


def _looks_like_iso_utc(value: Any) -> bool:
    """True if ``value`` is an ISO-8601 timestamp in UTC (``Z`` or ``+00:00``)."""

    if not isinstance(value, str) or not value:
        return False
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.utcoffset() == timedelta(0)

# Keyword → hazard_type. First match wins; order matters (specific before generic).
_HAZARD_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("hurricane", ("hurricane", "typhoon", "cyclone")),
    ("tornado", ("tornado", "twister", "funnel cloud")),
    ("fire", ("wildfire", "fire", "blaze", "burn")),
    ("flood", ("flood", "flash flood", "storm surge", "inundation")),
    ("earthquake", ("earthquake", "quake", "seismic", "aftershock")),
    ("outage", ("power outage", "blackout", "grid", "outage")),
    ("hazmat", ("hazmat", "chemical spill", "gas leak", "radiation", "toxic")),
    ("conflict", ("shooting", "explosion", "attack", "shelling", "airstrike", "conflict")),
    ("transport", ("crash", "derailment", "collision", "pileup", "aviation", "train")),
    ("storm", ("storm", "thunderstorm", "blizzard", "snow", "wind", "hail")),
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _require_number(value: Any, field_name: str) -> float:
    """Return ``value`` as float, raising ``ValueError`` unless it is a real
    number. Rejects strings/None/bool so the no-``jsonschema`` path does not
    accept e.g. ``confidence="0.5"`` and leave a non-numeric on the object."""

    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field_name} must be a number, got {type(value).__name__}")
    return float(value)


def _require_int(value: Any, field_name: str) -> int:
    """Return ``value`` if it is a real int, raising ``ValueError`` otherwise.
    Rejects numeric strings/None/bool so downstream integer ops (e.g.
    ``ttl_hops > 0`` in ``can_forward()``) cannot raise ``TypeError``."""

    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field_name} must be an integer, got {type(value).__name__}")
    return value


def infer_hazard_type(*texts: str | None) -> str:
    """Classify a hazard from free text using the keyword taxonomy."""

    haystack = " ".join(t for t in texts if t).lower()
    if not haystack:
        return "other"
    for hazard, keywords in _HAZARD_KEYWORDS:
        if any(keyword in haystack for keyword in keywords):
            return hazard
    return "other"


@dataclass
class EmergencyEvent:
    """Platform-wide emergency event. Construct via ``from_normalized`` from the
    ingest pipeline, or ``from_dict``/``from_json`` from a transport."""

    title: str
    schema_version: str = SCHEMA_VERSION
    event_id: str = field(default_factory=new_ulid)
    origin_node_id: Optional[str] = None
    hazard_type: str = "other"
    severity: str = "low"
    confidence: float = 0.0
    impact_score: int = 1
    timestamp_utc: str = field(default_factory=_now_iso)
    event_timestamp_utc: Optional[str] = None
    location: dict[str, Any] = field(default_factory=dict)
    summary: str = ""
    predictive_outcome: str = ""
    url: Optional[str] = None
    sources: list[str] = field(default_factory=list)
    trust: str = trust_tiers.DEFAULT_TRUST
    # Mesh propagation controls (issues #33/#34).
    ttl_hops: int = 4
    seen_nodes: list[str] = field(default_factory=list)
    # Recommended/dispatched response actions (routing + automation).
    actions: list[dict[str, Any]] = field(default_factory=list)
    # Optional Ed25519 signature, populated in Phase 4.
    signature: Optional[str] = None

    # ----- serialization -------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, ensure_ascii=False)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any], *, strict: bool = False) -> "EmergencyEvent":
        """Build an event from a mapping.

        With ``strict=True`` (the default for :meth:`from_json`, i.e. decoding a
        payload received from another node), the payload must carry every required
        field and pass full :meth:`validate` — we refuse to *mint* a missing
        ``event_id``/``timestamp_utc``/mesh-state on decode, and we reject
        malformed values (e.g. ``ttl_hops="1"`` or a non-ULID id) up front so the
        ``ValueError`` guarantee holds before any downstream mesh op runs. Lenient
        mode (the default here) is for locally-constructed events, where defaults
        like a fresh ULID are intended.
        """

        if not isinstance(data, Mapping):
            raise ValueError("event payload must be a JSON object")
        if strict:
            missing = [k for k in REQUIRED_ON_DECODE if data.get(k) in (None, "")]
            if missing:
                raise ValueError(
                    f"payload missing required field(s): {', '.join(missing)}"
                )
        known = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        filtered = {k: v for k, v in data.items() if k in known}
        if "title" not in filtered:
            filtered["title"] = data.get("title") or "(no title)"
        event = cls(**filtered)
        if strict:
            event.validate()
        return event

    @classmethod
    def from_json(cls, raw: str | bytes, *, strict: bool = True) -> "EmergencyEvent":
        """Decode an event from JSON. Strict by default: payloads from transports
        that omit required fields are rejected, not silently completed."""

        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, TypeError) as exc:
            raise ValueError(f"invalid event JSON: {exc}") from exc
        return cls.from_dict(data, strict=strict)

    # ----- mesh helpers --------------------------------------------------
    def mark_seen(self, node_id: str) -> None:
        """Record that ``node_id`` has handled this event (loop prevention)."""

        if node_id and node_id not in self.seen_nodes:
            self.seen_nodes.append(node_id)

    def can_forward(self, node_id: str) -> bool:
        """Whether this node should forward the event onward over the mesh."""

        return self.ttl_hops > 0 and node_id not in self.seen_nodes

    def decremented(self) -> "EmergencyEvent":
        """Return a copy with one hop consumed, for forwarding to peers."""

        clone = EmergencyEvent.from_dict(self.to_dict())
        clone.ttl_hops = max(0, self.ttl_hops - 1)
        return clone

    # ----- validation ----------------------------------------------------
    def validate(self) -> None:
        """Raise ``ValueError`` if the event violates the contract invariants.

        The structural checks below fully cover the schema's required invariants
        and always run, so validation is correct even on dependency-free edge
        nodes (no ``jsonschema``) and in packaged builds where the schema file may
        not be bundled. When ``jsonschema`` *is* available, the bundled schema is
        additionally enforced as a deep check. Every failure path raises
        ``ValueError`` — never ``TypeError`` — even for malformed parsed JSON.
        """

        if not self.title:
            raise ValueError("title is required")
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError(
                f"unsupported schema_version: {self.schema_version!r} (expected {SCHEMA_VERSION})"
            )
        if not _looks_like_ulid(self.event_id):
            raise ValueError("event_id must be a 26-character ULID")
        if not _looks_like_iso_utc(self.timestamp_utc):
            raise ValueError("timestamp_utc must be an ISO-8601 UTC timestamp")
        if self.event_timestamp_utc is not None and not _looks_like_iso_utc(
            self.event_timestamp_utc
        ):
            raise ValueError("event_timestamp_utc must be an ISO-8601 UTC timestamp")
        if self.hazard_type not in HAZARD_TYPES:
            raise ValueError(f"invalid hazard_type: {self.hazard_type!r}")
        if self.severity not in SEVERITIES:
            raise ValueError(f"invalid severity: {self.severity!r}")
        if not 0.0 <= _require_number(self.confidence, "confidence") <= 1.0:
            raise ValueError("confidence must be within [0, 1]")
        if not 1 <= _require_int(self.impact_score, "impact_score") <= 10:
            raise ValueError("impact_score must be within [1, 10]")
        if _require_int(self.ttl_hops, "ttl_hops") < 0:
            raise ValueError("ttl_hops must be non-negative")
        if self.trust not in trust_tiers.TRUST_TIERS:
            raise ValueError(f"invalid trust tier: {self.trust!r}")
        # Structured-field shapes (caught here so the no-jsonschema path doesn't
        # accept e.g. seen_nodes="nodeA", which would crash mark_seen() later).
        if not isinstance(self.location, dict):
            raise ValueError("location must be an object")
        for field_name in ("sources", "seen_nodes", "actions"):
            if not isinstance(getattr(self, field_name), list):
                raise ValueError(f"{field_name} must be a list")

        # Optional deep validation against the bundled JSON Schema, when present.
        try:
            import jsonschema  # type: ignore
        except ImportError:
            return
        try:
            from .schema import load_schema

            schema = load_schema()
        except FileNotFoundError:
            # Schema not bundled (e.g. packaged build); structural checks suffice.
            return
        try:
            jsonschema.validate(self.to_dict(), schema)
        except jsonschema.ValidationError as exc:
            raise ValueError(f"schema validation failed: {exc.message}") from exc

    # ----- adapter from the existing pipeline ----------------------------
    @classmethod
    def from_normalized(
        cls,
        *,
        normalized: Mapping[str, Any],
        title: str,
        snippet: str = "",
        impact_score: Any = 1,
        predictive_outcome: str = "",
        url: Optional[str] = None,
        source: Optional[str] = None,
        source_kind: Optional[str] = None,
        merged_sources: Any = (),
        origin_node_id: Optional[str] = None,
        hazard_type: Optional[str] = None,
        trust: Optional[str] = None,
        event_timestamp_utc: Optional[str] = None,
    ) -> "EmergencyEvent":
        """Build an ``EmergencyEvent`` from ``normalize_event_payload`` output.

        ``normalized`` is the dict returned by
        ``utils.event_normalization.normalize_event_payload`` (severity,
        confidence, timestamp_utc, location). The upgrade is lossless: the v1
        ``timestamp_utc`` (the published/observed time) is preserved verbatim in
        ``timestamp_utc``. ``event_timestamp_utc`` (when the hazard itself
        occurred) is left unset unless the caller explicitly supplies one, since
        the normalized payload carries only the observed time.
        """

        location = dict(normalized.get("location") or {})
        # Enrich location with a geohash for geo-routing/dedup when coords exist.
        if "geohash" not in location:
            geo = encode_optional(location.get("latitude"), location.get("longitude"))
            if geo:
                location["geohash"] = geo

        sources: list[str] = []
        for candidate in (source, *(merged_sources or ())):
            value = str(candidate or "").strip()
            if value and value not in sources:
                sources.append(value)

        resolved_trust = trust or trust_tiers.for_source_kind(source_kind)
        resolved_hazard = hazard_type or infer_hazard_type(title, snippet)

        return cls(
            title=title or "(no title)",
            origin_node_id=origin_node_id,
            hazard_type=resolved_hazard,
            severity=str(normalized.get("severity", "low")),
            confidence=float(normalized.get("confidence", 0.0) or 0.0),
            impact_score=max(1, min(10, int(impact_score or 1))),
            timestamp_utc=normalized.get("timestamp_utc") or _now_iso(),
            event_timestamp_utc=event_timestamp_utc,
            location=location,
            summary=snippet or "",
            predictive_outcome=predictive_outcome or "",
            url=url,
            sources=sources or ["Unknown"],
            trust=resolved_trust,
        )
