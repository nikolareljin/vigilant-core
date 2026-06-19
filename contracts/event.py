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
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
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
    def from_dict(cls, data: Mapping[str, Any]) -> "EmergencyEvent":
        known = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        filtered = {k: v for k, v in data.items() if k in known}
        if "title" not in filtered:
            filtered["title"] = data.get("title") or "(no title)"
        return cls(**filtered)

    @classmethod
    def from_json(cls, raw: str | bytes) -> "EmergencyEvent":
        return cls.from_dict(json.loads(raw))

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

        Uses ``jsonschema`` against the bundled schema when available, and always
        applies the cheap structural checks so validation works on dependency-free
        edge nodes too.
        """

        if not self.title:
            raise ValueError("title is required")
        if self.hazard_type not in HAZARD_TYPES:
            raise ValueError(f"invalid hazard_type: {self.hazard_type!r}")
        if self.severity not in SEVERITIES:
            raise ValueError(f"invalid severity: {self.severity!r}")
        if not 0.0 <= float(self.confidence) <= 1.0:
            raise ValueError("confidence must be within [0, 1]")
        if not 1 <= int(self.impact_score) <= 10:
            raise ValueError("impact_score must be within [1, 10]")
        if self.ttl_hops < 0:
            raise ValueError("ttl_hops must be non-negative")
        if self.trust not in trust_tiers.TRUST_TIERS:
            raise ValueError(f"invalid trust tier: {self.trust!r}")

        try:
            import jsonschema  # type: ignore
        except Exception:
            return
        from .schema import load_schema

        jsonschema.validate(self.to_dict(), load_schema())

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
    ) -> "EmergencyEvent":
        """Build an ``EmergencyEvent`` from ``normalize_event_payload`` output.

        ``normalized`` is the dict returned by
        ``utils.event_normalization.normalize_event_payload`` (severity,
        confidence, timestamp_utc, location). All v1.0 fields are preserved; the
        new platform fields are derived or defaulted.
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
            event_timestamp_utc=normalized.get("timestamp_utc"),
            location=location,
            summary=snippet or "",
            predictive_outcome=predictive_outcome or "",
            url=url,
            sources=sources or ["Unknown"],
            trust=resolved_trust,
        )
