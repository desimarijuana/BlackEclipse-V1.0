# ARCHITECT.md — System Architecture & Engineering Knowledge

> Read this file **before** making any significant architectural change to BlackEclipse.
> If the codebase conflicts with anything here, **the actual working implementation is the source of truth** until it is intentionally changed and this file is updated.

---

## 1. Product Definition

### What BlackEclipse is
An **open-source, agentic AI Harness and investment research platform** presented as a Bloomberg-inspired terminal UI. It provides market screening, crypto bubble visualization, portfolio tracking, financial news, and an AI research chat — all in a dark, glassmorphic interface.

### Long-term vision
BlackEclipse will grow into a **zero-configuration, agentic finance research tool** where users bring their own data sources (or use free built-in ones) and an AI agent performs research, screening, monitoring, and analysis. The immediate goal (Phase 1) is a working **data system**; the next is **agentic research agents** in the style of Hermes.

### What problem it solves
Free, good-quality market data APIs are scarce or expensive. Most users can't afford premium data feeds. BlackEclipse solves this by:
1. Working **out of the box with zero configuration** (demo data → free sources).
2. Letting users plug in their **own API keys** (Finnhub, Alpha Vantage, etc.) when they have them.
3. Providing a **free agentic scraper** (Yahoo Finance + lightweight HTML fallback) for markets without paid coverage.

### Who the intended users are
- Technical professionals: developers, quant researchers, analysts, and power users.
- Self-hosters who want a free, open, privacy-respecting research terminal.
- Open-source contributors extending the platform.

### What makes BlackEclipse different
- **Zero-config by default** — runs immediately with demo data, no keys, no DB setup.
- **Provider-agnostic** data + AI layers — swap sources/models freely.
- **Agentic direction** — a chat that becomes a real tool-using research agent.
- **Bloomberg-style density** — information-rich, data-first, professional.

### Core product principles
1. **Zero configuration** — the user should configure as little as possible.
2. **Free by default** — prefer open/free sources; paid APIs are optional opt-ins.
3. **Reuse before rebuild** — reuse existing components, hooks, and services.
4. **Data accuracy over appearance** — financial correctness is paramount.
5. **Open-source friendly** — no secret-only behavior, no hardcoded keys, clear docs.
6. **Dark, dense, professional** UI — not a generic AI dashboard.

---

## 2. System Architecture

### Architecture Map (current, accurate as of this writing)

> This is the deep reference. The canonical, readable summary with the same
> layer model lives in [`../docs/ARCHITECTURE.md`](../docs/ARCHITECTURE.md) and
> [`../docs/OVERVIEW.md`](../docs/OVERVIEW.md). Where they overlap, **the code
> wins**; fix the doc.

```
User
 │
 ▼
UI / Shell (StockChat terminal — ONE page, keep-alive tabs)
 ├── ChatBot tab        → src/components/screens/stock-chat.tsx → src/lib/agent/*
 ├── Command Center     → src/components/screens/dashboard/ → src/lib/workspace/ + src/lib/dashboard/
 ├── Chart Workspace    → src/components/market-workspace/ → src/lib/market-workspace/
 ├── Market Screener    → MarketOverviewScreen (market-overview.tsx + use-screener-filters.ts)
 ├── Portfolio          → src/components/screens/portfolio/ → use-portfolio-engine.ts
 ├── Journal            → src/components/journal/ → src/lib/journal/
 ├── News               → MarketNews → /api/news (reads JDDS; RSS ingested in background)
 ├── Market Bubbles     → market-bubbles.tsx
 ├── Economics          → src/components/screens/economics/ → /api/economics
 ├── Price Alerts       → src/app/alerts/ → src/lib/alerts/ (server poll loop)
 └── Chart (embedded)   → embedded-chart.tsx / tradingview-chart.tsx
 │
 ▼
Client Data Layer
 ├── DataHub (src/lib/workspace/data-hub.ts) — pub/sub topics, TTL, fan-out
 ├── Zustand stores — sidebar, dashboard, search, market-workspace, aurora
 └── Portfolio engine (src/hooks/use-portfolio-engine.ts) — pure FIFO/LIFO math
 │
 ▼
API / Services (src/app/api/**/route.ts — thin, server-only, api-guard protected)
 └── stocks · quote · price-history · asset-details · symbols · markets · indices ·
     forex · commodities · heatmap · news · economics · search · agent ·
     journal/* · alerts/* · scraper · refresh · settings · cron
 │
 ▼
JDDS — jdds.db (SQLite via Prisma + better-sqlite3, src/lib/db.ts)
 ├── Market universe: Market, Asset, Price, IndexQuote
 ├── News: NewsItem, SourceHealth
 ├── Macro: MacroSeries, CronJob, SystemConfig
 ├── Research memory: ResearchReport, AgentRun, ResearchFinding
 ├── Alerts: PriceAlert, PriceAlertEvent, Candles
 └── Trading journal: JournalProfile, TradingAccount, Strategy, … , Review
 │
 ▼
Background workers (all in-process, started from src/instrumentation.ts)
 ├── Price refresh (src/lib/scraper/scheduler.ts)      — default 15 min
 ├── Universe sync (daily) + News ingest (default 5 min)
 ├── Boot warm-up (prod-only unless BE_WARMUP=1)
 └── Alert monitor (src/lib/alerts/alertMonitor.ts)
 │
 ▼
Data Sources
 └── TradingView scanner (whole-market) · yfinance Python bridge ·
     RSS feeds (free) · crypto/macro providers · user API keys · demo fallback
```

