from __future__ import annotations

from typing import Any
import requests


class KanboardAPIError(RuntimeError):
    """Raised when JSON-RPC call fails."""


class KanboardAPIClient:
    def __init__(self, rpc_url: str, username: str, api_token: str, timeout_sec: int = 30):
        self.rpc_url = rpc_url
        self.timeout_sec = timeout_sec
        self.session = requests.Session()
        self.session.auth = (username, api_token)
        self._request_id = 0

    def get_task_file(self, file_id: int) -> dict[str, Any]:
        result = self._call("getTaskFile", {"file_id": int(file_id)})
        if not isinstance(result, dict):
            raise KanboardAPIError(f"getTaskFile returned unexpected payload for file_id={file_id}")
        return result

    def download_task_file(self, file_id: int) -> str:
        result = self._call("downloadTaskFile", {"file_id": int(file_id)})
        if not isinstance(result, str) or result == "":
            raise KanboardAPIError(f"downloadTaskFile returned empty payload for file_id={file_id}")
        return result

    def create_task_file(self, project_id: int | None, task_id: int, filename: str, blob_b64: str) -> int:
        params: dict[str, Any] = {
            "task_id": int(task_id),
            "filename": filename,
            "blob": blob_b64,
        }
        if project_id is not None:
            params["project_id"] = int(project_id)

        result = self._call("createTaskFile", params)
        if isinstance(result, bool):
            if result:
                return 0
            raise KanboardAPIError("createTaskFile returned false")
        if isinstance(result, int):
            return result
        if isinstance(result, str) and result.isdigit():
            return int(result)
        raise KanboardAPIError("createTaskFile returned unexpected result")

    def remove_task_file(self, file_id: int) -> bool:
        result = self._call("removeTaskFile", {"file_id": int(file_id)})
        if isinstance(result, bool):
            return result
        if isinstance(result, int):
            return result == 1
        if isinstance(result, str):
            return result.lower() in {"1", "true"}
        return False

    def _call(self, method: str, params: dict[str, Any]) -> Any:
        self._request_id += 1
        payload = {
            "jsonrpc": "2.0",
            "method": method,
            "id": self._request_id,
            "params": params,
        }

        try:
            response = self.session.post(
                self.rpc_url,
                json=payload,
                timeout=self.timeout_sec,
                headers={"Content-Type": "application/json"},
            )
        except requests.RequestException as exc:
            raise KanboardAPIError(f"RPC network error ({method}): {exc}") from exc

        if response.status_code != 200:
            raise KanboardAPIError(
                f"RPC HTTP {response.status_code} for method {method}: {response.text[:300]}"
            )

        try:
            data = response.json()
        except ValueError as exc:
            raise KanboardAPIError(f"RPC invalid JSON ({method})") from exc

        if not isinstance(data, dict):
            raise KanboardAPIError(f"RPC invalid payload type ({method})")

        error = data.get("error")
        if error:
            raise KanboardAPIError(f"RPC error ({method}): {error}")

        return data.get("result")
