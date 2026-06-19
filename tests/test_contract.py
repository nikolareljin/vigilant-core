from __future__ import annotations

import json
import unittest

from contracts import EmergencyEvent, infer_hazard_type, new_ulid, trust
from contracts.geohash import encode
from utils.event_normalization import normalize_event_payload


class EmergencyEventContractTests(unittest.TestCase):
    def _normalized(self) -> dict:
        return normalize_event_payload(
            source_event={"published_at": "2026-06-19T17:58:00Z", "source": "NWS"},
            impact_score=8,
            is_relevant=True,
            location_name="Mercer County, NJ",
            source_kind="rss",
            zip_code="08540",
            latitude=40.34,
            longitude=-74.65,
        )

    def test_from_normalized_upgrades_losslessly(self) -> None:
        normalized = self._normalized()
        event = EmergencyEvent.from_normalized(
            normalized=normalized,
            title="Tornado Warning issued for Mercer County",
            snippet="Take shelter now.",
            impact_score=8,
            predictive_outcome="Touchdown possible within 30 minutes.",
            url="https://example.gov/alerts/123",
            source="NWS",
            source_kind="rss",
        )
        # v1.0 fields preserved.
        self.assertEqual(event.severity, normalized["severity"])
        self.assertEqual(event.confidence, normalized["confidence"])
        # The v1 timestamp_utc (published/observed time) is preserved verbatim in
        # timestamp_utc; event_timestamp_utc stays unset (no hazard-occurrence
        # time in the normalized payload).
        self.assertEqual(event.timestamp_utc, normalized["timestamp_utc"])
        self.assertIsNone(event.event_timestamp_utc)
        self.assertEqual(event.location["zip_code"], "08540")
        # New platform fields derived.
        self.assertEqual(event.schema_version, "2.0")
        self.assertEqual(event.hazard_type, "tornado")
        # Generic RSS is uncurated (discovered feeds, Google News, Reddit), so it
        # is open_search — not trusted for automation.
        self.assertEqual(event.trust, "open_search")
        self.assertTrue(event.event_id)
        # Geohash enrichment from coordinates.
        self.assertEqual(event.location["geohash"], encode(40.34, -74.65))

    def test_json_round_trip(self) -> None:
        event = EmergencyEvent.from_normalized(
            normalized=self._normalized(),
            title="Flooding near the river",
            snippet="Water rising",
            impact_score=6,
            source="County OEM",
            source_kind="emergency_search",
        )
        restored = EmergencyEvent.from_json(event.to_json())
        self.assertEqual(restored.to_dict(), event.to_dict())

    def test_validate_passes_for_valid_event_and_uses_schema(self) -> None:
        event = EmergencyEvent.from_normalized(
            normalized=self._normalized(), title="Storm", impact_score=4
        )
        event.validate()  # should not raise

    def test_validate_rejects_bad_values(self) -> None:
        event = EmergencyEvent(title="x", hazard_type="not-a-hazard")
        with self.assertRaises(ValueError):
            event.validate()
        event2 = EmergencyEvent(title="x", confidence=5.0)
        with self.assertRaises(ValueError):
            event2.validate()

    def test_validate_enforces_core_invariants_without_jsonschema(self) -> None:
        """Structural checks must catch schema-required invariants even when the
        jsonschema deep check is unavailable/unbundled."""

        # Wrong schema version (e.g. a stale v1 payload).
        with self.assertRaises(ValueError):
            EmergencyEvent(title="x", schema_version="1.0").validate()
        # Empty event_id breaks cross-node dedup.
        with self.assertRaises(ValueError):
            EmergencyEvent(title="x", event_id="").validate()
        # Empty timestamp_utc.
        with self.assertRaises(ValueError):
            EmergencyEvent(title="x", timestamp_utc="").validate()

    def test_validate_raises_value_error_not_type_error_on_malformed_input(self) -> None:
        """Parsing untrusted JSON can yield None/str numerics; validate() must
        surface ValueError, never TypeError."""

        bad = EmergencyEvent.from_dict(
            {"title": "t", "confidence": None, "impact_score": "oops"}
        )
        with self.assertRaises(ValueError):
            bad.validate()

    def test_validate_rejects_numeric_strings_without_jsonschema(self) -> None:
        # A payload with ttl_hops="1" must be rejected by validate(), otherwise
        # can_forward() ("1" > 0) raises TypeError on dependency-free nodes.
        event = EmergencyEvent.from_dict(
            {"title": "t", "severity": "low", "confidence": 0.5,
             "impact_score": 5, "ttl_hops": "1"}
        )
        with self.assertRaises(ValueError):
            event.validate()

    def test_validate_enforces_ulid_and_iso_utc_formats(self) -> None:
        base = EmergencyEvent(title="t", severity="low", confidence=0.5, impact_score=5)
        base.validate()  # a freshly-minted event has a valid ULID + UTC timestamp
        # Non-ULID id.
        bad_id = EmergencyEvent(title="t", severity="low", confidence=0.5,
                                impact_score=5, event_id="not-a-ulid")
        with self.assertRaises(ValueError):
            bad_id.validate()
        # Non-ISO / non-UTC timestamp.
        bad_ts = EmergencyEvent(title="t", severity="low", confidence=0.5,
                                impact_score=5, timestamp_utc="last tuesday")
        with self.assertRaises(ValueError):
            bad_ts.validate()
        # event_timestamp_utc, when present, must also be ISO UTC.
        bad_ets = EmergencyEvent(title="t", severity="low", confidence=0.5,
                                 impact_score=5, event_timestamp_utc="nope")
        with self.assertRaises(ValueError):
            bad_ets.validate()

    def test_strict_decode_requires_mesh_fields(self) -> None:
        # A payload omitting ttl_hops/seen_nodes must be rejected, else a
        # forwarded (possibly TTL-exhausted/looping) event is re-admitted as fresh.
        full = EmergencyEvent(title="t", severity="high", confidence=0.5, impact_score=6)
        payload = json.loads(full.to_json())
        for missing in ("ttl_hops", "seen_nodes"):
            partial = dict(payload)
            partial.pop(missing)
            with self.assertRaises(ValueError):
                EmergencyEvent.from_dict(partial, strict=True)
        # The complete payload still decodes.
        EmergencyEvent.from_dict(payload, strict=True)

    def test_from_dict_ignores_unknown_fields(self) -> None:
        event = EmergencyEvent.from_dict(
            {"title": "t", "hazard_type": "fire", "totally_unknown": 1}
        )
        self.assertEqual(event.hazard_type, "fire")

    def test_from_json_rejects_incomplete_payload(self) -> None:
        # Decoding a transport payload must NOT mint a missing event_id/timestamp;
        # an incomplete payload is rejected so receivers don't assign new
        # identities and corrupt cross-node dedup.
        with self.assertRaises(ValueError):
            EmergencyEvent.from_json("{}")
        with self.assertRaises(ValueError):
            EmergencyEvent.from_json("not json")
        # A complete payload round-trips fine under strict decode.
        full = EmergencyEvent(title="t", hazard_type="fire", severity="high",
                              confidence=0.5, impact_score=6)
        self.assertEqual(EmergencyEvent.from_json(full.to_json()).event_id, full.event_id)

    def test_from_dict_lenient_for_local_construction(self) -> None:
        # Local construction (strict=False, the default) still mints an id.
        event = EmergencyEvent.from_dict({"title": "t"})
        self.assertTrue(event.event_id)

    def test_validate_rejects_malformed_structured_fields(self) -> None:
        event = EmergencyEvent(title="t", severity="low", confidence=0.5, impact_score=5)
        event.seen_nodes = "nodeA"  # should be a list
        with self.assertRaises(ValueError):
            event.validate()
        event2 = EmergencyEvent(title="t", severity="low", confidence=0.5, impact_score=5)
        event2.location = "somewhere"  # should be an object
        with self.assertRaises(ValueError):
            event2.validate()

    def test_hazard_inference(self) -> None:
        self.assertEqual(infer_hazard_type("Wildfire near town"), "fire")
        self.assertEqual(infer_hazard_type("Category 4 hurricane"), "hurricane")
        self.assertEqual(infer_hazard_type("Power outage hits grid"), "outage")
        self.assertEqual(infer_hazard_type("Nothing notable"), "other")

    def test_mesh_helpers(self) -> None:
        event = EmergencyEvent(title="t", ttl_hops=2)
        self.assertTrue(event.can_forward("A"))
        event.mark_seen("A")
        event.mark_seen("A")  # idempotent
        self.assertEqual(event.seen_nodes, ["A"])
        self.assertFalse(event.can_forward("A"))  # looped
        forwarded = event.decremented()
        self.assertEqual(forwarded.ttl_hops, 1)
        self.assertEqual(event.ttl_hops, 2)  # original untouched

    def test_ttl_zero_cannot_forward(self) -> None:
        event = EmergencyEvent(title="t", ttl_hops=0)
        self.assertFalse(event.can_forward("B"))

    def test_trust_ordering(self) -> None:
        self.assertGreater(trust.rank("signed_node"), trust.rank("open_search"))
        self.assertTrue(trust.is_trusted_for_automation("authenticated_api"))
        self.assertFalse(trust.is_trusted_for_automation("open_search"))

    def test_emergency_search_is_open_search_not_curated(self) -> None:
        # emergency_search runs open-web queries, so it must not be trusted for
        # automation as if it were a curated feed (issue #70 boundary).
        self.assertEqual(trust.for_source_kind("emergency_search"), "open_search")
        self.assertFalse(trust.is_trusted_for_automation("open_search"))
        event = EmergencyEvent.from_normalized(
            normalized=self._normalized(), title="x", source_kind="emergency_search"
        )
        self.assertEqual(event.trust, "open_search")

    def test_ulid_is_sortable_and_sized(self) -> None:
        a = new_ulid(timestamp_ms=1000)
        b = new_ulid(timestamp_ms=2000)
        self.assertEqual(len(a), 26)
        self.assertLess(a, b)  # time-ordered


if __name__ == "__main__":
    unittest.main()
