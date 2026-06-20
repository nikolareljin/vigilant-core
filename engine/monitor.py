"""Async monitoring loop for VigilantCore."""

from __future__ import annotations

import asyncio
import json
import logging
import re
import threading
from dataclasses import dataclass
from pathlib import Path
from math import asin, cos, radians, sin, sqrt
from datetime import datetime, timedelta, timezone
from time import perf_counter
from typing import Callable, Dict, Iterable, List, Optional
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import feedparser
import httpx
import pgeocode

from .parser import ImpactParser, ParsedImpact
from contracts import EmergencyEvent
from mesh.forwarding import ForwardingQueue
from mesh.node import load_or_create_node
from plugins import build_registry
from utils import database
from utils.config import AppConfig, config_dir
from utils.event_deduplication import deduplicate_events
from utils.event_normalization import normalize_event_payload
from utils.sources import (
    build_all_feeds,
    build_comprehensive_local_feeds,
    build_local_feeds,
    build_social_feeds,
    discover_local_source_feeds,
    ensure_seed_feeds,
    search_duckduckgo_results,
    search_emergency_info,
)

logger = logging.getLogger(__name__)
SENSITIVE_QUERY_PARAMS = {
    "key",
    "api_key",
    "apikey",
    "token",
    "access_token",
    "refresh_token",
    "cx",
    "client_secret",
    "subscription-key",
    "ocp-apim-subscription-key",
}

SOURCE_HEALTH_CATALOG = {
    "rss": "RSS feeds",
    "news_api": "NewsAPI",
    "google_cse": "Google CSE",
    "bing_search": "Bing Search",
    "duckduckgo": "DuckDuckGo",
    "emergency_search": "Emergency Search",
}


@dataclass
class AlertItem:
    url: str
    title: str
    snippet: str
    published_at: Optional[str]
    source: str
    source_kind: str = "unknown"
    merged_urls: tuple[str, ...] = ()
    merged_sources: tuple[str, ...] = ()


