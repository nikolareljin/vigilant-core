"""Curated sources and RSS discovery helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup


@dataclass(frozen=True)
class Source:
    name: str
    url: str


DEFAULT_SOURCES: List[Source] = [
    Source("BBC News", "https://www.bbc.com/news"),
    Source("The Guardian", "https://www.theguardian.com"),
    Source("Al Jazeera", "https://www.aljazeera.com"),
    Source("DW", "https://www.dw.com"),
    Source("France 24", "https://www.france24.com"),
    Source("NHK World", "https://www3.nhk.or.jp/nhkworld/"),
    Source("ABC News (AU)", "https://www.abc.net.au/news"),
    Source("CBC", "https://www.cbc.ca/news"),
    Source("CNN", "https://www.cnn.com"),
    Source("NBC News", "https://www.nbcnews.com"),
    Source("CBS News", "https://www.cbsnews.com"),
    Source("ABC News (US)", "https://abcnews.go.com"),
    Source("Fox News", "https://www.foxnews.com"),
    Source("USA Today", "https://www.usatoday.com"),
    Source("NPR", "https://www.npr.org/sections/news/"),
    Source("Axios", "https://www.axios.com"),
    Source("Politico", "https://www.politico.com"),
    Source("The Washington Post", "https://www.washingtonpost.com"),
    Source("Financial Times", "https://www.ft.com"),
    Source("Bloomberg", "https://www.bloomberg.com"),
    Source("The Economist", "https://www.economist.com"),
    Source("Reuters", "https://www.reuters.com"),
    Source("AP News", "https://apnews.com"),
    Source("Sky News", "https://news.sky.com"),
    Source("The Times of India", "https://timesofindia.indiatimes.com"),
    Source("The Hindu", "https://www.thehindu.com"),
    Source("Japan Times", "https://www.japantimes.co.jp"),
    Source("Sydney Morning Herald", "https://www.smh.com.au"),
    Source("The Globe and Mail", "https://www.theglobeandmail.com"),
    Source("The Straits Times", "https://www.straitstimes.com"),
]


def _same_domain(base: str, candidate: str) -> bool:
    try:
        return urlparse(base).netloc == urlparse(candidate).netloc
    except Exception:
        return False


def _looks_like_feed(url: str) -> bool:
    lowered = url.lower()
    return any(token in lowered for token in ("rss", "atom", "feed", "/feeds"))


def _normalize(url: str) -> str:
    return url.split("#", 1)[0]


def discover_feed_links(base_url: str, client: httpx.Client) -> List[str]:
    try:
        resp = client.get(base_url, timeout=8.0)
        resp.raise_for_status()
    except Exception:
        return []
    soup = BeautifulSoup(resp.text, "html.parser")
    feeds: List[str] = []
    for link in soup.find_all("link"):
        rel = " ".join(link.get("rel", [])).lower()
        link_type = (link.get("type") or "").lower()
        href = link.get("href")
        if not href:
            continue
        if "alternate" in rel and ("rss" in link_type or "atom" in link_type or "xml" in link_type):
            feeds.append(urljoin(base_url, href))
    for anchor in soup.find_all("a"):
        href = anchor.get("href")
        if not href:
            continue
        if _looks_like_feed(href):
            feeds.append(urljoin(base_url, href))
    return list(dict.fromkeys(_normalize(feed) for feed in feeds))


def discover_section_links(base_url: str, client: httpx.Client) -> List[str]:
    try:
        resp = client.get(base_url, timeout=8.0)
        resp.raise_for_status()
    except Exception:
        return []
    soup = BeautifulSoup(resp.text, "html.parser")
    links: List[str] = []
    keywords = {"world", "news", "us", "local", "weather", "alerts", "breaking", "politics"}
    for anchor in soup.find_all("a"):
        href = anchor.get("href")
        if not href:
            continue
        url = urljoin(base_url, href)
        if not _same_domain(base_url, url):
            continue
        path = urlparse(url).path.lower()
        if any(word in path for word in keywords):
            links.append(_normalize(url))
    return list(dict.fromkeys(links))


def _validate_feed(url: str, client: httpx.Client) -> bool:
    try:
        resp = client.get(url, timeout=8.0)
        resp.raise_for_status()
        text = resp.text.lower()
        return "<rss" in text or "<feed" in text
    except Exception:
        return False


def build_default_feeds(max_feeds: int = 60) -> List[str]:
    feeds: List[str] = []
    with httpx.Client(follow_redirects=True, timeout=8.0) as client:
        for source in DEFAULT_SOURCES:
            if len(feeds) >= max_feeds:
                break
            found = discover_feed_links(source.url, client)
            for feed in found:
                if feed not in feeds and _validate_feed(feed, client):
                    feeds.append(feed)
                    if len(feeds) >= max_feeds:
                        break
            if len(feeds) >= max_feeds:
                break
            for section in discover_section_links(source.url, client)[:5]:
                if len(feeds) >= max_feeds:
                    break
                for candidate in (f"{section}/rss", f"{section}/feed", f"{section}/rss.xml"):
                    if candidate in feeds:
                        continue
                    if _validate_feed(candidate, client):
                        feeds.append(candidate)
                        if len(feeds) >= max_feeds:
                            break
    return feeds


def ensure_seed_feeds(existing: List[str]) -> List[str]:
    if existing:
        return existing
    feeds = build_default_feeds()
    if feeds:
        return feeds
    return [
        "http://feeds.bbci.co.uk/news/rss.xml",
        "http://rss.cnn.com/rss/cnn_topstories.rss",
        "https://feeds.skynews.com/feeds/rss/home.xml",
    ]
