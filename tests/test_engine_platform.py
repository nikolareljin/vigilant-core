from __future__ import annotations

import json
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

from contracts import EmergencyEvent
from utils import database
from utils.config import AppConfig


def _patches(tmp: Path) -> ExitStack:
    """Redirect every data/config dir used by the engine platform layer to tmp."""

    stack = ExitStack()
    for target in (
        "utils.config.config_dir",
        "utils.config.data_dir",
        "utils.database.data_dir",
        "mesh.node.data_dir",
    ):
        stack.enter_context(patch(target, return_value=tmp))
    return stack


class EnginePlatformTests(unittest.TestCase):
    def _engine(self, plugins):
        from engine.monitor import MonitorEngine

        cfg = AppConfig(subject="Wildfires", plugins=plugins, relax_location_filter=True)
        return MonitorEngine(cfg)

    def test_no_platform_layer_without_plugins(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            with _patches(base):
                engine = self._engine([])
                # Truly no-op: no registry/forwarding and no node identity file.
                self.assertIsNone(engine.registry)
                self.assertIsNone(engine.forwarding)
                self.assertFalse((base / "node.json").exists())

    def test_inbound_event_preserves_identity(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            with _patches(base):
                database.init_db()
                engine = self._engine(
                    [{"type": "notify_device", "name": "n", "options": {"desktop": False}}]
                )
                self.assertIsNotNone(engine.registry)

                event = EmergencyEvent(
                    title="Inbound flood from a peer", hazard_type="flood",
                    severity="high", confidence=0.7, impact_score=7,
                    origin_node_id="PEER-NODE", url="http://peer/flood-1",
                )
                original_id = event.event_id
                engine._buffer_inbound_event(event)
                stored = engine._ingest_inbound_events()
                self.assertEqual(stored, 1)

                # The persisted event keeps its original identity (NOT re-minted).
                with database.connect() as conn:
                    row = conn.execute(
                        "SELECT normalized_payload_json FROM event_history "
                        "ORDER BY id DESC LIMIT 1"
                    ).fetchone()
                payload = json.loads(row["normalized_payload_json"])
                self.assertEqual(payload["event_id"], original_id)
                self.assertEqual(payload["origin_node_id"], "PEER-NODE")

    def test_inbound_buffer_is_bounded(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with _patches(Path(tmp)):
                engine = self._engine(
                    [{"type": "notify_device", "name": "n", "options": {"desktop": False}}]
                )
                engine._max_inbound = 5
                for i in range(20):
                    engine._buffer_inbound_event(EmergencyEvent(title=f"e{i}"))
                self.assertEqual(len(engine._drain_inbound_events()), 5)


if __name__ == "__main__":
    unittest.main()
