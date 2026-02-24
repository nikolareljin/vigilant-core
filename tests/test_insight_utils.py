from __future__ import annotations

import unittest

from utils.insight import normalize_suggestions


class InsightUtilsTests(unittest.TestCase):
    def test_normalize_suggestions_skips_none_and_unknown_objects(self) -> None:
        suggestions = normalize_suggestions(
            [
                None,
                {"foo": "bar"},
                {"text": "Use official utility outage map first."},
                {"label": "Follow local emergency management updates."},
                "Keep devices charged.",
                123,
            ]
        )
        self.assertEqual(
            suggestions,
            [
                "Use official utility outage map first.",
                "Follow local emergency management updates.",
                "Keep devices charged.",
            ],
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
