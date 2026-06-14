from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any


DATABASE_PATH = Path(__file__).resolve().parents[2] / "data" / "campusbuddy.sqlite3"


def _connect() -> sqlite3.Connection:
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS campusbuddy_records (
            kind TEXT NOT NULL,
            record_id TEXT NOT NULL,
            payload TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (kind, record_id)
        )
        """
    )
    return connection


def list_records(kind: str) -> list[dict[str, Any]]:
    with _connect() as connection:
        rows = connection.execute(
            """
            SELECT payload
            FROM campusbuddy_records
            WHERE kind = ?
            ORDER BY created_at, record_id
            """,
            (kind,),
        ).fetchall()
    return [json.loads(row["payload"]) for row in rows]


def count_records(kind: str) -> int:
    with _connect() as connection:
        row = connection.execute(
            "SELECT COUNT(*) AS total FROM campusbuddy_records WHERE kind = ?",
            (kind,),
        ).fetchone()
    return int(row["total"] if row else 0)


def upsert_record(kind: str, record_id: str, payload: dict[str, Any]) -> None:
    with _connect() as connection:
        connection.execute(
            """
            INSERT INTO campusbuddy_records (kind, record_id, payload)
            VALUES (?, ?, ?)
            ON CONFLICT(kind, record_id) DO UPDATE SET
                payload = excluded.payload,
                updated_at = CURRENT_TIMESTAMP
            """,
            (kind, record_id, json.dumps(payload, sort_keys=True)),
        )


def delete_record(kind: str, record_id: str) -> bool:
    with _connect() as connection:
        cursor = connection.execute(
            "DELETE FROM campusbuddy_records WHERE kind = ? AND record_id = ?",
            (kind, record_id),
        )
    return cursor.rowcount > 0
