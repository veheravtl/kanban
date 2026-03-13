#!/usr/bin/env bash
set -euo pipefail

usage() {
    cat <<'USAGE'
Usage:
  ./deploy_notify.sh [options]

Options:
  --host <ssh-host>         SSH host from ~/.ssh/config (default: kanboard-pi)
  --remote-root <path>      Remote root directory for bot-service files (default: /opt/autopdf)
  --service <name>          systemd service name for bot-service (default: assignee-notify-bot)
  --skip-restart            Do not restart systemd service after sync
  --skip-plugin             Do not deploy Kanboard plugin (only bot-service)
  -h, --help                Show this help

Examples:
  ./deploy_notify.sh
  ./deploy_notify.sh --host kanboard-pi --service assignee-notify-bot
  ./deploy_notify.sh --skip-restart
USAGE
}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOST="kanboard-pi"
REMOTE_ROOT="/opt/autopdf"
SERVICE_NAME="assignee-notify-bot"
SKIP_RESTART=0
SKIP_PLUGIN=0

while [[ $# -gt 0 ]]; do
    case "$1" in
        --host)
            HOST="${2:-}"
            shift 2
            ;;
        --remote-root)
            REMOTE_ROOT="${2:-}"
            shift 2
            ;;
        --service)
            SERVICE_NAME="${2:-}"
            shift 2
            ;;
        --skip-restart)
            SKIP_RESTART=1
            shift
            ;;
        --skip-plugin)
            SKIP_PLUGIN=1
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "Unknown argument: $1" >&2
            usage
            exit 2
            ;;
    esac
done

if [[ -z "$HOST" || -z "$REMOTE_ROOT" || -z "$SERVICE_NAME" ]]; then
    echo "Error: --host, --remote-root and --service must not be empty." >&2
    exit 2
fi

require_cmd() {
    local cmd="$1"
    if ! command -v "$cmd" >/dev/null 2>&1; then
        echo "Required command not found: $cmd" >&2
        exit 2
    fi
}

require_path() {
    local p="$1"
    if [[ ! -e "$p" ]]; then
        echo "Missing required path: $p" >&2
        exit 2
    fi
}

require_cmd ssh
require_cmd rsync

require_path "$SCRIPT_DIR/worker/bot_service"
require_path "$SCRIPT_DIR/worker/requirements.txt"

if [[ $SKIP_PLUGIN -eq 0 ]]; then
    require_path "$SCRIPT_DIR/plugins/AssigneeNotify"
fi

echo "==> Preflight: SSH connectivity (${HOST})"
ssh "$HOST" "echo connected: \$(hostname)"

echo "==> Ensure remote directories exist"
ssh -t "$HOST" "sudo mkdir -p '$REMOTE_ROOT/worker/bot_service' '$REMOTE_ROOT/worker'"

echo "==> Sync bot-service files"
rsync -av --delete --timeout=30 \
    --exclude '.env' \
    --exclude '*.sqlite' \
    --exclude '*.sqlite3' \
    --exclude '*.log' \
    --exclude 'nohup.log' \
    --exclude '__pycache__/' \
    "$SCRIPT_DIR/worker/bot_service/" \
    "$HOST:$REMOTE_ROOT/worker/bot_service/"

echo "==> Sync worker requirements (shared venv deps)"
rsync -av --timeout=30 \
    "$SCRIPT_DIR/worker/requirements.txt" \
    "$HOST:$REMOTE_ROOT/worker/"

if [[ $SKIP_PLUGIN -eq 0 ]]; then
    echo "==> Sync AssigneeNotify plugin"
    rsync -av --delete --timeout=30 \
        "$SCRIPT_DIR/plugins/AssigneeNotify/" \
        "$HOST:/tmp/AssigneeNotify/"

    ssh -t "$HOST" \
        "sudo install -d /var/www/kanboard/plugins/AssigneeNotify && sudo rsync -a /tmp/AssigneeNotify/ /var/www/kanboard/plugins/AssigneeNotify/"
fi

if [[ $SKIP_RESTART -eq 1 ]]; then
    echo "==> Skip service restart (--skip-restart)"
    exit 0
fi

echo "==> Restart service: ${SERVICE_NAME}"
ssh -t "$HOST" "sudo systemctl restart '$SERVICE_NAME' && sudo systemctl status --no-pager '$SERVICE_NAME'"

echo "==> Deployment completed"
