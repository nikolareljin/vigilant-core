"""Notification device plugin — the reference DevicePlugin.

By default it renders high/critical events as a local notification: it shells
out to ``notify-send`` when available, otherwise logs a formatted line. Rendered
events are also retained in ``self.rendered`` so tests and the dashboard can
inspect what was surfaced without a display. Real output devices (sirens, GPIO
relays, TTS — issue #29) follow this same ``render`` shape.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from typing import List

from contracts import EmergencyEvent

from ..base import DevicePlugin, PluginContext

logger = logging.getLogger(__name__)


class NotifyDevicePlugin(DevicePlugin):
    def __init__(self, name: str, options=None) -> None:
        super().__init__(name, options)
        self.rendered: List[dict] = []
        self._use_desktop = bool(self.options.get("desktop", True))
        self._notify_send = shutil.which("notify-send") if self._use_desktop else None

    def start(self, ctx: PluginContext) -> None:
        logger.info(
            "Notify device %s ready (desktop=%s)",
            self.name,
            bool(self._notify_send),
        )

    def render(self, event: EmergencyEvent) -> None:
        title = f"[{event.severity.upper()}] {event.hazard_type}: {event.title}"
        body_parts = [event.summary or event.predictive_outcome or ""]
        location = (event.location or {}).get("name")
        if location:
            body_parts.append(f"Location: {location}")
        body = " — ".join(p for p in body_parts if p)

        self.rendered.append({"title": title, "body": body, "event_id": event.event_id})
        if self._notify_send:
            try:
                subprocess.run(
                    [self._notify_send, "-u", "critical", title, body],
                    check=False,
                    timeout=5,
                )
                return
            except Exception:  # pragma: no cover - environment dependent
                logger.debug("notify-send failed for %s; logging instead", self.name)
        logger.warning("NOTIFY %s :: %s :: %s", self.name, title, body)
