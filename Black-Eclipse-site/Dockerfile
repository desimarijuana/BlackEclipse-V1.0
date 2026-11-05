# ── BlackEclipse — production image ──────────────────────────────────────────
# ONE container runs BOTH services:
#   * `next start`  — the Next.js web app (the front door)
#   * the Python FastAPI/LangGraph harness (uvicorn), which the Next process
#     spawns as a child on the first harness request (src/lib/harness/python-runtime.ts,
#     default http://127.0.0.1:8765). Python binds loopback inside the container,
#     so only port 3000 is exposed.
#
# Build:  docker build -t black-eclipse .
# Run:    docker run --env-file .env -p 127.0.0.1:3000:3000 -v be-data:/data black-eclipse
# Or:     docker compose up -d   (see docker-compose.yml)

# syntax=docker/dockerfile:1
FROM node:20-bookworm

ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    PYTHONUNBUFFERED=1 \
    HOME=/home/node

# Python 3 (for the agent harness) + build toolchain for native Node modules
# (better-sqlite3). Bookworm ships Python 3.11; the harness needs nothing newer.
RUN apt-get update && apt-get install -y --no-install-recommends \
      python3 python3-pip python3-venv \
      build-essential ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# ── Python harness dependencies ──────────────────────────────────────────────
# Installed as root, before the privilege drop, because `--break-system-packages`
# writes into /usr/local. Platform markers in requirements.txt keep Windows-only
# packages out on Linux.
COPY python/requirements.txt ./python/requirements.txt
RUN python3 -m pip install --break-system-packages --no-cache-dir -r python/requirements.txt

# Runtime state volume + workspace ownership. `/app` is created by WORKDIR as
# root; without this the unprivileged build cannot write `.next`, and a fresh
# named volume would not inherit the right owner. Docker copies directory
# ownership into an empty volume.
RUN mkdir -p /data && chown node:node /app /data

# ── Application, built as the unprivileged `node` user ───────────────────────
# WHY NON-ROOT: the app spawns Python, runs git, and writes files for the agent.
# A container escape or an agent tool that reaches the host must not already be
# root inside the container. `next start` needs no privileged port (3000) and no
# capabilities, so it runs as `node` (uid 1000) from here on.
COPY --chown=node:node package.json package-lock.json ./
USER node

# Install without lifecycle scripts (the postinstall provisions a WINDOWS-only
# embedded Python and links a global CLI we do not need in the image), then
# rebuild the native SQLite binding for this image's platform/arch explicitly.
RUN npm ci --ignore-scripts \
    && npm rebuild better-sqlite3

# ── Application source + build ───────────────────────────────────────────────
COPY --chown=node:node . .
RUN npx prisma generate \
    && npm run build \
    && chmod +x docker-entrypoint.sh

EXPOSE 3000

# Healthcheck hits the always-public login route (no auth required).
HEALTHCHECK --interval=30s --timeout=5s --start-period=90s --retries=5 \
  CMD curl -fsS "http://127.0.0.1:${PORT:-3000}/login" || exit 1

# The entrypoint links runtime state into the mounted data volume; the Python
# harness is spawned lazily by the app, so no separate process is declared.
ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD ["sh", "-c", "npx next start -p ${PORT:-3000}"]
