from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from contracts import EmergencyEvent
from mesh.forwarding import ForwardingQueue
from mesh.node import load_or_create_node
from utils import database


def _event(ttl: int = 3, severity: str = "high") -> EmergencyEvent:
    return EmergencyEvent(
        title="Flood warning",
        hazard_type="flood",
        severity=severity,
        confidence=0.8,
        impact_score=7,
        ttl_hops=ttl,
    )


class NodeIdentityTests(unittest.TestCase):
    def test_node_id_stable_across_loads(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            n1 = load_or_create_node(base=base, role="edge", label="field-1")
            n2 = load_or_create_node(base=base)
            self.assertEqual(n1.node_id, n2.node_id)
            self.assertEqual(n1.role, "edge")
            self.assertEqual(n1.label, "field-1")

    def test_invalid_role_falls_back_to_hub(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            node = load_or_create_node(base=Path(tmp), role="bogus")
            self.assertEqual(node.role, "hub")


class StoreAndForwardTests(unittest.TestCase):
    def test_offer_dedup_loop_and_ttl(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with patch("utils.database.data_dir", return_value=Path(tmp)):
                database.init_db()
                queue = ForwardingQueue("NODE-A")

                event = _event(ttl=3)
                result = queue.offer(event)
                self.assertEqual(result.status, "new")
                self.assertTrue(result.will_forward)
                self.assertEqual(queue.pending_count(), 1)

                # Forwarded copy decremented and stamped with this node.
                forwarded = queue.pending()[0]
                self.assertEqual(forwarded.ttl_hops, 2)
                self.assertIn("NODE-A", forwarded.seen_nodes)

                # Duplicate by event_id is suppressed.
                dup = _event(ttl=3)
                dup.event_id = event.event_id
                self.assertEqual(queue.offer(dup).status, "duplicate")
                self.assertEqual(queue.pending_count(), 1)

                # Looped event (already carries this node) is suppressed.
                looped = _event(ttl=3)
                looped.seen_nodes = ["NODE-A"]
                self.assertEqual(queue.offer(looped).status, "looped")

                # TTL-exhausted event is accepted but not forwarded.
                terminal = _event(ttl=0)
                tr = queue.offer(terminal)
                self.assertEqual(tr.status, "new")
                self.assertFalse(tr.will_forward)

    def test_survives_restart(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with patch("utils.database.data_dir", return_value=Path(tmp)):
                database.init_db()
                queue = ForwardingQueue("NODE-A")
                event = _event(ttl=2)
                queue.offer(event)
                forwarded_id = queue.pending()[0].event_id

                # New instance on the same DB == process restart.
                resumed = ForwardingQueue("NODE-A")
                self.assertTrue(resumed.has_seen(event.event_id))
                self.assertEqual(resumed.pending_count(), 1)

                resumed.mark_forwarded(forwarded_id)
                self.assertEqual(resumed.pending_count(), 0)
                # Dedup memory persists even after the queue is drained.
                self.assertTrue(resumed.has_seen(event.event_id))


if __name__ == "__main__":
    unittest.main()
