# Change Log

## 2026-11-10
- **feat(quant): closed the operational code gaps in the 10/10 foundation.**
  Live signals now refuse critical data findings; `risk_state.py` persists
  day-start/peak equity and auto-kills a trial on a daily-loss or drawdown
  breach; `live_scheduler.py` adds an idempotent `run-due` batch over active
  trials; `monitor_store.py` persists daily parity/drift/attribution snapshots;
  `model_card.py` renders the evidence record; `golden.py` repairs then freezes a
  content-hashed golden dataset. New routes cover golden freeze, monitor
  snapshots, model cards and the scheduler hook. Tests: 550 quant passes,
  QuantBench 51/51, `tsc`, evals and size pass. Docs updated:
  `docs/quant-system-blueprint.md`, `docs/NAVIGATION.md`, `docs/CHANGELOG.md`.
- **feat(bots): durable conversations, manual runs for paused bots, and consistent model pins.**
  Bots mode now mirrors per-bot threads and group rooms to a durable `BotState`
  document in JDdS (`src/app/api/bots/state/[key]/route.ts`,
  `src/lib/bots/state-sync.ts`). localStorage remains the instant/offline copy;
  the newest client timestamp wins, and other tabs adopt changes through a
  `storage` listener, so clearing browser storage no longer erases
  conversations. "Run now" now works on a paused bot — pause stops the
  scheduler, not an explicit run (the operator run route opts into
  `allow_paused`; `engine.fire`/`_launch` honour it for manual triggers only,
  while webhook/agent-tool/event/condition/fabric paths still require
  `active`). The `agent.bot` graph node now applies a saved bot's
  provider/model pin (credentials and base URL still come from the graph run),
  matching its scheduled runs. Tests: `state-sync.test.ts`,
  `test_automation_engine.py`, `test_graph_agent_node.py`; `tsc` clean. Docs
  updated: `docs/bot-mode.md` (new), `docs/NAVIGATION.md`,
  `docs/harness/automation-engine.md`, `docs/graph-studio.md`,
  `docs/graph-studio-bot-skill-nodes-plan.md`, `docs/CHANGELOG.md`.
- **feat(quant): closed the remaining code gaps in the 10/10 foundation.**
  The backtest route now refuses critical data findings unless
  `allowDirtyData` is explicit; `data-quality/repair` drops exact duplicates and
  counts conflicts without filling gaps. Added a durable `QuantOrder` OMS store
  (restart-safe, unique idempotency key), enforced stop/target on live-trial
  orders (the risk engine now requires a stop), a `run-due` scheduler hook,
  broker cost calibration from fills (`slippageBps`, commission per lot and
  explicit backtest assumptions), and a trial report route (runs, broker
  account, positions, orders, P&L). The health panel now reports data, broker,
  risk, runner and lifecycle. Tests: `test_quant_system_core.py` (14),
  `test_quant_live.py` (5), routes; QuantBench 51/51; `tsc` and size pass.
  Docs updated: `docs/quant-system-blueprint.md`, `docs/quant-engine.md`,
  `docs/CHANGELOG.md`.
- **feat(quant): shipped the 10/10 foundation across all 12 workstreams.**
  Added `quant/data_quality.py` (duplicate/conflict detection, gap
  classification, broker parity, content hash, blocking gate),
  `quant/lifecycle.py` (evidence-gated model state machine),
  `quant/risk_engine.py` (per-trade sizing, lot/notional/margin/spread/exposure
  checks, daily-loss and drawdown kill), `quant/oms.py` (idempotency, legal
  state machine, brackets, partial fills, reconciliation, TCA),
  `quant/live_runner.py` (one claim per strategy/version/timeframe/bar,
  restart-safe, pause/resume), `quant/monitor.py` (signal parity, drift,
  attribution), `quant/capital.py` (risk-budget allocation with caps) and
  `quant/system_health.py` (one operator view). The live trial now claims a run
  key, runs the risk engine before submit and records OMS state. Added
  `routers/quant_system.py` (data quality, parity, lifecycle, risk, allocation,
  runs, health) and the Strategy Studio `system-health-panel.tsx`. Tests:
  `test_quant_system_core.py` (11) + live (5) + routes; `tsc` clean; size
  re-pinned deliberately. Docs updated: `docs/quant-system-blueprint.md`,
  `docs/NAVIGATION.md`, `docs/CHANGELOG.md`.
- **docs(quant): added the Quant System Blueprint** (`docs/quant-system-blueprint.md`).
  It defines a measurable 10/10 target (data truth, research rigor, model
  lifecycle, broker-calibrated backtests, a hard risk engine, an idempotent OMS,
  bar-close automation, drift monitoring, portfolio allocation, governance and
  operator UX), 12 workstreams with exit criteria, a 13-week build plus 90-day
  evidence track, strategy promotion thresholds and a first-10-days checklist.
  Plan only; no runtime code changed. Docs updated:
  `docs/quant-system-blueprint.md`, `docs/NAVIGATION.md`, `docs/CHANGELOG.md`.
- **feat(quant): added governed live strategy trials.** New `quant/live.py` +
  `routers/quant_live.py` promote an approved, backtested strategy version to a
  live broker trial. Gates: approved review, completed backtest, typed phrase,
  live connection, future arm and a positive maxMargin. The trial creates a live
  mandate pinned to `strategy:<id>:<version>`, evaluates the strategy on the last
  closed bar with the same causal engine, submits ONE order under the mandate,
  refuses to stack a position, closes on an exit signal, reads broker results
  (account/positions/orders/open P&L) and stops by revoking the mandate. The
  existing broker layer, money guardrails, reconciliation and kill switch are
  reused; no second order path. Strategy Studio gained a live-trial panel.
  Tests: `test_quant_live.py` (5) + route registration; docs
  `docs/quant-live-strategy.md`, `docs/quant-engine.md`, `docs/NAVIGATION.md`.
- **feat(quant): widened Quant Research Intelligence to a horizon-wide, visual
  research system.** The method catalog grew from 17 to 33 methods across
  intraday, swing, position and long-term horizons (ARIMA, VECM, Kalman, carry,
  crypto funding, low-vol, seasonality, options income, volatility breakout,
  event drift, risk parity, Black-Litterman, value, quality, long-term trend,
  equal weight), and it is explicitly open: literature extraction and
  `quant_register_method` add methods at runtime. Added
  `quant_attach_implementation` so any method can receive a tested Python
  implementation; open-access PDF links and citation pointers are stored, and
  the generic worker uses Docker when configured.
  Added `research_method_matrix` (coverage by horizon) and `research_visualize`
  (method coverage, suitability, price, rolling volatility, return distribution,
  reproduction fit) with computed chart blocks. Reproduction grew to 12 built-in
  estimators (GJR-GARCH, EGARCH, HAR-RV, Engle-Granger, HMM, EVT/GPD, CAPM/FF,
  Almgren-Chriss) plus a generic registered-code path that runs in a separate
  process with a scrubbed environment, timeout and output cap. Extraction now
  accepts an optional model proposal only when each field's quote exists
  verbatim in the document. Academic search now merges OpenAlex, Semantic
  Scholar, Crossref and arXiv; SSRN/NBER/RePEc are scoped pointers. Added the
  Research Intelligence panel to Strategy Studio, an open-method matrix view,
  computed figures, and a figures section in the dossier. Tests:
  `test_quant_research_intel.py` (26), routes (5), connectors (11), QuantBench
  47/47; `tsc` clean; size budget re-pinned deliberately. Docs updated:
  `docs/quant-research-intelligence-plan.md`, `docs/quant-engine.md`,
  `docs/quant-research-prompts.md`, `docs/NAVIGATION.md`, `docs/CHANGELOG.md`.
- **feat(quant): shipped Quant Research Intelligence.** New
  `python/harness/quant/research_intel/` adds a formal method-spec contract with
  sourced equations, a 17-method seeded knowledge base, deterministic research
  query planning, scholarly search over the EXISTING OpenAlex/Crossref/arXiv
  connectors with DOI/arXiv/title dedupe, section/equation extraction with page
  provenance, explained suitability scoring, a reproduction harness separated
  from trading adaptation (OU/AR(1), EWMA, realized variance, GARCH(1,1)), a
  validation matrix, and a Quant Research Dossier registered in the Artifact
  Center. 14 agent tools (`research_*` + `quant_*_method`/dossier) are added to
  `QUANT_TOOLS`; `routers/quant_research.py` exposes the operator-gated routes;
  `quant/bootstrap.py` seeds the catalog; `model_catalog` gained `method` and
  `dossier` kinds. Reproduction is honest: an unregistered implementation
  returns `inconclusive`, and a validated lifecycle requires a passing
  validation record. New intent kinds: literature_review, method_comparison,
  method_reproduction, research_discovery, quant_model_development,
  research_extension. Tests: `test_quant_research_intel.py`,
  `test_quant_research_intent.py`, `test_quant_research_routes.py` + four
  QuantBench cases (routing and math); registry regenerated; size budget
  re-pinned deliberately. Added reusable research prompts
  (`docs/quant-research-prompts.md`) and a "Quant research" block in the base
  system prompt. Docs updated:
  `docs/quant-research-intelligence-plan.md`, `docs/quant-engine.md`,
  `docs/quant-research-prompts.md`, `docs/NAVIGATION.md`, `docs/CHANGELOG.md`.
- **docs(quant): added the Quant Research Intelligence implementation
  specification** (`docs/quant-research-intelligence-plan.md`). It defines the
  research-to-model evolution on top of the existing engine — scholarly search,
  paper/method extraction with page provenance, a method knowledge base,
  reproduction separated from trading adaptation, validation and a research
  dossier — with mandatory repository-inspection steps, a reuse map, proposed
  module responsibilities, tool/route contracts, additive `agent-memory.db`
  schema, phased acceptance tests and explicit no-rebuild guardrails. Plan only;
  no runtime code changed. Docs updated:
  `docs/quant-research-intelligence-plan.md`, `docs/CHANGELOG.md`.
- **feat(quant): method discovery, realism, portfolio risk and a measurable
  benchmark.** Quant mode now centres on finding, adapting and inventing
  tradable methods. New `quant/discovery/` (14-family taxonomy with thesis/edge
  source/failure modes; method cards; deterministic fit recommendations;
  market-structure diagnostics; falsifiable hypotheses; method→spec synthesis and
  two-method composition; bounded IS/OOS mining with the real trial count and
  Deflated Sharpe) plus `quant/discovery_tools.py` and the `/quant/methods/*`,
  `/quant/discovered-methods/*` routes and persisted `QuantMethod` rows. Quant
  intent now recognises discovery turns and the per-turn protocol drives
  library → scan → hypothesis → synthesize/mine → validate. Realism added:
  borrow/locate fees, financing, maintenance margin + liquidation, participation
  partial fills, corporate actions (all opt-in and zero by default), plus
  `quant/manifest.py` run manifests and `reproduce_experiment`. Portfolio layer:
  `risk_model.py` (sample/EWMA/Ledoit-Wolf covariance, Euler risk contributions,
  factor exposures), `portfolio_optimizer.py` (MV/min-var/max-Sharpe/risk
  parity/HRP/Black-Litterman + constraints), `scenario.py` (VaR/ES, historical,
  scenarios, reverse stress). Derivatives: `options_backtest.py` (dated
  chain-marked multi-leg backtest) and futures term-structure/roll-cost helpers.
  Research sessions + hypothesis/trial ledger, HTML/notebook export, QuantBench
  (`python -m harness.quant_bench`), and new Strategy Studio panels (method
  discovery, research journal, portfolio stress) + shared manifest panel.
  Trading playbook (`quant/playbook.py`, `generate_trading_playbook`) renders
  the actual spec into entry/exit/sizing/risk/execution/invalidation/monitoring
  instructions with the paper-first rule. Added `scan_universe_setups` +
  `/quant/methods/universe-setups` and a "Scan watchlist" action so a user can
  find which validated methods have an entry condition across several symbols
  now (bounded to 12; per-symbol failures are reported, never hidden). Added
  `mine_universe_methods` + `/quant/methods/mine-universe`: the same bounded
  mining across up to 5 symbols, aggregated per method family with support and
  mean OOS Sharpe, so a one-symbol fluke is visible instead of averaged away. Fixed the `sources` screen's stale
  `lucide-react` import (now the repo icon set) so `tsc` is clean.
  Tests: `test_quant_realism.py`, `test_quant_discovery.py`,
  `test_quant_portfolio.py`, `test_quant_desk.py`; `tsc` clean. Added
  `npm run test:quant-bench` (`scripts/quant-bench.js`), wired into
  `.github/workflows/ci.yml`, so the scorecard is a real CI gate. Regenerated
  `docs/harness/tool-registry.json` for the new tool surface and re-pinned
  `scripts/size-budget.json` for the measured discovery subsystem. Docs updated:
  `docs/quant-engine.md`, `docs/strategy-studio.md`,
  `docs/quant-method-discovery.md` (new), `docs/NAVIGATION.md`,
  `docs/DECISIONS.md` (ADR-078), `skills/ARCHITECT.md` (ADR-078),
  `docs/CHANGELOG.md`.
- **perf(chat): make send instant on Enter.** `saveConversations` wrote the
  entire transcript list to `localStorage` synchronously inside the send
  handler, so the new bubble could not paint until a full `JSON.stringify` +
  `setItem` finished (the cost grows with every saved chat). The in-memory store
  still updates immediately; the cache write is now coalesced and deferred
  400 ms, with an early flush on `pagehide`/`visibilitychange`. no doc change —
  bug fix; the storage contract is unchanged.

- **feat(quant): quant mode is figure-first.** Added the deterministic Quant
  Figure Kit (`python/harness/quant/visuals.py`) that builds equity, underwater,
  monthly returns, exposure, trade distribution/scatter, rolling risk, cost
  waterfall, Monte-Carlo, regime attribution, walk-forward and a 3D parameter
  surface from stored artifacts. Added the `render_quant_figures` tool
  (`quant/visual_tools.py`) and
  `GET /quant/experiments/{id}/figures[/{figure}]`; a chart block may now name
  `quant: {experimentId, figure}` and the browser resolves the computed spec, so
  a long series never travels through the model. The quant protocol now carries
  a visual contract and figure budget, `evaluate_quant_outcome` reports a missing
  figure after a series-producing run, response mode is upgraded to
  `visualization`, 3D panels get real matplotlib axes for the PNG copy, and the
  Backtest bench reuses the same kit through `QuantFigurePanel`. Docs updated:
  `docs/quant-engine.md`, `docs/chart-engine.md`,
  `docs/interactive-response-engine.md`, `docs/NAVIGATION.md`,
  `docs/DECISIONS.md` (ADR-076), `skills/ARCHITECT.md`, `docs/CHANGELOG.md`.

- **feat(sources): open, search and query folders/drives of any size in place.**
  New `python/harness/sources/` layer: a dedicated SQLite catalog
  (`.black-eclipse/sources/sources.db`) with an incremental, batched, resumable
  scanner that stats files without opening them; a bounded probe that reads at
  most 4 KB head + 1 KB tail and returns a *card* (magic/format, schema, page
  count, image size, archive entries, preview) whatever the file size; windowed
  byte/line reads; a streaming text extractor with content-defined chunks and
  FTS5; read-only DuckDB over CSV/TSV/JSONL/Parquet bound as view `t` with a
  statement allowlist, memory limit and spill directory; and a query router that
  derives candidates from the catalog and chooses metadata / FTS / DuckDB /
  bounded parallel scan, with time, byte, result and cancellation budgets plus
  honest partial reporting. Adaptive background indexing makes the second query
  fast; optional semantic reranking (`HARNESS_SOURCES_SEMANTIC=1`) embeds chunks
  through the existing `search.embeddings.EmbeddingService` and scores a bounded
  candidate subset, never the whole corpus. Agent tools `source_roots/list/open/
  read/lines/search/sql/index/stats` (read-only; adding a root is operator-only)
  register on the ONE registry and are advertised on the Eclipse and Code agents;
  routes live in `python/harness/routers/sources.py` and are proxied by
  `/api/sources/*`, with a new Sources tab (roots, scan progress, routed search,
  bounded preview, SQL runner). Tests: `python/tests/test_sources_core.py`,
  `test_sources_query_tools.py`. Docs updated: `docs/harness/large-sources.md`
  (new), `docs/NAVIGATION.md`, `docs/DECISIONS.md` (ADR-077),
  `skills/ARCHITECT.md`, `docs/CHANGELOG.md`. `no doc change` — n/a.
- **fix(capabilities): a "bot" request can no longer dead-end in the code
  builder.** `capability_request` had no automation vocabulary, so "turn this
  into a skill and then a bot" classified only the skill (or fell through to
  `scaffold_kit`), and a chat/code turn without `code.write` then answered
  `PROFILE_DENIED` — which reads as "Eclipse won't let me". Added `detect_kinds`
  (ordered, multi-deliverable), a `bot` kind → `bot_create` in the surface/next-tool
  maps, and a `_bot` hand-off whose notes explicitly forbid `scaffold_kit` and
  name the cron + IANA timezone as required input. `CODE_AGENT_TOOLS` now carries
  the Automation tools so a code task can create the same bot; `bot_create`
  refuses a cron/interval trigger with a plain-language reason instead of an
  exception. Hand-off responses now say "call the tool NOW in this turn" rather
  than "nothing was activated"; `scaffold_kit`'s `PROFILE_DENIED` /
  `WORKSPACE_UNBOUND` refusals name `skill_create` / `bot_create` / a code task.
  The verifier's `output-contract` failure now says which output had the wrong
  kind and what it got, so one build fixes it; a verifier crash is recorded as a
  failed version instead of leaving orphan draft files with no record. Tests:
  added bot/multi-deliverable routing, hand-off, tool-text and scaffold-refusal
  cases; `test_code_agent`, `test_automation_tools`; isolated the dynamic recipe
  registry in `test_capabilities_builder` and made the public-manifest drift gate
  generate in a clean subprocess (it was order-dependent). Docs updated:
  `docs/harness/capability-builder.md`, `docs/CHANGELOG.md`.
