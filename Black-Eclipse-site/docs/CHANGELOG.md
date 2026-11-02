# Change Log

## 2026-11-02
- **fix(graph): adapter-pack registration split out of `nodes.py`.** The Tier
  2/3 packs pushed `graph_runtime/nodes.py` to 1218 lines (ceiling 1200); the
  wiring now lives in `graph_runtime/node_packs.py` (`register_extra_packs`),
  and `graph.py` is re-pinned 2355→2370 for the AgentPreset fallback. Targeted
  graph/size tests green (79). no doc change — internal split, contracts
  unchanged.
- **chore(docs): rotated the changelog window.** Ran
  `scripts/rotate-changelog.js --write` to archive the oldest dated section into
  `docs/changelog/2026-10.md` (window of 7 preserved). no doc change — mechanical
  rotation, no contract or architecture change.
- **feat(graph): `logic.human_approval` — the approval gate (Tier 3).**
  `graph_runtime/approval_nodes.py` + `registry-utility.ts`: creates ONE
  `graph_approval` in the runtime's existing single-use approval store (the same
  rows the Permissions panel decides), keyed by `graph:<runId>:<nodeId>` and a
  digest of the request text, with a ≤ 24 h TTL. The decision is **not
  consumed** — it gates that run+node, so a resumed run reads the same answer.
  Denials fail the node and name the approver. New runtime primitive:
  **`DeferredWait(rerun=True)`** (`model.py` + `executor.py`): a rerun-deferred
  node is left **PENDING** and its outputs/control are NOT checkpointed, so the
  resumed durable job re-enters it — without this a deferred node was recorded
  as succeeded and the gate would silently pass. Durable runs therefore pause
  without holding a worker; synchronous runs poll up to `maxWaitS` (default
  300 s) and then fail honestly, leaving the request in Approvals. Test runs
  never create a request. Bootstrap binds `set_approval_runner` to
  `service.approvals`. Manifest regenerated. Tests:
  `python/tests/test_graph_approval_node.py` (10 cases) plus a durable
  integration case in `test_graph_durable.py` proving the paused run leaves the
  gate non-succeeded and finishes only after approval; parity green.
  Docs updated: `docs/graph-studio.md`, `docs/NAVIGATION.md`,
  `docs/graph-studio-bot-skill-nodes-plan.md`, `docs/CHANGELOG.md`.
- **feat(graph): the rest of Tier 2 — committee, chart, notify, evidence
  ranking.** Four nodes complete the plan's candidate set. `agent.team`
  (`team_nodes.py`, `registry-agents.ts`) runs the Institution committee through
  the existing team runtime (run → wait → finalize → synthesize), returns the
  reconciled `decision`, deterministic `synthesis` and terminal `status`
  (COMPLETED/PARTIAL succeed), never places an order or registers a trigger, and
  refuses a test run. `output.chart` (`output_nodes.py`, `registry-output.ts`)
  normalizes a spec / number list / `{values, categories}` / `{series,
  categories}` / `{rows}` + X/Y fields into a validated `ChartSpec` and the
  plotly figure the chart engine draws, reporting `rendered: false` (spec still
  returned) when plotly is absent — never a fake image. `output.notify` sends
  one message through the ONE channel service (`send_outbound`) with the
  `network` effect, so a test run can never send and a provider refusal fails
  the node with its reason. `research.source_rank` (pure, in `research_nodes.py`)
  ranks evidence by the `confidence` and freshness the items already carry
  (exponential decay of publishedAt/retrievedAt with a configurable half-life);
  an item with neither is sorted last and counted `insufficient_signal`, so no
  score is invented. Runners bound at boot (`set_team_runner`,
  `set_notify_runner`). Manifest regenerated. Tests:
  `python/tests/test_graph_team_output_nodes.py` (13 cases) + parity green.
  Docs updated: `docs/graph-studio.md`, `docs/NAVIGATION.md`,
  `docs/graph-studio-bot-skill-nodes-plan.md`, `docs/CHANGELOG.md`.

## 2026-11-01
- **test(graph): end-to-end coverage for the quant pack.** Added
  `python/tests/test_graph_quant_e2e.py`: one graph wires
  `finance.market_data` into every quant node added in this work (backtest,
  grade, regime, resample, robustness, benchmark, trade_analysis,
  multiple_testing, edge_report, position_size, options_strategy, costs) and is
  driven through the real `/graphs/runs` HTTP surface — compile, capability
  authorization, layered execution, run rows and output validation included.
  The bar provider is installed through the runtime's own
  `set_series_provider` seam, so nothing is fabricated and no network is used.
  It also pins two behaviours the unit suites could not show: a quant node
  failure is reported on that node's run row (not swallowed), and a checkpoint
  larger than the preview bound is stored as `{_truncated, preview}` rather than
  dropped. 3 cases, ~11s. Docs updated: `docs/graph-studio.md`,
  `docs/CHANGELOG.md`.
- **ops: the harness size budget remains red and is NOT caused by the quant
  work.** `npm run check:size` reports 6 budgeted directories over their
  ceilings (`python/harness/.`, `code`, `routers`, `eclipse_memory`, `skills`,
  `evaluation`) and the total ~38.7k lines over. Those directories hold the
  parallel trading/broker and skill work, not `graph_runtime/` (which has no
  per-directory budget). Raising those ceilings is a deliberate decision that
  belongs to whoever owns that growth; this changelog records the state so it
  cannot be mistaken for a quant regression. no doc change — operational note.
- **feat(graph): read nodes, an intent builder and a no-side-effect order preview.**
  Added `trading.broker_orders`, `trading.broker_fills` and `trading.order_ledger`
  (broker working orders, reconciled deals, Eclipse's own submitted-order rows),
  `trading.paper_account` (durable PAPER cash/positions/realized PnL, positions
  also emitted as rows) and `trading.order_intent` (validated
  symbol/side/quantity/type/price/SL/TP/TIF; a pending order without a price is an
  error). `trading.order_preview` answers "would this be allowed?" through
  `order_check` + policy + guardrails + optional mandate scope, and
  `trading.broker_order` gained `dryRun` to use it. Approval creation is now
  optional in `BrokerService.preview_order` (`record_approval=False`), so a graph
  dry run leaves no approval cards. `broker_positions`/`risk_check.positions` are
  now `array` ports, so position rows wire into the gate and an account envelope
  is refused at compile time. Contracts mirrored in `registry-trading.ts` /
  `config-fields.ts`; manifest regenerated. The preview body moved to
  `trade/preview.py` (a delegate in `service.py`) to stay under the module size
  ceiling. Tests: 30 broker-node cases (preview
  never creates an approval, mandate verify is non-consuming, dry run sends
  nothing, port-type wiring) and 3 paper-account cases. Docs updated:
  `docs/trading.md`, `docs/graph-studio.md`, `docs/NAVIGATION.md`,
  `docs/CHANGELOG.md`.
- **feat(graph): trading nodes gate on live state and report honest outcomes.**
  `trading.risk_check` now accepts `account`/`positions` plus numeric overrides
  and derives equity and open-position count from the broker/paper account
  before falling back to config; a new `state` output names the source of every
  figure. It also runs in `research`/`backtest` mode (it is pure), so a backtest
  can gate entries with the same limits. `trading.broker_order` honors an
  optional `decision` input (a rejected risk check stops the order before the
  broker) and returns `ok`/`reason`; `BrokerOrder` gained `runId`/`nodeId` so a
  graph order is traceable from the ledger (additive columns, migrated in
  `trade/store.py`). Added `trading.broker_positions`; every broker read/exit now
  returns `ok`/`reason`, `trading.broker_bars` also returns the deterministic
  ATR(14)/20-bar range/contract size, and `trading.broker_close` can close a whole
  symbol. Contracts mirrored in `registry-trading.ts` / `config-fields.ts`;
  manifest regenerated. Tests: `test_graph_broker_nodes.py`,
  `test_graph_registry_parity.py` (cross-language port parity) and 7 new
  `risk_check` cases. Docs updated: `docs/trading.md`, `docs/graph-studio.md`,
  `docs/ARCHITECTURE.md`, `docs/harness/security.md`, `docs/CHANGELOG.md`.
- **ux(graph): readable market-node summaries, direct OHLCV metrics and starter
  templates.** (1) Every gateway read node now emits a compact `summary` object
  (symbol/provider/as-of plus the key figures for that capability — spread,
  funding rate, liquidation totals, …) next to the full record and provenance,
  so the node card and Output tab are readable without opening raw JSON.
  (2) `quant.risk_metrics` and `quant.drawdown` accept OHLCV bars directly:
  closes are used as price levels, the detected source wins over `inputKind`,
  and the metrics report `source` — so `finance.history → quant.risk_metrics`
  no longer needs an intermediate indicator node. (3) Added the `Risk snapshot`,
  `Derivatives monitor` and `FX + bond yield` starter templates, and clarified
  the FX pair-vs-base/quote inspector help. Contracts mirror in
  `registry-market.ts` / `market_read_nodes.py` / `quant_metrics_nodes.py`;
  manifest regenerated. Docs updated: `docs/graph-studio.md`,
  `docs/CHANGELOG.md`.
- **feat(graph): instrument nodes — options payoffs and continuous futures.**
  `quant.options_strategy` (`graph_runtime/quant_instruments_nodes.py` →
  `quant/options.py` `analyze_option_strategy`) takes a leg list
  (`type/strike/quantity/premium`, optional `multiplier`/`iv`) and returns the
  expiry payoff curve, net premium, break-evens, max profit/loss and
  boundedness. An unbounded tail stays `null` with `bounded: false`; net Greeks
  appear only when a valuation spot AND a time-to-expiry are wired; the payoff
  range is configured or derived from the strikes/spot and `spotRangeSource`
  records which. `quant.futures_continuous` (`quant/futures.py`
  `splice_continuous`) splices ordered contracts at `rollDatesJson` with
  none/difference/ratio adjustment and emits an OHLCV series marked
  `proxy: true` with the engine's note (a continuous series is a backtest proxy,
  not a deliverable contract). Both mirrored in `registry-quant-advanced.ts`,
  presented in `config-fields.ts`, exemplified in `node-examples.ts`, manifest
  regenerated. Tests: `python/tests/test_graph_quant_instrument_nodes.py` (10:
  spread payoff/break-even/boundedness, naked-call unboundedness, Greeks wiring,
  derived range, half-configured range, engine leg errors, splice at roll,
  unadjusted splice, bad roll schedule, empty contracts).
  Also re-synced `docs/graph-studio.md` with the concurrent change that made
  `quant.risk_metrics`/`quant.drawdown` accept OHLCV or raw number lists (their
  `ANY` input ports were already in both registries; only the sentence was
  stale). Docs updated: `docs/graph-studio.md`, `docs/NAVIGATION.md`,
  `docs/CHANGELOG.md`.
- **feat(graph): quant tier-3 nodes — portfolio backtest, explicit costs, Edge
  Report.** `quant.portfolio_backtest` (`graph_runtime/quant_portfolio_nodes.py`)
  adapts the `{symbol: OHLCV}` map into one `MarketDataset` and drives the
  existing `run_portfolio_backtest` (shared book/cash, per-strategy symbol
  bindings). Default is one preset strategy per symbol; `strategiesJson`
  supplies explicit `StrategySpec`s that must declare `universe.symbols`. The
  engine's own double-claimed-symbol check and a missing-symbol check are the
  explicit failures. `quant.costs` (`quant/costs.py` `simulate_costs`) computes
  one cost family over an order list with the execution block as
  `executionJson`; a model missing its input contributes zero and emits a
  warning instead of inventing a cost. `quant.edge_report`
  (`quant/edge_report.py` `build_edge_report`) renders the Markdown report,
  bounded chart specs and verdict from a backtest artifact, naming absent
  figures rather than drawing empty ones. Refactor: `series_map` is now public
  and takes a node label so the shared `{symbol: rows}` adapter reports the
  node that actually rejected the payload. New TS contract file
  `registry-quant-advanced.ts` (`QUANT_ADVANCED_DEFINITIONS`), presentation in
  `config-fields.ts` (the portfolio block drops the single-series `symbol` and
  `strategyJson` labels), examples, manifest regenerated. Tests:
  `python/tests/test_graph_quant_portfolio_nodes.py` (6: preset basket,
  determinism, explicit specs, absent symbol, double claim, bad JSON) and five
  new cases in `test_graph_quant_validation_nodes.py` (commission total,
  frictionless zero with its warning, bad order/execution, report + charts +
  verdict, missing artifact). Docs updated: `docs/graph-studio.md`,
  `docs/NAVIGATION.md`, `docs/CHANGELOG.md`.
- **docs(graph): bot, skill and agent node plan.** Added
  `docs/graph-studio-bot-skill-nodes-plan.md`: verified inventory of the three
  agent nodes, the bot-as-tagged-Automation model, and the absence of any skill
  reference in either node registry; six Tier-1 node contracts (`agent.bot`,
  `skill.invoke`, `agent.classify`, `agent.extract`, `agent.summarize`,
  `agent.critique`); the `agent.bot` / `skill.invoke` execution sequences
  (including the real status mapping and the `NodeExecContext` operator/grant
  prerequisite); three bot-selectable surfaces (real agent presets in the create
  dialog, "Reuse a bot" in Bots mode, an `agent.bot` picker in the inspector);
  Tier-2/Tier-3 candidates; rejected alternatives; and the work breakdown.
  Docs updated: `docs/graph-studio-bot-skill-nodes-plan.md`, `docs/NAVIGATION.md`,
  `docs/CHANGELOG.md`.
- **feat(graph): quant structure nodes — align, regime labels, position size.**
  Added three executable COMPUTE nodes in
  `graph_runtime/quant_structure_nodes.py`, each an adapter over a tested
  engine: `quant.align` (`quant/transform.py` `align_rows`: `{symbol: rows}` in,
  shared timestamp axis + per-symbol series + missing counts out; `fill: none`
  by default, `ffill`/`zero` only on explicit request and `imputed` records
  it), `quant.regime` (`quant/regime.py` `classify_series`: trend × volatility
  label, confidence and counts per bar, with `warmupBars` naming the leading
  bars before the trend filter has a reading) and `quant.position_size`
  (`quant/sizing.py` `compute_quantity` with the engine's own `PositionSizing`:
  `percent_risk`/`atr`/Kelly take their stop, ATR and trade statistics as
  wired/config inputs and a missing one fails by name instead of returning
  zero). New TS contract file `registry-quant-structure.ts`
  (`QUANT_STRUCTURE_DEFINITIONS`), presentation in `config-fields.ts`, examples
  in `node-examples.ts`, manifest regenerated (`npm run graph:manifest`).
  Tests: `python/tests/test_graph_quant_structure_nodes.py` (13 cases: inner
  join, null-vs-imputed gaps, single-payload refusal, warm-up trend bars,
  classifier config rejection, percent-equity/percent-risk/ATR sizing, lot
  rounding, venue minimum, and the named missing-input failures).
  Docs updated: `docs/graph-studio.md`, `docs/NAVIGATION.md`,
  `docs/CHANGELOG.md`.
- **feat(graph): quant validation pack phase 2 — robustness, trade analysis,
  overfitting check.** Added `quant.robustness` (`quant/robustness.py`:
  one-at-a-time parameter sweep from `paramSpaceJson` or the preset's default
  space, cost-multiplier curve, trade concentration, chronological regime
  splits → deterministic `robust` / `fragile` / `insufficient_evidence` verdict
  plus conclusions that name their measurement), `quant.trade_analysis`
  (`quant/trade_log.py`: regime/trend/volatility context per entry, per-regime
  P&L, concentration and coverage; unmatched trades are counted and reported
  `unclassified`), and `quant.multiple_testing`
  (`quant/multiple_testing.py`: Deflated Sharpe from the selected return series
  plus trial Sharpes wired from `quant.optimize` or `trialSharpesJson`, and PBO
  via CSCV over `returnsMatrixJson`; trial Sharpes are de-annualized with
  `periodsPerYear` because deflation is defined on per-period Sharpes). When
  neither statistic is computable the node fails and names what is missing.
  Also exposed the shared `prepare_quant` / `param_space_from_config` /
  `STRATEGY_FIELDS` seams from `quant_nodes.py` so a validation run adapts the
  OHLCV payload and strategy config exactly like the research nodes do, instead
  of keeping a second copy. Mirrored in `registry-market.ts`, presented in
  `config-fields.ts`, exemplified in `node-examples.ts`, manifest regenerated,
  and the **Backtest and grade** starter template now also wires robustness
  conclusions beside the verdict. Tests: `python/tests/test_graph_quant_validation_nodes.py` grew to 24 cases
  (verdict determinism, insufficient-evidence, bad multiplier lists, entry
  classification vs unclassified, DSR trial count/source, PBO from a matrix,
  fallback Sharpes, and the explicit "nothing wired" failure).
  Docs updated: `docs/graph-studio.md`, `docs/NAVIGATION.md`,
  `docs/CHANGELOG.md`.
- **feat(graph): quant validation nodes — edge verdict, benchmark, resample.**
  Added three executable COMPUTE nodes in
  `graph_runtime/quant_validation_nodes.py`, each a thin adapter over an engine
  that already existed but was unreachable from a graph: `quant.grade`
  (`quant/verdict.py` `grade_edge` → A–F verdict, components, flags, and an
  explicit `assumptions.notGradedOn` for axes it could not judge),
  `quant.benchmark` (`quant/benchmark.py` → alpha/beta/correlation/tracking
  error/IR against a benchmark OHLCV series, reading the equity curve from a
  backtest result; `< 3` aligned returns is `available: false` with the reason)
  and `quant.resample` (`quant/transform.py` → deterministic OHLCV aggregation
  to a wider interval, partial buckets marked, finer targets refused). Mirrored
  in `src/lib/graph-studio/registry-market.ts` (`QUANT_VALIDATION_DEFINITIONS`),
  presented in `config-fields.ts`, exemplified in `node-examples.ts`, and
  regenerated into `registry.manifest.json` (`npm run graph:manifest` — this
  also brought the manifest back in sync with the pending market-read, webhook
  and integration contracts already in the working tree). Added the
  **Backtest and grade** starter template (`templates.ts`) so the pack is
  discoverable from the gallery. Tests:
  `python/tests/test_graph_quant_validation_nodes.py` (14 cases: components,
  redistributed weights, critical-flag capping, equity-curve flags, missing
  evidence failures, benchmark unavailability, bucket aggregation/partial
  marking, finer-target refusal). Docs updated: `docs/graph-studio.md`,
  `docs/NAVIGATION.md`, `docs/CHANGELOG.md`.
- **demo(graph): integration nodes live in Overview.** Added two starter
  templates — **Webhook to HTTP** (signed inbound webhook → `integration.http@1.1.0`
  → response/status) and **Signed webhook** (`integration.webhook_send`) — and
  `scripts/seed-integration-demo.mts`, which idempotently creates both demo
  workflows, creates/arms the inbound `WorkflowWebhook` with network access, and
  writes a gitignored signed-request helper to
  `.black-eclipse/demo/webhook-demo.ps1` (the secret is never printed). Verified
  end-to-end in the running app: the signed delivery started a run that fetched
  `https://postman-echo.com/get?demo=eclipse` (`200`, `ok: true`), and the signed
  outbound demo's run echoed `x-eclipse-signature`/`x-eclipse-timestamp` from
  postman-echo. Seed data lives in the local (gitignored) `jdds.db`; the
  templates and seed script are source.
  Docs updated: `docs/graph-studio-integration-nodes-plan.md`,
  `docs/NAVIGATION.md`, `docs/CHANGELOG.md`.
