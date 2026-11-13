---
title: Quickstart
status: Current
last-verified: 2026-11-09
---

# Quickstart

**Who this is for:** you just cloned the repo and want it running, then want to
know what you are looking at.

## Prerequisites

| Requirement | Notes |
|---|---|
| Node.js 20+ | Enforced by `package.json` `engines` |
| npm | The repo uses npm and a committed `package-lock.json` |
| Python 3.9+ *(optional)* | Enables the `yfinance` bridge for markets TradingView covers poorly. The app runs without it. |

## Run it

The product is the **desktop app**. There is no browser/website runtime in the
daily loop.

```bash
npm install              # also runs prisma generate + the Python setup
npm run desktop:dev      # build + launch the DEV window (port 3101)
# or
npm run desktop:refresh  # build + promote + open STABLE (port 3100)
```

First-time/package installs use the installed `Black Eclipse.exe`. `npm run
desktop:doctor` prints one screen: window, port, served build, harness, provider
and any running build.

Two channels can run at once: **Stable** (3100, harness 8767) and **Dev** (3101,
harness 8768). Dev has isolated data, so testing can never touch your real
journals. See [`environments.md`](./environments.md).

`npm run dev` / `npm run up` / `npm start` are **retired** and print a
desktop-only message. Set `BE_ALLOW_WEB=1` only when deliberately working on a
future browser release.

### Desktop shortcut (Windows)

`npm run setup:desktop` (or `black desktop`) creates/repairs the **Black
Eclipse** shortcut. When the native app is installed it points straight at
`%LOCALAPPDATA%\Programs\BlackEclipse\Black Eclipse.exe`; otherwise it falls
back to the old `.black-eclipse\Black Eclipse.exe` shim. Re-run after an icon
change.

**Legacy:** `start-eclipse.vbs` / `scripts/start-desktop.js` are the retired
browser launcher (built Next + local proxy + `https://blackeclipse`). They now
exit with a desktop-only message unless `BE_ALLOW_WEB=1`. The paragraph below
describes that retired path and is kept for the future browser release.

A click always shows something immediately. Before the app is ready the launcher
opens a loopback **progress page** (`http://127.0.0.1:3197/`, next free port if
taken) rendered in the **user's saved app-wide theme**: `scripts/lib/app-theme.js`
reads `SystemConfig.eclipse_theme` from JDDS (the row Settings › Customization
writes), so the page uses the saved brand color, dark/light scheme, fonts,
radius, glass tint/blur, background treatment and logo/favicon — with the
shipped theme as the fallback. It names the real phase — checking, building,
starting, waiting for the proxy — rotates a short hint every few seconds, shows
the last server log line, and redirects
itself to `https://blackeclipse/?desktop=1` when the app answers. If the boot
fails it stops spinning and shows the reason plus the log path instead of
exiting silently. The page is local-only, has no external assets, and a second
click attaches to the running launcher's page rather than starting a second boot.

Clicking the icon is a fast, non-destructive action: if the app is already
answering it just opens the tab, without killing or rebooting the server. Only a
cold/down app is started. The app behaves like a normal desktop app: the beacon
file is a **refcount of live tabs**, so closing one of several open (or
duplicated) tabs does not stop the server; when the LAST tab closes,
`scripts/start-desktop.js` stops the server about 8 seconds later and the
launcher exits. If a tab crashes or is force-closed without reporting
`pagehide`, the crash fallback stops the server after 30 minutes of complete
silence — deliberately long, because a hidden/frozen tab, a throttled timer and
a sleeping machine all pause the 10s heartbeat while the page is still open. A
page that resumes from sleep, focus or visibility re-beacons immediately.

There is no window to close by hand; stop a stuck launcher with Task Manager.
If an unmanaged production instance is already running, the icon opens it and
leaves its lifecycle alone (`black stop` stops it). Only one launcher boots at a
time: clicking the icon again while the first is still building attaches to its
progress page, so repeated clicks cannot start competing builds against the same
`.next` folder.

