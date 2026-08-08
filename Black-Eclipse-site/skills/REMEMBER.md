# REMEMBER.md — Persistent Project Context & Memory

> Read this file **before major work**. Update it when meaningful project knowledge is discovered.
> Never store useless noise. Never blindly trust outdated info — mark outdated entries `[DEPRECATED]` rather than deleting them.
> Prefer facts discovered from the codebase over assumptions. Use `[YYYY-MM-DD]` dates.

---

## Product Context

- **BlackEclipse** is an open-source, agentic AI investment research platform with a Bloomberg-inspired terminal UI.
- Runs **zero-configuration**: demo data by default, free RSS for news, optional user API keys later.
- Single-page terminal UI with 6 tabs: Chat, Discovery (screener), Market (portfolio), News, Bubbles (heatmap), Chart.
- Dark theme, glassmorphic, green-on-black, dense financial UI.

## Current Priorities

1. **Phase 1 — Data System**: an **agentic scraper** as the primary, free, zero-config data source (Yahoo Finance + cheerio fallback + smart scheduler). User-provided APIs are optional opt-ins. Demo data is the fallback. Source priority: **agentic scraper → user API → demo**.
2. **Phase 2 — Agentic Research Agents**: extend `src/lib/agent/` with tools (query data, scrape, search) and skills (research, screen, portfolio, monitor), Hermes-style.
3. User-provided API settings (Finnhub/Alpha Vantage/etc.) as optional opt-ins.

## Important Decisions

- **[2026] Zero-config policy** — the app must work with no setup. Demo data is the baseline; real data is an opt-in.
- **[2026] Agentic scraper is the primary data source** — free, built-in, zero-config. User APIs are optional and only used if supplied. Users configure as little as possible.
- **[2026] Free data first** — prefer free/open sources over paid APIs. Users can bring their own keys.
- **[2026] Agent provider abstraction** — `src/lib/agent/` defines `AgentProvider`; mock is default; real LLMs plug in later.
- **[2026] RSS for news** — `/api/news` uses free RSS feeds, with `NEWS_MOCK` offline fallback.
- **[2026] Test after every change** — run `npm run test` and `npx tsc --noEmit` after each change to catch issues early, not just at the end.

## Established Conventions

- **Folder structure:**
  - `src/components/ui/` — reusable primitives (button, card, skeleton, error-boundary, etc.)
  - `src/components/screens/` — full-page views + their data/logic modules
  - `src/components/layout/` — sidebar, top-bar
  - `src/components/chat/` — chat-specific pieces
  - `src/lib/agent/` — AI provider abstraction
  - `src/app/api/` — API routes (server-side only)
- **Client components** start with `'use client'`.
- **Named exports**, not default exports (except Aurora which is default).
- **`cn()` helper** from `src/lib/utils.ts` for class merging.
- **Barrel exports** via `index.ts` in component folders.
- **Single page** — tab switching via `activeTab` state in `stock-chat.tsx`, not URL routes.
- **Demo data** lives in `src/components/screens/market-data.ts`.
- **Filter/sort logic** is a pure hook: `src/components/screens/use-screener-filters.ts`.
- **Skeletons** use the neutral black/grey primitives in `src/components/ui/skeleton.tsx`.

## Known Constraints

- **Memory**: The machine has 7.9GB RAM. `next build`/`next dev` on the large `market-overview.tsx` (~1900 lines) can hit 16GB allocation failures when free RAM is low. **Keep components small; split large files into hooks/modules.**
- **@base-ui/react v1.5.0**: SSR/hydration quirks. Portal-based components (Tooltip, Dialog) must be **mounted-gated** (render `null` until client `mounted` state is true).
- **Fonts**: `--font-sans` and `--font-serif` are the **same** system sans stack (intentional for consistency). `--font-mono` is JetBrains/IBM Plex mono.
- **No database** currently — persistence is localStorage only.

## Known Problems

- `market-overview.tsx` is a monolith (~1900 lines, ~129KB). Being split (data → `market-data.ts`, filter → `use-screener-filters.ts`) but the JSX rendering remains large.
- News sentiment is a crude keyword heuristic — can misclassify.
- Chat is a keyword-based mock (no real LLM yet).
- `getTradingViewSymbol()` regex for ticker extraction is naive.

## Things That Must Not Change

- **The Aurora background** (`src/components/ui/Aurora.tsx`) — it is the visual USP. It must render at the **top of the viewport** (`h-56`, `z-0`, `pointer-events-none`, with a downward fade mask) and react to market sentiment (green = bullish, red = bearish via `isMarketBullish`).
- **The green-on-black / dark Bloomberg identity** — do not introduce light-mode or arbitrary color overrides.
- **Zero-config behavior** — the app must always run with no setup.
- **`getTradingViewSymbol()`** mappings (crypto, PSX `.KA`, India `.NS`, etc.) — many screens depend on them.
- **The `cn()` helper** and `cn("dark", "font-sans")` root classes.

## Temporary Decisions / Workarounds

- `next.config.ts` sets `eslint.ignoreDuringBuilds: true` because the large codebase has pre-existing lint warnings. Lint is run separately.
- `market-data.ts` and `use-screener-filters.ts` were extracted specifically to reduce compile memory — keep this pattern.
- The dev server needs ~5GB free RAM to compile the large codebase; run it when other apps are closed.

## Future Plans

- SQLite local storage (zero-config persistence).
- yahoo-finance2 free scraper + cheerio fallback for PSX/global markets.
- Provider registry auto-chain: user API → free scraper → demo.
- Agent tools (query data, scrape, search) + skills (research, screen, portfolio, monitor).
- A background scheduler / cron for price/universe/news refresh.

## Lessons Learned

- **Memory is the #1 constraint** on this machine. Split large files aggressively; never re-bloat.
- **`assetPrefix: "./"` broke the build** with a 16GB allocation failure on this low-RAM machine — avoid it.
- **Electron/desktop was reverted** back to a pure web app; the repo is web-first now.
- **Deleting data sources but keeping components** is the right separation — components are the product; data is swappable.

## Important Discoveries

- `src/app/api/news/route.ts` returns `{ news, source: "rss"|"empty"|"error", pagination }`.
- `market-news.tsx` fetches `/api/news?page=N&limit=10` and falls back to `NEWS_MOCK` when the feed is empty/unreachable.
- `getAgentProvider()` in `src/lib/agent/registry.ts` returns the mock provider today.
- `.gitignore` excludes `*.sql`, `*.log`, `dev-server.log`, `dev-log.txt`, and `.env*`.