- **feat(graph): complete the gateway read surface + pure risk/return metrics.**
  Added 15 executable READ nodes in `graph_runtime/market_read_nodes.py`
  (`finance.instrument|orderbook|trades|volume|market_cap|fx_rate|
  options_chain|bond|funding_rate|open_interest|supply|tvl|onchain|
  liquidations|long_short_ratio`). Each reuses the EXISTING `MarketDataGateway`
  through the same helper as `finance.quote`, returns a `provenance` object
  built from the record's own `meta` (provider/freshness/quality/as-of/
  retrieval time), and turns a gateway rejection into an explicit node failure
  instead of a zero or a synthetic book. Added 4 pure COMPUTE nodes in
  `graph_runtime/quant_metrics_nodes.py` (`quant.risk_metrics`, `quant.drawdown`,
  `quant.correlation`, `quant.beta`): deterministic math over an INDICATOR
  series, with undefined ratios reported as `null` plus a note, never `0`.
  Both packs are mirrored in `src/lib/graph-studio/registry-market.ts`, get
  inspector presentation in `config-fields.ts`, and were added to
  `registry.manifest.json` (`npm run graph:manifest`). Tests:
  `python/tests/test_graph_market_read_nodes.py` (registry/executability,
  dispatch, provenance, honest failures, test-run execution) and
  `python/tests/test_graph_quant_metrics_nodes.py` (hand-computed metrics,
  drawdown/correlation/beta, graph wiring). Docs updated:
  `docs/graph-studio.md`, `docs/NAVIGATION.md`, `docs/CHANGELOG.md`.
- **feat(graph): HTTP 1.1.0, signed inbound/outbound webhooks, and the redirect
  SSRF fix.** Implemented the integration plan's P0 (plus the P1 webhook/test
  items). (1) New `graph_runtime/http_client.py`: manual redirects with an SSRF
  re-check on **every** hop, hop cap, HTTPS→HTTP refusal, redacted logs, query
  merge, body modes, response-type/cap (`error|truncate`), retries with
  `Retry-After`, and credential-env resolution. (2) `integration.http@1.1.0`
  (query, body modes, retries, `headers`/`ok`/`contentType`/`durationMs`/
  `truncated`); `1.0.0` stays registered and keeps its exact output shape.
  (3) `integration.webhook_send@1.0.0` signs
  `X-Eclipse-Signature/Timestamp/Delivery`. (4) `trigger.webhook@1.0.0` is
  zero-config; a new `WorkflowWebhook` + receipt model (Prisma, applied with
  `db push`) owns the endpoint, encrypted secret, method filter, response mode
  and arm state. (5) Public `POST|GET /api/webhooks/[slug]` (middleware-exempt):
  HMAC/timestamp replay window or token, 64 KiB cap, per-endpoint rate limit,
  delivery-idempotency receipt, safe mode = test run, armed mode = pinned
  version + content hash + confirmed network grant; write/trading refused.
  (6) `triggerContext` plumbing (run-server → Python service → executor) and the
  webhook node's `start/headers/query/method/receivedAt/meta` outputs.
  (7) Inspector **Webhook** tab + card summary (create/copy/rotate/pause/arm,
  last delivery), and an explicit **Test with network** confirmation for HTTP
  nodes (runtime refuses unless `allowNetwork`). Verified with
  `webhook-crypto.test.ts`, the HTTP operator suite (redirect/retry/truncate/
  SSRF cases), registry manifest parity, and a direct store arm/rotate check.
  Docs updated: `docs/graph-studio.md`,
  `docs/graph-studio-integration-nodes-plan.md`, `docs/NAVIGATION.md`,
  `docs/CHANGELOG.md`, plus app ADR-057 in `skills/ARCHITECT.md` (mirrored into
  `docs/DECISIONS.md`). Schema: `prisma/schema.prisma` (`WorkflowWebhook`,
  `WorkflowWebhookReceipt`) applied with `npx prisma db push`; `jdds.db` is not
  committed.
- **docs(graph): integration / HTTP / webhook node improvement plan.** Added
  `docs/graph-studio-integration-nodes-plan.md`: a verified audit of the
  integration category (only `integration.http@1.0.0`; no `trigger.webhook`
  despite the stale "three triggers" note; webhooks cannot act because every
  run is a test run) and an implementation-ready plan. It covers the
  redirect-based SSRF gap in `_exec_http`, an additive `integration.http@1.1.0`
  contract (query/body modes/retries/response headers/ok/duration), a signed
  inbound `trigger.webhook` with a `WorkflowWebhook` model and public
  `/api/webhooks/[slug]` endpoint, an "armed" pinned-version authority model
  (safe by default), safe-mode vs armed-mode semantics, the test matrix, the
  ticket breakdown, and the decisions needed. No code changed.
  Docs updated: `docs/graph-studio-integration-nodes-plan.md`,
  `docs/NAVIGATION.md`, `docs/CHANGELOG.md`.
- **feat(graph): first-run tour + a labelled node diagram; U4 deferred.** Closes
  the legibility plan. (1) New `graph-onboarding.tsx`: a three-card tour
  (a node is one step · connectors are labelled, round = value / square = branch ·
  Start workflow is a safe TEST run), shown once per browser from
  `localStorage`, dismissible, never blocking the canvas; the same content stays
  in the `?` panel. (2) `docs/graph-studio.md` "Reading a node" now carries a
  labelled node diagram. (3) **U4 (variadic ports) is deferred by decision**: the
  card and the inspector already hide over-declared ports, so the remaining work
  would add manifest v2 + validator/executor/canvas surface for no user-visible
  gain; the plan records the trigger to revisit (> 8 switch cases or > 3 merge
  inputs).
  Docs updated: `docs/graph-studio.md`, `docs/graph-studio-node-ux-plan.md`,
  `docs/CHANGELOG.md`.
- **feat(graph): inserting a node explains the port, and every logic node has a
  worked example.** Two more legibility items. (1) The add-a-step panel now
  states the insertion point — `After If / else · If true — a branch (run
  control). Only nodes with a Run control input can follow it.` / `After Filter ·
  Items (array). The new node must accept that type.` / both sides when inserting
  on an edge — and its empty state explains the rule instead of "no node can be
  wired here". (2) New `node-examples.ts` (presentation only, never in the
  manifest) backs an **Example** block in the inspector's Settings tab with one
  concrete input → output line for every `logic.*`/`flow.*` node plus the core
  data/transform/finance nodes; a test asserts the logic pack is fully covered
  and that no example names an unregistered type.
  Docs updated: `docs/graph-studio.md`, `docs/graph-studio-node-ux-plan.md`,
  `docs/CHANGELOG.md`.
- **feat(graph): auto-save + fully opaque nodes.** (1) Node cards are now
  **fully opaque** (`#232329 → #141418`, light mode `#fff → #f5f5f8`): React
  Flow's transformed viewport is a backdrop root, so the previous near-opaque
  tint still let the grid/edges show faintly. No alpha remains. (2) The editor
  gained an **Auto-save** toggle (on by default, persisted per browser) and a
  2 s idle debounce: after the last edit the graph is persisted automatically,
  with `Saving…/Saved` in the header. The decision is the pure
  `shouldAutoSave()` policy — it never writes an invalid graph, never overlaps a
  save, keeps manual Save working, and additionally skips a save whose content
  hash equals the persisted one, so opening the editor cannot manufacture an
  empty version. Verified in the production build: opening created no version,
  a mode change auto-saved v4, reverting auto-saved v5.
  Covered by `autosave.test.ts` (6 cases). Typecheck + vitest green.
  Docs updated: `.opencode/skills/black-eclipse-ui/SKILL.md`,
  `docs/CHANGELOG.md`.
- **feat(graph): a node now says what it needs and what it did nothing with.**
  U2/U3 of the legibility plan. (1) A required input that is neither wired nor
  given a node literal puts an **amber ring** on the card plus a `Connect: Items`
  line, and names itself in the warning tooltip — the card's version of the
  validator's `missing_required_input`. (2) A node with more than one control
  output that fires a branch into nothing now logs `branch If true fired but
  nothing is connected to it — the run continues with no effect`
  (`executor._report_dead_branch`); single-`done` nodes stay quiet. (3) The
  inspector header shows the node's one-line description; the palette shows
  `N in · M out` and a `branch` marker. (4) The canvas `?` panel opens with a
  three-line **Reading a node** legend (round = value, square = branch, amber ring
  = needs a connection). Plan progress updated in
  `docs/graph-studio-node-ux-plan.md`.
  Docs updated: `docs/graph-studio.md`, `docs/graph-studio-node-ux-plan.md`,
  `docs/CHANGELOG.md`.
