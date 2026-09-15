---
title: Architecture
status: Current
last-verified: 2026-09-15
---

# Architecture

**Who this is for:** a developer about to make a structural change, or anyone
trying to understand how the pieces fit.

This is the *map*. For "why", read [`DECISIONS.md`](./DECISIONS.md). For
"where is the file", read [`NAVIGATION.md`](./NAVIGATION.md). For the data path,
read [`DATA-FLOW.md`](./DATA-FLOW.md).

> The authoritative, more detailed engineering brain lives in
> [`../skills/ARCHITECT.md`](../skills/ARCHITECT.md). Where the two overlap, that
> file is the deeper reference and this one is the readable summary.

## Layer 0 — The shell

`src/app/page.tsx` renders `<StockChat />` inside an `ErrorBoundary`. That is the
whole routing story for the app: **one page**.

`src/components/screens/stock-chat.tsx` is the SPA shell and owns:

- the `activeTab` state machine,
- keep-alive tabs (mount on first visit, then `display:none`),
- conversation persistence in `localStorage` (`chats_guest`),
- deep-link boot (`/?symbol=AAPL` opens the chart),
- the command-palette destination bus, and the `be:navigate` custom event,
- the full-viewport **Aurora** glow driven by combined sentiment.

Screen chunks are loaded with `next/dynamic` + `ssr: false` so first paint only
compiles the chat shell. This is a deliberate memory/perf decision — do not
convert these to static imports.

## Layer 1 — Screens & components

```
src/components/
  screens/        full-page views + their data/hook modules
  layout/         sidebar, top-bar, global-search, agentation
  chat/           chat-specific pieces
  ui/             reusable primitives (button, card, dialog, tab-bar, …)
  chart/          the ECharts/TradingView chart widget
  journal/        trading journal UI
  market-workspace/  the multi-panel market grid UI
  workspace/      the customizable widget-grid UI
```

Conventions: `'use client'` at the top of client files, **named exports**, and
the `cn()` helper from `src/lib/utils.ts`. UI primitives come from
`src/components/ui/`; do not hand-roll a new one.

## Layer 2 — Client data layer

Two mechanisms:

1. **DataHub** (`src/lib/workspace/data-hub.ts`) — a singleton client-side
   pub/sub. Widgets declare `dataDeps` (topic ids); the hub batches one fetch per
   topic, caches with a TTL, auto-refreshes on an interval, and fans the result
   out. Topics are registered with `registerTopic(jsonTopic(...))` at module load
   and consumed with `useTopic<T>(id)` / `useRefreshAll()`.
   - Hidden widgets unsubscribe, which stops the refresh timer — this is the
     rate-limit protection.
   - A failed topic becomes `UNAVAILABLE`; it never takes down the dashboard.
   - Provenance is explicit: `LIVE | CACHED | HISTORICAL | DEMO | ESTIMATED |
     UNAVAILABLE`.
2. **Zustand stores** for UI state (sidebar config, dashboard layouts, search,
   market-workspace, aurora palette) — persisted to `localStorage`, not the DB.
3. **Portfolio engine** (`src/hooks/use-portfolio-engine.ts`) — pure FIFO/LIFO
   cost-basis and stats logic, consumed by both the portfolio screens and the
   dashboard portfolio widgets. There is **no broker integration yet**: every
   `trading`-category widget (Quick Trade, Open Positions, Working Orders, Margin
   Usage, Today P&L) renders the shared `UNAVAILABLE` stub in
   `src/lib/dashboard/registry.tsx`. Do not fabricate fills — wire a real broker
   adapter first.

## Layer 3 — API routes

`src/app/api/**/route.ts`. Route handlers are thin and server-only. Mutating
routes are protected by `src/lib/api-guard.ts`:

- `checkMutationAllowed` / `guardMutation` — a three-tier policy: same-origin
  browser requests always pass; a correct `CRON_SECRET` (Bearer or `x-api-key`)
  passes; otherwise the request must come from localhost.
