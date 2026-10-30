#!/usr/bin/env bash
# ── Install BlackEclipse auto-deploy on this server (run once, with sudo) ────
# Creates a systemd timer that runs scripts/deploy.sh every 5 minutes. The
# deploy script no-ops when origin/main has not moved, so this is cheap.
#
#   sudo bash scripts/install-autodeploy.sh
#   sudo bash scripts/install-autodeploy.sh --interval 2   # minutes
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
  echo "run with sudo: sudo bash $0" >&2
  exit 1
fi

INTERVAL=5
while [ $# -gt 0 ]; do
  case "$1" in
    --interval) INTERVAL="${2:?missing minutes}"; shift 2 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
DEPLOY="$APP_DIR/scripts/deploy.sh"

if [ ! -f "$DEPLOY" ]; then
  echo "deploy script not found: $DEPLOY" >&2
  exit 1
fi
chmod +x "$DEPLOY"

cat > /etc/systemd/system/blackeclipse-deploy.service <<EOF
[Unit]
Description=BlackEclipse auto-deploy
Wants=network-online.target
After=network-online.target docker.service

[Service]
Type=oneshot
WorkingDirectory=$APP_DIR
ExecStart=$DEPLOY
EOF

cat > /etc/systemd/system/blackeclipse-deploy.timer <<EOF
[Unit]
Description=Check origin/main for BlackEclipse updates

[Timer]
OnBootSec=2min
OnUnitActiveSec=${INTERVAL}min
Persistent=true

[Install]
WantedBy=timers.target
EOF

systemctl daemon-reload
systemctl enable --now blackeclipse-deploy.timer

echo "Auto-deploy installed for $APP_DIR (every ${INTERVAL} min)."
echo "Deploying the current origin/main now..."
systemctl start blackeclipse-deploy.service || true

echo
echo "Status:  systemctl status blackeclipse-deploy.timer"
echo "Logs:    journalctl -u blackeclipse-deploy -f"
echo "Manual:  $DEPLOY --force"
