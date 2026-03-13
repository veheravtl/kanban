# AutoPdf worker

External Python worker for Kanboard that converts Office task attachments to PDF asynchronously.

## Behavior

1. Claims `pending` row from SQLite queue (`conversion_queue`) and sets it to `processing` atomically.
2. Reads file metadata via `getTaskFile`.
3. Downloads file via `downloadTaskFile` (base64).
4. Converts to PDF using adapter:
   - `.xls/.xlsx/.xlsm/.docx` -> existing `exel2pdf.py`
   - `.doc` -> LibreOffice fallback
5. Validates PDF (`exists`, `size > 0`, header `%PDF`).
6. Uploads PDF via `createTaskFile`.
7. Removes original via `removeTaskFile` only after successful upload.
8. Sets queue status:
   - `done` on full success
   - `partial_error` if PDF uploaded but source deletion failed
   - retry (`pending`) or `error` for other failures

## Files

- `config.py` - env config loader
- `queue_db.py` - SQLite queue operations with locking
- `kanboard_api.py` - JSON-RPC client
- `converter_adapter.py` - wrapper for existing converter + `.doc` fallback
- `worker.py` - main loop
- `.env.example` - sample config
- `requirements.txt` - Python dependencies

## Quick setup (Raspberry Pi)

1. Install packages:

```bash
sudo apt update
sudo apt install -y python3 python3-venv libreoffice libreoffice-writer
```

2. Copy project files to Pi (example path):

```bash
sudo mkdir -p /opt/autopdf
sudo chown -R $USER:$USER /opt/autopdf
# then copy files into /opt/autopdf
```

3. Create virtualenv and install deps:

```bash
cd /opt/autopdf
python3 -m venv .venv
source .venv/bin/activate
pip install -r worker/requirements.txt
```

4. Configure worker env:

```bash
cp worker/.env.example worker/.env
# edit worker/.env: KANBOARD_URL, KANBOARD_API_TOKEN, paths
```

5. Make sure queue DB path is writable by both:
   - Kanboard web user (`www-data` usually)
   - worker user (service account)

6. Run once manually:

```bash
cd /opt/autopdf
source .venv/bin/activate
python worker/worker.py
```

## Minimal checks

- Queue DB exists:

```bash
ls -l /var/www/kanboard/data/autopdf_queue.sqlite
```

- Schema exists:

```bash
sqlite3 /var/www/kanboard/data/autopdf_queue.sqlite ".schema conversion_queue"
```

- Queue state:

```bash
sqlite3 /var/www/kanboard/data/autopdf_queue.sqlite "SELECT id,file_id,status,retry_count,last_error FROM conversion_queue ORDER BY id DESC LIMIT 20;"
```

- Worker log:

```bash
tail -f /var/www/kanboard/data/autopdf-worker.log
```

## Fast deploy from PC

From local project root (`/home/vehera/dev/kanban`):

```bash
./deploy_worker.sh
```

Useful variants:

```bash
./deploy_worker.sh --with-plugin
./deploy_worker.sh --skip-restart
./deploy_worker.sh --host kanboard-pi
```

## systemd unit example

Create `/etc/systemd/system/autopdf-worker.service`:

```ini
[Unit]
Description=Kanboard AutoPdf Worker
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=www-data
Group=www-data
WorkingDirectory=/opt/autopdf
Environment=HOME=/var/www/kanboard/data
ExecStart=/opt/autopdf/.venv/bin/python /opt/autopdf/worker/worker.py
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

Enable and start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now autopdf-worker
sudo systemctl status autopdf-worker
journalctl -u autopdf-worker -f
```
