from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import sqlite3
from typing import Any


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _truncate_error(message: str, limit: int = 2000) -> str:
    if len(message) <= limit:
        return message
    return message[: limit - 3] + "..."


class QueueDB:
    def __init__(self, db_path: Path, schema_path: Path):
        self.db_path = db_path
        self.schema_path = schema_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    def init_schema(self) -> None:
        schema_sql = self.schema_path.read_text(encoding="utf-8")
        conn = self._connect()
        try:
            conn.executescript(schema_sql)
        finally:
            conn.close()

    def claim_next_pending(self) -> dict[str, Any] | None:
        while True:
            conn = self._connect()
            try:
                conn.execute("BEGIN IMMEDIATE")
                row = conn.execute(
                    """
                    SELECT id, file_id, task_id, project_id, original_name, target_name,
                           status, retry_count, last_error, created_at, updated_at
                    FROM conversion_queue
                    WHERE status = 'pending'
                    ORDER BY id ASC
                    LIMIT 1
                    """
                ).fetchone()

                if row is None:
                    conn.execute("COMMIT")
                    return None

                updated_at = _utc_now_iso()
                result = conn.execute(
                    """
                    UPDATE conversion_queue
                    SET status = 'processing', updated_at = ?
                    WHERE id = ? AND status = 'pending'
                    """,
                    (updated_at, row["id"]),
                )

                if result.rowcount == 1:
                    conn.execute("COMMIT")
                    return dict(row)

                conn.execute("ROLLBACK")
            finally:
                conn.close()

    def mark_done(self, job_id: int, note: str | None = None) -> None:
        conn = self._connect()
        try:
            conn.execute(
                """
                UPDATE conversion_queue
                SET status = 'done',
                    last_error = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (note, _utc_now_iso(), job_id),
            )
        finally:
            conn.close()

    def mark_partial_error(self, job_id: int, error_message: str) -> None:
        conn = self._connect()
        try:
            conn.execute(
                """
                UPDATE conversion_queue
                SET status = 'partial_error',
                    last_error = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (_truncate_error(error_message), _utc_now_iso(), job_id),
            )
        finally:
            conn.close()

    def mark_retry_or_error(self, job_id: int, error_message: str, max_retries: int) -> str:
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT retry_count FROM conversion_queue WHERE id = ?",
                (job_id,),
            ).fetchone()

            if row is None:
                conn.execute("COMMIT")
                return "error"

            next_retry_count = int(row["retry_count"]) + 1
            next_status = "error" if next_retry_count >= max_retries else "pending"

            conn.execute(
                """
                UPDATE conversion_queue
                SET status = ?,
                    retry_count = ?,
                    last_error = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    next_status,
                    next_retry_count,
                    _truncate_error(error_message),
                    _utc_now_iso(),
                    job_id,
                ),
            )
            conn.execute("COMMIT")
            return next_status
        except Exception:
            conn.execute("ROLLBACK")
            raise
        finally:
            conn.close()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=30, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA busy_timeout = 5000")
        return conn
