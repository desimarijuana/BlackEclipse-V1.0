#!/usr/bin/env bash
# ── Install BlackEclipse nightly backups on this server (run once, with sudo) ─
# Creates a systemd timer that runs scripts/backup.sh once a day and keeps the
# newest N archives out of the box.
#
#   sudo bash scripts/install-backup-timer.sh
#   sudo bash scripts/install-backup-timer.sh --time 02:30 --keep 30
#   sudo bash scripts/install-backup-timer.sh --data-dir /data --out /var/backups/blackeclipse
#
# When the app runs in the container, the data lives in the `be-data` volume;
# install this timer on the HOST and point --data-dir at that volume's path (or
# back up /var/lib/docker/volumes/...), or run the same script inside a cron
# job on any host that can read the data directory.
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
  echo "run with sudo: sudo bash $0" >&2
  exit 1
fi

TIME="03:15"
KEEP="14"
DATA_DIR=""
OUT_DIR=""
while [ $# -gt 0 ]; do
  case "$1" in
    --time)     TIME="${2:?missing HH:MM}"; shift 2 ;;
    --keep)     KEEP="${2:?missing count}"; shift 2 ;;
    --data-dir) DATA_DIR="${2:?missing directory}"; shift 2 ;;
    --out)      OUT_DIR="${2:?missing directory}"; shift 2 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
BACKUP="$APP_DIR/scripts/backup.sh"

if [ ! -f "$BACKUP" ]; then
  echo "backup script not found: $BACKUP" >&2
  exit 1
fi
chmod +x "$BACKUP"

ENV_LINES=""
[ -n "$DATA_DIR" ] && ENV_LINES="${ENV_LINES}Environment=BE_DATA_DIR=$DATA_DIR"$'\n'
[ -n "$OUT_DIR" ]  && ENV_LINES="${ENV_LINES}Environment=BE_BACKUP_DIR=$OUT_DIR"$'\n'
ENV_LINES="${ENV_LINES}Environment=BE_BACKUP_KEEP=$KEEP"

cat > /etc/systemd/system/blackeclipse-backup.service <<EOF
[Unit]
Description=BlackEclipse data backup
After=network-online.target

[Service]
Type=oneshot
WorkingDirectory=$APP_DIR
${ENV_LINES}
ExecStart=$BACKUP
Nice=10
IOSchedulingClass=best-effort
EOF

cat > /etc/systemd/system/blackeclipse-backup.timer <<EOF
[Unit]
Description=Nightly BlackEclipse data backup

[Timer]
OnCalendar=*-*-* ${TIME}:00
Persistent=true
RandomizedDelaySec=15min

[Install]
WantedBy=timers.target
EOF

systemctl daemon-reload
systemctl enable --now blackeclipse-backup.timer

echo "Nightly backup installed for $APP_DIR at ${TIME} (keep ${KEEP})."
echo
echo "Status:  systemctl status blackeclipse-backup.timer"
echo "Logs:    journalctl -u blackeclipse-backup -f"
echo "Manual:  $BACKUP"
