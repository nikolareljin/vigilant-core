"""Unit tests for event normalization schema."""

from __future__ import annotations

import unittest
from datetime import datetime

from utils.event_normalization import normalize_event_payload


class EventNormalizationTests(unittest.TestCase):
    def test_normalize_event_payload_has_required_schema_fields(self) -> None:
        event = normalize_event_payload(
            source_event={
                "published_at": "2026-02-27T10:15:20Z",
                "source": "News API",
            },
            impact_score=8,
            is_relevant=True,
            location_name="Dallas, TX",
            zip_code="75201",
            latitude=32.7767,
            longitude=-96.7970,
        )

        self.assertEqual(event["schema_version"], "1.0")
        self.assertEqual(event["severity"], "high")
        self.assertGreaterEqual(event["confidence"], 0.0)
        self.assertLessEqual(event["confidence"], 1.0)
        self.assertEqual(event["timestamp_utc"], "2026-02-27T10:15:20Z")
        self.assertEqual(event["location"]["name"], "Dallas, TX")
        self.assertEqual(event["location"]["zip_code"], "75201")
        self.assertEqual(event["location"]["latitude"], 32.7767)
        self.assertEqual(event["location"]["longitude"], -96.7970)

    def test_normalize_event_payload_parses_rfc822_timestamp(self) -> None:
        event = normalize_event_payload(
            source_event={
                "published_at": "Fri, 27 Feb 2026 10:15:20 GMT",
                "source": "RSS",
            },
            impact_score=3,
            is_relevant=False,
            location_name="Berlin",
        )
        self.assertEqual(event["severity"], "low")
        self.assertEqual(event["timestamp_utc"], "2026-02-27T10:15:20Z")

    def test_normalize_event_payload_handles_invalid_timestamp_and_impact(self) -> None:
        event = normalize_event_payload(
            source_event={
                "published_at": "not-a-timestamp",
                "source": "Unknown",
            },
            impact_score="not-a-number",
            is_relevant=False,
            location_name="Austin",
        )
        self.assertEqual(event["severity"], "low")
        # Fallback should still produce valid UTC ISO timestamp.
        parsed = datetime.fromisoformat(event["timestamp_utc"].replace("Z", "+00:00"))
        self.assertIsNotNone(parsed.tzinfo)

    def test_normalize_event_payload_clamps_impact_score_bounds(self) -> None:
        low = normalize_event_payload(
            source_event={"published_at": None, "source": "RSS"},
            impact_score=-99,
            is_relevant=False,
            location_name="Miami",
        )
        high = normalize_event_payload(
            source_event={"published_at": None, "source": "RSS"},
            impact_score=999,
            is_relevant=True,
            location_name="Miami",
        )
        self.assertEqual(low["severity"], "low")
        self.assertEqual(high["severity"], "critical")
        self.assertGreaterEqual(low["confidence"], 0.0)
        self.assertLessEqual(high["confidence"], 1.0)

    def test_normalize_event_payload_supports_empty_location_fields(self) -> None:
        event = normalize_event_payload(
            source_event={"published_at": None, "source": "RSS"},
            impact_score=5,
            is_relevant=True,
            location_name=None,
            zip_code=None,
            latitude=None,
            longitude=None,
        )
        self.assertEqual(event["location"]["name"], "")
        self.assertEqual(event["location"]["zip_code"], "")
        self.assertIsNone(event["location"]["latitude"])
        self.assertIsNone(event["location"]["longitude"])

    def test_normalize_event_payload_uses_source_kind_for_news_api_baseline(self) -> None:
        event = normalize_event_payload(
            source_event={
                "published_at": "2026-02-27T10:15:20Z",
                "source": "CNN",
            },
            impact_score=5,
            is_relevant=True,
            location_name="Dallas, TX",
            source_kind="news_api",
        )
        self.assertEqual(event["confidence"], 0.86)

    def test_normalize_event_payload_confidence_boundaries(self) -> None:
        high = normalize_event_payload(
            source_event={"published_at": None, "source": "News API"},
            impact_score=10,
            is_relevant=True,
            location_name="Seattle",
            source_kind="news_api",
        )
        low = normalize_event_payload(
            source_event={"published_at": None, "source": "Unknown"},
            impact_score=1,
            is_relevant=False,
            location_name="Seattle",
        )
        self.assertGreaterEqual(high["confidence"], 0.0)
        self.assertLessEqual(high["confidence"], 1.0)
        self.assertGreaterEqual(low["confidence"], 0.0)
        self.assertLessEqual(low["confidence"], 1.0)


if __name__ == "__main__":
    unittest.main()
