from __future__ import annotations

from http.server import ThreadingHTTPServer
import logging
import signal
import threading

from app import BotServiceApp
from config import ConfigError, load_settings
from http_server import build_handler
from logging_setup import configure_logging
from storage import BotServiceDB
from telegram_sender import TelegramSender


LOGGER = logging.getLogger("assignee_notify.bot_service")
STOP_EVENT = threading.Event()



def _handle_stop_signal(signum: int, _frame: object) -> None:
    LOGGER.info("Received signal %s, shutting down", signum)
    STOP_EVENT.set()



def run() -> int:
    try:
        settings = load_settings()
    except ConfigError as exc:
        logging.basicConfig(level=logging.ERROR)
        LOGGER.error("Configuration error: %s", exc)
        return 2

    configure_logging(settings.log_file, settings.log_level)

    storage = BotServiceDB(settings.db_path, settings.schema_path)
    storage.init_schema()

    app = BotServiceApp(
        settings=settings,
        storage=storage,
        telegram_sender=TelegramSender(
            bot_token=settings.telegram_bot_token,
            api_base_url=settings.telegram_api_base,
            timeout_sec=settings.http_timeout_sec,
        ),
    )

    handler = build_handler(
        app=app,
        endpoint_path=settings.endpoint_path,
        max_body_bytes=settings.max_body_bytes,
        logger=LOGGER,
    )

    server = ThreadingHTTPServer((settings.app_host, settings.app_port), handler)
    # Prevent indefinite block in handle_request so stop signals are handled promptly.
    server.timeout = 1

    signal.signal(signal.SIGTERM, _handle_stop_signal)
    signal.signal(signal.SIGINT, _handle_stop_signal)

    LOGGER.info("Bot-service starting on %s:%s", settings.app_host, settings.app_port)
    LOGGER.info("Endpoint: %s", settings.endpoint_path)
    LOGGER.info("Database: %s", settings.db_path)

    try:
        while not STOP_EVENT.is_set():
            server.handle_request()
    finally:
        server.server_close()

    LOGGER.info("Bot-service stopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
