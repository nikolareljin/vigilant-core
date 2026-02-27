"""SQLite storage for VigilantCore alerts."""

from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path
from typing import List, Optional

from .config import data_dir


DB_NAME = "vigilantcore.db"


def db_path() -> Path:
    base = data_dir()
    base.mkdir(parents=True, exist_ok=True)
    return base / DB_NAME


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(db_path())
    conn.row_factory = sqlite3.Row
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
        # Backward-compatible schema upgrades for existing databases.
        _ensure_alert_column(conn, "severity", "TEXT")
        _ensure_alert_column(conn, "confidence", "REAL")
        _ensure_alert_column(conn, "event_timestamp_utc", "TEXT")
        _ensure_alert_column(conn, "location_zip_code", "TEXT")
        _ensure_alert_column(conn, "location_latitude", "REAL")
        _ensure_alert_column(conn, "location_longitude", "REAL")


def _ensure_alert_column(conn: sqlite3.Connection, column: str, type_sql: str) -> None:
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
) -> bool:
    url_hash = hash_url(url)
    try:
        with connect() as conn:
            conn.execute(
                """
                INSERT INTO alerts (
                    url, url_hash, title, snippet, published_at, source,
                    severity, confidence, event_timestamp_utc,
                    location_zip_code, location_latitude, location_longitude,
                    impact_score, predictive_outcome, is_relevant, subject, location_name
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    url,
                    url_hash,
                    title,
                    snippet,
                    published_at,
                    source,
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
        return True
    except sqlite3.IntegrityError:
        return False


def fetch_recent(limit: int = 200) -> List[sqlite3.Row]:
    with connect() as conn:
        cur = conn.execute(
            """
            SELECT id, url, title, snippet, published_at, source,
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
