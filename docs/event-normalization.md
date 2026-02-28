# Event Normalization Layer

VigilantCore now normalizes every ingested alert into a unified event schema before persistence and API output.

## Schema (v1.0)

Each event includes:

- `severity`: `low | medium | high | critical`
- `confidence`: normalized confidence score (`0.0` to `1.0`)
- `timestamp_utc`: normalized ISO-8601 UTC timestamp
- `location`:
  - `name`
  - `zip_code`
  - `latitude`
  - `longitude`

## Notes

- Timestamp normalization supports both ISO timestamps and RFC822 feed timestamps.
- Severity is derived from impact score bands: `1-3` -> `low`, `4-6` -> `medium`, `7-8` -> `high`, `9-10` -> `critical`.
- Invalid/non-numeric impact inputs are normalized to `1` before clamping to `1..10`.
- Confidence is estimated from source type + impact + relevance and clamped to `[0.0, 1.0]`.
- Missing location text fields are normalized to empty strings, while missing coordinates remain `null`.
- Normalized event fields are persisted in SQLite and returned from `/api/alerts`.
- Ingestion now runs event deduplication before normalization so overlapping source reports become one canonical normalized event.
