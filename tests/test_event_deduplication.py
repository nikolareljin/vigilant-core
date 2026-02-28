"""Unit tests for event deduplication engine."""

from __future__ import annotations

import unittest

from utils.event_deduplication import deduplicate_events


class EventDeduplicationTests(unittest.TestCase):
    def test_merges_overlapping_multi_source_alerts(self) -> None:
        events = deduplicate_events(
            [
                {
                    "url": "https://a.example.com/alerts/bridge-fire-1",
                    "title": "Major bridge fire causes downtown closure",
                    "snippet": "Officials report highway closure near downtown after bridge fire.",
                    "published_at": "2026-02-27T10:00:00Z",
                    "source": "City News",
                    "source_kind": "rss",
                },
                {
                    "url": "https://b.example.com/live/bridge-fire-coverage",
                    "title": "Downtown closure after major bridge fire",
                    "snippet": "Emergency crews respond to large fire and road closure.",
                    "published_at": "2026-02-27T11:10:00Z",
                    "source": "Emergency Search",
                    "source_kind": "emergency_search",
                },
            ]
        )

        self.assertEqual(len(events), 1)
        merged = events[0]
        self.assertEqual(merged.merged_count, 2)
        self.assertEqual(merged.source_kind, "emergency_search")
        self.assertIn("City News", merged.source)
        self.assertIn("Emergency Search", merged.source)
        self.assertIn("bridge fire", merged.title.lower())

    def test_does_not_merge_distinct_incidents(self) -> None:
        events = deduplicate_events(
            [
                {
                    "url": "https://a.example.com/alerts/grid-outage",
                    "title": "Regional power outage affects 10,000 customers",
                    "snippet": "Utility crews are restoring power in the north district.",
                    "published_at": "2026-02-27T09:00:00Z",
                    "source": "Utility Wire",
                    "source_kind": "rss",
                },
                {
                    "url": "https://b.example.com/alerts/flood-warning",
                    "title": "Flash flood warning issued for river basin",
                    "snippet": "Authorities advise evacuation in low-lying neighborhoods.",
                    "published_at": "2026-02-27T09:30:00Z",
                    "source": "Weather Alert Center",
                    "source_kind": "news_api",
                },
            ]
        )

        self.assertEqual(len(events), 2)
        self.assertTrue(all(event.merged_count == 1 for event in events))

    def test_merges_same_headline_when_punctuation_differs(self) -> None:
        events = deduplicate_events(
            [
                {
                    "url": "https://a.example.com/item/1",
                    "title": "Airport disruption: severe weather delays",
                    "snippet": "Flights delayed at regional airport.",
                    "published_at": "2026-02-27T13:00:00Z",
                    "source": "Transit Desk",
                    "source_kind": "bing_search",
                },
                {
                    "url": "https://b.example.com/item/2",
                    "title": "Airport disruption severe weather delays",
                    "snippet": "Multiple flight delays continue.",
                    "published_at": "2026-02-27T13:20:00Z",
                    "source": "News API",
                    "source_kind": "news_api",
                },
            ]
        )

        self.assertEqual(len(events), 1)
        merged = events[0]
        self.assertEqual(merged.merged_count, 2)
        self.assertEqual(merged.source_kind, "news_api")

    def test_empty_titles_do_not_force_false_merge(self) -> None:
        events = deduplicate_events(
            [
                {
                    "url": "https://a.example.com/item/untitled-1",
                    "title": "",
                    "snippet": "",
                    "published_at": "2026-02-27T13:00:00Z",
                    "source": "Feed A",
                    "source_kind": "rss",
                },
                {
                    "url": "https://b.example.com/item/untitled-2",
                    "title": "",
                    "snippet": "",
                    "published_at": "2026-02-27T13:05:00Z",
                    "source": "Feed B",
                    "source_kind": "rss",
                },
            ]
        )
        self.assertEqual(len(events), 2)
        self.assertTrue(all(event.merged_count == 1 for event in events))

    def test_placeholder_titles_do_not_force_false_merge(self) -> None:
        events = deduplicate_events(
            [
                {
                    "url": "https://a.example.com/item/untitled-placeholder-1",
                    "title": "(no title)",
                    "snippet": "",
                    "published_at": "2026-02-27T13:00:00Z",
                    "source": "Feed A",
                    "source_kind": "rss",
                },
                {
                    "url": "https://b.example.com/item/untitled-placeholder-2",
                    "title": "(no title)",
                    "snippet": "",
                    "published_at": "2026-02-27T13:05:00Z",
                    "source": "Feed B",
                    "source_kind": "rss",
                },
            ]
        )
        self.assertEqual(len(events), 2)
        self.assertTrue(all(event.merged_count == 1 for event in events))

    def test_semantic_merge_requires_timestamps_for_window_check(self) -> None:
        events = deduplicate_events(
            [
                {
                    "url": "https://a.example.com/item/storm-1",
                    "title": "Severe storm causes citywide outages",
                    "snippet": "Emergency teams report widespread outages and road closures.",
                    "published_at": None,
                    "source": "Feed A",
                    "source_kind": "rss",
                },
                {
                    "url": "https://b.example.com/item/storm-2",
                    "title": "Citywide outages reported after severe storm warning",
                    "snippet": "Road closures continue while crews restore power.",
                    "published_at": None,
                    "source": "Feed B",
                    "source_kind": "rss",
                },
            ]
        )
        self.assertEqual(len(events), 2)
        self.assertTrue(all(event.merged_count == 1 for event in events))


if __name__ == "__main__":
    unittest.main()
