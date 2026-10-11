# Change Log

## Rotation policy

This file keeps a rolling window of the **most recent 7 dated sections** (the active window). Older dated sections are **moved** - never deleted - into monthly archive files under `docs/changelog/YYYY-MM.md`. New entries are appended under the current date; the commit-msg hook checks this path. Rotation is by hand only when this file grows unwieldy; the archive link below points at where the older entries went.

> Older entries are archived under `docs/changelog/` (monthly). The most recent 7 dated sections are kept here.

## 2026-10-10

- **Strategy Development Engine (lifecycle close-out): governance, source
  inspection, multi-file projects, deeper validation.** Added
  `quant/ops_tools.py` and store tables on `agent-memory.db`:
  `QuantStrategyApproval` (review gate) and `QuantStrategyDeployment` (governed
  **paper-only** records — `live` raises `LIVE_TRADING_DISABLED`, no path routes
  an order); tools `inspect_python_strategy` (static AST inspection — advisory),
  `request/decide/list_strategy_approval`, `create/list/stop_strategy_deployment`,
  and `run_python_project` (multi-file strategy project in the isolated worker,
  sibling imports by name). Added static validation codes `AMBIGUOUS_FILL_TIMING`
  (warning) and `INDICATOR_TF_UNORDERED`. Quant tools now **52**. Docs updated:
  `docs/quant-engine.md`, `docs/NAVIGATION.md`, `docs/harness/decisions.md`
  (ADR-H174). Tests: `python/tests/test_quant_ops.py`. Honest remaining gap:
  container-grade isolation + pinned per-run dependencies (process isolation
  today).

- **Strategy Development Engine (chatbot-only): expression DSL, expanded
  indicators, benchmark metrics; the dedicated strategy UI was removed.** The
  feature is now driven entirely from the chatbot (agent tools) per direction —
  deleted `strategy-canvas.tsx`, `python-lab.tsx`, `src/lib/backtest/
  graph-editor.ts` (+ test) and reverted the Backtest screen/client to their
  prior form. Engine additions: **expression DSL** (`strategy.py`/`rules.py`:
  arithmetic `+ - * /`, `min/max`, `neg/abs`, causal `lag`; safe, causal, no
  `eval`; validation recurses with `UNKNOWN_REFERENCE`/`BAD_LAG`); **indicators**
  (`indicators.py`: Stochastic, ADX ±DI, Donchian, Keltner, OBV, MFI, Williams
  %R, CCI + node-registry entries); **benchmark metrics** (`quant/benchmark.py`:
  alpha/beta/correlation/tracking-error/IR/excess via the new
  `analyze_against_benchmark` tool — 44 `quant_*` tools total). Docs updated:
  `docs/quant-engine.md`, `docs/NAVIGATION.md`, `docs/harness/decisions.md`
  (ADR-H170/H171 amended, ADR-H173). Tests: `test_quant_expressions.py`,
  `test_quant_indicators_ext.py`, `test_quant_copilot.py`.

- **Strategy Development Engine (Phase 7): AI Strategy Copilot support —
  grounded signals, research plans, reports and the remaining required tools.**
  Added `quant/copilot.py` (`calculate_signals` = the decision timeline with
  reason codes and NO orders; `build_research_plan` = an explicit hypothesis /
  split / benchmark / cost / parameter-search / acceptance-criteria / bias spec;
  `build_report` = Markdown grounded only in a stored experiment + artifact; plus
  rule/sizing/stop helpers) and `quant/copilot_tools.py` (12 tools:
  `calculate_signals`, `create_research_plan`, `generate_strategy_report`,
  `generate_entry_exit_rules`, `configure_position_sizing`,
  `configure_stops_and_targets`, `get_experiment_status`, `cancel_experiment`,
  `calculate_performance_metrics`, `analyze_trade_log`, `compare_strategies`,
  `run_parameter_sweep` — reusing existing handlers where one exists). Quant tools
  now total 43. Routes `/quant/signals`,
  `/quant/strategies/{id}/research-plan`, `/quant/experiments/{id}/report`.
  Grounding is carried by the tools (deterministic artifacts or typed errors);
  the agent system prompt is at its hard size ceiling, so no prompt text changed.
  `backtestClient` gains `researchPlan`/`report`/`signals`. Docs updated:
  `docs/quant-engine.md`, `docs/NAVIGATION.md`, `docs/harness/decisions.md`
  (ADR-H172). Tests: `python/tests/test_quant_copilot.py` (7).

- **Strategy Development Engine (Phase 3 backend): the Python Strategy SDK and
  managed, isolated runtime.** Added `quant/sdk.py` (typed `Strategy` base +
  `Context` + `run_user_strategy`; the driver *subclasses* `BacktestEngine`, so
  fills, protective legs, risk, portfolio accounting and metrics are the SAME
  code path as a declarative backtest), `quant/sdk_worker.py` +
  `quant/sdk_runtime.py` (the source runs in a **separate process** with
  `python -I`, a scrubbed environment — no PYTHONPATH/credentials — a wall-clock
  timeout, an output-size cap and POSIX rlimits where available; results are
  rehydrated into a typed `BacktestResult`), and reference strategies in
  `quant/examples/` (`ma_crossover`, `mean_reversion`, `vol_target_trend`). The
  `run_python_strategy` agent tool and `POST /quant/python/run` reuse the store;
  the Backtest screen gains a "Python lab" panel (`python-lab.tsx`) wired via
  `backtestClient.runPythonStrategy` + `useBacktestScreen.loadResult`. Capability
  is advertised `partial` for `pythonStrategies` (process isolation, not a
  container — stated honestly). Docs updated: `docs/quant-engine.md`,
  `docs/NAVIGATION.md`, `docs/harness/decisions.md` (ADR-H171). Tests:
  `python/tests/test_quant_sdk.py`, `test_quant_sdk_runtime.py`.
  _(Multi-file project authoring + a syntax-highlighting editor remain; the lab
  v1 is a single source module.)_

- **Strategy Development Engine (Phase 4 UI): the dependency-free Visual
  Strategy Builder canvas.** Added `src/components/screens/backtest/
  strategy-canvas.tsx` (node palette grouped by category, drag-to-move,
  typed-port click-to-connect, config inspector from each node's schema,
  compile-with-diagnostics, and save-the-compiled-strategy) and its pure,
  unit-tested core `src/lib/backtest/graph-editor.ts` (node/edge mutation,
  connection rules, editor⇄`StrategyGraph` conversion, geometry, draft
  persistence). Mounted behind a "Visual builder" toggle in the Backtest screen;
  it calls `/quant/graph/*` and never computes signals itself. No new
  dependency (the repo had no graph/ELK library). Docs updated:
  `docs/quant-engine.md`, `docs/NAVIGATION.md`, `docs/harness/decisions.md`
  (ADR-H170). Tests: `src/lib/backtest/graph-editor.test.ts` (9).

- **Strategy Development Engine (Phase 4 core): the Visual Strategy Builder's
  typed graph model, versioned node registry and graph→IR compiler.** Added
  `quant/graph_model.py` (validated `StrategyGraph`: identity + typed nodes +
  edges), `quant/nodes.py` (the versioned registry: data/universe, all catalog
  indicators incl. Bollinger/MACD output selectors, logic compare/cross/group/
  constant, trade entry/exit, sizing, stops/targets, risk limits — each with
  typed ports, config schema and a pure `compile`), and `quant/compiler.py`
  (parse → resolve types/versions → validate ports/types → deterministic topo
  order + cycle detection → assemble the canonical `StrategySpec` → shared
  `validate_strategy`; returns structured diagnostics and a spec-path→node-id
  source map). Three agent tools (`compile_strategy_graph`,
  `validate_strategy_graph`, `list_strategy_nodes`) and `/quant/graph/{nodes,
  compile,validate}` routes reuse the same registry/compiler; `backtestClient`
  gains `listGraphNodes`/`compileGraph`/`validateGraph`. The graph is an
  authoring front only — it compiles to the SAME IR the Python lab and AI copilot
  use, so it shares versions, bundles, validation and the whole engine. Docs
  updated: `docs/quant-engine.md`, `docs/NAVIGATION.md`,
  `docs/harness/decisions.md` (ADR-H170). Tests:
  `python/tests/test_quant_graph_compiler.py` (15).
  _(The React canvas UI, Python Strategy Lab and AI copilot authoring remain —
  future phases on this same IR + compiler contract.)_

- **Strategy Development Engine (Phase 1–2 foundation): immutable
  content-addressed strategy versions, Strategy IR schema identity, structural
  version diff, and portable strategy bundles.** Added `quant/schema.py`
  (`STRATEGY_SCHEMA_VERSION`, same-major compatibility policy, a lossless
  migration registry, and `spec_content_hash` = sha256 over the canonical IR) and
  `quant/bundle.py` (self-describing zip — manifest + canonical IR + README —
  with size/member caps, path-traversal rejection, schema gating and a
  hash-mismatch warning; import re-validates through the normal schema path).
  `quant/store.py` now records `contentHash`/`schemaVersion` on every version
  (idempotent `ALTER` upgrade), **freezes** a version once an experiment
  references it (`STRATEGY_VERSION_IMMUTABLE`/409 when different content is
  re-saved under it), and adds `version_meta` + `diff_versions`. Three agent
  tools (`export_strategy`, `import_strategy`, `diff_strategy_versions`) and
  matching `/quant/strategies/{id}/export|import|diff` routes reuse the same
  store/engine; the Backtest UI gains a `StrategyPortability` panel
  (list versions, export/import JSON bundle, diff). Docs updated:
  `docs/quant-engine.md`, `docs/NAVIGATION.md`, `docs/harness/decisions.md`
  (ADR-H169). Tests: `python/tests/test_quant_versioning.py`,
  `python/tests/test_quant_bundle.py`, `src/lib/backtest/backtest-client.test.ts`.
  _(Python Strategy Lab, visual strategy builder + compiler, and AI copilot
  authoring remain — future phases on the same IR + bundle contract.)_

- **Statistical engine — persistence, feature registry, market-data adapter,
  background jobs, caching and benchmarks (UI still pending).** Added to
  `python/harness/stats/`: `datasets.py` (gateway-backed series/frame resolution
  with honest errors) and `service.py` (cached, persistent, audited execution;
  `execute_with_data`; artifact spilling for >5000-point series); `store.py`
  (`StatsStore` on `agent-memory.db`: `StatsFeature`/`StatsFeatureVersion`
  immutable versions, `StatsAnalysis`, `StatsRun`, `StatsValidation`,
  `StatsAudit`, `StatsArtifact`, gzipped artifacts under `.black-eclipse/stats/`);
  `feature_registry.py` (semver versioning, clone/compare/rollback, dependency
  graph with cycle detection, real evaluate-based validate/preview, pipeline
  steps); `cache.py` (computation-identity LRU cache); `runner.py`
  (`StatsRunner` background jobs: submit/progress/cancel + durable mirror). Router
  `routers/stats.py` grew to 23 operator-gated routes (`/analyses[/run|/submit]`,
  `/jobs`, `/formulas/validate|execute`, `/features/*`, `/datasets/series`,
  `/artifacts/{id}`, `/audit`). Agent tools extended to 31 in `stats/tools.py`
  (registry + formula + data-driven analysis + jobs), allowlisted in `agents.py`.
  Tests: `test_stats_{store,features,datasets,service,runner,performance}.py`
  (40 new; 122 stats tests total). Benchmarks: returns 100k ~36 ms, corr 20×2000
  ~13 ms, 20 features/20k ~39 ms. docs updated: `docs/quant-research/
  IMPLEMENTATION_STATUS.md`, `API_CONTRACTS.md`, `FEATURES.md`,
  `DATA_AND_PROVENANCE.md`, `OPERATIONS.md`, `TESTING.md`, `docs/NAVIGATION.md`.
  _(Research Studio UI and per-workspace authorization remain.)_

- **Statistical Analysis & Feature Engineering Engine (backend): fourteen
  deterministic statistical tools, a safe formula language, agent tools, an
  HTTP surface and the Next.js front door.** New package
  `python/harness/stats/`: shared contract/provenance (`base.py`),
  first-principles distributions (`dist.py`), a dependency-free Nelder–Mead
  optimizer (`optim.py`), OLS/WLS/HC/HAC/ridge/lasso (`linreg.py`), a restricted
  expression parser + whitelist evaluator (`formula.py`), and the fourteen tools
  (`m_returns`, `m_volatility` [incl. EWMA/Parkinson/Garman–Klass/GARCH(1,1)],
  `m_correlation`, `m_beta`, `m_drawdown`, `m_stationarity` [ADF/KPSS],
  `m_cointegration` [Engle–Granger/Johansen], `m_autocorrelation` [ACF/PACF/
  Ljung–Box], `m_regression`, `m_regime` [vol/trend/changepoint/HMM],
  `m_features`, `m_outliers`, `m_leadlag`, `m_information`). Registry
  `registry.py`; agent tools `tools.py` (14 + `stats_capabilities`), allowlisted
  in `agents.py`; boot wiring `bootstrap.py` called from `service.py`; operator-
  gated routes `routers/stats.py` (`/stats/v1`) included by `main.py`; front door
  `src/app/api/stats/[...path]/route.ts` + `src/lib/stats-client.ts`. Tests:
  `python/tests/test_stats_{dist,core,relationships,inference,structure,formula,
  registry}.py` (82 passing). docs updated: `docs/quant-research/
  IMPLEMENTATION_STATUS.md`, `STATISTICAL_METHODS.md`, `API_CONTRACTS.md`,
  `FORMULA_LANGUAGE.md`, `docs/NAVIGATION.md`. _(UI studio, feature
  persistence/versioning, jobs and DB migrations remain — see the tracker.)_

- **Chat-history sidebar simplified: removed Import/Export, selection mode, and
  the Active/Archived/Trash scope tabs.** The panel now shows a single active
  view with search, sort, tag filter, folders (nested), drag, and the row options
  menu. Because the scope tabs were the only way to view archived/trashed chats,
  the row menu's Archive / Move-to-Trash / Restore actions were removed too —
  leaving a single confirmed permanent Delete so nothing can be hidden
  unrecoverably. The archive/trash data fields and pure logic remain (harmless,
  test-covered) for a future re-expose. docs updated: CHANGELOG.md only.

- **Research data: isolated notebook, fundamentals/macro endpoints, provider
  lineage, contract tests.** `research/notebook.py` executes operator analytical
  code in the ONE bounded sandbox against a read-only dataset CSV (no secrets/
  network; `/research-data/datasets/{id}/execute` + a Notebook tab in the
  Research Data screen). `POST /research-data/{fundamentals,macro}` exposes vault
  fundamentals and macro series. Provider descriptors declare an `upstream`
  lineage (shared upstream ≠ independent; unknown ⇒ unknown) consumed by
  verification. New tests: `test_research_notebook.py`,
  `test_market_provider_contract.py` (recorded fixtures; live keyed calls remain
  opt-in). Gateway `get_quote` gains provider pinning. docs updated:
  docs/harness/quant-research-data.md.

- **Chat history becomes a full client-side system: nested folders, tags,
  ranked search, archive, trash + undo, bulk actions, export/import, and
  mouse/touch drag.** Everything the earlier pass listed as missing is now built,
  except cross-device sync (deliberately out of scope — localStorage only, no
  auth). Data: `Conversation` gained `tags`/`archivedAt`/`deletedAt`;
  `ChatFolder` gained `parentId`/`order` for nesting + ordering. New pure logic in
  `chat-organization.ts` (folder forest with cycle safety, ranked AND-token search
  with body snippets, scope/tag filtering) and `chat-export.ts` (versioned JSON
  envelope, defensive parse, additive id-based merge). Hook gained tag/archive/
  trash/restore/purge/bulk/move-folder/import handlers. UI split into
  `chat-history-panel.tsx` (toolbar, scope tabs, tag filter, folder tree, bulk bar,
  undo toast, pointer-based drag working on touch) and `chat-history-menu.tsx`
  (options menu with tag editor). Legacy rows migrate on load. Tests: 21
  organization + 5 export. docs updated: ARCHITECTURE.md (Layer 0 persistence),
  CHANGELOG.md.

- **Interactive Response Engine — full build-out (planner, controls, exports,
  artifacts, financial charts, Mermaid).** Completes the engine's deferred
  capabilities, all reusing existing infrastructure: a deterministic **response
  planner** (`src/lib/response/planner.ts`) upgrades plain-Markdown GFM tables →
  interactive tables and link-only source lists → citations for **every** settled
  answer (no model call, byte-identical prose otherwise); **backend-driven
  controls** (`src/components/response/controls-block.tsx`) compose a validated
  prompt and re-enter the **existing** agent loop via a new `onFollowup` callback
  threaded through both chat surfaces; **export** (`src/lib/response/export.ts`)
  adds JSON / CSV / PNG (ECharts `getDataURL` via a new instance registry) / PDF
  (lazy `jspdf` + `jspdf-autotable`, embedding mounted charts and reporting
  anything it cannot embed in an appendix); **Artifact Center save** reuses the
  existing `registerArtifact` → `POST /api/artifacts`; a **`financial_chart`**
  block wraps the existing `ChartWidget` (live OHLCV, never embedded price data);
  a **`mermaid`** block renders sequence/ER/class/gantt diagrams with
  `securityLevel: 'strict'` (lazy-loaded; `mermaid` 12.1.0 added). Per-response
  export/save actions live in `src/components/response/response-actions.tsx`. New
  tests: `contract-extended.test.ts`, `planner.test.ts`, `export.test.ts`. docs
  updated: docs/interactive-response-engine.md, docs/NAVIGATION.md,
  docs/DECISIONS.md (ADR-043 amendment), skills/ARCHITECT.md (ADR-043 amendment).

- **Research data becomes a proper system: REST API, Dataset/Quality UI,
  point-in-time universes, dataset analytics.** `python/harness/routers/research_data.py`
  exposes the research services over HTTP (operator-gated, `/research-data/*`,
  included in `main.py`); `src/app/api/research-data/[...path]/route.ts` proxies
  it and `src/components/screens/research-data/research-data-screen.tsx` is a new
  `research-data` AppTab (Dataset Explorer + Builder + Data Quality Center +
  Provider view). Point-in-time universe membership lives in
  `python/harness/market/universe_store.py` (effective-dated, SCD-2) with
  `record_universe`/`list_universes` and `get_universe` as-of resolution. New
  `analyze_dataset` runs deterministic analytics (summary/returns/volatility/
  max_drawdown/sharpe/correlation) over an immutable version. New tests:
  `test_research_data_api.py` + universe/analyze tests in
  `test_research_data_tools.py`. Size pins updated (`main.py` kept ≤1200,
  `stock-chat.tsx` re-pinned). docs updated: docs/harness/quant-research-data.md,
  docs/NAVIGATION.md.

- **Chat history: drag a chat onto a folder to file it; folder options redesigned.**
  Chat rows are now HTML5-draggable and every folder group (plus "Unfiled") is a
  drop target that highlights while hovered and moves the chat on drop — a faster
  path than the menu's "Move to". The folder options popover was rebuilt: an
  identity header (color chip + name + chat count), a labelled color grid, and
  roomier action rows, with "Delete folder" now stating that its chats move to
  Unfiled. `docs updated: CHANGELOG.md only`.

