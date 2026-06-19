# EmergencyEvent Schema (v2.0)

`EmergencyEvent` is the canonical, versioned contract every platform component
exchanges — the ingest pipeline, the dashboard, the MQTT bus, sibling apps, and
the Rust/Go edge daemons. It is defined in `contracts/` with:

- `contracts/emergency_event.schema.json` — the JSON Schema (draft 2020-12).
- `contracts/event.py` — the `EmergencyEvent` dataclass, validator, and the
  `from_normalized()` adapter.

It is a **strict superset of the v1.0 normalized alert** (see
[event-normalization.md](event-normalization.md)), so existing alerts upgrade
without data loss while new fields enable cross-node propagation, routing, and
trust. This schema is the basis for ShelfCast-compatible MQTT output (issue #60).

## Fields

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `schema_version` | string (`"2.0"`) | yes | Contract version. |
| `event_id` | string (ULID) | yes | Stable id for cross-node dedup. |
| `origin_node_id` | string \| null | no | Node that first observed/produced it. |
| `title` | string | yes | Headline. |
| `hazard_type` | enum | yes | `storm`, `hurricane`, `tornado`, `fire`, `flood`, `earthquake`, `outage`, `hazmat`, `conflict`, `transport`, `medical`, `other`. |
| `severity` | enum | yes | `low`, `medium`, `high`, `critical`. |
| `confidence` | number 0–1 | yes | Source/relevance-derived confidence. |
| `impact_score` | integer 1–10 | yes | Impact magnitude. |
| `timestamp_utc` | string (ISO-8601) | yes | When the record was observed/created. |
| `event_timestamp_utc` | string \| null | no | When the hazard occurred. |
| `location` | object | no | `{name, zip_code, latitude, longitude, radius_km, geohash}`. |
| `summary` | string | no | Short description. |
| `predictive_outcome` | string | no | AI/heuristic prediction of what happens next. |
| `url` | string \| null | no | Canonical source URL. |
| `sources` | string[] | no | Provenance (merged source names). |
| `trust` | enum | no | `untrusted` < `open_search` < `known_feed` < `authenticated_api` < `signed_node`. |
| `ttl_hops` | integer ≥ 0 | no | Remaining mesh hops; decremented per forward. |
| `seen_nodes` | string[] | no | Nodes that handled it (loop prevention). |
| `actions` | object[] | no | Recommended/dispatched actions (`{kind, detail, status}`). |
| `signature` | string \| null | no | Optional Ed25519 signature (Phase 4). |

## Trust tiers

`trust` is the boundary the AI/RAG pipeline (issue #70) and the routing engine
consult. Higher-trust events may be acted on automatically and are preferred when
channels are contended; lower-trust content (open web search, unauthenticated
mesh) is treated as untrusted input and must never inject instructions into LLM
prompts. `contracts.trust` maps legacy `source_kind`s to tiers and exposes
`rank()` / `is_trusted_for_automation()`.

## Example

```json
{
  "schema_version": "2.0",
  "event_id": "01J9Z3R8K2QF7M4V0WXYABCDEF",
  "origin_node_id": "01J9Z000NODE000000000HUB00",
  "title": "Tornado Warning issued for Mercer County",
  "hazard_type": "tornado",
  "severity": "high",
  "confidence": 0.86,
  "impact_score": 8,
  "timestamp_utc": "2026-06-19T18:00:00Z",
  "event_timestamp_utc": "2026-06-19T17:58:00Z",
  "location": {"name": "Mercer County, NJ", "zip_code": "08540",
               "latitude": 40.34, "longitude": -74.65, "geohash": "dr4vmr9"},
  "summary": "Take shelter now; storm capable of producing a tornado.",
  "predictive_outcome": "Damaging winds and possible touchdown within 30 minutes.",
  "url": "https://example.gov/alerts/123",
  "sources": ["NWS"],
  "trust": "known_feed",
  "ttl_hops": 4,
  "seen_nodes": ["01J9Z000NODE000000000HUB00"],
  "actions": [],
  "signature": null
}
```

## Usage

```python
from contracts import EmergencyEvent

# Build from the existing normalization output (ingest path):
event = EmergencyEvent.from_normalized(normalized=normalized_payload,
                                       title=title, snippet=snippet,
                                       impact_score=8, source="NWS",
                                       source_kind="rss")
event.validate()          # raises on contract violation (uses jsonschema if present)
payload = event.to_json()  # for MQTT/transports

# Parse on the receiving side (transport / edge daemon):
received = EmergencyEvent.from_json(payload)
```

## MQTT topics

A later release adds an MQTT transport plugin that publishes schema-valid events
to:

- `intel/events/normalized` — every event (issue #57).
- `intel/events/high_priority` — `high`/`critical` events (issue #58).

The base topic will be configurable via the plugin's `base_topic` option. This
contract defines the payload shape those topics carry.
