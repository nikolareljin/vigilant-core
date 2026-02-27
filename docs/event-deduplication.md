# Event Deduplication Engine

VigilantCore now merges duplicate or overlapping alerts from multiple upstream sources into a single normalized event before LLM scoring and database insert.

## Purpose

- Reduce duplicate entries when the same incident is reported by multiple feeds/search providers.
- Keep one canonical event record while preserving merged source attribution.
- Avoid repeated parsing/scoring for equivalent alerts in the same polling cycle.

## Current Behavior

- Dedup runs after URL + location filtering in `MonitorEngine.gather_items()`.
- Direct URL duplicates are removed first.
- Remaining candidates are semantically merged when they overlap by:
  - normalized title fingerprint match, or
  - high title/body token overlap within a time window (default 6 hours).
- Blank/missing titles do not produce active title fingerprints, preventing unrelated untitled events from auto-merging.
- Merged event output keeps:
  - canonical URL/title/snippet,
  - merged source list (joined with ` | `),
  - preferred source kind (highest-priority source type),
  - merged metadata (`merged_count`, `merged_urls`, `merged_sources`) for internal use.
- Canonical URL selection is deterministic and DB-aware:
  - prefers an already-stored URL from the merged URL set when available
  - otherwise uses a stable lexical URL choice for consistent re-runs
- Before parsing/insertion, monitor processing checks all merged URLs against SQLite to avoid reinserting equivalent events when canonical URL choice differs between runs.

## Source Kind Priority

When merged events have multiple source types, the retained `source_kind` uses this priority:

1. `news_api`
2. `emergency_search`
3. `google_cse`
4. `bing_search`
5. `rss`
6. `duckduckgo`
7. `unknown`

This keeps confidence estimation aligned with the strongest available source signal.