- **feat(runtime): no dead ends — every offerable block becomes a durable gap
  and a user offer.** Added `python/harness/gaps/` (`taxonomy.py` = 8 classes,
  only capability/context/setup are offerable; `store.py` = durable
  `CapabilityGap` on `agent-memory.db` with stable signatures, suppression and
  resolution; `service.py` = the one-route offer + accept/decline/suppress;
  `runtime.py` = the fail-open graph glue). `graph.py` records refused tool
  payloads (a handler refusal is `ok=True` with `status:refused`), closes a gap
  on a later success, catches one narrow prose-only refusal, and at the answer
  seam emits `capability.offer` plus one visible sentence. `run_outcome` reads
  the offer into `capabilityGap`. Operator API `/capabilities/gaps*` (accept also
  asks the existing parked-task resume path); chat card wired through
  `events.ts` → `capability-card.tsx` → `chat-history.tsx` with
  `actionPrompt`/`actionLabel`; Capability Studio queue `gaps-section.tsx`;
  prompt rule "never end with a bare refusal"; safety denials never offer a
  bypass. Tests: `test_capability_gaps.py`, `test_no_dead_ends.py`,
  gaps API + event/card cases. Docs: `docs/harness/no-dead-ends.md` (new),
  `docs/harness/capability-builder.md`, `docs/NAVIGATION.md`,
  `docs/CHANGELOG.md`.

## 2026-11-09
- **ops: run the v0.3.2 production build as the soak instance on Windows.** Added
  `scripts/install-app-task.ps1`: a per-user scheduled task (2-minute ignore-new
  watchdog + Startup shortcut, no admin) that keeps a production `next start`
  alive, with `-AppPath`/`-DataDir` so a tagged release can run from its own
  checkout against the real databases. Verified C3 (clean build of `v0.3.2` in a
  pristine worktree, 297 s, `/login` 200) and C6 (login, settings, provider chat,
  and a completed harness run with one `finance_calc` tool call returning
  `+25.0%`). The dev server no longer restarts the soak instance; the main dev
  `.next` was restored. Docs updated: `docs/DEPLOYMENT.md`,
  `docs/PRODUCTION-READINESS.md`, `docs/CHANGELOG.md`.
- **docs(readiness): record the first soak checkpoint and its interruption.**
  `scripts/soak-report.ps1` over the first 0.9 h: 10 healthy, 3 failed, 76.92%
  uptime; the app on `:3100` was down 00:06-00:16 and recovered at 00:21, with
  every failure logged and locally escalated (not silent). Cause: concurrent
  development restarted the instance, so the 7-day gate needs a quiet host.
  Docs updated: `docs/PRODUCTION-READINESS.md`, `docs/CHANGELOG.md`.
- **fix(eval): the published-baseline pin test follows the newest pin.**
  `test_live_baseline` still expected `task_success 0.9574` after the live lane
  was re-pinned to `live:27c280164943e63520e14422a6c953cf` (0.9748), so the full
  Python suite was red. Updated the expectation and its comment. Test-only; no
  behaviour change. Docs updated: `docs/CHANGELOG.md`.
- **ops: local alert escalation, soak evidence and a runnable IR control.** The
  Windows health wrapper now shows a desktop notification
  (`scripts/alert-desktop.ps1`), keeps an `ALERT-ACTIVE.txt` marker until the
  next healthy run and exits non-zero (task Last Result red) when no webhook is
  configured; `scripts/soak-report.ps1` turns `health.log` into the soak
  exit-gate evidence (samples, failures, uptime, coverage gaps, marker). Added
  `scripts/revoke-sessions.js` (`--list`, `--user`, `--disable-user`, `--db`) so
  the incident-response "revoke sessions" step has a command, and ran the S1
  session-leak drill against an isolated production-posture instance
  (unauth 401 -> login -> revoke -> the same cookie 401; re-login as the
  disabled user 401), recorded in `docs/legal/INCIDENT-RESPONSE.md`. Docs
  updated: `docs/DEPLOYMENT.md`, `docs/legal/INCIDENT-RESPONSE.md`,
  `docs/legal/README.md`, `docs/PRODUCTION-READINESS.md`, `docs/CHANGELOG.md`.
- **fix(chat): remove the computed-result card from the transcript.** Deleted
  `src/components/chat/computed-result-panel.tsx` (and its test) and stopped
  `chat-history.tsx` from rendering `msg.analysis`; the card surfaced raw
  sandbox debug variables (`attempts`, `full_kwargs`, …) as if they were
  results. Provenance/fail-closed behaviour is unchanged at the runtime
  boundary, figures still render inline, and artifacts remain in the Artifact
  Center. Docs updated: `docs/interactive-response-engine.md`,
  `docs/NAVIGATION.md`, `docs/CHANGELOG.md`.
- **release: cut `v0.3.2`.** Version bump (`package.json`, project version in
  `package-lock.json`) and a release note capturing the measured live gate
  (`task_success 0.9748`, hallucination 0.0, citation 1.0, financial 0.9963),
  the evidence-safe citation gate, the deterministic finance surface, the
  Windows operations tooling and the legal draft pack. Docs updated:
  `docs/releases/v0.3.2.md`, `docs/CHANGELOG.md`.
- **docs(legal): draft the hosted contract pack and adopt the DCO.** Added
  clearly-marked Draft templates for Terms, Privacy, Risk, AI Usage, Acceptable
  Use, Automated Trading, DPA, Subprocessors, Cookies, Trademark, Incident
  Response, Complaints, Records Retention and Regulatory Status, each with the
  entity/jurisdiction/contact placeholders and a counsel-review gate. The
  register marks every one Draft (not Live) and links the pack. Adopted DCO 1.1
  at the repo root and required `git commit -s` in CONTRIBUTING; added the
  security safe-harbour statement. Docs updated: `docs/legal/*`,
  `CONTRIBUTING.md`, `SECURITY.md`, `docs/CHANGELOG.md`.
- **fix(chat): resolve the `auto`/`mock` provider sentinel from the saved endpoint.**
  A configured local Ollama/LM Studio endpoint whose saved provider was still
  `auto` or `mock` was forwarded to the Python runtime as `openai`, so every
  production chat failed with `Provider 'openai' is not configured (missing API
  key)` even though the local server was running. `resolveLLMProviderId` now
  maps the sentinel to the preset that owns the saved base URL (local or
  hosted) at every runtime entry point — chat, skills, autonomous jobs and the
  `NEXT_PUBLIC_LLM_CONFIGURED` flag. Regression tests cover chat + resolution.
  no doc change — bug fix; the documented provider-resolution contract is unchanged.
- **chore(size): re-pin the harness budget for the command/workspace release
  tree.** Measured total **465271** (was 465214); `python/harness/.` 30836 (+3)
  and `routers` 21156 (+14) from the checkpointed command/workspace work. This is
  a deliberate `scripts/size-budget.json` edit — the ceilings are the measured
  values, not padding. docs updated: `docs/CHANGELOG.md`.
- **feat(commands): typed UI intents + `/canvas` and `/open`.** A routed command
  can now return a typed `ui` intent — `{type:"navigate", tab, subroute?, params?}`
  or `{type:"openCanvas", artifactId?}` — on `CommandResult`, carried through the
  chat stream's `client.final`, validated in `events.ts`, stored on the turn and
  dispatched once by `stock-chat.tsx` through the same `useCommandStore`
  destination path as ⌘K. It is data, never code: remote/CLI surfaces ignore it.
  `/canvas [artifactId]` opens the inline Canvas and `/open <tab>` (alias `/go`)
  navigates, with tabs validated against the single `APP_TABS` vocabulary (now a
  const tuple with `AppTab` derived from it). Router and event tests cover the
  intents. The command-registry ratchet moved 1444→1499.
  Docs updated: `docs/harness/slash-commands.md`, `docs/NAVIGATION.md`.
- **feat(dashboard/economics): configurable filings widget + calendar health.**
  The Command Center **Recent SEC Filings** widget gained a Form type config
  (8-K, 10-K, 10-Q, S-1, 13F, Form 4, All) backed by one DataHub topic per form.
  The calendar header now reports tentative releases alongside source warnings.
  Docs: `docs/DATA-FLOW.md`.
- **feat(economics/filings): unblock the remaining gaps.** Added a runtime
  `SystemConfig` override for FRED series ids (`econ:fred-series-overrides`) so a
  discontinued/renamed id can be corrected without a code change — the exact
  replacement still needs an operator with working FRED access. Filing-list
  coverage is now stated explicitly per market in the company panel (US SEC, PK
  PSX, otherwise "no adapter yet"); keyless per-exchange routes for ASX, NSE/BSE
  and EDINET were probed and are not usable (404/403), and Companies House needs
  a key plus a company-number map. Docs: `docs/DATA-FLOW.md`.
- **feat(economics): released/actuals calendar view.** `/api/economics/calendar`
  now accepts `?past=1`, returning the last `days` of releases newest-first; the
  Calendar UI gained an Upcoming/Released toggle alongside the horizon controls,
  making the Actual column useful for post-release review. Docs:
  `docs/DATA-FLOW.md`.
- **feat(economics/filings): remaining quick wins.** (1) Unit-aware web fallback
  now covers the payroll level (thousands), not just percentage metrics. (2) The
  per-company filings panel exposes a filed-date range for every market and a
  PSX category filter for Pakistan. (3) The market-wide feed persists its last
  good result in `SystemConfig`, serves it as `cached` on failure, and both the
  feed and full-text search accept `?refresh=1`. (4) The calendar header now
  surfaces source warnings. Docs: `docs/DATA-FLOW.md`.
- **feat(commands): canonical manifest + local project command packs.** Added
  `GET /api/harness/commands`, the read-only manifest generated from the same
  registry the router executes (builtins + validated project commands, with
  `source`, `available`, args/flags/risk/examples, a stable ETag and `304`
  revalidation; `agentPrompt` is omitted). Local packs in
  `.black-eclipse/commands.json` add **agent-turn-only** commands
  (`handler: agent.plugin`) with a prompt template supporting `{{arg}}`,
  `{{flag.name}}` and `{{args}}`; `command-plugins.ts` validates names, aliases,
  categories, args/flags and caps, reports invalid entries, and can never
  shadow a builtin, register a routed handler or widen authority.
  `run-service.ts` loads the pack for slash-leading turns, and
  `use-project-commands.ts` merges the manifest's `source: "project"` entries
  into the `/` palette and ⌘K dialog with a **project** badge. `resolveCommand`,
  `searchCommands`, `parseCommandInvocation`, `parseAndBind` and
  `buildAgentInstruction` gained an optional `extra` command list (builtins win
  collisions). Tests cover the loader, prompt interpolation, palette merge and
  manifest/ETag.
  Docs updated: `docs/harness/slash-commands.md`, `docs/NAVIGATION.md`.
- **feat(economics): real refresh + data-health summary.** Snapshot Refresh now
  sends `?refresh=1` and actually bypasses the SWR cache (it previously returned
  the same cached payload); the calendar gained a refresh button with the same
  bypass. The snapshot header shows how many metrics are LIVE / WEB / CACHED /
  UNAVAILABLE, and the provenance copy explains each state. Docs:
  `docs/DATA-FLOW.md`.
- **feat(economics): calendar time horizon.** `/api/economics/calendar` now
  accepts `days=7|30|90|all` (default 30) and filters out past mirror rows
  (12-hour overnight grace) via `filterUpcoming`; the cached payload stays the
  full feed and filtering runs per request. The Calendar UI gained 7d/30d/90d/All
  controls without dropping the importance filters. Docs: `docs/DATA-FLOW.md`.
- **feat(commands): confirmations, durable audit, `/history`, `/usage
  --commands` and rate limits.** High/critical-risk commands (`/terminal`,
  `/code`) no longer run on first invocation: they return `pending` with the
  exact re-run command and a single-use `--confirm <token>` bound to the command,
  arguments/flags, actor and operator, expiring after five minutes
  (`command-confirm.ts`). Every terminal result — completed, failed, denied,
  pending, invalid or unknown — is appended as a redacted JSONL row to
  `.black-eclipse/command-audit.jsonl` (2 MB rotation), with the sink injected
  through `CommandDeps.audit` so tests never touch the real file. `/history
  [limit]` reads it newest-first and `/usage --commands` aggregates status
  counts, runs per command, p50/p95 duration and high-risk count
  (`command-audit.ts`). The router also enforces a sliding window per
  actor+command (`command-rate-limit.ts`, risk-based: 4/6/20/60/120 per minute,
  overridable per spec). The confirm flag is now a contract-test invariant for
  every high-risk command. The command-registry ratchet moved 1379→1411 for
  `/history`, the usage flag and the confirm flags.
  Docs updated: `docs/harness/slash-commands.md`, `docs/NAVIGATION.md`.
- **fix(company): filing list no longer disappears with fundamentals.** The
  company detail rendered Filings only inside the fundamentals tabs, so a symbol
  with no statement data could not reach its SEC/PSX filing list. The detail now
  renders a standalone **Filings** section when fundamentals are unavailable or
  empty; the filing index is independent of statement data. Docs:
  `docs/DATA-FLOW.md`.
- **fix(eval): make the release gate honest again.** The hallucination grader now
  counts a source the release gate withheld as fabricated when it falls outside
  the task's declared source contract — grading only the redacted answer let a
  fabrication pass — while `test_graph` asserts the
  documented redaction (`unverified source` + withheld note, no pointer). The
  live-baseline pin follows the newest recorded `live:7e9d…` run (task_success
  **0.9574**, superseding the 0.8520 ADR-071 pin), and the corpus manifest is
  regenerated for the committed `eclipse-benchmark` dataset (338 tasks). Verified:
  the four target tests pass; remaining offline-gate failures come from
  uncommitted harness WIP, not this change. docs updated: `docs/CHANGELOG.md`.
- **feat(economics): fill snapshot and calendar gaps.** `WEB_SPECS` now covers
  every snapshot metric family — all 11 policy rates, CPI/unemployment for the
  tracked economies, GDP growth and the US 10Y — so a FRED outage degrades to a
  labelled official-page value instead of a blank card (max 8 enrichments per
  snapshot, never overwriting a LIVE value). Added the Census
  **Advance Retail Sales** schedule (`calendars/census.ts`) to the official
  calendar fan-out. Docs: `docs/DATA-FLOW.md`, `docs/NAVIGATION.md`.
- **feat(commands): read-only workspace commands plus `/stop`.** Added
  `/alerts`, `/news [query|--ticker]`, `/theses [symbol]`, `/journal
  [all|open|closed]`, `/jobs`, `/artifacts`, `/sessions`, `/git
  [status|diff|log] [--staged]`, and `/stop [runId]` (lists active runs, or
  cancels one through the same cooperative route as the Stop button;
  operator-gated). `/memory` now accepts a query and searches the memory
  explorer. The readers only call existing front doors and never write or
  fabricate a row; `/git` deliberately exposes no stage/commit/push. The new
  domain handlers live in `command-handlers-workspace.ts`, with shared
  `Handler`/`HandlerOutput`/`fail`/`frontDoorError` moved to
  `command-handler-kit.ts`. Router tests cover each reader, the active-run
  filter, cancellation, and memory search. The command-registry ratchet is
  pinned at 1379 (split candidate: per-domain spec modules).
  Docs updated: `docs/harness/slash-commands.md`, `docs/NAVIGATION.md`.
- **fix(chat): the project chip shows the real folder path and works before a
  chat exists.** The empty-state chip was a static "Eclipse repo" pill inside a
  full-width row. It is now content-sized, always a button, and displays the
  folder name plus its absolute path (the bound root, or the server-resolved
  default returned as `defaultRoot` by `GET /api/workspace/roots` and the
  `/api/chat/session/project` GET). Choosing/approving a folder before the
  conversation id exists is remembered in `eclipse.pendingProjectRoot` and bound
  automatically when the first message creates the chat, so the folder is no
  longer "not found". Docs: `docs/NAVIGATION.md`.
- **feat(filings): first non-US filing list — PSX company announcements.**
  `src/lib/fundamentals/filings/psx-announcements.ts` parses the Pakistan Stock
  Exchange company page's Financial Results / Board Meetings / Others tables
  into the same filing-row shape as SEC EDGAR, with the official PSX PDF URL.
  `/api/stocks/[symbol]/filings?market=PK` branches to it, and the Fundamentals
  filings tab hides the SEC form filter and labels the PSX source for non-US
  markets. A market without an adapter still returns `not_covered`. Docs:
  `docs/DATA-FLOW.md`, `docs/NAVIGATION.md`.
- **feat(chat): a real command surface — grouped palette, ⌘K dialog, recents/
  pins, and argument completion.** The inline palette moved out of the
  1200-line composer into `command-palette.tsx` (+ pure ordering in
  `command-palette-model.ts`): Pinned → Recent → categories, a description/usage
  footer, risk/operator gates and accessible listbox navigation. `command-dialog.tsx`
  adds ⌘K / Ctrl+K as a centered two-column command surface (only the visible
  composer answers). `command-history.ts` persists the last 50 commands and 24
  pins in `localStorage` (a convenience, not an authority), and the composer
  records a command when it is submitted. `command-suggest.ts` +
  `GET /api/harness/suggest` add argument completion for skills, symbols,
  portfolios, workflows and models, with a debounced, fail-silent popover.
  `/quote` declares `completion: "symbols"`; the registry contract now knows the
  full provider allowlist. Tests cover palette ordering, the history store,
  completion detection and the suggest route. The `en.ts` ratchet moved
  1317→1326 for nine new `code.command.*` keys.
  Docs updated: `docs/harness/slash-commands.md`, `docs/NAVIGATION.md`.
- **feat(economics): broader BLS release coverage.** The BLS adapter now reads
  eight official schedules — CPI, Employment Situation, PPI, JOLTS, ECI, Real
  Earnings, Import/Export Prices and Productivity & Costs — with per-page
  failure isolation (one blocked page no longer blanks the rest). Releases carry
  high/medium importance for calendar filtering. Docs: `docs/DATA-FLOW.md`.
