---
title: Deployment — Production Container
status: Current
last-verified: 2026-11-08
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
| `Dockerfile` | Node 20 + Python 3 image; installs deps, builds Next, runs as the unprivileged `node` user |
| `docker-entrypoint.sh` | Links the SQLite DBs + `.black-eclipse/` into the mounted data volume (state survives restarts) |
| `docker-compose.yml` | One service, `.env` config, loopback publish, forced auth, dropped capabilities, `be-data` volume, healthcheck |
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
loopback-only instance. The container stack overrides it to `required`
regardless — see **Container hardening**.

## Security preflight

Run the deploy-time checklist before starting (and in the deploy pipeline):

```sh
npm run security:preflight
```

The script reads the **process environment**; it does not parse `.env` itself.
To check a filled `.env` without exporting every key into your shell, run it
with Node's env-file flag (Node >= 20.6):

```sh
node --env-file=.env scripts/security-preflight.js
```

It **fails closed** when an exposed deployment is missing `HARNESS_AUTH_SECRET`
or `CRON_SECRET`, and refuses a public bind with `HARNESS_AUTH=off`. On a
loopback/dev bind every check is advisory (exit 0), so it is also part of
`npm run check:all` and CI. The harness startup log additionally prints the
end-to-end posture (bind + front-door auth) and warns on any unsafe combination
(`docs/harness/authentication.md`).

## Container hardening

The packaged stack is deliberately conservative. Override these only with a
reason, and write it down:

| Control | Default | Why |
| --- | --- | --- |
| Publish address | `127.0.0.1:3000` (`BE_BIND_ADDR` to change) | The container exposes an agent with shell, browser, git and filesystem tools. It must not be reachable from the LAN or the internet without a TLS reverse proxy in front. |
| `HARNESS_AUTH` | forced to `required` in `docker-compose.yml` | `HARNESS_AUTH=off` is a local-dev escape hatch. The packaged stack overrides it, so a `HARNESS_AUTH_SECRET` mistake fails closed (503) instead of serving an unauthenticated agent. |
| Process user | `node` (uid 1000), not root | A tool or a Python side-effect must not start with root inside the container. No privileged port and no capability is needed. |
| Capabilities | `cap_drop: ALL` + `no-new-privileges` | The app installs nothing, binds no privileged port, and never needs to elevate. |
| Build context | `.dockerignore` excludes `.env*`, `*.db`, `.connector-key`, `mcp-servers.json`, `.black-eclipse/` | A secret that reaches an image layer is in every copy of the image forever, even if the file is deleted later. |
| Baseline headers | `next.config.ts` | `nosniff`, `SAMEORIGIN`, strict referrer policy, camera/mic self-only, HSTS in production builds. |

The `be-data` volume is written by uid 1000. A **bind mount** (`-v /srv/be:/data`)
must be `chown 1000:1000` first; a named volume inherits the right ownership
automatically.

Browser automation inside the container may refuse to start because Chromium's
own sandbox cannot initialise without a privileged helper. The documented opt-in
is `HARNESS_BROWSER_NO_SANDBOX=1`
(`python/harness/browser/providers/local_chromium.py`); set it **inside the
container only** — it weakens Chromium's isolation, so it is not a default and
should not be used on the host. Everything else works without it.

## Secret hygiene

Two independent checks keep credentials out of git:

1. `.gitignore` (`.env*`, `*.db`, `.connector-key`, `mcp-servers.json`,
   `python/.black-eclipse/`).
2. `node scripts/scan-secrets.js` — run by the pre-commit hook (`--staged`) and
   by `npm run check:secrets` in CI. It rejects a staged secret file and
   recognisable provider tokens, and prints only a redacted prefix.

If a secret ever lands in a commit, **rotate it first** and then rewrite history;
removing the file in a later commit does not remove it from clones.

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

The entrypoint also applies the Prisma schema (`prisma db push`)
before the app starts, because the container runs `next start` directly and
would not otherwise go through `scripts/doctor.js` (the `prestart` hook that
creates the tables on a bare host). A fresh volume therefore boots with a
complete schema; a destructive schema change fails closed with a loud warning.

Back up `/data`; do not bake it into the image.

## Backups & restore

`scripts/backup.sh` writes one archive of the state that must survive a host
loss, and verifies it before accepting it:

- `jdds.db`, `agent-memory.db`, `eclipse-memory.db` — copied with the **SQLite
  backup API**, so the snapshot is consistent while the app is running;
- `.black-eclipse/` — auth database, artifacts, sessions, plugins (its own
  `backups/` directory is excluded);
- each database is checked with `PRAGMA integrity_check` (a failure aborts the
  backup instead of writing a bad archive).

```bash
# one-off (defaults: data dir = the app dir, output = <data>/backups, keep 14)
bash scripts/backup.sh

# explicit paths for a container host whose data lives in the volume
bash scripts/backup.sh --data-dir /var/lib/docker/volumes/blackeclipse_be-data/_data \
                       --out /var/backups/blackeclipse --keep 30
```

**Schedule it.** `scripts/install-backup-timer.sh` installs a systemd timer
(daily 03:15 by default, with a randomized delay):

```bash
sudo bash scripts/install-backup-timer.sh                          # defaults
sudo bash scripts/install-backup-timer.sh --time 02:30 --keep 30 \
     --data-dir /var/lib/docker/volumes/blackeclipse_be-data/_data \
     --out /var/backups/blackeclipse
systemctl list-timers blackeclipse-backup.timer
```

A cron entry is equivalent:

