"""Relevance-aware reasoning context selection for VigilantCore.

The insight pipeline historically dumped every recent alert into the LLM prompt.
That pollutes reasoning in three ways:

1. **Stale content** — alerts from a *past* event (e.g. last winter's storm) linger
   in the local cache and keep getting injected on later runs.
2. **Off-topic bias** — data for a different event type leaks into the answer
   (e.g. expected snowfall inches surfacing during a *summer* storm question).
3. **Lost causal history** — naively dropping all old data also discards records
   that remain *structurally* relevant (e.g. a power-grid failure during a snow
   storm is informative when reasoning about grid risk in a summer storm).

This module selects context deterministically and offline (no extra deps) by
splitting candidate alerts into two clearly-labeled tiers:

* **CURRENT** — fresh (within a window) *and* topically relevant to the question.
* **HISTORICAL** — old, but sharing an *infrastructure* aspect with the question,
  retained as background about persistent structural risk (never current fact).

Nothing is deleted from storage; irrelevant records are simply not injected.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable, Optional

# Shared tokenizer/similarity primitives, so the notion of "a meaningful token"
# stays consistent across deduplication and context selection.
from .text_similarity import jaccard as _jaccard, tokenize as _tokenize

__all__ = [
    "ContextSelection",
    "ScoredAlert",
    "ASPECT_KEYWORDS",
    "INFRASTRUCTURE_ASPECTS",
    "extract_aspects",
    "relevance_score",
    "select_context",
    "build_context_text",
]


# ---------------------------------------------------------------------------
# Aspect taxonomy
# ---------------------------------------------------------------------------
# Aspects describe *what an alert is about*. Event-type aspects (storm, snow_ice,
# heat, wind) discriminate topic/season; infrastructure aspects describe systems
# that can fail across many event types and are therefore causally reusable.

ASPECT_KEYWORDS: dict[str, frozenset[str]] = {
    "power_grid": frozenset(
        {
            "power",
            "grid",
            "electric",
            "electrical",
            "electricity",
            "outage",
            "outages",
            "blackout",
            "blackouts",
            "substation",
            "transformer",
            "utility",
            "utilities",
            "voltage",
            "powerline",
            "powerlines",
        }
    ),
    "flooding": frozenset(
        {
            "flood",
            "flooding",
            "floods",
            "flash",
            "inundation",
            "overflow",
            "surge",
            "levee",
            "levees",
            "dam",
            "waterlogged",
        }
    ),
    "transport": frozenset(
        {
            "road",
            "roads",
            "traffic",
            "highway",
            "highways",
            "transit",
            "rail",
            "railway",
            "flight",
            "flights",
            "airport",
            "bridge",
            "bridges",
            "closure",
            "closures",
            "detour",
        }
    ),
    "structural": frozenset(
        {
            "building",
            "buildings",
            "collapse",
            "collapsed",
            "roof",
            "roofs",
            "infrastructure",
            "structural",
            "damage",
            "debris",
        }
    ),
    "communications": frozenset(
        {
            "cell",
            "cellular",
            "network",
            "internet",
            "communication",
            "communications",
            "signal",
            "phone",
            "telecom",
            "broadband",
        }
    ),
    "water": frozenset(
        {
            "water",
            "sewage",
            "sewer",
            "sanitation",
            "supply",
            "contamination",
            "drinking",
            "boil",
        }
    ),
    # Event-type aspects (not infrastructure) — used for topical/seasonal matching.
    "storm": frozenset(
        {
            "storm",
            "storms",
            "thunderstorm",
            "thunder",
            "lightning",
            "hail",
            "squall",
            "severe",
        }
    ),
    "wind": frozenset(
        {
            "wind",
            "winds",
            "gust",
            "gusts",
            "gale",
            "tornado",
            "hurricane",
            "cyclone",
            "downburst",
            "typhoon",
        }
    ),
    "heat": frozenset(
        {
            "heat",
            "heatwave",
            "hot",
            "temperature",
            "drought",
            "wildfire",
            "wildfires",
            "fire",
            "summer",
        }
    ),
    "snow_ice": frozenset(
        {
            "snow",
            "snowfall",
            "snowstorm",
            "ice",
            "icy",
            "blizzard",
            "freeze",
            "freezing",
            "frost",
            "sleet",
            "winter",
            "wintry",
            "inches",
        }
    ),
}

# Aspects that describe systems which can fail across event types. Sharing one of
# these between a past event and the current question is what makes old records
# *structurally* relevant rather than just stale noise.
INFRASTRUCTURE_ASPECTS: frozenset[str] = frozenset(
    {"power_grid", "flooding", "transport", "structural", "communications", "water"}
)


def _aspects_from_tokens(tokens: set[str]) -> set[str]:
    """Map an already-computed token set to its aspect labels."""
    if not tokens:
        return set()
    return {
        aspect for aspect, keywords in ASPECT_KEYWORDS.items() if tokens & keywords
    }


def extract_aspects(text: str) -> set[str]:
    """Return the set of aspect labels whose keywords appear in ``text``."""
    return _aspects_from_tokens(_tokenize(text))


# ---------------------------------------------------------------------------
# Alert access helpers (work for sqlite3.Row and plain dict/mapping)
# ---------------------------------------------------------------------------

def _get(alert: Any, key: str, default: Any = None) -> Any:
    try:
        value = alert[key]
    except (KeyError, IndexError, TypeError):
        return default
    return default if value is None else value


def _alert_text(alert: Any) -> str:
    parts = [
        str(_get(alert, "title", "")),
        str(_get(alert, "snippet", "")),
        str(_get(alert, "predictive_outcome", "")),
    ]
    return " ".join(p for p in parts if p)


def _parse_dt(value: Any) -> Optional[datetime]:
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    # SQLite CURRENT_TIMESTAMP uses "YYYY-MM-DD HH:MM:SS" (UTC, no tz marker).
    candidate = text.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(candidate)
    except ValueError:
        try:
            dt = datetime.strptime(text, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _alert_time(alert: Any) -> Optional[datetime]:
    # Prefer the real-world event time; fall back to the row's ingestion time.
    return _parse_dt(_get(alert, "event_timestamp_utc")) or _parse_dt(
        _get(alert, "created_at")
    )


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def relevance_score(
    question_tokens: set[str],
    question_aspects: set[str],
    alert: Any,
) -> float:
    """Topical relevance of ``alert`` to the question, in ``[0.0, 1.0]``.

    Combines how much of the question's vocabulary the alert covers with how
    much its aspect profile overlaps the question's. Coverage is weighted higher
    than raw Jaccard so a short, on-point question is not penalised for brevity.
    """
    alert_tokens = _tokenize(_alert_text(alert))
    return _relevance_from_parts(
        question_tokens, question_aspects, alert_tokens, _aspects_from_tokens(alert_tokens)
    )


def _relevance_from_parts(
    question_tokens: set[str],
    question_aspects: set[str],
    alert_tokens: set[str],
    alert_aspects: set[str],
) -> float:
    """Relevance score from pre-computed token/aspect sets (no re-tokenizing)."""
    if not alert_tokens:
        return 0.0
    if question_tokens:
        coverage = len(question_tokens & alert_tokens) / len(question_tokens)
    else:
        coverage = 0.0
    token_jaccard = _jaccard(question_tokens, alert_tokens)
    aspect_jaccard = _jaccard(question_aspects, alert_aspects) if question_aspects else 0.0
    return 0.5 * coverage + 0.2 * token_jaccard + 0.3 * aspect_jaccard


@dataclass
class ScoredAlert:
    """An alert paired with the signals used to place it in a context tier."""

    alert: Any
    relevance: float
    age_hours: Optional[float]
    aspects: set[str] = field(default_factory=set)

    @property
    def impact(self) -> int:
        try:
            return int(_get(self.alert, "impact_score", 0) or 0)
        except (TypeError, ValueError):
            return 0


def _recency_key(scored: "ScoredAlert") -> float:
    """Sort value for recency (higher = more recent), clamping future ages.

    A future-dated alert (negative age) is clamped to "now" so that a skewed or
    scheduled timestamp far in the future cannot sort ahead of genuine
    present-time alerts.
    """
    if scored.age_hours is None:
        return 0.0
    return -max(0.0, scored.age_hours)


@dataclass
class ContextSelection:
    """Result of splitting candidate alerts into reasoning tiers."""

    current: list[ScoredAlert] = field(default_factory=list)
    historical: list[ScoredAlert] = field(default_factory=list)
    dropped: int = 0
    sources_used: set[str] = field(default_factory=set)

    @property
    def is_empty(self) -> bool:
        return not self.current and not self.historical


# ---------------------------------------------------------------------------
# Selection
# ---------------------------------------------------------------------------

def select_context(
    alerts: Iterable[Any],
    *,
    question: str,
    subject: str = "",
    now: Optional[datetime] = None,
    fresh_window_hours: float = 24.0,
    min_relevance: float = 0.12,
    max_current: int = 20,
    max_historical: int = 6,
    enable_historical: bool = True,
) -> ContextSelection:
    """Split ``alerts`` into CURRENT and HISTORICAL reasoning tiers.

    * CURRENT  — fresh AND relevance >= ``min_relevance`` to
      ``question``/``subject``. Freshness is a +/- window around ``now``: an age
      within ``[-fresh_window_hours, fresh_window_hours]`` counts as fresh, so a
      small amount of future skew (scheduled posts, feed clock drift) is allowed
      while wildly future-dated timestamps are not. Alerts with an unparseable
      timestamp are treated as fresh.
    * HISTORICAL — genuinely past alerts older than the window that share an
      infrastructure aspect with the question (structurally relevant), capped
      and ranked by impact.

    Alerts that are neither fresh-and-relevant nor structurally relevant (and
    far-future timestamps) are dropped (counted, never deleted from storage).
    """
    if now is None:
        now = datetime.now(timezone.utc)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    # Defensive normalization: these knobs can come straight from a user-edited
    # config.json, so clamp them to sane ranges before use.
    fresh_window_hours = max(0.0, float(fresh_window_hours))
    min_relevance = min(1.0, max(0.0, float(min_relevance)))
    max_current = max(0, int(max_current))
    max_historical = max(0, int(max_historical))

    question_text = f"{question or ''} {subject or ''}".strip()
    q_tokens = _tokenize(question_text)
    q_aspects = extract_aspects(question_text)
    q_infra = q_aspects & INFRASTRUCTURE_ASPECTS
    # With no usable question signal (empty/very short/all-stopword input) every
    # alert scores 0, which would wrongly empty the CURRENT tier. Fall back to
    # recency: include all fresh alerts so the user still sees what's happening.
    has_question_signal = bool(q_tokens or q_aspects)

    current: list[ScoredAlert] = []
    historical: list[ScoredAlert] = []
    dropped = 0

    for alert in alerts:
        dt = _alert_time(alert)
        age_hours = (now - dt).total_seconds() / 3600.0 if dt is not None else None
        # Tokenize once per alert and reuse for both relevance and aspects.
        alert_tokens = _tokenize(_alert_text(alert))
        aspects = _aspects_from_tokens(alert_tokens)
        relevance = _relevance_from_parts(q_tokens, q_aspects, alert_tokens, aspects)
        scored = ScoredAlert(
            alert=alert, relevance=relevance, age_hours=age_hours, aspects=aspects
        )

        # Freshness is a +/- window around "now". A little future skew (scheduled
        # posts, feed clock drift) still counts as current, but a wildly
        # future-dated timestamp is anomalous: it is neither fresh nor eligible
        # as past historical background, so it is dropped rather than allowed to
        # dominate the CURRENT tier. Unparseable timestamps are treated as fresh.
        if age_hours is None:
            is_fresh, is_past = True, False
        else:
            is_fresh = -fresh_window_hours <= age_hours <= fresh_window_hours
            is_past = age_hours > 0.0

        if is_fresh and (not has_question_signal or relevance >= min_relevance):
            current.append(scored)
            continue

        # Genuinely older past alerts: keep only if structurally relevant.
        structurally_relevant = bool(q_infra and (aspects & q_infra))
        if enable_historical and is_past and not is_fresh and structurally_relevant:
            historical.append(scored)
        else:
            dropped += 1

    # CURRENT: most relevant first, then impact, then most recent. Future-dated
    # ages are clamped to "now" so they cannot sort ahead of present alerts.
    current.sort(
        key=lambda s: (s.relevance, s.impact, _recency_key(s)),
        reverse=True,
    )
    # HISTORICAL: highest impact first, then most relevant, then most recent.
    historical.sort(
        key=lambda s: (s.impact, s.relevance, _recency_key(s)),
        reverse=True,
    )

    dropped += max(0, len(current) - max_current)
    dropped += max(0, len(historical) - max_historical)
    current = current[:max_current]
    historical = historical[:max_historical]

    # Use the same sanitized/capped source label as the rendered line so
    # sources_used never disagrees with what actually appears in the prompt.
    sources_used: set[str] = {_clean_source(s.alert) for s in (*current, *historical)}

    return ContextSelection(
        current=current,
        historical=historical,
        dropped=dropped,
        sources_used=sources_used,
    )


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

_WHITESPACE_RE = re.compile(r"\s+")


def _sanitize_field(value: Any) -> str:
    """Collapse a feed field to safe single-line text for the prompt.

    Upstream feeds can carry newlines and non-printable characters (ASCII
    controls, DEL, and Unicode format/control characters such as zero-width or
    bidirectional marks); left intact they break the bullet structure and let
    injected text masquerade as separate prompt lines/instructions. Replace any
    non-printable character (everything except a regular space) with a space and
    collapse whitespace so each item stays on one clean line.
    """
    raw = "" if value is None else str(value)
    text = "".join(ch if ch.isprintable() else " " for ch in raw)
    return _WHITESPACE_RE.sub(" ", text).strip()


# Per-field caps keep a single feed item from ballooning the prompt (latency,
# cost, context-window pressure) if an upstream source returns very long text.
_MAX_SOURCE = 80
_MAX_TITLE = 200
_MAX_SNIPPET = 200
_MAX_PREDICTION = 200


def _clean_source(alert: Any) -> str:
    """Sanitized, capped source label with an "Unknown" fallback.

    Used for both the rendered alert line and ``sources_used`` so the two never
    disagree (no unclean or over-long source leaking into the API/UI).
    """
    return _sanitize_field(_get(alert, "source", "Unknown"))[:_MAX_SOURCE] or "Unknown"


def _format_alert_line(scored: ScoredAlert, *, with_date: bool = False) -> str:
    alert = scored.alert
    source = _clean_source(alert)
    title = _sanitize_field(_get(alert, "title", ""))[:_MAX_TITLE]
    snippet = _sanitize_field(_get(alert, "snippet", ""))[:_MAX_SNIPPET]
    # Use the normalized impact (same value used for ranking; always an int).
    score = scored.impact
    prediction = _sanitize_field(_get(alert, "predictive_outcome", ""))[:_MAX_PREDICTION]

    prefix = ""
    if with_date:
        dt = _alert_time(alert)
        if dt is not None:
            prefix = f"({dt.date().isoformat()}) "

    # Join only the non-empty pieces so a missing title or snippet never leaves
    # a ". " artifact in the text that gets fed straight into the LLM prompt.
    body = ". ".join(part for part in (title, snippet) if part)
    line = f"- {prefix}[{source}] (impact: {score}/10)"
    if body:
        line += f" {body}"
    if prediction:
        line += f" Prediction: {prediction}"
    return line


def build_context_text(selection: ContextSelection) -> str:
    """Render a selection into the two labeled sections used in the prompt."""
    sections: list[str] = []

    sections.append("CURRENT & RELEVANT ALERTS (fresh, on-topic):")
    if selection.current:
        sections.extend(_format_alert_line(s) for s in selection.current)
    else:
        sections.append("- (no fresh, on-topic alerts for this question)")

    # Always emit the HISTORICAL section (with a placeholder when empty) so the
    # two-group structure promised by the system prompt stays consistent.
    sections.append("")
    sections.append(
        "HISTORICAL CONTEXT — past events that may be STRUCTURALLY relevant "
        "(NOT current conditions; do not treat any forecast or figure here as "
        "present-day fact):"
    )
    if selection.historical:
        sections.extend(
            _format_alert_line(s, with_date=True) for s in selection.historical
        )
    else:
        sections.append("- (no structurally relevant history for this question)")

    return "\n".join(sections)
