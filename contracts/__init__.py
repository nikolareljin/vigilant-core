"""Shared platform contracts for VigilantCore.

The :class:`EmergencyEvent` here is the single source of truth for the event
shape exchanged between the Python hub, the dashboard, the MQTT bus, and the
Rust/Go edge daemons. Importing from ``contracts`` (rather than reaching into
``utils``) is the supported way for plugins and external components to speak the
platform's language.
"""

from __future__ import annotations

from .event import (
    EmergencyEvent,
    HAZARD_TYPES,
    SCHEMA_VERSION,
    SEVERITIES,
    infer_hazard_type,
)
from .ids import new_ulid
from .schema import load_schema
from . import trust

__all__ = [
    "EmergencyEvent",
    "HAZARD_TYPES",
    "SEVERITIES",
    "SCHEMA_VERSION",
    "infer_hazard_type",
    "new_ulid",
    "load_schema",
    "trust",
]
