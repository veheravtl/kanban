# AutoPdf plugin (Kanboard)

Lightweight Kanboard plugin that listens to `task.file.create` and puts supported Office files into a SQLite queue for asynchronous conversion.

## What it does

- Subscribes to `task.file.create`
- Filters files by extension: `.doc`, `.docx`, `.xls`, `.xlsx`, `.xlsm`
- Ignores `.pdf` and unsupported files
- Inserts queue item with `INSERT OR IGNORE` (by unique `file_id`)
- Does **not** convert files in PHP

## Queue database

Default path:

- `DATA_DIR/autopdf_queue.sqlite`

Optional custom path (in Kanboard `config.php`):

```php
<?php
const AUTOPDF_QUEUE_DB = '/var/www/kanboard/data/autopdf_queue.sqlite';
```

Table schema is compatible with `schema.sql` in project root.

## Install

1. Copy folder `plugins/AutoPdf` into Kanboard `plugins/`.
2. Ensure web server user can write queue DB path.
3. Enable plugin in Kanboard UI (if not auto-enabled).
4. Start external Python worker (see `worker/README.md`).

## Notes

- This plugin is intentionally minimal and safe for HTTP request path.
- Heavy conversion and API operations are done by external worker only.
