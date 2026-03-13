from __future__ import annotations

import base64
from pathlib import Path
import logging
import re
import signal
import tempfile
import threading
from typing import Any

from config import ConfigError, Settings, load_settings
from converter_adapter import ConversionError, ConverterAdapter, SUPPORTED_EXTENSIONS
from kanboard_api import KanboardAPIClient, KanboardAPIError
from queue_db import QueueDB


LOGGER = logging.getLogger("autopdf.worker")
STOP_EVENT = threading.Event()


def configure_logging(log_file: Path, level: str) -> None:
    log_file.parent.mkdir(parents=True, exist_ok=True)

    formatter = logging.Formatter(
        fmt="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S%z",
    )

    file_handler = logging.FileHandler(log_file)
    file_handler.setFormatter(formatter)

    logger = logging.getLogger()
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    logger.handlers.clear()
    logger.addHandler(file_handler)


def sanitize_filename(filename: str, fallback: str) -> str:
    name = Path(filename).name.strip()
    if not name:
        return fallback

    # Keep Unicode letters/digits (including Cyrillic) and replace only unsafe chars.
    safe = re.sub(r"[^\w.-]", "_", name)
    return safe or fallback


def is_pdf_file(name: str) -> bool:
    return Path(name).suffix.lower() == ".pdf"


def is_supported_office_file(name: str) -> bool:
    return Path(name).suffix.lower() in SUPPORTED_EXTENSIONS


def validate_pdf(pdf_path: Path) -> None:
    if not pdf_path.exists():
        raise ConversionError(f"PDF was not created: {pdf_path}")

    if pdf_path.stat().st_size <= 0:
        raise ConversionError(f"PDF is empty: {pdf_path}")

    with pdf_path.open("rb") as fp:
        magic = fp.read(4)

    if magic != b"%PDF":
        raise ConversionError(f"Output is not a valid PDF (bad header): {pdf_path}")


def decode_base64_blob(blob_b64: str) -> bytes:
    try:
        return base64.b64decode(blob_b64, validate=True)
    except Exception as exc:
        raise ValueError("Invalid base64 payload") from exc


def encode_base64_blob(payload: bytes) -> str:
    return base64.b64encode(payload).decode("ascii")


def normalize_target_name(target_name: str, fallback_source_name: str) -> str:
    if target_name and target_name.lower().endswith(".pdf"):
        return sanitize_filename(target_name, "converted.pdf")

    source_base = Path(fallback_source_name).stem or "converted"
    return sanitize_filename(f"{source_base}.pdf", "converted.pdf")


def to_int_or_none(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def process_job(
    job: dict[str, Any],
    queue: QueueDB,
    api: KanboardAPIClient,
    adapter: ConverterAdapter,
    settings: Settings,
) -> None:
    job_id = int(job["id"])
    file_id = int(job["file_id"])
    task_id = int(job["task_id"])

    queued_name = str(job.get("original_name") or "")
    if is_pdf_file(queued_name):
        queue.mark_done(job_id, note="ignored: source is already PDF")
        LOGGER.info("Job %s ignored: source already PDF", job_id)
        return

    if not is_supported_office_file(queued_name):
        queue.mark_done(job_id, note="ignored: unsupported source type")
        LOGGER.info("Job %s ignored: unsupported source type (%s)", job_id, queued_name)
        return

    file_meta = api.get_task_file(file_id)
    source_name = str(file_meta.get("name") or queued_name)

    if is_pdf_file(source_name):
        queue.mark_done(job_id, note="ignored: source became PDF")
        LOGGER.info("Job %s ignored: metadata says source is PDF", job_id)
        return

    if not is_supported_office_file(source_name):
        queue.mark_done(job_id, note="ignored: unsupported source type")
        LOGGER.info("Job %s ignored: unsupported source type (%s)", job_id, source_name)
        return

    blob_b64 = api.download_task_file(file_id)
    source_blob = decode_base64_blob(blob_b64)

    project_id = to_int_or_none(job.get("project_id"))
    if project_id is None:
        project_id = to_int_or_none(file_meta.get("project_id"))

    target_name = normalize_target_name(str(job.get("target_name") or ""), source_name)
    safe_source_name = sanitize_filename(source_name, f"file_{file_id}{Path(source_name).suffix}")

    settings.temp_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="autopdf_", dir=str(settings.temp_dir)) as tmp_dir_str:
        tmp_dir = Path(tmp_dir_str)
        source_path = tmp_dir / safe_source_name
        source_path.write_bytes(source_blob)

        pdf_path = adapter.convert_to_pdf(source_path, tmp_dir)
        validate_pdf(pdf_path)

        pdf_blob_b64 = encode_base64_blob(pdf_path.read_bytes())

    api.create_task_file(
        project_id=project_id,
        task_id=task_id,
        filename=target_name,
        blob_b64=pdf_blob_b64,
    )

    try:
        removed = api.remove_task_file(file_id)
    except KanboardAPIError as exc:
        message = f"PDF uploaded, but source removal RPC failed for file_id={file_id}: {exc}"
        queue.mark_partial_error(job_id, message)
        LOGGER.error("Job %s partial_error: %s", job_id, message)
        return

    if not removed:
        message = f"PDF uploaded, but source was not removed (file_id={file_id})"
        queue.mark_partial_error(job_id, message)
        LOGGER.error("Job %s partial_error: %s", job_id, message)
        return

    queue.mark_done(job_id)
    LOGGER.info("Job %s done (file_id=%s, task_id=%s)", job_id, file_id, task_id)


def _handle_stop_signal(signum: int, _frame: Any) -> None:
    LOGGER.info("Received signal %s, stopping worker", signum)
    STOP_EVENT.set()


def run() -> int:
    try:
        settings = load_settings()
    except ConfigError as exc:
        logging.basicConfig(level=logging.ERROR)
        LOGGER.error("Configuration error: %s", exc)
        return 2

    configure_logging(settings.log_file, settings.log_level)

    LOGGER.info("AutoPdf worker starting")
    LOGGER.info("Queue DB: %s", settings.queue_db_path)
    LOGGER.info("RPC URL: %s", settings.kanboard_url)

    queue = QueueDB(settings.queue_db_path, settings.schema_path)
    queue.init_schema()

    api = KanboardAPIClient(
        rpc_url=settings.kanboard_url,
        username=settings.kanboard_api_user,
        api_token=settings.kanboard_api_token,
        timeout_sec=settings.http_timeout_sec,
    )

    adapter = ConverterAdapter(
        converter_script_path=settings.converter_script_path,
        python_bin=settings.python_bin,
        libreoffice_bin=settings.libreoffice_bin,
        timeout_sec=max(settings.http_timeout_sec, 300),
    )

    signal.signal(signal.SIGTERM, _handle_stop_signal)
    signal.signal(signal.SIGINT, _handle_stop_signal)

    while not STOP_EVENT.is_set():
        job = queue.claim_next_pending()

        if job is None:
            STOP_EVENT.wait(settings.poll_interval_sec)
            continue

        job_id = int(job["id"])
        LOGGER.info("Job %s claimed (file_id=%s)", job_id, job.get("file_id"))

        try:
            process_job(job, queue, api, adapter, settings)
        except Exception as exc:
            next_status = queue.mark_retry_or_error(
                job_id=job_id,
                error_message=str(exc),
                max_retries=settings.max_retries,
            )
            LOGGER.exception(
                "Job %s failed, status -> %s (retry_count incremented)",
                job_id,
                next_status,
            )

    LOGGER.info("AutoPdf worker stopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
