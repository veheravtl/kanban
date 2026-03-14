from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import secrets
import sqlite3
from typing import Any


TOKEN_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"



def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()



def _truncate(value: str, limit: int = 1000) -> str:
    if len(value) <= limit:
        return value
    return value[: limit - 3] + "..."


def _parse_utc_iso(value: str) -> datetime:
    return datetime.fromisoformat(value)


class BindingConflictError(Exception):
    def __init__(self, telegram_chat_id: str, conflicting_user_id: int):
        self.telegram_chat_id = str(telegram_chat_id)
        self.conflicting_user_id = int(conflicting_user_id)
        super().__init__(
            f"telegram_chat_id already bound to kanboard_user_id={self.conflicting_user_id}"
        )


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

    def get_binding(self, kanboard_user_id: int) -> dict[str, Any] | None:
        conn = self._connect()
        try:
            row = conn.execute(
                """
                SELECT id, kanboard_user_id, telegram_chat_id, is_active, created_at, updated_at
                FROM user_bindings
                WHERE kanboard_user_id = ?
                LIMIT 1
                """,
                (int(kanboard_user_id),),
            ).fetchone()

            if row is None:
                return None
            return dict(row)
        finally:
            conn.close()

    def list_bindings(self, kanboard_user_id: int | None = None) -> list[dict[str, Any]]:
        conn = self._connect()
        try:
            if kanboard_user_id is None:
                rows = conn.execute(
                    """
                    SELECT id, kanboard_user_id, telegram_chat_id, is_active, created_at, updated_at
                    FROM user_bindings
                    ORDER BY kanboard_user_id ASC
                    """
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT id, kanboard_user_id, telegram_chat_id, is_active, created_at, updated_at
                    FROM user_bindings
                    WHERE kanboard_user_id = ?
                    ORDER BY kanboard_user_id ASC
                    """,
                    (int(kanboard_user_id),),
                ).fetchall()

            return [dict(row) for row in rows]
        finally:
            conn.close()

    def upsert_binding(
        self,
        kanboard_user_id: int,
        telegram_chat_id: str,
        is_active: bool = True,
    ) -> dict[str, Any]:
        now = _utc_now_iso()
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            if is_active:
                conflicting = self._find_active_binding_by_chat_id(
                    conn,
                    telegram_chat_id=str(telegram_chat_id),
                    exclude_user_id=int(kanboard_user_id),
                )
                if conflicting is not None:
                    raise BindingConflictError(
                        telegram_chat_id=str(telegram_chat_id),
                        conflicting_user_id=int(conflicting["kanboard_user_id"]),
                    )

            conn.execute(
                """
                INSERT INTO user_bindings (
                    kanboard_user_id,
                    telegram_chat_id,
                    is_active,
                    created_at,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(kanboard_user_id) DO UPDATE SET
                    telegram_chat_id = excluded.telegram_chat_id,
                    is_active = excluded.is_active,
                    updated_at = excluded.updated_at
                """,
                (
                    int(kanboard_user_id),
                    telegram_chat_id,
                    1 if is_active else 0,
                    now,
                    now,
                ),
            )

            row = conn.execute(
                """
                SELECT id, kanboard_user_id, telegram_chat_id, is_active, created_at, updated_at
                FROM user_bindings
                WHERE kanboard_user_id = ?
                LIMIT 1
                """,
                (int(kanboard_user_id),),
            ).fetchone()
            conn.execute("COMMIT")
            return dict(row) if row is not None else {}
        except Exception:
            conn.execute("ROLLBACK")
            raise
        finally:
            conn.close()

    def deactivate_binding(self, kanboard_user_id: int) -> bool:
        conn = self._connect()
        try:
            cursor = conn.execute(
                """
                UPDATE user_bindings
                SET is_active = 0,
                    updated_at = ?
                WHERE kanboard_user_id = ?
                """,
                (_utc_now_iso(), int(kanboard_user_id)),
            )
            return cursor.rowcount > 0
        finally:
            conn.close()

    def create_binding_token(
        self,
        kanboard_user_id: int,
        ttl_sec: int,
        token_length: int,
    ) -> dict[str, Any]:
        if ttl_sec <= 0:
            raise ValueError("ttl_sec must be positive")
        if token_length < 6 or token_length > 64:
            raise ValueError("token_length out of range")

        now = datetime.now(timezone.utc).replace(microsecond=0)
        expires_at = now + timedelta(seconds=ttl_sec)

        conn = self._connect()
        try:
            while True:
                token = "".join(secrets.choice(TOKEN_ALPHABET) for _ in range(token_length))
                existing = conn.execute(
                    "SELECT token FROM binding_tokens WHERE token = ? LIMIT 1",
                    (token,),
                ).fetchone()
                if existing is None:
                    break

            conn.execute(
                """
                INSERT INTO binding_tokens (
                    token,
                    kanboard_user_id,
                    is_used,
                    expires_at,
                    used_at,
                    created_at
                ) VALUES (?, ?, 0, ?, NULL, ?)
                """,
                (
                    token,
                    int(kanboard_user_id),
                    expires_at.isoformat(),
                    now.isoformat(),
                ),
            )

            return {
                "token": token,
                "kanboard_user_id": int(kanboard_user_id),
                "expires_at": expires_at.isoformat(),
                "created_at": now.isoformat(),
            }
        finally:
            conn.close()

    def consume_binding_token(self, token: str, telegram_chat_id: str) -> dict[str, Any]:
        token_value = token.strip().upper()
        if token_value == "":
            return {"status": "invalid"}

        chat_id_str = str(telegram_chat_id)
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                """
                SELECT token, kanboard_user_id, is_used, expires_at
                FROM binding_tokens
                WHERE token = ?
                LIMIT 1
                """,
                (token_value,),
            ).fetchone()

            if row is None:
                conn.execute("ROLLBACK")
                return {"status": "invalid"}

            if int(row["is_used"]) == 1:
                conn.execute("ROLLBACK")
                return {"status": "used"}

            expires_at = _parse_utc_iso(str(row["expires_at"]))
            now = datetime.now(timezone.utc).replace(microsecond=0)
            if expires_at < now:
                conn.execute("ROLLBACK")
                return {"status": "expired"}

            kanboard_user_id = int(row["kanboard_user_id"])
            existing = conn.execute(
                """
                SELECT telegram_chat_id
                FROM user_bindings
                WHERE kanboard_user_id = ?
                  AND is_active = 1
                LIMIT 1
                """,
                (kanboard_user_id,),
            ).fetchone()

            if existing is not None and str(existing["telegram_chat_id"]) != str(telegram_chat_id):
                conn.execute("ROLLBACK")
                return {
                    "status": "already_bound",
                    "kanboard_user_id": kanboard_user_id,
                    "current_chat_id": str(existing["telegram_chat_id"]),
                }

            conflicting = self._find_active_binding_by_chat_id(
                conn,
                telegram_chat_id=chat_id_str,
                exclude_user_id=kanboard_user_id,
            )
            if conflicting is not None:
                conn.execute("ROLLBACK")
                return {
                    "status": "chat_already_bound",
                    "kanboard_user_id": kanboard_user_id,
                    "conflicting_user_id": int(conflicting["kanboard_user_id"]),
                    "telegram_chat_id": chat_id_str,
                }

            now_iso = now.isoformat()
            conn.execute(
                """
                INSERT INTO user_bindings (
                    kanboard_user_id,
                    telegram_chat_id,
                    is_active,
                    created_at,
                    updated_at
                ) VALUES (?, ?, 1, ?, ?)
                ON CONFLICT(kanboard_user_id) DO UPDATE SET
                    telegram_chat_id = excluded.telegram_chat_id,
                    is_active = 1,
                    updated_at = excluded.updated_at
                """,
                (
                    kanboard_user_id,
                    chat_id_str,
                    now_iso,
                    now_iso,
                ),
            )

            conn.execute(
                """
                UPDATE binding_tokens
                SET is_used = 1,
                    used_at = ?
                WHERE token = ?
                """,
                (now_iso, token_value),
            )
            conn.execute("COMMIT")
            return {
                "status": "bound",
                "kanboard_user_id": kanboard_user_id,
            }
        except Exception:
            conn.execute("ROLLBACK")
            raise
        finally:
            conn.close()

    def _find_active_binding_by_chat_id(
        self,
        conn: sqlite3.Connection,
        telegram_chat_id: str,
        exclude_user_id: int | None = None,
    ) -> dict[str, Any] | None:
        if exclude_user_id is None:
            row = conn.execute(
                """
                SELECT kanboard_user_id, telegram_chat_id
                FROM user_bindings
                WHERE telegram_chat_id = ?
                  AND is_active = 1
                LIMIT 1
                """,
                (str(telegram_chat_id),),
            ).fetchone()
        else:
            row = conn.execute(
                """
                SELECT kanboard_user_id, telegram_chat_id
                FROM user_bindings
                WHERE telegram_chat_id = ?
                  AND is_active = 1
                  AND kanboard_user_id != ?
                LIMIT 1
                """,
                (str(telegram_chat_id), int(exclude_user_id)),
            ).fetchone()

        if row is None:
            return None
        return dict(row)

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