### Frontend
- **Next.js 15 App Router**, React 19, TypeScript, Tailwind CSS v4.
- Client components marked `'use client'` at the top of each file.
- The app is **one page**: `src/app/page.tsx` renders `<StockChat />`, which owns
  the `activeTab` state machine and keep-alive tabs (`AppTab` in
  `src/components/layout/sidebar.tsx`). There is no URL routing for main screens.
- Screens are loaded with `next/dynamic` + `ssr: false` (memory decision — do not
  convert to static imports).
- Reusable primitives in `src/components/ui/` (button, card, dialog, tab-bar, …).

### Backend
- Many route groups under `src/app/api/**/route.ts` — see the map above. Handlers
  are thin and server-only; mutating routes go through `src/lib/api-guard.ts`.

### Zero Configuration Policy
- The app runs with **zero setup**: `npm install && npm run dev`. `instrumentation.ts`
  seeds the US universe and starts the schedulers; `jdds.db` ships as a seed snapshot.
- **Data source priority (user configures as little as possible):**
  1. **Agentic scraper** (primary) — free, built-in, works for any market with zero setup.
  2. **User-provided API** (optional) — used only if the user supplies a key (Finnhub, Alpha Vantage, etc.).
  3. **Demo data** (fallback) — always works when no live source is available, behind a visible `DEMO` banner.
- The user should **never be required** to configure anything. The agentic scraper is the default.

### API Layer
- Route groups are listed in the Architecture Map above. `/api/news` reads from
  JDDS (`NewsItem`) rather than fetching feeds per request; RSS ingestion happens
  in the background (`src/lib/news/ingest.ts`).

### Database — JDDS (SQLite)
- **`jdds.db`** (SQLite) via **Prisma + `@prisma/adapter-better-sqlite3`**;
  `src/lib/db.ts` owns the client and exports `prisma` + `yieldToEventLoop()`.
- Schema in `prisma/schema.prisma`, organized in domains (market universe, news,
  macro, scheduling/config, research memory, alerts, trading journal). See the
  Architecture Map above for the model list.
- **Dedup by constraint.** `Asset` unique on `[marketId, symbol]`; `Price` keyed
  by `assetId`; `NewsItem` has a `dedupKey`. Imports are idempotent upserts.
- **Auth-ready, not auth-ful.** The journal carries an optional owner concept so a
  `User` relation can be added later. There are no accounts today.
- **Synchronous-write discipline.** better-sqlite3 blocks the event loop, so bulk
  writers chunk and `yieldToEventLoop()`. See `docs/DATA-FLOW.md`.
- Client-only state (sidebar, dashboard layouts, search, market-workspace,
  aurora) persists to **localStorage**, not the DB. The committed `jdds.db` is a
  **seed snapshot** — do not re-commit it on routine changes (see the
  `black-eclipse-db` skill).

### Data Ingestion
- **PRIMARY: agentic scraper** — a smart scheduler that scrapes market data for free. It is timezone-aware (only scrapes open markets), priority-based, and de-duplicated. This is the default source so users configure nothing.
- **SECONDARY: user-provided API** — optional keys (Finnhub, Alpha Vantage, etc.) override the scraper for that source when supplied.
- **FALLBACK: demo data** — used when no live source is available or reachable, behind a `DEMO` banner.
- Full detail lives in [`../docs/DATA-FLOW.md`](../docs/DATA-FLOW.md) — read it before touching ingestion.

