from __future__ import annotations

import requests


class TelegramSendError(RuntimeError):
    """Raised when Telegram sendMessage call fails."""


class TelegramSender:
    def __init__(
        self,
        bot_token: str,
        api_base_url: str = "https://api.telegram.org",
        timeout_sec: int = 15,
    ):
        self.bot_token = bot_token
        self.timeout_sec = timeout_sec
        self.api_base_url = api_base_url.rstrip("/")
        self.session = requests.Session()

    def send_message(self, chat_id: str, text: str) -> str | None:
        url = f"{self.api_base_url}/bot{self.bot_token}/sendMessage"

        try:
            response = self.session.post(
                url,
                json={
                    "chat_id": chat_id,
                    "text": text,
                },
                timeout=self.timeout_sec,
                headers={"Content-Type": "application/json"},
            )
        except requests.RequestException as exc:
            raise TelegramSendError(f"telegram network error: {exc}") from exc

        if response.status_code != 200:
            snippet = response.text[:300] if response.text else ""
            raise TelegramSendError(f"telegram http {response.status_code}: {snippet}")

        try:
            payload = response.json()
        except ValueError as exc:
            raise TelegramSendError("telegram invalid json") from exc

        if not isinstance(payload, dict):
            raise TelegramSendError("telegram invalid response type")

        if payload.get("ok") is not True:
            description = payload.get("description")
            raise TelegramSendError(f"telegram rejected: {description or 'unknown'}")

        result = payload.get("result")
        if isinstance(result, dict):
            message_id = result.get("message_id")
            if message_id is None:
                return None
            return str(message_id)

        return None
