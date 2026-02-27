from __future__ import annotations

import unittest

from utils.gguf_summarizer import summarize_alerts_and_risk_snapshot


class GGUFSummarizerTests(unittest.TestCase):
    def test_disabled_mode_returns_heuristic_bundle(self) -> None:
        alerts = [
            {
                "title": "Storm warning issued",
                "source": "NWS",
                "impact_score": 8,
            },
            {
                "title": "Power outage impacts downtown",
                "source": "Utility",
                "impact_score": 7,
            },
        ]
        bundle = summarize_alerts_and_risk_snapshot(
            alerts=alerts,
            subject="Power Outage",
            location="Austin, TX",
            question="When is outage risk highest?",
            enabled=False,
            model_path=None,
        )
        self.assertEqual(bundle.engine, "disabled")
        self.assertFalse(bundle.available)
        self.assertIn("Recent alert summary", bundle.alert_summary)
        self.assertIn("Risk snapshot", bundle.risk_snapshot)

    def test_enabled_without_model_path_reports_configuration_error(self) -> None:
        bundle = summarize_alerts_and_risk_snapshot(
            alerts=[],
            subject="Flooding",
            location="Dallas, TX",
            question="Risk?",
            enabled=True,
            model_path=None,
        )
        self.assertEqual(bundle.engine, "heuristic")
        self.assertFalse(bundle.available)
        self.assertIsNotNone(bundle.error)
        self.assertIn("GGUF_MODEL_PATH", bundle.error)


if __name__ == "__main__":
    unittest.main(verbosity=2)
