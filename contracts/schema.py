"""Loader for the bundled EmergencyEvent JSON Schema."""

from __future__ import annotations

import json
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any

SCHEMA_FILENAME = "emergency_event.schema.json"


def schema_path() -> Path:
    """Resolve the schema file, honoring PyInstaller's bundle dir when frozen.

    A ``--onefile`` build unpacks bundled data under ``sys._MEIPASS``; fall back
    to the source-relative path for normal runs. Callers should be prepared for
    ``FileNotFoundError`` if a packaged build did not include the data file.
    """

    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        bundled = Path(meipass) / "contracts" / SCHEMA_FILENAME
        if bundled.exists():
            return bundled
    return Path(__file__).with_name(SCHEMA_FILENAME)


@lru_cache(maxsize=1)
def load_schema() -> dict[str, Any]:
    """Return the parsed EmergencyEvent JSON Schema (cached)."""

    return json.loads(schema_path().read_text(encoding="utf-8"))
