from __future__ import annotations

from http.server import BaseHTTPRequestHandler
import json
import logging
from urllib.parse import parse_qs, urlsplit

from app import BotServiceApp


API_BINDINGS_PATH = "/api/v1/bindings"
API_BINDINGS_UPSERT_PATH = "/api/v1/bindings/upsert"
API_BINDINGS_UNBIND_PATH = "/api/v1/bindings/unbind"
API_BINDINGS_TEST_PATH = "/api/v1/bindings/test"
API_BINDINGS_TOKEN_CREATE_PATH = "/api/v1/bindings/token/create"



def build_handler(
    app: BotServiceApp,
    endpoint_path: str,
    max_body_bytes: int,
    logger: logging.Logger,
):
    class BotServiceHandler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802
            path = urlsplit(self.path).path
            if path == endpoint_path:
                content_length = self._read_content_length()
                if content_length is None:
                    self._write_json(400, {"ok": False, "status": "bad_request"})
                    return

                if content_length > max_body_bytes:
                    self._write_json(413, {"ok": False, "status": "bad_request"})
                    return

                body = self.rfile.read(content_length)
                status_code, payload = app.handle_webhook(self.headers, body)
                self._write_json(status_code, payload)
                return

            if path == API_BINDINGS_UPSERT_PATH:
                self._dispatch_binding_post(app.handle_bindings_upsert)
                return

            if path == API_BINDINGS_UNBIND_PATH:
                self._dispatch_binding_post(app.handle_bindings_unbind)
                return

            if path == API_BINDINGS_TEST_PATH:
                self._dispatch_binding_post(app.handle_bindings_test)
                return

            if path == API_BINDINGS_TOKEN_CREATE_PATH:
                self._dispatch_binding_post(app.handle_bindings_token_create)
                return

            self._write_json(404, {"ok": False, "status": "not_found"})

        def do_GET(self) -> None:  # noqa: N802
            parsed = urlsplit(self.path)
            if parsed.path != API_BINDINGS_PATH:
                self._write_json(404, {"ok": False, "status": "not_found"})
                return

            query = {
                key: values[-1]
                for key, values in parse_qs(parsed.query, keep_blank_values=True).items()
                if values
            }
            status_code, payload = app.handle_bindings_list(self.headers, query)
            self._write_json(status_code, payload)

        def log_message(self, fmt: str, *args) -> None:
            logger.info("http %s - %s", self.address_string(), fmt % args)

        def _dispatch_binding_post(self, handler) -> None:
            content_length = self._read_content_length()
            if content_length is None:
                self._write_json(400, {"ok": False, "status": "bad_request"})
                return

            if content_length > max_body_bytes:
                self._write_json(413, {"ok": False, "status": "bad_request"})
                return

            body = self.rfile.read(content_length)
            status_code, payload = handler(self.headers, body)
            self._write_json(status_code, payload)

        def _read_content_length(self) -> int | None:
            raw = self.headers.get("Content-Length")
            if raw is None:
                return None
            try:
                length = int(raw)
            except ValueError:
                return None
            if length < 0:
                return None
            return length

        def _write_json(self, status_code: int, payload: dict[str, object]) -> None:
            encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status_code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

    return BotServiceHandler