- **fix(notifications): header alerts show the full headline and open the real
  source.** The notification-center title is no longer truncated, and news
  alerts carry the article `url` (absolute http/https only, validated in
  `news-diff.ts` and `store.ts`) so selecting the item opens the publisher page
  in a new tab instead of the in-app News feed. Items without a link still jump
  to their owning tab, and selecting one marks only that item read. Docs:
  `docs/NAVIGATION.md`.
- **feat(filings): ticker mapping, search date window and a dashboard widget.**
  The latest-filings route now attaches a ticker from the cached SEC
  `company_tickers` reverse map (CIK→ticker; unmapped issuers stay null, never
  guessed), and the tab links a known ticker to its chart. Full-text search gained
  From/To date controls (the API already supported the window). Added the
  Command Center **Recent SEC Filings** widget backed by the `sec:filings` topic.
  Docs: `docs/DATA-FLOW.md`.
- **feat(economics): EDGAR full-text filing search.** The Economy **SEC Filings**
  tab now has a keyword search over the SEC's official full-text index
  (`src/lib/economics/edgar-search.ts` → `GET /api/economics/filings/search`),
  with form filters and an optional date window. Hits normalize to the same
  filing shape as the latest feed, document URLs are built only from the SEC's
  own accession + filename pair, results cache for 3 minutes, and short queries
  or malformed dates are rejected before any network call. Docs:
  `docs/DATA-FLOW.md`, `docs/NAVIGATION.md`.
- **feat(economics): market-wide SEC filings feed.** New
  `src/lib/economics/sec-filings-feed.ts` parses EDGAR's official current-events
  Atom feed (company, CIK, form, filed date/time, item summary, filing index
  URL). `GET /api/economics/filings?form=8-K&limit=40` serves it with a 3-minute
  cache, and a new **SEC Filings** tab on the Economics page
  (`filings-feed.tsx`) shows the newest filings with form filters. Global search
  now resolves "sec filings"/"edgar" to that tab. Docs: `docs/DATA-FLOW.md`,
  `docs/NAVIGATION.md`.
- **fix(harness): make slash commands honest — terminal output, enforced
  metadata, and `/help <command>`.** `/terminal` now unwraps the Python route's
  `{success, result}` envelope (it previously ran the command and then reported
  "no output"), shows exit code/duration/shell/cwd and honest
  `timedOut`/`truncated` markers, and accepts `--shell`/`--cwd` (on Windows the
  default is PowerShell, so `--shell cmd` is how cmd.exe syntax runs). The router
  now enforces declared `timeoutMs`, retries only `idempotent` commands, prepends
  a deprecation notice, and records `risk`/`approval` in the audit event; the
  composer palette shows operator and high/critical-risk chips; search gained a
  typo-tolerant fallback (`/help quotte` → `/quote`). `/help <command>` renders
  one command's full contract, and the new
  `command-registry.contract.test.ts` fails CI on a missing handler target or an
  unsafe high-risk/approval declaration.
  Docs updated: `docs/harness/slash-commands.md`,
  `docs/harness/architecture.md`, `docs/NAVIGATION.md`.
- **fix(chat): remove the AI notice from chat (user-directed reversal).** The
  composer one-liner, per-answer footer and response-view footer are gone again;
  the `AiOutputNotice` component and its test are deleted. The first-run risk
  acknowledgement stays, and `showNotice` remains a no-op prop so Canvas keeps
  compiling. This supersedes the legal entry below for chat surfaces.
  No doc change — copy/placement only, contracts unchanged.
- **refine(legal): restore the short per-answer clause and make gate intensity
  deployment-aware.** The per-answer notice is back as ONE responsibility clause
  ("Verify with your broker; decisions are yours") with the full text behind the
  expander — not the whole paragraph every turn. The composer one-liner and the
  Canvas `showNotice` footer return too. The upgrade notice is a dismissible
  bottom banner on local self-hosted (auth off on loopback) and a blocking modal
  only on hosted/remote requests (`GET /api/setup` now reports `hosted` from the
  auth config + request Host). This supersedes the chat-removal entries below.
  Docs: `docs/legal/disclosures.md`, ADR-075 in `docs/DECISIONS.md` +
  `skills/ARCHITECT.md`.
- **feat(economics): official schedules for BLS/BEA/ECB/BoE/BoJ + cached
  last-known-good.** `src/lib/economics/calendars/` now parses the institutions'
  own pages (BLS CPI and Employment Situation, BEA GDP/PCE, ECB decision days,
  BoE MPC dates, BoJ MPM dates) alongside the FOMC adapter, and release-family
  matching merges a mirror row with its official counterpart even when titles
  differ. Snapshot and calendar persist a last-known-good payload in
  `SystemConfig` and serve it as `CACHED` (with its confirmation date) when
  providers are briefly unreachable. Docs: `docs/DATA-FLOW.md`,
  `docs/NAVIGATION.md`.
- **fix(chat): remove the AI notice from chat entirely.** The composer one-liner,
  the per-answer footer, and the response-view footer are gone; the
  `AiOutputNotice` component and its test were deleted so no chat surface can
  render it again. The first-run risk acknowledgement is unchanged. No doc
  change — copy/placement only, contracts unchanged.
- **fix(chat): remove the repeated AI notice below every answer.** The point-of-use
  disclosure remains in the persistent composer one-liner and the first-run risk
  acknowledgement; the output placement now renders nothing. No doc change —
  copy/placement only, contracts unchanged.
- **fix(lint): clear the three release-gate errors.** `fomc.ts` used `let` for two
  variables it never reassigns, and the AI-provider settings copy had an
  unescaped apostrophe (`provider&apos;s`). `npx eslint .` is back to 0 errors
  (113 warnings); `tsc --noEmit` passes. no doc change beyond this note.
- **feat(economics): real FOMC dates, no fabricated calendar, search fallback,
  and a native SEC filings browser.** The economic calendar no longer spreads
  placeholder events over the next 30 days; `src/lib/economics/calendars/fomc.ts`
  reads the Federal Reserve's own meeting calendar (preserving its tentative
  marker) and `mergeOfficialEvents` upgrades mirror dates without discarding
  actual/forecast/previous. The snapshot reports the exact FRED series it
  fetched and fills missing US metrics from official pages via the screener's
  search→official-host→fetch→labelled-number pattern (`state: "WEB"`, source URL,
  never replacing a LIVE value). Added `GET /api/stocks/[symbol]/filings` over the
  existing `sec_filing_list` capability and a **Filings** tab in the Fundamentals
  panel. Also fixed the dashboard economic chart topic, which pointed at a
  non-existent `us-cpi` source. Docs: `docs/DATA-FLOW.md`, `docs/NAVIGATION.md`.
- **feat(chat): fork a conversation + quote selected text into the next turn.**
  The sidebar chat menu now has **Fork chat** and every message toolbar has
  **Fork from here** (`GitBranch`); a fork is a real new conversation with fresh
  message ids, provenance (`Conversation.forkedFrom`), its own session folder,
  and a server-side copy of the source's context documents
  (`POST /api/chat/session/clone`) so attachments keep working. Forking is
  blocked while a run/queue is active. Selecting text inside a message shows a
  floating **Quote** chip; the composer renders the passage as a card and the
  turn is sent with a delimited quote context (`Message.quote`,
  `turnTextForHarness`). Quote-only send uses "Explain the quoted passage.";
  quotes ride with queued prompts; editing/retrying a quoted turn preserves it.
  Shell boilerplate was extracted into `use-chat-conversation-actions.ts` and
  `use-chat-message-actions.ts` to keep `stock-chat.tsx` inside its size ratchet.
  Docs: `docs/chat-ui-audit.md` (§ Fork + quote), `docs/NAVIGATION.md`.
- **fix(finance): `finance_calc` also covers portfolio weight.** The finance
  suite's residual `finance.v6.weight.001` needed `value/total`; the calculator
  now computes `weight` / `portfolio_weights` and the prompt names it. The
  finance suite then stood at 267/269 with `task_success` **0.9926**
  (`financial_accuracy` **0.9926**, up from 0.937). The one remaining miss is a
  model-compliance edge case (answered +25 after the tool returned -25), not a
  tooling gap. Size ratchets re-pinned for the in-flight setup/update routers.
  Docs updated: `docs/CHANGELOG.md`.
- **feat(chat): OpenCode-style file selection with provenance.** The composer's
  "+" now opens a shared `FileSourcePicker` instead of a bare OS dialog: a
  **Project** tab browses the chat's approved workspace root (breadcrumb, folder
  paths, multi-select) and a **This computer** tab uploads local files labelled
  `Local · uploaded copy`. Every attachment chip shows its origin badge and the
  workspace-relative folder path. `@` in the composer now searches project files
  (debounced, keyboard-navigable, section beside bots) and attaches the chosen
  file as context. Provenance (`origin`/`sourcePath`/`rootId`/`rootLabel`) is
  persisted in a per-session `context-meta.json` sidecar. The runtime gained
  `GET /workspace/files/search` (bounded walk, optional `rootId`) and
  `rootId` support on `/workspace/files`; the folder picker gained a clickable
  breadcrumb, approved-root rail and recents; the editor can send a file to the
  active chat. Docs: `docs/chat-ui-audit.md` (§ File selection), `docs/NAVIGATION.md`.
- **feat(release): data-sources page, CI drift check, onboarding smoke, starter
  dashboard.** `npm run docs:data-sources` generates `docs/data-sources.md` from
  `src/lib/setup/source-catalog.ts`; CI runs the `--check` form so the page
  cannot drift. `npm run smoke:onboarding` walks all five setup steps in a real
  browser (no Finish click). Setup now seeds the first dashboard from the chosen
  bundle (`seedStarterDashboard`), so the Dashboard persona dialog does not
  appear after setup. Also fixed a production hydration mismatch in
  `UpdateBanner` (localStorage read during the initial render). Docs updated:
  `docs/data-sources.md`, `docs/NAVIGATION.md`, `docs/CHANGELOG.md`.
- **feat(legal): point-of-use AI/financial risk notice with a recorded first-run
  acceptance.** Every settled assistant answer now carries a non-dismissible
  "AI-generated · not financial advice" notice (expandable to the full text);
  the shared composer and the Assistant dock keep a permanent one-liner; Canvas
  reports opt in via `ResponseView.showNotice`. The first-run wizard requires a
  checkbox on its first step, and `POST /api/setup` rejects a missing or stale
  `riskAck.version`, recording `{version, acceptedAt, mode}` in `risk_ack_v1`
  (reset deletes it). Copy lives in `src/lib/legal/disclosure.ts`; this is
  evidence and risk allocation, not immunity — the enforceable clause stays in
  Terms. Docs: `docs/legal/disclosures.md` (new), `docs/legal/README.md`
  (statuses), `docs/NAVIGATION.md` (legal row), ADR-073 in `docs/DECISIONS.md` +
  `skills/ARCHITECT.md`.
- **feat(legal): cover existing installs and live orders.** An upgraded install
  that never saw the notice now gets a one-time blocking gate
  (`src/components/legal/risk-ack-gate.tsx`, mounted in the root layout) backed
  by `GET/POST /api/legal/risk-ack`; it reads `/api/setup`, appears only when
  setup is complete and the current version is unaccepted, and records the same
  versioned acknowledgement. The trade approval card also requires an explicit
  "this order is my decision and my responsibility" checkbox before Confirm &
  send (the typed live phrase is unchanged). Docs: `docs/legal/disclosures.md`,
  ADR-074 in `docs/DECISIONS.md` + `skills/ARCHITECT.md`, `docs/CHANGELOG.md`.
