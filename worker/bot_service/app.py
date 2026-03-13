from __future__ import annotations

import hmac
import logging
from typing import Any, Mapping

from config import Settings
from payload import PayloadValidationError, parse_event_payload
from storage import BotServiceDB
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
        token = self._read_header(headers, "X-Webhook-Token")
        if token is None or not hmac.compare_digest(token, self.settings.shared_secret):
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

    @staticmethod
    def _read_header(headers: Mapping[str, Any], name: str) -> str | None:
        for key, value in headers.items():
            if str(key).lower() == name.lower():
                return str(value)
        return None