- **feat(graph): ports are labelled, so a branch is readable at a glance.**
  The reported pain was that If / else showed three identical dots and Switch
  showed ten. (1) Every port now carries a visible label beside its handle (right
  of outputs, left of inputs, on a chip so an edge cannot hide it); single-port
  nodes keep just the dot. (2) Control ports are **square**, data ports **round**,
  in the card and in the inspector, so a branch handle can never be mistaken for a
  value handle. (3) Branch outputs come first and are named as sentences:
  `True`/`False` → **If true**/**If false**, `Default` → **No match**,
  `Matched` → **Any match**, gate `In 2/3` → **Run 2/3**, stop's value input →
  **Output** (handles keep their ids, so saved graphs are untouched; both
  registries + the manifest were updated). (4) The inspector's Settings tab now
  lists the SAME visible ports as the card via `node-ports.ts`, so a Switch no
  longer lists eight unused cases; its `Case index` data output only shows when
  wired. (5) The card subtitle is the node's one-line description instead of its
  category. (6) New validation warning `switch_double_branch` when "Any match"
  and a specific case are both wired (both would run). Plan:
  `docs/graph-studio-node-ux-plan.md`.
  Docs updated: `docs/graph-studio.md` ("Reading a node"),
  `docs/graph-studio-node-ux-plan.md`, `docs/NAVIGATION.md`, `docs/CHANGELOG.md`.
- **feat(graph): a working loop demo, created in the app (`npm run graph:loop`).**
  Adds `scripts/graph-loop-demo.mts`, which builds two IR documents with the real
  editor registry, validates them, and (without `--dry`) creates them in JDDS as
  **`Loop body — 7% growth step`** (trigger → `x * 1.07` → result) and
  **`Compounding planner (loops)`** — a parent exercising all three loop shapes
  against that pinned body: `flow.repeat` (12-year horizon, then an if/else on
  the target), `flow.while` (until the balance clears 2 000) and `flow.for_each`
  (three principals projected one year each). `npm run demo:loop` then runs the
  pair through the real runtime via `python/examples/loop_demo.py` +
  `scripts/demo-loop.js` and asserts every branch outcome (12 iterations,
  2 252.19 target met, 11 while-iterations, ordered for-each results), exiting
  non-zero on regression. Writing it surfaced a genuine wiring rule: a transform
  chained after a gate must take the gate's `done` on its `in` control port, or
  it runs on dataflow alone with a null input when the branch is skipped.
  Docs updated: `docs/graph-studio.md`, `docs/CHANGELOG.md`.
- **fix(graph): a Switch shows the cases you configured, not ten anonymous
  handles.** The node declared `case1…case8` for an eight-way branch, so every
  Switch card drew ten output handles (plus ten stacked `+` buttons) whatever the
  operator typed, and the per-case outputs were unlabelled — a 3-case switch
  looked broken and could not be adjusted. `node-ports.ts` now derives the
  *presentation* from the node's `cases` (handle ids unchanged, so edges,
  validation and the runtime are untouched): one output per configured case,
  labelled with its value, plus `default`/`matched`/`caseIndex`; a wired case
  handle stays visible when its case is removed so no edge is orphaned. Handle
  spacing compresses as the fan grows and the per-port `+` shortcut is withdrawn
  above four outputs, where the buttons overlapped and hit-tested the wrong
  branch. The field is relabelled **Cases (one output each)** with help that
  explains the mapping. Validation gained `invalid_switch_cases` (error) for
  non-JSON case text and `switch_case_not_configured` (warning) for a branch
  pointing at a case that no longer exists.
  Docs updated: `docs/graph-studio.md`, `docs/CHANGELOG.md`.
- **fix(graph): graph nodes are opaque — the canvas can no longer show through.**
  React Flow's viewport carries a CSS `transform`, which makes it a backdrop
  root: a node's `backdrop-filter` could only sample that subtree, so the
  0.58-alpha `.node-card` tint let the grid, edges and neighbouring nodes bleed
  through the card. Node cards are now a near-opaque graphite gradient
  (alpha 0.97/0.98, light mode matched) keeping the inset highlight and soft
  shadow; the blur was removed rather than left reporting a filter that cannot
  render there. Verified in the production build: computed
  `background-image` is the opaque gradient and `backdrop-filter` is `none`.
  The UI skill gained hard rule 6 (“canvas nodes cannot frost”) so this is not
  reverted later. CSS only.
  Docs updated: `.opencode/skills/black-eclipse-ui/SKILL.md`,
  `docs/CHANGELOG.md`.
- **refactor(graph): split the formula language and the template renderer out of
  `nodes.py`.** `nodes.py` reached 1597 lines, over the 1200-line hard ceiling
  enforced by `test_size_budget.py`. The safe formula language (tokenizer,
  parser, function table, `evaluate_formula`) moved to `graph_runtime/formula.py`
  and the bounded template renderer (paths, format specs, `{{#each}}` blocks,
  output budget) moved to `graph_runtime/template.py`; `nodes.py` (1080 lines)
  re-exports `evaluate_formula`, `FormulaError` and `render_template`, so every
  existing import site is unchanged. Behaviour is identical: the graph suite
  (408), `test_stats_formula.py` and the size-budget test pass.
  Docs updated: `docs/graph-studio.md`, `docs/NAVIGATION.md`, `docs/CHANGELOG.md`.
- **feat(graph): switch routing, gate joins, dedupe modes, loop state.** Closes
  the remaining logic-pack defects from the plan. (1) `logic.switch` fires the
  matching `case1`…`case8` control output in addition to `matched` (first match
  wins, >8 still fires `matched`), so a 3-way branch is one node. (2) `flow.gate`
  gained `in2`/`in3` and `require: any|all`; `all` is a join whose unmet case is
  reported as a skipped node (`skipped_by_node`) via a new generic `_skip`
  result key, not a scheduler special-case. (3) `logic.deduplicate` gained
  `keep: first|last` and `caseInsensitive`. (4) `flow.while` conditions can read
  the body's numeric and boolean fields (`done != 1`), fixing the state that
  silently projected to `0`; the legacy `value` projection is unchanged. (5)
  `RunStopRequest` now validates the `_stop` payload instead of being dead code.
  Additive: no node version changed, no config removed. New
  `test_graph_logic_pack.py` covers all four. Verified: manifest regenerated,
  Python graph suite 359 passed, vitest 141, `tsc --noEmit`.
  Docs updated: `docs/graph-studio.md`, `docs/CHANGELOG.md`.
- **feat(graph): Wave 0 of the logic-node plan — the pack can no longer lie.**
  (1) `logic.stop` gained an optional `value` input so it can carry the run
  output (`status` was already honoured by the preceding stop fix). (2)
  `logic.wait` polls cancellation every 100 ms and reports the time actually
  waited, instead of blocking a worker for up to 30 s. (3) `logic.map`/`filter`/
  `reduce` no longer bind a missing row field as `0.0` — a silent zero made
  `filter` drop every row of a text field; the field now fails honestly. (4)
  `logic.aggregate` returns `null` for an empty input on every op except `count`
  (its `value` port is declared `nullable`) instead of a fabricated `0`. (5)
  `logic.merge` gained `first_present` (legacy `first` shares it): a branch is
  present unless it is null or empty, so an empty `A` no longer shadows a
  populated `B`, while `0`/`false` stay real values. (6) every logic node emits
  one summary line per run. (7) a skipped node names the control wire that did not
  fire. (8) new `test_graph_node_config_usage.py` asserts every declared config
  field of the `logic.*`/`flow.*` pack is read by its executor — the test that
  would have caught the original `logic.stop` defect. `NodeExecContext` gained
  defaulted `control_fired` and `should_cancel` for the gate-join and
  cancellation work that follows. Manifest regenerated. Verified: `tsc --noEmit`,
  vitest (141), the graph Python suite (376) and `demo:transform`.
  Docs updated: `docs/graph-studio.md`, `docs/graph-studio-logic-nodes-plan.md`,
  `docs/CHANGELOG.md`.
- **fix(graph): logic/flow control surface + a silent Stop bug.** (1) *Stop
  ignored its own `status`.* Choosing `failed` still produced a SUCCEEDED run.
  The node now returns a `_stop` request the executor reads: the node succeeds
  (so `stops_run` skips the rest), and the run finishes FAILED with the
  configured message; `succeeded` keeps the previous behaviour. (2) *Control
  ports are consistent.* `logic.condition` and `logic.switch` gained the optional
  control `in` (their exclusive `true`/`false` and `matched`/`default` outputs
  stay); `logic.merge`, `flow.gate`, `logic.wait`, `flow.subworkflow` and
  `flow.for_each`/`repeat`/`while` gained `done` (loops and subworkflow fire it
  from the orchestrator), and merge/gate/wait also chain now. (3) *Switch cases*
  accept a JSON array (`["a,b","c"]`) when a case contains a comma. (4)
  `flow.repeat`/`flow.while` gained `continueOnError`, which the loop runner
  already honoured for `flow.for_each`. (5) Deferred `wait` now fires `done` on
  resume instead of dropping it. (6) Merge's `strategy` renders as a select
  instead of free text. Additive: no node version changed.
  Covered by `test_graph_executor.py`, `test_graph_registry_parity.py` and
  `config-fields.test.ts`. Docs updated: `docs/graph-studio.md`,
  `docs/CHANGELOG.md`.
- **docs(graph): the logic-node plan is now implementation-ready.**
  Rewrote `docs/graph-studio-logic-nodes-plan.md` as a spec-grade plan: 8
  documented defects (added `flow.while`'s numeric-only state), per-node target
  contracts (ports, config fields with bounds, semantics, errors, compat, tests),
  nine cross-cutting enablers (execution-context additions, rows config editor,
  shared condition module, typed expression language, variadic ports, error
  routing, inline bodies, body validation), a ticket-level work breakdown with
  effort and dependencies, versioning/`strictValues` rules, a per-node test
  matrix, a definition of done, risks and six open decisions. No source change.
  Docs updated: `docs/graph-studio-logic-nodes-plan.md`, `docs/CHANGELOG.md`.
- **docs(graph): plan for improving the logic / control-flow node pack.**
  Adds `docs/graph-studio-logic-nodes-plan.md`: an audit of the 15 logic nodes
  read from the code (7 concrete defects — `logic.stop` ignoring `status`, the
  silent-zero coercion in map/filter/reduce and aggregate, non-cancel-aware
  `logic.wait`, `logic.switch` routing every case to one output, `logic.merge`
  preferring an empty `a`), the shared contract chain, and a 4-wave plan
  (correctness → additive expressiveness → typed expression language + variadic
  ports + inline bodies → performance) with explicit compat/versioning rules and
  a test plan. Registered in `docs/NAVIGATION.md`.
  Docs updated: `docs/graph-studio-logic-nodes-plan.md`, `docs/NAVIGATION.md`,
  `docs/CHANGELOG.md`.
- **chore(next): honour the file-tracing exclude on production builds.**
  `next.config.ts` declared `outputFileTracing: { excludes: … }`, which Next 15
  does not recognise (build printed "Unrecognized key(s)"), so the
  `.black-eclipse/**` workspace copies were never excluded from the trace and
  the EPERM the comment describes could return. Replaced with the supported
  `outputFileTracingExcludes`. Verified by a production `next build` with no
  config warning.
  no doc change — build configuration only; `docs/QUICKSTART.md` already
  describes `npm run build && npm start`.
- **feat(bots): the bot brain picker shows real agent presets.** The New bot
  dialog rendered a hardcoded `BOT_AGENTS` array, so a preset authored in
  Settings › Agents was invisible (and the seven `institution-*` seats in that
  array could not resolve as a standalone `run_agent`). The option list is now
  built from the live runtime: `src/lib/agent-presets/choices.ts` (pure:
  built-ins first, user presets by name, archived kept and flagged, an unknown
  saved id appended and labelled) + `use-agent-choices.ts` (loader with a
  built-in fallback). `create-bot-dialog.tsx` renders it grouped and rejects an
  unknown agent before save; `validateDraft` takes an optional known-id list.
  **Runtime fix:** `graph.resolve_agent` now falls back to `AgentPresetStore`
  through the new `agent_presets.agent_config_from_preset`, the same projection
  `graph_runtime/bootstrap._agent_runner` uses — a bot's scheduled `run_agent`
  enters there, so without it a custom preset worked in chat and failed on its
  schedule. Tests: `src/lib/agent-presets/choices.test.ts` (6 cases),
  `python/tests/test_agent_presets.py` + `test_graph.py` (preset projection,
  preset resolution, unknown-agent failure).
  Docs updated: `docs/graph-studio.md`, `docs/NAVIGATION.md`,
  `docs/graph-studio-bot-skill-nodes-plan.md`, `docs/CHANGELOG.md`.

- **feat(graph): `skill.invoke` — installed skills run as a node.** One generic
  node, not one per skill (skills are runtime data; the registry is a static
  contract with a manifest + Python mirror). TS contract
  `src/lib/graph-studio/registry-skills.ts` (`SKILL_DEFINITIONS`, category
  `skills`, so the library has a "Skills" group), presentation in
  `config-fields.ts`, `NodeCategory` + the three category maps updated, manifest
  regenerated. Runtime `python/harness/graph_runtime/skill_nodes.py` is a thin
  adapter: `bootstrap._skill_runner` calls the EXISTING
  `AgenticService.run_skill` → `execute_skill`, so permissions, version
  resolution and the tool check are the same ones chat uses. Status is the
  contract — only `completed` yields `output`/`result`/`evidence`; `blocked` /
  `denied` / `failed` / `cancelled` / `unavailable` fail the node with the
  runtime's code and message, and a failed skill's partial transcript is never
  surfaced. `inputJson` and the optional `input` port merge per key (wire wins).
  `NodeExecContext` gained `operator` (filled as `not testRun` by the executor),
  so an operator-authored permission set is honoured; a test run refuses by name
  any skill whose declared tools are not all in `DRY_RUN_TOOLS`. The inspector
  picks from the live skill list (`skills-browser.listSkills`) with status, tools
  and description. Tests: `python/tests/test_graph_skill_node.py` (18 cases:
  completed projection, pinned version, wire-vs-config merge, missing skill,
  unbound runtime, bad payloads, five non-completed statuses, test-run compile,
  operator default).
  Docs updated: `docs/graph-studio.md`, `docs/NAVIGATION.md`,
  `docs/graph-studio-bot-skill-nodes-plan.md`, `docs/CHANGELOG.md`.

- **feat(bots): `agent.bot` node + "Start from" an existing bot.** A saved bot
  can now be a step in a graph: `agent.bot` (`registry-agents.ts`,
  `graph_runtime/agent_nodes.py`) resolves the id at run time through
  `set_bot_resolver` (bound in `bootstrap` to
  `automation_store().get_automation`, the same `bot`/`monitor`/`mon_` rule the
  workspace uses) and runs ONE bounded turn with the bot's own agent preset and
  objective. It never registers a trigger or runs the bot's schedule; a
  **workflow** bot is refused by name (`use flow.subworkflow`), a deleted bot
  fails by name, and an optional `context` object is appended as bounded
  labelled JSON data (never instructions). The bot's per-run model override is
  ignored — the graph run's resolved settings win. Inspector: a live bot picker
  (workflow bots shown disabled). B2: the New bot dialog gained a **Start from**
  picker that copies an existing bot's brain/objective/schedule/face into a NEW
  bot; the original is untouched and a copied schedule is created `draft`
  (paused), so two copies never fire at the same minute. Manifest regenerated.
  Tests: 8 new cases in `python/tests/test_graph_agent_node.py` (own agent,
  objective fallback, bounded context, workflow refusal, unknown bot, non-bot
  automation, missing id/store, unbound runtime).
  Docs updated: `docs/graph-studio.md`, `docs/NAVIGATION.md`,
  `docs/graph-studio-bot-skill-nodes-plan.md`, `docs/CHANGELOG.md`.

- **feat(graph): four structured agent nodes — classify, extract, summarize,
  critique.** Each is ONE bounded model call with a strict response schema, not
  an agent turn: `python/harness/graph_runtime/agent_structured.py` holds the
  prompts + JSON schemas + `normalize_labels`/`validate_extraction`;
  `agent_structured_nodes.py` holds the four contracts and executors, with the
  model bound at boot through `set_structured_runner` (so tests substitute a
  fake and the module imports no runtime). TS contracts in
  `registry-agents.ts`, presentation in `config-fields.ts`, manifest
  regenerated. The NODE owns the contract: a label outside the declared set, a
  verdict outside supported/weak/contradicted, a confidence/score outside 0..1
  or an empty summary fails the node instead of being coerced; an extraction
  that does not match the schema (type/required/properties/items) returns
  `valid: false` and logs the issues rather than pretending. Deliberate
  deviations from the plan: no `agent`/`maxSteps` config (there is no preset or
  tool loop to bound — these never bind a tool), `agent.critique.score` is
  nullable (the model may omit it), and `agent.summarize.text` is `any` so it
  takes an array/object as well as a string. Tests:
  `python/tests/test_graph_structured_nodes.py` (20 cases).
  Docs updated: `docs/graph-studio.md`, `docs/NAVIGATION.md`,
  `docs/graph-studio-bot-skill-nodes-plan.md`, `docs/CHANGELOG.md`.

- **feat(graph): utility + memory nodes — assert, fallback, extract, recall,
  remember.** Five nodes: three deterministic primitives
  (`logic.assert`: fails the node with a named message unless truthy/falsy/
  present; `logic.fallback`: first PRESENT of three inputs + which port;
  `data.extract`: dotted path with list indexes, `found: false` or a named
  failure — never an invented value) in `utility_nodes.py`, and two adapters over
  the ONE Eclipse memory service (`memory.recall` → `retrieve`, returning the
  same bounded `context` block an agent gets; `memory.remember` → `write_memory`,
  so dedupe/conflict/retention stay the service's) in `memory_nodes.py`. Runners
  are bound at boot (`set_memory_recall_runner` / `set_memory_remember_runner`).
  `memory.remember` declares `memory.write` + `local_write` and refuses a test
  run (compile-time capability envelope, plus an executor guard). TS contracts in
  the new `registry-utility.ts` (+ `MEMORY_TYPES`, asserted against the store by
  test), presentation in `config-fields.ts`, examples for the two new logic nodes,
  manifest regenerated. Tests: `python/tests/test_graph_utility_nodes.py` (20
  cases incl. the MEMORY_TYPES drift guard); parity green.
  Deliberately NOT shipped (recorded in the plan): `agent.team` (team runtime
  seam), `output.notify` (delivery is automation-definition-scoped),
  `output.chart` (artifact plane), `research.source_rank` (duplicates
  conflicts/completeness and would invent a trust taxonomy).
  Docs updated: `docs/graph-studio.md`, `docs/NAVIGATION.md`,
  `docs/graph-studio-bot-skill-nodes-plan.md`, `docs/CHANGELOG.md`.

## 2026-10-31
- **fix(graph): the template output cap is enforced while rendering.** Nested
  `{{#each}}` blocks multiply rows, and the 50 000-character cap was checked only
  on the finished string — a 10 000 × 10 000 block could allocate gigabytes
  before failing (the per-node timeout cannot kill the worker thread). The
  renderer now spends a shared budget as it appends, so the same input fails in
  ~10 ms instead of minutes. Regression test: `test_graph_template_formula.py::
  test_nested_blocks_hit_the_output_cap_while_rendering`.
  Docs updated: `docs/CHANGELOG.md`.
- **feat(graph): runnable transform demo (`npm run demo:transform`).** Adds
  `python/examples/transform_demo.py`, a self-checking walkthrough of the
  template/formula/tabular nodes against the real runtime: 20 PASS/FAIL checks
  over row blocks, formula guards, aliases, numeric sorting, composite joins,
  aggregate statistics, dedupe identity and control-port gating, exiting
  non-zero on any mismatch. `scripts/demo-transform.js` runs it with the same
  interpreter the runtime uses; interpreter discovery moved to
  `scripts/python-runner.js` so the demo and `test-python.js` cannot disagree
  (also corrected that runner's slice example to `python/tests/...`).
  Docs updated: `docs/graph-studio.md`, `docs/CHANGELOG.md`.
- **feat(graph): table analytics, row-block templates, one identity rule.**
  (1) `logic.aggregate` gained `median`, sample `stddev` and `percentile`
  (linear interpolation, new `percentile` 0–100 field) on top of
  sum/avg/min/max/count; it now coerces numeric strings instead of rejecting
  them, and orders groups by value rather than `str(tuple(...))`, so a group key
  of `"10"` no longer sorts before `"9"`. (2) `transform.template` renders
  `{{#each a}}…{{/each}}` row blocks — row-scoped lookups, `{{this}}`,
  `{{index}}`, five levels of nesting, 10 000 rows per block — plus `\{{` for a
  literal brace. (3) `logic.deduplicate` now uses the shared `key_part` identity
  from `values.py`, so `1`, `1.0` and `"1"` collapse exactly as `transform.join`
  matches them. All additive: no node version changed, no config removed.
  Covered by `test_graph_template_formula.py`, `test_graph_tables.py` and
  `config-fields.test.ts`.
  Docs updated: `docs/graph-studio.md`, `docs/CHANGELOG.md`.
- **feat(graph): node-contract guardrails + control coverage.** (1) *Parity now
  covers bounds*: `registry.manifest.json` carries each config field's
  `maxLength`/`enum`/`min`/`max`/`integer`, read from the zod schema (no
  duplicated spec), and `test_graph_registry_parity.py` fails when the editor and
  the runtime disagree about a valid value — 279 fields already matched, so the
  new assertion is a ratchet, not a migration. (2) *Undeclared control outputs*
  are refused by the executor: firing a `_control` name a node does not declare
  used to route nowhere and look like a successful branch. (3) *Control ports*
  extended to `logic.aggregate`, `logic.deduplicate`, `logic.map`,
  `logic.filter`, `logic.reduce`, `data.dataset.save` and `data.dataset.load`
  (optional `in` + `done`), completing the branchable set. (4) *Controls*:
  `transform.sort_limit` gained `caseInsensitive`, and `transform.select`'s
  `rename` is now a key/value row editor over the same JSON-string contract
  (`jsonString` presentation flag), so no saved graph changes. (5) **ADR-H344**
  records the additive-versioning rule this relied on. Additive only; no node
  version changed. Covered by `test_graph_registry_parity.py`,
  `test_graph_executor.py`, `test_graph_tables.py`, `config-fields.test.ts`.
  Docs updated: `docs/graph-studio.md`, `docs/harness/decisions.md`,
  `docs/CHANGELOG.md`.
- **feat(graph): transform nodes — correctness pass, richer controls, control
  ports.** (1) *Bugs*: `transform.formula` rejected trailing whitespace and
  parsed `-2 ** 2` as `4`; `transform.select` treated `a.b` as a literal column
  name (dotted paths now resolve, with `alias=path`), and a `rename` collision
  used to drop a column silently; `transform.sort_limit` sorted numeric strings
  lexicographically and put nulls first on `desc`; `transform.join` matched `1`
  and `1.0` differently and silently kept only the first of several right rows
  per key. (2) *Capabilities*: template dotted paths, number/date formats,
  `{{a?}}` and a hard error for a null required value; formula `if`/`div`/`nz`/
  `clamp`/`sign`/`log10`, half-up `round`, and series-payload inputs; multi-key
  sort with `offset`; join composite keys, right/full/anti, `onDuplicate`,
  `caseInsensitive`, `suffix` and null-filled outer rows. Shared path/identity
  rules moved to the new `graph_runtime/values.py`. (3) *Controls*: the panel now
  exposes sort-key, join-mode, missing-field and duplicate policies with help
  text instead of bare text boxes. (4) *Control ports*: each transform node
  gained an optional control `in` and a `done` output, so If/else, Switch and
  Gate can own them; the single-node tester reports `firedControls` instead of
  leaking `_control` into outputs. Additive only — unwired control inputs keep
  running on dataflow. Covered by `test_graph_template_formula.py`,
  `test_graph_tables.py`, `test_graph_executor.py` and `config-fields.test.ts`.
  Docs updated: `docs/graph-studio.md`, `docs/CHANGELOG.md`.
- **style(graph): graphite panel surfaces for the inspector rail and run console.**
  The node inspector (`aside`) and the expanded run console now use a shared
  `.graph-panel` material — translucent graphite gradient, 20px blur, inset top
  highlight — so they read as part of the node surface family instead of a flat
  `bg-background/40` cut. Light mode gets a soft white version. No behaviour
  change.
  no doc change — presentational surface only; behaviour is unchanged.
- **fix(artifacts): discovery no longer skips artifacts with long paths.** The
  idempotency key `discover:<path>:<checksum>` is capped at 200 chars by the
  schema; a deep artifact path overflowed it, raised, and the file was silently
  left out of the catalog. An over-long key is now hashed.
  no doc change — internal repair path, contract unchanged.
- **feat(graph): dataset picker + editable data-node fallbacks.** The four data
  nodes are now usable without an upstream wire. `data.json.parse` gained a
  **JSON text** field, `data.dataset.save` a **Payload (JSON)** field, and
  `data.dataset.load` a **Saved datasets** picker (ref, name, type, rows, bytes)
  backed by the new read-only `GET /graphs/datasets` route + `/api/graph-runs/
  datasets` proxy, with a manual ref field kept. Resolution is
  `wire → node literal → config`. The validator, compiler and executor share the
  same fallback table so a config-only node compiles and runs; `data.set_variables`
  keeps its key/value rows. Covered by `test_graph_datasets.py`,
  `test_graph_input_literals.py` and `validation.test.ts`.
  Docs updated: `docs/graph-studio.md`, `docs/CHANGELOG.md`.
- **feat(graph): port literals + richer node controls.** Two linked updates to
  the Graph Studio node UX. (1) **IR v2**: `WorkflowNode.inputValues` (keyed by
  port id) lets an unwired data input carry a literal, so a node is usable
  without a producer. A wire wins; required inputs are satisfied by a wire OR a
  literal; control ports never take literals. A v1→v2 migration adds an empty
  map, the validator warns when a wired port's literal is ignored, and the
  Python runtime mirrors the rule (`model.py`, `compiler.py`, `executor.py`:
  `wire → literal → optional/null`). The inspector gained an **Inputs** section
  with type-aware editors and the node **Test** tab prefills from literals.
  (2) **Structured field kinds**: `textarea`, `keyvalue` (row editor for
  `data.set_variables`), `code` (JSON validate/format), `combobox` (free text
  with suggestions) and `slider`, implemented in `config-field.tsx` +
  `key-value-editor.tsx` and wired through `config-fields.ts`. Constant/input,
  Save dataset and Write file now have clearer controls and help text.
  Covered by `validation.test.ts`, `patches.test.ts`, `ir.test.ts` and
  `python/tests/test_graph_input_literals.py`.
  Docs updated: `docs/graph-studio.md`, `docs/CHANGELOG.md`.
- **fix(charts): the allocation donut, trade replay and economics comparison
  use the palette too.** The portfolio allocation donut had a fixed rainbow,
  the trade-replay entry line and the economics comparison line were a fixed
  sky blue — the last charts that ignored Settings › General › Charts.
  no doc change — palette behaviour is documented in `docs/chart-engine.md`.
- **fix(charts): strictly greyscale axes and grid.** The series palette was
  neutral but the axis text, ticks and grid still used the slate blue-grey
  `#94a3b8` / `rgba(148,163,184,…)`, so a "monochrome" chart still carried a blue
  tint. Ink, muted text, ticks and grid are neutral greys now, in both the
  Plotly figure and the matplotlib theme.
  no doc change — `docs/chart-engine.md` already states the palette is neutral.
- **fix(chat): the "Proof it works" card only appears when there is a proof.** A
  run that recorded no check but did produce an artifact or a clean change
  review still rendered the card — with a "0 check(s)" count that claimed a
  check that never happened. The card now needs a recorded check, an unsupported
  claim, a FAILED artifact check, a review finding or a repair, and the count is
  hidden when there is nothing to count.
  Docs updated: `docs/interactive-response-engine.md`.
- **fix(chat): the metadata cards under an answer were noise.** "Proof it works"
  no longer renders when nothing was checked (a `0 check(s)` card claimed a
  check that never happened), and a computed result's method line drops debug
  dumps such as `type <class 'dict'> · keys [...]` instead of printing them.
  The evidence card's spacing was opened up (roomier header, source rows and
  section gaps) so "Sources consulted" no longer reads as one cramped block.
  Docs updated: `docs/interactive-response-engine.md`.
- **feat(charts): neutral default palette + the user's own colours.** Charts
  are greyscale by default (`#fafafa` → `#52525b`) because a hue should not
  invent a meaning the numbers do not carry; candlesticks use a light/dark pair
  and heatmaps a neutral ramp. The live Plotly figure now applies the palette
  from Settings › General › Charts in the browser (`charts/apply-palette.ts`),
  so a colour change repaints instantly (React, not a replot) and the new
  **Save as PNG** button exports exactly what is on screen. Plotly's own dark
  modebar pill is gone; the frosted zoom / reset / save toolbar replaces it.
  Docs updated: `docs/chart-engine.md`.
- **feat(graph): `Data pipeline` starter template.** Added a sixth starter graph
  that places all six basic data/write nodes in one workflow — `data.value`
  (twice: JSON text and output path), `data.json.parse`, `data.set_variables`,
  `data.dataset.save`, `data.dataset.load`, `file.write` — wired
  trigger → parse → variables → save → load → write → result. It is the clickable
  counterpart to `python/tests/test_graph_data_nodes_wiring.py`. Because
  `file.write` is a write effect, a test run refuses it by design; the template
  is meant for an operator run that grants the `workspace` scope, and its
  description says so. Covered by `validation.test.ts`.
  Docs updated: `docs/graph-studio.md`, `docs/CHANGELOG.md`.
- **test(graph): wiring proof for the six basic data/write nodes.** Added
  `python/tests/test_graph_data_nodes_wiring.py`, which places `data.value`
  (literal + wired override), `data.set_variables` (config wins over input),
  `data.json.parse` (strict true/false), `data.dataset.save`/`load` (roundtrip,
  missing ref, owner/TTL), and `file.write` (config vs wired path, append,
  traversal refusal, denied scopes) each in a minimal workflow, then chains all
  six in one operator run. This executes the real compiler + executor, not just
  the executor functions, so a palette-visible node is also proven usable. No
  doc change — test-only; the node contracts are already documented in
  `docs/graph-studio.md`.
- **fix(graph): a run's `runInput` never reached the trigger.** The Python
  `/graphs/runs` body named the field `input`, while the front door sends
  `runInput` (the same key the durable job payload uses), so every workflow-bot
  turn and scheduled workflow run started with a null Start value and replied
  with an empty result. `RunRequest.input` now accepts the `runInput` alias
  (`input` still works for direct callers), covered by
  `python/tests/test_graph_api.py::test_run_input_reaches_the_trigger`.
  No doc change — `docs/graph-studio.md` already describes the contract.
- **fix(bots): workflow bots show their workflow, not an agent id.** The bot
  Overview and Capabilities sections display the linked workflow name (or id)
  for an `execute_workflow` bot instead of the irrelevant default agent.
  No doc change — the workflow-bot behaviour is already documented in
  `docs/graph-studio.md`.
- **feat(bots): use a saved workflow as the brain of a bot.** The New-bot dialog
  gained a **Brain** choice (Agent / Workflow) and a saved-workflow picker. A
  workflow bot answers chat turns by running its graph with
  `runInput = { message, botId, context }` and replying with the terminal output
  (string or pretty JSON). Scheduled workflow bots use the automation
  `execute_workflow` action with `action.config.graphWorkflowId`; because the
  Python runtime cannot read JDDS, the dispatcher starts the run through the
  front door (`/api/workflows/{id}/runs`) and polls `/api/graph-runs/{id}` to a
  terminal state. Both paths stay in the read-only TEST envelope. A workflow that
  is a bot shows that bot's avatar in the Graph Studio header and a **Workflow**
  badge in chat.
- **fix(graph/ui): Ctrl+Tab add-node shortcut and calmer add-node affordances.**
  The canvas add-node shortcut and its hint are now `Ctrl/Cmd+Tab` (plain Tab
  did not fire reliably), and the small `+` on a node output is a larger neutral
  frosted button instead of a tiny accent circle.
  Docs updated: `docs/graph-studio.md`, `docs/harness/automation-engine.md`,
  `docs/NAVIGATION.md`, `docs/CHANGELOG.md`.

## Rotation policy

This file keeps a rolling window of the **most recent 7 dated sections** (the active window). Older dated sections are **moved** - never deleted - into monthly archive files under `docs/changelog/YYYY-MM.md`. New entries are appended under the current date; the commit-msg hook checks this path. Rotation is by hand only when this file grows unwieldy; the archive link below points at where the older entries went.

> Older entries are archived under `docs/changelog/` (monthly). The most recent 7 dated sections are kept here.

## 2026-10-30
- **fix(graph): production hardening for schedules + a stable perf guard.** A
  schedule linked to a `trigger.schedule` node is now paused (with a visible
  reason) on the next tick if that node no longer exists in the persisted
  workflow, so deleting a trigger cannot leave an orphaned schedule firing the
  graph. Added coverage for the deleted-node and still-present-node paths. The
  observability span-overhead perf test now measures the **median of five warmed
  batches** instead of one run, so a scheduling hiccup under load cannot fail a
  guard that still requires < 1 ms per span.
  Docs updated: `docs/graph-studio.md`, `docs/CHANGELOG.md`.
- **feat(graph): schedule details directly on the Schedule node.** The
  `trigger.schedule` card now shows an Active/Paused dot, a human schedule
  summary (`Weekdays at 09:00 · Asia/Karachi`), the next fire in the schedule's
  timezone, and the last error when a fire fails; a node with no linked schedule
  says so. The canvas loads schedules for the open workflow, refreshes after any
  schedule mutation (a small `eclipse:schedules-changed` event) and once a minute
  as the tick advances `nextRunAt`. The Schedule tab remains the editor.
  Docs updated: `docs/graph-studio.md`, `docs/CHANGELOG.md`.
- **fix(graph): black in-node input wells + double-click for details.** Inline
  text/number/select/JSON widgets use the original black field fill again
  (`bg-background/60`) while keeping the compact 28px rows and borders. A single
  click on a node now only selects it, so clicking into a widget never opens the
  right inspector; double-click opens the inspector as the shortcuts panel
  already documented. Widgets stop double-click propagation, so editing a value
  cannot accidentally open the panel.
  Docs updated: `docs/graph-studio.md`, `docs/CHANGELOG.md`.
- **style(graph): compact two-column node controls.** Inline parameters are now
  Blender-style rows — small label on the left, widget on the right — instead of
  stacked labels, which had made the cards tall and cramped. JSON parameters use
  a single-line value box on the card (the inspector keeps the full editor), and
  node width is 264 px so labels and dropdowns fit. No doc change — visual
  refinement of the in-node controls.
- **style(ui): filled Test glyph, lock for the broker, broom for “Tidy up”, and
  a calmer Add-node control.** The node hover Test button uses Phosphor's filled
  Play glyph (still a neutral solid-grey button). The sidebar broker launcher now
  uses the shared Lock icon so it matches the other sidebar icons instead of a
  brand mark. The graph canvas “Tidy up layout” action (toolbar and context menu)
  uses the Phosphor Broom icon. The canvas **Add node** affordance is now a
  frosted control with a neutral plus tile, the label and a `Tab` key hint —
  no green pill — and the empty-state “Add first step” uses the same treatment.
  No doc change — visual identity only.
- **style(graph): neutral solid-grey Test button.** The node hover toolbar's
  Test play button now uses the solid `muted` surface with a neutral foreground
  hover instead of green; the result dots keep their semantic colours.
  No doc change — visual tweak.
- **feat(graph): Blender/ComfyUI-style controls inside every node + one-click
  node Test.** Parameters are edited directly on the node: two priority fields
  always visible, a “+N more parameters” toggle expands the rest in place
  (Show less collapses). Number fields are drag-to-scrub widgets (Shift fine,
  Ctrl/Cmd coarse, click to type), selects are dropdowns, booleans are
  checkboxes, text is an input and JSON is a compact textarea. Every control
  dispatches the same `update_node_config` patch as the inspector; clicking the
  node still opens the full advanced inspector. `ConfigFieldDef.quick` chooses
  the two priority slots (logic.condition now surfaces compareTo,
  agent.research surfaces agent). The hover toolbar's play button — next to
  Duplicate — runs the node; the result renders inside the node body with
  running/succeeded/failed, duration, error and an expandable output preview.
  Side-effecting nodes show a lock and require an authorized run. Test state is
  ephemeral and nothing is persisted. Registry-driven, so it covers every node
  type without per-node UI code.
  Docs updated: `docs/graph-studio.md`, `docs/CHANGELOG.md`.
- **fix(graph): schedule triggers now have real time controls and cannot
  double-fire.** `trigger.schedule` is zero-config; its cron/timezone/enabled
  state is a `WorkflowSchedule` linked by a new `nodeId` column (Prisma db push),
  edited in the node inspector's **Schedule** tab: repeat presets, a time picker,
  weekday chips, IANA timezone select, catch-up policy, version pin, next-three-
  fires preview, Run now, pause and delete. The 60 s ticker now starts early in
  the boot pipeline, holds a process-level overlap lock, and **claims each due
  fire atomically** (compare-and-set on `nextRunAt`) so two ticks/processes
  cannot start the same run; missed fires keep the skip/coalesce policy and a
  later tick reconciles `lastStatus` from the run instead of leaving it at
  `started`. Zone names are validated with a clear error. Schedules still run in
  the read-only test envelope (the UI says so) and only while the server is up.
  Docs updated: `docs/graph-studio.md`, `docs/CHANGELOG.md`.
- **feat(graph): zero-config manual trigger + per-node Test panel.** `trigger.manual`
  now has no config fields, like n8n: `Start` is the one-off run input (Execution
  dock or webhook body) or null; stored defaults belong in `data.value` /
  `data.set_variables`. Legacy `seed`/`payload` keys in already-saved graphs are
  still honoured at runtime but are no longer declared or shown, and the starter
  templates were moved onto visible data-node defaults. The inspector gained a
  **Test** tab that executes a single node through the new
  `POST /api/graph-runs/node-test` → Python `POST /graphs/nodes/test` surface:
  explicit per-port inputs, re-validated config, the node's hard timeout, and a
  safe envelope that refuses network/write/trading/model nodes (403). Tests cover
  the zero-config trigger, node tests, input validation and the safe envelope.
  Docs updated: `docs/graph-studio.md`, `docs/CHANGELOG.md`.
- **feat(graph): n8n-style manual trigger — payload, run input and webhook body.**
  `trigger.manual` now has a `payload` (any JSON) plus `payloadType`
  (`auto`/`string`/`number`/`boolean`/`object`/`array`) in addition to the legacy
  `seed`; the executor resolves Start as run input → payload → seed → null, so
  existing graphs are unchanged. The runs route and the webhook-style trigger
  route now accept a bounded (64 KiB) `runInput` (webhook: the request body) and
  forward it to the Python runtime, which already supported it. The Execution
  dock gained a **Run input** JSON editor (one run only, never persisted), and the
  inspector shows Payload/Payload type with help text. Registry parity kept in
  both languages; `config_fields` gained an `any` kind for JSON values.
  Docs updated: `docs/graph-studio.md`, `docs/CHANGELOG.md`.
- **fix(ui): provider logos replace the sparkle in the model picker.** The
  composer's model selector and the Provider submenu now show the actual
  provider's brand mark (OpenAI, Anthropic, Gemini, Mistral, DeepSeek, Groq,
  Ollama, LM Studio, xAI, OpenRouter, Perplexity, Together, Fireworks, OpenCode,
  or the Eclipse mark) instead of the generic sparkle; unknown/custom providers
  get a neutral CPU glyph. Marks are vendored under `public/providers/` and
  rendered as a `currentColor` mask so they work in both themes and never call
  a CDN. The Manage-models dialog header shows the provider's mark too.
  No doc change — visual identity only.
- **feat(voice): dictation — speak prompts into the composer.** The dead mic in
  both composers is now a real voice-input control: Whisper through an
  OpenAI-compatible `/audio/transcriptions` endpoint (OpenAI, Groq, or a keyless
  local whisper.cpp server), with browser SpeechRecognition as the zero-config
  fallback. Audio is bounded, validated, transcribed once and discarded — never
  stored or logged — and the transcript is inserted at the caret without
  replacing typed text. Settings › Voice gained engine/language/vocabulary/max
  length/provider config plus an honest readiness report. A new Settings › Voice
  provider readiness route (`/api/voice/config`), transcription front door
  (`/api/voice/transcribe`), Python `/voice/transcribe` runtime route, and the
  optional `TRANSCRIBE_API_KEY` vault entry keep the key server-side.
  Docs updated: `docs/voice.md`, `docs/NAVIGATION.md`, `docs/ARCHITECTURE.md`.
- **feat(graph): n8n-style node parameter editing.** A single click now opens the
  inspector (drag still moves the node). The Parameters tab shows the node
  description/docs, friendly labels, one-line help, required markers, and an
  “Advanced: edit config as JSON” editor for any field the form does not expose.
  The Settings tab gained saved node **Notes** (`update_node_notes`; notes are
  copied on duplicate/paste and never executed). Added shared help text and
  required-field metadata in `config-fields.ts`.
  Docs updated: `docs/graph-studio.md`, `docs/CHANGELOG.md`.
- **test(graph): verified `trading.broker_order` on a real MT5 demo fill.** A
  graph `trigger → data.value(intent) → trading.broker_order → result` submitted
  a 0.01 lot EURUSD buy (SL 1.11000, TP 1.12500) under a one-order demo mandate:
  ticket `11183814415` filled at 1.11676, then closed/verified at 1.11677
  (`positions=0`). A first attempt without a stop was correctly refused by the
  connection's 0.5% risk-per-trade policy, proving the preflight gate. The
  configured connection is a demo account, so the live two-key path still needs
  an armed live connection to be exercised.
  no doc change — verification run; no contract changed.

- **feat(graph): MT5 live execution under a workflow-pinned mandate.** Phase 6
  adds LIVE broker nodes: `trading.broker_order` (armed live connection + live
  mandate; a mandate replaces the per-order typed phrase), read nodes
  `broker_account` / `broker_quote` / `broker_bars`, and risk-reducing
  `broker_close` / `broker_modify` / `broker_cancel` (no arm/approval/mandate).
  Live mandates pin `workflowId@version`, are capped at a 24 h TTL and require
  the connection arm before creation; `RunGrants`/`RunRequest`/the front door
  carry `allowLiveTrading`, the compiler refuses paper-only nodes in live mode
  and requires pinned `connectionId`/`mandateId`, and the execution context now
  carries the workflow id for the mandate check. The editor gained a broker
  connection/mandate picker and the Settings mandate form supports live + a
  workflow pin. Tests: live mandate/submit, pinned workflow mismatch, compiler
  live grant. Docs updated: `docs/trading.md`, `docs/graph-studio.md`,
  `docs/CHANGELOG.md`.
- **feat(graph): scoped external file writes.** Added `file.write` (Phase 5):
  a named operator-configured scope (`HARNESS_GRAPH_WRITE_ROOTS`, default
  `workspace` → `.black-eclipse/workspace`), relative paths only, `..`/absolute/
  symlink escapes refused, 8 MB cap, atomic replacement or append. A test run
  never writes; an operator run is granted only the exact scopes it confirms
  (`allowedWriteScopes`, carried through the front door to `RunGrants`). The
  authorization dialog lists the scopes; the editor marks file writes as an
  effect. Tests: node confinement/caps, compiler envelope, TS authorization.
  Docs updated: `docs/graph-studio.md`, `docs/CHANGELOG.md`.
- **feat(graph): bounded loop nodes.** Added `flow.for_each`, `flow.repeat` and
  `flow.while`: a pinned body workflow run under a hard `maxIterations`/`count`
  and optional `maxDurationMs` cap. The compiler still refuses graph cycles; a
  loop is an orchestrated node. Each iteration is a durable child run
  (`<parent>:<node>:i<N>`) and doubles as its checkpoint — a resumed parent
  reuses a succeeded iteration. `flow.while` evaluates the safe formula language
  over `value`/`index`/`iterations`; `flow.for_each` can continue on a failed
  item and records the error in `results`. The editor treats loop bodies like
  subworkflows (pinned workflow picker) and the front-door bundle walks them.
  Tests: compile/execute/cap/reuse and parity.
  Docs updated: `docs/graph-studio.md`, `docs/CHANGELOG.md`.
- **feat(graph): resumable agent runs.** Durable graph jobs now persist the
  front-door callback URL and re-resolve model credentials on resume through the
  operator-gated `POST /api/graph-runs/{id}/credentials` route — the key is held
  in worker memory only, never in the job payload. The agent adapter re-enters
  the same agent-plane run when a durable checkpoint exists
  (`agent_run_identity`), so a crashed turn continues instead of replaying; a
  run without a checkpoint restarts under a fresh id (model calls have no world
  effect). Added credential-resolution and identity tests. Docs updated:
  `docs/graph-studio.md`, `docs/CHANGELOG.md`.
- **feat(graph): dry-run agent nodes in a test run.** Added the `model` side
  effect (tokens, not a world effect), separate from `network`. Agent nodes are
  now `model`, so a test/dry run may execute them; the front door resolves model
  credentials for any graph with `agent.run`, and the runtime narrows the agent's
  declared allowlist DOWN to `DRY_RUN_TOOLS` (read-only finance, local evidence,
  response helpers) — web, browser, MCP, plugins, code and broker tools are
  removed. Operator runs keep the preset's surface. Added `requiresModel` /
  `modelNodes` to run authorization and the dialog, plus dry-run surface tests.
  Docs updated: `docs/graph-studio.md`, `docs/CHANGELOG.md`.
- **feat(graph): operator-authored agent presets from Settings.** New Settings ›
  Agents CRUD for a custom agent preset (prompt, max steps, explicit tool
  allowlist, MCP/plugin expansion). Presets live on `agent-memory.db` in
  `AgentPreset` + immutable `AgentPresetVersion`; every edit appends a version
  and an agent node pins `agent@version`. Tool names are validated against the
  live registry and a write/external tool requires the explicit “Allow effectful
  tools” acknowledgement. The Next front door is a thin proxy; the runtime owns
  resolution. Agent nodes gained `agentVersion` and the inspector gained a
  built-in/custom picker; the manifest was regenerated.
  Docs updated: `docs/graph-studio.md`, `docs/harness/decisions.md`
  (ADR-H342), `docs/CHANGELOG.md`.
- **fix(docs): rotate-changelog archives the oldest sections, not the newest.**
  The script read the newest-first file backwards (`marks[length - KEEP]`) and
  sliced the archive block with a dead identity check, so `--write` moved the
  newest section out and dropped the older ones. It now keeps the first 7
  newest sections and archives the contiguous oldest tail; 2026-10-23 moved to
  `docs/changelog/2026-10.md`.
  Docs updated: `docs/CHANGELOG.md`, `docs/changelog/2026-10.md`.
- **fix(graph): record the repro + root cause for failing agent nodes.** A
  trigger → `agent.research` → result graph run as an operator run returns a
  complete answer from the agent plane but the node is marked failed with
  `agent run completed: <output>`; downstream nodes are skipped. Cause: the
  bootstrap adapter accepts only `succeeded` while the run plane's terminal
  success status is `completed` (`RunStatus` in `python/harness/schemas.py`).
  Also found adjacent defects: run history is keyed by `ir.id` while the API
  lists by the JDDS row id, and subworkflow bundles fail the same identity
  equality check. Analysis only, no code changed in this pass.
  no doc change — investigation for a fix plan; `docs/graph-studio.md` will be
  updated with the fix, not the audit.
- **fix(graph): make agent nodes and run history work.** Extracted the agent
  result projection into `agent_nodes.agent_result_payload`, which now accepts
  the run plane's `completed` terminal status as success (and `failed`/
  `cancelled` report their own message, not the transcript). Run dispatch now
  aligns the IR id to the persisted JDDS workflow id (and bundled subworkflow
  IRs to their pinned row ids), so `/api/workflows/[id]/runs` and nested runs
  share one identity. `agent.research.query` / `agent.plan.objective` are
  optional ports backed by a compile-time "wire or config objective" rule, and
  the canvas "From wire" state maps a config field to its real port. The editor
  Start action now opens the authorization dialog for graphs with network /
  trading / write effects instead of firing a test run that must be refused.
  Added agent adapter, config-only objective and every-node-executable tests;
  regenerated `registry.manifest.json`.
  Docs updated: `docs/graph-studio.md`, `docs/CHANGELOG.md`.

## 2026-10-29
- **feat(voice): read assistant replies aloud with browser-native TTS.** Added a
  Speak/Stop control to the chat footer, structured-response header and bot
  messages, plus a Settings › Voice pane (voice, rate, pitch, volume, opt-in
  auto-speak). Uses the Web Speech API only — no dependency, key, server
  round-trip or transcript upload; unavailable browsers hide the control and say
  why. `src/lib/tts/text.ts` projects Markdown/structured replies to prose
  (drops code/JSON, keeps link labels, reads tables as rows, strips citations)
  and `speech.ts` chunks utterances and guards cancelled runs. Prefs persist in
  `be_tts_v1`; auto-speak primes on mount so history never replays.
  Docs updated: `docs/voice.md` (new), `docs/ARCHITECTURE.md`,
  `docs/NAVIGATION.md`.
- **feat(trading): reveal the MT5 terminal after a fill.** A successful
  `filled`/`placed` order now focuses the running `terminal64.exe` (or starts the
  connection's `terminalPath`) so the operator sees the position immediately.
  Windows-only and best-effort; it cannot change the order result, is a no-op on
  a container/remote bridge, and can be disabled per connection with
  `openTerminalOnTrade: false`. Docs updated: `docs/trading.md`.
- **ops(deploy): server-side auto-deploy (`scripts/deploy.sh`).** Production had
  no update path beyond a manual pull + rebuild, so a pushed commit never reached
  a running container. The script fetches `origin/main`, exits immediately when
  the commit is unchanged, pulls `--ff-only`, rebuilds the compose image, and
  waits for `/login`; a lock prevents overlapping builds and tracked local edits
  make it refuse. `scripts/install-autodeploy.sh` writes and enables the timer in
  one command. `.github/workflows/deploy.yml` gives an optional push-to-deploy
  path (skips unless deploy secrets are set). Documented a 5-minute systemd timer
  (and cron equivalent).
  Docs updated: `docs/DEPLOYMENT.md` (new "Automatic updates" section).
- **feat(trading): live exits are arm-free; live entries are one-click in chat.**
  A live connection can now close/modify its own positions without an arm (the
  account mode must still match), so an expired arm cannot trap live risk. A live
  close-all is scoped to the connection's magic (the kill-switch boundary); explicit
  tickets can include others. Added a
  chat `TradeApprovalBanner`: `order_preview` leaves a single-use approval, the
  banner shows the exact order, and the operator types the LIVE phrase and clicks
  Confirm & send. The server list view now carries `connectionId`/`intent` so the
  card submits without re-entry. Settings › Broker connection gained an edit/switch
  mode control. Live mandates and Graph Studio live nodes remain out of scope.
  Docs updated: `docs/trading.md`, `docs/DECISIONS.md`, `skills/ARCHITECT.md`
  (ADR-056), `docs/harness/tool-registry.json`.
- **fix(ui): frosted-glass dropdowns in the broker + quick-trade surfaces.** Replaced
  the native `<select>` mode/side/type pickers in Settings › Broker connection, the
  sidebar broker dialog, and the Quick Trade widget with the shared Base UI
  `Select` (`glass-tooltip`). Native OS popups cannot be blurred; the portalled
  select can. No contract change.
  no doc change — visual-only component swap.
- **feat(trading): read-only broker connectivity, attach-first MetaTrader 5.**
  New `python/harness/trade/` package: a `BrokerAdapter` read contract, a kind
  registry with honest dependency availability, a durable
  `BrokerConnection`/`BrokerConnectionEvent` store on `agent-memory.db`, one
  `BrokerService`, and read-only `broker_*` agent tools. The first adapter attaches
  to a running, logged-in MT5 `terminal64.exe` over local IPC and reads account,
  positions, working orders and quotes with named failure codes
  (`PACKAGE_MISSING`, `TERMINAL_NOT_FOUND`, `NOT_LOGGED_IN`, `NO_IPC`, …). Config
  validation refuses password/token-shaped keys at write time; no credential is
  stored and the preferred path needs none. `/trading/*` routes are
  operator-gated; `POST /trading/orders` is an honest 501 and there is no order
  tool. Front door: `src/app/api/trading/[[...path]]/route.ts` + allowlist +
  client. Tests: `python/tests/test_broker_layer.py`,
  `src/lib/harness/trading-routes.test.ts`.
  Docs updated: `docs/trading.md` (new), `docs/ARCHITECTURE.md` (portfolio layer),
  `docs/NAVIGATION.md`, `docs/harness/decisions.md` (ADR-H331).
- **feat(trading): demo order execution via preview → approval → submit.** P1
  adds `TradePolicy` (margin/volume/spread/open-position/allowlist), a
  `trade/authorizer.py` seam that evaluates the order as a `MoneyIntent` through
  the finance guardrails, creates a single-use `trade_order` approval bound to the
  exact `OrderIntent` digest, and consumes it atomically before `order_send`.
  Demo is enforced twice (connection record + `account_info().trade_mode`); live is
  refused with `LIVE_NOT_ENABLED`. MT5 gains `order_preview` (`order_check`),
  `submit_order` and `cancel_order` with retcode mapping, volume/stop/filling
  validation and a `BrokerOrder` ledger; an ambiguous send is `unknown` and never
  retried. Routes: connection-scoped `orders/preview`, `orders/submit`,
  `orders/{ticket}/cancel`, `orders/ledger`, plus trade approvals; the agent gets
  `order_preview`/`order_ledger` only, never submit. Tests:
  `python/tests/test_broker_orders.py`, `test_mt5_adapter.py`,
  `src/lib/harness/trading-routes.test.ts`.
  Docs updated: `docs/trading.md`, `docs/ARCHITECTURE.md`, `docs/NAVIGATION.md`,
  `docs/harness/decisions.md` (ADR-H332).
- **feat(trading): armed live execution and a magic-scoped kill switch.** P2 adds a
  time-boxed per-connection arm (typed `ARM LIVE <login>`, 60 s–8 h) that requires a
  real account, Algo Trading, a non-zero `magic`, and a positive `maxMargin`.
  Every live order still runs through `trade/policy.py`, the money guardrails, and
  the single-use `trade_order` approval, plus a mandatory per-order
  `LIVE <SIDE> <volume> <symbol>` phrase. The arm is cleared by mode/config changes,
  a failed probe, expiry, or the kill switch. `POST .../kill` cancels only working
  orders carrying the connection's magic and disarms; it never closes positions.
  `BrokerConnection` gains `armedUntil`/`armedAt`/`armedBy`; `TradingAdapter` gains
  `cancel_all(magic)`; MT5 gains a magic-filtered cancel-all. Routes: arm/disarm/
  kill. Tests: `test_broker_orders.py` (live arm, phrase, expiry, kill).
  Docs updated: `docs/trading.md`, `docs/ARCHITECTURE.md`, `docs/NAVIGATION.md`,
  `docs/harness/decisions.md` (ADR-H333).
- **feat(graph): demo broker orders under bounded mandates.** P3 adds a
  `TradingMandate` (demo-only; allowed symbols, per-order `maxMargin`, `maxOrders`,
  60 s–7 d expiry; typed `MANDATE DEMO <label>`; atomic usage; immediate revoke) and
  Graph Studio's `trading.broker_order` node. The node is paper-mode only and calls
  the SAME `BrokerService.submit_order` path, so policy, money guardrails, the
  demo/real account check and the no-retry rule still apply; the ledger records
  `mandateId`. Live trading nodes stay refused by the compiler and front door, and
  `create_mandate` refuses a live connection. Routes: mandate create/list/revoke.
  Tests: `test_broker_orders.py` (mandate lifecycle + node),
  `src/lib/graph-studio/run-authorization.test.ts`; `registry.manifest.json`
  regenerated (`npm run graph:manifest`).
  Docs updated: `docs/trading.md`, `docs/ARCHITECTURE.md`, `docs/NAVIGATION.md`,
  `docs/graph-studio.md`, `docs/harness/decisions.md` (ADR-H334).
- **feat(trading): durable fills/positions/order-state reconciliation.** P4 adds
  `trade/reconcile.py`: `BrokerFill` (deduped by connection + deal ticket),
  `BrokerPositionSnapshot` (atomic replace) and `BrokerSyncState` on
  `agent-memory.db`. A sync reads broker positions/working orders/deal history,
  updates in-flight ledger orders only from definitive history states, and records
  `error`/`unavailable` on failure without deleting the last good data. The
  background `ReconcilerLoop` is opt-in (`TRADING_RECONCILE_SECONDS`, default 0);
  manual `POST .../sync` always works. MT5 gains `deals_since`/`order_status`;
  routes for sync/reconciliation/fills; read-only `broker_reconciliation`/
  `broker_fills` tools. Tests: `python/tests/test_broker_reconcile.py`.
  Docs updated: `docs/trading.md`, `docs/ARCHITECTURE.md`, `docs/NAVIGATION.md`,
  `docs/harness/decisions.md` (ADR-H335), `.env.example`.
- **chore(trading): pin the MetaTrader 5 bridge for Windows x64.** `MetaTrader5`
  is now in `python/requirements.txt` with a `win32` + `AMD64` marker, so the
  runtime install keeps the bridge while Linux/macOS installs are unchanged. The
  terminal remains a separate operator install. Verified an attach to a local demo
  terminal (account/positions/quote reads + a reconciliation sync).
  Docs updated: `docs/trading.md`.
- **feat(settings): Trading › brokers panel.** Adds a Settings surface for
  connecting a MetaTrader 5 terminal, probing it, showing the account (login,
  balance/equity, margin, leverage, demo/real), sync/test/remove, and live
  arm/disarm/kill controls. It never places an order; orders stay on the existing
  operator routes, Graph Studio and the API. Wired into `settings.tsx` as the
  `trading` section.
  Docs updated: `docs/trading.md`, `docs/NAVIGATION.md`.
- **feat(dashboard): live MT5 trading widgets.** The five `trading` widgets are no
  longer `UNAVAILABLE` stubs. Quick Trade (preview → approve → submit, with the
  guardrail phrase), Open Positions, Working Orders (cancel), Margin Usage and
  Today P&L read the first saved broker connection and poll every 15 s. A missing
  connection renders a Settings → Broker connection setup note; every empty/error state is
  explicit and no number is fabricated. New `src/lib/dashboard/trading-widgets.tsx`,
  registered in `registry.tsx`.
  Docs updated: `docs/trading.md`, `docs/ARCHITECTURE.md`, `docs/NAVIGATION.md`.
- **feat(shell): broker connection button next to Gateway/Graph.** Moves the
  MT5 entry point into the sidebar's quick-launcher row (handshake icon, with a
  status dot and an **MT5** badge in the popup) and keeps it in the collapsed
  footer. The popup now uses the same
  `rounded-2xl border border-white/10 glass-card-strong` recipe as the
  Gateway/Graph dialogs, and reads the connection's stored account snapshot
  immediately instead of blocking on a live read. No orders are placed from the
  dialog. New `src/components/layout/sidebar-broker-dialog.tsx`; wired in
  `sidebar.tsx`; `Handshake` added to the central icon set.
  Docs updated: `docs/trading.md`.
- **style(shell): widen the broker connection popup.** `sm:max-w-md` → `sm:max-w-lg`
  (448 → 512 px) so the two-column connection form and account figures have room.
  no doc change — presentation-only, no contract or setup change.
- **style(settings): use the handshake for the Broker connection section.** The Settings rail
  entry and the Broker connection panel header now use the same `Handshake` icon as the
  sidebar broker button, instead of the MCP-looking plug.
  no doc change — presentation-only.
- **fix(trading): preview refusals are outcomes; MT5 sessions are serialized.** A
  blocked preview now returns `allowed:false` + `error.code`
  (`ALGO_TRADING_DISABLED`, `DEMO_ACCOUNT_REQUIRED`, `LIVE_NOT_ARMED`, …) instead of
  raising, and the front door preserves the runtime status instead of mapping 403
  to 502. The `order_preview` tool text names the code; `broker_account` includes
  margin mode/flags; `broker_quote` includes digits, point, volume step/min/max and
  stops level; `broker_positions` includes SL/TP. MT5 `initialize`/`shutdown` is
  guarded by a process-wide lock so concurrent agent tool calls cannot collide.
  Tests: `test_broker_orders.py` updated.
  Docs updated: `docs/trading.md`.
- **fix(reconciliation): server-time-safe deal window.** `history_deals_get`
  expects server time; the local clock was 2h behind the demo server, so the newest
  deal was outside the query window and a real fill produced `fillsAdded: 0`. Sync
  now queries 7 days back with a 2-day future margin and relies on deal-ticket
  dedupe; the cursor is advisory. Verified with a real demo fill (0.01 EURUSD,
  ticket 11164486049): `fillsAdded: 1`, position and ledger reconciled.
  Docs updated: `docs/trading.md`.
- **feat(trading): `order_submit` may omit the mandate id when exactly one is active.**
  The agent resolves the sole active demo mandate; with several active mandates it
  must name one from `broker_mandates` (or the handler returns the available ids).
  Docs updated: `docs/trading.md`.
- **feat(trading): agent-driven demo execution under a mandate.** Adds
  `order_submit` (the one effectful agent broker tool) and `broker_mandates`, plus
  a Settings panel to create/revoke bounded demo mandates. `order_submit` is
  admitted by an active mandate, not the generic approval card, and still runs the
  SAME service path (demo account check, policy, money guardrails, symbol/margin
  cap, order count). Live remains unreachable. Prompt guidance: keep analysis
  brief, call `order_submit` directly. Verified end-to-end: Eclipse analyzed
  EURUSD and filled **ticket 11164809214** (BUY 0.01, SL 1.11125, TP 1.12260)
  under mandate `mnd_c82ba003d785`; two earlier demo tickets were also filled.
  Tests: `test_broker_agent_trade.py`, updated broker tool test.
  Docs updated: `docs/trading.md`, `docs/NAVIGATION.md`,
  `docs/harness/decisions.md` (ADR-H336).
- **fix(trading): subscribe an unlisted symbol on demand.** `XAUUSD` existed on
  the demo but returned an all-zero tick until it was in Market Watch; the adapter
  now calls `symbol_select` and retries the tick for up to ~2 s (a local
  subscription, not an order). Verified live: XAUUSD bid 4010.87 / ask 4011.16,
  spread 29 points, 0.01–100 lots. Docs updated: `docs/trading.md`.
- **fix(trading): a plain "analyze gold and place a trade" prompt now executes.** Three
  fixes for a user who never types a mandate id: (1) `order_submit` and its
  authorizer resolve the one active mandate whose symbols cover the intent symbol
  (the sole active mandate when it is the only one) and the only saved connection,
  returning `MANDATE_REQUIRED` with the active ids only on real ambiguity;
  (2) `graph.py` adds a per-run `# Trading request` block when the turn asks to
  place/buy/sell an order — skip web/news/scrape, read the quote (plus at most one
  bar source), call `order_submit` once, never ask for ids — while a refusal or a
  question keeps the block out; (3) the mandate cap now sees the order's own margin
  (`order_check().margin − account.margin`, floored at zero) instead of the
  account total after the trade, which had refused a valid 0.01 XAUUSD lot at
  113.74 vs a 100 cap when it only needed 40.00. Verified live with the bare prompt
  “Analyze XAUUSD and place a small demo trade with a stop loss and take profit”:
  4 model steps, one `order_submit`, ticket **11165187813** (XAUUSD BUY 0.01 @
  4014.13, SL 3988.99, TP 4063.99) under mandate `mnd_c405bf889119`. Tests:
  `test_trading_intent.py` (new), `test_broker_agent_trade.py`,
  `test_mt5_adapter.py`. Docs updated: `docs/trading.md`.
- **feat(trading): close a demo position (or every one) so a user can step out.**
  Adds `TradingAdapter.close_position` (MT5 sends the exact opposite market deal,
  position ticket as `position`, position magic, once, ambiguity reported not
  retried), `BrokerService.close_position` / `close_positions`, routes
  `POST .../positions/{ticket}/close` and `POST .../positions/close`, the agent tool
  `position_close` (`ticket`, `tickets` or `all: true`), and Close / Close-all in the
  Open Positions dashboard widget (both confirm first). Closing is risk-reducing, so
  it needs no mandate and no approval and does not consume a mandate order; the
  service refuses a live connection (`LIVE_NOT_ENABLED`) and a real account
  (`DEMO_ACCOUNT_REQUIRED`). The per-run trading directive now has a
  `# Close request` variant (`python/harness/trading_intent.py`, extracted from
  `graph.py`) so “close my trade” never turns into research or a hedge. Tests:
  `test_broker_orders.py` (close one/all/targeted/live-refused),
  `test_broker_agent_trade.py` (no mandate, target required),
  `test_trading_intent.py`, `trading-routes.test.ts`. Regenerated
  `docs/harness/tool-registry.json` (981 tools) and the graph manifest; re-pinned
  the `graph.py`/`service.py` and prompt-size ceilings to their measured values.
  Docs updated: `docs/trading.md`, `docs/harness/decisions.md` (ADR-H337).
- **fix(trading): a stale/missing connection id no longer hides a valid mandate.**
  A remembered `connectionId` from another profile or database made the mandate
  list for that id empty, so `order_submit` answered "no active mandate" on an
  account that had one. Both the handler and the authorizer now drop an id that is
  not a saved connection and resolve the single existing one (they still refuse
  when several exist). Verified with the bare prompt “Analyze gold and place a
  small demo trade with a stop loss and take profit”: one `order_submit`, ticket
  **11165863645** (XAUUSD BUY 0.01 @ 4031.99, SL 4007.30, TP 4057.30). Tests:
  `test_broker_agent_trade.py` (stale id resolves; unknown id with two connections
  still refuses). Docs updated: `docs/trading.md`.
- **feat(trading): broker-native bars and ATR for uncovered symbols.** Adds
  `broker_bars` (and the `TradingAdapter.bars` / `BrokerService.bars` seam): MT5
  `copy_rates_from_pos` on `M1…W1`, clamped to 500 bars, server time, with the
  symbol's contract/tick size; a pure `trade/analysis.py` computes TR/ATR(14) and
  the 20-bar range. This replaces the proxy-ETF workaround for XAUUSD, whose
  history route returns `UNAVAILABLE`. Quote now also exposes `contractSize` and
  `tickSize`, so "$ at risk" is exact. The per-run directive and the system prompt
  prefer `broker_bars` for a broker symbol. Fixed the advisory gate's table-row
  false positive (`| Take profit | … |` became a "sell" claim) and its indicator
  acronyms (`ATR`, `SL`, `TP`, …). Verified live: XAUUSD H1 120 bars, contract
  100, ATR(14) 14.82; the bare prompt filled ticket **11166047327** (BUY 0.01 @
  4025.10, SL 4003.50 ≈ 1.46 ATR, TP 4055.00 ≈ 2.02 ATR) under mandate
  `mnd_dc9477f30067`. Tests: `test_analysis.py` (new), `test_mt5_adapter.py`,
  `test_advisory_gate.py`. Regenerated the graph manifest and tool registry (982
  tools); re-pinned the prompt ceiling to its measured size.
  Docs updated: `docs/trading.md`.
- **feat(trading): partial close, SL/TP modify, and read-back verification.** Adds
  `position_modify` (`TRADE_ACTION_SLTP`, 0 removes a level), a `volume` on
  `position_close` for partial exits, close-by-`symbol`, and a `verified` flag on
  every close/modify/market fill: the broker's stored position is read back and a
  mismatch is reported (`verifyNote`), never assumed. The lifecycle moved to a new
  `trade/positions.py` (the broker service was at its size ceiling) and keeps the
  identical demo-only rule: no live connection (`LIVE_NOT_ENABLED`), no real account
  (`DEMO_ACCOUNT_REQUIRED`), no mandate or approval for an exit. Adds routes
  `.../positions/{ticket}/modify` and `volume` on close, the client calls, the
  authorizer admission, and per-run `# Modify request` / partial-close guidance; the
  positions text now includes the ticket. Verified live on ticket 11166047327: TP
  moved to 4060.00, SL to 4010.00, both read back as stored. Tests:
  `test_broker_orders.py` (partial, modify, live refusal, invalid stops),
  `test_broker_agent_trade.py`, `test_trading_intent.py`, `trading-routes.test.ts`.
  Ratcheted `trade/adapters/mt5.py` (bars + lifecycle in one wire bridge; split
  candidate), regenerated registry (983 tools) and manifest, re-pinned the prompt
  ceiling. Docs updated: `docs/trading.md`, `docs/harness/decisions.md` (ADR-H339).
- **feat(trading): risk engine on the connection (per-trade risk, notional, 24 h
  brake).** Adds `riskPerTradePct`, `maxDailyLossPct` and `maxSymbolNotional` to
  the connection config (0 = off). Per-trade risk is `|entry − stop| × volume ×
  contractSize` against a percentage of equity; with the cap set, an order without
  a stop is refused. The daily brake sums the broker's realised deals over 24 h
  and open P&L, blocks new entries and never blocks a close. A per-order symbol
  notional cap and the existing spread/open-position caps round it out. Settings →
  Broker connection gains a **Risk limits** editor. Verified live: at 0.02% a 0.01
  XAUUSD order with a 100-point stop was refused (121.76 risk vs a 20.00 cap); at
  0.5% with a 120-point spread cap the shape previews as allowed. Tests:
  `test_trade_policy.py` (new), `test_broker_orders.py`. Docs updated:
  `docs/trading.md`, `docs/harness/decisions.md` (ADR-H340).
- **test(trading): a scripted MT5 terminal and wire-level chaos tests.** New
  `python/tests/mt5_sim.py` implements the adapter's slice of the MetaTrader API
  (account/symbols/ticks/positions/orders/`order_check`/`order_send`/deals/bars)
  with knobs for a lost send reply, a disconnected terminal, a dropped bracket, a
  partial fill and a modify the broker accepts but does not store. New
  `test_mt5_simulated.py` proves: a fill is verified against the stored bracket; a
  dropped stop is `verified:false` with a `verifyNote`; a lost reply raises and is
  **not retried**; a disconnect is a named error; a partial close reports the
  remaining volume; an ignored modify is unverified; bars normalize; deals read.
  This closes the gap between request-builder unit tests and a live terminal.
  no doc change — test-only (no contract or setup change).
- **feat(chat): a trade turn binds the trade surface, not ~700 tools.** A run whose
  prompt is a trade/close/modify request now narrows policy's allowlist to
  `TRADE_SURFACE_TOOLS` (~18 broker/trade + response helpers). It runs after
  surface resolution and can only remove; a run without an effect tool is
  untouched. Measured live on a refused gold order: `allowedTools` 721 → **18**,
  prompt tokens **47k** for 3 steps instead of ~228k, with exactly
  `broker_quote` → `broker_bars` → `order_submit`. Tests:
  `test_trading_intent.py`. Docs updated: `docs/trading.md`.
- **feat(dashboard): modify/partial close and a Recent Trades card.** The Open
  Positions widget now shows each ticket, an **SL/TP** action (prompts for the new
  levels, calls `positions/{ticket}/modify`) and a **Close** action that accepts a
  partial volume; an inline notice reports the verified result. A new
  **Recent Trades** widget reads the ledger (`orders/ledger`) and lists the last
  eight orders with ticket, fill and status. TypeScript clean; dashboard
  registry/size tests pass. Docs updated: `docs/trading.md`.
- **feat(trading): the sidebar broker popup becomes a full control center.** The
  handshake popup now has a connection switcher and five tabs. **Overview** shows
  every live `BrokerAccount` field (used/free margin, margin level, floating P/L,
  leverage, margin mode, trade/algo flags), bridge health, connection timestamps
  and a bid/ask quote lookup. **Positions** closes one or all positions;
  **Orders** cancels a working ticket; **Activity** lists broker deals with an
  `eclipse`/`manual` owner badge plus the Eclipse order ledger. **Settings**
  edits label/mode/terminal path/magic/max-margin, carries the typed **arm**,
  **disarm** and **kill switch** controls for live connections, and adds/removes
  connections. All calls reuse `src/lib/harness/trading-client.ts`; no new
  routes. Presentational panels split into
  `src/components/layout/sidebar-broker-panels.tsx`. The popup still cannot place
  an entry order, and mandates/approvals stay in Settings. Tests: `npm run test`
  (425 files / 4094) + `npx tsc --noEmit` + broker Python tests (56) pass.
  Docs updated: `docs/trading.md`.
- **perf(settings): the Settings modal opens instantly.** Three changes remove the
  cold-open wait. (1) The shell no longer blocks on a full skeleton: it paints the
  real nav + section immediately with the last-known snapshot and shows a slim
  "Loading settings…" line while `/api/settings` revalidates. (2) A new
  dependency-free `src/lib/settings-cache.ts` persists the non-secret payload
  (`hasApiKey` only, never a key) to localStorage, so even a fresh page load has
  values before the request starts; `src/hooks/use-settings-prefetch.ts` fetches
  them 2.5 s after first paint and warms the lazy Settings chunk on gear
  hover/focus or after 12 s (skipped on metered connections). (3) `/api/markets`
  now starts only after the settings read, so JDDS/Prisma work cannot queue
  ahead of the critical path; the Market tab shows "Loading markets…" instead of
  a false empty state. `stock-chat.tsx` stayed at its pinned size budget.
  Docs: no doc change — internal performance/UX only (contracts unchanged).

## 2026-10-28
- **fix(desktop): one launcher at a time, so repeated icon clicks cannot break boot.**
  `scripts/start-desktop.js` now takes an exclusive lock
  (`.black-eclipse/desktop-launcher.lock`, stale locks recovered by PID
  liveness). Before this, clicking the icon again during a cold build started
  another launcher that killed the port and ran its own `next build`; concurrent
  builds rewrote the same `.next` folder, failed with exit 1, and left the
  desktop log spinning for ~18 minutes. Extra clicks now no-op (and reopen the
  tab once the owner is up) instead of starting competing builds.
  Docs updated: `docs/QUICKSTART.md`.
- **fix(modeling): integrated DCF detection, aliases and honest check counts.**
  `integrated` now builds a DCF when `wacc`/`waccInputs`/`dcf.wacc` is present
  (snake_case or camelCase), merges DCF/LBO/comps metadata into the audit summary,
  deduplicates statement checks, counts WARN checks in the audit text, and accepts
  camelCase comps target/peer fields (`netDebt`, `totalDebt`, `sharesOutstanding`,
  `netIncome`). Preservation reports now count targeted parts separately from
  changed/untouched parts.
- **fix(verification): read back generated artifacts and audit values.** Document
  tools accept `artifactId`, so a generated XLSX/PPTX can be opened and queried
  without a filesystem path. `integrated` models now merge DCF/LBO/comps meta, so
  `financial_model_audit` returns `enterpriseValue`/`equityValue`/`valuePerShare`
  etc. instead of only PASS/FAIL. The edit result now spells out “N total /
  M targeted / K untouched” parts so the preservation count cannot be misread.
  Docs: `docs/harness/document-intelligence.md`,
  `docs/harness/financial-modeling.md`.
- **fix(institution): keep the run dialog polling when review queues repairs.**
  `finalize` can return `status: "repairing"` after queueing bounded repairs; the
  dialog now resumes polling instead of stopping on the first terminal task state.
  no doc change — behaviour fix covered by `docs/harness/institution-preset.md`.
- **feat(agents): Institution multi-agent preset (analyst → debate → trader → risk → PM).**
  Added one cast spec in `python/harness/institution/` that materialises into
  `AgentConfig` presets, A2A definitions, a validated `TeamDefinition` task graph
  and Bots-workspace bot specs. The debate produces a structured record (agreement,
  unresolved disagreements, missing facts) and never votes or averages; the
  read-only `read_run_output` tool hands a completed prerequisite memo to the next
  stage by run id. Added `/team/presets*` routes, the `run_team` automation action,
  a Bots-screen run dialog with a live stage timeline, and an idempotent bot seeder.
  Fixed `tasks.manager.recompute_plan` so a multi-level DAG stays `RUNNING` while
  queued work remains instead of being marked `BLOCKED` after its first stage.
  Tests: `test_institution_preset.py` (8), `preset-client.test.ts` (2).
  Docs updated: `docs/harness/institution-preset.md`,
  `docs/harness/bot-team-orchestration.md`, `docs/NAVIGATION.md`,
  `docs/harness/decisions.md` (ADR-H330).
- **feat(hardening): production guards for edits and model builds.** Artifact
  versions now accept `expectedChecksum` and refuse a stale edit with
  `ARTIFACT_CONFLICT`; `document_edit` confines path sources to authorized roots,
  refuses XML DTD/entities (`EDIT_XML_UNSAFE`) and macro packages when policy is
  off (`EDIT_MACRO_REFUSED`), logs `document.edit`, and is idempotent per
  plan/source; `financial_model_build` is idempotent per spec hash/format and
  logs `financial_model.build`; chart data replacement requires an exact series
  count. Docs: `docs/harness/office-edit.md`,
  `docs/harness/financial-modeling.md`, `docs/harness/artifact-center.md`.
- **fix(memory): preference proposals are deduped and never conflict with an active dimension.**
  `preferences.learn` now treats a pending suggestion as already-asked (no
  duplicate on every scan), skips any dimension that already has an active
  preference, and records a gate-staged suggestion exactly once in auto mode.
  Tests cover double-scan dedupe, active-dimension conflict, auto+ask staging,
  and the memory-off floor. Docs updated: `docs/harness/personal-memory.md`.
- **feat(memory): Personal Memory — learned preferences with evidence, not guesses.**
  Added `python/harness/eclipse_memory/preferences.py`: a closed style/format
  vocabulary (answer format, length, tone, research depth), deterministic
  inference with bounded trigger-phrase evidence, and a learner that proposes a
  preference only after 3 consistent observations across 3 distinct runs.
  Migration 34 adds `PreferenceObservation` and `MemorySuggestion.structuredData`;
  proposals stay inert until accepted through the existing suggestion route and
  the ONE memory gate. Dismissals suppress the inference (30-day cooling-off);
  explicit preferences win; memory/preference-learning off collects no evidence;
  secrets and current financial facts are never inferred. Wired into every turn
  and post-run analysis, exposed as `memory action="preferences"`,
  `/eclipse-memory/preferences` + operator-gated `/preferences/learn`, and the
  Eclipse Memory → Preferences tab (pending, remembered, evidence, scan).
  Tests: `test_preference_learning.py` (14), `test_preference_api.py` (3),
  `test_memory_tools.py` preferences surface, and the browser client contract.
  docs updated: `docs/harness/personal-memory.md`, `docs/NAVIGATION.md`,
  `docs/ARCHITECTURE.md`.
- **feat(modeling): mid-year DCF, rollover returns and comps FX/calendarization.**
  `DcfInputs.mid_year` discounts explicit FCF at `t+0.5` (default unchanged);
  LBO management rollover is a separate equity contribution with sponsor/
  management exit split and sponsor-only IRR/MOIC; comps translate non-target
  currencies via `comps.fx`/`fxRate` and calendarize fiscal periods to the target
  year end with an explicit approximate warning. Docs:
  `docs/harness/financial-modeling.md`.
- **feat(documents): structural XLSX edits rewrite references.** Row/column
  insert/delete now rewrites formulas, defined names, merged ranges, conditional
  formats, data validations, hyperlinks, auto-filters and column ranges instead of
  refusing any formula workbook; tables/charts/pivots/OLE are still refused.
  Docs: `docs/harness/office-edit.md`.
- **feat(documents): full structural document edits.** PPTX now has
  `add_smartart_node` / `remove_smartart_node` / `set_smartart_node_text` and
  `set_smartart_layout` (donor diagram in the same deck); structural XLSX edits
  rewrite table/chart references, pivot table locations + cache sources
  (refresh-on-load), and OLE/legacy VML anchors. Docs:
  `docs/harness/office-edit.md`.
- **feat(modeling): exact quarterly comps calendarization.** A peer with
  `quarterly` periods is calendarized by a four-quarter TTM ending at the target
  fiscal year end (`quarterly_ttm`). Incomplete quarterly data now requires an
  explicit `calendarizationFactor`; otherwise the peer is excluded. Docs:
  `docs/harness/financial-modeling.md`.
- **feat(documents): editable PPTX chart data and SmartArt labels.**
  `pptx.replace_chart_data` replaces an embedded chart's categories and series
  caches while preserving chart type, axes and styling; `pptx.replace_text` also
  scans SmartArt diagram data so labels are editable without changing node
  structure. Docs: `docs/harness/office-edit.md`.
- **feat(pdf): optional incremental PDF editing.** When PyMuPDF is installed
  (`python/requirements-pdf-incremental.txt`, optional because AGPL/commercial),
  `document_edit` appends an incremental update and reports
  `preservationMode: "incremental"`; redaction then removes the text objects in
  place (`incremental_true_removal`). Without it, the pypdf rewrite/rasterized
  redaction path is used and labelled honestly. Docs: `docs/harness/office-edit.md`.
- **feat(modeling): comps peer auto-retrieval.** `financial_model_build` accepts
  `comps.peerSymbols` and resolves each through the same read-only
  `market_snapshot` + `financial_statements` bridge as every market tool; a peer
  with no usable price/share count is excluded with a note. Docs:
  `docs/harness/financial-modeling.md`.
- **feat(documents): the edit limits are now features.** Added DOCX image
  insertion and deterministic accept/reject tracked revisions; XLSX
  insert/delete rows and columns (conservatively refused on formula/merge/chart
  sheets rather than breaking references); PPTX slide duplicate/delete with
  relationship + notes remapping; and true PDF redaction that rasterizes the
  page so the covered text object is removed, not just painted over. Docs:
  `docs/harness/office-edit.md`.
- **feat(modeling): reports + LBO leverage.** `financial_model_build` now exports
  PDF/Word/PowerPoint deliverables alongside the workbook; LBO models support
  PIK tranches, a revolver with capacity/rate/minimum cash and a cash sweep that
  preserves the minimum. Docs: `docs/harness/financial-modeling.md`.
- **feat(guardrails): money-movement guardrails + confirm gate.** Added
  `python/harness/finance_guardrails/`: a deterministic, model-free layer that
  normalizes every money-shaped tool call into a `MoneyIntent` and evaluates
  scam/coercion markers (urgency, secrecy, impersonated authority, remote access,
  guaranteed returns, gift cards/wire-only), impaired spending (declared state +
  baseline/escalation signals), crisis mode + panic pause, aggregate
  per-transaction/daily/velocity limits, counterparty allow/block lists and
  novelty. A `confirm`/`escalate` routes the exact intent through the existing
  single-use approval store (`kind="money_guardrail"`, digest-bound) with a
  cooling-off + typed-confirmation challenge; a `deny` is terminal and explained.
  Enforced at the computer finance/click handlers, the browser click handler,
  the shell/terminal authorizer seam and the MCP effect authorizer (before
  grants), so a prompt or standing grant cannot bypass it. Operator routes `/finance-guardrails/*` + Settings › Money
  Guardrails; read-only agent tools `finance_guardrail_status`/`_check`.
  Docs updated: `docs/harness/money-guardrails.md` (new),
  `docs/harness/security.md`, `docs/NAVIGATION.md`, `docs/DECISIONS.md` +
  `skills/ARCHITECT.md` (ADR-055).
- **feat(documents): preservation-first Office/PDF editing.** Added
  `document_edit` (`python/harness/documents/edit/`): a closed `EditPlan`
  (DOCX text/table/core props, XLSX cells/formulas/rows/sheet rename, PPTX
  title/notes/text, PDF forms/rotate/annotate/metadata), an `OoxmlPackage` that
  copies untouched ZIP parts verbatim, `verify_ooxml` proving every non-target
  part is unchanged (and refusing on a relationship/XML/expected-text failure),
  and artifact-version publishing (originals are never edited in place). Adds
  `pypdf` for the PDF rewrite path (honest `PDF_LIBRARY_MISSING` when absent).
  Docs: `docs/harness/office-edit.md`, `docs/NAVIGATION.md`, ADR-054.
- **feat(modeling): deterministic 3-statement/DCF/LBO/comps + Excel model.**
  Added `python/harness/modeling/` and tools `financial_model_build` /
  `financial_model_audit`: validated `ModelSpec`, integrated IS/CF/BS/debt with
  balance and tie checks, DCF composed over `finance_facts.valuation`, LBO
  sources/uses/debt/IRR/MOIC, comps peer multiples/stats/implied ranges, and a
  formula-bearing workbook (Assumptions, Three Statement, Values, Checks).
  Docs: `docs/harness/financial-modeling.md`, `docs/NAVIGATION.md`, ADR-054.
- **feat(ui): crypto alt-data surfaces over the market pack.** Added the
  read-only `GET /api/crypto/alt-data` front door (same TS adapters as the agent,
  30s cache, honest UNAVAILABLE envelope), a `CryptoAltData` panel on Market
  Overview › Crypto (liquidations, long/short, TVL cards), and two catalog
  widgets `crypto-tvl` / `crypto-liquidations` in a dedicated
  `dashboard/crypto-widgets.tsx` (kept separate to respect the source-size
  budget; `market-overview.tsx` stays at its pinned 2760 lines). Docs:
  `docs/harness/market-data.md`.
- **feat(market): CoinGlass + Solscan adapters — the pack is now fully runnable.**
  Added `providers/coinglass.ts` (V4 liquidation coin-list + global long/short
  account ratio, `CG-API-KEY`) and `providers/solscan.ts` (V2 account detail,
  `token` header, Solana lamports). New records `LiquidationStats`/`LongShortRatio`,
  normalizers, gateway methods, and tools `get_liquidations`/`get_long_short_ratio`;
  `get_onchain_metric` now routes `etherscan → solscan` (EVM vs base58 address
  shape decides deterministically). Endpoints verified against official docs
  before implementation. Docs: `docs/harness/market-data.md`, ADR-053 in
  `docs/DECISIONS.md` + `skills/ARCHITECT.md`.
- **feat(market): Hyperliquid read-only perps adapter + hardened POST transport.**
  Added `safePost` to `connectors/security.ts` (https-only, DNS-pinned, timeout,
  response/request-size caps, no redirects) so the GET-only bridge can carry
  Hyperliquid's POST-only `info` endpoint. New `providers/hyperliquid.ts` serves
  perps funding/open-interest (keyless, read-only; funding is hourly and
  annualization stays labelled derived). Hyperliquid is now `implemented=True`;
  funding/OI priority falls back `binance → hyperliquid`. Docs updated:
  `docs/harness/market-data.md`, ADR-053 amendment in `docs/DECISIONS.md` +
  `skills/ARCHITECT.md`.
- **feat(market): crypto/on-chain/alt-data pack — TVL + on-chain capabilities.**
  Added `tvl` and `onchain` capabilities to the market layer with runnable
  DefiLlama (`providers/defillama.ts`, keyless protocol/chain TVL) and Etherscan
  (`providers/etherscan.ts`, keyed EVM account metrics) adapters, new
  `TvlSnapshot`/`OnchainMetric` records, `get_tvl`/`get_onchain_metric` tools, and
  catalogued-only descriptors for CoinGlass/Solscan/Hyperliquid (`implemented=False`,
  so the router never calls a provider without an adapter). Added
  Etherscan/CoinGlass/Solscan vault keys. Why: extend asset-class coverage through
  the ONE router/bridge/quality path instead of a second pipeline, and never fake
  data for sources that are keyed or POST-only. Docs: `docs/harness/market-data.md`,
  `docs/DECISIONS.md` + `skills/ARCHITECT.md` (ADR-053).
- **ui(sidebar): give the app list its own scroll pane while chat history is open.**
  The sidebar's single long scroll is now a fixed control strip (mode switcher
  and launchers) above two independently scrolling panes: a flexible chat
  history pane and a capped Apps strip. A long conversation list can no longer
  push the apps out of reach, and the history list fills its pane instead of a
  fixed `45vh` cap. Files: `src/components/layout/sidebar.tsx`,
  `src/components/layout/chat-history-panel.tsx` (`fill` prop),
  `src/lib/i18n/dictionaries/en.ts` (`sidebar.apps`, ratchet re-pinned).
  no doc change beyond this entry — presentation only; nav contracts unchanged.
- **fix(sidebar): put pages above chat history and stop the app rows shrinking.**
  Corrects the previous layout: on ChatBot only, the app list is the top
  scrollable strip and chat history fills the space below it, separated by a
  divider. Nav anchors are now `shrink-0` (also in `saved-pages-nav.tsx`) so rows
  keep their 32px height and spacing inside a constrained scroll pane instead of
  compressing. no doc change beyond this entry.
- **revert(sidebar): restore the original single-scroll navigation.**
  Reverted the two sidebar layout experiments (the split history/apps panes and
  the Apps strip above them). Chat history sits under the menu again, only on the
  ChatBot tab, in the original one-column scroll. Restored `sidebar.tsx`,
  `chat-history-panel.tsx`, `saved-pages-nav.tsx`, and the `en.ts` /
  `size-budget.test.ts` entries to their pre-change state. no doc change beyond
  this entry.
- **feat(learning): add class-authorized self-modification (Tier B).**
  `self_improvement/self_modification.py` auto-accepts contract-clean,
  evaluated candidates and auto-enables **read-only** learned skills under an
  operator-authored policy (`HARNESS_SELF_MODIFICATION` modes off/accept/enable),
  with TTL expiry, active-skill/daily caps, durable audit rows, revocation and
  pause/run/status routes under `/evolution/self-modification`. Effectful skills,
  tool widening, financial actions and policy edits remain operator-only. Tests:
  `test_self_modification.py`. Docs: `docs/self-improvement/SELF_MODIFICATION.md`.
- **feat(skills): port the Minara catalog into the bundled Eclipse skill library.**
  Added 74 skills under `python/harness/skills/library/<category>/<skill>/`
  (21 finance, 13 external finance references, 3 research, 2 quality, 35 system),
  each with a validated `skill.json` and an Eclipse-specific `SKILL.md` that uses
  only real registered tool names. Read-only analysis skills are enabled;
  execution, publishing, plugin-backed and iOS skills are inert drafts. Trading
  and fund-moving skills stop at an approval-gated plan because `trade.execute`
  is forbidden. Updated the research-category discovery assertion to a subset
  check so new research skills do not make the test brittle. Tests: 121 focused
  skills tests passed; `npx tsc --noEmit` passed. no doc change beyond this entry
  — the new skills are self-describing and registry behavior is unchanged.
- **docs(changelog): restore the 7-section window and normalize one stray CRLF.**
  Moved the oldest dated section (`2026-10-21`) into
  `docs/changelog/2026-10.md`, keeping the newest seven sections, and normalized
  a single CRLF in `docs/harness/roadmap/progress/phase-05-progress.md` so the
  tracked-file line-ending guard passes. no behavioral change.
- **test(harness): re-audit roadmap Phase 5 (coding agent/approvals).**
  Added `test_phase5_audit.py`: code-agent/finance separation, `allowMcpTools`
  false, all 389 `plan_only` tools read-only against the real registry,
  `edit_verify` external-action removal, unknown-autonomy fail-closed, shared
  `claim_guarded`, and `RunLineage` task checkpoints. Targeted gates: 38 passed.
  Correction recorded: the roadmap's literal "finance has no code tool" is stale
  after later phases (`scaffold_kit`, `capability_*`, `python_env_*` are now
  effect/approval-gated); no external code action reaches finance. Docs:
  `docs/harness/roadmap/progress/phase-05-progress.md` and the Phase 5 roadmap
  `last-verified`.
- **test(learning): pin the operator gates.**
  Added `test_learning_gates.py` and an accept-route 403 test: candidate
  acceptance, skill authoring, skill lifecycle writes, and effectful capability
  activation remain operator-gated; the advisory cadence writes only observed
  outcomes. These tests run in the default Python suite. Documentation:
  `docs/self-improvement/GATE_REGRESSION.md`.
- **feat(advisory): explain and honestly backfill legacy debt.**
  `GET /advisory/legacy` reports why each legacy recommendation is unscorable
  (`no_horizon`, `no_entry_price`, `no_symbol`, `no_method`).
  `POST /advisory/backfill-entry-prices` (operator-gated, dry-run first) fetches
  a real historical bar at the decision's creation time and stores it with
  source/as-of provenance; a missing bar is a named skip, and existing prices
  are never overwritten; dry-run is the default and applying requires an
  explicit `dryRun:false`. The live 14 legacy rows stay unscorable (no horizon,
  no price, non-tradable symbols). Tests: `test_advisory_backfill.py`.
- **feat(advisory): add a bounded unattended outcome-scoring cadence.**
  `advisory/cadence.py` scores due, priced recommendations on an interval,
  skips no-price/not-due rows with named counts, makes no market request when
  nothing is due, and is disabled by `HARNESS_ADVISORY_AUTO_EVALUATE=0`.
  Operator surfaces `GET /advisory/cadence` and `POST /advisory/cadence/run`
  expose the last tick; the runtime lifespan starts/stops the single bounded
  task. No approval gate is touched; no legacy score is invented. Tests:
  `test_advisory_cadence.py`.
- **fix(learning): reconcile advisory scoring and make lesson keys structural.**
  The advisory gate and scorecard now share one canonical definition
  (`advisory/scoring.py`: evaluated / scorable / no_entry_price / unscored /
  not_due); `auto_evaluate` scores only due rows with an entry price and counts
  the two skip reasons separately. Lesson recurrence is keyed by the recorded
  procedure/failure evidence, not the templated text or a stored signature;
  explicit corrections are eligible at recurrence 1. Memory promotion runs the
  recurrence + conflict gate before activating a proposed row. Legacy advisory
  rows get an additive `legacyUnscored` mark; no score is invented. Tests: 282
  related advisory/learning/skills/memory tests passed; `npx tsc --noEmit`
  passed. Docs: `docs/self-improvement/LOOP_MAP.md`,
  `SCORING_CHANGES.md`, `RECURRENCE_FIX.md`, `MEMORY_PROMOTION.md`.
- **feat(learning): close the candidate→draft→accept→score→retire loop.**
  The operator accept route now accepts `detected` and auto-drafted candidates,
  re-validates the contract, creates/keeps the inert skill and records
  `accepted` (never enables). Explicit corrections draft on the first
  occurrence; inferred procedures still require recurrence. Startup evaluates
  learned drafts and used learned skills, and deprecates a non-discriminating
  skill instead of keeping it. Proposed memory promotes after recurrence ≥2 with
  a clean conflict gate; conflicting proposals stay proposed. Legacy reviews are
  marked `legacyUnscored` without rewriting history. All approval gates are
  unchanged. Tests: 277 related learning/skills/memory/advisory tests passed;
  `npx tsc --noEmit` passed. Docs:
  `docs/self-improvement/LOOP_MAP.md`, `docs/self-improvement/CHANGES.md`,
  `docs/self-improvement/loop-closure.md`.
- **fix(chat): make the message rail legible when unselected.** Only the
  unselected ticks were lightened (`bg-muted-foreground/70`, was `/45`); their
  size and the active/hover states are unchanged, so the rail stays visible on
  both light and dark glass without getting heavier. no doc change — visual
  contrast fix.
- **feat(learning,graph): tool-widening safety case, boot-time recall, graph UI
  polish.** Added the evidence-gated `self_improvement/widening.py` ratification
  package (read/compute only, refusal by default) with its spec and tests; startup
  now consolidates duplicate automatic memories (contradictions left for review)
  and backfills completed runs into the session index; the self-improvement
  denylist now also covers the widening/capability/grant surfaces and can no
  longer be narrowed by a caller; graph node cards, canvas, home and globals
  styling were tightened. `npx tsc --noEmit` passed. Docs:
  `docs/self-improvement/loop-closure.md`, `docs/self-improvement/tool-widening/`,
  `docs/graph-studio.md`, `docs/harness/tool-registry.json`.
- **feat(strategy-studio): make the studio a workspace you can come back to.**
  The tab was a JSON sandbox with amnesia: a refresh lost the thesis, spec,
  strategy and result, and saved strategies/experiments were never listed. It now
  has a saved-strategy library, schema-versioned `localStorage` persistence with
  `?strategy=&experiment=` deep links, this strategy's experiment history with
  `/quant/compare`, a data-coverage preflight against the stored-series catalogue
  (absent ≠ impossible; unreadable = unknown), debounced inline validation with
  copyable spec paths, and metric definitions from the runtime. Also fixed the
  strategy record's description being passed as its name, and the paper approval
  recording the same actor for request and decision. Shared `EquityChart`,
  `DrawdownChart`, `TradeTable` and `MetricGrid` were extracted to
  `src/components/screens/backtest/shared/` and the Backtest bench now imports
  them (net −118 lines there). Honest labelling: the paper button replays the
  research window and says so. Docs updated: `docs/strategy-studio.md` (new),
  `docs/NAVIGATION.md`.
- **feat(strategy-studio): research without hand-written JSON.** Robustness is
  now derived from the spec: `src/lib/strategy-studio/param-space.ts` proposes
  the engine-supported dotted paths (indicator params, sizing, stop/target and
  risk limits) and builds `paramSpace`/`paramRanges` from min/max/step rows. A
  "Run the robustness suite" button runs walk-forward → Monte-Carlo → robustness
  into one page, and `research-verdict.ts` calls it `robust` ONLY when the whole
  suite ran and every scored check passed (partial = inconclusive, any failure =
  fragile; every threshold is printed in its check label, and `info` rows are
  never scored). The Edge Report now renders in full through the shared
  `EdgeReportView` (grade, axes, flags, Artifact Center figures, markdown) used
  by both the Studio and the Backtest bench. Added six starter templates labelled
  as examples, not recommendations, and an on-demand runtime research plan
  (hypothesis, assumptions, acceptance criteria, potential biases). Tests:
  `param-space`, `research-verdict`, `templates`, `research-studio`,
  `edge-report-view`. Docs updated: `docs/strategy-studio.md`,
  `docs/NAVIGATION.md`.
- **feat(strategy-studio): no-code builder, forward paper, versions and
  publishing.** The spec card now has a Builder view over the same JSON
  (`src/lib/strategy-studio/spec-edit.ts` deep-clones; unknown fields survive;
  nested/expression rules are marked `advanced` and left to the JSON tab instead
  of being silently rewritten). Paper got two explicit modes
  (`paper-window.ts`): **forward** from the day after the research window ends,
  or a **replay**; a forward window with no forward period is refused, never
  downgraded. Every paper run is listed in a track record with its window and
  drift against the latest backtest (never against another paper run). Added a
  versions panel with structural diff (`/quant/strategies/{id}/diff`) and JSON
  bundle export (`format=json`), plus a grade-gated publish into the local
  gallery. Tests: `spec-edit`, `paper-window`, `spec-builder`, `paper-panel`.
  Docs updated: `docs/strategy-studio.md`, `docs/NAVIGATION.md`.
- **chore(test): green the JS suite after the studio work.** Normalised the one
  stray CRLF line in `mobile-bottom-nav.tsx`, `sidebar/config.ts` and
  `sidebar/config.test.ts`, and re-pinned the `stock-chat.tsx` line budget
  1584→1589 for the Strategy Studio keep-alive mount (the page lives in
  `components/screens/strategy-studio/`). Full Vitest run: 4065/4065.
  no doc change — test/hygiene only.
- **feat(strategy-studio): connect the studio to Projects, the dashboard and a
  share link.** `ProjectLink` attaches the current strategy to a project
  (`kind: "strategy"`, `ref: strategy.id`, version/symbols in `meta`) through a
  new `projectClient.addMember`; the dashboard gains a `strategy-studio` widget
  that lists saved strategies and deep-links each workspace; the header copies
  the exact `?strategy=&experiment=` link. Docs updated:
  `docs/strategy-studio.md`, `docs/NAVIGATION.md`.
- **fix(harness): close eleven pre-existing Python suite failures; add paper
  health.** Advisory cadence/scoring now honour the caller's clock
  (`auto_evaluate(now=…)`, forwarded by `run_once`) instead of re-deriving
  `now_iso()`, so a not-yet-due row can no longer be scored after 00:00 UTC; a
  regression re-check no longer short-circuits to an unchanged-passed record
  with no dimensions; the migration-matrix test uses the production
  `add_column_already_present` guard (now a shared module helper); the four
  DeFi/derivatives tools are allowlisted for the finance agent; the graph API
  tests bind their own service instead of the process-wide singleton; the Python
  size ratchet is re-pinned to the measured tree and its duplicate `service.py`
  entry removed. The studio also gained a pure paper-health badge (fresh /
  stale >30 days / drifting ≥10 return points or ≥0.5 Sharpe, thresholds
  printed). Docs updated: `docs/strategy-studio.md`, `docs/NAVIGATION.md`.
- **feat(strategy-studio): share card, portfolio runs, import, provider check,
  mobile summary.** The studio now exports/imports portable bundles (import
  validates before saving), offers an opt-in 30-day provider check beside the
  stored-catalogue preflight, runs two or more SAVED strategies through
  `/quant/portfolio-backtest` with the shared result panels, produces a
  read-only Markdown share card (identity, metrics, grade, paper state,
  disclaimer), and shows a compact read-only summary under `md`. The dashboard
  widget joins the local gallery so each strategy shows the grade its published
  version earned. Fixed the last two lint warnings (`withCosts` extracted,
  artifact `<img>` documented). Full Python suite: 8707 passed, 29 skipped, 0
  failed. Docs updated: `docs/strategy-studio.md`, `docs/NAVIGATION.md`.
- **feat(strategy-studio): recursive rule builder + mobile summary.** The
  builder now edits nested rule groups (`rule-tree.tsx`) through the pure tree
  API in `spec-edit.ts` (`readTree`/`addTreeNode`/`updateTreeNode`/
  `removeTreeNode`/`setTreeCombine`); expression operands and nesting deeper
  than three levels stay read-only with a pointer to JSON. Added a compact
  read-only summary under `md`, a Markdown share card, bundle import, an opt-in
  provider check, portfolio backtests over saved strategies, and a dashboard
  widget that shows the grade a published version earned. Docs updated:
  `docs/strategy-studio.md`, `docs/NAVIGATION.md`.

## 2026-10-27
- **ui(graph): align the New workflow button with the shared menu system.** The
  template picker is now a real `DropdownMenu` (anchored, dismissable, keyboard
  navigable) instead of a hand-rolled floating panel, and the trigger uses the
  standard primary button sizing alongside Generate from prompt.
  no doc change — UI consistency only.
- **ui(graph): move Start workflow into the header toolbar.** The center-stage
  floating run button is gone; the same save-and-run control now sits inline in
  the editor header row and uses the standard black primary button style. Docs:
  `docs/graph-studio.md`.
- **fix(learning,rsl): finish the loop-closure and widening verification.** Migration
  32 no longer re-adds columns that the base schema already creates (a fresh or
  historical db now reopens), the published tool registry is regenerated, the
  chat-code profile declares `learning_candidate_validate` and
  `skill_discrimination_check`, and the two recovery tests now retry the same tool
  (a different tool that merely succeeds is not recovery evidence). A
  discrimination gap (named base, no outcome metrics) is reported on the
  dimension but is non-blocking, so an ordinary patch still activates; a
  mandatory regression/indistinguishability still blocks. Size ratchets re-pinned
  to the measured tree. Docs: `docs/self-improvement/loop-closure.md`.
- **feat(learning): close the skill, memory and recall loops.** Automatic
  memories now carry `authority=automatic` (source `automatic_learning`) instead
  of masquerading as explicit; gate-approved model preferences save under
  `automatic_selective`; recurring candidates update their occurrence count and
  auto-draft an inert `status=draft` skill; recorded user corrections become
  scoped candidates; startup consolidation merges duplicates but leaves
  contradictions for review; startup quarantines nonconforming legacy
  candidates and drafts the ready ones; startup also runs the deterministic
  evaluation for every `learned.*` draft (enabling stays operator-only); and
  startup backfills up to 200 historical runs into the session index. A preference inside a long prompt is
  stored as its own clause, not the whole prompt; a save proposed by the
  model-facing `memory` tool or post-run analysis is labelled
  `automatic_learning`/`automatic`, not explicit. `skill_list`/`skill_view` now
  expose store-only drafts, and `learning_candidate_list` prints the drafted
  skill id. `session_search` skips the local caller-id filter (indexed messages
  are unowned in single-user mode), retries a multi-token query with ANY terms,
  prints `matchMode`, and indexes an explicit `run_id` once before retrying.
  Migration 33 restores `LearningCandidate.occurrenceCount` on older stores.
  Nothing is auto-enabled: operator acceptance, evaluation and promotion remain
  the only activation path. The usage report now separates `automaticSaved` from
  explicit saves. Tests: 361 related memory / skills / learning / session tests
  passed; `npx tsc --noEmit` passed. Docs:
  `docs/self-improvement/loop-closure.md` (Autonomy update).
- **feat(rsl): add an evidence-gated tool-widening safety-case builder and
  freeze the mechanism it protects.** `self_improvement/widening.py` assembles a
  pure, deterministic ratification package for adding one read/compute tool
  (need, holdout, replay, deny path, conclusion stability, blast radius, TTL,
  revocation); it never grants, auto-applies or self-renews. `security.py` now
  refuses RSL targets under `self_improvement/**`, `capabilities/**`,
  `grants.py` and `recovery/envelope.py`, and the frozen denylist can no longer
  be replaced by a caller. Tests: `python/tests/test_widening.py` (16 targeted
  tests passed with the related RSL/autonomy/capability suites). Docs:
  `docs/self-improvement/tool-widening/{corrections,diagnosis,safety-case-spec,design,risks}.md`.
- **feat(learning): expose the accept-route dry-run and the mandatory flag.**
  `learning_candidate_validate` is a read-only probe that returns the HTTP status
  the operator accept route would produce (404/409/422/200) without writing, so
  the negative paths are observable from chat. The discrimination probe prints
  `mandatory=True/False` in its text. Candidate rows already print procedure
  steps and occurrence count. Live: `gate.ok=true`, `accepted=2`, `detected=0`,
  typed 1, memory 0/0/2/0. Docs:
  `docs/self-improvement/loop-closure.md`.
- **feat(learning): add a read-only discrimination probe and close the remaining
  read gaps.** `skill_discrimination_check` lets a chat run prove
  identical→failed / better→passed / worse→failed with caller-supplied metrics
  without persisting an evaluation. `skill_reviews` now prints the
  discrimination detail. Candidate rows print `occurrenceCount` and the
  procedure step count; the queue line prints `quarantinable`; the scorecard
  prints `needsBackfill`; `learning_review_list(status="superseded")` is a valid
  filter. The app-API proxy is excluded from recoverable-tool lessons (a retry
  cannot fix a down front door), so the current typed lesson is the genuine
  `research_search` transient-`UNAVAILABLE` retry. Live: `gate.ok=true`,
  `accepted=2`, `detected=0`, current typed lessons 1, memory 0/0/2/0. Docs:
  `docs/self-improvement/loop-closure.md`.
- **fix(learning): withdraw the false lessons and keep only a replayable one.**
  The gate now prints the memory domain too (duplicates/conflicts/residue/
  related), review rows print the evidence list, candidate rows print
  `occurrenceCount` and the procedure step count, and a re-review refreshes the
  review timestamp so a corrected lesson is current. The two `app_api_get`
  lessons were superseded and their candidates rejected; the sole current typed
  lesson is the genuine `research_search` transient-`UNAVAILABLE` retry, accepted
  as `cand_2a07300e`. The generic "record the working source preference" lesson
  is rejected as a generic action. Live: `gate.ok=true`, `accepted=2`,
  `detected=0`, current typed lessons 1. Docs:
  `docs/self-improvement/loop-closure.md`.
- **fix(learning): only a genuine same-capability recovery becomes a lesson.**
  A later tool that happens to succeed is no longer treated as recovery
  evidence; the recovery must be the same tool or the same recorded capability,
  and its body must not itself report `UNAVAILABLE`/`TimeoutError`/`TOOL_FORBIDDEN`.
  The two accepted lessons whose `app_api_get` replay timed out were withdrawn
  (`rejected`, retained) and their reviews superseded; a genuine
  `research_search` retry from `run_615d7fce` was reviewed, encoded and accepted.
  Review rows now print the evidence list, and re-evaluating a version marks
  earlier same-version evaluations `superseded` so a self-referential pass is
  no longer presented as current. Live: `gate.ok=true`, `accepted=2`,
  `detected=0`, current typed lessons 2. Docs:
  `docs/self-improvement/loop-closure.md`.
- **fix(learning): print the full candidate census and `relatedCount`.** The
  candidate list now reports the complete store counts by status (not only the
  page) and the number hidden by the 50-row cap, so a legacy row cannot vanish
  from the audit. Memory inventory prints `relatedCount` alongside the
  duplicate/conflict/residue dry-run counts. Gate remains `ok=true`, gaps empty,
  accepted 3, detected 0. Docs: `docs/self-improvement/loop-closure.md`.
- **fix(learning): make every gate domain readable from the bound tool.** The
  `learning_review_list` gate block now prints `contractSince`, current reviews
  (typed/justified/unjustified), legacy reviews, current and legacy advice
  (evaluated/unscored/overdue), and candidates (accepted/detected/nonconforming/
  stale). `learning_candidate_list` prints `staleDetected`/`nonconforming` and an
  accepted row's limitations; `memory(action="inventory")` reports the
  consolidation dry-run counts and cross-type `related` pairs. Accepted the last
  actionable candidate (`cand_421aa3c1`, with the recovery-tool-timeout
  limitation): live `accepted=3, detected=0, gate.ok=true`. Docs:
  `docs/self-improvement/loop-closure.md`.
- **fix(learning): expose the gate on the read tool; tighten discrimination.**
  `learning_review_list` now returns `gate` (ok, gaps, current/legacy windows) so
  a chat run can read `gate.ok` without HTTP-body permission. A version with a
  named base but no outcome metrics now reports `discrimination=needs_review`
  (explicit gap), not `not_applicable`; a root version stays
  `not_applicable`. Residue detection is limited to <=2 tokens or the known
  `loopback can save` fragment, so a real short preference is not mislabelled.
  Live: `system.anatomy-figure` v1.1.1 vs v1.1.0 is `needs_review`; gate remains
  `ok=true`, gaps empty. Docs: `docs/self-improvement/loop-closure.md`.
- **fix(learning): gate the current contract window, report legacy separately.**
  `gate_report` now counts reviews and advice created since
  `HARNESS_LEARNING_CONTRACT_SINCE` (default `2026-10-28T00:00:00Z`) for its pass
  criteria, and reports pre-contract rows under `legacyReviews` /
  `legacyAdvisory` instead of letting them keep the gate red forever. The advice
  gate is due-aware: an unscored recommendation is a defect only at its stated
  horizon, not before. Live result: `gate.ok=true`; current window 3 reviews
  with 0 unjustified nulls and 2 current recommendations not yet due; legacy
  window retains 197 bare nulls and 109 unscored rows for audit. Docs:
  `docs/self-improvement/loop-closure.md`.
- **fix(advisory): record a basis method and a stated horizon at issue time.**
  Every recommendation now gets `method` (explicit, else the basis class
  `portfolio_computation`/`portfolio_read`/`model_advice`, never the action
  verb), `horizon` (explicit, else the policy default `30d`), and `dueAt`; both
  are recorded as basis entries. Quote tools (`market_get_quote`/`get_quote`)
  now contribute an entry price, so a later evaluation can compute a return.
  Backfill applied to the live ledger (111 rows); `advice_missing_horizon`
  cleared and the scorecard reports `byMethod`/hit rate/demotion. Also reports
  memory residue (`fragment: <=4 tokens, no subject`) without touching it, and
  diagnoses a generic-only all-fail route as a provider failure. Regression
  evaluation no longer compares a version against itself. Docs:
  `docs/self-improvement/loop-closure.md`.
- **fix(learning): persist the falsifiable method and unfreeze intake.** The
  `LearningCandidate` table now stores `condition`, `action`, `failedCall`,
  `recoveredCall`, `precondition`, `replayTest` and `occurrenceCount` (migration
  32), so the writer no longer drops the fields the contract requires. A
  previously-created detected candidate was repaired from its run draft and is
  now conforming; intake was re-enabled (`automatic_selective`), a conforming
  specimen was created and accepted (accepted=2, detected=0,
  nonconforming=0). `_regression_dimension` never compares a version against a
  later one (the 1.1.0-vs-1.1.1 inversion), a completed review updates its
  existing row instead of duplicating, and persisted nulls keep
  `justified`/`evidenceChecked`. Fresh `system.anatomy-figure` evaluations now
  carry the `discrimination` dimension (`not_applicable`, explicit gap). Docs:
  `docs/self-improvement/loop-closure.md`.
- **fix(harness): persist null justification, dedupe reviews, expose accept/eval.**
  `_bounded` now keeps `justified`/`evidenceChecked` at the outcome level, so a
  saved null no longer reads as bare; a completed review for one run updates the
  existing row instead of appending a duplicate. Adds operator
  `POST /learning/candidates/{id}/accept` (status only; never enables a skill),
  extends `POST /skills/{id}/evaluate` with `baseVersion`/`metrics`/`baseMetrics`
  so `discrimination` is reachable, reports `intake_disabled` when
  `skill_learning_mode=off`, and records a missing advisory method as
  `unclassified` rather than echoing the action verb. Live state: accepted 1,
  detected 0, duplicate review superseded, fresh evaluation includes
  `discrimination`. Docs: `docs/self-improvement/loop-closure.md`.
- **fix(harness): make pre-contract learning rows visible and drainable.** The
  review list now prints every typed lesson and labels a bare null
  `UNJUSTIFIED`; the candidate list shows `failedCall`/`recoveredCall`/
  `precondition`/`replayTest` and a `CONTRACT VIOLATION` per stored row. The gate
  counts unjustified nulls and nonconforming candidates, not only typed lessons.
  Adds operator-gated quarantine (`POST /learning/candidates/quarantine`) and
  advisory backfill (`POST /advisory/backfill`) that exposes legacy
  method/horizon as `unscored` without inventing a result. Consolidation now
  resolves near-duplicates (containment/subject link) and the verbosity conflict
  ("straight to the facts" vs "detailed with sources"), still supersede-only.
  Applied to the live stores: 48 nonconforming candidates quarantined, 2 stale
  candidates expired, 2 memory records superseded, 109 advisory rows backfilled,
  and one real review produced a typed lesson (recurrence 1/2). Docs:
  `docs/self-improvement/loop-closure.md`.
- **feat(harness): close the learning loop, not just record it.** Reviews now emit
  a typed lesson (`condition -> action -> evidence`) or a justified `no_learning`
  null (reason + `evidenceChecked`), and carry a cross-review signal aggregate
  that requires two distinct runs before a lesson is eligible. Failure-recovery
  candidates must carry the failed call, recovered call, precondition, procedure
  and a replay test; templated titles and constant `0.55` confidence are rejected
  at creation. Skill evaluation adds a `discrimination` dimension against a named
  base on outcome metrics (identical results fail; repeated identical passes are
  flagged as a broken harness). Advisory decisions record `method` + `horizon` +
  `dueAt`, and the scorecard reports unscored/overdue/per-method calibration and
  demotes methods that do not score. Route health diagnoses generic-vs-market
  routing defects, active memory is consolidated (duplicates + contradictions
  supersede to the later statement, retained), and `gate_report` treats an
  unconsumed candidate queue as a design failure. Docs:
  `docs/self-improvement/loop-closure.md`; `docs/NAVIGATION.md` rows updated.
- **fix(harness): scope the candidate empty state and keep the read-only footer.**
  A status-filtered empty listing now says "No learning candidates captured with
  status 'accepted' yet." instead of implying the whole store is empty, and every
  empty response keeps the read-only footer. A request above the 50-row cap now
  says it was capped. no doc change - bug fix; no contract, setup, or architecture
  change.
- **fix(harness): upgrade the graph-run schema before indexing `jobId`.**
  `GraphRunStore` created `idx_graph_run_job` inside the base schema script, so a
  legacy `HarnessGraphRun` table without `jobId` raised `no such column: jobId`
  and left the whole graph runtime unavailable at boot. The index is now created
  after the column upgrade; regression test covers the legacy table. no doc
  change - bug fix; no contract, setup, or architecture change.
- **fix(harness): report the true candidate total past the 50-row page.**
  `learning_candidate_list` now reads `count_candidates(status)` and says
  "Showing N of M" when the page is truncated, so an operator cannot mistake the
  tool's output cap for the queue size. Adds one read-only store count method and
  a regression test. no doc change - bug fix; no contract, setup, or architecture
  change.
- **fix(graph): make the connection aurora actually visible.** The first pass
  was too faint (2px, blurred, 16–55% opacity). Now a 3px hot core with an
  accent box-shadow glow plus a wider blurred haze, breathing 45–100% on the
  same 8s loop. Still respects reduced motion and Glow-off.
  no doc change - tuning only.
- **fix(harness): `learning_candidate_list` resolves the Eclipse-Memory store by
  capability.** It now prefers `memory_service.store` and only accepts
  `learning_store` when it exposes `list_candidates`, so the research path store
  can no longer cause an `AttributeError`. The empty state reads
  `skill_learning_mode` and no longer promises automatic capture when detection
  is off (or unreadable); tests now use the production wiring. no doc change - bug
  fix; no contract, setup, or architecture change.
- **feat(graph): minimal live connection aurora on node edges.** Wired nodes show
  a small blurred accent light bar on the left (`hasIncoming`) and/or right
  (`hasOutgoing`) edge, breathing/bobbing on an 8s loop with the two sides
  phase-offset. Respects `prefers-reduced-motion` and the Glow-off preference.
  Rendered in `eclipse-node.tsx`; keyframes/classes in `globals.css`.
  no doc change - visual restyle only; uses existing node data fields.
- **feat(chat): show the Python program in the activity step.** `analysis_run`
  and `execute_python` now emit a bounded (`8 000` chars), secret-redacted
  `codePreview` on `tool.requested`, so the source appears inside the activity
  step's existing expandable details (not as a separate panel), with honest
  truncation. The preview is persisted with the run. Producer:
  `code/activity.py::tool_code_preview`;
  emitter `graph.py`; client `ActivityItem.codePreview` + `activity-item.tsx` /
  `output-panel.tsx`. docs updated: `docs/chat-ui-audit.md`, `docs/NAVIGATION.md`.
- **feat(graph): accent-aurora node restyle.** Graph nodes now use the frosted
  `node-card` material with a thick accent border, a plain foreground-coloured
  icon (no tinted tile), and a per-node **aurora** halo when wired. Wires and
  handles take the source node's category accent (with a gradient stroke + soft
  glow) instead of the neutral slate/sky hardcode. Category accents moved to
  `lib/graph-studio/port-style.ts` (`categoryAccent`) as the single source.
  no doc change - visual restyle; new node/edge data fields are internal to the
  canvas renderer and no contract changed.
- **fix(graph): aurora moved off the node body and onto its connected edge.**
  Follow-up to the node restyle: the accent halo no longer wraps the whole card
  (which read as background glow). It is now a thin drifting light bar on the
  node's **left** side when it has incoming wires and on its **right** side when
  it has outgoing wires (both sides when both). Node borders are near-black
  again, not accent-coloured; selection uses an accent outline offset outside
  the frame. Node glass was deepened (multi-layer tint, stronger blur, inset
  sheen). no doc change - visual restyle only.
- **fix(graph): n8n-style compact nodes, theme-driven colour.** Narrowed nodes
  from 244px to 184px and moved the icon to a centred top slot with the label and
  category stacked beneath. All glow (aurora, wire stroke/glow, handles, `+`
  affordance, selection outline) now reads `var(--primary)`, so it follows the
  active theme instead of a hardcoded per-category palette; the unused category
  accent table was removed from `port-style.ts`. no doc change - visual restyle
  and internal cleanup only.
- **fix(graph): remaining blue chrome moved to the theme accent.** The floating
  "Start workflow" button lost its blue glow and now uses a shared
  `.graph-accent` control (border/tint/text from `var(--primary)`, no box-shadow).
  Applied the same class to "Add node", "Add first step", the wire insert `+`, and
  the schedule action; focus rings, active toggles, inspector tabs/checkboxes and
  the editor icon now use primary tokens instead of `sky-*`. Running-status dots
  stay sky (semantic state, not chrome). no doc change - styling only.
- **feat(graph): black bezel nodes with an inner aurora.** Node body is now true
  black (not grey), framed by a wide 5px solid-black border with a larger radius.
  The identity block is centred with a bigger icon and a single label - the
  category kicker and the divider line above the ports were removed. When a node
  is connected, an accent aurora now drifts **inside** the card (radial sweep,
  gated by `data-incoming`/`data-outgoing`) instead of hugging the outside edge.
  Node border no longer changes colour for run status (the status badge remains).
  no doc change - visual restyle only.
- **fix(graph): side aurora, centred handles, glass matched to the system.** The
  aurora moved back out of the card to the connected **side** (left = incoming,
  right = outgoing) as a drifting light bar. Port handles are now centred on the
  node's vertical midline (fanned only for multi-port sides), so wires meet the
  middle of the card like the reference. `.node-card` now uses the exact
  `.glass-card` material recipe (black tint, 18px blur, saturate 1.35, inset
  highlights) instead of a bespoke grey gradient. no doc change - visual restyle
  only.
- **fix(graph): node icons tinted with the accent and heavier stroke.** Icons are
  now outline-style but rendered at `var(--primary)` with `strokeWidth 2.5`
  (was muted `text-foreground` at default weight), so they read solid rather
  than faint inside the black card. no doc change - visual restyle only.
- **fix(graph): 10px node bezel, solid white icons.** Node border widened from
  5px to 10px. Icons are now solid white filled glyphs (`fill=currentColor`,
  thin residual stroke) instead of accent outlines. Side aurora stays on the
  connected wire side and was nudged out to clear the thicker bezel. no doc
  change - visual restyle only.
- **fix(graph): solid white icons, inner animated aurora, graphite glass.** Icons
  render Phosphor `weight="fill"` (true solid glyphs) in white instead of light
  outline strokes. The accent aurora moved back inside the card as a diagonal
  sheen that continuously travels beneath the glass on connected nodes. Node body
  lifted from pure black to a graphite tint (`rgb(34 34 39 / 0.72)`) so the black
  bezel and white icon have contrast. no doc change - visual restyle only.
- **fix(graph): wider nodes and a dominant icon.** Node width restored to 244px
  (from 184px) so port labels and long titles fit again, and the filled icon
  grew to 34px in a 48px slot — clearly larger than the 12.5px label. Node body
  darkened to charcoal and the aurora is now a wave running along the connected
  side. no doc change - visual restyle only.
- **feat(graph): reference-accurate node card.** Nodes are now wide 244px cards
  (112px min height, 18px radius, 4px black bezel) with a **horizontal** identity
  block: solid white filled icon on the left, 16px white title over an 11px muted
  category subtitle on the right. Visible per-port label rows removed; handles
  sit on the edge midpoints (fanned per port) with names in the tooltip, and the
  add-next `+` follows each output handle on hover. Aurora is now a soft radial
  bloom anchored at each connected edge midpoint (left/right) that breathes
  in-place, spilling outside the bezel and washing into the body. no doc change -
  visual restyle only.
- **fix(graph): inner half-clipped live aurora + lighter glass.** Replaced pseudo
  blooms with an inner `.node-aurora-clip` layer (`overflow:hidden`) holding two
  glows centred on the card edges, so only the inner half is visible at the
  connected side (left incoming, right outgoing) and it drifts/breathes on a
  loop. Node tint lowered to `rgb(24 24 28 / 0.58)` so the 18px backdrop blur is
  actually visible. Content and handles sit above the clip layer. no doc change -
  visual restyle only.
- **fix(graph): smaller, visibly moving aurora.** Glow reduced to 110px / 104%
  and the animation now travels horizontally (translate 55% → 22% of its own
  width, plus scale/opacity) so the motion is obvious. Added a scoped
  `prefers-reduced-motion` override for `.node-aurora-glow`: the global reset was
  freezing it on machines with reduce-motion enabled. no doc change - visual
  restyle only.
- **fix(graph): aurora ripples in waves, smaller and lighter.** Glow shrunk to
  88px / 96%, gradient alphas lowered (55% → 22%), and the animation now follows
  a 5-stop undulating path (in/out + up/down) at 4.8s, so it ripples like an
  aurora. no doc change - visual restyle only.
- **fix(graph): real ribbon aurora instead of a moving blur.** Replaced the
  single radial glow with an inline SVG of three sine ribbons that drift
  horizontally at different speeds/directions (7/5/10px strokes, blurred,
  low opacity), faded away from the connected edge via `mask-image`. Renders a
  proper flowing wave, half-visible at the wire side, inside the clipped card.
  no doc change - visual restyle only.
- **fix(graph): aurora ribbons glow instead of reading as lines.** Layered three
  strokes as a wide soft curtain (14px / blur 12), a mid ribbon (7px / blur 7)
  and a thin bright crest (3px / blur 3), with `mix-blend-mode: screen` and an
  accent drop-shadow, on a 2-wave path loop. The strokes now fuse into a glowing
  band rather than separate lines.   no doc change - visual restyle only.
- **fix(graph): aurora is now pure blurred waves, no visible strokes.** Removed
  the thin bright crest and drop-shadow; all three layers are wide strokes with
  heavy blur (18/14/22px) and low opacity, screen-blended. Nothing resolves into
  a line — only soft flowing curtains. no doc change - visual restyle only.
- **fix(graph): aurora confined to a smaller side patch.** Wave canvas inset to
  18% top/bottom (64% height), mask fade tightened to ~48% of the width, and
  stroke widths reduced, so the glow is a compact patch at the connected edge
  instead of spanning the whole card. no doc change - visual restyle only.
- **fix(graph): aurora waves have real amplitude and show in light mode.** Wave
  paths now swing across most of the card height (control points near the
  viewBox edges) instead of tiny ripples that read as a flat line; canvas back to
  76% height with mask fade at 55%. Light mode switches the blend from `screen`
  to `multiply`, since screen-on-white was hiding the glow entirely. no doc
  change - visual restyle only.
- **fix(graph): aurora sized as a compact centred band.** Wave canvas reduced to
  48% height (inset 26% top/bottom) with `overflow: hidden` so blur can't bleed
  toward the card edges, and the side mask now fades out by ~42% of the width.
  Strokes tightened accordingly. no doc change - visual restyle only.
- **revert(graph): aurora removed from nodes entirely.** Deleted the inner
  aurora SVG, clip layer, wave CSS/keyframes and the `data-incoming`/
  `data-outgoing` hooks. Nodes are now just the black-bezel glass card with the
  icon/title/subtitle; wires carry the accent colour only. no doc change -
  visual restyle only.
- **feat(graph): compact node cards with inline parameter editing.** Node cards
  shrink from a 112px min-height / 4px bezel to a 46px identity header / 2px
  bezel (icon 48→32px, title 16→13px), with the run status folded into the header
  and the hover toolbar tightened. Up to two scalar config fields now render as
  inline editors on the card (text/number commit on blur or Enter, selects and
  booleans immediately, Escape reverts); fields supplied by an incoming edge show
  a read-only "From wire" chip. `config-fields.ts` adds presentation metadata
  (label/kind/options/inline) over the registry defaults, a shared
  `config-field.tsx` replaces the inspector's hand-rolled fields, and
  `dispatch(patch, { coalesceKey })` collapses a typing session into one undo
  entry. `buildNodes` reuses unchanged node objects so editing one node no longer
  re-renders the whole canvas. Docs: `docs/graph-studio.md`.
- **style(graph): node icons are plain outline glyphs.** Removed the filled
  Phosphor weight and the accent-tinted icon chip; nodes now use the same
  regular-weight, muted icon treatment as the rest of the site. no doc change —
  visual restyle only.
- **fix(graph): remove the node connection glow.** Deleted the side aurora spans,
  their CSS/keyframes, the handle glow and the now-unused incoming/outgoing
  flags. Nodes are a flat glass card; wires stay the accent colour. no doc change
  — visual restyle only.

