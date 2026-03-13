CREATE TABLE IF NOT EXISTS notification_events (
    id INTEGER PRIMARY KEY,
    event_uuid TEXT NOT NULL UNIQUE,
    event_type TEXT NOT NULL,
    task_id INTEGER NOT NULL,
    old_assignee_user_id INTEGER,
    new_assignee_user_id INTEGER,
    created_at TEXT NOT NULL,
    delivery_status TEXT NOT NULL,
    delivery_attempted_at TEXT,
    delivery_http_status INTEGER,
    delivery_error_message TEXT,
    raw_response_snippet TEXT
);

CREATE INDEX IF NOT EXISTS idx_notification_events_status_id
    ON notification_events(delivery_status, id);

CREATE INDEX IF NOT EXISTS idx_notification_events_task_id
    ON notification_events(task_id);
