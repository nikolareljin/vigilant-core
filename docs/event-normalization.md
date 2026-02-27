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
- Severity is derived from the existing impact score bands.
- Confidence is estimated from source type + impact + relevance and clamped to `[0.0, 1.0]`.
- Normalized event fields are persisted in SQLite and returned from `/api/alerts`.
