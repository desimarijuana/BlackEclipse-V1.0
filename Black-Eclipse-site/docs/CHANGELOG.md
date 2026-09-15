---
title: Change Log
status: Current
last-verified: 2026-09-15
---

# Change Log

**Who this is for:** anyone who wants to know *what changed, when, and whether
the docs were updated* — without reading git history.

This is a **required** artifact. Every task that changes the repository appends
an entry here, including changes that needed no doc update. It is the record that
proves the documentation obligation was considered rather than skipped.

## Rules

1. **Append, never rewrite.** Add new entries at the top of the log. Do not edit
   or delete past entries — a wrong entry gets a follow-up entry, not a rewrite.
2. **Newest first.** One `##` section per date, entries as bullets beneath it.
3. **Group by date**, not by commit. Multiple changes on the same day share a
   date section.
4. **Link the docs.** Each entry ends with either the doc files it updated or
   `no doc change — <reason>`.
5. **Keep it terse.** One bullet per change: what changed and why it mattered.
   The diff holds the detail; this holds the *narrative*.

## Entry format

```markdown
## YYYY-MM-DD

- **<Area>** — <what changed and why>.
  docs updated: `docs/<file>.md`
- **<Area>** — <what changed and why>.
  no doc change — internal refactor, contracts unchanged.
```

`<Area>` is a short label: `Docs`, `Scraper`, `Workspace`, `Journal`, `Agent`,
`UI`, `DB`, `Alerts`, `API`, `Search`, `Economics`, `News`, `Charts`, `Build`.

---

## 2026-09-15

- **Investor Eye** — New **Investor Eye** world-state surface (Phase 1 + 2): a
  large interactive ECharts world map with a pluggable `MapLayer` system
  (events, markets, conflict, energy, trade, weather, economy, companies,
  portfolio, risk), a timeline (1H–30D), layer controller, country/event
  intelligence panels, "What Changed" summary, and honest data-freshness
  indicators. Backed by a new **additive** event tier `src/lib/investor-eye/`:
  `EventSource` adapters (GDELT DOC 2.0 + USGS, both free/keyless, fetched
  through the existing `connectors/security.safeGet`), pure normalization
  (classification, clustering/dedup, internal data-quality confidence, grid
  aggregation), a real country gazetteer, server SWR cache + persisted
  last-known, an in-process ingestion cron, and 13 `/api/investor-eye/*` routes
  (state, events, countries, markets, layers, economy, companies, portfolio,
  risk, analogues, query, health). Markets reuse the existing `IndexQuote` +
  yfinance path and portfolio exposure reuses `use-portfolio-engine` — no second
  market/portfolio/news stack. Phase 2 analytics are deterministic (risk
  decomposition, exposure, `OBSERVED|HISTORICAL|INFERRED` transmissions,
  historical analogues, keyword+gazetteer NL map search — no LLM on the query
  path). New JDDS models `Country`, `GeopoliticalEvent`, `EventEntity`,
  `SourceRun`; vendored `public/geo/world.geo.json` (Natural Earth, via
  `scripts/fetch-world-geo.mjs`); new `investor-eye` sidebar tab registered in
  sidebar config, search registry, top-bar and the shell. A failed source is
  `UNAVAILABLE`, never a fake zero. 106 new tests.
  docs updated: `docs/investor-eye-architecture.md` (new), `docs/ARCHITECTURE.md`,
  `docs/NAVIGATION.md`, `docs/DATA-FLOW.md`, `docs/DECISIONS.md`,
  `skills/ARCHITECT.md`
- **Build** — `scripts/doctor.js` now detects **schema drift** on an existing
  `jdds.db` and self-heals with `prisma db push`. Previously it only pushed when
  the DB file was *missing*, so an install carrying the old committed seed would
  never receive models added since (the connector + Investor Eye tables) and
  would 500 on every query against a missing table. Expected table names are
  parsed from `schema.prisma`, so the check cannot itself go stale; a locked or
  corrupt DB is left to the existing integrity guard.
  no doc change — self-healing boot fix; no documented contract changed.

