---
title: Quickstart
status: Current
last-verified: 2026-10-23
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

```bash
npm install     # also runs prisma generate + python/global-link setup
npm run dev     # boots the DEVELOPMENT server on http://localhost:3000
```

Open <http://localhost:3000>. That is genuinely all — `instrumentation.ts` starts
the schedulers, seeds the US universe on first boot, and (in production) warms
market prices in the background.

Development and production are separate servers on separate ports and can run at
the same time: `npm run dev` is `3000` with isolated runtime state, while
`npm run up` builds and serves production on `3100` at `http://blackeclipse`.
See [`environments.md`](./environments.md).

### Desktop shortcut (Windows)

`start-eclipse.vbs` starts the **production** site (built Next on `3100`
behind the local proxy) in a visible console, waits until it answers, and opens
`https://blackeclipse` (or `http://` when TLS is not configured). Create a
shortcut to it (or run `wscript start-eclipse.vbs`) and the app behaves like a
normal desktop app: when the tab is closed, `scripts/start-desktop.js` stops the
server a few seconds later and the console closes with it. Closing the console
by hand also stops the server. If an unmanaged production instance is already
running, the launcher restarts it under its own lifecycle.

The icon starts the existing build directly (`local-host`), never rebuilding:
startup is about two seconds. The only slow launch is the first one on a fresh
clone, when there is no build yet. If the source is newer than the build, the
console says so and still starts instantly. To update the build, close the app
and run `npm run build` (its `postbuild` records the source hash); the next icon
click uses it. For day-to-day editing, use `npm run dev`; the icon is for running
the built app. Setting `BE_DESKTOP_BUILD=1` forces a rebuild from the launcher.
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
| `npm run dev` | **Development** server on `3000` (`predev` runs the doctor + frees the dev ports); Turbopack, no proxy, runtime state in `.black-eclipse/dev/` — see [`environments.md`](./environments.md) |
| `npm run dev:next` | `next dev --turbopack` on all interfaces (raw; no profile env) |
| `npm run dev:local` | Dev server on **Turbopack**, bound to `127.0.0.1` only (raw; no profile env) |
| `npm run proxy` / `npm run proxy:stop` | Loopback reverse proxy on `:80` so `http://blackeclipse` reaches production on `:3100` — see [`local-hostname.md`](./local-hostname.md) |
| `npm run setup:hostname` | Adds `127.0.0.1 blackeclipse` to the Windows hosts file (self-elevating) |
| `npm run up` | **Production** server on `3100` behind the proxy (doctor + build-if-changed + start) |
| `npm run build` / `npm start` | Production build / production serve |
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

## Next

- [`ARCHITECTURE.md`](./ARCHITECTURE.md) — the layers.
- [`DATA-FLOW.md`](./DATA-FLOW.md) — how a price reaches the screen.