### Market data providers
- **PRIMARY: TradingView scanner** (`fetchers/tradingview.ts`) — a whole-market scan prices an entire market in ~1 request; the primary path and covers markets Yahoo misses.
- **SECONDARY: yfinance bridge** (`fetchers/yfinance.ts` + `scripts/yfinance_bridge.py`) — batched Python bridge for markets TradingView covers poorly (optional Python 3.9+).
- **FALLBACK chain:** `fetchers/http.ts`, `fetchers/browser.ts` (Playwright), `fetchers/scrapling.ts`, `fetchers/crypto.ts`. `SourceHealth` learns which source is reliable.
- **OPTIONAL: user-supplied** Finnhub/Alpha Vantage/Twelve Data when a user configures them.
- Symbols map to TradingView via `getTradingViewSymbol()` in `src/lib/utils.ts`.

### Background workers / scheduled jobs
All in-process, started from `src/instrumentation.ts` (no external daemon). They
coordinate through mutex flags so two heavy SQLite write storms never collide.

| Worker | Cadence | Source |
|---|---|---|
| Price refresh | default 15 min | `src/lib/scraper/scheduler.ts` |
| Universe sync | daily | `src/lib/scraper/scheduler.ts` |
| News ingest | default 5 min | `src/lib/news/ingest.ts` |
| Boot warm-up | once (prod-only unless `BE_WARMUP=1`) | `src/lib/scraper/scheduler.ts` |
| Alert monitor | polling loop | `src/lib/alerts/alertMonitor.ts` |

### Agent/AI architecture
- `src/lib/agent/types.ts` defines `AgentProvider`, `AgentTool`, `ChatMessage`.
- `src/lib/agent/mock-provider.ts` — built-in keyword-based responder (last-resort fallback).
- `src/lib/agent/openai-provider.ts` — OpenAI-compatible provider (OpenAI / Ollama / Anthropic-style) that runs **server-side**; the client reaches it via `POST /api/agent/chat`.
- `src/lib/agent/registry.ts` — `getAgentProvider()` returns the first configured provider else mock. `NEXT_PUBLIC_LLM_CONFIGURED` (set by `instrumentation.ts`) tells the client whether a real LLM exists.
- `src/lib/agent/loop.ts` + `tools.ts` — the tool-calling loop and tool registry (query data, scrape, search); `research.ts` is the multi-agent research pipeline that persists findings (`ResearchReport` / `AgentRun` / `ResearchFinding`).
- `src/components/screens/stock-chat.tsx` calls `getAgentProvider().chat(...)` for replies; research-worded questions hit the research engine.

### Charts & visualization
- ECharts (`echarts` + `useEChart` in `src/components/screens/portfolio/use-echart.ts`) for dashboard/chart widgets; TradingView widget via `src/components/screens/embedded-chart.tsx` and `tradingview-chart.tsx`; Recharts for portfolio charts.
- `ogl` WebGL for the **Aurora background** (`src/components/ui/Aurora.tsx`).

---

## 3. Technology Stack

### CURRENT (verified in package.json)
| Layer | Tech |
|---|---|
| Framework | Next.js **15.5.18** |
| Language | TypeScript **5** |
| UI | React **19.1.0** |
| Styling | Tailwind CSS **v4** + tw-animate-css + class-variance-authority |
| Components | @base-ui/react **1.5.0** (shadcn-style), lucide-react icons |
| DB | Prisma **7.9.1** + @prisma/adapter-better-sqlite3 + better-sqlite3 |
| Workspace | @dnd-kit/core + @dnd-kit/sortable + zustand + immer |
| Charts | echarts **6.1.0**, Recharts **3.8.1**, TradingView widget |
| Search | flexsearch **0.7.31** |
| Scraping | cheerio, playwright, `scripts/yfinance_bridge.py` (Python) |
| Scheduling | node-cron **4.6.0** (in-process) |
| 3D/GL | ogl **1.0.11** |
| News | rss-parser **3.13.0** |
| Alerts/agent | nodemailer, axios, duck-duck-scrape |
| PDF | jspdf + jspdf-autotable |
| Utils | clsx, tailwind-merge |
| Tests | Vitest **4.1.10** |

### PLANNED (not yet implemented — do not treat as current)
- A broker / paper-trading integration (the `trading`-category dashboard
  widgets are `UNAVAILABLE` stubs today).
- Vercel/serverless support for the in-process SQLite scheduler (a
  `POST /api/cron/run` endpoint exists for hosted schedulers).

