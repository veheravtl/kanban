from __future__ import annotations

import logging
import re
import threading
from typing import Any

import requests

from config import Settings
from storage import BotServiceDB
from telegram_sender import TelegramSendError, TelegramSender


BIND_COMMAND_RE = re.compile(r"^/bind(?:@\w+)?\s+([A-Za-z0-9-]{4,64})\s*$")


class TelegramBindingPoller:
    def __init__(
        self,
        settings: Settings,
        storage: BotServiceDB,
        telegram_sender: TelegramSender,
        logger: logging.Logger,
    ):
        self.settings = settings
        self.storage = storage
        self.telegram_sender = telegram_sender
        self.logger = logger
        self.offset: int | None = None
        self.session = requests.Session()

    def run(self, stop_event: threading.Event) -> None:
        self.logger.info("Telegram bind poller started")

        while not stop_event.is_set():
            try:
                self._poll_once()
            except Exception as exc:  # noqa: BLE001
                self.logger.error("Telegram bind poller error: %s", exc)
                stop_event.wait(2)

        self.logger.info("Telegram bind poller stopped")

    def _poll_once(self) -> None:
        url = f"{self.settings.telegram_api_base}/bot{self.settings.telegram_bot_token}/getUpdates"
        params: dict[str, Any] = {
            "timeout": self.settings.telegram_poll_timeout_sec,
        }
        if self.offset is not None:
            params["offset"] = self.offset

        response = self.session.get(
            url,
            params=params,
            timeout=self.settings.telegram_poll_timeout_sec + 5,
        )
        response.raise_for_status()

        payload = response.json()
        if not isinstance(payload, dict) or payload.get("ok") is not True:
            raise RuntimeError("invalid getUpdates response")

        updates = payload.get("result")
        if not isinstance(updates, list):
            return

        for update in updates:
            if not isinstance(update, dict):
                continue

            update_id = update.get("update_id")
            if isinstance(update_id, int):
                self.offset = update_id + 1

            self._handle_update(update)

    def _handle_update(self, update: dict[str, Any]) -> None:
        message = update.get("message")
        if not isinstance(message, dict):
            return

        chat = message.get("chat")
        if not isinstance(chat, dict):
            return

        chat_id = chat.get("id")
        if chat_id is None:
            return

        chat_id_str = str(chat_id)
        text = message.get("text")
        if not isinstance(text, str):
            return

        text = text.strip()
        if text == "":
            return

        if text.startswith("/start"):
            self._safe_reply(
                chat_id_str,
                "Отправьте команду /bind <код> из Kanboard для привязки уведомлений.",
            )
            return

        match = BIND_COMMAND_RE.match(text)
        if match is None:
            return

        code = match.group(1).upper()
        result = self.storage.consume_binding_token(code, chat_id_str)
        status = result.get("status")

        if status == "bound":
            kanboard_user_id = result.get("kanboard_user_id")
            self._safe_reply(chat_id_str, "Привязка выполнена. Уведомления включены.")
            self.logger.info(
                "Telegram binding completed: kanboard_user_id=%s chat_id=%s",
                kanboard_user_id,
                chat_id_str,
            )
            return

        if status == "already_bound":
            self._safe_reply(
                chat_id_str,
                "У пользователя уже есть активная привязка. Попросите администратора отвязать старый чат.",
            )
            return

        if status == "chat_already_bound":
            self._safe_reply(
                chat_id_str,
                "Этот Telegram уже привязан к другому пользователю Kanboard. Попросите администратора отвязать его сначала.",
            )
            return

        if status == "expired":
            self._safe_reply(chat_id_str, "Код истек. Сгенерируйте новый код в Kanboard.")
            return

        if status == "used":
            self._safe_reply(chat_id_str, "Этот код уже использован.")
            return

        self._safe_reply(chat_id_str, "Некорректный код. Проверьте и попробуйте снова.")

    def _safe_reply(self, chat_id: str, text: str) -> None:
        try:
            self.telegram_sender.send_message(chat_id=chat_id, text=text)
        except TelegramSendError as exc:
            self.logger.error("Telegram bind reply error for chat_id=%s: %s", chat_id, exc)
