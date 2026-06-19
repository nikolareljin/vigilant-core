"""Store-and-forward queue + cross-node dedup for mesh propagation.

This is the data model and reference algorithm behind distributed rapid alert
propagation (#33) and mesh storm protection (#34); Phase 2's radios drive it.

The model is gossip / flood-with-suppression:

* Each event carries a stable ``event_id``, a ``ttl_hops`` budget, and the list
  of ``seen_nodes`` it has passed through.
* When a node *offers* an event (locally produced or received from a peer), the
  queue suppresses it if this node already appears in ``seen_nodes`` (it looped)
  or if the ``event_id`` was seen before (a duplicate arriving by another path).
* Otherwise the node stamps itself into ``seen_nodes`` and, if ``ttl_hops`` is
  left, enqueues a hop-decremented copy for transports to forward. Decrementing
  TTL bounds flooding so a storm of duplicates cannot amplify across the mesh.

Everything is persisted in SQLite (the platform DB) so an edge node that loses
power resumes with its dedup memory and pending forwards intact.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, List

from contracts import EmergencyEvent
from utils import database


@dataclass
class OfferResult:
    status: str        # "new" | "duplicate" | "looped"
    will_forward: bool  # whether a hop-decremented copy was enqueued

    @property
    def accepted(self) -> bool:
        return self.status == "new"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


class ForwardingQueue:
    """SQLite-backed store-and-forward queue with cross-node dedup.

    ``connect`` defaults to the platform DB connection but can be injected with a
    factory pointing at a temp database for tests.
    """

    def __init__(
        self,
        node_id: str,
        connect: Callable[[], sqlite3.Connection] = database.connect,
    ) -> None:
        self.node_id = node_id
        self._connect = connect
        self.init_schema()

    def init_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS mesh_seen_events (
                    event_id TEXT PRIMARY KEY,
                    first_seen_utc TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS mesh_forward_queue (
                    event_id TEXT PRIMARY KEY,
                    payload_json TEXT NOT NULL,
                    ttl_hops INTEGER NOT NULL,
                    enqueued_utc TEXT NOT NULL,
                    forwarded INTEGER NOT NULL DEFAULT 0,
                    attempts INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_mesh_queue_forwarded "
                "ON mesh_forward_queue(forwarded)"
            )

    # ----- dedup memory --------------------------------------------------
    def has_seen(self, event_id: str) -> bool:
        with self._connect() as conn:
            cur = conn.execute(
                "SELECT 1 FROM mesh_seen_events WHERE event_id = ? LIMIT 1", (event_id,)
            )
            return cur.fetchone() is not None

    def _record_seen(self, conn: sqlite3.Connection, event_id: str) -> None:
        conn.execute(
            "INSERT OR IGNORE INTO mesh_seen_events (event_id, first_seen_utc) VALUES (?, ?)",
            (event_id, _now_iso()),
        )

    # ----- core gossip logic --------------------------------------------
    def offer(self, event: EmergencyEvent) -> OfferResult:
        """Consider an event for forwarding; suppress loops and duplicates."""

        if self.node_id in event.seen_nodes:
            return OfferResult("looped", False)
        if self.has_seen(event.event_id):
            return OfferResult("duplicate", False)

        event.mark_seen(self.node_id)
        will_forward = event.ttl_hops > 0
        with self._connect() as conn:
            self._record_seen(conn, event.event_id)
            if will_forward:
                forward_copy = event.decremented()
                conn.execute(
                    """
                    INSERT OR IGNORE INTO mesh_forward_queue
                        (event_id, payload_json, ttl_hops, enqueued_utc)
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        forward_copy.event_id,
                        forward_copy.to_json(),
                        forward_copy.ttl_hops,
                        _now_iso(),
                    ),
                )
        return OfferResult("new", will_forward)

    # ----- queue draining (transports call these) ------------------------
    def pending(self, limit: int = 100) -> List[EmergencyEvent]:
        """Return enqueued, not-yet-forwarded events (oldest first)."""

        with self._connect() as conn:
            cur = conn.execute(
                "SELECT payload_json FROM mesh_forward_queue "
                "WHERE forwarded = 0 ORDER BY enqueued_utc ASC LIMIT ?",
                (limit,),
            )
            rows = cur.fetchall()
        events: List[EmergencyEvent] = []
        for row in rows:
            try:
                # Trusted local storage we wrote ourselves: decode leniently so the
                # original trust tier/signature is preserved for relay (strict
                # decode would clamp it as if it were untrusted inbound).
                events.append(
                    EmergencyEvent.from_json(row["payload_json"], strict=False)
                )
            except (KeyError, ValueError, json.JSONDecodeError, TypeError):
                continue
        return events

    def mark_forwarded(self, event_id: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE mesh_forward_queue SET forwarded = 1, attempts = attempts + 1 "
                "WHERE event_id = ?",
                (event_id,),
            )

    def pending_count(self) -> int:
        with self._connect() as conn:
            cur = conn.execute(
                "SELECT COUNT(*) AS c FROM mesh_forward_queue WHERE forwarded = 0"
            )
            return int(cur.fetchone()["c"])