### EXPERIMENTAL / DEPRECATED
- The original **JDdS daemon** and its PostgreSQL provider system were **removed**. Do not reintroduce them without updating this file.
- `src/lib/customize/` — the older customization kernel, **superseded** by
  `src/lib/workspace/` (ADR-005). The folder no longer exists; do not rebuild it.
- `@base-ui/react` v1.5.0 has **SSR/hydration quirks** — Portal-based components (Tooltip, Dialog) must be mounted-gated.

---

## 4. Data Architecture

### Core entities (DB — see `prisma/schema.prisma`)
- **Market universe** — `Market`, `Asset` (unique `[marketId, symbol]`), `Price`
  (one per `assetId`, `source: 'scraper' | 'csv'`), `IndexQuote`.
- **News** — `NewsItem` (unique `dedupKey`), `SourceHealth`.
- **Macro** — `MacroSeries` (JSON cache keyed by `cacheKey`).
- **Scheduling & config** — `CronJob`, `SystemConfig`.
- **Research memory** — `ResearchReport`, `AgentRun`, `ResearchFinding`.
- **Alerts** — `PriceAlert`, `PriceAlertEvent`, `Candles`.
- **Trading journal** — `JournalProfile`, `TradingAccount`, `Strategy`,
  `StrategyRule`, `Setup`, `Tag`, `JournalDay`, `DailyReview`, `DailyEmotion`,
  `Trade`, `TradeExecution`, `TradeScreenshot`, `TradeAnnotation`, `TradeTag`,
  `MarketContext`, `JournalEntry`, `Review`.

Client-side shapes:
- `StockItem` — demo/screener record (`market-data.ts`).
- `Message` (`src/types/chat.ts`) — chat messages.
- Portfolio/transaction shapes come from `use-portfolio-engine.ts`; persisted client-side.

### Relationships
- The journal domain is the most relational (profiles → accounts → strategies →
  trades → executions/annotations). Market data is upsert-only and keyed by
  unique constraints. Optional journal owner is reserved for a future `User`.

### Market data flow
1. Background workers scrape/import into **JDDS** (see the map above).
2. Screens read through an API route (`/api/stocks`, `/api/indices`, …) or a
   DataHub topic that wraps it.
3. `use-screener-filters.ts` applies filter/sort logic as a pure hook; the
   screener filters/paginates **server-side**.
4. Demo data (`market-data.ts`) is the fallback when no universe is loaded.

### Symbol/universe management
- `getTradingViewSymbol()` maps raw symbols → TradingView format (crypto, indices, PSX `.KA`, India `.NS`, etc.).
- `universe-sync.ts` scans TradingView markets, upserts new listings, and
  deactivates symbols that miss repeatedly (daily).

### Data normalization & validation
- Filter logic in `use-screener-filters.ts` parses market-cap/volume strings (`1.3T`, `28.4B`, `540M`) to numbers.
- News sentiment is a keyword heuristic (`src/lib/sentiment.ts`).

### Data freshness
- **`Price.source`** is the provenance field: `'scraper'` = live scrape, `'csv'` = imported.
- `Price.updatedAt` / `CronJob.lastRunAt` tell you how old data is.
- DataHub entries carry a `DataSource` label
  (`LIVE | CACHED | HISTORICAL | DEMO | ESTIMATED | UNAVAILABLE`).
- Never present stale or simulated data as live. See `docs/DATA-FLOW.md`.

---

## 5. Important Architectural Rules

1. **Do not duplicate business logic.** Reuse `use-screener-filters.ts`, `use-portfolio-engine.ts`, and the agent layer.
2. **Reuse existing services before creating new ones.**
3. **Do not bypass the established patterns** (client components, ui primitives, screens).
4. **Do not introduce unnecessary dependencies.** If a new dep is needed, justify it in REMEMBER.md.
5. **Keep frontend and backend responsibilities separated.** Server-only code (RSS parsing, secrets) must live in API routes, not client components.
6. **Prefer existing patterns over new ones.**
7. **Preserve backward compatibility** unless explicitly instructed otherwise.
8. **Never silently change data shapes** that screens depend on (e.g., `StockItem` fields).
9. **Never remove existing functionality without confirming its dependency chain.**
10. **Never put secrets or API keys in client-side code.**
11. **Memory discipline:** the codebase is large (market-overview.tsx is ~1900 lines). Keep splitting large components into hooks/modules; avoid re-bloating a single file.

---

## 6. Architectural Decision Record (ADR)

