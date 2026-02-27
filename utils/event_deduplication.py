"""Event deduplication helpers for merged multi-source alerts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import re
from typing import Iterable


SOURCE_KIND_PRIORITY = {
    "news_api": 6,
    "emergency_search": 5,
    "google_cse": 4,
    "bing_search": 3,
    "rss": 2,
    "duckduckgo": 1,
    "unknown": 0,
}

_WORD_RE = re.compile(r"[a-z0-9]+")
_STOPWORDS = {
    "a",
    "an",
    "and",
    "at",
    "by",
    "for",
    "from",
    "in",
    "into",
    "is",
    "of",
    "on",
    "or",
    "the",
    "to",
    "with",
}


@dataclass
class DeduplicatedEvent:
    url: str
    title: str
    snippet: str
    published_at: str | None
    source: str
    source_kind: str
    merged_count: int
    merged_urls: tuple[str, ...]
    merged_sources: tuple[str, ...]


def _to_utc_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except ValueError:
        pass
    try:
        dt = parsedate_to_datetime(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def _tokenize(text: str) -> set[str]:
    return {
        token
        for token in _WORD_RE.findall((text or "").lower())
        if len(token) >= 3 and token not in _STOPWORDS
    }


def _title_fingerprint(title: str) -> str:
    tokens = sorted(_tokenize(title))
    if not tokens:
        return ""
    return "|".join(tokens[:8])


def _jaccard(left: set[str], right: set[str]) -> float:
    if not left and not right:
        return 1.0
    if not left or not right:
        return 0.0
    overlap = left & right
    union = left | right
    return len(overlap) / len(union)


def _is_overlap(
    incoming: "_AggregateEvent",
    current: "_AggregateEvent",
    overlap_window_hours: int,
) -> bool:
    if incoming.title_fingerprint and incoming.title_fingerprint == current.title_fingerprint:
        return True

    title_similarity = _jaccard(incoming.title_tokens, current.title_tokens)
    body_similarity = _jaccard(incoming.body_tokens, current.body_tokens)
    shared_title_tokens = len(incoming.title_tokens & current.title_tokens)

    within_window = False
    if incoming.timestamp and current.timestamp:
        diff_seconds = abs((incoming.timestamp - current.timestamp).total_seconds())
        within_window = diff_seconds <= overlap_window_hours * 3600
    else:
        within_window = True

    if title_similarity >= 0.55 and shared_title_tokens >= 4 and within_window:
        return True
    if title_similarity >= 0.78 and shared_title_tokens >= 3 and within_window:
        return True
    if body_similarity >= 0.86 and shared_title_tokens >= 2 and within_window:
        return True
    return False


@dataclass
class _AggregateEvent:
    url: str
    title: str
    snippet: str
    source_kind: str
    timestamp: datetime | None
    title_tokens: set[str]
    body_tokens: set[str]
    title_fingerprint: str
    merged_urls: list[str]
    merged_sources: list[str]
    merged_snippets: list[str]
    merged_count: int

    @classmethod
    def from_raw(
        cls,
        *,
        url: str,
        title: str,
        snippet: str,
        source: str,
        source_kind: str,
        published_at: str | None,
    ) -> "_AggregateEvent":
        raw_title = (title or "").strip()
        normalized_title = raw_title or "(no title)"
        normalized_snippet = snippet or ""
        body_text = f"{raw_title} {normalized_snippet}".strip()
        return cls(
            url=url,
            title=normalized_title,
            snippet=normalized_snippet,
            source_kind=source_kind or "unknown",
            timestamp=_to_utc_datetime(published_at),
            title_tokens=_tokenize(raw_title),
            body_tokens=_tokenize(body_text),
            title_fingerprint=_title_fingerprint(raw_title),
            merged_urls=[url],
            merged_sources=[source or "Unknown"],
            merged_snippets=[normalized_snippet] if normalized_snippet else [],
            merged_count=1,
        )

    def merge(self, incoming: "_AggregateEvent") -> None:
        self.merged_count += 1

        if incoming.url and incoming.url not in self.merged_urls:
            self.merged_urls.append(incoming.url)
        for source in incoming.merged_sources:
            if source and source not in self.merged_sources:
                self.merged_sources.append(source)
        if incoming.snippet and incoming.snippet not in self.merged_snippets:
            self.merged_snippets.append(incoming.snippet)

        if incoming.timestamp and (self.timestamp is None or incoming.timestamp < self.timestamp):
            self.timestamp = incoming.timestamp
            self.url = incoming.url

        current_priority = SOURCE_KIND_PRIORITY.get(self.source_kind, 0)
        incoming_priority = SOURCE_KIND_PRIORITY.get(incoming.source_kind, 0)
        if incoming_priority > current_priority:
            self.source_kind = incoming.source_kind

        if len(incoming.title_tokens) > len(self.title_tokens):
            self.title = incoming.title
            self.title_tokens = incoming.title_tokens
            self.title_fingerprint = incoming.title_fingerprint

        merged_body = f"{self.title} {' '.join(self.merged_snippets)}".strip()
        self.body_tokens = _tokenize(merged_body)
        self.snippet = " | ".join(self.merged_snippets[:2])

    def to_event(self) -> DeduplicatedEvent:
        published_at = self.timestamp.isoformat().replace("+00:00", "Z") if self.timestamp else None
        merged_sources = tuple(sorted(self.merged_sources))
        return DeduplicatedEvent(
            url=self.url,
            title=self.title,
            snippet=self.snippet,
            published_at=published_at,
            source=" | ".join(merged_sources),
            source_kind=self.source_kind,
            merged_count=self.merged_count,
            merged_urls=tuple(self.merged_urls),
            merged_sources=merged_sources,
        )


def deduplicate_events(
    items: Iterable[dict[str, str | None]],
    *,
    overlap_window_hours: int = 6,
) -> list[DeduplicatedEvent]:
    """Merge duplicate or overlapping alerts from multiple sources."""

    aggregates: list[_AggregateEvent] = []
    fingerprint_index: dict[str, list[_AggregateEvent]] = {}
    token_index: dict[str, list[_AggregateEvent]] = {}

    def _index_aggregate(entry: _AggregateEvent) -> None:
        if entry.title_fingerprint:
            fingerprint_index.setdefault(entry.title_fingerprint, []).append(entry)
        index_tokens = sorted(entry.title_tokens)[:8]
        if not index_tokens:
            index_tokens = sorted(entry.body_tokens)[:8]
        for token in index_tokens:
            token_index.setdefault(token, []).append(entry)

    for item in items:
        url = str(item.get("url") or "").strip()
        if not url:
            continue
        candidate = _AggregateEvent.from_raw(
            url=url,
            title=str(item.get("title") or ""),
            snippet=str(item.get("snippet") or ""),
            source=str(item.get("source") or "Unknown"),
            source_kind=str(item.get("source_kind") or "unknown"),
            published_at=item.get("published_at"),
        )
        candidate_pool: dict[int, _AggregateEvent] = {}
        if candidate.title_fingerprint:
            for aggregate in fingerprint_index.get(candidate.title_fingerprint, []):
                candidate_pool[id(aggregate)] = aggregate
        lookup_tokens = sorted(candidate.title_tokens)[:8]
        if not lookup_tokens:
            lookup_tokens = sorted(candidate.body_tokens)[:8]
        for token in lookup_tokens:
            for aggregate in token_index.get(token, []):
                candidate_pool[id(aggregate)] = aggregate
        merged = False
        for current in candidate_pool.values():
            if _is_overlap(candidate, current, overlap_window_hours):
                current.merge(candidate)
                _index_aggregate(current)
                merged = True
                break
        if not merged:
            aggregates.append(candidate)
            _index_aggregate(candidate)
    return [entry.to_event() for entry in aggregates]
