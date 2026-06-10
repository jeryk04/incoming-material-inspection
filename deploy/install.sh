#!/usr/bin/env bash
# install.sh — first-time setup on the server
# Run once as a user with sudo access:  bash deploy/install.sh

set -e

# ── Configuration ────────────────────────────────────────────────────────────
PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"   # repo root (auto-detected)
APP_USER="${SUDO_USER:-$USER}"                     # user that will run the services
PYTHON="${PYTHON:-python3}"
# ─────────────────────────────────────────────────────────────────────────────

echo "=== QC Inspection — First-time install ==="
echo "  Project dir : $PROJECT_DIR"
echo "  Service user: $APP_USER"
echo

# 1. Virtual environment
if [ ! -d "$PROJECT_DIR/.venv" ]; then
    echo "Creating virtual environment..."
    "$PYTHON" -m venv "$PROJECT_DIR/.venv"
fi

echo "Installing Python dependencies..."
"$PROJECT_DIR/.venv/bin/pip" install --quiet --upgrade pip
"$PROJECT_DIR/.venv/bin/pip" install --quiet -r "$PROJECT_DIR/requirements.txt"

# 2. .env — copy example if no real .env exists yet
if [ ! -f "$PROJECT_DIR/.env" ]; then
    cp "$PROJECT_DIR/.env.example" "$PROJECT_DIR/.env"
    echo
    echo "  *** .env created from .env.example"
    echo "  *** Edit $PROJECT_DIR/.env and set your API keys and folder paths, then re-run:"
    echo "  ***   sudo systemctl start qc-watcher qc-dashboard"
    echo
fi

# 3. Inject the real PROJECT_DIR and APP_USER into the service files, then install them
for SERVICE in qc-watcher qc-dashboard; do
    sed \
        -e "s|__PROJECT_DIR__|$PROJECT_DIR|g" \
        -e "s|__APP_USER__|$APP_USER|g" \
        "$PROJECT_DIR/deploy/$SERVICE.service" \
        | sudo tee "/etc/systemd/system/$SERVICE.service" > /dev/null
    echo "Installed /etc/systemd/system/$SERVICE.service"
done

# 4. Enable and start
sudo systemctl daemon-reload
sudo systemctl enable qc-watcher qc-dashboard
sudo systemctl start  qc-watcher qc-dashboard

echo
echo "=== Done ==="
echo "  Dashboard : http://$(hostname -I | awk '{print $1}'):5000"
echo "  Status    : sudo systemctl status qc-watcher qc-dashboard"
echo "  Logs      : journalctl -u qc-watcher -u qc-dashboard -f"
