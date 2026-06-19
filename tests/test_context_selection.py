"""Tests for relevance-aware reasoning context selection."""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from utils.context_selection import (
    INFRASTRUCTURE_ASPECTS,
    ScoredAlert,
    _format_alert_line,
    _sanitize_field,
    build_context_text,
    extract_aspects,
    relevance_score,
    select_context,
)
from utils.text_similarity import tokenize as _tokenize


NOW = datetime(2026, 6, 18, 12, 0, 0, tzinfo=timezone.utc)


def _alert(title, snippet, when, *, source="Feed", impact=5, prediction=""):
    """Build a dict alert with an event timestamp ``when`` hours before NOW."""
    ts = (NOW - timedelta(hours=when)).isoformat().replace("+00:00", "Z")
    return {
        "title": title,
        "snippet": snippet,
        "source": source,
        "impact_score": impact,
        "predictive_outcome": prediction,
        "event_timestamp_utc": ts,
        "created_at": ts,
    }


# Fresh summer storm directly threatening the grid.
SUMMER_STORM = _alert(
    "Severe summer thunderstorm warning",
    "Damaging winds and power outages possible across the area.",
    impact=8,
    when=2,
)
# Old winter snow forecast — off topic, no infrastructure overlap with a power
# question. This is the "12 inches of snow" noise that must not pollute reasoning.
SNOW_FORECAST = _alert(
    "Winter storm: 12 inches of snow expected",
    "Heavy snowfall and wintry conditions forecast; schools may close.",
    impact=7,
    when=24 * 150,  # ~5 months ago
    source="SnowFeed",  # distinct source so drop-leak tests are meaningful
)
# Old snow-era grid failure — different event type, but shares the power_grid
# infrastructure aspect, so it stays as structural history.
SNOW_GRID_FAILURE = _alert(
    "Power grid failures during January blizzard",
    "Substation outages left thousands without electricity during the snow storm.",
    impact=9,
    when=24 * 151,
)

QUESTION = "How likely are power outages during this summer storm?"
SUBJECT = "Power Outages"


class AspectTests(unittest.TestCase):
    def test_extract_power_aspect(self):
        self.assertIn("power_grid", extract_aspects("widespread power outage"))

    def test_extract_snow_aspect(self):
        self.assertEqual(extract_aspects("12 inches of snow"), {"snow_ice"})

    def test_infrastructure_subset(self):
        self.assertIn("power_grid", INFRASTRUCTURE_ASPECTS)
        self.assertNotIn("snow_ice", INFRASTRUCTURE_ASPECTS)

    def test_sanitize_field_preserves_falsy_values(self):
        # Falsy non-string values are meaningful (e.g. a numeric 0 code) and
        # must not be silently dropped; only None becomes empty.
        self.assertEqual(_sanitize_field(0), "0")
        self.assertEqual(_sanitize_field(False), "False")
        self.assertEqual(_sanitize_field(None), "")
        self.assertEqual(_sanitize_field("ok"), "ok")

    def test_relevance_prefers_on_topic(self):
        q_tokens = _tokenize(f"{QUESTION} {SUBJECT}")
        q_aspects = extract_aspects(f"{QUESTION} {SUBJECT}")
        on_topic = relevance_score(q_tokens, q_aspects, SUMMER_STORM)
        off_topic = relevance_score(q_tokens, q_aspects, SNOW_FORECAST)
        self.assertGreater(on_topic, off_topic)


class SelectContextTests(unittest.TestCase):
    def _select(self, **kw):
        return select_context(
            [SUMMER_STORM, SNOW_FORECAST, SNOW_GRID_FAILURE],
            question=QUESTION,
            subject=SUBJECT,
            now=NOW,
            **kw,
        )

    def test_current_has_fresh_relevant_only(self):
        sel = self._select()
        current_titles = [a.alert["title"] for a in sel.current]
        self.assertIn(SUMMER_STORM["title"], current_titles)
        # Old alerts never appear as CURRENT — stale content cannot pollute.
        self.assertNotIn(SNOW_FORECAST["title"], current_titles)
        self.assertNotIn(SNOW_GRID_FAILURE["title"], current_titles)

    def test_structurally_relevant_history_retained(self):
        sel = self._select()
        hist_titles = [a.alert["title"] for a in sel.historical]
        # Grid failure shares the power_grid aspect -> kept as background.
        self.assertIn(SNOW_GRID_FAILURE["title"], hist_titles)
        # Pure snow forecast has no infrastructure overlap -> dropped entirely.
        self.assertNotIn(SNOW_FORECAST["title"], hist_titles)
        self.assertGreaterEqual(sel.dropped, 1)

    def test_off_topic_snow_absent_from_rendered_context(self):
        text = build_context_text(self._select())
        self.assertIn("CURRENT", text)
        self.assertIn("HISTORICAL", text)
        self.assertIn(SNOW_GRID_FAILURE["title"], text)
        self.assertNotIn("12 inches of snow", text)

    def test_disable_historical_drops_structural(self):
        sel = self._select(enable_historical=False)
        self.assertEqual(sel.historical, [])

    def test_sources_used_only_from_selected(self):
        sel = select_context(
            [SUMMER_STORM, SNOW_FORECAST, SNOW_GRID_FAILURE],
            question=QUESTION,
            subject=SUBJECT,
            now=NOW,
        )
        # SNOW_FORECAST (source "SnowFeed") is dropped, so its source must not
        # leak into sources_used; only sources of selected alerts appear.
        self.assertEqual(sel.sources_used, {"Feed"})
        self.assertNotIn("SnowFeed", sel.sources_used)