**What is an ADR?** It is a short note recording *why* a significant architecture decision was made — like a git commit message for architecture. It exists so future AI agents understand the reasoning instead of re-deciding or re-litigating it. Write one whenever you make a meaningful choice. Keep it to a few lines.

### ADR-001 — Demo data + zero-config (2026)
**Decision:** Ship with demo data; no DB, no keys required.
**Reason:** Zero-config policy + open-source friendliness.
**Impact:** All screens work immediately; real data is a future opt-in.

### ADR-002 — RSS for news (2026)
**Decision:** Use free RSS feeds (Yahoo/CoinDesk/CoinTelegraph/CNBC) for news.
**Reason:** No API key, no rate limits, open standard.
**Impact:** `/api/news` returns live news with offline mock fallback.

### ADR-003 — Agent provider abstraction (2026)
**Decision:** Define `AgentProvider` interface; mock by default; plug in real LLMs later.
**Reason:** Keeps the chat functional now and enables Hermes-style agents later.
**Impact:** UI calls `getAgentProvider().chat()`; adding a real provider is additive.

### ADR-004 — Agentic scraper as primary data source (2026)
**Decision:** The default market-data source is a free, built-in agentic scraper; user APIs are optional opt-ins; demo data is the fallback.
**Reason:** Users should configure as little as possible; free data must work out of the box.
**Impact:** Data source priority is always: agentic scraper → user API → demo.

### ADR-005 — Customization kernel (2026)
**Decision:** All page customization is driven by the shared kernel in `src/lib/workspace/` (`useWorkspace` + `WorkspaceCanvas` + widget registry). Layouts use the **section → column → widget model (v2)**: sections hold rows of 1–4 columns with relative weight shares (1–6); widget cards stack inside columns with optional fixed pixel heights. Stored layouts are validated/normalized on load (corrupt data falls back without overwrite); presets are curated section templates. Pages get edit-mode chrome (drag/drop, add/remove widgets, height + column-width resize, column counts, templates) through the kernel. No page-local layout state or storage code.
**Reason:** The flat span model could not express free-form placement (multiple widgets per column, individual column widths). A prior v3 "element model" (`src/lib/customize/`) was sketched in docs but never shipped — the workspace kernel is the real implementation.
**Impact:** Adding a customizable page = one widget registry + `useWorkspace()` + `<WorkspaceCanvas renderWidget={...}>`. The fund workspace and portfolio pages are migrated; other screens follow when touched (see `skills/CUSTOMIZE.md`).

