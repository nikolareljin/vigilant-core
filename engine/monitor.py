"""Async monitoring loop for VigilantCore."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from math import asin, cos, radians, sin, sqrt
from datetime import datetime
from typing import Callable, Dict, Iterable, List, Optional

import feedparser
import httpx
import pgeocode

from .parser import ImpactParser
from utils import database
from utils.config import AppConfig
from utils.sources import (
    build_local_feeds,
    build_social_feeds,
    discover_local_source_feeds,
    ensure_seed_feeds,
)


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
        async with httpx.AsyncClient(timeout=20) as client:
            for feed_url in feed_urls:
                try:
                    resp = await client.get(feed_url)
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
        return items

    async def fetch_news_api_items(self) -> List[AlertItem]:
        items: List[AlertItem] = []
        if not self.config.news_api_key:
            return items
        query = self._build_search_query()
        url = "https://newsapi.org/v2/everything"
        params = {
            "q": query,
            "pageSize": 50,
            "sortBy": "publishedAt",
            "language": "en",
        }
        headers = {"X-Api-Key": self.config.news_api_key}
        async with httpx.AsyncClient(timeout=20) as client:
            try:
                resp = await client.get(url, params=params, headers=headers)
                resp.raise_for_status()
                payload = resp.json()
            except Exception:
                return items
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

    async def fetch_google_cse_items(self) -> List[AlertItem]:
        items: List[AlertItem] = []
        if not self.config.google_cse_api_key or not self.config.google_cse_cx:
            return items
        query = self._build_search_query()
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

    async def fetch_bing_items(self) -> List[AlertItem]:
        items: List[AlertItem] = []
        if not self.config.bing_search_key:
            return items
        query = self._build_search_query()
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

    async def fetch_x_items(self) -> List[AlertItem]:
        items: List[AlertItem] = []
        if not self.config.x_api_bearer:
            return items
        query = self._build_search_query()
        if not query:
            return items
        url = "https://api.x.com/2/tweets/search/recent"
        params = {"query": query, "max_results": 10, "tweet.fields": "created_at"}
        headers = {"Authorization": f"Bearer {self.config.x_api_bearer}"}
        async with httpx.AsyncClient(timeout=20) as client:
            try:
                resp = await client.get(url, params=params, headers=headers)
                resp.raise_for_status()
                payload = resp.json()
            except Exception:
                return items
        for tweet in payload.get("data", []) or []:
            tweet_id = tweet.get("id")
            text = tweet.get("text") or ""
            if not tweet_id or not text:
                continue
            items.append(
                AlertItem(
                    url=f"https://x.com/i/web/status/{tweet_id}",
                    title=(text[:77] + "...") if len(text) > 80 else text,
                    snippet=text,
                    published_at=tweet.get("created_at"),
                    source="X",
                )
            )
        return items

    async def gather_items(self) -> List[AlertItem]:
        feed_urls = ensure_seed_feeds(self.config.rss_feeds)
        local_feeds = build_local_feeds(self.config.location_name, self.config.zip_code)
        if local_feeds:
            for feed in local_feeds:
                if feed not in feed_urls:
                    feed_urls.append(feed)
        local_source_feeds = self._get_local_source_feeds()
        if local_source_feeds:
            for feed in local_source_feeds:
                if feed not in feed_urls:
                    feed_urls.append(feed)
        social_feeds = self._get_social_feeds()
        if social_feeds:
            for feed in social_feeds:
                if feed not in feed_urls:
                    feed_urls.append(feed)
        google_news_feed = self._build_google_news_feed()
        if google_news_feed and google_news_feed not in feed_urls:
            feed_urls = feed_urls + [google_news_feed]
        self.config.rss_feeds = feed_urls
        results = await asyncio.gather(
            self.fetch_rss_items(feed_urls),
            self.fetch_news_api_items(),
            self.fetch_google_cse_items(),
            self.fetch_bing_items(),
            self.fetch_x_items(),
        )
        combined = []
        for group in results:
            combined.extend(group)
        seen = set()
        unique_items = []
        for item in combined:
            if item.url in seen:
                continue
            if not self._matches_location(item):
                continue
            seen.add(item.url)
            unique_items.append(item)
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
        for item in items:
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
