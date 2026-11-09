#!/usr/bin/env bash
# ── BlackEclipse data backup ────────────────────────────────────────────────
# One consistent archive of the data that must survive a host loss:
#
#   jdds.db, agent-memory.db, eclipse-memory.db   (via the SQLite backup API,
#                                                   safe while the app writes)
#   .black-eclipse/                                (auth db, artifacts, sessions,
#                                                   plugins, backups excluded)
#
# The archive is written to $BE_BACKUP_DIR (default <data-dir>/backups), keeps
# the newest $BE_BACKUP_KEEP archives (default 14) and verifies every database
# with PRAGMA integrity_check before it is accepted.
#
# Usage:
#   scripts/backup.sh [--data-dir DIR] [--out DIR] [--keep N]
#
# Restore: stop the app, extract the archive over the data directory, start the
# app. See docs/DEPLOYMENT.md "Backups & restore".
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

DATA_DIR="${BE_DATA_DIR:-$APP_DIR}"
OUT_DIR="${BE_BACKUP_DIR:-$DATA_DIR/backups}"
KEEP="${BE_BACKUP_KEEP:-14}"

while [ $# -gt 0 ]; do
  case "$1" in
    --data-dir) DATA_DIR="${2:?missing directory}"; shift 2 ;;
    --out)      OUT_DIR="${2:?missing directory}"; shift 2 ;;
    --keep)     KEEP="${2:?missing count}"; shift 2 ;;
    -h|--help)  sed -n '2,20p' "$0"; exit 0 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

if [ ! -d "$DATA_DIR" ]; then
  echo "data directory does not exist: $DATA_DIR" >&2
  exit 1
fi

PY="${BLACK_ECLIPSE_PYTHON:-}"
if [ -z "$PY" ]; then
  if [ -x "$APP_DIR/scripts/vendor/python/bin/python3" ]; then
    PY="$APP_DIR/scripts/vendor/python/bin/python3"
  elif [ -x "$APP_DIR/scripts/vendor/python/python.exe" ]; then
    # The vendored Windows interpreter (Git Bash / the desktop launcher host).
    PY="$APP_DIR/scripts/vendor/python/python.exe"
  elif command -v python3 >/dev/null 2>&1; then
    PY=python3
  elif command -v python >/dev/null 2>&1; then
    PY=python
  else
    echo "python3 (or python) is required for the SQLite snapshots" >&2
    exit 1
  fi
fi

mkdir -p "$OUT_DIR"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
ROOT="$WORK/data"
mkdir -p "$ROOT"

found=0
for name in jdds.db agent-memory.db eclipse-memory.db; do
  db="$DATA_DIR/$name"
  [ -f "$db" ] || continue
  "$PY" - "$db" "$ROOT/$name" <<'PY'
import sqlite3
import sys

src, dst = sys.argv[1], sys.argv[2]
source = sqlite3.connect(f"file:{src}?mode=ro", uri=True)
target = sqlite3.connect(dst)
try:
    source.backup(target)
    target.execute("PRAGMA journal_mode=DELETE")
    result = target.execute("PRAGMA integrity_check").fetchone()
    if not result or str(result[0]).lower() != "ok":
        raise SystemExit(f"integrity check failed for {src}: {result}")
finally:
    target.close()
    source.close()
PY
  echo "snapshot: $name"
  found=1
done

if [ -d "$DATA_DIR/.black-eclipse" ]; then
  (cd "$DATA_DIR" && tar -cf - \
      --exclude='./backups' \
      --exclude='./.black-eclipse/backups' \
      .black-eclipse) | (cd "$ROOT" && tar -xf -)
  echo "snapshot: .black-eclipse/"
  found=1
fi

if [ "$found" -eq 0 ]; then
  echo "no BlackEclipse data found under $DATA_DIR" >&2
  exit 1
fi

ARCHIVE="$OUT_DIR/blackeclipse-$STAMP.tar.gz"
# Write from inside $OUT_DIR with a bare file name: GNU tar on Windows/Git Bash
# reads the `C:` in an absolute output path as a remote host and fails.
( cd "$OUT_DIR" && tar -czf "$(basename "$ARCHIVE")" -C "$WORK" data )

# Retention: keep the newest KEEP archives, delete the rest.
if [ "$KEEP" -gt 0 ]; then
  ls -1t "$OUT_DIR"/blackeclipse-*.tar.gz 2>/dev/null \
    | tail -n "+$((KEEP + 1))" \
    | while IFS= read -r old; do rm -f -- "$old"; done
fi

echo "backup written: $ARCHIVE ($(du -h "$ARCHIVE" | cut -f1))"
