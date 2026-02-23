from __future__ import annotations

import unittest

from utils.sources import (
    build_contextual_google_news_feeds,
    build_emergency_service_queries,
    build_utility_search_queries,
)


class SourceQueryTests(unittest.TestCase):
    def test_utility_queries_include_poweroutage_and_multi_utility_terms(self) -> None:
        queries = build_utility_search_queries("Dallas", "75201")
        combined = " || ".join(queries).lower()
        self.assertIn("poweroutage.us", combined)
        self.assertIn("water utility", combined)
        self.assertIn("gas utility", combined)
        self.assertIn("wind farm outage", combined)
        self.assertIn("solar outage", combined)

    def test_emergency_service_queries_include_transport_and_aviation(self) -> None:
        queries = build_emergency_service_queries("Dallas", "75201")
        combined = " || ".join(queries).lower()
        self.assertIn("traffic alerts", combined)
        self.assertIn("transit service alerts", combined)
        self.assertIn("airport operations alerts", combined)
        self.assertIn("faa ground stop", combined)
        self.assertIn("flood warning", combined)
        self.assertIn("tornado warning", combined)

    def test_contextual_google_news_feeds_expand_for_conflict(self) -> None:
        feeds = build_contextual_google_news_feeds(
            "war conflict escalation and missile strikes",
            "Ukraine",
        )
        text = " || ".join(feeds).lower()
        self.assertIn("news.google.com/rss/search", text)
        self.assertIn("ukraine+conflict+escalation", text)
        self.assertIn("global+conflict+alerts", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
