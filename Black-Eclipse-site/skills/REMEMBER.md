# REMEMBER.md — Persistent Project Context & Memory

> Read this file **before major work**. Update it when meaningful project knowledge is discovered.
> Never store useless noise. Never blindly trust outdated info — mark outdated entries `[DEPRECATED]` rather than deleting them.
> Prefer facts discovered from the codebase over assumptions. Use `[YYYY-MM-DD]` dates.

---

## Product Context

- **BlackEclipse** is an open-source, agentic AI investment research platform with a Bloomberg-inspired terminal UI.
- Runs **zero-configuration**: JDDS seeds itself + `jdds.db` ships as a committed seed snapshot; free RSS for news; optional user API keys.
- Single-page terminal UI. Tabs (`AppTab` in `src/components/layout/sidebar.tsx`): ChatBot, Command Center, Market Workspace, Market Screener, Portfolio, Journal, Market News, Market Bubbles, Economics, Price Alerts, Settings, plus an embedded Chart tab. Tabs are keep-alive (mount once, then hide).
- Dark theme, glassmorphic, green-on-black, dense financial UI (frosted-glass classes — see the `black-eclipse-ui` skill).

## Current Priorities

1. **Phase 1 — Data System (largely built)**: the **agentic scraper** is the primary, free, zero-config data source (TradingView scanner + yfinance Python bridge + adaptive fallback chain + in-process scheduler), importing into JDDS. User-provided APIs are optional opt-ins. Demo data is the fallback. Source priority: **scraper → user API → demo**.
2. **Phase 2 — Agentic Research Agents (partly built)**: `src/lib/agent/` now has the tool loop (`loop.ts` + `tools.ts`), an OpenAI-compatible server provider (`openai-provider.ts`), and a multi-agent research pipeline (`research.ts`) that persists findings into JDDS (`ResearchReport` / `AgentRun` / `ResearchFinding`). Extend, don't rebuild.
3. User-provided API settings (Finnhub/Alpha Vantage/etc.) as optional opt-ins.
4. **STANDING GOAL — Simple, fast, light**: the website must be simple, fast, and light for the best user experience. Applies to every change, forever. See `skills/GOALS.md` → "Performance & Simplicity".

## Important Decisions

- **[2026] Zero-config policy** — the app must work with no setup. Demo data is the baseline; real data is an opt-in.
- **[2026] Agentic scraper is the primary data source** — free, built-in, zero-config. User APIs are optional and only used if supplied. Users configure as little as possible.
- **[2026] Free data first** — prefer free/open sources over paid APIs. Users can bring their own keys.
- **[2026] Agent provider abstraction** — `src/lib/agent/` defines `AgentProvider`; mock is default; real LLMs plug in later.
- **[2026] RSS for news** — `/api/news` uses free RSS feeds, with `NEWS_MOCK` offline fallback.
- **[2026] Test after every change** — run `npm run test` and `npx tsc --noEmit` after each change to catch issues early, not just at the end.
- **[2026] Simple, fast, light is a standing goal** — every feature/refactor/dependency is evaluated against it. Prefer the simpler, lighter, faster option. See `skills/GOALS.md`.
- **[2026] Workspace kernel** — page/widget customization is registered via the shared kernel in `src/lib/workspace/` (`useWorkspace` + `CustomizableWorkspace` + `WidgetDefinition`); never hand-roll layout state, localStorage, or width-picker UI in a screen (ADR-005/006 in `skills/ARCHITECT.md`, patterns in `skills/CUSTOMIZE.md`). `src/lib/customize/` is **retired**.
- **[2026] Central command palette** — global search (⌘K) is one palette over `src/lib/search/`, split into a pure grammar (`grammar.ts`) and a pure resolver (`resolver.ts`); it dispatches a `Destination` bus and stays offline/deterministic (ADR-009). Never put an LLM on the query path.

## Established Conventions

- **Folder structure:**
  - `src/components/ui/` — reusable primitives (button, card, skeleton, error-boundary, tab-bar, etc.)
  - `src/components/screens/` — full-page views + their data/logic modules
  - `src/components/layout/` — sidebar, top-bar, global-search (command palette)
  - `src/components/chat/` — chat-specific pieces
  - `src/components/workspace/` — customizable widget grid UI
  - `src/components/market-workspace/` — the multi-panel market grid UI
  - `src/lib/workspace/` — the widget workspace kernel (layout state, ops, presets, DataHub)
  - `src/lib/market-workspace/` — the separate market-panel engine
  - `src/lib/agent/` — AI provider abstraction + tool loop + research pipeline
  - `src/lib/search/` — the command palette (registry, grammar, resolver, stores)
  - `src/app/api/` — API routes (server-side only)
- **Client components** start with `'use client'`.
- **Frosted glass** is the default surface style (`.glass-card` / `-strong` / `-subtle` / `.glass-drawer` / `.glass-button`) — never raw `backdrop-blur-*` or flat fills. See the `black-eclipse-ui` skill.
- **Named exports**, not default exports (except Aurora which is default).
- **`cn()` helper** from `src/lib/utils.ts` for class merging.
- **Barrel exports** via `index.ts` in component folders.
- **Single page** — tab switching via `activeTab` state in `stock-chat.tsx`, not URL routes.
- **Demo data** lives in `src/components/screens/market-data.ts`.
- **Filter/sort logic** is a pure hook: `src/components/screens/use-screener-filters.ts`.
- **Skeletons** use the neutral black/grey primitives in `src/components/ui/skeleton.tsx`.

