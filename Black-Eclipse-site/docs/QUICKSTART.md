---
title: Quickstart
status: Current
last-verified: 2026-11-16
---

# Quickstart

**Who this is for:** you just cloned the repo and want it running, then want to
know what you are looking at.

> Installing the app, rather than building a checkout? Use the installer or the
> one-command scripts in [`install.md`](./install.md). A checkout is not a
> substitute: the window is a compiled shell, and Stable runs the installed
> shell against your tree.

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

**While you are iterating, use `npm run desktop:live`.** The window serves an
immutable pinned build, so a `src/` edit is invisible until `desktop:refresh`
rebuilds, promotes and reopens the app. Live mode relaunches the same window
against `next dev`, so every save hot-reloads it — no build per change. The
launcher prepares the channel itself: it bridges the installed shell to this
checkout on first use and builds the Dev shell if it is missing. Leave live mode
with `desktop:refresh` (Stable) or `desktop:dev`.

First-time/package installs use the installed `Black Eclipse.exe`. `npm run
desktop:doctor` prints one screen: window, port, served build, harness, provider
and any running build.

Housekeeping: `npm run clean:junk` sweeps dead runtime scratch (corrupt index
snapshots, test-created index DBs, stale workspace caches, logs) and reports
what it freed; add `-- --build` to also wipe regenerable build output (`.next`,
`dist`, Rust targets). It never touches DB vaults, credentials, pinned builds or
`releases/`.

Two channels can run at once: **Stable** (3100, harness 8767) and **Dev** (3101,
harness 8768). Dev has isolated data, so testing can never touch your real
journals. See [`environments.md`](./environments.md).

Nothing to run in a browser any more. `npm run dev`, `npm run up`, `npm start`,
`npm run proxy`, the TLS/hosts scripts and the old `start-eclipse.vbs` launcher
were deleted with the browser lane; `black eclipse` / `black start` /
`black proxy` print where that went and exit 1. There is no flag to re-enable
them.

### Desktop shortcut (Windows)

`npm run setup:desktop` (or `black desktop`) creates/repairs the **Black
Eclipse** shortcut. It points straight at
`%LOCALAPPDATA%\Programs\BlackEclipse\Black Eclipse.exe` — the native app owns
the icon, which is also what Windows 11's right-click "Open" row draws. If the
app is not installed the installer **fails loudly** with the path it expected
and the command to build the installer; it never creates an icon for a launcher
that does not exist. Re-run it after reinstalling the app or changing its icon.

Clicking the icon opens the app. The shell boots its own loopback server and
shows a progress screen (`desktop/ui/index.html`, embedded at compile time) while
`scripts/desktop-server.js` works through checking → building → starting, with a
Retry panel on failure instead of a silent exit. A second click focuses the
existing window (Tauri single-instance).

To load new code: `npm run desktop:refresh` (build if needed, promote, reopen),
or `npm run desktop:dev` for the Dev channel. While iterating, `npm run
desktop:live` hot-reloads the open window on every save. `black status` shows
both channels; `black stop` stops only the server tree this install started.

**Only one production build runs at a time.** `next build` deletes and rewrites
`.next` in place, so a terminal `npm run build` racing another build corrupts the
output and can leave the app unable to start — the "icon hangs, then the next
click works" report. `npm run build` runs `scripts/build-prod.js`, and every
supported entry point (`npm run build`, `desktop:build:dev`, `desktop:refresh`,
`desktop:promote`, the desktop launcher) takes `.next-build.lock` first; a second
build **waits** for the first and reuses it if the source is unchanged.

A plain `npm run build` also **refuses while the desktop app is running**: the
build would saturate the CPU and starve the Python runtime's cold start. Use
`npm run desktop:refresh` (build → pin → reopen) or `black stop` first. The
managed paths — `desktop:refresh` and `black update` — are exempt because they
own the pin and the restart.

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
   and can take minutes on this (memory-constrained) machine; the desktop server
   waits `HARNESS_PY_START_TIMEOUT_MS` (default 120000) for `/health`.

