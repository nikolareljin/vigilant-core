from __future__ import annotations

import asyncio
import unittest

from contracts import EmergencyEvent
from plugins import EventBus, TOPIC_INGEST, TOPIC_NEW, build_registry
from plugins.base import PluginContext, SourcePlugin
from plugins.builtin.mqtt_transport import MqttTransportPlugin
from plugins.builtin.notify_device import NotifyDevicePlugin
from plugins.loader import build_plugin, resolve_plugin_class


class FakeMqttClient:
    def __init__(self) -> None:
        self.published: list[tuple[str, str]] = []

    def publish(self, topic, payload):
        self.published.append((topic, payload))
        return type("R", (), {"rc": 0})()


class _Cfg:
    """Minimal config-like object exposing a plugins list."""

    def __init__(self, plugins):
        self.plugins = plugins
        self.location_name = "Test County"
        self.zip_code = None
        self.latitude = None
        self.longitude = None


def _event(severity: str = "high") -> EmergencyEvent:
    return EmergencyEvent(
        title="Test hazard",
        hazard_type="storm",
        severity=severity,
        confidence=0.7,
        impact_score=8 if severity in ("high", "critical") else 3,
    )


class EventBusTests(unittest.TestCase):
    def test_publish_delivers_to_subscribers(self) -> None:
        bus = EventBus()
        received = []
        bus.subscribe(TOPIC_NEW, received.append)
        delivered = bus.publish(TOPIC_NEW, _event())
        self.assertEqual(delivered, 1)
        self.assertEqual(len(received), 1)

    def test_failing_subscriber_is_isolated(self) -> None:
        bus = EventBus()
        ok = []

        def boom(_event):
            raise RuntimeError("kaboom")

        bus.subscribe(TOPIC_NEW, boom)
        bus.subscribe(TOPIC_NEW, ok.append)
        bus.publish(TOPIC_NEW, _event())  # must not raise
        self.assertEqual(len(ok), 1)

    def test_unsubscribe(self) -> None:
        bus = EventBus()
        received = []
        bus.subscribe(TOPIC_NEW, received.append)
        bus.unsubscribe(TOPIC_NEW, received.append)
        bus.publish(TOPIC_NEW, _event())
        self.assertEqual(received, [])


class RegistryRoutingTests(unittest.TestCase):
    def test_high_severity_routes_to_device_and_transport(self) -> None:
        fake = FakeMqttClient()
        cfg = _Cfg([
            {"type": "mqtt_transport", "name": "bus",
             "options": {"client": fake, "base_topic": "intel/events"}},
            {"type": "notify_device", "name": "siren",
             "options": {"desktop": False}},
        ])
        registry = build_registry(cfg, node_id="NODE-A")
        registry.publish(_event("critical"))

        topics = [t for t, _ in fake.published]
        self.assertIn("intel/events/normalized", topics)
        self.assertIn("intel/events/high_priority", topics)
        siren = next(p for p in registry.plugins if p.name == "siren")
        self.assertEqual(len(siren.rendered), 1)

    def test_low_severity_skips_default_device_and_high_topic(self) -> None:
        fake = FakeMqttClient()
        cfg = _Cfg([
            {"type": "mqtt_transport", "name": "bus",
             "options": {"client": fake, "base_topic": "intel/events"}},
            {"type": "notify_device", "name": "siren",
             "options": {"desktop": False}},
        ])
        registry = build_registry(cfg, node_id="NODE-A")
        registry.publish(_event("low"))

        topics = [t for t, _ in fake.published]
        self.assertEqual(topics, ["intel/events/normalized"])  # no high_priority
        siren = next(p for p in registry.plugins if p.name == "siren")
        self.assertEqual(siren.rendered, [])  # device defaults to high only

    def test_device_min_severity_low_receives_all(self) -> None:
        cfg = _Cfg([
            {"type": "notify_device", "name": "log",
             "options": {"min_severity": "low", "desktop": False}},
        ])
        registry = build_registry(cfg, node_id="NODE-A")
        registry.publish(_event("low"))
        log = registry.plugins[0]
        self.assertEqual(len(log.rendered), 1)

    def test_disabled_plugin_not_loaded(self) -> None:
        cfg = _Cfg([
            {"type": "notify_device", "name": "off", "enabled": False, "options": {}},
        ])
        registry = build_registry(cfg, node_id="NODE-A")
        self.assertEqual(registry.plugins, [])

    def test_inert_registry_with_no_plugins(self) -> None:
        registry = build_registry(_Cfg([]), node_id="NODE-A")
        # publish must be a no-op and never raise.
        registry.publish(_event("critical"))
        self.assertEqual(registry.health(), [])