- **Screener** — Fixed the broken glyphs on the Market Screener (the `□` boxes
  in the "Global Markets Overview" row and in the table headers). Root cause was
  a pre-existing encoding corruption, not a missing icon: commit `34d76fd`
  (frosted-glass pass) re-encoded `market-overview.tsx` and turned 80 non-ASCII
  characters — em dashes, middots, ellipses, en dashes — into `U+FFFD`
  replacement characters baked into the source. Recovered the original
  characters by matching each damaged line's ASCII skeleton against the last
  clean revision (`c8ec9d3`) and restored them; also fixed one instance in
  `src/app/globals.css`. Verified zero `U+FFFD` remains across all source files.
  no doc change — character-encoding repair, no contract or architecture change.

- **Connectors/UI** — De-duplicated and expanded the provider surface. The AI
  Agent screen previously showed a generic "Provider" **dropdown and** a
  provider **list** — the same choice twice, and the list's "Set up" button
  navigated back to the screen you were already on. It is now a single
  preset-grid picker: click a provider and it fills the base URL + model, leaving
  only the key. Added `src/lib/agent/presets.ts` with **14 working
  OpenAI-compatible presets** (OpenAI, Anthropic, Ollama, LM Studio, Groq,
  DeepSeek, Mistral, Google Gemini, xAI, OpenRouter, Together, Perplexity,
  Fireworks, Custom), and the catalog's AI entries are now **derived from that
  list** so a new preset appears in both places with one edit. Also fixed a real
  bug: `setLLMConfig` rejected any provider without a key, so **keyless local
  servers (Ollama/LM Studio) could not be saved** — it now allows local base URLs
  (`isLocalBaseUrl`) and stubs `"local"` since some clients require a non-empty
  string. Added 12 market/crypto providers (Finnhub, Polygon, Alpha Vantage,
  Twelve Data, Marketstack, CoinGecko, CoinMarketCap, Kraken, …) — **72 providers
  total**, up from 53. Env-var key status is now a single list
  (`CATALOG_ENV_VARS`) shared by `/api/providers` and `/api/settings`, so the two
  cannot disagree. 21 new tests.
  docs updated: `docs/ARCHITECTURE.md`

- **Connectors/UI** — Moved the provider catalog OUT of Data Sources and into
  the settings section that actually configures each provider, so APIs are no
  longer dumped in one place: **AI Agent** shows AI & LLM, **Market Data** shows
  Market Data + Crypto, **Integrations** shows all 44 Economics & Macro sources,
  and **Data Sources** now shows only "Your own data" (the wizard). The new
  `provider-list.tsx` renders a catalog slice in context with a module-level
  fetch cache, so appearing in four sections still costs one request. The
  Integrations section also dropped its hand-written rows (which listed
  `finnhub`/`binance`/`coingecko` — nothing consumes those) in favour of the
  derived list, leaving only AI Model + Database as genuine status rows.
  Long lists (economics) are collapsible with a filter box. 543 tests pass.
  docs updated: `docs/ARCHITECTURE.md`

- **Connectors/UI** — Added a browsable **provider catalog** to Settings → Data
  Sources, grouped by what each provider is for (AI & LLM, Economics & Macro,
  Market Data, Crypto, Your own data) instead of a flat connector list —
  53 providers across 5 collapsible categories with per-category counts.
  `src/lib/connectors/catalog.ts` builds it purely (`buildCatalog(env)`), and
  **Economics entries are derived from `ECON_SOURCES`**, so the catalog cannot
  drift from the fetch layer. Status is honest: `builtin`, `connected`,
  `not_configured`, or `available`, computed from the real environment — of 44
  economics sources only FRED is key-gated, and it shows `needs FRED_API_KEY`
  until set. Buttons never claim to have saved a key: built-ins show a status
  pill, Custom REST opens the wizard, and env-gated providers route to
  Settings → AI Agent / Integrations (via the destination bus, since Settings is
  a modal, not a tab). New `GET /api/providers`. 10 new tests.
  docs updated: `docs/ARCHITECTURE.md`, `docs/NAVIGATION.md`