### ADR-006 — Workspace kernel stack: dnd-kit + Zustand + Immer (2026)
**Decision:** The customization kernel is built on three libraries: **dnd-kit** (`@dnd-kit/core`) owns drag & drop (`DndContext` + `PointerSensor` + `useDraggable`/`useDroppable` + `DragOverlay`), **Zustand** owns editor/layout/selection state (one cached store per workspace storageKey, selector subscriptions, `selectedWidgetId`/`dragging`), **Immer** owns layout mutations (all ops in `ops.ts` are draft mutators invoked via `produce` in the store's `commit()`).
**Reason:** Replaced hand-rolled pointer-drag DOM surgery, useState plumbing, and manual structural clones. dnd-kit gives accessible, collision-driven DnD; Zustand gives cross-mount state without prop drilling; Immer removes clone boilerplate and makes ops trivially testable (tests wrap calls in `produce`).
**Impact:** `npm i @dnd-kit/core zustand immer` are required deps. New layout ops must follow the draft-mutator signature in `ops.ts` (mutate the draft, return void) and get a unit test. Persisting happens automatically inside `commit()`; never call `saveWorkspace` elsewhere.

### ADR-007 — Page-header icon tiles (2026)
**Decision:** Every page header uses the portfolio-style icon tile: a 56px (`h-14 w-14`) rounded-2xl container with `border-primary/25 bg-primary/15 shadow-lg shadow-primary/10` wrapping a 30px primary-colored lucide icon.
**Reason:** Bare inline icons looked inconsistent next to the redesigned portfolio header.
**Impact:** New screens copy the tile pattern (see market-overview.tsx or economics.tsx headers); do not revert to bare `w-7 h-7` icons.

### ADR-008 — Two-click placement confirm (2026)
**Decision:** Widget placement is **preview-then-confirm**, not drop-to-commit. Grab a card (click or drag-release), hover to preview a labeled ghost slot, then click again (or the ghost / Confirm button) to commit; **Escape or right-click cancels** at any point. Empty columns and inter-section strips are clickable while grabbing; auto-scroll runs during both drag and grab so off-screen rows are reachable.
**Reason:** Drop-to-commit was unreliable across devices (touch pan-gestures, scroll-adjusted deltas, off-screen targets) and gave users no chance to verify placement before committing. A two-click model is deterministic, works on mouse/touch/trackpad, and never mutates the layout until the user confirms.
**Impact:** The drop target is projected from the **real pointer** (native `pointermove` + `elementFromPoint`), not dnd-kit's scroll-adjusted delta. New ops: `moveWidgetToNewSectionAt` (insert above/below any section), `createSectionAt` (click strips to create empty sections), and `DropTarget.columnIndex` (insert new columns before/after an anchor). See `skills/CUSTOMIZE.md` for the exact interaction contract.

### ADR-009 — Central command palette + query grammar (2026)
**Decision:** Global search (⌘K) is a single command palette over
`src/lib/search/`, structured as two **pure, framework-free** steps: a **grammar**
(`grammar.ts`) that parses scopes/operators, then a **resolver** (`resolver.ts`)
that classifies intent, scores the static registry + FlexSearch universe, and
returns a `ResolvedSearch`. The palette dispatches a **`Destination`** on a bus
(`pendingDestination`) rather than navigating directly.
**Reason:** The command-center vocabulary (scopes/operators) is a user-facing
contract that must grow without touching the UI; keeping the query path fully
offline and deterministic avoids an LLM on every keystroke.
**Impact:** Extending scopes/operators means editing `grammar.ts` + its tests
together. Ranking stays pure; personalization (visit history), pins, and collapse
state live in the Zustand command store. `calc.ts`/`commands.ts` add offline
calculation and parameterized-command autocomplete. See `docs/ARCHITECTURE.md`
→ "The command center".

### ADR-010 — Universal Data Connector Layer (2026)
**Decision:** A capability-addressed connector tier under `src/lib/connectors/`
sits after the scraper chain and before route-level demo fallbacks. Consumers
request a *capability* (`PRICE`), never a provider. Custom API data lands in
dedicated `CustomDataset*` tables and can never write `Asset`/`Price`/`Candles`.
**Reason:** Operators need to bring their own REST API without a rewrite per
provider, while preserving ADR-004 precedence and the "never fabricate" rule.
**Impact:** `DataSource` gained `CUSTOM`; topics may return a provenance
envelope. Credentials are AES-256-GCM encrypted (`.connector-key` locally or
`CONNECTOR_SECRET_KEY` hosted). No automatic cross-provider fallback.

### ADR-011 — Investor Eye is a separate event/intelligence tier, reused not forked (2026)
**Decision:** Investor Eye ("God's Eye") is built as a new **event + world-state
tier** under `src/lib/investor-eye/`, **not** as another connector capability and
**not** as a second market/portfolio/news stack. It:
1. registers its own `EventSource` adapters (GDELT, USGS) instead of forking the
   existing `DataConnector` contract, but reuses its hardened `safeGet` transport;
2. persists only **additive** JDDS models (`Country`,
   `GeopoliticalEvent`, `EventEntity`, `SourceRun`) — **no graph database**, no
   Redis, no microservice;
3. visualizes through a provider-agnostic `MapLayer` abstraction rendered by
   ECharts (already a dependency), so the visualization can be swapped later
   without touching the data layer;
4. sources market observations from the **existing** `/api/indices` path
   (`IndexQuote` + the yfinance bridge) and portfolio exposure from the
   **existing** `use-portfolio-engine`, never duplicating them;
5. keeps the query path fully deterministic (keyword + gazetteer NL search, no
   LLM), matching ADR-009.
**Reason:** The repository is a single-page, SQLite-backed SPA with no geo/map
infrastructure and no geopolitical-event model. Building the smallest robust
foundation that reuses existing services avoids the duplicate-architecture and
over-build traps the spec explicitly warns against.
**Impact:** A new `investor-eye` tab, `country-fill`/`scatter`/`effect-scatter`/
`lines`/`heatmap` layer types (extensible via `registerLayer()`), and honest
provenance (`LIVE`/`CACHED`/`HISTORICAL`/`UNAVAILABLE`). A failed source is
`UNAVAILABLE`, never a fake zero; the map and page still load on partial source
failure. Optional authenticated sources (e.g. ACLED) are supported but never
required. See `docs/investor-eye-architecture.md` and `docs/ARCHITECTURE.md`
→ "Investor Eye".
