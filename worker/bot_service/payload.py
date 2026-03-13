from __future__ import annotations

import json
from typing import Any


class PayloadValidationError(ValueError):
    """Raised when incoming JSON payload is malformed."""



def _require_key(payload: dict[str, Any], key: str) -> Any:
    if key not in payload:
        raise PayloadValidationError(f"missing field: {key}")
    return payload[key]



def _parse_positive_int(value: Any, field_name: str) -> int:
    if isinstance(value, bool):
        raise PayloadValidationError(f"invalid integer for {field_name}")

    if isinstance(value, int):
        parsed = value
    elif isinstance(value, str) and value.isdigit():
        parsed = int(value)
    else:
        raise PayloadValidationError(f"invalid integer for {field_name}")

    if parsed <= 0:
        raise PayloadValidationError(f"{field_name} must be positive")

    return parsed



def _parse_nullable_int(value: Any, field_name: str) -> int | None:
    if value is None or value == "":
        return None
    return _parse_positive_int(value, field_name)



def parse_event_payload(raw_body: bytes) -> dict[str, Any]:
    if not raw_body:
        raise PayloadValidationError("empty body")

    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except Exception as exc:
        raise PayloadValidationError("invalid json") from exc

    if not isinstance(payload, dict):
        raise PayloadValidationError("payload must be a JSON object")

    event_id = _require_key(payload, "event_id")
    if not isinstance(event_id, str) or event_id.strip() == "":
        raise PayloadValidationError("invalid event_id")

    event_type = _require_key(payload, "event_type")
    if event_type != "assignee_changed":
        raise PayloadValidationError("unsupported event_type")

    occurred_at = _require_key(payload, "occurred_at")
    if not isinstance(occurred_at, str) or occurred_at.strip() == "":
        raise PayloadValidationError("invalid occurred_at")

    task_id = _parse_positive_int(_require_key(payload, "task_id"), "task_id")
    kanboard_user_id = _parse_positive_int(
        _require_key(payload, "kanboard_user_id"),
        "kanboard_user_id",
    )

    old_assignee = _parse_nullable_int(payload.get("old_assignee_user_id"), "old_assignee_user_id")
    new_assignee = _parse_nullable_int(payload.get("new_assignee_user_id"), "new_assignee_user_id")

    return {
        "event_id": event_id.strip(),
        "event_type": event_type,
        "occurred_at": occurred_at.strip(),
        "task_id": task_id,
        "kanboard_user_id": kanboard_user_id,
        "old_assignee_user_id": old_assignee,
        "new_assignee_user_id": new_assignee,
    }