- `rateLimit` / `guardExpensiveMutation` — in-memory fixed-window per-IP limiter
  for expensive endpoints.
- `checkOutboundUrl` / `filterSafeUrls` — SSRF allowlist for user-configurable
  feed URLs.

Key route groups: `stocks`, `quote`, `price-history`, `markets` (+`global`),
`indices`, `forex`, `commodities`, `heatmap`, `news` (+`status`, `alert`),
`economics` (+`snapshot`, `calendar`), `search` (+`global`, `index`), `agent`
(+`chat`, `research`, `activity`), `journal/*` (largest group), `alerts/*`,
`scraper` (+`import`), `refresh`, `settings`, `cron` (+`run`, `refresh-news`),
`asset-details`, `symbols`, `commodities`.

## Layer 4 — JDDS (the data vault)

**JDDS = "Joint Data Distribution System".** One SQLite file (`jdds.db`) accessed
through Prisma with the `better-sqlite3` adapter. `src/lib/db.ts` owns the client
and exports `prisma` plus `yieldToEventLoop()` (critical: better-sqlite3 is
synchronous, so bulk writers must yield or they freeze the server).

The schema (`prisma/schema.prisma`) is organized in domains:

| Domain | Models |
|---|---|
| Market universe | `Market`, `Asset`, `Price`, `IndexQuote` |
| News | `NewsItem`, `SourceHealth` |
| Macro | `MacroSeries` |
| Scheduling & config | `CronJob`, `SystemConfig` |
| Agentic research memory | `ResearchReport`, `AgentRun`, `ResearchFinding` |
| Alerts | `PriceAlert`, `PriceAlertEvent`, `Candles` |
| Trading journal | `JournalProfile`, `TradingAccount`, `Strategy`, `StrategyRule`, `Setup`, `Tag`, `JournalDay`, `DailyReview`, `DailyEmotion`, `Trade`, `TradeExecution`, `TradeScreenshot`, `TradeAnnotation`, `TradeTag`, `MarketContext`, `JournalEntry`, `Review` |

Two design notes that matter:

- **Dedup by constraint.** `Asset` is unique on `[marketId, symbol]`; `Price` is
  keyed by `assetId`; `NewsItem` has a `dedupKey`. Imports are idempotent upserts,
  not inserts.
- **Auth-ready, not auth-ful.** The journal carries an optional owner concept so
  a `User` relation can be added later without a rewrite. There are no accounts
  today — the app is a guest app.

## Background workers

All in-process, all started from `src/instrumentation.ts`:

| Worker | Cadence | Source |
|---|---|---|
| Price refresh | configurable, default 15 min | `src/lib/scraper/scheduler.ts` |
| Universe sync | daily | `src/lib/scraper/scheduler.ts` |
| News ingest | default 5 min | `src/lib/news/ingest.ts` |
| Boot warm-up | once, prod-only by default | `src/lib/scraper/scheduler.ts` |
| Alert monitor | polling loop | `src/lib/alerts/alertMonitor.ts` |

They coordinate through mutex flags (`isRunning`, `syncBusy`, `warmUpBusy`) so
two heavy SQLite write storms never run at once. This is not incidental — running
them concurrently is what used to freeze the API.

## The two workspace systems (read this twice)

| | Widget workspace | Market workspace |
|---|---|---|
| Engine | `src/lib/workspace/` | `src/lib/market-workspace/` |
| UI | `src/components/workspace/` | `src/components/market-workspace/` |
| Powers | Command Center dashboard | Market Workspace tab |
| Unit | widget card in a column | chart/market panel |
| Shape | sections → columns → widgets, + rail zone | panels with presets/ops |
| Persistence | `localStorage` via `use-workspace` | `localStorage` via `use-market-workspace` |

Both are real and both are supported. The **retired** thing is
`src/lib/customize/` — an earlier kernel that is documented as superseded and
must not receive new features. See ADR-005 and ADR-006.

