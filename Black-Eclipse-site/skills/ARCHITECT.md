# ARCHITECT.md — System Architecture & Engineering Knowledge

> Read this file **before** making any significant architectural change to BlackEclipse.
> If the codebase conflicts with anything here, **the actual working implementation is the source of truth** until it is intentionally changed and this file is updated.

---

## 1. Product Definition

### What BlackEclipse is
An **open-source, agentic AI investment research platform** presented as a Bloomberg-inspired terminal UI. It provides market screening, crypto bubble visualization, portfolio tracking, financial news, and an AI research chat — all in a dark, glassmorphic interface.

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

```
User
 │
 ▼
UI / Chat (StockChat terminal)
 ├── Chat tab        → src/components/screens/stock-chat.tsx → src/lib/agent/*
 ├── Discovery tab   → MarketOverviewScreen (market-overview.tsx + use-screener-filters.ts + market-data.ts)
 ├── Market tab      → MyPortfolio (my-portfolio.tsx + use-portfolio-engine.ts)
 ├── News tab        → MarketNews (market-news.tsx) → /api/news (RSS)
 ├── Bubbles tab     → CryptoBubbles (crypto-bubbles.tsx)
 └── Chart tab       → EmbeddedChart (embedded-chart.tsx) → TradingView widget
 │
 ▼
Application Layer (React client components, 'use client')
 │
 ▼
API / Services (src/app/api/*)
 └── /api/news → rss-parser → Yahoo/CoinDesk/CoinTelegraph/CNBC feeds
 │
 ▼
AI / Research Layer (src/lib/agent/*)
 ├── types.ts        → AgentProvider, AgentTool, ChatMessage interfaces
 ├── mock-provider.ts→ built-in keyword-based mock
 └── registry.ts     → getAgentProvider() → first configured provider, else mock
 │
 ▼
Data Sources
 └── RSS feeds (free) + demo data (src/components/screens/market-data.ts)
```

### Frontend
- **Next.js 15 App Router**, React 19, TypeScript, Tailwind CSS v4.
- Client components marked `'use client'` at the top of each file.
- All screens live in `src/components/screens/` and are routed through `src/components/screens/stock-chat.tsx` via an `activeTab` state (no URL routing for tabs — single page).
- Reusable primitives in `src/components/ui/` (button, card, dialog, etc.).

### Backend
- Minimal — only `/api/news` currently exists (`src/app/api/news/route.ts`).
- Route handlers use `NextResponse` and `export const dynamic = "force-dynamic"`.

### Zero Configuration Policy
- The app runs fully on **demo data** (`src/components/screens/market-data.ts`) with no keys/DB.
- News works via **free RSS** with an offline mock fallback (`NEWS_MOCK` in market-news.tsx).
- **Data source priority (user configures as little as possible):**
  1. **Agentic scraper** (primary) — free, built-in, works for any market with zero setup.
  2. **User-provided API** (optional) — used only if the user supplies a key (Finnhub, Alpha Vantage, etc.).
  3. **Demo data** (fallback) — always works when no live source is available.
- The user should **never be required** to configure anything. The agentic scraper is the default.

### API Layer
- `src/app/api/news/route.ts` — fetches RSS, extracts headline/summary/source/sentiment, paginates server-side.

### Database
- **None currently.** No SQLite, no PostgreSQL, no ORM in the active codebase.
- Portfolio + watchlist + chat persistence are client-side via **localStorage**.
- `jdds_backup.sql` (a removed PostgreSQL dump) is deleted and gitignored (`*.sql`).
- **PLANNED:** a local SQLite store for real persistence (zero-config, file-based).

### Data Ingestion
- **PRIMARY: agentic scraper** — a smart scheduler that scrapes market data for free. It is timezone-aware (only scrapes open markets), priority-based (watchlists first), and de-duplicated. This is the default source so users configure nothing.
- **SECONDARY: user-provided API** — optional keys (Finnhub, Alpha Vantage, etc.) override the scraper for that source when supplied.
- **FALLBACK: demo data** — used when no live source is available or reachable.