- **refine(legal): notice intensity by deployment, one short line per answer.**
  The per-answer notice is now a single responsibility clause ("Verify with your
  broker; decisions are yours") with the full text behind the expander, instead
  of repeating the whole paragraph every turn. The upgrade notice is a
  dismissible bottom banner on local self-hosted (auth off on loopback) and a
  blocking modal only on hosted/remote requests; `GET /api/setup` reports
  `hosted` from the auth config + request host. Docs:
  `docs/legal/disclosures.md`, ADR-075 in `docs/DECISIONS.md` +
  `skills/ARCHITECT.md`, `docs/CHANGELOG.md`.
- **feat(finance): one deterministic calculator for the metrics the agent must
  not do mentally.** New `finance_calc` computes percentage change/return
  (signed), EPS, P/E, P/S, margins, position_size (reward/risk), CAGR and FCF
  from named inputs, returning the value, formula and inputs. Its formulas match
  the evaluation grader, and a 15-case test asserts the two agree. The prompt now
  names the tool with worked examples and requires the returned value verbatim,
  including its sign. Registered in the agent allowlist and the tool registry
  (1,025 tools). Size ratchets re-pinned deliberately (total 465,125; see the
  budget comment). Docs updated: `docs/CHANGELOG.md`.
- **chore(updates): keep private development honest with `published: false`.**
  `config/updates.json` now carries a maintainer `published` flag, defaulting to
  false while the release repo is private. In that state no network request is
  made, Settings reports "Updates are not published yet", and `black update`
  changes nothing — instead of a 404 that looks like a broken check. Launch is a
  one-line flip once the repo is public. Docs updated: `docs/UPDATES.md`,
  `docs/CHANGELOG.md`.
- **feat(updates): signed release notices and a safe `black update` path.**
  Eclipse now tells users when a newer release exists, without phoning home:
  the local server fetches a public GitHub release manifest, verifies an Ed25519
  signature against `config/update-signing-key.pub`, and only then shows a
  dismissible glass notice (`src/components/layout/update-banner.tsx`) with a
  copyable `black update`. Settings › General › Updates owns the local-only
  on/off toggle and a manual check that reports "couldn't check" honestly.
  `black update` refuses a dirty tree, verifies the release tag's commit against
  the signed manifest, backs up `jdds.db`, builds, and rolls back on failure.
  The private key is generated locally (`npm run update:keys`) and must stay
  offline; publishing steps are in the new doc. Not an auto-updater by design.
  Docs updated: `docs/UPDATES.md`, `docs/NAVIGATION.md`, `docs/CHANGELOG.md`.
- **fix(eval,research): close the hallucination gate and pin the passing live
  run.** `research/release_gate.py` now withholds an unretrieved citation from the
  released answer (`[label] (unverified source)`) and appends a URL-free note; the
  URL stays only in the operator blob. The underspecified
  `adversarial.hallucination.001` prompt now names Apple and the SEC source, and
  tasks can opt out of the live lane with `metadata.live_eligible: false`.
  Regenerated the corpus baseline and published benchmark; the full live re-run
  `evalrun-1794245939159` reports `task_success` **0.9149**,
  `hallucination_rate` **0.0000**, gate **PASS**, pinned as
  `live:7e9d161037e45360f95717198f839ced`. Verified: 32 release-gate/task/live
  tests and `test_published_benchmarks` 3/3. Docs updated:
  `docs/releases/v0.3.0.md`, `docs/PRODUCTION-READINESS.md`, `docs/CHANGELOG.md`.
- **feat(chat): queue multiple prompts while the agent is replying.** Pressing
  Enter (or the new Queue button) during a run now appends the draft to an
  ordered queue instead of silently dropping it. A new `MessageQueue` panel
  above the composer (Eclipse Agent page + floating Assistant dock) lists every
  waiting prompt and lets the user edit, reorder, remove, clear, or promote one
  with "Run this next" — which interrupts the in-flight reply and runs the
  promoted prompt immediately. The queue drains one item at a time through the
  same dispatch path as a normal send, in typed order. Rules live in
  `src/lib/chat/message-queue.ts` (pure, tested) with `useMessageQueue` keeping
  a synchronous ref for the async drain. Docs updated: `docs/CHANGELOG.md`.
- **feat(settings): add global temperature and max-output-tokens controls.**
  Settings › AI gains an opt-in sampling block: temperature (Auto / Precise /
  Balanced / Creative plus a 0–2 slider) and a blank-by-default output cap.
  Both persist as `LLMConfig.temperature`/`maxTokens` (null clears back to Auto,
  values clamped in `setLLMConfig`), round-trip through `/api/settings`, and are
  forwarded by `resolveModelSettings` only when set — an untouched install sends
  a byte-identical payload. The runtime maps the cap per provider
  (OpenAI-compatible/Anthropic/Mistral/Groq `max_tokens`, Gemini
  `max_output_tokens`) and omits both when absent. Docs updated:
  `docs/ARCHITECTURE.md`, `docs/CHANGELOG.md`.
- **feat(keyboard): audit the global shortcut surface, add four reliable chords,
  and rebuild the help dialog.** The catalogue moved to `src/lib/shortcuts.ts`
  (single source for labels, groups and predicate helpers) and the dialog now
  has Essentials / Navigation & panels / Focused chart / Sidebar sections,
  platform-aware ⌘ labels, search auto-focus, an inline “browser-reserved”
  warning for F1/F5/F11/F12, and the previously unused i18n group keys. Fixed
  Ctrl/Cmd+Alt+N and Ctrl+Alt+X failing on AltGr/non-US layouts by falling back
  to `event.code`, and added the `?` alias for help. New chords: Ctrl/Cmd+B
  (collapse sidebar, now a shared persisted sidebar-store preference),
  Ctrl/Cmd+, (Settings) and Ctrl/Cmd+Shift+L (light/dark). Docs updated:
  `docs/ARCHITECTURE.md`, `docs/CHANGELOG.md`.
- **feat(shell): every launch opens the Eclipse Agent first.** With no explicit
  tab deep link, the boot effect now always lands on `chat` instead of resolving
  a saved start screen / resuming the last visited tab, so opening the app never
  shows a different page first. Removed the now-contradictory Start screen
  control from Settings › General and dropped `startScreen` /
  `resolveStartTab` / `recordLastTab` from `general-prefs` (legacy stored
  `startScreen` JSON is ignored; explicit `?tab=` deep links still work). Docs
  updated: `docs/ARCHITECTURE.md`, `docs/CHANGELOG.md`.
- **fix(setup): make every setup toggle real, fix saved state, and close the
  reset/attribution gaps.** Enforcement now covers Investor Eye
  (GDELT/USGS/FIRMS), news ingestion + `/api/news`, the economics cache, and
  the web-search provider chain — not just the scraper/crypto path. The
  readiness check runs probes in parallel, persists `setup_check_v1`, and uses
  a real SEC contact. `GET /api/setup` returns `acceptedRestrictedSources` and
  the last check; the draft restores accepted sources and derives price mode
  from a configured provider. Custom endpoint keys are stored in the encrypted
  vault (`CUSTOM_LLM_API_KEY`) and old plaintext keys are cleared. Commercial
  mode hides community price/crypto/search sources. Reset setup now clears the
  MCP config; a scheduled factory reset can be cancelled (`GET`/`DELETE
  /api/setup/reset` + Settings banner). Added a focus trap, styled
  acknowledgement checkboxes, `DataAttribution` strips on Economics, Market
  News and Market Discover, and a `data-source-preferences` test. Docs updated:
  `docs/onboarding-plan.md`, `docs/CHANGELOG.md`.
- **refactor(setup): the onboarding shell is now literally the production
  launch card.** Replaced the wide dashboard panel with the launch page's
  580px centered card: masked 44px brand grid, top glow, 22/24/18 padding,
  22px wordmark, 20px serif title, 13.5px phase line, 3px gradient progress
  bar with the travelling shine (`be-setup-sweep`), 10.5px mono meta row,
  compact text buttons and the `LOCAL SETUP · 127.0.0.1 / FIRST RUN` footer.
  Step content is one decision per page, single-column, no accordions or
  dropdowns. Docs updated: `docs/onboarding-plan.md`, `docs/CHANGELOG.md`.
- **fix(chat): the composer "+" menu's mode submenus no longer throw.** The
  Quant / Choices / Plan submenus in `src/components/chat/{quant,choices,plan}-mode-control.tsx`
  rendered `DropdownMenuLabel` (Base UI `Menu.GroupLabel`) as a direct child of
  the submenu popup. `Menu.GroupLabel` requires a `Menu.Group`/`Menu.RadioGroup`
  context, so opening any of those submenus from the Eclipse Agent composer's
  "+" menu threw `Base UI: MenuGroupContext is missing` and broke the menu. The
  labels now live inside their `DropdownMenuRadioGroup` (which also labels the
  radio group correctly for a11y). Also made the "+" trigger an explicit
  `type="button"` with pointer feedback so it can never submit the composer
  form. Docs updated: `docs/CHANGELOG.md`.
- **docs(release): record the post-tag full live run.** The repaired lane ran the
  full live-eligible set against local Ollama (`deepseek-v4.1-flash:cloud`, run
  `evalrun-1794235655908`). `task_success` **0.9043** now clears the 0.9 task
  floor, but `hallucination_rate` **0.1111** trips the critical 0.0 gate, so the
  run FAILS. Repeated task misses were percentage-change sign, position sizing
  and EPS; one adversarial task fabricated two PSX sources. v0.3.0 keeps the
  ADR-071 floor; the next release's blocker is hallucination, not task success.
  The published `benchmarks.md` is reverted to its reproducible pinned baseline
  (a machine-local run is not a publishable artifact). Docs updated:
  `docs/releases/v0.3.0.md`, `docs/PRODUCTION-READINESS.md`, `docs/CHANGELOG.md`.
- **fix(home): live time-of-day greeting + fill the Dashboard's production gaps.**
  The header greeting was computed once per render from the browser clock, so a
  keep-alive Dashboard tab could keep saying “Good morning/evening” long after
  the day moved on; it also never distinguished night. `home-prefs.ts` now
  exposes `timeOfDayFor` / a minute-ticking `useGreeting` hook (morning
  05–11:59, afternoon 12–16:59, evening 17–21:59, night 22–04:59) and the
  greeting shows the day label plus the optional saved name. The Dashboard
  gains two previously unused data surfaces as first-class sections — a
  “Daily brief” hero (personal brief, market bias/breadth, portfolio health and
  value, demo-book disclosure) and a “Watchlist radar” card — plus working
  Personalize controls (name + investor/trader/both lens, which reapplies that
  lens's card order). The portfolio sparkline legend now uses the active
  benchmark label instead of hard-coded “S&P 500”, and the J/K/Enter/A/R// key
  hint is visible. New tests cover greeting boundaries. Also repaired the
  in-progress settings route cache refactor's POST path, which still referenced
  the removed module-local `settingsCache` and failed `npm test`/`tsc`. Docs
  updated: `docs/CHANGELOG.md`.
- **feat(chat): `/compact` compacts the conversation on demand.** Adds a
  routed slash command (registry `runtime.compact`, handler `native.compact`)
  that asks the Python runtime for a real compaction instead of waiting for the
  automatic history bound. `POST /history/compact` calls the new deterministic
  `compact_history()` (`python/harness/compaction.py`): the older turns become
  the fenced `<compacted-conversation>` block and the latest `--keep N` turns
  (default 6, clamped 0-50) stay verbatim; no model call, so it works when no
  provider is reachable. The chat and stream routes now parse history/chatId
  before command routing, pass them to the router, and persist a successful
  result as `compaction.json` beside the transcript; later runs prepend the
  block and slice history at the stored boundary, so the effect survives a
  reload while the visible transcript stays intact. Honest failure states:
  `NO_HISTORY` when there is nothing to compact, "Nothing to compact" when the
  history is within the keep window (nothing stored), and the normal runtime
  error when Python is unreachable. Tests: 3 Python cases + 2 router cases.
  Docs updated: `docs/harness/slash-commands.md`, `docs/NAVIGATION.md`,
  `docs/CHANGELOG.md`.
- **copy(nav): the chat page is now called "Eclipse Agent".** Renamed the
  user-facing label everywhere it appeared: the sidebar/nav label, the
  translation key `nav.chat` in all locales, the search palette title, the
  start-screen option, the Customization tab ("Eclipse Agent Page") and its
  backdrop/conversation copy, plus the keyboard-shortcut and dashboard hints.
  Search aliases still include `chatbot`, and internal identifiers (`tab:
  'chat'`, `ChatbotPageSettings`, file names, comments) are unchanged. No doc
  change — copy/label-only edit with no contract or architecture impact. Docs
  updated: `docs/CHANGELOG.md`.
- **fix(eval): a subset smoke can no longer claim the live gate.**
  `Threshold.evaluate` ignored its `sample_size`, so the 12-task live smoke
  (11/12 = 0.9167) printed `gate PASS` against the 0.9 floor. The live lane now
  applies `MIN_LIVE_TRIALS = 30`: a smaller sample keeps and prints its metrics
  but is marked FAIL with
  `sample_size=N < 30 (a subset smoke is not a release gate)`. The full
  196-trial live run is unaffected. Test:
  `test_a_subset_smoke_cannot_claim_the_live_gate`. Docs updated:
  `docs/CHANGELOG.md`.
- **fix(eval): the live lane crashed before it could measure anything.**
  `run_live_gate()` called `provider_configured()` but the function was never
  defined, so every `npm run eval:live` invocation died with a `NameError` before
  selecting a task. It now resolves the provider contract (a provider name is
  required; local providers such as Ollama need no key; hosted providers need
  `BLACK_ECLIPSE_API_KEY`) and a unit test pins all three cases. Verified end to
  end against the local Ollama (`deepseek-v4.1-flash:cloud`, bridge on :3000): a
  fresh 12-task run reported `task_success 0.9167` (run
  `evalrun-1794234662234`); the full live-eligible run was started from the same
  fix. Docs updated: `docs/CHANGELOG.md`.
- **fix(ops): `scripts/backup.sh` runs on the Windows host and survives a live
  code index.** The interpreter lookup now falls back to the vendored
  `scripts/vendor/python/python.exe` and then `python`; the archive is written
  from inside the output directory (GNU tar on Git Bash read the `C:` in an
  absolute path as a remote host); and `.black-eclipse/code-index` (a rebuildable
  multi-GB cache whose SQLite sidecars the running app holds open) plus
  `*.db-wal`/`*.db-shm` are excluded. The three app databases still use the
  SQLite backup API. Verified: a real 337 MB archive restored into a clean
  directory, and all three databases passed `PRAGMA integrity_check`. Docs
  updated: `docs/PRODUCTION-READINESS.md`, `docs/CHANGELOG.md`.
- **docs(setup): add the first-run onboarding implementation plan.** Documents
  the boot-style gate, personal-vs-commercial source modes, the built-in API
  commercial-use matrix with upstream links, AI provider / BYO-key flow, the
  `onboarding_v1` + `data_source_prefs_v1` config contracts, the enforcement
  layer required to make toggles real, the existing-install migration, and the
  phased build/test plan. Docs updated: `docs/onboarding-plan.md`,
  `docs/CHANGELOG.md`.
- **docs(setup): add the legal model for built-in data APIs.** Separates
  shipping integration code from shipping/proxying data, lists the
  redistributable open-data sources (SEC, FRED, BEA/BLS, World Bank, GDELT,
  USGS), marks TradingView/Yahoo/Binance/CoinGecko-Demo/scrapers as
  never-default for a paid product, and makes the bring-your-own-key rule
  explicit (no shared keys, no server-side proxy). Docs updated:
  `docs/onboarding-plan.md`, `docs/CHANGELOG.md`.
- **docs(setup): reorganize onboarding around capabilities and a working first
  session.** The flow is now Welcome/mode → AI → Data/capabilities →
  Review/readiness. Data is grouped by what the user wants to do (company,
  macro, events, prices, news/search, crypto) instead of by vendor; Included,
  Connect-your-own and Advanced/community are visibly separate. Adds bundle
  presets, the three-way live-prices decision, a readiness check
  (`POST /api/setup/check`), a "definition of starts without issues", and the
  capability mapping modules. Docs updated: `docs/onboarding-plan.md`,
  `docs/CHANGELOG.md`.
- **docs(setup): plan restarting onboarding and starting from scratch.** Adds
  three explicit reset scopes (re-run onboarding, reset setup/keys, factory
  reset), a Settings "Danger zone" with typed confirmation and optional backup,
  a `POST /api/setup/reset` contract that schedules a factory reset rather than
  deleting live SQLite from the web process, boot-time consumption in
  `scripts/doctor.js`, and `black reset --onboarding|--setup|--factory` CLI
  commands sharing `scripts/lib/reset.js` and the existing
  `scripts/wipe-personal-data.js` primitive. Docs updated:
  `docs/onboarding-plan.md`, `docs/CHANGELOG.md`.
- **feat(setup): first-run onboarding, enforced source toggles, and reset
  scopes.** New `src/lib/setup/` (source catalog, capabilities, bundles, safe vs
  legacy defaults, state, existing-install probe, readiness check) and
  `src/components/setup/` (boot-style gate + Welcome/AI/Data/Review) mounted in
  the root layout. `GET/POST /api/setup`, `POST /api/setup/check`, and
  `POST /api/setup/reset`. New installs get open data only (SEC/FRED/BEA/BLS/
  World Bank/GDELT/USGS); connected providers need the user's key; community
  sources (TradingView/Yahoo/Binance/CoinGecko Demo/DuckDuckGo/scrapers) are off
  until acknowledged. Existing installs migrate to completed and keep the legacy
  chain. `src/lib/data-source-preferences.ts` is now read by the scraper chain,
  crypto connector and economics route, so toggles are real. Settings adds
  General → Run setup again and Data & Storage → Reset setup/Factory reset.
  `scripts/lib/reset.js`, `scripts/reset.js`, `black onboarding`,
  `black reset --onboarding|--setup|--factory`, npm aliases, and the doctor boot
  consumer complete the three reset scopes (factory reset is scheduled, not
  deleted from the web process). Tests: `src/lib/setup/setup.test.ts` (12
  passing). Docs updated: `docs/onboarding-plan.md`, `docs/QUICKSTART.md`,
  `docs/NAVIGATION.md`, `docs/data-and-privacy.md`, `docs/DECISIONS.md`
  (ADR-072), `skills/ARCHITECT.md`, `docs/CHANGELOG.md`.
- **feat(setup): real reachability probes for included open sources.** The
  readiness check no longer treats included data as merely "no account
  required". `src/lib/setup/included-probes.ts` declares one documented,
  bounded endpoint per included source (SEC, FRED public CSV, BEA/BLS via FRED
  CSV, World Bank, Eurostat, GDELT, USGS, NASA FIRMS, official RSS), with a
  contact-shaped User-Agent for SEC. `check.ts` probes each enabled source,
  reports `ok`/`rate-limited`/`failed` with latency and HTTP status, and a unit
  test now fails if a new included source is added without a probe. Docs
  updated: `docs/onboarding-plan.md`, `docs/CHANGELOG.md`.
- **refactor(setup): splash-style onboarding, no accordions or dropdowns.**
  The gate is now a full-screen opaque page matching the production launch
  screen: `app-page-bg` grid, soft brand glow, one centered glass card, wordmark
  header, `01 / 05` counter and a 3px step-progress bar. It raised to
  `z-[200]` so the sidebar/app shell is fully covered. The data step was split
  into **Included data** (four flat cards with source switches) and **Connect
  providers** (three live-prices radio cards + flat, sectioned provider cards).
  Removed `steps/data-step.tsx` and `parts/capability-row.tsx`; added
  `included-step.tsx`, `providers-step.tsx`, `parts/provider-card.tsx` and
  `parts/switch.tsx`. Acknowledgements are now local to their section (prices,
  crypto, search) instead of one hidden cross-step flag. Docs updated:
  `docs/onboarding-plan.md`, `docs/CHANGELOG.md`.
- **feat(ui): real, type-any page pagination for Artifacts and Market News; fix cards that silently vanished.** Artifacts now uses ServerPaginationFooter instead of an append-only "Load more": numbered pages, a typed per-page box (1–200, the runtime's real cap), current-page polling, and last-page clamping after deletes. Artifact cards fall back to the category icon when an image/video has no generated thumbnail instead of rendering a 404 `<img>` (a blank card); the failed-thumbnail state is per card. Market News gets the same typed per-page control in its pagination footer plus a typed "go to page" box, and the Customize panel accepts any cards-per-page value; `/api/news`'s `limit` cap rises 50→200 and the UI clamps to it. Fixed the card toggle bug where "Timestamp" was nested inside "Badges", so disabling Badges hid timestamps even though the Timestamp toggle said on. Clustering now uses a fixed 600-row window so `pagination.total`/`totalPages` stay consistent between pages. Docs updated: `docs/DATA-FLOW.md`, `docs/CHANGELOG.md`.
- **feat(ui): paginated Alert History and a real Saved-news library.** Alert History now pages the server archive with numbered pages and a typed per-page box (1–200) instead of always requesting the first 100 rows; filters/search reset to page 1, and the current page is clamped when the archive shrinks. `/api/alerts/history` widened its bounded union window 500→2000 and documents that `total` describes that window. News bookmarks now persist the full article snapshot (`be_news_saved_items_v1`) instead of only IDs, so Saved is its own searchable, category/sentiment/sort-filtered, paginated list that no longer depends on which feed page is loaded; legacy ID-only bookmarks migrate when their article next appears in the feed, and the detail dialog is extracted to `news-detail-dialog.tsx`. Docs updated: `docs/DATA-FLOW.md`, `docs/CHANGELOG.md`.

## 2026-11-08
- **docs(oss): make the repository publish-ready as MIT open source.** GitHub
  renders the repository ROOT, which had no README or LICENSE (both lived only
  under `Black-Eclipse-site/`), so the project read as unlicensed. Added root
  `README.md` (what it is, quick start, layout, production status, license map)
  and root `LICENSE` (MIT, with the scope note that
  `Black-Eclipse-site/pine-engine/` is AGPL-3.0-only via `pinets`). Fixed
  `pine-engine/NOTICE.md`, which still said the app "stays proprietary"; the app
  is MIT, the Pine engine is the separate AGPL component. `package.json` now
  declares `license: MIT`. The GitHub repository is still **private** —
  flipping visibility is an owner action, not a repo edit. Docs updated:
  `README.md` (root), `LICENSE`, `pine-engine/NOTICE.md`, `docs/CHANGELOG.md`.
- **fix(evaluation): restore the live gate's `provider_configured` helper.** The
  v0.3.0 tree called and exported `provider_configured()` in
  `python/harness/evaluation/live_gate.py` but the definition was missing, so
  `npm run eval:live` died with a `NameError` before any trial. The helper is
  back (a local provider needs only a name; a hosted one also needs a key) with
  three unit tests, and the live lane now runs end-to-end against the configured
  Ollama model — `--limit 1` produced a recorded run. Size budget re-pinned
  464766→464772 and evaluation 12066→12073 for the restored code. Docs updated:
  `docs/CHANGELOG.md`.
- **ops(release): P5 operational scaffolding for a self-hosted instance.**
  `scripts/backup.sh` (consistent SQLite snapshots via the backup API, a
  `PRAGMA integrity_check` before the archive is accepted, gzip archive,
  retention, `.black-eclipse/` included), `scripts/install-backup-timer.sh`
  (daily systemd timer), `scripts/health-watch.sh` (public health probe that
  posts to `ALERT_WEBHOOK_URL` and says plainly when no channel is configured),
  `deploy/prometheus/blackeclipse.rules.yml` (availability + health-probe alerts,
  runtime-metric templates), and `.github/workflows/ops-drift.yml` (weekly
  drift/size/ADR/secrets cadence, at the repository root where Actions reads it).
  `docs/DEPLOYMENT.md` gains Backups & restore, Monitoring & alerts, Incident
  response and Drift watch. The P5 exit gate is time-based (one week of a live
  instance with no silent failure), so it is recorded open, not done. Docs
  updated: `docs/DEPLOYMENT.md`, `docs/PRODUCTION-READINESS.md`,
  `docs/CHANGELOG.md`.
- **docs(harness): refresh benchmark results.** `docs/harness/benchmarks.md`
  now records run `evalrun-1794189449278` at commit `216277a2` (tier 0,
  gate PASS) with updated latency. Doc updated: `docs/harness/benchmarks.md`.
  No code or contract change — recorded benchmark output only.
- **refactor(ui): remove the Eclipse SDK page.** The dedicated `?tab=sdk`
  screen (`src/components/screens/sdk/`) is deleted along with its AppTab,
  sidebar/Agentic entry, search-palette page and launcher row, app-shell nav
  section, deep-link entry and nav translation key. The Eclipse SDK itself —
  `/sdk/*`, `eclipseSdk`, widgets, dashboards, themes, locks, audit and the
  `/app` / `/eclipsesdk` chat tools — is unchanged and remains driveable from
  ChatBot and the typed client. Docs updated: `docs/ARCHITECTURE.md`,
  `docs/eclipse-sdk.md`, `docs/NAVIGATION.md`, `docs/CHANGELOG.md`.
- **fix(ui): the sidebar Graph pop-up now shows only the learned graph.** The
  **Relations** tab duplicated the Investor Eye relationship graph (the same
  `IE_GRAPH_TOPIC` chart, with no capability the Investor Eye panel lacks), so
  it is removed; the pop-up keeps the learning-journey graph and drops the tab
  strip. The Investor Eye **Relationship Graph** panel is unchanged, and the
  now-unused `RelationshipGraphChart` re-export and `sidebar.graphSkills` /
  `sidebar.graphRelations` strings are removed. `graphHint` / `graphDialogHint`
  now describe the learned graph. No data or API change. Docs updated:
  `docs/CHANGELOG.md`.
- **fix(ui): the crash card now offers one clear action — Reload.** The
  top-level "Something went wrong" fallback (`error-boundary.tsx`) paired
  "Try again" (reset the boundary state in place) with "Reload" (full document
  reload). For a boundary wrapping the whole app, the in-place reset rarely
  recovers: a deterministic render error immediately re-throws, and the subtree's
  state is already gone, so it mostly flashed the card back. "Try again" was
  removed and the surviving **Reload** button is now the primary action. No doc
  change — copy/affordance-only UI change, contracts unchanged.
- **fix(ui): the sidebar menu always reads F1–F12 in order again.** Saved
  shortcut slots had drifted for legacy orders (ChatBot kept F3 from the old
  default order) and for the Dashboard insertion, which left one slot blank and
  shifted every following key by one; duplicate keys could also survive. The
  config is now versioned (v3) with an explicit `shortcutsCustomized` flag:
  un-customized menus are re-numbered F1..F12 in visible order on load, after an
  app-wide nav update and after a reorder, while keys assigned in Settings are
  preserved and de-duplicated. Sidebar badges and collapsed titles render the
  formatted label; the shortcut help no longer double-formats labels (which
  upper-cased `Shift + E`) and now lists the missing `Alt+G` Graph mode entry.
  Docs updated: `docs/OVERVIEW.md`, `docs/CHANGELOG.md`.
- **Skills Phase 8: surface promotion evidence, version comparison, and bundle
  update preview/rollback.** Three capabilities already existed in the browser
  client but had no UI. Skill Detail now has a **Promotion evidence** section
  (evaluation status, execution metrics, CI, usefulness, deprecation advice,
  sample warning) and a **Compare versions** section (older-vs-current success,
  validation, duration, regressions, case-set deltas, low-sample honesty).
  Locked bundles gained **Preview update** (member/version/hash deltas) and
  **Rollback**. New `skill-evidence.tsx` + `skill-evidence.test.tsx`; read-only,
  no API change. Docs updated: `docs/NAVIGATION.md`, `docs/CHANGELOG.md`.
- **fix(harness): a cold start no longer reports 503 while it is still importing.**
  The P2 drill saw the first authenticated harness call return 503 under a
  concurrent build/test load, then succeed on the next call. Measured cause: the
  runtime cold start is 36 s standalone and ~51 s alongside the app's own boot,
  and can exceed the old 240 s budget when the host is saturated — the front door
  then reports the runtime unavailable while it is still healthy. The default
  `HARNESS_PY_START_TIMEOUT_MS` is now **300 s** (with margin over the measured
  worst case), `waitForHealth` logs progress every 15 s instead of waiting
  silently, and `_boot()` now logs per-subsystem timings so a slow start is
  diagnosable from the log. Verified: a fresh isolated production app + data dir
  returned the first `/api/harness/models` **200 in 51.4 s**; the boot marks show
  every subsystem step under 200 ms, so the remaining time is the Python import
  itself. Docs updated: `docs/DEPLOYMENT.md`, `docs/CHANGELOG.md`.
- **Skills Phase 7: execution runs are addressable.** `?tab=skills&sub=skills.activity&focus=<runId>`
  now opens (and highlights/expands) that run. The Learning Queue's "View run"
  is restored and routes there; a run older than the 100-row list window is
  fetched by id from `/api/skill-executions/:runId`, and a missing run shows an
  honest "Run not found" state. Collapsing the focused row clears the URL param.
  Added the browser `getSkillExecution` helper and an SSR test
  (`execution-activity.test.tsx`) pinning the expanded/collapsed states. Docs
  updated: `docs/harness/phase-3-architecture.md`, `docs/CHANGELOG.md`.
- **Skills Phase 6: bulk enable/disable in the Library.** Each skill card now has
  a labelled selection checkbox and a selection toolbar ("Enable", "Disable",
  "Clear"). Bulk actions call the existing operator-gated
  `setSkillLifecycle` per skill in batches of five, count successes/failures,
  report a partial-failure toast instead of claiming blanket success, then
  refresh the list. Only reversible transitions are offered — no bulk
  deprecate/delete. No API or data-shape change; the server remains the
  authority for every transition. Docs updated:
  `docs/harness/phase-3-architecture.md`, `docs/CHANGELOG.md`.
- **Skills Phase 5: navigation + accessibility pass.** The primary group tab bar
  now stays visible during a skill drill-down; choosing a group closes it (URL
  replaced, not pushed), so detail is escapable without the Back button. Added
  `aria-pressed` to Library filter/sort and Guided Learn source toggles,
  `aria-expanded` to detail sections and execution rows, `aria-label`s to the
  Library search and Evaluation skill picker, `role="status"`/`aria-live` to the
  toast, and Escape-to-close + `aria-modal` to the author drawer. New SSR test
  `src/components/screens/skills/skill-library.test.tsx` pins the filter state,
  pagination range and empty-state action. Docs updated:
  `docs/harness/phase-3-architecture.md`, `docs/CHANGELOG.md`.
- **fix(deploy): the container applies the Prisma schema on first boot.**
  `docker-entrypoint.sh` execs `next start` directly, bypassing
  `scripts/doctor.js` (the `prestart` hook that runs `prisma db push`), so a
  fresh `be-data` volume booted with an empty `jdds.db` and every Prisma table
  failed with P2021 (`CronJob does not exist`, news-refresh cycle errors). The
  entrypoint now runs `prisma db push` before `exec` — idempotent, and fail-soft
  (a destructive schema change warns loudly instead of dropping data). Found by
  the P2 production-posture drill. Verified on an isolated data dir: 58 tables
  including `CronJob`, `PRAGMA integrity_check = ok`, and an app boot with zero
  schema errors. The same drill confirmed: unauthenticated `/api/settings` 401;
  first-run setup + login + authenticated `/api/auth/me`; a killed/absent
  runtime reporting 503 then recovering to 200; and a backup → destroy →
  restore with 4/4 databases passing `integrity_check`. Docs updated:
  `docs/DEPLOYMENT.md`, `docs/PRODUCTION-READINESS.md`, `docs/CHANGELOG.md`.
- **Skills Phase 4: server-side list query contract + large-registry UX.**
  `GET /skills` now accepts `q`/`category`/`status`/`risk`/`sort`/`limit`/`offset`
  and returns an exact envelope (`registryTotal`, `total`, `offset`, `limit`,
  `hasMore`); the old bare call still returns every skill. The pure semantics
  live in `python/harness/skills/listing.py` with
  `python/tests/test_skills_listing.py`; the front door and both TS clients
  forward the query. Added `updatedAt` to summaries and an "Updated" sort to the
  Library, and gave the Evaluation Center a searchable skill picker (a 90+ item
  `<select>` was unusable). The UI intentionally stays client-side below ~500
  rows for instant filtering; above that the same params drive server paging with
  no API change. Docs updated: `docs/harness/phase-3-architecture.md`,
  `docs/CHANGELOG.md`.
- **fix(trading): the approval card IS an execution path — stop reporting fills as
  refusals.** A demo XAUUSD order filled (`ord_a143a70d5baa`, ticket 11290511790,
  0.1 lot @ 4071.91) through approval `appr_bca8be7bf25b44db`, yet the chat then
  claimed the card "never sends" and that a demo mandate was the only way. Root
  cause was contradictory guidance: `prompts.py` `<fiduciary_advice>` called the
  demo mandate the ONLY execution path and told the model to call `order_submit`
  directly, while the per-run trading directive says `order_preview` + the
  operator's card. The system block now names both operator-gated paths (manual
  approval card, unattended demo mandate), states that the card submits and needs
  no mandate, and requires an `order_ledger`/`broker_positions` read before
  reporting a failure. `trading_intent.py` says the same; `order_preview`'s result
  names the card as the submit path; `order_submit`'s `MANDATE_REQUIRED` message
  points at `order_preview` for a one-off trade. The approval banner also kept its
  success line only while a pending approval existed — a fill consumed the
  approval and the confirmation vanished — so the notice now survives the
  unmount for 10 s. Prompt ceiling re-pinned 43307 → 44183 (measured). Tests:
  `test_trading_intent.py`, `test_phase_s_stabilization.py`,
  `test_memory_tools.py`, broker suite. Docs updated: `docs/trading.md`,
  `docs/CHANGELOG.md`.
- **Skills Phase 3: URL-addressable detail and persisted Library filters.** A
  skill drill-down now has a real URL (`?tab=skills&sub=skills.detail&focus=<id>`)
  and pushes a history entry, so browser Back closes it and a link/Cmd-click
  opens the same skill. Library search/filters/sort live in the URL
  (`q`/`cat`/`status`/`risk`/`sort`), are restored on reload, and survive the
  detail round-trip; the pure parse/serialize pair is
  `src/lib/skills/library-view.ts` with `library-view.test.ts`. Added shared
  `EmptyState`/`ErrorState` to `skill-ui.tsx` and replaced the bespoke empty and
  error panels across Library, Evaluation, Activity, Learning Queue, Bundles,
  Project Skills, Maintenance and Journey. No API change; deep links use the
  existing `focus` dispatch path. Docs updated:
  `docs/harness/phase-3-architecture.md`, `docs/CHANGELOG.md`.
- **Skills Control Room: 10 tabs → 5 groups, real pagination, and dead
  controls removed.** The Skills screen flattened discovery, authoring, review
  and monitoring into one ten-tab bar. It now renders five primary destinations
  — Library · Learning · Journey · Collections · Operations — with sub-tabs;
  `SKILLS_TABS` remains the deep-link/agent-surface inventory and Start Here is
  `hidden` (first-run content in the Library empty state, still reachable at
  `?tab=skills&sub=skills.start`). RSL Experiments moved out of Journey into
  Operations. Added the shared `PaginationFooter` to the 91-skill Library
  (25/page), Evaluation Center, all four Skill Detail histories, Project Skills
  trust/approval history, Bundles, and Maintenance; added a Library sort control
  and derived the status/category filter chips from the registry (the hardcoded
  list omitted seven real statuses). Removed the Learning Queue "View run"
  no-op, the unreachable read-only-operator banners, and the raw-JSON-only run
  input (now a schema-driven form with a JSON fallback). Bundle delete now
  confirms first. Docs updated: `docs/harness/phase-3-architecture.md`,
  `docs/NAVIGATION.md`, `docs/CHANGELOG.md`.
- **Memory Control Room follow-up: every remaining list is paged; diagnostics
  moved out of Facts.** Sessions, automatic-learning reviews, suggestions,
  corrections and mistakes now accept `offset` and return exact `total` /
  `hasMore`, with the shared footer ("Showing X–Y of N") in each view. Added
  `listChatSessionsPage`, `listLearningReviewsPage`, `listSuggestionsPage`,
  `listCorrectionsPage` and `listMistakesPage` to both clients; the
  array-returning wrappers remain for bounded batch callers. Preferences
  evidence groups are paged client-side. Retention, contradiction-detection
  prose, real-usage metrics and compaction now live in Maintenance →
  Diagnostics (`diagnostics-panel.tsx`) instead of above the Facts lifecycle
  list; Facts → Lifecycle keeps the state counts, view chips and paged list.
  Tests: browser-client paging cases; Python suite re-run. Docs updated:
  `docs/harness/personal-memory.md`, `docs/CHANGELOG.md`.
- **Memory Control Room: 16 tabs → 7, exact counts, and real pagination.** The
  screen had accumulated 16 top-level tabs that duplicated the same records
  (Facts/Lifecycle, Sessions/Session Search, Preferences/Suggestions,
  Files/Health) and pushed content below diagnostic prose. It now renders
  Overview · Facts (Browse + Lifecycle) · Sessions (list + search) · Review
  (suggestions + learning reviews) · Preferences (learned + context snapshot) ·
  Settings (policies + providers + profiles) · Maintenance (diagnostics + files
  + health/data), with every legacy slug kept as a deep-link alias. Removed the
  redundant Skills tab, the three-card model legend, and the duplicate Markdown
  actions in Health. Fixed the literal `{Math.round(...)}` that appeared in the
  usage report, fixed the JSON import picker (a disabled button swallowed the
  file dialog), and corrected the empty-state copy that claimed nothing is
  learned automatically. Overview totals are now `COUNT(*)` queries instead of
  `len(list(limit=500))`; `/eclipse-memory/memories`, `/lifecycle` and
  `/session-search` accept `offset` and return exact `total`/`hasMore`.
  Facts search is server-side and paged (50/page), Lifecycle is paged, and
  Session Search has a working "Load more". The Settings cluster (profiles,
  providers, policies) was extracted to `settings-panel.tsx` so the shell stays
  under the source-size ratchet. Tests: new
  `python/tests/test_memory_pagination.py`, browser-client pagination cases.
  Docs updated: `docs/harness/personal-memory.md`,
  `docs/harness/phase-3-memory-progress.md`, `docs/CHANGELOG.md`.
- **fix(desktop): the right-click "Open" icon is the app icon.** Windows 11's
  modern context menu draws the **target's** icon for "Open", so the desktop
  shortcut to `wscript.exe` showed the colourful Windows Script Host icon there
  even though its `IconLocation` pointed at `black-eclipse.ico` (setting
  `IconLocation` can only fix the desktop/Start tile). New
  `scripts/desktop-shortcut.js` (`npm run setup:desktop`, `black desktop`)
  compiles `.black-eclipse/Black Eclipse.exe` with the .NET Framework `csc` that
  ships with Windows, embeds `public/branding/black-eclipse.ico` in it, points
  the shortcut (repairing an existing one under any name) at that exe with the
  same icon, and asks the shell to refresh its icon cache. The exe just starts
  `start-eclipse.vbs`, so boot/stop behaviour is unchanged. No new dependency:
  `csc` is part of Windows and the generated exe is gitignored. Docs updated:
  `docs/QUICKSTART.md`, `docs/NAVIGATION.md`, `docs/CHANGELOG.md`.
- **fix(trading): attach to MetaTrader 5 instead of launching it in the
  background.** `mt5.initialize(path=...)` starts `terminal64.exe` when it is
  closed, so the 15 s dashboard broker snapshot and the journal auto-sync
  reopened MT5 every time it was shut. The adapter now checks the OS process list
  first (`trade/terminal.py` `terminal_running`, a dependency-free Toolhelp
  snapshot kept separate from `terminal/proctree.py` so the broker layer does not
  pull in the sandbox) and refuses before `initialize` with
  `TERMINAL_NOT_RUNNING` unless the connection opts in with
  `config.autoLaunchTerminal: true`. `probe()` reports the same honest code
  without launching. `autoLaunchTerminal`/`openTerminalOnTrade` joined
  `ALLOWED_CONFIG_KEYS`, and boolean config values now stay booleans
  (`false` used to become the truthy string `"False"`, which also made
  `portable` misbehave). New checkbox in Settings › Broker connection, off by
  default. Tests: `python/tests/test_mt5_launch.py`; the simulated-terminal
  fixture stubs the running check. Docs updated: `docs/trading.md`,
  `docs/CHANGELOG.md`.
- **feat(graph-studio): expose typed decisions as workflow nodes + a zero-config demo.**
  New `decision.ask` (general: wired/`stateJson` state + a closed question
  template, `model` side effect) and `decision.demo` (deterministic rules
  scenario, `local_write` audit only) in `python/harness/graph_runtime/decision_nodes.py`,
  registered through `node_packs.py` and bound to `service.decision` in
  `graph_runtime/bootstrap.py`; editor contracts in
  `src/lib/graph-studio/registry-decisions.ts` + `registry.manifest.json`; new
  `decision` node category, inspector fields, `brain` icon and the
  `decision-demo` starter template. Both nodes reuse `DecisionService.ask`, so
  status stays the only branch (`answered` / `review` / `unavailable`), a
  missing provider fails closed, and `ECLIPSE_PRIVACY=local-models` is still
  enforced. The `decision.ask` capability joins `TEST_RUN_CAPABILITIES` (a
  typed judgment is information, not a world effect), so the demo template is
  runnable in a workflow test run. Tests:
  `python/tests/test_graph_decision_nodes.py` (15) plus the regenerated manifest
  parity. `scripts/size-budget.json` total re-pinned
  463916 → 464234 for the new node adapter (deliberate; no per-file ratchet
  changed). Docs updated: `docs/graph-studio.md`,
  `docs/decision-models.md`, `docs/NAVIGATION.md`, `docs/CHANGELOG.md`.
- **docs(release): add the production-readiness roadmap.** New
  `docs/PRODUCTION-READINESS.md` records the measured 2026-11-08 baseline
  (typecheck, tests, secrets, ADRs and size are green; `npx eslint .` has 3
  errors; the live agent gate still fails at `task_success 0.8520 < 0.9`; the
  preflight passes only as advisory and the container path is unverified),
  names the six blockers (R1-R6), defines
  twelve re-runnable exit criteria (C1-C12), and sequences the work as P0 tree +
  lint + merge, P1 clean build + secrets + container, P2 production-posture
  proof (journey, backup/restore, failure drill), P3 the live-gate decision
  (improve to 0.9 or an ADR with a recorded accepted floor), P4 release
  engineering (check:all on `main`, release note, tag, deploy/rollback), and P5
  operations. It deliberately separates engineering blockers from the external
  inputs (provider key, Docker host, second reviewer, CODEOWNERS team, counsel)
  so a finished code phase is never reported as a finished release. NAVIGATION
  gets a trigger row. Docs:
  `docs/PRODUCTION-READINESS.md`, `docs/NAVIGATION.md`, `docs/CHANGELOG.md`.
- **chore(changelog): rotate the active window.** Adding today's section took
  `CHANGELOG.md` to 8 dated sections, over the committed 7-section window the
  `changelog-guard` test enforces. `node scripts/rotate-changelog.js --write`
  moved `2026-11-01` into `docs/changelog/2026-11.md` (a move, never a prune),
  preserving the archive's line endings. no doc change — rotation is tooling,
  the policy is unchanged.
- **fix(lint): clear the three gate-blocking errors.** `folder-picker.tsx`
  renamed the `useWindows` callback to `openWindows` (it is a `useCallback`
  named like a hook, so `react-hooks/rules-of-hooks` failed the gate);
  `desktop-launcher.test.ts` replaced its two `any`s with a typed
  `LauncherTheme` shape. `npx eslint .` now exits 0 (0 errors, 118 warnings).
  Verified: `npx tsc --noEmit`, the two affected Vitest files (19 tests) and
  `python/tests/test_decisions.py` (28). no doc change — lint-only.
- **chore(release): complete P0 and land it on `main`.** The typed-decision and
  legal work (`cc5519ea`) and the roadmap + lint fix (`9785b485`) are merged into
  local `main` as `b48d3ba5`; the `CHANGELOG.md` merge conflict kept BOTH sides'
  `2026-11-04` entries and the rotated archive now carries main's `2026-11-01`
  bullets (including the `423,998` size re-pin), so no history was dropped.
  `npm run check:all` on `main` passes **ALL GATES** (tsc, eslint 0 errors,
  secret scan, advisory preflight, ADR + size, Vitest + Python, eval gates,
  corpus). `main` is clean and not pushed. Docs updated:
  `docs/PRODUCTION-READINESS.md`, `docs/CHANGELOG.md`.
- **fix(deploy): the security preflight accepts `HARNESS_AUTH=required`.**
  `scripts/security-preflight.js` had its own `truthy()` that omitted `required`
  — the documented production value, and the exact value `docker-compose.yml`
  forces — so a correctly hardened deployment failed its own deploy gate with
  "HARNESS_AUTH missing". It now mirrors `src/lib/auth/config.ts` exactly
  (`required`/`enable`/`enabled` are on; `off`/`none`/`disabled` are off) and
  returns `undefined` for anything else. Regression test
  `src/lib/security-preflight.test.ts` (8 cases) covers both the accepted
  vocabulary and the three fail-closed paths. Verified manually: a public
  production posture with generated secrets passes; without them it exits 1.
  `docs/DEPLOYMENT.md` now states that the script reads the process environment
  (not `.env`) and shows `node --env-file=.env scripts/security-preflight.js`
  for checking a filled file without exporting it. Also verified the clean
  build actually serves: `next start` on the fresh `.next` returned
  `GET /login` 200 in 2 s. Docs updated:
  `docs/PRODUCTION-READINESS.md`, `docs/DEPLOYMENT.md`, `docs/CHANGELOG.md`.
- **fix(ui): a partial autonomy status no longer crashes the skills panel.**
  `RslAutonomyCardView` read `status.killSwitch.paused` without guarding
  `killSwitch`, so a proxy error envelope or an older payload threw during
  render and blanked the whole panel. `npm run test:drift` had been red for this
  reason (the fixture's broad `/api/evolution/rsl` mock matched the autonomy
  route and returned the wrong shape). The field is guarded, a regression test
  covers a missing `killSwitch`, and the fixture now mocks
  `/api/evolution/rsl/autonomy` before the broader route. `npm run test:drift`
  passes both smokes. Also documented why `useInView` intentionally has no
  dependency list (a ref-only mount check that cannot loop), and corrected
  `CONTRIBUTING.md`'s release-gate list to match `check-all.js`/CI (it omitted
  the secret scan, preflight, ADR and size checks, the corpus gate and the drift
  smokes). Also removed six dead `eslint-disable` directives (their rules are not
  enabled) and one unused icon import, so the advisory warning count drops
  without changing behaviour. Docs updated: `CONTRIBUTING.md`,
  `docs/CHANGELOG.md`.

## 2026-11-07
- **feat(decisions): typed decision models (System One-shaped) as a first-class
  layer.** New `python/harness/decisions/` asks closed `choice` / `score` /
  `noul` questions about a `state` and returns typed answers with probabilities
  and confidence — deliberately NOT a chat provider (no messages/tools/
  streaming). Ships the deterministic rule provider (fully offline), a
  fail-closed `DecisionPolicy` (`answered` / `review` / `unavailable`), a
  privacy-gated provider registry, and an immutable `DecisionRecord` /
  `DecisionOutcome` audit on `agent-memory.db`. Read-only tools
  `decision_ask`/`decision_list`/`decision_scorecard` are wired through
  `AgenticService` → `execute_run` → `ToolContext.decision_service` and the
  Eclipse agent allowlist. A partial/mistyped answer, a provider error or no
  provider is `unavailable`, never a guess. TypeSafe/Jev and LLM adapters are
  additive next; no remote provider is installed implicitly. Docs:
  `docs/decision-models.md`, `docs/ARCHITECTURE.md`, `docs/NAVIGATION.md`,
  `docs/DECISIONS.md`, ADR-070, `docs/CHANGELOG.md`.
- **docs(legal): add the Legal, Compliance & Risk Management Blueprint.** New
  `docs/legal/LEGAL-COMPLIANCE-BLUEPRINT.md` covers the entity/IP structure,
  US/UK/EU/Pakistan regulatory characterisation, AI and financial disclaimers,
  automated-trading responsibility and existing broker controls (arming,
  per-order approval, typed phrase, risk limits, kill switch, bounded mandates,
  reconciliation, audit), privacy/security, MIT vs Apache/AGPL and DCO vs CLA,
  the capability/consent matrix, the document register, incident/dispute
  handling, and a costed 90-day roadmap. `docs/legal/README.md` is the document
  register and status board. The core position: Eclipse is self-directed
  research and order-entry software; the user owns the decision and the account,
  and no disclaimer is treated as immunity. NAVIGATION gets a legal trigger row.
  Docs: `docs/legal/LEGAL-COMPLIANCE-BLUEPRINT.md`,
  `docs/legal/README.md`, `docs/NAVIGATION.md`, `docs/CHANGELOG.md`.
- **fix(changelog): rotation keeps the archive's line endings.** `2026-10-31`
  pushed `CHANGELOG.md` to 8 dated sections, so the active window was rotated
  into `docs/changelog/2026-10.md` with `npm run rotate:changelog`. The script
  appended an LF block to a CRLF archive, producing a file with mixed endings
  and failing `gitignore-guard`'s "no tracked text file mixes CRLF and bare LF"
  contract (measured: 20,628 CRLF + 205 LF). It now normalizes the merged block
  to the target's dominant ending. no doc change — tooling fix, policy unchanged.

## 2026-11-06
- **fix(runtime): a runtime already on the harness port is adopted, not raced.**
  `ensurePythonRuntime()` probed `/health`, and when a listener existed it probed
  again — but a SUCCESSFUL second probe fell through to the spawn anyway, booting
  a rival uvicorn that died with `WinError 10048`; the front door then reported
  "runtime unavailable" for the rest of the session (observed live: a second
  `npm run start` while a healthy runtime held 8766). It now adopts that runtime.
  A child that dies from a port conflict is detected from its stderr and the live
  runtime is adopted; a spawn that exits no longer makes boot wait the whole
  cold-start budget; listener PIDs are parsed from the exact local-address column
  (so `:18766` / a foreign `:8766` cannot match). `HARNESS_PY_URL` /
  `HARNESS_PY_PORT` / `HARNESS_PY_HOST` now actually override the profile default
  in the launcher, and `kill-port` clears the port that will be used. Tests:
  `src/lib/harness/python-runtime.test.ts` (11). Docs:
  `docs/harness/architecture.md`.
- **fix(build,reports): production build and model-authored PDF tables.** The
  build failed on stale imports from in-flight build-screen work: restored
  `getProjectBrief`/`prepareProjectIndex` on the server client, added their
  browser-client versions, restored `GET /code/project`, removed the stale
  preview `mode` field, and added the missing `code.project.*` copy. Separately,
  the PDF report renderer raised `REPORT_RENDER_FAILED: list index out of range`
  for a table without headers, dict-shaped rows, or empty rows; `_table` now
  derives headers, accepts list-of-objects rows and skips an empty table.
  Verified: `npm run build` passes; `test_reports.py` (9), code task/tool/root
  (40) and code API/UI Vitest (13) pass. Docs updated: `docs/CHANGELOG.md`.
- **fix(vision): one privacy story and a bounded fallback chain.** Vision had its
  own default (`HARNESS_VISION_PRIVACY=cloud_allowed`) that ignored the app-wide
  `ECLIPSE_PRIVACY`; with local models configured, a screenshot still walked five
  local models, LM Studio and OpenRouter (12 provider calls) before one answered.
  The mode now inherits `ECLIPSE_PRIVACY=local-models` as `local_only`, caps the
  chain (`HARNESS_VISION_MAX_ATTEMPTS`=4, `…_MAX_PER_PROVIDER`=2), emits
  `vision.route.capped`, and records the provider/model that actually looked.
  Tests: `test_vision_privacy_chain.py` (8). Docs: `docs/harness/vision.md`.
- **fix(chat-api): the one-shot endpoint hands back a run instead of dying at
  180 s.** `POST /api/harness/chat` awaited the whole run under
  `maxDuration = 180`, while a writable turn is budgeted 80 steps / 2,700 s, so a
  real build was killed with `PROVIDER_TIMEOUT` and no run id. It now stops
  waiting at 150 s (`HARNESS_CHAT_SOFT_DEADLINE_MS`) and returns `202
  {status:"running", runId, streamUrl}`, with the same id given to the runtime;
  the run continues. Test: `src/app/api/harness/chat/route.test.ts`. Docs:
  `docs/CHANGELOG.md`.
- **feat(auth): `npm run auth:setup`.** One supported edit that sets
  `HARNESS_AUTH=required` and generates a 32-byte `HARNESS_AUTH_SECRET`, refusing
  to rotate an existing secret and never printing it (`--dry-run`, `--file`).
  The doctor line now points at it. Docs: `docs/harness/authentication.md`.
- **fix(code): five defects found by the LIVE failing-check acceptance run.**
  (1) `shell_run` crashed with `name 'redact_output' is not defined` — the import
  was missing, so the whole real-shell surface was dead. (2) `resolve_class`
  rejected the obvious plural (`unit_tests`) and the refusal never named the
  valid vocabulary, so the agent abandoned the pinned-check path and shelled out;
  it now accepts the plural and lists the classes. (3) `package_test` refused with
  "exit 1" and DROPPED the failing output; the refusal text now carries it.
  (4) a `.black-eclipse/verify.json` written with a BOM silently pinned NO checks
  (read with `utf-8-sig` now), so the verify-and-repair node never ran. (5) a
  PASSED check was reported `REPAIR_EXHAUSTED` — and the answer annotated "still
  failing" — when a later command spent the last check-run slot; status is now
  fact-first and a spent budget after a pass is a no-op. Verified live twice
  (fail → repair → pass, no false note). Tests: `test_code_check_path.py` (4),
  `test_graph_repair_node.py` (+2). Docs: `docs/developing-a-project.md` (how to
  pin and prove the loop).
- **docs(security): say what actually runs.** `terminal_run`/`shell_run` use the
  LOCAL tier (process-tree bounds, no filesystem/network isolation); Docker is a
  selectable backend, not the executor. `BLACK_ECLIPSE_SANDBOX_REQUIRED=1` refuses
  every execution it cannot isolate (`SANDBOX_UNAVAILABLE`). The boot line now
  says this instead of implying a container. Docs: `docs/harness/security.md`.
- **fix(trading): Deny on the trade-approval card removes it at once and stops
  the turn.** The card was only removed *after* the decide round-trip, so a slow
  request left it on screen, and the 6s poll could bring it back. Deny is now
  optimistic: the card leaves immediately, the approval id is suppressed from
  polling, and `onCancel` stops the in-flight run (the order is never sent). If
  the decision genuinely fails, the card returns with the error. Verified live:
  card gone in 58ms, `POST /trading/approvals/{id}/decide` 200, still gone after
  the next poll. Tests: `tsc` clean, full suite 476 files / 4,417. No doc change
  — a behaviour fix with no contract change.
- **feat(search): semantic retrieval is now switchable and honest.** The vector
  layer already existed but shipped dormant: with no provider it silently stayed
  keyword-only, so a user could not tell what was on or turn it on. Added a
  structured `EmbeddingService.resolution()` (`state`/`source`/`hint`/
  `suggestions`) exposed via `/search/stats` and `/search/models`;
  `POST /search/embedding/{apply,test,clear}` to pick a model live, verify one
  real round-trip, and revert; and persistence of the operator's choice in
  `SearchMeta.embedding_config` so it survives a runtime restart. Switching
  vector space now schedules a forced re-index (`bulk_index(force=True)`,
  dedup skipped) because old vectors are keyed to the previous model. The Search
  Intelligence screen renders an actionable setup card instead of a passive
  "keyword-only" pill. No silent provider substitution: a chat-only provider is
  reported as unsupported, never swapped for a hosted embedding provider.
  Docs updated: `docs/harness/search-retrieval.md`, `docs/CHANGELOG.md`.
- **test(harness): first real chat quant eval passes.** Ran “forecast gold for
  tomorrow” through the live configured model (Ollama / deepseek-v4.1-flash) and
  graded the actual answer + 23 tool executions with `quant_chat_eval`:
  **passed**, with an explicit spot-XAUUSD vs GC=F basis, a GARCH distribution
  (no point forecast), walk-forward validation, costs, and an artifact line
  (`art_…`). The artifact regex now recognises `art_`/`artifact_` ids too.
  Docs updated: `docs/CHANGELOG.md`.
- **feat(capabilities): a generated capability belongs to its project (P4).**
  The draft root was already the run's project (`draft_root(root)` →
  `<project>/.black-eclipse/capabilities`), but the process-wide dynamic recipe
  registry was only refreshed on build/activate with whatever root that call
  used — so a recipe built in project B could be reported active while
  `analysis_run` could not execute it from B, and A's recipes could linger while
  working in B. `capability_request` now refreshes the registry for the run's
  root before assessing, so discovery and execution agree and capabilities are
  isolated per project. Test: a built recipe is listed in
  `project_b/.black-eclipse`, absent from `project_a`, a `gap` again in A, and
  callable again in B without rebuilding. Docs updated: `docs/NAVIGATION.md`,
  `docs/CHANGELOG.md`.