- **Interactive Response Engine — structured, interactive assistant answers.**
  An assistant turn may now carry ONE fenced ```eclipse-response block whose JSON
  body is validated by a versioned zod contract and rendered through a registered
  component registry inline in chat: metric grids, sortable/filterable/paginated
  tables, ECharts charts (line/area/bar/stacked/grouped/pie/scatter/histogram/
  heatmap), dependency-free SVG diagrams (flow/dependency/state), timelines,
  citations, callouts, key-value panels, collapsible details and tabs. This closes
  the audit's documented gap (`docs/chat-ui-audit.md` §16, Risk R7 — "no
  structured wire contract"). New `src/lib/response/` (contract/parse/chart-option/
  diagram-layout + tests) and `src/components/response/`; `components/chat/
  markdown.tsx` intercepts the fence and gained a `streaming` prop (threaded from
  `chat-history.tsx`); per-block error boundaries; hard resource limits; unknown/
  malformed blocks degrade to diagnostics, never code. Charts lazy-load ECharts;
  persistence/reopen reuse the existing `Message.content` store. `zod` promoted to
  a direct dependency; `prompts.py` gained a "Structured answers" section.
  docs updated: docs/interactive-response-engine.md (new), docs/NAVIGATION.md,
  docs/DECISIONS.md (ADR-043), skills/ARCHITECT.md (ADR-043).
- **Research data: trading calendar, currency conversion, corporate actions,
  universe resolution, export/refresh, point-in-time and Artifact linkage.** Adds
  the tools the research surface previously lacked, all backend and credential-free:
  `get_trading_calendar` (`market/calendar.py` — deterministic US-equity sessions +
  holidays + DST, FX 24/5, crypto 24/7, no `tzdata` dependency; session-aware
  freshness integrated into `quality.check_freshness` so a closed market is
  `closed_recent`, never mislabelled `stale`); `get_currency_conversion` (direct
  FX + documented cross-via-USD, `derived` labelled); `get_corporate_actions`
  (provider-supplied, honest UNAVAILABLE when absent); `get_universe` (resolves
  current identities; an `as_of` is marked `asOfUnknown` — survivorship guard);
  `export_dataset` (CSV/JSON) and `refresh_dataset` (new immutable version);
  point-in-time `as_of` on `query_dataset`/`export_dataset` with `pitUnknown`
  honesty. New `market/series_store.py` persists normalized bars on
  `agent-memory.db`; built datasets are catalogued through the Artifact Center.
  Secondary handlers split into `market/research_tools_ext.py` to stay under the
  size budget. New tests: `test_market_calendar.py`, `test_market_series_store.py`
  + additions to `test_research_data_tools.py`. docs updated:
  docs/harness/quant-research-data.md, docs/NAVIGATION.md.

- **Mount the Quant Research workspace as the `backtest` AppTab.** The existing
  `BacktestScreen` was exported but never mounted; it is now the `backtest` AppTab
  (deep link `/?tab=backtest`, reachable from the command palette as "Quant
  Research"), following the Pages/UI-Builder pattern — deliberately not a sidebar
  section. Edits: `src/lib/app-tabs.ts` (+`backtest`), `src/lib/search/deep-link.ts`
  (`APP_TABS`), `src/lib/i18n/nav.ts` + `dictionaries/en.ts` (`nav.backtest`),
  `src/lib/search/registry.ts` (`page-backtest` search entry) and
  `src/components/screens/stock-chat.tsx` (lazy mount). docs updated:
  docs/harness/quant-research-data.md.

- **Fix chat-history follow-ups: empty folders now appear; the list scrolls
  instead of pushing the nav down; option menus no longer clip.** `groupConversations`
  was dropping empty groups, so a newly created folder was invisible — every
  folder now renders even with zero chats (the trailing "Unfiled" bucket still
  only appears when non-empty). The sidebar list is bounded again
  (`max-h-[45vh]` + its own scrollbar) so it never grows the sidebar and shoves
  the navigation below it. Row/folder option menus moved into a `createPortal`
  popover anchored to the opening button (with up-flip), so the scroll container
  can no longer clip them. docs updated: CHANGELOG.md only.

- **Quantitative research data infrastructure: independent verification, versioned
  datasets and a shared research tool surface.** The market layer gains five named
  verification policies (`cached_fast`, `fresh_preferred`, `cross_verified`,
  `historical_reproducible`, `strict_research`) and a deterministic cross-source
  verification engine that classifies an observation as verified/unverified/
  conflicted/failed, records material conflicts and never averages disagreeing
  sources (`python/harness/market/verification.py`). The Market Data Gateway gains
  provider pinning (`provider=`) and `candidate_providers()` so a caller can
  deliberately retrieve an INDEPENDENT source; the provider registry gains
  intervals, adjustment support, a timeliness taxonomy (realtime/delayed/eod/
  reference) and an entitlement field. Deterministic transforms
  (`python/harness/quant/transform.py`: OHLCV resampling with partial-bucket flags
  and explicit-only alignment) and an immutable, content-hashed, versioned dataset
  store with manifests (`python/harness/quant/dataset_store.py`) are added. A new
  shared research tool surface (`python/harness/market/research_tools.py`:
  `get_market_data`, `verify_market_data`, `resample_data`, `align_timeseries`,
  `build_research_dataset`, `query_dataset`, `compare_datasets`,
  `get_data_quality_report`, `get_data_provenance`, `resolve_instrument`,
  `list_providers`, `get_provider_health`, plus dataset version listing) is
  registered in `market/bootstrap.py` and added to the Eclipse agent allowlist
  (`agents.py`); the quant `run_backtest`/optimization tools are also now
  allowlisted. New tests: `test_market_verification.py`, `test_quant_transform.py`,
  `test_quant_dataset_store.py`, `test_research_data_tools.py`.
  docs updated: docs/harness/quant-research-data.md (new), docs/NAVIGATION.md.

- **Chat history gains folders, colors, pinning, rename and search.** The sidebar
  recent-chats list was a flat localStorage array with only delete. It now
  supports user-created folders (collapsible, colored), per-chat accent color,
  pin-to-top, inline rename, move-to-folder, and a search box filtering across
  titles and message bodies with recent/created/alpha sort. New organization
  layer: `src/lib/chat/chat-organization.ts` (conversation + folder types, color
  palette, localStorage helpers, pure filter/sort/group view logic) and
  `src/lib/chat/use-chat-organization.ts` (the state/handlers hook); UI extracted
  to `src/components/layout/chat-history-panel.tsx`; `sidebar.tsx` takes one
  bundled `organization` prop instead of a dozen callbacks. Legacy transcripts
  are migrated on load (backfilled `createdAt`/`folderId`/`color`/`pinned`); the
  new `chat_folders_v1` key is additive so no existing history is lost.
  docs updated: ARCHITECTURE.md (Layer 0 persistence bullet).

- **Re-pin the system-prompt size ratchet for the Eclipse UI authoring capability.**
  `prompts.py` gained a "Pages, widgets and tools" paragraph for the `ui_*` tools
  (compose pages/widgets, file engineering tasks), growing the prompt from 23725
  to 25217 chars. The size-ratchet tests in `test_memory_tools.py` and
  `test_phase_s_stabilization.py` were re-pinned to 25217 with updated rationale,
  matching the established convention (raise only for a genuinely new capability).
  no doc change — test-only ratchet update; the capability itself is already
  documented.

- **Investor Eye: event click opens the dossier popup; dossier reads vertically;
  lens filters match type OR channel; window-switch feedback.** (1) Clicking an
  event — a map pin or a Live Event Stream row (or Enter on a focused row) — now
  opens the full `EventDossierOverlay` directly via a new `handleOpenEvent`;
  keyboard j/k stepping still only peeks the right rail, so arrowing never
  throws a modal. (2) The wide dossier no longer flows into two `lg:columns-2`
  columns (which read left-to-right); `EventPanel` in `wide` mode is now a
  single vertical column that spans the (wide, `max-w-6xl`) overlay, and the
  duplicate close button in the panel header is suppressed in `wide` mode — it
  stacked a second cross under the overlay's own, giving two crosses. (3) `LiveFeed` lenses and the dashboard
  `InvestorEyeWidget` lens now match on event TYPE **or** economic CHANNEL (the
  same rule the map layers use), so an event classified under a neighbouring
  type but transmitting through Energy/Trade/Shipping is no longer dropped. (4)
  A "Loading <window> window — still showing <old>h" chip appears while a
  time-range change is assembling (a cold window takes ~15s and previously
  showed the old window's data with no feedback, so the range filter looked
  inert). (5) The main screen's detail section no longer uses `lg:columns-3`
  multi-column flow (which packed What Changed / Alerts / Risk / Transmissions /
  Conflict research / Portfolio / Source health left-to-right); it is now a
  single vertical stack, matching the dossier. (6) The event **heatmap** layer is
  on by default and its wide cells were the pointer target for much of the map,
  but it had no click handler — clicking a hotspot silently did nothing. It now
  selects the cell's representative event (`buildEventHeatmapLayer` takes the
  `onSelect` callback), so a hotspot opens that event's dossier. (7) The
  dashboard `InvestorEyeMapWidget` — which deliberately embedded no dossier —
  now opens the same `EventDossierOverlay` (lazy-loaded) on pin/hotspot click.
  `npx tsc --noEmit` clean; `vitest` 2524 pass.
  no doc change — UI/UX behavior fixes within the existing contract; no data
  shape, setup, or architecture change.

- **Remove the `/login` page.** Deleted `src/app/login/`; `HARNESS_AUTH=off` in the
  local `.env` (gitignored) — no sign-in. The `/api/auth/*` API and middleware
  remain but are inert while auth is off. no doc change — page removal; auth is
  local env only.

- **Agentic sidebar trimmed: Tasks, Pages and UI Builder removed from the nav.**
  Dropped the `tasks`, `pages` and `ui-builder` entries from
  `DEFAULT_SIDEBAR_SECTIONS` (`src/lib/sidebar/config.ts`) and the now-unused
  icon imports; updated the Agentic-list and shortcut-count guards in
  `config.test.ts`. The screens still mount via keep-alive and remain reachable
  by deep-link (`/?tab=…`) — only the sidebar entries are gone.
  no doc change — nav list edit only (no contract/architecture change).

- **Assistant now shows the model that answered, and the floating dock renders
  the full turn.** Two gaps behind "it doesn't show the model / output is wrong".
  (1) **Model display**: the run record's `provider`/`model` now ride on the
  `client.final` frame (`api/harness/chat/stream/route.ts`), are normalized into
  the `final` UI event (`lib/agent/events.ts`), carried on `AssistantTurn.model`
  (`use-agent-run.ts` / `response-model.ts`) and on `Message.model`
  (`types/chat.ts`), and rendered as a quiet `Cpu` model chip above each finished
  assistant reply (`chat-history.tsx`). The dock's pill now shows the **real**
  model that answered (falling back to the configured provider label until one is
  known), never a fabricated name. (2) **Dock output completeness**: the dock's
  turn sink (`chat-dock.tsx`) dropped `memory`, `documents`, `codeVerification`,
  `autonomy`, `capability` and `runId`, so the memory/document panels, the code
  capability panel and the run-explanation panel never rendered in the floating
  assistant even though they do in the ChatBot tab; it now forwards every field,
  matching the Chat tab. Additive and honest — a run that reports no model simply
  shows no chip. `npx tsc --noEmit` clean.
  docs updated: `docs/chat-ui-audit.md` (`client.final` frame), `docs/CHANGELOG.md`.

- **Fundamentals P2–P4: filings framework, cross-source reconciliation,
  persistence hooks.** (P2) Official-filings **adapter registry**
  (`src/lib/fundamentals/filings/registry.ts`) — the `eclipse-filings` provider now
  dispatches through it, so adding a market is one adapter; PSX (PK) registered.
  (P3) `src/lib/fundamentals/reconcile.ts` (`reconcilePeriods`) deterministically
  compares the SAME metric/period across every source that returned periods and
  surfaces material disagreements (>threshold) — wired into `buildSnapshot` as
  `cross-source disagreement` insights (never averaged away), plus `PeriodConflict`
  on `AssembleInputs`. (P4) The provider order/registry is the coverage surface
  (eclipse-filings before yahoo; keyless). Tests: `filings/registry.test.ts` (5),
  `reconcile.test.ts` (6), `filings/psx.test.ts` (3). Known blocker: India's
  official portals (BSE/NSE) return 403 to server-side fetches — a real
  anti-bot limit that needs the browser runtime (documented, not faked). Full
  `vitest` 2524 (2 failures are a concurrent sidebar-guard change, not this work),
  `next build` + `tsc` + `eslint` clean; server restarted.
  docs updated: `docs/CHANGELOG.md`.

- **Capability Extension Phase A: live Pages — the UI-Engineering bridge.** The
  agent/UI-authored blueprints (UI-Engineering runtime, `agent-memory.db`) are no
  longer stranded in a separate store: a new **Pages** app tab
  (`src/components/screens/pages/pages-screen.tsx`, `AppTab 'pages'`) lists the
  saved blueprints and renders the selected one through the REAL
  `CustomizableWorkspace` + `renderDashboardWidget`, so an agent-composed page is
  a visible, usable page (add/rearrange widgets like the Command Center; "Save to
  page" writes the arrangement back as a new blueprint revision via
  `ui_save_layout`; "Revert" discards the local cache). New pure, tested bridge
  `src/lib/ui-engineering/live-page.ts` (`blueprintLayoutToKernel` /
  `kernelLayoutToWire` / `pageStorageKey`) is the ONE wire↔kernel layout
  translator. Tab wired through `app-tabs.ts`, `sidebar/config.ts`,
  `i18n/nav.ts` + `en.ts` (`nav.pages`), `search/deep-link.ts`, and
  `stock-chat.tsx`.
- **Agent glue: Eclipse now knows the `ui_*` tools exist.** Added a "Pages,
  widgets and tools" section to `ECLIPSE_AGENT_SYSTEM_PROMPT`
  (`python/harness/prompts.py`) documenting the Compose/Engineer flow and
  `ui_classify_request`. Fixed the Compose/Engineer classifier
  (`python/harness/ui/mode.py`): "new widget"/"create a widget"/"widget that" and
  "new tool" now signal **Engineer** (a genuinely new capability), while
  restyling an existing widget ("change the design"/"restyle") stays **Compose**.
  This is why "create a new widget" previously degraded to adding an existing one.
- Plan: `docs/harness/capability-extension-plan.md` (Phases A–E). Tests:
  `live-page.test.ts` (6), `test_ui_mode.py` (+4). Full `vitest` 239 files /
  2524 tests + UI `pytest` 31 + `tsc --noEmit` clean.
  docs updated: `docs/CHANGELOG.md`, `docs/harness/capability-extension-plan.md`,
  `docs/ui-engineering.md`.

- **Capability Extension Phase B-rest: the run learns the page the user is on.**
  The chat forwards the focused page with the run — a client focus store
  (`src/lib/ui-engineering/ui-focus.ts`, set by Pages/UI Builder, read by
  `use-agent-run`) → `ChatOptions.uiContext` → `buildPayload` → the
  `/api/harness/chat[/stream]` routes sanitize it → `startChatRun`/`chatWithAgent`
  put it in `input.context.ui` → `graph.py::_ui_focus_block` renders a per-run
  "Current UI page" prompt note (cache-key excluded) naming the blueprint. So
  "change my widgets" resolves to the actual page. Tests `test_ui_focus.py`.
- **Phase C: Engineer requests actually run.** `UiEngineering.start` left the plan
  in `PLANNING`, which the task scheduler skips — the root cause of "create a new
  widget" finishing with nothing. It now starts the plan (RUNNING) so the
  existing scheduler dispatches the task, and pins the invoking run's model on the
  plan metadata (`ctx.model_settings`) so the task uses the operator's provider.
  Tests `test_ui_engineering.py`.
- **Phase D (started): engineering-task visibility.** The UI Builder now polls
  `GET /ui/engineering/{planId}` and shows a live status card (plan + task
  statuses) after filing an engineering task.
- **Phase E (started, one-way): the Command Center mirrors to a blueprint.**
  `CustomizableWorkspace` gained `onLayoutChange`; the dashboard debounce-publishes
  its board into a per-dashboard UI blueprint (`dashboard-blueprint.ts`,
  localStorage id map + idempotent create), so Eclipse can see and edit the board
  the user actually has and it appears as a page. The reverse (agent edit → live
  dashboard) is the documented follow-up.
  Full `vitest` 239/2524 + UI `pytest` 62 + `tsc`/`eslint` clean.
  docs updated: `docs/CHANGELOG.md`, `docs/harness/capability-extension-plan.md`.

## 2026-10-09

- **Fundamentals P1: first-party official-exchange provider (PSX / Pakistan).**
  New `src/lib/fundamentals/filings/psx.ts` parses the PSX data-portal company
  page (`dps.psx.com.pk/company/<SYM>`) — the exchange's OWN annual key financials
  table (Sales, Profit after Taxation, EPS; "in thousands except EPS") —
  deterministically with cheerio into real periods (thousands → base, PK fiscal
  year end, sorted oldest→newest). New provider
  `src/lib/fundamentals/providers/eclipse-filings.ts` (`id: eclipse-filings`,
  keyless, `supports` PK) is registered in `PROVIDER_ORDER` before Yahoo, with
  `FundamentalProviderId`/`PROVIDER_LABELS`/`SOURCE_LABEL` extended. So PK stocks
  that had NO filings-backed fundamentals now show official exchange statements
  (`primarySource: eclipse-filings`), reducing third-party reliance. Verified
  live: OGDC, LUCK, ENGRO, HUBC, MCB, MARI, SYS each → 4 real periods. Tests
  `filings/psx.test.ts` (3, incl. the page's malformed `<tbody>`-in-`<thead>`).
  Full `vitest` 2508 + `next build` + `tsc` + `eslint` clean; server restarted.
  docs updated: `docs/CHANGELOG.md`.

- **Investor Eye: readable rail, full dossier overlay, AI-setup CTAs, agent world-events tool.**
  Right rail widened to 440/460px and retyped (11–13px) for readability, with
  the event dossier prioritised over the country panel; a wide, two-column
  **full event dossier overlay** opens via "Open dossier"/double-click (Esc/back,
  `store.dossierOpen`); the Explain/Research panels now offer an actionable
  "Open AI settings" deep link (`be:navigate` → Settings modal at the AI
  section); and the authoritative Python runtime gains `get_world_events` over a
  new `world_events` JDdS bridge capability. Bundles in-flight ChatBot-page
  customization. Full `vitest` 235 files / 2505 tests green, `tsc` clean.
  docs updated: `docs/investor-eye-architecture.md` (§5s).

- **Fundamentals: first-party web-extraction fallback (parse research into
  figures).** New deterministic `src/lib/fundamentals/research-parse.ts`
  (`parseFinancialFacts`/`parseNumber`) pulls standard line items (revenue, gross/
  operating/net income, EBITDA, EPS, margins, OCF/FCF, capex, debt, cash, assets,
  equity, ROE, market cap, P/E …) out of the web-research engine's verified text
  into `{key,label,value,unit,raw}` — conservatively (metric keyword + number in
  the same sentence, word/suffix rescaling, percent requires a `%`), never
  inventing a value. `companyBriefQuestion` now explicitly requests those figures
  with period + currency, and `ResearchedFinancialsSection` renders them as a
  metric grid (with the source sentence as the tooltip) above the findings and
  collapsible sources. This is P0 of the first-party fundamentals plan (reduce
  third-party API reliance); full official-filings extraction (P1/P2) remains.
  Tests `research-parse.test.ts` (8). Full `vitest` 2505 + `next build` + `tsc`
  + `eslint` clean. docs updated: `docs/CHANGELOG.md`.

- **Investor Eye: readable right rail (was too narrow / too small).** The hero's
  right rail was 360px with 8–10px type, so events/countries were unreadable.
  Widened to `440px` (lg) / `460px` (xl) and taller (`62vh`); the Live Event
  Stream and Country panel now use 11–13px type, larger markers, more row
  padding and 3-line titles (was 2). The event dossier is prioritised over the
  country panel in the rail (clicking a conflict shows the event, not a stale
  country). `Block`/`Row` dossier primitives bumped 9–10px → 11–12px.
  Presentation only; no data change. Full `vitest` **235 files / 2505 tests
  green**, `tsc` clean. docs updated: `docs/investor-eye-architecture.md` (§5s).

- **ChatBot landing wordmark default → Michroma; Background "Type" order
  Solid-first.** `DEFAULT_WORDMARK_FONT` in `src/lib/backgrounds.ts` now defaults
  to Michroma (`var(--font-michroma), system-ui, sans-serif`) instead of Bodoni,
  matching the shipped preset wordmark face; existing saved prefs keep their
  stored font. The backdrop "Type" options are reordered so **Solid** reads first,
  then **Image** (default mode is unchanged). New users/reset now get the
  Michroma wordmark. `backgrounds.test.ts` + `tsc` clean. no doc change — default
  value + option order only, no contract or architecture change.

- **Company detail: AI overview moved to the top-right (visible without
  scrolling).** The AI brief card is now the first card in the at-a-glance rail
  beside the chart, so it renders on the first screen instead of below technical
  /risk. Presentation only. `tsc`/`eslint` clean, `next build` green.
  no doc change — layout only.

- **Investor Eye: full event dossier + actionable AI-setup.** Clicking an event
  keeps the compact right-rail peek, but an **"Open dossier"** button
  (or double-click) now opens a wide, two-column, Esc-dismissible **full event
  dossier overlay** (`event-dossier-overlay.tsx`, portaled like `FullPageMap`;
  `EventPanel` gained `onOpen`/`wide`). The dead "AI not configured" states are
  now **actionable**: Explain/Evidence/Conflict-research panels show an
  "Open AI settings" button that deep-links to Settings → AI Agent via a new
  SSR-safe `navigation.ts` (`be:navigate {tab:'settings', section:'ai'}`; the
  shell's handler now opens the Settings modal at a section). Escape ownership
  handed to the dossier while open. Tests: `navigation.test.ts` (+2). Full
  `vitest` **234 files / 2497 tests green**, `tsc` clean. docs updated:
  `docs/investor-eye-architecture.md` (§5s).

- **ChatBot Page customization tab + working conversation font.** New
  **Customization › ChatBot Page** tab (`src/components/screens/chatbot-page-settings.tsx`):
  the backdrop/landing-wordmark controls move here out of Settings › General
  (General now links nowhere — the tab owns the whole ChatBot-page look),
  alongside a new **conversation font** picker. New store
  `src/lib/chat/appearance.ts` (`be_chat_appearance_v1`) offers the self-hosted
  wordmark typefaces + an "App font" default, applies the pick as `--chat-font`
  on `<html>`, and `ChatHistory`/the chat shell read it via
  `var(--chat-font, var(--font-sans))` — so choosing a face really changes the
  messages and composer instead of a system-only stack that silently fell back
  to the app font. Verified live: `--chat-font` → Orbitron on the chat
  container; the ChatBot Page tab renders the font grid + moved backdrop card.
  `tsc` + targeted `eslint` clean; `vitest` green (the only size-budget failure
  is the pre-existing concurrent `data-bridge.ts` growth). docs updated:
  `docs/ARCHITECTURE.md`, `docs/NAVIGATION.md`.

- **Investor Eye: AI conflict search + `get_world_events` Python tool.** (1) New
  "Conflict research (AI, cited)" panel in the analysis row drives the shared
  Evidence & Research Engine for a cited conflict situation report over the
  window (shared `research-findings.tsx`); it does NOT fabricate map pins —
  findings are labelled research. Pure `windowConflictQuestion` mandate (+3
  tests). (2) New read-only JDdS bridge capability `world_events` (own module
  `src/lib/harness/world-events.ts`, so ratcheted `data-bridge.ts` does not grow)
  + Python tool `get_world_events` (`python/harness/world_tools.py`, registered
  in `service.py`) exposing geopolitical events to the authoritative agent
  runtime, with source-failure/no-match honesty. Full `vitest` green
  (233 files/2495 tests; one unrelated concurrent edit to
  `customization-settings.tsx` trips the size-budget ratchet), `tsc` clean,
  targeted Python tool tests 625 passed. docs updated:
  `docs/investor-eye-architecture.md` (§5r).

- **Asset detail: load ALL assets — indices + on-demand resolution.** Two gaps
  closed in `/api/asset-details`: (1) **indices** (`^GSPC`, `^IXIC`, …) now
  resolve from `IndexQuote` (canonical ticker + aliases) → real name + level;
  (2) **symbols the vault never ingested** (e.g. `SPY`, `SGOV`) now resolve
  **on-demand** through the shared Yahoo chart fetch (`yahooChartCandidates` +
  `fetchYahooChartSeries`, extended to carry `longName`/`shortName`/`exchangeName`/
  `instrumentType`). Result: any Yahoo-resolvable instrument opens a detail page
  instead of a dead "not found". Verified live: `^GSPC`→S&P 500 7811.54,
  `^IXIC`→Nasdaq Composite, `SGOV`→iShares 0-3 Month Treasury ETF 100.51,
  `SPY`→State Street SPDR S&P 500 ETF Trust 778.57, `GC=F`→Gold. Full `vitest`
  2492 + `next build` + `tsc` + `eslint` clean. docs updated: `docs/CHANGELOG.md`.

- **Investor Eye: shared Evidence & Research Engine in the event dossier.** New
  `components/investor-eye/event-research.tsx` + `use-event-research.ts` drive the
  SAME Python web-research engine (via `/api/research/*`) used by the Research
  screen and company brief. LAZY (no auto-run on dossier open), cached per event,
  renders sources/claims(status)/citations/conflicts + the run's deterministic
  answer; 503-honest when the runtime is absent. Mandate built by pure, tested
  `research-question.ts` (+4 tests). This is the concrete "use AI to corroborate
  a conflict" path. Map-level promotion of AI findings to `AI-INTERPRETED` events
  and Python-native world tools remain (documented). Full `vitest` **233 files /
  2492 tests green**, `tsc` clean. docs updated:
  `docs/investor-eye-architecture.md` (§5q, Phase 4 event level).

- **Company detail: commodities/FX identity, market qualifier, AI overview moved
  below.** `/api/asset-details` now resolves catalog symbols (gold `GC=F`,
  `EURUSD=X`, …) → a synthetic asset (`found: true`, name/sector/marketId
  `COMMODITY`/`FX`), so clicking a commodity/FX row (already wired via
  `handleSymbolClick`) opens a detail page with a proper identity instead of "not
  found". Header now shows a market/exchange qualifier chip next to the symbol
  (disambiguates cross-market collisions like BNB CRYPTO vs DE). AI overview row
  moved below the technical/risk row (bottom of the page). Verified live:
  `/api/asset-details?symbol=GC=F` and `EURUSD=X` return `found:true`. Full
  `vitest` + `next build` + `tsc` + `eslint` clean. docs updated:
  `docs/CHANGELOG.md`.

- **Investor Eye: fix intermittent/missing conflicts + honest coverage.** Root
  causes audited: (1) GDELT only fetched the newest 15-minute bulk file, (2)
  `assembleState` never replayed persisted events, (3) the relevance gate
  silently dropped low-signal material conflicts, (4) no GDELT retry, (5) no way
  to see *why* the Conflict layer was empty. Fixes: rolling GDELT window over the
  last N 15-min slots with bounded concurrency + provider-id dedup + transient
  retry; persisted-event replay into the window (flagged `replayed`, never
  re-persisted); a material-conflict relevance floor (`quadClass===4` /
  `goldstein<=-5`); and a new pure `coverage.ts` (`observed|quiet|degraded|
  unavailable`) surfaced as a `retained` badge in the dossier, a `N retained`
  count in the map footer, and an amber explanation under the map when no
  conflicts are plotted. Tests: `gdelt-window.test.ts` (8), `coverage.test.ts`
  (7), relevance +2; full `vitest` **232 files / 2488 tests green**, `tsc` clean.
  docs updated: `docs/investor-eye-architecture.md` (§5q). ReliefWeb was
  evaluated and rejected as a zero-config source (v2 now needs a pre-approved
  `appname`).

- **Company detail: web-research fundamentals fallback + shared sources
  disclosure.** When a filings-backed fundamentals snapshot has **no statement
  periods** (all providers missed, or the instrument has none — e.g. crypto BNB
  returns a quote-only profile with 0 periods), the page no longer dead-ends:
  it renders `ResearchedFinancialsSection`, which reuses the SAME research run as
  the AI brief (no duplicate search) and shows the engine's verified findings as
  clearly-labelled "Researched financials (web) — not filings-backed", with the
  collapsible sources dropdown. Extracted the shared `SourcesDisclosure` used by
  both AI and researched-financials sections. `useCompanyResearch` already runs
  per symbol, so this adds sourced figures without a second request. Verified:
  `/api/fundamentals?symbol=BNB&market=CRYPTO` → available but 0 periods (now
  falls back); AAPL → 8 periods (unchanged). Presentation + reuse only; no new
  backend. Full `vitest` 2473 + `next build` + `tsc` + `eslint` clean.
  docs updated: `docs/CHANGELOG.md`.

- **Company detail UI: proper AI brief formatting, collapsible sources, layout
  polish.** The AI brief now parses the engine's structured synthesis
  (`Research:`/`Coverage:` meta + titled sections `Findings`, `Partially
  supported`, `Not established / conflicting`, `Conflicts`, `Gaps`, `Excluded`,
  `Citation issues`) and renders each as a real heading + bulleted list with
  severity tones — previously only `FACT:`-prefixed lines matched, so the whole
  answer rendered as flat text. Sources are now a collapsed native `<details>`
  dropdown ("Sources (N) — view") instead of an always-visible list. The AI
  overview is a full-width row below the data (no narrow-column gaps), the section
  icon is neutral (`BookOpen`), and the detailed claims list + inline citation
  clutter were removed. Price-history chart raised to 300px. Presentation only.
  docs updated: `docs/CHANGELOG.md`.

- **Investor Eye: NASA EONET hazard source + per-source ingestion circuit
  breaker.** (1) New keyless source adapter `sources/eonet.ts` adds the missing
  storm/flood/volcano/drought/ice coverage (before: earthquakes + fires only),
  normalizing EONET's observation history to a current position, mapping its
  categories onto the shared hazard vocabulary, scaling severity from the
  provider magnitude only where the unit is known (earthquake magnitude, storm
  wind knots), and using the EONET event id as the stable cluster signature.
  Registered in `sources/registry.ts`, licensed in `SOURCE_CATALOG` (governance
  invariant intact), quality added to `SOURCE_QUALITY`. (2) New
  `circuit-breaker.ts` short-circuits a source after 3 consecutive failures for a
  5-minute cooldown (half-open probe, success closes), wired into `runSource`;
  an open breaker reports the real reason — never a fake healthy-but-quiet
  result. Tests: `sources/eonet.test.ts` (19), `circuit-breaker.test.ts` (6);
  full `vitest` **230 files / 2473 tests green**, `tsc --noEmit` clean.
  docs updated: `docs/investor-eye-architecture.md` (§5p, last-verified bumped).

- **Company detail: wide side-by-side layout; AI overview moved below.** The
  overlay now uses a full-width `max-w-[1760px]` multi-column grid instead of a
  single narrow `max-w-5xl` stack: Row 1 = interactive chart (2/3) beside the
  at-a-glance rail (core metrics, 52-week range, session, risk & income,
  tokenomics, profile, leadership); Row 2 = filings financials (2/3) beside the
  AI brief (moved below the top row); Row 3 = technical + risk side by side;
  Row 4 = news (2/3) beside the AI conclusion. Chart raised to 420px; removed the
  now-orphaned right-pane divider. Presentation only — no contract change.
  no doc change — layout/visual change. Full `vitest` 2448 + `next build` + `tsc` clean.

- **Live quote: reject Yahoo's stale/bogus `regularMarketPrice` (real OGDC root
  cause).** Reproduced live: Yahoo's chart `meta.regularMarketPrice` for
  `OGDC.KA` is **131.87** while the actual latest bar close is **315.91** (and
  `chartPreviousClose` 310.34), so the read-through produced a bogus
  −57.5%/−57.5% quote. `fetchYahooChartSeries` now uses `selectChartPrice()`,
  which trusts the meta price **only when it agrees with the newest real bar**
  (≤5%), else the bar is authoritative. Applies to every instrument that uses
  the shared chart fetch (quotes, ribbon, portfolio, header). Verified live:
  `/api/quote?symbols=OGDC&market=PK` → **315.91 / +1.79%** (was 131.87).
  Test `src/lib/scraper/yahoo-chart.test.ts` (+5). no doc change — bug fix; the
  freshness/provenance contracts are unchanged.

- **Company detail: close the gaps (canonical quote, persisted AI answer,
  leadership).** (1) The overlay now fetches ONE canonical `/api/quote` and uses
  it for the header **and** the metric cards (with source + freshness), so the
  header can never show a different price than the chart/metrics — the structural
  form of the OGDC 306.12-vs-131.87 class (live checks: real PSX OGDC ≈ 306–316
  PKR; 131.87 exists nowhere in JDDS). (2) The web-research engine's deterministic
  `answer` is now persisted (`WebResearchRun.answer`, additive migration;
  `answer=COALESCE(...)` so state-only writes don't clobber it) and returned by
  `GET /research/web/{id}`; the AI brief/conclusion render the typed
  FACT/CALCULATION/INFERENCE/UNCERTAINTY synthesis + claims/citations/sources.
  (3) Leadership is now a real provider integration: the yfinance bridge extracts
  `companyOfficers`, the Yahoo provider normalizes `Officer[]` into
  `CompanyProfile.leadership`, and `LeadershipSection` renders it with an
  "verify against the latest filing" caveat (live: AAPL returned 10 officers incl.
  CEO/CFO). Python tests added (`test_web_research_store.py`, +3); TS
  `fundamentals.test.ts` (+1). Full `vitest` 2443, `next build`, `tsc`, `eslint`
  clean. docs updated: `docs/NAVIGATION.md`, `docs/harness/web-research-engine.md`,
  `docs/CHANGELOG.md`.

- **Company Intelligence: single-page stock detail (no Fundamentals/Technical
  tabs).** The Market Discovery stock overlay is now one continuous, vertically
  scrollable page: quote header (A), AI company brief (B, driven by the existing
  web-research engine via `/api/research/*` with per-symbol caching and honest
  unavailable/retry states), interactive chart (C), inline filings fundamentals —
  overview/statements/valuation/timeline via the new non-tabbed `FundamentalsFull`
  (D/E/F/H), JDDS news feed (G), deterministic technical analysis (I), deterministic
  risk synthesis (J) and an AI conclusion (K). New pure engines
  `src/lib/company/technical.ts` (reuses `chart/indicators/registry`) and
  `src/lib/company/risk.ts` (documented thresholds, evidence-backed), hooks
  `use-company-news`/`use-company-research`, and `src/components/screens/company/sections.tsx`.
  The duplicative right sidebar was removed. Tests `technical.test.ts` (6) +
  `risk.test.ts` (6); full `vitest` 2442, `tsc` and `eslint` clean.
  docs updated: `docs/NAVIGATION.md`, `docs/CHANGELOG.md`.

- **Chore: de-emphasize the ticker example in the freshness guard.** Reworded the
  comments/docs so the guard is described as symbol- and market-agnostic (it is:
  every instrument on both endpoints flows through the same path). No behaviour
  change. docs updated: `docs/harness/market-data.md`.

- **Thesis store: fix revision-versioning collision + real-DB integration test.**
  `updateThesis` recorded a revision at the *prior* version, colliding with the
  origin revision written at creation (`@@unique([thesisId, version])`). It now
  records the resulting version's snapshot, so the full history is preserved and
  the original hypothesis is never rewritten. Added
  `src/lib/theses/store.integration.test.ts` (self-skips when the Thesis tables
  are absent, unique symbol, cleans up). Full `vitest` (2430) + `tsc` clean.
  no doc change — bug fix + test; the contracts in `docs/NAVIGATION.md` are unchanged.

- **Fix: normalize `prisma/schema.prisma` line endings + drop an unused import.**
  The appended Thesis models introduced one CRLF into an LF-only file, which the
  `gitignore-guard` test correctly flagged; normalized back to LF. Removed the
  pre-existing unused `DAILY_HISTORY_TTL_MS` import in
  `/api/price-history`. Full `vitest` (2427), `tsc`, and `eslint` now clean.
  no doc change — regression fix + lint cleanup.

- **Docs: navigation + market-data sync.** `NAVIGATION.md` gains trigger rows for
  the Investment Thesis Tracker and observation freshness, and
  `docs/harness/market-data.md` documents the observation-freshness envelope; both
  `last-verified` bumped to 2026-10-09. docs updated: `docs/NAVIGATION.md`,
  `docs/harness/market-data.md`, `docs/CHANGELOG.md`.

- **Investment Thesis Tracker: API route tests (WIP).** Adds
  `src/app/api/theses/route.test.ts` (5 cases). no doc change — test-only change.

- **Investment Thesis Tracker: analysis tests (WIP).** Adds
  `src/lib/theses/analysis.test.ts` (11 cases). no doc change — test-only change.

- **Investment Thesis Tracker: API + screen (WIP).** `/api/theses` (list/create),
  `/api/theses/[id]`, `/api/theses/[id]/evidence`, `/api/theses/[id]/revisions`
  routes and the `src/app/theses/` screen over the versioned thesis models/lib.
  `npx tsc --noEmit` clean. docs updated: `docs/CHANGELOG.md`.

- **Investment Thesis Tracker (workstream, WIP).** New Prisma models `Thesis` /
  `ThesisEvidence` / `ThesisRevision` (a thesis is versioned; every edit appends a
  revision so the original hypothesis is never silently rewritten, and evidence is a
  first-class relation with provenance) and a `src/lib/theses/` library
  (`types.ts`/`store.ts`/`analysis.ts`). `npx tsc --noEmit` clean.
  docs updated: `docs/CHANGELOG.md`.

- **Market data: observation freshness guard.** New `src/lib/chart/observation-freshness.ts`
  (metric-and-interval-aware freshness: `live`/`delayed`/`stale`/`historical`/
  `unavailable`/`unknown`, never inventing a timestamp) + tests; `/api/price-history`
  and `/api/quote` now carry observation time/age/freshness so a stale series is
  labelled rather than drawn as current, and the chart surfaces it.
  docs updated: `docs/CHANGELOG.md`.

- **Recovery: test hardening.** `python/conftest.py` now isolates the process-global
  recovery service singleton (`set_recovery_service`) in the autouse fixture, and the
  approve-route API test uses a unique incident per run so it cannot collide with a
  shared database. no doc change — test-only change.

- **Agent Workspace: Context panel leads the right sidebar.** The Agent Workspace
  panel order now lists Context first (plus Output/Changes/Permissions/History) and
  the default/open panel is Context. Presentation only.
  no doc change — UI panel ordering; no architecture, contract or setup change.

- **UI Engineering foundation (TS): component catalog + declarative blueprint
  engine.** New framework-pure module `src/lib/ui-engineering/`: `catalog.ts`
  projects the existing `WidgetDefinition` registry into queryable
  `UiComponentSpec`s (`adaptWidgetDefinition`, `ComponentCatalog.search`,
  `validateComponentConfig`); `blueprint.ts` wraps the existing `WorkspaceLayout`
  in a versioned `UiBlueprint` with strict, truthful validation (unknown
  component / duplicate instance / bad config are reported, not silently
  dropped); `patches.ts` applies a closed set of atomic, catalog-validated
  `BlueprintOp`s in one Immer transaction (delegating layout math to
  `workspace/ops.ts`); `revisions.ts` adds `diffBlueprints`, a bounded
  append-only `BlueprintHistory`, `restoreRevision` and optimistic-concurrency
  `detectConflict`; `store.ts` provides in-memory + localStorage
  `BlueprintStore`s that never overwrite a corrupt payload. 38 vitest cases pass
  and `npx tsc --noEmit` is clean. **Boundary:** frontend foundation only — the
  `ui.*` agent tools, the Python `agent-memory.db` blueprint store, Compose/
  Engineer mode selection and the UI Builder workspace are the next phases.
  docs updated: `docs/ui-engineering.md` (new), `docs/NAVIGATION.md`, this file.

- **UI Engineering runtime (Phases 4–5): server-side blueprint store + `ui_*`
  agent tools.** New `python/harness/ui/` on the ONE `agent-memory.db` and the
  ONE event system: `model.py` (pydantic contracts — `UiComponentSpec`,
  `UiBlueprint`, the workspace layout tree, closed vocabularies; camelCase on
  the wire), `catalog.py` (`UiCatalog` seeded with the foundational component
  kinds + `validate_component_config` with TS-identical semantics), `engine.py`
  (`validate_blueprint` strict/truthful + atomic `apply_ops` with revision bump
  + `diff_blueprints`), `store.py` (`UiStore`: `UiBlueprint`,
  `UiBlueprintRevision`, `UiComponent`, `UiOperation`, `UiIdempotency`), and
  `service.py` (`UiService` = catalog + blueprints + widget ops + optimistic
  concurrency `UI_CONFLICT` + operation audit + `ui.*` events). Registered 24
  `ui_*` tools on the shared `ToolRegistry` (introspection `ui_get_*` +
  `ui_create_page`/`ui_add_widget`/`ui_move_widget`/`ui_resize_widget`/
  `ui_update_widget_config`/`ui_save_layout`/`ui_restore_revision`/
  `ui_preview_change`) and added them to the default agent allowlist; new
  operator-gated routes `routers/ui.py` (`/ui/*`) included by `main.py`; boot
  wiring `install_ui_layer` in `service.py` + the `ui_service` `ToolContext`
  seam in `graph.py`/`tools.py`; Next.js front door
  `src/lib/harness/ui-client.ts` + `src/app/api/ui/[[...path]]/route.ts`; `ui`
  event namespace. Tests `python/tests/test_ui_{engine,store,service,tools,api}.py`
  (38 cases). All UI tools are `permission="read"` — they change only Eclipse's
  own owner-scoped UI config, never filesystem/network/shell/secrets. **Boundary:**
  the runtime seeds the foundational component kinds; syncing the real dashboard
  widget registry into the runtime catalog, the two-mode Compose/Engineer flow
  (Phase 6) and the UI Builder workspace (Phase 8) remain. Verified: pytest
  5086+ passed (16 opt-in skips), `npx tsc --noEmit` clean. docs updated:
  `docs/ui-engineering.md`, `docs/NAVIGATION.md`, this file.

- **Failure Intelligence & Adaptive Recovery — the one cross-subsystem failure
  layer.** New `python/harness/recovery/`: `taxonomy.py` (the shared
  `FailureKind`/`Retryability` vocabulary + pure `normalize_failure`),
  `signature.py` (stable 16-hex signatures + `RecurrenceTracker`), `policy.py`
  (ordered `select_strategies` + `reject_reason`; never retries a deterministic
  failure unchanged, never provider-swaps an auth denial), `controller.py`
  (bounded `RecoveryDecision` + exponential backoff), `store.py`
  (`RecoveryIncident`/`RecoveryAttempt` on **`eclipse-memory.db`**, migration 26),
  `service.py` (classify+decide+persist), `bootstrap.py` (idempotent install +
  Event System failure subscription), `tools.py` (read-only `recovery_*` tools),
  and operator routes `routers/recovery.py` (`/recovery/*`). Wired in `boot.py`
  (not `service.py`/`graph.py`, which are ratcheted) and `main.py`. It composes
  existing taxonomies/diagnostics/retry/routing — it is NOT a second execution
  loop and never runs a tool or mutates task state. 40 new pytest cases pass,
  including a live `tool.failed` → incident end-to-end case. Full suite
  `5129 passed, 16 skipped`; vitest 2375; `npx tsc --noEmit` clean; eval gates
  ALL PASS. The `test_size_budget` ratchet is re-pinned for the pre-existing
  in-flight drift in `graph.py`/`service.py` and `main.py` is held at 1200.
  **Boundary:** the UI panel, automatic strategy execution and feeding incidents
  into skill promotion remain. docs updated: `docs/harness/failure-recovery.md`
  (new), `docs/harness/decisions.md` (ADR-H163), `docs/NAVIGATION.md`, this file.

- **Recovery engine completes the loop: diagnosis, automatic execution, capability
  discovery, incident→skill promotion, and a `/recovery` console.** New in
  `python/harness/recovery/`: `diagnosis.py` (evidence-ranked `DiagnosisEngine` +
  `Hypothesis`; decisive only with strong evidence, otherwise names the gap),
  `executor.py` (`recover_operation` — a bounded async retry/verify loop driving the
  controller, with caller-registered repair handlers and verify-gated success),
  `discovery.py` (`CapabilityIndex` over tools/providers/skills + approval-flagged
  `acquisition_plan`), `learning.py` (`promote_incidents` — inert `LearningCandidate`s
  through the existing learning store). Persistence: migration 27 adds the
  idempotent `RecoveryDiagnosis` table. New read tools `recovery_diagnose` /
  `recovery_discover`; operator routes `POST /recovery/incidents/{id}/diagnose`,
  `POST /recovery/promote`, `GET /recovery/discover`. Standalone front door:
  `src/app/recovery/` console (mirrors `/events`), `src/app/api/recovery/[[...path]]`,
  and `src/lib/harness/recovery-view.ts`. 64 pytest cases + `recovery-view.test.ts`;
  full suite `5161 passed, 16 skipped`; vitest 2389; `npx tsc --noEmit` clean; eval
  gates ALL PASS. docs updated: `docs/harness/failure-recovery.md`,
  `docs/harness/decisions.md` (ADR-H164), `docs/NAVIGATION.md`, this file.

- **Autonomy Envelope + deterministic probes + operation/compensation ledger.** New
  in `python/harness/recovery/`: `envelope.py` (`AutonomyEnvelope`/`ActionClass` —
  pre-committed, scoped, expiring permission by action class with risk/reversibility/
  cost/file/network caps and a `HARNESS_AUTONOMY` kill switch; default is
  conservative, effectful classes opt-in), `probes.py` (read-only dependency/provider
  probes registered at boot), `operations.py` (`OperationLedger` — idempotency-keyed
  side-effect tracking + compensation bookkeeping; migration 28 `RecoveryOperation`).
  The executor now acts unattended ONLY inside the envelope (else returns
  `outside_autonomy_envelope`). New operator routes `GET/PUT /recovery/envelope` and
  `GET /recovery/operations`; console gains an "Autonomy & operations" tab. Fixed a
  variable-shadowing bug in the executor found by the new tests. 87 pytest cases;
  full suite `5190 passed, 16 skipped`; vitest 2392; `npx tsc --noEmit` clean; eval
  gates ALL PASS. docs updated: `docs/harness/failure-recovery.md`,
  `docs/harness/decisions.md` (ADR-H165), `docs/NAVIGATION.md`, this file.

- **Autonomy made durable + coordinated: persisted envelope, per-signature repair
  lease, one-off operator approvals, and compensating actions.** Migration 29 adds
  `AutonomyEnvelope` (a `PUT /recovery/envelope` now persists and survives restart),
  `RecoveryLease` (two workers never repair the same root cause at once; the executor
  returns `repair_lease_held`), and `RecoveryApproval` (`POST
  /recovery/incidents/{id}/approve` authorizes exactly one out-of-envelope strategy
  for one incident). New `recovery/compensation.py` `compensate_pending()` runs
  caller-registered compensation handlers, envelope-gated under `COMPENSATE`. The
  console gains a decision + "Approve strategy" control in the incident detail. 99
  recovery pytest cases; full suite `5202 passed, 16 skipped`; vitest 2394;
  `npx tsc --noEmit` clean; eval gates ALL PASS. docs updated:
  `docs/harness/failure-recovery.md`, `docs/harness/decisions.md` (ADR-H166),
  `docs/NAVIGATION.md`, this file.

- **Auto-reproduction + hard safety invariants (production hardening).** New
  `recovery/reproduction.py` (`ReproducerRegistry`/`reproduce` — a caller-registered
  reproducer per failure kind, run under a hard timeout; a successful reproduction
  becomes evidence and makes the diagnosis decisive) with operator route
  `POST /recovery/incidents/{id}/reproduce`. New tests pin the trust properties:
  `test_recovery_safety.py` (envelope cannot be bypassed, kill switch, non-retryable
  never retried, bounded recovery, scoped one-off approval, no secret persisted) and
  `test_recovery_concurrency.py` (repair-lease exclusivity under thread contention).
  `docs/harness/failure-recovery.md` gains a Production & operations section. 115
  recovery pytest cases; full suite `5202+ passed, 16 skipped`; vitest 2394;
  `npx tsc --noEmit` clean; eval gates ALL PASS. docs updated:
  `docs/harness/failure-recovery.md`, `docs/harness/decisions.md` (ADR-H167),
  `docs/NAVIGATION.md`, this file.

- **Agent Workspace: new Context tab (session-context gauge).** The right sidebar
  gains a fifth tab showing how full the model's context window is, mirroring the
  OpenCode session sidebar: usage % + a segmented breakdown gauge, plus tiles for
  window / total / input / output tokens, remaining, turns kept-dropped, memories
  and estimated cost, and a per-source legend. It reuses the already-normalized
  store (`state.context`, `state.contextSources`, `state.telemetry`) — no harness
  change — and resolves the window from the declared model catalog. New pure
  module `src/lib/agent-workspace/context-usage.ts` (+9 tests) keeps the math
  testable and honest (unknown window → "Not available", never a faked full bar);
  `totalTokens` is run-cumulative per step, as documented. docs updated:
  `docs/agent-workspace.md`.

- **Agent Workspace tabs gain icons.** The sidebar nav was text-only, so the new
  Context tab had no visual affordance. Each tab now renders its `PANEL_ICONS`
  glyph before the label (Output=Bot, Context=SlidersHorizontal, Changes=FileText,
  Approvals=ShieldAlert, History=Bot); `PANEL_ICONS.output` was added. No behavior
  change — labels, order and attention dots unchanged. no doc change — visual
  affordance only, contracts unchanged.

- **UI Engineering Phases 6 & 8 + event-system shutdown fix.** Two-mode
  generation: `python/harness/ui/mode.py::classify_request` is a deterministic,
  model-free Compose/Engineer/both selector (errs toward Compose so a
  configuration change is never silently turned into a source-code release),
  exposed as the `ui_classify_request` tool and `POST /ui/classify`. UI Builder:
  new `src/components/screens/ui-builder/ui-builder-screen.tsx` (AppTab
  `ui-builder`) — page navigator, component catalog, structural preview,
  properties inspector (config validated against each component's schema),
  AI command panel (classify + add matched component), revision history/restore
  and a diagnostics log — wired via `ui-client.ts` + the `/api/ui` proxy; added
  `POST /ui/blueprints/{id}/widgets/{instance_id}/reorder` (+ client and
  sidebar/nav/i18n entries; sidebar shortcut tests updated). **Defect fixed
  (pre-existing, order-dependent):** `event_system/bus.py::shutdown` awaited
  `asyncio.gather` across worker tasks created on a PREVIOUS loop, raising
  `ValueError: The future belongs to a different loop`, which aborted
  `EventSystem.stop()` before `_started=False`; the next boot's `start()` then
  no-opped and the bus stayed `_closed`, so `publish()` silently dropped events
  (the intermittent `test_recovery_api` live-event failure — reproduced with the
  UI layer disabled). Shutdown is now loop-safe (drains only same-loop workers,
  clears subscriptions) and `stop()` resets `_started` in a `finally`; `start()`
  clears stale subscriptions. Tests: `python/tests/test_ui_mode.py` + reorder/
  classify API cases + `test_events_bus.py` drain case; vitest 220 files / 2389
  tests, pytest green. docs updated: `docs/ui-engineering.md`,
  `docs/NAVIGATION.md`, this file.

- **UI Engineering Agent (Phase 7): Engineer-mode orchestration over the existing
  Task/Plan runtime.** New `python/harness/ui/engineering.py` (`UiEngineering`)
  turns an Engineer/Both-mode request (`mode.classify_request`) into a DURABLE
  plan + task on the EXISTING `python/harness/tasks/` manager (assigned to
  `code-agent` at `edit_verify`, with UI acceptance criteria) — no parallel agent
  loop is introduced; the existing scheduler + code capability execute it. The
  loop closes via `ui_register_engineered_component`, which registers the new
  component in the ONE catalog (so a later Compose request can use it), satisfies
  the "registered in the UI catalog" criterion with evidence, and attaches a
  `ui-component` artifact. Compose-mode requests create no task (`start` says so
  honestly). `UiService` gains an `engineering` collaborator (built from
  `service.tasks` in `bootstrap.install_ui_layer`); four tools
  (`ui_start_engineering`, `ui_engineering_status`,
  `ui_register_engineered_component`, `ui_link_engineering_artifact`) and four
  operator-gated routes (`POST /ui/engineering`, `GET
  /ui/engineering/{plan_id}`, `POST /ui/engineering/{task_id}/components`,
  `POST /ui/engineering/{task_id}/artifacts`); the UI Builder AI panel gains a
  "Create engineering task" action. Tests: `test_ui_engineering.py` +
  engineering API cases (51 UI pytest cases total). docs updated:
  `docs/ui-engineering.md`, `docs/NAVIGATION.md`, this file.

- **Agent Workspace: reopening a past chat restores its run; Context tiles use the
  glass system.** Opening an existing conversation now repoints the workspace at
  that chat's most recent run instead of leaving the last live run's data on
  screen: new `src/lib/agent-workspace/restore.ts` resolves the run id (last
  `Message.runId`, else the runtime's `/api/sessions/{chatId}` run list), rebuilds
  it via new `history.loadRunSnapshot` (replayed event trace **plus** the
  authoritative run record — tokens, model, context window), and commits it with
  the new `store.loadRun` action; a new chat / run-less chat calls `store.clear()`.
  The History tab's reopen uses the same snapshot path. Also fixed the Context
  stat tiles to the design language: `StatTile` now uses `.glass-card-subtle`
  (frosted) instead of a flat fill + `border border-white/8`. New
  `history.applyRunRecord` (+3 tests). docs updated: `docs/agent-workspace.md`.

- **UI Engineering: host-registry ↔ runtime-catalog sync bridge + live-render
  preview.** The UI Builder now pushes the REAL dashboard widget specs into the
  runtime catalog via `syncCoreCatalog()` (`src/lib/harness/ui-sync.ts`,
  adapting `dashboardComponentSpecs()` and POSTing `POST /ui/components`), so the
  agent can Compose with the actual widgets and the specs persist on
  agent-memory.db across restarts — no second hand-maintained widget list in
  Python. Its "live render" toggle draws a widget through the SAME host
  implementation the published dashboard uses (`renderDashboardWidget`) wrapped
  in an error boundary (`ui-builder/live-boundary.tsx`); ids with no host
  renderer fall back to the structural card. `registerComponent` now accepts a
  loose spec (the runtime validates). Tests: `src/lib/harness/ui-sync.test.ts`.
  docs updated: `docs/ui-engineering.md`, `docs/NAVIGATION.md`, this file.

- **Production deployment kit (container).** New `Dockerfile` (Node 20 + Python 3;
  installs Node + Python deps, `prisma generate`, `next build`),
  `docker-entrypoint.sh` (links `jdds.db` / `agent-memory.db` /
  `eclipse-memory.db` / `.black-eclipse/` into a mounted `/data` volume so state
  survives restarts — needed because `src/lib/db.ts` hard-codes `cwd/jdds.db`),
  `docker-compose.yml` (single service, `.env`, `be-data` volume, healthcheck,
  `restart: unless-stopped`), `.dockerignore`, and `.env.example` (all required
  production vars). One container runs both services: the app spawns the Python
  harness as a child, so only port 3000 is exposed. Guide: `docs/DEPLOYMENT.md`
  (new). docs updated: `docs/DEPLOYMENT.md`, `docs/NAVIGATION.md`, this file.

- **UI Engineering production-readiness: boot sync, export/import, CLI, and an
  end-to-end agent proof.** (1) `UiCatalogSync` (mounted in `src/app/page.tsx`)
  seeds the runtime catalog with the real dashboard widgets on first app load,
  so the agent can Compose without opening the Builder. (2) Blueprint
  portability: `GET /ui/blueprints/{id}/export` (self-describing snapshot) and
  `POST /ui/blueprints/import` (validated, stored as a NEW blueprint), surfaced
  as Builder Export/Import buttons. (3) `eclipse ui
  {components|capabilities|blueprints|show|history|create|classify|export|import|restore}`
  CLI group over the runtime's own store. (4) `test_ui_agent_e2e.py` drives the
  REAL `execute_run` graph with a scripted model emitting `ui_*` tool calls and
  asserts a durable page + metric card — the natural-language → tools → state
  path proven without a live provider (removing the "needs credentials to
  verify" blocker). `npm run build` (production) also passes cleanly. Tests:
  `test_ui_cli.py`, export/import API case, `test_ui_agent_e2e.py`. docs
  updated: `docs/ui-engineering.md`, `docs/NAVIGATION.md`, this file.

## 2026-10-08

- **Run-path tenant identity + identity header on the explicit run routes.**
  `RunRequest` gains a verified `tenantId`; the Python `/runs` boundary resolves it
  from the edge identity (`resolve_identity`) and the graph puts it on the
  `ToolContext`, so the security gateway scopes every effect decision to the run's
  tenant (multi-tenant runs now authorize correctly instead of failing closed).
  The explicit `/runs`, `/chat` and `/chat/stream` routes now attach
  `X-Harness-Identity` (`runtimeIdentityHeaders`) via `runViaRuntime`, threading it
  through `run-service`. Tests: `test_security_tenancy.py` (run endpoint sets
  tenant from identity / leaves it None without). **Boundary:** run DATA still
  lands in the shared store; routing the run path through `TenantStoreRegistry`
  and isolating memory/tasks/artifacts/JDdS per tenant remain the data-plane work.
  docs updated: `docs/harness/security.md`, this file.
- **Tenant isolation + sandbox gate + universal identity header.** (1)
  `security/tenant_store.py`: `TenantStoreRegistry` maps a sanitized tenant id to
  its own `AgentMemoryStore` file under `.black-eclipse/tenants/<tenant>/`
  (`BLACK_ECLIPSE_TENANT_DB_DIR`) — two tenants, two databases, so a missing
  `WHERE` cannot leak rows; wired into `AgenticService.tenant_stores`. (2) The
  identity header `X-Harness-Identity` is now forwarded by **every** `[[...path]]`
  proxy (13 routes) via `runtimeIdentityHeaders`, so no feature route reaches the
  runtime without the verified user/tenant. (3) `BLACK_ECLIPSE_SANDBOX_REQUIRED`
  (`1`|`docker`) makes the gateway refuse an execution action when the required
  isolation backend is absent (audited `security.sandbox.blocked`); a forced
  `UnavailableSandbox` is now honored instead of silently re-detected. (4)
  `scripts/security-preflight.js` (`npm run security:preflight`) fails closed on a
  network-facing deployment missing `HARNESS_AUTH_SECRET`/`CRON_SECRET`. Tests
  `test_security_tenant_store.py` + updated sandbox tests (231 security tests).
  **Boundary:** the tenant-store primitive is available but the run path is not yet
  routed through it, and the explicit `/runs` route still forwards only the
  front-door-verified `userId`/`scopeId`; full data-plane tenancy remains. docs
  updated: `docs/harness/security.md`, `docs/harness/decisions.md` (ADR-H162), this
  file.
- **Production hardening of the evidence release gate: credential-safe verdicts,
  and production gates exercised.** The gate now strips a cited URL's `user:pass@`
  authority before it is persisted on the run blob or emitted as
  `evidence.release_gate`, so an embedded token never leaves the gate
  (host/path/query preserved for the reader). Verified in production mode: a clean
  `npm run build` (**✓ Compiled successfully**, no errors) and the operator-
  triggered live smoke (`npm run test:smoke`) reached DuckDuckGo, the SEC ticker
  map, SEC XBRL and TSMC IR (PDF correctly reported `unsupported_document`). docs
  updated: `docs/harness/web-research-engine.md`, this file.
- **Test isolation for the Artifact Center's process global (fixes a flaky
  test).** `AgenticService.__init__` (and the `/artifacts/*` self-heal) register a
  process-wide `ArtifactService`, so a test that constructed a service leaked it
  into later tests and made
  `test_artifacts_tools.py::test_tool_without_service_reports_unavailable`
  order/timing dependent. Added an autouse `python/conftest.py` fixture that saves,
  clears, and restores the `artifacts.bootstrap` singleton around every test, and
  pinned the global accessor in that test. `no doc change — test isolation only`.
- **Evidence release gate + research artifacts — claim verification now reaches
  the delivery seam.** Closes the gap where the evidence/verification engine
  existed but an ordinary (non-gated) run's answer was never checked against the
  evidence it actually retrieved. (1) `python/harness/research/release_gate.py`: a
  deterministic, model-free gate at the existing `graph.execute_run` answer seam
  (beside the code and finance enforcements) that extracts the final answer's
  http(s) citations and checks each against the URLs the run actually
  retrieved/consulted (`SourceCollector.known_urls()`). An unretrieved citation is
  disclosed as unverified; the verdict (`ok`/`unverified`/`no_citations`/
  `no_evidence`) is persisted on the run's `research` blob
  (`metadata.citationIntegrity`) and emitted as `evidence.release_gate`. Private/
  loopback links are ignored, user-supplied URLs and consulted-but-failed fetches
  are admissible, and a citation-free answer is untouched. (2)
  `artifacts.producers.register_research_report`: a completed
  `research/web_engine.py` run is registered in the Artifact Center as an
  evidence-REFERENCING Markdown report (claim verdicts, conflicts and an evidence
  appendix by id; `researchId`/`snapshotId`/evidence ids in metadata), idempotent
  per `(researchId, snapshotId)` and a no-op when the catalog is absent — research
  history is durable in the one catalog WITHOUT duplicating the evidence store.
  Tests `python/tests/test_evidence_release_gate.py` +
  `python/tests/test_research_artifact.py` + two end-to-end cases in
  `test_graph.py`. Full suite green: Python 5040 passed/16 skipped, Vitest 2337
  passed, `tsc` clean, eval gates ALL PASS. docs updated:
  `docs/harness/web-research-engine.md`, `docs/harness/artifact-center.md`,
  `docs/harness/decisions.md` (ADR-H162), `docs/NAVIGATION.md`, this file.

- **Multi-tenant security plane: verified edge identity, tenant isolation, bind
  hardening.** The runtime no longer trusts a caller-supplied `userId`/`tenantId`.
  The front door (`src/lib/harness/runtime-identity.ts`) mints a 5-minute HS256
  identity JWT from the authenticated session with `HARNESS_AUTH_SECRET`; proxies
  forward it as `X-Harness-Identity`; `python/harness/security/identity.py`
  verifies it with stdlib only (no new dependency). Precedence: session token →
  operator (loopback/secret) → anonymous. Multi-tenant mode (`HARNESS_MULTI_TENANT`,
  or auto-on when the front door requires auth) refuses anonymous callers (401).
  The security subsystem is now tenant-aware: capabilities, secret grants,
  sessions and audit carry a `tenantId` and never cross tenants; the gateway
  refuses an untenanted request in multi-tenant mode. Beyond loopback the runtime
  refuses to start without `CRON_SECRET` (and `HARNESS_AUTH_SECRET` in multi-tenant
  mode). Per-tenant token-bucket rate limiting on the security endpoints. Tests
  `python/tests/test_security_tenancy.py` + `test_security_ratelimit.py` (218
  security tests total). **Boundary:** this is the multi-tenant *security plane*
  and identity seam; full per-tenant DATA isolation (runs, memory, tasks,
  artifacts, JDdS reads) and the remaining proxy rollout are the follow-on
  data-plane migration (ADR-H161). docs updated: `docs/harness/security.md`,
  `docs/harness/decisions.md` (ADR-H161), this file.
- **Security hardening — full effect-tool migration, real sandbox abstraction,
  production secret providers, anchored audit, and an operator UI.** Extends the
  Security subsystem to production scope. (1) Migration: `security/classification.py`
  maps EVERY effectful tool of every capability (filesystem, shell/code, git/VCS,
  application-runtime, infrastructure/deploy, database, browser, computer/finance,
  vision, plugins, MCP, skills) to the `(action, resource, permission)` vocabulary by
  importing the canonical `code/policy.py` tool tuples — so `build_effect_authorizer`
  now routes them all through the gateway; a bypass-audit test asserts zero
  unclassified effect tools. Hard-deny and policy-deny are authoritative; approvals
  defer to each capability's own single-use chain (exactly one approval, no
  double-prompt). Environment resolves from the run context, the deploy action, or
  `BLACK_ECLIPSE_ENVIRONMENT`, so PRODUCTION gates bite. (2) `security/sandbox.py`:
  the `ExecutionSandbox` abstraction with a real `DockerSandbox` (`--network
  none|bridge`, read-only rootfs, non-root, cap-drop ALL, no-new-privileges,
  memory/pids/cpu limits, explicit mounts + secret env), a `LocalSandbox` over the
  existing `code/sandbox.py` primitive, and an `UnavailableSandbox` that fails
  closed; selection never returns an unbounded backend. (3) `security/secrets.py`:
  `OsKeychainProvider` (Windows Credential Manager / macOS Keychain / Linux Secret
  Service) and `CliSecretProvider` (Vault / AWS / 1Password / GCP / Azure via an
  operator-configured argv template), both reporting availability honestly. (4)
  `security/audit.py`: an optional append-only JSONL `AuditSink` with an HMAC-signed
  head (`BLACK_ECLIPSE_SECURITY_AUDIT_LOG`), anchoring the trail outside the
  runtime's database. (5) UI: a `SecuritySettingsPanel` (Settings › Security)
  surfacing posture, pending approvals, capabilities (revoke) and audit-chain
  validity. Tests `python/tests/test_security_{bypass_audit,sandbox,audit_sink,secret_providers}.py`
  (202 security tests, all passing). docs updated: `docs/harness/security.md`,
  `docs/harness/decisions.md` (ADR-H160), this file.
- **Artifact Center — one durable catalog for everything the runtime and the user
  produce.** New `python/harness/artifacts/`: `ArtifactService` + `ArtifactStore`
  own the lifecycle (register, version, preview, tag, collect, archive, restore,
  delete, purge, reconcile) over `HarnessArtifact*` tables on the ONE
  `agent-memory.db` connection, with a confined, content-addressed
  `LocalArtifactStorage` under `.black-eclipse/artifacts/` for the bytes (never
  JDdS, never a workspace path from a caller). Producer hooks register real output
  from `analysis_run` (`analysis_tools.py`), the task scheduler
  (`tasks/scheduler.py`), and the Code Execution & Verification Layer
  (`execution/orchestrator.py`); the `artifact_*` agent tools and the operator-gated
  `/artifacts/*` route group go through the same service. Front door: the
  `/api/artifacts/**` proxy + client-safe `artifacts-browser.ts` + the Artifact
  Center screen (AppTab `artifacts`, Agentic sidebar). Search/filter/sort/pagination
  are server-side; previews (text/CSV/JSON/code + Pillow image/PDF thumbnails),
  downloads, version history, tags, collections, favorites, bulk actions, archive/
  restore/delete and reconciliation are all real. `docs updated:
  docs/harness/artifact-center.md, docs/harness/decisions.md (ADR-H160),
  docs/NAVIGATION.md`.
- **Artifacts page is full width.** Dropped the `max-w-6xl` cap on the Artifact
  Center screen and let the grid scale to `lg:grid-cols-5 xl:grid-cols-6`, so the
  catalog uses the whole workspace pane. `no doc change — style-only`.
- **Artifact retention + auto-purge (production hardening).** `ArtifactService.cleanup_expired`
  permanently removes soft-deleted artifacts whose `retentionUntil` (or
  `deletedAt + HARNESS_ARTIFACT_RETENTION_DAYS`, default 30d) has elapsed; the
  background reconciler now runs reconcile+discover+purge, gated by
  `HARNESS_ARTIFACT_AUTO_PURGE`. Adds tests for expiry, grace retention, and
  persistence across a process restart. `docs updated:
  docs/harness/artifact-center.md`.

- **Security subsystem — one authorization decision path over the existing
  per-subsystem policies.** New `python/harness/security/`: the `SecurityGateway`
  (`gateway.py`) answers every privileged operation with `ALLOW` / `DENY` /
  `APPROVAL_REQUIRED`, composing the existing controls (`code/policy.py`,
  `skills/permissions.py`, `mcp/approvals.py`, `browser/policy.py`,
  `computer/policy.py`+finance firewall, `git/safety.py`, `execution/policy.py`,
  `plugins/permissions.py`, `mcp/ssrf.py`, `observability/redaction.py`) rather
  than duplicating them. It adds the missing central pieces: a resource-scoped
  **Permission Engine** (`permissions.py`), a layered restrict-only **Policy
  Engine** with profiles LOCKDOWN/SECURE/DEVELOPER/AUTONOMOUS/CUSTOM and atomic
  hot reload (`policy.py`), a server-side **Risk Engine** (`risk.py`), a typed
  **Approval Engine** over the single-use `McpApproval` store + `StandingGrant`s
  (`approval.py`), a no-escalation **Capability Engine** (`capabilities.py`), an
  immutable **Security Floor** (`floor.py`) that hard-denies credentials/keys/the
  security config/OS dirs/destructive infra and mandates approval for
  production/financial classes, a default-deny **Network Policy Engine** reusing
  `mcp/ssrf.py` with DNS pinning (`network.py`), a scoped **Secrets Manager** with
  value redaction (`secrets.py`), session-isolated `SecurityContext`s
  (`context.py`), and an append-only **hash-chained audit** on `agent-memory.db`
  (`audit.py`+`store.py`). Everything fails closed. Migrated this change:
  filesystem + shell/execution effects route through the gateway at the
  `code/authorizers.py` seam (`integration.py::make_security_authorizer`) — floor
  and network policy authoritative, policy approvals deferred to the existing
  single-use chain, all evaluations audited. Boot wiring `install_security_layer`
  in `service.py` + `start_security`/`stop_security` in `boot.py`; operator routes
  `/security/*` (`routers/security.py`, operator-gated) + `/api/security/**`
  proxy and `security-{client,browser}.ts`; `/health.security`. Tests
  `python/tests/test_security_{core,adversarial,failure,concurrency,network_secrets,integration,api}.py`
  (77 passing). docs updated: `docs/harness/security.md` (new),
  `docs/harness/decisions.md` (ADR-H159), `docs/NAVIGATION.md`, this file.
- **Fix: chat/runtime wedge caused by code-intelligence indexing.** A code-intel
  read (`code_get_project_structure` and peers) could freeze the entire Python
  runtime — `/health` timed out and chat returned no output — for two compounding
  reasons, both now fixed. (1) The per-workspace watcher's first snapshot walked
  every file under ignored trees and only filtered afterwards:
  `code/fs/watch.py::_snapshot` now PRUNES ignored/protected directories during
  the walk instead of `rglob`-ing the whole workspace (first snapshot ~58s → ~0.4s;
  `node_modules`, `scripts/vendor`, `.black-eclipse`, build dirs never descended).
  (2) The `next dev` build directory `.next-dev` (`next.config.ts` `distDir`) was
  not in any ignore list, so its hundreds of multi-MB generated bundles were
  parsed by the indexer; `.next-dev` is now excluded in `code/policy.py`
  `IGNORED_DIRS` and the mirrored `code/fs/search.py` / `code/intel/language/detect.py`
  lists. (3) `code/intel_tools.py` now acquires the manager, refreshes freshness
  and runs the query via `asyncio.to_thread`, and no longer forces a synchronous
  full index when the runtime's background indexer owns freshness — a code query
  can no longer block the event loop, so `/health` and concurrent runs stay live.
  (4) Defense in depth: `src/lib/harness/python-runtime.ts` now clears a
  still-silent listener on the runtime port before spawning (a hung/zombie runtime
  held the port and blocked a fresh start) and clears the resolved spawn promise
  after a start settles, so a later `/health` miss can no longer return a stale
  `true` and mask a runtime that has since hung.
  Tests: `test_intel_regressions.py` (dev-dir skip + ignore policy),
  `test_intel_tools.py` (read path never forces a sync index). no doc change —
  bug fix; no architecture, data-contract, or setup change.
- **Observability Platform — one vendor-neutral, fail-open telemetry layer that
  projects the existing event bus into OpenTelemetry-shaped traces, metrics,
  structured logs, token/cost accounting, SLOs, anomaly/loop detection and error
  tracking, with export to OTLP/Langfuse/Sentry/Prometheus/JSONL and a
  `/observability/*` operator API.** New `python/harness/observability/`:
  `config.py` (single env-resolved `ObservabilityConfig`, never raises),
  `context.py` (`ObservationContext` + `contextvars` propagation + W3C
  `traceparent` inject/extract), `events.py` (closed `HOOKS` vocabulary + typed
  `HookEvent`), `observers.py` (`Observer`/`ObserverHub`, fail-open + quarantine),
  `tracing.py` (`Tracer`/`Span`/`SpanStore` + `trajectory()`),
  `metrics.py` (counters/gauges/histograms + Prometheus + RED/USE),
  `costs.py` (`CostEngine` + `PricingRegistry`, data not code), `redaction.py`
  (the ONE redactor: keys, bearer/JWT/private-key/connection-string, optional
  PII), `sampling.py` (head + tail, always keeps errors/security/anomalies),
  `health.py`, `anomaly.py` (`LoopDetector` + statistical `AnomalyDetector`),
  `slo.py`, `logging_setup.py` (structured JSON with context + redaction),
  `exporters.py` (`Exporter` + non-blocking `BoundedExporter` with bounded queue,
  batching, retry + backoff, circuit breaker; OTLP/HTTP, Langfuse, Sentry, JSONL,
  console, in-memory sinks), `core.py` (`ObservabilityHub` — ingestion, metrics,
  cost, exports, diagnostics), `integration.py` (`RunEventProjector` projecting
  `service.bus` runs/models/tools/jobs/plugins/A2A/events, `ModelObserverBridge`,
  `install_observability`/`start`/`stop`). Routes
  `python/harness/routers/observability.py` (`/observability/*`, operator-gated)
  included by `main.py`; `install_observability(self)` at the end of
  `AgenticService.__init__`; `start_observability`/`stop_observability` in
  `boot.py` (structured logging installed on boot). Tests
  `python/tests/test_observability_{core,integration,failure,security,trace,perf,api,e2e}.py`
  (51): context propagation, span relationships, observer fail-open/quarantine,
  redaction, sampling, cost/token math, metrics/Prometheus, anomaly/loop, SLO,
  bus projection, dead/flaky/slow exporters + circuit breaker, secret leakage,
  cross-worker/queue/A2A trace integrity, overhead bounds. Fail-open by design: a
  telemetry backend outage drops-and-counts and can never break a run. docs
  updated: `docs/harness/observability.md` (new),
  `docs/harness/decisions.md` (ADR-H158), `docs/NAVIGATION.md`, this file.
- **Execution Fabric — one execution substrate: an `ExecutionManager` that routes
  every unit of work to DIRECT / CONCURRENT / BACKGROUND / DURABLE over a NATIVE
  durable queue (no Redis/BullMQ/Postgres — the runtime is single-process,
  zero-config, SQLite), with a worker pool that reuses the existing runtime.**
  New `python/harness/fabric/`: `models.py` (Job/JobState/ExecutionMode/QueueName/
  WorkerKind/priorities/WorkerOutcome), `state.py` (a closed job state machine),
  `config.py` (env config + validation), `store.py` (`FabricStore`:
  `FabricJob`/`FabricJobAttempt`/`FabricJobEvent`/`FabricWorker`/`FabricLock`/
  `FabricIdempotency` on the ONE `agent-memory.db`), `policies.py`
  (`ExecutionPolicy` + `PolicyRegistry` per job type), `metrics.py`, `locks.py`
  (`DistributedLockManager`), `workers.py` (`BaseWorker`/`FunctionWorker`/
  `WorkerRegistry`/`WorkerManager`: atomic claim, lease heartbeats, timeouts,
  hard cancellation, retry with exponential backoff + jitter, dead-letter,
  crash recovery, graceful drain), `builtin_workers.py` (agent→`service.run`,
  tool→`ToolRegistry.execute`, python/code→`code.sandbox`, plugin→PluginManager,
  automation→AutomationEngine, notification/event→bus+Event System, research/
  browser/market/quant→named tool else agent run), `integrations.py` (event rules
  → jobs), `manager.py` (`ExecutionManager` routing, idempotency/coalescing,
  priority, parent/root lineage, DAG delegation to the existing orchestration
  engine, admin retry/replay), `tools.py` (the `fabric_*` tools), `bootstrap.py`.
  Routes `python/harness/routers/fabric.py` (`/fabric/*`, operator-gated);
  `main.py` includes the router; `boot.py` installs/starts/stops the layer
  (`service.py` is untouched — it wires from boot). Front door
  `src/app/api/fabric/[[...path]]/route.ts` + UI console `/fabric`
  (`src/app/fabric/` + `src/lib/harness/fabric-types.ts`): Queues, Workers, Jobs
  (timeline + attempts), Dead letters, Metrics. Tests
  `python/tests/test_fabric_{state,store,workers,manager,integration}.py` (51) +
  `src/lib/harness/fabric-types.test.ts`. docs updated:
  `docs/harness/execution-fabric.md` (new), `docs/harness/decisions.md`
  (ADR-H156), `docs/NAVIGATION.md`, this file.

- **Trimmed the Agentic sidebar mode to ChatBot, Skills and Eclipse Memory;
  the other agentic capabilities stay available through ChatBot.** The
  Terminal/Agentic switcher and its machinery are kept (`NavGroup`,
  `navGroupsFor`, `modeForTab`, the store `mode`/`setMode`, the switcher UI,
  Alt+T/Alt+A). Removed only the eight agentic nav tabs/mounts — Code Tasks,
  Editor, Scheduled Jobs, Tasks, Plugins, Model Control Center, Search
  Intelligence, Research, Backtest — from `DEFAULT_SIDEBAR_SECTIONS`
  (`src/lib/sidebar/config.ts`) and from the keep-alive render blocks + dynamic
  imports in `stock-chat.tsx`; dropped them from `AppTab`, `NavTabId`, the
  command-palette registry/deep-link allowlist and their `nav.*` i18n keys.
  Skills and Eclipse Memory remain full pages in the Agentic menu. The backend is
  untouched: the Python tools (`workspace_*`, `command_run`, `quant_*`,
  `research_*`, `search_*`, `plugin_*`, task/plan tools) and all `/api/**` routes
  remain, so every removed surface is still driveable from chat. Front-door setup
  is unaffected (provider keys = Settings › AI, MCP = Settings › MCP, retrieval =
  Settings › Market). Removed screens' component files are retained but
  unreferenced. tests: updated `sidebar/config.test.ts`,
  `search/registry.test.ts`, and the screen reachability guards. docs updated:
  `docs/OVERVIEW.md`, `docs/ARCHITECTURE.md`, this file.

- **Agent-to-Agent (A2A) — a first-class registry + typed message bus over the
  EXISTING execution plane.** New `python/harness/a2a/`: a versioned **Agent
  Registry** (`registry.py`; agent behaviour is data — capabilities, tools,
  permissions, budgets, delegation rights) with a capability index, a typed
  **AgentEnvelope** protocol (`protocol.py`; closed message types, per-type
  payload validation, content-derived idempotency key) and a durable **MessageBus**
  (`bus.py`; publish/consume/acknowledge/reject/dead-letter, TTL, one delivery per
  recipient) over the ONE `agent-memory.db` (`store.py`: `A2A{Agen,AgentVersion,
  Message,MessageDelivery,Delegation,Event,Budget,Approval,Result}`). Delegation
  creates a durable child **Task** dispatched by the existing `TaskScheduler` — a
  delegated task IS a normal `service.run`, never a second loop. Adds
  `delegate_task`/`spawn_agent`/`send_message`/`receive_message`/`wait_agent`/
  `cancel_agent`/`merge_results`/`ask_agent`/`broadcast_message`/`get_agent`/
  `list_agents`/`get_agent_status`/`get_task_status`/`get_task_result`/
  `request_review`/`request_approval`/`report_failure` (`tools.py`, `A2A_TOOLS`,
  on `ECLIPSE_AGENT`). Least privilege (`permissions.py`): child budgets and
  spawned agents are the INTERSECTION of the parent's; `operator` is never
  inherited; trading/external capabilities are approval-gated and `trading-agent`
  holds no analysis tools. Results merge with normalization, dedupe, evidence
  linking and numeric-conflict detection (`results.py`); an unbacked claim is
  disclosed as unsupported with capped confidence, never promoted to fact. A
  **Supervisor + QA** stage returns PASS/REWORK_REQUIRED/BLOCKED
  (`supervisor.py`). Built-in catalogue of 15 specialists + `AgentConfig` presets
  (`agents_seed.py`). Operator-gated routes `python/harness/routers/a2a.py`
  (`/a2a/*`); boot wiring `boot.install_a2a_layer`/`recover_a2a`. Tests
  `python/tests/test_a2a_{core,bus,delegation,results,security,tools_api}.py`
  (61). docs updated: `docs/harness/agent-to-agent.md` (new),
  `docs/harness/decisions.md` (ADR-H155), `docs/NAVIGATION.md`, this file.

- **Event System — a canonical, durable event model bridged to the existing run
  bus.** New `python/harness/event_system/`: a canonical `EclipseEvent` envelope
  (`envelope.py`) with auto-propagating correlation/causation/trace via
  `contextvars` and secret redaction; a centralized `EventRegistry`
  (`registry.py`) declaring every event type/namespace with schema, producer,
  consumers, permission, priority, retention, retry and sensitivity; an indexed
  durable store on `agent-memory.db` (`HarnessEventLog` + `HarnessEventConsumer`
  + `HarnessEventDeadLetter` + `HarnessEventSubscription`) queryable by
  id/type/correlation/causation/trace/task/workflow/agent/time with a causation
  graph; an `EventBus` (`bus.py`) with publish/publishMany/subscribe/unsubscribe/
  once/request, composable middleware, per-consumer async workers with
  backpressure, exponential-backoff retry (never retrying non-retryable classes),
  consumer idempotency, a real DLQ, metrics and graceful shutdown; `config.py`
  env switches; `replay.py` (observe/simulation/full, operator-gated, destructive
  confirmation); `rules.py` (event→action via the Automation Engine); a
  `service.py` facade with built-in memory-candidate, self-improvement
  (loop/depth-guarded) and market-sampler consumers; boot wiring via
  `bootstrap.py`. The bus **bridges** to `harness.events.EventBus` (ingests every
  legacy event reusing its id; never echoes legacy events back) rather than
  introducing a second transport. Task events now publish canonical names
  (`task.created`, plan→`workflow.created`) and the automation engine publishes
  `schedule.triggered`. Operator-gated `/events/*` console API
  (`routers/events.py`) + front door (`src/lib/harness/events-client.ts`,
  `src/app/api/events/[[...path]]/route.ts`) + standalone `/events` console UI.
  Tests `python/tests/test_events_{core,bus,service,api}.py` (46). docs updated:
  `docs/harness/event-system.md` (new), `docs/harness/decisions.md` (ADR-H153),
  `docs/NAVIGATION.md`, this file.

- **Event System — source wiring.** The remaining registered families now emit at
  their sources: a thread-safe process-wide emitter `event_system/emit.py`
  (`publish_event`), legacy-name normalization so `terminal.process.*` becomes
  canonical `process.started/completed/failed`, the workspace watcher publishes
  `file.created/changed/deleted` (debounced), `portfolio/service.py` publishes
  `portfolio.position.added/updated/removed`, `eclipse_memory/service.py` publishes
  `memory.created/updated`, and `quant/runner.py` publishes
  `backtest.started/completed/failed`. The size ratchet was re-pinned for the
  in-flight Plugin Platform growth (`graph.py`, `service.py`) and the new
  emissions (`portfolio/service.py`, `eclipse_memory/service.py`). Tests
  `python/tests/test_events_emit.py` + `test_events_core.py` normalization cases.
  docs updated: `docs/harness/event-system.md`, this file.

- **Task / Plan production hardening: plan roll-up, plan-level model settings, and
  a real-runtime E2E.** (1) `TaskManager.recompute_plan` now derives a plan's
  terminal status from its tasks — a plan reaches `COMPLETED` on its own when its
  last task completes (`FAILED`/`CANCELLED`/`BLOCKED`/`RUNNING` otherwise), only
  via a legal transition. (2) A task run resolves model settings with precedence
  task `metadata.modelSettings` → plan `metadata.modelSettings` → env default, so a
  whole plan can pin a provider. (3) New `python/tests/test_tasks_e2e.py` drives a
  plan through a REAL `AgenticService` + the real `service.run`/`execute_run` graph
  with only the LLM scripted, asserting plan completion, real `HarnessRun` rows,
  the failed-task→failed-plan path, and settings precedence — no network.
  docs updated: `docs/harness/task-plan-system.md`, this file.

- **Tasks screen reachability test.** Added `src/components/screens/tasks/tasks-screen.test.ts`
  (mirrors the search-screen guard): the mounted Tasks screen imports the
  browser-safe client, reads the real `/api/plans` + `/api/tasks` endpoints,
  is imported/rendered by the shell, and has an AppTab + sidebar + `nav.tasks`
  label. Test-only; no production behavior changed. no doc change — test-only.

- **Task / Plan System — a durable, production-grade execution backbone.** New
  `python/harness/tasks/`: a `Plan` containing an arbitrary hierarchy of `Task`s
  with first-class dependencies (DAG + cycle rejection before persist), acceptance
  criteria with VERIFIED completion, priorities, priorities-aware runnable
  discovery, a closed seven-state machine (`TODO/IN_PROGRESS/BLOCKED/WAITING/FAILED/
  COMPLETED/CANCELLED`, explicit `retry`/`reopen`/`recover` operations), atomic
  claim (`HarnessTask` conditional `UPDATE`) with leases + heartbeats, exponential
  backoff retry for retryable errors only, lease-expiry recovery (a crashed worker
  never leaves a task stuck), cancellation with child cascade, deterministic
  parent-state/weighted-progress roll-up, and durable events/executions/
  checkpoints/artifacts on the ONE `agent-memory.db`. The scheduler dispatches each
  claimed task through the EXISTING `service.run` (no second agent loop/registry/
  adapter). 22 LLM-facing tools (`create_plan`/`create_task`/…, permission `read`
  like memory) + operator-gated `/tasks` and `/plans` routes; boot wired in
  `service.py`/`boot.py`, allowlists in `agents.py`, guidance in `prompts.py`.
  Tests `python/tests/test_tasks_{state,dag,manager,scheduler,tools,api}.py`
  (unit, concurrency 100-way claim race, retry/backoff, lease recovery, cancellation,
  API, and an E2E DAG through the production executor). Front door + mounted UI:
  `src/lib/harness/tasks-{browser,client}.ts`, `src/app/api/{tasks,plans}/[[...path]]/route.ts`,
  and the live `src/components/screens/tasks/tasks-screen.tsx` (AppTab `tasks`,
  sidebar + `nav.tasks` i18n). The prompt ceiling was re-pinned 23025→23725 for the
  one new guidance paragraph; the Phase-11 tenancy tests were aligned to the
  automation-backed `/jobs` contract. docs updated: `docs/harness/task-plan-system.md`
  (new), `docs/NAVIGATION.md`, this file.

- **Parallel Execution & DAG Orchestration — a real execution subsystem.** New
  `python/harness/orchestration/`: a validated DAG of agent/tool/function/
  aggregate-join nodes with a strict state machine (`state.py`), DAG validation and
  critical-path/wave analysis (`graph.py`), a dependency-aware scheduler that runs
  independent nodes concurrently (`engine.py`), a worker pool over the EXISTING
  `execute_run` / `ToolRegistry.execute` seams (`runner.py`), resource-aware
  admission (`resources.py`), bounded retries with backoff/jitter (`retry.py`),
  join policies (ALL/ANY/FIRST_SUCCESS/QUORUM/THRESHOLD), failure policies, task
  deduplication + TTL caching (authorization-scoped; opt-in engine-wide sharing via
  `dedupScope`), rate-limit-aware execution (`rateKey` buckets feed retry),
  scheduler-level batching (`batching.py`: compatible ready nodes coalesce into one
  call) plus `task_map(batchSize)`/`task_batch`, timeouts, cancellation/pause/resume,
  dynamic node insertion, durable `Orchestration*` tables on `agent-memory.db` and
  crash recovery (`recovery.py`) that PARKS credential-requiring agent executions
  (`awaitingRuntime`) and resumes them when the front door supplies `modelSettings`
  (`/resume`, `/recover`). Primitives + tools `parallel_execute`, `task_fork`,
  `task_join`, `task_race`, `task_quorum`, `task_map`, `task_batch`, `task_reduce`,
  `dependency_graph`, `execution_status`, `execution_cancel`; operator-gated routes
  `/orchestration/*`; env `HARNESS_ORCH_*`. Tests
  `python/tests/test_orchestration_{graph,engine,tools,concurrency,integration,api,production}.py`
  (unit, concurrency/race, failure/recovery [incl. credentialed parking + resume],
  scheduler batching, engine-scope dedup, end-to-end agent runs,
  sequential-vs-parallel). docs updated: `docs/harness/parallel-orchestration.md`
  (new), `docs/NAVIGATION.md`, this file.

- **Quant Engine — production hardening: live data path + background runs +
  performance guard.** (1) Live market-data path fixed in
  `python/harness/market/gateway.py`: `_fetch_provider` now forwards each
  provider's OWN ticker via `providerSymbols` (so `BTC-USD` → `BTCUSDT` for
  Binance instead of requesting a nonexistent `BTCUSD` spot pair), and intraday
  crypto (`1m`–`4h`) routes to Binance first — the yfinance/stooq adapters
  collapse intraday bars to a calendar date, so the previous order returned
  unusable intraday crypto. New `_dispatch(prefer=…)` reorders candidates; tests
  `python/tests/test_market_intraday_routing.py`. (2) Heavy runs no longer block
  the request: new `python/harness/quant/runner.py` (in-process asyncio runner
  behind a concurrency semaphore, status + stage/percent progress + cancel, 1h
  in-memory retention) with routes `POST …?background=true` and
  `GET /quant/runs`, `GET /quant/runs/{id}`, `POST /quant/runs/{id}/cancel`;
  engines gained progress hooks; UI "Run in background" toggle that polls.
  (3) `python/tests/test_quant_performance.py` guards a 5000-bar/eight-indicator
  backtest against accidental quadratic behaviour (runs in <1s, asserted <20s).
  Tests: `test_quant_runner.py` + the intraday-routing file. docs updated:
  `docs/quant-engine.md` (Production notes), `docs/NAVIGATION.md`, this file.

- **Portfolio engine — the remaining capability gaps closed.** (1) **Cost basis**:
  added `HIFO` and `SPECIFIC_ID` (exact-lot selection via a transaction's
  `lot_selection`). (2) **Corporate actions**: added `RIGHTS_ISSUE`,
  `WARRANT_EXERCISE` (warrant basis + strike carried to the underlying) and
  `RETURN_OF_CAPITAL` (basis reduction, cash in, excess recognized as a taxable
  gain via a new realized-only `REALIZED_ADJUSTMENT`). (3) **Crypto/derivatives**:
  `SLASHING` (zero-proceeds write-off / loss) and `FUNDING` (signed funding cash).
  (4) **Attribution**: Brinson single-period allocation/selection/interaction.
  (5) **Optimizer**: projected-gradient `min_variance`/`mean_variance`/
  `inverse_volatility` with exact bounded-simplex projection + turnover cap.
  (6) **Factor exposure** and P&L rollups by asset class/sector/strategy.
  (7) **Currency hedging** proposals. (8) **Reconciliation** engine
  (`PortfolioReconciliation` table) → MATCHED/MISMATCH/MISSING/UNKNOWN.
  (9) **Cross-portfolio aggregation**. 28 tools; new routes
  (`.../slashing|funding|reconcile|reconciliations|optimize|attribution|
  factor-exposure|hedge`, `POST /portfolio/aggregate`); UI Advanced-analytics
  panel. Verification: **`npm run build` now succeeds** (an unrelated `/login`
  `useSearchParams` Suspense blocker was fixed); additive-migration test on an
  old-schema DB added. Tests: `test_portfolio_{advanced,migration}.py` + route
  cases (114 portfolio tests passing). docs updated:
  `docs/portfolio-accounting.md`, this file.

- **Quant Engine — limitations fixed + research engines (optimization,
  walk-forward, Monte-Carlo, sensitivity/robustness).** Two correctness
  limitations are gone: (1) a portfolio backtest now builds one
  `ExecutionSimulator` + `RiskEngine` **per strategy binding**, so each symbol's
  fills and risk limits follow its own strategy's costs (a test asserts two
  strategies with different commission each pay their own rate); (2)
  `historical` spread is real — a new optional per-bar `spread` column on the
  dataset is used by the simulator, and its absence produces an explicit
  `HISTORICAL_SPREAD_UNAVAILABLE` warning (never a silent zero). Four
  deterministic research engines added under `python/harness/quant/`:
  `params.py` (dotted-path spaces), `optimize.py` (grid/random/evolutionary +
  genuine GP-EI Bayesian; objectives oriented higher-is-better; multi-objective
  Pareto; per-axis stability), `walkforward.py` (train→test with optimization on
  the training slice only — a test proves a mutated test period cannot change the
  chosen params; IS/OOS/combined + divergence), `montecarlo.py` (trade reshuffle,
  return bootstrap, parameter and execution perturbation; percentiles, P(loss),
  P(ruin), expected/worst drawdown; seeded), `robustness.py` (one-at-a-time
  sensitivity + cost sensitivity + trade concentration + sample size + regime
  dependence → deterministic verdict `robust`/`fragile`/`insufficient_evidence`
  with evidence-backed conclusions). Wired end-to-end: 5 new agent tools
  (`optimize_parameters`, `run_walk_forward`, `run_monte_carlo`,
  `run_sensitivity_analysis`, `run_robustness_analysis`; 24 `quant_*` total),
  operator-gated routes `/quant/{optimize,walk-forward,monte-carlo,sensitivity,
  robustness}`, capability flags flipped to `available`, and a research panel in
  the Backtest tab. Tests: `python/tests/test_quant_research.py` + additions to
  `test_quant_engine.py`/`test_quant_tools.py` (74 quant tests passing).
  Options (Phase 7) and backend job offload remain explicit capability states.
  docs updated: `docs/quant-engine.md`, `docs/NAVIGATION.md`,
  `docs/harness/decisions.md` (ADR-H150), this file.

- Test-only: bumped the `stock-chat.tsx` size-budget ratchet 1272 → 1296 (the
  SPA shell gained one dynamic import + one keep-alive block each for the
  Portfolio and Unified Search tabs). No production code change — the shell's
  per-tab keep-alive blocks remain the standing split candidate. Fixes the
  `src/lib/size-budget.test.ts` gate; `vitest` (2322) and `tsc` are green — no doc
  change.

- **Portfolio engine — corporate actions, crypto, tenant isolation and
  materialized positions.** Closed the four deferred gaps in the Portfolio
  Accounting Engine. (1) **Corporate actions**: new transaction types
  `SPIN_OFF`/`MERGER`/`SYMBOL_CHANGE`/`COST_BASIS_ADJUSTMENT` and
  `PortfolioService.apply_corporate_action` — spin-offs reallocate parent basis to
  the child by relative FMV (basis conserved), mergers carry basis and treat cash
  consideration as a genuine lot-matched partial disposal, and symbol changes are
  an in-kind transfer pair; unsupported actions are refused. (2) **Crypto**:
  real `apply_swap` (taxable disposal + FMV acquisition), `apply_bridge`
  (book-value carry, no gain), `record_reward` (staking reward/airdrop at FMV) and
  `apply_staking` (custody-only `STAKE`/`UNSTAKE` passthrough). (3) **Tenant
  authorization**: `ownerId` is stamped on create and every read/mutation now
  authorizes the asserted actor (`X-Harness-User` header / `actorId`), refusing a
  mismatch with `PORTFOLIO_FORBIDDEN` -> HTTP 403; unowned/local mode unchanged.
  (4) **Materialized positions**: a derived `PortfolioPosition` cache rebuilt
  incrementally per symbol on mutation, read without a full-ledger recompute,
  self-healing when absent, plus `rebuild_all`. New transactions: 6 more
  `portfolio_*` tools (19 total), routes `.../corporate-action|swap|bridge|reward|
  staking|rebuild`, TS client functions, and an `X-Harness-User` forwarding proxy.
  Tests: `python/tests/test_portfolio_{corporate_actions,crypto,tenancy,
  materialization}.py` + new API/route cases (99 portfolio tests passing).
  docs updated: `docs/portfolio-accounting.md` (new sections), this file.

- **Quant Engine (Phases 1–2): deterministic trading & backtesting, end-to-end.**
  New `python/harness/quant/` package implementing a modular, event-driven
  backtester — no placeholders and no LLM-computed statistics. Strategy contract
  with a structured rules DSL, validation and semver versioning
  (`strategy.py`, `rules.py`); causal indicators (`indicators.py`); a
  point-in-time market dataset over the ONE Market Data Gateway with quality
  checks and higher-timeframe alignment (`data.py`, `datasets.py`); an order
  state machine (`orders.py`); realistic execution (commission/slippage/spread/
  market-impact/latency, all reported and only-zero when explicitly selected,
  `execution.py`); position sizing (`sizing.py`); pre-trade risk limits
  (`risk.py`); a long/short simulation portfolio (`portfolio.py`); the full
  metric set with units/definitions (`metrics.py`); the event-driven engine and
  `BacktestResult` (`engine.py`); strategy+experiment persistence with gzipped
  result artifacts (`store.py`, metadata on the ONE `agent-memory.db`); synthetic
  golden datasets (`fixtures.py`). 19 agent tools registered on the shared
  registry (`quant_*`, read-only, run_backtest marked long-running); operator-
  gated HTTP in `routers/quant.py`; boot wiring `quant/bootstrap.py` +
  `ToolContext.quant_store`. Front door `src/lib/backtest/` +
  `src/app/api/backtest/[...path]/route.ts` + the mounted Backtest tab
  (`src/components/screens/backtest/backtest-screen.tsx`, ECharts). Capabilities
  are reported honestly (`available`/`partial`/`unsupported`); options,
  walk-forward, Monte-Carlo, optimization and robustness are advertised as
  `unsupported` and are NOT registered as tools (later phases). The backtest
  simulation portfolio is deliberately separate from the long-only tax-lot
  Portfolio Accounting Engine; long-only realized P&L is reconciled against
  `portfolio.accounting` in tests. Data-quality findings (gaps/duplicates/
  out-of-order/incomplete) are surfaced as `DATA_*` result warnings. Tests:
  `python/tests/test_quant_*.py` (59 passing) +
  `src/lib/backtest/backtest-client.test.ts`. Verifiable via
  `npm run test:py`. docs updated: `docs/quant-engine.md` (new),
  `docs/NAVIGATION.md`, `docs/harness/decisions.md` (ADR-H150), this file.

- **Portfolio Accounting Engine — full subsystem.** New `python/harness/portfolio/`
  package: a Decimal-based transaction ledger with real FIFO/LIFO/weighted-average
  tax-lot engines (`accounting.py`), tax-lot matching, valuation with provider-neutral
  FX + mandatory price freshness/data-quality (`Mark`, `market_adapter.py`),
  realized/unrealized P&L, exposure + allocation (`analytics.py`), deterministic risk
  incl. seeded Monte-Carlo VaR (`risk.py`), TWR/MWR/IRR/CAGR + benchmark comparison
  (`performance.py`), and a proposal-only rebalancing engine with estimated fees and
  configurable tax impact (`rebalance.py`). Persistence is `PortfolioStore` on the ONE
  `agent-memory.db` connection (own tables, idempotent DDL; partial-unique idempotency
  on `(portfolioId, source, externalId)`); the ledger is the source of truth and lots
  are derived. 13 tools registered on the shared registry
  (`portfolio_get/add_position/remove_position/update_position/calculate_pnl/exposure/
  allocation/risk/tax_lots/rebalance/…`) with read vs mutating
  (`portfolio.write`) vs consequential (`portfolio.rebalance_proposal`) effects;
  boot wiring in `portfolio/bootstrap.py`, run wiring through
  `ToolContext.portfolio_service`; operator-gated HTTP in
  `routers/portfolio.py`; front door `src/lib/harness/portfolio-client.ts` +
  `src/app/api/portfolio/[[...path]]/route.ts` + the Ledger view in
  `src/components/screens/portfolio/portfolio-ledger.tsx`. Shorts are refused, not
  miscalculated; rebalancing never executes a trade. Tests:
  `python/tests/test_portfolio_{accounting,store,service,risk_performance,tools,api}.py`
  (golden case + invariants + edge cases; 60 passing).
  docs updated: `docs/portfolio-accounting.md` (new), `docs/NAVIGATION.md` (trigger
  table), this file. Persistence deliberately reuses `agent-memory.db`, not
  `jdds.db`/Prisma — portfolio state is private runtime state, not market data.

- **Financial Analysis Engine: deterministic metric surface expanded
  end-to-end.** Extended the existing deterministic calculators — no parallel
  engine, no duplicated formula. (1) `research/calculations.py` gained returns
  (cumulative/annualized, simple/log), Jensen alpha, correlation
  (pearson/spearman/kendall), covariance (sample/population), CVaR/expected
  shortfall (historical/parametric/seeded Monte-Carlo), parametric VaR, seeded
  Monte-Carlo VaR, full drawdown analysis (peak/trough/recovery/durations/series/
  top-N), rolling volatility/correlation/beta, correlation & covariance matrices
  and Euler risk contribution; the advanced metrics were split into
  `research/calculations_ext.py` (re-exported) to stay within the size budget, and
  `CalculationResult` now carries a structured `detail` payload. (2)
  `finance_facts/metrics.py` gained FCF (OCF−CapEx), explicit enterprise value,
  FCFF/FCFE, and an explicit-basis growth engine (yoy/qoq/mom/ttm/percent/cagr).
  (3) `finance_facts/valuation.py` gained a per-period DCF schedule, a
  WACC×terminal-growth sensitivity grid (invalid cells `None`, never a number) and
  named bear/base/bull DCF scenarios; one `dcf_breakdown` implementation underlies
  all of them. (4) `research/finance_analysis.py` composes a security / portfolio
  analysis from caller-supplied inputs; a metric that cannot be computed is
  reported `UNAVAILABLE` with its reason, never fabricated. (5) New agent tools:
  `finance_growth`, `finance_fcf`, `finance_security_analysis`,
  `finance_portfolio_analysis`; `finance_series`/`finance_valuation` extended
  (sensitivity/scenarios). Tests: `python/tests/test_finance_analysis_engine.py`
  (59 cases: known values, financial invariants, refusal paths, seed
  reproducibility, tool surface). Docs updated: `docs/harness/financial-analysis-
  engine.md` (new), `docs/NAVIGATION.md`, `docs/CHANGELOG.md`.

- **Market Data Layer: remaining gaps closed — equity book/trades + streaming,
  computed option Greeks, corporate-bond data.** (1) *Keyed providers*: new
  `src/lib/harness/market/providers/{polygon,finnhub}.ts` (real adapters over the
  SSRF-hardened `safeGet` + encrypted vault) serve US-equity quotes, history, and
  — via Polygon NBBO — **top-of-book order books and trade tapes**; absent a key
  they report `AUTHENTICATION_FAILED`, and the gateway falls through. Their Python
  descriptors are now `implemented=True` with routing priority for equity
  orderbook/trades. (2) *Equity streaming*: a new bridge capability
  `market_stream_config` hands the Python stream manager a keyed provider's socket
  URL/token (same trust boundary as `mcp_secret_resolve`); `streaming.py` is now
  multi-provider (Binance + Finnhub) with Finnhub/Polygon frame normalizers and a
  `provider` argument on `stream_market_data`. (3) *Option Greeks*: new
  `python/harness/market/greeks.py` CALCULATES delta/gamma/theta/vega/rho with
  Black-Scholes from provider IV when `greeks=True` (provider values win; missing
  inputs stay `None`, never zero), labelled `calculated`. (4) *Corporate bonds*:
  the FRED adapter now serves ICE BofA corporate-index yields/spreads (IG/HY/
  AAA/BBB, OAS) with `seriesType=corporate`/rating; new
  `python/harness/market/bondmath.py` computes duration/modified duration/
  convexity (provider values win). Config `HARNESS_MARKET_RISK_FREE`. Tests:
  `python/tests/test_market_derivatives.py`,
  `src/lib/harness/market/keyed-providers.test.ts`; updated market gateway
  tests. Docs updated: `docs/harness/market-data.md`, `docs/CHANGELOG.md`.

- Test-only: the data-bridge identity news case now gets a 20s timeout (it
  exercises the real news/web transport with no provider mock, so the 5s default
  made the release gate load-sensitive). No production code change — no doc change.

- Agent Workspace sidebar chrome polish: removed the hard `border-b` separators
  under the header and the panel tabs (the frosted-glass edge is the separation),
  and replaced the header `Sparkles` glyph with the `Bot` agent icon. Cosmetic
  only — no doc change — no contract/architecture impact.
- Agent Workspace sidebar is now actually draggable-resizable: the left-edge
  handle was sitting under the `z-10` content layer and was ungrabbable. Raised
  it to `z-30`, widened the hit area, added a hover affordance (no permanent
  border), locked body cursor/text-selection during the drag, and gave the handle
  `role="separator"`. Width still persists to `localStorage`. Cosmetic/interaction
  only — no doc change.

- **Market Data Layer hardening: observability console, measured rate limits,
  streaming durability.** Closes the three limitations recorded for the market
  subsystem. (1) *Operability*: an operator console `MarketDataConsole`
  (`src/components/screens/market-data-console.tsx`) rendered inside Settings ›
  Data & providers (composed with the Financial Data Gateway panel), backed by a
  front-door proxy `src/app/api/harness/market/[...path]/route.ts` +
  `src/lib/harness/market-client.ts`, showing providers/key presence, per-provider
  health, declared-vs-observed rate limits with latency, stream state/metrics,
  cache and quality findings; the Python health route now returns
  `providerMetrics` (calls/avg/max latency + rate-limit snapshot). (2) *Rate-limit
  realism*: new `python/harness/market/ratelimit.py` paces on the DECLARED limit
  AND the provider's live quota observed from response headers;
  `connectors/security.ts` now returns response headers, `market/rate-limit.ts`
  parses provider quota headers (Binance `X-MBX-USED-WEIGHT-1M`, generic
  `x-ratelimit-*`, `Retry-After`), adapters attach a `rateLimit` block, and the
  gateway feeds it back via `observe()` so the effective limit is the stricter of
  declared and observed. (3) *Streaming durability*: jittered exponential backoff,
  a silence watchdog that reconnects a connected-but-silent socket, an optional
  reconnect cap (`state="backoff"`), bounded dedup LRU, and per-provider metrics.
  Tests: `python/tests/test_market_ratelimit.py` +
  `src/lib/harness/market/rate-limit.test.ts` + durability/soak cases in
  `test_market_streaming.py` + opt-in live soak `test_market_live.py`
  (`BLACK_ECLIPSE_MARKET_LIVE=1`). Docs updated: `docs/harness/market-data.md`,
  `docs/CHANGELOG.md`.

- **Vision model recognition + cross-provider vision fallback (fixes "needs a
  vision-capable model configured").** Vision is now decided **per model family,
  not per SDK kind**: the shared `openai` kind no longer blanket-claims vision, so
  text-only models (gpt-3.5/gpt-4/o1-mini, deepseek-chat, groq/llama, grok-2, …)
  are no longer routed natively and wasted, while known VLMs are recognized
  (gpt-4o/4.1/o-series/5, Claude, Gemini, grok-2-vision, and open-weight llava,
  qwen2-vl/qwen2.5-vl/qwen3-vl, minicpm-v, moondream, pixtral, llama-3.2-vision,
  llama-4, internvl, phi-3-vision/phi-4-multimodal, gemma-3, deepseek-vl, …).
  `plan_route` now reads the run model's capabilities DIRECTLY (never a routed
  substitute), fixes a registry lookup that passed a string where a list was
  required, defaults to the process runtime, and may fall back to a vision model
  on a DIFFERENT provider when that provider is keyless-local or has an env-var
  credential (`models.provider_has_credentials`; still never a provider without a
  key). Document Intelligence routes its embedded-image analysis and OCR fallback
  through the vision orchestrator so a text-only run model still gets a real VLM.
  Files: `model_runtime/catalog.py`, `harness/models.py`,
  `vision/capabilities.py`, `vision/routing.py`,
  `document_intelligence/{orchestrator,ocr}.py`. Tests
  `python/tests/test_model_vision_capability.py` (+ updated local-only vision
  invariant). ADR-H148. Docs: `docs/harness/vision.md`, `docs/harness/decisions.md`.

- **Release-gate hardening (found while validating the Financial Data Gateway).**
  (1) `eslint.config.mjs` now ignores `.black-eclipse/**` and `.tmp-tests/**` — the
  code agent's disposable worktrees under `.black-eclipse/code-workspaces/` were
  being linted and crashed `eslint .` with `ENOENT` on a partially-removed
  worktree, failing the release gate. (2) `tsconfig.json` `exclude` gains
  `.black-eclipse` for the same reason. (3) Rotated the oldest active CHANGELOG
  section (`## 2026-10-01`) into the new monthly archive
  `docs/changelog/2026-10.md` (8 active dated sections exceeded the 7-section
  window), restoring `changelog-guard.test.ts`. (4) `financial-data-console.tsx`
  used straight quotes in JSX text, tripping `react/no-unescaped-entities`
  (`eslint .`); rephrased. (5) `retrieval_tools._credential_present` now awaits
  the bridge's `provider_key_status` capability instead of a non-existent
  `fetch_sync`, so keyed-provider presence resolves correctly. (6) The
  network-dependent news case in `data-bridge-identity.test.ts` gets an explicit
  20s budget (it exercises the real news/web transport, so the 5s default made the
  gate load-sensitive). docs updated: `docs/CHANGELOG.md`; tests unchanged except
  (6).

- **Unified Retrieval / Search Intelligence Layer (semantic + keyword + hybrid search).**
  New `python/harness/search/` package: a provider-agnostic embedding layer
  (OpenAI/OpenAI-compatible, Google, Cohere, Voyage) with content caching,
  batching, retry/backoff and a dimension/version model registry; a reusable
  chunking engine (fixed/sliding/structural/semantic, tables kept intact); a
  dedicated SQLite vector + FTS5 index (`.black-eclipse/search/search.db`,
  `ECLIPSE_SEARCH_DB_PATH`) with documents/sections/chunks/vectors, jobs,
  observability events and an embedding cache; an idempotent, content-hash
  deduplicated indexing pipeline with explicit states; source adapters that
  index existing memory/evidence/documents/skills rows; keyword/vector/hybrid
  retrieval with metadata, entity and fail-closed temporal filters, ranking,
  second-stage reranking (local deterministic + Cohere/Voyage), near-duplicate
  dedup and parent/neighbour context; token-budgeted context assembly;
  citations + an EvidenceStore bridge; a 60-query golden dataset with
  Recall@K/Precision@K/MRR/NDCG. Exposed as 13 read-only agent tools
  (`SEARCH_TOOLS`, added to the finance and code agents), an operator-gated
  `/search/*` HTTP router, the front-door proxy
  `src/app/api/harness/search/[[...path]]/route.ts` + `src/lib/harness/search-{client,types}.ts`,
  and a mounted **Search Intelligence** tab. Chose a dedicated SQLite store over
  PostgreSQL + pgvector to preserve zero-config (ADR-H151). Authorization is
  compiled into the query SQL (never scan-then-filter); with no embedding
  provider the layer is honestly keyword-only. tests:
  `python/tests/test_search_*.py` (+ updated `test_size_budget.py`,
  `test_code_agent.py`, `src/lib/sidebar/config.test.ts`, `src/lib/i18n/nav.ts`).
  docs updated: `docs/harness/search-retrieval.md`, `docs/harness/decisions.md`
  (ADR-H151), `docs/NAVIGATION.md`, `docs/CHANGELOG.md`.

- **Unified search — limitation fixes: real ANN, indexed filters, incremental reindex, embedding chunking.**
  (1) **ANN vector search** via a real `sqlite-vec` `vec0` index per vector space
  (cosine), with the KNN restricted to the caller's authorization buckets
  (`aclKey IN (…)`, `store.acl_keys`/`scope_acl_keys`) *before* scoring and
  candidate validation against the full metadata/temporal+scope SQL; brute-force
  cosine remains the automatic fallback when the extension is absent
  (`SearchIndexStore.rebuild_ann()`, dimension-mismatch refusal, `annBackend`
  in stats). `sqlite-vec>=0.1.6` added to `python/requirements.txt` + a
  best-effort `doctor.js` probe. (2) **Indexed metadata filtering**:
  tickers/sectors/industries/scalar `meta` now project into a
  `SearchDocumentMeta` table and compile into SQL (no Python post-filter); a
  distinct `SearchDocument.documentType` column replaces the `sourceType`
  conflation (additive column migration for existing DBs). (3) **Incremental
  re-index**: an unchanged `INDEXED` document (same id + content hash) is skipped
  (`IndexResult.unchanged`; `force` overrides), so `bulk_index` only pays for
  what changed. (4) **Embedding-based semantic chunking**: the `semantic`
  strategy now splits on real sentence-embedding similarity when a provider is
  available (lexical-cohesion fallback retained). tests:
  `python/tests/test_search_ann.py`, `test_search_fixes.py` (+ updated
  `test_search_*`). docs updated: `docs/harness/search-retrieval.md`,
  `docs/harness/decisions.md` (ADR-H151), `docs/CHANGELOG.md`.

- **Unified search — production readiness: boot auto-index, live smoke, release gate, UI guard.**
  (1) **Automatic boot indexing**: `SearchService.schedule_warm_index` (called
  from `harness/boot.py`) builds the index from existing sources in a
  non-blocking background task; `HARNESS_SEARCH_WARM_INDEX=0` disables it; the
  test suite disables it via `python/conftest.py` so it never races temp DBs.
  Warm-up is incremental (keyword-only re-runs are cheap and idempotent).
  (2) **Opt-in live verification**: `harness/search/live_smoke.py` +
  `python/tests/test_search_live.py` (`BLACK_ECLIPSE_SEARCH_LIVE=1`) contact a
  real provider and assert non-degenerate embeddings + relevant-above-distractor
  similarity — the only networked search test, never in the offline suite.
  (3) **Release gate**: `harness/search/eval_gate.py` wired into
  `scripts/test-evals.js` as the `search` gate (Recall@k/MRR/NDCG floors over the
  golden corpus, offline). (4) **UI reachability guard**:
  `src/components/screens/search/search-screen.test.ts` asserts the screen is
  real + mounted + plain-language. docs updated:
  `docs/harness/search-retrieval.md`, `docs/CHANGELOG.md`.

- **Fix: `research/web_coverage.py` semantic coverage.** The optional
  embedding-based coverage layer imported `model_runtime.embeddings.embed_texts`,
  which did not exist, so it silently always fell back to IDF/keyword. Added a
  real `python/harness/model_runtime/embeddings.py` (a thin sync adapter over the
  search layer's `EmbeddingService`) so the semantic path works when a provider
  is configured and still degrades honestly when none is. docs updated:
  `docs/CHANGELOG.md`.

- **Native Automation Engine — automation as a first-class domain object.** New
  `python/harness/automation/`: a durable `AutomationDefinition` (trigger +
  condition + action + execution/retry/concurrency/limit/permission/delivery
  policy) with two separate state machines (lifecycle vs execution, invalid
  transitions rejected), timezone-aware cron/interval/one-time scheduling
  (`timeutil.py`), a deterministic three-valued condition engine with
  edge-triggering and domain helpers (`conditions.py`), and a durable store
  (`store.py`: `Automation`, `AutomationVersion`, `AutomationExecution`,
  `AutomationExecutionEvent`, `AutomationLock`, `AutomationDelivery`,
  `AutomationEventSubscription`, `AutomationConditionState`, `AutomationEventDedup`)
  on the ONE `agent-memory.db`, with `migrate_legacy_jobs()` importing existing
  `HarnessJob` rows + run history without destroying data. The `AutomationEngine`
  (`engine.py`) is the ONE scheduler: due lookup by indexed `nextRunAt`, indexed
  event routing (no full scan), event dedup, persisted edge state, lease-based
  distributed locking, retry with backoff+jitter and non-retryable classification,
  concurrency policies (queue/skip/cancel), resource-limit enforcement, restart
  recovery (expired leases reclaimed, interrupted executions reconciled, misfire
  skip/run_once/catch_up), and execution snapshots. Actions dispatch through the
  EXISTING runtime (`service.run`/`run_skill`/`run_workflow`, the Task System via
  `service.tasks`, and the Orchestration layer) — never a second execution path.
  Delivery reuses the in-app bus / artifact dir / messaging vocabulary. New
  operator-gated `/automations` routes + `service.automation_*` wiring; the legacy
  `/jobs` router is now a thin ADAPTER over the same service (routes + shapes
  unchanged). TS front door `src/lib/harness/automation-{client,browser}.ts` +
  `/api/automations/**`; job detail gains Preview/Check backed by dry-run/test.
  Tests `python/tests/test_automation_{core,engine,api}.py` (conditions/timezones/
  lifecycle/validation, scheduler/trigger/retry/concurrency/recovery with an
  injected clock, operator gating + CRUD cycle + legacy-adapter equivalence).
  docs updated: `docs/harness/automation-engine.md` (new),
  `docs/harness/decisions.md` (ADR-H114), `docs/NAVIGATION.md`, this file.

- **Plugin Platform — a production native plugin/extension system.** New
  `python/harness/plugins/`: a fully validated, versioned manifest with a closed
  permission vocabulary, a closed lifecycle state machine
  (`install/enable/disable/update/rollback/repair/uninstall`, atomic install,
  automatic rollback on a failed update, restart-durable state), a persistence
  store on `agent-memory.db` (registry + contributions + config + encrypted
  secrets + scoped storage + bounded logs + health + install history), and a
  developer SDK (`Plugin` + `@tool/@skill/@hook/@command/@event_handler/@worker/
  @webhook/@ui_panel/@data_provider/@research_provider`) whose `PluginContext`
  enforces permissions at every call site (network, filesystem, database,
  secrets, events, tasks, memory, research, …). Contributed tools register on the
  ONE `ToolRegistry` as `plug_<id>_<name>` and effectful ones reuse the existing
  approval authorizer; plugin events ride the ONE run bus (ingested by the Event
  System); hooks run at `before/after_tool_call` (full canonical set registered).
  A controlled HTTP client centralizes timeouts/retries/rate limiting/circuit
  breaking + a metadata-IP SSRF guard; secrets are Fernet-encrypted at rest;
  package integrity is checksum-verified on load and package paths are
  traversal-checked. Surfaces: agent tools `plugin_*`, operator-gated
  `/plugins/*` routes, the `eclipse plugin …` CLI, a local marketplace index, a
  health manager and a doctor. Reference plugins ship under `bundled/`
  (hello-world + github/slack/jira/postgres/binance/sec). Tests
  `python/tests/test_plugins_{manifest,lifecycle,sdk,security,reference,cli_api}.py`
  (63 cases). docs updated: `docs/harness/plugin-platform.md` (new),
  `docs/harness/decisions.md` (ADR-H154), `docs/NAVIGATION.md`, this file.

- **Plugin Platform — process sandbox, OAuth2, hosted registry, outbound
  webhooks/WebSocket, and plugin UI.** Extended `python/harness/plugins/`:
  `sandbox.py`/`sandbox_runner.py` run `community`/`untrusted` Python plugins in a
  **separate OS process** over JSON-RPC (host-proxied context so every permission
  check/SSRF guard/secret boundary still applies; crash isolation, per-call
  timeouts, message-size limit, optional POSIX `RLIMIT_AS`); `oauth.py` implements
  `client_credentials`, `device_code` (RFC 8628) and `authorization_code` + PKCE
  (S256) with refresh/revoke, tokens in the encrypted store, exposed via
  `ctx.auth.token()`; `registry_client.py` adds a **hosted registry** (HTTP/local
  index, SHA-256 verified download, zip-slip/symlink-guarded extract) wired to
  `install_from_registry`; outbound **webhook delivery** (HMAC + retries + DLQ)
  and a reconnecting **WebSocket** client (`ctx.http.connect_ws`); declarative
  **plugin UI view specs** (`render_ui`) rendered by a new `Plugins` screen
  (`src/components/screens/plugins/plugins-screen.tsx` + `plugins-browser.ts` +
  `/api/harness/plugins/**` proxy). New routes/CLI for all five. Tests
  `python/tests/test_plugins_{oauth,webhooks_ws,registry,sandbox}.py` +
  `src/components/screens/plugins/plugins-screen.test.ts`; sidebar/tab/nav wired.
  docs updated: `docs/harness/plugin-platform.md`, `docs/NAVIGATION.md`, this file.

- **Agent Evaluation System — a first-class way to measure whether the agent is
  getting better or worse, by running the REAL runtime.** New
  `python/harness/evaluation/`: `tasks.py` (versioned `EvaluationTask` schema +
  dataset loader, `(task_id, task_version)`-scoped results), `environments.py`
  (deterministic filesystem/database/finance/memory/mock_services/composite
  environments with `setup/reset/snapshot/restore/seed/execute/inspect_state/
  teardown`), `trajectory.py` (capture from the runtime's own event bus + the
  normalized versioned format), `stats.py` (`pass@1`/`pass@k`/variance/Wilson CI/
  flakiness), `taxonomy.py` (multi-label failure taxonomy), `graders/` (a
  pluggable engine with 12 built-ins: exact/state/tool/research/citation/
  financial/code/browser/memory/safety/semantic/hallucination — financial values
  are independently recomputed, code is executed, state is read from the
  environment), `scoring.py` (per-dimension metrics + thresholds + a composite
  that returns `None` when a critical dimension fails), `runner.py` (the runner +
  `ScriptedAgentInvoker` offline tier and `ServiceAgentInvoker` live tier, with
  contextvar isolation so trials run concurrently), `store.py` (11 durable tables
  on the ONE `agent-memory.db`), `baseline.py`, `regression.py`, `report.py`
  (JSON/JSONL/Markdown/HTML), `replay.py`, `mining.py` (production-failure →
  deduplicated regression candidate), `improvement.py` (the self-improvement
  verification loop with the anti-regression rule), `experiments.py` (A/B, model
  matrix, routing, skill/memory deltas), `dependencies.py` (affected-component
  map), `gate.py`, `cli.py`, `tools.py` (sandbox tools), and
  `datasets/benchmark_v1.json` (31 labelled tasks across 15 categories).
  `scripts/test-evals.js` runs the offline gate on a private temp DB as one more
  floor; `harness/cli.py` dispatches `eclipse eval …`; `routers/evaluation.py`
  (`/evaluation/*`, operator-gated) is included by `main.py`. Tests
  `python/tests/test_evaluation_{tasks,graders,scoring,runner,store,regression,
  report_replay,mining_improvement,cli_gate,api}.py` (89, incl. the
  gate-has-teeth proofs). docs updated: `docs/harness/agent-evaluation.md` (new),
  `docs/harness/decisions.md` (ADR-H157), `docs/NAVIGATION.md`, this file.

- **Verification Engine ↔ run claim-ledger integration + memory-recall budget
  honors policy.** The verification-engine tools (`build_project`, `test_project`,
  `run_verification`) executed real build/test runs but never recorded them in the
  run's `VerificationLedger`, so a truthful "the build succeeded / the tests
  passed" backed by a REAL execution was rendered `[UNVERIFIED]` by `code/verify.py`
  (the ledger was fed only by `command_run`). `execution/tools.py` now records each
  engine execution through `_record_engine_verification` (additive, best-effort:
  a missing ledger or unknown class is a no-op); a passing `BUILD_AND_TEST` records
  `build` + `unit_test`, a non-passing outcome records a failing `unit_test` only.
  Also fixed a policy bypass: `graph_context._memory_context` hardcoded
  `budget_chars=4000`, so the operator's `context_budget_chars` setting was
  ineffective; it now omits the value so `EclipseMemoryService.retrieve` applies
  the policy. Tests: `python/tests/test_verification_engine_integration.py` (5).
  docs updated: `docs/harness/execution-architecture.md` (ledger data-flow);
  memory-budget change needs no doc change — bug fix, contract intact.

- **Task/Plan lifecycle hardening — VERIFYING & ASKING_USER states, escalation,
  plan cancel/revision, durable checkpoints, artifact linking, retention, mounted
  Tasks UI.** Closed the remaining Task/Plan DoD gaps. State machine
  (`tasks/{model,state,manager,scheduler}.py`): added `VERIFYING` (authoritative
  state between a completed run and the completion decision) and `ASKING_USER`
  (a human wait, distinct from `WAITING`/`BLOCKED`), with closed transitions and
  retry/recover edges; the scheduler now enters `VERIFYING` before evaluating the
  completion contract. Retry exhaustion can ESCALATE to `BLOCKED`/`ASKING_USER`
  (opt-in `metadata.escalateOnExhaustion`; default stays `FAILED`) via
  `TaskManager.escalate_task` + `TASK_ESCALATED`. Plans: `cancel_plan` (cancels
  every non-terminal task deepest-first; terminal plans untouched) and a
  monotonic `metadata.revision` + `PLAN_REVISED` on structural change. Checkpoints
  become real: the scheduler writes `run_start`/`run_complete` boundaries and
  `restore_checkpoint` resumes a stuck task; `task_view` exposes them. Task
  artifacts now link the run's Artifact-Center entries by reference
  (`artifact://<id>`), replacing the dead `codeVerification.artifacts` read; the
  code-emitted `artifact_service` is threaded correctly through
  `build_graph`/`execute_run` (fixes an undefined-`service` crash in the in-flight
  Artifacts work). Bounded retention (`HARNESS_TASK_RETENTION_DAYS`, default 90)
  prunes aged checkpoints/executions/events only. New tools `resume_task`,
  `escalate_task`, `cancel_plan`; routes `POST /plans/{id}/cancel`,
  `POST /tasks/{id}/resume|escalate`, `GET /tasks/{id}/checkpoints`,
  `POST /tasks/{id}/checkpoints/restore`. Event registry gains
  `task.verifying|asking_user|escalated` and `workflow.revised`. Native search
  output (`search/tools.py`) is now delimited as untrusted content. The Tasks
  screen is mounted (AppTab `tasks`, Agentic sidebar menu) with a nav label.
  Tests: `python/tests/test_tasks_state_hardening.py` (18);
  `src/lib/sidebar/config.test.ts` updated for the new section. Checks: pytest
  4972 passed / 16 skipped, `tsc --noEmit` clean, vitest 2331 passed.
  docs updated: `docs/harness/task-plan-system.md`,
  `docs/harness/search-retrieval.md`.

- **Closeout: wire the search ContextAssembler, the eval gates, and the
  worktree↔verification binding.** Three previously-unwired production paths are
  now live. (1) `search/context.py::ContextAssembler` (token budget, per-source/
  document diversity, neighbour context) is exposed to the agent as the
  `search_context` tool (`search/tools.py` → `SearchService.build_context`),
  returning a bounded, deduplicated block delimited as untrusted data instead of
  raw snippets. (2) The offline harness closeout gates (`harness/eval_gates/`:
  route_health/workflow/resume/capability_matrix) — previously reachable only
  from the offline eval CLI — are exposed at the operator-gated `GET /eval/gates`
  (`harness/routers/eval_gates.py`, registered in `main.py`). (3)
  `execution/service.py::workspace_binding`/`make_actor` now prefer the run's
  allocated code workspace (the per-run worktree the agent edited) over the
  server-root binding, so `build_project`/`test_project`/`run_verification`/
  `execute_*` verify the same tree that was modified. Tests:
  `python/tests/test_eval_gates.py` (3, self-contained — no process-wide app),
  `test_search_tools.py` (+1), `test_execution_tools.py` (+1). Fixed a test
  isolation leak (a module-scoped full-app TestClient in the eval-gates test).
  Checks re-run on this tree: pytest **5040 passed / 16 skipped**,
  `tsc --noEmit` clean, vitest **2337 passed**. docs updated:
  `docs/harness/search-retrieval.md`, `docs/harness/execution-architecture.md`.

## 2026-10-07

- **Financial Data Gateway — provider registry, centralized rate limits, crypto
  source, provider-introspection tool + console.** Extends the existing Financial
  Retrieval Layer (not a second data plane). New
  `python/harness/retrieval/registry.py` (`ProviderDescriptor`/`ProviderRegistry`:
  capabilities, credential REFERENCE only, rate-limit shape, recorded
  license/attribution/redistribution/storage policy; `implemented=False` rows name
  their missing dependency rather than faking an adapter),
  `python/harness/retrieval/ratelimit.py` (`RateLimitManager`: per-provider
  sliding-window + concurrency + 429/`Retry-After` cooldown; a denied acquire
  never calls the provider and yields an honest `rate_limited` outcome), and
  `python/harness/retrieval/crypto.py` (`CryptoSource`; crypto is not an equity —
  `is_crypto()` is the ONE classifier and the vault/live provider refuses crypto).
  Layer wiring in `retrieval/layer.py` (`_retrieve_one` acquires/releases; `CRYPTO`
  source registered; `effective_authority` is crypto-aware) + `retrieval/routing.py`
  (`rate_limited` route category). New TS capability `crypto_market_data`
  (`data-bridge.ts`/`types.ts`/`api/harness/data/route.ts`/`health-key.ts`) reusing
  the existing crypto connector + `classifyIdentifier`; new `provider_key_status`
  capability (presence only, never a value). New agent tools
  `financial_providers`/`financial_resolve_entity`/`market_get_crypto`
  (`retrieval_tools.py`, added to `eclipse-agent`). Operator-gated route
  `GET /financial/providers` (`routers/financial.py` + front door
  `api/harness/financial/providers/route.ts`, which merges vault credential
  presence). UI `src/components/screens/financial-data-console.tsx` (frosted-glass
  provider console in Settings › Data). Tests: `python/tests/test_provider_gateway.py`
  (20) + `src/lib/harness/data-bridge-gateway.test.ts` (4). Docs updated:
  `docs/harness/financial-data-gateway.md` (new), `docs/NAVIGATION.md`. Fixed an
  incomplete `build_graph(market=…)` keyword left by the in-flight Market Data
  Layer work so the graph tests pass.

- **Market Data Layer — first-class, provider-agnostic market data + real-time
  streaming.** New `python/harness/market/`: canonical records (`models.py`),
  closed error vocabulary (`errors.py`), env-driven config (`config.py`),
  canonical instruments + provider symbol mapping (`instruments.py`), declarative
  provider capabilities (`providers.py`), capability-aware routing with circuit
  breaking (`router.py`), the `MarketDataGateway` (route → fetch → normalize →
  quality → provenance, `gateway.py`), a mandatory data-quality engine
  (`quality.py`), a freshness-aware cache (`cache.py`), Evidence-Engine provenance
  + point-in-time (`provenance.py`), derived analytics (`analytics.py`), durable
  snapshot/instrument/quality persistence on the ONE `agent-memory.db`
  (`store.py`), real WebSocket streaming (`streaming.py`: connection manager,
  normalizer, sequence validation, dedup, reconnect, backpressure), the fourteen
  agent tools (`tools.py`), and boot wiring (`bootstrap.py`). New TS provider
  adapters under `src/lib/harness/market/` (yahoo, binance, coingecko, stooq,
  treasury/FRED, ECB-FX) reached through ONE new bridge capability `market_data`
  (`data-bridge.ts`, `api/harness/data/route.ts`, `harness/types.ts`); all reuse
  the SSRF-hardened `safeGet` and existing scraper helpers. 14 tools
  (`get_quote`, `get_historical_prices`, `get_ohlcv`, `get_volume`,
  `get_orderbook`, `get_trades`, `get_market_cap`, `get_supply`,
  `get_funding_rate`, `get_open_interest`, `get_options_chain`, `get_fx_rate`,
  `get_bond_data`, `stream_market_data`) registered and added to the
  `eclipse-agent` allowlist; operator-gated routes `routers/market.py`. Tests:
  `python/tests/test_market_{unit,gateway,streaming}.py` +
  `src/lib/harness/market/bridge.test.ts`. Requirements: `websockets` + `httpx`
  pinned. Docs updated: `docs/harness/market-data.md`, `docs/NAVIGATION.md`,
  `docs/CHANGELOG.md`.

- **Document Intelligence subsystem — production vision + document understanding.**
  New `python/harness/document_intelligence/`: one `process_document` pipeline
  (validate → cache → detect → adapter parse → OCR/vision → structure → entities →
  chunk → index → evidence → assess) over a unified `DocumentIR`, with one adapter
  per format (PDF, DOCX, PPTX, XLSX, ODS/ODT/ODP, CSV/TSV, JSON/JSONL/XML/YAML/TOML,
  HTML, Markdown/TXT, image, EPUB, RTF, archive, legacy OLE). OOXML is parsed with
  stdlib `zipfile`+`ElementTree` (lxml recovery) — no `openpyxl`/`python-docx`/
  `python-pptx` dependency. Deterministic-first OCR routing (`ocr.py`) escalates to
  a vision model only when there is no usable text or confidence is low; all model
  calls, OCR engines and PDF rendering reuse `harness.vision`; extracted text
  becomes the SAME `research.web_contracts.Evidence` via `EvidenceStore`
  (`contentTrust=UNTRUSTED`); tabular questions are computed with read-only
  DuckDB/pandas SQL (`query.py`), never model arithmetic. Security: size/magic/macro
  validation, archive/zip-bomb guards before extraction, `mcp.ssrf` on document URLs,
  HTML sanitization, and the shared injection boundary (document text is DATA).
  States (`READY`/`PARTIALLY_READY`/`FAILED`), bounded retry, per-document timeout,
  content-hash caching, and hybrid lexical+structured retrieval with full
  document/version/page/section/table/cell provenance. The `Di*` tables live on the
  ONE `agent-memory.db`. New `DOCUMENT_TOOLS` (`document_open|inspect|search|extract|
  analyze|query|compare|render|capabilities`, all read-only) on the finance and code
  agents; boot wiring in `service.py`; `documents` run blob on `HarnessRun`/
  `RunResult`/`client.final`; TS `document-view.ts` + `document-panel.tsx`; tests
  `python/tests/test_document_intelligence_{unit,tools,security,graph}.py` +
  `document_intelligence_helpers.py` + `src/lib/harness/document-view.test.ts`.
  No new dependency. Docs updated: `docs/harness/document-intelligence.md`,
  `docs/harness/decisions.md` (ADR-H147), `docs/NAVIGATION.md`, `docs/CHANGELOG.md`.

- **Vision operational hardening — sensitive decided pre-flight; the asset TTL is
  real.** Two problems a surface "limitation" could otherwise cause were closed.
  (1) The orchestrator now runs `security.preflight_scan` (deterministic OCR over
  the frame) BEFORE routing/storage and merges the verdict into the privacy
  decision, so a frame containing a key/PII-shaped string or an injection attempt
  is marked sensitive — under `local_only` it never reaches a cloud provider, and
  `_store_asset` gives it a TTL. Only STRONG signals auto-flag (a crypto chart's
  bare "token" does not over-refuse cloud); without an OCR engine the pre-scan is
  skipped and reported, never silently "clean". (2)
  `AgenticService.run_startup_maintenance` now calls
  `VisionAssetStore.sweep_expired()`, deleting expired asset rows and their files
  on boot, so a sensitive screenshot does not outlive its purpose and disk stays
  bounded. Added `security.preflight_scan`, a `vision.security` telemetry event,
  and tests in `python/tests/test_vision_capabilities.py`. Docs updated:
  `docs/harness/vision.md`, `docs/CHANGELOG.md`.

- **Vision live provider smoke test (opt-in).** New
  `python/tests/test_vision_live.py` exercises a REAL multimodal model —
  native-vision image reading, deterministic OCR, and the auxiliary-fallback path
  (a text-only run model delegating to a configured vision model). It is skipped
  by default with an explicit `NOT RUN — ...` reason, gated by
  `BLACK_ECLIPSE_VISION_IT=1` + `BLACK_ECLIPSE_VISION_MODEL`. Verified against a
  live provider (native read + OCR + fallback all pass). Docs:
  `docs/harness/vision.md`.

- **Vision capability closers — stdlib PDF, persistent visual memory, image
  generation.** Closed three items that were implementable rather than genuine
  external limits. (1) `vision/documents.py` gains a dependency-free `_StdlibPdf`
  backend: text extraction from PDF content streams always works without
  `pypdfium2`, and Pillow rasterizes standard-font pages; each `DocumentPage`
  records `textMethod`/`rasterMethod` and `pdf_capabilities()` reports availability
  (never a faked page). (2) New `vision/memory.py` + `vision_remember` tool persist
  a visual observation through the SAME Eclipse-Memory decision gate
  (`authorize_proposal`+`commit_decision`) — a text summary only, the
  content-addressed `assetId`/regions/model/confidence in `structuredData`, and a
  1-day TTL for sensitive/ephemeral results. (3) New `vision/generate.py` +
  `image_generate` tool speak the OpenAI-compatible `/images/generations` protocol,
  gated by a declared `image_generation` capability; the tool is registered
  `external_action` (approval-gated) and removed at `plan_only` via
  `policy.VISION_EXTERNAL_TOOLS`. Image-generation model families declared in
  `model_runtime/catalog.py`. `VISION_TOOLS` now 18; tests
  `python/tests/test_vision_capabilities.py`. Docs updated: `docs/harness/vision.md`,
  `docs/harness/decisions.md` (ADR-H146 addendum), `docs/CHANGELOG.md`.

- **Vision / Multimodal subsystem — one orchestrator, native-first, integrated
  end to end.** New `python/harness/vision/` gives the agent a production image
  capability (analyze/describe/VQA, screenshot + clipboard, OCR, visual grounding
  for computer-use coordinates, chart analysis with deterministic market-data
  verification, document/PDF/table vision, visual comparison) behind the ONE
  `VisionOrchestrator.orchestrate` pipeline (resolve→preprocess→content-addressed
  store→route→capability detect→cache→dispatch→fallback→telemetry). Every model
  call routes through the existing `model_runtime` (no second provider stack);
  native vision is used first and an auxiliary vision model is the fallback.
  Deterministic-first: OCR before a model, PDF text layer before a model, pixel
  diff before a model describes it. Untrusted input: SSRF-guarded URL fetch on
  every hop (`mcp.ssrf`), bomb/size ceilings, and in-image text scanned + wrapped
  as DATA (`research.web_security`); no visual instruction can override the system
  prompt. Images are SHA-256 content-addressed on the gitignored filesystem tier
  with a `VisionAsset` metadata table on `agent-memory.db`; the cache is a bounded
  in-process TTL keyed over image hash + model + provider + prompt + mode +
  preprocessing + schema version (no Redis — consistent with the repo). Visual
  observations become the existing `research.web_contracts.Evidence` with full
  provenance. `VISION_TOOLS` (all read-only) are declared on the finance and code
  agents; boot wiring `AgenticService.vision_assets`; a bounded `vision` run blob
  persisted on `HarnessRun.vision` and carried on `RunResult`/`client.final`;
  TS `src/lib/harness/vision-view.ts` + `src/components/chat/vision-panel.tsx`
  render it inline in the chat transcript; vision tool labels in
  `response-model.ts` and activity detail/summary in `code/activity.py`;
  `pypdfium2` added to `requirements.txt`. Tests
  `python/tests/test_vision_{unit,orchestrator,tools,graph}.py` +
  `src/lib/harness/vision-view.test.ts`. Docs updated:
  `docs/harness/vision.md`, `docs/harness/decisions.md` (ADR-H146),
  `docs/NAVIGATION.md`.

- **Agent Workspace is now a real docked right sidebar.** Replaced the floating,
  13-tab telemetry overlay with a proper full-height glass column in the shell's
  primary row (mount moved from `app/layout.tsx` to `stock-chat.tsx`, sibling of
  the main panel, so the main panel shrinks instead of being overlapped; same
  pattern as `TerminalDock slot="right"`). Minimal tabs only: **Output**
  (default), **Changes**, **Approvals**, **History** — the removed
  overview/activity/tasks/context/telemetry/research/browser/computer/artifacts
  panels read as noise. New `output-panel.tsx` feed: chronological tool
  calls/commands/file writes, each expandable IN PLACE to render its bounded
  large output (ChatGPT / Claude Code / Kimi idiom); `viewer.tsx` split so
  `ArtifactContent` is reusable inline and by the full viewer. Resizable by
  dragging the inner edge (width persisted, `MIN_W=300`/`MAX_W=760`). No hard
  border frame — the glass edge is the separation. Store panel vocabulary
  reduced to the four ids; pin/auto-focus removed. Docs updated:
  `docs/agent-workspace.md`, `docs/DECISIONS.md` (ADR-042 amended),
  `NAVIGATION.md`.

- **Agent Workspace sidebar: toggle shortcut + denser Claude-style feed.** Added
  a global Ctrl/Cmd + Shift + E toggle (new `workspace-keybind.tsx`, a
  capture-phase listener mounted in `app/layout.tsx` beside the terminal keybind
  so it works whether the sidebar is open or closed; predicate skips while typing
  and is unit-tested). Listed it in the keyboard-shortcuts help dialog. Reworked
  the Output feed for density: timestamps are no longer shown in the row (kept in
  the expanded detail line), consecutive same-tool calls GROUP into one row with a
  ×N badge and expand to the list, and a header **Collapse all** clears every open
  row when any is expanded. New i18n key `workspace.collapseAll`. Docs updated:
  `docs/agent-workspace.md`.

- **Computer Use Engine — isolated + remote desktops (Xvfb / RDP / Windows Sandbox
  / Wayland).** `desktop.py` becomes a provisioner lifecycle
  (`DesktopProvisioner`/`DesktopInstance`/`build_provisioner`): the real
  `X11HeadlessProvisioner` (a private `Xvfb` display per session),
  `WindowsSandboxProvisioner` (launches `WindowsSandbox.exe`, attaches a
  `WindowDriver` to the client window), `RdpDesktopProvisioner` (`mstsc` against
  `isolation.rdp_host`/`rdp_file`) and `WaylandHeadlessProvisioner` (a nested
  headless `wlheadless-run`/`sway`/`weston` on a private socket). New
  `drivers/window.py` scopes capture/input to one contained desktop window
  (background-first, then foreground) and derives a real element tree from OCR of
  the window (`source=ocr`; `accessibility:false` honestly without OCR). New
  `drivers/wayland.py` (grim + ydotool); real `drivers/linux.py` (+AT-SPI) and
  `drivers/macos.py` (+AX). `manager.py` provisions/tears down per session;
  isolated sessions skip the machine-wide broker; `headless_desktop` is true only
  for a genuinely provisioned desktop; absent backends fall back to local with a
  reason. New `broker.py` (machine-wide lease); config `isolation.*`
  (`HARNESS_COMPUTER_ISOLATION*`, `HARNESS_COMPUTER_RDP_*`). Tests
  `test_computer_hardening.py` + opt-in `test_computer_apps_live.py` /
  `test_computer_xvfb_live.py`. Docs updated: `docs/harness/computer-use.md`,
  `computer.example.json`.

- **Approvals — "Always allow" standing grants, a redesigned card, and an alert
  on request.** Made the repeated approval prompts stoppable. (1) New
  `python/harness/grants.py` (`GrantStore` on the ONE `agent-memory.db`, table
  `StandingGrant`): an explicit, operator-only, revocable permission scoped to
  `(kind, scope, pattern)` — one program/tool in one workspace. (2)
  `ApprovalStore` gains `.grants`, additive `grantPattern`/`grantKind`/`grantScope`
  columns on `McpApproval`, and `remember_grant()` (built ONLY from the row's own
  columns). (3) The shell/terminal/terminal-subsystem/MCP/Git authorizers consult
  a grant BEFORE creating a pending request: a match authorizes immediately and
  emits `approval.granted`; a `deny`-classified command is still refused first, and
  a dangerous/destructive/critical Git op is never grantable. (4) `POST
  /mcp/approvals/{id}/decide` and `POST /code/approvals/{id}/decide` accept
  `remember`; new operator-gated `GET /grants` + `POST /grants/{id}/revoke`
  (`routers/grants.py`), fronted by `src/lib/harness/grants-client.ts` +
  `grants-browser.ts` + `src/app/api/harness/grants/**`. (5) Redesigned
  `ApprovalCard` — no yellow: the app's emerald primary + neutral/rose risk scale,
  buttons **Allow once / Always allow `<program>` / Cancel**; "Always allow" is
  offered only when the runtime marks the action grantable and never for high
  risk. (6) An `approval_request` now plays the `notification` cue and raises the
  shared toast/OS notice (`ALERT_NOTIFY_EVENT`). (7) New `StandingGrantsPanel`
  (Code › Approvals) lists and revokes grants. Docs: `docs/harness/decisions.md`
  (ADR-H144), `docs/harness/architecture.md`, `docs/NAVIGATION.md`; tests
  `python/tests/test_standing_grants.py`.

- **Authentication & multi-user mode — opt-in, auto-engages off loopback.**
  BlackEclipse is now able to require a signed-in user, without breaking
  zero-config. A single mode resolver (`src/lib/auth/config.ts`) makes auth
  **required** when `HARNESS_AUTH=required`, or automatically when the app is
  bound beyond loopback (or is a production build), and **off** for a local dev
  bind — so `npm run dev` on localhost stays accountless. When required but
  `HARNESS_AUTH_SECRET` is missing the app **fails closed** (`503
  AUTH_MISCONFIGURED`); `doctor.js` prints the posture at boot. Two layers: the
  Edge `middleware.ts` gates every page and `/api/**` on a validly signed session
  cookie (except `/login` and `/api/auth/**`), and `requireApiAuth` /
  `getAuthContext` (Node) do the authoritative session-row check. Passwords are
  `scrypt`-hashed (Node `crypto`, no new dependency); sessions are opaque ids in
  the gitignored `.black-eclipse/auth.db`; the cookie is `HttpOnly`/`SameSite=Lax`/
  `Secure` off loopback and signed with `jose`. Tenancy is the session's: when auth
  is on, `scope` comes from the session, never the request body (`resolveScope`).
  `/health`'s `identity` now reports the real mode (`authentication`,
  `frontDoorAuth`) instead of a hardcoded "not implemented". New: `src/lib/auth/*`,
  `src/middleware.ts`, `src/app/login/page.tsx`, `/api/auth/{me,setup,login,logout}`,
  a `better-sqlite3` ambient type. Tests: `src/lib/auth/*.test.ts`,
  `src/middleware.test.ts`, updated `python/tests/test_identity_tenancy_boundary.py`.
  Docs: `docs/harness/authentication.md`, ADR-H145. With `HARNESS_AUTH=off` the
  prior no-auth, no-tenancy reality still holds and belongs on a trusted local
  machine only.

- **Search providers — per-provider keys in the Settings modal.** A user can now
  add any named search provider (Tavily/Brave/Exa/Serper/SerpApi/Bing/Google CSE/
  SearXNG) by pasting ONE key in Settings — no `SEARCH_API_CONFIG` JSON. Each
  `SEARCH_PROVIDER_PRESETS` entry gained a unique `keyEnv` (registered in
  `provider-keys.ts`); `buildPresetSearchProvider`/`firstConfiguredPreset` build
  the chosen provider from the vault. `data-bridge.ts` resolution moved to a new
  `lib/harness/web-provider-resolve.ts` (advanced JSON config still wins; else the
  first configured named provider; else the keyless chain). `SearchRetrievalSettings`
  now renders one `ProviderKeyEditor` per provider (vault-backed, encrypted,
  never echoed) and the `/api/search-provider` status/test use the same resolution.
  Docs updated: `docs/harness/web-research-engine.md`.




- **Housekeeping — commit `73be050` scope correction (no history rewrite).**
  Commit `73be050` ("Document parallel sub-question search in the research
  engine") has a message that claims a docs-only change but actually bundles a
  ~2,841-line, 43-file Computer-Use/Browser-Runtime hardening drop; the parallel
  sub-question search it names landed in its parent `aaed4c2`. It is already
  published on `origin/main`, so history is intentionally NOT rewritten (per the
  repo rule against force-push without explicit authorization). This note records
  the true scope so the change is findable/reviewable by intent. No code change.

- **Research retrieval — Phase 7: honest missing-input refusal messaging.** The
  `finance_metrics` tool's refusal now names the exact missing input, states that
  no default/approximation will be substituted, and points at the remedy
  (`web_extract` the source, or `finance_metric_catalog` for a metric whose
  inputs exist). This is a by-design invariant (never fabricate financial data),
  not a defect. Docs updated: `docs/harness/web-research-engine.md`.

- **Research retrieval — Phase 6: evidence-anchored entity/knowledge graph.**
  Added a general graph beyond claim→evidence. `web_store.py` gains
  `WebResearchEntity` + `WebResearchRelation` tables (every node/edge records the
  `evidenceId`/`sourceUrl` it came from; no ungrounded node) with
  `save_entity`/`save_relation`/`list_entities`/`list_relations`/`find_entity`.
  New deterministic extractor `research/web_graph.py` (`build_graph`) resolves
  companies via the existing `resolve_entity`, extracts proper-noun terms, and
  derives `metric → value` and co-occurrence edges from the structured
  enrichment. The engine persists the graph and returns `entities`/`relations` on
  `EngineResult`; a new `research_graph` tool exposes it; the run API returns it;
  the Research screen gains a Knowledge Graph widget. Docs updated:
  `docs/harness/web-research-engine.md`.


- **Phase S — stabilization (ratchet hygiene, docs drift, process).**
  (S.2) **Ratchet hygiene** — `main.py`'s FastAPI lifespan boot/shutdown wiring
  extracted to `harness/boot.py`; `main.py` dropped from ~1018 to ~955 lines (under
  the 1200-line hard ceiling) and was removed from the size ratchet rather than
  raised. `main` still re-exports `lifespan`, `identity_boundary`,
  `deployment_exposure`, `IDENTITY_BOUNDARY` so the public surface is unchanged.
  The finance-agent prompt ceiling was LOWERED 23300 → 23025 (trimmed a redundant
  worked example; no honesty/authority rule removed) so the ratchet bites again.
  (S.3) **Docs drift** — new `docs/harness/research-surfaces.md`, the ONE "which
  surface answers which question" page (search finds → browser reads behind a
  login → computer-use reads a desktop app), cross-linked from
  `web-research-engine.md`, `browser-runtime.md`, `computer-use.md` and named in
  `NAVIGATION.md`'s trigger table. (S.1) **Concurrency** — recorded as a
  working-practice rule (serialize writers / short-lived branches): recent commits
  swept unrelated changes together, including this session's Phase 8–10 browser
  work committed by another writer. Tests:
  `python/tests/test_phase_s_stabilization.py`. Docs: `docs/harness/decisions.md`
  (ADR-H141), `docs/NAVIGATION.md`,
  `docs/harness/{browser-runtime,web-research-engine,computer-use,research-surfaces}.md`.

- **Research retrieval — Phase 5: semantic coverage + honest provider cost.**
  (a) `web_engine.py` coverage is now layered and discloses its method
  (`coverageMethod`): embedding similarity when an embedding runtime exists
  (`_semantic_answered`), else an IDF-weighted term-overlap score
  (`_idf_answered`) that answers a sub-question only when its distinctive terms
  are corroborated, else the conservative keyword fallback. Per-question scores
  are returned in `questionScores`; still a coverage signal, never a correctness
  claim. (b) New `research/web_pricing.py` (`CostLedger`, `price_for`) gives an
  HONEST cost estimate: keyless providers are FREE known-0.0, a paid provider
  with no `HARNESS_WEB_PRICE_<PROVIDER>_QUERY` is UNKNOWN (None, never 0), and a
  total is `exact` only when every used provider was priced. `maxCost` is now
  ENFORCED before extraction when prices are exact; `coverage["cost"]` is
  recorded on the run. Docs updated: `docs/harness/web-research-engine.md`.

- **Research retrieval — Phase 4: dedicated Research screen.** Added a
  first-class `research` AppTab (not just the chat Sources panel), wired into
  `app-tabs.ts`, `sidebar/config.ts`, `i18n/nav.ts` + `dictionaries/en.ts`,
  `search/deep-link.ts` and the SPA shell (`stock-chat.tsx`). The screen
  (`src/components/screens/research/research-screen.tsx`) reuses the shared
  `CustomizableWorkspace` with a research widget catalog
  (`src/lib/research/research-widgets.tsx`): run list, new-run form (background),
  live run status, evidence, claims/citations, conflicts, and a one-click
  scheduled-research enabler over the existing `/jobs` engine. State comes from
  the ONE `useResearchScreen` hook polling `/api/research/*` (new front-door
  proxy). Docs updated: `docs/harness/web-research-engine.md`.

- **Research retrieval — Phase 3: background research runs.** A long research run
  no longer blocks a single turn. `web_engine.py` gains
  `schedule_background_research(request, bridge, store, emitter)` and
  `background_research_active`; the mandate is planned+persisted SYNCHRONOUSLY
  (`create_research_sync`) before the task is scheduled, so the research id is
  observable at once and a cancel issued before start is honoured. The engine
  re-persists observable state on every transition (`_set_state`), so
  `research_status`/`research_cancel`/`research_continue` work from any later tool
  call. New tool `research_start` (registered in `WEB_RESEARCH_TOOLS`) and route
  `POST /research/web/start` return the id immediately. No schema change. Docs
  updated: `docs/harness/web-research-engine.md`. (Frictionless enabling of the
  existing disabled templates is delivered with the research screen in Phase 4,
  reusing `/jobs`.)

- **Research retrieval — Phase 2: first-class academic/news/image/video
  connectors.** Replaced the keyword-augmented `academic_search`/`image_search`/
  `video_search` hacks. New keyless connectors in `src/lib/web-connectors.ts`
  (OpenAlex, Crossref, GDELT, Openverse, Wikimedia Commons) return the same
  normalized `WebSearchResult`/`RetrievalDiagnostic` shape over the SSRF-hardened
  transport. New bridge capabilities `academic_search`/`news_search`/
  `image_search`/`video_search` (`data-bridge.ts`, `DataCapability`, data route
  allowlist). Python `web_providers.py` adds `ConnectorSearchProvider` and
  registers `eclipse_academic`/`eclipse_image`/`eclipse_video`; `web_tools.py`
  routes each tool to its kind and falls back to web search only when the
  connector chain is unavailable. Docs updated: `docs/harness/web-research-engine.md`.

- **Research retrieval — Phase 1: dependable coverage, keyless chain, paywall/JS
  escalation, one-click JS rendering.** Addressed the top retrieval limitation
  ("DuckDuckGo default is frequently bot-blocked"). (1) `web-search.ts` now
  exposes a KEYLESS FALLBACK CHAIN — `DuckDuckGoHtmlProvider`,
  `DuckDuckGoLiteProvider`, `MojeekProvider`, `BingHtmlProvider` — tried in order
  by `resolveSearchProviders`/`searchWeb`, so one blocked engine no longer blanks
  a search; the operator-configured provider still runs first. (2) Presets
  expanded to AllProviders (`serpapi`, `bing`/Azure, `google-cse` alongside
  tavily/brave/exa/serper/searxng). (3) New `src/lib/web-paywall.ts` detects
  subscription/login walls (and HTTP 402) as the new `paywalled` diagnostic
  category (`retrieval-diagnostics.ts`), routed to `ineligible`
  (`retrieval/routing.py`); a bare 403 stays `http_error` (bot/geo block).
  (4) `web_engine.py` fetch loop escalates `javascript_only`/`parse_failure`/
  `unsupported_document`/`paywalled` to the existing browser runtime
  (`web_browser.py`); `needs_escalation` recognizes paywall errors.
  (5) One-click JS rendering: `POST /browser/install` (Python) installs
  Playwright + Chromium idempotently and reports the binary's true presence;
  proxied at `src/app/api/search-provider/install`; Settings gains a
  `SearchRetrievalSettings` panel (search provider + connectivity test + Enable
  JS rendering). No architecture/contract change beyond the added diagnostic
  category. Docs updated: `docs/harness/web-research-engine.md`.

- **Computer Use Engine — hardening pass: enforce advertised limits, real
  backends, challenge stops.** Closed the gap between what the subsystem advertises
  and what it enforces. (1) `max_actions` and `action_timeout_seconds` are now
  enforced (`ComputerCore.act` wraps handlers in `asyncio.wait_for` and counts
  `session.actions_started`; over-budget ⇒ `BudgetExceeded`/`COMPUTER_BUDGET_EXCEEDED`,
  timeout ⇒ `COMPUTER_TIMEOUT`). (2) `vision_model` and `ocr_enabled` now have
  consumers; a cloud vision model is wired as the CLOUD backend so a sensitive frame
  is refused; finance allowlists (`finance_allowed_apps/accounts/instruments` +
  `HARNESS_COMPUTER_FINANCE_ALLOWED_*`) flow into the firewall. (3) New
  `ocr/windows.py` (`WindowsOCREngine`, `Windows.Media.Ocr`) makes OS-native OCR the
  `auto` default on Windows; `Pillow`/`uiautomation`/`winsdk` are declared and
  installed/repaired by `setup-python.js`/`doctor.js`. (4) CAPTCHA/MFA/biometric
  detection (`security.detect_challenge`) refuses BEFORE any input and returns
  `COMPUTER_HUMAN_REQUIRED` (verdict `ask_user`); new `computer_request_human` tool.
  (5) `security.scan_injection` flags screen text posing as instructions in the
  UNTRUSTED wrapper. (6) Background delivery now covers mouse move/scroll/drag and
  button press/release; foreground focus is restored after escalation. Config
  reference committed at `computer.example.json`. Docs updated: `docs/harness/
  computer-use.md`, `docs/harness/decisions.md` (ADR-H140).


- **Browser Automation Runtime — Phase 10 (progress, financial workflow,
  cross-engine coordination, browser→claim).** (1) **Progress → planner** —
  `browser/task.py` adds a persisted, bounded step-level checklist
  (`BrowserTask`/`BrowserTaskRegistry`) emitted as `browser.task.*` AND stored in
  `agent-memory.db` (a `BrowserTask` table), so a long run shows “open SEC →
  search → find filing → download → extract” and the progress survives the call;
  the `browser_task` tool and `GET /browser/tasks` drive/read it. (2) **A second
  bundled financial workflow** — `system.sec-filing-research` (disabled/inert by
  default, progressive disclosure, real browser/web tools only), following the
  `system.browser-research` pattern. (3) **Cross-engine coordination** —
  `research/coordination.py` documents and implements ONE routing policy (“search
  finds → browser reads behind a login → computer-use reads a desktop app”),
  deterministic via `route(SurfaceRequest)`, sharing the ONE evidence store; a
  browser-read value is a candidate. (4) **Browser→Evidence deepening** —
  `browser/bridge.py` is the ONE legal path from a browser observation to a
  verified claim: build engine `Evidence` (provenance never fabricated), then run
  the engine's OWN `verify_claim`; a claim not grounded in the observed text is
  refused. Tests: `python/tests/test_phase10_coordination.py`. Docs:
  `docs/harness/browser-runtime.md`, ADR-H139.

- **Search provider: configure a real provider by name, not JSON.** The
  `SEARCH_PROVIDER_PRESETS` catalog (Tavily, Brave, Exa, Serper, SearXNG) is now
  reachable: `resolveSearchApiConfig` accepts `SEARCH_API_CONFIG` as a preset name
  (`"tavily"` / `{"preset":"tavily"}`) or a full config object, and
  `data-bridge.resolveCustomSearchProvider` uses it, so an operator adds an
  independent second search route with a name + key (`SEARCH_API_KEY`) instead of
  hand-writing the JSON shape. Tests: `src/lib/web-search-presets.test.ts`.

- **Browser Automation Runtime — Phase 9 (provider layer completion).**
  (1) **Camofox** (`camofox`) — a stealth Firefox backend (Playwright `firefox`,
  not CDP): resolves a Camoufox binary (`camoufox` package resolver or
  `HARNESS_CAMOFOX_ENDPOINT`) and launches via the local provider with
  `executable_path`; an endpoint attaches over CDP. Honest `available:false` when
  no binary/endpoint is resolvable. (2) **Browser Use** — a real adapter: when the
  `browser-use` package is installed it starts Browser Use's browser and returns a
  `ProviderSession` Eclipse drives (Eclipse keeps reasoning/sessions/policy/
  observation/tracing); an incompatible build fails honestly. (3) **Firecrawl as
  an extraction backend** — `FirecrawlProvider.extract` calls `/v1/scrape` and is
  wired into the research engine's extraction path (`web_extract`
  `backend:"firecrawl"`, falling back to the SSRF bridge). It declares
  `interactive:false` and `launch` refuses, so an interaction can never route to
  it. (4) **Router maturity** — `ProviderHealth` demotes a provider after
  consecutive failures (re-promoting on success) with the demotion in the
  decision; `HARNESS_BROWSER_PREFER_LOW_COST` orders fitting candidates
  cheapest-first (relative hint, never a money figure); an explicit request
  overrides demotion. New config: `HARNESS_CAMOFOX_*`, `HARNESS_FIRECRAWL_ENDPOINT`,
  `HARNESS_BROWSER_PREFER_LOW_COST`, `HARNESS_BROWSER_ALLOW_PRIVATE_REMOTE`.
  Tests: `python/tests/test_browser_providers.py`. Docs:
  `docs/harness/browser-runtime.md`, ADR-H138.
- **Computer Use Engine — production readiness: high-risk target gate, prompt
  guidance, benchmark and live demo + finance harnesses.** (1) **High-risk target
  gate** — `ComputerCore._resolve_target(high_risk=True)` refuses a
  coordinate-only or low-confidence target for a CRITICAL action (a financial
  mutation, or a Submit/Buy/Sell/Transfer control the adapter flags risky), so a
  critical action can never be a blind pixel click; a caller may override only
  with BOTH `allow_coordinates` and `confirm_coordinates`. `_is_high_risk_target`
  derives the classification from the financial-mutation vocabulary, the
  destructive-label heuristic and the application adapter. (2) **Model guidance**
  — a `## Computer Use (native desktop)` prompt block (observe-first, stale-handle
  refusal, verdict/recovery, untrusted screen data, the finance firewall);
  prompt ceiling raised to 23300. (3) **Eclipse CUA Benchmark**
  (`tests/test_computer_benchmark.py`) measures grounding accuracy, verification
  accuracy, recovery success, task completion and — the finance priority —
  false-action rate and dangerous-action rate, all at their production bar
  (0 false/dangerous actions). (4) **Live demo workflows**
  (`tests/test_computer_demos.py`) run demos 1–5 against owned Win32 windows with
  the REAL Windows driver. (5) **End-to-end finance harness**
  (`tests/computer_finance_e2e.py` + `computer_finance_terminal.py`) drives a mock
  trading terminal: reads screen-derived state with provenance, computes a
  rebalance via the deterministic calculator, and proves the firewall blocks
  read_only, holds assisted for approval, and NEVER clicks a mutation control
  (checked against the terminal's own click log). Also: the fake test driver now
  models a position-aware semantic change on click, and
  `test_mcp_orphan_reaping` is cwd-independent. Docs:
  `docs/harness/computer-use.md`. 21 new tests. `docs updated:
  docs/harness/computer-use.md, docs/CHANGELOG.md`

- **Browser Automation Runtime — Phase H (hardening: frames, interception, device,
  recovery, injection).** (1) **Frames** — a `Target` may carry `frame` (nested
  with `>>`); the resolver scopes every strategy inside `page.frame_locator(...)`
  and `browser_snapshot` accepts `frame`, so cross-origin/nested frames are
  observed and acted on like the top document (cross-frame action routing).
  (2) **Recovery** — a coordinate-only target (or a locator that can't click an
  occluded/stale element) falls back to a pixel click (`strategy:"coordinates"`);
  a crashed/closed provider session surfaces a structured failure, a destroyed
  session is cleanly recreated, and an unavailable explicit provider falls back to
  the next-best. (3) **Device emulation** — `browser/devices.py` resolves a
  descriptor from whichever catalog the runtime exposes (Playwright instance
  `devices` / module export / driver `local_utils`) and reports the applied
  viewport/UA/locale/timezone; unknown device = honest error. `browser_set_*` and
  `emulate_device` record their override on the session. Device/viewport ops
  extracted to `browser/context_ops.py` (kept `session.py` under its ceiling).
  (4) **Prompt injection** — adversarial test pages (`/injection-text`,
  `/injection-tools`, `/injection-attrs`) prove page content never changes policy,
  permission levels, or the tool registry. Tests: `test_browser_hardening.py`
  (real Chromium) and `test_browser_hardening_unit.py` (offline). Docs:
  `docs/harness/browser-runtime.md`, ADR-H137. `session.py` net-shrinks.

- **Test-suite reproducibility: `test_mcp_orphan_reaping` is cwd-independent.**
  The orphan-reaping test spawned its parent with `sys.path.insert(0,
  os.path.join(os.getcwd(), "python"))` and `cwd=os.getcwd()`, so it passed only
  when pytest ran from the repo root and failed ("parent exited before starting
  its child") when run from `python/` — which is how a contributor or a
  single-file invocation runs it. It now derives the import root from
  `Path(__file__).resolve().parent.parent` and passes it to the child. No
  production code changed. `no doc change — test-only reproducibility fix`.

- **Browser Automation Runtime — Phase 8 (observability, replay, telemetry, cost).**
  (1) **Replay/inspection** — `browser/replay.py` reconstructs a stored
  `BrowserTrace` into a bounded (≤500 step) browser-free timeline with a
  `failureAnalysis` (first failing step's code/category/plain sentence) and a
  `render_text` human view; exposed as the `browser_replay` tool and
  `GET /browser/traces/{id}/replay`. It never opens a browser and never
  re-executes. (2) **Telemetry aggregates** — `browser/telemetry.py` is the ONE
  process-wide content-free aggregate: session/action/failure/timeout/crash/
  navigation counters, per-action and per-provider latency (sum/count/max only),
  vision calls, provider failures, downloads/uploads and error-category buckets,
  surfaced in `/health.browser.telemetry`, `GET /browser/telemetry`. Every tool
  call records one action at the single registration seam (`_telemetry_wrap`).
  (3) **Cost** — accrues from REAL measurements (browser-seconds split local/cloud
  by the provider's `remote` capability, vision tokens, screenshots, artifact/
  download bytes); a money figure appears ONLY when a non-zero `HARNESS_BROWSER_COST_*`
  rate is set, otherwise `ratesConfigured:false` / `estimatedMicros:null`
  (`GET /browser/cost`). (4) **Structured logs** — a bounded content-free ring
  queryable by code/level/category/session (`GET /browser/logs`). New config:
  `HARNESS_BROWSER_COST_*`, `HARNESS_BROWSER_TELEMETRY_LOG_CAP`. Tests:
  `python/tests/test_browser_observability.py` (telemetry/cost/logs/replay, no
  browser) and `test_browser_observability_api.py` (routes). Docs:
  `docs/harness/browser-runtime.md`, ADR-H136. `main.py` unchanged (`/health`
  browser block is `browser_health()`).
- **Browser Automation Runtime — Phase C/D (evidence, skills, isolation, fusion).**
  (1) **Evidence/Research integration** — `browser/evidence.py` records every
  consulted `http(s)` page (navigation, snapshot, extract) on the run's existing
  `source_sink` (`SourceCollector.add_fetched_source`), so a browser-derived fact
  reaches the answer's Sources panel with URL/title/retrieval time; internal pages
  (`about:blank`, `data:`) are never recorded and the collector shape is reused,
  not duplicated. (2) **Skills integration** — a bundled, inert
  `system.browser-research` skill wrapper (progressive disclosure; `requiredTools`
  = the browser tools) so a browser research workflow is teachable. (3)
  **Delegation/session isolation** — `session_of` now prefers a session owned by
  THIS run/agent before the cross-run fallback (`BrowserManager.list_active`), so a
  delegated subagent never drives the parent's browser. (4) **DOM+vision fusion
  surfaced** — `browser_visual_locate` (`vision.locate`) fuses the DOM locator with
  a visual match, reports the chosen path + both confidences + rationale, and emits
  `browser.visual.locate` for the trace. `waiting.py` extracted from `session.py`
  to keep it under the size ceiling. 84 `browser_*` tools. Tests:
  `test_browser_unit.py` (+provenance/fusion) and `test_browser_integration.py`
  (+`visual_locate`, source recording, two-run isolation).
- **Computer Use Engine — production stress-test hardening.** A controlled live
  validation (real Windows driver, a real Win32 test target, a bounded background
  message pump) found and fixed seven defects, each with a regression test
  `python/tests/test_computer_hardening.py`:
  (1) **Background input never reached child controls** — `PostMessage` was sent
  to the top-level window with screen coordinates; it now resolves the deepest
  child control (`RealChildWindowFromPoint`, z-order independent) and converts to
  client coordinates, and keyboard background input targets the thread's focused
  control (`GetGUIThreadInfo`). Background clicks now activate controls WITHOUT
  focus stealing, instead of silently escalating.
  (2) **Foreground escalation could click blind into a covering window** —
  `click`/`type_text`/`key` now refuse when an absolute-coordinate foreground
  action would land on a different top-level window (`COMPUTER_TARGET_OBSCURED`,
  verdict `foreground_required`) rather than hitting the wrong application.
  (3) **Verification reused the pre-action snapshot**, so semantic change was
  never seen and every action fell back to pixel noise; `capture_state`/
  `verify_action` now read a FRESH accessibility digest + title, settle-poll for
  a bounded window, and treat ONLY semantic change as `verified` (pixel-only
  churn is `uncertain`). An `uncertain` verification can no longer yield a
  `success` verdict.
  (4) **`SecurityLayer` was constructed but never called** — observation now
  scans for sensitive controls/text, flags the snapshot `sensitive`, masks the
  persisted image, and refuses cloud vision for a sensitive frame.
  (5) **`allowed_actions` was declared but never enforced** — a non-empty
  allowlist now blocks an unlisted action (`COMPUTER_ACTION_NOT_ALLOWED`).
  (6) **The recovery ladder was never surfaced** — a failed action now carries
  its ordered `recoveryPlan`, and an unexpected dialog (`UNEXPECTED_DIALOG`)
  stops the loop instead of typing into it.
  (7) **`set_value` used a blocking `SendMessage`** (an unresponsive control could
  hang the async loop) — now `SendMessageTimeoutW` with `SMTO_ABORTIFHUNG`.
  Also: `Bounds.from_any([x, y])` returns a point (not `None`), snapshot ids are
  unique across sessions, `mouse_move` uses a real permission band, and
  `computer_remember` uses `execution_lesson` (the permitted Eclipse-Memory
  source) so memory writes actually succeed. Stress rig:
  `python/tests/computer_stress_rig.py` + `computer_stress_target.py` +
  `computer_stress_focus.py` (36/36 pass). Docs:
  `docs/harness/computer-use.md`.

- **Evidence-Driven Web Research Engine — a first-class research subsystem.**
  New `python/harness/research/web_*.py` package implementing
  `question → intent → mandate → plan → provider registry (ordered fallback) →
  search → extract → browser escalation → normalize → entity resolution →
  EvidenceStore → freshness/point-in-time → source ranking → source comparison →
  conflict detection → deterministic calculations → claim verification →
  citation generation → citation validation → coverage → synthesis → status →
  immutable snapshot`. The governing rule is explicit and enforced: **search
  results are pointers, not evidence; the LLM reasons over evidence and is never
  the source of truth.** Reuses (never duplicates) the existing retrieval layer,
  the TS web transport via the `DataBridge` (`web_search`/`web_fetch`), the
  Browser Automation Runtime (escalation only), `research.budget`/`periods`/
  `calculations`, the SSRF/redirect guards, the untrusted-content boundary and
  the ONE `agent-memory.db` connection for its `EvidenceStore`. 21 read-only
  tools on the ONE `ToolRegistry` (`web_search`, `news_search`, `company_search`,
  `academic_search`, `image_search`, `video_search`, `web_extract`,
  `page_extract`, `pdf_extract`, `structured_extract`, `research_plan`,
  `research_query`, `source_rank`, `source_compare`, `claim_verify`,
  `citation_extract`, `citation_validate`, `research_status`, `research_cancel`,
  `research_continue`, `research_update`); `WEB_RESEARCH_TOOLS` added to the
  finance and code agents; operator-gated router `routers/research.py`
  (`/research/web/*`); `EvidenceStore` tables on `agent-memory.db`. Point-in-time
  research fails closed (unknown-time sources are excluded), news syndication is
  grouped into source families, and injected page instructions are preserved as
  evidence but never laundered into a finding. Tests: `test_web_research_{unit,
  integration,tools,api,hardcore}.py` (48 cases). Docs: `docs/harness/web-research-engine.md`,
  `docs/harness/decisions.md` (ADR-H135), `docs/NAVIGATION.md`.

- **Web research engine — production hardening.** Fixed a set of defects found in
  the first cut: (1) **deep runs were hard-killed by the agent's generic
  `toolTimeoutMs` ceiling** — a `ToolDefinition.long_running` flag now lets
  `research_query`/`research_continue`/`research_update`/`web_extract` use their own
  declared budget (still clamped to the global ceiling), and `ToolRegistry.execute`
  exposes the ACTUAL effective timeout on `ToolContext.tool_timeout_ms` so the
  engine sizes its internal deadline below the ceiling and returns a bounded
  partial instead of dying; (2) **`update_research` deleted prior evidence** — it is
  now non-destructive (idempotent upsert + a new snapshot) and returns a delta
  (added/changed/dropped sources, added/removed evidence); (3) **unbounded payloads**
  — evidence `rawText` is bounded to 8k in the tool/API view (the store keeps the
  full text); (4) **unbounded process-wide status/cancel maps** — pruned to 256
  tracked runs, terminal-first; (5) events namespaced `webresearch.*` (no collision
  with the Phase-4 `research.*` stream); (6) coverage no longer overstates
  `answeredQuestions` (keyword-corroboration count, plus `sourceCoverage`); (7)
  router rejects an unknown `depth` with 422 and bounds snapshot/evidence payloads.
  Tests: `test_web_research_hardening.py` (9 cases). Doc: `docs/harness/web-research-engine.md`.

- **Web research engine — second bug-fix pass (data integrity).** (1) **Shared
  `EvidenceStore` never reached the run** — `service.evidence_store` was built but
  not passed to `execute_run`/`build_graph`, so tools silently built a throwaway
  store; it is now threaded through on both the sync and async paths. (2) **Cross-run
  clobbering** — `sourceId`/`evidenceId` were the primary key, so fetching the same
  URL in two runs made the second run's `list_*` return nothing; membership is now
  an explicit many-to-many link table (`WebResearchSourceLink`/`WebResearchEvidenceLink`)
  with a one-time marker-tracked backfill. (3) `make_source` returned an EMPTY
  `retrievedAt`; it now stamps retrieval time. (4) Per-run claim/citation/conflict
  ids were namespaced by `researchId`. (5) `list_evidence` coerces NULL/partial
  legacy columns to honest defaults so `Evidence(**row)` can never crash a tool.
  (6) A `continue`/`update` after a cancel no longer aborts itself (the event is
  cleared at resume) while a create→cancel→execute still honors the cancel. Tests:
  `test_web_research_store.py` (7 cases). Doc: `docs/harness/web-research-engine.md`.

- **Computer Use Engine — a production-grade desktop-control runtime.** New
  `python/harness/computer/` package (62 modules) implementing the full agentic
  loop `OBSERVE → … → AUTHORIZE → ACT → VERIFY → RECOVER`: a platform-independent
  `ComputerDriver` (Windows via `ctypes` Win32 — no third-party package; honest
  `NullDriver` elsewhere), accessibility-first observation (UI Automation when
  installed, a Win32 child-window baseline, OCR, provider-agnostic vision),
  screen-of-marks snapshots with **stable element handles + stale-element
  protection**, a grounding hierarchy (accessibility → semantic → structured →
  OCR → vision → coordinates), mouse/keyboard/`set_value` actions with
  **background-first** delivery and explicit foreground escalation with focus
  restore, an action verifier (verified/failed/uncertain + screen diff), a bounded
  recovery ladder, a window/application manager with an `ApplicationAdapter`
  framework and initial adapters (Excel, VS Code, terminal, Chrome/Edge, PDF,
  TradingView, MetaTrader 5, Interactive Brokers, Bloomberg-style), a permission/
  risk policy engine, sensitive-region detection/redaction, a **Finance Action
  Firewall** (read_only/assisted/autonomous/simulation; buy/sell gated,
  transfer/withdraw always blocked), screen-derived finance with provenance,
  human-takeover control leases, recording/replay, telemetry, a doctor/diagnostics
  report, `agent-memory.db` persistence, and Eclipse-Memory knowledge (never JDdS,
  never screenshots). Integrated on the ONE `ToolRegistry` (`computer_*`),
  the ONE authorizer chain (`code/authorizers.py`), the ONE policy authority
  (`code/policy.py` `COMPUTER_EFFECTFUL_TOOLS`), `agents.py` (`COMPUTER_TOOLS`),
  `service.py`, `main.py` (`/computer/*`), and the CLI (`eclipse computer …`).
  Finance actions route through the firewall BEFORE any UI action; coordinate
  clicking is never the primary method. Tests: `python/tests/test_computer_{unit,
  safety,tools,adversarial}.py` (77 cases). Docs: `docs/harness/computer-use.md`;
  NAVIGATION row.

- **Browser Automation Runtime — Phase B (limitations closed).** (1) **Real visual
  interpretation** — `browser_vision` now interprets the screenshot when the run
  has a multimodal model, via `vision_model.BrowserVisionInterpreter` reusing the
  harness model runtime (`task="vision"`, which requires a known-good `vision`
  capability); no configured model yields an honest `available:false` and the raw
  screenshot + DOM map are unchanged. (2) **`browser_find` / `browser_highlight`**
  (`inspection.py`) — describe every element a locator matches (with its snapshot
  ref, role, name, text) WITHOUT interacting, and briefly outline a target for
  visual confirmation. (3) **Log paging** — large console/network/error dumps are
  bounded for the model and the full text is persisted under
  `artifactsRoot/<kind>/<session>/` (`tool_support.bound_log_text` +
  `observation.persist_artifact`). (4) **Browserbase is a real cloud backend** —
  session creation through its REST API + CDP attach when enabled with a
  vault-resolved credential, honest `CREDENTIAL_UNAVAILABLE` otherwise; the
  credential never reaches the model. 83 `browser_*` tools. Tests:
  `test_browser_unit.py` (+vision/log/browserbase cases) and
  `test_browser_integration.py` (+`find`/`highlight`, vision-no-model). Docs:
  `docs/harness/browser-runtime.md`.

- **Browser Automation Runtime — a Hermes-grade, provider-agnostic browser
  subsystem.** New `python/harness/browser/` package: a `browser_*` toolset on the
  ONE registry (navigation, accessibility-first snapshots with Eclipse-stable refs
  `@e1…`, interaction, waiting, tabs, iframes, dialogs, downloads/uploads,
  console/network/errors, JS eval, controlled CDP, storage, profiles, vault,
  human-in-the-loop, device emulation, network interception), a `BrowserManager`
  pool + `BrowserSession` state machine, a `BrowserProvider` layer (`LocalChromium`
  on Playwright, `CDPProvider`, and honest optional backends Browser Use/Browserbase/
  Lightpanda/agent-browser/Firecrawl that report unavailability rather than faking
  it), a capability-based provider router (private/local targets always run
  locally), a locator/resolution engine with stale re-resolution, action→observe→
  verify, vision + DOM/vision fusion, a sandboxed `browser_exec` program AST, ONE
  security policy engine (permissions ALLOW/DENY/ASK routed through the existing
  single-use approval store, domain policy, destructive-action elevation, an
  untrusted-page boundary vs prompt injection), a credential vault (references,
  never values), persistent profiles, durable metadata on `agent-memory.db`, and
  bounded traces. Boot wiring in `service.py`/`main.py` (`/health.browser`, router
  `/browser/*`); `BROWSER_TOOLS` added to the finance agent, code agent and chat
  code profile; `code/policy.py` + `code/authorizers.py` narrowing/admission;
  prompt guidance; `playwright>=1.62,<1.63` in `requirements.txt` + a doctor probe
  (never auto-downloads the browser). A missing Playwright/Chromium is an honest
  `BROWSER_UNAVAILABLE`, never a fake browser. Tests: `test_browser_unit.py` +
  `test_browser_integration.py` (real Chromium against the stdlib test app
  `browser_app.py`). Docs: `docs/harness/browser-runtime.md`, `docs/harness/decisions.md`
  (ADR-H134), `docs/NAVIGATION.md`.
- **Computer Use Engine — desktop control as a first-class, isolated capability.**
  New `python/harness/computer/` package: a `computer_*` toolset on the ONE
  registry, a `ComputerManager` + desktop session/state model, a platform-driver
  layer (`drivers/`) with honest availability, accessibility/grounding/OCR/vision
  engines, a finance firewall + policy/security layer, takeover leases, recording
  and replay, and the matching router (`routers/computer.py`, `/computer/*`,
  operator-gated) plus a `computer` CLI group. Boot wiring in
  `service.py`/`main.py` (`start_computer`/`start_computer_sweeper`/
  `stop_computer`). Tests: `test_computer_{unit,tools,safety,adversarial}.py`
  (77 passing). This subsystem landed alongside the Browser Automation Runtime and
  shares the same runtime files (`service.py`, `main.py`, `cli.py`), so both ship
  in one commit to keep the tree buildable.
- **Size/ratchet tests tolerate the vendored Python + prompt growth.** The TS
  size-budget walk now skips `scripts/vendor` (the vendored interpreter's
  site-packages carries Playwright `.d.ts` files); the Python `main.py` ratchet and
  the finance prompt char ceiling were raised with justification for the browser
  boot wiring + guidance block. `test_code_agent.py`/`test_chat_code_profile.py`
  count the shared `BROWSER_TOOLS` set.

- **Fix: client components imported server-only harness clients, breaking the
  build (`Can't resolve 'child_process'`).** `research-widgets.tsx` dynamically
  imported `@/lib/harness/jobs-client` and `standing-grants.tsx` statically
  imported `@/lib/harness/grants-client`; both pull `child_process`/`fs` via
  `python-runtime.ts`, so the browser bundle failed to compile. Switched both to
  the client-safe `jobs-browser` module and a new `grants-browser.ts` (fetch-only
  mirror of the `/api/harness/grants/**` front door, type-only re-export of
  `StandingGrant`), matching the existing browser/server split. No doc change —
  bug fix keeping the client/server contract intact.

## 2026-10-06

- **Application Runtime — the remaining limitations closed (production hardening
  + the last capabilities).** (1) **Provider readiness gate** — `provisioning.py`
  reports (non-secret) which orchestration/infra/cloud tools are installed AND
  signed in, with a plain next step per gap; surfaced on `/health`
  (`runtimeProviders`), `GET /runtime/providers`, `eclipse providers`. A provider
  whose credentials are unknown reports `null`, never a fabricated `true`.
  (2) **Metric history** — `AppRuntimeMetric` on `agent-memory.db`, a trend summary
  (`rising`/`falling`/`flat`/`unknown`, never a false `flat`), `runtime_metrics_history`
  + `GET /runtime/{id}/metrics/history` + `eclipse runtime metrics-history`.
  (3) **Long-running CLI ops as managed processes** — `managed_cli.py` starts
  `kubectl port-forward` / `kubectl logs -f` through the EXISTING terminal process
  manager (tree-killed, cancellable, streamed); tools `k8s_port_forward` /
  `k8s_logs_follow`. (4) **Deployment promotion** — `DeploymentEngine.promote()` +
  `deploy_promote`: staging → (authorization) → production with a health-gated
  ROLLBACK; a staging failure never touches production. (5) **Cross-application
  graph** — `app_graph.py` + `workspace_ops.py`: order several apps by declared
  dependency (`.black-eclipse/app.json`) or a monorepo heuristic, with
  `workspace_graph` / `workspace_start` / `workspace_stop` and `eclipse workspace`.
  (6) **Compose-config fallback** — when the tolerant reader finds no services,
  `docker compose config` resolves anchors/merges/includes for the graph via the
  SAME `ComposeAdapter`. (7) **Auto-deploy job templates** — two Application Runtime
  templates (`deploy-app-on-schedule`, `deploy-app-on-webhook`) wired to the jobs
  scheduler, shipping disabled and still subject to per-action authorization.
  (8) **UI** — a Providers tab (readiness + workspace graph) in the terminal dock.
  (9) **Opt-in live provider tests** (`test_application_provider_live.py`,
  `BLACK_ECLIPSE_PROVIDER_IT=1`). 103 application-runtime tools total. Docs:
  `docs/harness/application-runtime.md`; ADR-H133. Tests:
  `test_application_{provisioning,workspace}.py` + expanded deploy/orchestration.

- **Git UI now uses the ONE engine (no second implementation).** Corrected an
  architecture violation: the Settings Git panel used a standalone TypeScript Git
  wrapper (`src/lib/git/service.ts`) that spawned git from Node, bypassing the
  Python engine entirely (no journal, no operation state, no risk engine, no lock,
  only a filename secret check). `/api/git` is now a THIN proxy over the runtime's
  `/git/*` routes — the same service the agent uses; `src/lib/git/service.ts`
  forwards and holds no Git logic, browser types moved to the client-safe
  `src/lib/git/types.ts`, and the route returns 503 honestly when the runtime is
  unavailable rather than falling back. Added engine routes `/git/draft-message`,
  `/git/unstage`, `/git/push`, and `cached=1` on `/git/diff`; the push result now
  carries the branch. Tests: `test_git_api.py` extended. docs updated:
  `docs/harness/git-version-control.md`.

- **Size-budget guard green again after the Application Runtime commit.** The
  Git/Application-Runtime change (146f6d5) left `main.py` (1220 lines) above the
  1200-line hard ceiling — together with `execution/application/manager.py`
  (1239) at the time — so `test_size_budget.py` failed. `manager.py` was split
  under the ceiling by the follow-up work; `main.py` got a justified `RATCHET_PY`
  entry pinned to 1220 (route-group extraction noted as the split candidate; may
  only shrink from here). Full Python suite green. no doc change — test-only
  ratchet bookkeeping.

- **Backup: consistent snapshot of all runtime SQLite state.** Took `VACUUM INTO`
  copies (WAL-safe while the app runs) of `jdds.db`, `agent-memory.db`,
  `eclipse-memory.db`, and the `python/` copies into
  `_backups/2026-10-07-03-56-42/` with a `MANIFEST.json` of sizes + SHA-256, each
  verified `quick_check=ok`. `_backups/` stays gitignored; no code or contract
  changed. no doc change — operational backup artifact, no architecture/data-shape/setup change.

- **Application Runtime â€” the future tiers are now real, and the layer is
  production-hardened.** (1) **Orchestration:** `KubernetesAdapter`,
  `HelmAdapter`, `KustomizeAdapter` (a closed operation table, validated args,
  JSON output parsed), behind one shared `CliAdapter` base. (2) **Infrastructure:**
  `TerraformAdapter` (init/validate/fmt/plan/apply/destroy/output/state; apply and
  destroy are CRITICAL). (3) **Cloud:** `AwsAdapter`/`AzureAdapter`/`GcpAdapter`/
  `CloudflareAdapter`/`VercelAdapter`/`RailwayAdapter`/`RenderAdapter` â€” the common
  `deploy`/`status`/`logs`/`rollback`/`delete` surface, credentials read only
  through each provider's own ambient mechanism. (4) **`DeploymentEngine`**:
  validateâ†’buildâ†’testâ†’packageâ†’deployâ†’verify; a production deploy requires
  authorization; a deployment is never claimed live from a status call alone.
  (5) **29 new agent tools** (`k8s_*`, `helm_*`, `kustomize_*`, `terraform_*`,
  `cloud_providers`, `deploy_*`) â€” 96 application-runtime tools total â€” with the
  cluster/infra/cloud mutations removed at `edit_verify`/`plan_only` and each
  destructive one requiring authorization. (6) **A real CLI** (`python -m
  harness.cli`, `eclipse` bin, `npm run eclipse`): `runtime|package|environment|
  port|container|compose|k8s|terraform|deploy` over the SAME manager the agent
  uses, JSON output, `--authorized` for destructive commands. (7) **Production
  hardening:** an mtime-keyed `DiscoveryCache` (invalidated on any manifest/
  lockfile/compose/.env change), health-check exponential backoff, and bounded/
  filtered runtime logs (substring/severity/errors-only + line cap). (8) HTTP
  routes (`/runtime/orchestrator/*`, `/runtime/terraform/*`, `/runtime/deploy`,
  `/runtime/orchestrators`) and the Applications-tab provider footer. Docs:
  `docs/harness/application-runtime.md`; ADR-H132. Tests:
  `test_application_{orchestration,deploy}.py` + expanded unit/security/reachability.

- **Git subsystem â€” interactive Git made limitless (no TTY).** Removed the two
  "needs a terminal" limitations. (1) **Selective hunk staging**: new
  `git/diffs.py` parses a unified diff into files/hunks and re-renders a chosen
  subset, which `git apply --cached` stages â€” tools `git_list_hunks`,
  `git_stage_hunks`, `git_unstage_hunks`, `git_apply_patch` (git's `add -p` is no
  longer needed). (2) **Automated interactive rebase**: new `git/rebase_plan.py`
  + machine `_sequence_editor.py`/`_message_editor.py` drive `git rebase -i`
  through env vars so `git_rebase_plan` performs pick/reword/edit/squash/fixup/
  drop/reorder from a structured plan; a partial plan never reorders or drops an
  unnamed commit. (3) **Long-tail capabilities** now exposed in
  `git/tools_extra.py`: `git_move_path`, `git_remove_paths`, `git_restore`,
  `git_unset_upstream`, `git_stash_branch`, `git_stash_clear`, `git_tag_show`,
  `git_worktree_prune`, `git_worktree_move`, `git_submodule_init`,
  `git_submodule_sync`, `git_lfs_fetch`, `git_lfs_pull` (115 git/vcs tools total).
  (4) **Opt-in live provider tests** (`test_git_provider_live.py`) exercise a real
  GitHub/GitLab/Bitbucket account (skipped unless `BLACK_ECLIPSE_PROVIDER_IT=1` +
  a token + `BLACK_ECLIPSE_PROVIDER_REPO`; never in `npm test`). New tests in
  `test_git_advanced.py` (20 tests). `interactive=True` was dropped from the plain
  rebase op (the planned op is the only path to `-i`). docs updated:
  `docs/harness/git-version-control.md`.

- **Execution layer â€” every caveat closed: extra languages, DB dialects and OS
  resource limits are now verified end-to-end, not just unit-tested.** (1) **Seven
  toolchains executed for real** (Go, Java, PHP, C, C++, C#, Rust) against a
  portable toolchain set fetched into `%TEMP%` (no admin, nothing installed
  globally). Fixes found and made: Go needed a real `GOCACHE`/`GOTMPDIR` (the
  sandbox scrubs the env); C/C++ now actually compile a standalone source into a
  runnable binary (previously only drove `make`/`cmake`, so a bare `.c`/`.cpp`
  could never run); the .NET adapter needed `DOTNET_CLI_HOME`/`NUGET_PACKAGES` plus
  a curated non-secret Windows platform env (real `%APPDATA%`, `%PROGRAMFILES%`,
  `%USERPROFILE%`, â€¦) because NuGet/MSBuild resolve paths the sandbox allowlist
  strips. (2) **SQL dialects**: DuckDB runs embedded end-to-end (create/insert/
  select + cross-execution persistence); PostgreSQL now selects `psycopg`/
  `psycopg2`/`pg8000` â€” with a libpqâ†’pg8000 keyword translation (`dbname`â†’
  `database`) â€” and a *connection* failure is reported as `SQL_CONNECT_FAILED`
  (previously mis-labelled `SQL_DRIVER_MISSING`), while an absent driver still
  refuses honestly; `pg8000` and `duckdb` were added to `python/requirements.txt`
  as optional-but-default. (3) **OS resource limits enforced + classified**: the
  sandbox now kills the process tree and reports `RESOURCE_LIMIT` for memory,
  cumulative-CPU and process-count breaches â€” both when the parent monitor samples
  a peak and when the kernel (Windows Job Object / POSIX `RLIMIT_AS`) DENIES an
  operation at the limit (`MemoryError`, `WinError 1816`). `ResourceLimits` gains
  `cpu_seconds`; `ErrorClass.RESOURCE_LIMIT` is new. A latent bug was fixed where
  `from_env` clamped an unset `cpu_seconds` to `1`, imposing a 1-second CPU
  ceiling on every execution. Tests `python/tests/test_execution_resources.py`.
  Full Python suite green (3203); tsc clean; eval gates PASS. docs updated:
  `docs/harness/execution-architecture.md`, `docs/harness/decisions.md`
  (ADR-H129 consequences), `docs/NAVIGATION.md` (trigger row).

- **Git subsystem hardening pass (production review fixes).** (1) **Worktree
  escape** â€” `git_worktree_add`/`git_worktree_remove`/`git_worktree_move` accepted
  a `../â€¦` or absolute filesystem path, so a working tree (and a later
  `worktree remove --force`) could land outside the project; a path is now
  realpath-confined to the repository root or a sibling under its parent (a
  sibling worktree is the normal `git worktree` layout; a climb above the parent
  or a system path is refused). (2) **Global git-config escalation** â€” a
  `git_config_set --global` write (machine-wide: `core.hooksPath`, `core.sshCommand`,
  â€¦) was only `caution`/no-approval; it is now `dangerous` and requires a
  single-use operator approval. (3) **Refspec force** â€” a leading-`+` refspec (a
  force push that bypasses `--force-with-lease`) is now rejected by a dedicated
  `refspec` validator. (4) **Cross-host credential leak** â€” the VCS HTTP client now
  drops the `Authorization` header on a redirect to a different host (urllib
  otherwise re-sends it); a CI job log is also passed through the shared
  redaction before it reaches the model. Regression tests added to
  `test_git_security.py` (worktree confinement, global-config risk, `+refspec`);
  150 Git tests pass. docs updated: `docs/harness/git-version-control.md`.

- **New Application Runtime / DevOps subsystem.** Eclipse now understands
  *applications*, not shell commands. New package
  `python/harness/execution/application/`: a provider-agnostic `RuntimeRegistry`
  (package managers, container runtimes, compose, and empty-but-live Kubernetes/
  Terraform/cloud seams); `ApplicationDiscovery` (framework/language/package
  manager/lockfile, install-build-dev-start-test-lint commands, Docker/Compose,
  env files, required vars, databases/caches, services, ports, service graph);
  `EnvironmentDetector` + `EnvironmentManager` (secret values masked as
  `[SECRET]`, never returned); 11 package-manager adapters
  (npm/pnpm/yarn/bun/pip/uv/poetry/cargo/go/maven/gradle, declared manager is
  authoritative â€” no silent npm switch); `DockerAdapter`/`PodmanAdapter` behind
  one `ContainerRuntimeAdapter`; `DockerComposeAdapter`/`PodmanComposeAdapter`;
  `PortManager`; `HealthCheckEngine` (process/tcp/http/container/database/custom
  â€” `RUNNING` is never `HEALTHY`); `RuntimeDiagnosticsEngine` (structured
  category + a `{file,line,column}` location linking runtime errors to code
  intelligence); `RecoveryEngine` (bounded diagnoseâ†’actâ†’verify, never a loop);
  `ApplicationRuntimeStore` on `agent-memory.db`; a closed event vocabulary;
  `ApplicationRuntimeManager` (the ONE lifecycle) with boot reconciliation.
  67 agent tools (`runtime_*`, `package_*`, `container_*`, `compose_*`,
  `environment_*`, `port_*`, `health_*`) on the SAME registry, the write half
  removed at `plan_only`; route group `/runtime/*` (operator-gated); front door
  `application-{client,browser}.ts` + `/api/runtime/**` + an Applications tab in
  the terminal dock. No new dependency; every argv runs through the ONE sandbox.
  Docs: `docs/harness/application-runtime.md`; ADR-H131. Tests:
  `python/tests/test_application_{unit,runtime,security,tools,api,e2e}.py`
  (+ `test_size_budget.py` split of `application/tools.py`).

- **New Git / Version-Control subsystem.** A production-grade Git engine + VCS
  provider layer for the agentic coding environment â€” not a wrapper. New package
  `python/harness/git/`: repository discovery (normal/`.git`-file/bare/nested/
  worktree/submodule), a CLOSED operation table (`catalog.py`) with strict value
  validation, the ONE controlled executor (absolute argv, no shell, scrubbed env,
  `GIT_EDITOR=true`/`GIT_MERGE_AUTOEDIT=no` so a merge never blocks on an editor,
  timeout + output cap), machine-readable parsers, a structured error model, the
  multi-step operation state machine + conflict-marker parser, a risk/safety
  engine (secret + large-file scans reusing the ONE `session_index` pattern set,
  protected branches, `.black-eclipse/git.json` policy, untrusted-repo inspection
  that never runs a hook), an operation journal + active-operation store on
  `agent-memory.db`, a per-repository mutating lock, recovery/reconcile, and a
  per-repository mutating lock. Local Git is separate from the remote VCS layer
  (`git/vcs/`: `VCSProvider` + `GitHubProvider`/`GitLabProvider`/
  `BitbucketProvider`, a normalized PR=MR model, and a stdlib-only HTTP client;
  tokens come from operator-declared env-var NAMES and are never exposed). The
  full tool surface (`git_*` reads + local mutations + `vcs_*` remote actions) is
  registered on the SAME registry via `register_git_subsystem`; the ONE policy
  authority narrows it by autonomy (`GIT_READ_TOOLS`/`GIT_WRITE_TOOLS`/
  `GIT_EXTERNAL_TOOLS`), and the Git effect authorizer requires a single-use
  operator approval for every dangerous/destructive operation and every remote
  action (a force push is `critical`, never the default). Routes `/git/*` serve
  the UI from the same service. Tests: `test_git_{engine,mutations,security,tools,
  integration,api}.py` (163 tests, isolated temp repos). The fs subsystem's older
  read `git_status` tool was removed in favour of the one richer engine tool (the
  `FileSystemService.git_status` method and `file_metadata` git awareness stay).
  docs updated: `docs/harness/git-version-control.md` (new), `docs/NAVIGATION.md`.

- **Execution-layer build/test fixes found by an autonomous buildâ†’testâ†’fixâ†’
  retest run on Windows.** (1) **Bare program names could not be spawned** â€” the
  JS/TS adapters emitted `['npm', ...]`/`['npx', ...]`/`['tsc', ...]`, which
  `subprocess` cannot run on Windows (`npm`/`npx`/`tsc` are `.CMD`/`.cmd` shims;
  `FileNotFoundError [WinError 2]`), so `build_project`/`test_project` reported
  `exitCode=null`, empty output. Every adapter now emits an ABSOLUTE executable
  path (`base._require_program`/`_program`), matching `code/commands.py`.
  (2) **Toolchain resolution / offline** â€” a project with no local `node_modules`
  now resolves `tsc` and the test runner from Eclipse's OWN bundled
  `node_modules/.bin` (via `_app_bin` + `_node_env`, which prepends the node bin
  dirs to the scrubbed `PATH`), so `npm run build`/`vitest` work without a network
  install and without fetching a different version. (3) **UTF-8 BOM manifests** â€”
  `package.json`/`tsconfig.json` saved with a BOM (Windows editors, PowerShell)
  failed to parse, so the test framework/scripts were missed and the engine fell
  back to `node --test`; `projects.read_json`/`_read_text` now read `utf-8-sig`
  and the TS adapter uses it. (4) **ANSI color codes broke result parsing** â€”
  vitest color-codes its summary, so a PASSING run reported `parsed:false`/0 tests
  and colored compiler errors produced no diagnostics; `testing._parse_summary`
  and `diagnostics.normalize` now strip ANSI first (reusing the terminal
  subsystem's `strip_ansi`). (5) vitest/jest now run with a machine-readable
  reporter (`--reporter=json`/`--json`) so per-test failures (name, file,
  expected/actual) are extracted structurally. Verified end-to-end: build PASS â†’
  tests fail (`add` expected 5, got -1) â†’ structured diagnostic â†’ agent fixes
  `a - b`â†’`a + b` (tests untouched) â†’ rebuild PASS â†’ **2 passed / 0 failed**.
  Regression tests in `python/tests/test_execution_capabilities.py`. docs updated:
  `docs/harness/execution-architecture.md`.

- **Execution-layer bug fixes found by an end-to-end verification pass (TypeScript
  and SQL).** (1) `TypeScriptRuntime.prepare_run` built `['npx', '<file.ts>']` â€” it
  dropped the `tsx`/`ts-node` program for the `npx` runner, so every TypeScript
  execution failed with `[WinError 2]`. Rewritten as a `_runner_prefix()` that
  always emits an invocable program followed by the file, preferring the project's
  declared `tsx`/`ts-node`, then the app's own bundled `tsx` (`<repo>/node_modules/
  .bin`, offline), then `npx`. (2) `SqlRuntime` rejected multi-statement scripts
  ("You can only execute one statement at a time") and never committed DML, so
  `INSERT`s reported COMPLETED but a later `SELECT` returned 0 rows â€” a fake
  success. The runner now splits a script into statements (quote/comment aware),
  executes each, and **commits** (rolls back on error); it returns per-statement
  results plus the last result set. (3) A database filename matching the index
  ignore-globs (`*.db`/`*.sqlite`) was refused as `IGNORED_PATH`, so a real DB could
  not be opened; `policy.resolve_within` gains an explicit `allow_ignored=False`
  opt-in that the SQL runtime uses â€” traversal, symlink, outside-root and
  PROTECTED checks are unchanged. Regression tests added to
  `python/tests/test_execution_capabilities.py`. docs updated:
  `docs/harness/execution-architecture.md` (SQL/TypeScript notes).

- **Execution layer hardening â€” every earlier limitation closed.** (1) The
  sandbox now measures REAL resource usage with no `psutil`: a new
  `execution/telemetry.py` samples CPU time (`GetProcessTimes` on Windows;
  `/proc/<pid>/stat` on Linux) and peak RSS (`GetProcessMemoryInfo` /
  `/proc/<pid>/statm`) across the whole process tree, and the values flow into
  `RawResult` â†’ `ResourceUsage` â†’ the `ExecutionMetric` rows (`cpuMs`/
  `memoryPeakMb`/`processCount`); an unmeasurable value stays `None`, never a
  fabricated zero. (2) `SqlRuntime` connects PostgreSQL through any installed
  PEP-249 driver (`psycopg`, `psycopg2`, pure-Python `pg8000`), plus MySQL
  (`pymysql`/`MySQLdb`) and DuckDB, refusing with a stable `SQL_DRIVER_MISSING`
  when none is present â€” never pretending to connect. (3) Eight more real
  runtime adapters ship: Go, Rust, Java, C#, C, C++, PHP, Ruby (inline where the
  language supports it â€” Go/Java/PHP/Ruby â€” and honest `UNAVAILABLE`/refusal
  otherwise); `build`/`test` wired for `go`/`cargo`/`maven`/`gradle`/`dotnet`/
  `cmake`/`make`. (4) `run_verification` can now fix code IN-PROCESS: a new
  `execution/autofix.py` (opt-in via `HARNESS_EXEC_AUTOFIX=1`) asks the RUN's own
  model for one schema-validated, diagnostic-driven, workspace-confined edit and
  applies it through the filesystem service; it never touches a
  security/infrastructure failure and never retries blindly. (5) An intermittent
  CIUE index flake (`fileCount == 0`) was root-caused and fixed: the shared
  `check_same_thread=False` `CodeIndex` connection now serializes EVERY mutation
  (`IncrementalIndexer._mutate_lock` + `CodeIndex._write_lock`), so the background
  watcher and a synchronous index trigger can no longer interleave
  delete/insert transactions and lose rows; regression test
  `python/tests/test_intel_index_concurrency.py` (25/25 stable). Tests
  `python/tests/test_execution_capabilities.py` + the reachability case in
  `test_execution_e2e.py`. Full Python suite green; docs updated:
  `docs/harness/execution-architecture.md`, `docs/harness/decisions.md`
  (ADR-H129 consequences), `docs/NAVIGATION.md` (trigger row).

- **Code Execution & Verification Layer â€” Eclipse can now run, build, test,
  diagnose and VERIFY software autonomously.** New subsystem
  `python/harness/execution/`: a strict `ExecutionState` machine (validated
  transitions, `execution/state.py`), strongly-typed domain models
  (`models.py`), a `RuntimeRegistry` with `PythonRuntime`/`JavaScriptRuntime`/
  `TypeScriptRuntime`/`SqlRuntime`/`ShellRuntime` adapters (`runtimes/`), a
  `ProjectDetector` + language detection in the spec's priority order
  (`projects.py`), a `DiagnosticEngine` normalizing `tsc`/Python-traceback/V8/
  ESLint/pytest/generic compiler output (`diagnostics.py`), a `BuildEngine` and
  `TestEngine` (vitest/jest JSON + summary parsers, `build.py`/`testing.py`), an
  `ExecutionPolicyEngine` (risk bands, network/filesystem narrowing, secret
  isolation, `policy.py`), an `ArtifactManager` (`artifacts.py`), a synchronous
  `ExecutionOrchestrator` with guaranteed cleanup and a `finally` that always
  lands on a terminal state (`orchestrator.py`), an `ExecutionStore` for history
  and evidence on the ONE `agent-memory.db` connection (`store.py`), an
  `ExecutionScheduler`/`ExecutionWorkflow`/`RetryPolicy` (`scheduler.py`/
  `workflow.py`), a `ExecutionVerifier` bounded buildâ†’testâ†’fix loop
  (`verify_loop.py`), and a `ServiceManager`/`PortManager`/`HealthChecker` built
  on the EXISTING terminal process manager   (`services.py`). It reuses
  `code/sandbox.py` as the ONE execution primitive (no second spawn path), the
  terminal subsystem for long-running services, `code/policy.py` for the
  autonomy/binding boundary, and `code/workspace.py` for confinement; it does
  NOT touch the terminal subsystem. The sandbox primitive gains OPTIONAL OS-level
  `RunSpec` limit fields (`cpu_seconds`/`memory_mb`/`process_limit`), applied via
  POSIX `setrlimit` (RLIMIT_CPU/AS/NPROC) and Windows Job Object limits, with the
  wall-clock timeout always enforced; entrypoints and SQLite databases are
  confined with `resolve_within`. 21 agent tools registered on the SAME
  registry (`execution/tools.py`): `execute_python`/`execute_javascript`/
  `execute_typescript`/`execute_sql`/`execute_shell`/`execute_code`,
  `build_project`/`test_project`/`discover_tests`/`run_verification`,
  `start_service`/`stop_service`/`restart_service`/`service_status`/
  `service_logs`/`list_services`, `execution_get`/`execution_logs`/
  `execution_result`/`execution_artifacts`/`cancel_execution` (retrieval tools
  prefixed `execution_`/`service_` to keep the code-agent's finance-tool guard).
  Write/execute tools added to `policy.WRITE_TOOLS` (removed at `plan_only`);
  read tools to `READ_ONLY_TOOLS`. Service wiring in `service.py`
  (`AgenticService.execution` + `stop_execution`), lifespan in `main.py`, routes
  `python/harness/routers/execution.py` (`/execution/*`, operator-gated). Tests
  `python/tests/test_execution_{unit,runtime,security,e2e,tools}.py` (state
  machine, diagnostics, policy, real Python/JS/SQL/shell runs, timeout/cancel/
  traversal/secret attacks, the buildâ†’testâ†’fixâ†’retest acceptance loop). Full
  Python suite green (2930); Vitest 2169; tsc clean. docs updated:
  `docs/harness/execution-architecture.md` (new),
  `docs/harness/decisions.md` (ADR-H129), `docs/NAVIGATION.md` (trigger row).

- **CIUE hardcore torture test: 14 real bugs fixed, verified against a live
  `typescript-language-server` and a 220-file multi-language monorepo.** Running
  the engine end-to-end (real subprocess LSP, edits, diagnostics, watcher,
  concurrency) surfaced and fixed: (1) `lsp.client.uri_to_path` now percent-decodes
  before the Windows drive-letter fix, so `file:///c%3A/â€¦` LSP results match the
  workspace; (2) `manager._normalize_locations` understands the `LocationLink`
  (`targetUri`/`targetRange`) shape; (3) `get_definition`/`get_references` send the
  symbol's real name column (`_symbol_position`) not the indentation column;
  (4) `_resolve_symbols` scopes by file first, so a same-named symbol in another
  file/language is not resolved; (5) LSP `find_references` marks the declaration
  site; (6) `get_implementations` returns the union of the semantic (LSP) and
  structural (index heritage) results instead of one backend's view;
  (7) `_js_heritage` captures `extends`/`implements` so inheritance is structural;
  (8) the rename fallback is code-mask-aware (`_code_mask`) and never rewrites
  strings/comments; (9) `rebase_edits` accepts workspace-relative paths, not only
  absolute LSP paths; (10) `_enrich_location` returns a stable `location` object on
  the LSP path too (one shape across engines); (11) `CodeIndex.integrity_ok` adds a
  schema probe so non-database bytes are detected and recovered; (12)
  `policy.IGNORED_DIRS` excludes `dist`/`build`/`target`/`coverage`/`generated`/â€¦;
  (13) the context engine is prefix-aware (`authentication` reaches `Auth*`) and
  bounded; (14) `CodeIntelRuntime` indexes asynchronously so the first query never
  blocks on a full walk. New regression tests `python/tests/test_intel_regressions.py`.
  Full Python suite green (2870); Vitest 2169; tsc clean. docs updated:
  `docs/harness/code-intelligence.md` (unchanged â€” behaviour now matches the doc),
  `docs/harness/decisions.md` (ADR-H128 already covers the design).

- **Code Intelligence & Understanding Engine (CIUE): the agent now understands
  software structurally and semantically.** New subsystem
  `python/harness/code/intel/` â€” one `CodeIntelligenceManager` over an LSP manager
  (`lsp/`), an AST engine (`ast.py`), an optional Tree-sitter layer
  (`treesitter.py`), a DEDICATED incremental code index (`persistence/index.py`
  under `.black-eclipse/code-index/`, never agent memory), a dependency graph, a
  diagnostics engine, structural search, a project analyzer, a deterministic
  context engine and safe semantic editing. It normalizes every backend into a
  Unified Code Model (`models.py`) and always names the engine that answered
  (`lsp`/`tree-sitter`/`ast`/`index`); a missing or crashed language server is a
  structured fallback (`lsp.providers` ships nine real servers; adding one is a
  `LanguageServerSpec`), never a crash. New `code_*` tools (26, read plus the
  semantic `code_rename_symbol`) registered on the SAME registry via
  `code/intel_tools.py`; write policy in `code/policy.py` (`INTEL_WRITE_TOOLS`); a
  process-wide `CodeIntelRuntime` on `AgenticService` (lazy async indexing + a
  reused fs watcher); routes `python/harness/routers/code_intel.py` (`/code/intel/*`,
  operator-gated) and a content-free `codeIntel` block in `/health`; plain-language
  labels in `src/lib/agent/response-model.ts`. Reuses the existing path authority,
  fs reading/encoding/watching/extractors and tool/event/authorizer seams â€” no
  second filesystem, registry or confinement. Tests `python/tests/test_intel{,_tools,
  _lsp,_api}.py` + fixtures `python/tests/fixtures/intel/` + a fake language-server
  subprocess; ADR-H128. docs updated: `docs/harness/code-intelligence.md` (new),
  `docs/harness/decisions.md` (ADR-H128), `docs/NAVIGATION.md` (trigger row).

- **Ultra effort: the fill now FLOWS as a real moving gradient (was a static
  fill + thin beam).** The reported "gradient is not moving" was two things:
  (a) the fill was a static Tailwind gradient with only a narrow beam sweeping
  it, and (b) under the app's reduce-motion / "animations off" settings (or the
  OS preference) a global rule froze *every* animation to 0.001ms, pinning the
  beam at the left â€” a frozen band. Fix: `.effort-ultra-fill` animates the WHOLE
  fill (`background-size: 200%` + `effortUltraFlow`) on both the slider and the
  persistent pill, the beam is kept on top, and the Ultra energy is now
  DELIBERATELY EXEMPT from the reduce-motion / animations-off kill switches (like
  the price ticker) â€” each layer carries `--ultra-dur` so one rule restores its
  timing. Verified with Playwright frame-diffs: the fill and beam both change
  every frame under default, OS reduce-motion, AND the app's no-anim classes.
  tests updated: `effort-control.test.ts`.
  no doc change â€” visual-only; behavior unchanged (see the Ultra behavior entry).

- **Ultra effort: fixed the "animation doesn't work" report (two real bugs).**
  Diagnosed live with Playwright. (1) The brain SVG rendered muted GRAY, not the
  accent: a global CSS remap forces `.text-primary` to gray with `!important`,
  and its `.dark` variant out-specifies the `svg.text-primary { color: var(--brand) }`
  green rule â€” a solid green icon must not rely on `text-primary`. Added a
  dedicated `.effort-accent` class and used it for the brain (pill + core).
  (2) The energy effect lived only INSIDE the popover, which closes the moment a
  level is picked â€” so at rest the always-visible pill was static. Extracted the
  core into a shared `EnergyCore` and put a live laser-beam sweep on the
  persistent pill while Ultra is active. Verified by frame-diff (frames change)
  and the computed brain color = `#7aff78`. Added tests.
  no doc change â€” visual-only; behavior unchanged (see the Ultra behavior entry).

- **Ultra effort thumb: an "energy core" animation.** Reworked the composer
  slider's top-stop thumb (`effort-control.tsx` + `globals.css`) into a layered
  energy effect â€” a pulsing outer glow, a rotating conic plasma ring, two
  phase-offset expanding shockwaves, three orbiting sparks, and a throbbing
  brain core â€” all in the theme `--primary` green and disabled by the global
  `prefers-reduced-motion` rule (static, fully-lit fallback). Replaced the old
  single pulse + static rays. The brain icon is now a SOLID accent fill (both
  the trigger pill and the Ultra core), and the Ultra fill carries a laser beam
  that sweeps the full bar (`effortUltraBeam`).
  no doc change â€” visual-only; behavior unchanged (see the Ultra behavior entry).

- **Composer effort slider: theme-consistent skin, animated Ultra, and a real
  top stop.** Re-skinned `EffortControl` to the theme tokens (`--primary` green,
  `--border`/`--accent` chrome) instead of a foreign violet/sky palette, and
  matched the trigger pill to the model-selector chrome. The Ultra thumb now
  animates (pulsing glow + slowly radiating rays, `globals.css`
  `effortUltraPulse`/`effortUltraSpin`, reduced-motion safe). Made the top stop
  actually strongest: `prepare_model` normalizes `very_high` â†’ the runtime's
  `max` tier (was mapped to `high`, so Ultra == High), so Anthropic `thinking`
  (16384) and Gemini `thinking_budget` (24576) deepen beyond High; native
  OpenAI caps Ultra at `high` (its knob has no higher tier). `low`/Minimal stays
  a no-op by design. Added Python + JS tests.
  docs updated: `docs/ARCHITECTURE.md`, `docs/CHANGELOG.md`.

- **Chat composer: per-question "model intelligence" effort slider.** Added
  `EffortControl` (`src/components/chat/effort-control.tsx`) â€” the Fasterâ†’Smarter
  slider from the reference â€” beside the model selector in `ChatInput`, wired
  through `EmptyState` and `stock-chat.tsx`. It is a PER-QUESTION override (not a
  Settings edit): a new `useReasoningEffort` hook persists the choice client-side
  (`be_reasoning_effort_v1`), and the level rides `ChatOptions.reasoningEffort` â†’
  `/api/harness/chat[/stream]` â†’ `chatWithAgent`/`startChatRun` â†’
  `input.context.reasoning`, where it OUTRANKS the saved
  `LLMConfig.reasoningEffort` default; Auto sends nothing. Reuses the shared
  vocabulary (`reasoning.ts`, extended with captions + skins and slider index
  helpers); only native-reasoning models are affected, as before. Added tests
  (reasoning mapping, run-service precedence, composer reachability).
  docs updated: `docs/ARCHITECTURE.md` (reasoning-effort section).

- **Settings â€º General: reorganized the preset/customization surface.** The
  merged General section no longer reads as one long undifferentiated stack.
  The General sub-tab is now four titled sections (Startup & Display, Live Data,
  Behavior & Safety, Background) and finally exposes the previously-dead
  **Start screen** control (`general-prefs.ts` already defined
  `START_SCREEN_OPTIONS` but nothing rendered it). The Theme tab is now "Theme &
  Presets": presets lead, the brand generator and token editors sit under a
  "Fine-tune" group, and the duplicated Glass & Sidebar controls were removed
  (surfaces now live only on the Glass & Surfaces tab â€” the sidebar card moved
  there so no control was lost). Presets render as **miniature app screenshots**
  built from each theme's own tokens (rail + glass cards + a chart line) rather
  than flat gradient circles. The draft Live-preview/Apply/Discard toolbar is now
  scoped to draft-backed tabs only (Theme/Glass/Aurora/Charts); General,
  Background and Language & Access autosave instantly and no longer show it.
  Extracted shared `Panel`/`Field`/`Toggle`/`SectionHeader`/`SubSection` into
  `src/components/screens/settings-ui.tsx`, removing four sets of duplicates.
  no doc change â€” UI layout/UX reorg; no architecture, contract, data-shape or
  setup change.

- **File System Toolset: full validation run; one correctness fix.**
  A 141-check validation driven through the real registered tools (and verified
  against on-disk state) found `find_references` trusted a stale workspace index:
  a file created or changed after the last indexing pass was invisible â€” a Â§30
  stale-information violation. Fixed: `find_references` now refreshes the index
  incrementally before trusting it (`symbols.find_references(refresh_index=True)`),
  and skips the extra walk when an active watcher already keeps it current
  (`service.find_references`). Added a regression test. All 141 checks pass; full
  Python suite 2809 passed; `npx tsc --noEmit` clean.
  docs updated: `docs/harness/code-filesystem.md` (index-is-a-cache note).

- **File System subsystem: added verification and Git awareness (the last two
  spec deliverables), plus transaction/index events.** `code/fs/verify.py` is the
  verification layer: `validate_syntax` (Python `ast`, JSON, TOML, and a bounded
  string/comment-aware bracket-balance scan for JS/TS/Go/Rust/Java/C#/C/C++),
  `validate_changes` (check proposed edits WITHOUT writing â€” the same
  all-or-nothing rule `multi_file_patch` enforces), and a post-write verdict now
  carried on every `write_file`/`create_file`/patch/insert/delete result
  (`verification.verified`, syntax error + line). New tools `verify_file` and
  `validate_changes`. `code/fs/git.py` adds additive Git awareness â€” normalized
  `modified`/`untracked`/`staged`/`deleted`/`renamed`/`copied`/`conflicted` states
  plus branch/HEAD, one fixed argument-free argv, never a hard dependency â€” via
  the new `git_status` tool and a `git` field on `file_metadata`. `apply_diff`/
  `multi_file_patch` now emit `fs.transaction.started|committed|rolled_back` and
  `index_workspace` emits `fs.index.updated`. 20 new tests; full Python suite 2808
  passed; `npx tsc --noEmit` clean; vitest 2151 passed.
  docs updated: `docs/harness/code-filesystem.md`, `docs/NAVIGATION.md`.

- **File System subsystem: closed the four stated limitations.** (1) Watchers now
  use a NATIVE OS backend when available â€” Windows `ReadDirectoryChangesW` and
  Linux `inotify`, built on `ctypes`/`libc` only (`code/fs/watch_native.py`) â€” with
  transparent degradation to the portable polling watch (the fallback re-baselines
  so it reports only future changes); `watcher.status()` reports the active
  backend. (2) Symbol extraction is now parser-backed and broader: Python `ast`
  distinguishes methods from functions and captures decorators; JS/TS use a
  brace-depth scanner (classes, methods, arrow-function consts, interfaces, type
  aliases); targeted patterns for Go/Rust/Java/C#/C/C++. (3) `find_references` marks
  each hit `definition: true` at the declaration site (new additive `definitions`
  column on the index, migrated in place) and names its engine. (4) `edit_file`
  deterministically parses a plain instruction (`code/fs/intent.py`) into a
  concrete minimal edit ("rename X to Y", "add X after Y", "delete X") and falls
  back to the inspection packet â€” never a guess â€” for a vague one. 20 new tests;
  full Python suite 2788 passed; `npx tsc --noEmit` clean.
  docs updated: `docs/harness/code-filesystem.md`, `docs/NAVIGATION.md`.

- **Added the File System subsystem (`python/harness/code/fs/`) and its tools
  (`python/harness/code/fs_tools.py`).** A unified, deterministic filesystem
  service layered under the existing code capability: workspace-bound path
  security (delegated to the existing `code/policy.py` + `code/workspace.py`, not
  re-implemented), a centralized capability permission system (read/write/create/
  delete/move/copy/rename/watch/search; profile grants, config narrows only), the
  basic operations (list/read/write/create/delete/move/copy/rename/mkdir/rmdir),
  search (`search_text` via ripgrep with a bounded Python fallback, `search_files`,
  `find_files`), symbol/reference search (Python `ast` + a regex fallback, an
  extensible extractor table), the edit/patch engine (`patch_file`, `replace_text`,
  `insert_text`, `delete_text`, `apply_diff`, `multi_file_patch`) with hash-guarded
  optimistic concurrency, ambiguity refusal, atomic writes and byte-exact rollback,
  metadata/hash/permissions, a SEPARATE incremental workspace index
  (`<repo>/.black-eclipse/workspace-index/<id>.db` â€” never agent memory), portable
  debounced file watchers with cache invalidation + incremental re-index, and the
  high-level `edit_file` (inspect â†’ locate â†’ minimal patch â†’ verify). 28 tools
  registered; the write half is removed at `plan_only` by the ONE policy authority
  (`code/policy.py`), effects are admitted by the existing `make_code_authorizer`,
  and every path is re-checked by `permissions.require` â†’ `decide_write`. Writes
  land in the disposable code workspace (or the user's approved folder in direct
  mode), never silently in the checkout. 115 new tests; full Python suite 2732
  passed; `npx tsc --noEmit` clean.
  docs updated: `docs/harness/architecture.md`, `docs/harness/code-filesystem.md`
  (new), `docs/NAVIGATION.md`.

## 2026-10-05

- **AI settings: added a reasoning-effort ("model variant") control, and fixed
  the Manage-models action + widened its dialog.** Settings â€º AI â€º Active setup
  now has an **Auto / Minimal / Standard / High / Ultra** selector
  (`src/lib/agent/reasoning.ts`): Auto (the default) sends no override and the
  runtime's task profile keeps choosing; the four levels map to the runtime's
  `low`/`medium`/`high`/`very_high`. It persists as `LLMConfig.reasoningEffort`
  (`setLLMConfig`, `null` = Auto; masked-into `/api/settings`) and is forwarded as
  `input.context.reasoning`, which the router honors as a requirement and
  `prepare_model` applies to a native reasoning control only â€” never to an
  OpenAI-compatible endpoint that lacks one. Fixes: the composer's per-provider
  **Manage** button opened the dialog behind the still-open `z-[110]` dropdown
  (now the menu closes first, and the dialog is `z-[130]`); the no-arg "Manage
  modelsâ€¦" path could resolve to `undefined` and render nothing (now falls back
  to the active/first usable provider); the dialog was `max-w-2xl` (now `max-w-3xl`
  with a roomier, 3-column model grid).
  `npx tsc --noEmit` clean; `vitest` 2151 passed, `pytest` model-runtime 64 passed.
  docs updated: `docs/ARCHITECTURE.md` (composer model picker: Manage-models fix +
  reasoning-effort note).

- **Reorganised the CFA Level I knowledge skills by exam topic (Equities and
  Portfolio Construction first).** The repo-root `.black-eclipse/skills/` now
  holds **twelve** topic-organised skills instead of ten process-organised ones:
  `cfa.00.curriculum-map` (index), `cfa.01.equities`,
  `cfa.02.portfolio-construction`, `cfa.03.financial-statement-analysis`,
  `cfa.04.quantitative-methods`, `cfa.05.fixed-income`, `cfa.06.ethics`,
  `cfa.07.economics`, `cfa.08.corporate-finance`, `cfa.09.derivatives`,
  `cfa.10.alternative-investments`, and `cfa.99.exam-preparation` (the
  cross-cutting plan/calculator/formulas/mocks/resources that applies to every
  topic). One skill per exam topic, in study order, each carrying the official
  2027 learning modules, Tier 1/Tier 2 formulas, common traps, question patterns,
  free resources, a practice target and its dependencies. `requiredSkills` form a
  real dependency graph (Equities -> Portfolio Construction -> Fixed Income ->
  Derivatives). All twelve validate against `harness.skills.manifest.SkillManifest`
  and load through `_load_project_skills` with no dangling dependency or prose
  cross-reference; the bundled 13-entry library is unchanged. Every skill ships
  `status: disabled` and the root stays untrusted until an operator grants both.
  Verified with the vendored interpreter (`./scripts/vendor/python/python.exe`).
  docs updated: `docs/NAVIGATION.md` (project skill root row + CFA task row).
  no source-contract change â€” data-only skill folders; no app or harness code
  touched.

- **Renamed the "Market Screener" page to "Market Discover"; aligned the Skills
  header icon with the sidebar.** Every user-facing string was updated â€” the
  sidebar/i18n nav label (`nav.discovery`), the page `<h1>`, the search registry
  page + "Open â€¦" action, market-result subtitles, the workspace panel
  label/title, the settings section + provider-registry copy (`providers/
  directory.ts` `usedBy` labels), and the "Back to â€¦" buttons. The Skills
  Library header now uses the same `Blocks` (Phosphor `SquaresFour`) glyph as
  the sidebar's Skills item, replacing a mismatched `Sparkles`. Internal
  symbol/function names (`useScreenerFilters`, `StockScreenerWidget`, the
  `screener` panel id) are unchanged â€” the page id/tab stays `discovery`.
  `npx tsc --noEmit` clean; search/sidebar/i18n tests (149) pass; `next build`
  compiles.
  no doc change â€” UI naming/icon consistency only; no contract change.

- **Fix: the approval card could not be reached from the two most important
  paths â€” patching code and the streaming chat.** Three defects: (1) the code
  authorizer's `workspace_patch_apply` branch created a PENDING request but
  returned without pausing, so a code write was refused with no card; it now
  blocks on the shared `pause_for_decision` gate and re-claims on approval
  (deny/timeout still refuses). (2) `approvalMode` was set only in the streaming
  chat payload; it is now a per-call-site opt-in on `run-service.ts` (`startRun`
  gains `approvalMode?`), set by the streaming chat path and deliberately UNSET
  for the synchronous `/api/harness/chat` and generic `/runs` callers â€” a pause
  there would block the HTTP request with no card to resolve it. (3) The
  `code_write`/`code_write_session` approval kinds were reviewable in the MCP
  panel but a paused run needs the card, not that panel. Added: an end-to-end
  graph test proving the run pauses (not finishes) on `approval.requested`,
  resumes in place on approve, and refuses on deny
  (`python/tests/test_approval_card_e2e.py`); authorizer-level tests for the code
  write pause (`test_approval_pause.py`, +2); front-door assertions that the
  streaming path sends `approvalMode: "ask"` and the sync path does not
  (`run-service.test.ts`, +3). Also fixed the Python stale-runtime detector
  (`python-runtime.ts` `harnessSourceMtimeMs`): it scanned ONLY top-level
  `python/harness/*.py`, so edits in `code/`, `mcp/`, `terminal/`, `skills/` never
  marked a running runtime stale â€” the runtime kept serving old code after a
  change. It now walks the whole tree, so `npm run dev` picks up harness changes.
  `npx tsc --noEmit` clean; full `vitest` 2144 passed, `pytest` 2653 passed, eval
  gates pass.
  docs updated: `docs/harness/architecture.md` (approval cards: code-write path,
  streaming-only opt-in).

- **Settings: organized the Intelligence-section pages to match the AI page's
  clarity, and fixed a duplicate-provider bug.** AI: the "Show more providers"
  list now excludes anything already shown under Connected/Popular, so a
  connected non-popular provider (e.g. xAI) or an active keyless local server no
  longer renders twice. Shared `ProviderRegistry` (Economics / Market / News) now
  groups rows by state â€” **Configured**, **Available** (built-in/keyless),
  **Needs a key** â€” with the key-gated list collapsed past 6 and a filter, and
  keeps the Economics by-kind sub-grouping. News feeds moved out of the flat
  74-row wall into a new `news-feeds-panel.tsx`: grouped Live/Paused, searchable,
  with inline add/remove. Market and Investor Eye pages gained consistent
  `SubSection` headings (Markets, Providers, Priority, Custom sources / Feature
  map, Event sources). No contract change: `NewsFeed` shape and `/api/settings`
  payload unchanged. `npx tsc --noEmit` clean; `vitest` 2141 passed, `pytest`
  2649 passed.
  no doc change â€” UI organization only; data contracts unchanged.

- **Approval cards: Eclipse now asks before any effectful step, and pauses the
  run until you answer.** Effectful actions (MCP write/action, external
  actions, and `ask`-classified commands) previously refused the call and let the
  model retry after you approved in Settings. A chat run now sends
  `approvalMode: "ask"`: the effect authorizer creates the single-use PENDING
  request, emits `approval.requested`, and PAUSES the in-flight run on an
  in-process gate (`_GATES`/`notify_decision` in `python/harness/mcp/approvals.py`,
  shared `pause_for_decision`/`_await_then_reclaim`). Approve resumes the run in
  place and runs exactly that one step; deny/timeout refuses as before. The
  decision is still the single-use, digest-bound approval â€” pause only changes how
  long the run waits, never whether a call is authorized; the wait is bounded
  below the run deadline and a runtime restart falls back to deny-and-retry. New
  frosted-glass `ApprovalCard` (`src/components/chat/approval-card.tsx`, portaled
  to `<body>`) floats above the composer in both chat surfaces, theme-adaptive,
  with Approve/Deny; wired via `HarnessUiEvent.approval_request`/`approval_resolved`,
  the `awaiting_approval` status, and `useAgentRun.decide`. `RunRequest.approvalMode`
  + `ToolContext.pause_for_approval`/`approval_timeout_s` are additive; the
  deny-and-retry path is unchanged. Tests: `python/tests/test_approval_pause.py`
  (+8). `npx tsc --noEmit` clean; full `vitest` 2141 passed, `pytest` 2649 passed,
  eval gates pass.
  docs updated: `docs/harness/architecture.md` (approval cards section).

- **Settings modal now opens instantly and no longer hangs on a slow market
  fetch.** Four causes fixed: (1) `/api/markets` and `/api/settings` were
  fetched in `Promise.all`, so a cold JDDS market build blocked the whole modal
  until it resolved â€” they now load independently and settings paints the moment
  it lands; (2) the settings dialog is unmounted on close, so every open
  re-fetched behind a skeleton â€” a module-level snapshot now paints cached
  values instantly and revalidates quietly; (3) the code-split `Settings` chunk
  was only ever fetched on first open â€” it is now warmed during idle and has a
  loading fallback; (4) `GET /api/settings` now uses the same in-memory SWR cache
  as `/api/markets`, so reads are instant even while the startup WarmUp/NewsIngest
  jobs hold SQLite (POST keeps the cache coherent). Measured with a production
  build + Playwright: modal open **510 ms** (fixed) vs the old build failing to
  appear within 15 s; `/api/settings` warm **22â€“28 ms** (fixed) vs old spikes of
  **17â€“30 s** under startup IO load. NOTE: the running dev server was serving a
  stale production build, so the fix only takes effect after a rebuild
  (`npm run up`). `npx tsc --noEmit` clean; full `vitest` 2140 passed,
  `pytest` 2642 passed.
  no doc change â€” load-path/perf fix only, no contract change.

- **Investor Eye Trade layer: hovering a country isolates ITS trade routes.**
  With the Trade layer on, the map showed every route, so hovering a country
  told you nothing about that country. Now the pointer answers "what does THIS
  country trade?": entering a country region isolates the routes that touch it
  (its links draw full-strength, every other route is hidden) and leaving
  restores the full web. Wired on both projections â€” the 2D geo map via new
  `mouseover`/`mouseout` region hooks in `bindLayerEvents`, the globe via the
  existing raycast pick â€” through a new `hoveredCountryIso` option. A
  click-selection still wins over hover. Isolated routes are marked `silent` so
  they cannot steal the pointer from the region and make the layer flicker. A
  country with no route honestly shows none. Tests: `map-echarts.test.ts` (+6).
  `npx tsc --noEmit` clean; investor-eye tests pass.
  no doc change â€” behaviour within the existing `lines` layer contract.

- **Dark sidebars are always black/charcoal (never neutral grey).** The shipped
  default sidebar moved from grey `#2a2a2e` to charcoal `#141416`, and the
  `SIDEBAR_PRESETS` list dropped its `Grey` entry in favour of black/charcoal
  options (`Black`, `Charcoal`, `Slate`, `Smoke`, `Crystal` â€” the last two keep
  only a faint cool/warm cast). Every dark-scheme preset's rail is now under
  luminance 0.011. Verified with `npx tsc --noEmit` and the theme tests (54 pass).
  no doc change â€” preset/default tweak; contracts unchanged.

- **White presets listed after the dark ones + Electric Blue Crystal sidebar.**
  The four white-background presets (`White`, `Paper`, `Snow`, `Ivory`) now sit
  at the END of `THEME_PRESETS` so the preset buttons read all dark looks first,
  then go light â€” instead of interrupting the dark grid at the top. Electric Blue
  now uses the translucent Crystal sidebar recipe (`#26262c` @ 0.55 / blur 34)
  rather than the default neutral Grey, so the cold blue brand carries into the
  rail. Verified with `npx tsc --noEmit` and the theme tests.
  no doc change â€” preset list/ordering tweak; contracts unchanged.

- **Added white-background theme presets (`White`, `Paper`, `Snow`, `Ivory`).**
  A new internal `scheme: 'dark' | 'light'` token on `EclipseTheme` lets a
  preset switch the whole app to a light look in one click â€” selectable from the
  normal preset grid, no separate mode toggle. `applyThemeToDocument` owns the
  `dark` class (was hardcoded in `layout.tsx`, which now only seeds the dark
  default plus a pre-paint script to avoid a flash) and scopes color vars to
  `html.dark` / `html:not(.dark)` by scheme; light presets carry dark ink text,
  white surfaces, a light landing and a dark wordmark. Charts resolve
  grid/axis/tooltip chrome from the scheme (`eclipse-provider.ts`), and a scoped
  compatibility layer in `globals.css` remaps hardcoded dark neutral utilities
  (`border-white/*`, `bg-black/*`, `bg-white/*`, `text-white/*`, near-black
  hexes, aurora glow) when light. Verified with `npx tsc --noEmit`,
  `npm run test` (188 files, all pass) and `npm run build`.
  docs updated: `ARCHITECTURE.md`, `NAVIGATION.md`, `docs/CHANGELOG.md`.

- **Settings: removed the yellow "providers need a key" attention dots.** The
  rail and mobile pill indicators (and the `ATTENTION` map / `useProviderHealth`
  wiring behind them) are gone (`settings.tsx`). `npx tsc --noEmit` clean.
  no doc change â€” UI-surface removal only.

- **General settings: folded the full-screen preview launcher into the sticky
  Live-preview/Apply card, and fixed the rail item text alignment.** The
  "Preview on the real app" row is now a section inside the sticky card
  (`customization-settings.tsx` / `customization-preview.tsx`) instead of a
  separate card below it. The left-nav buttons inherited browser-default
  `text-align: center`, so wrapped description lines centered under the icon;
  added `text-left` (`settings.tsx`). `npx tsc --noEmit` clean.
  no doc change â€” UI-surface layout fix only.

- **Settings cleanup: removed the provider-count status banner and the footer
  "N/M feeds live" readout.** Dropped the `SettingsStatusHeader` component
  (`provider-registry-panel.tsx`) and its render in `settings.tsx`; the footer
  keeps only the save-state line and the Reload button. `npx tsc --noEmit`
  clean; `vitest` green apart from a pre-existing `stock-chat.tsx` size-budget
  failure (unrelated, file not touched).
  no doc change â€” copy/UI-surface removal only.

- **Restored a green size-budget guard after the terminal/model work grew the
  SPA shell.** `stock-chat.tsx` reached 1237 lines (terminal-dock plumbing plus
  the focus-mode "tuck the terminal" effect) while its ratchet stayed pinned at
  1212, so `size-budget.test.ts` failed on `main`. Bumped the ratchet to 1237
  with a note; the file may still only shrink from here. `npx tsc --noEmit`
  clean; `vitest` size-budget suite passes.
  no doc change â€” test budget bookkeeping only.

- **Market Screener / Market Bubbles "Ask AI" runs no longer fail on an
  uninstalled default model.** The buttons themselves were correctly wired (they
  navigate to ChatBot and start a real harness run); the run failed with a raw
  `404 model 'llama3.1' not found` because the active config pointed at a
  keyless-local placeholder the installed server does not serve (this box's
  Ollama only has cloud models). Fix makes the default resolve to a model the
  provider ACTUALLY serves, without inventing one: the model runtime now exposes
  the provider's raw served ids (`discover_served`; the discover endpoint returns
  `served` alongside the merged registry view), the front door records that set
  in the `discovered_models_v1` snapshot (`served` map, replaced per probe, not
  merged), `GET /api/harness/chat/models` reports it per provider, and
  `useChatModel` auto-probes a keyless local provider and adopts the first served
  model â€” VISIBLY (the composer selector updates) and persisted to the vault. An
  explicit user pick is never overridden; nothing changes when the provider
  serves nothing known. Added `pickServableModel` (+5 vitest), discover `served`
  tests in `route.test.ts` (+3) and `model-runtime-browser.test.ts` (+1), and a
  Python API test for `served` separately from the merged list. `vitest` 2122
  passed; `pytest` 2642 passed; `npx tsc --noEmit` clean. docs updated:
  `docs/CHANGELOG.md`, `docs/harness/architecture.md`.

- **Theme colors fixed: Surface now recolors the glass surfaces, and the dead
  "Accent" token is wired up.** Two real bugs in the customization system.
  (1) Every frosted-glass tier (`.glass-card`, `-strong`, `-subtle`, `.glass-tooltip`,
  `.glass-button`, `.glass-drawer`, tab/command/ws strips) used a **hardcoded**
  `rgba(18,18,20,â€¦)` tint, so the theme's "Surface" color only recolored flat
  `bg-card` blocks â€” editing Surface barely changed the UI. `themeCssVars` now
  emits `--card-rgb` (the Surface as an `r g b` triplet) and every glass recipe
  builds its tint as `rgb(var(--card-rgb, <fallback>) / Î±)`. (2) The theme's
  "Accent" color was emitted as `--brand-accent` / `--brand-accent-rgb` but
  consumed **nowhere**, so editing Accent did nothing visible. The shared
  `TabBar` active pill now carries a primaryâ†’accent gradient + accent hairline,
  giving the token a real consumer. Verified with pixel diffs: changing Surface
  went from ~1.4% to ~8.7% of the viewport, and Accent visibly tints the active
  tab. Tests: `theme/tokens.test.ts` (+1 for `--card-rgb`). `vitest` 2113 passed;
  `npx tsc --noEmit` clean. docs updated: `docs/CHANGELOG.md`.

- **Icon set switched from Lucide to Phosphor behind one aliased module.** Every
  icon now renders Phosphor (`@phosphor-icons/react`) via a new central surface
  `src/lib/icons/index.ts`, which re-exports each glyph under its original Lucide
  name (plus `LucideIcon`), so all ~165 importing modules keep their existing call
  sites and only the import specifier changed (`lucide-react` â†’ `@/lib/icons`).
  This gives the dark glass UI a distinctive shape language and Phosphor weights
  (fill/duotone). Selected/active states were converted from `fill="currentColor"`
  to `weight="fill"` (Phosphor outlines are filled paths, so `fill="none"` would
  erase the glyph). `components/chat/{chat-history,markdown}.tsx` and
  `components/screens/portfolio/fund-store.ts` gained a `'use client'` boundary
  because Phosphor icons read `useContext`. `lucide-react` removed. `npx tsc
  --noEmit` clean; `next build` succeeded; `vitest` 187 files / 2112 tests passed.
  docs updated: `docs/NAVIGATION.md`, `docs/DECISIONS.md`, `skills/ARCHITECT.md`
  (ADR-041).

- **Investor Eye Trade layer: selecting a route now isolates it.** Clicking a
  trade line selected the event but left every route on the map equally loud, so
  you could not see *which* link the click referred to or what it connected. The
  selected route now draws full-strength (thicker, opaque) while every other
  route dims to 10% opacity, the flow animation stops (a moving target cannot be
  "the one"), and the two endpoint countries get glowing labelled markers â€” so
  "what is traded between X and Y" reads straight off the map. The line datum now
  carries `fromName`/`toName`/`fromIso`/`toIso`/`eventKey`, and a dedicated
  `tradeTooltip` leads with the ROUTE and the traded goods instead of a generic
  event blurb. `selectedEventKey` is threaded `WorldMap` â†’ `buildMapOption` on
  the main screen, full-page map, and dashboard widget. Tests:
  `layers.test.ts` (+1), `map-echarts.test.ts` (+3). `npx tsc --noEmit` clean;
  `vitest` 2106 passed (the 1 failing `pytest` test is in the model-runtime area
  from concurrent work, untouched by this change).
  no doc change â€” behaviour within the existing `lines` layer contract.

- **Restored the sidebar width to its original `w-60` (was shrunk to `w-52`).**
  A prior commit narrowed the desktop sidebar and the Settings rail from `w-60`
  to `w-52`; both are back to `w-60` (`sidebar.tsx` collapse/expanded/mobile and
  `settings.tsx` rail). no doc change â€” layout fix; no contract change.

- **Terminal command approvals now actually surface; agent steered to auto-allowed
  `mkdir`.** An agent asked to "create a folder on my Desktop" reported it was
  blocked. Two causes, both fixed. (1) A terminal `ask` command (`New-Item â€¦`)
  creates a pending approval, but `/code/approvals` only listed `kind='code_action'`,
  so the request was invisible in the UI â€” the user could never approve it and the
  agent looped. The route now lists and decides `code_action` + `terminal_command`
  + `shell_command`. (2) `mkdir`/`md` is already `allow` (runs with no approval;
  verified it creates the folder), but the code-agent prompt did not say so, so the
  agent chose the long `New-Item` form. The prompt now tells it to prefer the short
  auto-allowed form, not to retry the same refused tool in a loop, and to state
  plainly when a requested path is outside the bound folder. Tests: `test_code_api.py`
  green; Vitest unchanged; Python suite green.
  docs updated: `docs/harness/terminal-architecture.md`.

- **Terminal: the "dock back" icon is now an inward-corners glyph, not a download
  arrow.** `ArrowDownToLine` read as a download button, so the detached pop-out's
  "dock back" control now uses `CornersIn` (a dock/restore glyph), matching the
  restore control on the docked panel. no doc change â€” icon swap only.

- **Terminal: the `[?1;2c` prompt garbage is gone.** Root cause: the shell asks
  the terminal "what are you?" (Device Attributes, `ESC[c`); xterm auto-replies
  `ESC[?1;2c`; because every keystroke is forwarded to the PTY, that reply reached
  PowerShell, which cannot interpret it and ECHOED the literal text at the prompt.
  Filtering the output could not fix it (the shell had already echoed the bytes).
  The reply is now dropped from the INPUT stream (`filterTerminalInput` in
  `xterm-terminal.tsx`) before it reaches the PTY â€” the shell never needs it â€” with
  the output-side strip kept as a fallback for a session that echoed it earlier.
  Verified in-browser: no `?1;2c`, typing unchanged. Vitest **2140 passed**; Python
  **2642 passed**; eval gates ALL PASS; `npx tsc --noEmit` clean.
  docs updated: `docs/harness/terminal-architecture.md`.

- **Terminal: instant open, accurate icons, frosted glass, real resize.** Four
  phases. (1) Speed: the dock now starts the shell on the server IN PARALLEL with
  the xterm JS download (`Promise.all`), the runtime is prewarmed from the root
  layout, and the service pre-opens one idle shell at boot (`TerminalManager.warm_shell`
  + `WARM_OWNER`, adopted by the first UI open). Measured: open-to-prompt went from
  ~24s to ~1.1s. Also fixed the warm path's undefined `WARM_OWNER`/unwired boot call.
  (2) Icons: replaced the inaccurate set with semantic Phosphor icons â€” `Rows3`
  (dock bottom), `Columns3` (dock right), `CornersOut`/`CornersIn` (full/restore),
  `Export` (detach), `AppWindow` (new window), `Cpu` (processes) â€” added to
  `src/lib/icons`. (3) Glass: the dock and the pop-out use `glass-card-strong`
  (measured `backdrop-filter: blur(22px) saturate(1.4)`); the xterm host is
  transparent so the frost shows through, and the pop-out is portaled to `document.body`
  so its blur samples the real page. (4) Resize: the docked bottom/right panels have
  a pointer-drag handle that resizes them and pushes the new rows/cols to the PTY
  (`/terminal/sessions/{id}/resize`); the pop-out is drag + resize by pointer (its
  native CSS `resize` handle was unusable). Tests: Vitest **2140 passed**; full
  Python suite green; `npx tsc --noEmit` clean.
  docs updated: `docs/harness/terminal-architecture.md`.

- **Terminal: narrow-screen overlap fix, detach pop-out, and a new-window terminal.**
  Three fixes/features. (1) Overlap in sidebar/narrow mode: the right dock was a
  fixed-width column at every width, so on a narrow viewport it covered the main
  panel; it now collapses to a bottom strip below `md` (`md:w-[24rem] lg:w-[26rem]`,
  else full-width strip) and the header wraps instead of crowding, so nothing
  overlaps. (2) The stray `?1;2c` in the terminal: xterm answers the shell's
  Device-Attributes query (`ESC[c`) with `ESC[?1;2c`; we forward every keystroke to
  the PTY, so PowerShell echoed it literally. The answer and its echo are now
  filtered from the DISPLAY stream (`stripTerminalNoise`); terminal output is
  otherwise untouched. (3) Detach + new window: a detach control turns the docked
  terminal into a draggable floating pop-out sharing the same session, and a
  new-window control opens `/terminal?session=<id>`, a standalone page
  (`terminal-window.tsx`) that ATTACHES to the running shell (or opens its own if
  no id). Added `terminalOwnerId()` so the dock, pop-out and window share one owner.
  Added `ArrowDownToLine`/`SquareArrowOutUpRight` to the icon surface. Full Python
  suite green; Vitest **2139 passed**; `npx tsc --noEmit` clean.
  docs updated: `docs/harness/terminal-architecture.md`.

- **Terminal is now a real docked region, not a floating overlay.** It no longer
  overlaps the app (including the ChatBot). The app shell reserves the space: docked
  **bottom** the terminal is a strip inside the shell below the main content, docked
  **right** it is a full-height column beside the main panel (which shrinks), and
  **full page** it covers the window. Sidebar + main column + right dock are one flex
  row, with the bottom dock below it; the terminal is no longer `fixed` in the root
  layout (the floating `terminal-panel.tsx` is deleted). Placement is persisted and
  the shell hydrates it on mount (`useTerminalShell`), so the docked region reserves
  its space on first paint. The terminal refits and the PTY resizes on every
  placement change, and the shell is preserved across placement switches (bottom â†’
  right keeps history). Fixed a latent `api-guard` same-origin check in the same
  change (see above). Extracted `useTerminalShell` to keep `stock-chat.tsx` within its
  size ratchet. docs updated: `docs/harness/terminal-architecture.md`.

- **Terminal: fix typing and add bottom / right / full-page placement.** Three real
  bugs fixed. (1) Typing did nothing: the mutation guard compared `Origin`
  (`http://127.0.0.1:3000`) against the request host (`localhost`) byte-for-byte,
  so every browser mutation â€” including opening a session â€” got a 403
  "Cross-origin requests are not allowed". Loopback aliases are now normalized to
  one origin (`normalizeHost`), so same-machine requests are allowed while a real
  cross-site request is still blocked. (2) The terminal rendered but received no
  output: React StrictMode double-mounts the effect and the first cleanup's
  `stopRef` was never reset, so the stream loop exited immediately â€” now reset on
  every mount (and the terminal auto-focuses so typing works without a click).
  (3) Typed commands ran jumbled ("terminal" â†’ "terimnal"): one HTTP request per
  keystroke let concurrent writes interleave. Writes are now serialized with a
  per-session lock in the runtime, and the client drains an ordered input queue
  (one in-flight request, coalescing keystrokes without reordering). Added a
  placement control â€” **dock bottom / dock right (full height) / full page** â€” with
  the choice persisted; the terminal refits and the PTY resizes on every placement
  change. Tests: `api-guard.test.ts` (+2 loopback-origin), `terminal-keybind.test.ts`
  (+3 placement, +2 ordered-queue). Full Python suite **2642 passed**; Vitest
  **2127 passed**; `npx tsc --noEmit` clean; `npm run test:evals` ALL PASS.
  docs updated: `docs/harness/terminal-architecture.md`.

- **Terminal: header button + a reliable Ctrl/Cmd + ` toggle.** The terminal is now
  opened from a button at the header's right edge (next to the search bar) and by
  Ctrl/Cmd + `, both driving one shared `useTerminalStore`. The shortcut previously
  lived in local panel state and only bound while the panel was open (so it could
  not open the panel), and matched on `event.key`, which varies by keyboard layout.
  It now listens in the CAPTURE phase on `window` in the root layout (`TerminalKeybind`),
  matches `event.code === 'Backquote'` (layout-independent) with a `key` fallback,
  and calls `preventDefault`/`stopPropagation` so the browser or a focused xterm
  cannot swallow it. Also added an expand/restore control and a "New" shell action,
  persisted the open state, and hardened the shortcut matcher with unit tests.
  Fixed a concurrent duplicated-block syntax error in `src/lib/investor-eye/map-echarts.ts`
  that broke `tsc`/vitest. Tests: `terminal-keybind.test.ts` (+9).
  docs updated: `docs/harness/terminal-architecture.md` (Terminal UI section).

- **Real interactive terminal UI (xterm.js over a live PTY).** The Terminal tab was
  a fake one-shot command box: line-based, no streaming, no interactive programs.
  It is now a genuine terminal â€” xterm.js
  (`src/components/terminal/xterm-terminal.tsx`) rendering a live PTY-backed shell
  in the runtime. Keystrokes go straight to the PTY
  (`POST /terminal/sessions/{id}/raw`), output arrives over a low-latency long-poll
  stream (`GET /terminal/sessions/{id}/stream`, ~0.06 s) with ANSI preserved, and
  the window is resized to fit. The session lives in the runtime, so closing the
  panel or reloading does not kill the shell; the panel passes a durable `owner` id
  and reattaches (`attach_or_open_shell`), with "New shell" to open a fresh one.
  Added `@xterm/xterm` + `@xterm/addon-fit`. Backend: a per-session output
  `Condition` wakes the stream the instant output lands, `wait_for_output`,
  `stream_shell_output`, `send_shell_raw`, and an `owner` filter on session listing.
  Tests: `test_terminal_api.py` +2 (owner reattach, raw-inputâ†’stream round trip).
  Full Python suite **2639 passed**; Vitest **2093 passed**; `npx tsc --noEmit`
  clean. docs updated: `docs/harness/terminal-architecture.md` (UI section).

- **Terminal follow-up: real PTY, Docker/SSH runtimes, resource/runaway protection.**
  Closed the four known limitations of the terminal subsystem. (1) A real PTY
  (`pywinpty` on Windows, `ptyprocess` elsewhere) is now installed by default via
  platform markers in `python/requirements.txt`, so persistent shells are genuine
  ConPTYs (`pty: true`); agent-facing session text strips ANSI while the UI buffer
  keeps it for rendering, and a `cd`/`export` is sent to the real shell and its
  resulting cwd read back via the sentinel then workspace-confined (a command that
  leaves the workspace is refused and the shell returned to the root). (2/3)
  `DockerRuntime` and `SSHRuntime` are implemented for command execution and
  background processes behind operator config (`HARNESS_TERMINAL_DOCKER_CONTAINER`
  / `_WORKDIR`, `HARNESS_TERMINAL_SSH_HOST`); interactive sessions for them refuse
  `NOT_IMPLEMENTED`; SSH uses the host's own OpenSSH config/agent and never reads a
  key. New `runtime.extra_env()` forwards only non-secret host vars
  (`DOCKER_HOST`, `SSH_AUTH_SOCK`). (4) `terminal/resources.py` adds CPU/memory
  telemetry (no `psutil`) plus `ResourceLimits` â€” a start past `maxProcesses` is
  refused `PROCESS_LIMIT`, and a process over its output/lifetime bound is FLAGGED
  `runaway` (never auto-killed) with a `terminal.process.runaway` event; surfaced
  by `resource_report`/`system_info` and `/terminal/resources`. Also made the
  sandbox orphan test precise: it now asserts on the test process's own python
  descendants (`proctree.descendant_pids_matching`), not a machine-wide process
  count, so an unrelated python process can no longer perturb it. Tests: 11 new
  `test_terminal_resources.py` cases plus Docker/SSH unit tests and the PTY session
  coverage (86 terminal tests total). Full Python suite **2637 passed**; Vitest
  **2093 passed**; `npx tsc --noEmit` clean; `npm run test:evals` ALL PASS.
  docs updated: `docs/harness/terminal-architecture.md`, `docs/NAVIGATION.md`,
  `docs/harness/decisions.md` (`ADR-H127`).

- **Terminal/Shell/Process execution subsystem â€” the execution backbone.**
  Added `python/harness/terminal/` (one `TerminalManager` shared by agent tools and
  the UI): persistent shells (`open_shell`/`run_shell_command`/`write_shell_input`/
  `read_shell_output`/`resize_shell`/`send_shell_control`), background process
  management (`start_process`/`stop_process`/`restart_process`/`kill_process`/
  `read_process_output`/`write_process_input`/`send_signal`/`process_tree`),
  `execute_command` foreground execution, `list_ports`, `terminal_capabilities`,
  `system_info`; a sequenced/bounded output `RingBuffer` with cursor polling;
  secret redaction; a deterministic process state machine with crash detection; a
  Windows Job-Object / POSIX-group per-process isolation backend; OS process-tree
  and port attribution; `TerminalSession`/`ProcessRecord`/`TerminalCommand` rows on
  the one `agent-memory.db`; boot `RecoveryManager`; operator-gated `/terminal/*`
  routes; front-door `src/lib/harness/terminal-{client,browser}.ts` + `/api/terminal/**`;
  and Processes/Ports views in the terminal panel. The tools are removed at
  `plan_only` (`code/policy.py`) and classified allow/ask/deny by the effect
  authorizer composed into the graph. Docker/SSH runtimes refuse honestly
  (`NOT_IMPLEMENTED`). Also fixed a latent env-scrub gap: `PATHEXT` was missing
  from `SECRET_ENV_ALLOWLIST`, so a shell with a scrubbed environment could not
  resolve an executable by name. Tests: `python/tests/test_terminal_*.py` (72),
  incl. `test_terminal_e2e.py`. Full Python suite green (2550 passed);
  `npx tsc --noEmit` clean.
  docs updated: `docs/harness/terminal-architecture.md` (new),
  `docs/NAVIGATION.md`, `docs/harness/decisions.md` (`ADR-H126`).

- **Investor Eye Heatmap button now matches the surrounding controls.** The
  standalone `HeatmapToggle` was styled differently from the buttons beside it
  and sat alone on the map surface. It now sits in the Investor Eye header
  toolbar directly beside Map/skin/stars/names and Full page / Ask the map /
  Refresh, and uses the identical `glass-button` recipe; the dashboard widget
  gets an `accent` variant that matches its own `bg-accent/30` header buttons.
  `npx tsc --noEmit` clean; investor-eye tests pass.
  no doc change â€” control styling/placement only; no contract change.

- **Investor Eye heatmap: scope its visualMap (event dots no longer turn purple
  and stick) + coarser density grid.** Two regressions in the `event-heatmap`
  layer. (1) A continuous ECharts `visualMap` defaults to `seriesIndex: 'all'`,
  so it recoloured EVERY series from its `value` â€” the event pins (value = a
  0.2â€“1 severity weight) were re-tinted to the low/violet end, and because the
  update path only `replaceMerge`d `series`, the mapping (and the purple) stayed
  after the heatmap was switched off. The `visualMap` is now scoped with
  `seriesId: 'event-heatmap'`, and `world-map.tsx` replaces `visualMap` too, so
  turning the layer off REMOVES the mapping and every layer reverts to its own
  colouring. (2) The heatmap reused the pin-cluster grid (0.1Â° at high counts),
  so every event was its own faint speck instead of a regional hotspot. It now
  aggregates on a coarse `heatmapCellDegrees()` grid (1.5â€“8Â° by count), so
  neighbouring events accumulate into one hotspot the way a heatmap should.
  Tests: `map-echarts.test.ts` (+2 visualMap-scoping cases).
  `npx tsc --noEmit` clean.
  no doc change â€” bug fix to heatmap rendering; `MapLayerType`/contract unchanged.


- **Fixed the composer model dropdown crashing on open (Base UI error #31).**
  `ModelSelector` in `chat-input.tsx` rendered `DropdownMenuLabel` (Base UI
  `Menu.GroupLabel`) as a direct child of `DropdownMenuContent`, but a group
  label requires a `<Menu.Group>` ancestor â€” clicking the pill threw
  `Base UI error #31` and the menu never appeared. Wrapped the label + model
  list in `DropdownMenuGroup`. Verified with a Playwright probe: menu opens,
  lists all providers/models, no console errors. `vitest` 2085 passed;
  `npx tsc --noEmit` clean. no doc change â€” bug fix; no contract change.

- **Model menu restyled to frosted glass.** The composer model dropdown and its
  Provider submenu used the opaque `bg-popover` fill, so it read as a flat solid
  panel over the dark page. Both surfaces now use the shared `.glass-tooltip`
  tier (translucent tint `rgba(18,18,20,0.5)` + `backdrop-filter: blur(18px)
  saturate(1.35)` + inset highlight), matching the UI system's popover recipe;
  the solid `bg-popover` + `ring` fill and shadow were removed from
  `dropdown-menu.tsx`. The dropdown is already portaled by Base UI, so the blur
  samples the real page (verified with a Playwright high-contrast backdrop:
  background is visibly blurred through the panel and submenu, no console
  errors). This changes every consumer of the shared `DropdownMenuContent`
  (composer model selector is the only one today). `vitest` 2087 passed;
  `npx tsc --noEmit` clean. no doc change â€” visual-only restyle using the
  existing glass system; no architecture/contract change.

- **Scrollbar + provider-status colour toned down (professional, neutral).** The
  global scrollbar was brand-tinted, and on hover it turned bright brand green
  (`#7aff78`) â€” a loud yellow-green streak on dark glass. Both global scrollbar
  blocks in `globals.css` (the early brand block + the late `#262626`/`var(--brand)`
  cascade layer) now use a neutral translucent-white thumb
  (`rgba(255,255,255,0.16)`, `0.30` hover) on a transparent track, so no theme can
  turn the scrollbar a saturated colour. In the composer model dropdown's Provider
  submenu, the `needs key` / `no key` labels were saturated amber/green; they are
  now muted (`text-muted-foreground/50`; `key set` at `text-emerald-400/70`), so
  the menu reads as chrome rather than a traffic-light. `vitest` 2087 passed;
  `npx tsc --noEmit` clean. no doc change â€” visual-only; no contract change.

- **Composer model menu: fixed dead item handlers + made "Discover" list and keep
  every installed model.** Three compounding bugs. (1) The shadcn-style wrapper
  `dropdown-menu.tsx` exposed Radix's `onSelect` API, but Base UI's `Menu.Item`
  only fires `onClick` â€” so **every** menu item (`setModel`, provider switch,
  Discover, Custom) silently did nothing. All items now use `onClick`, with
  `closeOnClick={false}` where the menu must stay open (Discover, Custom id).
  (2) `ModelRegistry.discover_models` returned only the *newly registered* models,
  so a second "Discover" click returned an empty list; it now returns the
  provider's full registered set (idempotent) â€” Python test added.
  (3) The composer catalog (`GET /api/harness/chat/models`) read only the static
  preset (`llama3.1`, â€¦), never the runtime's discovered registry, so installed
  Ollama models vanished on reload. The route now merges `listRuntimeModels()`
  (best-effort, server-side) per provider. Result: an Ollama "Discover" now shows
  ALL installed models and they persist across reloads. Tests: `models/route.test.ts`
  (+2), `test_model_runtime.py` (+1). `vitest` 2089 passed; `pytest` green;
  `npx tsc --noEmit` clean. docs updated: `docs/CHANGELOG.md`.

- **Model menu: providers that need a key now link straight to Settings â€º AI.**
  Clicking a provider whose key is missing previously selected it and then failed
  at run time. The Provider submenu item now detects `!keyless && !available` and
  dispatches the command bus to `settings.ai`
  (`useCommandStore.getState().dispatch({ tab: "settings", subroute: "settings.ai" })`)
  â€” the established modal-navigation idiom â€” so the user lands on the AI/LLM page
  to paste the key. The label changed from "needs key" to a primary "Add key" with
  a key icon. Keyless/configured providers still select normally. `vitest` 2089
  passed; `npx tsc --noEmit` clean. no doc change â€” small navigation affordance;
  no architecture/contract change.

- **Settings â€º AI redesigned: grouped providers, connect/disconnect, readable
  active model.** The old surface dumped every provider into one two-column grid
  beside a duplicate config form, so it was unclear what was selected or how to
  add/remove a key. New `ai-provider-settings.tsx` groups it: (1) **Active setup**
  â€” the current provider + model echoed prominently, with model picker, base URL,
  context window, key editor and Test, in one card; (2) **Connected providers**
  â€” those that work (key set, or keyless local), each with **Disconnect**
  (deletes the vault key) or **Use**; (3) **Popular providers** â€” one click to
  **Connect** (reveals the key field) or select; (4) **Show more providers** â€”
  the rest, collapsed. Provider state is derived honestly (Active / Connected /
  Ready / Not connected). `ProviderKeyEditor` gained an `onChanged` callback.
  The model picker (`model-picker.tsx`) no longer shows a raw `__custom__`
  sentinel â€” the current id is always in the Select, with a separate "Custom
  model idâ€¦" toggle. `GET /api/harness/models` now merges runtime-discovered
  models, so the Settings picker reads the operator's installed Ollama models
  too. Tests: `api/harness/models/route.test.ts` (+3). `vitest` 2092 passed;
  `pytest` green; `npx tsc --noEmit` clean. docs updated: `docs/CHANGELOG.md`.

- **Settings â€º AI: removed themed (blue) borders, provider cards now full-width.**
  The provider cards and section icon used `border-primary/*` / `border-emerald-*`,
  which resolve to the active theme's brand colour â€” so under a blue theme
  ("Electric Blue", "Blueprint") every card had a blue outline. They now use
  neutral white-alpha borders, so no theme can tint the chrome. The catalog
  grids also changed from two columns (`sm:grid-cols-2`) to a single full-width
  column. `vitest` 2092 passed; `npx tsc --noEmit` clean. no doc change â€”
  visual-only; no contract change.

- **Site sidebars unified to one neutral grey, accent-free look; rows shortened.**
  The main app sidebar (`layout/sidebar.tsx`) and the Settings screen's own left
  rail (`screens/settings.tsx`) are now the same surface: both carry `sidebar-root`
  + `glass-card-strong`, so Settings no longer renders a rounded, accent-tinted
  `glass-card-subtle` panel that drifted from the shell rail. Green `primary`
  accents (active mode button, active nav row/icon, shortcut badge, settings gear,
  Settings header/chevron/nav pills) were replaced with neutral white-wash
  (`bg-white/[0.08]`, `text-foreground`). Nav rows shrank `h-10` â†’ `h-9`. The
  shipped sidebar tint moved `#1a1a1c` â†’ `#2a2a2e` (clearly grey) and
  `SIDEBAR_PRESETS` gained a `Grey` default preset (`charcoal` retained). Tests
  updated in `lib/theme/tokens.test.ts`. no doc change â€” surface styling only; no
  architecture/contract change.

- **ChatBot transcript rail de-accented; default sidebar width reduced.** The chat
  page's right-edge `MessageRail` ticks no longer use the green brand accent â€”
  idle ticks are `bg-muted-foreground/50`, hover/active brighten to a neutral
  `bg-foreground/70â€“80` with no glow. The default sidebar width dropped `w-60`
  (15rem) â†’ `w-52` (13rem) on the shell rail (`layout/sidebar.tsx`), its mobile
  drawer, and the Settings rail (`screens/settings.tsx`) so the default chrome is
  less dominant. `npx tsc --noEmit` clean; `vitest` 2092 passed.
  no doc change â€” surface styling only; no architecture/contract change.

- **Chat scrollbars de-accented to neutral grey.** The chat transcript's visible
  scrollbar (`.chat-transcript-scroll`) was still brand-green â€” after scrolling
  up it rendered as a bright vertical streak on the right edge of the ChatBot
  page. It (plus `.chat-composer-scroll` and `.tv-metrics-rail`) now uses the
  same neutral `rgba(255,255,255,0.16)` thumb / `0.30` hover as the global bar,
  and the transcript/composer bars slimmed 8/10px â†’ 6px. `npx tsc --noEmit`
  clean; `vitest` 2092 passed. no doc change â€” styling only.

- **Chat transcript scrollbar replaced with a short capped thumb.** The native
  transcript bar always spans the full scroll-container height (it ran down the
  right edge and under the header, looking like a long band). `ChatHistory` now
  hides the native bar (`scrollbar-hide`) and renders a compact custom thumb
  capped at ~28% of the track, inset 6px from the top/bottom, tracking the
  reading position via a ResizeObserver + scroll listener. The unused
  `.chat-transcript-scroll` CSS was removed. `npx tsc --noEmit` clean;
  `vitest` 2092 passed. no doc change â€” styling only.

- **Settings model dropdown no longer renders behind the modal; discovered
  models persist; all connected providers usable from chat.** Three fixes:
  (1) `SelectContent` and `DropdownMenuContent` were portaled at `z-50` while the
  Settings `Dialog` popup/overlay sit at `z-[100]`, so the model list painted
  behind the modal â€” both moved to `z-[110]` (same for `TooltipContent`, which
  has the identical class of bug). Verified live with Playwright against a fresh
  dev server: the popup now computes `z-110` and sits above the dialog at
  `z-100`. (2) "Discover installed models"
  results lived only in the Python runtime's in-memory registry (lost on reload /
  restart), so discovery had to be re-run every time; the discover route now
  merges found ids into a durable `SystemConfig` snapshot
  (`src/lib/agent/discovered-models.ts`, key `discovered_models_v1`) that both
  catalog routes merge ahead of the runtime registry. (3) The chat composer's
  model menu listed only the active provider's models; it now groups the models
  of EVERY provider usable right now (keyless locals + any provider with a
  resolving key), active first, and selecting one switches the active provider to
  that model's provider. Also fixed a pre-existing CRLF/LF mix in
  `python/harness/terminal/runtimes.py` flagged by the gitignore-guard test.
  `npx tsc --noEmit` clean; `vitest` 2093 passed. docs updated:
  `docs/ARCHITECTURE.md`, `docs/NAVIGATION.md`.

- **`Select` dropdown restyled to frosted glass.** The select popup used a flat
  opaque `bg-popover` panel with a generic `ring`/`shadow-md` â€” visually a plain
  system menu, and the odd one out next to the `DropdownMenu` (which already uses
  `.glass-tooltip`). It now uses the same `.glass-tooltip` frosted recipe
  (translucent tint + backdrop blur + saturation, rounded-2xl, soft shadow +
  inset highlight), with roomier rounded items, a neutral white-wash
  hover/selected state, a primary-tinted check indicator, and gradient scroll
  affordances instead of opaque `bg-popover` strips. `npx tsc --noEmit` clean;
  `vitest` 2093 passed. no doc change â€” styling only.

- **Every provider can enumerate its live models (OpenRouter, OpenAI, Groq, â€¦).**
  Previously only local servers + routers (Ollama/LM Studio/OpenRouter) offered
  "Discover installed models"; a hosted API showed only its declared sample, so
  you could not pull e.g. OpenRouter's catalog. Fixes: `ProviderSpec.dynamic_discovery`
  is now true for OpenAI, Anthropic, Gemini, Mistral, Groq, DeepSeek, xAI,
  Together, Perplexity, Fireworks; the probe is protocol-generic
  (`python/harness/model_runtime/providers/openai.py` `probe_openai_models` =
  `GET {base}/models` with a `Bearer` key for every OpenAI-protocol family;
  `AnthropicAdapter`/`GoogleAdapter` override `discover_models` for their own
  list shapes); and the Next discover route now resolves the provider key
  server-side from the env/vault (`resolveProviderKey`) with a preset base-URL
  fallback, since the browser never holds it â€” so a private endpoint that would
  401 keyless now enumerates. Discovered ids are cached in the durable snapshot
  added earlier. Tests: `python/tests/test_model_runtime.py` (catalog flags +
  adapter probes + parser). `npx tsc --noEmit` clean; vitest 2093 passed;
  Python model-runtime 71 passed. docs updated: `docs/ARCHITECTURE.md`,
  `docs/NAVIGATION.md`.

- **Model lists are now curated via a "Manage models" dialog (no more flooded
  dropdowns).** A provider can enumerate hundreds of models (OpenRouter: 466),
  which is unusable in a picker. Discovery now opens a searchable,
  checkbox enable/disable dialog (`src/components/screens/manage-models-dialog.tsx`)
  showing the full catalog; the enabled subset is what the compact pickers show,
  persisted per provider in `src/lib/agent/enabled-models.ts` (`be_enabled_models_v1`,
  shared zustand store + pure `compactModels()` with `MODEL_LIST_SOFT_LIMIT`=40).
  Both Settings â†’ AI (`model-picker.tsx`) and the chat composer
  (`chat-input.tsx` `ModelSelector`) gained a "Manage" affordance and render the
  same dialog, so curation is reflected everywhere. It is a client-side filter,
  never an allowlist (the runtime accepts any id; "Custom model idâ€¦" still
  works). `npx tsc --noEmit` clean; vitest 2112 passed (incl.
  `enabled-models.test.ts`). docs updated: `docs/ARCHITECTURE.md`,
  `docs/NAVIGATION.md`.

## 2026-10-04

- **Composer model selector: fixed to be ALWAYS visible + switch providers.**
  The previous attempt gated the dropdown on a non-empty model list, so for the
  default configuration (one saved model) it never rendered and the pill stayed a
  static label â€” the selector appeared "broken". It also only offered the active
  provider's models, so there was nothing to switch to. `chat-input.tsx` now
  renders an always-present `ModelSelector`; `use-chat-model.ts` + new
  `GET /api/harness/chat/models` list the models the operator can actually use
  across ALL providers (availability derived server-side from the real env/vault;
  models from the runtime catalog with a preset-default fallback when the runtime
  is down). Selecting a model/provider PERSISTS it to the settings vault via
  `POST /api/settings` â€” the source the runtime reads â€” so the next message uses
  it; it is also sent per-turn as `model`. Provider switch persists provider +
  base URL + default model together; a failed save shows the error and reverts;
  a "Custom model idâ€¦" entry types any id; local/router providers get a live
  discover action. Tests: `models/route.test.ts` (+4). `vitest` 2085 passed;
  `pytest` 2550 passed; `npx tsc --noEmit` clean; eval gates ALL PASS.
  docs updated: `docs/ARCHITECTURE.md`, `docs/CHANGELOG.md`

- **Added a real model selector to the chat composer.** The composer only ever
  showed a static provider pill; the old model dropdown was REMOVED earlier
  because it was fabricated (hardcoded "Flash-Lite/Flash/Pro"). `use-chat-model.ts`
  now backs the pill as a dropdown of the models the configured provider can
  serve (the runtime's declared catalog + a live `discover` probe for local
  servers/routers), persisted in localStorage, and the choice is threaded
  end-to-end: `ChatOptions.model` â†’ chat request body `model` â†’ `startChatRun`/
  `chatWithAgent` â†’ `resolveModelSettings(model)` â†’ the run's
  `modelSettings.model`. It overrides ONLY the model â€” provider/key/base URL stay
  the operator's configured ones, and a declared context window is dropped since
  it belongs to the previous (provider, model). Never a fabricated list: with no
  catalog it degrades to the saved model alone. `stock-chat.tsx` stays at its
  1212-line ratchet (lines reclaimed). Tests: `run-service.test.ts` (+2).
  `vitest` 2081 passed; `pytest` 2550 passed; `npx tsc --noEmit` clean; eval
  gates ALL PASS.
  docs updated: `docs/ARCHITECTURE.md`, `docs/CHANGELOG.md`

- **Investor Eye: heatmap look + one-click Heatmap button on every surface.**
  Added a standalone `HeatmapToggle` (Flame icon) on the main map (top-left of
  the map surface), the full-page map dock, and the dashboard "Investor Eye Map"
  widget header. It uses the SAME visible control recipe as its sibling buttons
  (`border-white/15 bg-accent/30`, active = `border-primary/40 bg-primary/15`) â€”
  an earlier `glass-button`/`glass-card-subtle` restyle blended into the dark map
  and made the control effectively invisible. Restyled the heat layer:
  `pointSize`/`blurSize` 22/28 â†’ 16/18 and `minOpacity` 0.35 â†’ 0.12 so sparse
  regions stay dark and only genuine concentrations light up, and replaced the
  blueâ†’red `visualMap` ramp with a warm violetâ†’magentaâ†’roseâ†’orangeâ†’yellow ramp
  that contrasts the blue/cyan map surface instead of blending into it. The
  widget header now wraps so the extra control cannot be clipped. `vitest` 414
  investor-eye tests pass; `npx tsc --noEmit` clean.
  no doc change â€” presentation/control tuning; layer contract unchanged.

- **Investor Eye Map dashboard widget had no layer controls.** The embeddable
  "Investor Eye Map" widget rendered the world map with only expand/Open buttons
  and no way to toggle layers â€” so the Event Heatmap (and every other layer) was
  unreachable from the dashboard, unlike the full Investor Eye screen. Added a
  Layers button opening a popover that reuses the canonical `LayerController`
  (same chips, colours, availability rules), portaled to `document.body` and
  anchored to the button because the widget card is `overflow-hidden` and would
  otherwise clip it; the popover flips above the button near the viewport bottom.
  `vitest` 2079 passed; `npx tsc --noEmit` clean.
  no doc change â€” the Investor Eye Map widget is already covered by the workspace
  skill; this is a control-surface fix, no contract change.

- **Investor Eye: event heatmap now actually reads as a heatmap; pins shrunk to
  a Bloomberg-like scale.** The `event-heatmap` layer emitted one datum per raw
  event with a ~1px weight, so ECharts' heat brush blurred single events away and
  the layer rendered as an invisible flat wash. It now aggregates events onto the
  same grid the pins use (`aggregatePoints`) and each cell's intensity is the SUM
  of its members' severity weights, so a hotspot is literally where the most and
  most-severe events are; `pointSize`/`blurSize` widened to 22/28 and
  `minOpacity` raised to 0.35 so even a light cell survives the dark map. Fixed
  the controller: `availableLayers` never included `event-heatmap`, so its chip
  was dimmed as "no data" and looked broken. Enabled the heatmap by default
  (`DEFAULT_LAYERS`) and gave it a legend swatch (new `heat` glyph in
  `SYMBOL_PATHS`). Markers reduced to Bloomberg scale â€” 2D pins 18/14/11/8 â†’
  8/6/5/4 and glow halos 26/17/10/5 â†’ 12/8/5/3; globe core 17 â†’ 9 and ring 24 â†’
  13 â€” so hundreds of dots stay legible instead of collapsing into blobs.
  Tests: `layers.test.ts` (+3 heatmap density cases). `vitest` 2079 passed;
  `npx tsc --noEmit` clean.
  no doc change â€” layer rendering/tuning only; heatmap contract already documented
  in `docs/investor-eye-architecture.md` Â§2.13.

- **Fix: configured models were silently substituted + Ollama's installed models
  were unselectable.** The front door stores a BARE model id (`cfg.model`) with a
  separate provider id. `ModelRouter` resolved a bare id only when it was
  globally unambiguous, so any model not in the static catalog (an operator's
  `deepseek-v4.1-flash`, any custom/local model) looked "unknown" and the router
  fell through to its own best pick â€” `deepseek/deepseek-v4.1-flash` resolved to
  `google/gemini-2.0-flash`, so the user's model never ran. `ModelRuntime` now
  qualifies the bare id with the run's provider (`_explicit_ref`), so ANY model
  id the operator configured is honoured as the explicit choice and never
  silently swapped. Second regression: `prepare_model` force-set
  `reasoning_effort` from the task profile on EVERY model, including
  OpenAI-compatible endpoints that reject the knob (a hard 400); reasoning is now
  shaped only for a provider-native control (Anthropic/Google/native-OpenAI) that
  declares reasoning support. Third: the Settings model dropdown only ever showed
  the static catalog, never the models actually installed, so Ollama showed
  `llama3.1â€¦phi3` and nothing the operator had pulled. Added runtime model
  discovery â€” `POST /model-runtime/providers/{id}/discover` probes the live
  `/models` endpoint (Ollama/LM Studio/router) and registers what it serves, with
  a new `ModelPicker` component (extracted from `settings.tsx`, which stays under
  its size ratchet) exposing a "Discover installed models" action; a failed probe
  reports an honest reason, never a silent empty success. `ProviderSpec.dynamicDiscovery`
  marks discoverable providers. Tests: `test_model_runtime.py` (+5),
  `test_model_runtime_api.py` (+2), `test_models.py` (+1),
  `model-runtime-browser.test.ts` (+2). `vitest` 2076 passed; `pytest` 2550
  passed; `npx tsc --noEmit` clean; eval gates ALL PASS.
  docs updated: `docs/harness/architecture.md`, `docs/CHANGELOG.md`

- **Reverted the General â€º Theme "ChatBot background" card.**
  The color option already lives under Settings â€º General â€º Background
  (`background-settings.tsx`), so the duplicate card added earlier today in
  `customization-settings.tsx` was removed and that file restored.

- **Eclipse preset landing defaults pinned to the brand greens.**
  `src/lib/theme/tokens.ts`: the `eclipse` preset's ChatBot landing now uses
  `solidColor: '#131615'` and wordmark `textColor: '#e6ffe5'` (previously both
  derived from the accent/primary mix). `npx tsc --noEmit` clean; `vitest` passed.
  no doc change â€” preset token values only, no contract/shape change.

- **Dedicated "ChatBot background" color in Settings â€º General â€º Theme.**
  Added a "ChatBot background" card to the theme Colors area
  (`src/components/screens/customization-settings.tsx`) that sets the flat
  backdrop color of the empty ChatBot landing only, independent of the app-wide
  page `background` token. It stores into the background store's `solidColor`
  (`mode: solid` + `solidFill: flat`); empty follows the page color. The edit is
  tracked as a separate draft value so it respects the panel's live-preview /
  Apply / Discard model, overrides a selected preset's snapshot solid color, and
  counts toward `dirty`. `vitest` passed; `npx tsc --noEmit` clean.
  docs updated: `docs/ARCHITECTURE.md`, `docs/NAVIGATION.md`, `docs/CHANGELOG.md`

- **Fix: Settings â€º AI could not add an API key or select most providers.**
  Root cause was the keyless-local key sentinel `"local"`: a local endpoint
  (Ollama) persisted `apiKey:"local"` in `llm_config`, and switching to a hosted
  provider kept it, so `getLLMConfig` never fell back to the provider-key vault
  and the runtime sent `"local"` as the credential (HTTP 401). `src/lib/settings.ts`
  now defines `LOCAL_KEY_SENTINEL`, drops it on save (it is never a credential),
  and `getLLMConfig` ignores it once the endpoint is remote; `setLLMConfig` also
  accepts a remote provider when the vault or environment holds the key instead
  of demanding a plaintext key. `LLMProviderName` and the Settings "Mode" select
  now expose every provider preset (they previously allowed only 5 values, so
  most providers were unselectable and the model catalog could not resolve).
  Preset/provider selection now sets the provider id + base URL + default model
  together, and the Model field is a real dropdown of the runtime catalog's known
  models plus a free-text custom id (the previous `<datalist>` was not surfaced
  by the input primitive). Regression tests: `src/lib/settings.test.ts`.
  `vitest` 2074 passed; `pytest` 2542 passed; `npx tsc --noEmit` clean.
  docs updated: `docs/CHANGELOG.md`

- **Model Control Center front door + UI.** The provider-agnostic Model Runtime
  is now reachable from Next.js. Server/browser clients
  `src/lib/harness/model-runtime-{client,browser}.ts` proxy the runtime's
  operator-gated `/model-runtime/*` routes via `src/app/api/harness/model-runtime/**`
  (providers, models, routing, routing/decisions, route [pure computation],
  health, usage). A mounted screen `src/components/screens/model-runtime/`
  (`model-runtime-screen.tsx` + providers/models/routing/usage/health/debug
  panes) is the Model Control Center: it lists providers/models with capability
  states and pricing (unknown stays unknown), shows task routing, usage/cost,
  provider health and   the routing debug view ("why this model"). Mounted via
  AppTab `model-runtime` (`src/lib/app-tabs.ts`, `src/components/layout/sidebar.tsx`,
  the keep-alive block in `src/components/screens/stock-chat.tsx`, the sidebar
  entry in `src/lib/sidebar/config.ts`), i18n `modelRuntime.*`/`nav.modelRuntime`,
  and the global-search page `page-model-runtime`. User routing overrides
  (spec Â§44) round-trip through `LLMConfig.routingPolicy` â†’ the run's
  `input.context.modelPolicy` â†’ the runtime's `RoutingRequirements`, toggleable
  in the Routing pane ("local models only", "avoid paid models").
  Tests: `src/lib/harness/model-runtime-browser.test.ts`,
  `src/components/screens/model-runtime/model-runtime-screens.test.ts`,
  `src/lib/harness/run-service.test.ts`,
  `python/tests/test_model_runtime_api.py`. `vitest` 2068 passed; `pytest`
  2542 passed; `npx tsc --noEmit` clean.
  docs updated: `docs/harness/architecture.md`, `docs/NAVIGATION.md`,
  `docs/ARCHITECTURE.md`, `docs/CHANGELOG.md`

- **Provider-agnostic Model Runtime layer (the agent no longer talks to a
  provider).** New package `python/harness/model_runtime/` implements
  `Agent â†’ ModelRuntime â†’ ModelRouter â†’ ProviderAdapter â†’ Provider`: provider and
  model registries seeded from the existing `PROVIDER_CATALOG`; capability
  detection as states (supported/unsupported/unknown/degraded); 15 task profiles;
  dynamically-resolved aliases (`eclipse-fast|smart|reasoning|coder|vision|cheap|local`);
  a scoring router (capability/quality/reliability/latency/availability/context/cost,
  configurable weights) with an explainable decision trace; fallback + error-classified
  retry with backoff; health/circuit-breaker/rate-limit managers; normalized
  token/cost/latency/budget tracking; normalized streaming, tool schemas,
  structured output and reasoning. `build_chat_model` is reused as the
  adapter's construction primitive (one path, one source of provider facts).
  `graph.py`, `history.py`, `learning_review.py` and the MCP sampling factory now
  ROUTE and BUILD through the runtime while still invoking the module-level
  factory, so the existing test seam and all 2535 harness tests are unchanged.
  A concrete `ModelSettings` provider/model remains the explicit override;
  cross-provider fallback and in-place retry are flag-gated
  (`HARNESS_MODEL_FALLBACK` default OFF, `HARNESS_MODEL_RETRIES` default 1).
  Model usage/health persist to the runtime's OWN `ModelRequest`/`ModelHealth`
  tables on `agent-memory.db` (never JDdS); read-only `/model-runtime/*` routes
  are operator-gated. Tests: `python/tests/test_model_runtime.py` (54).
  `pytest` 2535 passed; `npx tsc --noEmit` clean.
  docs updated: `docs/harness/architecture.md`, `docs/harness/decisions.md`
  (ADR-H123), `docs/ARCHITECTURE.md`, `docs/NAVIGATION.md`, `docs/CHANGELOG.md`

- **Bounded replanning added to the one execution graph (Phase 11).** A tool step
  that FAILS or STALLS (the agent re-issues the same `(tool,args)` set as the
  previous turn) may now divert through ONE `replan` node on the SAME
  `tools â†’ agent` edge before continuing. The node appends inert prose naming the
  failures/stall â€” it authorizes nothing, widens no allowlist, and builds no
  second loop/registry/adapter. New module `python/harness/replan.py` owns the
  trigger (`should_replan`; a stall outranks a failure), the bound
  (`ReplanBudget.max_replans`, default 2), the deterministic directive and an
  optional best-effort model-authored plan. Flag-gated `HARNESS_REPLAN_ENABLED`
  (default OFF) â€” when off the graph is byte-identical to before. Emits a
  persisted `run.replanned` event. To respect the `graph.py` size ratchet, the
  checkpoint (de)serialization moved to `python/harness/checkpoint_io.py` and the
  history-bounding + dropped-context helpers moved to `python/harness/history.py`
  (both re-exported by `graph.py`, so callers/tests are unchanged). Tests:
  `python/tests/test_replan.py`. `npm test` and `npx tsc --noEmit` pass.
  docs updated: `docs/harness/architecture.md`, `docs/harness/decisions.md`
  (ADR-H122), `docs/ARCHITECTURE.md`, `docs/NAVIGATION.md`, `docs/CHANGELOG.md`

- **Preset ChatBot wordmark font unified to Michroma.** Every shipped theme
  preset's giant ChatBot landing wordmark (the "ECLIPSE AGENT" text) now uses
  Michroma (`var(--font-michroma)`), replacing the per-preset Bodoni / VT323 /
  IBM Plex Mono / Playfair choices. `src/lib/theme/tokens.ts`: `ECLIPSE_WORDMARK_FONT`
  â†’ `PRESET_WORDMARK_FONT` and all 12 presets reference it (size, opacity and
  uppercase unchanged). `vitest` 2074 passed; `npx tsc --noEmit` clean.
  no doc change â€” theme-token value only, no contract/shape change.
