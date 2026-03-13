#!/usr/bin/env bash
set -euo pipefail

usage() {
    cat <<'EOF'
Usage:
  ./deploy_worker.sh [options]

Options:
  --host <ssh-host>         SSH host from ~/.ssh/config (default: kanboard-pi)
  --remote-root <path>      Remote root directory for worker files (default: /opt/autopdf)
  --service <name>          systemd service name (default: autopdf-worker)
  --with-plugin             Also deploy plugins/AutoPdf to Kanboard plugins directory
  --skip-restart            Do not restart systemd service after file sync
  -h, --help                Show this help

Examples:
  ./deploy_worker.sh
  ./deploy_worker.sh --host kanboard-pi --with-plugin
  ./deploy_worker.sh --skip-restart
EOF
}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOST="kanboard-pi"
REMOTE_ROOT="/opt/autopdf"
SERVICE_NAME="autopdf-worker"
WITH_PLUGIN=0
SKIP_RESTART=0

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
        --with-plugin)
            WITH_PLUGIN=1
            shift
            ;;
        --skip-restart)
            SKIP_RESTART=1
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

require_path() {
    local p="$1"
    if [[ ! -e "$p" ]]; then
        echo "Missing required path: $p" >&2
        exit 2
    fi
}

require_cmd() {
    local cmd="$1"
    if ! command -v "$cmd" >/dev/null 2>&1; then
        echo "Required command not found: $cmd" >&2
        exit 2
    fi
}

require_cmd ssh
require_cmd rsync

require_path "$SCRIPT_DIR/worker"
require_path "$SCRIPT_DIR/exel2pdf.py"
require_path "$SCRIPT_DIR/schema.sql"

if [[ $WITH_PLUGIN -eq 1 ]]; then
    require_path "$SCRIPT_DIR/plugins/AutoPdf"
fi

echo "==> Preflight: SSH connectivity (${HOST})"
ssh "$HOST" "echo connected: \$(hostname)"

echo "==> Ensure remote directories exist"
ssh -t "$HOST" "sudo mkdir -p '$REMOTE_ROOT' '$REMOTE_ROOT/worker'"

echo "==> Sync worker directory"
rsync -av --delete --timeout=30 \
    "$SCRIPT_DIR/worker/" \
    "$HOST:$REMOTE_ROOT/worker/"

echo "==> Sync exel2pdf.py and schema.sql"
rsync -av --timeout=30 \
    "$SCRIPT_DIR/exel2pdf.py" \
    "$SCRIPT_DIR/schema.sql" \
    "$HOST:$REMOTE_ROOT/"

if [[ $WITH_PLUGIN -eq 1 ]]; then
    echo "==> Sync AutoPdf plugin"
    rsync -av --delete --timeout=30 \
        "$SCRIPT_DIR/plugins/AutoPdf/" \
        "$HOST:/tmp/AutoPdf/"

    ssh -t "$HOST" \
        "sudo install -d /var/www/kanboard/plugins/AutoPdf && sudo rsync -a /tmp/AutoPdf/ /var/www/kanboard/plugins/AutoPdf/"
fi

if [[ $SKIP_RESTART -eq 1 ]]; then
    echo "==> Skip service restart (--skip-restart)"
    exit 0
fi

echo "==> Restart service: ${SERVICE_NAME}"
ssh -t "$HOST" "sudo systemctl restart '$SERVICE_NAME' && sudo systemctl status --no-pager '$SERVICE_NAME'"

echo "==> Deployment completed"