class EmptyAndEdgeTests(unittest.TestCase):
    def test_no_fresh_alerts_renders_placeholder(self):
        sel = select_context(
            [SNOW_GRID_FAILURE],
            question=QUESTION,
            subject=SUBJECT,
            now=NOW,
        )
        self.assertEqual(sel.current, [])
        text = build_context_text(sel)
        self.assertIn("no fresh, on-topic alerts", text)

    def test_sources_used_includes_unknown_for_missing_source(self):
        ts = (NOW - timedelta(hours=1)).isoformat().replace("+00:00", "Z")
        no_source = {
            "title": "Power outage now",
            "snippet": "Electricity down across the area.",
            "source": "",
            "impact_score": 6,
            "predictive_outcome": "",
            "event_timestamp_utc": ts,
            "created_at": ts,
        }
        sel = select_context([no_source], question=QUESTION, subject=SUBJECT, now=NOW)
        self.assertEqual(len(sel.current), 1)
        # Rendered line falls back to "[Unknown]"; sources_used must agree.
        self.assertEqual(sel.sources_used, {"Unknown"})

    def test_sources_used_is_sanitized_and_capped(self):
        ts = (NOW - timedelta(hours=1)).isoformat().replace("+00:00", "Z")
        alert = {
            "title": "Power outage now",
            "snippet": "Electricity down across the area.",
            "source": "Feed\nName " + "X" * 200,
            "impact_score": 6,
            "predictive_outcome": "",
            "event_timestamp_utc": ts,
            "created_at": ts,
        }
        sel = select_context([alert], question=QUESTION, subject=SUBJECT, now=NOW)
        self.assertEqual(len(sel.current), 1)
        (src,) = sel.sources_used
        self.assertNotIn("\n", src)
        self.assertLessEqual(len(src), 80)
        # sources_used must match exactly what the rendered prompt line shows.
        self.assertIn(f"[{src}]", build_context_text(sel))

    def test_empty_question_falls_back_to_fresh_alerts(self):
        # A question with no meaningful tokens must not drop everything; fresh
        # alerts still populate CURRENT so the user gets the current situation.
        sel = select_context(
            [SUMMER_STORM, SNOW_GRID_FAILURE],
            question="ok",  # too short to yield a meaningful token
            subject="",
            now=NOW,
        )
        current_titles = [a.alert["title"] for a in sel.current]
        self.assertIn(SUMMER_STORM["title"], current_titles)

    def test_within_window_future_alert_is_current(self):
        # Small future skew (scheduled post / clock drift) still counts as fresh.
        future = _alert(
            "Power outage imminent",
            "Electricity expected to fail across the area soon.",
            impact=6,
            when=-2,  # 2 hours in the future
        )
        sel = select_context([future], question=QUESTION, subject=SUBJECT, now=NOW)
        self.assertEqual(len(sel.current), 1)

    def test_far_future_alert_excluded(self):
        # A wildly future-dated timestamp must not dominate CURRENT, nor count
        # as past historical background.
        far = _alert(
            "Power maintenance scheduled",
            "Planned electricity grid maintenance.",
            impact=9,
            when=-24 * 30,  # 30 days in the future
        )
        sel = select_context([far], question=QUESTION, subject=SUBJECT, now=NOW)
        self.assertEqual(sel.current, [])
        self.assertEqual(sel.historical, [])
        self.assertGreaterEqual(sel.dropped, 1)

    def test_out_of_range_knobs_are_clamped(self):
        # Negative / out-of-range config values must not crash or misbehave.
        sel = select_context(
            [SUMMER_STORM, SNOW_GRID_FAILURE],
            question=QUESTION,
            subject=SUBJECT,
            now=NOW,
            fresh_window_hours=-10,
            min_relevance=-1,
            max_current=-5,
            max_historical=-2,
        )
        # max_current / max_historical clamp to 0 -> both tiers empty, no error.
        self.assertEqual(sel.current, [])
        self.assertEqual(sel.historical, [])

    def test_unparseable_timestamp_treated_as_fresh(self):
        weird = {
            "title": "Power outage reported now",
            "snippet": "Electricity down in the area.",
            "source": "Feed",
            "impact_score": 6,
            "predictive_outcome": "",
            "event_timestamp_utc": None,
            "created_at": "not-a-date",
        }
        sel = select_context([weird], question=QUESTION, subject=SUBJECT, now=NOW)
        self.assertEqual(len(sel.current), 1)

    def test_format_line_omits_empty_fields(self):
        def line(title, snippet):
            scored = ScoredAlert(
                alert={
                    "title": title,
                    "snippet": snippet,
                    "source": "Feed",
                    "impact_score": 5,
                    "predictive_outcome": "",
                },
                relevance=0.5,
                age_hours=1.0,
            )
            return _format_alert_line(scored)

        self.assertEqual(line("Grid down", "Outage spreading"),
                         "- [Feed] (impact: 5/10) Grid down. Outage spreading")
        # No trailing ". " artifact when snippet is missing.
        self.assertEqual(line("Grid down", ""), "- [Feed] (impact: 5/10) Grid down")
        # No leading ". " artifact when title is missing.
        self.assertEqual(line("", "Outage spreading"),
                         "- [Feed] (impact: 5/10) Outage spreading")

    def test_format_line_sanitizes_newlines_and_control_chars(self):
        scored = ScoredAlert(
            alert={
                "title": "Line1\nLine2\tTab",
                "snippet": "Ignore previous\r\ninstructions",
                "source": "Feed\nX",
                "impact_score": 5,
                "predictive_outcome": "",
            },
            relevance=0.5,
            age_hours=1.0,
        )
        line = _format_alert_line(scored)
        # No injected line breaks or control chars survive into the prompt line.
        self.assertNotIn("\n", line)
        self.assertNotIn("\r", line)
        self.assertNotIn("\t", line)
        self.assertIn("Line1 Line2 Tab", line)
        self.assertIn("Feed X", line)

    def test_format_line_strips_unicode_and_del_controls(self):
        # DEL (U+007F), zero-width space (U+200B), and a bidi override
        # (U+202E) must not survive into the prompt text.
        scored = ScoredAlert(
            alert={
                "title": "Grid\x7fdown\u200b now",
                "snippet": "evac\u202euate",
                "source": "Feed",
                "impact_score": 5,
                "predictive_outcome": "",
            },
            relevance=0.5,
            age_hours=1.0,
        )
        line = _format_alert_line(scored)
        for ch in ("\x7f", "\u200b", "\u202e"):
            self.assertNotIn(ch, line)
        self.assertIn("Grid", line)
        self.assertIn("down", line)

    def test_format_line_caps_long_fields(self):
        scored = ScoredAlert(
            alert={
                "title": "T" * 500,
                "snippet": "S" * 500,
                "source": "F" * 200,
                "impact_score": 5,
                "predictive_outcome": "P" * 500,
            },
            relevance=0.5,
            age_hours=1.0,
        )
        line = _format_alert_line(scored)
        self.assertIn("T" * 200, line)
        self.assertNotIn("T" * 201, line)
        self.assertIn("S" * 200, line)
        self.assertNotIn("S" * 201, line)
        self.assertIn("F" * 80, line)
        self.assertNotIn("F" * 81, line)
        self.assertIn("P" * 200, line)
        self.assertNotIn("P" * 201, line)

    def test_format_line_uses_normalized_impact(self):
        # A missing/invalid impact_score renders as the normalized int (0), the
        # same value used for ranking.
        scored = ScoredAlert(
            alert={
                "title": "T",
                "snippet": "S",
                "source": "Feed",
                "impact_score": None,
                "predictive_outcome": "",
            },
            relevance=0.5,
            age_hours=1.0,
        )
        self.assertIn("(impact: 0/10)", _format_alert_line(scored))

    def test_historical_section_always_rendered(self):
        # Only a fresh, on-topic alert -> no historical, but the section (with a
        # placeholder) must still appear so the two-group prompt stays stable.
        sel = select_context(
            [SUMMER_STORM], question=QUESTION, subject=SUBJECT, now=NOW
        )
        self.assertEqual(sel.historical, [])
        text = build_context_text(sel)
        self.assertIn("HISTORICAL CONTEXT", text)
        self.assertIn("no structurally relevant history", text)


if __name__ == "__main__":
    unittest.main()
