"""RSS source plugin — the reference SourcePlugin proving the ingest seam.

This wraps plain RSS fetching as a first-class plugin: it returns
:class:`~contracts.EmergencyEvent` objects built through the existing
``normalize_event_payload`` adapter, so events produced here flow through the
same dedup/store pipeline as the engine's native fetchers. New inbound
transports (LoRa-in #25, MQTT-in #57, sensors #36) follow this exact pattern.
"""

from __future__ import annotations

import asyncio
import logging
from time import perf_counter
from typing import List

import feedparser
import httpx

from contracts import EmergencyEvent
from utils.event_normalization import normalize_event_payload

from ..base import PluginContext, SourcePlugin

logger = logging.getLogger(__name__)


class RssSourcePlugin(SourcePlugin):
    """Fetch one or more RSS feeds listed in ``options['feeds']``."""

    async def poll(self, ctx: PluginContext) -> List[EmergencyEvent]:
        feeds = list(self.options.get("feeds", []) or [])
        if not feeds:
            return []
        started = perf_counter()
        events: List[EmergencyEvent] = []
        config = ctx.config
        location_name = getattr(config, "location_name", "") if config else ""
        zip_code = getattr(config, "zip_code", None) if config else None
        latitude = getattr(config, "latitude", None) if config else None
        longitude = getattr(config, "longitude", None) if config else None

        timeout = httpx.Timeout(self.options.get("timeout", 20))
        try:
            async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
                for feed_url in feeds:
                    try:
                        resp = await client.get(feed_url)
                        resp.raise_for_status()
                        parsed = await asyncio.to_thread(feedparser.parse, resp.text)
                    except Exception as exc:
                        logger.debug("RSS plugin %s: feed %s failed: %s", self.name, feed_url, exc)
                        continue
                    feed_title = parsed.feed.get("title", "RSS")
                    for entry in parsed.entries:
                        url = entry.get("link")
                        if not url:
                            continue
                        title = entry.get("title", "(no title)")
                        snippet = entry.get("summary", "")
                        published = entry.get("published") or entry.get("updated")
                        normalized = normalize_event_payload(
                            source_event={"published_at": published, "source": feed_title},
                            impact_score=5,
                            is_relevant=True,
                            location_name=location_name or "",
                            source_kind="rss",
                            zip_code=zip_code,
                            latitude=latitude,
                            longitude=longitude,
                        )
                        events.append(
                            EmergencyEvent.from_normalized(
                                normalized=normalized,
                                title=title,
                                snippet=snippet,
                                impact_score=5,
                                url=url,
                                source=feed_title,
                                source_kind="rss",
                                origin_node_id=ctx.node_id,
                            )
                        )
        except Exception as exc:  # pragma: no cover - network defensive
            self.health.record_error(str(exc), latency_ms=(perf_counter() - started) * 1000)
            return events
        self.health.record_success(
            latency_ms=(perf_counter() - started) * 1000, item_count=len(events)
        )
        return events
