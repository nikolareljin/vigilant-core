"""Config-driven plugin loader (plugin loader v0, issue #12).

Reads the ``plugins`` list from :class:`~utils.config.AppConfig` and builds a
started :class:`~plugins.registry.PluginRegistry`. Each entry looks like::

    {"type": "rss_source", "name": "local-rss", "enabled": true,
     "options": {"feeds": ["https://…/rss"]}}

``type`` resolves against the built-in catalog, or as a ``"module:ClassName"``
path for out-of-tree plugins — the groundwork for the richer Plugin API (#19/#40).
"""

from __future__ import annotations

import importlib
import logging
from typing import Any, List, Optional, Type

from .base import Plugin, coerce_bool
from .builtin.mqtt_transport import MqttTransportPlugin
from .builtin.notify_device import NotifyDevicePlugin
from .builtin.rss_source import RssSourcePlugin
from .registry import PluginRegistry

logger = logging.getLogger(__name__)

# Built-in plugin catalog: type string -> class.
BUILTIN_PLUGINS: dict[str, Type[Plugin]] = {
    "rss_source": RssSourcePlugin,
    "mqtt_transport": MqttTransportPlugin,
    "notify_device": NotifyDevicePlugin,
}


def resolve_plugin_class(type_name: str) -> Optional[Type[Plugin]]:
    """Resolve a plugin ``type`` to a class, by catalog name or ``module:Class``."""

    if type_name in BUILTIN_PLUGINS:
        return BUILTIN_PLUGINS[type_name]
    if ":" in type_name:
        module_path, _, class_name = type_name.partition(":")
        try:
            module = importlib.import_module(module_path)
            cls = getattr(module, class_name)
        except Exception as exc:
            logger.warning("Could not import plugin %s: %s", type_name, exc)
            return None
        if isinstance(cls, type) and issubclass(cls, Plugin):
            return cls
        logger.warning("Plugin %s is not a Plugin subclass", type_name)
        return None
    logger.warning("Unknown plugin type %r", type_name)
    return None


def build_plugin(entry: dict[str, Any]) -> Optional[Plugin]:
    """Instantiate a single plugin from a config entry, or ``None`` if disabled/invalid."""

    if not isinstance(entry, dict):
        return None
    if not coerce_bool(entry.get("enabled", True), True):
        return None
    type_name = entry.get("type")
    if not type_name:
        logger.warning("Plugin entry missing 'type': %r", entry)
        return None
    cls = resolve_plugin_class(str(type_name))
    if cls is None:
        return None
    name = str(entry.get("name") or type_name)
    options = entry.get("options")
    if options is None:
        options = {}
    elif not isinstance(options, dict):
        logger.warning(
            "Plugin %s 'options' must be an object, got %s; ignoring",
            name,
            type(options).__name__,
        )
        options = {}
    try:
        return cls(name=name, options=options)
    except Exception as exc:
        logger.warning("Failed to instantiate plugin %s: %s", name, exc)
        return None


def build_registry(
    config: Any = None,
    node_id: Optional[str] = None,
    *,
    start: bool = True,
) -> PluginRegistry:
    """Build (and by default start) a registry from ``config.plugins``."""

    registry = PluginRegistry(config=config, node_id=node_id)
    entries: List[dict[str, Any]] = []
    if config is not None:
        raw = getattr(config, "plugins", None)
        if raw is None:
            raw = []
        elif not isinstance(raw, list):
            logger.warning(
                "config.plugins must be a list, got %s; ignoring",
                type(raw).__name__,
            )
            raw = []
        entries = raw
    for entry in entries:
        plugin = build_plugin(entry)
        if plugin is not None:
            registry.register(plugin)
            logger.info("Loaded plugin %s (%s)", plugin.name, plugin.kind)
    if start:
        registry.start_all()
    return registry
