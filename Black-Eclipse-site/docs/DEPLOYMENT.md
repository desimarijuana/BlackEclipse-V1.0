---
title: Deployment — Production Container
status: Current
last-verified: 2026-10-29
---

# Deployment — Production Container

**Who this is for:** anyone putting BlackEclipse on a server.

The app is **one process tree**: `next start` serves the front door, and the app
spawns the Python FastAPI/LangGraph harness (uvicorn, `127.0.0.1:8765`) as a
child on the first harness request (`src/lib/harness/python-runtime.ts`). So a
**single container** runs everything; only port `3000` is exposed.

## Files

| File | Role |
| --- | --- |
| `Dockerfile` | Node 20 + Python 3 image; installs deps, builds Next, starts the app |
| `docker-entrypoint.sh` | Links the SQLite DBs + `.black-eclipse/` into the mounted data volume (state survives restarts) |
| `docker-compose.yml` | One service, `.env` config, `be-data` volume, healthcheck, `restart: unless-stopped` |
| `.env.example` | Every env var a production deploy needs (copy to `.env`) |

## Quick start

```sh
cp .env.example .env      # fill in real secrets + a provider key
docker compose up -d --build
# open http://localhost:3000
```

## Required secrets

Generate each with `openssl rand -hex 32` (connector key: `openssl rand -base64 32`):

| Var | Why |
| --- | --- |
| `HARNESS_AUTH_SECRET` | Signs session cookies. **Without it a production build fails closed (503)** — see `src/lib/auth/config.ts`. |
| `CRON_SECRET` | Guards `/api/cron/*` and the harness's non-loopback bind. |
| `CONNECTOR_SECRET_KEY` | AES-256 key for connector credentials (else a local `.connector-key` file is used, which does **not** persist in the image). |
| a provider key | `OPENAI_API_KEY` (or `ANTHROPIC_API_KEY`, or `OLLAMA_BASE_URL`). Without one, frontier chat runs have no model. |

`NODE_ENV=production` makes auth **auto-require** a signed-in user
(`HARNESS_AUTH` unset → `required`). Set `HARNESS_AUTH=off` only for a trusted,
loopback-only instance.

## Security preflight

Run the deploy-time checklist before starting (and in the deploy pipeline):

```sh
npm run security:preflight
```

It **fails closed** when an exposed deployment is missing `HARNESS_AUTH_SECRET`
or `CRON_SECRET`, and refuses a public bind with `HARNESS_AUTH=off`. On a
loopback/dev bind every check is advisory (exit 0), so it is also part of
`npm run check:all` and CI. The harness startup log additionally prints the
end-to-end posture (bind + front-door auth) and warns on any unsafe combination
(`docs/harness/authentication.md`).

## Automatic updates (systemd timer)

`scripts/deploy.sh` pulls `origin/main` and rebuilds only when the commit
changed. It is safe to run on a timer: an unchanged commit exits immediately, a
lock prevents overlapping builds, tracked local edits make it refuse, and it
waits for `/login` before reporting success.

Install it once per server:

```sh
cd /path/to/BlackEclipse-V1.0
git pull --ff-only
sudo bash Black-Eclipse-site/scripts/install-autodeploy.sh
```

That writes the two systemd units with the correct paths, enables the timer and
runs one deploy immediately. Check it with:

```sh
systemctl status blackeclipse-deploy.timer
journalctl -u blackeclipse-deploy -f
```

Use `--interval 2` for a 2-minute poll. The equivalent units, if you prefer to
manage them yourself:

```ini
# /etc/systemd/system/blackeclipse-deploy.service
[Unit]
Description=BlackEclipse auto-deploy
Wants=network-online.target
After=network-online.target docker.service

[Service]
Type=oneshot
WorkingDirectory=/opt/BlackEclipse-V1.0/Black-Eclipse-site
ExecStart=/opt/BlackEclipse-V1.0/Black-Eclipse-site/scripts/deploy.sh
```

```ini
# /etc/systemd/system/blackeclipse-deploy.timer
[Unit]
Description=Check origin/main for BlackEclipse updates

[Timer]
OnBootSec=2min
OnUnitActiveSec=5min
Persistent=true

[Install]
WantedBy=timers.target
```

```sh
sudo systemctl daemon-reload
sudo systemctl enable --now blackeclipse-deploy.timer
sudo journalctl -u blackeclipse-deploy -f
```

A cron entry is equivalent:

```cron
*/5 * * * * /opt/BlackEclipse-V1.0/Black-Eclipse-site/scripts/deploy.sh >> /var/log/blackeclipse-deploy.log 2>&1
```

The timer polls; it does not receive webhooks. For an immediate deploy on every
push, `.github/workflows/deploy.yml` SSHes to each host and runs
`scripts/deploy.sh --force`. It **skips harmlessly** until these repository
secrets exist: `DEPLOY_SSH_KEY` (OpenSSH private key), `DEPLOY_USER`,
`DEPLOY_PATH` (repo root on the server) and `DEPLOY_HOST_1` (plus optional
`DEPLOY_HOST_2`/`_3`). The server-side lock, `--ff-only` pull and health check
still apply, so the workflow cannot bypass them.

## Persistence

The entrypoint symlinks these into the `be-data` volume mounted at `/data`:

- `jdds.db` (the market-data vault — `src/lib/db.ts` hard-codes `cwd/jdds.db`),
- `agent-memory.db`, `eclipse-memory.db` (harness state),
- `.black-eclipse/` (auth DB, artifacts, sessions, plugins).

Back up `/data`; do not bake it into the image.

## Health & operations

- Healthcheck: `GET /login` (always public) — the container reports healthy once
  the app answers. `instrumentation.register()` now awaits only a short critical
  path (the deployment-exposure log + the LLM-config flag the client reads); the
  heavy boot pipeline (DB seed, cron registration, warm-up, ingests, the Python
  runtime pre-start) runs AFTER it returns, so the app is reachable immediately
  while that work finishes in the background. (Formerly the heavy steps were
  awaited inside `register()`, which delayed first-request readiness on every
  boot.)
- Logs: `docker compose logs -f app`.
- Rebuild after a code change: `docker compose up -d --build` (or run
  `scripts/deploy.sh`, which pulls only when `origin/main` moved).
- **Runtime port (`127.0.0.1:8765`):** only one Python runtime may own it; a
  second one fails to bind (`WinError 10048`) and exits. In the container a fresh
  process tree starts on every `up`, so this is self-contained. On a bare host
  (dev or `npm start`), a runtime spawned by a previous run can survive on
  Windows and hold the port — `scripts/kill-port.js` (run by `predev` and
  `prestart`) clears both `3000` and the runtime port at launch, so startup
  always begins from a clean runtime. The runtime resolves the port from
  `HARNESS_PY_URL` / `HARNESS_PY_PORT` (default `8765`); set the same value in
  `.env` if you change it. Do not run `next dev` in production — it self-restarts
  under memory pressure, which kills any agent run in flight.

## Notes / known limits

- **First boot warms markets** (prices, news) and can take a minute; the app is
  responsive throughout.
- The **browser tool** needs the Chromium download (`python -m playwright install
  chromium`) which is not baked in; the tool reports `BROWSER_UNINSTALLED` until
  present, and the container does not include it to stay small. Add it to the
  Dockerfile if you need browser automation.
- CI (`/.github/workflows/ci.yml`) runs the same gates as `npm run check:all`;
  a deploy should follow a green push.
