"""
Ingestion Quarantine — Dead Letter Queue.

When a connector returns data that fails schema validation,
the record is quarantined here instead of being silently dropped.

The investigation continues with the evidence explicitly marked
as INGESTION_ERROR — the case never silently proceeds with
fabricated or missing data.

Storage: SQLite alongside cases in raven.db.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel

logger = logging.getLogger(__name__)


class QuarantinedRecord(BaseModel):
    """A record that failed ingestion validation."""

    id: str                        # Auto-generated UUID
    case_id: str
    source_system: str             # "razorpay", "merchant_shipping", etc.
    evidence_category: str         # "payment", "delivery", etc.
    raw_payload: dict[str, Any]    # The exact payload that failed
    error_message: str             # Pydantic validation error details
    quarantined_at: datetime


def _clean_sqlite_path(db_path: str | None) -> str:
    """Normalize a database URL or file path into a clean SQLite connection path."""
    if not db_path:
        from app.config import settings
        db_path = settings.database_url

    if db_path.startswith("sqlite:///"):
        cleaned = db_path[len("sqlite:///"):]
        return cleaned if cleaned else ":memory:"
    return db_path


class IngestionQuarantine:
    """SQLite-backed Dead Letter Queue for failed ingestion records.

    Stored alongside cases in the existing raven.db so that
    quarantined records are discoverable during case review.
    """

    def __init__(self, db_path: str | None = None):
        self._db_path = _clean_sqlite_path(db_path)
        self._ensure_table()

    def _get_connection(self) -> sqlite3.Connection:
        """Create a SQLite connection with timeout and WAL mode enabled."""
        conn = sqlite3.connect(self._db_path, timeout=30)
        if self._db_path != ":memory:":
            try:
                conn.execute("PRAGMA journal_mode=WAL")
                conn.execute("PRAGMA synchronous=NORMAL")
            except Exception:
                pass
        return conn

    def _ensure_table(self) -> None:
        """Create the quarantine table if it doesn't exist."""
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS quarantined_records (
                    id TEXT PRIMARY KEY,
                    case_id TEXT NOT NULL,
                    source_system TEXT NOT NULL,
                    evidence_category TEXT NOT NULL,
                    raw_payload TEXT NOT NULL,
                    error_message TEXT NOT NULL,
                    quarantined_at TEXT NOT NULL
                )
            """)
            conn.commit()

    def quarantine(self, record: QuarantinedRecord) -> None:
        """Store a failed record in the quarantine table."""
        try:
            with self._get_connection() as conn:
                conn.execute(
                    """
                    INSERT INTO quarantined_records
                        (id, case_id, source_system, evidence_category,
                         raw_payload, error_message, quarantined_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        record.id,
                        record.case_id,
                        record.source_system,
                        record.evidence_category,
                        json.dumps(record.raw_payload, default=str),
                        record.error_message,
                        record.quarantined_at.isoformat(),
                    ),
                )
                conn.commit()
            logger.warning(
                f"Quarantined {record.source_system}/{record.evidence_category} "
                f"for case {record.case_id}: {record.error_message[:100]}"
            )
        except sqlite3.Error as e:
            logger.error(f"Failed to quarantine record: {e}")

    def list_quarantined(self, case_id: str) -> list[QuarantinedRecord]:
        """Retrieve all quarantined records for a case."""
        try:
            with self._get_connection() as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    "SELECT * FROM quarantined_records WHERE case_id = ? ORDER BY quarantined_at",
                    (case_id,),
                ).fetchall()
                return [
                    QuarantinedRecord(
                        id=row["id"],
                        case_id=row["case_id"],
                        source_system=row["source_system"],
                        evidence_category=row["evidence_category"],
                        raw_payload=json.loads(row["raw_payload"]),
                        error_message=row["error_message"],
                        quarantined_at=datetime.fromisoformat(row["quarantined_at"]),
                    )
                    for row in rows
                ]
        except sqlite3.Error as e:
            logger.error(f"Failed to list quarantined records: {e}")
            return []

    def count(self, case_id: str | None = None) -> int:
        """Count quarantined records, optionally filtered by case_id."""
        try:
            with self._get_connection() as conn:
                if case_id:
                    row = conn.execute(
                        "SELECT COUNT(*) FROM quarantined_records WHERE case_id = ?",
                        (case_id,),
                    ).fetchone()
                else:
                    row = conn.execute(
                        "SELECT COUNT(*) FROM quarantined_records"
                    ).fetchone()
                return row[0] if row else 0
        except sqlite3.Error as e:
            logger.error(f"Failed to count quarantined records: {e}")
            return 0

    @staticmethod
    def make_record(
        case_id: str,
        source_system: str,
        evidence_category: str,
        raw_payload: dict,
        error_message: str,
    ) -> QuarantinedRecord:
        """Convenience factory for creating quarantine records."""
        return QuarantinedRecord(
            id=str(uuid.uuid4()),
            case_id=case_id,
            source_system=source_system,
            evidence_category=evidence_category,
            raw_payload=raw_payload,
            error_message=error_message,
            quarantined_at=datetime.now(timezone.utc),
        )
