"""SQLite storage for VigilantCore alerts."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, List, Optional, Sequence

from .config import data_dir


DB_NAME = "vigilantcore.db"
ALERT_MIGRATION_COLUMNS = {
    "severity": "TEXT",
    "confidence": "REAL",
    "event_timestamp_utc": "TEXT",
    "location_zip_code": "TEXT",
    "location_latitude": "REAL",
    "location_longitude": "REAL",
    "source_kind": "TEXT",
}


def db_path() -> Path:
    base = data_dir()
    base.mkdir(parents=True, exist_ok=True)
    return base / DB_NAME


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(db_path())
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    with connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT NOT NULL,
                url_hash TEXT NOT NULL UNIQUE,
                title TEXT NOT NULL,
                snippet TEXT,
                published_at TEXT,
                source TEXT,
                source_kind TEXT,
                severity TEXT,
                confidence REAL,
                event_timestamp_utc TEXT,
                location_zip_code TEXT,
                location_latitude REAL,
                location_longitude REAL,
                impact_score INTEGER,
                predictive_outcome TEXT,
                is_relevant INTEGER,
                subject TEXT,
                location_name TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_alerts_created_at ON alerts(created_at)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_alerts_impact ON alerts(impact_score)"
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS event_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                alert_id INTEGER NOT NULL,
                event_timestamp_utc TEXT,
                severity TEXT,
                confidence REAL,
                impact_score INTEGER,
                predictive_outcome TEXT,
                is_relevant INTEGER,
                normalized_payload_json TEXT,
                recorded_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(alert_id) REFERENCES alerts(id) ON DELETE CASCADE
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS source_metadata (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                alert_id INTEGER NOT NULL,
                source_name TEXT NOT NULL,
                source_kind TEXT,
                source_url TEXT,
                is_primary INTEGER NOT NULL DEFAULT 0,
                source_rank INTEGER NOT NULL DEFAULT 0,
                merged_urls_json TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(alert_id) REFERENCES alerts(id) ON DELETE CASCADE
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_event_history_alert_id ON event_history(alert_id)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_source_metadata_alert_id ON source_metadata(alert_id)"
        )
        # Backward-compatible schema upgrades for existing databases.
        for column, type_sql in ALERT_MIGRATION_COLUMNS.items():
            _ensure_alert_column(conn, column, type_sql)


def _ensure_alert_column(conn: sqlite3.Connection, column: str, type_sql: str) -> None:
    expected_type = ALERT_MIGRATION_COLUMNS.get(column)
    if expected_type is None or expected_type != type_sql:
        raise ValueError(f"Unsafe migration column definition: {column} {type_sql}")
    cur = conn.execute("PRAGMA table_info(alerts)")
    existing = {row["name"] for row in cur.fetchall()}
    if column in existing:
        return
    conn.execute(f"ALTER TABLE alerts ADD COLUMN {column} {type_sql}")


def hash_url(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()


def alert_exists(url: str) -> bool:
    url_hash = hash_url(url)
    with connect() as conn:
        cur = conn.execute(
            "SELECT 1 FROM alerts WHERE url_hash = ? LIMIT 1", (url_hash,)
        )
        return cur.fetchone() is not None


def insert_alert(
    *,
    url: str,
    title: str,
    snippet: str,
    published_at: Optional[str],
    source: str,
    source_kind: str,
    severity: str,
    confidence: float,
    event_timestamp_utc: str,
    impact_score: int,
    predictive_outcome: str,
    is_relevant: bool,
    subject: str,
    location_name: str,
    location_zip_code: Optional[str] = None,
    location_latitude: Optional[float] = None,
    location_longitude: Optional[float] = None,
    merged_urls: Sequence[str] = (),
    merged_sources: Sequence[str] = (),
    normalized_payload: Optional[dict[str, Any]] = None,
) -> bool:
    url_hash = hash_url(url)
    try:
        with connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO alerts (
                    url, url_hash, title, snippet, published_at, source,
                    source_kind,
                    severity, confidence, event_timestamp_utc,
                    location_zip_code, location_latitude, location_longitude,
                    impact_score, predictive_outcome, is_relevant, subject, location_name
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    url,
                    url_hash,
                    title,
                    snippet,
                    published_at,
                    source,
                    source_kind,
                    severity,
                    confidence,
                    event_timestamp_utc,
                    location_zip_code,
                    location_latitude,
                    location_longitude,
                    impact_score,
                    predictive_outcome,
                    int(is_relevant),
                    subject,
                    location_name,
                ),
            )
            alert_id = int(cur.lastrowid)
            _insert_event_history(
                conn=conn,
                alert_id=alert_id,
                event_timestamp_utc=event_timestamp_utc,
                severity=severity,
                confidence=confidence,
                impact_score=impact_score,
                predictive_outcome=predictive_outcome,
                is_relevant=is_relevant,
                normalized_payload=normalized_payload,
            )
            _insert_source_metadata(
                conn=conn,
                alert_id=alert_id,
                canonical_source=source,
                source_kind=source_kind,
                canonical_url=url,
                merged_urls=merged_urls,
                merged_sources=merged_sources,
            )
        return True
    except sqlite3.IntegrityError:
        return False


def _insert_event_history(
    *,
    conn: sqlite3.Connection,
    alert_id: int,
    event_timestamp_utc: str,
    severity: str,
    confidence: float,
    impact_score: int,
    predictive_outcome: str,
    is_relevant: bool,
    normalized_payload: Optional[dict[str, Any]],
) -> None:
    payload_json = None
    if normalized_payload is not None:
        payload_json = json.dumps(normalized_payload, sort_keys=True, ensure_ascii=False)
    conn.execute(
        """
        INSERT INTO event_history (
            alert_id, event_timestamp_utc, severity, confidence,
            impact_score, predictive_outcome, is_relevant,
            normalized_payload_json, recorded_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            alert_id,
            event_timestamp_utc,
            severity,
            confidence,
            impact_score,
            predictive_outcome,
            int(is_relevant),
            payload_json,
            datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        ),
    )


