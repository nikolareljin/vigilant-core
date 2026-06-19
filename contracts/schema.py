"""Loader for the bundled EmergencyEvent JSON Schema."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

SCHEMA_PATH = Path(__file__).with_name("emergency_event.schema.json")


@lru_cache(maxsize=1)
def load_schema() -> dict[str, Any]:
    """Return the parsed EmergencyEvent JSON Schema (cached)."""

    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
