# Assignee Notify bot-service

Minimal HTTP service that receives assignee-change events from Kanboard plugin and sends anonymized Telegram message.

## Behavior

1. Accepts `POST /events/assignee-changed`.
2. Checks `X-Webhook-Token` shared secret.
3. Validates JSON payload.
4. Looks up `kanboard_user_id -> telegram_chat_id` in `user_bindings`.
5. If mapping missing: writes `delivery_log` with `unmapped`, returns JSON status.
6. If mapping exists: sends fixed Telegram message, writes `delivery_log`.
7. Provides admin API to list/update/unbind/test `user_bindings`.
8. Polls Telegram updates and processes `/bind <code>` self-binding command.

## Storage

SQLite database with tables:

- `user_bindings`
- `delivery_log`

Schema file:

- `worker/bot_service/schema.sql`

## Run locally

```bash
cd /home/vehera/dev/kanban
cp worker/bot_service/.env.example worker/bot_service/.env
# edit worker/bot_service/.env
python3 worker/bot_service/main.py
```

## Deploy from PC to Raspberry Pi (SSH)

From local repo root:

```bash
./deploy_notify.sh --host kanboard-pi
```

Useful variants:

```bash
./deploy_notify.sh --skip-restart
./deploy_notify.sh --skip-plugin
./deploy_notify.sh --service assignee-notify-bot
```

This script syncs:

- `worker/bot_service/` -> `${REMOTE_ROOT}/worker/bot_service/`
- `plugins/AssigneeNotify/` -> `/var/www/kanboard/plugins/AssigneeNotify/` (unless `--skip-plugin`)

## Required env vars

- `BOT_SERVICE_SHARED_SECRET`
- `BOT_SERVICE_TELEGRAM_BOT_TOKEN`

See full list in `.env.example`.

## API contract

All endpoints require header:

- `X-Webhook-Token: <shared secret>`

### Request

Headers:

- `Content-Type: application/json`

Body:

```json
{
  "event_id": "uuid",
  "event_type": "assignee_changed",
  "task_id": 123,
  "kanboard_user_id": 45,
  "occurred_at": "2026-03-13T12:00:00Z",
  "old_assignee_user_id": null,
  "new_assignee_user_id": 45
}
```

### Responses

Delivered (`200`):

```json
{"ok": true, "status": "delivered"}
```

Unmapped (`200`):

```json
{"ok": false, "status": "unmapped"}
```

Unauthorized (`401`):

```json
{"ok": false, "status": "unauthorized"}
```

Bad request (`400`):

```json
{"ok": false, "status": "bad_request"}
```

Telegram failure (`502`):

```json
{"ok": false, "status": "telegram_error"}
```

## Bindings API (admin)

### `GET /api/v1/bindings`

Optional query param:

- `kanboard_user_id=<id>`

Response (`200`):

```json
{
  "ok": true,
  "status": "ok",
  "data": {
    "bindings": [
      {
        "id": 1,
        "kanboard_user_id": 2,
        "telegram_chat_id": "506566433",
        "is_active": true,
        "created_at": "2026-03-13T18:00:00+00:00",
        "updated_at": "2026-03-13T18:00:00+00:00"
      }
    ]
  }
}
```

### `POST /api/v1/bindings/upsert`

Body:

```json
{
  "kanboard_user_id": 2,
  "telegram_chat_id": "506566433",
  "is_active": true
}
```

Response (`200`): `{"ok": true, "status": "upserted", ...}`

Conflict (`409`) when `telegram_chat_id` is already active for another user:

```json
{
  "ok": false,
  "status": "chat_already_bound",
  "error": "telegram_chat_id already bound to kanboard_user_id=2",
  "data": {
    "telegram_chat_id": "506566433",
    "conflicting_user_id": 2
  }
}
```

### `POST /api/v1/bindings/unbind`

Body:

```json
{
  "kanboard_user_id": 2
}
```

Response (`200`): `{"ok": true, "status": "unbound", ...}`

### `POST /api/v1/bindings/test`

Body:

```json
{
  "kanboard_user_id": 2
}
```

Response:

- delivered (`200`): `{"ok": true, "status": "delivered"}`
- unmapped (`200`): `{"ok": false, "status": "unmapped"}`
- telegram error (`502`): `{"ok": false, "status": "telegram_error"}`

### `POST /api/v1/bindings/token/create`

Body:

```json
{
  "kanboard_user_id": 2
}
```

Response (`200`):

```json
{
  "ok": true,
  "status": "created",
  "data": {
    "code": "ABCD2345",
    "kanboard_user_id": 2,
    "expires_at": "2026-03-14T09:00:00+00:00"
  }
}
```

Use this code in Telegram:

```text
/bind ABCD2345
```

If the chat is already linked to another Kanboard user, `/bind` is rejected and bot replies with a conflict message.

## Manual test

1. Add mapping:

```bash
sqlite3 /var/www/kanboard/data/kanboard_bot_service.sqlite \
  "INSERT INTO user_bindings (kanboard_user_id, telegram_chat_id, is_active, created_at, updated_at) VALUES (45, '123456789', 1, datetime('now'), datetime('now'));"
```

2. Send test event:

```bash
curl -i -X POST http://127.0.0.1:8089/events/assignee-changed \
  -H 'Content-Type: application/json' \
  -H 'X-Webhook-Token: replace_with_shared_secret' \
  -d '{"event_id":"test-1","event_type":"assignee_changed","task_id":1,"kanboard_user_id":45,"occurred_at":"2026-03-13T12:00:00Z"}'
```

3. Check log rows:

```bash
sqlite3 /var/www/kanboard/data/kanboard_bot_service.sqlite "SELECT id,event_id,kanboard_user_id,send_status,error_message,created_at FROM delivery_log ORDER BY id DESC LIMIT 20;"
```

## Current limitations

- no background retry queue (direct send)
- single hardcoded Telegram message text
- one-chat-per-user binding model

## systemd unit example

Create `/etc/systemd/system/assignee-notify-bot.service`:

```ini
[Unit]
Description=Kanboard Assignee Notify Bot Service
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=www-data
Group=www-data
WorkingDirectory=/opt/autopdf
Environment=HOME=/var/www/kanboard/data
ExecStart=/opt/autopdf/.venv/bin/python /opt/autopdf/worker/bot_service/main.py
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

Enable and start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now assignee-notify-bot
sudo systemctl status assignee-notify-bot
journalctl -u assignee-notify-bot -f
```