- **UI** — Navigation icon and label pass. Renamed the **Market Workspace** tab
  to **Chart Workspace** (tab id and `src/lib/market-workspace/` folder unchanged)
  so the label says what the screen is, and gave it the candlestick icon that the
  screener was using. The screener now uses `ScanSearch` (magnifier over scan
  lines) to read as "screen the market" instead of duplicating the chart glyph,
  and Portfolio switched from `Briefcase` to `ChartPie` per request. Applied the
  same choices to every surface that carried a stale icon: sidebar config, the
  search registry (`page-market-workspace`, `page-screener`, `page-portfolio`,
  the screener sub-pages, and the three open actions), the palette's `NAME_ICON`
  map, and both page headers (Chart Workspace had no icon at all; Portfolio and
  Screener used the old glyphs). All `open …` action labels and the page title
  updated too; old labels kept as search aliases so muscle memory still resolves.
  docs updated: `docs/OVERVIEW.md`, `docs/GLOSSARY.md`, `docs/ARCHITECTURE.md`,
  `docs/DECISIONS.md`, `skills/ARCHITECT.md`, `skills/REMEMBER.md`

- **Search** — Tests + docs for sub-page navigation. Added
  `search/subroute.test.ts` (channel semantics: tab scoping, focus pass-through,
  seq re-fire, scoped clear) and registry assertions that sub-pages carry a
  `subroute`, nest under their parent `group`, and that only children are marked
  `child`. Documented the subroute channel and its two invariants in
  `docs/ARCHITECTURE.md`, and the "add a palette sub-page" recipe in
  `docs/NAVIGATION.md`.
  docs updated: `docs/ARCHITECTURE.md`, `docs/NAVIGATION.md`
