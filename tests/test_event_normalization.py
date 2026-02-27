"""Unit tests for event normalization schema."""

from __future__ import annotations

import unittest

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


if __name__ == "__main__":
    unittest.main()
