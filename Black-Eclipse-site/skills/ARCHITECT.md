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
3. Providing a **free agentic scraper** (TradingView whole-market scanner + a yfinance Python bridge, with HTML/Playwright fallbacks) for markets without paid coverage.

### Who the intended users are
- Technical professionals: developers, quant researchers, analysts, and power users.
- Self-hosters who want a free, open, privacy-respecting research terminal.
- Open-source contributors extending the platform.

### What makes BlackEclipse different
- **Zero-config by default** — runs immediately with a self-seeding SQLite vault (`jdds.db` ships as a seed snapshot), demo data, and no keys required.
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
 ├── Market Screener    → MarketOverviewScreen (market-overview.tsx + use-screener-filters.ts,
 │                        use-global-markets.ts, use-market-tabs.ts, market-*-tables.tsx)
 ├── Portfolio          → src/components/screens/portfolio/ → use-portfolio-engine.ts
 ├── Journal            → src/components/journal/ → src/lib/journal/
 ├── News               → MarketNews → /api/news (reads JDDS; RSS ingested in background)
 ├── Market Bubbles     → market-bubbles.tsx
 ├── Economics          → src/components/screens/economics/ → /api/economics
 ├── Price Alerts       → src/app/alerts/ → src/lib/alerts/ (server poll loop)
 ├── Investor Eye       → src/components/investor-eye/ → src/lib/investor-eye/ (world-state tier)
 └── Chart (embedded)   → embedded-chart.tsx / tradingview-chart.tsx
 │
 ▼
Client Data Layer
 ├── DataHub (src/lib/workspace/data-hub.ts) — pub/sub topics, TTL, fan-out
 ├── Zustand stores — sidebar, dashboard, search, market-workspace, aurora, investor-eye
 └── Portfolio engine (src/hooks/use-portfolio-engine.ts) — pure FIFO/LIFO math
 │
 ▼
