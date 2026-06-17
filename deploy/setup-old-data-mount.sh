#!/usr/bin/env bash
# setup-old-data-mount.sh — ensure the OLD_DATA SMB share is mounted (idempotent).
#
# Run ONCE during server setup, as root:
#     sudo bash deploy/setup-old-data-mount.sh
#
# Safe to re-run any time: it always makes sure the /etc/fstab entry exists
# (needed for persistence across reboots AND for the systemd .mount unit that
# qc-watcher/qc-dashboard depend on), then mounts the share only if it isn't
# already mounted.
#
# IMPORTANT: this needs root (mount / fstab / apt). Do NOT call it from a
# service's ExecStartPre — the services run as the unprivileged 'gjsteel' user
# and cannot mount. Once fstab is set up, systemd auto-mounts on every boot.

set -euo pipefail

# ── Configuration ────────────────────────────────────────────────────────────
SHARE="//10.0.0.35/OLD_DATA"
MOUNT_POINT="/mnt/gjsteel-old-data"
CREDS_FILE="/etc/gjsteel-smb-credentials"   # reused from the GJSteel setup
MOUNT_UID="gjsteel"
MOUNT_GID="gjsteel"
OPTS="credentials=${CREDS_FILE},uid=${MOUNT_UID},gid=${MOUNT_GID},file_mode=0664,dir_mode=0775,iocharset=utf8,nofail,_netdev"
# ─────────────────────────────────────────────────────────────────────────────

if [ "$(id -u)" -ne 0 ]; then
    echo "ERROR: must run as root:  sudo bash $0" >&2
    exit 1
fi

echo "=== OLD_DATA share mount setup ==="
echo "  Share : $SHARE"
echo "  Mount : $MOUNT_POINT"
echo

# 1. cifs-utils present?
if ! command -v mount.cifs >/dev/null 2>&1; then
    echo "Installing cifs-utils..."
    apt-get update -qq
    apt-get install -y cifs-utils
fi

# 2. mount point
mkdir -p "$MOUNT_POINT"

# 3. credentials — never hardcode them here; reuse the existing file or stop.
if [ ! -f "$CREDS_FILE" ]; then
    echo "Credentials file $CREDS_FILE not found — creating a template."
    cat > "$CREDS_FILE" <<'EOF'
username=CHANGE_ME
password=CHANGE_ME
domain=GJSTEEL
EOF
    chmod 600 "$CREDS_FILE"
    echo "ERROR: edit $CREDS_FILE with the real SMB credentials, then re-run this script." >&2
    exit 1
fi

# 4. fstab entry — always ensure it exists (persistence + the systemd .mount unit).
if grep -qsE "[[:space:]]${MOUNT_POINT}[[:space:]]" /etc/fstab; then
    echo "fstab already has an entry for $MOUNT_POINT — leaving it unchanged."
else
    echo "Adding fstab entry..."
    printf '%s %s cifs %s 0 0\n' "$SHARE" "$MOUNT_POINT" "$OPTS" >> /etc/fstab
    # Regenerate the mnt-gjsteel\x2dold\x2ddata.mount unit the services depend on.
    systemctl daemon-reload
fi

# 5. mount now if not already mounted
if mountpoint -q "$MOUNT_POINT"; then
    echo "Already mounted — nothing to mount."
else
    echo "Mounting..."
    mount "$MOUNT_POINT"
fi

# 6. verify
if mountpoint -q "$MOUNT_POINT"; then
    echo
    echo "SUCCESS: $SHARE is mounted at $MOUNT_POINT"
    ls -la "$MOUNT_POINT" | head -20
else
    echo
    echo "ERROR: mount failed. Try manually:" >&2
    echo "  mount -t cifs $SHARE $MOUNT_POINT -o $OPTS" >&2
    exit 1
fi
