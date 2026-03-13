# AssigneeNotify plugin (Kanboard)

Kanboard plugin that tracks real assignee changes and forwards minimal events to external bot-service.

## Scope of current stage

- listens to task assignee events (`task.assignee_change`, `task.update`)
- listens to subtask update hook (`model:subtask:modification:prepare`)
- detects only real assignee change (`old_assignee_user_id != new_assignee_user_id`)
- writes event rows to SQLite table `notification_events`
- sends HTTP POST to bot-service with shared token (`X-Webhook-Token`)
- saves delivery result (`sent`, `failed`, `skipped`)
- does not break task save when bot-service is unavailable

## Install

1. Copy `plugins/AssigneeNotify` into Kanboard `plugins/`.
2. Set config in Kanboard `config.php` (recommended):

```php
<?php
const ASSIGNEE_NOTIFY_BOT_SERVICE_URL = 'http://127.0.0.1:8089/events/assignee-changed';
const ASSIGNEE_NOTIFY_SHARED_SECRET = 'replace_me';

// Optional overrides
// const ASSIGNEE_NOTIFY_EVENTS_DB_PATH = '/var/www/kanboard/data/assignee_notify.sqlite';
// const ASSIGNEE_NOTIFY_HTTP_TIMEOUT_SEC = 5;
// const ASSIGNEE_NOTIFY_RESPONSE_SNIPPET_LIMIT = 400;
```

3. Ensure Kanboard web user can write SQLite DB file path.
4. Enable plugin in Kanboard UI.

## Storage

SQLite DB path defaults to:

- `DATA_DIR/assignee_notify.sqlite`

Schema file:

- `Schema/notification_events.sql`

Main table:

- `notification_events`

## Outbound JSON payload

```json
{
  "event_id": "uuid",
  "event_type": "assignee_changed",
  "task_id": 123,
  "kanboard_user_id": 45,
  "occurred_at": "2026-03-13T12:00:00Z",
  "old_assignee_user_id": null,
  "new_assignee_user_id": 45,
  "subtask_id": 77,
  "source": "subtask"
}
```

## Notes

- No task title/description/project metadata is sent.
- `unchanged` and `both_null` events are ignored (no delivery).
- `old=user, new=null` is recorded as `skipped` and not delivered.
