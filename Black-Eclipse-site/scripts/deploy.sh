#!/usr/bin/env bash
# ── BlackEclipse auto-deploy (server side) ───────────────────────────────────
# Pull origin/main and rebuild the production container ONLY when the commit
# actually changed. Safe to run from a systemd timer or cron every few minutes:
# an unchanged commit exits immediately, and a lock prevents overlapping runs.
#
#   ./deploy.sh            # update if origin/main moved
#   ./deploy.sh --force    # rebuild the current commit anyway
#
# Config (optional):
#   BE_APP_DIR       app directory (default: the parent of this script)
#   BE_DEPLOY_BRANCH branch to track (default: main)
#   BE_HEALTH_PORT   host port for the health check (default: 3000)
#   BE_DEPLOY_LOCK   lock file (default: /tmp/blackeclipse-deploy.lock)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="${BE_APP_DIR:-$(cd "$SCRIPT_DIR/.." && pwd)}"
BRANCH="${BE_DEPLOY_BRANCH:-main}"
HEALTH_PORT="${BE_HEALTH_PORT:-3000}"
FORCE=""
for arg in "$@"; do
  case "$arg" in
    --force|-f) FORCE="1" ;;
    *) echo "unknown argument: $arg" >&2; exit 2 ;;
  esac
done

log() { printf '%s %s\n' "$(date -u +%FT%TZ)" "$*"; }

GIT_ROOT="$(git -C "$APP_DIR" rev-parse --show-toplevel 2>/dev/null || true)"
if [ -z "$GIT_ROOT" ]; then
  log "not a git checkout: $APP_DIR"
  exit 1
fi

LOCK="${BE_DEPLOY_LOCK:-/tmp/blackeclipse-deploy.lock}"
if command -v flock >/dev/null 2>&1; then
  exec 9>"$LOCK"
  if ! flock -n 9; then
    log "another deploy is already running; skipping"
    exit 0
  fi
fi

cd "$GIT_ROOT"
git fetch --quiet origin "$BRANCH"
LOCAL="$(git rev-parse HEAD)"
REMOTE="$(git rev-parse "origin/$BRANCH")"

if [ "$LOCAL" = "$REMOTE" ] && [ "$FORCE" != "1" ]; then
  log "up to date at ${LOCAL:0:8}; nothing to do"
  exit 0
fi

if ! git diff --quiet || ! git diff --cached --quiet; then
  log "refusing: tracked local changes in $GIT_ROOT — commit or stash them first"
  exit 1
fi

log "updating ${LOCAL:0:8} -> ${REMOTE:0:8}"
git pull --ff-only origin "$BRANCH"

cd "$APP_DIR"
if [ ! -f docker-compose.yml ] && [ ! -f docker-compose.yaml ]; then
  log "no docker-compose file in $APP_DIR"
  exit 1
fi

# The security preflight only runs when a Node toolchain is present on the host.
# In a Docker-only deploy the container carries its own runtime.
if command -v node >/dev/null 2>&1 && [ -d node_modules ]; then
  npm run security:preflight
fi

docker compose up -d --build

log "container rebuilt; waiting for the health route"
for _ in $(seq 1 90); do
  if curl -fsS "http://127.0.0.1:${HEALTH_PORT}/login" >/dev/null 2>&1; then
    log "healthy at ${HEALTH_PORT}; deployed $(git -C "$GIT_ROOT" rev-parse --short HEAD)"
    exit 0
  fi
  sleep 2
done

log "health check failed after 180s; inspect: docker compose logs --tail=100 app"
exit 1
