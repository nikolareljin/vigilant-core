"""Plugin contracts and the in-process event bus for VigilantCore.

The kernel turns every capability — fetching sources, talking to other nodes,
driving local devices, running automations — into a plugin of one of four kinds
that all speak the :class:`~contracts.EmergencyEvent` contract and report health
in a single, dashboard-friendly shape (the same telemetry introduced for source
health in v0.8.0). The :class:`EventBus` replaces the engine's single
``on_new_alert`` callback with publish/subscribe so any number of plugins can
react to an event without editing the engine.
"""

from __future__ import annotations

import logging
import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from contracts import EmergencyEvent

logger = logging.getLogger(__name__)

# Bus topics. Egress plugins subscribe to what they care about; the engine
# publishes every stored alert to NEW and additionally to HIGH when high-priority.
TOPIC_NEW = "event.new"          # every newly stored alert
TOPIC_HIGH = "event.high"        # high-priority: severity high/critical OR impact_score >= 7
TOPIC_INGEST = "event.ingest"    # inbound events from transports/sources -> pipeline

# Plugin kinds.
KIND_SOURCE = "source"
KIND_TRANSPORT = "transport"
KIND_DEVICE = "device"
KIND_SINK = "sink"

# High-priority routing criteria (issue #58): severity high/critical OR a high
# impact score, since EmergencyEvent does not force the two to agree.
HIGH_PRIORITY_IMPACT = 7
_HIGH_SEVERITIES = ("high", "critical")


def coerce_bool(value: Any, default: bool = False) -> bool:
    """Parse a plugin-option bool, recognizing JSON string forms.

    ``bool("false")`` is ``True``, a footgun for user-edited config.json, so
    accept the usual string spellings explicitly (mirrors utils.config)."""

    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in ("1", "true", "yes", "on"):
            return True
        if lowered in ("0", "false", "no", "off"):
            return False
    if isinstance(value, (int, float)):
        return bool(value)
    return default


def coerce_int(value: Any, default: int) -> int:
    """Parse a plugin-option int, falling back to ``default`` on bad input."""

    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def coerce_float(value: Any, default: float) -> float:
    """Parse a plugin-option float, falling back to ``default`` on bad input."""

    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def is_high_priority(event: EmergencyEvent) -> bool:
    """Whether an event should be routed to high-priority sinks/topics."""

    if str(getattr(event, "severity", "")).lower() in _HIGH_SEVERITIES:
        return True
    try:
        return int(getattr(event, "impact_score", 0) or 0) >= HIGH_PRIORITY_IMPACT
    except (TypeError, ValueError):
        return False


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


@dataclass
class PluginHealth:
    """Uniform health telemetry for every plugin (mirrors source-health v0.8.0)."""

    name: str
    kind: str
    enabled: bool = True
    last_attempt_utc: Optional[str] = None
    last_success_utc: Optional[str] = None
    last_error_utc: Optional[str] = None
    last_error: Optional[str] = None
    attempt_count: int = 0
    success_count: int = 0
    error_count: int = 0
    last_latency_ms: Optional[float] = None
    last_item_count: int = 0

    def record_success(self, *, latency_ms: float = 0.0, item_count: int = 0) -> None:
        now = _now_iso()
        self.last_attempt_utc = now
        self.last_success_utc = now
        self.attempt_count += 1
        self.success_count += 1
        self.last_latency_ms = round(max(0.0, float(latency_ms)), 2)
        self.last_item_count = max(0, int(item_count))
        # Clear both the message and its timestamp on success (matches v0.8.0).
        self.last_error = None
        self.last_error_utc = None

    def record_error(
        self, message: str, *, latency_ms: float = 0.0, item_count: int = 0
    ) -> None:
        now = _now_iso()
        self.last_attempt_utc = now
        self.last_error_utc = now
        self.attempt_count += 1
        self.error_count += 1
        self.last_latency_ms = round(max(0.0, float(latency_ms)), 2)
        # Update item_count on every attempt, including failures (matches v0.8.0).
        self.last_item_count = max(0, int(item_count))
        self.last_error = (message or "error")[:240].strip() or "error"

    def as_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "kind": self.kind,
            "enabled": self.enabled,
            "last_attempt_utc": self.last_attempt_utc,
            "last_success_utc": self.last_success_utc,
            # Alias matching the v0.8.0 source-health dashboard key.
            "last_successful_fetch_utc": self.last_success_utc,
            "last_error_utc": self.last_error_utc,
            "last_error": self.last_error,
            "attempt_count": self.attempt_count,
            "success_count": self.success_count,
            "error_count": self.error_count,
            "last_latency_ms": self.last_latency_ms,
            "last_item_count": self.last_item_count,
        }


