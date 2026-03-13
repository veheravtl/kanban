CREATE TABLE IF NOT EXISTS user_bindings (
    id INTEGER PRIMARY KEY,
    kanboard_user_id INTEGER NOT NULL UNIQUE,
    telegram_chat_id TEXT NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS delivery_log (
    id INTEGER PRIMARY KEY,
    event_id TEXT NOT NULL,
    kanboard_user_id INTEGER NOT NULL,
    telegram_chat_id TEXT,
    message_type TEXT NOT NULL,
    send_status TEXT NOT NULL,
    telegram_message_id TEXT,
    error_message TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_delivery_log_event_id
    ON delivery_log(event_id);

CREATE INDEX IF NOT EXISTS idx_delivery_log_status_created
    ON delivery_log(send_status, created_at);