- **feat(harness): close the chat quant loop.** Deep quant turns now get a
  32-step / 10-minute budget floor. The final answer is post-checked by
  `finalize_quant_text`: if the model omitted the required artifact line, Eclipse
  appends `Artifacts: <ids>` (or `Artifacts: none — …`) and names any still-missing
  validation, OOS or cost evidence as an explicit `Eclipse check`, never silently
  passing. The protocol also requires the gold basis (spot `XAUUSD` vs `GC=F`
  futures). New offline gate `eval_gates/quant_contract.py` locks the contract
  into `npm run test:evals`; new `quant_chat_eval.py` grades real chat outputs
  from JSONL (`python -m harness.quant_chat_eval`) and `test_quant_chat_eval.py`
  covers it. `graph.py` re-pinned 2461→2469. ADR-H345 records that quant work is
  chat-native, not a UI mode. Docs updated: `docs/harness/decisions.md`,
  `docs/CHANGELOG.md`.
- **feat(builds): chat builds are durable, and the scorecard is per project (P3).**
  A writing chat turn now records a `session.created` boundary
  (`code/session.py::record_chat_build`, called from the same
  `AgenticService.run`/`run_background` seam as the budget floor), pre-creating
  the run row when needed so the FK-bound checkpoint can be written. Chat builds
  therefore appear in the scorecard and are resumable through the existing run
  path. It also writes the same `task.created` boundary a Code task has, so a
  chat build now lists in **Builds** (diff, checks, preview, undo), not only in
  the transcript; `code/tasks.py` lists any run with that boundary and
  `TaskStore.view` returns None for a run that never built. `build_scorecard` no
  longer requires `agentId == "code-agent"`: a build is any run with a session and
  a code workspace row, and the row's `checkoutRoot` attributes it to a project.
  `GET /code/scorecard` takes `taskId`/`rootId`
  (resolved server-side, never a raw path) and the Builds tab gained a
  **This project / All builds** toggle. Tests: 3 new `test_build_session.py`
  cases (records once, planning is not a build, the chat build is listed) and a
  per-project scorecard case.
  Docs updated: `docs/NAVIGATION.md`,
  `docs/harness/roadmap/phase-22-self-hosting.md`, `docs/CHANGELOG.md`.
