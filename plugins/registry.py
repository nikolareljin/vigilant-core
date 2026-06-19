"""Plugin lifecycle + event routing registry.

The registry owns the :class:`EventBus`, starts/stops plugins, wires egress
plugins (transport/device/sink) to the bus topics they care about, and gives the
engine two integration points: :meth:`poll_sources` (pull new events from source
plugins each cycle) and :meth:`publish` (fan a stored event out to all egress
plugins). It is intentionally inert when no plugins are configured, so default
installs behave exactly as before.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable, Dict, List, Optional

from contracts import EmergencyEvent

from .base import (
    DevicePlugin,
    EventBus,
    Plugin,
    PluginContext,
    SinkPlugin,
    SourcePlugin,
    TransportPlugin,
    TOPIC_HIGH,
    TOPIC_INGEST,
    TOPIC_NEW,
    is_high_priority,
)

logger = logging.getLogger(__name__)


class PluginRegistry:
    def __init__(self, config: Any = None, node_id: Optional[str] = None) -> None:
        self.config = config
        self.node_id = node_id
        self.bus = EventBus()
        self._plugins: List[Plugin] = []
        self._started = False
        # (topic, handler) pairs wired in _wire_egress, so stop_all can remove
        # them and a subsequent start_all doesn't double-subscribe.
        self._egress_subs: List[tuple[str, Callable[[EmergencyEvent], None]]] = []

    # ----- registration / lifecycle -------------------------------------
    def register(self, plugin: Plugin) -> None:
        self._plugins.append(plugin)

    @property
    def plugins(self) -> List[Plugin]:
        return list(self._plugins)

    def sources(self) -> List[SourcePlugin]:
        return [p for p in self._plugins if isinstance(p, SourcePlugin)]

    def _context_for(self, plugin: Plugin) -> PluginContext:
        return PluginContext(
            bus=self.bus,
            config=self.config,
            node_id=self.node_id,
            options=plugin.options,
        )

    def start_all(self) -> None:
        if self._started:
            return
        for plugin in self._plugins:
            try:
                plugin.start(self._context_for(plugin))
                self._wire_egress(plugin)
            except Exception as exc:
                logger.exception("Failed to start plugin %s", plugin.name)
                plugin.health.record_error(f"start failed: {exc}")
        self._started = True

    def _subscribe_egress(self, topic: str, handler: Callable[[EmergencyEvent], None]) -> None:
        self.bus.subscribe(topic, handler)
        self._egress_subs.append((topic, handler))

    def _wire_egress(self, plugin: Plugin) -> None:
        """Subscribe egress plugins to the appropriate bus topics."""

        if isinstance(plugin, TransportPlugin):
            # Transports get every event; they decide normal vs high internally.
            self._subscribe_egress(TOPIC_NEW, self._guard(plugin, plugin.send))
        elif isinstance(plugin, DevicePlugin):
            # Devices (sirens/displays) default to high-priority only (severity
            # high/critical OR impact_score >= 7); override with options
            # {"min_severity": "low"} to receive everything (case-insensitive).
            min_severity = str(plugin.options.get("min_severity", "")).strip().lower()
            topic = TOPIC_NEW if min_severity == "low" else TOPIC_HIGH
            self._subscribe_egress(topic, self._guard(plugin, plugin.render))
        elif isinstance(plugin, SinkPlugin):
            self._subscribe_egress(TOPIC_NEW, self._guard(plugin, plugin.handle))

    def _guard(self, plugin: Plugin, fn: Callable[[EmergencyEvent], None]):
        """Wrap an egress handler so it records health and never raises into the bus."""

        def _handler(event: EmergencyEvent) -> None:
            try:
                fn(event)
                plugin.health.record_success(item_count=1)
            except Exception as exc:  # pragma: no cover - defensive
                logger.exception("Plugin %s handler failed", plugin.name)
                plugin.health.record_error(str(exc))

        return _handler

    def stop_all(self) -> None:
        for plugin in self._plugins:
            try:
                plugin.stop()
            except Exception:
                logger.exception("Failed to stop plugin %s", plugin.name)
        # Remove egress subscriptions so a later start_all() re-wires cleanly
        # instead of double-delivering events to every plugin.
        for topic, handler in self._egress_subs:
            self.bus.unsubscribe(topic, handler)
        self._egress_subs.clear()
        self._started = False

    # ----- engine integration -------------------------------------------
    async def poll_sources(self) -> List[EmergencyEvent]:
        """Collect new events from all source plugins concurrently."""

        source_plugins = self.sources()
        if not source_plugins:
            return []
        ctx_map = {p: self._context_for(p) for p in source_plugins}
        results = await asyncio.gather(
            *[p.poll(ctx_map[p]) for p in source_plugins],
            return_exceptions=True,
        )
        events: List[EmergencyEvent] = []
        for plugin, result in zip(source_plugins, results):
            if isinstance(result, Exception):
                # Only record here for an *uncaught* error; a plugin's own poll()
                # (e.g. RssSourcePlugin) records its success/error itself, so we do
                # not double-count the success path.
                logger.warning("Source plugin %s poll failed: %s", plugin.name, result)
                plugin.health.record_error(str(result))
                continue
            if not isinstance(result, list):
                # A misbehaving plugin (returns None or a single event) must not
                # abort polling for the others — keep the isolation guarantee.
                logger.warning(
                    "Source plugin %s returned %s, expected list; skipping",
                    plugin.name,
                    type(result).__name__,
                )
                plugin.health.record_error(
                    f"poll returned {type(result).__name__}, expected list"
                )
                continue
            events.extend(result)
        return events

    def publish(self, event: EmergencyEvent) -> None:
        """Fan a stored event out to egress plugins (NEW, plus HIGH when the event
        is high-priority: severity high/critical OR impact_score >= 7)."""

        if not self._plugins:
            return
        self.bus.publish(TOPIC_NEW, event)
        if is_high_priority(event):
            self.bus.publish(TOPIC_HIGH, event)

    def subscribe_ingest(self, handler: Callable[[EmergencyEvent], None]) -> None:
        """Register the engine's handler for inbound events from transports."""

        self.bus.subscribe(TOPIC_INGEST, handler)

    # ----- introspection -------------------------------------------------
    def health(self) -> List[Dict[str, Any]]:
        return [p.health_snapshot() for p in self._plugins]