## Known Constraints

- **Git**: never commit, push, or create branches/PRs unless the user explicitly asks. When asked, inspect status/diff, stage only intended files, never commit secrets.
- **Memory**: The machine has 7.9GB RAM. `next build`/`next dev` on the large `market-overview.tsx` (~1900 lines) can hit 16GB allocation failures when free RAM is low. **Keep components small; split large files into hooks/modules.**
- **@base-ui/react v1.5.0**: SSR/hydration quirks. Portal-based components (Tooltip, Dialog) must be **mounted-gated** (render `null` until client `mounted` state is true).
- **Fonts**: `--font-sans` and `--font-serif` are the **same** system sans stack (intentional for consistency). `--font-mono` is JetBrains/IBM Plex mono.
- **Database = JDDS**: one SQLite file (`jdds.db`) via Prisma + better-sqlite3. `src/lib/db.ts` owns the client; `yieldToEventLoop()` must be used between bulk write chunks (better-sqlite3 is synchronous). Client-only UI state still persists to localStorage.
- **`jdds.db` is a committed seed snapshot** — do NOT re-commit it on routine changes; it churns constantly from background scraping. See the `black-eclipse-db` skill.

## Known Problems

- `market-overview.tsx` is a monolith (~1900 lines, ~129KB). Being split (data → `market-data.ts`, filter → `use-screener-filters.ts`) but the JSX rendering remains large.
- News sentiment is a crude keyword heuristic — can misclassify.
- Chat is a keyword-based mock (no real LLM yet).
- `getTradingViewSymbol()` regex for ticker extraction is naive.
- **SQLite Prisma connector does NOT support `mode: "insensitive"`** on string filters. JDDS stores symbols uppercase, so normalize input to uppercase (e.g. `symbol.toUpperCase()`) instead of using `mode`. (Fixed in `src/lib/agent/tools.ts`.)
- **`skills/ARCHITECT.md` sections 2–4 were stale** (pre-JDDS: claimed "no database" and "only /api/news"). Corrected 2026-09-15; if you spot similar relics, fix them against `docs/` + code.

## Things That Must Not Change

- **The Aurora background** (`src/components/ui/Aurora.tsx`) — it is the visual USP. It must render at the **top of the viewport** (`h-56`, `z-0`, `pointer-events-none`, with a downward fade mask) and reflect **combined market + news sentiment** via the `sentiment` prop (a continuous score in [-1, +1]): bright green = bullish, subdued green = neutral/mixed, red = bearish. **Never purple** — Aurora stays in the green-on-black brand language unless sentiment is negative. The score is computed by `src/lib/aurora-sentiment.ts` (market 60% + news 40%, smoothed inside the component's rAF loop). Do not hard-code it to bullish.
- **The green-on-black / dark Bloomberg identity** — do not introduce light-mode or arbitrary color overrides.
- **Zero-config behavior** — the app must always run with no setup.
- **`getTradingViewSymbol()`** mappings (crypto, PSX `.KA`, India `.NS`, etc.) — many screens depend on them.
- **The `cn()` helper** and `cn("dark", "font-sans")` root classes.

## Temporary Decisions / Workarounds

- `next.config.ts` sets `eslint.ignoreDuringBuilds: true` because the large codebase has pre-existing lint warnings. Lint is run separately.
- `market-data.ts` and `use-screener-filters.ts` were extracted specifically to reduce compile memory — keep this pattern.
- The dev server needs ~5GB free RAM to compile the large codebase; run it when other apps are closed.

## Future Plans

- Broker / paper-trading integration — the `trading`-category dashboard widgets (Quick Trade, Open Positions, …) are `UNAVAILABLE` stubs until then.
- Vercel/serverless-friendly scheduling (in-process node-cron + SQLite don't fit serverless; `POST /api/cron/run` exists for hosted schedulers).
- Deeper agent skills (research, screen, portfolio, monitor) on top of the existing tool loop.
- More markets / better coverage in the scraper fallback chain.

## Lessons Learned

- **Memory is the #1 constraint** on this machine. Split large files aggressively; never re-bloat.
- **`assetPrefix: "./"` broke the build** with a 16GB allocation failure on this low-RAM machine — avoid it.
- **Electron/desktop was reverted** back to a pure web app; the repo is web-first now.
- **Deleting data sources but keeping components** is the right separation — components are the product; data is swappable.

## Important Discoveries

- `src/app/api/news/route.ts` returns `{ news, source: "rss"|"empty"|"error", pagination }` and reads from JDDS (RSS is ingested in the background).
- `market-news.tsx` fetches `/api/news?page=N&limit=10` and falls back to `NEWS_MOCK` when the feed is empty/unreachable.
- `getAgentProvider()` in `src/lib/agent/registry.ts` returns the first configured provider (openai-compatible via `/api/agent/chat`) else the mock.
- `.gitignore` excludes `*.sql`, `*.log`, `dev-server.log`, `dev-log.txt`, `.env*`, and `jdds.db-*` (WAL/shm side files). `jdds.db` itself IS committed (seed snapshot).
- The canonical human docs live in `docs/` (start at `docs/README.md`); `skills/` is the agent engineering OS. See `skills/DOCS.md`.
