from __future__ import annotations

import unittest
from unittest.mock import patch

from engine.monitor import MonitorEngine
from utils.config import AppConfig


class SourceHealthTests(unittest.TestCase):
    def _build_engine(self, **config_overrides) -> MonitorEngine:
        config = AppConfig(**config_overrides)
        with patch("engine.monitor.ImpactParser") as parser_cls:
            parser = parser_cls.return_value
            parser.current_model.return_value = "test-model"
            return MonitorEngine(config)

    def test_source_health_initializes_with_enabled_flags(self) -> None:
        engine = self._build_engine(
            disable_rss_fetch=True,
            enable_duckduckgo_search=False,
            news_api_key=None,
            google_cse_api_key=None,
            google_cse_cx=None,
            bing_search_key=None,
            location_name="",
            zip_code=None,
        )
        by_key = {entry["source_key"]: entry for entry in engine.get_source_health_snapshot()}
        self.assertFalse(by_key["rss"]["enabled"])
        self.assertFalse(by_key["duckduckgo"]["enabled"])
        self.assertFalse(by_key["news_api"]["enabled"])
        self.assertFalse(by_key["google_cse"]["enabled"])
        self.assertFalse(by_key["bing_search"]["enabled"])
        self.assertFalse(by_key["emergency_search"]["enabled"])

    def test_source_health_records_success_and_failures(self) -> None:
        engine = self._build_engine()

        engine._record_source_fetch("rss", success=True, latency_ms=18.6, item_count=4)
        after_success = {entry["source_key"]: entry for entry in engine.get_source_health_snapshot()}["rss"]
        self.assertEqual(after_success["error_count"], 0)
        self.assertEqual(after_success["attempt_count"], 1)
        self.assertEqual(after_success["success_count"], 1)
        self.assertEqual(after_success["last_item_count"], 4)
        self.assertIsNotNone(after_success["last_successful_fetch_utc"])
        self.assertAlmostEqual(float(after_success["last_latency_ms"]), 18.6, places=1)

        engine._record_source_fetch(
            "rss",
            success=False,
            latency_ms=27.3,
            item_count=0,
            error="timeout",
        )
        after_failure = {entry["source_key"]: entry for entry in engine.get_source_health_snapshot()}["rss"]
        self.assertEqual(after_failure["error_count"], 1)
        self.assertEqual(after_failure["attempt_count"], 2)
        self.assertEqual(after_failure["success_count"], 1)
        self.assertEqual(after_failure["last_error"], "timeout")
        self.assertIsNotNone(after_failure["last_error_utc"])
        self.assertIsNotNone(after_failure["last_successful_fetch_utc"])

    def test_mark_source_skipped_does_not_increment_attempts(self) -> None:
        engine = self._build_engine(enable_duckduckgo_search=False)
        before = {entry["source_key"]: entry for entry in engine.get_source_health_snapshot()}["duckduckgo"]
        self.assertEqual(before["attempt_count"], 0)
        self.assertEqual(before["success_count"], 0)

        engine._mark_source_skipped("duckduckgo")
        after = {entry["source_key"]: entry for entry in engine.get_source_health_snapshot()}["duckduckgo"]
        self.assertEqual(after["attempt_count"], 0)
        self.assertEqual(after["success_count"], 0)
        self.assertIsNone(after["last_attempt_utc"])

    def test_sanitize_error_message_redacts_sensitive_query_params(self) -> None:
        engine = self._build_engine()
        raw = (
            "Client error '403 Forbidden' for url "
            "'https://www.googleapis.com/customsearch/v1?key=abc123&cx=def456&q=test'"
        )
        safe = engine._sanitize_error_message(raw)
        self.assertNotIn("abc123", safe)
        self.assertNotIn("def456", safe)
        self.assertIn("key=%5BREDACTED%5D", safe)
        self.assertIn("cx=%5BREDACTED%5D", safe)


if __name__ == "__main__":
    unittest.main(verbosity=2)
