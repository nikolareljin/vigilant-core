"""Provenance trust tiers for the EmergencyEvent contract.

Trust is the trust boundary the AI/RAG pipeline (issue #70) and the routing
engine both consult: higher-trust events may be acted on automatically and are
preferred when channels are contended, while lower-trust content (open web
search, unauthenticated mesh) must be treated as untrusted input and never be
allowed to inject instructions into LLM prompts.

The tiers are ordered; ``rank()`` gives a comparable integer (higher = more
trusted) so callers can threshold or sort without hard-coding the strings.
"""

from __future__ import annotations

# Ordered from least to most trusted.
TRUST_TIERS: tuple[str, ...] = (
    "untrusted",          # unsolicited / unauthenticated mesh or user-pasted content
    "open_search",        # open web search results (DuckDuckGo, CSE, Bing)
    "known_feed",         # curated RSS / agency feeds
    "authenticated_api",  # keyed API (NewsAPI) or authenticated MQTT peer
    "signed_node",        # cryptographically signed event from a known node (Phase 4)
)

# Map each existing source_kind to its default trust tier. New transports register
# their own tier explicitly when they emit events.
SOURCE_KIND_TRUST: dict[str, str] = {
    "rss": "known_feed",
    "emergency_search": "known_feed",
    "news_api": "authenticated_api",
    "google_cse": "open_search",
    "bing_search": "open_search",
    "duckduckgo": "open_search",
}

DEFAULT_TRUST = "open_search"


def rank(tier: str | None) -> int:
    """Return a comparable rank for a trust tier (higher = more trusted)."""

    try:
        return TRUST_TIERS.index((tier or "").strip().lower())
    except ValueError:
        return TRUST_TIERS.index(DEFAULT_TRUST)


def for_source_kind(source_kind: str | None) -> str:
    """Best-effort trust tier for a legacy ``source_kind`` string."""

    return SOURCE_KIND_TRUST.get((source_kind or "").strip().lower(), DEFAULT_TRUST)


def is_trusted_for_automation(tier: str | None, *, minimum: str = "known_feed") -> bool:
    """Whether an event at ``tier`` is trusted enough to drive automated actions."""

    return rank(tier) >= rank(minimum)
