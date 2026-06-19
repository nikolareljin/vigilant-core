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
    "news_api": "authenticated_api",
    "google_cse": "open_search",
    "bing_search": "open_search",
    "duckduckgo": "open_search",
    # The ingest pipeline tags *every* feed item — discovered local feeds, Google
    # News RSS, Reddit RSS, as well as genuine agency feeds — with source_kind
    # "rss"/"emergency_search". Since the bucket is mostly uncurated, both map to
    # open_search so arbitrary feed/web content cannot cross the automation /
    # prompt-injection trust boundary (issue #70). A dedicated higher-trust
    # source kind for curated agency feeds (e.g. NWS CAP) can be added later.
    "rss": "open_search",
    "emergency_search": "open_search",
}

DEFAULT_TRUST = "open_search"

# The highest trust a payload may *self-declare* over an unauthenticated
# transport. Tiers above this (known_feed and up — the automation-eligible band)
# require verification the receiver does not yet have (authenticated transport or
# a valid signature, Phase 4), so unverified inbound events are clamped here to
# stop a peer from self-promoting across the automation boundary.
UNVERIFIED_CEILING = "open_search"


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


def cap_unverified(tier: str | None) -> str:
    """Clamp a self-declared trust tier to :data:`UNVERIFIED_CEILING`.

    Applied to events decoded from an unauthenticated transport so a sender
    cannot self-declare ``authenticated_api``/``signed_node`` and have the
    receiver act on it. Phase 4 signature verification will re-establish higher
    trust for events that actually prove it.
    """

    if not isinstance(tier, str):
        # Non-string (e.g. a JSON number/array): a ValueError here keeps both the
        # strict-decode guarantee and this helper's str return type intact.
        raise ValueError(f"trust must be a string, got {type(tier).__name__}")
    normalized = tier.strip().lower()
    if rank(normalized) > rank(UNVERIFIED_CEILING):
        return UNVERIFIED_CEILING
    return normalized if normalized in TRUST_TIERS else DEFAULT_TRUST
