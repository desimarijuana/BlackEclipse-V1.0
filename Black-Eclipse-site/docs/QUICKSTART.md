---
title: Quickstart
status: Current
last-verified: 2026-10-15
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
npm run dev     # boots Next.js on http://localhost:3000
```

Open <http://localhost:3000>. That is genuinely all — `instrumentation.ts` starts
the schedulers, seeds the US universe on first boot, and (in production) warms
market prices in the background.

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
| `npm run dev` | App + local proxy together, shown as `http://blackeclipse` (`predev` runs the doctor + frees the port); Next runs on **Turbopack** |
| `npm run dev:next` | `next dev --turbopack` on all interfaces (no proxy) |
| `npm run dev:local` | Dev server on **Turbopack**, bound to `127.0.0.1` only (keeps it off the LAN, no proxy) |
| `npm run proxy` / `npm run proxy:stop` | Loopback reverse proxy on `:80` so `http://blackeclipse` reaches `:3000` — see [`local-hostname.md`](./local-hostname.md) |
| `npm run setup:hostname` | Adds `127.0.0.1 blackeclipse` to the Windows hosts file (self-elevating) |
| `npm run up` | Doctor + `scripts/up.js` (the "just make it work" path) |
| `npm run build` / `npm start` | Production build / serve |
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
  default. Set `observe`, `propose` or `verify` and restart to enable it; follow
  the rollout and operator runbook in
  [`self-improvement/rsl-implementation-plan.md`](self-improvement/rsl-implementation-plan.md) §5.1.

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
