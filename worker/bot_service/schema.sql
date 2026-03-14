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

CREATE TABLE IF NOT EXISTS binding_tokens (
    token TEXT PRIMARY KEY,
    kanboard_user_id INTEGER NOT NULL,
    is_used INTEGER NOT NULL DEFAULT 0,
    expires_at TEXT NOT NULL,
    used_at TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_binding_tokens_user
    ON binding_tokens(kanboard_user_id);

CREATE INDEX IF NOT EXISTS idx_binding_tokens_expires
    ON binding_tokens(expires_at);