Subscriber = Callable[[EmergencyEvent], None]


class EventBus:
    """Thread-safe, synchronous, in-process publish/subscribe for events.

    Handlers are isolated: one failing subscriber never blocks the others or the
    publisher. This is deliberately simple — the same semantics work on a Pi as
    in tests, and durable cross-node delivery is the transports' job, not the bus'.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._subs: Dict[str, List[Subscriber]] = {}

    def subscribe(self, topic: str, handler: Subscriber) -> None:
        with self._lock:
            handlers = self._subs.setdefault(topic, [])
            # Idempotent: subscribing the same handler twice (e.g. a repeated
            # subscribe_ingest on config reload) must not double-deliver.
            if handler not in handlers:
                handlers.append(handler)

    def unsubscribe(self, topic: str, handler: Subscriber) -> None:
        with self._lock:
            handlers = self._subs.get(topic)
            if handlers and handler in handlers:
                handlers.remove(handler)

    def publish(self, topic: str, event: EmergencyEvent) -> int:
        """Deliver ``event`` to every subscriber of ``topic``. Returns delivery count."""

        with self._lock:
            handlers = list(self._subs.get(topic, ()))
        delivered = 0
        for handler in handlers:
            try:
                handler(event)
                delivered += 1
            except Exception:  # pragma: no cover - defensive isolation
                logger.exception("EventBus subscriber on %s failed", topic)
        return delivered


@dataclass
class PluginContext:
    """Everything a plugin needs from the host at startup."""

    bus: EventBus
    config: Any
    node_id: Optional[str] = None
    options: Dict[str, Any] = field(default_factory=dict)


class Plugin(ABC):
    """Base class for all plugins."""

    kind: str = "plugin"

    def __init__(self, name: str, options: Optional[Dict[str, Any]] = None) -> None:
        self.name = name
        self.options = options or {}
        self.health = PluginHealth(name=name, kind=self.kind)

    def start(self, ctx: PluginContext) -> None:
        """Acquire resources and wire bus subscriptions. Override as needed."""

    def stop(self) -> None:
        """Release resources. Override as needed."""

    def health_snapshot(self) -> Dict[str, Any]:
        return self.health.as_dict()


class SourcePlugin(Plugin):
    """Produces events. The engine calls :meth:`poll` each cycle and ingests the
    returned events through the normal dedup/store pipeline."""

    kind = KIND_SOURCE

    @abstractmethod
    async def poll(self, ctx: PluginContext) -> List[EmergencyEvent]:
        """Return any new events discovered this cycle (may be empty)."""


class TransportPlugin(Plugin):
    """Bidirectional link to other nodes/devices. Outbound via :meth:`send`
    (the kernel subscribes it to the bus); inbound by publishing received events
    to ``TOPIC_INGEST`` so they re-enter the pipeline."""

    kind = KIND_TRANSPORT

    @abstractmethod
    def send(self, event: EmergencyEvent) -> None:
        """Transmit an event to peers/devices over this transport."""


class DevicePlugin(Plugin):
    """Local output device (siren, display, GPIO relay, native notification)."""

    kind = KIND_DEVICE

    @abstractmethod
    def render(self, event: EmergencyEvent) -> None:
        """Present/actuate the event on the local device."""


class SinkPlugin(Plugin):
    """Side-effecting consumer (webhook, shell action, digest, export)."""

    kind = KIND_SINK

    @abstractmethod
    def handle(self, event: EmergencyEvent) -> None:
        """Process the event (fire webhook, append to digest, etc.)."""
