CREATE TABLE IF NOT EXISTS conversion_queue (
    id INTEGER PRIMARY KEY,
    file_id INTEGER NOT NULL UNIQUE,
    task_id INTEGER NOT NULL,
    project_id INTEGER,
    original_name TEXT NOT NULL,
    target_name TEXT NOT NULL,
    status TEXT NOT NULL,
    retry_count INTEGER NOT NULL DEFAULT 0,
    last_error TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_conversion_queue_status_id
    ON conversion_queue(status, id);
