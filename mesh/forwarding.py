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
import logging
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable, List

from contracts import EmergencyEvent
from contracts.event import REQUIRED_ON_DECODE
from utils import database

logger = logging.getLogger(__name__)


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

    def _open(self) -> sqlite3.Connection:
        """Open a connection with ``sqlite3.Row`` factory.

        The injected ``connect=`` seam may hand back a plain connection (tuple
        rows); forcing the row factory here lets us address columns by name
        without raising on those connections.
        """

        conn = self._connect()
        conn.row_factory = sqlite3.Row
        return conn

    def init_schema(self) -> None:
        with self._open() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS mesh_seen_events (
                    event_id TEXT PRIMARY KEY,
                    first_seen_utc TEXT NOT NULL
                )
                """
            )
            # Supports pruning the dedup ledger by age (see prune()).
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_mesh_seen_first_seen "
                "ON mesh_seen_events(first_seen_utc)"
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
            # Composite index satisfies the hot drain query's filter AND ordering
            # (WHERE forwarded = 0 ORDER BY enqueued_utc), avoiding a sort as the
            # queue grows. Drop the older filter-only index it subsumes.
            conn.execute("DROP INDEX IF EXISTS idx_mesh_queue_forwarded")
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_mesh_queue_forwarded_enqueued "
                "ON mesh_forward_queue(forwarded, enqueued_utc)"
            )

    # ----- dedup memory --------------------------------------------------
    def has_seen(self, event_id: str) -> bool:
        with self._open() as conn:
            cur = conn.execute(
                "SELECT 1 FROM mesh_seen_events WHERE event_id = ? LIMIT 1", (event_id,)
            )
            return cur.fetchone() is not None

    # ----- core gossip logic --------------------------------------------
    def offer(self, event: EmergencyEvent) -> OfferResult:
        """Consider an event for forwarding; suppress loops and duplicates.

        Dedup is atomic: the ``event_id`` is inserted into ``mesh_seen_events``
        (PRIMARY KEY) inside one transaction, so concurrent offers of the same
        event race on the unique constraint and exactly one wins — a separate
        has_seen() pre-check would let both be accepted under threaded use.
        """

        if self.node_id in event.seen_nodes:
            return OfferResult("looped", False)

        now = _now_iso()
        will_forward = event.ttl_hops > 0
        with self._open() as conn:
            try:
                conn.execute(
                    "INSERT INTO mesh_seen_events (event_id, first_seen_utc) VALUES (?, ?)",
                    (event.event_id, now),
                )
            except sqlite3.IntegrityError:
                return OfferResult("duplicate", False)
            if will_forward:
                # Stamp a COPY (not the caller's event) so a rollback can't leave
                # this node spuriously in the original's seen_nodes.
                forward_copy = event.decremented()
                forward_copy.mark_seen(self.node_id)
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
                        now,
                    ),
                )
        # Only mutate the caller's event once the transaction has committed.
        event.mark_seen(self.node_id)
        return OfferResult("new", will_forward)

    # ----- queue draining (transports call these) ------------------------
    def pending(self, limit: int = 100) -> List[EmergencyEvent]:
        """Return enqueued, not-yet-forwarded events (oldest first).

        Rows that can't be decoded are marked forwarded so a corrupt payload
        can't permanently wedge the queue (``pending_count`` would otherwise never
        drain and transports would spin on it)."""

        events: List[EmergencyEvent] = []
        bad_ids: List[str] = []
        with self._open() as conn:
            cur = conn.execute(
                "SELECT event_id, payload_json FROM mesh_forward_queue "
                "WHERE forwarded = 0 ORDER BY enqueued_utc ASC LIMIT ?",
                (limit,),
            )
            for row in cur.fetchall():
                try:
                    # Require the mesh-critical fields to be present (so a
                    # partially corrupt row can't be minted into a "fresh"
                    # full-TTL event and break dedup/storm protection), then decode
                    # leniently so the original trust tier/signature is preserved
                    # for relay (not clamped as untrusted inbound), and validate()
                    # the structure.
                    data = json.loads(row["payload_json"])
                    if not isinstance(data, dict) or any(
                        data.get(k) in (None, "") for k in REQUIRED_ON_DECODE
                    ):
                        raise ValueError("missing required field(s)")
                    event = EmergencyEvent.from_dict(data, strict=False)
                    event.validate()
                    if event.event_id != row["event_id"]:
                        # A diverging id would make mark_forwarded(event.event_id)
                        # miss this row, wedging the queue — treat as undecodable.
                        raise ValueError("event_id does not match queue row")
                    events.append(event)
                except (KeyError, ValueError, json.JSONDecodeError, TypeError):
                    bad_ids.append(row["event_id"])
            for event_id in bad_ids:
                conn.execute(
                    "UPDATE mesh_forward_queue SET forwarded = 1, attempts = attempts + 1 "
                    "WHERE event_id = ?",
                    (event_id,),
                )
        if bad_ids:
            logger.warning(
                "Dropped %d undecodable mesh forward-queue row(s)", len(bad_ids)
            )
        return events

    def mark_forwarded(self, event_id: str) -> None:
        with self._open() as conn:
            conn.execute(
                "UPDATE mesh_forward_queue SET forwarded = 1, attempts = attempts + 1 "
                "WHERE event_id = ?",
                (event_id,),
            )

    def pending_count(self) -> int:
        with self._open() as conn:
            cur = conn.execute(
                "SELECT COUNT(*) AS c FROM mesh_forward_queue WHERE forwarded = 0"
            )
            return int(cur.fetchone()["c"])

    def prune(self, retention_days: float = 30.0) -> int:
        """Delete dedup-ledger entries and already-forwarded queue rows older than
        ``retention_days``, returning the number of rows removed.

        The dedup ledger (``mesh_seen_events``) otherwise grows without bound on a
        long-lived node; hosts call this periodically to cap it. Events older than
        the window can be re-accepted if they reappear, which is the intended
        trade-off for bounded storage.
        """

        cutoff = (
            datetime.now(timezone.utc) - timedelta(days=retention_days)
        ).isoformat(timespec="seconds").replace("+00:00", "Z")
        with self._open() as conn:
            seen = conn.execute(
                "DELETE FROM mesh_seen_events WHERE first_seen_utc < ?", (cutoff,)
            ).rowcount
            queued = conn.execute(
                "DELETE FROM mesh_forward_queue WHERE forwarded = 1 AND enqueued_utc < ?",
                (cutoff,),
            ).rowcount
        return int(seen or 0) + int(queued or 0)