The icon starts the existing build directly (`local-host`), never rebuilding:
startup is about two seconds, and a click on an already-running app is immediate
(the icon opens a tab rather than restarting it). The only slow launch is the
first one on a fresh clone, when there is no build yet. If the source is newer
than the build, the log says so and still starts instantly. To update the build,
stop the app first (`black stop`, or close its last tab), run `npm run build`
(its `postbuild` records the source hash), then click the icon. For day-to-day
editing, use `npm run dev`; the icon is for running the built app. Setting
`BE_DESKTOP_BUILD=1` forces a rebuild from the launcher; `black eclipse --restart`
replaces a running instance.

**Only one production build runs at a time.** `next build` deletes and rewrites
`.next` in place, so a terminal `npm run build` racing the launcher's build (or
`npm run up`) corrupts the output and can leave the app unable to start — the
"icon hangs, then the next click works" report. `npm run build` now runs
`scripts/build-prod.js`, and every supported entry point (`npm run build`,
`npm run up`, `black eclipse`, the desktop launcher) takes
`.next-build.lock` first; a second build **waits** for the first and reuses it if
the source is unchanged. If the icon is clicked while a build is running, the
progress page says so and waits, instead of starting a competing build.

The page reports its lifecycle through `/api/desktop/session`, which is inert
unless the launcher set `BE_DESKTOP_HEARTBEAT_FILE`. A console-launched server
(`npm run dev`) is not affected.

> `npm install` is not a plain install here. Its `postinstall` runs
> `prisma generate`, `scripts/setup-python.js`, and `scripts/link-global.js`.
> If install "hangs", it is probably the optional Python setup.

## What happens on first boot

Understanding this sequence explains most "why is it empty / slow" questions:

1. `src/instrumentation.ts` runs once when the server starts.
2. **DB durability guard** (`scripts/db-guard.js`) sets SQLite WAL +
   `synchronous=NORMAL`, and schedules a rolling local backup.
3. **`seedUniverse(["US"])`** ensures the US market has assets.
4. **Price scheduler** starts (interval stored in JDDS, default 15 min).
5. **Universe-sync cron** starts (daily) to pick up new listings.
6. **News-refresh cron** starts (default 5 min) and does one ingest ~15s after boot.
7. **Warm-up** bulk-prices open markets — *skipped in dev* unless you set
   `BE_WARMUP=1`.
8. **Alert monitor** starts its server-side poll loop.
9. **Python agent runtime** is pre-started (non-blocking) so the first chat
   request does not pay a cold spawn. A cold start imports the whole agent stack
   and can take minutes on this (memory-constrained) machine; the front door
   waits `HARNESS_PY_START_TIMEOUT_MS` (default 120000) for `/health`.

Because of steps 4–7, the first minute can look sparse and then fill in.

## Verify it works

- The **Market Screener** tab shows rows with prices, not a `DEMO` banner.
- `curl http://localhost:3000/api/news` returns JSON with a `source` field.
- `npx tsc --noEmit` and `npm test` pass (this is also the required
  after-every-change check).

## Useful scripts

| Script | What it does |
|---|---|
| `npm run desktop:dev` | Build/pin the Dev payload and launch the **Dev window** (3101) |
| `npm run desktop:refresh` | Build if needed, promote, reopen **Stable** (3100) |
| `npm run desktop:promote` | Stage + validate the current build, make it Stable, restart |
| `npm run desktop:rollback` | Switch Stable back to the previous release |
| `npm run desktop:doctor` | One-screen health check |
| `npm run desktop:build:dev` | Build `.next-desktop-dev` only |
| `npm run build` | Build Stable's `.next` (the source promotion stages) |
| `npm run dev` / `npm run up` / `npm start` / `npm run proxy` | **Retired** browser lane; prints a desktop-only message unless `BE_ALLOW_WEB=1` |
| `npm test` | Vitest unit tests |
| `npm run lint` | ESLint |

