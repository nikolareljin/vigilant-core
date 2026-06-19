"""Shared lightweight text-similarity primitives.

Public helpers used by both the event-deduplication engine and the
relevance-aware context selector, so neither module has to reach into the
other's private internals. Keeping these in one place also guarantees both use
the same notion of a "meaningful token".
"""

from __future__ import annotations

import re

__all__ = ["tokenize", "jaccard"]

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


def tokenize(text: str) -> set[str]:
    """Lowercase word tokens of length >= 3 with common stopwords removed."""
    return {
        token
        for token in _WORD_RE.findall((text or "").lower())
        if len(token) >= 3 and token not in _STOPWORDS
    }


def jaccard(left: set[str], right: set[str]) -> float:
    """Jaccard similarity of two token sets (1.0 when both are empty)."""
    if not left and not right:
        return 1.0
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)