```cron
15 3 * * * /opt/BlackEclipse-V1.0/Black-Eclipse-site/scripts/backup.sh \
           >> /var/log/blackeclipse-backup.log 2>&1
```

**Windows (Task Scheduler).** `scripts/install-backup-task.ps1` registers the
same daily backup, wrapping the same `backup.sh`:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/install-backup-task.ps1
# optional: -Time 02:30 -Keep 30 -OutDir D:\backups\blackeclipse
schtasks /Run /TN "BlackEclipse Backup"   # verify one run
```

It writes the wrapper to `%LOCALAPPDATA%\BlackEclipse\backup-task.cmd` — a
space-free path, because `schtasks` stores `/TR` unquoted and splits a path
containing spaces (`0x80070002`). The task's logon mode is **interactive only**:
it fires while the user is signed in. For a server, use the systemd timer or a
dedicated service account. The archive excludes `.black-eclipse/code-index`
(a rebuildable cache whose sidecars the live app holds open) and the SQLite
`-wal`/`-shm` sidecars; the three app databases still use the SQLite backup API.

**Restore** (tested in the P2 drill: backup → destroy → restore, 4/4 databases
passing `PRAGMA integrity_check`):

```bash
sudo systemctl stop blackeclipse          # stop the app AND the timer
tar -xzf /var/backups/blackeclipse/blackeclipse-<stamp>.tar.gz -C /tmp/restore
# copy /tmp/restore/data/* over the live data directory
sudo systemctl start blackeclipse
```

Keep backups off the data disk (a lost volume should not take its own backup
with it) and restrict their permissions — `.black-eclipse/` contains the auth
database. Never commit a backup; `jdds.db` and `.env` stay out of git.

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

## Monitoring & alerts

- **Liveness:** `GET /login` (public) is the container healthcheck and the
  external probe target.
- **Runtime telemetry:** the operator-gated surface in
  `docs/harness/observability.md` — `/observability/status`, `health`, `metrics`,
  `slos`, `diagnostics`, and the Prometheus exposition at
  `/observability/metrics/prometheus`.
- **Rules:** `deploy/prometheus/blackeclipse.rules.yml` ships two
  token-free rules (app scrape down, health probe failing) plus commented
  templates for runtime metrics. Scrape the app with a job named
  `blackeclipse` and probe `/login` with a blackbox exporter named
  `blackeclipse-health`.
- **Route to a human.** A rules file with no Alertmanager route is not an alert.
  Point Alertmanager (or the hosting provider's alarm) at a pager/chat/email
  channel someone reads, and name that owner in the deployment notes.
- **Bare host without Prometheus:** `scripts/health-watch.sh` exits non-zero and
  posts to `ALERT_WEBHOOK_URL` when the health surface fails. A one-minute cron
  entry is enough:

  ```cron
  * * * * * cd /opt/BlackEclipse-V1.0/Black-Eclipse-site && \
    HEALTH_URL=http://127.0.0.1:3000/login \
    ALERT_WEBHOOK_URL=https://hooks.example/ops \
    bash scripts/health-watch.sh >> /var/log/blackeclipse-health.log 2>&1
  ```

  Without a webhook it only writes to the log — a local check, not an alert.

## Incident response

| Incident | First action | Channel |
|---|---|---|
| Security vulnerability | Keep details out of public issues | GitHub **Security › Advisories › Report a vulnerability** (SECURITY.md) |
| Outage / unhealthy app | Check `/observability/health` and `journalctl -u blackeclipse` / `docker compose logs app`; roll back with `git checkout <previous tag> && bash scripts/deploy.sh --force` | The operator's on-call channel wired into Alertmanager |
| Data loss / corruption | Stop the app, restore the latest verified archive (see **Backups & restore**) | On-call channel |
| Red weekly drift run | Triage before the next release; do not tag past a red run | `@BlackEclipse/maintainers` (CODEOWNERS) |

Every alert and every red scheduled workflow must name an owner. For a
single-operator install that owner is the operator; for the repository it is the
maintainers role.

## Drift watch

`.github/workflows/ops-drift.yml` runs every Monday at 06:00 UTC (and on
`workflow_dispatch`): the browser drift smokes, the ADR record, the harness size
ratchet and the committed-secret scan. Push/PR runs stay in `ci.yml`; this is the
cadence that notices a tree nobody touched. A red run is owed a triage by the
owner before the next release — do not tag around it. For policy/authority
changes, the operator-run path is
`npm run self:maintenance -- plan --preview <file>` (read-only) followed by
`execute`.

## Notes / known limits

- **First boot warms markets** (prices, news) and can take a minute; the app is
  responsive throughout. The first boot also runs the one-time `prisma db push`
  (a few seconds) before the app process starts.
- **The Python runtime's first cold start** imports the whole agent stack
  (measured 36 s standalone and ~51 s alongside the app's own boot on the
  reference host; longer under a concurrent build). The app pre-starts it in the
  background and the first harness request waits for it, logging progress every
  15 s. The budget is **5 minutes** before an honest 503; raise it with
  `HARNESS_PY_START_TIMEOUT_MS` on a slower host.
- The **browser tool** needs the Chromium download (`python -m playwright install
  chromium`) which is not baked in; the tool reports `BROWSER_UNINSTALLED` until
  present, and the container does not include it to stay small. Add it to the
  Dockerfile if you need browser automation.
- CI (`/.github/workflows/ci.yml`) runs the same gates as `npm run check:all`;
  a deploy should follow a green push.
