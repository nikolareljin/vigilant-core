"""Async monitoring loop for VigilantCore."""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from math import asin, cos, radians, sin, sqrt
from datetime import datetime, timedelta
from typing import Callable, Dict, Iterable, List, Optional

import feedparser
import httpx
import pgeocode

from .parser import ImpactParser
from utils import database
from utils.config import AppConfig, config_dir
from utils.sources import (
    build_all_feeds,
    build_local_feeds,
    build_social_feeds,
    discover_local_source_feeds,
    ensure_seed_feeds,
    search_duckduckgo_results,
)

logger = logging.getLogger(__name__)


@dataclass
class AlertItem:
    url: str
    title: str
    snippet: str
    published_at: Optional[str]
    source: str


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
            self._local_source_feeds = discover_local_source_feeds(
                self.config.location_name, self.config.zip_code
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
        items: List[AlertItem] = []
        feed_urls = feed_urls or ensure_seed_feeds(self.config.rss_feeds)
        bad_feeds: List[str] = []
        async with httpx.AsyncClient(timeout=20) as client:
            for feed_url in feed_urls:
                try:
                    resp = await client.get(feed_url)
                    if resp.status_code in (404, 410):
                        bad_feeds.append(feed_url)
                        continue
                    resp.raise_for_status()
                    parsed = await asyncio.to_thread(feedparser.parse, resp.text)
                except Exception:
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
        return items

    async def fetch_news_api_items(self) -> List[AlertItem]:
        items: List[AlertItem] = []
        if not self.config.news_api_key:
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
            except Exception:
                logger.exception("NewsAPI request failed")
                return items
            if payload.get("status") != "ok":
                logger.info("NewsAPI error: %s", payload.get("message"))
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
                    )
                )
            if items:
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
                        )
                    )
                if items:
                    return items
            except Exception:
                logger.exception("NewsAPI top-headlines request failed")
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
        items: List[AlertItem] = []
        if not self.config.bing_search_key:
            return items
        query = self._limit_query(self._build_search_query())
        if not query:
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
            except Exception:
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
                )
            )
        return items

    async def fetch_duckduckgo_items(self) -> List[AlertItem]:
        if not self.config.enable_duckduckgo_search:
            return []
        query = self._limit_query(self._build_search_query())
        if not query:
            return []
        items: List[AlertItem] = []
        for result in search_duckduckgo_results(query, max_results=20):
            items.append(
                AlertItem(
                    url=result.url,
                    title=result.title,
                    snippet=result.snippet,
                    published_at=None,
                    source="DuckDuckGo",
                )
            )
        return items

    async def fetch_google_cse_items(self) -> List[AlertItem]:
        items: List[AlertItem] = []
        if not self.config.google_cse_api_key or not self.config.google_cse_cx:
            return items
        query = self._limit_query(self._build_search_query())
        if not query:
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
            except Exception:
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
                )
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
            local_feeds = build_local_feeds(self.config.location_name, self.config.zip_code)
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
            if location_active and not local_signal_feeds and not self.config.use_only_rss_feeds:
                for feed in build_all_feeds():
                    if feed not in feed_urls:
                        feed_urls.append(feed)
            feed_urls = await self._filter_valid_feeds(feed_urls)
            self.config.rss_feeds = feed_urls
        if self.config.news_api_key:
            news_items = await self.fetch_news_api_items()
            combined = list(news_items)
            if not combined:
                tasks = [
                    self.fetch_google_cse_items(),
                    self.fetch_bing_items(),
                    self.fetch_duckduckgo_items(),
                ]
                if not self.config.disable_rss_fetch:
                    tasks.insert(0, self.fetch_rss_items(feed_urls))
                results = await asyncio.gather(*tasks)
                combined = []
                for group in results:
                    combined.extend(group)
        else:
            tasks = [
                self.fetch_google_cse_items(),
                self.fetch_bing_items(),
                self.fetch_duckduckgo_items(),
            ]
            if not self.config.disable_rss_fetch:
                tasks.insert(0, self.fetch_rss_items(feed_urls))
            results = await asyncio.gather(*tasks)
        combined = []
        for group in results:
            combined.extend(group)
        logger.info("Fetched %d raw items before filtering", len(combined))
        seen = set()
        unique_items = []
        for item in combined:
            if item.url in seen:
                continue
            if not self._matches_location(item):
                continue
            seen.add(item.url)
            unique_items.append(item)
        logger.info("Items after de-dup/location filter: %d", len(unique_items))
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

    async def process_items(self, items: Iterable[AlertItem]) -> int:
        new_count = 0
        total = 0
        for item in items:
            total += 1
            if database.alert_exists(item.url):
                continue
            parsed = await self._parser.parse_async(item.title, item.snippet)
            inserted = database.insert_alert(
                url=item.url,
                title=item.title,
                snippet=item.snippet,
                published_at=item.published_at,
                source=item.source,
                impact_score=parsed.impact_score,
                predictive_outcome=parsed.predictive_outcome,
                is_relevant=parsed.is_relevant,
                subject=self.config.subject,
                location_name=self.config.location_name,
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
                            "impact_score": parsed.impact_score,
                            "predictive_outcome": parsed.predictive_outcome,
                            "is_relevant": parsed.is_relevant,
                            "created_at": datetime.utcnow().isoformat(),
                        }
                    )
        logger.info("Processed %d items, inserted %d", total, new_count)
        return new_count

    async def run_once(self) -> int:
        items = await self.gather_items()
        return await self.process_items(items)

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