> **`next dev` vs `npm run up` on a loaded machine.** `npm run dev` now runs
> Next on **Turbopack** (`--turbopack`): ready in ~3s and a first-page compile of
> ~34s instead of the old webpack dev server's ~10s-ready + ~71s compile — and it
> no longer balloons to multiple GB of heap. It still compiles the ~19k-module
> graph on demand, so the FIRST visit to a route takes tens of seconds and a cold
> build under memory pressure can exceed the browser's chunk-load budget,
> surfacing as a `ChunkLoadError` or an "Invalid or unexpected token" overlay —
> that is a slow compile, **not** a syntax error in your source
> (`npx tsc --noEmit` and `next build` both pass; the `next.config.ts` webpack
> chunk budget is ignored under Turbopack and no longer needed). If you only need
> to *use* the app, prefer `npm run up`: production chunks are prebuilt and serve
> instantly (first paint ~200ms, no per-route compile).
>
> Opening the app in a **second browser tab** no longer re-downloads that graph:
> Turbopack dev chunk URLs are content-hashed and are now served immutable
> (HTML/RSC stays `no-store`), so only the first tab pays the download/parse
> cost. `black eclipse` and `npm run up` also leave an already-running server
> alone — opening Eclipse again just reports the live URL; use
> `black eclipse --restart` (or `npm run up -- --restart`) to force a restart.

### Headless one-shot (scripting / CI)

Ask Eclipse one question without the web app and print the answer:

```bash
node scripts/eclipse.js chat -z "Summarise AAPL's last earnings"
node scripts/eclipse.js chat -z "Is the market risk-on today?" --json
```

It runs the SAME runtime the web chat uses, in-process; model settings come from
the `HARNESS_JOB_*` environment (the same source a scheduled job uses), and a
real provider key env wins. `--json` prints `{success, runId, status, output,
error}` for scripts. Exit code is `0` on a completed run, `1` when the run failed
or could not start. `eclipse eval .` runs the offline evaluation gate headlessly
for CI.

## Configuration (all optional)

Copy `.env.example` to `.env.local` if you want to configure anything. The table
in [`../README.md`](../README.md) is authoritative; in short:

- `CRON_SECRET` — **set this when deploying publicly.** It is what unlocks
  programmatic access to mutating endpoints. Without it, only same-origin
  browser requests and localhost can mutate state.
- `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` / `OLLAMA_BASE_URL` — power the real
  agent. Without any of them, a built-in **mock** provider answers. Keys can also
  be set from the in-app Settings screen.
- `BE_WARMUP=1` — opt into the dev boot warm-up so prices are pre-fetched.
- `NEXT_PUBLIC_AGENTATION=1` — opt into the Agentation visual-feedback toolbar.
  It is **off by default because it claims global single-letter keys** (`L`, `P`,
  `H`, `C`, `X`, `S`), which would shadow the app's own keyboard shortcuts.
- `CONNECTOR_SECRET_KEY` — base64 32-byte key for encrypting operator
  data-source credentials. **Required on hosted/serverless deploys.** Locally it
  is optional: a gitignored `.connector-key` is generated on first use.
- `NEXT_PUBLIC_LLM_CONFIGURED` — set by `instrumentation.ts`; tells the client
  whether a real LLM exists so it can pick the right provider.
- `HARNESS_RSL_MODE` — the Recursive Self-Improvement Loop is **off** by
  default. Set `observe`, `propose`, `verify` or `auto` and restart to enable
  it. `auto` proposes and verifies; it still never lands a change. Follow the
  rollout and operator runbook in
  [`self-improvement/rsl-implementation-plan.md`](self-improvement/rsl-implementation-plan.md) §5.1.
  Test it without touching your data with `npm run rsl:smoke`. Compare a
  baseline, a surface snapshot and surface+lessons with
  `npm run rsl:bench -- --surface-snapshot <file>`; the report is written under
  `.black-eclipse/evaluation/reports/`. Add `--live --provider <p> --model <m>`
  (and `HARNESS_EVAL_API_KEY`) for a real-model tier; replay datasets are built
  explicitly with `python -m harness.evaluation.replay_builder --out <file>`.
  Run the unattended session with `npm run rsl:nightly` — it compares the
  corpus with the recorded baseline and exits non-zero on a critical
  regression (`--promote` moves the baseline forward on a clean run; the
  release gate `npm run check:all` uses the committed baseline in
  `python/harness/evaluation/baselines/corpus_v1.json`). Export
  the benchmark as a portable bundle with `npm run rsl:corpus -- --out <file>`,
  and check a bundle was not edited in flight with `--verify <file>`. Let the
  loop try to improve its own harness with `npm run rsl:lab -- --memory-db
  <eclipse-memory.db>` — it reports a measured CANDIDATE, never a landing. Add
  `--live --provider <p> --model <m>` (credential from `HARNESS_EVAL_API_KEY`)
  for the only tier in which a prompt change can move the result.
