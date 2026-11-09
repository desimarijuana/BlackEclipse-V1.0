#!/bin/sh
# ── BlackEclipse container entrypoint ────────────────────────────────────────
# The app writes its databases and runtime state relative to the working
# directory (`/app`), and `src/lib/db.ts` hard-codes `cwd/jdds.db`. To make that
# state survive container restarts without an env-var path override, link the
# expected paths into a mounted data volume ($BE_DATA_DIR, default /data).
#
# Idempotent: on every boot any real file/dir already in the image is moved into
# the volume first, then replaced with a symlink.
set -e

DATA_DIR="${BE_DATA_DIR:-/data}"
mkdir -p "$DATA_DIR"

# Root-level SQLite databases (jdds + the two harness DBs). SQLite creates the
# -wal/-shm sidecars next to the resolved path, so only the .db itself is linked.
for f in jdds.db agent-memory.db eclipse-memory.db; do
  if [ -f "/app/$f" ] && [ ! -L "/app/$f" ]; then
    mv "/app/$f" "$DATA_DIR/$f"
  fi
  [ -L "/app/$f" ] || ln -sf "$DATA_DIR/$f" "/app/$f"
done

# Runtime state: auth DB, artifacts, sessions, plugins, connector key fallback.
if [ -d /app/.black-eclipse ] && [ ! -L /app/.black-eclipse ]; then
  mkdir -p "$DATA_DIR/.black-eclipse"
  cp -a /app/.black-eclipse/. "$DATA_DIR/.black-eclipse/" 2>/dev/null || true
  rm -rf /app/.black-eclipse
fi
[ -L /app/.black-eclipse ] || ln -sf "$DATA_DIR/.black-eclipse" "/app/.black-eclipse"

# Apply the Prisma schema BEFORE the app starts. `npm start` does this through
# `scripts/doctor.js` (the `prestart` hook), but the container runs `next start`
# directly, so a fresh `be-data` volume would otherwise boot with an empty
# database and every Prisma table (CronJob, journal, ...) would fail with P2021.
# Additive `db push` is safe and idempotent; a destructive schema change fails
# closed with a loud warning instead of silently dropping data.
if command -v npx >/dev/null 2>&1; then
  if ! npx prisma db push; then
    echo "[entrypoint] WARNING: prisma db push failed; the database schema may be incomplete." >&2
  fi
fi

exec "$@"
