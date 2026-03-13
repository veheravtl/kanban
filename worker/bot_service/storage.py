from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import sqlite3
from typing import Any



def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()



def _truncate(value: str, limit: int = 1000) -> str:
    if len(value) <= limit:
        return value
    return value[: limit - 3] + "..."


class BotServiceDB:
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

    def get_active_binding(self, kanboard_user_id: int) -> dict[str, Any] | None:
        conn = self._connect()
        try:
            row = conn.execute(
                """
                SELECT kanboard_user_id, telegram_chat_id
                FROM user_bindings
                WHERE kanboard_user_id = ?
                  AND is_active = 1
                LIMIT 1
                """,
                (int(kanboard_user_id),),
            ).fetchone()

            if row is None:
                return None
            return dict(row)
        finally:
            conn.close()

    def insert_delivery_log(
        self,
        event_id: str,
        kanboard_user_id: int,
        telegram_chat_id: str | None,
        message_type: str,
        send_status: str,
        telegram_message_id: str | None = None,
        error_message: str | None = None,
    ) -> None:
        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT INTO delivery_log (
                    event_id,
                    kanboard_user_id,
                    telegram_chat_id,
                    message_type,
                    send_status,
                    telegram_message_id,
                    error_message,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event_id,
                    int(kanboard_user_id),
                    telegram_chat_id,
                    message_type,
                    send_status,
                    telegram_message_id,
                    _truncate(error_message) if error_message else None,
                    _utc_now_iso(),
                ),
            )
        finally:
            conn.close()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=30, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA busy_timeout = 5000")
        return conn
