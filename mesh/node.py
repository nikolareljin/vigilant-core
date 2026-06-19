"""Persistent node identity for the VigilantCore mesh.

Every install has a stable ``node_id`` so events can record their origin and the
path they have travelled (``origin_node_id``, ``seen_nodes``). Identity is stored
once under the platform data dir and reused across restarts; without it, mesh
dedup and loop-prevention have nothing to key on.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from contracts import new_ulid
from utils.config import data_dir

NODE_FILE = "node.json"
VALID_ROLES = ("hub", "edge", "relay")


@dataclass
class Node:
    node_id: str
    label: str
    role: str
    created_at: str

    def as_dict(self) -> dict:
        return asdict(self)


def node_path(base: Optional[Path] = None) -> Path:
    base = base or data_dir()
    base.mkdir(parents=True, exist_ok=True)
    return base / NODE_FILE


def load_or_create_node(
    *,
    base: Optional[Path] = None,
    label: Optional[str] = None,
    role: str = "hub",
) -> Node:
    """Load this node's identity, creating and persisting it on first run."""

    path = node_path(base)
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return Node(
                node_id=str(data["node_id"]),
                label=str(data.get("label") or data["node_id"]),
                role=str(data.get("role") or "hub"),
                created_at=str(data.get("created_at") or _now_iso()),
            )
        except Exception:
            # Corrupt identity file: fall through and recreate.
            pass
    node = Node(
        node_id=new_ulid(),
        label=label or "vigilant-node",
        role=role if role in VALID_ROLES else "hub",
        created_at=_now_iso(),
    )
    path.write_text(json.dumps(node.as_dict(), indent=2), encoding="utf-8")
    return node


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