API / Services (src/app/api/**/route.ts — thin, server-only, api-guard protected)
 └── stocks · quote · price-history · asset-details · symbols · markets ·
     indices · forex · commodities · heatmap · news · economics · search · agent ·
     journal/* · alerts/* · scraper · refresh · settings · cron ·
     connectors (data-sources, datasets, providers, provider-keys) ·
     investor-eye/* (state, events, countries, markets, layers, economy,
     companies, portfolio, risk, analogues, query, graph, health)
 │
 ▼
JDDS — jdds.db (SQLite via Prisma + better-sqlite3, src/lib/db.ts)
 ├── Market universe: Market, Asset, Price, IndexQuote
 ├── News: NewsItem, SourceHealth
 ├── Macro: MacroSeries, CronJob, SystemConfig
 ├── Research memory: ResearchReport, AgentRun, ResearchFinding
 ├── Alerts: PriceAlert, PriceAlertEvent, Candles
 ├── Connectors: DataConnector, ConnectorMapping, CustomDataset*
 ├── Investor Eye: Country, GeopoliticalEvent, EventEntity, Relationship, SourceRun
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
     RSS feeds (free) · crypto/macro providers · user API keys · demo fallback ·
     Investor Eye event feeds (GDELT, USGS, NASA FIRMS, conflict RSS)
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
| Components | @base-ui/react **1.5.0** (shadcn-style), @phosphor-icons/react icons (aliased to legacy Lucide names in `src/lib/icons/`) |
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
- **Connector layer** — `DataConnector`, `ConnectorMapping`, `CustomDataset`,
  `CustomDatasetField`, `CustomDatasetRecord` (custom API data is isolated here
  and can never write `Asset`/`Price`/`Candles` — ADR-010).
- **Investor Eye (world-state)** — `Country`, `GeopoliticalEvent`,
  `EventEntity`, `Relationship`, `SourceRun` (ADR-011). The relationship graph
  is this relational edge table, aggregated by a pure builder — no graph DB.

Client-side shapes:
- `StockItem` — demo/screener record (`src/lib/screener/data.ts`).
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
4. Demo data (`src/lib/screener/data.ts`) is the fallback when no universe is loaded.

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
11. **Memory discipline:** large screens are split into hooks/modules (the screener lives in `market-overview.tsx` + `use-global-markets.ts` + `use-market-tabs.ts` + `market-overview-global-markets.tsx` + `market-*-tables.tsx`). Keep components small; avoid re-bloating a single file.

---

## 6. Architectural Decision Record (ADR)

**What is an ADR?** It is a short note recording *why* a significant architecture decision was made — like a git commit message for architecture. It exists so future AI agents understand the reasoning instead of re-deciding or re-litigating it. Write one whenever you make a meaningful choice. Keep it to a few lines.

### ADR-001 — Demo data + zero-config (2026)
**Decision:** Ship with demo data seeded into JDDS; no keys required. `jdds.db` is a committed seed snapshot so the app boots populated with zero setup.
**Reason:** Zero-config policy + open-source friendliness.
**Impact:** All screens work immediately; real data is a future opt-in. **Superseded in part:** the DB was added later (SQLite JDDS) — see ADR-004 and `docs/ARCHITECTURE.md`. The "no DB" clause is historical, not current.

### ADR-002 — RSS for news (2026)
**Decision:** Use free RSS feeds (Yahoo/CoinDesk/CoinTelegraph/CNBC) for news.
**Reason:** No API key, no rate limits, open standard.
**Impact:** RSS is ingested in the background into `NewsItem`; `/api/news` serves from JDDS and returns `source: "jdds"` (`"error"` on a DB failure) with `lastIngestAt`. The client may fall back to its local mock when the feed is empty. **Correction:** the old claim that the route fetches live with an offline mock fallback is stale — the route never fetches feeds.

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

### ADR-012 — Data-source governance is its own registry, enforced by test (2026)
**Decision:** Every external Investor Eye source must have an entry in
`src/lib/investor-eye/source-catalog.ts` (provider, licence, terms URL,
commercial-use, API-key requirement, attribution, rate limit, freshness),
kept separate from the `EventSource` adapter and enforced by
`source-catalog.test.ts`.
**Reason:** "Public API" ≠ "free for commercial use"; fusing governance into
adapters makes a licence question answerable only by constructing a fetcher.
**Impact:** A new source = connector + normalizer + registry entry + catalog
entry, the last two held in sync mechanically. AIS/ADS-B/OSM/CelesTrak are
deliberately not wired. See `docs/DECISIONS.md` ADR-012.

### ADR-013 — Operator API keys are an encrypted vault over env vars (2026)
**Decision:** Settings → API Keys credentials are AES-256-GCM-encrypted in
`SystemConfig` via `connectors/secrets`, declared once in `PROVIDER_KEYS`
(`src/lib/provider-keys.ts`), and resolved **env var first, vault second**;
`applyStoredKeysToEnv()` copies them into `process.env` at boot.
**Reason:** Env vars suit a deployment but not a zero-config local install, and
there was no single place to enter a credential.
**Impact:** The key value never crosses the API boundary (only `stored`,
`fromEnv`, masked hint). Adding a provider is one `PROVIDER_KEYS` entry. See
`docs/DECISIONS.md` ADR-013.

### ADR-014 — Map-local loading states must never portal to the body (2026)
**Decision:** A region-scoped loading/empty overlay renders inside that region;
`TopLoader` is reserved for whole-screen loads and must never be used inside a
card, panel, or widget.
**Reason:** `TopLoader` portals to `document.body` at `z-[45]`, so a map-local
spinner silently became a full-app blocker frozen at 95%.
**Impact:** The rule applies to any region-scoped loader; the globe halo
contract is now covered by a test. See `docs/DECISIONS.md` ADR-014.

### ADR-015 — Media widgets tear down their own player when not visible (2026)
**Decision:** A widget that plays media must not rely on the shell to stop it.
The keep-alive tab model keeps visited screens MOUNTED and hides them with
`display:none`, and `WidgetDefinition.lazy` is declared but never read, so an
embed left mounted keeps streaming. Such a widget owns its teardown: an
`IntersectionObserver` on its root (zero intersection inside a `display:none`
ancestor, and when scrolled off) plus a `visibilitychange` listener (browser
tab). Both are required — each misses the case the other covers.
**Reason:** Nothing in the repo tore an embed down on visibility; a live-stream
widget would burn bandwidth and CPU indefinitely on an unwatched tab.
**Impact:** Applies to any future media widget (video, audio, streaming, WebGL
animation). `lazy` remains dead — do not treat it as a teardown mechanism. See
`docs/DECISIONS.md` ADR-015 and `docs/ARCHITECTURE.md` → "Live Intelligence".

### ADR-016 — Track board replaces the row-band layout grammar (2026)
**Decision:** The widget workspace's default arrangement is a masonry track
board. A section's columns are vertical tracks; the pure packer
`src/lib/workspace/pack.ts` (`rebalanceColumns`/`rebalanceLayout`) distributes
each section's cards into the shortest track by estimated height. Every
placement sizes to content (`height: null`) with an intrinsic floor
(`WidgetPlacement.minHeight`, from `WidgetDefinition.minHeight` /
`WIDGET_MIN_HEIGHT`). `WorkspaceLayout.version` is `2`;
`buildMarketViewLayout`/`composeBoard` replace `composeRows`; `HEIGHTS`,
`LayoutRow` and the `items-start` row renderer are removed.
**Reason:** The row-band grammar was structurally gappy — a rigid full-width row
of content-height columns left dead space beside any short widget, and the pinned
side rails left ~490px blank under the Watchlist. Pinned `HEIGHTS` were too
coarse for real content, so cards clipped or left empty tails.
**Impact:** Packing is COMPOSE-TIME only (defaults, templates, imports) — never
inside the store's `commit`, because masonry has no stable fixed point for
equal-height cards and re-packing on edit would silently reshuffle dropped cards.
Storage reset to v7 dashboards / v3 funds / `be_dashboards_index_v7`; old layouts
are not migrated. The 4-track capability remains for user drag/drop. See
`docs/DECISIONS.md` ADR-016 and `docs/ARCHITECTURE.md` → "Dashboard layout grammar
(personas + track board)".

### ADR-017 — Frame vs grow card sizing and resizable side panels (2026)
**Decision:** Every track-board placement carries EITHER a frame
(`WidgetPlacement.defaultHeight` — a definite box whose body stretches, for
charts/maps/live/scrollable tables) OR a grow floor (`WidgetPlacement.minHeight`
— a floor under self-sizing content, for compact tiles). The renderer keys its
body class off `isDefiniteCard(placement)`. Side zones get a persisted,
user-resizable width (`WorkspaceLayout.zoneWidths`, `ops.setZoneWidth`, clamped
180–520px via a drag handle; `main` is not resizable).
**Reason:** The single `minHeight` field collapsed widgets — a grow card got a
`min-h` frame but the body used `flex-1`/`flex-basis:0`, so content with no
intrinsic height (a chart, a scrollable list) rendered at zero height. Splitting
definite frames from growing tiles is what makes them render. Fixed side widths
also wasted space.
**Impact:** `defaultHeight` added and preserved by `normalizeLayout`;
`WIDGET_FRAME_HEIGHT` / `WidgetDefinition.defaultHeight` alongside
`WIDGET_MIN_HEIGHT` / `minHeight`. Personas redesigned into nine different band
shapes and renamed. Frame/grow confusion is the first thing to check when a
widget renders empty. See `docs/DECISIONS.md` ADR-017 and `docs/ARCHITECTURE.md`
→ "Dashboard layout grammar (personas + track board)".

### ADR-018 — Agentic runtime is Python (LangChain + LangGraph); separate agent-memory DB (2026)
**Decision:** The agentic harness runtime is **Python** — FastAPI + LangChain +
LangGraph in `python/harness/` — and owns agents, tools, model providers, harness
events and run persistence. Next.js is a thin front door that validates input,
resolves the agent preset + LLM config from the settings vault, assigns the run
id, and proxies. It also serves a guarded, read-only JDdS **data bridge** for the
Python tools. Run state and agent memory/skills live in a **separate** SQLite
file `agent-memory.db`, NOT JDdS.
**Reason:** The agentic side must not be written in TypeScript, and it must
connect every model. Python is where the LangChain/LangGraph ecosystem and
provider integrations live, making universal model coverage and agent authoring
configuration rather than bespoke TS adapters. The vault and Prisma are the two
things Python cannot own, which is why the front door keeps exactly those two
jobs. A separate DB keeps high-churn operational state off the committed JDdS
snapshot.
**Impact:** Agent runs require the Python stack, installed by `postinstall` /
`doctor.js`; without it runs return 503 — never a fake agent. Model coverage is a
provider catalog (`PROVIDER_CATALOG`) plus the OpenAI-compatible protocol. The
TypeScript Phase-1 kernel was retired; only validation, vault resolution, the
proxy and the data bridge remain in TS. A later phase must add an explicit
approval path before any non-`read` tool becomes callable. See
`docs/harness/architecture.md`, `docs/harness/decisions.md` (ADR-H1–H7) and
`docs/DECISIONS.md` ADR-018.

### ADR-025 — Skills are versioned procedures on the existing runtime; generated skills are inert (2026)
**Decision:** A Phase-3 "skill" is a versioned, machine-readable procedure
(`skill.json` + `SKILL.md` under `python/harness/skills/library/`) executed by the
**existing** Phase-1 `execute_run` graph — not a second runtime, tool registry or
agent loop. Manifests, permissions and lifecycle live in Python
(`python/harness/skills/`), persisted in `agent-memory.db`. Permissions are a
single **default-deny** policy enforced in code; Markdown instructions are data,
not a security boundary. The learning engine creates inert `LearningCandidate`
records from run traces; a candidate can only become an active skill through an
explicit operator-gated promote path, never automatically.
**Reason:** The brief forbids duplicate infrastructure and unrestricted
self-modification; a skill must reuse the hardened Phase-1/2 runtime and every
capability must stay reviewable. Instructions cannot be a boundary because they
are untrusted prose, so enforcement must be code (permission check + tool
allowlist on the composed `AgentConfig`).
**Impact:** New Phase-3 tables in `agent-memory.db` (idempotent DDL, no manual
migration). Runtime skills live under `python/harness/skills/library/`, distinct
from the unrelated `Black-Eclipse-site/skills/` *coding-agent* operating system.
The front door adds `/api/skills/**` + `/api/learning/**` proxies and a Skills
tab; the browser talks only to those routes (never the Python service or Prisma
directly). pydantic is reused for schema validation — no Zod. See
`docs/harness/phase-3-architecture.md` and `docs/DECISIONS.md` ADR-025.

### ADR-026 — Eclipse-Memory is a separate SQLite database and service (2026)
**Decision:** Memory, skills, learning, evaluations, corrections and mistakes
persist in a dedicated SQLite file **`eclipse-memory.db`**, owned by one service
(`python/harness/eclipse_memory/`), separate from `jdds.db` (market data +
Trading Journal) and `agent-memory.db` (run/event traces). Skill *definitions*
stay as reviewable files in `skills/library/`; all runtime state lives in the
DB (Option C hybrid). The Phase-3 `SkillStore` is now an alias for
`EclipseMemoryStore`, so there is one skill registry; existing Phase-3 skill
rows are imported once, idempotently and non-destructively.
**Reason:** The audit found memory was never written or recalled, and the system
prompt promised tools (`memory`, `skill_view`, `skill_manage`, `terminal`…) that
did not exist. A dedicated, inspectable database with an explicit write/retrieve
pipeline — plus real tools — fixes the behaviour; keeping authoring in files
keeps skills reviewable.
**Impact:** New `eclipse-memory.db`, `python/harness/eclipse_memory/`,
`memory_tools.py`, `/api/eclipse-memory/**`, and an **Eclipse Memory** tab.
`graph.execute_run` recalls scoped memory into each run and registers the
memory/skill tools on the existing registry. The system prompt was corrected to
name only real tools. Path config: `ECLIPSE_MEMORY_DB_PATH`. See
`docs/harness/phase-3-memory-progress.md` and `docs/DECISIONS.md` ADR-026.

### ADR-030 — Resilient multi-source research: structured failure diagnostics, independent routes, bounded retry (2026)
**Decision:** Web search and page fetch return a structured RetrievalDiagnostic (provider, category, HTTP status, latency, timeout, result count, bytes, parse outcome, retryability) instead of collapsing every failure into an opaque UNAVAILABLE; a JSON source document is accepted rather than rejected as 'not HTML'. Structured retrieval is one route among several: a direct SEC EDGAR source (tier primary, US issuers, identity-gated) and an operator-configurable second search provider (vault keys SEARCH_API_CONFIG/SEARCH_API_KEY) join the keyless DuckDuckGo default, with selection policy as explicit data in 
etrieval/planner.py (inancial_statements → [SEC, JDDS, WEB]). The loop retries only transient failures with bounded backoff, switches to the next independent provider, targets unresolved legs, and records a stopReason when it ends.
**Reason:** The NVDA run could not distinguish 'the web had nothing' from 'every route is broken'. Verified root causes: DuckDuckGo answered HTTP 202 with an anti-bot page that parsed to zero results and returned []; a valid pplication/json SEC XBRL response was rejected by a content-type gate; and escalation inspected only status == 'OK', discarding the reason. All web routes shared one transport, so there was no independent fallback.
**Impact:** src/lib/{retrieval-diagnostics,web-search,web-research}.ts, data-bridge.ts (sec_filings, 
esearch_health, diagnostics on web_search/web_fetch), python/harness/retrieval/{retry,sources,structured,planner,web,layer}.py, python/harness/research/{engine,run,receipt,escalation}.py; NVDA labeled eval python/harness/research/eval/nvda.py; operator smoke python/harness/research/smoke.py. Full decisions: ADR-H25–H28 in docs/harness/decisions.md.

### ADR-031 — Global market research: truthful capability matrix, suffix-aware identity, declared UA, provider eligibility (2026)
**Decision:** Coverage is reported as a per-market CAPABILITY MATRIX (recognition / searchable universe / quote / history / fundamentals / official filings / web+documents / observed health / live-checked) so a listed country is never read as 'every capability works'. Source health is keyed by the route dimensions (source x market x assetClass), never a market-level aggregate copied onto every provider. Instrument identity is global: a recognised exchange suffix (.TW, .KS, .L, …) is split into an implied market and the vault is queried for both the bare local code and the suffixed form; an unknown suffix is never guessed. Providers are gated by eligibility — SEC is skipped (not attempted-then-failed) for a non-US issuer. The shared fetch transport sends a DECLARED, email-contact User-Agent (required by SEC's fair-access policy) and handles JSON/XML/XBRL plus bounded text-PDF extraction. Escalation queries are market-aware (no global '10-K' assumption). Learning candidates carry the run's structured diagnostics and an explicit regional scope, remain inert, and promotion stays operator-gated.
**Reason:** Users reported US-centric failures on real non-US runs (TSMC/Samsung/Petrobras): all web fetch returned UNAVAILABLE, non-US tickers were 'not in the universe', SEC was attempted for a Taiwanese issuer, and coverage/health implied more than was true. Verified causes: (1) a spoofed browser UA gets 403 from SEC/TSMC IR, while a declared email-contact UA gets 200; (2) the vault stores bare local codes while users type Yahoo suffixes, so 2330.TW returned not_found though 2330 (TW) existed; (3) the SEC adapter's supports() gate was never consulted by the retrieval planner; (4) source-health collapsed recorded runs to (market, assetClass) and copied one aggregate onto every declared provider row, producing duplicates; (5) get_coverage instructed the agent to stop when JDdS lacked a ticker.
**Impact:** src/lib/{markets,web-research,web-search,retrieval-diagnostics}.ts, src/lib/harness/{capability,data-bridge,types}.ts, src/lib/fundamentals/providers/sec-edgar.ts, src/app/api/harness/data/route.ts; python/harness/{finance_tools,retrieval_tools,prompts}.py, python/harness/retrieval/structured.py, python/harness/research/escalation.py, python/harness/skills/learning.py, python/harness/eclipse_memory/{schema,store}.py. See docs/harness/decisions.md (ADR-H29..H32) and docs/DECISIONS.md ADR-031.

### ADR-033 — Aurora sentiment becomes an explainable Market Regime (2026)
**Decision:** The app-wide Aurora glow is driven by a transparent Market Regime model (src/lib/regime/) instead of a fixed 60% price / 40% coarse-RSS blend. A reading is a set of named components — price & breadth, volatility/options, macro/risk, news/narrative, positioning — each exposing score, weight actually used, availability, timestamp, source and confidence. Weights renormalize over the available set; missing inputs lower confidence (never a false neutral); stale inputs are excluded; a missing core price/breadth input makes the reading UNAVAILABLE. Taxonomy: Risk-on broadening / Fragile rally / Mixed / Risk-off / Narrative shock / Unavailable. Scope is explicit (selected market | US | global). All inputs come from JDDS only, through one new contract GET /api/regime. The glow stays decorative (pointer-events-none, aria-hidden); an accessible top-bar control opens the interactive frosted-glass breakdown, with actions to open Market Overview, filter news, ask Eclipse (be:ask-eclipse), and create a regime-change alert.
**Reason:** The old model was hardwired to US indices, exposed no confidence/data-age/provenance, used fixed weights, and could be influenced by cached/fallback data — attractive but not trustworthy. Financial data must never be fabricated; simulated/fallback/stale data must never read as live sentiment.
**Impact:** src/lib/regime/{types,scoring,client,store,visuals}.ts, src/app/api/regime/route.ts, src/components/layout/{aurora-glow,market-regime-control,top-bar}.tsx, src/components/ui/Aurora.tsx (added `dim`), src/components/screens/stock-chat.tsx (be:ask-eclipse), tests src/lib/regime/scoring.test.ts. See docs/DECISIONS.md ADR-033 and docs/ARCHITECTURE.md › Market Regime.


### ADR-034 — Autonomous-but-governed learning: provider layer, structured skill patches, hybrid namespaces, prompt segments (2026)
**Decision:** Four capabilities were added without relaxing any safety invariant. (1) External memory is a dedicated provider layer (python/harness/memory_providers/) implementing ONE MemoryProvider contract over the existing MCP boundary; external results are labelled provenance=external_provider / verified=false, fenced, native-first routed, never promoted, and external writes need an explicit user request AND approval (automatic external writes are absent by construction). (2) Self-improving skills are STRUCTURED patches (JSON-pointer replace/add/remove over an allowed-field set; identity/permission/tool/risk fields are not patchable) that always create a NEW SkillVersion; a stale base version is rejected, activation requires a passing evaluation, canary is limited to safe non-mutating skills, and rollback (manual or automatic on a regression/correction) is atomic and preserves both versions. (3) Memory retrieval uses logical namespaces and a bounded hybrid score whose semantic term can only nudge an already-authorized memory — never confirm, supersede, archive or authorize. (4) The prompt is split into immutable segments with an identity-only prompt_cache_key, so a new user message never invalidates the reusable prefix, and skills are injected as a bounded relevant-only manifest.
**Reason:** The product goal is autonomy in discovering, proposing, testing, versioning, activating, monitoring and rolling back improvements — but never autonomy in silently changing truth, permissions, financial-retrieval rules, or irreversible behavior. Each capability therefore ends at a reviewable, versioned, reversible or clearly-labelled boundary.
**Impact:** python/harness/memory_providers/* (new), python/harness/prompt_segments.py (new), python/harness/skills/{patches,versioning}.py (new), python/harness/eclipse_memory/hybrid.py (new); memory_tools.py, service.py, graph.py, main.py, agents.py; eclipse_memory/{policy,schema,store,skill_quality}.py; skills/{manifest,registry,evaluation}.py; migrations 12/13; routes /memory-providers/*, /skills/{id}/version-history + /skills/{id}/patch/**; TS skills-client/browser, eclipse-memory-client/browser/types, routes + a patch-version UI panel. Full decisions: ADR-H52—H55 in docs/harness/decisions.md.

### ADR-035 — Long-lived sessions, named profiles and reversible file editing (2026)
**Decision:** Sessions are first-class: a durable `ChatSession` (metadata + a bounded deterministic summary) in agent-memory.db, a run belongs to a session which belongs to one profile, session search ranks by the documented hybrid (exact phrase > BM25 > decision/correction/skill-failure/memory-action > recency > prose) with full filters, and a summary is searchable but never auto-injected. Named profiles are a metadata registry (eclipse_memory/profiles.py) over `.black-eclipse/profiles/` with per-namespace scoping, prompt profile, retention and settings, explicit READ-ONLY inheritance, and request-scoped isolation on every memory/session/skill/provider query. The Markdown memory projection is edited only through a targeted, atomic, versioned API (expectedVersion stale-edit guard, temp+fsync+rename, backup before regenerate, structured revision history + rollback + diff); SQLite remains canonical and archive/restore stay structured-memory actions.
**Reason:** Users need to continue long-lived sessions and keep work/personal/project memory isolated, and a hand-edited projection must not lose a concurrent edit, leave a partial file, or lack an audit trail — all without merging stores or adding infrastructure.
**Impact:** python/harness/persistence.py (ChatSession + run/session scope columns), session_index.py (build_summary), eclipse_memory/profiles.py, schemas.py (RunRequest ids), graph.py, main.py (/sessions*, /profiles*, filters); src/lib/harness/{memory-files,run-service,eclipse-memory-*,python-client}.ts, new /api/sessions, /api/profiles, /api/eclipse-memory/files/{edit,history}, and Memory Control Room tabs (Sessions/Profiles/Providers/Files/Skills + richer Overview). Full decisions: ADR-H56—H58 in docs/harness/decisions.md.

### ADR-036 - MCP Phase 6: trustworthy-before-capable hardening and resilience (2026)
**Decision:** The MCP layer is hardened in ordered phases. (1) The config contract is shareable and safe: `${VAR}`/`${env:VAR}` interpolation with a fail-closed remote rule, `selected_tools` include/exclude globs (legacy list unchanged), a static entry screen that REFUSES shell/interpreter/egress shapes at load, save and spawn, a fail-closed `trust` tier (`full`/`untrusted`) where an untrusted server needs a per-call approval for every non-read call and its own annotations can never activate a tool, and Eclipse tool names use a double-underscore boundary (`mcp__<server>__<tool>`) with the identity digest kept only as a genuine-collision last resort. The Python MCP read routes are operator-gated. (2) Lifecycle is resilient: separate jittered retry budgets, a call-time reconnect that re-checks authority, an honest session-expiry rule (a read replays once; a write returns `outcomeUncertain` and is never replayed), optional keepalive/recycle, POSIX orphan reaping via a stdlib-only supervisor (Windows relies on the SDK's Job Object), and lazy startup with a fingerprint-keyed on-disk schema cache. Every capability stays inert until an operator selects it; discovery never activates.
**Reason:** Everything users get wrong happens at the config boundary (a hostile entry that executes, a secret in plaintext, an unshareable file, an unusable filter, an undocumented authorization story), and one transient network blip permanently disabled a server until a manual reload while a crashed parent leaked children. Trust must be declared, not inferred from a server's own metadata, and a call that may have had an effect must say so rather than silently replay.
**Impact:** python/harness/mcp/{interpolation,screening,lifecycle,schema_cache,orphan_supervisor}.py (new); config.py, naming.py, client.py, manager.py, diagnostics.py, __init__.py; routers/mcp.py (read routes gated + save screening); python/requirements.txt (httpx2 pin); mcp-servers.example.json; tests python/tests/test_mcp_{config_hardening,lifecycle,orphan_reaping}.py. Full decisions: ADR-H67, ADR-H68 in docs/harness/decisions.md; progress docs/harness/mcp-phase-6-progress.md.

### ADR-037 - MCP data sources join native planning; sampling uses the run model; AC OAuth is a manual https step (2026)
**Decision:** An operator-declared MCP data tool (`data_source_tools: {tool: dataType}`) becomes a native `RetrievalSource` via `manager.mcp_sources()`, reaches `FinancialRetrievalLayer` through `ToolContext.mcp_manager`, and is considered by `plan_retrieval(additional_sources=...)` after native structured sources but before generic web; provenance stays `secondary`/`eclipseVerified=false` and JDdS is never silently upgraded. Server sampling (`sampling/createMessage`) runs on the runtime's own model adapter (`models.build_chat_model`) with the run's credentials and the policy token cap, still off by default. Eclipse-as-server is exercised by TWO offline clients (Streamable HTTP + SSE); the real Hermes interop is a documented manual step.
**Reason:** The deferred seams were real: without wiring, an MCP source could never be planned, a server sampling request could never be served, and "two clients" was asserted from one. The SDK's OAuth client refuses plain-http OAuth URLs (RFC 8252), so the interactive authorization-code leg is necessarily a manual https step — stated, not faked.
**Impact:** python/harness/mcp/{manager,mcp_retrieval,config,interactions}.py, python/harness/{tools,graph,service,retrieval_tools}.py, python/harness/retrieval/{layer,planner}.py, python/harness/routers/mcp.py; TS src/lib/harness/{mcp-types.ts}; tests test_mcp_source_planning.py, test_mcp_sampling.py, test_mcp_server_exposure.py, test_mcp_oauth.py. Full decision: ADR-H73 in docs/harness/decisions.md; progress docs/harness/mcp-phase-6-progress.md.

### ADR-038 - MCP config round-trip integrity: a save can never silently widen authority (2026)
**Decision:** `upsert_mcp_config` merges from the incoming model's `model_fields_set`, not `if value is not None`: absent means preserve, explicitly present means replace (including explicit `null`/`false`/`{}`/`[]` for clearing). An omitted field cannot be reset by a partial save; the UI can still clear a field because it always sends every field it owns. This makes a save provably unable to widen authority by omission (`trust`, `enabled_effects`, `tool_effects`, `data_source_tools`, `confirmed_catalog_digest`, `selected_tools`). `env` keeps its write-only merge; `install_mcp_integration` is create-if-absent; `public_dict()` emits the raw operator-set bounds so the wire is lossless. A pure TS module (`src/lib/harness/mcp-draft.ts`) owns view<->draft<->input mapping.
**Reason:** The Phase-6 field set lived only on the wire, not in the UI payload. Re-saving a server through Settings silently downgraded `untrusted`->`full`, disabled resources/prompts, dropped the data-source declaration and every tool effect, and invalidated the catalog confirmation - a silent authority widening.
**Impact:** python/harness/mcp/{config,runtime,introspection,oauth_flow,manager}.py, python/harness/service.py, src/lib/harness/{mcp-types,mcp-draft,mcp-client}.ts, src/components/screens/mcp-settings.tsx + src/components/screens/mcp/*, src/app/api/harness/mcp/{integrations/[id]/install,supply-chain}/route.ts; tests test_mcp_config_roundtrip.py, test_mcp_example_config.py, mcp-draft.test.ts. See docs/harness/decisions.md ADR-H74 and docs/harness/mcp-ui-parity-progress.md.

### ADR-039 - The release gate is local and runnable (2026)
**Decision:** Delete the unreachable `Black-Eclipse-site/.github/workflows/` (GitHub reads only root `/.github/workflows`; the repo git root is above the app dir) and replace it with ONE local gate: `npm run check:all` runs prisma generate, typecheck, lint, `npm test` and `npm run test:evals` in order, failing on the first error. The three eval gates (retrieval, contradiction, compaction) move into `npm test` via `scripts/test-evals.js` (offline, ~0.7s) using the explicit-`sys.path` launcher; the dead `semantic_cli` reference is removed. The CHANGELOG obligation is enforced by `.githooks/commit-msg` (non-doc change must stage the CHANGELOG; `SKIP_CHANGELOG_CHECK=1` bypass).
**Reason:** The release gate was fictional three ways: a CI job that could not pass, a workflow GitHub never read, and eval floors no local command ran.
**Impact:** .github/ removed; scripts/test-evals.js + scripts/check-all.js (new); package.json (`test:evals`, `check:all`, `test` includes evals); .githooks/commit-msg (new); scripts/install-git-hooks.js. See docs/harness/decisions.md ADR-H75 and docs/harness/engineering-hardening-progress.md.

### ADR-040 - A theme preset is holistic: it carries a partial ChatBot-backdrop snapshot (2026)
**Decision:** A preset is more than design tokens. `ThemePreset` and
`UserThemePreset` carry an optional **partial** `background` snapshot
(`Partial<BackgroundPrefs>`, validated by `normalizePresetBackground`). Selecting
a preset previews its backdrop (`useBackgroundStore.preview`, non-persisted) and
Apply commits it (`applyPreset(theme, background)`); the snapshot is **merged over
the user's live background prefs**, so a preset that only sets the wordmark keeps
the user's wallpaper and vice versa. `ChatWordmark` reads `previewPrefs ?? prefs`
so glyphs update live. The theme store calls the background store's adapter
(`applyBackgroundToDocument`) rather than subscribing to it — a store-to-store
subscription was a module **cycle** (`backgrounds.ts` imported `useThemeStore`);
`refreshBackground()` re-asserts the saved backdrop after every theme write.
**Reason:** Applying a preset changed colors/fonts/sidebar but left the ChatBot
landing (the most visible surface) untouched, because the two stores had no
coupling. The separation was intentional for *manual* backgrounds but wrong for a
unified "look".
**Impact:** src/lib/theme/{tokens,store,index}.ts, src/lib/backgrounds.ts,
src/components/screens/customization-settings.tsx (+ extracted
`customization-preview.tsx` to stay under the size ratchet),
src/components/chat/chat-wordmark.tsx, src/components/layout/{sidebar,top-bar}.tsx,
src/app/globals.css (`--font-heading`). Tests: tokens/store/backgrounds + new
preset-snapshot cases. See docs/ARCHITECTURE.md.

### ADR-019 — Provider-agnostic financial retrieval layer; web research is first-class (2026)
**Decision:** The agent requests an **objective + data type**, not a provider. A
dedicated `python/harness/retrieval/` package (`FinancialRetrievalLayer`) plans
the source(s) with a deterministic, explainable planner, retrieves them
(cache-aware, possibly in parallel), normalizes to one
`NormalizedFinancialObject`, validates, resolves source conflicts, and returns
provenance-carrying evidence. Tools call the layer; the layer is the only place
that knows JDdS, yfinance or the web exist. Web research
(`src/lib/web-research.ts`, the single shared search+fetch implementation) is a
first-class selectable path, not merely a fallback. A precise quantitative
request (historical prices, macro series, derived metrics) **never** uses web:
with no structured dataset the layer returns `UNAVAILABLE`.
**Why:** The Phase-2 objective is "what information do I need → what is the best
source → structured/cache/web/multiple → is the evidence fresh and reliable?" —
a decision that belongs in one explainable place, not scattered across tools.
It keeps the agent decoupled from every individual data source and keeps JDdS and
yfinance as *sources*, not mandates.
**Impact:** Adding a provider means implementing the `RetrievalSource` contract
and adding its name to the planner; source-selection policy is data. The
retrieval cache is in-process and shared across runs with in-flight
deduplication (no new database). See
[`harness/architecture.md`](./harness/architecture.md) and
[`harness/decisions.md`](./harness/decisions.md) (ADR-H10…H12).

---

### ADR-020 — A ticker is not an instrument identity; unhonoured qualifiers fail loudly (2026)
**Decision:** Instrument resolution requires a **canonical identity** —
`{ market, symbol, currency (ISO 4217), assetClass }` — not a bare ticker. Every
instrument resolution and payload carries it. A market qualifier (venue, country,
market id) is resolved through a single alias table (`resolveMarketId`); if it
cannot be honored the request **fails** (`market_unknown`). A bare ticker that
maps to more than one instrument is **`AMBIGUOUS`**, never a "best match". A
provider answer whose currency/market disagrees with the resolved identity is
**discarded**. `AMBIGUOUS` and `UNAVAILABLE` are correct, first-class outcomes.
**Why:** A live analysis of `FFC` (Fauji Fertilizer, PSX) returned a US
closed-end fund's price, stamped `realtime`, because the live path dropped the
`market` qualifier and fetched the bare ticker. Tickers are reused across venues,
asset classes and issuers (4160 colliding tickers in the committed master alone)
and carry no currency — a confidently wrong number is worse than no number.
**Impact:** `src/lib/instrument-identity.ts` owns resolution and returns a typed
failure union; the read-only bridge returns `AMBIGUOUS`/`UNAVAILABLE`; the Python
retrieval contract gains `AMBIGUOUS` + `InstrumentIdentity`; the fetchers refuse
an unresolvable market rather than emitting a bare US ticker. Every real
collision is a permanent regression fixture
(`src/lib/instrument-collisions.json`, generated from the master). Supersedes any
implicit "symbol is enough" assumption in the retrieval layer (ADR-019).

---

### ADR-021 — One failure contract, declared coverage, and terms-aware identity (2026)
**Decision:** Every tool and source reports failure through one taxonomy
(`src/lib/harness/failure.ts`): `ambiguous`, `market_unknown`, `not_found`,
`currency_mismatch`, `venue_mismatch`, `terms_missing`, `not_covered`,
`no_data`, `source_failure`, `incomplete`, `conflict`, `invalid_request`.
Message text is derived from the class, never hand-written per tool. Coverage is
**declared data** (`src/lib/harness/coverage.ts`), queryable via a `coverage`
capability — an unregistered market/asset class returns `not_covered` instead of
routing to a guessed backend. Derivatives and fixed income require contract
terms (`expiry`/`strike`/`right`, `maturity`/`coupon`/`seniority`) before a
value may be returned. Every numeric payload carries `currency` and `units`.
`get_news` falls through from the vault to the shared web transport and never
phrases a source failure as "no news". Source health is derived from recorded
runs (`healthy`/`degraded`/`failing`/`unknown`), so confidence is earned.
**Why:** The same underlying miss behaved differently across tools
(`get_market_snapshot` refused; `market_get_quote` returned a US fund;
`get_news` reported "no news" on an infrastructure miss). A false "no news" in a
financial tool reads as "nothing happened" — materially misleading. Uniformity
is the only way one tool's safety guarantee holds for all of them.
**Impact:** Extends ADR-020 (identity). Tools route through the shared classes;
a new asset class/venue is a data change in `coverage.ts`. `isCovered()` gates a
request before any source is attempted.

---

### ADR-022 — Deterministic retrieval, strict macro identity, and top-level degradation (2026)
**Decision:** Four rules complete the identity contract. (1) **D1 — parse once,
persist, replay.** A successful retrieval is written to `RetrievalRecord`
(`agent-memory.db`) keyed by request; an identical, non-realtime request replays
the stored result, so the same question yields identical figures and citations
instead of re-scraping (which drifts). (2) **A8 — macro series are identities.**
`python/harness/macro_identity.py` + `src/lib/harness/macro-identity.ts` resolve a
series to geography + institution + measure + adjustment + frequency. A generic
measure (`POLICY_RATE`) without a geography is AMBIGUOUS and never defaults to
US; non-US series route to non-US sources. (3) **D2 — truncation is withheld.**
A partial numeric parse (`1,23` from `1,234.56`) is detected and the result is
UNAVAILABLE + `incomplete`, never a figure. (4) **D3 — degradation is
top-level.** `degraded`/`degradation`/`incomplete`/`conflicts`/
`provenanceVerified` are fields on the result itself, not nested metadata, so a
value whose identity was not verified is structurally flagged.
**Why:** The same infrastructure produced drifting fundamentals (read-time
scrapes), conflicting policy-rate values (measure collision), a truncated figure,
and a wrong instrument — each invisible to the consumer because degradation was
either absent or buried.
**Impact:** Extends ADR-020/021. `RetrievalRecord` is idempotent (upsert on key).
Realtime data types are excluded from durable replay by design.

---

### ADR-023 — One shared resolution layer for every tool; no country/venue/asset-class default (2026)
**Decision:** Instrument resolution is unified in a single bridge resolver
(`resolveVaultInstrument` / `resolveAnyInstrument`), and **every** resolving
capability (`market_snapshot`, `fundamentals`, `live_quote`, `price_history`,
`financial_statements`) routes through it. A tool cannot bypass the gate; a test
enumerates the tool surface and fails if a resolving tool touches a non-gated
capability. There is **no** US (or any) default: an unqualified multi-listed
ticker is `AMBIGUOUS`; an unknown venue is `NOT_COVERED` (not `AMBIGUOUS`); FX
and crypto are first-class asset classes that never inherit an equity country
universe; a wrong-currency/venue answer is discarded. Instrument identity carries
the exchange and MIC where known.
**Why:** The previous round gated only the quote fallback path, so
`market_get_quote` was safe while `fundamentals_get_company_profile` silently
returned the US ADR of a multi-listed issuer and `market_snapshot` defaulted
unqualified lookups to the US — the original defect, reachable by omitting a
parameter.
**Impact:** Extends ADR-020/021/022. `market_unknown` now maps to
`not_covered`. New `financial_statements` capability serves the persisted
`FundamentalsCache` (parse-once, deterministic). Source health records from the
live path, keyed by source × market × asset class. Macro generic measures are
`AMBIGUOUS` even with a geography, and macro rows are newest-first with units.

---

### ADR-024 — Generic macro aliases never narrow silently; recognition ≠ coverage (2026)
**Decision:** A generic macro alias (`CPI`, `INFLATION`, `POLICY_RATE`, …) resolves
only when it names exactly ONE measure; a multi-meaning alias is AMBIGUOUS with
named candidates, and a recognised concept with no registered series (`PMI`) is
NOT_COVERED. An index series carries its `unitBase` (e.g. `1982-84=100`) so the
number is meaningful. Macro rows are newest-first with an explicit `asOf`. A
venue the system recognises but does not cover (`CME` → `DERIV`) is NOT_COVERED,
not "unknown venue" — recognition and coverage are distinct. FX/crypto payloads
state `served: live` and echo the requested symbol, since the vault holds
equities only. Warnings are de-duplicated, and a slow source cadence marks data
"delayed" (a transformation, not a quality warning).
**Why:** CPI silently resolved to the index level, `ES/CME` read as "unknown
venue", and the FX payload said "not in the universe" beside a valid quote — each
a confidently-wrong or self-contradictory answer.
**Impact:** Extends ADR-020…023. `macro_resolve` in TS is the single alias table
(the Python tool asks it before falling back locally). `get_source_health`
enumerates the declared source registry so a source with no runs is `unknown`,
not absent.

### ADR-027 — Evidence-grounded answering: a deterministic research flow over the existing retrieval layer (2026)
**Decision:** Add one shared Python package `python/harness/research/` that turns
an objective into a typed research mandate, retrieves each fact leg through the
*existing* Financial Retrieval Layer, produces deterministic per-leg coverage,
validates structured claims against actual evidence, computes named metrics in
pure Python, and persists a bounded research receipt. It adds no agent loop, no
model adapter, no second retrieval system and no second database. The model
interprets and explains; the harness owns coverage, calculation truth, structural
validation and the accept/partial/reject decision. Point-in-time `asOf` is
explicit and enters cache identity; `NormalizedFinancialObject` gains additive
`basis`/`publishedAt`. Receipts live in `agent-memory.db` (idempotent DDL), never
in `eclipse-memory.db` or JDdS.
**Why:** Phase 2 retrieval produced provenance and conflicts but nothing turned
an objective into required facts or gated the model's citations against evidence.
A shared flow is reusable by every financial agent (and future workflow nodes)
rather than each rebuilding citation logic.
**Impact:** New `/research/*` runtime endpoints and `ResearchReceipt` table; 61
new tests; general/unsupported chat is unchanged (`supported=false`). Full
decision set: ADR-H15…H19 in `docs/harness/decisions.md`; progress in
`docs/harness/phase-4-progress.md`.

---

### ADR-028 — Phase 4 hardening: deterministic identifiers, gated live chat, honest semantic evaluation (2026)
**Decision:** Evidence/calculation identifiers use SHA-256 content digests (not
the salted built-in `hash()`); a supported `financial_comparison` is routed into
the evidence gate before the agent graph and never silently downgraded; period
matching is canonical (no substring-of-digits); a versioned human-labeled
semantic-support evaluation reports false accepts/rejects per slice, and
production claim status stays `needs_review` where support is unproven.
Supersession links come only from explicit source revision metadata.
**Why:** The first Phase 4 cut had non-reproducible receipt hashes, a coverage
gate that let missing required metadata pass, no live wiring, and no way to
measure semantic support without over-claiming.
**Impact:** `python/harness/research/{periods,ids,synthesis,supersession,run}.py`
+ `eval/`; additive `research` on `HarnessRun`/`RunResult`; TS `ResearchRunInfo`
contracts + `/api/harness/runs/[id]/receipt` + `ResearchEvidencePanel`. Full
decisions: ADR-H20…H22 in `docs/harness/decisions.md`.

---

### ADR-029 — Bounded web escalation keeps answers evidence-grounded when structured data cannot (2026)
**Decision:** When structured retrieval is empty, stale, missing a requested
fiscal period, or lacks required metadata, the research flow escalates a leg
through a fixed hierarchy — structured → primary-source web (SEC/IR/regulators)
→ bounded reputable secondary web — using the existing web bridge and a single
`ResearchBudget`. Every numeric web fact must pass a deterministic validator
(fetched-page id, verbatim `sourceSpan`, value-in-span, no contradicting period,
metric/period/currency/basis match) before becoming evidence. Coverage gains
distinct statuses (`no_matching_period`, `stale`, `qualified`), and a missing
consolidation basis qualifies the value with disclosure rather than failing it.
**Why:** Stopping at an unrelated structured row produced unhelpful answers; but
"answer anyhow" must never mean invent. A snippet is not a number, a page
instruction is not a fact, and the model cannot decide a source is trustworthy.
**Impact:** `python/harness/research/{budget,web_facts,escalation}.py`;
`retrieval/web.py` serves `financial_statements`; receipt carries escalation +
budget; evidence panel shows tier/dates/period/span. Full decisions: ADR-H23/H24
in `docs/harness/decisions.md`.

---

## Decisions implied by the code (not yet formal ADRs)

These are real, load-bearing, and currently only documented in prose. Promote one
to an ADR if it gets challenged.

- **SQLite-only JDDS.** PostgreSQL was removed along with the old daemon.
  Reintroducing `DATABASE_URL`/pg tooling would be a new ADR.
- **Keep-alive tabs, single page.** Tabs mount on first visit and stay mounted;
  no URL routing for main screens.
- **In-process schedulers.** Cron runs inside the Next.js server (not Vercel-
  friendly by design; a `POST /api/cron/run` endpoint exists for hosted setups).
- **Synchronous-write discipline.** Bulk writers yield and sleep by design
  because better-sqlite3 blocks the event loop.
- **Separate market-workspace engine.** The Chart Workspace tab (tab id
  `market-workspace`) has its own panel engine rather than reusing the widget
  workspace.

---

### ADR-032 — Reliability & global-research hardening: capability-specific health, distinct route categories, a deterministic comparability gate (2026)
**Decision:** (1) The truthful-capability tools (`get_capability_matrix`,
`get_research_health`) are read-only and in the Eclipse agent allowlist. (2) A
tool's own `timeout_ms` is authoritative; the agent `toolTimeoutMs` is only a
ceiling, and optional news enrichment has its own bounded budget. (3) Source
health is keyed `(source × market × assetClass × capability × probeKind)`: a
healthy quote never makes statements/filings healthy, zero attempts stays
`unknown`, and fixture probes are labelled and excluded from live health. (4) The
route planner reports distinct categories (ineligible / not_implemented /
unconfigured / provider_failure / no_instrument / no_data / no_matching_period /
stale_data / invalid_document) so a skip is never an outage. (5) Documents
distinguish `too_large` / `empty_response` / `javascript_only` /
`unsupported_document` / `parse_failure`, preserve title/document-id/publication
metadata, stream to a bounded size, and refuse a value-less XBRL taxonomy. (6) A
comparison is permitted only when the legs are the same fact for the same entity
— `research/comparability.py` blocks a demerger/ticker reuse, unequal durations
(9M vs 12M), consolidation basis, metric definition, currency, unit, scale or an
unstated restatement, with the exact reason; each verified leg is still reported
and no misleading percentage is computed. The model is never the validator.
**Why:** The international runs recorded `TOOL_FORBIDDEN` for
`get_capability_matrix`, a 20s news timeout despite a declared 30s budget,
`unknown — 0 ok / 0 fail` health rows beside a `configured` coverage claim, SEC
attempted for non-US issuers, and correctness risks (Tata demerger, 9M vs 12M,
standalone vs consolidated, gross vs operations, issuer currency vs thousands,
EPS after a subdivision) that only the model understood.
**Impact:** `python/harness/{agents,finance_tools,retrieval_tools,tools,graph}.py`,
`python/harness/retrieval/{routing,layer}.py`,
`python/harness/research/{comparability,engine,run,receipt,citations}.py`,
`src/lib/harness/{capability,coverage,data-bridge,types}.ts`,
`src/lib/{web-research,retrieval-diagnostics}.ts`, `scripts/test-python.js`.
Progress: `docs/harness/phase-4-progress.md` (Phase 8).

---

### ADR-041 — Icon set is Phosphor behind a single aliased surface (2026)
**Decision:** The UI renders **Phosphor** (`@phosphor-icons/react` ^2.1.10) instead of lucide-react. Every icon is imported from ONE module, `src/lib/icons/index.ts`, which re-exports each Phosphor glyph under its original Lucide name (e.g. lucide `Search` → Phosphor `MagnifyingGlass`) plus `LucideIcon` (Phosphor `Icon`), so call sites and the `LucideIcon` map types stay unchanged and the set can be swapped in one file. Components never import an icon library directly. Selected/active states use Phosphor's `weight="fill"` prop — Phosphor outline glyphs are filled paths, so `fill="none"` would erase them; accent-colored fills use a className text color instead.
**Reason:** Lucide is ubiquitous and reads generic; Phosphor's weights (including duotone) and shape language are distinctive and suit the dark glass UI. Aliasing avoids a 165-file / 216-icon rename while confining the dependency to one module.
**Impact:** `src/lib/icons/index.ts` (new). Every icon-importing module imports from `@/lib/icons`. Three files that render icons gained a `'use client'` boundary (`components/chat/{chat-history,markdown}.tsx`, `components/screens/portfolio/fund-store.ts`) because Phosphor icons read `useContext`. `lucide-react` removed; `@phosphor-icons/react` added. `components.json` (`shadcn` CLI `iconLibrary`) still says `lucide` for generated components — reconcile when the CLI is next run. See `docs/NAVIGATION.md` (By task).

---

### ADR-043 — Structured responses ride the existing Markdown stream as a fenced block; the renderer is a registered component registry (2026)
**Decision:** Add the **Interactive Response Engine**: an assistant turn may include ONE fenced ```eclipse-response block whose JSON body a versioned zod contract (`src/lib/response/contract.ts`) validates, and which renders through a registry of components (`src/components/response/response-view.tsx`) — metric grids, sortable/filterable tables, ECharts charts, SVG diagrams, timelines, citations — inline in the existing chat. It reuses the **existing** Markdown renderer (`components/chat/markdown.tsx` intercepts the fence language), the **existing** ECharts dependency (lazily imported), and the **existing** message persistence (the fence is stored in `Message.content`; reopening re-parses it). No second chat engine, stream, transport, or artifact store is introduced.
**Reason:** The documented gap (`docs/chat-ui-audit.md` §16, Risk R7) was that the runtime's terminal output is plain Markdown with no structured wire contract, so structured blocks/charts were deliberately not built. A fenced block is the smallest real producer→renderer contract that needs no Python protocol rewrite, works in both chat surfaces unchanged, persists for free, and degrades safely (unknown/malformed blocks become diagnostics, never code execution, never a lost answer).
**Impact:** New `src/lib/response/**` (contract/parse/chart-option/diagram-layout + tests) and `src/components/response/**`; `components/chat/markdown.tsx` gains a `streaming` prop and the fence branch; `chat-history.tsx` passes it. `zod` promoted to a direct dependency (was transitive). `prompts.py` gains a "Structured answers" section so agents can author the block when it helps. No Python protocol, database schema, or persisted-conversation migration. Security posture: structured JSON only — never model-authored JS/HTML; per-block resource limits; per-block error boundaries.

**Amendment (2026-10-10) — full build-out.** The previously deferred capabilities are now shipped, each by reusing existing infrastructure: a deterministic **response planner** (`src/lib/response/planner.ts`; GFM tables → interactive tables, link-only source lists → citations, for every settled answer, no model call); **backend-driven controls** (`controls-block.tsx`) that compose a validated prompt and re-enter the existing agent loop via `onFollowup`; **export** JSON/CSV/PNG/PDF (`export.ts`; PNG via an ECharts instance registry, PDF via lazy `jspdf`+`jspdf-autotable`); **Artifact Center save** via the existing `registerArtifact`; a **`financial_chart`** block wrapping the existing `ChartWidget`; and a **`mermaid`** block (lazy, `securityLevel: 'strict'`; `mermaid` 12.1.0). Still out of scope, documented not faked: React-Flow *editable* graphs (diagrams are read-only by design), server-side pagination for tables over the 2000-row contract cap, and PDF embedding of unmounted/financial charts (those are listed in the PDF's export notes). See `docs/interactive-response-engine.md`.

**Amendment (2026-10-11) — rich block family + link hardening.** The catalogue grows to the full interactive vocabulary: **`stepper`** (numbered process with per-step status), **`infographic`** (icon cards — icons resolved through a semantic allowlist in `src/lib/response/icons.ts`; the model names a key, never a component or import path), **`report`** (a multi-section container whose section `blocks` are validated recursively like `tabs`), **`node_graph`** (a *selectable* graph that reuses the same deterministic `diagram-layout` engine — no second graph library; nodes are focusable/selectable and reveal their `detail`), **`action_group`** (PROPOSED next steps whose click sends a follow-up prompt into the existing agent loop — never a privileged backend call), and **`artifact`** (a reference to the existing Artifact Center, linked via its own download route). Spec-name synonyms are normalized to canonical blocks (`text`→`markdown`, `table`→`data_table`, `source_list`→`citations`, `interactive_form`→`controls`, `execution_timeline`→`timeline`). Every model-supplied citation/artifact link is now **scheme-restricted to http(s)** — bare `z.string().url()` accepts `javascript:`/`data:`, which becomes an XSS vector once rendered as an anchor. The agent guidance in `prompts.py` was rewritten to be more directive and to list the new blocks, **within the unchanged 26410-char ceiling**. All new blocks render through the same registry + `BlockBoundary`, and PDF export represents each. Tests: `src/lib/response/contract-blocks.test.ts`.

**Amendment (2026-10-14) — branching `flow` block + native-flow routing over Mermaid.** A new dependency-free **`flow`** block renders a branching process as frosted HTML/CSS cards: ordered `steps` joined by CSS connectors, each step optionally branching into parallel `paths`. It is distinct from `workflow` (strictly linear icon stages) and from `diagram`/`node_graph` (absolute-positioned SVG graphs) — the native, responsive answer for a flowchart. `mermaid` is now reserved for sequence/ER/class/gantt, and the prompt directs flow/flowchart answers to `diagram`/`flow`/`workflow`, so the heavy `mermaid` bundle stays unloaded for ordinary process answers. New aliases route producer vocabulary (`process`→`workflow`, `process_flow`/`pipeline`→`flow`, `flow_graph`→`diagram`). Rendering reuses the existing registry + `BlockBoundary`; the block is data-only (no model-authored HTML). Tests: `contract-blocks.test.ts`, `render.test.tsx`; `prompts.py` stays within its char ceiling. See `docs/interactive-response-engine.md`.

---

### ADR-044 — Private per-conversation long-term memory: a first-class `conversation` scope on the ONE Eclipse-Memory pipeline (2026)
**Decision:** A bot chat and each group-room member turn keep their own **private durable memory**, isolated from every other conversation/bot and from ordinary chat. This is implemented as an additive **`conversation` scope** on the existing `MemoryRecord.scope` column, keyed by `scopeId = conversation id` (the run's `sessionId`: `bot-<id>` or `group-<gid>-<botid>`). A `conversation` actor may read ONLY its own bucket, the signed-in user's own `user` rows (when present) and truly-global `general` knowledge — never another conversation. The scope is normalized at the ONE write gate (`EclipseMemoryService.commit_decision` via `decision.resolve_owner_scope`): in a conversation-scoped run with no signed-in user, a personal (`user`) fact is owned by that conversation. Opt-in is explicit: only the bot/group call sites set `memoryScope: 'conversation'`, which the front door maps to `RunRequest.conversationId`; ordinary chat is unchanged. Scheduled bot runs bind the SAME `bot-<id>` conversation so background learning is recalled in chat. `bot_delete` archives the bot's conversation memory (never hard-deletes). No new database, table, or column.
**Reason:** The bots UI documented "no separate memory" — every durable fact landed in shared `general`/unattributable `user` rows, so a bot could neither accumulate its own long-term context nor be isolated from other bots. A separate memory store per bot would violate the one-store/one-pipeline invariants (ADR-026/034); a new scope value reuses the authoritative scope-before-rank filter, the single decision gate and the single persistence path.
**Impact:** `eclipse_memory/{decision,retrieval,service}.py` (`resolve_owner_scope`, conversation candidate gathering + `_scope_authorized`, `forget_conversation`); `memory_tools.py` (default scope + `conversation` enum); `graph.py`/`graph_context.py`/`schemas.py`/`tools.py` (thread `conversationId`/`conversation_id`); `automation/dispatcher.py` (bind `bot-<id>`) and `automation/tools.py` (purge on delete); `routers/memory.py` (scopeId filter + `POST /eclipse-memory/conversations/{id}/forget`); TS `agent/types.ts`, `agent/registry.ts`, `harness/run-service.ts`, `harness/python-client.ts`, `harness/eclipse-memory-browser.ts`, both chat routes, `bot-chat.tsx`, `group-chat-room.tsx`, `bot-detail.tsx`, new `bot-memory-section.tsx`, i18n `en.ts`. Conversation ids remain local labels, not security identities. Tests: `python/tests/test_memory_conversation.py`. See `docs/harness/memory-skills-evolution-plan.md`, `docs/harness/automation-engine.md`.

---

### ADR-045 - Page targeting: a resolvable current-page default, distinguishable summaries, plain-string data sources, one owner policy (2026)
**Decision:** (1) `UiService.get_current_page` resolves the page by explicit `blueprintId`, else `path`, else `title`, else the owner's **most recently updated** page; it always returns `resolution` and, on a choice among candidates, the other `candidates` - it never silently returns row 1. Paths are normalised and `None` never matches; an unmatched lookup is `UI_BLUEPRINT_PATH_UNASSIGNED` when pages exist without a path, else `UI_BLUEPRINT_NOT_FOUND`. A new `GET /ui/current-page` exposes it (the `/ui/blueprints/{id}/current` route is unchanged). (2) `BlueprintSummary` gains `path` and `componentIds` so pages that share a title are distinguishable, and `q` searches path too. (3) `get_blueprint` fetches unscoped and applies the owner rule in the service, so `get_current_page`/`get_layout`/`preview` share ONE policy; a mismatch is the distinct `UI_BLUEPRINT_OWNER_MISMATCH` (HTTP 403), never `unknown blueprint`; read tools pass no owner scope. (4) The UI runtime advertises its valid structured data sources via `get_capabilities()["dataSourceRegistry"]`; the one family is `portfolio:<portfolio_id>:<view>` for the Ledger kinds.
**Reason:** Fifteen blueprint pages can share the title "Main", and there was no active-page notion, no path in the list summary, and path matching could never hit an unset path - so an agent could not unambiguously name a page, and the HTTP route and the agent tool disagreed on owner scope. A `data-table`/`metric-card` had a free-text source with no registry, so no one could know which strings resolve a portfolio. These are contract/data-shape fixes, not new subsystems.
**Impact:** `python/harness/ui/{service,store,model,catalog,tools}.py`, `python/harness/routers/ui.py`, `src/lib/harness/ui-client.ts`; tests in `python/tests/test_ui_{service,tools,api}.py`; docs `docs/ui-engineering.md`, `docs/portfolio-accounting.md`. No new store, table, migration, or agent loop. A page-level icon remains a scoped, unbuilt gap (needs a new model field + renderer; not the chat response-block icon enum).

**Amendment (2026-10-15) - the generic render path + portfolio surfaced end to end.** The page-targeting/data-source work above was contract-only: an agent could name a page and declare a `portfolio:<id>:<view>` source, but nothing rendered it (Pages/Builder render only host widget ids, and `source` config was inert). Two host primitives now close the loop: `data-table` and `metric-card` (`src/lib/workspace/generic-widgets.tsx`, registered in `src/lib/dashboard/registry.tsx` with ids matching the runtime catalog, so the workspace kernel does not drop them). `src/lib/workspace/data-source.ts` is the ONE allow-listed resolver (never an arbitrary URL): it parses the source, fetches through the existing portfolio front door (`src/lib/portfolio/engine-read.ts` -> `/api/portfolio/{id}/query|history|tax-lots`), caches it on a dynamic DataHub topic, and returns rows/columns or a value - or an explicit UNAVAILABLE with the reason. The six bespoke `portfolio-*` catalog kinds introduced earlier were removed: every advertised component is now renderable. Pages cache their arrangement by blueprint revision (`pageStorageKey(id, revision)`) so an agent edit seeds a fresh workspace instead of being shadowed, and Refresh reloads the open page. `ui_verify_page` / `UiService.verify_page` reads a page back and reports per-widget renderability. Remaining gaps (charts, other source families, live push) stay scoped: `docs/ui-engineering.md`.

**Amendment 2 (2026-10-15) - production surface: full renderable vocabulary, more source families, parity, page icons.** The generic render path was broadened so "compose anything" is real, not aspirational. The catalog seed (`builtin_specs`) is now EXACTLY `RENDERABLE_COMPONENTS`, the ids the host registry defines (metric-card, data-table, list, line/area/bar/pie-chart, markdown, status-indicator, empty-state, error-state); the nine never-renderable foundational kinds were removed, and parity is enforced on both sides (python/tests/test_ui_service.py + src/lib/workspace/generic-widgets.test.ts). The resolver gained allow-listed families: market:quote:<SYMBOLS>, market:indices:<MARKET>, market:price:<SYMBOL> (series), news:latest, agent:activity - each backed by an existing read route, cached on DataHub, still never fetching an arbitrary URL. Page-level icons (the previously scoped gap) are implemented: `UiBlueprint.icon`/`BlueprintSummary.icon` with an idempotent add-column migration, agent/HTTP/TS support, and Pages UI rendering. Pages refreshes the open page when its durable revision changes (focus + 20s poll), so an agent edit appears without disrupting a user's local arrangement. Docs: docs/ui-engineering.md.

**Amendment 3 (2026-10-15) - the remaining gaps closed: more source families, push updates, engineer loop proven.**
The resolver gained four more allow-listed families, each backed by an existing read route and tested: tasks:list / tasks:plans, artifacts:list, research:list, and jdds:search:<QUERY> (JDDS instrument search). Live page updates moved from a blind poll to a Server-Sent-Events stream (GET /api/ui/stream): the server watches the runtime's most-recently-updated blueprint (id:revision:updatedAt) and pushes a changed event; Pages reloads the open blueprint only when its durable revision moves (focus + a slow 60s poll remain as fallbacks). The Engineer -> Compose closure is now proven end to end in test_ui_api.py: register an engineered component, discover it via GET /ui/components, add it to a page, and GET /ui/blueprints/{id}/verify reports it renderable. Docs: docs/ui-engineering.md.

**Amendment 4 (2026-10-15) - production hardening: verify every family, no silent widget drops.** erify_page now validates a declared source against ALL families via catalog.validate_source (portfolio, market, news, agent, tasks, artifacts, research, jdds), not only portfolio. And the Pages surface no longer silently drops a blueprint widget whose id the host registry does not render yet: it passes the workspace a knownWidgetIds set = host registry + every id present in the blueprint, and 
enderDashboardWidget draws an explicit "Needs a renderer" card for it (the Engineer path can add the real renderer). Tests: python/tests/test_ui_service.py, src/app/api/ui/stream/route.test.ts. Docs: docs/ui-engineering.md.

---

### ADR-046 - The Eclipse theme is APP-WIDE: a server source-of-truth plus one canonical origin (2026)
**Decision:** The user's theme stops being a per-browser property. **(1) Server source of truth:** the JDDS `SystemConfig` table (key `eclipse_theme`) owns the single app-wide theme, exposed by `/api/theme` (GET/PUT/DELETE, operator-gated via the existing `guardMutation`). The client store (`src/lib/theme/store.ts`) demotes `localStorage` (`be_theme_v1`) to a per-origin first-paint cache: on boot it hydrates the cache then `hydrateFromServer()` adopts the saved app-wide theme; every edit pushes to the server; Reset issues DELETE. A *successful* null read means "shipped default": if the app-wide theme was never initialized the client MIGRATES its pre-existing per-origin theme up instead of wiping it; after an explicit reset it clears the local override (an unreachable server leaves the cache untouched). **(2) One canonical origin:** when `BE_CANONICAL_HOST` is set, `src/middleware.ts` redirects any other host to it (307, path + query preserved) before the auth gate; `scripts/local-host.js` sets it to the local hostname by default, while `npm run dev:next` leaves it unset so zero-config localhost is unchanged.
**Reason:** `localStorage` is scoped to the browser ORIGIN, so `http://localhost:3000`, `http://127.0.0.1:3000` and `https://blackeclipse` each held their own theme - three visibly different instances of one app. The repo had already solved this exact problem for chat transcripts (server copy + `localStorage` cache); the theme was the last major surface left per-origin. A DB property also makes the theme shared across devices, which is what "app-wide" means.
**Impact:** New `src/lib/theme/server.ts` + `src/app/api/theme/route.ts`; `src/lib/theme/store.ts` (`persistLocal`/`pushThemeToServer`/`clearServerTheme`, `hydrateFromServer`, server-aware `reset` + `useHydrateTheme`); `src/middleware.ts` (canonical redirect) + `scripts/local-host.js` (sets `BE_CANONICAL_HOST`) + `.env.example`. `localStorage` keys are unchanged; user-saved presets (`be_theme_presets_v1`) stay per-origin (a personal library, not the active look). Tests `src/app/api/theme/route.test.ts`, `src/lib/theme/store.test.ts`, `src/middleware.test.ts`. Docs `docs/ARCHITECTURE.md`, `docs/local-hostname.md`, `docs/NAVIGATION.md`. No schema change, no new table, no new agent loop.

### ADR-047 - The Anatomy isometric engine is a declarative response block over a vendored kit; the model authors a SCENE, never code (2026)
**Decision:** A new `anatomy` block type renders an interactive isometric mechanism figure inline in chat. It rides the ONE existing structured-response pipeline (ADR-043): a zod schema in `src/lib/response/blocks/anatomy.ts`, one entry in the renderer registry (`src/components/response/response-view.tsx`), the `finalize`/repair/degrade chokepoint, the Markdown projection, and the `response_block_schema`/`response_validate` read-back (so the model can query the exact field names before emitting). The model authors a **bounded, declarative scene** — parts (a `<kind, x, y, z, w, d, radius, height, corner, tone, lit, label>` slab/cylinder), wires (`from`/`to`/`via`/`tone`), a legend, and optional deterministic **stages** (`{ label, note, readout, lit[] }`) — and the geometry is compiled purely by `src/lib/anatomy/scene.ts` with the MIT-licensed Anatomy-derived kit vendored into `src/lib/anatomy/` (`NOTICE` + `LICENSE` record the MIT origin and the verified upstream commit `e9488296a44211c42701ff71705b7901470ec78f`; blob hashes prove `iso-kit.ts`/`live.tsx` byte-identical). The model never supplies SVG, HTML or code. The renderer is `'use client'` and renders the figure inside a frosted-glass card with a full-page overlay; the **stage is the sole source of live readout text**, animation is discrete (no rAF loop), autoplay is off under `prefers-reduced-motion`, and the interval is cleared on unmount — so the figure cannot invent a value and cannot leak a timer.
**Reason:** The Interactive Response Engine already covers flows, charts, diagrams, timelines, simulators and learning maps — but not a *physical-mechanism* illustration, which is what "explain how a CPU/cache/refinery works" needs. Anatomy (wheresryan22/anatomy, MIT) is exactly that toolkit; its bespoke figures are standalone HTML built by node scripts, which do not fit a chat artifact. Reusing only its geometry primitives and React drawing components, then driving them from a declared scene, keeps the Eclipse posture intact: a registered component registry, no model-authored code path (SEC-001), deterministic model-as-source-of-truth, and a text fallback (the Markdown projection) for surfaces that cannot render it.
**Impact:** New `src/lib/anatomy/` (vendored `iso-kit.ts`, `draw.tsx`, `live.tsx` + `NOTICE`; Eclipse-authored `scene.ts`), `src/lib/response/blocks/anatomy.ts` (schema extracted from `contract.ts`, whose size ratchet it helps satisfy), `src/components/response/anatomy-block.tsx`; `contract.ts` (import + union entry), `normalize.ts` (`anatomy` type aliases + status-tone normalization), `projection.ts` + `export.ts` (projection/PDF cases), `response-view.tsx` (registry). Tests `src/lib/anatomy/scene.test.ts`, `src/components/response/anatomy-render.test.tsx`, the matrix (`contract-matrix.test.tsx`). Docs `docs/interactive-response-engine.md`, `docs/NAVIGATION.md`. **Not wired:** WebGL/3D and the bespoke lathe/tube parts stay out of runtime (kept in `docs/figures/eclipse-refinery/` as a reference); only slab/cylinder parts render. No new dependency, no new agent loop, no wire-contract change.

### ADR-048 - True 3D mechanism models are a separate `model3d` block compiled to world meshes and rendered in an orbitable WebGL viewport (2026)
**Decision:** `/anatomy` now authors a `model3d` block, not the isometric `anatomy` scene. It keeps ADR-047's trust posture — the model supplies a bounded declarative SCENE (JSON), never meshes, shaders, SVG or code — but the scene is a real 3D graph: `parts[]` carry a `position`/`rotation`/`scale` transform, an optional `parent` (assemblies), material/tone/lit/label, and geometry as either a primitive (`box`, `cylinder`, `cone`, `sphere`, `torus`, `lathe`, `extrude`, `tube`, `gear`) or a **named mechanism recipe** with numeric `params` (`motor`, `gearbox`, `pump`, `valve`, `gauge`, `tank`, `bearing`, `gear`, `pulley`, `belt-drive`, `frame`, `bracket`, `fan`, `heat-exchanger`, `pcb`, `lever`, `spring`). The pure compiler (`src/lib/model3d/compile.ts` + `mesh.ts` + `recipes.ts`) expands recipes, composes parent transforms with a cycle guard, bakes every triangle to world space, grounds the scene, fits the camera and reports anything it cannot place as a diagnostic — it is total and server-safe. The renderer is split: a DOM half (`model3d-block.tsx`) owns the header, numbered key, legend, readout, stage controls and `.glb` download; a `next/dynamic(ssr:false)` WebGL half (`model3d-canvas.tsx`) uses the already-vendored `ogl` dependency for orbit/zoom/pan, lighting, a fading grid and projected hotspots. `glb.ts` is a dependency-free glTF 2.0 binary writer. The legacy `anatomy` block stays registered and renders unchanged for old payloads.
**Reason:** The isometric SVG compiler can only draw what it has primitives for and paints in producer order with no depth buffer; it cannot rotate, compose assemblies or show a machine from another angle, so `/anatomy` collapsed to "a base slab plus cylinders". The two real levers are (1) genuine 3D with depth/lighting and (2) a reusable parametric mechanism kit, so the model composes recognisable assemblies instead of guessing primitives. `ogl` is already a dependency (~15 KB, used by the Aurora background), so no new package and no bundle cost on the initial chat load (the viewport is lazy). Keeping the legacy block avoids a breaking wire-contract change; keeping compilation pure preserves determinism, tests and the no-model-code security posture (SEC-001).
**Impact:** New `src/lib/model3d/` (`names.ts`, `math.ts`, `mesh.ts`, `recipes.ts`, `compile.ts`, `glb.ts`), `src/lib/response/blocks/model3d.ts`, `src/components/response/model3d-block.tsx` + `model3d-canvas.tsx`; `contract.ts`, `normalize.ts` (type aliases), `projection.ts` + `export.ts` (text/PDF cases), `response-view.tsx` (registry), `command-agent.ts` (/anatomy directive), the `system.anatomy-figure` skill. Tests `src/lib/model3d/{mesh,compile}.test.ts`, `src/components/response/model3d-render.test.tsx`, `contract-matrix.test.tsx`. Docs `docs/interactive-response-engine.md`, `docs/NAVIGATION.md`, `docs/harness/slash-commands.md`, `.opencode/skills/black-eclipse-anatomy/SKILL.md`. No new dependency, no new agent loop, no schema change to existing blocks.

### ADR-049 - Eclipse Canvas is an editable document/code/visual workspace over the ONE Artifact Center; AI edits are typed operations re-applied under a revision guard (2026)
**Decision:** Eclipse Canvas is a persistent, editable workspace for documents, code and visual reports, built **on top of the existing Artifact Center with no second store**. A canvas document IS an ordinary `Artifact` whose bytes are canonical UTF-8 text and whose revisions are the artifact's immutable versions; the canvas kind (`document`/`code`/`visual`) and optional `language` live in the artifact's `metadata` under the key `canvas` (`python/harness/canvas/`, `CANVAS_METADATA_KEY`). `CanvasService` is the ONE canvas writer over `ArtifactService` (create/read/list/save/restore); each save is guarded by the `baseVersion` the editor loaded and serialized by a lock, so a stale save returns `409 CANVAS_CONFLICT` carrying `currentVersion` instead of overwriting. AI assistance is one orchestrator (`CanvasEditOrchestrator`): it builds a strict-JSON prompt, calls the model through the ONE model runtime (`vision.providers.call_model`, task `canvas_edit`), validates the reply with `model_runtime/structured.py`, and **re-validates every operation against the loaded revision**; modes are `ask`/`edit`/`review`/`build`, Ask mode never proposes edits, and a missing model configuration is the honest `CANVAS_MODEL_UNAVAILABLE`. Edits are a **closed vocabulary of typed operations** (`ops.py`: `append`, `replace_text_range`, `replace_section`, `insert_after_section`, `replace_document`, `apply_code_patch`) applied deterministically to current bytes — never a free-form patch, eval, template, or model-authored code. An AI-assisted save sends `operations`, and the server re-applies them to the current revision, so **client content is not trusted**; unknown, ambiguous or stale operations are rejected. Routes are `python/harness/routers/canvas.py` (`/canvas/artifacts*`, operator-gated, owner from `x-harness-user`), proxied by `src/app/api/canvas/[[...path]]/route.ts`, which also resolves the operator's model from the settings vault (`resolveRunModelSettings`) and injects `modelSettings` for `.../edits` (the runtime cannot read the vault). The UI (`src/components/screens/canvas/`) is a three-region workspace: a rail (list/search/create/import), a center editor (Tiptap document with Markdown as canonical content, Monaco code, JSON editor + live `ResponseView` preview for Eclipse response-envelope visuals) with debounced autosave, Ctrl/Cmd+S, version history + restore, export and a `409` conflict UI, and an AI panel with a propose → diff → accept flow.
**Reason:** The Artifact Center stores immutable, versioned, content-addressed files but has no editor, so "make this artifact editable" would otherwise require a second document store with its own versions, owner scope and model path — three new authorities over the same bytes. Reusing the catalog keeps one storage root, one version table and one owner scope. A typed-operation contract (rather than accepting model-authored content or patches) preserves the no-model-code security posture (SEC-001) and makes every AI change reviewable and reproducible; a revision guard is required because keep-alive editors and AI proposals can both hold stale bytes, and silently overwriting would be a data-loss path.
**Impact:** New `python/harness/canvas/` (`model.py`, `ops.py`, `service.py`, `edits.py`), route group `python/harness/routers/canvas.py` registered in `main.py`, tests `python/tests/test_canvas.py` + `test_canvas_api.py`; front door `src/lib/harness/canvas-client.ts` + `src/app/api/canvas/[[...path]]/route.ts`; UI `src/components/screens/canvas/` (`canvas-screen.tsx` + rail/center/workspace/ai-panel/editors); new `canvas` AppTab (`src/lib/app-tabs.ts`, sidebar `config.ts` icon `SquarePen` in the agentic group, `nav.canvas`, deep-link `APP_TABS`, mobile bottom nav, keep-alive block in `stock-chat.tsx`); integrations `/canvas [document|code|report|visual]` (`command-registry` + `native.canvas` returning an open link), Artifact Center "Open in Canvas" for artifacts whose metadata carries `canvas`, and response-actions "Canvas"; new editing dependencies (`@tiptap/*`, lowlight, `monaco-editor`, `@monaco-editor/react`); tests `src/app/api/canvas/route.test.ts` + `src/components/screens/canvas/canvas-screen.test.tsx`. Storage stays SQLite (`agent-memory.db` + artifact files under `.black-eclipse/artifacts`), never Postgres. Docs `docs/canvas.md`, `docs/harness/artifact-center.md`, `docs/NAVIGATION.md`, `docs/ARCHITECTURE.md`. No new agent loop, no new store, no new database table.

**Amendment (inline, 2026-10-17):** Canvas is **not a standalone surface**. The `canvas` AppTab, the sidebar entry/`nav.canvas`, the deep-link tab, the mobile bottom-nav item and the `/canvas` command were **removed**; there is no external Canvas page. Canvas renders as an **inline pane inside the ChatBot tab** (`stock-chat.tsx`): when `useCommandStore.canvasInlineOpen`/`pendingCanvasArtifactId` is set, the chat column and a right-hand `CanvasPane` (`CanvasScreen inline`) split the view, with a close button; the pane carries the editor and (collapsed by default) the same AI panel. It opens from a response's **Canvas** action (save → inline) and from the Artifact Center's **Edit in Canvas** (`dispatch({tab:'chat', params:{artifactId}})`), never a separate route. The backend, artifact model, typed-operation contract and revision guard are unchanged.

### ADR-050 - The chat's charts are drawn by the PYTHON engine (a composable SCENE of marks, so ANY chart can be drawn); the rest of the app stays on ECharts (2026)
**Decision:** The **chat's** chart blocks are drawn by the Python chart engine and by NOTHING else. A `chart` block in an answer is turned into a **SPEC** and drawn by the runtime with `matplotlib` (Agg, **transparent** background, the app's own palette), and the picture is recorded in the Artifact Center and fetched back as an artifact. The chat has no ECharts path: `chart-option.ts` (the old ECharts option builder) is deleted, and a chart in an answer is never a live canvas. The SPEC is DATA - a validated, `extra="forbid"` contract (`python/harness/charts/spec.py`: `kind`, title/footnote, `categories`, `series[]` with `null` for a missing reading, `points[]`, `matrix` + label axes, `candles[]`, `labels`/`values`, reference lines, highlight spans, a volume pane, value formats) - never a callback, a URL or a path, so a malformed chart is a refusal that names the missing part rather than a broken picture. **Any chart is expressible**: a chart may also arrive as a **SCENE** - `panels` of `marks` - which is compositional rather than a fixed list of kinds, so a violin, a box plot, a Gantt, a funnel, a ridgeline, an error-bar chart or a dual-axis chart is a composition of the primitives (`line`, `area`, `bar`, `scatter`, `band`, `rule`, `label`, `box`, `violin`, `histogram`, `errorbar`, `heatmap`, `pie`, `donut`, `candlestick`, `waterfall`, `ridge`, `stem`) rather than a new kind that must be invented for it. The model reaches the scene through the block schema (the bridge read-back now describes the mark vocabulary) and through the agent prompt. The engine is reached through the `python_chart` agent tool, the operator-gated route `POST /charts/render` (proxied by `src/app/api/harness/charts/route.ts`), and the browser client `src/lib/harness/charts.ts`. A figure is always `computed` and never evidence - `isEvidence: false` is part of the contract, not a caption (ADR-H123); the renderer draws what the spec says and nothing else; a missing `matplotlib` is a named `CHART_RENDER_UNAVAILABLE` refusal, never an empty picture; and the picture's identity is the digest of its spec. **The rest of the application is NOT part of this**: the journal, portfolio, dashboard, backtest, economics, fundamentals and workspace widgets, the price chart, the Investor Eye map and the relationship graphs stay on ECharts, because they draw from live data at interactive rates (a price chart that redraws on every tick, a map the user hovers) and a server-drawn picture cannot serve that. A lossy *mapping* is never silent: a block type the engine cannot draw exactly (`treemap`/`sunburst`/`funnel`/`gauge`) is drawn as the closest honest shape and the note appears under the picture.
**Reason:** ECharts could only draw the charts it already had: a fixed vocabulary of kinds, with a hover tooltip and a crosshair as the price of the interactivity. A chat answer is the one surface where the chart ITSELF is the payload - the model authored it, it travels in the response contract, and it is exported, saved and re-shared - so it is also the one surface where "the reader asked for a chart and got something else" is most visible. Making the chat's charts composable (a scene of marks) removes the ceiling: the system can now draw what the user asked for instead of the closest thing in a dropdown. The rest of the app keeps ECharts because there the interactivity IS the product, and a round trip per frame would be a downgrade, not an upgrade.
**Impact:** New `python/harness/charts/` (`spec.py`, `theme.py`, `render.py`, `service.py`, `tools.py`, `scene.py`, `scene_render.py`), route group `python/harness/routers/charts.py` registered in `main.py`, `register_chart_tools` wired into `HarnessService` and the chat agent's allowlist; front door `src/lib/harness/charts.ts` + `src/app/api/harness/charts/route.ts`; the chat's chart path `src/lib/response/chart-spec.ts` (block -> spec), `src/components/response/response-chart.tsx`, `src/lib/response/chart-registry.ts`, the export helpers in `src/lib/response/export.ts`, the `chart` block's scene fields in `src/lib/response/contract.ts`, and the schema bridge's deeper read-back (`src/lib/harness/response-bridge.ts`) so the model can see the mark vocabulary. Deleted: the chat's ECharts builder (`src/lib/response/chart-option.ts` + test) and the engine preference store. `matplotlib`/`numpy`/`pandas` are already installed in the runtime and the analysis sandbox - **no new dependency**, no new agent loop, no new store. Tests `python/tests/test_charts.py`, `python/tests/test_chart_scene.py`, `src/lib/harness/charts.test.ts`, `src/app/api/harness/charts/route.test.ts`, `src/lib/response/chart-spec.test.ts`, `src/lib/response/repair.test.ts`. Docs `docs/chart-engine.md`, `docs/interactive-response-engine.md`, `docs/NAVIGATION.md`, `docs/ARCHITECTURE.md`. ECharts stays a dependency of the app - for everything except the chat.

**Amendment (inline, 2026-10-21):** the chat's charts are **live figures, not
pictures**. The engine authors each chart as a **Plotly figure** in Python
(`python/harness/charts/plotly_figure.py`) and the browser renders it as
**vector SVG** with scroll-zoom, pan, a hover readout, a legend and a PNG/zoom
toolbar. The chart is still authored in Python from the same validated spec, so
the data, the palette and the honesty rules are unchanged; only the rendering
moved from "a PNG of a chart" to "a chart". The library is served by the app
from **its own route** (`/api/harness/charts/plotly`), out of the Python package
that ships it - never vendored into git, never fetched from a CDN, so the app
keeps working offline - and the figure has **no background**, so the chart sits
on the app's frosted surface without hiding the frost. The matplotlib picture is
still produced from the same spec and stays the export (PNG/PDF) and the honest
fallback when the library cannot load. The mark vocabulary grew the family
charts (`treemap`, `sunburst`, `funnel`, `sankey`), so a treemap of holdings is
a real treemap rather than a bar standing in for one. `plotly` is a new runtime
dependency, justified by exactly this: interactivity and vector output are
things a server-drawn PNG cannot provide.

**Amendment (inline, 2026-10-22, superseding the ECharts rework):** the chat's chart renderer stays **Plotly**. A chart block is mapped to the shared ChartSpec (src/lib/response/chart-spec.ts), a named dataSource is resolved through the app's own /api/price-history route (src/lib/response/chart-data.ts), and the Python engine returns both the live Plotly figure and the transparent matplotlib PNG. src/components/charts/plotly-chart.tsx paints the PNG immediately, then loads plotly.js only when the chart nears the viewport and on an idle frame, caches the library for the session, and cross-fades to the live chart; response-chart.tsx caches the rendered figure per spec. The chart registry maps the block id to the artifact id for PNG/PDF export. Drawability is validated with the engine's own list (src/lib/response/chart-capabilities.ts), candle shapes ([date,o,h,l,c], object rows) are normalised instead of dropped, and gauge/treemap/funnel/sunburst are drawn natively. The rest of the app keeps ECharts.
### ADR-051 - The scraper lane: a generated program collects what the vault does not have, through the host's fetch and a per-domain consent
**Decision:** Eclipse can now **build a scraper on demand**. When the answer is not in JDdS, the agent writes a Python program and runs it in the SAME analysis sandbox; the program fetches pages ONLY through a new host-mediated binding (`eclipse_tools.web_page`), and leaves its records in `result = {"rows": [...]}`. The lane is `python/harness/scraper/` (`tools.py` = the `scraper_run` tool, `program.py` = the answer contract + the wrapper that makes "the program never answered" a failure rather than an empty dataset, `authorizers.py` = the per-domain consent, `store.py` = where the rows and the program are kept), registered in `service.py` and advertised on the research agent (`WEB_RESEARCH_TOOLS`). The program cannot open a socket (`socket`/`ssl` stay denied by the runtime guard), no HTTP client is importable, and a URL literal is refused by the AST gate unless the HOST turned the web binding on for that run (`check_imports(..., allow_url_literals=True)`); the fetch itself is the existing `web_collect` capability � the same SSRF-hardened transport, size cap and timeout `web_scrape` uses � so the lane adds **no second transport, no second HTML parser and no second network path**. The consent is **per DOMAIN**: the approval kind `scraper_domain` is keyed by the host, the operator approves a site once, and the consent is then remembered as a revocable standing grant; a different site asks again. The collected rows are stored through ONE new front-door route (`POST /api/scraper/datasets` ? `CustomDatasetRecord`, provenance `SCRAPER`, each row keyed by its own content so a re-run updates in place), and the program is saved under `.black-eclipse/scrapers/` so it can be run again by id. Everything collected is **COLLECTED page data** � never a verified source, never a canonical market row.
**Reason:** "Eclipse cannot get data the vault does not have" was a design choice, not a physics limit, and it made the product fail the most ordinary user request ("pull these daily holdings and keep them"). The three gates that blocked it were all policy: the analysis runner hard-coded `network=False`, the runtime guard denied `socket`, and the AST gate refused URL literals. Flipping those in place would have handed the ANALYSIS sandbox a raw network � a second transport, a second parser, an SSRF and exfiltration surface, and a break of the "the sandbox computes, it does not fetch" invariant that the research engine depends on. The alternative was a HOST-MEDIATED fetch: the program asks, the host fetches through the transport that already carries every other web call, and the program keeps the logic (pagination, joining two pages, reshaping records) that no single declarative call can express. The consent is per DOMAIN rather than per program because the thing the operator is really approving is "let Eclipse read this site", and asking again for every scraper against one site would train the user to click through approvals without reading them. Storing the rows as a labelled dataset (not as canonical market rows) keeps the vault's provenance rules intact: a scraped row says where it came from and never claims to be verified.
**Impact:** New `python/harness/scraper/` (`__init__.py`, `program.py`, `authorizers.py`, `store.py`, `tools.py`), tests `python/tests/test_scraper_lane.py`; `python/harness/code/sandbox_tools.py` gains the `web_page` binding (the analysis sandbox's own set is UNCHANGED � `DATA_TOOL_NAMES` vs `WEB_TOOL_NAMES`), `python/harness/code/execution.py` gains `tool_allowlist`/`allow_url_literals`/`tool_call_limit`, `python/harness/code/policy.py` gains `SCRAPER_TOOLS`, `python/harness/code/authorizers.py` composes the scraper authorizer, `python/harness/routers/code.py` lists `scraper_domain` as reviewable, `python/harness/bridge.py` gains `post_json` (the ONE write seam to the front door � `/api/harness/data` stays read-only), `python/harness/agents.py` advertises `scraper_run`; front door `src/app/api/scraper/datasets/route.ts` (+ test) and `src/lib/harness/data-bridge-collect.ts` gains `links` extraction (the pagination handle a generated scraper needs). No new dependency, no new agent loop, no new database table (the rows land in `CustomDatasetRecord`), no change to the read bridge's contract. Docs `docs/harness/scraper-lane.md`, `docs/harness/web-research-engine.md`, `docs/NAVIGATION.md`.

### ADR-052 - Model-authored interactive apps are an `interactive` block in an opaque-origin sandbox; the host injects the market series (2026)
**Decision:** Eclipse can now render a **model-authored mini-app** inline in chat (a price knob, a VWAP explorer, a doji figure). It rides the ONE structured-response pipeline (ADR-043): a new `interactive` schema in `src/lib/response/blocks/interactive.ts`, one entry in the renderer registry, the finalize/repair/degrade chokepoint, the Markdown projection, the PDF export and the `response_block_schema` read-back. The block carries `html` (body markup, inline SVG), optional `css`/`js`, a height, optional static `data`, and an optional `dataset` (`{ kind:'series', symbol, market?, range?, interval? }`). `src/lib/interactive/document.ts` composes ONE document whose `<head>` carries an immutable meta CSP (`default-src 'none'; script-src/style-src 'unsafe-inline'; img-src data: blob:; connect-src 'none'; frame-src/worker-src/object-src 'none'; base-uri/form-action 'none'`) and a tiny runtime (`Eclipse.data()/onData()/resize()`); a model-supplied full document is unwrapped to its body so the model can never replace the policy. The frame is `<iframe sandbox="allow-scripts">` with **no `allow-same-origin`**, i.e. an opaque origin with no app DOM, cookies, storage or network; messages are accepted only from that `contentWindow` with a per-render nonce. The model **never types prices**: `src/lib/interactive/dataset.ts` validates the request and calls the existing read-only `/api/price-history` route from the HOST, normalizes up to 5000 bars with `source`/`asOf`/`freshness`/`stale`, and posts the snapshot into the frame; an empty or failed series is an explicit `unavailable` envelope, never a fabricated line. `provenance:"illustrative"` labels example-only numbers.
**Reason:** Users need to BUILD and VISUALIZE things in the conversation, and the declarative blocks (including `simulation`/`gauge`/`model3d`) cannot express arbitrary interaction. Injecting model markup into the app DOM would be an XSS surface; the accepted posture is an opaque-origin sandbox with an immutable CSP and zero network, which closes host access and exfiltration for a frame that has nothing sensitive behind it. The two-origin/process-isolation shape (Claude Artifacts, MCP Apps) is stronger but needs a second deployable origin and token plumbing; it is deliberately deferred until interactive content is exposed to untrusted third parties. Keeping the data on the host is the fiduciary guard: a widget cannot show invented numbers under a "live" badge, and the real series still carries its observation/provenance envelope.
**Impact:** New `src/lib/response/blocks/interactive.ts`, `src/lib/interactive/{document,dataset}.ts` (+ tests), `src/components/response/{interactive-block,interactive-frame}.tsx`; `contract.ts` union/type, `normalize.ts` aliases, `projection.ts`, `export.ts`, `canvas/content.ts` (`REPORT_BLOCKS`), `prompts.py` guidance, `contract-matrix.test.tsx` sample. A settled ```` ```html ````/```` ```svg ````/```` ```eclipse-app ```` fence renders through the same sandbox (models often answer with code instead of the block), and a full document's own `<style>`/`<script>`/body are preserved while any model-supplied CSP `<meta>` is stripped. No new dependency, no new origin, no new backend route, no change to the read bridge. Docs `docs/interactive-response-engine.md`.

## ADR-053 - The crypto/on-chain/alt-data pack extends the ONE market layer with capabilities, not a second pipeline (2026)
**Decision:** Crypto/on-chain/alt-data coverage is added as **capabilities on the existing Market Data Layer** (ADR-023/024), not a parallel data path. `providers.py` gains `tvl`, `onchain`, `liquidations` and `long_short`; `config.DEFAULT_PRIORITY`/cache TTLs route them to the matching adapter. Five runnable TS adapters ship: `providers/defillama.ts` (keyless protocol/chain TVL), `providers/etherscan.ts` (keyed EVM account), `providers/solscan.ts` (keyed Solana account), `providers/coinglass.ts` (keyed liquidations/long-short) and `providers/hyperliquid.ts` (keyless perps funding/OI). `MarketDataRequest` carries optional `address`/`chain` fields, and `connectors/security.ts` gains ONE hardened `safePost` transport so Hyperliquid's POST-only `info` endpoint rides the same https-only/DNS-pinned/size-capped path as `safeGet` (request-body cap, no redirects, no signing/trading). Canonical records `TvlSnapshot`, `OnchainMetric`, `LiquidationStats` and `LongShortRatio` are normalized by the same gateway/quality/provenance path, and four agent tools (`get_tvl`, `get_onchain_metric`, `get_liquidations`, `get_long_short_ratio`) join the market tool set. The pack is reachable from the UI through ONE read-only route (`GET /api/crypto/alt-data`, same adapters), a Market Overview crypto panel and two catalog widgets.
**Reason:** The crypto pack touches quotes, supply, funding, TVL and on-chain facts, so a second pipeline would duplicate routing, quality, provenance, caching and secret handling — the exact drift the market layer exists to prevent. Adding capabilities keeps one router, one bridge transport, one secret store and one evidence path. Every shipped endpoint was verified against the provider's official docs first (DefiLlama, Etherscan V2, Solscan V2, CoinGlass V4, Hyperliquid `info`); keyed providers fail honestly with `AUTHENTICATION_FAILED` when no credential is present, and an absent/unknown symbol is `SYMBOL_NOT_FOUND` — never a zero or a guess. Hyperliquid deliberately serves only funding/open interest: the instrument master has no spot/perp stamp, so a perp quote/book offered as a spot fallback would be a silent category error.
**Impact:** `python/harness/market/{providers,config,models,gateway,tools,instruments}.py`, `src/lib/harness/market/{types,bridge}.ts`, `src/lib/harness/market/providers/{defillama,etherscan,solscan,coinglass,hyperliquid}.ts`, `src/lib/connectors/security.ts` (`safePost`), `src/lib/provider-keys.ts` (Etherscan/CoinGlass/Solscan entries), `src/app/api/crypto/alt-data/route.ts`, `src/components/screens/crypto-alt-data.tsx`, `src/lib/dashboard/{crypto-widgets.tsx,registry.tsx,layout.ts}`, `docs/harness/market-data.md`, `docs/harness/tool-registry.json`. No Prisma model change, no new agent loop, no second data pipeline, no new HTTP client (`safePost` is the same outbound layer), no change to `/api/harness/data`'s read-only contract.
