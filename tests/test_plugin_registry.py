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


class PluginHealthTests(unittest.TestCase):
    def test_success_clears_error_and_error_updates_item_count(self) -> None:
        from plugins.base import PluginHealth
        h = PluginHealth(name="x", kind="source")
        h.record_success(item_count=5)
        h.record_error("boom")  # item_count must update on failure too
        self.assertEqual(h.last_item_count, 0)
        self.assertIsNotNone(h.last_error_utc)
        h.record_success(item_count=3)  # success clears error + its timestamp
        self.assertIsNone(h.last_error)
        self.assertIsNone(h.last_error_utc)
        snap = h.as_dict()
        self.assertEqual(snap["last_successful_fetch_utc"], snap["last_success_utc"])


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

    def test_high_impact_score_routes_high_even_if_severity_low(self) -> None:
        # issue #58: high_priority is impact_score >= 7 OR severity high/critical.
        fake = FakeMqttClient()
        cfg = _Cfg([
            {"type": "mqtt_transport", "name": "bus",
             "options": {"client": fake, "base_topic": "intel/events"}},
            {"type": "notify_device", "name": "siren",
             "options": {"desktop": False}},
        ])
        registry = build_registry(cfg, node_id="NODE-A")
        ev = EmergencyEvent(title="Quiet-looking but severe", hazard_type="outage",
                            severity="medium", confidence=0.6, impact_score=8)
        registry.publish(ev)
        self.assertIn("intel/events/high_priority", [t for t, _ in fake.published])
        siren = next(p for p in registry.plugins if p.name == "siren")
        self.assertEqual(len(siren.rendered), 1)

    def test_disabled_plugin_not_loaded(self) -> None:
        cfg = _Cfg([
            {"type": "notify_device", "name": "off", "enabled": False, "options": {}},
        ])
        registry = build_registry(cfg, node_id="NODE-A")
        self.assertEqual(registry.plugins, [])

    def test_restart_does_not_double_subscribe(self) -> None:
        cfg = _Cfg([
            {"type": "notify_device", "name": "log",
             "options": {"min_severity": "low", "desktop": False}},
        ])
        registry = build_registry(cfg, node_id="NODE-A")
        log = registry.plugins[0]
        registry.publish(_event("low"))
        self.assertEqual(len(log.rendered), 1)
        # Stop then start again (config reload / reconnect) must not leave a
        # stale subscription that double-delivers.
        registry.stop_all()
        registry.start_all()
        registry.publish(_event("low"))
        self.assertEqual(len(log.rendered), 2)

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


class ConfigPersistenceTests(unittest.TestCase):
    def test_appconfig_persists_plugins(self) -> None:
        import tempfile
        from pathlib import Path
        from unittest.mock import patch
        from utils.config import AppConfig, load_config, save_config

        with tempfile.TemporaryDirectory() as tmp:
            with patch("utils.config.config_dir", return_value=Path(tmp)):
                cfg = AppConfig(plugins=[
                    {"type": "mqtt_transport", "name": "bus", "enabled": True,
                     "options": {"host": "127.0.0.1"}},
                ])
                save_config(cfg)
                loaded = load_config()
                self.assertEqual(loaded.plugins, cfg.plugins)


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
        # High impact with non-severe severity still targets high_priority (#58).
        high_impact = EmergencyEvent(title="x", severity="medium", confidence=0.5,
                                     impact_score=9)
        self.assertIn("intel/events/high_priority",
                      plugin.published_topics_for(high_impact))

    def test_send_raises_when_disconnected(self) -> None:
        # No client injected and no broker: send must fail, not fake success.
        plugin = MqttTransportPlugin("bus", {"base_topic": "intel/events"})
        plugin.start(PluginContext(bus=EventBus(), config=None, node_id="N"))
        with self.assertRaises(RuntimeError):
            plugin.send(_event("critical"))

    def test_stop_resets_client_for_reconnect(self) -> None:
        fake = FakeMqttClient()
        plugin = MqttTransportPlugin("bus", {"client": fake})
        plugin.start(PluginContext(bus=EventBus(), config=None, node_id="N"))
        plugin.stop()
        self.assertIsNone(plugin._client)


class LoaderHardeningTests(unittest.TestCase):
    def test_missing_type_returns_none(self) -> None:
        # A name without a type is a misconfiguration, not a type.
        self.assertIsNone(build_plugin({"name": "siren"}))

    def test_nonobject_options_coerced(self) -> None:
        plugin = build_plugin(
            {"type": "notify_device", "name": "n", "options": "not-a-dict"}
        )
        self.assertIsInstance(plugin, NotifyDevicePlugin)
        self.assertEqual(plugin.options, {})


if __name__ == "__main__":
    unittest.main()