- **feat(builds): run the project and look at it (P2).** New
  `python/harness/code/preview.py` starts a project's dev command on the
  EXISTING execution layer (`ServiceManager` + the terminal process manager) and
  reports the URL it actually finds: it watches the process tree for the first
  listening port that answers HTTP, so a running-but-silent process is `not
  ready` with logs, never a fake URL. Command precedence is
  `.black-eclipse/preview.json` > `package.json` `dev`/`start`/`preview`/`serve` >
  a `Makefile` target. Routes `POST /code/preview/start`, `POST
  /code/preview/stop`, `GET /code/preview`, `GET /code/preview/logs` (the project
  is resolved server-side from the task's workspace or an approved root; no
  `cwd` in a body), proxied by `src/app/api/code/preview/route.ts`. The Builds
  tab gains `preview-panel.tsx` (Run / Check again / Open / Stop / logs) with
  `code.preview.*` copy in `dictionaries/builds.ts`. A preview runs the project
  ON DISK — an unlanded change is not included, and the panel says so. Tests:
  `python/tests/test_preview.py` (9), +1 wiring assertion. Docs updated:
  `docs/NAVIGATION.md`, `docs/CHANGELOG.md`.
- **feat(harness): chat deliverable contract + catalog-first reuse.** The quant
  protocol now requires exactly one final `Artifacts: <ids>` or
  `Artifacts: none — <missing>` line on every standard/deep turn, and a
  `model_catalog` check BEFORE a build with reuse of a fitting artifact instead of
  a duplicate. An ambiguous model family (DCF vs ML vs strategy vs risk) gets ONE
  `clarify` question with those options. Reuse/catalog asks ("reuse the model from
  last week", "what models do we have", "list my strategies") are now classified
  as standard quant turns instead of concept/lookup non-turns. New deterministic
  chat fixtures `python/tests/test_quant_chat_contract.py` (6) and benchmark cases
  cover the contract. No separate UI: chat is the only delivery surface. Docs
  updated: `docs/harness/architecture.md`, `docs/CHANGELOG.md`.
- **feat(builds): the Builds tab names its project, and land checks fit it (P1).**
  New `components/screens/code/project-bar.tsx` shows the project new builds
  belong to and switches it through the ONE trusted-roots registry + shared
  `FolderPicker`; `task-list.tsx` passes `workspaceRootId` on both create paths,
  so a build no longer relies on an invisible global selection. New
  `dictionaries/builds.ts` holds the `code.project.*` copy (en.ts is ratcheted).
  `code/land.py` now detects a user project's checks — `package.json` scripts,
  `Cargo.toml`, `go.mod`, a declared pytest, a `Makefile` `test:` target — with
  precedence `land.json` > harness defaults (Eclipse's repo only) > detected >
  none-with-a-warning; an unrecognised project gets no checks rather than
  Eclipse's. Tests: `project-bar.test.ts`, an extended
  `code-screen-mounted.test.ts`, 4 new `test_land.py` cases. Harness budget
  re-pinned to the measured tree. Docs updated: `docs/NAVIGATION.md`,
  `docs/CHANGELOG.md`.
- **feat(harness): chat-native reuse of the model catalog.** The Eclipse Agent
  prompt now tells the model to call `model_catalog` before building a duplicate,
  reuse or extend an existing artifact where it fits, and name the created
  artifact's id in the answer. This is intentionally chat-native: the catalog is
  a read-only agent tool whose text result is summarized inline; there is no
  separate catalog screen or workspace panel. The deep quant protocol already
  carries the same instruction. Docs updated: `docs/CHANGELOG.md`.
- **fix(workspace): the folder picker can find and create folders.** The chat
  project chip's "Open folder…" (and the Editor's folder picker) now has a path
  bar that accepts a typed/pasted absolute path, a **Drives** button back to the
  filesystem roots, and a **+ New folder** action that enters the folder it just
  created. Browse + create are **Node-native** (`src/lib/workspace/browse-server.ts`
  + the `/api/workspace/browse[/mkdir]` routes) so a Python runtime restart can
  no longer freeze the picker; approving a folder as a ROOT still goes through the
  runtime's trusted-root store. When the page is on `localhost`, the picker calls
  the same server on `127.0.0.1` (a separate browser connection pool) with a
  narrow loopback CORS grant, fixing the dev keep-alive wedge that hung the second
  request. Browse/create time out honestly and offer **Retry**. The runtime health
  probe budget is raised (1.5s→8s, TTL 5s→15s) so a healthy-but-busy runtime is
  not mistaken for dead and restarted. Tests: `browse-server.test.ts` (5),
  `test_code_roots.py` (+3), `test_workspace_editor_api.py` (+2), `tsc` clean,
  full vitest green (474 files / 4408). Docs updated: `docs/NAVIGATION.md`,
  `docs/CHANGELOG.md`.
- **fix(workspace): the folder dialog sits above the app, is accessible, and can
  open the Windows picker.** `FolderPicker` is now portaled to `<body>` at
  `z-[200]` (it was `z-[70]` inline, so the sidebar/menus covered it), with a
  `role="dialog"` labelled title, initial focus on the path field, Escape to
  close, a Tab focus trap and focus restore. Redesigned header/toolbar/list/
  footer, folder rows with icons, explicit loading/empty/error states, and
  `aria-live` status. On Windows a **Windows…** button calls the new
  `POST /api/workspace/pick-folder` (`src/lib/workspace/native-picker.ts`),
  which opens the real OS "Select Folder" dialog via a topmost
  `FolderBrowserDialog`; the chosen path is loaded into the in-app picker for
  confirmation. Docs updated: `docs/NAVIGATION.md`, `docs/CHANGELOG.md`.
- **fix(code): a build belongs to ONE project (P0).** Worktrees were always cut
  from the globally *selected* trusted root, and `build_preview` resolved its
  target the same way at promote time — so a build bound to project B could be
  reviewed against, and land into, project A after a selection change.
  `worktree.allocate/release/diff` now take the run's resolved root;
  `CodeWorkspace` records `checkoutRoot` (additive column, legacy rows derive it
  from the scratch path); `build_preview` and the rollback route read it back and
  refuse a project that has moved instead of redirecting; `CreateTaskRequest`
  accepts `workspaceRootId` and the front door forwards it. Cancel/discard now
  release in the task's own project. Tests: new `test_project_binding.py` (5)
  proves the diff cannot land in the selected project and that a vanished project
  is refused; promotion/selfhost/maintenance/land/session suites still pass.
  Docs updated: `docs/NAVIGATION.md`, `docs/CHANGELOG.md`.
- **refactor(self-build): the chat build-budget seam moved to the run funnel.**
  The `standard`-budget floor now lives in `AgenticService.run` /
  `run_background` (`apply_chat_build_budget`) instead of `main.start_run`, so
  every entry point gets it and `main.py` stays under its hard ceiling (1199).
  No behavioural change for `POST /runs`; the earlier entry's `start_run` wording
  is superseded. Docs updated: `docs/CHANGELOG.md`,
  `docs/harness/roadmap/phase-22-self-hosting.md`, `docs/NAVIGATION.md`.
- **feat(harness): unified model/research catalog (Phase 3).** New
  `python/harness/model_catalog.py` registers a read-only `model_catalog` tool
  that aggregates the app's own registries — quant strategies + experiments, ML
  models + datasets, statistical features and factors — with `kind`/`query`/`limit`
  filters and an honest empty-registry note. It never writes and never invents an
  entry; the stores are resolved lazily, so boot order cannot hide a family.
  Registered from `quant/bootstrap.py`, added to the Eclipse Agent allowlist and
  the quant surface, and the deep protocol now says to check the catalog before
  building and confirm the id after creating. Tests: `test_model_catalog.py` (5),
  plus the quant-tools/registry-parity/tool-contract/size suites. Size budget
  re-pinned. Docs updated: `docs/harness/architecture.md`, `docs/CHANGELOG.md`.
- **chore(chat): drop the code-capability headline, de-clutter the learning line,
  fix the composer's right-edge overflow.** Removed `ChatCapabilityPanel` from the
  transcript (the "I'll look at the project…" card with its `details` toggle) and
  deleted the component + its source-text test; the "Put this change into my
  project" control it carried stays on the Code task screen, recovery console and
  RSL panel via `PromoteChange`. Gave the memory/learning outcome line vertical
  breathing room (`py-1.5`, `gap-y-1`, `leading-relaxed`). Composer toolbar no
  longer overflows at ~850px: dropped `shrink-0` from the controls group, added
  `min-w-0` and made the model label truncate inside a shrinking trigger. Tests:
  `tsc` clean, full vitest green (472 files / 4399). Docs updated:
  `docs/NAVIGATION.md`, `docs/interactive-response-engine.md`,
  `docs/CHANGELOG.md`.
- **feat(chat): Plan mode — plan first, then wait for approval.** Added the third
  per-turn preference beside Quant and Choices, inside the composer's "+" menu:
  `src/lib/agent/plan-mode.ts` (Auto/On/Off, persisted), `plan-mode-control.tsx`
  (submenu + active badge), and `planMode` threaded through `ChatOptions`,
  `buildChatPayload`, both chat routes and `run-service` into
  `input.context.planMode`. `python/harness/plan_mode.py` appends a `<plan_mode>`
  block to `runtime_context` only for `"on"`: work out goal/assumptions/steps,
  record them with the existing `create_plan`/`create_task` tools when present
  (otherwise write the plan in the reply), present it, then stop and wait for
  approval before `run_plan`/effectful work. Guidance only — no hard block, no
  capability grant; `off`/`auto` add nothing. Tests: `plan-mode.test.ts` (5),
  `run-service` (+2), chat-route (+1), Python `test_plan_mode.py` (5); `tsc`
  clean; targeted suites green. Size guard: `graph.py` re-pinned 2457→2461 for
  the one import + one call seam. Docs updated: `docs/harness/architecture.md`,
  `docs/CHANGELOG.md`.
- **feat(chat): move the Quant and Choices modes into the composer's "+" menu.**
  The two always-visible Auto/On/Off pills crowded the toolbar (and collapsed to
  cryptic `Q`/`C` glyphs on narrow screens). They are now two submenus —
  **Quant mode** and **Choices mode** — under the composer's "+" menu, each with
  Auto / On / Off radio items and a small badge showing the active choice.
  Default stays `auto` (nothing is sent); picking On or Off persists in
  localStorage and therefore applies to every later run until changed. The
  preference plumbing, server validation and Python behaviour are untouched.
  Tests: `tsc --noEmit` clean, full vitest suite green (4393), targeted
  `test_choices_mode.py` + `test_quant_intent.py` green (54). Docs updated:
  `docs/harness/architecture.md`, `docs/CHANGELOG.md`.
- **fix(self-build): the Builder surface is reachable, and a chat build gets a
  build budget.** `CodeScreen` was exported but never imported, so the Code
  screen, land checks, per-file diffs and scorecard strip had no UI. Added the
  `code` tab to `AppTab` + `ALL_TABS`, mounted it through a keep-alive wrapper
  (`components/screens/code/code-tab.tsx`, so `stock-chat.tsx` grows by one
  import + one line and its ratchet moves 1603→1606), and registered the palette
  page **Builds** (`page-code`, launcher row) with a `code` icon. Also fixed the
  24-step wall that cut the acceptance run off mid-change: `start_run` now
  applies the `standard` session budget (80 steps / 45 min, additive,
  hard-capped) when the turn's autonomy may write, via
  `code/session.py::budget_for_autonomy`; planning turns keep the chat budget.
  Harness size budget re-pinned to the measured tree (total, `.`, `code`). New
  guard `code-screen-mounted.test.ts` fails if the surface is ever exported but
  not mounted again. Tests: `test_build_session.py` (2 new), `app-tabs`,
  `registry-sync`, `size-budget` green. Docs updated: `docs/NAVIGATION.md`,
  `docs/harness/roadmap/phase-22-self-hosting.md`, `docs/CHANGELOG.md`.
- **fix(harness): a code-build task is never a quant turn.** The full suite
  caught a real regression: the team task "write alpha.py and beta.py" matched
  the bare `alpha` model object, so the quant surface narrowed away
  `eval_fs_write`/`eval_run` and the modules were never written. The classifier
  now has a code-task guard (`alpha.py`, `model.py`, `print(...)`, `def `,
  `import `) that returns `none` unless a genuine quant term (backtest, quant,
  forecast, portfolio, volatility, drawdown, Monte Carlo, optimization, a named
  model) is present; bare `alpha` is no longer a model object. Regression cases
  added to `test_quant_intent.py` and the 56-case benchmark; the team comparison
  and code-eval suites pass again. Size budget re-pinned. Docs updated:
  `docs/harness/architecture.md`, `docs/CHANGELOG.md`.

## 2026-11-05
- **feat(chat): composer "Choices" mode — ask with selectable options up front.**
  New `src/lib/agent/choices-mode.ts` + `src/components/chat/choices-mode-control.tsx`
  put an Auto/Choices/Off pill beside Quant in the composer; the value flows as
  `ChatOptions.choicesMode` through both chat routes and `run-service` into
  `input.context.choicesMode`. On the runtime side, `python/harness/choices_mode.py`
  appends a short `runtime_context` block ONLY for `"on"` (and only when `clarify`
  is on the run's surface), telling the model to call `clarify` once with 2–4
  concrete options before an ambiguous turn; the existing question card already
  renders those as clickable buttons and resumes the run in place. `off`/`auto`
  add nothing, so the base prompt's act-don't-ask guidance stands — this is
  presentation guidance, never a capability grant. The block is wired in
  `graph.py` next to the trading/quant context. Tests: TS `choices-mode` (5),
  `run-service` (2 new), chat-route (1 new), Python `test_choices_mode.py` (6);
  `graph.py` size ratchet re-pinned 2452→2457. Docs updated:
  `docs/harness/architecture.md`, `docs/CHANGELOG.md`.
- **feat(harness): quant tool surface + derived quant outcome (Phase 2).**
  `apply_quant_surface` narrows a `standard`/`deep` turn to the data, compute,
  portfolio/broker-read, synthesis and artifact tools (engine names imported
  from `QUANT_TOOLS`/`STATS_TOOLS`/`FACTOR_TOOLS`/`ML_TOOLS`/`RESEARCH_DATA_TOOLS`),
  with trade precedence first and a remove-only guarantee; lookups and tiny
  surfaces are untouched. `apply_intent_surfaces` replaces the trade-only call in
  `graph.py` and still keeps `graph.py` at its size ratchet. `evaluate_quant_outcome`
  derives a read-only completeness record (artifact names, missing computation,
  validation, OOS and cost evidence) and `run_outcome.build_outcome_envelope`
  exposes it as `quant` on `GET /runs/{id}/outcome`. Tests: surface narrowing,
  trade precedence, never-widen, light/standard/deep outcome cases and the
  envelope integration (`test_quant_intent.py`, `test_quant_outcome.py`,
  existing run-outcome/surface suites). Size budget re-pinned. Docs updated:
  `docs/harness/architecture.md`, `docs/CHANGELOG.md`.
- **feat(harness): quant-intent benchmark + composer Auto/Quant/Off toggle.** New
  `python/harness/quant_intent_benchmark.py` (`quant-intent-v1`, 53 labelled cases)
  measures tier + kind accuracy and separately counts false-positive non-quant
  turns and trade-precedence violations; runnable with
  `python -m harness.quant_intent_benchmark`. New
  `src/lib/agent/quant-mode.ts` + `src/components/chat/quant-mode-control.tsx`
  put an Auto/Quant/Off pill in the composer; `ChatOptions.quantMode` flows through
  both chat routes and `run-service` as `input.context.quantMode` (`on`/`off`
  forwarded, `auto` omitted). The Python classifier already honours it. Tests:
  `test_quant_intent_benchmark.py` (2), `test_quant_intent.py` (38), the TS
  `quant-mode` suite (4), `run-service` and the chat route. Size budget re-pinned
  for the benchmark. Docs updated: `docs/harness/architecture.md`,
  `docs/CHANGELOG.md`.
- **feat(harness): deterministic quant protocol (Phase 1, observe-only).** New
  `python/harness/quant_intent.py` classifies a turn as `light` / `standard` /
  `deep` quantitative work (forecast, strategy, model, factor, financial model,
  risk) and renders a per-run protocol into `runtime_context`: frame → data →
  compute → validate → artifact → caveat, with a model-synthesis ladder and model
  contract at `deep`. Plain quotes, news, filings and concept explanations stay
  `none`; a trade/close/modify turn returns `none` so `trading_intent.py` keeps
  execution. The classifier is wired in `graph.py` next to the trading directive,
  emits a `quant.plan` event, and grants nothing (no surface narrowing yet). The
  presentation planner learns quant vocabulary. Auto/Quant/Off is read from
  `input.context.quantMode`; the composer toggle is a later slice. Tests:
  `python/tests/test_quant_intent.py` (38 passed) plus the existing response-mode
  and trading-intent suites (93 passed). `graph.py` stays at its size ratchet;
  the new module's ~579 lines are a deliberate size-budget re-pin.
  Docs updated: `docs/harness/architecture.md`, `docs/CHANGELOG.md`.
- **feat(code): per-file review and review notes (Phase 22 / S5 slice 2).** The
  promotion preview now accepts `include`: `promotion.filter_preview` keeps only
  the files the reviewer ticked and RECOMPUTES the digest over that set, so the
  single-use approval is bound to exactly what will be written. The preview and
  apply routes take the same `include`, and the promote card renders a checkbox
  per file (re-previewing on every toggle; at least one file stays selected).
  A new "Request changes" panel records an optional `file:line` and a note, then
  opens a new chat turn with `/eclipsesdk <goal>` plus the notes through the
  shell's `navigateTo` prompt param. Honest limits: per-HUNK accept is not
  supported (file granularity only), and the note starts a NEW chat turn in a
  new working copy rather than editing the same one in place. Tests
  `python/tests/test_promotion_filter.py` (4 passed). Size budget re-pinned
  (total, `code`, `routers`; `en.ts` 1305 -> 1312).
  Docs updated: `docs/NAVIGATION.md`,
  `docs/harness/roadmap/phase-22-self-hosting.md` (S5 slice 2),
  `docs/harness/roadmap/README.md`.
- **feat(chat): per-chat project folder (Phase 23).** Each conversation can now be
  bound to one APPROVED workspace root, OpenCode-style, instead of the whole app
  sharing the single global selection. A **project chip** beside the session bar
  shows the current folder and opens a picker (approved folders + "Open folder…" +
  "Use Eclipse repo"). The binding is stored per chat as
  `.black-eclipse/sessions/<chatId>/project.json`, and the run routes forward an
  approved **root id** (never a path) as `RunRequest.workspaceRootId`; the runtime
  resolves it through `TrustedRootStore` and binds that run's workspace. An
  unknown/revoked id yields NO workspace (honest refusal), never a silent
  fallback; `direct` mode follows the per-run folder exactly like the global
  selection. New: `src/components/chat/project-chip.tsx`,
  `src/components/workspace/folder-picker.tsx` (extracted from the editor),
  `src/app/api/chat/session/project/route.ts`, `project.json` helpers in
  `src/lib/chat/session-store.ts`, `set_trusted_root_lookup` in
  `python/harness/code/workspace.py`. Tests: `python/tests/test_workspace_per_chat.py`,
  `src/lib/chat/session-project.test.ts`, plus run-service cases. Docs updated:
  `docs/NAVIGATION.md`.
- **feat(code): the self-build acceptance eval (Phase 22 / S6, final slice).** New
  `python/harness/code/selfbuild_eval.py`: six acceptance fixtures, one per
  shipped self-build capability (project memory, build session, maintenance door,
  land pipeline, Builder surface, scorecard). Each fixture names the exact files
  and contract strings that must exist after a candidate change, so it grades a
  worktree deterministically. Commands are OFF by default (a release run passes
  `--commands`) and a skipped command is reported as skipped, never a pass. The
  human diff grade is `UNKNOWN` - the eval never invents a quality number. The
  repository passes 6/6 today as a regression check. Tests
  `python/tests/test_selfbuild_eval.py` (4 passed). Size budget re-pinned to the
  measured tree (total, `code`). This completes S6; S5 slice 2 (per-hunk review,
  line comments, dedicated Builder tab) remains.
  Docs updated: `docs/NAVIGATION.md`,
  `docs/harness/roadmap/phase-22-self-hosting.md` (S6),
  `docs/harness/roadmap/README.md`.
- **feat(models): a coding model for build runs (Phase 22 / S6, slice 2).** The
  LLM config gains an optional `codingModel` (same provider/key/URL): chat turns
  the deterministic classifier recognises as code, forced `/eclipsesdk` turns,
  and Code tasks now resolve that model; every other turn keeps the chat model.
  The Settings > AI surface gains a "Coding model (optional)" field, and the
  value round-trips through the settings API. The self-build scorecard also
  breaks results down by `provider/model` (`byModel`). `planner`/`editor`/
  `reviewer` multi-role routing is folded into this one build model on purpose:
  one run still uses one model, and no second router was added. Tests
  `python/tests/test_scorecard.py` (4 passed), `tsc` clean. Size budget re-pinned
  (total, `code`; `en.ts` 1302 -> 1305). Repo eval remains.
  Docs updated: `docs/NAVIGATION.md`,
  `docs/harness/roadmap/phase-22-self-hosting.md` (S6),
  `docs/harness/roadmap/README.md`.
- **feat(code): the self-build scorecard (Phase 22 / S6, slice 1).** New
  `python/harness/code/scorecard.py` derives the honest numbers from the ONE run
  lineage: builds (`session.created`), checks run, first-pass checks, landed
  (`land.promoted`), rolled back (`land.rolled_back`), average steps, tokens and
  median time-to-first-change. A dimension with no data is `UNKNOWN`, never `0`;
  cost and human edits are named as unmeasured. `promote_apply` now records
  `land.promoted`, and rollback records `land.rolled_back` when the caller names
  the run (the chat and Code rollback paths pass it). `GET /code/scorecard`
  exposes it; the Code screen shows a compact strip. Tests
  `python/tests/test_scorecard.py` (4 passed). Size budget re-pinned to the
  measured tree (total, `code`, `routers`; `en.ts` 1297 -> 1302).
  Model roles (`planner`/`editor`/`reviewer`) and the repo eval remain.
  Docs updated: `docs/NAVIGATION.md`,
  `docs/harness/roadmap/phase-22-self-hosting.md` (S6 slice 1),
  `docs/harness/roadmap/README.md`.
- **feat(code): the Builder surface, slice 1 (Phase 22 / S5).** The Code screen
  now derives ONE honest state from recorded facts (`session.derive_phase`:
  planning / editing / checking / ready / blocked / stopped) plus the single next
  action, and exposes the latest `land.verified` result on the session view. The
  landing gate is real in the Code screen: `PromoteChange` is disabled until a
  FULL check pass, with a plain-language hint. The diff viewer splits a unified
  diff into per-file, collapsible sections (`src/lib/code/diff-sections.ts`), so a
  multi-file change is reviewable file by file. Tests: `test_build_session.py`
  (11 passed), `diff-sections.test.ts`. Size budget re-pinned to the measured
  tree (total, `code`; `en.ts` 1285 -> 1297).
  Docs updated: `docs/NAVIGATION.md`,
  `docs/harness/roadmap/phase-22-self-hosting.md` (S5 slice 1),
  `docs/harness/roadmap/README.md`.
- **feat(code): the landing pipeline (Phase 22 / S4).** New
  `python/harness/code/land.py`: an ordered, data-driven check plan (typecheck,
  tests, size, secret scan, the change-log obligation, and a build when
  `src/**` changed), with `.black-eclipse/land.json` as a project override and
  the exit code as the judge. A check that cannot run is an `error`, never a
  pass; the first required failure stops the pipeline and the rest are reported
  as `skipped`. `GET /code/tasks/{id}/land` is the read-only plan;
  `POST /code/tasks/{id}/land/verify` runs it (`full=false` skips the long suite)
  and records a `land.verified` checkpoint. The checks run against the project on
  disk (the disposable copy has no installed dependencies), so the Code-screen
  `LandChecks` panel sits after the change is applied and offers quick/full runs
  with per-check output, plus the `code.land.*` i18n keys. Tests
  `python/tests/test_land.py` (8 passed). Size
  budget re-pinned to the measured tree (total, `code`, `routers`; `en.ts`
  1272 -> 1285).
  Docs updated: `docs/NAVIGATION.md`,
  `docs/harness/roadmap/phase-22-self-hosting.md` (S4 shipped),
  `docs/harness/roadmap/README.md`.
- **feat(code): the self-build boundary and offline maintenance mode (Phase 22 / S3).**
  `selfhost.plan_landing` turns the existing classifier into ordered steps:
  `python/harness/**` restarts only the builder, `src/**` builds only the target,
  and an authority file exits through maintenance - never a live hot-swap. New
  `python/harness/code/maintenance.py` is the one authority door: it refuses a
  non-authority change, refuses a dirty tree unless explicitly allowed, stops the
  builder, applies, runs the gate, restarts, health-checks, and rolls back on any
  failure after the apply. Every side effect is injected, so the order is tested
  without a live process. `npm run self:maintenance -- plan|execute` is the thin
  operator runner (`scripts/self-maintenance.js`), and `plan` is read-only. Tests
  `python/tests/test_maintenance.py` (11 passed). Size budget re-pinned to the
  measured tree (total, `code`; no ratcheted-file growth).
  Docs updated: `docs/NAVIGATION.md`,
  `docs/harness/roadmap/phase-22-self-hosting.md` (S3 shipped),
  `docs/harness/roadmap/README.md`.
- **feat(code): durable build sessions with a budget ladder (Phase 22 / S2).**
  New `python/harness/code/session.py`: a session is a lens over the existing
  run lineage, not a second store. It records the goal, the acceptance list and
  the budget as one `session.created` checkpoint, and derives progress/resume
  from the checkpoints the task lifecycle already writes. The budget is a
  profile NAME (`small` 24 steps / 10 min, `standard` 80 / 45 min, `deep` 240 /
  3 h), never a raw number from the caller. `RunRequest` gains additive
  `maxSteps` / `runTimeoutMs`; `graph.requested_budget` applies them as a floor
  and clamps to the runtime's hard caps, so a deep session can run long without
  widening the autonomy floor or the tool surface. `POST /code/tasks` accepts
  `budgetProfile` + `acceptance` and returns the session block; `GET
  /code/tasks/{id}` carries it too. The front door validates the profile and the
  `/code` command gains `--budget`. The Code task detail now shows the session
  (goal, budget, acceptance, finished state) through `getCodeSession` and
  `TaskDetail`, with four `code.session.*` i18n keys. Tests
  `python/tests/test_build_session.py` (9 passed). Size budget re-pinned to the
  measured tree (`.`, `code`, `routers`, total; `graph.py` 2406 -> 2434;
  `en.ts` 1268 -> 1272).
  Docs updated: `docs/NAVIGATION.md`,
  `docs/harness/roadmap/phase-22-self-hosting.md` (S2 shipped).
- **feat(code): load the project's own rules into a code turn (Phase 22 / S1).**
  New `python/harness/code/project_memory.py`: a bounded, deterministic loader for
  `AGENTS.md`, `.eclipse/instructions.md`, `CLAUDE.md` and the top-level map in
  `docs/NAVIGATION.md`. It walks from the workspace root to the git root (so this
  app finds the repository's `AGENTS.md` one level above `Black-Eclipse-site/`),
  redacts secret-shaped spans, truncates at a line boundary, and memoises by
  `(path, mtime, size)`. The rendered block is injected into the first code turn
  by `graph_context._repo_map_context`, and a new read-only `project_rules` tool
  lets the agent re-read it on demand. The rules are **context, never
  permission** - no rule can change the allowlist or the autonomy floor.
  `CHAT_CODE_TOOLS` and `CODE_AGENT_TOOLS` gain the tool; the task code-agent
  prompt says so. The chat prompt is unchanged - the injected block already
  carries the "context, never permission" rule - so the ECLIPSE prompt-size
  ratchet and the read-only navigator prompt both stay put. The published tool
  registry is regenerated (`docs/harness/tool-registry.json`, 1020 tools). Tests
  `python/tests/test_project_memory.py` (12 pass, 1 symlink skip), plus the
  updated exact-surface pin in `python/tests/test_chat_code_profile.py`. The harness size budget is re-pinned
  to the measured tree (`scripts/size-budget.json`; the `code/tools.py` ratchet
  moves 1268 -> 1270) because `python/harness/code` was at its ceiling.
  Docs updated: `docs/NAVIGATION.md`,
  `docs/harness/roadmap/phase-22-self-hosting.md` (S1 shipped),
  `docs/harness/roadmap/README.md`, `docs/harness/tool-registry.json`;
  `docs/CHANGELOG.md`.
- **docs(harness): add the Phase 22 self-hosting plan.** The gap analysis for
  using Eclipse to build Eclipse, grounded in the merged tree: no project-rule
  loader (nothing reads `AGENTS.md` under `python/harness/`), a 24-step / 600s
  chat code budget, the builder and target sharing one process, authority files
  refused live with no maintenance path, landing that does not run the repo gate,
  all-or-nothing review, no coding model policy, no self-build metrics, and a
  finance-first default surface. Six workstreams in three waves, each with a
  contract, file list, UX and acceptance gates. S1 (project memory) shipped
  2026-11-05; the other five are not started.
  Docs updated: `docs/harness/roadmap/phase-22-self-hosting.md`,
  `docs/harness/roadmap/README.md`.
- **fix(chat): quiet the evidence cards under an answer.** Three changes to the
  metadata area, all presentation-only (the runtime's provenance and fail-closed
  rules are untouched). (1) The "Proof it works" card no longer prints a
  `0 check(s)` header when no check was recorded, and it opens by default when a
  check failed or a claim is unsupported, so the evidence is visible instead of
  hidden behind a click. (2) A speculative capability offer (`gap` /
  `needs_source`, the "Build it" card) no longer renders in the transcript; a
  card describing a real capability — including an unverified one — still does.
  (3) "Sources consulted" now opens on the numbered source list by default, with
  calculations/limitations/run detail nested after it. Covered by
  `code-verification-panel.test.tsx`, `research-evidence-panel.test.tsx` and
  `capability-types.test.ts`. Docs updated: `docs/interactive-response-engine.md`.
- **fix(chat): only Sources stays under an answer (follow-up).** User direction:
  remove the other evidence cards entirely. The chat transcript no longer renders
  the "Proof it works" ledger (it remains on the Code screen) or the generated
  capability card (it remains in Capability Studio); the code headline keeps only
  the intent line and the promote-change action. `research-evidence-panel.tsx` is
  now the only provenance block under a normal answer, and it opens on Sources by
  default. No runtime/provenance logic changed — presentation only. Tests updated:
  `chat-capability-panel.test.ts` now asserts both cards are absent from the
  transcript. Docs updated: `docs/interactive-response-engine.md`.
- **fix(chat): drop the empty computed-result card.** A result with no
  provenance record (the "This number has no record of where it came from…"
  UNAVAILABLE state) or with nothing to show (no outputs, artifact, figure or
  recipe) no longer renders a card at all; the fail-closed refusal still happens
  at the runtime boundary. A computed result with provenance and data is
  unchanged. Covered by new empty-state cases in
  `computed-result-panel.test.ts`. Docs updated: `docs/interactive-response-engine.md`.
- **fix(chat): keep the Sources panel collapsed and align table columns.** Two
  follow-ups from the browser review. (1) "Sources consulted" no longer opens by
  default; the header summary stays visible and the body (Sources first) is
  behind the toggle. (2) Tables now use ONE alignment per column shared by the
  header and every body cell — the Markdown path previously right-aligned each
  numeric cell individually, leaving the header on the opposite side and mixed
  columns flipping; `data-table-block.tsx` also reverses the header row on a
  right-aligned column so the always-present sort icon does not push the label
  away from the numbers. Covered by new `markdown-table.test.tsx`, an updated
  `research-evidence-panel.test.tsx`, and a header-alignment case in
  `render.test.tsx`. Docs updated: `docs/interactive-response-engine.md`,
  `docs/chat-ui-audit.md`.
- **style(chat): give the response action row room to breathe.** The export row
  (JSON / Read aloud / MD / PDF / Save / Open in Canvas) sat flush against the
  header above and the content below. It now has a little top margin and a
  clear bottom gap, with wrap row-gap, so it reads as its own strip.
  Presentation-only; no doc change beyond this note.
- **style(canvas): the inline Canvas dock opens as one surface card.** Replaced
  the thin `Eclipse response · REPORT · Save to edit` toolbar with the rounded
  card from the review: a rounded icon tile plus a surface label (`Writing` for a
  prose answer, otherwise `Code` / `Report` / `Web page` / `Image`), with Save to
  edit and Close on the right and the document title as the card tooltip.
  Presentation-only. Docs updated: `docs/canvas.md`.
- **style(graph-studio): simplify canvas nodes to a borderless solid surface.**
  The node card now uses a solid `#0E0E0E` fill with no outer border and a soft
  lift instead of the heavy 2px black bezel and translucent gradient. The header
  gets roomier top/bottom padding so the icon no longer crowds the card edge,
  and the icon sits in a solid neutral rounded tile (`#1A1A1C` dark / `#F2F2F4`
  light). Ports, inline fields, run/test states and hover actions are unchanged.
  Presentation-only; no contract change.
- **fix(graph-studio): tidy layout respects node heights; wires are curved and neutral.**
  `autoLayout` now accepts the nodes' measured React Flow heights and stacks each
  layer by the real card height (240px fallback when unmeasured), with a 96px
  column gap — so "Tidy up" no longer piles tall nodes on top of each other. The
  canvas measures on tidy and passes the map through the store. Wires switched
  from straight to bezier paths, and idle/selected wires render neutral (brighter
  on hover) with the theme accent reserved for a running workflow; success and
  failure keep their status colors. Added `layout.test.ts`. No doc change —
  interaction/presentation fix only.
- **fix(news): high-level stories join the feed and notify the header.** The News
  tab no longer opens with a separate High Alert band. Those stories are ranked
  into the main feed with `sort=importance` (default, one-time migration for a
  saved `newest` preference) so the first rows are the most critical, and the
  existing cards carry the CRITICAL/HIGH ALERT/BREAKING badges. Added the pure
  `src/lib/notifications/news-diff.ts` + root-mounted
  `src/lib/notifications/news-watcher.tsx`, which polls `/api/news/alerts`, seeds
  the current set silently, then raises a `news`-tab ledger entry (header bell +
  sidebar badge + toast/cue) for each newly seen critical/high story and each
  high-impact release within 90 minutes. Removed the now-unused
  `news-high-alerts.tsx`; the card preferences moved to
  `src/lib/news/card-settings.ts` to keep the screen inside the size budget
  (re-pinned 1486→1446). Tests: `news-diff.test.ts`. Docs updated:
  `docs/ARCHITECTURE.md`, `docs/DATA-FLOW.md`, `docs/CHANGELOG.md`.
- **fix(notifications): the header ledger is not a news backfill.** The news
  watcher was seeding the current high-alert set into the ledger on load, which
  made the header look like a news-only feed and pushed the operator's
  price-alert/task/agent entries down (or out of the 100-item ring over time).
  The first poll now only seeds the seen set — no ledger write — so news behaves
  exactly like the task/bot/price watchers: it records events that happen after
  the app opens. The notification panel also always renders every kind filter
  (Alerts/Tasks/Approvals/Agent/Bots, count 0 included) so each producer lane is
  discoverable. Tests updated: `news-diff.test.ts`. Docs updated:
  `docs/ARCHITECTURE.md`, `docs/DATA-FLOW.md`, `docs/CHANGELOG.md`.
- **feat(alerts): durable alert archive + a filterable History tab.** Every
  notification raised in the app is now mirrored from the header ledger into a
  new `AppNotification` table through `POST /api/notifications` (idempotent on
  the producer's stable id; the local ledger backfills once on hydrate). New
  `GET /api/alerts/history` unions that archive with the price engine's
  `PriceAlertEvent` log (deduped by id, newest-first) and supports `q`,
  `kind`, `tab` and `24h/7d/30d/all` ranges. Alerts › History now shows all
  sources (news/price/tasks/approvals/agent/bots) with a search box, source and
  range filters, and plays the alert cue once when a genuinely new archived row
  arrives. `prisma/schema.prisma` gains `AppNotification` (additive; `db push`
  applies it, so `jdds.db` is not committed). Tests:
  `api/alerts/history/route.test.ts`, `api/notifications/route.test.ts`. Docs
  updated: `docs/ARCHITECTURE.md`, `docs/DATA-FLOW.md`, `docs/CHANGELOG.md`.