### Market data providers
- **CURRENT:** none live. Demo data only.
- **PRIMARY (PLANNED): agentic scraper** — Yahoo Finance (`yahoo-finance2`, free, covers 80+ markets incl. PSX `.KA`, India `.NS`, China `.SS`) with a lightweight cheerio fallback for markets Yahoo misses.
- **OPTIONAL: user-supplied** Finnhub/Alpha Vantage/Twelve Data when a user configures them.
- Symbols map to TradingView via `getTradingViewSymbol()` in `src/lib/utils.ts`.

### Background workers / scheduled jobs
- **None currently.** No daemon. **PLANNED:** cron-based scheduler for price/universe/news refresh.

### Agent/AI architecture
- `src/lib/agent/types.ts` defines `AgentProvider`, `AgentTool`, `ChatMessage`.
- `src/lib/agent/mock-provider.ts` — built-in keyword-based responder.
- `src/lib/agent/registry.ts` — `getAgentProvider()` returns first configured provider else mock.
- `src/components/screens/stock-chat.tsx` calls `getAgentProvider().chat(...)` for replies.
- **PLANNED:** real providers (OpenAI/Anthropic/Ollama), a tool registry (query data, scrape, search), and skills (research, screen, portfolio, monitor).

### Charts & visualization
- TradingView widget via `src/components/screens/embedded-chart.tsx` and `tradingview-chart.tsx`.
- Recharts for portfolio charts (my-portfolio.tsx).
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
| Charts | Recharts **3.8.1** |
| 3D/GL | ogl **1.0.11** |
| News | rss-parser **3.13.0** |
| PDF | jspdf + jspdf-autotable |
| Utils | clsx, tailwind-merge |
| Tests | Vitest **4.1.10** |

### PLANNED (not yet implemented — do not treat as current)
- SQLite / better-sqlite3 (local storage)
- yahoo-finance2 (free market data)
- A real LLM provider SDK (openai / @anthropic-ai/sdk / ollama)
- A background scheduler / daemon

### EXPERIMENTAL / DEPRECATED
- The original **JDdS daemon** and its PostgreSQL provider system were **removed**. Do not reintroduce them without updating this file.
- `@base-ui/react` v1.5.0 has **SSR/hydration quirks** — Portal-based components (Tooltip, Dialog) must be mounted-gated.

---

## 4. Data Architecture

### Core entities
- `StockItem` — full fundamental/technical stock record (see `market-data.ts`).
- `IndexCard`, `SectorPerformance`, `ShifterItem` — dashboard metadata.
- `FundItem`, `ETFItem`, `NewStockItem`, `BlueChipItem` — screener categories.
- `NewsItem` — headline, source, ticker, sentiment, impact, url.
- `Message` (`src/types/chat.ts`) — chat messages.
- Portfolio/transaction/alert data — client-side shapes in `my-portfolio.tsx` + `use-portfolio-engine.ts`.

### Relationships
- No DB relationships — all data is in-memory/static or localStorage.

### Market data flow
1. Screens call `/api/stocks` **or** read demo data directly (currently the latter).
2. `use-screener-filters.ts` applies filter/sort logic as a pure hook.
3. `market-data.ts` supplies demo universe + regional datasets.

### Symbol/universe management
- `getTradingViewSymbol()` maps raw symbols → TradingView format (crypto, indices, PSX `.KA`, India `.NS`, etc.).
- `getRegional*()` functions in `market-data.ts` return country-specific datasets (USA/India/Pakistan).

### Data normalization & validation
- Filter logic in `use-screener-filters.ts` parses market-cap/volume strings (`1.3T`, `28.4B`, `540M`) to numbers.
- Sentiment is a keyword heuristic in the news route.

### Data freshness
- News is `force-dynamic` (fetched per request).
- No caching layer currently (the old `data-layer/cache.ts` was removed).

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
