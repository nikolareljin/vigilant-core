"""VigilantCore plugin kernel.

Public surface: the plugin base classes and the :class:`EventBus`/registry that
turn ingest, transport, device, and automation capabilities into composable
plugins speaking the :class:`~contracts.EmergencyEvent` contract.
"""

from __future__ import annotations

from .base import (
    DevicePlugin,
    EventBus,
    Plugin,
    PluginContext,
    PluginHealth,
    SinkPlugin,
    SourcePlugin,
    TransportPlugin,
    TOPIC_HIGH,
    TOPIC_INGEST,
    TOPIC_NEW,
)
from .loader import BUILTIN_PLUGINS, build_registry
from .registry import PluginRegistry

__all__ = [
    "Plugin",
    "SourcePlugin",
    "TransportPlugin",
    "DevicePlugin",
    "SinkPlugin",
    "PluginContext",
    "PluginHealth",
    "EventBus",
    "PluginRegistry",
    "build_registry",
    "BUILTIN_PLUGINS",
    "TOPIC_NEW",
    "TOPIC_HIGH",
    "TOPIC_INGEST",
]
