#!/usr/bin/env bash
# install.sh — first-time setup on the server (idempotent; safe to re-run).
# Run as a user with sudo access:  bash deploy/install.sh
#
# Glues together:
#   1. the OLD_DATA SMB mount (deploy/setup-old-data-mount.sh)
#   2. the Python virtualenv + dependencies
#   3. the .env file
#   4. ownership for the service user
#   5. the systemd units (qc-watcher, qc-dashboard)

set -euo pipefail

# ── Configuration ────────────────────────────────────────────────────────────
PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"   # repo root (auto-detected)
SERVICE_USER="gjsteel"                             # must match the SMB mount uid/gid
SERVICE_GROUP="gjsteel"
PYTHON="${PYTHON:-python3}"
# ─────────────────────────────────────────────────────────────────────────────

echo "=== QC Inspection — First-time install ==="
echo "  Project dir  : $PROJECT_DIR"
echo "  Service user : $SERVICE_USER"
echo

# 0. The service user must already exist — it owns the SMB mount (uid/gid).
if ! id "$SERVICE_USER" >/dev/null 2>&1; then
    echo "ERROR: user '$SERVICE_USER' does not exist." >&2
    echo "       It must match the SMB mount uid/gid (same as the GJSteel deploy)." >&2
    echo "       Create it first, then re-run this script." >&2
    exit 1
fi

# 1. Mount the OLD_DATA share (installs cifs-utils, writes fstab, mounts).
#    Needs root; run via sudo. Aborts here if credentials aren't set yet.
echo "Setting up the OLD_DATA SMB share..."
sudo bash "$PROJECT_DIR/deploy/setup-old-data-mount.sh"
echo

# 2. System package needed to create a virtualenv on a fresh Ubuntu box.
if ! "$PYTHON" -m venv --help >/dev/null 2>&1; then
    echo "Installing python3-venv..."
    sudo apt-get update -qq
    sudo apt-get install -y python3-venv
fi

# 3. Virtual environment + dependencies.
if [ ! -d "$PROJECT_DIR/.venv" ]; then
    echo "Creating virtual environment..."
    "$PYTHON" -m venv "$PROJECT_DIR/.venv"
fi

echo "Installing Python dependencies..."
"$PROJECT_DIR/.venv/bin/pip" install --quiet --upgrade pip
"$PROJECT_DIR/.venv/bin/pip" install --quiet -r "$PROJECT_DIR/requirements.txt"

# 4. .env — copy the example on first run. Track whether it was just created so
#    we don't start the services with empty API keys / paths (crash loop).
ENV_WAS_CREATED=0
if [ ! -f "$PROJECT_DIR/.env" ]; then
    cp "$PROJECT_DIR/.env.example" "$PROJECT_DIR/.env"
    ENV_WAS_CREATED=1
    echo "  *** .env created from .env.example — must be edited before the services will work."
fi

# 5. Ownership — the services run as $SERVICE_USER, so it must own the repo + venv.
echo "Setting ownership to $SERVICE_USER:$SERVICE_GROUP..."
sudo chown -R "$SERVICE_USER:$SERVICE_GROUP" "$PROJECT_DIR"

# 6. Install the systemd units (inject the real project dir).
for SERVICE in qc-watcher qc-dashboard; do
    sed -e "s|__PROJECT_DIR__|$PROJECT_DIR|g" \
        "$PROJECT_DIR/deploy/$SERVICE.service" \
        | sudo tee "/etc/systemd/system/$SERVICE.service" > /dev/null
    echo "Installed /etc/systemd/system/$SERVICE.service"
done

sudo systemctl daemon-reload
sudo systemctl enable qc-watcher qc-dashboard

# 7. Start now only if .env is already configured.
if [ "$ENV_WAS_CREATED" -eq 1 ]; then
    echo
    echo "=== Almost done ==="
    echo "  Edit $PROJECT_DIR/.env (API key + folder paths), then start the services:"
    echo "    sudo systemctl start qc-watcher qc-dashboard"
else
    sudo systemctl restart qc-watcher qc-dashboard
    PORT="$(grep -E '^DASHBOARD_PORT=' "$PROJECT_DIR/.env" | cut -d= -f2)"
    PORT="${PORT:-5000}"
    echo
    echo "=== Done ==="
    echo "  Dashboard : http://$(hostname -I | awk '{print $1}'):$PORT"
fi

echo "  Status    : sudo systemctl status qc-watcher qc-dashboard"
echo "  Logs      : journalctl -u qc-watcher -u qc-dashboard -f"