## The command center (⌘K)

`src/components/layout/global-search.tsx` (palette) + `src/components/layout/top-bar.tsx`
(header trigger) sit on top of `src/lib/search/`. The flow is two pure steps:

1. **Grammar** (`search/grammar.ts`) — `parseQuery(raw)` splits the raw query into a
   *scope* (a leading prefix: `>` commands, `#` symbols, `@` indicators, `/` pages,
   `~` your data, `?` help), *free text*, and *field operators* (`kind:`, `class:`,
   `market:`, `symbol:`/`asset:`). It is framework-free and unit-tested
   (`grammar.test.ts`) so the vocabulary can grow without touching the UI.
2. **Resolver** (`search/resolver.ts`) — classifies intent, scores the static
   registry + FlexSearch universe, and applies the parsed scope/filters
   (`scopeKinds`, `matchesFilters`) plus a recency multiplier. It returns
   `ResolvedSearch` including the `parsed` query and a `showHelp` flag.

Invariants: search is **fully offline and deterministic** — no LLM on the query
path (only the explicit "Ask AI" escalation row). Navigation is a *destination
bus*: the palette dispatches a `Destination`, the shell subscribes to
`pendingDestination`, so no component reaches into the router. The command-center
vocabulary (scopes/operators) is a user-facing contract — extending it means
editing `grammar.ts` and its tests together.

**Intelligence & actions.** Beyond the resolver:
- `resolver.ts` `expandTerms` (a curated synonym/acronym table) turns "gold",
  "us jobs data", "fed rate" into the right symbol at a score discount, so an
  explicit match still wins. Ranking is personalized by entity *visit* history
  (`recencyScore` opt; the palette feeds it `visitRecencyScore` from the store).
- `calc.ts` powers an inline offline calculator + indicative currency conversion;
  `commands.ts` detects parameterized verbs (`alert`, `watch`, `compare`, `chart`)
  and offers argument autocomplete. Both are pure and unit-tested.

**Result UX.** The resolver returns `total` (untruncated match count, for
"showing N of M"), a `suggestion` "did you mean" on a zero-hit query (static
registry only), and `related` cross-tab pivots for a resolved instrument. The
palette groups results by entity kind with per-group counts and collapsible
headers, pins entities (persisted in `localStorage`, replayed from a serialized
destination), and copies symbols. Pins, visits, and collapse state live in the
command store — the resolver stays pure.

**Accessibility.** The input is an ARIA combobox driving a `role="listbox"`
result list with `aria-activedescendant`; a polite live region announces result
counts. Rows are memoized so selection changes don't re-render the whole list.

## Design system

All surfaces use the shared frosted-glass classes from
`src/app/globals.css`: `.glass-card`, `.glass-card-strong`,
`.glass-card-subtle`, `.glass-drawer`, `.glass-button`. Tab bars use `TabBar`
(`src/components/ui/tab-bar.tsx`), which has two container variants: `glass`
(default, heavy frosted strip) and `subtle` (the restrained `.tab-bar-subtle`
control-strip tier for dense/toolbar-adjacent rows, e.g. the Command Center
market tabs). There are hard rules about `backdrop-filter`, tint opacity, and
backdrop roots — see the
[`black-eclipse-ui` skill](../../.opencode/skills/black-eclipse-ui/SKILL.md).
Do not introduce raw `backdrop-blur-*` or flat fills for cards.

## Architectural rules (short list)

1. Reuse existing hooks/services/primitives before writing new ones.
2. Do not duplicate business logic (`use-screener-filters.ts`,
   `use-portfolio-engine.ts`, the agent layer).
3. Server-only logic stays in API routes — never in client components.
4. Do not change data shapes screens depend on without updating all consumers.
5. Do not add a dependency without justification; prefer the lighter option.
6. Keep files small — memory is the top constraint on this machine.
7. Simulated data is always labeled; missing data is `UNAVAILABLE`, never faked.
