"""MQTT transport plugin — publishes events to the ShelfCast-compatible bus.

Outbound: every event is published as schema-valid JSON to
``<base_topic>/normalized``; high/critical events additionally go to
``<base_topic>/high_priority`` (issues #57/#58/#59, schema #60). Inbound:
when ``subscribe_inbound`` is set, events received on ``<base_topic>/ingest``
are republished to the local bus' ``TOPIC_INGEST`` so they re-enter the pipeline.

``paho-mqtt`` is imported lazily and a client can be injected via
``options['client']`` for tests, so importing this module never requires a broker.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from contracts import EmergencyEvent

from ..base import PluginContext, TransportPlugin, TOPIC_INGEST, is_high_priority

logger = logging.getLogger(__name__)

NORMALIZED_SUFFIX = "normalized"
HIGH_PRIORITY_SUFFIX = "high_priority"
INGEST_SUFFIX = "ingest"


class MqttTransportPlugin(TransportPlugin):
    def __init__(self, name: str, options: Optional[dict[str, Any]] = None) -> None:
        super().__init__(name, options)
        self._client = self.options.get("client")  # injectable for tests
        self._ctx: Optional[PluginContext] = None
        self._base_topic = str(self.options.get("base_topic", "intel/events")).rstrip("/")
        self._validate = bool(self.options.get("validate", True))

    # ----- lifecycle -----------------------------------------------------
    def start(self, ctx: PluginContext) -> None:
        self._ctx = ctx
        if self._client is None:
            self._client = self._connect()
        if self._client is not None and self.options.get("subscribe_inbound"):
            self._subscribe_inbound()

    def _connect(self):
        try:
            import paho.mqtt.client as mqtt  # type: ignore
        except Exception:
            logger.warning(
                "paho-mqtt not installed; MQTT transport %s is inert (install paho-mqtt)",
                self.name,
            )
            return None
        host = self.options.get("host", "127.0.0.1")
        port = int(self.options.get("port", 1883))
        client = mqtt.Client()
        username = self.options.get("username")
        if username:
            client.username_pw_set(username, self.options.get("password"))
        try:
            client.connect(host, port, keepalive=int(self.options.get("keepalive", 60)))
            client.loop_start()
        except Exception as exc:
            logger.warning("MQTT transport %s failed to connect: %s", self.name, exc)
            self.health.record_error(f"connect failed: {exc}")
            return None
        return client

    def _subscribe_inbound(self) -> None:
        topic = f"{self._base_topic}/{INGEST_SUFFIX}"

        def _on_message(_client, _userdata, message) -> None:
            try:
                event = EmergencyEvent.from_json(message.payload)
                if self._ctx is not None:
                    self._ctx.bus.publish(TOPIC_INGEST, event)
            except Exception:
                logger.exception("MQTT transport %s: bad inbound payload", self.name)

        try:
            self._client.on_message = _on_message
            self._client.subscribe(topic)
        except Exception as exc:  # pragma: no cover - broker dependent
            logger.warning("MQTT transport %s inbound subscribe failed: %s", self.name, exc)

    def stop(self) -> None:
        client = self._client
        if client is None:
            return
        for closer in ("loop_stop", "disconnect"):
            try:
                getattr(client, closer)()
            except Exception:
                pass
        # Clear the client so a later start() reconnects instead of staying inert.
        self._client = None

    # ----- outbound ------------------------------------------------------
    def send(self, event: EmergencyEvent) -> None:
        if self._client is None:
            # Configured but not connected (broker down / paho missing): surface
            # a failure so the registry guard records it instead of faking success.
            raise RuntimeError(f"MQTT transport {self.name} is not connected")
        if self._validate:
            event.validate()  # raises on contract violation before we publish
        payload = event.to_json()
        self._publish(f"{self._base_topic}/{NORMALIZED_SUFFIX}", payload)
        if is_high_priority(event):
            self._publish(f"{self._base_topic}/{HIGH_PRIORITY_SUFFIX}", payload)

    def _publish(self, topic: str, payload: str) -> None:
        result = self._client.publish(topic, payload)
        # paho returns an object with rc; injected fakes may return anything.
        rc = getattr(result, "rc", 0)
        if rc not in (0, None):
            raise RuntimeError(f"MQTT publish to {topic} failed rc={rc}")
        logger.debug("MQTT %s -> %s (%d bytes)", self.name, topic, len(payload))

    def published_topics_for(self, event: EmergencyEvent) -> list[str]:
        """Topics ``send`` would target for ``event`` (handy for tests/docs)."""

        topics = [f"{self._base_topic}/{NORMALIZED_SUFFIX}"]
        if is_high_priority(event):
            topics.append(f"{self._base_topic}/{HIGH_PRIORITY_SUFFIX}")
        return topics
