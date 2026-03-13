from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os


class ConfigError(RuntimeError):
    """Raised when required configuration is missing or invalid."""


@dataclass(frozen=True)
class Settings:
    app_host: str
    app_port: int
    endpoint_path: str
    shared_secret: str
    telegram_bot_token: str
    telegram_api_base: str
    message_text: str
    db_path: Path
    schema_path: Path
    http_timeout_sec: int
    max_body_bytes: int
    log_file: Path
    log_level: str



def _load_dotenv(dotenv_path: Path) -> None:
    if not dotenv_path.exists():
        return

    for raw_line in dotenv_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")

        if key and key not in os.environ:
            os.environ[key] = value



def _env_str(name: str, default: str | None = None, required: bool = False) -> str:
    value = os.getenv(name, default)
    if required and (value is None or value == ""):
        raise ConfigError(f"Missing required env var: {name}")
    if value is None:
        return ""
    return value



def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default

    try:
        value = int(raw)
    except ValueError as exc:
        raise ConfigError(f"Invalid integer for {name}: {raw}") from exc

    if value <= 0:
        raise ConfigError(f"Expected positive integer for {name}: {raw}")

    return value



def load_settings() -> Settings:
    component_dir = Path(__file__).resolve().parent
    _load_dotenv(component_dir / ".env")

    app_host = _env_str("BOT_SERVICE_HOST", default="0.0.0.0")
    app_port = _env_int("BOT_SERVICE_PORT", default=8089)

    endpoint_path = _env_str("BOT_SERVICE_ENDPOINT", default="/events/assignee-changed")
    if not endpoint_path.startswith("/"):
        endpoint_path = "/" + endpoint_path

    telegram_api_base = _env_str("BOT_SERVICE_TELEGRAM_API_BASE", default="https://api.telegram.org")
    telegram_api_base = telegram_api_base.rstrip("/")

    db_path = Path(_env_str("BOT_SERVICE_DB_PATH", default="/var/www/kanboard/data/kanboard_bot_service.sqlite"))
    schema_path = Path(
        _env_str("BOT_SERVICE_SCHEMA_PATH", default=str(component_dir / "schema.sql"))
    )

    log_file = Path(_env_str("BOT_SERVICE_LOG_FILE", default="/var/log/kanboard-bot-service.log"))

    return Settings(
        app_host=app_host,
        app_port=app_port,
        endpoint_path=endpoint_path,
        shared_secret=_env_str("BOT_SERVICE_SHARED_SECRET", required=True),
        telegram_bot_token=_env_str("BOT_SERVICE_TELEGRAM_BOT_TOKEN", required=True),
        telegram_api_base=telegram_api_base,
        message_text=_env_str(
            "BOT_SERVICE_MESSAGE_TEXT",
            default="You have a new task assigned. Open Kanboard.",
        ),
        db_path=db_path,
        schema_path=schema_path,
        http_timeout_sec=_env_int("BOT_SERVICE_HTTP_TIMEOUT_SEC", default=15),
        max_body_bytes=_env_int("BOT_SERVICE_MAX_BODY_BYTES", default=32768),
        log_file=log_file,
        log_level=_env_str("BOT_SERVICE_LOG_LEVEL", default="INFO"),
    )