class SourcePluginPollTests(unittest.TestCase):
    def test_poll_sources_collects_events(self) -> None:
        class StubSource(SourcePlugin):
            async def poll(self, ctx: PluginContext):
                return [_event("medium"), _event("medium")]

        registry = build_registry(_Cfg([]), node_id="NODE-A")
        registry.register(StubSource("stub"))
        events = asyncio.run(registry.poll_sources())
        self.assertEqual(len(events), 2)

    def test_poll_sources_isolates_failures(self) -> None:
        class BadSource(SourcePlugin):
            async def poll(self, ctx: PluginContext):
                raise RuntimeError("nope")

        class GoodSource(SourcePlugin):
            async def poll(self, ctx: PluginContext):
                return [_event("low")]

        registry = build_registry(_Cfg([]), node_id="NODE-A")
        registry.register(BadSource("bad"))
        registry.register(GoodSource("good"))
        events = asyncio.run(registry.poll_sources())
        self.assertEqual(len(events), 1)


class IngestSubscriptionTests(unittest.TestCase):
    def test_inbound_events_reach_subscriber(self) -> None:
        registry = build_registry(_Cfg([]), node_id="NODE-A")
        got = []
        registry.subscribe_ingest(got.append)
        registry.bus.publish(TOPIC_INGEST, _event())
        self.assertEqual(len(got), 1)


class LoaderTests(unittest.TestCase):
    def test_resolve_builtin_and_module_path(self) -> None:
        self.assertIs(resolve_plugin_class("notify_device"), NotifyDevicePlugin)
        cls = resolve_plugin_class(
            "plugins.builtin.mqtt_transport:MqttTransportPlugin"
        )
        self.assertIs(cls, MqttTransportPlugin)
        self.assertIsNone(resolve_plugin_class("does_not_exist"))

    def test_build_plugin_respects_enabled(self) -> None:
        self.assertIsNone(build_plugin({"type": "notify_device", "enabled": False}))
        plugin = build_plugin({"type": "notify_device", "name": "n"})
        self.assertIsInstance(plugin, NotifyDevicePlugin)


class MqttTransportTests(unittest.TestCase):
    def test_validate_before_publish(self) -> None:
        fake = FakeMqttClient()
        plugin = MqttTransportPlugin("bus", {"client": fake, "base_topic": "intel/events"})
        plugin.start(PluginContext(bus=EventBus(), config=None, node_id="N"))
        # An invalid event must be rejected before any publish happens.
        bad = EmergencyEvent(title="x", severity="not-real")
        with self.assertRaises(ValueError):
            plugin.send(bad)
        self.assertEqual(fake.published, [])

    def test_published_topics_for(self) -> None:
        plugin = MqttTransportPlugin("bus", {"base_topic": "intel/events"})
        self.assertEqual(
            plugin.published_topics_for(_event("low")),
            ["intel/events/normalized"],
        )
        self.assertEqual(
            plugin.published_topics_for(_event("critical")),
            ["intel/events/normalized", "intel/events/high_priority"],
        )


if __name__ == "__main__":
    unittest.main()