def _split_sources(canonical_source: str, merged_sources: Sequence[str]) -> list[str]:
    sources: list[str] = []
    for source in merged_sources:
        raw = str(source or "").strip()
        if raw and raw not in sources:
            sources.append(raw)
    if not sources:
        for part in str(canonical_source or "").split("|"):
            raw = part.strip()
            if raw and raw not in sources:
                sources.append(raw)
    if not sources:
        sources.append("Unknown")
    return sources


def _dedupe_urls(urls: Iterable[str]) -> list[str]:
    deduped: list[str] = []
    for url in urls:
        value = str(url or "").strip()
        if value and value not in deduped:
            deduped.append(value)
    return deduped


def _insert_source_metadata(
    *,
    conn: sqlite3.Connection,
    alert_id: int,
    canonical_source: str,
    source_kind: str,
    canonical_url: str,
    merged_urls: Sequence[str],
    merged_sources: Sequence[str],
) -> None:
    sources = _split_sources(canonical_source, merged_sources)
    urls = _dedupe_urls(merged_urls)
    if canonical_url and canonical_url not in urls:
        urls.insert(0, canonical_url)
    merged_urls_json = json.dumps(urls, sort_keys=False, ensure_ascii=False)
    for rank, source_name in enumerate(sources):
        conn.execute(
            """
            INSERT INTO source_metadata (
                alert_id, source_name, source_kind, source_url,
                is_primary, source_rank, merged_urls_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                alert_id,
                source_name,
                source_kind,
                canonical_url,
                1 if rank == 0 else 0,
                rank,
                merged_urls_json,
            ),
        )


def fetch_recent(limit: int = 200) -> List[sqlite3.Row]:
    with connect() as conn:
        cur = conn.execute(
            """
            SELECT id, url, title, snippet, published_at, source,
                   source_kind,
                   severity, confidence, event_timestamp_utc,
                   location_zip_code, location_latitude, location_longitude,
                   impact_score, predictive_outcome, is_relevant, subject, location_name,
                   created_at
            FROM alerts
            ORDER BY impact_score DESC, created_at DESC
            LIMIT ?
            """,
            (limit,),
        )
        return list(cur.fetchall())
