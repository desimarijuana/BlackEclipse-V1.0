---
title: Navigation — Where Things Live
status: Current
last-verified: 2026-09-15
---

# Navigation — Where Things Live

**Who this is for:** anyone asking "which file do I open to change X?"

This doc is also the **update trigger table**: when you add, move, or rename a
top-level folder or a major module, update the relevant row here in the same
change. That is the mechanism that keeps docs from drifting.

## Top-level map

```
Black-Eclipse-site/
  src/
    app/            Next.js App Router: page.tsx + api/**/route.ts
    components/     UI — screens, layout, chat, ui primitives, workspaces
    lib/            All logic: data, scraper, agent, domains
    hooks/          Shared React hooks
    types/          Shared TypeScript types
    generated/      Prisma client output (gitignored — do not edit)
  prisma/           schema.prisma (the JDDS schema)
  scripts/          Importers, bridge, doctor, db-guard, QA
  skills/           The engineering operating system (ARCHITECT/REMEMBER/…)
  docs/             This folder
  jdds.db           SQLite data vault (committed as a seed snapshot)
```

## By task

| I want to… | Open |
|---|---|
| Change the app shell / add a tab | `src/components/screens/stock-chat.tsx`, `src/components/layout/sidebar.tsx` |
| Change sidebar defaults / shortcuts | `src/lib/sidebar/config.ts` |
| Work on the screener | `src/components/screens/market-overview.tsx`, `use-screener-filters.ts`, `market-data.ts` |
| Work on portfolio | `src/components/screens/portfolio/`, `src/lib/portfolio/`, `src/hooks/use-portfolio-engine.ts` |
| Work on the journal | `src/components/journal/`, `src/lib/journal/` |
| Work on the dashboard widgets | `src/lib/dashboard/`, `src/components/screens/dashboard/` |
| Add/edit a dashboard widget | `src/lib/dashboard/registry.tsx` + `widgets.tsx` (and `widget-def.ts` contract) |
| Work on the widget-grid engine | `src/lib/workspace/`, `src/components/workspace/` |
| Work on the market-panel grid | `src/lib/market-workspace/`, `src/components/market-workspace/` |
| Change scraping / scheduling | `src/lib/scraper/` (`scheduler.ts`, `price-scraper.ts`, `fetchers/`) |
| Change news ingestion | `src/lib/news/ingest.ts`, `src/app/api/news/` |
| Change economics/macro | `src/lib/economics/`, `src/components/screens/economics/` |
| Change alerts | `src/lib/alerts/`, `src/app/api/alerts/`, `src/app/alerts/` |
| Change the AI agent / research | `src/lib/agent/` (`registry.ts`, `loop.ts`, `research.ts`, `tools.ts`) |
| Change the chart | `src/lib/chart/`, `src/components/chart/`, `src/components/screens/tradingview-chart.tsx` |
| Change global search (⌘K) | `src/lib/search/` (query grammar: `grammar.ts`; commands: `commands.ts`; calculator: `calc.ts`), `src/components/layout/global-search.tsx` |
| Add a symbol to the watchlist outside React | `addToWatchlist` in `src/lib/dashboard/watchlist-store.ts` |
| Create a price alert programmatically | `src/lib/alerts/quick-alert.ts` → `POST /api/alerts` |
| Change the Aurora glow | `src/components/ui/Aurora.tsx`, `src/lib/aurora-sentiment.ts`, `src/lib/aurora/` |
| Change API protection / rate limits | `src/lib/api-guard.ts` |
| Change the DB schema | `prisma/schema.prisma` → `prisma db push` |
| Change the DB client | `src/lib/db.ts` |
| Change boot behavior / start a worker | `src/instrumentation.ts` |
| Change styling / glass classes | `src/app/globals.css` (see the `black-eclipse-ui` skill) |
| Change boot diagnostics | `scripts/doctor.js`, `scripts/up.js` |
| Change DB durability/backup | `scripts/db-guard.js` |

## By domain folder (`src/lib/`)

| Folder | Owns |
|---|---|
| `agent/` | Provider abstraction, tool loop, multi-agent research, journal tools |
| `alerts/` | Condition evaluator, feeds, notifier, alert monitor |
| `aurora/` | Aurora palette store + theme |
| `chart/` | Chart types, data hooks, indicators, drawings, structure, providers |
| `dashboard/` | Widget catalog/definitions, renderers, market views, intelligence, dashboard + portfolio stores |
| `economics/` | Macro fetching, sources, calendar, snapshot |
| `journal/` | Journal data access, trade math, analytics suite, CSV import |
| `market-workspace/` | The market-panel workspace engine |
| `news/` | Background RSS ingestion |
| `portfolio/` | Portfolio types + risk math |
| `scraper/` | Price/universe scraping, scheduler, fetchers, CSV |
| `search/` | Global search registry, intent, query grammar/operators, ranking, resolver, calculator/commands, stores |
| `sidebar/` | Sidebar config + store |
| `workspace/` | The widget workspace kernel (DataHub, ops, persistence, canvas) |

## By API route group

`stocks` · `quote` · `price-history` · `asset-details` · `symbols` ·
`markets`(+`global`) · `indices` · `forex` · `commodities` · `heatmap` ·
`news`(+`status`,`alert`) · `economics`(+`snapshot`,`calendar`) ·
`search`(+`global`,`index`) · `agent`(+`chat`,`research`,`activity`) ·
`journal/*` · `alerts/*` · `scraper`(+`import`) · `refresh` · `settings` ·
`cron`(+`run`,`refresh-news`).

## Key contracts (read before changing)

| Contract | File |
|---|---|
| Widget definition | `src/lib/workspace/widget-def.ts` |
| Widget registry (dashboard) | `src/lib/dashboard/registry.tsx` |
| DataHub topic/entry | `src/lib/workspace/data-hub.ts` |
| Workspace layout ops | `src/lib/workspace/ops.ts` |
| Market workspace ops | `src/lib/market-workspace/ops.ts` |
| Agent provider interface | `src/lib/agent/types.ts` |
| Mutation guard | `src/lib/api-guard.ts` |
| Tab ids | `AppTab` in `src/components/layout/sidebar.tsx` |

## Documentation trigger table

When a change touches one of these, update the listed doc in the same change:

| Changed path | Update |
|---|---|
| `src/instrumentation.ts`, `src/lib/scraper/`, `src/lib/news/` | `DATA-FLOW.md` |
| `prisma/schema.prisma`, `src/lib/db.ts` | `ARCHITECTURE.md` (JDDS section), `DATA-FLOW.md` |
| `src/lib/workspace/`, `src/lib/market-workspace/`, `src/lib/customize/` | `ARCHITECTURE.md` (workspaces), `DECISIONS.md` |
| `src/lib/api-guard.ts`, auth/env behavior | `ARCHITECTURE.md`, `QUICKSTART.md` |
| `src/components/screens/stock-chat.tsx`, `src/lib/sidebar/config.ts` | `OVERVIEW.md`, `ARCHITECTURE.md` |
| Setup/scripts/`package.json` scripts | `QUICKSTART.md` |
| A new top-level folder or major module | this file |
| A new architectural decision | `DECISIONS.md` |

## Retired / do not build on

- `src/lib/customize/` — superseded customization kernel (ADR-005).
- The old JDdS daemon and its PostgreSQL provider system — removed.
- `MarketSidePanel` as a separate page — its widgets are now the workspace rail.