Because of steps 4–7, the first minute can look sparse and then fill in.

## Verify it works

- The **Market Screener** tab shows rows with prices, not a `DEMO` banner.
- `curl http://127.0.0.1:3100/api/news` returns JSON with a `source` field.
- `npx tsc --noEmit` and `npm test` pass (this is also the required
  after-every-change check). While iterating use `npm run test:fast`; before
  reporting done use `npm run verify`, which runs the **full** suite for each
  domain you touched (`src/` → vitest, `python/` → pytest, the memory
  subsystem → eval floors) instead of all three every time.

## Useful scripts

| Script | What it does |
|---|---|
| `npm run desktop:dev` | Build/pin the Dev payload and launch the **Dev window** (3101) |
| `npm run desktop:live` | Relaunch the window on `next dev` — hot reload on every save (`-- --channel dev` for Dev) |
| `npm run desktop:refresh` | Build if needed, promote, reopen **Stable** (3100) |
| `npm run desktop:promote` | Stage + validate the current build, make it Stable, restart |
| `npm run desktop:rollback` | Switch Stable back to the previous release |
| `npm run desktop:doctor` | One-screen health check |
| `npm run desktop:build:dev` | Build `.next-desktop-dev` only |
| `npm run build` | Build Stable's `.next` (the source promotion stages) |
| `npm run dev` / `npm run up` / `npm start` / `npm run proxy` | **Deleted** with the browser lane; no such scripts exist |
| `npm run app` / `black` | Open the installed Stable desktop app |
| `npm test` | Everything: vitest + Python suite + eval floors (~22 min on a loaded machine) |
| `npm run verify` | The gate: full suite for each domain you changed (no `python/` change → no 16-min Python run) |
| `npm run test:fast` | Iteration loop: `tsc` + only the tests reachable from your changed `src/` files (~45 s) |
| `npm run lint` | ESLint |

> **Build times on a loaded machine.** `desktop:dev` runs Next on Turbopack
> (ready in ~3s, first-page compile ~34s instead of the old webpack dev server's
> ~10s-ready + ~71s compile) and it no longer balloons to multiple GB of heap. It
> still compiles the ~19k-module graph on demand, so the FIRST visit to a route
> takes tens of seconds, and a cold build under memory pressure can exceed the
> window's chunk-load budget, surfacing as a `ChunkLoadError` or an "Invalid or
> unexpected token" overlay — that is a slow compile, **not** a syntax error in
> your source (`npx tsc --noEmit` and `next build` both pass; the `next.config.ts`
> webpack chunk budget is ignored under Turbopack and no longer needed). If you
> only need to *use* the app, open the installed Stable window: its chunks are
> prebuilt and serve instantly (first paint ~200ms, no per-route compile).

### Headless one-shot (scripting / CI)

Ask Eclipse one question without opening the desktop window and print the answer:

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

Everything persistent is in **one file**: `jdds.db` (SQLite, WAL side-files
alongside it). It is **runtime data and untracked** — git ignores `*.db`, so no
vault ever travels with the source. The live path resolves through
`src/lib/db.ts` (`BE_DB_PATH` → `BE_DATA_DIR` → the channel data dir, e.g.
`Black-Eclipse-site/.black-eclipse/dev/jdds.db`).

A fresh clone is never empty: `doctor.js` creates the schema, and the boot hook
seeds a **demo** journal (~88 trades, `source:'demo'`, one-time marker, removable
from the Journal UI). A packaged installer additionally ships
`app/seed/jdds.db` containing that same schema + demo dataset, built by
`scripts/lib/seed-db.js`. Rolling backups land in `backups/` and are ignored. See
[`../../.opencode/skills/black-eclipse-db/SKILL.md`](../../.opencode/skills/black-eclipse-db/SKILL.md)
for the rules (never stage a `.db`; real broker data never ships).

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

Factory reset from Settings is **scheduled**: the server process cannot safely
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
