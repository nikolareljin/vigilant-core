from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from utils import database


class SQLiteLocalCacheTests(unittest.TestCase):
    def _insert_sample_alert(self) -> bool:
        return database.insert_alert(
            url="https://example.com/incidents/flood-1",
            title="Flash flood warning issued",
            snippet="Evacuation advised in low-lying areas.",
            published_at="2026-02-28T08:10:00Z",
            source="Feed A | Feed B",
            source_kind="rss",
            severity="high",
            confidence=0.87,
            event_timestamp_utc="2026-02-28T08:10:00Z",
            impact_score=8,
            predictive_outcome="Potential utility disruption in the next 24h.",
            is_relevant=True,
            subject="Flooding",
            location_name="River County",
            location_zip_code="07001",
            location_latitude=40.61,
            location_longitude=-74.26,
            merged_urls=(
                "https://example.com/incidents/flood-1",
                "https://mirror.example.net/flood-1",
            ),
            merged_sources=("Feed A", "Feed B"),
            normalized_payload={
                "schema_version": "1.0",
                "severity": "high",
                "confidence": 0.87,
                "timestamp_utc": "2026-02-28T08:10:00Z",
                "location": {"name": "River County", "zip_code": "07001"},
            },
        )

    def test_insert_alert_persists_history_and_source_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            data_root = Path(tmpdir)
            with patch("utils.database.data_dir", return_value=data_root):
                database.init_db()
                inserted = self._insert_sample_alert()

                self.assertTrue(inserted)

                with database.connect() as conn:
                    alert_row = conn.execute(
                        "SELECT id, source_kind FROM alerts LIMIT 1"
                    ).fetchone()
                    self.assertIsNotNone(alert_row)
                    self.assertEqual(alert_row["source_kind"], "rss")
                    alert_id = int(alert_row["id"])

                    history_row = conn.execute(
                        """
                        SELECT alert_id, severity, confidence, normalized_payload_json
                        FROM event_history
                        WHERE alert_id = ?
                        """,
                        (alert_id,),
                    ).fetchone()
                    self.assertIsNotNone(history_row)
                    self.assertEqual(history_row["alert_id"], alert_id)
                    self.assertEqual(history_row["severity"], "high")
                    self.assertAlmostEqual(float(history_row["confidence"]), 0.87, places=5)
                    payload = json.loads(history_row["normalized_payload_json"])
                    self.assertEqual(payload["schema_version"], "1.0")

                    source_rows = conn.execute(
                        """
                        SELECT source_name, source_kind, is_primary, source_rank, merged_urls_json
                        FROM source_metadata
                        WHERE alert_id = ?
                        ORDER BY source_rank ASC
                        """,
                        (alert_id,),
                    ).fetchall()
                    self.assertEqual(len(source_rows), 2)
                    self.assertEqual(source_rows[0]["source_name"], "Feed A")
                    self.assertEqual(source_rows[0]["is_primary"], 1)
                    self.assertEqual(source_rows[1]["source_name"], "Feed B")
                    self.assertEqual(source_rows[1]["is_primary"], 0)
                    merged_urls = json.loads(source_rows[0]["merged_urls_json"])
                    self.assertIn("https://example.com/incidents/flood-1", merged_urls)
                    self.assertIn("https://mirror.example.net/flood-1", merged_urls)

    def test_foreign_key_cascade_removes_child_cache_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            data_root = Path(tmpdir)
            with patch("utils.database.data_dir", return_value=data_root):
                database.init_db()
                self.assertTrue(self._insert_sample_alert())

                with database.connect() as conn:
                    pragma_enabled = conn.execute("PRAGMA foreign_keys").fetchone()[0]
                    self.assertEqual(pragma_enabled, 1)
                    alert_row = conn.execute("SELECT id FROM alerts LIMIT 1").fetchone()
                    self.assertIsNotNone(alert_row)
                    alert_id = int(alert_row["id"])
                    conn.execute("DELETE FROM alerts WHERE id = ?", (alert_id,))

                    history_count = conn.execute(
                        "SELECT COUNT(*) AS c FROM event_history WHERE alert_id = ?",
                        (alert_id,),
                    ).fetchone()["c"]
                    source_count = conn.execute(
                        "SELECT COUNT(*) AS c FROM source_metadata WHERE alert_id = ?",
                        (alert_id,),
                    ).fetchone()["c"]
                    self.assertEqual(history_count, 0)
                    self.assertEqual(source_count, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
