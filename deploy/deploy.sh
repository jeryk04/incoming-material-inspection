#!/usr/bin/env bash
# deploy.sh — pull latest changes and restart services
# Usage (from anywhere on the server):  bash /path/to/project/deploy/deploy.sh

set -e

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

echo "=== QC Inspection — Deploy ==="

echo "Pulling latest changes..."
git -C "$PROJECT_DIR" pull

echo "Updating dependencies..."
"$PROJECT_DIR/.venv/bin/pip" install --quiet -r "$PROJECT_DIR/requirements.txt"

echo "Restarting services..."
sudo systemctl restart qc-watcher qc-dashboard

echo
echo "=== Done ==="
sudo systemctl status qc-watcher qc-dashboard --no-pager -l