class MonitorEngine:
    def __init__(
        self,
        config: AppConfig,
        on_new_alert: Optional[Callable[[Dict], None]] = None,
    ) -> None:
        self.config = config
        self.on_new_alert = on_new_alert
        self._stop_event = asyncio.Event()
        self._geo = pgeocode.Nominatim("us")
        self._local_source_feeds: Optional[List[str]] = None
        self._social_feeds: Optional[List[str]] = None
        self._seed_feeds: Optional[List[str]] = None
        self._source_health_lock = threading.Lock()
        self._source_health: Dict[str, Dict[str, object]] = {}
        self._initialize_source_health()
        if not logging.getLogger().handlers:
            logging.basicConfig(
                level=logging.INFO,
                format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            )
        location_context = self._location_context()
        self._parser = ImpactParser(
            config.subject,
            location_context,
            config.question,
            prefer_light_model=config.prefer_light_model,
        )
        self.model_name = self._parser.current_model()

        # Platform layer: node identity, plugin kernel, store-and-forward queue.
        # Only stood up when plugins are configured — with none, behavior is
        # identical to prior releases (no node file, no mesh tables, no queue).
        self.node = None
        self.node_id: Optional[str] = None
        self.registry = None
        self.forwarding: Optional[ForwardingQueue] = None
        self._inbound_lock = threading.Lock()
        self._inbound_events: List[EmergencyEvent] = []
        self._max_inbound = 1000
        if config.plugins:
            # Wrapped so a field node still monitors even if an optional plugin or
            # transport dependency is unavailable.
            try:
                self.node = load_or_create_node(
                    label=config.node_label, role=config.node_role
                )
                self.node_id = self.node.node_id
                self.registry = build_registry(config, node_id=self.node_id)
                self.registry.subscribe_ingest(self._buffer_inbound_event)
                self.forwarding = ForwardingQueue(self.node_id)
            except Exception:
                logger.exception(
                    "Platform layer init failed; continuing in standalone mode"
                )

    def _buffer_inbound_event(self, event: EmergencyEvent) -> None:
        """Bus handler for events received from transports (TOPIC_INGEST)."""

        with self._inbound_lock:
            self._inbound_events.append(event)
            # Bound the buffer so a noisy transport or stalled gather loop can't
            # grow it without limit; drop the oldest on overflow.
            overflow = len(self._inbound_events) - self._max_inbound
            if overflow > 0:
                del self._inbound_events[:overflow]
                logger.warning(
                    "Inbound event buffer full; dropped %d oldest event(s)", overflow
                )

    def _drain_inbound_events(self) -> List[EmergencyEvent]:
        with self._inbound_lock:
            drained = self._inbound_events
            self._inbound_events = []
        return drained

    def get_plugin_health(self) -> List[Dict[str, object]]:
        """Plugin health snapshots for the dashboard (empty when no plugins)."""

        return self.registry.health() if self.registry else []

    def _is_source_enabled(self, source_key: str) -> bool:
        if source_key == "rss":
            return not self.config.disable_rss_fetch
        if source_key == "news_api":
            return bool(self.config.news_api_key)
        if source_key == "google_cse":
            return bool(self.config.google_cse_api_key and self.config.google_cse_cx)
        if source_key == "bing_search":
            return bool(self.config.bing_search_key)
        if source_key == "duckduckgo":
            return bool(self.config.enable_duckduckgo_search)
        if source_key == "emergency_search":
            return bool(self.config.zip_code or self.config.location_name)
        return True

    def _initialize_source_health(self) -> None:
        with self._source_health_lock:
            for source_key, display_name in SOURCE_HEALTH_CATALOG.items():
                self._source_health[source_key] = self._default_source_health_entry(source_key, display_name)

    def _default_source_health_entry(self, source_key: str, source_name: str | None = None) -> Dict[str, object]:
        return {
            "source_key": source_key,
            "source_name": source_name or SOURCE_HEALTH_CATALOG.get(source_key, source_key),
            "enabled": self._is_source_enabled(source_key),
            "last_attempt_utc": None,
            "last_successful_fetch_utc": None,
            "last_error_utc": None,
            "last_error": None,
            "error_count": 0,
            "attempt_count": 0,
            "success_count": 0,
            "last_latency_ms": None,
            "last_item_count": 0,
        }

    def _record_source_fetch(
        self,
        source_key: str,
        *,
        success: bool,
        latency_ms: float,
        item_count: int = 0,
        error: str | None = None,
    ) -> None:
        now_iso = datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
        with self._source_health_lock:
            entry = self._source_health.get(source_key)
            if entry is None:
                entry = self._default_source_health_entry(source_key)
                self._source_health[source_key] = entry
            entry["enabled"] = self._is_source_enabled(source_key)
            entry["last_attempt_utc"] = now_iso
            entry["last_latency_ms"] = round(max(0.0, float(latency_ms)), 2)
            entry["last_item_count"] = max(0, int(item_count))
            entry["attempt_count"] = int(entry.get("attempt_count", 0)) + 1
            if success:
                entry["success_count"] = int(entry.get("success_count", 0)) + 1
                entry["last_successful_fetch_utc"] = now_iso
                entry["last_error"] = None
                entry["last_error_utc"] = None
            else:
                entry["error_count"] = int(entry.get("error_count", 0)) + 1
                safe_error = self._sanitize_error_message(error or "Fetch failed")
                entry["last_error"] = safe_error[:240].strip() or "Fetch failed"
                entry["last_error_utc"] = now_iso

    def _mark_source_skipped(self, source_key: str) -> None:
        with self._source_health_lock:
            entry = self._source_health.get(source_key)
            if entry is None:
                entry = self._default_source_health_entry(source_key)
                self._source_health[source_key] = entry
            entry["enabled"] = self._is_source_enabled(source_key)

    def _sanitize_error_message(self, error: object) -> str:
        message = str(error or "Fetch failed")
        if not message:
            return "Fetch failed"

        def _replace(match: re.Match[str]) -> str:
            candidate = match.group(0)
            if "://" not in candidate:
                return candidate
            try:
                split = urlsplit(candidate)
                if not split.query:
                    return candidate
                redacted_pairs = []
                changed = False
                for key, value in parse_qsl(split.query, keep_blank_values=True):
                    if key.lower() in SENSITIVE_QUERY_PARAMS:
                        redacted_pairs.append((key, "[REDACTED]"))
                        changed = True
                    else:
                        redacted_pairs.append((key, value))
                if not changed:
                    return candidate
                safe_query = urlencode(redacted_pairs, doseq=True)
                return urlunsplit((split.scheme, split.netloc, split.path, safe_query, split.fragment))
            except Exception:
                return candidate

        return re.sub(r"https?://[^\s)]+", _replace, message)

    def get_source_health_snapshot(self) -> List[Dict[str, object]]:
        with self._source_health_lock:
            keys = sorted(self._source_health.keys())
            return [{**self._source_health[key]} for key in keys]

    @staticmethod
    def _url_exists_cached(
        url: str,
        cache: Dict[str, bool],
    ) -> bool:
        if not url:
            return False
        exists = cache.get(url)
        if exists is None:
            exists = database.alert_exists(url)
            cache[url] = exists
        return exists

    def _location_context(self) -> str:
        if self.config.relax_location_filter:
            return "Global"
        parts = [self.config.location_name]
        if self.config.zip_code:
            parts.append(f"ZIP {self.config.zip_code}")
        if self.config.latitude is not None and self.config.longitude is not None:
            parts.append(f"{self.config.latitude},{self.config.longitude}")
        if self.config.radius_km:
            parts.append(f"within {self.config.radius_km}km")
        return " | ".join(p for p in parts if p)

    def _is_low_bandwidth(self) -> bool:
        return bool(getattr(self.config, "low_bandwidth_mode", False))

    def _feed_cache_path(self) -> Path:
        base = config_dir()
        base.mkdir(parents=True, exist_ok=True)
        return base / "feed_cache.json"

    def _load_feed_cache(self) -> dict:
        path = self._feed_cache_path()
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _save_feed_cache(self, cache: dict) -> None:
        try:
            self._feed_cache_path().write_text(json.dumps(cache, indent=2), encoding="utf-8")
        except Exception:
            logger.exception("Failed to write feed cache")

    async def _validate_feed_async(self, url: str, client: httpx.AsyncClient) -> bool:
        try:
            resp = await client.get(url, timeout=10)
            if resp.status_code in (404, 410):
                return False
            resp.raise_for_status()
            text = resp.text.lower()
            return "<rss" in text or "<feed" in text
        except Exception:
            return False

    async def _filter_valid_feeds(self, feed_urls: List[str]) -> List[str]:
        if not feed_urls:
            return feed_urls
        cache = self._load_feed_cache()
        checked_at = cache.get("checked_at")
        valid_cached = set(cache.get("valid_feeds", []))
        invalid_cached = {
            url: meta for url, meta in (cache.get("invalid_feeds", {}) or {}).items()
        }
        now = datetime.utcnow()
        cache_age_ok = False
        if checked_at:
            try:
                cache_time = datetime.fromisoformat(checked_at.replace("Z", "+00:00"))
                cache_age_ok = (now - cache_time).total_seconds() < 24 * 3600
            except Exception:
                cache_age_ok = False

        valid_feeds: List[str] = []
        to_check: List[str] = []
        for url in feed_urls:
            if url in valid_cached and cache_age_ok:
                valid_feeds.append(url)
                continue
            if url in invalid_cached:
                try:
                    invalid_time = datetime.fromisoformat(
                        invalid_cached[url]["checked_at"].replace("Z", "+00:00")
                    )
                    if (now - invalid_time).total_seconds() < 7 * 24 * 3600:
                        continue
                except Exception:
                    pass
            to_check.append(url)

        if not to_check:
            return list(dict.fromkeys(valid_feeds))

        sem = asyncio.Semaphore(10)

        async def _check(url: str, client: httpx.AsyncClient) -> tuple[str, bool]:
            async with sem:
                return (url, await self._validate_feed_async(url, client))

        async with httpx.AsyncClient(follow_redirects=True, timeout=10) as client:
            results = await asyncio.gather(*[_check(url, client) for url in to_check])

        for url, ok in results:
            if ok:
                valid_feeds.append(url)
                valid_cached.add(url)
                invalid_cached.pop(url, None)
            else:
                invalid_cached[url] = {"checked_at": now.isoformat() + "Z"}

        cache["checked_at"] = now.isoformat() + "Z"
        cache["valid_feeds"] = sorted(valid_cached)
        cache["invalid_feeds"] = invalid_cached
        self._save_feed_cache(cache)
        return list(dict.fromkeys(valid_feeds))

    def _get_local_source_feeds(self) -> List[str]:
        if self._local_source_feeds is None:
            # Use comprehensive local feeds when location info is available
            has_coords = (
                self.config.latitude is not None and self.config.longitude is not None
            )
            if self.config.zip_code or has_coords:
                self._local_source_feeds = build_comprehensive_local_feeds(
                    subject=self.config.subject,
                    location_name=self.config.location_name,
                    zip_code=self.config.zip_code,
                    latitude=self.config.latitude,
                    longitude=self.config.longitude,
                    low_bandwidth=self._is_low_bandwidth(),
                )
                logger.info(
                    "Discovered %d comprehensive local feeds for %s",
                    len(self._local_source_feeds),
                    self.config.location_name or self.config.zip_code,
                )
            else:
                self._local_source_feeds = discover_local_source_feeds(
                    self.config.location_name,
                    self.config.zip_code,
                    max_feeds=5 if self._is_low_bandwidth() else 20,
                    low_bandwidth=self._is_low_bandwidth(),
                )
        return self._local_source_feeds

    def _get_social_feeds(self) -> List[str]:
        if self._social_feeds is None:
            self._social_feeds = build_social_feeds(
                self.config.subject, self.config.location_name, self.config.zip_code
            )
        return self._social_feeds

    def _get_seed_feeds(self) -> List[str]:
        if self._seed_feeds is None:
            self._seed_feeds = ensure_seed_feeds([])
        return self._seed_feeds

    def _get_center_coords(self) -> Optional[tuple[float, float]]:
        if self.config.latitude is not None and self.config.longitude is not None:
            return (self.config.latitude, self.config.longitude)
        if not self.config.zip_code:
            return None
        info = self._geo.query_postal_code(self.config.zip_code)
        lat = info.get("latitude")
        lon = info.get("longitude")
        if lat is None or lon is None:
            return None
        return (float(lat), float(lon))

    def _haversine_km(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        r = 6371.0
        dlat = radians(lat2 - lat1)
        dlon = radians(lon2 - lon1)
        a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
        return 2 * r * asin(sqrt(a))

    def _extract_coords(self, text: str) -> Optional[tuple[float, float]]:
        # Look for simple "lat,lon" patterns in content.
        for token in text.replace("(", " ").replace(")", " ").split():
            if "," not in token:
                continue
            left, right = token.split(",", 1)
            try:
                lat = float(left)
                lon = float(right)
            except ValueError:
                continue
            if -90 <= lat <= 90 and -180 <= lon <= 180:
                return (lat, lon)
        return None

    def _location_keywords(self) -> List[str]:
        keywords = []
        if self.config.location_name:
            keywords.extend(self.config.location_name.lower().split())
        if self.config.zip_code:
            keywords.append(self.config.zip_code.lower())
        if self.config.latitude is not None and self.config.longitude is not None:
            keywords.append(f"{self.config.latitude}".lower())
            keywords.append(f"{self.config.longitude}".lower())
        return [kw for kw in keywords if kw]

    def _matches_location(self, item: AlertItem) -> bool:
        if self.config.relax_location_filter:
            return True
        # Plugin/transport events are produced intentionally for this node and
        # carry their own structured location; don't drop them for lacking
        # location words/coords in the title/summary text.
        if item.source_kind == "plugin":
            return True
        keywords = self._location_keywords()
        center = self._get_center_coords()
        if center:
            text = f"{item.title} {item.snippet}"
            coords = self._extract_coords(text)
            if coords:
                distance = self._haversine_km(center[0], center[1], coords[0], coords[1])
                return distance <= max(1, self.config.radius_km)
        if not keywords:
            return True
        haystack = f"{item.title} {item.snippet}".lower()
        return any(kw in haystack for kw in keywords)

    async def fetch_rss_items(self, feed_urls: Optional[List[str]] = None) -> List[AlertItem]:
        source_key = "rss"
        started = perf_counter()
        items: List[AlertItem] = []
        if not self._is_source_enabled(source_key):
            self._mark_source_skipped(source_key)
            return items
        feed_urls = feed_urls or ensure_seed_feeds(self.config.rss_feeds)
        if self._is_low_bandwidth() and len(feed_urls) > 40:
            feed_urls = feed_urls[:40]
        bad_feeds: List[str] = []
        fetch_errors = 0
        async with httpx.AsyncClient(timeout=12 if self._is_low_bandwidth() else 20) as client:
            for feed_url in feed_urls:
                try:
                    resp = await client.get(feed_url)
                    if resp.status_code in (404, 410):
                        bad_feeds.append(feed_url)
                        continue
                    resp.raise_for_status()
                    parsed = await asyncio.to_thread(feedparser.parse, resp.text)
                except Exception:
                    fetch_errors += 1
                    continue
                for entry in parsed.entries:
                    url = entry.get("link")
                    if not url:
                        continue
                    published = entry.get("published") or entry.get("updated")
                    items.append(
                        AlertItem(
                            url=url,
                            title=entry.get("title", "(no title)"),
                            snippet=entry.get("summary", ""),
                            published_at=published,
                            source=parsed.feed.get("title", "RSS"),
                            source_kind="rss",
                        )
                    )
        if bad_feeds:
            cache = self._load_feed_cache()
            invalid_cached = cache.get("invalid_feeds", {}) or {}
            now = datetime.utcnow().isoformat() + "Z"
            for feed_url in bad_feeds:
                invalid_cached[feed_url] = {"checked_at": now}
            cache["invalid_feeds"] = invalid_cached
            self._save_feed_cache(cache)
        latency_ms = (perf_counter() - started) * 1000
        failed_feeds = fetch_errors + len(bad_feeds)
        if failed_feeds > 0 and len(items) == 0 and len(feed_urls) > 0:
            error_parts = []
            if fetch_errors > 0:
                error_parts.append(f"{fetch_errors} feed(s) had fetch errors")
            if bad_feeds:
                error_parts.append(f"{len(bad_feeds)} feed(s) returned 404/410")
            self._record_source_fetch(
                source_key,
                success=False,
                latency_ms=latency_ms,
                item_count=0,
                error="; ".join(error_parts) if error_parts else "RSS fetch failed",
            )
        else:
            self._record_source_fetch(source_key, success=True, latency_ms=latency_ms, item_count=len(items))
        return items

    async def fetch_news_api_items(self) -> List[AlertItem]:
        source_key = "news_api"
        started = perf_counter()
        items: List[AlertItem] = []
        if not self._is_source_enabled(source_key):
            self._mark_source_skipped(source_key)
            return items
        window_hours = max(1, int(self.config.news_time_window_hours or 6))
        since = (datetime.utcnow() - timedelta(hours=window_hours)).isoformat() + "Z"
        url = "https://newsapi.org/v2/everything"
        headers = {"X-Api-Key": self.config.news_api_key}

        async def _query_news_api(query: str) -> dict:
            params = {
                "q": query,
                "pageSize": 50,
                "sortBy": self.config.news_sort_by or "popularity",
                "language": "en",
                "from": since,
            }
            logger.info(
                "NewsAPI request q=%r from=%s sortBy=%s",
                query,
                since,
                params["sortBy"],
            )
            async with httpx.AsyncClient(timeout=20) as client:
                resp = await client.get(url, params=params, headers=headers)
                resp.raise_for_status()
                payload = resp.json()
                logger.info(
                    "NewsAPI response status=%s totalResults=%s",
                    resp.status_code,
                    payload.get("totalResults"),
                )
                return payload

        base_query = self._build_search_query()
        query_steps = [base_query]
        if self.config.location_name:
            query_steps.append(f"{self.config.subject} {self.config.location_name}")
        if self.config.subject:
            query_steps.append(self.config.subject)
        seen = set()
        for raw_query in query_steps:
            query = self._limit_query(raw_query.strip())
            if not query or query in seen:
                continue
            seen.add(query)
            if raw_query and len(query) < len(raw_query):
                logger.info(
                    "NewsAPI query trimmed from %d to %d chars", len(raw_query), len(query)
                )
            try:
                payload = await _query_news_api(query)
            except Exception as exc:
                logger.exception("NewsAPI request failed")
                self._record_source_fetch(
                    source_key,
                    success=False,
                    latency_ms=(perf_counter() - started) * 1000,
                    item_count=0,
                    error=str(exc),
                )
                return items
            if payload.get("status") != "ok":
                logger.info("NewsAPI error: %s", payload.get("message"))
                self._record_source_fetch(
                    source_key,
                    success=False,
                    latency_ms=(perf_counter() - started) * 1000,
                    item_count=0,
                    error=str(payload.get("message") or "NewsAPI returned non-ok status"),
                )
                return items
            articles = payload.get("articles", []) or []
            if not articles:
                logger.info("NewsAPI returned 0 results for q=%r; broadening query", query)
                continue
            for article in articles:
                url = article.get("url")
                if not url:
                    continue
                items.append(
                    AlertItem(
                        url=url,
                        title=article.get("title") or "(no title)",
                        snippet=article.get("description") or "",
                        published_at=article.get("publishedAt"),
                        source=article.get("source", {}).get("name", "News API"),
                        source_kind="news_api",
                    )
                )
            if items:
                self._record_source_fetch(
                    source_key,
                    success=True,
                    latency_ms=(perf_counter() - started) * 1000,
                    item_count=len(items),
                )
                return items
        # Fallback: try top-headlines with subject only (country=us).
        if self.config.subject:
            try:
                params = {
                    "q": self._limit_query(self.config.subject),
                    "pageSize": 50,
                    "country": "us",
                }
                url = "https://newsapi.org/v2/top-headlines"
                logger.info("NewsAPI top-headlines fallback q=%r country=us", params["q"])
                async with httpx.AsyncClient(timeout=20) as client:
                    resp = await client.get(url, params=params, headers=headers)
                    resp.raise_for_status()
                    payload = resp.json()
                logger.info(
                    "NewsAPI top-headlines status=%s totalResults=%s",
                    resp.status_code,
                    payload.get("totalResults"),
                )
                for article in payload.get("articles", []) or []:
                    url = article.get("url")
                    if not url:
                        continue
                    items.append(
                        AlertItem(
                            url=url,
                            title=article.get("title") or "(no title)",
                            snippet=article.get("description") or "",
                            published_at=article.get("publishedAt"),
                            source=article.get("source", {}).get("name", "News API"),
                            source_kind="news_api",
                        )
                    )
                if items:
                    self._record_source_fetch(
                        source_key,
                        success=True,
                        latency_ms=(perf_counter() - started) * 1000,
                        item_count=len(items),
                    )
                    return items
            except Exception as exc:
                logger.exception("NewsAPI top-headlines request failed")
                self._record_source_fetch(
                    source_key,
                    success=False,
                    latency_ms=(perf_counter() - started) * 1000,
                    item_count=0,
                    error=str(exc),
                )
                return items
        self._record_source_fetch(
            source_key,
            success=True,
            latency_ms=(perf_counter() - started) * 1000,
            item_count=len(items),
        )
        return items

    def _build_search_query(self) -> str:
        query = self.config.subject
        if self.config.location_name:
            query = f"{query} {self.config.location_name}"
        if self.config.zip_code:
            query = f"{query} {self.config.zip_code}"
        if self.config.latitude is not None and self.config.longitude is not None:
            query = f"{query} {self.config.latitude},{self.config.longitude}"
        return query.strip()

    def _limit_query(self, query: str, limit: int = 500) -> str:
        if not query:
            return query
        if len(query) <= limit:
            return query
        trimmed = query[:limit]
        if " " in trimmed:
            trimmed = trimmed.rsplit(" ", 1)[0]
        return trimmed.rstrip()

    async def fetch_bing_items(self) -> List[AlertItem]:
        source_key = "bing_search"
        started = perf_counter()
        items: List[AlertItem] = []
        if not self._is_source_enabled(source_key):
            self._mark_source_skipped(source_key)
            return items
        query = self._limit_query(self._build_search_query())
        if not query:
            self._record_source_fetch(source_key, success=True, latency_ms=(perf_counter() - started) * 1000, item_count=0)
            return items
        endpoint = self.config.bing_search_endpoint or "https://api.bing.microsoft.com/v7.0/search"
        params = {
            "q": query,
            "count": 20,
            "mkt": self.config.bing_search_market or "en-US",
            "safeSearch": self.config.bing_search_safe or "Moderate",
        }
        headers = {"Ocp-Apim-Subscription-Key": self.config.bing_search_key}
        async with httpx.AsyncClient(timeout=20) as client:
            try:
                resp = await client.get(endpoint, params=params, headers=headers)
                resp.raise_for_status()
                payload = resp.json()
            except Exception as exc:
                self._record_source_fetch(
                    source_key,
                    success=False,
                    latency_ms=(perf_counter() - started) * 1000,
                    item_count=0,
                    error=str(exc),
                )
                return items
        for entry in payload.get("webPages", {}).get("value", []) or []:
            link = entry.get("url")
            if not link:
                continue
            items.append(
                AlertItem(
                    url=link,
                    title=entry.get("name") or "(no title)",
                    snippet=entry.get("snippet") or "",
                    published_at=None,
                    source="Bing Search",
                    source_kind="bing_search",
                )
            )
        self._record_source_fetch(
            source_key,
            success=True,
            latency_ms=(perf_counter() - started) * 1000,
            item_count=len(items),
        )
        return items

    async def fetch_duckduckgo_items(self) -> List[AlertItem]:
        source_key = "duckduckgo"
        started = perf_counter()
        if not self._is_source_enabled(source_key):
            self._mark_source_skipped(source_key)
            return []
        query = self._limit_query(self._build_search_query())
        if not query:
            self._record_source_fetch(source_key, success=True, latency_ms=(perf_counter() - started) * 1000, item_count=0)
            return []
        items: List[AlertItem] = []
        try:
            for result in search_duckduckgo_results(query, max_results=8 if self._is_low_bandwidth() else 20):
                items.append(
                    AlertItem(
                        url=result.url,
                        title=result.title,
                        snippet=result.snippet,
                        published_at=None,
                        source="DuckDuckGo",
                        source_kind="duckduckgo",
                    )
                )
        except Exception as exc:
            self._record_source_fetch(
                source_key,
                success=False,
                latency_ms=(perf_counter() - started) * 1000,
                item_count=0,
                error=str(exc),
            )
            return []
        self._record_source_fetch(
            source_key,
            success=True,
            latency_ms=(perf_counter() - started) * 1000,
            item_count=len(items),
        )
        return items

    async def fetch_emergency_items(self) -> List[AlertItem]:
        """Fetch emergency-related search results for the subject and location."""
        source_key = "emergency_search"
        started = perf_counter()
        items: List[AlertItem] = []

        # Only run if we have location info
        if not self._is_source_enabled(source_key):
            self._mark_source_skipped(source_key)
            return items

        try:
            results = search_emergency_info(
                subject=self.config.subject,
                location_name=self.config.location_name,
                zip_code=self.config.zip_code,
                latitude=self.config.latitude,
                longitude=self.config.longitude,
                max_results=10 if self._is_low_bandwidth() else 20,
                low_bandwidth=self._is_low_bandwidth(),
            )
            for result in results:
                items.append(
                    AlertItem(
                        url=result.url,
                        title=result.title,
                        snippet=result.snippet,
                        published_at=None,
                        source="Emergency Search",
                        source_kind="emergency_search",
                    )
                )
            logger.info("Found %d emergency-related results", len(items))
        except Exception as exc:
            logger.exception("Failed to fetch emergency items")
            self._record_source_fetch(
                source_key,
                success=False,
                latency_ms=(perf_counter() - started) * 1000,
                item_count=0,
                error=str(exc),
            )
            return items

        self._record_source_fetch(
            source_key,
            success=True,
            latency_ms=(perf_counter() - started) * 1000,
            item_count=len(items),
        )
        return items

    async def fetch_google_cse_items(self) -> List[AlertItem]:
        source_key = "google_cse"
        started = perf_counter()
        items: List[AlertItem] = []
        if not self._is_source_enabled(source_key):
            self._mark_source_skipped(source_key)
            return items
        query = self._limit_query(self._build_search_query())
        if not query:
            self._record_source_fetch(source_key, success=True, latency_ms=(perf_counter() - started) * 1000, item_count=0)
            return items
        url = "https://www.googleapis.com/customsearch/v1"
        params = {
            "key": self.config.google_cse_api_key,
            "cx": self.config.google_cse_cx,
            "q": query,
            "num": 10,
        }
        async with httpx.AsyncClient(timeout=20) as client:
            try:
                resp = await client.get(url, params=params)
                resp.raise_for_status()
                payload = resp.json()
            except Exception as exc:
                self._record_source_fetch(
                    source_key,
                    success=False,
                    latency_ms=(perf_counter() - started) * 1000,
                    item_count=0,
                    error=str(exc),
                )
                return items
        for entry in payload.get("items", []) or []:
            link = entry.get("link")
            if not link:
                continue
            items.append(
                AlertItem(
                    url=link,
                    title=entry.get("title") or "(no title)",
                    snippet=entry.get("snippet") or "",
                    published_at=None,
                    source="Google CSE",
                    source_kind="google_cse",
                )
            )
        self._record_source_fetch(
            source_key,
            success=True,
            latency_ms=(perf_counter() - started) * 1000,
            item_count=len(items),
        )
        return items

    async def gather_items(self) -> List[AlertItem]:
        feed_urls: List[str] = []
        if not self.config.disable_rss_fetch:
            feed_urls = list(self.config.rss_feeds)

            if not self.config.use_only_rss_feeds:
                for feed in self._get_seed_feeds():
                    if feed not in feed_urls:
                        feed_urls.append(feed)
            location_active = bool(self.config.location_name or self.config.zip_code)
            local_signal_feeds: List[str] = []
            local_feeds = build_local_feeds(
                self.config.location_name,
                self.config.zip_code,
                self.config.latitude,
                self.config.longitude,
            )
            if local_feeds:
                for feed in local_feeds:
                    if feed not in feed_urls:
                        feed_urls.append(feed)
                    if feed not in local_signal_feeds:
                        local_signal_feeds.append(feed)
            local_source_feeds = self._get_local_source_feeds()
            if local_source_feeds:
                for feed in local_source_feeds:
                    if feed not in feed_urls:
                        feed_urls.append(feed)
                    if feed not in local_signal_feeds:
                        local_signal_feeds.append(feed)
            social_feeds = self._get_social_feeds()
            if social_feeds:
                for feed in social_feeds:
                    if feed not in feed_urls:
                        feed_urls.append(feed)
            google_news_feed = self._build_google_news_feed()
            if google_news_feed and google_news_feed not in feed_urls:
                feed_urls = feed_urls + [google_news_feed]
            if google_news_feed and google_news_feed not in local_signal_feeds:
                local_signal_feeds.append(google_news_feed)
            if self._is_low_bandwidth() and len(feed_urls) > 60:
                feed_urls = feed_urls[:60]
            if location_active and not local_signal_feeds and not self.config.use_only_rss_feeds:
                fallback_max = 60 if self._is_low_bandwidth() else 400
                for feed in build_all_feeds(max_feeds=fallback_max):
                    if feed not in feed_urls:
                        feed_urls.append(feed)
            feed_urls = await self._filter_valid_feeds(feed_urls)
            self.config.rss_feeds = feed_urls
        if self.config.news_api_key:
            news_items = await self.fetch_news_api_items()
            combined = list(news_items)
            # Always add emergency items when location is available
            if self.config.zip_code or self.config.location_name:
                emergency_items = await self.fetch_emergency_items()
                combined.extend(emergency_items)
            if not combined:
                tasks = []
                if self._is_source_enabled("google_cse"):
                    tasks.append(self.fetch_google_cse_items())
                if self._is_source_enabled("bing_search"):
                    tasks.append(self.fetch_bing_items())
                if self._is_source_enabled("duckduckgo"):
                    tasks.append(self.fetch_duckduckgo_items())
                if not self.config.disable_rss_fetch:
                    tasks.insert(0, self.fetch_rss_items(feed_urls))
                results = await asyncio.gather(*tasks)
                combined = []
                for group in results:
                    combined.extend(group)
        else:
            tasks = []
            if self._is_source_enabled("google_cse"):
                tasks.append(self.fetch_google_cse_items())
            if self._is_source_enabled("bing_search"):
                tasks.append(self.fetch_bing_items())
            if self._is_source_enabled("duckduckgo"):
                tasks.append(self.fetch_duckduckgo_items())
            if not self.config.disable_rss_fetch:
                tasks.insert(0, self.fetch_rss_items(feed_urls))
            # Add emergency search if location info is available
            if self.config.zip_code or self.config.location_name:
                tasks.append(self.fetch_emergency_items())
            results = await asyncio.gather(*tasks)
            combined = []
            for group in results:
                combined.extend(group)
        plugin_items = await self._gather_plugin_items()
        if plugin_items:
            combined.extend(plugin_items)
        logger.info("Fetched %d raw items before filtering", len(combined))
        seen = set()
        filtered_items = []
        for item in combined:
            if item.url in seen:
                continue
            if not self._matches_location(item):
                continue
            seen.add(item.url)
            filtered_items.append(item)

        merged_events = deduplicate_events(
            [
                {
                    "url": item.url,
                    "title": item.title,
                    "snippet": item.snippet,
                    "published_at": item.published_at,
                    "source": item.source,
                    "source_kind": item.source_kind,
                }
                for item in filtered_items
            ]
        )

        unique_items: List[AlertItem] = []
        for event in merged_events:
            merged_urls = tuple(dict.fromkeys(event.merged_urls)) if event.merged_urls else (event.url,)
            canonical_url = min((url for url in merged_urls if url), default=event.url)
            unique_items.append(
                AlertItem(
                    url=canonical_url,
                    title=event.title,
                    snippet=event.snippet,
                    published_at=event.published_at,
                    source=event.source,
                    source_kind=event.source_kind,
                    merged_urls=merged_urls,
                    merged_sources=event.merged_sources,
                )
            )
        logger.info(
            "Items after URL/location filter: %d | after event dedup: %d",
            len(filtered_items),
            len(unique_items),
        )
        return unique_items

    def _build_google_news_feed(self) -> Optional[str]:
        query_parts = [self.config.subject]
        if self.config.location_name:
            query_parts.append(self.config.location_name)
        if self.config.zip_code:
            query_parts.append(self.config.zip_code)
        if not any(query_parts):
            return None
        query = "+".join(
            part.strip().replace(" ", "+") for part in query_parts if part.strip()
        )
        return (
            "https://news.google.com/rss/search"
            f"?q={query}&hl=en-US&gl=US&ceid=US:en"
        )

    async def _gather_plugin_items(self) -> List[AlertItem]:
        """Pull events from *source* plugins (newly observed by this node).

        These re-enter the normal dedup/store pipeline as ``AlertItem``s. Inbound
        *transport* events are handled separately (see ``_ingest_inbound_events``)
        because they must keep their original identity, not be re-minted here.
        """

        if self.registry is None:
            return []
        events: List[EmergencyEvent] = []
        try:
            events.extend(await self.registry.poll_sources())
        except Exception:
            logger.exception("Source plugin polling failed")
        return [self._event_to_alert_item(event) for event in events]

    @staticmethod
    def _event_to_alert_item(event: EmergencyEvent) -> AlertItem:
        source = event.sources[0] if event.sources else "plugin"
        return AlertItem(
            url=event.url or event.event_id,
            title=event.title,
            snippet=event.summary,
            # event_timestamp_utc is optional; fall back to the always-present
            # observed timestamp so the normalizer doesn't reset it to "now".
            published_at=event.event_timestamp_utc or event.timestamp_utc,
            source=source,
            source_kind="plugin",
        )

    def _ingest_inbound_events(self) -> int:
        """Store and relay inbound transport events, preserving their identity.

        Unlike source-plugin items, inbound mesh/transport events arrive as
        fully-formed ``EmergencyEvent``s (stable ``event_id``, ``origin_node_id``,
        ``ttl_hops``, ``seen_nodes``). They must NOT be re-minted, or cross-node
        dedup/loop/storm protection breaks — so they bypass the AlertItem pipeline.
        """

        if self.registry is None and self.forwarding is None:
            return 0
        stored = 0
        for event in self._drain_inbound_events():
            try:
                # Mesh dedup/loop suppression keyed on the ORIGINAL event_id.
                if self.forwarding is not None and not self.forwarding.offer(event).accepted:
                    continue
                url = event.url or event.event_id
                if database.alert_exists(url):
                    continue
                location = event.location or {}
                source_name = event.sources[0] if event.sources else "mesh"
                observed = event.event_timestamp_utc or event.timestamp_utc
                inserted = database.insert_alert(
                    url=url,
                    title=event.title,
                    snippet=event.summary,
                    published_at=observed,
                    source=source_name,
                    source_kind="mesh",
                    severity=event.severity,
                    confidence=event.confidence,
                    event_timestamp_utc=observed,
                    impact_score=event.impact_score,
                    predictive_outcome=event.predictive_outcome,
                    is_relevant=True,
                    subject=self.config.subject,
                    location_name=location.get("name") or self.config.location_name,
                    location_zip_code=location.get("zip_code") or None,
                    location_latitude=location.get("latitude"),
                    location_longitude=location.get("longitude"),
                    normalized_payload=event.to_dict(),
                )
                if inserted:
                    stored += 1
                    # Relay the ORIGINAL event (identity preserved) to egress.
                    if self.registry is not None:
                        self.registry.publish(event)
                    if self.on_new_alert:
                        self.on_new_alert(
                            {
                                "url": url,
                                "title": event.title,
                                "snippet": event.summary,
                                "published_at": observed,
                                "source": source_name,
                                "severity": event.severity,
                                "confidence": event.confidence,
                                "event_timestamp_utc": observed,
                                "location": location,
                                "impact_score": event.impact_score,
                                "predictive_outcome": event.predictive_outcome,
                                "is_relevant": True,
                                "created_at": datetime.utcnow().isoformat(),
                            }
                        )
            except Exception:
                logger.exception("Failed to ingest inbound event %s", event.event_id)
        return stored

    def _publish_platform_event(
        self,
        item: AlertItem,
        parsed: ParsedImpact,
        normalized: Dict,
    ) -> None:
        """Emit a stored alert as an EmergencyEvent to the mesh + egress plugins."""

        if self.registry is None and self.forwarding is None:
            return
        try:
            event = EmergencyEvent.from_normalized(
                normalized=normalized,
                title=item.title,
                snippet=item.snippet,
                impact_score=parsed.impact_score,
                predictive_outcome=parsed.predictive_outcome,
                url=item.url,
                source=item.source,
                source_kind=item.source_kind,
                merged_sources=item.merged_sources,
                origin_node_id=self.node_id,
            )
            # Stamp this node + enqueue a hop for forwarding (store-and-forward).
            if self.forwarding is not None:
                self.forwarding.offer(event)
            if self.registry is not None:
                self.registry.publish(event)
        except Exception:
            logger.exception("Failed to publish platform event for %s", item.url)

    async def process_items(self, items: Iterable[AlertItem]) -> int:
        new_count = 0
        total = 0
        existing_url_cache: Dict[str, bool] = {}

        for item in items:
            total += 1
            dedup_urls = item.merged_urls or (item.url,)
            if any(self._url_exists_cached(candidate, existing_url_cache) for candidate in dedup_urls):
                continue
            parsed = await self._parser.parse_async(item.title, item.snippet)
            normalized = normalize_event_payload(
                source_event={
                    "published_at": item.published_at,
                    "source": item.source,
                },
                impact_score=parsed.impact_score,
                is_relevant=parsed.is_relevant,
                location_name=self.config.location_name,
                source_kind=item.source_kind,
                zip_code=self.config.zip_code,
                latitude=self.config.latitude,
                longitude=self.config.longitude,
            )
            normalized_location = normalized.get("location", {})
            inserted = database.insert_alert(
                url=item.url,
                title=item.title,
                snippet=item.snippet,
                published_at=item.published_at,
                source=item.source,
                source_kind=item.source_kind,
                severity=normalized["severity"],
                confidence=normalized["confidence"],
                event_timestamp_utc=normalized["timestamp_utc"],
                impact_score=parsed.impact_score,
                predictive_outcome=parsed.predictive_outcome,
                is_relevant=parsed.is_relevant,
                subject=self.config.subject,
                location_name=self.config.location_name,
                location_zip_code=normalized_location.get("zip_code") or None,
                location_latitude=normalized_location.get("latitude"),
                location_longitude=normalized_location.get("longitude"),
                merged_urls=dedup_urls,
                merged_sources=item.merged_sources,
                normalized_payload=normalized,
            )
            if inserted:
                new_count += 1
                if self.on_new_alert:
                    self.on_new_alert(
                        {
                            "url": item.url,
                            "title": item.title,
                            "snippet": item.snippet,
                            "published_at": item.published_at,
                            "source": item.source,
                            "severity": normalized["severity"],
                            "confidence": normalized["confidence"],
                            "event_timestamp_utc": normalized["timestamp_utc"],
                            "location": normalized_location,
                            "impact_score": parsed.impact_score,
                            "predictive_outcome": parsed.predictive_outcome,
                            "is_relevant": parsed.is_relevant,
                            "created_at": datetime.utcnow().isoformat(),
                        }
                    )
                self._publish_platform_event(item, parsed, normalized)
        logger.info("Processed %d items, inserted %d", total, new_count)
        return new_count

    async def run_once(self) -> int:
        items = await self.gather_items()
        new_count = await self.process_items(items)
        # Inbound transport events take the identity-preserving path.
        new_count += self._ingest_inbound_events()
        return new_count

    async def run_forever(self) -> None:
        poll_seconds = max(60, self.config.polling_minutes * 60)
        while not self._stop_event.is_set():
            try:
                await self.run_once()
            except Exception:
                pass
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=poll_seconds)
            except asyncio.TimeoutError:
                continue

    def stop(self) -> None:
        self._stop_event.set()
