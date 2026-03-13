from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os


class ConfigError(RuntimeError):
    """Raised when required configuration is missing or invalid."""


@dataclass(frozen=True)
class Settings:
    kanboard_url: str
    kanboard_api_user: str
    kanboard_api_token: str
    http_timeout_sec: int
    queue_db_path: Path
    schema_path: Path
    converter_script_path: Path
    python_bin: str
    libreoffice_bin: str | None
    temp_dir: Path
    poll_interval_sec: float
    max_retries: int
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
    value = os.getenv(name)
    if value is None or value == "":
        return default
    try:
        return int(value)
    except ValueError as exc:
        raise ConfigError(f"Invalid integer for {name}: {value}") from exc


def _env_float(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    try:
        return float(value)
    except ValueError as exc:
        raise ConfigError(f"Invalid float for {name}: {value}") from exc


def load_settings() -> Settings:
    worker_dir = Path(__file__).resolve().parent
    root_dir = worker_dir.parent

    _load_dotenv(worker_dir / ".env")

    kanboard_url = _env_str("KANBOARD_URL", required=True).rstrip("/")
    if not kanboard_url.endswith("/jsonrpc.php"):
        kanboard_url = f"{kanboard_url}/jsonrpc.php"

    kanboard_api_user = _env_str("KANBOARD_API_USER", default="jsonrpc")
    kanboard_api_token = _env_str("KANBOARD_API_TOKEN", required=True)

    queue_db_path = Path(_env_str("QUEUE_DB_PATH", default="/var/www/kanboard/data/autopdf_queue.sqlite"))
    schema_path = Path(_env_str("SCHEMA_PATH", default=str(root_dir / "schema.sql")))
    converter_script_path = Path(
        _env_str("CONVERTER_SCRIPT_PATH", default=str(root_dir / "exel2pdf.py"))
    )

    temp_dir = Path(_env_str("TEMP_DIR", default="/tmp/autopdf"))
    log_file = Path(_env_str("LOG_FILE", default="/var/log/autopdf-worker.log"))

    return Settings(
        kanboard_url=kanboard_url,
        kanboard_api_user=kanboard_api_user,
        kanboard_api_token=kanboard_api_token,
        http_timeout_sec=_env_int("HTTP_TIMEOUT_SEC", default=30),
        queue_db_path=queue_db_path,
        schema_path=schema_path,
        converter_script_path=converter_script_path,
        python_bin=_env_str("PYTHON_BIN", default="python3"),
        libreoffice_bin=_env_str("LIBREOFFICE_BIN", default="") or None,
        temp_dir=temp_dir,
        poll_interval_sec=_env_float("POLL_INTERVAL_SEC", default=2.0),
        max_retries=_env_int("MAX_RETRIES", default=5),
        log_file=log_file,
        log_level=_env_str("LOG_LEVEL", default="INFO"),
    )
