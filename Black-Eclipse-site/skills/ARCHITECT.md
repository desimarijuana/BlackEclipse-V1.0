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
**Decision:** Web search and page fetch return a structured RetrievalDiagnostic (provider, category, HTTP status, latency, timeout, result count, bytes, parse outcome, retryability) instead of collapsing every failure into an opaque UNAVAILABLE; a JSON source document is accepted rather than rejected as 'not HTML'. Structured retrieval is one route among several: a direct SEC EDGAR source (tier primary, US issuers, identity-gated) and an operator-configurable second search provider (vault keys SEARCH_API_CONFIG/SEARCH_API_KEY) join the keyless DuckDuckGo default, with selection policy as explicit data in etrieval/planner.py (inancial_statements → [SEC, JDDS, WEB]). The loop retries only transient failures with bounded backoff, switches to the next independent provider, targets unresolved legs, and records a stopReason when it ends.
**Reason:** The NVDA run could not distinguish 'the web had nothing' from 'every route is broken'. Verified root causes: DuckDuckGo answered HTTP 202 with an anti-bot page that parsed to zero results and returned []; a valid pplication/json SEC XBRL response was rejected by a content-type gate; and escalation inspected only status == 'OK', discarding the reason. All web routes shared one transport, so there was no independent fallback.
**Impact:** src/lib/{retrieval-diagnostics,web-search,web-research}.ts, data-bridge.ts (sec_filings, esearch_health, diagnostics on web_search/web_fetch), python/harness/retrieval/{retry,sources,structured,planner,web,layer}.py, python/harness/research/{engine,run,receipt,escalation}.py; NVDA labeled eval python/harness/research/eval/nvda.py; operator smoke python/harness/research/smoke.py. Full decisions: ADR-H25–H28 in docs/harness/decisions.md.