- `HARNESS_RSL_MAX_PARALLEL` — how many independent candidates one RSL
  experiment verifies at once (1–8, default `2`). It never bypasses the daily
  budget or the one-experiment-at-a-time conductor.
- `HARNESS_DRIFT_WATCH_SECONDS` — how often the read-only drift watch checks
  every configured scope (default `300`; `0` disables). It publishes a drift
  transition event but never creates a candidate.
- `HARNESS_RSL_DRIFT_AUTOCANDIDATE` — when `on`, a NEW drift transition also
  opens the same inert candidate the operator button opens (no target, no
  operations; it enters the normal propose → verify → land flow and lands
  nothing by itself). **Off by default.**

**Drift runbook.** Leave the watch at its default interval. When a scope
transitions, the Learning Journey header shows `N drifting` and the production
drift card lists the scope with its drop. Select the scope, adjust window /
baseline / threshold / minSamples if needed, inspect the recent history, then use
**Open drift candidate** to create the inert candidate. From there the existing
propose → verify → land flow applies; drift never lands or activates anything on
its own. The watcher's last status is persisted, so restarting the runtime does
not re-alert the same episode, and a reset run history clears that state. The
policy inputs are remembered across reloads, and the journey badge raises one
notification per drifting scope per day. `npm run test:drift-ui` exercises the
card in isolation; `npm run test:drift-app` drives the real app shell
(Skills → Journey) with mocked network data. The Command Center's `Production
Drift` widget shows the same per-scope overview and trend, and drift
transitions are also recorded as durable notifications (`GET
/evolution/drift/alerts`). CI runs both browser smokes.

## Where your data lives

Everything persistent is in **one file**: `Black-Eclipse-site/jdds.db` (SQLite,
WAL side-files ignored by git). The committed `jdds.db` is a **seed snapshot** —
new clones get real markets without scraping. See
[`../.opencode/skills/black-eclipse-db/SKILL.md`](../../.opencode/skills/black-eclipse-db/SKILL.md)
for the rules (never re-commit it casually; checkpoint WAL before committing it).

## Common first-run questions

**"The tables are empty / it says DEMO."** No universe has been imported for that
market yet, or the scraper has not run. Check the scheduler logs, or set
`BE_WARMUP=1` and restart.

**"The app uses a lot of memory or freezes."** This is a known constraint of the
target machine (7.9 GB RAM). The code is deliberately split to keep individual
files small. See the constraints in
[`../skills/REMEMBER.md`](../skills/REMEMBER.md).

**"Which page am I editing?"** Find it in [`NAVIGATION.md`](./NAVIGATION.md).

## Starting over

There are three scopes; pick the smallest one that solves the problem.

| I want to… | Settings | CLI |
|---|---|---|
| Answer the setup questions again (keep keys, chats, portfolio) | General → Setup → **Run setup again** | `black onboarding` or `black reset --onboarding` |
| Clear setup, source choices, AI config and API keys (keep chats/portfolio/research) | Data & Storage → **Reset setup & API keys** (type `RESET`) | `black reset --setup` |
| Erase all local Eclipse data and boot as a new install | Data & Storage → **Factory reset** (type `WIPE`) | `black reset --factory --confirm=WIPE` |

Factory reset from Settings is **scheduled**: the web process cannot safely
delete live SQLite files on Windows, so it writes a marker and the reset runs on
the next start (before the database is opened). The CLI stops the servers first.
A backup is created by default at `reset-backups/<timestamp>/` (outside every
wipe target); pass `--no-backup` to skip it. `.env` is not deleted unless you
pass `--include-env` or tick the box.

Dry run: `black reset --list` (or `npm run reset:list`) prints every path a
factory reset would touch. See §13 of
[`onboarding-plan.md`](./onboarding-plan.md) for the full contract.

## Next

- [`ARCHITECTURE.md`](./ARCHITECTURE.md) — the layers.
- [`DATA-FLOW.md`](./DATA-FLOW.md) — how a price reaches the screen.
