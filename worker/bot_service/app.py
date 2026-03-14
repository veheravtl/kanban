from __future__ import annotations

import hmac
import json
import logging
from uuid import uuid4
from typing import Any, Mapping

from config import Settings
from payload import PayloadValidationError, parse_event_payload
from storage import BindingConflictError, BotServiceDB
from telegram_sender import TelegramSendError, TelegramSender


LOGGER = logging.getLogger("assignee_notify.bot_service")


class BotServiceApp:
    def __init__(
        self,
        settings: Settings,
        storage: BotServiceDB,
        telegram_sender: TelegramSender,
    ):
        self.settings = settings
        self.storage = storage
        self.telegram_sender = telegram_sender

    def handle_webhook(self, headers: Mapping[str, Any], body: bytes) -> tuple[int, dict[str, Any]]:
        if not self._is_authorized(headers):
            LOGGER.warning("Rejected request: invalid token")
            return 401, {"ok": False, "status": "unauthorized"}

        try:
            event = parse_event_payload(body)
        except PayloadValidationError as exc:
            LOGGER.warning("Rejected request: bad payload (%s)", exc)
            return 400, {"ok": False, "status": "bad_request"}

        event_id = event["event_id"]
        kanboard_user_id = event["kanboard_user_id"]

        binding = self.storage.get_active_binding(kanboard_user_id)
        if binding is None:
            self.storage.insert_delivery_log(
                event_id=event_id,
                kanboard_user_id=kanboard_user_id,
                telegram_chat_id=None,
                message_type=event["event_type"],
                send_status="unmapped",
                telegram_message_id=None,
                error_message="user binding not found",
            )
            LOGGER.info(
                "Event %s unmapped: kanboard_user_id=%s",
                event_id,
                kanboard_user_id,
            )
            return 200, {"ok": False, "status": "unmapped"}

        telegram_chat_id = str(binding["telegram_chat_id"])

        try:
            telegram_message_id = self.telegram_sender.send_message(
                chat_id=telegram_chat_id,
                text=self.settings.message_text,
            )
        except TelegramSendError as exc:
            self.storage.insert_delivery_log(
                event_id=event_id,
                kanboard_user_id=kanboard_user_id,
                telegram_chat_id=telegram_chat_id,
                message_type=event["event_type"],
                send_status="failed",
                telegram_message_id=None,
                error_message=str(exc),
            )
            LOGGER.error(
                "Event %s telegram error: %s",
                event_id,
                exc,
            )
            return 502, {"ok": False, "status": "telegram_error"}

        self.storage.insert_delivery_log(
            event_id=event_id,
            kanboard_user_id=kanboard_user_id,
            telegram_chat_id=telegram_chat_id,
            message_type=event["event_type"],
            send_status="delivered",
            telegram_message_id=telegram_message_id,
            error_message=None,
        )

        LOGGER.info(
            "Event %s delivered to kanboard_user_id=%s",
            event_id,
            kanboard_user_id,
        )
        return 200, {"ok": True, "status": "delivered"}

    def handle_bindings_list(
        self,
        headers: Mapping[str, Any],
        query: Mapping[str, str],
    ) -> tuple[int, dict[str, Any]]:
        if not self._is_authorized(headers):
            return 401, {"ok": False, "status": "unauthorized"}

        raw_user_id = query.get("kanboard_user_id")
        if raw_user_id in (None, ""):
            filtered_user_id = None
        else:
            try:
                filtered_user_id = self._parse_positive_int(raw_user_id, "kanboard_user_id")
            except ValueError as exc:
                return 400, {"ok": False, "status": "bad_request", "error": str(exc)}

        rows = self.storage.list_bindings(filtered_user_id)
        return 200, {
            "ok": True,
            "status": "ok",
            "data": {
                "bindings": [self._serialize_binding(row) for row in rows],
            },
        }

    def handle_bindings_upsert(
        self,
        headers: Mapping[str, Any],
        body: bytes,
    ) -> tuple[int, dict[str, Any]]:
        if not self._is_authorized(headers):
            return 401, {"ok": False, "status": "unauthorized"}

        payload, error = self._parse_json_body(body)
        if error is not None:
            return 400, {"ok": False, "status": "bad_request", "error": error}

        try:
            kanboard_user_id = self._parse_positive_int(payload.get("kanboard_user_id"), "kanboard_user_id")
            telegram_chat_id = self._parse_chat_id(payload.get("telegram_chat_id"))
            is_active = self._parse_bool(payload.get("is_active", True), "is_active")
        except ValueError as exc:
            return 400, {"ok": False, "status": "bad_request", "error": str(exc)}

        try:
            row = self.storage.upsert_binding(
                kanboard_user_id=kanboard_user_id,
                telegram_chat_id=telegram_chat_id,
                is_active=is_active,
            )
        except BindingConflictError as exc:
            return 409, {
                "ok": False,
                "status": "chat_already_bound",
                "error": str(exc),
                "data": {
                    "telegram_chat_id": exc.telegram_chat_id,
                    "conflicting_user_id": exc.conflicting_user_id,
                },
            }

        LOGGER.info(
            "Binding upserted for kanboard_user_id=%s is_active=%s",
            kanboard_user_id,
            is_active,
        )
        return 200, {
            "ok": True,
            "status": "upserted",
            "data": {
                "binding": self._serialize_binding(row),
            },
        }

    def handle_bindings_unbind(
        self,
        headers: Mapping[str, Any],
        body: bytes,
    ) -> tuple[int, dict[str, Any]]:
        if not self._is_authorized(headers):
            return 401, {"ok": False, "status": "unauthorized"}

        payload, error = self._parse_json_body(body)
        if error is not None:
            return 400, {"ok": False, "status": "bad_request", "error": error}

        try:
            kanboard_user_id = self._parse_positive_int(payload.get("kanboard_user_id"), "kanboard_user_id")
        except ValueError as exc:
            return 400, {"ok": False, "status": "bad_request", "error": str(exc)}

        updated = self.storage.deactivate_binding(kanboard_user_id)
        if not updated:
            return 404, {"ok": False, "status": "not_found"}

        row = self.storage.get_binding(kanboard_user_id)
        LOGGER.info("Binding deactivated for kanboard_user_id=%s", kanboard_user_id)
        return 200, {
            "ok": True,
            "status": "unbound",
            "data": {
                "binding": self._serialize_binding(row or {}),
            },
        }

    def handle_bindings_test(
        self,
        headers: Mapping[str, Any],
        body: bytes,
    ) -> tuple[int, dict[str, Any]]:
        if not self._is_authorized(headers):
            return 401, {"ok": False, "status": "unauthorized"}

        payload, error = self._parse_json_body(body)
        if error is not None:
            return 400, {"ok": False, "status": "bad_request", "error": error}

        try:
            kanboard_user_id = self._parse_positive_int(payload.get("kanboard_user_id"), "kanboard_user_id")
        except ValueError as exc:
            return 400, {"ok": False, "status": "bad_request", "error": str(exc)}

        event_id = f"binding-test-{uuid4().hex}"
        binding = self.storage.get_active_binding(kanboard_user_id)
        if binding is None:
            self.storage.insert_delivery_log(
                event_id=event_id,
                kanboard_user_id=kanboard_user_id,
                telegram_chat_id=None,
                message_type="binding_test",
                send_status="unmapped",
                telegram_message_id=None,
                error_message="user binding not found",
            )
            return 200, {"ok": False, "status": "unmapped"}

        telegram_chat_id = str(binding["telegram_chat_id"])
        text = "Test notification: Telegram binding is active."
        try:
            telegram_message_id = self.telegram_sender.send_message(
                chat_id=telegram_chat_id,
                text=text,
            )
        except TelegramSendError as exc:
            self.storage.insert_delivery_log(
                event_id=event_id,
                kanboard_user_id=kanboard_user_id,
                telegram_chat_id=telegram_chat_id,
                message_type="binding_test",
                send_status="failed",
                telegram_message_id=None,
                error_message=str(exc),
            )
            LOGGER.error(
                "Binding test failed for kanboard_user_id=%s: %s",
                kanboard_user_id,
                exc,
            )
            return 502, {"ok": False, "status": "telegram_error"}

        self.storage.insert_delivery_log(
            event_id=event_id,
            kanboard_user_id=kanboard_user_id,
            telegram_chat_id=telegram_chat_id,
            message_type="binding_test",
            send_status="delivered",
            telegram_message_id=telegram_message_id,
            error_message=None,
        )

        return 200, {"ok": True, "status": "delivered"}

    def handle_bindings_token_create(
        self,
        headers: Mapping[str, Any],
        body: bytes,
    ) -> tuple[int, dict[str, Any]]:
        if not self._is_authorized(headers):
            return 401, {"ok": False, "status": "unauthorized"}

        payload, error = self._parse_json_body(body)
        if error is not None:
            return 400, {"ok": False, "status": "bad_request", "error": error}

        try:
            kanboard_user_id = self._parse_positive_int(payload.get("kanboard_user_id"), "kanboard_user_id")
        except ValueError as exc:
            return 400, {"ok": False, "status": "bad_request", "error": str(exc)}

        token_row = self.storage.create_binding_token(
            kanboard_user_id=kanboard_user_id,
            ttl_sec=self.settings.binding_token_ttl_sec,
            token_length=self.settings.binding_token_length,
        )

        return 200, {
            "ok": True,
            "status": "created",
            "data": {
                "code": token_row["token"],
                "kanboard_user_id": token_row["kanboard_user_id"],
                "expires_at": token_row["expires_at"],
            },
        }

    @staticmethod
    def _read_header(headers: Mapping[str, Any], name: str) -> str | None:
        for key, value in headers.items():
            if str(key).lower() == name.lower():
                return str(value)
        return None

    def _is_authorized(self, headers: Mapping[str, Any]) -> bool:
        token = self._read_header(headers, "X-Webhook-Token")
        return token is not None and hmac.compare_digest(token, self.settings.shared_secret)

    @staticmethod
    def _parse_json_body(body: bytes) -> tuple[dict[str, Any], str | None]:
        if not body:
            return {}, "empty body"
        try:
            payload = json.loads(body.decode("utf-8"))
        except Exception:
            return {}, "invalid json"
        if not isinstance(payload, dict):
            return {}, "payload must be a JSON object"
        return payload, None

    @staticmethod
    def _parse_positive_int(value: Any, field_name: str) -> int:
        if isinstance(value, bool):
            raise ValueError(f"invalid integer for {field_name}")

        if isinstance(value, int):
            parsed = value
        elif isinstance(value, str) and value.isdigit():
            parsed = int(value)
        else:
            raise ValueError(f"invalid integer for {field_name}")

        if parsed <= 0:
            raise ValueError(f"{field_name} must be positive")

        return parsed

    @staticmethod
    def _parse_bool(value: Any, field_name: str) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, int):
            if value in (0, 1):
                return value == 1
            raise ValueError(f"invalid boolean for {field_name}")
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in ("1", "true", "yes"):
                return True
            if normalized in ("0", "false", "no"):
                return False
        raise ValueError(f"invalid boolean for {field_name}")

    @staticmethod
    def _parse_chat_id(value: Any) -> str:
        if isinstance(value, bool):
            raise ValueError("invalid telegram_chat_id")
        if isinstance(value, int):
            text = str(value)
        elif isinstance(value, str):
            text = value.strip()
        else:
            raise ValueError("invalid telegram_chat_id")

        if text == "":
            raise ValueError("telegram_chat_id must not be empty")
        if len(text) > 255:
            raise ValueError("telegram_chat_id is too long")
        return text

    @staticmethod
    def _serialize_binding(row: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "id": row.get("id"),
            "kanboard_user_id": row.get("kanboard_user_id"),
            "telegram_chat_id": row.get("telegram_chat_id"),
            "is_active": bool(row.get("is_active")),
            "created_at": row.get("created_at"),
            "updated_at": row.get("updated_at"),
        }