- **Search** — Sub-page navigation: `Destination.subroute` (previously emitted by
  the registry but ignored by the shell) is now honored. Added a `pendingSubroute`
  channel + `useSubroute(tab, handler)` hook so keep-alive screens react to
  `economics.calendar`, `journal.<tab>`, `discovery.<tab>`, `alerts.<view>`, and
  `settings.<section>`; the shell also routes `tab:'settings'` to the Settings
  modal (it previously switched to a tab that rendered nothing). Registered ~40
  sub-pages in the registry (grouped under their parent, rendered indented in the
  palette's "Go to"), added an Economics "Calendar" section with indicator focus
  highlighting, and removed the superseded `search/settings.ts`. New:
  `src/hooks/use-subroute.ts`, `getPageEntries()`.
  docs updated: `docs/ARCHITECTURE.md`, `docs/NAVIGATION.md`
- **Charts** — Drawing toolbar rendered the same `MousePointer2` glyph for every
  tool, so the Lines/Shapes/Analysis grids were unreadable at a glance. Added a
  `TOOL_ICON` name→lucide map in `chart-widget.tsx` (unknown names fall back to
  the pointer, so a future tool never renders blank) and wired each button to its
  own glyph, with the active tool tinted `primary` for contrast. Also split the
  two colliding registry icons: `ray` now uses `move-diagonal` and `arrow` keeps
  `arrow-up-right`.
  no doc change — UI-only change, drawing contracts and tool registry shape unchanged.

- **Connectors** — Hardening pass on the custom REST connector after review.
  Fixed a silent URL bug: `new URL(path, base)` treats a leading `/` as
  root-relative, so a base like `https://api.example.com/v1` + `/quote`
  produced `…/quote` and **dropped the `/v1` prefix** — a very common API shape
  that would have 404'd with no explanation. Added `joinPaths()`, which joins
  the base pathname explicitly, and preserved any query string the operator put
  on the base URL (a common spot for a query-param key). Added `validateHeaders`
  so CRLF injection / empty header names fail with a clear config error instead
  of Node's opaque `ERR_INVALID_CHAR`. Anchored the connector registry on
  `globalThis` (same reason `lib/db.ts` anchors Prisma) so dev HMR cannot leave
  a second empty registry behind. Verified end-to-end against the live Binance
  API with a `/api/v3` base: multi-symbol pulls, records, and agent reads all
  correct. 9 new tests.
  docs updated: `docs/ARCHITECTURE.md`

- **Connectors** — Completed the connector loop end-to-end. Fixed a dishonest
  count: `ingestRecords` always returned `rejected: 0` even when `mapResponse`
  silently dropped rows, so an import could report success while losing records.
  Mapping now reports `extracted` / `rejectedRequired` / `rejectedIdentity` /
  `deduped` (`mapResponseDetailed` in `mapping.ts`) and every extracted row is
  accounted for. The Data Sources panel gained a **Datasets** browser with
  **Pull** (fetch through the connector and ingest), per-dataset parameter
  inputs, a records table showing provenance, delete-dataset, and a **Sample
  test value** field in the wizard (draft tests previously failed with "Missing
  required parameter" because no value was ever supplied). Pull errors now
  return 400 with the real message for a misconfigured connector instead of an
  opaque 502; connector fetch errors are classified (`invalid_config` /
  `blocked` / `timeout` / `too_large`) rather than all reported as `network`.
  New `DELETE /api/datasets?id=…`. 6 new tests.
  docs updated: `docs/ARCHITECTURE.md`, `docs/DATA-FLOW.md`, `docs/NAVIGATION.md`

- **Agent** — The research agent can now read operator-connected datasets via
  three read-only tools (`src/lib/agent/dataset-tools.ts`): `list_datasets`,
  `describe_dataset`, `query_dataset`. They are spread into `TOOLS`, so the
  existing tool loop picks them up with no loop change; the fundamentals and
  risk agent prompts were updated to use them. Every tool result states
  provenance (`CUSTOM` vs. canonical scraper data) so the LLM never invents a
  source. Added `queryRecords` / `datasetSummaries` / `findDatasetByName` to
  `connectors/store.ts`; filters are exact-match on mapped field names
  (case-insensitive), JS-evaluated because SQLite cannot query inside the JSON
  `values` column. 15 new tests.
  docs updated: `docs/ARCHITECTURE.md`, `docs/NAVIGATION.md`, `docs/DECISIONS.md`

- **Connectors** — Introduced the Universal Data Connector Layer
  (`src/lib/connectors/`): a capability-addressed connector tier that sits
  *after* the existing scraper chain and before route-level demo fallbacks.
  Added hardened outbound security (`security.ts`: canonical IP
  classification, DNS validation + pinned lookup, `redirect: manual`, streamed
  5 MB cap, ≤10s timeout), AES-256-GCM credential encryption (`secrets.ts`,
  local auto-generated key vs. `CONNECTOR_SECRET_KEY` on hosted), a declarative
  `custom-rest.ts` connector (GET + percent-encoded `{{param}}` substitution),
  mapping/`recordPath`/`recordKey` dedup (`mapping.ts`), the crypto fetcher
  migrated as the Phase-2 proof (`providers/crypto.ts`, legacy facade retained),
  and server-side capability resolution (`GET /api/data/[capability]`).
  New JDDS models: `DataConnector`, `CustomDataset`, `CustomDatasetField`,
  `CustomDatasetRecord`, `ConnectorMapping` — custom data never writes to
  `Asset`/`Price`/`Candles`. New routes: `api/data-sources`,
  `api/data-sources/test`, `api/datasets`. DataHub gained an optional
  provenance envelope + `CUSTOM` tag and a `capabilityTopic` helper (no internal
  redesign). New Settings → Data Sources wizard (`data-sources-panel.tsx`).
  Deferred: webhooks, POST bodies, pagination, OAuth, `~` dataset search, agent
  `query_dataset`, AI connector generation.
  docs updated: `docs/ARCHITECTURE.md`, `docs/DECISIONS.md`,
  `docs/DATA-FLOW.md`, `docs/NAVIGATION.md`, `README.md`

- **Search** — The palette is now full navigation, not just search. The bottom
  group is generated from `getAllPages()` so every registered page is reachable
  (adding a `registerPage` entry adds a nav row automatically); it is labeled
  "Go to", collapsible, and part of the keyboard list. Added paging keys
  (PageUp/PageDown/Home/End), a conditional bottom scroll-fade so overflow is
  visible, and a `nameIcon` map for registry string icon names.
  docs updated: `docs/ARCHITECTURE.md`
- **Aurora** — Made the shipped bearish color a proper pure red (`#ff0000` core /
  `#3a0000` edge) instead of the yellowish `#ff3e3e`, so the default Eclipse
  preset's red no longer reads orange.
  no doc change — default color values only; palette model/contract unchanged.
- **Search** — Wired the command palette's cross-tab pivots and parameterized
  commands to real behavior (they were previously cosmetic). `alert SYMBOL` now
  creates a ±3% CHANGE_PCT watch via new `lib/alerts/quick-alert.ts` and opens
  the Alerts tab; `watch SYMBOL` calls new `addToWatchlist` /
  `removeFromWatchlist` / `isInWatchlist` exports in
  `lib/dashboard/watchlist-store.ts`; `chart SYMBOL` opens the chart. The
  misleading `compare` verb was removed, registry actions gained `requiresArg`
  so they never render as bare commands, failures surface an inline error
  instead of a fake recent, and the keep-alive Alerts screen re-lists on a
  `be:alerts-changed` event. `MarketNews` gained a `symbol` prop (seeds the
  `ticker:` operator); `MarketOverviewScreen` gained `initialSymbol`; the
  destination bus in `stock-chat.tsx` now routes `tab:news`/`tab:discovery`
  symbols.
  docs updated: `docs/ARCHITECTURE.md`, `docs/NAVIGATION.md`
- **Docs** — Documentation/skills audit before sharing with an external tool.
  The `docs/` set was already current; the agent *skills* had drifted badly and
  were corrected against code: `skills/ARCHITECT.md` §2–4 described a pre-JDDS app
  ("no database", "only `/api/news`", 6 tabs, SQLite listed as PLANNED) — rewritten
  to the JDDS/scheduler/agent reality; `skills/REMEMBER.md` (DB, tabs, agent,
  retired `src/lib/customize/`) and `skills/GOALS.md` (agentic research now
  active, not deferred) updated; `skills/README.md` skill list fixed (6 → 8);
  `CONTRIBUTING.md` "no database/demo data" claim corrected.
  docs updated: `docs/DECISIONS.md` (mirror), `docs/CHANGELOG.md`
- **Search** — Completed the command-center improvement phases. Phase 4:
  deterministic synonym/acronym expansion (`expandTerms`), visit-history
  personalized ranking, and cross-tab `related` pivots for a resolved
  instrument. Phase 5: offline in-palette calculator + indicative currency
  conversion (`calc.ts`) and parameterized commands with argument autocomplete
  (`commands.ts`). Phase 6: ARIA combobox/listbox semantics with a polite live
  region, memoized rows, and a mobile-sized palette. New store state: `visits`.
  docs updated: `docs/ARCHITECTURE.md`, `docs/NAVIGATION.md`
- **Search** — Result UX pass on the command palette: groups now show per-kind
  counts and collapse on click, results can be pinned (persisted to
  `localStorage` and replayed from a serialized destination) or have their symbol
  copied, the footer shows "N of M results", and a zero-hit query offers a
  "did you mean" correction from the static registry (`suggestCorrection`).
  `ResolvedSearch` gained `total` + `suggestion`.
  docs updated: `docs/ARCHITECTURE.md`
- **Search** — Added a query grammar to the command center: scoped prefixes
  (`>` commands, `#` instruments, `@` indicators, `/` pages, `~` your data, `?`
  syntax help) and field operators (`kind:`, `class:`, `market:`, `symbol:`).
  `resolver.ts` now parses scope/filters before resolving, and the palette shows
  a scope chip, a syntax help card, a clear button, and scope-aware empty states.
  The header trigger gained a contextual per-tab placeholder, a platform-aware
  ⌘/Ctrl shortcut label, and a live index count.
  docs updated: `docs/ARCHITECTURE.md`, `docs/NAVIGATION.md`

- **Market Workspace** — Interactive drag placement now keeps a panel where it was
  dropped: added `placePanel` (absolute placement, pushes displaced panels down),
  `clampPanels` (bounds-only, row-preserving) and `packPanels` (full repack for
  templates/repair); `normalizePanels` is deprecated as an alias. Added
  `recomputeRows` so the grid ends at its content height instead of scrolling
  into empty space. New charts seed from the layout's lead instrument instead of
  hard-coded AAPL, and panels gained a `chrome: 'minimal'` full-page mode.
  Duplicate/remove moved into the panel menu (copy/trash icons).
  no doc change — no documented shape changed; `/lib/market-workspace/` is
  already mapped in `docs/NAVIGATION.md`.
- **Command Center** — New layouts can start from a persona preset:
  `MarketView` gained `templateId` (threaded `market-views.tsx` →
  `dashboard-screen.tsx`), and the new-layout flow was extracted into
  `new-layout-dialog.tsx`.
  no doc change — additive field; dashboard/workspace contract unchanged.
- **UI** — Added a `variant` prop to the shared `TabBar` (`glass` default,
  `subtle` for the new `.tab-bar-subtle` control-strip tier), applied to the
  Command Center market tabs.
  docs updated: `docs/ARCHITECTURE.md`, `.opencode/skills/black-eclipse-ui/SKILL.md`
- **Heatmap** — Tile sizes are compressed before grouping (sqrt for crypto,
  ^0.75 for equities) so a mega-cap no longer flattens the board; added
  `rawMarketCap` so tooltips and sector totals keep showing the true figure.
  no doc change — additive field on an internal heatmap shape.
- **Aurora** — `normalizePalette` now validates every color is real hex (guards
  the shader against malformed values); `setPalette` normalizes + clones so
  applying a preset never stores a shared module reference. Presets refactored
  through a compact `preset()` helper, swatches render a bearish→bullish ramp,
  and `theme.test.ts` covers every preset.
  no doc change — internal hardening, contract unchanged.
- **Docs** — Made the documentation obligation enforceable: every change must now
  append a `docs/CHANGELOG.md` entry (including changes needing no doc update),
  and an always-on rule was added in `AGENTS.md` so it applies to every session
  rather than only doc-keyed tasks.
  docs updated: `docs/CHANGELOG.md`, `docs/README.md`, `skills/DOCS.md`,
  `skills/REVIEW.md`, `.opencode/skills/black-eclipse-docs/SKILL.md`, `AGENTS.md`
- **Docs** — Established the documentation system: a flat canonical doc set in
  `docs/` plus an always-on obligation in `AGENTS.md`, the `black-eclipse-docs`
  skill, `skills/DOCS.md`, and the Documentation Review section in
  `skills/REVIEW.md`. Added a maintained change log (this file).
  docs updated: `docs/README.md`, `docs/OVERVIEW.md`, `docs/QUICKSTART.md`,
  `docs/ARCHITECTURE.md`, `docs/DATA-FLOW.md`, `docs/NAVIGATION.md`,
  `docs/DECISIONS.md`, `docs/GLOSSARY.md`, `docs/CHANGELOG.md`
- **Docs** — Corrected a pre-existing drift: `black-eclipse-workspace` skill and
  the new docs described a paper broker (`dashboard/paper-broker.ts`,
  `trading-widgets.tsx`, `broker/types.ts`) that does not exist. Trading widgets
  are `UNAVAILABLE` stubs in `src/lib/dashboard/registry.tsx`.
  docs updated: `docs/ARCHITECTURE.md`, `docs/OVERVIEW.md`, `docs/GLOSSARY.md`,
  `.opencode/skills/black-eclipse-workspace/SKILL.md`
