---
title: Glossary
status: Current
last-verified: 2026-09-15
---

# Glossary

**Who this is for:** anyone hitting a term that is not obvious from the code.

Terms are grouped, not alphabetical, so related ideas stay together.

## Data

**JDDS** — "Joint Data Distribution System." The project's own name for the
SQLite vault (`jdds.db`) plus the rule that goes with it: data is stored once and
distributed to every screen. It is not a service or a daemon — just the DB and
the architecture around it. (`prisma/schema.prisma` header)

**DataHub** — the client-side pub/sub layer (`src/lib/workspace/data-hub.ts`).
Components subscribe to *topics*; the hub fetches each topic once, caches it with
a TTL, refreshes on an interval, and fans the result out. Hidden widgets
unsubscribe so they stop burning rate limits.

**Topic** — a named data feed in the DataHub, e.g. `market:indices:US`,
`market:overview`, or `journal:analytics`. Registered once with
`registerTopic(jsonTopic(...))`.

**Provenance / `DataSource`** — the label on every DataHub entry saying where the
data came from: `LIVE | CACHED | HISTORICAL | DEMO | ESTIMATED | UNAVAILABLE`.
A source of truth for "is this real and current".

**`Price.source`** — the database-level provenance: `'scraper'` (live scrape) vs
`'csv'` (imported historical/API data).

**Warm-up** — the boot-time bulk job that fills prices for open markets so page
loads are instant. Production-only by default; opt in during dev with
`BE_WARMUP=1`.

**Universe** — the set of assets belonging to a market (`Asset` rows). "Syncing
the universe" means discovering new listings and deactivating dead symbols.

**`yfinance` bridge** — the optional Python path (`scripts/yfinance_bridge.py`)
used for markets TradingView covers poorly. Requires Python 3.9+.

**Stale** — data older than its refresh cycle, or imported data. It must be
labeled, never presented as live.

## Workspaces & UI

**Widget** — a single card on the Command Center dashboard, defined by a
`WidgetDefinition` (id, category, label, icon, sizes, `dataDeps`, …).

**Widget workspace** — the engine behind the Command Center dashboard:
`sections → columns → widget cards`, with optional **side zones** (`left` and
`right`) flanking the centre `main` zone. Lives in `src/lib/workspace/`.

**Market workspace** — a *separate* engine behind the **Chart Workspace** tab,
based on panels rather than widget cards. Lives in `src/lib/market-workspace/`.
Not the same as the widget workspace. The label was renamed Chart Workspace while
the folder and tab id (`market-workspace`) stayed put.

**Zone** — a canvas column a widget workspace section belongs to: `main`
(centre), `left`, or `right`. All render under one `DndContext`, so cards drag
freely between them. The legacy name for the right zone was **rail**; stored
layouts using `rail` are migrated to `right` on read. A zone can be **removed**
(hidden) from the Customize edit bar — its sections are kept in the layout, so
re-showing restores the exact arrangement.

**Left / right panel** — the narrow side columns of a widget workspace (the
Command Center's Watchlist on the left, Market on the right). Cards drag freely
between the centre and the side panels.

**Rail** — *legacy* name for the workspace's right side zone (the Market panel).
Now just the `right` zone; stored layouts still using `rail` are migrated on read.

**Preset** — a curated starting layout offered to users.

**Persona / template** — a curated starting layout for the Command Center
(Trader, Investor, Macro, Crypto, Forex, Quant), authored as **widget-id specs**
in `src/lib/dashboard/templates.ts` — never registry indices, so adding a widget
cannot silently repoint a template. A template describes only the **centre**;
the side rails are added by `buildMarketViewLayout`.

**Band** — a row-role in the dashboard layout grammar: **hero** (4 at-a-glance
widgets) → **primary** (the one big chart) → **analysis** → **intelligence** →
**context** → **live**. `composeRows` enforces global first-wins dedupe and a
4-column cap, so a widget never renders twice and a section never exceeds four
columns. See `src/lib/dashboard/layout.ts`.

**Placement / two-click contract** — the interaction model for moving widgets:
grab to *preview* a slot, click again to *commit*. Escape or right-click cancels.
See ADR-008.

**Keep-alive tab** — a tab that mounts on first visit and then stays mounted
(hidden with `display:none`) so revisits are instant.

**Frosted glass / glass tiers** — the shared surface styling: `.glass-card`
(default), `.glass-card-strong` (overlays), `.glass-card-subtle` (small tiles),
`.glass-drawer` (real-frost drawers), `.glass-button`.

**Aurora** — the WebGL glow at the top of the viewport that reflects combined
market + news sentiment in green-on-black. The visual USP.

**Backdrop root** — a CSS condition (transform, filter, persisting animation) on
an ancestor that silently breaks `backdrop-filter` on descendants. This is the
reason drawers are portaled to `document.body`.

## Agent & AI

**Agent provider** — the abstraction (`src/lib/agent/types.ts`) behind chat.
Default is a keyword-based **mock provider**; real providers (OpenAI/Anthropic/
Ollama) are pluggable and selected by `getAgentProvider()`.

**Research engine** — the multi-agent pipeline that produces real, sourced
answers instead of canned ones, and persists its work in JDDS
(`ResearchReport` / `AgentRun` / `ResearchFinding`).

**Research memory** — the persisted record of what agents did, so they can cite
past findings, avoid redoing work, and retry failed tool calls.

**Tool call** — one action an agent takes (query data, scrape, search), recorded
with its outcome.

## Trading

**Portfolio engine** — the pure FIFO/LIFO cost-basis + stats logic in
`src/hooks/use-portfolio-engine.ts`, shared by the portfolio screens and the
dashboard portfolio widgets. It is read-only analysis over user-entered
transactions.

**Broker integration** — *not implemented.* There is no paper broker and no
broker adapter in the codebase today. The `trading`-category dashboard widgets
are `UNAVAILABLE` stubs (`UnavailableStub` in `src/lib/dashboard/registry.tsx`).
This is a planned area, not existing functionality.

**Watch** — one alert rule (a condition tree over market data), evaluated by a
server-side poll loop. Fires into `PriceAlertEvent` history, which survives
deleting the watch.

**R-multiple** — profit measured in units of the initial risk. A core journal
metric.

**MFE / MAE** — max favorable / adverse excursion: how far a trade went in your
favor or against you, in R. Used for behavioral analytics, not prediction.

## Process & repo

**ADR** — Architecture Decision Record. A short note on *why* a decision was
made. See [`DECISIONS.md`](./DECISIONS.md).

**Skill** — a persistent instruction file for AI agents. Two sets exist:
`skills/*.md` (the human-readable engineering OS) and `.opencode/skills/*/SKILL.md`
(the same knowledge registered so opencode auto-loads it on matching tasks).

**Guard / `api-guard`** — the module (`src/lib/api-guard.ts`) that decides
whether a mutating request is allowed, plus per-IP rate limiting and the SSRF
allowlist for outbound feed URLs.

**`doctor`** — the boot preflight script (`scripts/doctor.js`) that checks the
environment before `dev`/`up` runs.

**`db-guard`** — the script (`scripts/db-guard.js`) that sets SQLite durability
PRAGMAs and takes rolling backups.

**Seed snapshot** — the committed `jdds.db` that ships real data to fresh clones.
Deliberately updated rarely; never re-committed casually.