### ADR-031 — Global market research: truthful capability matrix, suffix-aware identity, declared UA, provider eligibility (2026)
**Decision:** Coverage is reported as a per-market CAPABILITY MATRIX (recognition / searchable universe / quote / history / fundamentals / official filings / web+documents / observed health / live-checked) so a listed country is never read as 'every capability works'. Source health is keyed by the route dimensions (source x market x assetClass), never a market-level aggregate copied onto every provider. Instrument identity is global: a recognised exchange suffix (.TW, .KS, .L, …) is split into an implied market and the vault is queried for both the bare local code and the suffixed form; an unknown suffix is never guessed. Providers are gated by eligibility — SEC is skipped (not attempted-then-failed) for a non-US issuer. The shared fetch transport sends a DECLARED, email-contact User-Agent (required by SEC's fair-access policy) and handles JSON/XML/XBRL plus bounded text-PDF extraction. Escalation queries are market-aware (no global '10-K' assumption). Learning candidates carry the run's structured diagnostics and an explicit regional scope, remain inert, and promotion stays operator-gated.
**Reason:** Users reported US-centric failures on real non-US runs (TSMC/Samsung/Petrobras): all web fetch returned UNAVAILABLE, non-US tickers were 'not in the universe', SEC was attempted for a Taiwanese issuer, and coverage/health implied more than was true. Verified causes: (1) a spoofed browser UA gets 403 from SEC/TSMC IR, while a declared email-contact UA gets 200; (2) the vault stores bare local codes while users type Yahoo suffixes, so 2330.TW returned not_found though 2330 (TW) existed; (3) the SEC adapter's supports() gate was never consulted by the retrieval planner; (4) source-health collapsed recorded runs to (market, assetClass) and copied one aggregate onto every declared provider row, producing duplicates; (5) get_coverage instructed the agent to stop when JDdS lacked a ticker.
**Impact:** src/lib/{markets,web-research,web-search,retrieval-diagnostics}.ts, src/lib/harness/{capability,data-bridge,types}.ts, src/lib/fundamentals/providers/sec-edgar.ts, src/app/api/harness/data/route.ts; python/harness/{finance_tools,retrieval_tools,prompts}.py, python/harness/retrieval/structured.py, python/harness/research/escalation.py, python/harness/skills/learning.py, python/harness/eclipse_memory/{schema,store}.py. See docs/harness/decisions.md (ADR-H29..H32) and docs/DECISIONS.md ADR-031.

### ADR-033 — Aurora sentiment becomes an explainable Market Regime (2026)
**Decision:** The app-wide Aurora glow is driven by a transparent Market Regime model (src/lib/regime/) instead of a fixed 60% price / 40% coarse-RSS blend. A reading is a set of named components — price & breadth, volatility/options, macro/risk, news/narrative, positioning — each exposing score, weight actually used, availability, timestamp, source and confidence. Weights renormalize over the available set; missing inputs lower confidence (never a false neutral); stale inputs are excluded; a missing core price/breadth input makes the reading UNAVAILABLE. Taxonomy: Risk-on broadening / Fragile rally / Mixed / Risk-off / Narrative shock / Unavailable. Scope is explicit (selected market | US | global). All inputs come from JDDS only, through one new contract GET /api/regime. The glow stays decorative (pointer-events-none, aria-hidden); an accessible top-bar control opens the interactive frosted-glass breakdown, with actions to open Market Overview, filter news, ask Eclipse (be:ask-eclipse), and create a regime-change alert.
**Reason:** The old model was hardwired to US indices, exposed no confidence/data-age/provenance, used fixed weights, and could be influenced by cached/fallback data — attractive but not trustworthy. Financial data must never be fabricated; simulated/fallback/stale data must never read as live sentiment.
**Impact:** src/lib/regime/{types,scoring,client,store,visuals}.ts, src/app/api/regime/route.ts, src/components/layout/{aurora-glow,market-regime-control,top-bar}.tsx, src/components/ui/Aurora.tsx (added `dim`), src/components/screens/stock-chat.tsx (be:ask-eclipse), tests src/lib/regime/scoring.test.ts. See docs/DECISIONS.md ADR-033 and docs/ARCHITECTURE.md › Market Regime.


### ADR-034 � Autonomous-but-governed learning: provider layer, structured skill patches, hybrid namespaces, prompt segments (2026)
**Decision:** Four capabilities were added without relaxing any safety invariant. (1) External memory is a dedicated provider layer (python/harness/memory_providers/) implementing ONE MemoryProvider contract over the existing MCP boundary; external results are labelled provenance=external_provider / verified=false, fenced, native-first routed, never promoted, and external writes need an explicit user request AND approval (automatic external writes are absent by construction). (2) Self-improving skills are STRUCTURED patches (JSON-pointer replace/add/remove over an allowed-field set; identity/permission/tool/risk fields are not patchable) that always create a NEW SkillVersion; a stale base version is rejected, activation requires a passing evaluation, canary is limited to safe non-mutating skills, and rollback (manual or automatic on a regression/correction) is atomic and preserves both versions. (3) Memory retrieval uses logical namespaces and a bounded hybrid score whose semantic term can only nudge an already-authorized memory � never confirm, supersede, archive or authorize. (4) The prompt is split into immutable segments with an identity-only prompt_cache_key, so a new user message never invalidates the reusable prefix, and skills are injected as a bounded relevant-only manifest.
**Reason:** The product goal is autonomy in discovering, proposing, testing, versioning, activating, monitoring and rolling back improvements � but never autonomy in silently changing truth, permissions, financial-retrieval rules, or irreversible behavior. Each capability therefore ends at a reviewable, versioned, reversible or clearly-labelled boundary.
**Impact:** python/harness/memory_providers/* (new), python/harness/prompt_segments.py (new), python/harness/skills/{patches,versioning}.py (new), python/harness/eclipse_memory/hybrid.py (new); memory_tools.py, service.py, graph.py, main.py, agents.py; eclipse_memory/{policy,schema,store,skill_quality}.py; skills/{manifest,registry,evaluation}.py; migrations 12/13; routes /memory-providers/*, /skills/{id}/version-history + /skills/{id}/patch/**; TS skills-client/browser, eclipse-memory-client/browser/types, routes + a patch-version UI panel. Full decisions: ADR-H52�H55 in docs/harness/decisions.md.

### ADR-035 � Long-lived sessions, named profiles and reversible file editing (2026)
**Decision:** Sessions are first-class: a durable `ChatSession` (metadata + a bounded deterministic summary) in agent-memory.db, a run belongs to a session which belongs to one profile, session search ranks by the documented hybrid (exact phrase > BM25 > decision/correction/skill-failure/memory-action > recency > prose) with full filters, and a summary is searchable but never auto-injected. Named profiles are a metadata registry (eclipse_memory/profiles.py) over `.black-eclipse/profiles/` with per-namespace scoping, prompt profile, retention and settings, explicit READ-ONLY inheritance, and request-scoped isolation on every memory/session/skill/provider query. The Markdown memory projection is edited only through a targeted, atomic, versioned API (expectedVersion stale-edit guard, temp+fsync+rename, backup before regenerate, structured revision history + rollback + diff); SQLite remains canonical and archive/restore stay structured-memory actions.
**Reason:** Users need to continue long-lived sessions and keep work/personal/project memory isolated, and a hand-edited projection must not lose a concurrent edit, leave a partial file, or lack an audit trail � all without merging stores or adding infrastructure.
**Impact:** python/harness/persistence.py (ChatSession + run/session scope columns), session_index.py (build_summary), eclipse_memory/profiles.py, schemas.py (RunRequest ids), graph.py, main.py (/sessions*, /profiles*, filters); src/lib/harness/{memory-files,run-service,eclipse-memory-*,python-client}.ts, new /api/sessions, /api/profiles, /api/eclipse-memory/files/{edit,history}, and Memory Control Room tabs (Sessions/Profiles/Providers/Files/Skills + richer Overview). Full decisions: ADR-H56�H58 in docs/harness/decisions.md.

### ADR-036 - MCP Phase 6: trustworthy-before-capable hardening and resilience (2026)
**Decision:** The MCP layer is hardened in ordered phases. (1) The config contract is shareable and safe: `${VAR}`/`${env:VAR}` interpolation with a fail-closed remote rule, `selected_tools` include/exclude globs (legacy list unchanged), a static entry screen that REFUSES shell/interpreter/egress shapes at load, save and spawn, a fail-closed `trust` tier (`full`/`untrusted`) where an untrusted server needs a per-call approval for every non-read call and its own annotations can never activate a tool, and Eclipse tool names use a double-underscore boundary (`mcp__<server>__<tool>`) with the identity digest kept only as a genuine-collision last resort. The Python MCP read routes are operator-gated. (2) Lifecycle is resilient: separate jittered retry budgets, a call-time reconnect that re-checks authority, an honest session-expiry rule (a read replays once; a write returns `outcomeUncertain` and is never replayed), optional keepalive/recycle, POSIX orphan reaping via a stdlib-only supervisor (Windows relies on the SDK's Job Object), and lazy startup with a fingerprint-keyed on-disk schema cache. Every capability stays inert until an operator selects it; discovery never activates.
**Reason:** Everything users get wrong happens at the config boundary (a hostile entry that executes, a secret in plaintext, an unshareable file, an unusable filter, an undocumented authorization story), and one transient network blip permanently disabled a server until a manual reload while a crashed parent leaked children. Trust must be declared, not inferred from a server's own metadata, and a call that may have had an effect must say so rather than silently replay.
**Impact:** python/harness/mcp/{interpolation,screening,lifecycle,schema_cache,orphan_supervisor}.py (new); config.py, naming.py, client.py, manager.py, diagnostics.py, __init__.py; routers/mcp.py (read routes gated + save screening); python/requirements.txt (httpx2 pin); mcp-servers.example.json; tests python/tests/test_mcp_{config_hardening,lifecycle,orphan_reaping}.py. Full decisions: ADR-H67, ADR-H68 in docs/harness/decisions.md; progress docs/harness/mcp-phase-6-progress.md.

### ADR-037 - MCP data sources join native planning; sampling uses the run model; AC OAuth is a manual https step (2026)
**Decision:** An operator-declared MCP data tool (`data_source_tools: {tool: dataType}`) becomes a native `RetrievalSource` via `manager.mcp_sources()`, reaches `FinancialRetrievalLayer` through `ToolContext.mcp_manager`, and is considered by `plan_retrieval(additional_sources=...)` after native structured sources but before generic web; provenance stays `secondary`/`eclipseVerified=false` and JDdS is never silently upgraded. Server sampling (`sampling/createMessage`) runs on the runtime's own model adapter (`models.build_chat_model`) with the run's credentials and the policy token cap, still off by default. Eclipse-as-server is exercised by TWO offline clients (Streamable HTTP + SSE); the real Hermes interop is a documented manual step.
**Reason:** The deferred seams were real: without wiring, an MCP source could never be planned, a server sampling request could never be served, and "two clients" was asserted from one. The SDK's OAuth client refuses plain-http OAuth URLs (RFC 8252), so the interactive authorization-code leg is necessarily a manual https step � stated, not faked.
**Impact:** python/harness/mcp/{manager,mcp_retrieval,config,interactions}.py, python/harness/{tools,graph,service,retrieval_tools}.py, python/harness/retrieval/{layer,planner}.py, python/harness/routers/mcp.py; TS src/lib/harness/{mcp-types.ts}; tests test_mcp_source_planning.py, test_mcp_sampling.py, test_mcp_server_exposure.py, test_mcp_oauth.py. Full decision: ADR-H73 in docs/harness/decisions.md; progress docs/harness/mcp-phase-6-progress.md.
