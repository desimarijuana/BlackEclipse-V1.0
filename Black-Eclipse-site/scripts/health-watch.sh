#!/usr/bin/env bash
# ── BlackEclipse health watch ───────────────────────────────────────────────
# Polls the public health surface and, when it is not answering, sends the alert
# to a channel a human actually reads. Designed for a cron entry or a systemd
# timer on the server (see docs/DEPLOYMENT.md "Monitoring & alerts").
#
#   HEALTH_URL=http://127.0.0.1:3000/login \
#   ALERT_WEBHOOK_URL=https://hooks.slack.com/services/... \
#     scripts/health-watch.sh
#
# Exit 0 = healthy. Exit 1 = unhealthy (and, with a webhook, alerted).
# No webhook is a WARN on stderr only: the repo cannot choose a person's channel
# for them. The Windows health-task wrapper turns this exit code into a desktop
# notification; on Linux, wire this script to your alertmanager/on-call route.
set -euo pipefail

HEALTH_URL="${HEALTH_URL:-http://127.0.0.1:3000/login}"
ALERT_WEBHOOK_URL="${ALERT_WEBHOOK_URL:-}"
HEALTH_TIMEOUT="${HEALTH_TIMEOUT:-10}"
ALERT_SOURCE="${ALERT_SOURCE:-$(hostname 2>/dev/null || echo blackeclipse)}"

if ! command -v curl >/dev/null 2>&1; then
  echo "curl is required" >&2
  exit 2
fi

CODE="$(curl -s -o /dev/null -w '%{http_code}' --max-time "$HEALTH_TIMEOUT" "$HEALTH_URL" || true)"
case "$CODE" in
  2??|3??)
    echo "healthy: $HEALTH_URL -> $CODE"
    exit 0
    ;;
esac

MESSAGE="BlackEclipse is unhealthy on ${ALERT_SOURCE}: ${HEALTH_URL} -> ${CODE:-no response}"
echo "ALERT: $MESSAGE" >&2

if [ -z "$ALERT_WEBHOOK_URL" ]; then
  echo "no ALERT_WEBHOOK_URL set; the local wrapper (if any) owns the human alert" >&2
  exit 1
fi

# Slack-compatible JSON; Teams/Discord webhooks accept the same `text` field.
# Escape the message BEFORE it is placed inside the JSON string.
ESCAPED="$(printf '%s' "$MESSAGE" | sed 's/\\/\\\\/g; s/"/\\"/g')"
PAYLOAD="$(printf '{"text": "%s"}' "$ESCAPED")"
if curl -sS -o /dev/null --max-time "$HEALTH_TIMEOUT" \
    -H 'Content-Type: application/json' \
    -d "$PAYLOAD" "$ALERT_WEBHOOK_URL"; then
  echo "alert delivered" >&2
else
  echo "alert delivery FAILED" >&2
fi

exit 1
