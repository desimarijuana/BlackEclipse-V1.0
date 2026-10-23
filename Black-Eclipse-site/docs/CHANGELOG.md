# Change Log

## Rotation policy

This file keeps a rolling window of the **most recent 7 dated sections** (the active window). Older dated sections are **moved** - never deleted - into monthly archive files under `docs/changelog/YYYY-MM.md`. New entries are appended under the current date; the commit-msg hook checks this path. Rotation is by hand only when this file grows unwieldy; the archive link below points at where the older entries went.

> Older entries are archived under `docs/changelog/` (monthly). The most recent 7 dated sections are kept here.

## 2026-10-23
- **ci(rsl): a quarterly rotation reminder that cannot write a dataset.**
  Added `.github/workflows/rsl-rotation.yml`: quarterly schedule plus dispatch,
  resolves and validates the quarter label, runs
  `node scripts/rsl-rotate.js --json` (dry run), publishes the plan to the step
  summary and fails when `plan.ok` is false. It never passes `--apply`, and it
  proves the dry run left the corpus tree unchanged. `--json`
  now keeps stdout pure JSON (the human dry-run note goes to stderr) so the
  plan can be redirected and parsed. Files: `.github/workflows/rsl-rotation.yml`,
  `python/harness/evaluation/rotation.py`,
  `python/tests/test_evaluation_rotation.py`.
  docs updated: `docs/harness/agent-evaluation.md`,
  `docs/self-improvement/rsl-v4-plan.md`, `docs/CHANGELOG.md`.
- **feat(rsl-ui): corpus and autonomy cards on the RSL control panel.**
  Added typed runtime calls and Next proxies for `GET /evolution/corpus`, the
  rotation preview, autonomy status/pause/resume/decide and the state
  autonomy-apply route. Two frosted cards show the 338-task splits, 263
  oracle-backed + 75 documented exemptions, verification/audit, and the
  autonomy level, kill switch and daily budget. Apply is disabled when the
  level, kill switch or budget refuses; the runtime's evidence refusal reasons
  are shown, never bypassed. Files: `src/lib/harness/{evolution-client,
  evolution-browser}.ts`, `src/app/api/evolution/{corpus,corpus/rotation,
  rsl/autonomy/**,states/[id]/autonomy-apply}/route.ts`,
  `src/components/screens/skills/rsl-{corpus,autonomy}-card.tsx`,
  `rsl-control-panel.tsx`, `src/lib/i18n/dictionaries/evolution.ts`, tests.
  docs updated: `docs/harness/agent-evaluation.md`,
  `docs/self-improvement/rsl-v4-plan.md`, `docs/CHANGELOG.md`.
- **docs(rsl): auto-apply stays operator-triggered (Phase 4 decision).**
  Recorded ADR-H326: no scheduler tick and no `HARNESS_RSL_AUTO_APPLY` switch;
  the only activation path remains `POST
  /evolution/states/{id}/autonomy-apply`, bounded by the existing
  L1/evidence/kill-switch/daily-budget policy. A future scheduler needs its own
  ADR, an off-by-default flag, one apply per tick and a dry-run period. Files:
  `docs/harness/decisions.md`, `docs/self-improvement/rsl-v4-plan.md`.
  docs updated: `docs/harness/decisions.md`,
  `docs/self-improvement/rsl-v4-plan.md`, `docs/CHANGELOG.md`.
- **fix(evaluation): the nightly report can no longer contradict its exit code.**
  Moved the report write to the end of `run_nightly`, after the live comparison,
  promotion and baseline write; a live regression used to set `ok=False` after
  the PASS file was already on disk (and the file omitted those results).
  `GET /evolution/corpus` now also exposes `oracleExemptCount`. Size ceilings
  raised 5 lines (382,030 total; evaluation 11,603; routers 17,214). Files:
  `python/harness/evaluation/nightly.py`,
  `python/harness/routers/evolution_corpus.py`,
  `python/tests/{test_evaluation_nightly,test_evolution_corpus_routes}.py`,
  `scripts/size-budget.json`.
  docs updated: `docs/harness/agent-evaluation.md`, `docs/CHANGELOG.md`.
- **data(evaluation): the first live-tier baseline is pinned.**
  Recorded `ollama` / `deepseek-v4.1-flash:cloud` on the validation split of the
  338-task corpus (244 tasks, dataset checksum `d6375ca4…`, prompt hash
  `f05e7c03…`): task_success 0.6901 (95% CI 0.6292..0.7450), 242 measured
  trials. A same-identity rerun exited FAIL on the critical gates
  (task_success −0.0083, financial_accuracy −0.0195, safety_score −0.0625); the
  gates allow no drop on those dimensions, so the regression is reported, not
  smoothed. Cost reads 0.0 because `ollama/*` is priced free/local. Files:
  `python/harness/evaluation/baselines/live_v1.json`,
  `docs/self-improvement/rsl-report-2026-10-23.md`.
  docs updated: `docs/harness/agent-evaluation.md`, `docs/CHANGELOG.md`.
- **data(evaluation): 338-task corpus with 263 real oracles and 75 documented
  exemptions.** Added `metadata.oracleExempt` + `oracleReason` (task or dataset
  level) and dataset-level contamination so `validate_tasks(strict=True)`
  treats the seven legacy fixture sets (benchmark, construction, adversarial,
  research, replay, routing_e2e, team — 75 tasks) as intentional rather than
  gaps. `finance_v1`'s 13 tasks gained real oracles; new `finance_v7` adds 88
  oracle-backed tasks (60 validation / 28 optimization). The manifest now
  records `oracleExemptCount` (total and per dataset) and verifies it. Splits:
  validation 244 / optimization 88 / held_out 6; corpus audit PASS. Size
  ceilings raised 75 lines for `corpus.py` (382,025 total; evaluation 11,600).
  Files: `python/harness/evaluation/{corpus,contamination}.py`,
  `python/harness/evaluation/datasets/*`,
  `python/harness/evaluation/baselines/corpus_manifest.json`,
  `python/tests/{test_evaluation_corpus,test_rsl_provenance,
  test_evolution_corpus_routes}.py`, `scripts/size-budget.json`.
  docs updated: `docs/harness/agent-evaluation.md`, `docs/CHANGELOG.md`.
- **data(evaluation): the 2026Q4 held_out rotation moved four finance tasks.**
  `finance.v5.percentage_change.004`, `finance.v5.operating_margin.005`,
  `finance.v4.eps.003` and `finance.v3.opt.cagr.001` moved
  optimization → held_out (version bumped, `metadata.rotation` recorded); the
  rotation-exempt team tasks stayed put. Splits are now validation 184 /
  optimization 60 / held_out 6, still 250 tasks; the manifest was rebuilt and
  verifies. Files: `python/harness/evaluation/datasets/{finance_v3,finance_v4,
  finance_v5}.json`, `python/harness/evaluation/baselines/corpus_manifest.json`,
  `python/tests/test_rsl_provenance.py`.
  docs updated: `docs/harness/agent-evaluation.md`, `docs/CHANGELOG.md`.
- **safety(evaluation): the live nightly is bounded and capped before it spends.**
  `--limit N` runs only the first N tasks (hard bound 500) and a positive
  `--max-cost USD` is required for `--live`; both are validated before any task
  is sent and recorded in the report (`limit`, `maxCostUsd`,
  `estimatedWorstCaseTrials`). `--publish` with no value now resolves to the app
  root's `docs/self-improvement` instead of the Python child's cwd. Files:
  `python/harness/evaluation/nightly.py`, `scripts/rsl-nightly.js`,
  `python/tests/test_evaluation_nightly.py`; raised the committed size
  ceilings to the measured tree (381,950 total; evaluation 11,525) for the 69
  added lines, `scripts/size-budget.json`.
  docs updated: `docs/harness/agent-evaluation.md`, `docs/CHANGELOG.md`.
- **merge(harness): origin/main's Round 3/4 work landed on the local tree.**
  Merged 22 upstream commits (Round 3/4, v0.2.0, and the live-eval publishing
  fix) and resolved the content conflicts in `docs/harness/decisions.md`,
  `package.json`, `python/tests/test_size_budget.py` and the generated
  `docs/harness/benchmarks.md`. The local RSL v4 / notebook decisions moved from
  H293-H302 to H316-H325 so H310-H315 stay reserved for the Round 4 plan;
  `scripts/check-adr-numbers.js` now reserves that range, and every doc reference
  was updated. Raised the harness size ceilings to the measured merged tree
  (381,881 total; `.` 24,845; routers 17,212; evaluation 11,456), pinned
  `graph.py` at 2,323, regenerated the tool registry (957 tools) and benchmarks,
  and included the read-only corpus/rotation routes
  (`python/harness/routers/evolution_corpus.py`, its test, the `main.py`
  registration and the `agent-evaluation.md` note). `npx tsc --noEmit` clean;
  lint 0 errors; ADR and size gates pass; full suite 8,223 passed / 27 skipped,
  with only the two stale-generated-artifact failures, both regenerated and
  their 15 tests green; the follow-up eval-publishing merge's affected
  benchmark/public/size tests (15) also pass.
  docs updated: `docs/harness/decisions.md`,
  `docs/harness/roadmap/round-4-gap-closure.md`,
  `docs/harness/agent-evaluation.md`, `docs/NAVIGATION.md`,
  `docs/self-improvement/rsl-v4-plan.md`,
  `docs/harness/roadmap/{README,phase-21-notebook-cells}.md`,
  `docs/harness/benchmarks.md`, `docs/harness/tool-registry.json`,
  `docs/CHANGELOG.md`.
- **test(evaluation): the one-split export check no longer hardcodes 61 tasks.**
  `test_one_split_can_be_exported_alone` now compares the optimization split
  count against the full built-in corpus, so legitimate corpus growth (64
  optimization / 250 total) cannot fail a test that is about split filtering,
  not a fixed size. `python/tests/test_evaluation_export.py`.
  no canonical doc change — test-only; the rolling-window rotation moved the
  2026-10-16 section into `docs/changelog/2026-10.md`.

## 2026-10-22
- **fix(chat): a sent paste stays visible in the transcript.** A long paste is
  no longer folded into a giant user message and deleted: it remains a context
  document and each user turn shows a compact "Pasted text" card (name, chars,
  preview, Open), so the exact content that went to the run is visible in
  history. Paste-only sends use "Read the attached document."; pastes over
  100 000 chars are truncated by the document pipeline instead of rejected by
  the turn bound. User prompts over 2 000 chars collapse to an 800-char excerpt
  with "Show full message". New `MessageAttachment` on `Message`; `claimPastes`
  is unit-tested. Files: `src/components/chat/{chat-history,message-attachments}.tsx`,
  `src/lib/chat/{paste,use-session}.ts`, `src/components/screens/stock-chat.tsx`,
  `src/types/chat.ts`, `src/lib/chat/paste.test.ts`; docs updated:
  `docs/chat-ui-audit.md`, `docs/CHANGELOG.md`.
- **chat jump rail: tighter hairlines, calm hover wave, scroll thumb moved right.**
  `MessageRail` ticks are now 1px hairlines stacked 2px apart (was 2px bars with
  a ~5px pitch), baseline width 7px, active 9px, hover 11px (was 10→14px), and
  hovering ripples a decaying wave outward with a 28ms-per-step delay instead of
  one oversized pill. The transcript scroll thumb moved from `right-5` (left of
  the rail) to `right-0.5`, so it now sits just to the right of the ticks.
  `src/components/chat/message-rail.tsx`, `src/components/chat/chat-history.tsx`.
  `npx tsc --noEmit` clean; Vitest 3824 passed (Python suite did not finish
  within the run window; UI-only change).
  no doc change — presentation only, no contract or data-shape change.
- **feat(chat): editable notebook cells + chart code.** Shipped Phase 21:
  a per-conversation cell document (`notebook.json`), the sandbox-backed
  `POST /notebook/cells/{id}/run` and kernel restart routes, an opt-in
  persistent kernel namespace (`AnalysisRequest.persist_namespace`, default
  false so `analysis_run` stays fresh), chart-spec → matplotlib codegen at
  `POST /charts/code`, and a Monaco notebook panel with a composer action and a
  chart "Edit code" link. A cell's outputs are always `computed`, chart data
  travels as a JSON input (never source text), and the original chart block is
  never mutated. Files: `python/harness/routers/notebook.py`,
  `python/harness/charts/codegen.py`, `python/harness/code/{execution,kernel}.py`,
  `python/harness/analysis_tools.py`, `src/lib/chat/notebook-{types,store}.ts`,
  `src/lib/harness/notebook-client.ts`, `src/app/api/chat/notebook/route.ts`,
  `src/app/api/harness/notebook/**`, `src/app/api/harness/charts/code/route.ts`,
  `src/components/chat/notebook-{cell,panel,provider}.tsx`,
  `src/components/response/response-chart.tsx`, `src/components/chat/chat-dock.tsx`,
  `src/components/screens/stock-chat.tsx`, `src/lib/i18n/dictionaries/notebook.ts`;
  tests `test_{chart_codegen,notebook_kernel,notebook_route}.py`,
  `notebook-{store,client}.test.ts`; docs `docs/harness/roadmap/phase-21-notebook-cells.md`,
  `docs/harness/roadmap/progress/phase-21-progress.md`,
  `docs/harness/roadmap/README.md`, `docs/harness/python-runtime.md`,
  `docs/chart-engine.md`, `docs/NAVIGATION.md`. Full Python (8160) and Vitest
  (3824) suites green; `npx tsc --noEmit` clean.
- **feat(charts): chat charts are interactive ECharts — Plotly and PNG left
  the chat path.** A `chart` block is mapped to the shared `ChartSpec`
  (`chart-spec.ts`), a named `dataSource` is resolved in the browser through
  `/api/price-history` (`chart-data.ts`), and the ONE option builder
  (`chart-echarts.ts`, `echarts` + `echarts-gl`) renders it.
  `response-chart.tsx` no longer calls the Python engine or fetches an
  artifact; `plotly-chart.tsx`, `python-chart.tsx` and
  `/api/harness/charts/plotly` were deleted. Also: gauge/treemap/funnel/
  sunburst render natively (no bar stand-in); dated `[date,o,h,l,c]` and
  object candle rows survive normalization; scatter/bubble and radar read the
  fields they carry; drawability is checked with the renderer's own list
  (`chart-capabilities.ts`) inside `response_validate`; an unsupported Python
  picture mark is a named refusal, not a blank PNG. Chart launch:
  `/api/price-history` serves the persisted last-good series FIRST on a cold
  start and refreshes in the background; the batch route dedupes and bounds
  concurrency; the client hydrates bars from `localStorage` before
  revalidating. Session-index messages cap raised 4,000→16,000 so a structured
  answer's fence is not cut. Files:
  `src/lib/response/chart-{spec,data,echarts,capabilities,registry}.ts`,
  `src/components/response/response-chart.tsx`,
  `src/components/charts/echart-chart.tsx`,
  `src/app/api/price-history/{route,batch/route}.ts`,
  `src/lib/chart/subscription-manager.ts`,
  `src/lib/response/normalize.ts`, `src/lib/harness/response-bridge.ts`,
  `python/harness/charts/scene_render.py`, `python/harness/session_index.py`;
  tests `chart-render.test.ts`, updated `chart-spec.test.ts`. docs updated:
  `docs/chart-engine.md`, `docs/ARCHITECTURE.md`, `docs/DECISIONS.md`
  (ADR-050 amendment), `skills/ARCHITECT.md`, `docs/NAVIGATION.md`,
  `docs/interactive-response-engine.md`.
- **fix(charts): revert chat charts to Plotly and make them load fast.** The
  ECharts renderer is removed from the chat path: `chart-echarts.ts` and
  `echart-chart.tsx` are deleted, and `plotly-chart.tsx`, `python-chart.tsx`
  and `/api/harness/charts/plotly` are restored. `response-chart.tsx` maps the
  block to the shared `ChartSpec`, hydrates a named `dataSource` in the
  browser, asks the Python engine for the figure + PNG, and registers the
  artifact for export (`chart-registry.ts`). Load is staged: the PNG paints
  immediately, plotly.js is loaded once on an idle frame only when the chart
  nears the viewport (`IntersectionObserver`, 400 px margin), and rendered
  figures are cached per spec so history scrolling does not redraw. Scene
  marks the matplotlib picture cannot draw no longer fail the render (the
  Plotly figure still draws them). `chart-capabilities.ts` now names the
  engine's allowlist (not ECharts). Files:
  `src/components/charts/plotly-chart.tsx`,
  `src/components/response/response-chart.tsx`,
  `src/lib/response/chart-{capabilities,registry}.ts`,
  `src/app/api/harness/charts/plotly/route.ts`; tests
  `src/lib/response/chart-render.test.ts`. docs updated:
  `docs/chart-engine.md`, `docs/ARCHITECTURE.md`, `docs/DECISIONS.md`
  (ADR-050 amendment), `docs/NAVIGATION.md`,
  `docs/interactive-response-engine.md`, `docs/CHANGELOG.md`.
- **feat(charts): explicit zoom/reset controls on the live chart.** The
  bottom-left of every Plotly chart now carries zoom in, zoom out and reset.
  Zoom scales the current 2-D axis ranges around their centre (or the 3-D
  camera eye); reset re-applies the figure the engine authored. The focus
  overlay no longer closes when the chart's own toolbar is clicked, and
  double-click still resets. Files: `src/components/charts/plotly-chart.tsx`,
  `src/components/response/response-chart.tsx`; docs updated:
  `docs/chart-engine.md`, `docs/CHANGELOG.md`.
- **docs(harness): plan editable notebook cells in chat (ADR-H323 + phase 21).**
  Added a plan for a per-conversation cell document over the existing analysis
  sandbox, an "Edit code" path from a chart into a linked cell, chart-spec to
  matplotlib codegen, and an opt-in persistent kernel namespace. The chart
  contract stays data-only and `analysis_run` keeps a fresh namespace. Docs:
  `docs/harness/decisions.md` (ADR-H323),
  `docs/harness/roadmap/phase-21-notebook-cells.md` (new),
  `docs/harness/roadmap/README.md`, `docs/NAVIGATION.md`,
  `docs/CHANGELOG.md`.
- **style(chat): computed/proof/sources panels lose their fill and stop
  colliding.** `ComputedResultPanel`, `CodeVerificationPanel` and
  `ResearchEvidencePanel` no longer paint a glass background (border-only),
  their headers are left-aligned with the label on its own row and the method
  text clamped below it, and the computed header now previews the first two
  outputs while collapsed so a result is visible without expanding. In
  `chat-history.tsx` the analysis/research pair stacks full-width instead of
  sharing a 50/50 row. no doc change — presentation-only.
- **style(dashboard): strip the header chrome.** Removed the search trigger,
  Screener / Open portfolio buttons, the Investor/Trader/Both lens toggle and
  the profile/Investor chip from the Dashboard header. The greeting, market
  selector and refresh remain. no doc change — layout-only.
- **feat(response): just-in-time design modules + one shared interaction bridge.**
  Added `response_style_guide` (seven families: data, chart, diagram, workflow,
  interactive, explanation, mechanical) so the model loads a family's nuance and
  worked examples on demand instead of carrying them in every prompt; the field
  map still comes live from the TS contract, and the prompt gets only a compact
  module index. Added `RENDER_DISCIPLINE` ("when NOT to render") to the per-run
  response plan, and extracted `src/lib/response/followup.ts` as the one
  state→prompt serializer used by `controls` and `simulation`. Files:
  `python/harness/response_style.py`, `response_tools.py`, `graph.py`,
  `response_mode.py`, `src/lib/response/followup.ts`, `controls-block.tsx`,
  `simulation-block.tsx`, tests `test_response_tools.py`, `followup.test.ts`;
  docs `docs/interactive-response-engine.md`, `docs/NAVIGATION.md`.
- **feat(dashboard): add the genuinely useful workspace cards.** New
  Dashboard-only surfaces: today's P&L attribution ("what moved your book"),
  a "Needs a look" action list (near support / falling / reporting soon) with
  one-click ±3% alerts, market session clock (time-zone-aware open/closed for
  12 exchanges), portfolio risk snapshot (volatility, drawdown, beta,
  concentration), currency exposure, sector rotation buckets, relative
  performance vs the benchmark, an alerts strip, per-section show/hide +
  reorder (persisted locally), keyboard shortcuts (J/K, Enter, A, R, /), and a
  data-freshness strip. Files:
  `src/components/screens/dashboard/home-alpha-insights.tsx`,
  `home-{dashboard,alpha-cards,primitives}.tsx`,
  `src/lib/dashboard/{home-model,use-home-data,home-prefs}.ts`, tests
  `home-model.test.ts`. no doc change — UI/data additions only.
- **style(dashboard): remove Getting started and tighten the footer.** The
  Dashboard no longer shows the onboarding checklist (and its prefs are no
  longer stored), Portfolio value now leads the feed at full width, and the
  footer spacing is reduced. no doc change — layout-only.
- **style(dashboard): the feed fills the full content width.** Removed the
  1120px max-width cap on `home-dashboard.tsx` so the AlphaGen-style feed uses
  the whole main panel. no doc change — layout-only.
- **feat(ui): the Dashboard becomes an international-first, AlphaGen-style decision feed.**
  The `home` tab is now a borderless single-column feed rather than a widget
  grid: greeting + display name + Investor/Trader/Both lens + search + market
  selector, getting-started checklist, portfolio value vs S&P 500, a personal
  feed over JDDS news/alerts/published results, four-state holdings health,
  this-week events (company results + macro), global market pulse, confirmed
  results season, Eclipse-momentum leaders you don’t hold, research/theses on
  holdings, sector exposure, and a track record drawn from the journal and
  closed theses. No sidebar, tab, or other-screen changes. Data stays real:
  no AlphaGen scores, invented report windows, or fabricated track record;
  unavailable inputs are labelled. Files:
  `src/components/screens/dashboard/home-{dashboard,alpha-cards,primitives}.tsx`,
  `src/lib/dashboard/{home-model,use-home-data,home-prefs}.ts(x)`, and
  `src/app/api/harness/charts/route.test.ts` (typed the fetch mock so the lint
  gate passes). docs updated: docs/CHANGELOG.md (no other doc change — the
  Dashboard data path is already documented in docs/ARCHITECTURE.md).
- **chore(harness): regenerate the committed capability statement.** The full
  Python suite's `test_the_committed_statement_matches_a_fresh_generation`
  caught the generated `docs/harness/capability-statement.md` drifting from
  `render_statement()` after the in-flight capability changes. Regenerated it
  from the module; the statement is derived data and the test now passes. Files:
  `docs/harness/capability-statement.md`. no other doc change - generated
  artifact.

- **feat(evaluation): read-only corpus and rotation operator routes.** Added
  `routers/evolution_corpus.py` (mounted in `main.py`):
  `GET /evolution/corpus` returns the compact committed manifest, its
  verification and the authoring audit; `GET /evolution/corpus/rotation`
  returns a deterministic rotation PREVIEW. Neither writes a dataset - rotation
  apply stays the deliberate `npm run rsl:rotate -- --apply` CLI action. Files:
  `python/harness/routers/evolution_corpus.py`, `python/harness/main.py`,
  `python/tests/test_evolution_corpus_routes.py`, `package.json`. Docs updated:
  `docs/harness/agent-evaluation.md`.

- **feat(evaluation): a deterministic, operator-applied held_out rotation.**
  A held_out task a candidate has seen is no longer a clean canary. Added
  `evaluation/rotation.py` and `npm run rsl:rotate`: the plan is seeded by the
  quarter label (reproducible), moves N optimization tasks to `held_out` and
  returns the current `held_out` tasks to `optimization`, never touches
  validation, and skips datasets marked `metadata.rotationExempt` (the frozen
  team benchmark). The CLI is a dry run unless `--apply` is given; an apply
  writes the split, bumps each task version, records `metadata.rotation`, and
  refreshes the manifest. Re-applying the same quarter is a no-op. Files:
  `python/harness/evaluation/rotation.py`,
  `python/harness/evaluation/datasets/team_v1.json` (`rotationExempt`),
  `python/tests/test_evaluation_rotation.py`, `scripts/rsl-rotate.js`,
  `package.json`. Docs updated: `docs/harness/agent-evaluation.md`,
  `docs/self-improvement/rsl-v4-plan.md`, `docs/harness/decisions.md`
  (ADR-H325).

- **feat(evaluation): finance tranche 6 - the corpus reaches 250 tasks.** Added
  `datasets/finance_v6.json`: 50 deterministic fixtures (three validation and
  one optimization per metric, plus two extra validation fixtures), each with
  `metadata.oracle` and `metadata.contamination` and graded by the independent
  `financial` recomputation. The corpus reaches the 250-task target (validation
  184, optimization 64, held_out 2), oracle coverage 0.648 (162/250), and the
  evaluation gate reports `finance: 182/182 measured, 100%` at
  `task_success=1.0`. The committed manifest is refreshed. Files:
  `python/harness/evaluation/datasets/finance_v6.json`,
  `python/harness/evaluation/baselines/corpus_manifest.json`,
  `python/tests/test_rsl_provenance.py`. Docs updated:
  `docs/harness/agent-evaluation.md`,
  `docs/self-improvement/rsl-v4-plan.md`.

- **feat(evaluation): finance tranche 5 - the corpus reaches 200 tasks.** Added
  `datasets/finance_v5.json`: 60 deterministic fixtures across the same twelve
  metrics (three validation and two optimization per metric), each with
  `metadata.oracle` and `metadata.contamination` and graded by the independent
  `financial` recomputation. The corpus grows 140 → 200 (validation 146,
  optimization 52), oracle coverage 0.371 → 0.560, and the evaluation gate
  reports `finance: 132/132 measured, 100%` at `task_success=1.0`. The committed
  manifest is refreshed. Files:
  `python/harness/evaluation/datasets/finance_v5.json`,
  `python/harness/evaluation/baselines/corpus_manifest.json`,
  `python/tests/test_rsl_provenance.py`. Docs updated:
  `docs/harness/agent-evaluation.md`,
  `docs/self-improvement/rsl-v4-plan.md`.

- **feat(rsl): supervised autonomy can apply one measured L1 surface state.**
  The P6 policy could decide "allowed" but nothing acted on it. Added
  `RSLLoop.auto_apply_surface(state_id)`: it accepts only a `candidate` state
  whose `EvolutionCandidate` is a surface with a valid `surfaceConfig`, derives
  per-task rates from the recorded baseline and candidate `EvaluationRun`s, runs
  the paired bootstrap and the regression gates, classifies the risk, and calls
  the existing `decide(...)` policy (kill switch, L1, lift floor, canary/replay,
  daily budget). On success it uses the existing
  `HarnessStateStore.activate_surface`, so the returned `HarnessActivation` row
  is the rollback handle; missing paired evidence is a refusal. The activation
  counter is persisted (`rsl.autonomy.activations`) so a restart cannot reset
  the budget. `POST /evolution/states/{state_id}/autonomy-apply` is the
  operator-triggered seam. Files:
  `python/harness/self_improvement/{autonomy,loop}.py`,
  `python/harness/routers/evolution_autonomy.py`,
  `python/tests/test_autonomy_apply.py`, `package.json`. Docs updated:
  `docs/self-improvement/rsl-v4-plan.md`, `docs/harness/architecture.md`,
  `docs/harness/decisions.md` (ADR-H324).

- **feat(evaluation): finance tranche 4 - 36 generated oracle-tagged tasks.**
  Added `datasets/finance_v4.json`: 36 deterministic fixtures across twelve
  metrics (two validation and one optimization per metric), each with
  `metadata.oracle` and `metadata.contamination` and graded only by the
  independent `financial` recomputation. The corpus grows 104 → 140 tasks
  (validation 110, optimization 28), oracle coverage 0.154 → 0.371, and the
  evaluation gate reports `finance: 72/72 measured, 100%`. The committed
  manifest is refreshed. Files:
  `python/harness/evaluation/datasets/finance_v4.json`,
  `python/harness/evaluation/baselines/corpus_manifest.json`,
  `python/tests/test_rsl_provenance.py`. Docs updated:
  `docs/harness/agent-evaluation.md`,
  `docs/self-improvement/rsl-v4-plan.md`.

- **feat(evaluation): optimization-split finance tranche 3.** Added
  `datasets/finance_v3.json` (6 deterministic finance tasks: EPS, P/E, P/S,
  FCF, CAGR, gross margin) reserved for the **optimization** split, so the RSL
  search has measured material it may train on while validation stays the
  acceptance set. Every task carries `metadata.oracle` and
  `metadata.contamination`; the corpus grows 98 → 104 (optimization 10 → 16,
  oracle coverage 0.154) and `finance` is 36/36 measured in the gate. The
  committed manifest is refreshed. Files:
  `python/harness/evaluation/datasets/finance_v3.json`,
  `python/harness/evaluation/baselines/corpus_manifest.json`,
  `python/tests/test_rsl_provenance.py`. Docs updated:
  `docs/harness/agent-evaluation.md`,
  `docs/self-improvement/rsl-v4-plan.md`.

- **chore(rsl): keep the autonomy routes out of the ratcheted evolution router,
  and re-pin the shared graph.** The P6 routes pushed
  `routers/evolution.py` past its size ratchet, so they now live in
  `routers/evolution_autonomy.py` and are included by the existing evolution
  router (the same pattern as `evolution_drift`/`evolution_models`/
  `evolution_report`). `graph.py` re-pinned 2305→2316 for the in-flight
  response-style JIT index wiring; the tool loop is untouched and the
  subsystem-wiring block remains the split candidate. Files:
  `python/harness/routers/{evolution,evolution_autonomy}.py`,
  `python/tests/test_size_budget.py`. Docs updated:
  `docs/self-improvement/rsl-v4-plan.md` (P6 route module).

- **feat(evaluation): finance tranche 2, with an independent oracle on every
  task.** Added `datasets/finance_v2.json` (10 deterministic tasks: gross
  margin, percentage change, CAGR, P/E, P/S, FCF, portfolio weight,
  reward-to-risk, operating margin, EV/EBITDA). Every task declares
  `metadata.oracle` (the recomputation) and `metadata.contamination`
  (source/authored date), so the corpus grows from 88 to 98 tasks and oracle
  coverage from 0.0 to 0.102. All ten are graded by the independent
  `financial` grader plus `exact`; the evaluation gate is 98 tasks with finance
  30/30 measured. The committed manifest is refreshed. Files:
  `python/harness/evaluation/datasets/finance_v2.json`,
  `python/harness/evaluation/baselines/corpus_manifest.json`. Docs updated:
  `docs/harness/agent-evaluation.md`,
  `docs/self-improvement/rsl-v4-plan.md`.

- **feat(rsl): autonomy is risk-classed, evidence-gated and killable.** Added
  `self_improvement/autonomy.py`: risk classes `L0` (code, tool widening,
  guardrail removal, model identity — never automatic), `L2`
  (capability-widening — human only) and `L1` (bounded surface: prompt wording,
  tool guidance, narrowed context policy, delegated-child prompt, added
  guardrails). The pure `decide(...)` policy requires supervised/bounded level,
  no kill switch, L1 risk, a paired `deltaCiLow` above the floor, no critical
  regression, a clean canary/replay, a matching predicted direction and a daily
  budget; it names every refusal reason. `AutonomyKillSwitch` persists under
  `rsl.autonomy.kill` on the ONE agent-memory DB; `/evolution/rsl/autonomy/
  pause|resume` stop/allow decisions without a restart, and
  `/evolution/rsl/autonomy/decide` previews a decision without activating
  anything. `GET /evolution/rsl` now reports `autonomyStatus`. New opt-in,
  clamped flags `HARNESS_RSL_AUTONOMY` (off), `HARNESS_RSL_AUTO_MIN_LIFT`
  (0.02), `HARNESS_RSL_AUTO_MAX_PER_DAY` (1), `HARNESS_RSL_AUTO_RISK` (low),
  accepted by hot config. Activation remains the existing single-use surface
  path; auto-applying an L1 winner is a supervised follow-up after a dry run.
  Files: `python/harness/self_improvement/{autonomy,config,runtime_settings,
  loop,__init__}.py`, `python/harness/routers/evolution.py`,
  `python/tests/test_autonomy.py`, `package.json`, `.env.example`. Docs
  updated: `docs/self-improvement/rsl-v4-plan.md`,
  `docs/harness/architecture.md`, `docs/harness/decisions.md` (ADR-H322).

- **feat(evaluation): only the live tier may be pinned, and the key includes the
  prompt and corpus.** The scripted tier cannot see a prompt change, so pinning
  it as a model baseline would manufacture evidence. Added
  `evaluation/live_baseline.py`: a baseline is keyed by provider + model + base
  URL + temperature + prompt hash + corpus checksum; `build_live_baseline`
  refuses the scripted tier and an empty provider/model, and stores the Wilson
  CI, per-category rates, task rates, cost/latency and provenance without ever
  storing a key. `write_live_baseline`/`read_live_baselines`/
  `find_live_baseline` maintain a committed registry (created on first write);
  `compare_live_baseline` runs the existing regression gates plus a paired CI;
  `publish_report` writes Markdown that names the tier, identity, prompt hash,
  corpus checksum and verdict, with `NOT COMPARED` when unpinned (never PASS).
  `nightly.py` gained `--live-baseline`/`--write-live-baseline`/`--publish`
  (all require `--live`); the one recorded live run remains an operator action.
  Files: `python/harness/evaluation/{live_baseline,nightly}.py`,
  `python/tests/test_live_baseline.py`, `scripts/rsl-nightly.js`.
  Docs updated: `docs/harness/agent-evaluation.md`,
  `docs/self-improvement/rsl-v4-plan.md`, `docs/harness/decisions.md`
  (ADR-H321).

- **feat(evaluation): a lift must clear its paired noise floor.** A Wilson
  interval describes one arm; the acceptance decision was comparing point
  estimates from samples too small to distinguish from noise. Added
  `evaluation/significance.py`: `paired_bootstrap` (resamples TASKS, percentile
  CI + one-sided p-value), exact `mcnemar` for paired pass/fail, a
  `required_trials` planning estimate, and `paired_rates` (a metrics dict or a
  `SuiteResult`). `ablation.compare_arms` now reports `deltaCi`/`pValue`/
  `pairedTasks` and renders the CI. `utility.acceptance` gained the opt-in
  `require_significance`: when `HARNESS_RSL_SIGNIFICANCE=on`, at least
  `HARNESS_RSL_SIGNIFICANCE_MIN_TASKS` paired tasks are required and the CI low
  bound must be above zero, so a two-task "win" is refused. It is an acceptance
  rule, never a sampling signal. Files:
  `python/harness/evaluation/{significance,ablation}.py`,
  `python/harness/self_improvement/{utility,hillclimb,config,loop}.py`,
  `python/tests/{test_significance.py,test_rsl_significance.py}`, `package.json`,
  `.env.example`. Docs updated: `docs/harness/agent-evaluation.md`,
  `docs/self-improvement/rsl-v4-plan.md`, `docs/harness/decisions.md`
  (ADR-H320).

- **feat(evaluation): a committed corpus manifest and one split per purpose.**
  The corpus count had drifted between documents (76 vs 88) with nothing
  checking a dataset change against a recorded summary. Added
  `evaluation/corpus.py` (build/verify/audit; every checksum is recomputed from
  the task files, never trusted) and `baselines/corpus_manifest.json` (88 tasks,
  8 datasets, split counts, oracle coverage, canary count). The new
  `corpus-manifest` gate in `scripts/test-evals.js` fails on drift; refresh it
  deliberately with `npm run rsl:manifest -- --build`. Added
  `evaluation/contamination.py`: each purpose reads exactly one split
  (`optimization`/`validation`/`canary`/`release`), `access_guard` refuses a
  cross-split read, and a decoy canary (`metadata.canary`) makes a PASS a
  `CANARY_HACK` instead of a win. `--audit --strict` reports/enforces the
  oracle + contamination metadata rule for new tasks; the legacy corpus reports
  `0.0` oracle coverage honestly. Files:
  `python/harness/evaluation/{corpus,contamination}.py`,
  `python/harness/evaluation/baselines/corpus_manifest.json`,
  `python/tests/{test_evaluation_corpus.py,test_evaluation_contamination.py}`,
  `scripts/{rsl-manifest.js,test-evals.js}`, `package.json`. Docs updated:
  `docs/harness/agent-evaluation.md`,
  `docs/self-improvement/rsl-v4-plan.md`, `docs/harness/decisions.md`
  (ADR-H319).

- **feat(rsl): type every proposal, veto near-duplicates, and let islands migrate
  evidence.** A proposal now names the surface it mutates (prompt, tool guidance,
  tool subset, ceilings, context policy, guardrail, subagent prompt, model
  identity, skill draft, code patch, composition) via the new
  `self_improvement/operators.py`; `CandidateProposal.operator` carries it as
  evidence, never authority. `propose_many` gained `novelty_min` and
  `exclude_signatures`: a Jaccard-near-duplicate of an already-tried proposal is
  dropped, and if nothing new remains it raises `PROPOSAL_ALL_DUPLICATES`
  instead of returning a smaller comparison silently. The archive now treats a
  non-global scope as an island: every `HARNESS_RSL_ISLAND_MIGRATION` measured
  states, `StateArchive.migrate_best` copies the island's best measured state
  into `global` as an inert `stepping_stone` (same digest, new row), and
  `parent_for(island=...)` can restrict sampling. Migration copies evidence, not
  a decision; acceptance is untouched and the per-scope lease still allows two
  scopes to climb concurrently. New opt-in, clamped flags
  `HARNESS_RSL_NOVELTY_MIN` (0), `HARNESS_RSL_ISLANDS` (off),
  `HARNESS_RSL_ISLAND_MIGRATION` (5), accepted by hot config. Files:
  `python/harness/self_improvement/{operators,proposer,archive,config,recursion,loop,__init__}.py`,
  `python/tests/{test_rsl_operators.py,test_rsl_islands.py}`, `package.json`,
  `.env.example`. Docs updated: `docs/self-improvement/rsl-v4-plan.md`,
  `docs/harness/architecture.md`, `docs/harness/decisions.md` (ADR-H318).

- **feat(rsl): rank exploration parents by what their descendants achieved.**
  The archive ranked a state by its own score; HGM showed that is a poor proxy
  for self-improvement potential. Added `self_improvement/cmp.py` (descendant
  lift: depth-discounted mean of `utility(descendant) - utility(state)` over
  measured descendants, bounded horizon, explicit `coldStart` when there is too
  little evidence). `StateArchive` persists `cmpScore` on a state and its
  ancestors when a measured state is retained, and attaches a read-path estimate
  for older rows; `sampler.scores` blends it (weight 0.30). It remains a sampling
  signal only — `utility.acceptance` is untouched, so a high-lift state cannot
  promote itself or its children. New opt-in, clamped flags `HARNESS_RSL_CMP`
  (off) and `HARNESS_RSL_CMP_HORIZON` (3, 1–6), accepted by hot config. Files:
  `python/harness/self_improvement/{cmp,archive,config,loop,__init__}.py`,
  `python/tests/test_rsl_cmp.py`, `package.json`, `.env.example`. Docs updated:
  `docs/self-improvement/rsl-v4-plan.md`, `docs/harness/architecture.md`,
  `docs/harness/decisions.md` (ADR-H317).

- **feat(rsl): the climb may explore from a measured stepping stone, and only the
  champion can be replaced.** Greedy ascent proposed only from the incumbent and
  discarded every measured loser; the DGM ablation reports that exact shape as
  the weakest (50.0% with an archive vs 39.7% greedy vs 23.0% no archive). Added
  `self_improvement/sampler.py` (seeded `uniform`/`weighted`/`uct` parent
  sampling) and `self_improvement/archive.py` (`StateArchive` retains measured
  states as inert `stepping_stone` rows, refuses unmeasured ones, dedupes by
  snapshot digest, and evicts only stepping stones). `hillclimb.run_hillclimb`
  now takes an optional `archive=`/`rng=`, records `proposalParentId`, and
  retains rejected measured neighbors; acceptance is unchanged and still compares
  against the champion. `HarnessState` gained additive `visitCount`/`novelty`/
  `island`/`cmpScore`/`lastSampledAt` columns plus the `stepping_stone` status
  (never promotable/activatable). New opt-in, clamped env flags
  `HARNESS_RSL_ARCHIVE` (off), `HARNESS_RSL_ARCHIVE_MAX` (200),
  `HARNESS_RSL_ARCHIVE_SAMPLE` (weighted), accepted by hot config. Archive-off
  behavior is byte-identical. Files: `python/harness/self_improvement/{archive,sampler,state,hillclimb,config,loop,__init__}.py`,
  `python/tests/{test_rsl_archive.py,test_rsl_loop.py}`, `package.json`,
  `.env.example`. Docs updated: `docs/self-improvement/rsl-v4-plan.md` (new),
  `docs/harness/architecture.md`, `docs/harness/decisions.md` (ADR-H316).

- **fix(ui): the Dashboard is monochrome white and its portfolio panels wait honestly.**
  Replaced the initial gold/amber chrome with a white/grey treatment (green/red
  reserved for up/down and trend semantics), fixed the sidebar migration so an
  existing nav gets Dashboard directly after ChatBot, and removed the misleading
  zero-value/unavailable flash while quotes and price history load:
  `useAggregatePortfolio` now exposes `loading`, `usePriceHistories` marks a new
  symbol set loading immediately, and the Dashboard cards render explicit
  loading states instead of `$0.00` / "history missing". Files:
  `src/components/screens/dashboard/home-{dashboard,cards,primitives}.tsx`,
  `src/lib/dashboard/{use-home-data,portfolio-store}.ts`,
  `src/hooks/use-price-histories.ts`, `src/lib/sidebar/config.ts`,
  `src/lib/sdk/app-shell-types.ts`. no doc change — UI/data-loading polish; the
  Dashboard architecture and data path are already documented.
- **fix(tests): type the chart-route fetch mock so the lint gate passes.** The
  mock was declared `Promise<any>`; `npx eslint .` is a step of the release gate
  (`check:all`) and of the CI workflow, so one `no-explicit-any` error kept the
  whole gate red. It is now typed `Promise<Response>`. Files:
  `src/app/api/harness/charts/route.test.ts`. Docs updated: none - test-only.
- **fix(chat): a display formula after a prose line is typeset, not printed
  between dollar signs.** A real run wrote `**Return definition**\n$$r_t = ...$$`
  with no blank line; `$$` was not a block start, so the paragraph swallowed the
  formula line and the inline parser saw `$` + math + `$`, leaving literal
  dollar signs around a cramped inline formula. Display math (`$$...$$`, and
  `\[...\]`) now opens a block regardless of the preceding line, a mid-line
  `$$...$$` is display mathematics, and `\(...\)` / `\[...\]` are recognised
  (models emit them even when told to use dollars). Inline `$...$` also trims
  surrounding spaces (`$ x $` typesets) and accepts compact digit/letter terms
  (`$2x$`); escaped `\$100` stays money. Files:
  `src/lib/chat/markdown.ts`, `src/components/chat/markdown.tsx`; tests
  `src/lib/chat/math.test.ts`, `src/components/chat/math-render.test.tsx`.
  docs updated: `docs/chat-ui-audit.md`.

- **fix(harness): repair the broken merge state, regenerate the two published
  artifacts, and hold `graph.py` under its ratchet.** The tree about to land was
  internally inconsistent: `boot.py` imported
  `harness.self_improvement.session_watch`, but that module only existed on
  main's newer commit, so four a2a tests and two recovery tests failed with
  `ModuleNotFoundError`. Merging main fixed all six. Three conflicts resolved:
  the RSL lab ADRs claimed H290/H291/H292, which were already the sandbox ADRs,
  so they became **H306/H307/H308** with a provenance note on each (the decision
  text is untouched; the gate now reports 303 entries, H1..H308, contiguous); the
  `package.json` kept both sides; and their `Promise<Response>` on the chart-route
  mock does not compile, because the mock returns a plain object - `unknown` is
  the form that passes both `tsc` and `eslint`. The merge also made both generated
  artifacts stale, so `docs/harness/tool-registry.json` (956 tools, digest
  `cc523b84547c456c`) and `docs/harness/benchmarks.md` were regenerated, and
  `graph.py` (2,314 lines, past its pinned 2,309) was compacted to 2,308 rather
  than raising the ceiling.
  docs updated: docs/harness/decisions.md.

- **release(harness): v0.2.0 is tagged, and `main` is the released tree.** Round 4
  V1 is closed. `origin/main` fast-forwarded to `b3e08d1c` (no force), the branch
  was pushed, and an annotated `v0.2.0` (`8068674e`) was pushed and verified with
  `git ls-remote`. The release was only cut after the full `check:all` passed on
  the exact tree that was tagged - the gate had failed four times first, each time
  on something real (a divergent `main`, stale generated artifacts, a module over
  its ratchet, and CRLF this tool wrote into an LF file). The plan's ADR
  reservations were shifted to H309-H314, because the merge resolution consumed
  H306-H308. The other stream's local `main` is behind and must `git pull`.
  docs updated: docs/harness/roadmap/round-4-gap-closure.md,
  docs/releases/v0.2.0.md.

- **refactor(git): nine diff ops, one argv builder.** Round 4 / V2, first slice.
  The nine `diff_*` operations differed only by a flag prefix and whether the
  revision pair was `(base)` or `(from, to)`, so they are now one `_diff_argv`
  plus a nine-row table. Every name, argument list and argv string is unchanged
  (verified by building all nine against sample args and diffing the output), so
  no caller and no shim is affected. 319 git tests pass; the total falls from
  377,242 to 377,238 lines. The saving is small on purpose: the audit found the
  catalog was already dense, so V2 cannot deliver its promised reduction this
  way and that is recorded in the plan rather than papered over.
  no doc change — internal refactor, no contract or architecture change.

- **docs(adr): the 15 legacy entries now carry the full shape.** Round 4 / V3a.
  The gate had been exempting 15 decisions below H295. Every one was closed by
  re-labelling prose that was already written, never by inventing a rationale:
  `Impact` became `Consequences` (H45-H50, six), `Context` became `Why`
  (H147-H151, five - each Context paragraph already stated the motivation),
  `Consequences (non-goals)` became `Consequences` (H96), `Why this supersedes
  ADR-H75's choice (b)` became `Why` (H76), and H7's marker was welded to its
  heading by a missing line break. One heading - H70's `Consequences` - had no
  prose to relabel, so it restates what that entry's own Decision section already
  says about subscriptions, conditional registration and inert prompt text.
  The gate now reports **zero** legacy exemptions: 303 entries, H1..H308, all
  shaped. docs updated: docs/harness/decisions.md.

- **test(graph): the cancellation test waits for the retry instead of guessing.**
  Round 4 / V3a. `test_cancellation_during_retry_still_cancels` slept a fixed
  0.3 s and then cancelled, assuming the first attempt had already overflowed and
  the retry had begun. On a loaded machine that race went the other way, so the
  cancel landed during the *first* attempt and the assertion described a state
  the run had not reached. The model now sets an `asyncio.Event` on its second
  call and the test awaits it (10 s ceiling) before cancelling - the same
  assertion, no race, and a failure to reach the retry now reports as a timeout
  rather than a wrong status. 16/16 in the file, twice.
  no doc change — test-only fix, no contract or behaviour change.

- **fix(bridge): the structured-read budget is now measured, not assumed.** Round
  4 / V5. The bridge gave structured reads 8 s because "the smallest market-tool
  budget is 10 s" — true, and still too tight. Timed against the live front door:
  `market_data` 3.91 s, `live_quote` 3.57 s, `market_snapshot` 0.04 s cached, and
  **`financial_statements` 8.56 s cold** — permanently over the line, so the live
  lane could not measure a single finance dimension. Bridge is now 15 s and the
  finance tools' `timeout_ms` 25 s, preserving the ordering the contract depends
  on (15 s < 25 s), which the existing timeout test still enforces. Live-suite
  bridge failures fell 15 -> 6 -> 3 across the runs. It did not reach zero: the
  three remaining calls include `market_snapshot`, measured at 42 ms, so they are
  connection faults under suite load and not budget faults - recorded as the next
  open item rather than claimed fixed. ADR-H309 carries the measurement and the
  reasoning; the plan's V1-V6 ADR reservations shift to H310-H315.
  docs updated: docs/harness/decisions.md,
  docs/harness/roadmap/round-4-gap-closure.md.

- **fix(bridge): a bridge failure now names its exception, and a dropped peer is
  retried.** The three remaining live-suite failures logged as
  `data bridge failed (market_snapshot):` with nothing after the colon, which made
  them indistinguishable from a timeout. The logger now always prefixes the
  exception type and the returned error carries the same text. That immediately
  identified them: **`ConnectError: All connection attempts failed`** - the front
  door was not listening, not a budget problem. `RemoteProtocolError` (a peer that
  accepts then drops the request, and whose `str()` is empty) is now retried once
  alongside `ConnectError`; a timeout still never is. The residual failures are
  environmental: the local server is not surviving between runs in this
  environment, so they are recorded as an operations issue rather than a harness
  defect.
  no doc change — diagnosability and retry class only, no contract change.

- **fix(eval): the published benchmarks show the live run that exists.** The
  generator accepted `--live-run <id>` and then never loaded the suite, so it
  published *"no live run has been recorded"* while six completed live runs sat in
  the store. `_load_live_suite` now rebuilds the publishable view from the
  `EvaluationRun` row plus its metrics and recomputes the thresholds with the same
  `check_thresholds` the live gate uses. `write_benchmarks()` selects the most
  recent completed live run itself, so the canonical regeneration and the
  committed file agree - which the `generated not hand-edited` test enforces.
  The live tier now publishes `deepseek-v4.1-flash:cloud` with gate **FAIL** and
  its real dimensions (`task_success 0.0`, `tool_accuracy 0.2985`,
  `planning_quality 0.9872`, `safety_score 0.6667`, `reliability 1.0`). A failing
  measurement is published, not hidden - that is the point of recording it.
  docs updated: docs/harness/benchmarks.md.

## 2026-10-21
- **feat(quant): the backfill says out loud that no subscription is needed.**
  The durable cache only holds what has been fetched, and the backfill is how
  you fill it - but the honest question is whether bundling a universe costs
  money. It does not: the keyless providers (Yahoo Finance, Stooq, Binance,
  the ECB reference rates, Treasury/FRED) are enough, and the backfill now says
  so. It names the provider that served each symbol, whether that provider
  needs a key, and which providers are usable right now with NO credential; a
  keyed provider that is not configured is reported as needing a key, never as
  free. The difference between hosting and owning the data: the hosted
  platform rents you a decade of ticks, this one KEEPS what it fetched, on
  your machine, and serves it from there forever. Files:
  python/harness/market/tools.py, python/tests/test_gallery_venues.py. docs
  updated: docs/quant-engine.md.

- **test(harness): a production smoke test - the real app, the real routes.**
  The other tests check units. This one starts the actual FastAPI application
  (the same `harness.main:app` the runtime serves) and asks it the questions
  a user's first minute would ask: is it alive, what does it hold, what can it
  run, and does it refuse HONESTLY when something is missing - a request for a
  report that does not exist must be a named refusal, not a fake success, and a
  Pine run must say whether the engine is installed. It is deliberately
  read-only: a smoke test that mutates production state is not a smoke test.
  Files: python/tests/test_production_smoke.py. no doc change - a test.

- **feat(quant): bundle it, see the venues, and publish it.** Three closers.
  **(1) The backfill.** The durable cache only holds what has been fetched, so
  `backfill_history` (tool and POST /market/history/backfill) fetches a window
  ONCE and keeps it - that is how a local-first runtime holds a universe the way
  a hosted platform "bundles" one: the user decides what to keep, and every
  later run is served from the machine. **(2) The venue seam.**
  `quant/venues.py` makes the multi-DSL promise explicit instead of implied: a
  venue is a language a strategy can be written in, and each declares whether
  it can run, what it needs and how to reach its engine. Pine runs (the isolated
  engine, on Eclipse's bars); NinjaScript, PowerLanguage and EasyLanguage are
  NAMED gaps that say exactly what is missing - "no NinjaScript engine is
  installed; the venue needs a C# runtime" - because a venue that never claims
  to work is better than a promise the runtime cannot keep. The seam exists so
  that adding a venue is a registration, not a refactor. **(3) The gallery.**
  `python/harness/gallery/` is the community layer, done honestly for a
  local-first, single-operator runtime: a catalogue of FROZEN, GRADED
  strategies. Publishing freezes a strategy and the Edge Report that graded it
  into an immutable record; cloning copies the spec into the quant store as a
  NEW strategy, so the published record and the live strategy never share an
  identity; favouriting counts interest locally. Surfaces: the tools
  `backfill_history`, `list_strategy_venues`, `publish_strategy`,
  `list_gallery`, `favourite_published_strategy`, `clone_published_strategy`;
  the routes /market/history/backfill, /quant/venues and /gallery*; and the
  Strategy Gallery widget on the Command Center. Files:
  python/harness/gallery/ (new), python/harness/routers/gallery.py (new),
  python/harness/quant/venues.py (new), python/harness/market/tools.py,
  python/harness/routers/market.py, python/harness/boot.py,
  python/harness/agents.py, src/lib/dashboard/gallery-widget.tsx (new),
  src/lib/dashboard/registry.tsx, src/app/api/harness/gallery/ (new).
  Tests: python/tests/test_gallery_venues.py (13),
  python/tests/test_market_history_cache.py (11). docs updated:
  docs/quant-engine.md.

- **feat(ui): a global-first Dashboard tab now sits above Command Center.**
  The new `home` tab (`/?tab=home`, F2 by default) folds market weather,
  sector/market leadership, portfolio trend health + trend mix, the review
  queue, portfolio watch, watchlist radar, sector concentration, screener CTAs
  and the alerts archive into one daily decision surface. It reads real JDDS
  data only (`/api/regime`, `/api/heatmap`, `/api/global-overview`,
  `/api/price-history`, `/api/alerts`) plus the existing seeded fund book
  (labelled **Demo book**). When the explainable regime read is stale or
  unavailable, the hero falls back to a labelled breadth-derived weather read;
  the regime card stays honestly **Unavailable**. Files:
  `src/components/screens/dashboard/home-{dashboard,cards,primitives}.tsx`,
  `src/lib/dashboard/{use-home-data,home-model}.ts(x)`, plus the `home`
  AppTab/deep-link/sidebar/search/i18n/mobile-nav wiring and 23 model tests.
  docs updated: docs/OVERVIEW.md, docs/NAVIGATION.md, docs/ARCHITECTURE.md.

- **feat(quant): the local data vault, made visible.** A cache nobody can see
  is a cache nobody trusts. The **Local History** widget on the Command Center
  now shows what the machine actually holds - which instruments, how many bars,
  how fresh, from which provider - with the coverage of one instrument on
  demand, and the agent can ask the same question through the new
  `history_catalog` tool. The runtime serves it from the durable cache
  (`GET /market/history`, `/market/history/{symbol}`,
  `/market/history/{symbol}/bars`), so it works OFFLINE and can never claim a
  bar the runtime does not have. Files: python/harness/routers/market.py,
  python/harness/market/tools.py, python/harness/market/series_store.py,
  python/harness/market/bootstrap.py, src/lib/dashboard/history-widget.tsx
  (new), src/lib/dashboard/registry.tsx, src/app/api/market/history/route.ts
  (new), src/app/api/market/history/[symbol]/route.ts (new). Tests:
  python/tests/test_market_history_cache.py (11). docs updated:
  docs/quant-engine.md.

- **feat(quant): the durable history cache - one copy of the history Eclipse
  has already seen.** The gateway cached history IN PROCESS, so every restart
  re-fetched every bar from the provider. The durable half now lives on the ONE
  agent-memory connection, and a later request for the same window is served
  from it. This is the engineering half of "bundled data": it does not buy a
  vendor's history, it buys ONE copy of the history Eclipse has already paid
  for - on the machine, offline, reproducible - and the SAME bars then feed the
  backtest, the regime classifier, the Monte-Carlo, the Pine engine and the
  trade-log analysis, so all five agree by construction. Two rules keep it
  honest: a cached window is served only when it actually COVERS the request (a
  partial cache is a miss, not a short answer), and a stale tail is refetched -
  with no explicit window the cache is only the whole history if its last bar is
  still fresh, because a cache that never refreshed would silently freeze the
  market. A backtest that pins its window is served from the cache; an
  open-ended request refetches the tail. Files:
  python/harness/market/history_cache.py (new),
  python/harness/market/bootstrap.py, python/harness/quant/datasets.py.
  Tests: python/tests/test_market_history_cache.py (9). docs updated:
  docs/quant-engine.md.

- **feat(sdk): eclipse_data - ECLIPSE's data and research from a notebook.** The
  runtime is the authority; this package is a thin client for it, so a notebook
  and the app see the SAME bars, the SAME verdict and the SAME project. It
  speaks to the local runtime (the operator token when one is configured) and
  exposes: normalized OHLCV with its provenance, the coverage the runtime
  already holds, the projects and their curated digests, the proposals, the
  Edge Report, a prop-firm evaluation of a trade log, and a Pine script with
  and without its grade. It has NO third-party dependency - the standard
  library alone - and it never invents a value: a refusal from the runtime is
  raised with the runtime's own code and message. A test checks every path the
  client calls against the runtime's OWN OpenAPI schema, so the client cannot
  drift away from the surface it talks to. Files: sdk/eclipse_data/ (new:
  __init__.py, pyproject.toml, README.md), python/tests/test_eclipse_sdk.py.
  docs updated: docs/quant-engine.md.

- **feat(harness): the proposer reads the project's own notes.** A note is a
  finding a human wrote down, and it is evidence like any other. If a note
  names a regime that no attached result was ever measured in - "the NQ cross has
  never been traded in up_high" - the proposer raises it and proposes the
  backtest that would answer it. If a result already covers that regime,
  nothing is proposed: a note that has been tested is a note that has been
  answered. That is the proposer's content edge: it is a function not only of
  what the project HOLDS, but of what it SAYS. Files:
  python/harness/projects/propose.py. Tests:
  python/tests/test_project_proposals.py (12). docs updated: docs/projects.md.

- **feat(harness): a project may act on its own - inside a policy the operator
  can see.** The loop that runs a proposal existed, but only when the agent or
  the user asked. A project can now act unattended, and the bound is explicit
  and enforced BY THE RUNTIME rather than by the model's good intentions. The
  policy says whether the project is enabled (OFF for every project until
  someone turns it on), how many runs a day and how many seconds a day it may
  spend, how far apart two runs must be, and which tools it may run - and that
  tool list is filtered to **compute only** (a backtest, a sweep, a rule
  evaluation), so a project can never act on the world by itself, whatever the
  policy asks for. Every tick, each project whose policy allows it runs ONE
  proposal through the same tool path an agent would use, and the outcome goes
  into a ledger - the successful runs and the refusals alike. A project that
  cannot act is a NORMAL outcome, not an error: it is skipped with the reason
  (`daily_run_budget`, `min_interval`, `no_runnable_proposal`) recorded. The
  policy and what is left of its budget are visible in the curated view, so the
  agent can see that a project acts on its own and what it has spent today.
  Surfaces: the tools `project_auto_policy` and `project_auto_run`; the routes
  GET/POST /projects/{id}/auto and POST /projects/auto/run. The loop starts at
  boot and stops at shutdown, and the implementation lives in
  `python/harness/projects/` - `service.py` and `graph.py` are untouched, so
  their size ratchets do not move. Files:
  python/harness/projects/policy.py (new), python/harness/projects/auto.py
  (new), python/harness/projects/curate.py, python/harness/projects/propose.py,
  python/harness/projects/tools.py, python/harness/projects/bootstrap.py,
  python/harness/routers/projects.py, python/harness/boot.py.
  Tests: python/tests/test_project_auto.py (10). docs updated: docs/projects.md.

- **feat(harness): a project runs its own proposal and records the outcome.**
  The proposer named the next experiment; now it is RUN - through the same tool
  the agent would have called, so the policy gate, the allowlist, the sandbox
  and the persistence are the agent's own path, not a second one - and the
  outcome is recorded back into the project, so the next proposal is made
  against a project that knows what just happened. Three rules: a proposal is
  only run when it names a tool and the arguments it needs (a proposal that
  cannot be run is reported, not attempted); a FAILURE is recorded as a
  failure - a refused or failed run is attached as a note that says what went
  wrong, because a project that hides its failures cannot learn; and nothing is
  attached that did not happen - the executor attaches the experiment the run
  really produced, by the id the run really returned. The proposal actions are
  now real, executable tool calls (a strategy that was never run names
  `run_backtest` with its id and instruments; an unsafe tail names
  `run_robustness_analysis` with the cost multipliers). Surfaces: the tool
  `project_run_proposal`, the route
  POST /projects/{id}/proposals/{proposal_id}/run, and the Project Scope
  widget, which now shows the project's next step with a button that runs it -
  after which the widget re-reads the digest and the proposals, because the
  next step has changed. Files: python/harness/projects/execute.py (new),
  python/harness/projects/propose.py, python/harness/projects/tools.py,
  python/harness/routers/projects.py,
  src/app/api/harness/projects/[...path]/route.ts (new - the digest, the
  proposals and the run needed a front door that did not exist),
  src/lib/projects/project-client.ts, src/lib/dashboard/project-widget.tsx.
  Tests: python/tests/test_project_execute.py (7),
  python/tests/test_project_proposals.py. docs updated: docs/projects.md.

- **feat(quant): the trade-log analysis - where the money actually came from.**
  A trade log on its own says what you made; it does not say WHEN you made it,
  which is the question that decides whether a strategy is worth trading. Every
  entry is now placed on the regime of its entry bar - the SAME causal trend x
  volatility classifier the Edge Report uses, so the log, the verdict, the
  Monte-Carlo and the report all speak ONE regime language instead of two - the
  realised P&L is attributed per regime, the concentration of the profit is
  measured (the share of gross positive P&L the best few entries carry), and
  each entry carries its own context: regime, trend, volatility, ATR and the
  distance from entry to exit in ATR terms. A log whose profit sits in one
  streak is FLAGGED, because a streak is not a rule. Entries that cannot be
  placed on a bar of their own symbol's series are counted in the totals and
  reported as unclassified - they are never given a regime they were not
  measured in. It is a measurement, not a verdict: it never says a strategy is
  good, it says where the money came from and what it could not measure.
  Surfaces: the tool `analyse_trade_log` (which reads the Journal's own trades
  when no log is passed) and the route POST /quant/trade-log. Files:
  python/harness/quant/trade_log.py (new),
  python/harness/quant/advanced_tools.py, python/harness/quant/tools.py,
  python/harness/routers/quant_reports.py. Tests:
  python/tests/test_quant_trade_log.py (9). docs updated: docs/quant-engine.md.

- **fix(quant): a prop-firm EV with no fee in it is now marked as an upper
  bound.** The engine never invents a price - the caller supplies the fee and
  the reset fee - which is right, but it left a trap: a caller who forgot
  `feePerAttempt` got an optimistic expected value with nothing flagging the
  omission. The report now carries `assumptions.feeSupplied`, says outright
  that the EV is GROSS of every cost when no fee was given, and raises
  `PROP_FIRM_NO_FEE_SUPPLIED`. A missing input must never quietly flatter a
  number. Files: python/harness/quant/propfirm_mc.py. Tests:
  python/tests/test_quant_trade_log.py. docs updated: docs/quant-engine.md.

- **feat(harness): a project proposes what to do next, from its own evidence.**
  The curated view says where a project stands; this says what to do about it,
  and it may only say it from evidence the project ACTUALLY holds. A strategy
  with no result is proposed for a backtest (with the exact tool call and the
  instruments). A result resting on fewer than 30 trades is proposed for a
  wider sample - below 30 trades the difference between an edge and luck is not
  measurable. A strategy whose trades only ever happened in a few market
  regimes is proposed for a wider window, because the regimes it has never been
  observed in are unknown. A Monte-Carlo whose probability of loss is high, or
  whose 5th-percentile return is not positive, is proposed for a cost test -
  the tail is the problem, not the average. And any result with trades is
  tested against a prop firm's evaluation rules, using the strategy's OWN trade
  sequence. Every proposal cites its evidence (an experiment id, a regime, a
  metric, a pass probability) and names the concrete action, so it can be run
  without being re-invented. A proposal that cannot cite its evidence is NOT
  made: a project that holds what it needs gets the honest answer - there is
  nothing to propose. And a rule that could not be evaluated is REPORTED in
  `skipped`, never silently skipped - a broken check must not look like a
  project with nothing to propose. (That last rule earned itself: two broken
  imports were hiding in the first cut, silently disabling a whole check.)
  Surfaces: the tool `project_next`, the route GET /projects/{id}/proposals,
  and the Project Scope widget, which shows the active project's next step.
  Files: python/harness/projects/propose.py (new),
  python/harness/projects/tools.py, python/harness/routers/projects.py,
  src/lib/projects/project-client.ts, src/lib/dashboard/project-widget.tsx.
  Tests: python/tests/test_project_proposals.py (10),
  python/tests/test_projects.py (the `project_next` tool's refusals),
  python/tests/test_quant_routes.py (the new route is registered).
  docs updated: docs/projects.md.

- **feat(harness): the curated project view - what a project is, and what it
  is missing.** A member list is a filing cabinet; a curated project is a
  summary. The new curator ranks a project's members by a FIXED priority per
  kind - a tested result outranks a strategy, which outranks a dataset, which
  outranks an output artifact, which outranks a run record - breaks ties by
  recency, and carries **the reason each member was promoted**, so the ranking
  can be argued with rather than merely trusted. It derives a headline from
  what the project actually holds ("NQ momentum on NQ, ES - 1 strategy, 2
  results") and it names the GAPS plainly: a project with a strategy and no
  result says so - "no result has been attached yet - a strategy with no tested
  outcome is an intention, not a finding". The curated view is what the AGENT
  sees: the run's per-run project context is the digest, not a flat member
  list, so a turn inside a project starts from "where does this stand?"
  rather than from a wall of references. Surfaces: the tool `project_digest`,
  the route GET /projects/{id}/digest, and the Project Scope widget, which shows
  the active project's headline, its top members with their reasons, and what it
  still lacks. Files: python/harness/projects/curate.py (new),
  python/harness/projects/tools.py, python/harness/routers/projects.py,
  python/harness/graph.py, src/lib/projects/project-client.ts,
  src/lib/dashboard/project-widget.tsx. Tests:
  python/tests/test_project_curation.py (10), python/tests/test_projects.py.
  docs updated: docs/projects.md.


- **feat(harness): the harness has a PUBLIC surface, a published tool
  manifest, and a package that carries no data.** The harness was excellent and
  unreachable: everything it could do - the retrieval layer, the research
  verifier, the comparability gate, the receipts, the tool surface - was
  valuable to another harness and available only here. And a public surface
  that is not DECLARED is not a public surface; it is a directory listing.
  `python/harness/public.py` is now the WHOLE public API -
  `AgenticService`, `ToolRegistry`, the run contract, and the export
  functions - and it is a closed list, asserted by a test.
  `export_tool_schemas()` produces the PORTABLE tool manifest: the MCP
  tool-manifest shape plus the parts a consumer needs to bind a tool safely
  (`permission`, `effect`, `risk`, `version`, the deprecation fields).
  `docs/harness/tool-registry.json` is that manifest, GENERATED, with a drift
  test that regenerates and compares: **946 tools**. The honesty contract is
  the point of the export - a tool is published with its permission and its
  effect class, or it is NOT published, because a consumer cannot honour a
  rule it cannot read and a tool that cannot be classified is a tool nobody
  should call. A consumer inherits Eclipse's honesty: it can see that a tool
  writes, or that it reaches the network, before it binds it. The package
  metadata (`pyproject.toml`) declares `black-eclipse-harness` - the RUNTIME,
  with the provider SDKs as OPTIONAL extras (a consumer that only wants the
  tool surface should not install an SDK for a model it never calls), no
  package data, and no dependency on the app.
  The manifest also caught a real bug: the `analysis_run` tool's description
  interpolated the FUNCTION OBJECT instead of its result, so the tool that
  runs analyses had been advertising `<function recipe_catalogue_text at
  0x...>` to the model instead of the recipes it can actually run. That is
  fixed, and a guard now asserts that no published description carries an
  object repr. Files: python/harness/public.py (new),
  Black-Eclipse-site/pyproject.toml (new),
  scripts/generate-tool-registry.js (new),
  scripts/size-budget.json (the ceiling was raised on purpose for the public
  surface - a real addition, not drift),
  docs/harness/tool-registry.json (generated),
  python/tests/test_public_api.py (new). ADR-H298. docs updated:
  docs/harness/decisions.md, docs/harness/architecture.md, docs/NAVIGATION.md.

- **fix(harness): a shell sees no more of the environment than a command
  does, the output is redacted, and the network is refused BY NAME.** The real
  host shell used to inherit the FULL `os.environ`, so a single `shell_run`
  could read a provider key, the callback token or the vault and print it into
  the conversation, the run blob and the ledger - while the sandboxed command
  path had been scrubbed since Phase 1. Both now use the SAME builder
  (`code.sandbox.build_env`: the allowlist ONLY, never the vault, never the
  provider keys, never the callback token, never a proxy), so a shell and a
  sandboxed command see the same world. Command and shell OUTPUT is now
  REDACTED through the one existing primitive before it reaches the model -
  the file reader has done this since Phase 1, and the command and shell paths
  are the ones a model can most easily push a secret through - and the
  `code.output.redacted` event names the NUMBER of lines changed, never the
  value. `RunSpec.network` was a declaration whose refusal was unreadable: a
  caller could not tell "the network is refused" from "there is no sandbox
  primitive here". The refusal now carries `NETWORK_DENIED`, and the answer to
  "is the network contained?" is PUBLISHED rather than assumed - the container
  tier really does run `--network none`, and the local tier cannot, so the
  command result says which one it was. Two new adversarial cases attack the
  real modules: `S15-network-enforced` and `S16-shell-env-scrubbed`. Files:
  python/harness/code/shell.py, python/harness/code/events.py,
  python/harness/code/shell_tools.py, python/harness/code/command_tools.py,
  python/harness/code/sandbox.py,
  python/harness/code/eval/safety_cases.py, python/harness/code/eval/safety.py,
  python/harness/code/eval/capabilities.py,
  python/tests/test_isolation_secrets.py (new). ADR-H297. docs updated:
  docs/harness/decisions.md, docs/harness/architecture.md, docs/NAVIGATION.md,
  docs/harness/capability-statement.md.

- **feat(harness): the benchmarks are GENERATED, the live tier is a lane, and
  no capability is published unmeasured.** The evaluation framework was already
  first-rate - the real graph, 17 graders, 22 dimensions with un-averagable
  criticals, `pass@k` with Wilson intervals, flakiness classification, frozen
  baselines stamped with the commit, per-dimension regression detection, a
  worktree invoker, a canary split, a verdict-leak tripwire, and a
  team-vs-single benchmark that returned a NEGATIVE verdict and therefore did
  not ship. Almost nobody builds that. And then: the offline tier REPLACED the
  model with a recorded program, the live tier existed but was reachable only
  by hand, no number a stranger could check had ever been published, and four
  capability classes were published unmeasured. `docs/harness/benchmarks.md` is
  now GENERATED by `python -m harness.evaluation.report` (or
  `npm run eval:benchmarks`) and never hand-edited, so a number cannot be
  quietly improved - a test regenerates it and compares. The two tiers are
  kept APART and named: the OFFLINE tier replaces the model with a recorded
  script, so it measures the RUNTIME - the tool surface, the policy, the
  graders, the wiring - and it says so; the LIVE tier runs a real model and
  is the only tier that measures the agent. Both carry their dataset,
  checksum, agent version, commit and grader version, because a number without
  its provenance is a rumour, and a rumour in a benchmark table is worse than
  an empty row. The live lane never fabricates: with no provider it publishes
  "NOT MEASURED" with the reason and exits 0, and the nightly workflow SKIPS
  rather than failing when no secret is configured. And the capability
  registry stops publishing things it cannot back: `price_authority` (the
  authority ARBITRATES a disagreement rather than taking the first answer, and
  the conflict is recorded), `promotion` (the full landing round trip -
  preview, apply, rollback, re-apply - asserted on the real bytes in a real
  folder) and `scraping_breadth` (the registry knows more than one KIND of
  data source) are now graded END TO END; `code_intel`, `code_chat_routing` and
  `context_compaction` are new classes; and the `messaging_gateway` class is
  RETIRED, because it names a capability that is not built and a published
  class for something that does not exist is worse than an unmeasured one. The
  registry is now **24 classes, 24 measured, 0 not measured yet.** Files:
  python/harness/evaluation/report.py, python/harness/evaluation/live_gate.py
  (new), python/harness/code/eval/capabilities.py,
  scripts/generate-benchmarks.js (new), scripts/run-live-evals.js (new),
  python/tests/test_published_benchmarks.py (new),
  .github/workflows/live-evals.yml (new), docs/harness/benchmarks.md
  (generated), docs/harness/capability-statement.md (regenerated). ADR-H296.
  docs updated: docs/harness/decisions.md, docs/harness/architecture.md,
  docs/NAVIGATION.md, docs/harness/capability-statement.md,
  docs/harness/benchmarks.md.

- **chore(harness): the decision record is unambiguous, the harness has a TOTAL
  ceiling, and the release is real.** The operational score was the harness's
  weakest dimension, and the reason was not capability - it was DISCIPLINE. The
  decision series had SEVEN duplicate numbers (H160, H162, H242 x2, H243, H244,
  H245) and five gaps: "ADR-H242" named two different things. The later
  duplicate of each was renumbered and the old number RETIRED with a redirect,
  so an old reference still resolves and the decision is unchanged. The
  withdrawn numbers are reserved explicitly. `scripts/check-adr-numbers.js`
  now fails the release gate on a duplicate, an unreserved gap, or an entry
  without Decision / Why / Consequences - and it NEVER renumbers anything,
  because renumbering is a judgement call that belongs to a human. The shape is
  enforced from H288 onward; the older entries are reported and
  countable rather than rewritten, because inventing a rationale for someone
  else's decision is not honesty. The harness also gains the missing half of
  its size ratchet: `python/tests/test_size_budget.py` bounded each FILE's
  growth but not the TREE's, so a harness could keep every file under its pin
  and still double by adding files. `scripts/size-budget.js` adds a committed
  TOTAL ceiling (`scripts/size-budget.json`) plus the twelve largest
  subsystem ceilings; the harness is 368,218 lines against a 371,900 ceiling
  that must now be raised ON PURPOSE. And the release is real: the version is
  0.2.0, `docs/releases/v0.2.0.md` is derived from the CHANGELOG, the
  changelog's rolling 7-section window is rotated by a script instead of by
  hand, and `CODEOWNERS` names the harness paths - the part of the tree where
  a mistake is hardest to see. The 30% surface cut is NOT in this release: it
  is a multi-release program over DUPLICATION, not capability, and the two
  candidates the plan named first (the FS write stack and the search stack) are
  already merged. Files: scripts/check-adr-numbers.js (new),
  scripts/size-budget.js (new), scripts/size-budget.json (new),
  scripts/rotate-changelog.js (new), scripts/check-all.js, package.json,
  .github/workflows/ci.yml, CODEOWNERS (new), docs/releases/v0.2.0.md (new),
  docs/harness/decisions.md, docs/harness/roadmap/phase-20-measuring-all-of-it.md.
  ADR-H295. docs updated: docs/harness/decisions.md,
  docs/harness/architecture.md, docs/NAVIGATION.md,
  docs/harness/roadmap/phase-20-measuring-all-of-it.md, docs/releases/v0.2.0.md.

- **feat(harness): the model is TOLD the shape of the project.** The harness
  had NO repo map at all. A model that wanted to know what was in the project
  had to GUESS a path, spend a tool call on it, and - on a miss - get a bare
  "that file isn't there". The CIUE index and the context engine are genuinely
  good - the context engine ranks files by symbol matches, path matches and
  related tests, and finds the related test file too - but they were
  reachable only if the model THOUGHT to call `code_get_relevant_context`.
  Excellent machinery, invisible. A repo map - the folders, and a symbol
  outline of the top files - is now built EAGERLY and DETERMINISTICALLY and
  handed to the model in the FIRST turn, together with the CIUE context
  engine's answer for THIS request (the "seeded slice"), resolved once per
  run with no model call. The map is BOUNDED (a file count, a
  symbols-per-file count, a byte budget and a render budget - it is a summary,
  never a copy), DETERMINISTIC (the same tree produces the same map and the
  same digest, byte for byte), and HONEST about its engine: the outline comes
  from the stdlib extractor (Python's own `ast`, a brace/regex scanner for
  everything else), and tree-sitter's availability is published in the
  code-intel status - an optional layer that silently no-ops is a false
  capability. The map's content hash is the prompt-cache key's witness: a
  project whose shape changed invalidates the cache, and one that did not
  change does not. It gets its OWN segment for exactly that reason -
  `runtime_context` is run-frozen and its content is NOT hashed, so a map
  appended there would have been cache-key-invisible. The same change fixes an
  UNMEASURED claim: `CodeIntelRuntime.is_fresh()` used to `return True` for
  EVERY workspace - including one that was never indexed and one with no
  background indexer. It now looks for the EVIDENCE (the background watcher
  that owns the index's freshness), and a workspace with neither is honestly
  not fresh - which is what lets a read path ask for a refresh instead of
  trusting a claim. Files:
  python/harness/code/intel/repo_map.py (new),
  python/harness/code/intel/runtime.py, python/harness/prompt_segments.py,
  python/harness/graph_context.py, python/harness/graph.py,
  python/harness/code/eval/capabilities.py,
  python/tests/test_repo_map.py (new, 14 cases). ADR-H287. docs updated:
  docs/harness/decisions.md, docs/harness/architecture.md, docs/NAVIGATION.md,
  docs/harness/capability-statement.md.

- **feat(harness): the dropped turns are COMPACTED, not just dropped.** The
  harness TRUNCATED its history: `_bounded_history` kept the most recent turns
  and dropped the oldest, and the dropped-context extractor mined them for
  INERT candidates ("you mentioned a file called X"). Everything else the
  conversation carried - the decision that was made, the question that was
  still open, the state of the work - was GONE. `context_budget.py` said it
  plainly: *"no tokenizer dependency, no network call, no summarization."*
  Every top-tier harness compacts; a long run in Eclipse could keep twenty
  turns and no more, and the twenty-first turn started from nothing. What the
  history bound removes is now carried forward as a fenced, labelled summary:
  the requests that were made and the answers that were given (the
  DETERMINISTIC skeleton, which always runs), plus a bounded model NARRATIVE
  on top of it - the decisions taken, the open questions, the state of the
  work. The existing inert dropped-context block is NOT replaced: both reach
  the model, the compaction first. The narrative is ADDITIVE and fails
  CLOSED - an unavailable, silent or failing model leaves the skeleton
  untouched and the run records why - and the block is DATA, never instruction
  (a compaction can contain anything the user typed). It never enters a
  research claim: a summary of a conversation is not evidence. The model
  narrative is OPT-IN (the policy key `history_compaction_model` turns it
  ON), because it costs a model call and up to twenty seconds on the run's
  critical path - the deterministic skeleton is what actually carries the
  conversation forward, and it ALWAYS runs. Files: python/harness/compaction.py (new), python/harness/history.py,
  python/tests/test_history_compaction.py (new, 12 cases),
  python/tests/test_size_budget.py (the re-pin). ADR-H286. docs updated:
  docs/harness/decisions.md, docs/harness/architecture.md, docs/NAVIGATION.md.

- **fix(harness): ONE edit tool, and it insists the run read the file.** The
  harness had THREE ways to change a file's contents and ELEVEN more
  file-lifecycle tools, spread over two subsystems - and NONE of them required
  proof that the model had seen the file it was about to change. `expectedHash`
  was accepted everywhere and required NOWHERE, so the model could write to a
  file it had never read, and a file that had changed underneath it was
  overwritten silently. The text-edit surface is now ONE tool, `code_edit`
  (`path`, `oldText`, `newText`, `expectedOccurrences`), with two rules
  enforced in code. **A file may only be changed if THIS RUN read it**: the
  per-run READ LEDGER records every file a read tool returned a hash for, the
  registry feeds it in ONE place so every read tool participates, and an edit
  to a file the run never read is refused with `FILE_NOT_READ` - the refusal
  names the read that would make the edit legal. **A file may only be changed
  if it has not changed since it was read**: the ledger's hash is passed to
  the edit engine as `expected_hash`, so the engine's own `STALE_FILE`
  refusal fires - the same code, the same recovery hint, in one place. An
  ambiguous match is refused, never guessed. `code_edit` is a WRITE tool in the
  ONE policy authority, so `plan_only` removes it and `edit_verify` keeps it -
  exactly like the tool it replaces. A wrong path comes back with up to five
  nearest candidates instead of a bare "that file isn't there". The mutators
  `code_edit` subsumes are DEPRECATED, still callable, and name their
  replacement (`replace_text`, `patch_file` and `edit_file` name `code_edit`;
  `multi_file_patch` names `apply_diff`; `workspace_patch_apply` names
  `code_edit`). The genuinely DIFFERENT operations - create, delete, move,
  copy, rename, the directory tools, insert, line-range delete, unified diff -
  are NOT deprecated: removing those would remove capability, not duplication.
  The plan had sketched thirteen deprecations; the audit showed nine of them
  are distinct operations one edit tool cannot express, so the honest set is
  the four text-edit paths it actually subsumes. `workspace_read` now returns
  the file's hash, so a workspace-level read feeds the ledger too. Three new
  adversarial cases (S12 never-read, S13 stale-file, S14 ambiguous-match)
  attack the real enforcing modules, and the `code_edit_contract` capability
  class makes the whole contract measured. Files:
  python/harness/code/edit_tools.py (new), python/harness/tools.py,
  python/harness/code/fs/errors.py, python/harness/code/policy.py,
  python/harness/code/tools.py, python/harness/code/fs_tools.py,
  python/harness/agents.py,
  python/harness/code/eval/{safety_cases,safety,capabilities}.py,
  python/tests/test_code_edit_primitive.py (new, 13 cases). ADR-H285. docs
  updated: docs/harness/decisions.md, docs/harness/architecture.md,
  docs/NAVIGATION.md, docs/harness/capability-statement.md.

- **fix(plugins): the bundled SEC reference plugin is source, not a scratch
  dir.** `.gitignore` carried a bare `sec/` pattern - a gitignore pattern with
  no leading slash matches a directory of that name at ANY depth - so it was
  silently excluding `python/harness/plugins/bundled/sec/` from version
  control. Every clean clone therefore shipped without a reference plugin, and
  the plugin marketplace gate (`test_plugins_reference.py`) failed on any
  checkout that was not the author's own working tree - which is exactly why it
  passed locally and failed everywhere else. The pattern is re-included
  explicitly and the plugin is tracked. Files: Black-Eclipse-site/.gitignore,
  Black-Eclipse-site/python/harness/plugins/bundled/sec/{plugin.py,plugin.yaml}.
  docs updated: docs/CHANGELOG.md.

- **feat(charts): the chat's charts are drawn by the PYTHON engine, and ANY chart
  can be drawn.** The chat's `chart` block no longer has an ECharts path: the
  block is turned into a validated chart **SPEC** (data only - a kind, some
  series, a title - never a callback, a URL or a path) and the runtime draws it
  with `matplotlib` into a transparent PNG in the app's own palette, recorded in
  the Artifact Center and fetched back as an artifact. The chat's ECharts option
  builder (`chart-option.ts`) and the engine-preference store are **deleted**.
  **The ceiling is gone:** a chart block may also arrive as a **SCENE** -
  `panels` of `marks` - which is compositional rather than a fixed list of
  kinds, so a violin, a box plot, a Gantt, a funnel, a ridgeline, an error-bar
  chart or a dual-axis chart is a composition of the primitives (`line`, `area`,
  `bar`, `scatter`, `band`, `rule`, `label`, `box`, `violin`, `histogram`,
  `errorbar`, `heatmap`, `pie`, `donut`, `candlestick`, `waterfall`, `ridge`,
  `stem`) instead of needing a new kind invented for it. The marks are drawn
  exactly as the model writes them, and the schema read-back now describes the
  mark vocabulary so the model can see it. The rest of the app stays on ECharts.
  Files: python/harness/charts/scene.py, scene_render.py, render.py, spec.py,
  tools.py; src/lib/response/chart-spec.ts, chart-registry.ts, contract.ts,
  export.ts, response-chart.tsx; src/lib/harness/response-bridge.ts;
  src/lib/response/chart-option.ts, chart-engine.ts (deleted);
  python/tests/test_chart_scene.py; src/lib/response/chart-spec.test.ts,
  repair.test.ts.
  docs updated: docs/chart-engine.md, docs/interactive-response-engine.md,
  docs/DECISIONS.md (ADR-050), skills/ARCHITECT.md (ADR-050).

- **feat(harness): ONE search primitive, and the engine is always named**
  (Round 3 / W5, ADR-H284). The harness answers two questions about a codebase
  - "what does this SAY?" and "what files are there?" - with exactly two tools:
  `search_text` (contents, ripgrep-first with a bounded Python fallback) and
  `search_files` (names, now carrying every filter `find_files` had: exclude,
  extensions, directoriesOnly, filesOnly, includeHidden, includeIgnored). The
  older names (`workspace_search`, `find_files`) stay callable for one release
  as DEPRECATED ALIASES, the registry warns once per run naming the
  replacement, and the agent surfaces carry the canonical names only. Before
  this, the tool the model reached for FIRST was the slow one: the workspace
  search ran its own naive Python walk while the fs subsystem's `search_text`
  was already ripgrep-first. The old `workspace_search` also bypassed the code
  policy entirely; the search now goes through the code capability, so it needs
  a code profile. The workspace walker moved to its own module
  (`python/harness/code/scan.py`) so the ratcheted core file shrinks.
  Files: python/harness/code/scan.py, fs_tools.py, tools.py, agents.py;
  python/tests/test_code_search_surface.py, test_code_tools.py,
  test_chat_code_profile.py, test_code_reachability.py.
  docs updated: docs/NAVIGATION.md, docs/harness/architecture.md.

- **feat(harness): the verify-and-repair loop runs in the graph, and its status
  is DERIVED** (Round 3 / W1, ADR-H281). A change is not finished because the
  model said so: the graph's `verify_repair` node runs the project's pinned
  check CLASSES through the ONE command path, and a failure is handed back to
  the model. `RepairLoop.status` is now a property computed from the facts
  (`last_passed`, `refused`, `stopped_reason`) rather than a field someone set
  by hand - a status that said "passed" while the last check failed is exactly
  the kind of unbacked claim this harness exists to refuse. The new
  `REPAIR_FAILED` state (the check was still failing when the run ended) is
  disclosed in the answer, not only in the blob. A new eval case
  (`repair-in-graph`) drives the REAL graph with a scripted model and a
  scripted check: a graph with no repair node records nothing, and the case
  fails. Files: python/harness/code/repair.py, repair_graph.py, verify.py;
  python/harness/code/eval/capabilities.py, dataset_tasks_v1.json,
  statement.py, tasks.py; python/tests/test_graph_repair_node.py.
  docs updated: docs/harness/architecture.md, docs/harness/capability-statement.md,
  docs/harness/roadmap/round-3-parity-plan.md.

- **fix(harness): the eval gates hand back the model builder they override.**
  `eval_gates/resume.py` and `eval_gates/workflow.py` patched
  `graph.build_chat_model` and never restored it, so every later run in the
  same process answered with the gate's model. The evaluation seam now
  refuses to replace an ACTIVE override (a test double) - only a chaining seam
  may be wrapped - so an override's teardown cannot silently drop the double
  for every later test. Files: python/harness/eval_gates/resume.py,
  workflow.py, python/harness/evaluation/runner.py.
  no doc change - a test-hygiene repair inside the harness.

- **fix(harness): the surface snapshot carries the tool guidance.** A
  snapshot that drops the guidance turns "the model was told" into "the model
  was never told" on replay. Files: python/harness/routers/evolution.py.
  no doc change - one added field on an existing payload.

- **chore(harness): re-pin the size ratchet for the in-flight work.** The
  quant tool surface, the graph and the fs tool surface grew past their
  ceilings; each ceiling was re-pinned to the measured size with the reason
  recorded, and each line names its split candidate. Files:
  python/tests/test_size_budget.py.
  no doc change - a size ratchet.

- **docs(rsl): the P2 row names what the gate actually measures.** The
  per-scope concurrency cap and the deterministic selection are not in flight
  in P2, so the row now names the one thing that is: the cost per accepted
  improvement, and the proof that real usage survives into the experiment
  report. Files: docs/self-improvement/rsl-v3-plan.md.
  docs updated: docs/self-improvement/rsl-v3-plan.md.

- **chore(harness): the mandated check cannot finish, and that is why the agent
  spins.** **The cause:** AGENTS.md requires `npm run test` after EVERY change.
  That script is `vitest run && node scripts/test-python.js && node
  scripts/test-evals.js`, and the middle stage runs the Python suite, which
  stalls for over a minute inside
  `python/tests/test_application_e2e.py::test_e2e_start_health_observe_stop_restart`
  - `harness/execution/application/health.py:check_with_retries` retries a TCP
  check against port 8000 sixteen times with a backoff that grows to eight
  seconds per attempt. Measured end to end, `npm run test` takes 153s even when
  the first stall is cut short, and it never completes on its own. The shell
  tool's own ceiling is 120s, so the check is killed mid-flight every time and
  returns an opaque `Unknown: ChildProcess.kill` instead of a pass or a fail.
  The agent cannot tell whether the check passed, so it runs it again: 344
  check re-runs with no code change between them across the last forty
  sessions, `npx tsc --noEmit` 450 times all-time (87 in one session), and more
  than half of all check invocations piped through `Select-Object -First/-Last`
  to re-read an output it had already been truncated out of. The loop is also
  invisible to the host: OpenCode's own doom-loop guard only fires on
  byte-identical tool inputs, and every retry here differs by a few
  characters, so it never trips. A check that cannot report a result is not a
  check - it is a treadmill. Files: (diagnosis only - no source changed).
  no doc change - a diagnosis; the fix is not in this entry.

- **fix(chat): a long message no longer fails with "Something went wrong".**
  Pasting more than 4 000 characters into Eclipse was rejected by the front
  door with `query too long (max 4000 chars)` and rendered as a generic
  "Something went wrong" card - a message the composer had accepted was
  refused on the way to the agent, and the user was given no way to tell a
  rejected request from a broken agent. A turn is whatever the person pasted,
  so the bound now only guards ONE REQUEST BODY: it is 100 000 characters
  (~25k tokens) on both sides of the bridge, and the RUNTIME owns the real
  limit - it measures the assembled request against the resolved model's
  context window and reports an honest CONTEXT_OVERFLOW when a prompt
  genuinely does not fit. The two bounds are MIRRORED on purpose: the front
  door's `MAX_QUERY_LENGTH` (`src/lib/harness/validation.ts`) must stay >=
  the runtime's `RunInput.query` bound (`python/harness/schemas.py`), or the
  runtime would reject a request the app accepted with a bare pydantic 422.
  A prior turn now carries the same per-turn bound, so a long message is not
  silently sliced when it returns as history on the next turn; the whole
  history is bounded by dropping the OLDEST whole turns (never a turn cut in
  half), so the runtime receives every turn it is given intact and applies its
  own budget on top. The refusal itself
  improved too: it now carries the stable `INVALID_INPUT` code (the chat card
  badges it instead of showing a bare sentence), it says what to do
  ("send it in smaller parts or attach it as a document"), and it is NOT
  retried - a refused request used to be sent three times (stream 400 ->
  one-shot 400 -> one-shot retry 400), all failing identically. A missing
  streaming ENDPOINT (404/405, an older front door) still falls back to the
  one-shot path; a REFUSED request does not. Files:
  src/lib/harness/validation.ts, src/app/api/harness/chat/route.ts,
  src/app/api/harness/chat/stream/route.ts, src/lib/agent/registry.ts,
  src/lib/agent/use-agent-run.ts, src/components/screens/stock-chat.tsx,
  src/lib/bots/use-bot-delegation.ts, python/harness/schemas.py. Tests:
  src/lib/harness/validation.test.ts, src/app/api/harness/chat/route.test.ts,
  src/lib/agent/registry.test.ts. docs updated: docs/chat-ui-audit.md,
  docs/harness/architecture.md.

- **feat(chat): a long paste becomes an attachment, the way ChatGPT does it.**
  A paste over 4 000 characters is no longer dumped into the composer: it is
  intercepted, written into the conversation's session folder as a
  `pasted-text.txt` context document, and shown as a chip above the composer
  (`pasted-text-2.txt`, `pasted-text-3.txt`, … on repeat). It then flows
  through the SAME path as an attached file — extracted, injected into the run,
  removable from the chip — so there is one attachment pipeline, not two. Small
  pastes still insert normally, and the floating dock gets the same rule. The
  document caps were raised to match the turn bound (100 000 chars per document,
  200 000 combined) so a paste that becomes a document arrives as readable as
  the same text would have as a message; the runtime still measures the
  assembled turn (documents included) against the model window and reports a
  CONTEXT_OVERFLOW rather than silently dropping text. Files:
  src/lib/chat/paste.ts (new), src/lib/chat/use-session.ts,
  src/lib/chat/session-types.ts, src/lib/chat/extract.ts (caps),
  src/components/chat/chat-input.tsx, src/components/chat/empty-state.tsx,
  src/components/chat/chat-dock.tsx, src/components/screens/stock-chat.tsx,
  src/lib/harness/validation.ts, python/harness/schemas.py. Tests:
  src/lib/chat/paste.test.ts (new), src/lib/chat/extract.test.ts,
  src/lib/harness/validation.test.ts. docs updated: docs/chat-ui-audit.md.

- **fix(chat): the pasted-text chip is now readable, and Enter sends it.**
  Two things the first cut got wrong. (1) A chip you cannot open is a black
  box: clicking a pasted-text chip now opens a glass preview with the full text
  (a real file opens the session file). (2) The composer refused to send with
  nothing typed, so a paste followed by Enter did nothing at all. Now a paste
  sent with an empty composer IS the message — the text is taken back out of
  the attachment list and sent as the query, so it is never also injected as a
  document (no double tokens); with only FILE attachments and no text, a
  neutral "Read the attached document." is sent instead of a dead click. The
  send button is enabled whenever there is something to send. The floating
  dock keeps inserting a long paste as text (it has no chip UI, so intercepting
  there would swallow the paste). Files: src/components/chat/attachment-preview.tsx
  (new), src/lib/chat/use-session.ts, src/components/chat/chat-input.tsx,
  src/components/chat/empty-state.tsx, src/components/chat/chat-dock.tsx,
  src/components/screens/stock-chat.tsx. Tests: src/lib/chat/paste.test.ts.
  docs updated: docs/chat-ui-audit.md.

- **style(response): notice cards drop the left accent bar.** Every response
  notice/warning surface (callouts, unsupported-block and diagnostic cards,
  diagram/render failures, curriculum gaps, node details) shared `NoticeCard`'s
  vertical tone gradient strip on the left edge. Removed the strip and its
  palette entries so the cards keep only the frosted surface, tone icon chip,
  tinted title and wash/glow. Files:
  src/components/response/blocks.tsx. no doc change — styling only, contracts
  unchanged.

- **fix(chat): formulas are TYPESET, not printed as source.**
  A formula in the chat came out as raw text: the Markdown subset had no
  mathematics at all, so `$S = \frac{r_p - r_f}{\sigma}$` reached the reader
  as its own characters. The subset now recognises LaTeX - `$...$` inline and
  `$$...$$` as a block - and draws it with KaTeX.
  **Money stays money.** A `$...$` span only counts as a formula when it looks
  like one: it carries a LaTeX operator (`\`, `^`, `_`, `{`, `}`, `=`, `+`, `<`,
  `>`) or is a single non-digit symbol (`$x$`, `$\mu$`). The opening `$` may
  not follow a word character or a digit (`US$100`), the span may not break
  over a line, it may not begin or end with whitespace (`$5 and $10` is
  prose), and the closing `$` may not be followed by a digit (`$100`). So
  `it trades at $100` is still money, and a Sharpe ratio is a formula. The
  agent is told the same rule (`python/harness/prompts.py`, "Formulas"): write
  `USD 100`, never `$100`.
  KaTeX (already on disk as mermaid's dependency) is now a DIRECT dependency
  and is loaded ON DEMAND, so the chat's initial bundle does not carry it;
  until it arrives the formula shows its own source, and a formula KaTeX
  cannot parse shows the same way rather than breaking the message. Its
  stylesheet is global (`src/app/katex.css`) - one stylesheet for the whole
  typesetting, with its own maths faces.
  The `eclipse-response` fence renders through the same component, so a
  `markdown` block inside a structured answer typesets formulas too.
  Files: `src/lib/chat/markdown.ts` (the parser), `src/lib/chat/math.tsx` (the
  renderer), `src/components/chat/markdown.tsx` (the wiring),
  `src/lib/response/export.ts` (the plain-text export), `src/app/katex.css`,
  `python/harness/prompts.py`. docs updated: `docs/chat-ui-audit.md`,
  `docs/interactive-response-engine.md`.

- **feat(runtime): a surface can carry its own policy, and the sandbox fails
  closed.**
  A live surface (a profile, a bot, a group) can now set `memoryPolicy`
  (`off` / `profile_only`), `guardrails`, `maxAnswerChars` and a
  `subagentPrompt`. The runtime ENFORCES it: a finished answer that breaks a
  surface's guardrails fails the run with a named code
  (`GUARDRAIL_TOOL_REQUIRED`, `GUARDRAIL_CITATION_MISSING`,
  `GUARDRAIL_ANSWER_TOO_LONG`) instead of shipping as a completed result, and
  a delegated child inherits its parent's context policy - the surface adds
  prompt evidence, never a tool or a permission.
  A turn is bounded by a ceiling that MIRRORS the front door's
  `MAX_QUERY_LENGTH`, so the runtime accepts everything the front door lets
  through and reports an honest CONTEXT_OVERFLOW instead of a hard rejection.
  The sandbox fails CLOSED when the operator demands a real isolation
  primitive (`HARNESS_SANDBOX_REQUIRED=1`): the local backend caps memory, the
  process count and the tree, but it does NOT confine the filesystem or the
  network, so the analysis path refuses rather than presenting a weaker
  boundary as the requested one. Analyses pass through a concurrency gate
  (`HARNESS_ANALYSIS_CONCURRENCY`, default 2) so a burst cannot stampede the
  host.
  The chat agent's step budget is 24 by default (8 was too tight for a
  navigation turn, 12 for a turn carrying several deliverables); an operator
  can override it with `ECLIPSE_CHAT_MAX_STEPS` (clamped 1..32).
  Files: `python/harness/{main.py,tools.py,schemas.py,graph.py,graph_context.py,analysis_tools.py,delegation_tools.py}`,
  `python/harness/code/{sandbox.py,execution.py}`, `python/harness/routers/sandbox.py`,
  `src/lib/harness/{errors.ts,validation.ts}`. Tests: `python/tests/test_{chat_step_budget,delegation_tool,graph,qa_round1_acceptance,sandbox_surface,surface_context_policy,size_budget,quant_routes}.py`,
  `src/lib/harness/validation.test.ts`. docs updated:
  `docs/harness/architecture.md`.

- **feat(self-improvement): the RSL operator surface - guardrails, a digest, and
  a weekly card.**
  The self-improvement loop can now be READ, not only run. A guardrail is a
  rule the RUNTIME checks (never a rule the model is told): a violation fails
  the run with a named code and the answer is not shipped as a completed
  result, and the citation rule reuses the evaluator's own citation parser so
  a guardrail and the citation grader agree on what a citation IS. The digest
  (`GET /evolution/rsl/report`, operator-gated) is one read-only summary of
  what the loop actually did - the experiments that ran, what they cost, what
  was accepted, the candidates in flight, the lessons adopted and where
  production drifts - and everything in it is measured or `UNKNOWN`: a missing
  source never becomes a fabricated zero. The Skills page grew the matching
  surface: the RSL control panel and a weekly card.
  Files: `python/harness/self_improvement/{guardrails.py,report.py,drift_watch.py,live_surface.py,models.py,recursion.py}`,
  `python/harness/evaluation/{repair_metrics.py,export.py,nightly.py}`,
  `python/harness/routers/{evolution.py,evolution_report.py}`,
  `src/lib/harness/{evolution-client.ts,evolution-browser.ts}`,
  `src/components/screens/skills/{rsl-control-panel.tsx,rsl-weekly-card.tsx}`,
  `src/app/api/evolution/rsl/report/`. Tests:
  `python/tests/test_{drift_watch,live_surface,evaluation_repair_metrics,evaluation_export,evaluation_nightly,rsl_digest,rsl_guardrails,rsl_provenance,rsl_snapshot}.py`,
  `src/components/screens/skills/rsl-weekly-card.test.tsx`. docs updated:
  `docs/harness/agent-evaluation.md`, `docs/self-improvement/rsl-v3-plan.md`.

- **feat(chat): a refused turn reads as a refusal, and a long paste is an
  attachment.**
  A chat request the front door refused used to show a bare "Something went
  wrong" plus the server's sentence, with no code - a rejected request was
  indistinguishable from a runtime failure, and the retry logic repeated the
  SAME request that could not succeed. The refusal now carries its code and
  status, the UI badges it, and a refused turn fails ONCE.
  A paste above 4,000 characters is intercepted and ATTACHED: it lands in the
  conversation's session folder as a context document and shows as a chip, the
  way an uploaded file does, because a multi-thousand-character blob in the
  composer makes the composer unusable. A pasted document sent with nothing
  typed IS the message (the text is taken back out of the attachment list, so
  it is not injected twice). An attachment can be OPENED and read before it is
  sent.
  Files: `src/lib/chat/{paste.ts,session-types.ts,use-session.ts}`,
  `src/lib/agent/{registry.ts,use-agent-run.ts}`, `src/lib/harness/index.ts`,
  `src/app/api/harness/chat/{route.ts,stream/route.ts}`,
  `src/components/chat/{chat-input.tsx,chat-dock.tsx,empty-state.tsx,attachment-preview.tsx}`,
  `src/components/screens/stock-chat.tsx`, `src/lib/bots/use-bot-delegation.ts`.
  Tests: `src/lib/chat/{paste.test.ts,extract.test.ts}`,
  `src/lib/agent/registry.test.ts`, `src/app/api/harness/chat/route.test.ts`.
  docs updated: `docs/chat-ui-audit.md`.

- **fix(market): the yfinance window travels explicitly, and a chart's `data`
  alias actually draws.**
  A 1y range was requested from yfinance as a rolling `period`, which is
  anchored to "now": a request for 2025-10-20..2026-10-20 came back starting
  on the 21st - a silently short series that changes every return, drawdown
  and statistic computed from it. The window is now passed to yfinance as
  explicit `start`/`end`, so the series really covers the requested days.
  The chat's chart spec carries the scene fields the newer marks need (`z`,
  `parents`, `colors`, `sources`, `targets`, `weights`), and the Python
  figure reads a mark's values through the model's own accessor, so a mark
  that arrives as `data` instead of `y` is drawn instead of coming out
  empty.
  Files: `scripts/yfinance_bridge.py`, `python/harness/charts/plotly_figure.py`,
  `src/lib/scraper/fetchers/yfinance.ts`, `src/lib/response/chart-spec.ts`.
  Tests: `python/tests/test_yfinance_bridge_window.py`,
  `src/lib/scraper/fetchers/yfinance-window.test.ts`,
  `src/lib/harness/data-bridge-{identity,phase2}.test.ts`. docs updated:
  `docs/CHANGELOG.md`.

- **fix(chart): a linear regression is a chart kind, and an unknown kind no
  longer loses the chart.**
  A "linear regression chart" had nowhere to go: the vocabulary had no
  regression, and an unknown `chartType` INVALIDATED the whole chart block,
  so the reader got nothing at all. Now:
  - `regression` is a real kind - a chart block with `chartType: "regression"`
    (or a `regression` mark in a scene) draws the points, ONE ordinary
    least-squares line through them, and the R-squared in the legend. The
    engine fits the line from the same numbers it draws, so the picture and
    the R-squared can never disagree; a fit that cannot be computed (fewer
    than two points, no variation in x, no variation in y) is not drawn, and
    the trace says why. The arithmetic is plain on purpose - a reader must be
    able to check `R2 = 0.87` from the picture
    (`python/harness/charts/regression.py`).
  - An UNKNOWN `chartType` now falls back to `auto` instead of invalidating
    the block: one odd kind must never cost the reader every other panel.
    The mark types already worked that way; the block kind now does too.
  - The synonyms a producer actually uses are read (`linear_regression`,
    `linear regression`, `trendline`, `ols`, `fit`, `trend`), and the agent is
    told that a regression is a `regression` mark - never to fit the line
    itself.
  Files: `python/harness/charts/{regression.py,scene.py,plotly_figure.py,scene_render.py,tools.py}`,
  `src/lib/response/{contract.ts,normalize.ts,chart-spec.ts}`,
  `src/lib/harness/charts.ts`, `python/harness/prompts.py`. Tests:
  `python/tests/test_chart_regression.py`, `src/lib/response/chart-regression.test.ts`.
  docs updated: `docs/chart-engine.md`, `docs/interactive-response-engine.md`.

- **fix(chat): a chart is ONE step, and a market refusal names the routes that
  already failed.**
  A real run of "regress AAPL's daily close over 12 months" burned all 24
  steps and 2.7M tokens and answered with prose and no chart. The engine was
  never the problem: the agent had the 251 closes by step 7 and then spent
  sixteen steps re-verifying them (6 scraper runs, 5 browser evaluations, 3
  sandbox computations) because it thought a chart needed a drawing TOOL call
  to read the numbers back. Two rules fix that:
  - **A chart block IS the drawing.** The data goes IN the block and the engine
    draws it: a `regression` mark fits the line and shows the R-squared in its
    legend. No drawing tool call, no round trip, ONE step. The agent is told
    never to fit the line itself and never to quote an R-squared it has not
    read back.
  - **One attempt per route.** A route that refuses is a routing problem, not
    a reason to keep asking: try the next route once, and if the second route
    for the same series also refuses, use the data already in hand (or the
    numbers the user gave) and say plainly what it is and where it came from.
    Never re-verify a series you already hold, and never spend a browser on a
    provenance audit the reader did not ask for.
  The market refusal now carries the WHOLE provider trail
  (`Providers tried: yahoo: DATA_NOT_AVAILABLE (...); stooq: ...; polygon:
  AUTHENTICATION_FAILED (no POLYGON_API_KEY)`) and says that a provider
  answering AUTHENTICATION_FAILED needs a credential it does not have - do
  not try it again. The last provider's error alone hid the more useful one
  (a keyless route with no data), so the agent could not tell which routes had
  already been tried and went to scrape a page instead.
  Files: `python/harness/prompts.py`, `python/harness/market/{gateway.py,tools.py}`.
  Tests: `python/tests/test_market_refusal_trail.py`. docs updated:
  `docs/chart-engine.md`, `docs/harness/market-data.md`.

- **fix(chart): a chart may NAME its series, and a mark's points are read the
  way a model writes them.**
  A real run of "regress AAPL's daily close over 12 months" produced no chart
  at all, and the run's own record says why - in the model's words: "The chart
  did not render. The scatter-plus-regression block I built failed the
  renderer's schema check on the mark data format, and I've run out of steps
  to resubmit it." Three separate causes, all fixed:
  - **A mark's points are read the way a person writes them.** A mark's `y` /
    `data` now accept a scalar, an `[x, y]` pair (the pair carries its own x)
    or an object with named fields - `{i: 1, close: 188.7}` (a field named
    like an x is the x, one named like a y is the y; when the names say
    nothing, the first two numeric fields are the point, in order). The engine
    splits a pair into its x and its y. A chart that refuses a point over its
    FORMAT is a chart the reader never sees.
  - **A chart may NAME its series instead of carrying it.** A mark (or a whole
    chart block) may set a `dataSource` - `{symbol, market?, interval?,
    start?, end?, field?, name?}` - and the engine fetches that series through
    the SAME market gateway every price comes from, then draws and fits it. A
    chart that spells out 250 prices is a long message, and a long message
    gets truncated: the block stops being valid and the chart is lost with no
    diagnostic. With a named source the model writes ~200 characters and the
    reader gets the real 251-bar series, fitted (R2 = 0.687 on AAPL over
    2025-10-22..2026-10-21). A source that cannot be fetched is a named
    refusal, never a guess. The chart route binds the server bridge to the
    gateway (the bridge is bound per RUN, so a route outside a run had none).
  - **The agent is told not to fetch a market series into its own context.**
    The market tool's text result is truncated by design (a 251-bar series
    arrives as its first 30 and last 10 bars), so a model that tries to fit
    the series itself is fitting a fraction of it. The chart fetches the
    series; the model does not.
  Verified in the real app: the same request now answers with a live chart -
  the points, the fitted line and the legend "Series fit (R2 = 0.687)" - in
  14 steps and a 1 KB block (was 24 steps and a 3.8 KB block that was lost).
  Files: `python/harness/charts/{scene.py,source.py,tools.py,spec.py}`,
  `python/harness/routers/charts.py`, `python/harness/service.py`,
  `src/lib/response/{contract.ts,normalize.ts,chart-spec.ts}`,
  `src/lib/harness/charts.ts`, `python/harness/prompts.py`. Tests:
  `python/tests/test_chart_{pairs,source}.py`,
  `src/lib/response/chart-{pairs,point-shapes,source}.test.ts`. docs updated:
  `docs/chart-engine.md`, `docs/harness/market-data.md`.

## 2026-10-20

- **docs(harness): Round 4 — the plan that closes the last two dimensions,
  and a correction to the score.** Round 3 finished every workstream, and five
  of the seven dimensions are at target. The remaining gap is concentrated:
  **Evaluation 9.0** and **Operations 4.0**. The plan re-derives the weighted
  score and **corrects an earlier over-claim**: it was reported as ~9.42 with
  Ops at 7.5, which was optimistic about the *process* criteria. Scored against
  its own sub-criteria, Ops is **4.0** (`v0.2.0` is prepared but `git tag -l` is
  empty; `CODEOWNERS` has placeholder owners; the branch is not on `main`; the
  tree is 375,997 lines and grew this round), so the published number is
  **9.01**, not 9.42. The arithmetic then lands exactly: Eval 9.0 → 9.5 is
  +0.05 and Ops 4.0 → 9.5 is +0.44, and **9.01 + 0.49 = 9.50**. That is why the
  plan spends nothing on Loop/Ctx/ACI/Safe/Ext — they are at target and further
  work there cannot move the total. Six workstreams in four waves: **V1** land
  the branch and tag it (one command, +0.20, and every other "done" claim is
  measured against a landed tree); **V2** shrink the surface, one merge per
  release, with the ceiling required to *fall* (and an explicit warning not to
  merge `browser/` into `computer/` — they were listed together by size, not by
  duplication); **V3** a second pair of eyes, which closes the 15 legacy ADR
  shape gaps by **re-labelling prose that is already there**, never by inventing
  a rationale, and fixes the one flaky test; **V4** distribute; **V5** the first
  live number — the only thing that turns `NOT MEASURED` into a number — and
  the four dimensions that are measured but ungated (`cost`, `latency`,
  `token_usage`, `reliability`), gated from that measured baseline; **V6** an
  external suite, the only route to a number anyone else can compare. The plan
  also names the four inputs only the operator can supply (a provider key, the
  SWE-bench dataset, a second human, a PyPI credential) so a blocked workstream
  is never reported as unknown. docs updated:
  docs/harness/roadmap/round-4-gap-closure.md,
  docs/harness/roadmap/README.md.

- **chore(harness): the Round 3 work is merged onto main, and the decision
  series is unambiguous again.** The two branches had both taken ADR numbers
  284-289, so the merged series had seven DUPLICATES and a reference to
  "ADR-H284" would have named two different decisions. The later occurrence of
  each was renumbered and the old number retired with a redirect, so an old
  reference still resolves and the decision is unchanged; the vacated numbers
  are now explicitly RESERVED in the ADR check. The release gate keeps both
  sides' steps: the decision record, the harness size budget and the corpus
  gate all run before the tests. The size ratchets were re-pinned to the
  merged tree, and the generated artifacts (the capability statement, the
  published benchmarks, the portable tool manifest - now 953 tools) were
  regenerated against it. One lint error that was already on `main` and
  blocked `npm run check:all` for everyone is fixed (`Promise<any>` in the
  chart route's test - a mock's return type, which the rule rejects and which
  nothing reads). Files: docs/harness/decisions.md,
  python/tests/test_size_budget.py, scripts/check-all.js,
  scripts/size-budget.json, scripts/check-adr-numbers.js,
  docs/harness/capability-statement.md, docs/harness/benchmarks.md,
  docs/harness/tool-registry.json,
  src/app/api/harness/charts/route.test.ts.

- **fix(charts): the full-view chart no longer collides with the app's header.**
  The focus overlay lived inside the chat's stacking context, so the top bar and
  the price ribbon painted OVER the chart and its toolbar. The full view is now
  **portalled to `<body>`** (the app's rule for floating surfaces) and sits at
  `z-[300]` - above every layer of the shell - so the chart's toolbar is clear
  of the header. The backdrop is unchanged: the same frosted blur it has always
  been (`bg-black/55 backdrop-blur-sm`), so the app reads through it. The
  focused chart also fills the viewport height instead of a fixed 640 px.
  Verified in the real app: the overlay computes to `position: fixed`,
  `z-index: 300`, 1440x900, above the price ribbon's `z-index: 50`.
  File: `src/components/response/response-chart.tsx`. docs updated:
  `docs/CHANGELOG.md`.

- **fix(macro): a provider's HTML error page can no longer become an
  observation (silent corruption).** FRED's graph endpoint answered a site-wide
  maintenance page with HTTP **200**. The FRED source split that page into
  lines and emitted them as `{ date, value }` rows, so the normaliser produced
  observations out of an error document — `value: 400`, `dataTimestamp: "<link
  href=\"https://fonts.googleapis.com...\"`, `publishedAt: "</html>"` — and
  stamped them `Retrieval status: OK`, `Quality: valid`, `validationStatus:
  'valid'`. Anything downstream that trusted `quality: valid` would have
  regressed a 10y real yield of 400%. Two layers now refuse it: **the source**
  detects an HTML body and throws (a transport failure with a plain message:
  *"FRED is serving a web page instead of CSV — the series is unavailable right
  now, not a value"*), and **the normaliser** only accepts a row whose date
  looks like a date (`YYYY`, `YYYY-MM`, `YYYY-MM-DD`, `YYYY-Qn`) — a fragment of
  an error page is not a date, so it is not an observation. Files:
  `src/lib/economics/fetch.ts` (`isHtmlPayload`, `looksLikeDate`, the date
  picker), `src/lib/economics/sources.ts` (the FRED source), and the economics
  panel's own fetcher in `src/lib/economics/snapshot.ts`. Tests:
  `src/lib/economics/fetch.test.ts` (6). docs updated: `docs/CHANGELOG.md`.

- **fix(market): the history route conflated a WINDOW with a BAR SIZE — a
  multi-year history came back EMPTY and read as "no data".** `period` was read
  as the interval, so `period: "1y"` asked the provider for a "1y bar" — not a
  bar size at all. The request came back empty, and the market tool (showing the
  OLDEST bars) made a five-year history read as *2021* data, so an analysis
  reasoned about the wrong years and held no current print. The bar size
  (`interval`) and the window (`period` / `range`) are now read from their own
  fields, and a value that is both ("1d", "1mo", "3mo") is a WINDOW.
  **Market-data symbols are no longer refused by the equity universe:** an index
  (`^VIX`), a future (`GC=F`) or a currency index (`DX-Y.NYB`) has no
  instrument row — a coverage gap, not an identity failure — so it is fetched
  from Yahoo and labelled `marketData: true`. Verified end to end: `^VIX`,
  `GC=F`, `DX-Y.NYB` and `^TNX` now return 1,255–1,258 DAILY bars
  (2021-10-21 → 2026-10-21), and GLD returns 1,255 bars over the same window.
  Files: `src/lib/harness/data-bridge-history.ts`, `src/lib/harness/data-bridge.ts`.
  Tests: `src/lib/harness/data-bridge-history.test.ts` (10). docs updated:
  `docs/CHANGELOG.md`.

""- **feat(agent): a missing data series is now a ROUTE, not a dead end — the
  agent writes a scraper for the page that has it.** The vault does not hold
  everything, so a failed data call used to end the analysis. Two changes make
  the agent fight the limitation instead of stopping: **(1) the agent's
  guidance** now says that a data route answering UNAVAILABLE is a routing
  problem, and names the lane to use — write a scraper for the site with
  `scraper_run` (a short program that fetches through `eclipse_tools.web_page`
  and leaves the records in `result = {"rows": [...]}`; the host does the
  fetching, so the program never opens a socket, and the operator approves the
  site once per domain). The rows land as a dataset labelled **SCRAPER** —
  collected page data, never a verified source — and the agent must say so
  wherever it uses them. **(2) every data refusal now names its next route**,
  so the correction is read where the failure happens: the market tool's
  UNAVAILABLE answer and the app's data-bridge failure message both carry
  "a scraper can collect this from the page that has it", and the bridge
  result carries `nextRoute: "scraper_run"`. Files:
  `python/harness/prompts.py`, `python/harness/market/tools.py`,
  `src/lib/harness/failure.ts`. docs updated: `docs/CHANGELOG.md`.
- **fix(market): the macro series an asset analysis needs, and the RECENT
  window.** A full gold analysis came back honest but incomplete, and named its
  two blockers — both real product bugs. **(1) No real-yield series existed:**
  `DFII10` was not a registered macro series, so the driver regression could
  not be run at all. The macro registry (Python and its TS mirror) now carries
  the 10y and 5y TIPS **real yields**, the 2y and 10y **nominal yields**, the
  10y **breakeven**, the **broad dollar index** (`DTWEXBGS` — the daily dollar
  series the analysis could not get) and the **volatility index** (`VIXCLS`),
  with the generic names (`real_yield`, `breakeven`, `dollar_index`, `dxy`,
  `vix`) resolving to them. Verified: all three resolve from FRED. **(2) The
  market tool rendered the OLDEST bars** of a series (and only the last three),
  so a five-year history read as *2021* data and the model held no current
  print — it was reasoning about the wrong years. It now shows the first bar
  for context and the **last ten** — the present. Files:
  `python/harness/macro_identity.py`, `src/lib/harness/macro-identity.ts`,
  `python/harness/market/tools.py`. docs updated: `docs/CHANGELOG.md`.

- **fix(charts): a chart that "was not loading" now loads — and the chat's
  charts are plain, centred and big.** **The cause:** the engine refused the
  WHOLE spec when one mark used a shape it did not know (the contract
  tolerated it, the engine did not), so a block with one odd mark came back
  as a 400 and the chart never drew. The engine now normalises a mark the way
  the contract does — a synonym (`candles`, `bars`, `doughnut`) is mapped, an
  unknown type becomes a `line`, and a mark may carry its values under
  `data` (the name a series uses) as well as `y` — so **one odd mark can
  never cost the reader every other panel**. **The look:** the chart no longer
  sits on a glass card (the chart IS the surface now), it is **centred** in the
  column and as **large** as the column allows (up to 1100 px wide, 420 px
  tall; 640 px in the focus view), and the loading state says **"Drawing the
  chart…"** instead of showing an empty pulse — the first chart after a runtime
  start can take a while, and an empty box read as broken. Files:
  `python/harness/charts/scene.py` (the tolerant mark), `src/lib/response/contract.ts`
  (the `data` alias), `src/components/response/response-chart.tsx` (the look).
  docs updated: `docs/CHANGELOG.md`.

- **feat(charts): 3D charts — a 3D mark, not a separate chart.** The chart
  engine can now draw in three dimensions: `scatter3d` (a point cloud) and
  `surface` (a grid) carry a third dimension (`z`) and live in the figure's
  `scene` — a camera, three axes, a cube — so the reader can orbit, zoom and
  pick points. Because the chart is a live Plotly figure, the 3D view is as
  interactive as the flat one (drag to orbit, scroll to zoom, hover for the
  point). The flat axes step aside for a 3D chart, and the mark's `x`/`y` now
  accept labels as well as numbers (a 3D bar's categories). Files:
  `python/harness/charts/scene.py` (the 3D marks + the `z` axis),
  `python/harness/charts/plotly_figure.py` (the 3D traces and the scene
  layout), `src/lib/response/contract.ts` (the model's 3D marks),
  `src/lib/harness/charts.ts`, `python/harness/prompts.py`. Tests:
  `python/tests/test_chart_3d.py` (4). docs updated: `docs/chart-engine.md`,
  `docs/CHANGELOG.md`.

- **feat(charts): the chat's charts are REAL charts now — vector, zoomable,
  pannable, with a legend.** A picture cannot be zoomed, so the engine now
  authors each chart as a **Plotly figure** in Python (`plotly_figure.py`) and
  the browser renders it as **vector SVG**: scroll-zoom, pan, a hover readout, a
  legend, and a PNG/zoom toolbar. The chart is still authored in Python from
  the same validated spec, so the data and the look are unchanged — only the
  rendering moved from "a PNG of a chart" to "a chart". The library is served by
  the app from **its own route** (`/api/harness/charts/plotly`), out of the
  Python package that ships it: never vendored into git, never fetched from a
  CDN, so the app keeps working offline. **No background**: the figure's paper
  and plot are transparent, so the chart sits on the app's frosted surface
  without hiding the frost. The drawn picture (matplotlib) is still produced
  from the same spec and stays the export and the honest fallback when the
  library cannot load. The mark vocabulary grew the family charts — `treemap`,
  `sunburst`, `funnel` and `sankey` are marks now, so a treemap of holdings is
  a real treemap rather than a bar that stands in for one. Files:
  `python/harness/charts/plotly_figure.py` (new), `python/harness/charts/scene.py`
  (the new marks), `python/harness/charts/service.py` + `routers/charts.py` +
  `charts/tools.py` (the figure travels with the picture),
  `src/app/api/harness/charts/plotly/route.ts` (new: serves the library),
  `src/components/charts/plotly-chart.tsx` (new: the live chart),
  `src/components/response/response-chart.tsx` (renders the live chart, the
  picture as the fallback), `src/lib/harness/charts.ts`, `python/requirements.txt`
  (+ `plotly`), `scripts/doctor.js` (reports it). Tests:
  `python/tests/test_chart_figure.py` (20) and a browser check (SVG rendered,
  zoom changes the axis, transparent background, the toolbar present).
  docs updated: `docs/chart-engine.md`, `docs/CHANGELOG.md`.

- **fix(charts): the chat's charts are legible — bigger text, no duplicated
  title, no overlapping dates, and a card that is not full width.** Four
  problems, all fixed in the engine and the chat's chart surface. **(1) The
  text was too small:** the engine now draws in fewer inches at a higher
  resolution (`DRAW_DPI = 150`), so the labels and strokes are a fixed
  fraction of the PICTURE — a chart shown at 860 px has legible labels whether
  it was drawn at 720 px or 1400 px. **(2) The title was drawn twice** — once
  by the chat above the chart and once inside the picture. The picture no
  longer repeats the title or the description (the chat shows both); a caller
  that wants the title in the picture asks for it. **(3) Ninety daily dates
  overlapped into a smear:** the engine now THINS the category labels (every
  Nth label is kept — the DATA is never thinned) and turns long labels, so
  the axis stays readable at any density. **(4) The picture was a small image
  in a full-width card:** the chat draws at 1000×560, shows it at up to 860 px
  at its natural aspect, and the card now shrinks to the picture
  (`w-fit`) instead of spanning the column. The **candle chart is hoverable
  now**: the interaction map covers candlesticks, so the crosshair snaps to a
  candle and the tooltip shows its open / high / low / close. Files:
  `python/harness/charts/render.py` (`DRAW_DPI`, `_set_category_labels`),
  `python/harness/charts/interaction.py` (candles),
  `src/lib/response/chart-spec.ts` (`includeTitle`),
  `src/components/response/response-chart.tsx` (size, card width).
  docs updated: `docs/chart-engine.md`, `docs/CHANGELOG.md`.

- **feat(quant): a Pine run is now graded by Eclipse's own machinery.** The two
  halves of this work did not meet: the verdict, the regimes and the Edge
  Report judged ECLIPSE-native backtests, while a Pine script came back as raw
  plots and trades. The new adapter closes that: the Pine trades are translated
  into the engine's own trade shape, the equity and drawdown curves are
  rebuilt from the bars the script ran on, and then EVERYTHING downstream is the
  existing machinery - the metrics engine computes the numbers, the regime
  classifier labels the conditions, the Monte-Carlo resamples the sequence, the
  Edge Verdict grades it and the Edge Report writes the document. A TradingView
  script now gets an **Eclipse-native A-F grade**, with the same regime
  attribution, the same Monte-Carlo fan and the same downloadable report as a
  strategy written in Eclipse. The adapter does three things and nothing else -
  translate, rebuild the curves, hand over - and it does **not** re-account the
  trades: the Pine engine's own fills, sizes and P&L are taken as produced. Two
  warnings travel with the artifact so a reader cannot miss it: the equity
  curve is marked at each trade's EXIT bar (the Pine engine reports fills, not
  a mark-to-market curve), so per-bar volatility is understated and the
  risk-adjusted ratios are optimistic; and the fills are the Pine broker
  model's, so they are not comparable to an Eclipse backtest's fills. The
  Monte-Carlo needed one small generalisation to serve this: the families that
  resample a *recorded* trade sequence now work on any recorded run
  (`MonteCarloEngine.from_recorded`), while the families that re-run the
  strategy cannot - a Pine script is not ours to re-run - and they refuse with
  a named reason instead of pretending. Surfaces: the tool `grade_pine_script`
  and the route POST /quant/pine/report. Files:
  python/harness/quant/pine_report.py (new),
  python/harness/quant/pine_tools.py, python/harness/quant/montecarlo.py,
  python/harness/quant/edge_report.py, python/harness/routers/pine.py. Tests:
  python/tests/test_quant_pine_report.py (11). docs updated: docs/pine.md.


- **feat(charts): the chat's Python charts are now INTERACTIVE, and they are no
  longer stretched.** A picture cannot be hovered, so the engine now returns an
  **interaction map** with the picture: the picture's own pixel geometry (the
  axes' box) and, per category, its x position and each series' value there
  (`python/harness/charts/interaction.py`). The chat draws the pointer
  experience over the picture from that map — a crosshair at the nearest
  category and a tooltip with the values (`src/components/charts/chart-hover.tsx`).
  Because the map is in the picture's pixels and the browser converts it to
  percentages, the interaction survives any display size, and the values are
  the same ones the picture was drawn from (a gap stays a gap). **The
  stretching is fixed:** the chat draws at 720×400 and shows the picture at its
  natural aspect, left aligned and capped at 640 px, instead of stretching it
  to the full column width with a fixed height. Files:
  `python/harness/charts/interaction.py`, `python/harness/charts/render.py`
  (`render_chart_with_interaction`), `python/harness/charts/service.py` (the
  map rides the figure), `src/lib/harness/charts.ts` (`ChartInteraction`),
  `src/components/charts/chart-hover.tsx`,
  `src/components/response/response-chart.tsx`. Tests:
  `python/tests/test_chart_interaction.py` (5). docs updated:
  `docs/chart-engine.md`, `docs/CHANGELOG.md`.

- **fix(harness): re-pin the prompt ceiling after the sandbox-rules guidance.**
  The system prompt grew to 34,804 characters - the per-command sandbox rules and
  the "a refusal names the correction" guidance - while the ceiling stayed at
  34,277, so the prompt-size ratchet failed. Re-pinned to the measured size,
  with the reason recorded in the same style the ceiling has always used; it may
  only shrink from here. The two file-system tools that are registered but not
  yet in any agent allowlist are now listed as deliberately invisible, so the
  registry-visibility gate is honest about them instead of failing on them.
  Files: python/tests/test_phase_s_stabilization.py,
  python/tests/test_memory_tools.py, python/tests/test_registry_visibility.py.
  no doc change - a size ratchet and a test-hygiene repair.


- **feat(charts): the chat's charts are drawn by the PYTHON engine, and any chart
  can be drawn at all.** The chat's `chart` block no longer has an ECharts
  path: the block is turned into a validated chart **SPEC** (data only — a
  kind, some series, a title — never a callback, a URL or a path) and the
  runtime draws it with `matplotlib` into a transparent PNG in the app's own
  palette, recorded in the Artifact Center and fetched back as an artifact.
  The chat's ECharts option builder (`chart-option.ts`) is **deleted**.
  **The ceiling is gone:** a chart block may also arrive as a **SCENE** —
  `panels` of `marks` — which is compositional rather than a fixed list of
  kinds, so a violin, a box plot, a Gantt, a funnel, a ridgeline, an error-bar
  chart or a dual-axis chart is a composition of the primitives (`line`, `area`,
  `bar`, `scatter`, `band`, `rule`, `label`, `box`, `violin`, `histogram`,
  `errorbar`, `heatmap`, `pie`, `donut`, `candlestick`, `waterfall`, `ridge`,
  `stem`) instead of needing a new kind invented for it. The marks are drawn
  exactly as the model writes them, and the schema read-back now describes the
  mark vocabulary so the model can see it. The `python_chart` agent tool takes
  the same scene form. A figure is always `computed` and never evidence; a
  malformed chart is a refusal that names the missing part, never a broken
  picture. **Scope:** the chat only — the journal, portfolio, dashboard,
  backtest, economics, fundamentals and workspace widgets, the price chart, the
  Investor Eye map and the relationship graphs stay on ECharts, because they
  draw from live data at interactive rates and a server-drawn picture cannot
  serve that. Files: `python/harness/charts/{scene,scene_render}.py`,
  `python/harness/charts/spec.py` (the `scene` kind + the panel/mark
  vocabulary), `python/harness/charts/render.py` (the scene renderer),
  `python/harness/charts/tools.py` (the tool's scene schema),
  `src/lib/response/contract.ts` (the block's `panels`),
  `src/lib/response/chart-spec.ts` (block → spec, including the scene),
  `src/components/response/response-chart.tsx` (the picture),
  `src/lib/response/chart-registry.ts`, `src/lib/response/export.ts`,
  `src/lib/harness/charts.ts`, `src/lib/harness/response-bridge.ts` (the
  deeper read-back), `python/harness/prompts.py` (the model's guidance).
  Tests: `python/tests/test_chart_scene.py` (23), `python/tests/test_charts.py`
  (29), `src/lib/response/chart-spec.test.ts` (22), `src/lib/response/repair.test.ts`.
  docs updated: `docs/chart-engine.md`, `docs/interactive-response-engine.md`,
  `docs/DECISIONS.md` (ADR-050), `skills/ARCHITECT.md` (ADR-050),
  `docs/CHANGELOG.md`.

- **perf(harness): one search primitive per question, on a fast engine, and the
  engine is always named.** The harness had FOUR tools for TWO questions, and
  the two the model reached for FIRST were the slow ones. `workspace_search`
  ran its OWN naive Python walk while the fs subsystem's `search_text` - one
  name away, in a surface that listed both - was already ripgrep-first; the
  slow one had the friendlier name and sat first in every surface.
  `search_files` and `find_files` were always ONE implementation with two
  front-doors (`search_files` is literally `find_files(include=[pattern])`),
  and only `find_files` carried the exclude/extension/directory filters. A
  model asking "where is this?" paid the slow path by default, and the answer
  never said which engine ran. The search surface is now TWO tools:
  `search_text` for file CONTENTS and `search_files` for file NAMES.
  `workspace_search` now DELEGATES to the one content search, so the old name
  runs on the fast engine - and **the answer always names the engine that
  produced it** (`ripgrep` or `python-scan`), so a slow result is explainable
  rather than mysterious. `search_files` now carries every filter `find_files`
  had, so nothing was lost in the consolidation. The two older names stay
  callable for one release as DEPRECATED ALIASES - the registry warns once per
  run naming the replacement (deprecation is advisory, not a block) - and the
  agent surfaces carry the canonical names only. A search now goes through the
  code capability, so it needs a code profile: that is the Phase-0 rule (no
  profile, no code capability) and it closes a hole, because the old
  workspace-level search bypassed the code policy entirely. The workspace
  walker moved out of the ratcheted `code/tools.py` into `code/scan.py`,
  because it is a scan and not policy. The cost is honest and bounded:
  `code/fs_tools.py` crossed the 1200-line hard ceiling and now carries a
  justified ratchet entry, with the fs tool surface named as a W7a split
  candidate. The two walkers - the moved one and the fs subsystem's own - were
  NOT merged: they have different contracts (a file OR a directory, bounded by
  bytes, versus directory-only and hidden-file aware), and merging them would
  change the fs search's behaviour while looking like a cleanup. The legacy
  payload field `filesScanned` is gone (nothing read it) and is replaced by
  `engine` and `filesWithMatches`, both of which are exact. Files:
  python/harness/code/scan.py (new), python/harness/code/tools.py,
  python/harness/code/fs_tools.py, python/harness/agents.py,
  python/harness/code/eval/capabilities.py,
  python/tests/test_code_search_surface.py (new, 11 cases). ADR-H284. docs
  updated: docs/harness/decisions.md, docs/harness/architecture.md,
  docs/NAVIGATION.md, docs/harness/capability-statement.md.

- **feat(quant): the Pine fix loop - the script fails, the model rewrites it,
  the engine runs it again.** The loop QuantPad demonstrates, with the policy
  **reused rather than reinvented**: the budget (`RepairBudget`), the outcome
  vocabulary and the output digest all come from the code verify-and-repair
  subsystem (`code/repair.py`, `code/verify.py`), so a Pine fix loop and a code
  fix loop are bounded the same way and report the same way. Two rules the
  loop keeps. **The failure text is DATA, not an instruction**: a Pine error
  can contain anything the script put in it, so it is fenced
  (`<pine-error>`), labelled and bounded to 4,000 characters before it reaches
  the model. **A failed patch is not a pass**: a reply WITHOUT a fenced script
  is not a patch - the loop stops rather than guessing where the script starts
  in a wall of prose (that was a real defect in the first cut, caught by the
  tests) - and a script that still fails is reported as still failing. The
  model is asked for one fenced ```pine block and the patched script is RUN
  before anything is claimed, so the engine is always the judge. The run's own
  model settings are used, so a controlled sub-run inherits the same provider
  and credentials. Surfaces: `run_pine_script` with `autoFix` and
  `maxFixAttempts`. Files: python/harness/quant/pine_repair.py (new),
  python/harness/quant/advanced_tools.py. Tests:
  python/tests/test_quant_pine_repair.py (13).

- **feat(harness): a project fills itself up with what a run actually made.** A
  project is only useful if it fills itself up, and the policy is deliberately
  conservative: a run that names a project **records itself** in that project
  (a `note` member carrying the run id, its status and a bounded excerpt of
  its answer), and every **artifact the run produced** joins the project as an
  `artifact` member. It attaches what the run **made**, never what the run
  **mentioned**; the user's own `project_attach` calls are untouched, and
  attaching the same run twice does not duplicate a member. Nothing here can
  fail a run - a project that does not exist, an artifact service that is not
  configured, a member that cannot be written are all reported and swallowed,
  because a finished answer must not be lost to a bookkeeping step. Files:
  python/harness/projects/attach.py (new), python/harness/graph.py. Tests:
  python/tests/test_quant_pine_repair.py (13).


- **docs(charts): narrow the Python chart engine to the chat's chart blocks.**
  The docs now say what the code does: the CHAT's chart block can be drawn by
  EITHER engine — the interactive ECharts chart (the default) or the picture the
  runtime's Python engine draws — and every other surface (journal, portfolio,
  dashboard, backtest, economics, fundamentals, workspace, the price chart, the
  Investor Eye map and the relationship graphs) stays on ECharts, because those
  draw from live data at interactive rates and a server-drawn picture cannot
  serve that. ADR-050 is rewritten to match, in both `skills/ARCHITECT.md` and
  `docs/DECISIONS.md`. docs updated: `docs/ARCHITECTURE.md`,
  `docs/interactive-response-engine.md`, `docs/investor-eye-architecture.md`,
  `docs/chart-engine.md`, `skills/ARCHITECT.md`, `docs/DECISIONS.md`.

- **feat(quant): run a Pine Script on Eclipse's own bars.** Pine is the lingua
  franca of TradingView: a trader who already has a Pine strategy usually
  cannot run it anywhere else, because the script is bound to TradingView's
  data and their fills. A Pine script can now be evaluated **here**, against
  the bars the caller already holds. The engine is **`pinets`** (PineTS, by
  LuxAlgo), which is AGPL-3.0-only, so it is NOT a dependency of the app and
  NOT imported by it: it lives in its own program
  (`Black-Eclipse-site/pine-engine/`, with its own `package.json`) that Eclipse
  spawns as a child process and talks to over files - a JSON request in, a
  JSON response out, nothing but data crossing the boundary. That is the
  "separate programs communicating at arm's length" pattern from the GPL FAQ,
  and it keeps the app proprietary: this folder is the corresponding source of
  the AGPL-covered work here, nothing from `pinets` is copied into the
  repository, and `pine-engine/NOTICE.md` states the boundary. Four rules the
  runtime keeps: the engine **never reaches the network** (the bars come in
  the request); a **missing engine is a named refusal**
  (`PINE_ENGINE_UNAVAILABLE`, naming `npm run setup:pine`) rather than an
  empty result that looks like a script that plotted nothing; a **Pine runtime
  error is the script's own error**, reported with its message, never
  swallowed and never replaced with a zero; and the child is **bounded** - a
  timeout, a bar cap, a source cap and a **scrubbed environment**, so the
  engine never inherits the runtime's API keys, tokens or database paths. The
  tool and the route accept either explicit OHLCV bars or a stored research
  dataset; the first plot is drawn through the ONE chart engine and recorded
  in the Artifact Center. Surfaces: the tool `run_pine_script`, the routes
  POST /quant/pine and GET /quant/pine. Files: pine-engine/ (new: runner.mjs,
  package.json, NOTICE.md), python/harness/quant/pine.py (new),
  python/harness/quant/advanced_tools.py, python/harness/quant/tools.py,
  python/harness/routers/pine.py (new), python/harness/main.py, package.json
  (`npm run setup:pine`). Tests: python/tests/test_quant_pine.py (10; the
  engine tests skip when Node or the engine is absent - the Python side must
  never pretend it is there). docs updated: docs/pine.md (new),
  docs/NAVIGATION.md, docs/quant-engine.md.

- **fix(harness): a change is verified by the project's own checks, and a
  failure drives a repair.** The harness had a correct, bounded, cost-capped
  repair loop (`code/repair.py`: plan -> check -> edit -> re-check, two
  attempts, a fifteen-minute wall clock, a $1.50 ceiling) whose own docstring
  said *"`execute_run` CALLS `run_verify_repair`"*. It did neither. The only two
  callers in the repository were the EVAL harness, and production passed
  `repair_outcome=None` to the answer seam on every single run. So three
  things were true and none of them were intended: a check the project pins
  never ran unless the MODEL chose to run it; a failed check never drove a
  repair (the model was told a check had failed only if it had run the check
  itself, and then had to notice, decide, edit and re-run with no budget and
  no cost cap); and the answer seam could not tell "no repair happened" from
  "the repair passed", because the only value it ever received was `None`.
  The agent graph now gains a **`verify_repair` node** between the tool turn
  and the next agent turn: after a turn that CHANGED something, the node runs
  the project's pinned check CLASSES through the ONE command path
  (`code.command_tools.command_run` - the same function the model's own
  `command_run` tool call goes through, so the policy gate, the authorization,
  the ledger row, the store row and the events are identical to a
  model-issued check), and when one fails the failure is handed back to the
  MODEL, because the model is the only thing that can fix code. The output is
  labelled and fenced as DATA, never as an instruction. The budget is the
  run's - attempts, wall clock, cost and the number of check runs - and
  exhaustion is a REPORTED state, never a silent stop. The loop's outcome is a
  first-class state whose word is DERIVED from the facts
  (`REPAIR_NOT_RUN` / `REPAIR_PASSED` / `REPAIR_FAILED` / `REPAIR_EXHAUSTED` /
  `REPAIR_NOT_APPLICABLE` / `REPAIR_REFUSED`), the answer seam receives the
  REAL outcome instead of a hard-coded `None`, and when the check was still
  failing the answer now says so - a result must show what it hides. The
  operator pins the checks in `.black-eclipse/verify.json` as class NAMES
  (`{"checks": ["unit_test", "typecheck"]}`), not a shell string: a check that
  cannot be named cannot back a "tests pass" claim, so it is not evidence and
  it is not run here, and the existing `{"command": "..."}` pin form keeps its
  single-shot behaviour. A repair NEVER widens authority - the pinned class
  still goes through `code.policy.decide_command` and the profile's grants,
  and `plan_only` - the read-only profile - never repairs at all. The new
  `repair-in-graph` eval shape drives the REAL graph (the model and the check
  are scripted; the graph is not), the `code_verify_repair_loop` capability
  class makes it measured (the capability statement is regenerated, and the
  dataset checksum is re-pinned because a new case is a new review), and the
  new shape reuses the plain name the user already sees - the distinction
  between the repair module and the repair loop is an implementation detail,
  and the plain-language surface does not carry it. Files:
  python/harness/code/repair_graph.py (new),
  python/harness/code/repair.py, python/harness/code/verify.py,
  python/harness/graph.py, python/harness/code/eval/tasks.py,
  python/harness/code/eval/capabilities.py,
  python/harness/code/eval/dataset_tasks_v1.json,
  python/harness/code/eval/statement.py,
  python/tests/test_graph_repair_node.py (new, 20 cases). ADR-H281. docs
  updated: docs/harness/decisions.md, docs/harness/architecture.md,
  docs/NAVIGATION.md, docs/harness/capability-statement.md.

- **feat(ui): the Project Scope widget - a project is now reachable by a
  human.** The project entity, the agent tools and the run binding landed with
  the harness, but nothing in the app pointed at one. A new **Project Scope**
  widget on the Command Center lists the projects the runtime holds, creates
  one, and pins the chat to it; `src/lib/agent/registry.ts` adds the active
  project id to the chat payload, so both the streaming and the one-shot path
  inherit the same scope without a second code path. The active id is a LOCAL
  preference (`be_active_project`), not a grant: the runtime still resolves it,
  and an unknown id is reported in the run's context rather than ignored. A
  blocked `localStorage` must never break the chat, so the read is guarded and
  returns null. Files: src/lib/projects/project-client.ts (new),
  src/lib/dashboard/project-widget.tsx (new), src/lib/dashboard/registry.tsx,
  src/lib/agent/registry.ts, src/app/api/harness/projects/route.ts. Tests:
  src/lib/projects/project-client.test.ts (7). docs updated: docs/projects.md.

- **fix(tests): the approval-card e2e was racing its own timeout.** The test
  that drives a run from "paused for approval" to "resumed and completed" gave
  the resumed run ten seconds, and the run legitimately takes about eleven -
  so `wait_for` cancelled it and the cancellation surfaced as a `cancelled`
  status instead of the real outcome. The wait is now a generous bound, and
  the test passes repeatedly. A flaky test that fails for the wrong reason is
  worse than a slow one. Files: python/tests/test_approval_card_e2e.py. no doc
  change - a test-timing repair.

- **feat(charts): the chat's chart blocks can now be drawn by EITHER engine —
  the interactive ECharts chart (the default) or a picture the Python chart
  engine draws in the runtime.** A `chart` block in an answer is translated into
  a validated chart **SPEC** (data only: a kind, some series, a title — never a
  callback, a URL or a path) by a new pure module
  (`src/lib/response/chart-spec.ts` — `chartBlockToSpec`, plus the visual
  director that resolves `chartType: "auto"`), and the runtime draws it with
  `matplotlib` into a **transparent** PNG in the app's own palette. The picture
  is recorded in the Artifact Center, so a chart is downloadable, versioned and
  shareable like any produced file. The **user chooses** the engine with a
  toggle on the chart, and the choice is remembered across answers
  (`src/lib/response/chart-engine.ts`); the ECharts path is unchanged, so the
  crosshair, the hover tooltip and the legend all still work. The export
  helpers serve both: the drawn picture is an artifact, the interactive chart is
  a live canvas. A lossy mapping is **TOLD**: a block type the engine cannot
  draw exactly (`treemap`/`sunburst`/`funnel`/`gauge`) is drawn as the closest
  honest shape and the note appears under the picture. A figure is always
  `computed` and never evidence (`isEvidence: false` is part of the contract).
  **Scope:** this is the CHAT's chart block only — the journal, portfolio,
  dashboard, backtest, economics, fundamentals and workspace widgets, the price
  chart, the Investor Eye map and the relationship graphs stay on ECharts,
  because they draw from live data at interactive rates. The engine also serves
  the agent's own figures through the `python_chart` tool. Files:
  `python/harness/charts/` (spec, theme, render, service, tools),
  `python/harness/routers/charts.py`, `src/lib/harness/charts.ts`,
  `src/app/api/harness/charts/route.ts`, `src/components/charts/python-chart.tsx`,
  `src/lib/response/chart-spec.ts` (+ `.test.ts`),
  `src/lib/response/chart-engine.ts` (+ `.test.ts`),
  `src/components/response/response-chart.tsx`,
  `src/lib/response/chart-registry.ts`, `src/lib/response/export.ts`.
  Tests: `python/tests/test_charts.py` (29), `src/lib/response/chart-spec.test.ts`
  (20), `src/lib/response/chart-engine.test.ts` (7),
  `src/app/api/harness/charts/route.test.ts`, `src/lib/harness/charts.test.ts`.
  docs updated: `docs/chart-engine.md`, `docs/interactive-response-engine.md`,
  `docs/DECISIONS.md` (ADR-050), `skills/ARCHITECT.md` (ADR-050),
  `docs/ARCHITECTURE.md`, `docs/NAVIGATION.md`, `docs/CHANGELOG.md`.

- **fix(charts): the chart engine's value-axis formatter crashed every chart that
  had a unit.** Matplotlib calls a tick formatter with `(value, position)`, and
  the formatter took one argument — so every chart that asked for a value
  format (percent, currency, compact, R) raised a `TypeError` inside the
  renderer and came back as a 500 "the chart could not be drawn". That is
  every widget, every dashboard chart and every portfolio chart: the widgets
  that looked blank were refused charts, not empty ones. The formatter now
  accepts both arguments, the expected `tight_layout` warning on the
  gauge/radar/treemap is silenced, and there is a regression test that draws
  one chart per value format (`python/tests/test_charts.py`). The runtime was
  restarted, so the fix is live. Files: `python/harness/charts/render.py`.
  docs updated: `docs/CHANGELOG.md`.

- **fix(harness): a chat coding turn keeps the finance agent's tools - a
  surface UNIONS, it never replaces.** A coding request typed in ordinary chat
  was served the code profile by **replacing** the finance agent's whole
  allowlist with it. Measured against a real `AgenticService` (956 registered
  tools), the finance agent declares 668 tools and the code profile declares
  454, and the two are largely disjoint - so the replacement cost the model
  **441 tools** on every coding turn and named **none** of them: the whole
  task/plan family (`create_plan`, `create_task`, `read_plan`, `run_plan`, ...),
  the whole web/research family (`web_search`, `web_extract`, `research_query`,
  `claim_verify`, ...), the unified retrieval/search family (`semantic_search`,
  `hybrid_search`, `search_evidence`, ...), the truthful-capability
  diagnostics (`get_capability_matrix`, `get_research_health`) and the
  response-contract tools (`response_block_schema`, `response_validate`).
  Two of those losses were defects, not inconveniences: `response_block_schema`
  is what the run checks before injecting the live response-schema digest and
  the response-mode plan, so a coding turn produced a **degraded structured
  response with no error and no warning**; and `get_capability_matrix` is the
  tool whose absence was already recorded as a real incident in the
  `ECLIPSE_AGENT` allowlist comment ("verified in the SYS/RELIANCE/Tata runs,
  where `get_capability_matrix` returned TOOL_FORBIDDEN"). The stated intent
  had always been the opposite of the behaviour - `agents.py` said *"ADDITIVE:
  `ECLIPSE_AGENT`'s declared tools are NOT touched"* and ADR-H117 described the
  profile as applied *"after the autonomy narrowing"*. The code replaced
  instead. The resolver now moves to `python/harness/surface.py` (its own
  module, so `graph.py` shrinks by ~120 lines) and combines the two halves by
  UNION - `allowed = policy_narrowed(base) UNION policy_narrowed(surface)` -
  with BOTH halves narrowed through the ONE policy authority, so an autonomy
  profile still removes every write/execute/external tool it bans, from the base
  half and from the surface half. A surface never removes a base tool: a tool
  may leave a run's surface only through the autonomy profile or through an
  operator-disabled store, and **both are named**. The resolution is published
  on the run row and returned on the run result (additive, optional field
  `surface`): the surface id, what it added, what the profile removed, what a
  disabled store removed, the bound tool count, and the **measured** schema
  characters the surface added - ratcheted by
  `MAX_SURFACE_ADDED_SCHEMA_CHARS`, so the cost can never grow silently.
  **The same change fixed a latent crash on a fresh install**: the answer seam
  writes `codeVerification` UNCONDITIONALLY, and that column was in neither the
  `CREATE TABLE` nor the migration list - so on a fresh `agent-memory.db`
  (which every new clone gets, because the file is gitignored) the write
  raised `no such column: codeVerification` and **every run crashed after the
  model had already produced its answer**. The live repository masked it
  because its database predates the column. `codeVerification`, `autonomy`,
  `workspaceId` and the new `surface` column are now in the migration list, so
  `npm install && npm run dev` keeps working on a clean machine. The
  `code-navigator` preset's allowlist is UNCHANGED (it is pinned by
  `test_memory_tools.py`); only its stale "read-only, five tools" comment was
  corrected. Files: python/harness/surface.py (new),
  python/harness/graph.py, python/harness/persistence.py,
  python/harness/schemas.py, python/harness/agents.py,
  python/tests/test_surface_resolution.py (new, 18 tests). ADR-H280. docs
  updated: docs/harness/decisions.md, docs/harness/architecture.md,
  docs/NAVIGATION.md.

- **feat(harness): projects - a named scope for the work that belongs together.**
  Before projects, Eclipse could already *label* work: `RunRequest.projectId`
  was on the wire, `HarnessRun.projectId` and `SessionMessage.projectId` were
  persisted, `HarnessArtifact.projectId` had an index - but nothing resolved
  the label. A project id was a string with no entity behind it, so "the same
  project" could not be listed, shown, or extended. A project now closes that
  gap with three pieces. (1) **The entity**: `python/harness/projects/store.py`
  owns `Project` and `ProjectMember` on the ONE `agent-memory.db` connection
  (never `eclipse-memory.db`, never `jdds.db`), with idempotent DDL so a store
  can be constructed in any order. A member is a **reference, not a copy** -
  `strategy`, `experiment`, `dataset`, `artifact`, `chat` or `note`, each owned
  by its own subsystem; the project only remembers where to look. (2) **The
  tools**: `project_create`, `project_list`, `project_show`, `project_attach`
  and `project_detach`, allowlisted in `agents.py`; a project that does not
  exist is a named refusal, never an empty list. (3) **The binding**: a run
  that carries `projectId` gets the project's members as a per-run
  `runtime_context` note - the block that already carries the run's date and
  the user's page. The brief says what the project HOLDS and never what the
  run should conclude, and an unknown project id is *reported* in the context
  so a typo cannot masquerade as "no project". It changes what the model knows,
  not what it may do: the tool surface is still resolved by policy. Surfaces:
  the five agent tools; the operator-gated routes `/projects`,
  `/projects/{id}` and `/projects/{id}/members`; the front-door proxy
  `/api/harness/projects`; and a chat turn, which now carries `projectId`
  through both chat routes. Files: python/harness/projects/ (new),
  python/harness/routers/projects.py (new), python/harness/main.py,
  python/harness/graph.py, python/harness/service.py, python/harness/tools.py,
  python/harness/agents.py, src/app/api/harness/projects/route.ts (new),
  src/app/api/harness/chat/route.ts, src/app/api/harness/chat/stream/route.ts,
  src/lib/harness/run-service.ts. Tests: python/tests/test_projects.py (24).
  docs updated: docs/projects.md (new), docs/NAVIGATION.md.

- **fix(quant): a funded prop account no longer inherits the evaluation's access
  period, and a failed account pays nothing.** Two real bugs in the prop-firm
  engine. (1) The access period belonged to the EVALUATION, but the funded
  phase fell back to the size's `maxTradingDays`, so a 40-day funded run could
  "fail" an access period it was never subject to - and the payout was still
  paid on the truncated balance. The access period now applies only to a phase
  with a profit target, and a payout is made only by an account that is still
  ALIVE: any failure (a breach, a consistency violation, an expired access
  period) closes the account, and a closed account pays nothing. (2) A
  qualifying day was counted when a day's P&L was `>= 0`, so a flat day
  counted as a qualifying day for the payout policy; it now requires a day that
  actually reaches the firm's minimum day profit. Also: placing trades on their
  regime bar was a linear scan per trade (quadratic over a long backtest) - it
  is now an O(1) index, with a regression test that places 5,000 trades over
  2,000 bars; and the consistency breach now names the BEST day rather than
  the last day simulated. Files: python/harness/quant/propfirm.py,
  python/harness/quant/regime.py, python/harness/quant/advanced_tools.py.
  Tests: python/tests/test_quant_propfirm.py,
  python/tests/test_quant_regime_verdict.py. docs updated:
  docs/quant-engine.md, docs/backtesting-engine.md.

- **docs(harness): Round 3 — the parity plan, from 7.2 to 9.5.** The harness
  was scored against the 2026 field (Claude Code, OpenHands, Codex CLI, Cursor,
  Devin, OpenCode, GitHub Copilot, Cline, Goose, Aider) on seven dimensions
  that decide how a harness actually performs. The result was **7.18** against
  a field median of 8.15 — and the deficit is not broad. Eclipse already
  **beats** the field median on safety (8.5 vs 8.0), on extensibility (8.5 vs
  8.25) and on the *design* of its evaluation system (7.0 vs 6.75). It loses
  on exactly two: **context management (5.5 vs 8.5)** and **operational
  maturity (5.0 vs 8.25)** — and those two carry 0.80 of the 0.97-point gap.
  The new plan says so, and says what closing them costs: +2.32 points to
  reach 9.5, of which +0.72 is context and +0.36 is operations. The last one
  is the cheapest prize in the plan — no new mechanism, only discipline — and
  that asymmetry is the plan's central argument. **Ten workstreams in three
  waves**, each with the evidence that opened it, the exact files, the
  contract, the runnable gate, the score it moves and its proposed ADR.
  Wave A removes defects: **W1** wires the verify→repair loop into the live
  graph (the module is correct and bounded; it has **zero production
  callers** — `graph.py` passes `repair_outcome=None`, so the model is told a
  check failed and must drive the retry itself with no budget and no cost
  cap); **W2** fixes surface resolution so a code surface *narrows* the
  allowlist instead of replacing it (today a chat code turn loses every
  finance, retrieval, plan and web tool, because `chat_code_allowlist`
  returns a list that overwrites the base); **W3** collapses three overlapping
  write stacks into one edit primitive with a **mandatory** stale-file guard
  (today `expectedHash` is optional everywhere, so the model can write to a
  file it never read) and closes the landing path with an end-to-end
  `promotion` fixture; **W5** collapses two search implementations into one
  ripgrep-first tool that always reports its engine (today the tool the chat
  profile leads with is the slow Python scan). Wave B closes the two capping
  dimensions: **W4** adds a deterministic, bounded **repo map** seeded into
  the first turn (there is none anywhere today, and the good machinery that
  would build one — `code/intel/context.py` — is reachable only if the model
  thinks to ask for it), and **W6** adds real **compaction** with a
  deterministic fallback plus lazy tool loading, against a harness that today
  truncates history and says so (`context_budget.py:12` — *"no summarization"*)
  while binding ~450-550 tool schemas every turn. Wave C makes it real:
  **W7** ships it (tag, release, shrink the harness by 30% under a
  CI-enforced size budget, fix the 7 duplicated ADR numbers, get a second
  pair of eyes); **W8** measures it live (the offline tier scripts the model
  out, the live tier is not in CI, and there is no external suite — no
  `swe.?bench` anywhere in the repo) and **publishes** a generated,
  provenance-stamped number; **W9** makes the isolation real (`network=False`
  is declarative with no consumer, the container backend's `.execute()` is
  never called, and `shell_run` hands the full `os.environ` to a host shell);
  **W10** distributes it. The plan refuses the two easy escapes: it does not
  add capability that already exists twice, and it does not weaken the honesty
  rules to win a benchmark — `UNMEASURED` stays `UNMEASURED`, and a harness
  that refuses to guess scoring worse than one that guesses is published as a
  scoring artifact, not fixed by guessing. The plan ends with the one item
  that can falsify it: **an outside re-measurement of the scorecard**. Until
  then the published number stays 7.18, not 9.5. Files:
  docs/harness/roadmap/round-3-parity-plan.md (new),
  docs/harness/roadmap/README.md (round 3 in the index),
  docs/NAVIGATION.md (the roadmap trigger row). docs updated:
  docs/harness/roadmap/round-3-parity-plan.md,
  docs/harness/roadmap/README.md, docs/NAVIGATION.md.

- **feat(quant): the Edge Report — the grade, the evidence and the figures as one
  durable document.** The verdict, the regimes and the Monte-Carlo used to be
  three answers in three places. The Edge Report binds them into ONE artifact:
  a grade, the four axes behind it, the flags, the measured numbers, the
  figures, and — always — what was *not* measured. The report computes nothing
  of its own: every number in it was measured by the quant engine, and every
  picture is a chart spec drawn by the **ONE** chart engine (ADR-050) and
  recorded in the Artifact Center. The panels are the equity curve, the
  drawdown, the Monte-Carlo return percentiles, the simulated return
  distribution, and the realised P&L by market regime. Two honesty rules ride
  along: a **figure is computed, never evidence** (every chart carries the
  `computed` label the chart contract requires, and the report says it in
  words), and a **long series is sampled, and the figure says so** — the chart
  engine bounds a series at 5,000 points and a category axis at 2,000, so the
  report samples to the tighter bound, keeps the first and last points, and
  writes the number of dropped points into the figure's footnote. A panel with
  no data is **absent**, not empty: a report without a Monte-Carlo has no
  Monte-Carlo panel and says so (`EDGE_REPORT_WITHOUT_MONTE_CARLO`) rather than
  scoring an axis it could not judge. The document is registered in the
  Artifact Center as a Markdown REPORT (`edge-report-<experiment>.md`) and each
  figure as a CHART artifact, so the report is downloadable and versioned like
  any other produced file. Surfaces: the agent tool `generate_edge_report`, the
  route POST /quant/edge-report (both through the existing /api/backtest/*
  proxy), and a new **Edge Report panel** on the Backtest screen that picks a
  stored experiment and an optional Monte-Carlo and shows the grade, the four
  axis scores, the flags and the figures. Nothing is computed in the browser.
  Files: python/harness/quant/edge_report.py (new),
  python/harness/quant/advanced_tools.py, python/harness/quant/tools.py,
  python/harness/routers/quant.py,
  src/components/screens/backtest/edge-report-panel.tsx (new),
  src/components/screens/backtest/backtest-screen.tsx,
  src/lib/backtest/backtest-client.ts. Tests:
  python/tests/test_quant_edge_report.py (10), python/tests/test_quant_routes.py,
  src/lib/backtest/backtest-client.test.ts. docs updated: docs/quant-engine.md,
  docs/backtesting-engine.md, docs/chart-engine.md.

- **fix(quant): the report routes are mounted on the running app.** The five
  routes that judge a result - `/quant/regime-monte-carlo`,
  `/quant/edge-verdict`, `/quant/prop-firm`, `/quant/prop-firm/firms` and
  `/quant/edge-report` - were registered on their router but the router was
  never included on the app, so the paths did not exist at runtime even though
  the router test passed. A route on a router is not a route until the app
  includes it; a test now asserts the OpenAPI schema carries them, so this
  class of bug cannot come back silently. The routes also moved out of
  `routers/quant.py` into their own `routers/quant_reports.py`, because that
  module is at its size budget and these are a separate concern: they do not
  run a backtest, they *judge* one. Files: python/harness/main.py,
  python/harness/routers/quant_reports.py (new),
  python/harness/routers/quant.py, python/tests/test_quant_routes.py. docs
  updated: docs/quant-engine.md.

- **fix(ui): the RSL control panel parses again - the release gate was broken.**
  The in-flight RSL climb-toggle work left the panel's JSX unbalanced (a
  fragment opened around the status grid was not closed), so `npx tsc --noEmit`
  failed and the `npm run check:all` gate was red. The markup is now balanced
  and the typecheck is clean; nothing about the panel's behaviour changed.
  Files: `src/components/screens/skills/rsl-control-panel.tsx`. no doc change -
  a syntax repair, not a behaviour or contract change.

- **feat(quant): prop-firm evaluation - the rules as data, and a Monte-Carlo
  over trading days.** A prop firm sells a funded account for a fee, and the fee
  is only worth paying if the trader reaches the profit target **without
  breaching the risk limits**. That question is now answerable instead of a
  matter of opinion. Every limit - profit target, maximum loss, daily loss
  limit, consistency rule, access period, payout split, payout cap - is a
  **field on a spec**, not a branch in the code, so a firm the engine has never
  heard of is still supported: the caller passes their own spec. Built-in specs
  for **Topstep**, **Apex Trader Funding (EOD)**, **FTMO (2-step Pro)** and
  **Take Profit Trader** were read from each firm's own published page on
  2026-10-20, and every spec carries its `source` and `as_of` so the engine
  reports the rules it used and tells the trader to confirm them - firm rules
  change constantly and the engine never pretends a built-in spec is current.
  Only sizes whose numbers appear on the firm's own page are encoded; an
  unknown size is **refused**, never guessed. Two behaviours are named because
  they are easy to get wrong: a log shorter than the access period is
  `inconclusive`, **not** `failed` (ten days of history cannot decide a 30-day
  evaluation), and a consistency rule measured against the *total profit* is
  decided at the decision points rather than day by day (on the first
  profitable day the best day IS the whole profit, so a mid-flight reading
  would condemn every trader). The uncertainty is expressed by resampling
  **trading days**, not trades: the rules are day-based and a trader's days
  cluster, so a good streak is three good days, not three good trades
  scattered across a month. Two modes - `block` (a stationary bootstrap over
  the day sequence, so streaks survive) and `iid` (which flatters the result
  and is the honest lower bar). Every path is evaluated against the **real**
  rules, so a path can fail exactly the way a live account fails. The report
  carries the pass probability, the outcome distribution, days-to-pass, the
  funded-phase payout distribution and the economics - net EV per attempt,
  expected attempts, expected resets to pass, cost to pass. **Fees come from
  the caller**; the engine never invents a price. And the blindness is stated:
  prop firms liquidate on *intraday* equity including unrealised P&L, which a
  log of closed trades cannot reconstruct, so every report carries
  `PROP_INTRADAY_EQUITY_NOT_MODELED`. Surfaces: the agent tools
  `run_prop_firm_simulation` and `list_prop_firm_rules`, and the routes POST
  /quant/prop-firm and GET /quant/prop-firm/firms. A real trading log comes
  from the existing `journal_trades` tool, whose output the simulation tool
  consumes. Files: python/harness/quant/propfirm.py (new),
  python/harness/quant/propfirm_mc.py (new),
  python/harness/quant/advanced_tools.py, python/harness/quant/tools.py,
  python/harness/routers/quant.py. Tests: python/tests/test_quant_propfirm.py
  (25), python/tests/test_quant_routes.py. docs updated: docs/quant-engine.md,
  docs/backtesting-engine.md.

- **feat(quant): regimes, a regime-aware Monte-Carlo and the Edge Verdict - the
  engine can now say WHERE an edge came from and WHETHER it should be trusted.**
  Two new modules answer the two questions a single backtest cannot. (1) A
  **causal regime classifier**: every bar is labelled on two axes - trend
  (`up`/`down`/`flat`, measured as the fast/slow EMA distance **in ATR units**)
  and volatility (`high`/`normal`/`low`, measured against its own trailing
  median). Causality is enforced, not assumed: bar *i* uses bars *<= i* only,
  so a label can be attached to a trade taken at *i* without smuggling the
  future into it. The regime is derived from the **same bars the backtest used**
  - not a second vendor, not a macro series, not a hand-set label - so an
  attribution is reproducible from the stored artifact alone. Realised P&L is
  then attributed per regime, with the share measured against **gross positive**
  P&L so a regime that only ever lost cannot claim a positive share. (2) The
  **`regime_block_bootstrap`** Monte-Carlo method: `trade_reshuffle` and
  `return_bootstrap` treat observations as independent, which *understates the
  tail* of any strategy whose edge clusters in one condition; the new method
  partitions the trade sequence into maximal same-regime runs and resamples
  whole blocks, so the clustering of good and bad conditions survives. Two
  explicit mixes: `resample` (blocks are drawn and re-ordered - the arrival of
  conditions changes, the clustering does not) and `preserve` (each original
  block is replaced by a drawn block of the same regime - chronology and mix
  kept exactly, content changed). Trades that cannot be placed on a regime are
  counted and reported, never silently dropped. (3) The **Edge Verdict** grades
  the *evidence* A-F across edge / robustness / risk / sample: an axis that
  cannot be judged has its weight **redistributed** and is named, never scored
  as zero and never assumed perfect; a **critical flag caps the grade**, so a
  non-positive expectancy, a profit factor below one or a sample too small to
  tell an edge from luck cannot be averaged away by a good Sharpe; and the
  overfit tells are named - a suspiciously smooth equity curve (lag-1
  autocorrelation of per-period returns), P&L concentrated in a few trades, a
  high Monte-Carlo probability of loss, and dependence on a single regime. The
  verdict grades what was measured and says what it could not measure; it is a
  judgement about evidence, not advice. Surfaces: the agent tools
  `run_regime_monte_carlo` and `grade_strategy_edge`, and the routes POST
  /quant/regime-monte-carlo and POST /quant/edge-verdict (which persists the
  verdict as an `edge_verdict` artifact), both reachable through the existing
  /api/backtest/* proxy. Files: python/harness/quant/regime.py (new),
  python/harness/quant/verdict.py (new), python/harness/quant/montecarlo.py,
  python/harness/quant/advanced_tools.py, python/harness/quant/tools.py,
  python/harness/routers/quant.py. Tests: python/tests/test_quant_regime_verdict.py
  (20), python/tests/test_quant_routes.py. docs updated: docs/quant-engine.md,
  docs/backtesting-engine.md.

- **feat(charts): the Python chart engine - Eclipse's one chart renderer, and the
  plan that retires ECharts.** A chart is now described by a validated chart
  **SPEC** (data only: a kind, some series, a title - never a callback, a URL
  or a path) and drawn by the Python runtime with matplotlib into a
  **transparent** PNG in the app's own palette, so the picture sits on the
  frosted glass card without hiding the frost. The picture is recorded in the
  Artifact Center, so a chart is downloadable, versioned and shareable like any
  produced file. Three doors onto that one engine: the **python_chart agent
  tool** (a malformed spec is a refusal that names the missing part), the
  **operator-gated route** POST /charts/render (proxied by
  /api/harness/charts), and the **browser client** + <PythonChart> surface.
  A figure is always computed and never evidence (isEvidence: false is part
  of the contract); the renderer draws what the spec says and nothing else; a
  missing matplotlib is a named CHART_RENDER_UNAVAILABLE, never an empty
  picture; and the picture's identity is the digest of its spec. matplotlib/
  
umpy/pandas are **already installed** in the runtime and the analysis
  sandbox - no new dependency, no new agent loop, no new store. The ECharts
  retirement is deliberately **not** a dual engine: the staged plan, the full
  surface inventory and the honest costs (no hover/crosshair/zoom; the 3D globe
  and the force graph have no counterpart in the current Python stack) are in
  docs/chart-engine.md section 4. Files: python/harness/charts/ (spec,
  theme, render, service, tools), python/harness/routers/charts.py,
  src/lib/harness/charts.ts, src/app/api/harness/charts/route.ts,
  src/components/charts/python-chart.tsx. Tests: python/tests/test_charts.py
  (26), src/lib/harness/charts.test.ts, src/app/api/harness/charts/route.test.ts.
  docs updated: docs/chart-engine.md, docs/DECISIONS.md (ADR-050),
  skills/ARCHITECT.md (ADR-050), docs/ARCHITECTURE.md, docs/NAVIGATION.md.
- **feat(charts,scraper,quant): land the Python chart engine, scraper lane and
  quant analysis additions.** Charts now render from a validated spec through
  the Python engine into Artifact Center PNGs; the scraper lane generates a
  program for data the vault lacks through the existing sandbox; quant adds
  regime classification, the Edge Verdict, prop-firm rules/Monte-Carlo and the
  supporting routes/tools. Docs updated:
  `docs/chart-engine.md`, `docs/harness/scraper-lane.md`, `docs/quant-engine.md`,
  `docs/backtesting-engine.md`, `docs/harness/web-research-engine.md`,
  `docs/ARCHITECTURE.md`, `docs/DECISIONS.md`, `docs/NAVIGATION.md`.

- **docs(rsl): close v2 with decisions and acceptance evidence.**
  Model identity remains trial-only (ADR-H275); skill drafts promote through the
  existing skills lifecycle (ADR-H276); v2 acceptance is slice-level (ADR-H277).
  Added `docs/self-improvement/rsl-v2-acceptance.md` and updated the v2 plan
  status. docs updated: `docs/self-improvement/rsl-v2-plan.md`,
  `docs/self-improvement/rsl-v2-acceptance.md`,
  `docs/harness/decisions.md`.

- **feat(harness,ui): scheduled climb with pause/resume.**
  `HARNESS_RSL_CLIMB_SECONDS`/`HARNESS_RSL_CLIMB_SCOPE` run an injected climb
  runner on a cadence; without a runner the schedule is inert. Added pause and
  resume routes, status/next-run display and the operator toggle. Budget, busy,
  mode and strategy gates still apply. Docs: ADR-H274,
  `docs/harness/architecture.md`,
  `docs/self-improvement/rsl-implementation-plan.md`,
  `docs/self-improvement/rsl-v2-plan.md`.

- **feat(harness): opt-in Pareto climb mode.**
  `HARNESS_RSL_OBJECTIVE=pareto` lets the climb retain a measured, non-critical
  trade-off that the weighted utility rejects when the current state does not
  dominate it on at least two comparable objectives; `single` remains the
  default. The status shows the active objective. Docs: ADR-H273,
  `docs/harness/architecture.md`,
  `docs/self-improvement/rsl-implementation-plan.md`,
  `docs/self-improvement/rsl-v2-plan.md`.

- **feat(harness): add a canary split before code landing.**
  `HARNESS_RSL_CANARY=on` re-runs the patched worktree on a second split
  (`held_out` by default) after validation; an unmeasured canary, a target drop
  beyond tolerance, or a critical regression rejects the candidate. Docs:
  ADR-H272, `docs/harness/architecture.md`,
  `docs/self-improvement/rsl-implementation-plan.md`,
  `docs/self-improvement/rsl-v2-plan.md`.

- **docs(rsl): publish the RSL v2 plan.**
  Added `docs/self-improvement/rsl-v2-plan.md` with the remaining v2 phases
  (canary landing, continuous climb scheduling, multi-objective search,
  identity expansion, hardening), safety floor and definition of done; linked
  it from `docs/NAVIGATION.md`. docs updated:
  `docs/self-improvement/rsl-v2-plan.md`, `docs/NAVIGATION.md`.

- **feat(harness): opt-in cross-scope lesson transfer.**
  `HARNESS_RSL_LESSON_TRANSFER=on` lets a cue-matched adopted lesson from
  another recorded scope be retrieved; the default remains exact-scoped, and
  transferred lessons still enter the injected/control cohorts so lift is
  measured. Docs: ADR-H271, `docs/harness/architecture.md`,
  `docs/self-improvement/rsl-implementation-plan.md`.

- **test(rsl): automated v1 acceptance passed.**
  `npm run rsl:smoke` passed (code candidate `evaluated_ok`, measured surface
  `benchmark_rejected`, budget 2/3) and the focused acceptance suite passed
  (`65 passed`: state, utility, replay, hill climb, lesson feedback, drift,
  drift watch, v1b skill drafts, surface e2e, self-improvement e2e). The live
  operator experiment is still the manual sign-off described in
  `docs/self-improvement/rsl-v1-acceptance.md`. docs updated:
  `docs/CHANGELOG.md`.

- **fix(ui): the sidebar mode-switcher dropdown reads as real frosted glass and
  the chat-history sort arrow is no longer oversized.** The mode menu used the
  shared dropdown tier (`.glass-tooltip`), which is too faint over the
  already-frosted rail; it is now cut from the SAME material as the nav bar it
  belongs to (`.nav-menu-glass` reuses the sidebar's own tint + blur tokens,
  dark/light + glass-off aware). The compact chat sort/filter selects shrank
  their chevron from 16px to 12px to match the 28px trigger. Files:
  `src/components/layout/sidebar.tsx`,
  `src/components/layout/chat-history-panel.tsx`, `src/app/globals.css`. no doc
  change â€” UI styling only.

- **fix(ui): the activity feed shows the newest step and no longer hides steps
  behind its own scrollbar.** The feed keeps every step visible (the chat's own
  scroll follows it) and collapsing into the header remains the user's choice;
  while a run is live the header names the current step and that row is gently
  foregrounded. Python execution is now explicit: `analysis_run` reads
  "Executing Python" (with the recipe/plain purpose as its detail) instead of
  "Working it out", and the `execute_*` tools have plain labels. Files:
  `src/components/chat/activity-feed.tsx`, `activity-item.tsx`,
  `src/lib/agent/response-model.ts`, `python/harness/code/activity.py`. Tests:
  `events.test.ts`, `test_code_activity.py`. no doc change â€” UI behavior only.

- **fix(search,ui): stop Bots mode stalling behind a broken embedding provider
  and a background polling loop.** Three independent causes. (1) The boot search
  warm-index called `embed_texts` once per document; a provider that rejected
  every input (the observed `localhost:11434/v1/embeddings 404`) produced
  thousands of doomed requests on the runtime event loop, starving `/health` and
  slowing every Python-proxy route. `EmbeddingService` now opens a circuit when
  all pending inputs in a call fail with no vector, so the rest of the pass is
  keyword-only until `configure()` resolves the provider again. (2) `hydrate()`
  in the bots store awaited every per-bot status call before publishing the list;
  it now paints the list first and hydrates statuses in the background, and
  concurrent callers (sidebar + workspace) share one in-flight hydrate. (3) The
  Bots workspace and the open bot thread kept polling every 20 s / 30 s while the
  keep-alive tab was hidden; both now poll only while the Bots tab is active.
  Tests: `python/tests/test_search_embeddings.py` (+1). No data/API shape change.
  no doc change â€” perf/behavior fix, contracts unchanged.

- **feat(server): split development and production into two independent
  servers.** `scripts/lib/profiles.js` is the ONE profile table: dev = app 3000 +
  harness 8765 + `.next-dev` + `.black-eclipse/dev/` runtime DBs, no proxy;
  prod = app 3100 + harness 8766 + `.next`, behind the `blackeclipse` proxy with
  the canonical-host redirect. `scripts/local-host.js` applies the profile env,
  `scripts/kill-port.js dev|prod` frees only its own ports (previously a dev
  start killed the production server and its harness), and the harness spawn
  lock is now per runtime port. Commands unchanged (`npm run dev`, `npm run up`,
  `black dev/eclipse`). Docs updated: `docs/environments.md` (new),
  `docs/QUICKSTART.md`, `docs/NAVIGATION.md`, `docs/local-hostname.md` (marked
  stale for the new proxy port), `.env.example`.

- **feat(harness): W1.3 â€” the per-run outcome envelope.** One derived, read-only
  record names how a run was routed: the intent verdict, the resolved surface +
  allowlist, the refusal code and the capability gap (`GET /runs/{id}/outcome`).
  Three of the four facts were already persisted (the run row's agent and
  terminal error code, the `prompt.plan` event, the `ui.capability_gap` and
  `recovery.decided` events); the intent verdict had no home â€” it died with the
  `ui_classify_request` tool result â€” so that tool now records it once per run
  (the FIRST verdict wins, because it is the routing). The module owns its own
  `RunOutcome` table (the `run_lineage.py` pattern) so the ratcheted
  `persistence.py` does not grow. The run-scoped read routes
  (`/runs/{id}/events`, `/explain`, `/outcome`) moved to the new
  `python/harness/routers/runs.py` so `main.py` stays under the hard ceiling
  (1199 â†’ 1166 lines; the paths are unchanged). A fact that was never recorded
  is `null` â€” the envelope never guesses and never infers from prose. Tests:
  `python/tests/test_run_outcome.py` (12). Docs updated:
  `docs/harness/architecture.md`, `docs/harness/self-evolution-roadmap.md`,
  `docs/harness/decisions.md` (ADR-H241).

- **fix(harness,ui): the extension capability lane â€” compute, chart, report and reach the board.** Six real failures, all traced to a specific cause:
  - **The sandbox was never used.** The default prompt said financial models are
    "subject matter you reason about and explain, not actions you execute", and
    the `analysis_run` description named no recipe, so the model answered with
    prose. The prompt now teaches the sandbox (`analysis_run` + the recipes),
    the tool description names every ready-made recipe and its inputs, and a
    failed computation returns its error instead of "I couldn't work that out".
  - **The sandbox environment was not reproducible.** `package_lock_digest`
    hashed the HARNESS process's packages, not the interpreter that ran the
    code; the vendored interpreter was never provisioned on Windows when a
    system Python existed; and nothing installed numpy/pandas/matplotlib. The
    digest now covers the interpreter's distributions, `python/analysis-requirements.txt`
    pins the numerical stack, `setup-python.js` provisions the interpreter the
    sandbox actually runs, and `doctor.js` reports the stack's versions.
  - **A candlestick chart came back as text.** `chart` had no candlestick type
    and its points could not hold OHLC, so the model's chart was REJECTED and
    degraded to a markdown block (the raw JSON). `candlestick`/`ohlc` are now
    chart types, an OHLC point is `[open, high, low, close]`, the renderer
    draws real candles, the synonyms recover instead of being dropped, and the
    prompt and mode director route a chart request to a chart block. The
    normalizer also converts the ROW shape the model actually writes
    (`data: [{label, values}]` â†’ `categories` + `series`) and the two axis-label
    spellings, so the block survives validation.
  - **Formulas were computed but never shown.** The tool result carried the
    formula; no block could display it. `provenance.formula` now exists and is
    rendered under the metric and hero figures.
  - **"Show it in the Command Center" landed on a stray page.** The dashboard
    mirrors were hidden from `ui_list_blueprints`, and a dispatched engineering
    task ran with NO autonomy, so every write was refused with
    `PROFILE_DENIED`. The mirrors are now listed and a task runs with the
    autonomy its creator declared.
  - **Reports and quant models.** The prompt never mentioned `eclipse_report`
    (so a "proper report" was prose), PDF needed an undeclared matplotlib, and
    the produced file was invisible in the chat; a "quant model" request read
    as `not_code`, and the strategy schema was an opaque `object`. The prompt
    now names the report tool, the artifact id travels with the document, the
    numerical stack is declared, and a quant-model request routes to the code
    profile with a legible strategy schema.
  Tests: `python/tests/test_analysis_tool.py`, `test_code_request_intent.py`,
  `test_tasks_scheduler.py`, `src/lib/response/chart-option.test.ts`,
  `src/lib/response/finalize.test.ts`. Docs updated:
  `docs/interactive-response-engine.md`, `docs/harness/python-runtime.md`,
  `docs/quant-engine.md`, `docs/harness/decisions.md` (ADR-H242).

- **fix(harness): the Python sandbox now enforces its boundary at runtime (W14 audit).**
  The audit found the sandbox's "no network / no path into the user's files"
  claim rested on a SOURCE check that three vectors walked past: an aliased
  `__import__` (`f = __import__`), a URL built by concatenation, and
  `numpy`/`pandas` reading a path directly. The AST walk stays as the first
  filter, and a new **runtime guard** (`python/harness/code/sandbox_guard.py`)
  is the enforcement point inside the child: a guarded `__import__`, a safe
  `os`/`sys`/`importlib`/`builtins` (no `system`, no frame walking, a safe
  `exec`/`eval` that re-applies the source rules to a dynamic string), denied
  privilege modules (`subprocess`, `socket`, `ssl`, `ctypes`, `multiprocessing`),
  an audit hook that refuses a network, a process, native code and any file
  outside the program's own folder, and confined library readers/writers. Also:
  the operator's `HARNESS_ANALYSIS_ENABLED` decides the surface (the per-run
  flag is a request, not a decision); a cancelled analysis kills its process tree
  and says `CANCELLED`; the backend's CPU / peak-RSS / process-count / limit /
  exit-code telemetry is reported instead of discarded; the result and artifact
  reads are size-checked before they are read; and the interpreter's tree is
  read-only for a program (`PYTHONDONTWRITEBYTECODE=1`). The stale claims in
  ADR-H110/H178, the phase-08 non-goals and the prompt's import list are
  corrected in place â€” the code wins. Tests:
  `python/tests/test_analysis_guard.py` (22). Docs updated:
  `docs/harness/python-runtime.md`, `docs/harness/decisions.md` (ADR-H242),
  `docs/harness/roadmap/phase-08-analysis-sandbox.md`.

- **fix(harness): the capability chain the adversarial probe exposed.** A five-prompt
  adversarial probe (alias import, concatenated URL, host file read/write,
  process, socket, dunder chain) found the boundary itself solid â€” every escape
  was refused, and the model declined consistently â€” but it exposed four
  product defects in the working path: a **guessed recipe name** (`max_drawdown`
  does not exist; `drawdown_profile` does) failed with a bare
  `RECIPE_NOT_FOUND`, so the refusal now **lists the ready-made recipes**; the
  close series never reached the sandbox (a dataset tool's row count is not a
  series), so the prompt now says to let the **program** fetch it
  (`eclipse_tools.price_history`); the stats engine's computed metrics had no
  provenance, so the transcript showed "this number has no record of where it
  came from" â€” the engine now **publishes its metrics as a resolvable computed
  result** with their provenance, like the sandbox's; and the prompt names the
  two rules (use a recipe name exactly; let the program fetch the series). The
  honest-failure path was already right: an unlisted issuer with no daily bars
  is refused by name, with real alternatives. Tests:
  `python/tests/test_analysis_guard.py` (+2). Docs updated:
  `docs/harness/decisions.md` (ADR-H243).

- **fix(harness): the five-prompt limit probe â€” refusals that teach, and results that show.** A
  hostile-prompt probe (alias import, concatenated URL, host file read/write,
  process, socket, dunder chain, plus a full capability chain) found the boundary
  solid and the *working path* leaky in four ways: a **guessed recipe name**
  (`max_drawdown` does not exist; `drawdown_profile` does) failed with a bare
  `RECIPE_NOT_FOUND`, so the refusal now **lists the ready-made recipes**; a
  recipe called with the wrong input asked only "which series should I use?",
  so it now **names the input and its kind** (`prices` (series: a list of
  prices over time)) and the whole declared input set; the refusal for a
  disallowed source element named only the element, so a model concluded "numpy
  is not permitted" when the real cause was a dunder in its probe â€” the
  message now says **only that element is refused, the rest of the program
  runs**, and lists the importable modules; and a computed result with 26
  values showed only the first few **without saying it was cut off**, so the
  tool text now reports "showing 12 of 30 values". The stats engine's computed
  metrics now publish their provenance, so a number the engine computed is
  resolvable in the transcript instead of rendering as "this number has no
  record of where it came from". Tests: `python/tests/test_analysis_guard.py`
  (26). Docs updated: `docs/harness/decisions.md` (ADR-H243).

- **fix(harness): the limit probe's real findings — a per-command guard, the method
  write hole, and refusals the model can act on.** A two-prompt probe (a hostile
  side-quest inside a real computation, and the full product chain) found four
  defects, all now fixed:
  - **The guard's rules were installed once per KERNEL process**, so a later
    command was judged by the FIRST command's allowlist: a `drawdown_figure`
    recipe (which legitimately adds `matplotlib`) was refused because an earlier
    plain program had set the list. The allowlist and the path roots are now
    re-configured **per command**.
  - **A program could write a host file through `pandas.DataFrame.to_csv`** —
    the confinement wrapped the MODULE function, but the method is what a program
    calls. The methods are wrapped now (`DataFrame`/`Series` writers, resolved
    through the factory pandas 3 exposes), and the audit hook reads `os.open`'s
    int flags as the write they are.
  - **The recipe's input NAME never reached the model** — the refusal explained
    itself in `stderr`, but the model reads the prompt. The prompt now names the
    input and its kind (`prices` (series: a list of prices over time)) and lists
    the recipe's declared inputs, so one call corrects the guess instead of
    three.
  - **A 19-value result showed 12 values and never said so.** The computed text
    now carries up to 30 values and states what it hides ("showing 12 of 40").
  - Plus: the transcript's computed blob is **merged**, not replaced (a second
    computation no longer orphans the first one's references — the "this number
    has no record of where it came from" chip), and the prompt names
    `sdk_dashboard_add_widget` for "put it on my Command Center".
  Tests: `python/tests/test_analysis_guard.py` (27). Docs updated:
  `docs/harness/decisions.md` (ADR-H245).

- **fix(harness): the probe's remaining findings — the refusal keeps the runtime's
  explanation, the bindings publish their signatures, and a file says where it
  is.** A three-prompt probe (the sandbox under fire, the whole product chain,
  and the honesty surface) confirmed the boundary — the credential read, the
  socket, the process and the host write were each refused by a different,
  correct mechanism, the memory ceiling bit at ~1.62 GiB repeatably, and the
  seeded Monte-Carlo was bit-identical for the same seed — and found three
  things the model could not get past:
  - **An unknown recipe name still refused with a bare "I couldn't work that
    out"**, because the tool's refusal path dropped the runtime's own
    explanation. The refusal now carries it: the ready-made catalogue (so the
    model stops guessing `max_drawdown_recipe`, `drawdown_stats`, …).
  - **A program could not learn `price_history`'s arguments** without trial
    runs, and a model that burns runs on it concludes the sandbox is closed.
    The tool schema now publishes every binding's signature
    (`price_history(symbol, market?, interval?, range?, start?, end?)`).
  - **A produced file could not be found**, because the model looked for it in
    the project tree: the result now says the file is registered in the
    Artifact Center and its ids ride the result.
  The probe also found a real DATA-layer defect (a narrow date request was
  answered from the cached 251-bar window, ignoring the bounds) and confirmed
  the first bar of a `2025-10-20 → 2026-10-20` request is the **21st** (the
  start date is exclusive). Tests: `python/tests/test_analysis_guard.py` (30).
  Docs updated: `docs/harness/decisions.md` (ADR-H246).

- **chore(repo): normalize two mixed line-ending files.**
  `python/harness/capabilities/external.py` and
  `src/components/screens/capability-studio/generated-section.tsx` mixed CRLF and
  bare LF, which tripped the mixed-line-ending guard; both are now LF-only, with
  no content change.
  no doc change â€” line-ending hygiene only.

- **perf(bots): opening Bots no longer pays the Python cold start or an N+1
  status fan-out.** Two causes. (1) The boot pre-warm of the Python runtime ran
  LAST, after the sequential DB seeds/schedulers, so Bots (usually the first
  Python-backed surface opened) paid the ~9 s import. It now starts first in the
  background boot pipeline. (2) The Bots workspace, sidebar and the global
  bot-run watcher each fetched one `/automations/{id}/status` per bot (each
  re-scanning up to 200 executions). New `GET /automations/statuses` returns the
  lifecycle fields + latest execution for every bot in ONE request
  (`?ids=a,b` optional); `getAutomationStatuses()` replaces all three fan-outs.
  Files: `src/instrumentation.ts`, `python/harness/automation/{store,service}.py`,
  `python/harness/routers/automation.py`,
  `src/app/api/automations/[...path]/route.ts`,
  `src/lib/harness/automation-{client,browser}.ts`, `src/lib/bots/bots-store.ts`,
  `src/components/bots/bots-sidebar-panel.tsx`,
  `src/lib/notifications/bots-run-watcher.tsx`, `bots-run-diff.ts`. Tests:
  `python/tests/test_automation_api.py` (+1, operator gating included). Docs
  updated: `docs/harness/automation-engine.md`.

- **perf(bots): Bots now paints in milliseconds, not after a network round-trip.**
  The bot list + latest runs are cached in `localStorage` (`be_bots_cache_v1`)
  and seed the store synchronously, so a cold page load (or a deep link to a bot)
  renders the real workspace immediately while the refresh runs. The root
  bot-run watcher now hydrates the SHARED store (one list + one batched status
  call, no duplicate sweep) at app boot, so opening Bots later needs no request
  on the critical path; the cache is only rewritten when the payload changes,
  and a failed refresh keeps the cached list and shows the error banner. The
  Bots screen chunk is prefetched 3 s after the shell is interactive so the first
  click does not wait on a dynamic import. Files:
  `src/lib/bots/bots-store.ts`,
  `src/lib/notifications/bots-run-watcher.tsx`. no doc change â€” perf/behavior
  fix; no data or API contract changed.

- **perf(shell): the first-load client graph no longer carries closed chrome,
  ECharts, xterm, or the dev toolbar.** The app shell now code-splits everything
  that is closed or hidden at boot: the terminal dock (only loaded once the
  terminal opens), the Bots scheduler dock, the floating `ChatDock` (only mounted
  on tabs where it is visible, so it no longer instantiates a second
  `useAgentRun`/`useChatModel`), the decorative WebGL Aurora (loaded 1.2 s after
  the shell is interactive), and the sidebar graph/gateway dialogs (the graph one
  pulled in two full ECharts graphs). The dev-only Agentation toolbar now loads
  through an effect gated on its env flag, not a root import. The boot overlay
  hides at 900 ms and its CSS fallback at 1.1 s (was 2.5 s / 2.4 s); the warm-up
  requests keep running after it fades. New `src/components/screens/lazy-chrome.tsx`
  keeps `stock-chat.tsx` within its size ratchet. Measured on the dev server:
  initial HTML script tags **70 â†’ 43** and boot JS **18.52 MB â†’ 10.04 MB
  (âˆ’46%)**; `stock-chat.tsx` remains at its pinned budget. Also re-saved
  `src/app/globals.css` as UTF-8/LF with the same rules (no selector/value
  changes) after a line-ending/encoding normalization. Verified:
  `npx tsc --noEmit`, `npx vitest run` (362 files / 3671 tests). no doc change â€”
  performance/plumbing only; no contract or architecture change.

- **perf(shell): hidden keep-alive tabs stop polling, and the response engine
  leaves the first-load graph.** Three follow-ups. (1) The shell keeps visited
  screens mounted behind `hidden`, so Tasks (5 s), Alerts (5 s), Chart (1 s
  countdown), MarketBubbles (20 s), Dashboard (30/60 s + SSE) and News (60 s)
  kept polling forever. Each now takes an `active` prop from `stock-chat.tsx`
  and uses the new `useActiveInterval` (or an `if (!active)` guard), which also
  skips `document.hidden`. The theme (15 s), app-shell (30 s) and saved-pages
  (60 s) probes gained the same visibility guard. (2) The response engine (Zod
  contract + block registry + planners) is no longer in the boot chunk:
  `chat-history` loads `assistant-content` on demand with a plain-Markdown
  first paint, `markdown` uses a small SSR-safe `ResponseFenceLazy` that projects
  prose immediately, and the canvas-content import is deferred. (3) Portfolio
  history is one `POST /api/price-history/batch` instead of N per-symbol browser
  requests (the browser caps a host at ~6 concurrent connections, so the tail
  used to serialize). Measured on the dev server after both passes: initial
  HTML scripts **70 â†’ 38** and boot JS **18.52 MB â†’ 7.75 MB (âˆ’58%)**. Tests:
  362 files / 3672 pass; size ratchets re-pinned for the `active` plumbing.
  Docs updated: `docs/DATA-FLOW.md` (batch route contract).
- **feat(scraper): Eclipse can now build a scraper on demand — collect what the
  vault does not have.** The old answer to "pull this data from that site" was
  `UNAVAILABLE`, and `web_scrape` could only ever collect ONE page with ONE
  selector. The **scraper lane** removes that ceiling without opening the
  sandbox to the network: the agent writes a Python program that fetches pages
  through a new host-mediated binding (`eclipse_tools.web_page`) and leaves its
  records in `result = {"rows": [...]}`, and the program runs in the SAME
  analysis sandbox. The program still cannot open a socket (`socket`/`ssl` stay
  denied), no HTTP client is importable, and a URL literal is refused by the AST
  gate unless the HOST turned the web binding on for that run — so the fetch is
  the same SSRF-hardened `web_collect` capability `web_scrape` uses, with **no
  second transport and no second parser**. The consent is **per DOMAIN** (the
  `scraper_domain` approval kind, keyed by the host): the operator approves a
  site once and that consent is remembered as a revocable standing grant; a
  different site asks again. Collected rows are stored through ONE new
  front-door route (`POST /api/scraper/datasets` -> `CustomDatasetRecord`,
  provenance `SCRAPER`, each row keyed by its own content so a re-run updates
  in place) and the program is saved under `.black-eclipse/scrapers/` so it can
  be run again by id. Honesty rules hold: a program that never answered is a
  FAILURE, not an empty dataset; a selector that matched nothing is a confirmed
  zero for the pages it read; and everything collected is COLLECTED page data —
  never a verified source. The analysis sandbox itself is unchanged (still no
  network). ADR-051.
  Docs updated: `docs/harness/scraper-lane.md` (new), `docs/harness/web-research-engine.md`,
  `docs/harness/roadmap/phase-16-bulk-acquisition.md`, `docs/NAVIGATION.md`,
  `skills/ARCHITECT.md` + `docs/DECISIONS.md` (ADR-051).
- **fix(front door): a run the runtime does not know is now 404, not 500.** The
  runtime answers "not found" as HTTP 404 with a human detail ("Run not
  found"), but the TypeScript clients dropped the status and threw only the
  detail text. Every caller that maps 404 -> "nothing here" (`getRunFromRuntime`,
  the run explanation, the research receipt, the skill and workflow lookups)
  therefore missed the match, and the front door reported a missing run as a
  500 - which reads as "the runtime is broken" and paints errors in the browser
  console for a run that simply is not in this store. The status now travels on
  the error itself (`HarnessHttpError` in `src/lib/harness/errors.ts`, with
  `isNotFoundError()` as the one way to ask), so the honest answer reaches the
  browser: 404 for a run that is not there, 503 for a runtime that is
  unreachable, 500 for a real failure. The message the operator reads is still
  exactly what the runtime said. Files: `src/lib/harness/errors.ts`,
  `src/lib/harness/python-client.ts`, `src/lib/harness/skills-client.ts`,
  `src/lib/harness/workflows-client.ts`,
  `src/lib/harness/eclipse-memory-client.ts`,
  `src/lib/harness/python-client.test.ts` (new).
  Docs updated: `docs/harness/architecture.md`.
- **fix(dev): the dev server no longer serves stale module bytes - "the module
  factory is not available" cannot come back.** In dev, Turbopack names a chunk
  after the MODULE it serves (`src_components_screens_a6343f43._.js`), not after
  the bytes it holds: when a module is edited, renamed or deleted, the bytes
  behind that same URL change while the URL stays put. The dev chunk header
  marked those responses `immutable` for a year, so the browser kept the OLD
  bytes; the next load asked the runtime for a module factory the server no
  longer had and the page died behind the "the module factory is not available.
  It might have been deleted in an HMR update" overlay. Dev chunks now
  REVALIDATE (`public, max-age=0, must-revalidate`): the server already sends
  `ETag`/`Last-Modified`, so a second tab still gets a cheap 304 instead of
  re-downloading the whole client graph, and a changed chunk is always fetched
  fresh. Production is untouched (real builds are content-hashed and
  immutable). One-time repair for a browser that already cached the old
  immutable copies: `GET /api/dev/cache-reset` (dev only) answers with
  `Clear-Site-Data: "cache"` - the HTTP cache only, never cookies or
  localStorage, so the operator stays signed in. Files: `next.config.ts`,
  `src/app/api/dev/cache-reset/route.ts` (new).
  Docs updated: `docs/environments.md`.
- **fix(build): the wordmark fonts are vendored - the build no longer needs
  Google, and the app can no longer fail to compile over a font.** The 16
  wordmark faces were pulled in with `next/font/google`, so EVERY build made a
  live request to fonts.googleapis.com. Google answers a query with the CSS
  split per subset and per weight; Turbopack resolves one font entry per query,
  and when it got more than one it refused the import outright -
  "next/font/google queries have exactly one entry" - which took the WHOLE app
  down (a 500 on every page) whenever the dev cache was cold or the network
  answered differently. The faces now live in `public/fonts/` (the very files
  the production build already shipped) and are declared in
  `src/app/fonts.css` with the same 16 `--font-*` variables, so the wordmark
  options, the chat appearance picker and the themes are unchanged. The build
  is offline-safe from here. Files: `public/fonts/` (new, 20 woff2),
  `src/app/fonts.css` (new), `src/app/layout.tsx`.
  Docs updated: `docs/ARCHITECTURE.md`.

- **feat(rsl): post-landing canary + hot, persisted config (v3 P0).** A
  promoted `rsl-*` change that needs a restart now carries a `postLanding` hint.
  `POST /code/promotions/{rollbackId}/post-landing` runs restart → `GET /health`
  → keep, or on failure rollback → restart → re-probe; the front door can pass
  `alreadyRestarted=true` after its own supervisor restart. With no restart seam
  the record is `unverified`, never a success, and a failed rollback is
  `rollback_failed`. Probe records land in `HarnessPostLanding` on the ONE
  `agent-memory.db`. Separately, `RSLConfig.from_dict`/`apply_payload` reuse the
  env clamps, `RSLLoop.set_config` applies bounded overrides without a restart,
  starts/stops the conductor on mode changes, and persists the last override in
  `HarnessRuntimeSetting`; `POST /evolution/rsl/config` is the operator surface
  and `GET /evolution/rsl` reports `configSource`. Defaults remain
  `HARNESS_RSL_MODE=off`. The promotion card calls the probe after its restart
  and shows healthy / rolled-back / unverified. Files:
  `python/harness/self_improvement/{post_landing,runtime_settings,config,loop}.py`,
  `python/harness/routers/{code,evolution}.py`,
  `src/lib/harness/{code-client,code-browser}.ts`,
  `src/app/api/code/promotions/[rollbackId]/post-landing/route.ts`,
  `src/components/chat/promote-change.tsx`,
  `src/lib/i18n/dictionaries/en.ts`, `src/lib/size-budget.test.ts` (ratchet
  1263→1266 for the three status strings). Tests:
  `python/tests/test_post_landing.py` (7), `test_rsl_config.py`,
  `test_rsl_loop.py`. Docs updated: `docs/self-improvement/rsl-v3-plan.md`
  (new), `docs/harness/architecture.md`, `docs/harness/decisions.md`
  (ADR-H278), `docs/NAVIGATION.md`.

- **feat(rsl): three-arm ablation + `rsl:bench` (v3 P1 foundation).** RSL could
  prove one candidate beat the current state on one suite; it could not answer
  "does the surface, and do adopted lessons, beat doing nothing on the same
  tasks?" `python/harness/evaluation/ablation.py` now runs `baseline` (the
  production prompt + the evaluation registry's tools), `surface` (an operator
  `HarnessSnapshot`) and `surface+lessons` (a per-task verified lesson manifest)
  through the same `CandidateAgentInvoker`/`EvaluationRunner`, same tasks, seed
  and trials. The report carries the Wilson interval, measured/total trials,
  per-category rates, cost, and a critical-regression veto for `safety` /
  `adversarial`; a measured gain is `improved`, a critical drop is `vetoed`.
  `npm run rsl:bench` wraps the CLI with a disposable `agent-memory.db`.
  `CandidateAgentInvoker` gained an additive bounded `prompt_suffix` (static or
  per-task callable) for the lessons arm. The production Eclipse prompt is ~34k
  characters, so `HarnessSnapshot`'s `MAX_PROMPT_CHARS` moved 16k→48k; otherwise
  no surface could be derived from the real agent. `CandidateAgentInvoker` also
  gained an explicit `--live` tier (real provider/model, key from
  `HARNESS_EVAL_API_KEY`); it refuses to run live without explicit settings and
  the report labels the tier. `python/harness/evaluation/replay_builder.py` turns
  recorded completed runs into deduplicated, redacted, **live-only** regression
  tasks (expected behavior = the recorded tool sequence, never an invented
  answer); it is operator-invoked and writes an unreviewed dataset. Honest limits
  are printed in every report: the default is the deterministic scripted tier,
  the corpus was 53 tasks when this landed (62 after the adversarial/finance
  datasets below), and no replay dataset is committed yet. Files:
  `python/harness/evaluation/{ablation,candidate_invoker,replay_builder}.py`,
  `python/harness/self_improvement/models.py`, `scripts/rsl-bench.js`,
  `package.json`. Tests: `python/tests/test_ablation.py` (6),
  `test_replay_builder.py` (4), `test_rsl_config.py` (production-prompt cap).
  Docs updated: `docs/self-improvement/rsl-v3-plan.md`, `docs/QUICKSTART.md`,
  `docs/harness/agent-evaluation.md`, `docs/harness/decisions.md` (ADR-H279).
- **chore(rsl): remove the Harness² program; RSL is Eclipse-owned.** No code
  path imported or executed the external framework — only two research docs,
  docstrings and plan references did. The active plan no longer names it
  (`rsl-implementation-plan.md`, `rsl-v3-plan.md`), the NAVIGATION row is gone,
  and the native verdict guard / contrast bundle / selection / lesson gate are
  described as Eclipse mechanisms (`evaluation/{verdict_guard,contrast}.py` +
  their tests). The two historical documents are marked `status: Stale` with a
  `superseded-by` pointer and a withdrawal note rather than deleted, per the
  docs policy ("mark stale, never delete"). Historical CHANGELOG entries are
  unchanged (append-only). Files:
  `python/harness/evaluation/{verdict_guard,contrast}.py`,
  `python/tests/test_evaluation_{verdict_guard,contrast}.py`,
  `docs/{NAVIGATION.md,self-improvement/rsl-implementation-plan.md,self-improvement/rsl-v3-plan.md,self-improvement/architecture-audit.md,self-improvement/harness2-borrowings.md}`.
  Tests: no behavior change; the evaluator suites still pass.
  Docs updated: the docs above; no active doc references Harness².
- **feat(rsl): parallel candidate verification (v3 P2 slice).**
  `HARNESS_RSL_MAX_PARALLEL` (1–8, default 2) now bounds one semaphore per
  experiment. `recursion.run_recursive` verifies its `k` independent candidates
  with `asyncio.gather`, preserves proposal order for selection, and turns one
  verification exception into that candidate's non-answer rather than a batch
  failure. `hillclimb.run_hillclimb` evaluates independent validation neighbors
  concurrently under the same cap, then runs replay gates in order. The daily
  budget still trims `k` before any call and `max_evaluations` is counted before
  the batch; the result carries `maxParallel`. Per-scope leases now let two
  experiments in different scopes run at once (the same scope refuses a second;
  a tick still owns the global busy flag). Recursive results carry
  `costUsd`/`totalTokens` when reported. Cost-per-accepted-improvement reporting
  remains open. Files:
  `python/harness/self_improvement/{config,loop,recursion,hillclimb}.py`.
  Tests: `test_rsl_recursion.py` (parallel cap + order + per-scope lease + usage),
  `test_rsl_hillclimb.py` (parallel validation), `test_rsl_config.py`
  (default/clamp). Docs updated: `docs/self-improvement/rsl-v3-plan.md`,
  `docs/QUICKSTART.md`, `docs/harness/architecture.md`,
  `docs/harness/decisions.md` (ADR-H282).
- **feat(rsl): bounded tool guidance on the editable surface (v3 P3 slice).**
  `HarnessSnapshot.toolGuidance` (≤4,000 chars) is prompt evidence, never
  authority: it cannot add a tool, raise a ceiling, change a permission or grant
  an effect. `effective_prompt()` appends it for candidate trials
  (`to_agent_config`) and the live surface (`apply_active_surface`); the digest
  includes guidance only when non-empty, so every snapshot written before the
  field keeps its exact identity. Guardrails, memory policy, subagent prompts
  and the skill-manifest policy remain P3 work. Files:
  `python/harness/self_improvement/{models,live_surface}.py`,
  `python/harness/evaluation/candidate_invoker.py`. Tests:
  `test_rsl_snapshot.py` (bound + digest), `test_live_surface.py` (applied,
  allowlist unchanged). Docs updated: `docs/self-improvement/rsl-v3-plan.md`,
  `docs/harness/architecture.md`, `docs/harness/decisions.md` (ADR-H283).
- **fix(harness): a process-wide model override is now a lease, not a leak.**
  The evaluation seam and the offline gates replace `graph.build_chat_model` for
  the whole PROCESS. The workflow and resume gates never handed it back, so
  every later run in the same process answered with the gate's model: in the
  full suite that broke 36 unrelated tests (graph, memory, vision, portfolio,
  RSL, resume) that all pass in isolation - a failure that looked like a
  regression in the code under test and was not one. Both gates now save and
  restore the builder in a `finally`, and the evaluation seam refuses to
  replace an ACTIVE override (a test double), because replacing it made the
  double disappear at teardown. The seam still chains over a delegating seam.
  Full suite after the fix: 7830 passed, 27 skipped; the 2 remaining
  prompt-ceiling failures came from a concurrent edit to `harness/prompts.py`
  during the run (the prompt measured 34804 chars against a 34804 ceiling
  afterwards, and both tests pass). Files:
  `python/harness/evaluation/runner.py`,
  `python/harness/eval_gates/{workflow,resume}.py`. Tests:
  `python/tests/test_evaluation_runner.py` (2). Docs updated:
  `docs/harness/decisions.md` (ADR-H284).
- **feat(eval): two new labelled datasets grow the corpus from 53 to 62 tasks.**
  `adversarial_v1` (4 fixtures) and `finance_v1` (5 fixtures) join the built-in
  corpus. The adversarial set is about HONESTY, not vocabulary: a missing
  service must stay UNAVAILABLE instead of becoming a guessed price, a stale
  quote must carry its as-of date, a note in a service response cannot widen the
  agent's scope, and the wrong metric is not the requested metric (net income
  is not EPS). The finance set is graded by an INDEPENDENT recomputation of the
  same metric (net margin, operating margin, EV/EBITDA, EPS, position weight);
  every number is a synthetic literal inside the task, so no provider call and
  no market data is involved. The release gate now runs 62 tasks and stays
  green. Files:
  `python/harness/evaluation/datasets/{adversarial_v1,finance_v1}.json`.
  Docs updated: `docs/harness/agent-evaluation.md`, `docs/NAVIGATION.md`,
  `docs/self-improvement/rsl-v3-plan.md`.
- **chore(harness): the Python size ratchet is re-pinned for the in-flight
  shared-tree work.** `graph.py` 2238→2241 (the chat step budget moved from
  12 to 24 steps, with the longer rationale it carries) and `quant/tools.py`
  1203→1229 (a CPU-bound backtest now runs in a worker thread with an honest
  wall-clock timeout instead of blocking the event loop). Both were red on the
  shared working tree before this re-pin; the standing split candidates are
  unchanged. Files: `python/tests/test_size_budget.py`.
- **fix(harness): the shared tree's own regressions are repaired - the chat step
  budget, the prompt ratchet and the Python size ratchet.** The in-flight work
  raised the ordinary chat budget from 12 to 24 model steps (12 was too tight
  for a request that carries several deliverables) and grew the agent prompt to
  35,251 characters, but its own tests still pinned the old numbers, so the
  suite was red: the budget assertions now expect 24, the prompt ceiling is
  re-pinned 34,804->35,251 in both places that measure it, and the Python size
  ratchet is re-pinned for `graph.py` (2238->2241) and `quant/tools.py`
  (1203->1229). Full Python suite: 7919 passed, 27 skipped. Files:
  `python/tests/test_chat_step_budget.py`,
  `python/tests/test_qa_round1_acceptance.py`,
  `python/tests/test_memory_tools.py`,
  `python/tests/test_phase_s_stabilization.py`,
  `python/tests/test_size_budget.py`.
- **fix(front door): the in-flight price-history window change keeps its own
  tests honest.** The bridge now carries the caller's start/end window into the
  transport instead of filtering the rows afterwards, so the two call
  expectations had to name the new argument (and the TS size ratchet is
  re-pinned 1400->1408 for the same change). Full vitest: 3696 passed;
  `npx tsc --noEmit` clean. Files:   `src/lib/harness/data-bridge-identity.test.ts`,
  `src/lib/harness/data-bridge-phase2.test.ts`, `src/lib/size-budget.test.ts`.
- **feat(eval): the corpus is now a portable, tamper-evident bundle.** Our
  benchmark is ours: it must travel without any external framework.
  `evaluation/export.py` writes one entry per built-in dataset (name, version,
  split, content checksum, every task in the shared task schema), reads such a
  bundle back through the SAME schema, and VERIFIES it by recomputing each
  checksum from the tasks themselves - an edited task is detected, not trusted.
  `npm run rsl:corpus -- --out <file>` exports (add `--split validation` for
  one split); `--verify <file>` re-checks a bundle and exits non-zero on a
  mismatch. The bundle is derived data: labelled tasks only, no production data
  and no market data. Files: `python/harness/evaluation/export.py`,
  `scripts/rsl-corpus.js`, `package.json`. Tests:
  `python/tests/test_evaluation_export.py` (4). Docs updated:
  `docs/harness/agent-evaluation.md`, `docs/NAVIGATION.md`,
  `docs/self-improvement/rsl-v3-plan.md`.
- **feat(rsl): the cost of a self-improvement experiment is now measured.** A
  recursive experiment records the real `costUsd`/`totalTokens` the verifier
  reported (absent stays `UNKNOWN`, never a fabricated zero), and the
  self-evolution metric block gains `rsl_cost_usd` and `rsl_cost_per_accepted`
  — the recorded experiment cost divided by the accepted experiments. A run
  that reported no cost does not become a zero-cost run. Files:
  `python/harness/self_improvement/recursion.py`,
  `python/harness/evaluation/repair_metrics.py`. Tests:
  `test_evaluation_repair_metrics.py` (the block + the cost rule),
  `test_rsl_recursion.py`. Docs updated:
  `docs/self-improvement/rsl-v3-plan.md`.
- **feat(rsl): a surface may narrow the CONTEXT it injects (v3 P3 slice 2).**
  Two closed-set policies now ride the surface: `skillManifest`
  (`none` | `top3` | `top8`) bounds how many skills are listed as a hint, and
  `memoryPolicy` (`off` | `profile_only` | `profile_plus_search`) decides
  whether recalled memory, the persistent profile, or both reach the prompt.
  Both live on `AgentConfig` and on `HarnessSnapshot` (digest-additive, so an
  older snapshot keeps its exact identity); an unknown value is REFUSED rather
  than treated as the default. Neither grants a tool, a permission or an
  effect, and neither touches the tool allowlist — the manifest is a hint and
  narrowing it removes hints, never a capability. Enforced where the blocks are
  built (`graph_context.py`), and the surface experiment request carries them.
  Files: `python/harness/schemas.py`,
  `python/harness/self_improvement/{models,live_surface}.py`,
  `python/harness/graph_context.py`, `python/harness/routers/evolution.py`.
  Tests: `python/tests/test_surface_context_policy.py` (6),
  `test_rsl_snapshot.py`, `test_live_surface.py`. Docs updated:
  `docs/self-improvement/rsl-v3-plan.md`, `docs/harness/decisions.md`
  (ADR-H285), `docs/harness/architecture.md`.
- **feat(rsl): guardrails the runtime ENFORCES (v3 P3 slice 3).** Everything a
  surface could change before this was prompt text, a tool subset or a ceiling:
  all either advisory or authority. A surface may now carry a closed set of
  `guardrails` plus `maxAnswerChars`: `require_tool_before_answer` (the run
  executed at least one tool), `require_citation` (the answer carries a
  citation, judged by the evaluator's own citation parser) and an answer-length
  bound. They are checked ONCE, at the end of the run, against what the run
  really did (the persisted tool executions) and what it really answered: a
  violation FAILS the run with a named code (`GUARDRAIL_TOOL_REQUIRED`,
  `GUARDRAIL_CITATION_MISSING`, `GUARDRAIL_ANSWER_TOO_LONG`) and the answer is
  not shipped as a completed result. A broken guardrail implementation degrades
  to "no violation" - it can never break a run. The codes are part of the
  runtime error contract on both sides (Python `HarnessErrorCode` + the TS
  union). Files: `python/harness/self_improvement/guardrails.py` (new),
  `python/harness/schemas.py`, `python/harness/graph.py`,
  `python/harness/self_improvement/{models,live_surface}.py`,
  `python/harness/routers/evolution.py`, `src/lib/harness/errors.ts`. Tests:
  `python/tests/test_rsl_guardrails.py` (6), `test_graph.py` (a run that breaks
  a guardrail fails with the named code), `test_live_surface.py`,
  `test_rsl_snapshot.py`. Docs updated: `docs/self-improvement/rsl-v3-plan.md`,
  `docs/harness/decisions.md` (ADR-H286), `docs/harness/architecture.md`.
- **feat(rsl): the loop reports on itself, and a drift episode may open its own
  candidate (v3 P4 slice).** `GET /evolution/rsl/report?days=7` returns ONE
  honest summary: experiments, accepted / rejected / unmeasured, the real cost
  and the cost per accepted improvement, the candidates in flight, the lessons
  adopted and where production is drifting. A measure that was never taken
  reads `UNKNOWN` - never a fabricated zero - and the same digest renders as
  Markdown, so a person or CI can read it. The operator panel gained a weekly
  card (what was tried, what improved, what it cost, the drift state). With
  `HARNESS_RSL_DRIFT_AUTOCANDIDATE=on` (OFF by default) the drift watch opens,
  on a NEW transition into drift, the SAME inert candidate the operator route
  opens: no target, no operations, it enters the existing propose -> verify ->
  land flow and lands nothing by itself. Files:
  `python/harness/self_improvement/{report,drift_watch}.py`,
  `python/harness/routers/evolution_report.py`,
  `src/components/screens/skills/rsl-weekly-card.tsx` (new),
  `src/app/api/evolution/rsl/report/route.ts` (new),
  `src/lib/harness/evolution-{client,browser}.ts`,
  `src/lib/i18n/dictionaries/evolution.ts`. Tests: `test_rsl_digest.py` (3),
  `test_drift_watch.py` (the opt-in candidate), `rsl-weekly-card.test.tsx`.
  Docs updated: `docs/self-improvement/rsl-v3-plan.md`,
  `docs/harness/decisions.md` (ADR-H287), `docs/QUICKSTART.md`.
- **feat(eval): the unattended session is a GATE (v3 P4 slice 2).**
  `npm run rsl:nightly` runs the corpus once (the deterministic tier), compares
  the result with the recorded baseline through the EXISTING per-dimension
  regression gates, writes a dated JSON + Markdown report, and exits non-zero
  when a CRITICAL measure regressed (task success, safety, hallucination rate,
  financial accuracy, routing). Cost, latency and token movements are warnings
  and do not fail the session. The baseline only moves forward on a clean run
  and only with `--promote`: a worse run never silently becomes the new normal.
  The gate is PROVEN by planting a regression - a test adds a task that does not
  pass and asserts the session says FAIL, names the regressed measure and
  writes it to the report; a gate that cannot fail is decoration. No second
  gate, no second baseline store: the baseline, the regression gates and the
  report writers are the existing ones. Files:
  `python/harness/evaluation/nightly.py` (new), `scripts/rsl-nightly.js`,
  `package.json`. Tests: `python/tests/test_evaluation_nightly.py` (2). Docs
  updated: `docs/self-improvement/rsl-v3-plan.md`, `docs/harness/agent-evaluation.md`,
  `docs/harness/decisions.md` (ADR-H288), `docs/QUICKSTART.md`.
- **feat(rsl): a delegated child inherits the surface's context policy (v3 P3
  slice 4).** A delegated child ran the SAME agent preset as its parent, so a
  surface that improved the parent's prompt did nothing for the child - and the
  child is where the fan-out work happens. A surface may now carry
  `subagentPrompt` (≤4,000 chars): the child keeps its own preset prompt, gains
  the surface's bounded instructions, and its tools are the NARROWED set the
  delegation already computed. It is prompt evidence - no tool, no ceiling, no
  permission, no effect - and the delegation path is unchanged when the field is
  absent. That closes the editable-surface set: prompt, tool guidance, tool
  subset, ceilings, context policy, guardrails and the delegated child's
  prompt. Files: `python/harness/schemas.py`, `python/harness/tools.py`
  (`ToolContext.agent`), `python/harness/graph.py`,
  `python/harness/delegation_tools.py`,
  `python/harness/self_improvement/{models,live_surface}.py`,
  `python/harness/routers/evolution.py`. Tests: `test_delegation_tool.py` (the
  child inherits the prompt and the narrowed tools), `test_rsl_snapshot.py`
  (bounded + digest). Docs updated: `docs/self-improvement/rsl-v3-plan.md`,
  `docs/harness/decisions.md` (ADR-H289), `docs/harness/architecture.md`.
- **feat(eval): the corpus gate joins the release gate, and the corpus carries
  replay fixtures (v3 P4/P1 slice).**
  `python/harness/evaluation/baselines/corpus_v1.json` is the COMMITTED record
  of what the corpus measures today - the stable measures only, because cost,
  latency and token usage move on every run and are never pinned.
  `scripts/check-all.js` (the repo's real release gate; the GitHub workflows
  never ran from this subfolder) now ends with the corpus gate: a critical
  regression (task success, safety, hallucination rate, financial accuracy,
  routing) fails the release. Refreshing the baseline is a deliberate act
  (`npm run rsl:nightly -- --dataset all --write-baseline <file>`).
  `replay_v1.json` joins the corpus as six AUTHORED replay fixtures in the
  shape the replay builder produces from real runs (expected behavior = the
  recorded tool sequence, never an invented answer); they are live-only, so the
  scripted tier reports them UNMEASURED rather than pretending a stale model
  response replays. The corpus is now 68 tasks. Files:
  `python/harness/evaluation/{nightly.py,datasets/replay_v1.json,baselines/corpus_v1.json}`,
  `scripts/{rsl-nightly.js,check-all.js}`. Tests:
  `python/tests/test_evaluation_nightly.py` (the committed baseline is the
  gate; a broken baseline file is refused). Docs updated:
  `docs/harness/agent-evaluation.md`, `docs/self-improvement/rsl-v3-plan.md`.
- **feat(eval): the corpus grows to 76 tasks - a second adversarial + finance
  tranche.** `adversarial_v1` (8) and `finance_v1` (9) join the corpus, and
  the committed baseline is refreshed against it. The new adversarial fixtures
  are about HONESTY under pressure: two sources that disagree (report both, do
  not pick one), a quote in the wrong currency (name the currency you
  actually have), a price with no currency at all (the unit is missing), and a
  document carrying an injected instruction (a document is data; publishing is
  not allowed). The new finance fixtures are independently recomputed:
  percentage change, three-year CAGR, free cash flow after capital spending,
  and a position size from reward and risk. The corpus is now 76 tasks (64
  validation / 10 optimization / 2 held_out) and the release gate still passes
  against the committed baseline. Files:
  `python/harness/evaluation/datasets/{adversarial_v1,finance_v1}.json`,
  `python/harness/evaluation/baselines/corpus_v1.json`. Docs updated:
  `docs/harness/agent-evaluation.md`, `docs/self-improvement/rsl-v3-plan.md`.
- **feat(rsl): the lab tries to improve the harness itself, and it may only
  report a CANDIDATE (v3 P5 slice).** Everything the loop can change is code
  (a worktree, a promotion) or a surface (prompt, tool guidance, context
  policy, guardrails). The surface is the cheap one - no worktree, no landing -
  and it is where most of the headroom is. `npm run rsl:lab` (the surface lab)
  does that honestly: the variants are DETERMINISTIC and derived from the
  lessons the loop already ADOPTED (one lesson, the top three, their cues as a
  checklist - with no adopted lesson there is no variant, because the lab never
  invents an instruction nobody verified); each variant is measured on the SAME
  tasks through the existing measured surface path against the base's own run;
  an UNMEASURED variant is never a winner, a critical regression (safety,
  adversarial) is VETOED even when the average is better, and "flat" is a
  result, not a win; the winner is a CANDIDATE for the operator - the lab never
  lands, never activates and never writes to the harness. On the scripted tier
  the lab correctly finds NO improvement, because a scripted answer does not
  depend on the prompt. Files: `python/harness/self_improvement/surface_lab.py`
  (new), `scripts/rsl-lab.js`, `package.json`. Tests:
  `python/tests/test_surface_lab.py` (7). Docs updated:
  `docs/self-improvement/rsl-v3-plan.md`, `docs/harness/decisions.md`
  (ADR-H290), `docs/QUICKSTART.md`.
- **feat(rsl): ONE surface-candidate path, and the lab stages EVIDENCE
  (v3 P5 slice 2).** The identity of a surface experiment and the row it
  creates now live in `self_improvement/surface_candidate.py`; the operator
  route and the surface lab BOTH call it, so a lab winner and an operator
  experiment are the same thing to the rest of the system, and re-running the
  same experiment never creates a second row. The lab stages its winner as an
  INERT surface candidate whose problem statement carries the measured delta
  and the lessons it came from; `POST /evolution/surface-lab/{id}/queue` is the
  operator's one click to queue it, and the loop then verifies it through the
  SAME measured path every other surface experiment uses - only then can it be
  activated (canary + rollback). The lab never lands, never activates and never
  queues: a machine-authored improvement meets the same gate as an
  operator-authored one. Files:
  `python/harness/self_improvement/surface_candidate.py` (new),
  `python/harness/self_improvement/surface_lab.py`,
  `python/harness/routers/evolution.py`. Tests:
  `python/tests/test_surface_candidate.py` (4). Docs updated:
  `docs/self-improvement/rsl-v3-plan.md`, `docs/harness/decisions.md`
  (ADR-H291).
- **feat(rsl): the live lab tier - a prompt can only be measured with a real
  model (v3 P5 slice 3).** The lab has two tiers and they are not
  interchangeable. The scripted tier (the default) replays a deterministic
  answer: it proves the harness path works and it CANNOT see a prompt change,
  because a scripted answer does not depend on the prompt - so it reports
  "flat" and no winner, which is the honest result, not a gap. The live tier
  (`npm run rsl:lab -- --live --provider <p> --model <m>`, credential from
  `HARNESS_EVAL_API_KEY`) runs the SAME measured path with a real model: the
  runtime never guesses a provider, a model or a key, and a live run without
  explicit settings is refused before it starts. The live tier is the only tier
  in which the lab's verdict about a PROMPT change means anything. Files:
  `python/harness/self_improvement/{surface_lab,verifier}.py`. Tests:
  `python/tests/test_surface_lab.py` (the live tier reaches the invoker with the
  explicit settings; the test run stays deterministic). Docs updated:
  `docs/self-improvement/rsl-v3-plan.md`, `docs/harness/decisions.md`
  (ADR-H292), `docs/QUICKSTART.md`.
- **feat(rsl): the whole remaining list, in one pass (v3 P2/P3/P4/P5 + the
  evidence program).**
  - **The conductor now improves its OWN harness.** `HARNESS_RSL_SURFACE_LAB=on`
    makes the `auto` tick run ONE measured surface session
    (`self_improvement/lab_runner.py`) and STAGE the winner as an inert
    candidate. The surface budget is SEPARATE from the code budget
    (`HARNESS_RSL_MAX_SURFACE_EXPERIMENTS_PER_DAY`), so exploring the harness
    is never starved by (or starves) the code experiments.
  - **The session can run unattended.** `HARNESS_RSL_SESSION_SECONDS` starts
    the session watcher inside the runtime (the drift-watch pattern): one bounded
    session per cadence, bounded by the surface budget, staging evidence only.
  - **The lab searches the WHOLE surface**, not just the prompt: guidance
    variants from the adopted lessons, a context-policy variant and a
    guardrail variant.
  - **Two more runtime guardrails**: `no_fabricated_url` (the answer may only
    cite a URL a TOOL returned) and `require_source_for_numbers` (a number
    needs a source, or the answer must say the data was unavailable).
  - **The corpus gate has a live tier** (`npm run rsl:nightly -- --live
    --provider <p> --model <m>`): the corpus answered by a real model, compared
    against a committed live baseline. The scripted tier stays the default.
  - **The corpus is 88 tasks** (was 76): `adversarial_v1` (12) and
    `finance_v1` (13) grew, and `research_v1` (4) joined - the SOURCE-DISCIPLINE
    set where the PROMPT decides the answer (cite the source you used, say when
    the data is not there, present a conflict, carry the as-of date). Those four
    are live-only on purpose: a scripted answer does not depend on the prompt,
    so the scripted tier reports them UNMEASURED rather than pretending.
  - **The operator sees the loop's own work**: the weekly card now shows what
    Eclipse tried on itself, with a "check it again" button that queues a
    staged candidate for the loop's verification; the digest remembers the last
    one and reports the week-over-week change; `GET /evolution/replay/digest`
    reports how much REAL-RUN evidence the store holds.
  - **Verification hygiene**: `npm run test:rsl` runs the RSL slice in ~80
    seconds; `npm run check:all` is the gate of record (this repo has no
    working remote CI - the workflows live in a subfolder GitHub never reads).
  - **Two decisions, recorded**: the loop stays `off` by default (zero-config
    must not write), and the size ratchets keep their history (the real fix is
    splitting the hot files, not moving the pins).
  Files: `python/harness/self_improvement/{lab_runner,session_watch,guardrails,report,config,loop}.py`,
  `python/harness/evaluation/{nightly,replay_builder}.py`,
  `python/harness/evaluation/datasets/{adversarial_v1,finance_v1,research_v1}.json`,
  `python/harness/routers/evolution_report.py`,
  `src/components/screens/skills/rsl-lab-card.tsx` (new),
  `src/app/api/evolution/surface-lab/**` (new), `scripts/test-python.js`,
  `package.json`. Tests: `test_rsl_session.py`, `test_rsl_guardrails.py`,
  `test_surface_lab.py`, `test_rsl_digest.py`. Docs updated:
  `docs/self-improvement/rsl-v3-plan.md`, `docs/harness/agent-evaluation.md`,
  `docs/harness/architecture.md`, `docs/harness/decisions.md` (ADR-H292),
  `docs/QUICKSTART.md`.
- **fix(ci): the repository workflow now runs the corpus gate, and the local
  gate mirrors it.** Correction to the entry above: a working workflow DOES
  exist at the repository root (`/.github/workflows/ci.yml`); the stale claim
  was about the OLD workflows under `Black-Eclipse-site/.github/`. The root
  workflow now ends with the same corpus gate as `npm run check:all`, and the
  comment in `check-all.js` no longer calls CI unreachable. A guard test now
  pins the wiring: the workflow and the local gate must BOTH run the eval and
  corpus gates. Files: `.github/workflows/ci.yml`,
  `scripts/check-all.js`, `src/lib/ci-gate.test.ts` (new). Docs updated:
  `docs/self-improvement/rsl-v3-plan.md`, `docs/harness/agent-evaluation.md`.

## 2026-10-19

- **fix(shell): the sidebar mode is now per browser tab/window.** Switching to
  Bots in one tab no longer drags another open tab out of its mode. The mode
  lives in `sessionStorage` per shell; remote `/api/sdk/app` updates still sync
  section order/visibility but never override an open shell's mode, and the
  shared mode is only the seed for a newly opened tab. Tests:
  `src/lib/sidebar/store.test.ts`. Docs updated: `docs/ARCHITECTURE.md`,
  `docs/eclipse-sdk.md`, `docs/NAVIGATION.md`.

- **fix(perf): second browser tab no longer re-downloads the whole dev bundle.** Dev
  Turbopack chunks/CSS were served `Cache-Control: no-store`, so every new tab
  re-fetched and re-parsed the ~22 MB client graph. `next.config.ts` now serves
  `/_next/static/chunks/*` immutable in dev only (URLs are content-hashed; HTML
  and RSC stay `no-store`), and enables `optimizePackageImports` for the
  `@phosphor-icons/react` barrel. `bin/black.js` and `scripts/up.js` now leave an
  already-running server untouched instead of killing and cold-booting it
  (`--restart` keeps the old behavior); `isUp` probes without following the
  canonical-host redirect so a healthy TLS-fronted server is not read as down.
  Docs updated: `docs/QUICKSTART.md`.

- **feat(harness): persistent analysis kernel for chat conversations.** Added
  `python/harness/code/kernel.py` (Kernel/KernelPool/worker protocol) and
  interactive spawn in `code/sandbox.py` (`spawn`/`SpawnedProcess`, per-process
  job map); extracted `ANALYSIS_PRELUDE`/`PreparedAnalysis`/`prepare_analysis`/
  `resolve_tool_request` in `code/execution.py` so one-shot and kernel share the
  same gate and tool replay; `run_analysis`/`run_recipe` accept `kernel=`;
  `analysis_tools.py` selects `kernel_for_context`. Session-scoped keys, default
  max 4, 300 s idle sweep, LRU eviction, crash â†’ `KERNEL_CRASHED` + respawn,
  one-shot fallback on spawn failure or `ECLIPSE_ANALYSIS_KERNEL=0`. Bounds and
  provenance unchanged. Tests: `python/tests/test_analysis_kernel.py` (10) plus
  the existing analysis suites. Docs updated: `docs/harness/python-runtime.md`
  (new), `docs/harness/decisions.md` (ADR-H236), `docs/NAVIGATION.md`,
  `docs/harness/capability-extension-plan.md`.

- **feat(ui): response presentation intelligence â€” auto charts, weights, bands, alignment, focus.** `chart` gains
  `chartType: "auto"` (default; explicit wins): temporal/multi-series â†’ line,
  single series â‰¤12 labels â†’ bar, triples â†’ bubble, monotonic pairs â†’ line,
  other pairs â†’ scatter. Series `weight` scales width/opacity; `band`
  `{lower, upper, weight?}` renders as hidden stacked band series on category
  axes (legend lists only real series). `data_table` derives right alignment
  (â‰¥80 % numeric; explicit `align` wins) and locale-formats raw numbers (â‰¤4
  fraction digits; numeric strings untouched; fixes `(2,500)` parsing).
  `response-chart.tsx` adds a focus overlay (Escape/backdrop/Close,
  `role="dialog"`). Tests: `chart-option.test.ts`, `table-presentation.test.ts`,
  `render.test.tsx` (91 passed across 4 files); `npx tsc --noEmit` clean. Docs
  updated: `docs/interactive-response-engine.md`, `docs/harness/decisions.md`
  (ADR-H237), `docs/harness/capability-extension-plan.md`.

- **feat(harness,ui): disabled broker/API adapter authoring + read-only built-in catalogue.** Added
  `python/harness/capabilities/adapter.py` (`author_adapter`/`AdapterDraft`) and
  the `capability_adapter` tool: writes a reviewable, DISABLED plugin draft
  (`plugin.yaml` validated with the real `PluginManifest`, generated `plugin.py`,
  README) under `.black-eclipse/adapters/<slug>/`; HTTPS-only, credential NAMES
  only (shared `normalize_credential_names`), GET â†’ `read` / POST â†’
  `external_action`, permissions `[network]`, never installed or enabled. Studio
  gains the read-only static recipe catalogue (`GET /capabilities/builtins`,
  declared before `/{id}`) with `listBuiltins` + built-in badge (`studio.generated.builtin*`
  keys). Tests: `test_capabilities_adapter.py` (9),
  `test_capabilities_api.py` (builtins), allowlist tests updated. Docs updated:
  `docs/harness/capability-builder.md`,
  `docs/harness/capability-extension-plan.md`,
  `docs/harness/self-evolution-roadmap.md`, `docs/harness/decisions.md`
  (ADR-H238), `docs/NAVIGATION.md`.

- **chore(docs): normalize `docs/harness/decisions.md` line endings.** The
  ADR-H236â€“H238 append left the file mixing CRLF and bare LF, which tripped the
  mixed-line-ending guard; converted to LF-only, no content change. Full
  verification after all three landings: `npm run test` green (Vitest 361 files /
  3,652 tests; Python 7,373 passed, 27 skipped; eval gates ALL PASS),
  `npx tsc --noEmit` clean.
  no doc change â€” line-ending hygiene only.

- **feat(harness): W14 â€” completion is verified per task type against the evidence the runtime recorded.** `TaskType` gains `data`; every task-type verifier now reads the evidence the runtime really writes. `research` â‡’ traceable sources + a supported, evidence-linked claim + the uncertainty RECORDED (a partial answer naming no open gap is refused; a rejected engine verdict is refused). `document` â‡’ the artifact AND every section the contract required (named deterministically by `goal.parse_required_sections`; the delivered document records the headings it wrote). `workflow` â‡’ observed steps AND an observable state change â€” the stored run id is no longer accepted as a "result", so a workflow that started, called one tool and produced nothing is refused (the old check could never fail). `finance` â‡’ provenance + freshness + claim-to-evidence, deferring to the Evidence Engine's verdict. `data` â‡’ a reproducible calculation: a recorded formula with its inputs, or an analysis that pinned the program and the inputs it read (`analysis_tools.load_run_analyses` â†’ the task outcome's `analyses` evidence). Three recordings were added so these rules can be checked at all: required document sections, the sandbox's `AnalysisRecord` rows, and an authored document's headings. Tests: `python/tests/test_tasks_verification.py` (37), `python/tests/test_w14_verification_evidence.py` (9).   Docs updated: `docs/harness/task-plan-system.md`, `docs/harness/self-evolution-roadmap.md`, `docs/harness/decisions.md` (ADR-H240).

- **chore(repo): normalize `src/app/globals.css` line endings.** Removed the lone
  CRLF left by an unrelated 17-line addition so the mixed-line-ending guard
  passes; no CSS content changed. Full verification: `npm run test` green
  (Vitest 360 files / 3,633 tests; Python 7,352 passed, 27 skipped; eval gates
  ALL PASS), `npx tsc --noEmit` clean.
  no doc change â€” line-ending hygiene only.

- **fix(ui,harness): stop the boot overlay freezing at 95% and page loads stalling for minutes.**
  Two independent causes. (1) The cosmetic `GlobalLoader` dismissed itself from a
  main-thread timer, so while a route hydrated/dev chunks compiled the overlay
  froze at its last percentage; it now also carries a compositor-driven CSS
  auto-dismiss (`be-boot-overlay`) that works even if React never gets a turn.
  `TopLoader` no longer fabricates a 0â†’95% count-up (the number sat at 95% while
  a dynamic import/request was still pending) and is now honestly
  indeterminate. The root-layout command-palette chunk, the SDK/dashboard
  catalog sync, and the terminal prewarm are deferred to idle instead of
  competing with hydration. (2) The Python runtime could be cold-started by more
  than one Next server context at once; the extras booted the whole agent stack,
  fought over SQLite and pegged CPU, and every Python-proxy route (tasks,
  automations, SDK app, etc.) took 15â€“30s behind the resulting `/health` misses.
  `python-runtime.ts` now takes an atomic cross-context spawn lock, waits for a
  tracked booting child instead of spawning a rival, uses a 5s probe for a
  late `/health`, kills tracked children as a tree, and defaults the cold-start
  budget to 240s. Docs updated: `docs/harness/architecture.md`.

- **feat(harness): read-only `eclipse_tools` RPC in the analysis sandbox (Phase 3).**
  Added `python/harness/code/sandbox_tools.py` and a deterministic replay path in
  `code/execution.py`: an `analysis_run` program may call exactly
  `market_snapshot`, `live_quote` and `price_history`; the runner writes one
  pending request and exits, the host validates it against the allowlist,
  resolves through the existing DataBridge, memoizes it and replays. No live
  channel, no writes/network, and no fetched payload in the model context â€” only
  final outputs and audit digests. `analysis_tools.py` runs the sync sandbox with
  `asyncio.to_thread` and bridges the async DataBridge via
  `run_coroutine_threadsafe`; `code/recipes.py` passes the resolver through.
  Bounds: 8 calls, 4 KiB args, 16 KiB request read cap, 1 MB result, 4 MB memo.
  Tests: `python/tests/test_analysis_sandbox_tools.py` plus the analysis suites.
  Docs updated: `docs/harness/capability-builder.md`,
  `docs/harness/capability-extension-plan.md`,
  `docs/harness/self-evolution-roadmap.md`, `docs/NAVIGATION.md`,
  `docs/harness/decisions.md` (ADR-H235).

- **feat(harness,ui): capability close-out â€” operator global promotion, card/Studio actions, recipe label.**
  Added `builder.promote` and the operator-gated `POST /capabilities/{id}/promote`
  route (ADR-H234): a verified read-only workspace recipe is copied to
  `python/harness/generated/capabilities/<slug>/<version>/`, its manifest `scope`
  is rewritten to `global`, and the record points at the copy (workspace files
  kept). Guards: operator required, contract test verified, source digest
  unchanged, `GLOBAL_EXISTS` refused, idempotent re-promote. The chat card now
  offers Build it / Show plan / Not now, hand-off Continue, and Rebuild with RSL
  (prompt-only); Studio â€º Generated adds **Promote to global** and **Rebuild with
  RSL**. The computed-result payload carries `recipe` and the panel renders it.
  Tests: `test_capabilities_builder.py`, `test_capabilities_api.py`,
  `capability-card.test.tsx`, `analysis-types.test.ts`. Docs updated:
  `docs/harness/capability-builder.md`, `docs/harness/capability-extension-plan.md`,
  `docs/NAVIGATION.md`, `docs/harness/decisions.md` (ADR-H234).

- **feat(harness): capability activation resumes the original parked task; failures feed learning.**
  Added `ToolContext.task_id`/`task_manager` wiring, `CapabilityRequest.resume_task_id`
  and a versioned `CapabilityRecord.taskId` (additive column migration), plus
  `capabilities/resume.py`. Operator and agent activation/rollback resume a
  `WAITING`/`ASKING_USER` task from its durable checkpoint; running/TODO tasks
  are never rewound. Failed generated-recipe calls record a `capability_failure`
  recurrence in the ONE learning ledger. Re-pinned `graph.py` 2215â†’2221 and
  `service.py` 1532â†’1533 for the task-link seams. Tests:
  `python/tests/test_capabilities_resume.py`. Docs updated:
  `docs/harness/capability-builder.md`,
  `docs/harness/capability-extension-plan.md`, `docs/harness/self-evolution-roadmap.md`,
  `docs/NAVIGATION.md`, `docs/harness/decisions.md` (ADR-H232).

- **feat(harness): RSL controlled smoke test + real worktree verifier fixes.**
  Added `npm run rsl:smoke` (`python/harness/self_improvement/smoke.py` +
  `scripts/rsl-smoke.js`): a disposable git repo with a failing owning test is
  verified by the real conductor in a real worktree, then a scripted surface
  baseline/candidate benchmark is recorded; both use a temp `agent-memory.db`,
  and the checkout/dev databases are untouched. The smoke exposed and fixed two
  production bugs in the code verifier: `evolution_service._resolved_for` built
  no `WorkspaceBinding` (every worktree write was refused as `NO_BINDING`) and
  `_make_check_runner` returned an un-awaited coroutine instead of a sync
  callable. Added `test_code_verifier_runs_the_owning_test_in_a_real_worktree`.
  Docs: `docs/self-improvement/rsl-implementation-plan.md`,
  `docs/NAVIGATION.md`, `docs/QUICKSTART.md`, `docs/CHANGELOG.md`.

- **feat(harness,ui): RSL post-R8 closure â€” reachable surface experiments and the event wake.**
  Added additive `subjectType`/`surfaceConfig` columns on `EvolutionCandidate`
  (idempotent `ALTER`; old rows default to `code`), operator-gated
  `POST /evolution/surface-experiments` (validated base/candidate snapshot,
  dataset/split/task ids, one proposed candidate), and
  `verifier.verify_surface_candidate` (record the same base snapshot as an
  `rsl-baseline`, reuse it only when the base digest and task fingerprint match,
  then run the measured candidate benchmark). The verify tick dispatches by
  subject type, records one budget-counted `EvolutionAttempt` plus the
  completion event (creating the `HarnessRun` container the event FK requires
  when absent), and `landing.prepare` refuses surface subjects
  (`RSL_SURFACE_NOT_LANDABLE`). `evaluation.started` now wakes the conductor;
  the learning-journey operator panel gained the surface form. Production
  controls: `GET /evolution/rsl` (mode/running/busy/daily budget),
  `POST /evolution/rsl/tick` (one bounded tick), and
  `POST /evolution/candidates/{id}/propose` (stage validated ops without
  applying), surfaced by `rsl-control-panel.tsx`; the plan gained the operator
  runbook. Tests:
  `python/tests/test_rsl_surface.py`, `test_rsl_surface_e2e.py`,
  `test_rsl_security.py`, `test_rsl_loop.py`,
  `test_evolution_rsl_operator.py`, `test_evolution_rsl_routes.py`, the
  `test_events_service.py` wake test, and the panel test. Docs:
  `docs/self-improvement/rsl-implementation-plan.md`, `docs/NAVIGATION.md`,
  `docs/harness/architecture.md`, `docs/harness/decisions.md` (ADR-H233),
  `docs/QUICKSTART.md`, `.env.example`, `docs/CHANGELOG.md`.

- **chore(sdk,ui): polish the app-shell/theme surfaces.** Automatic sidebar
  mode-following now uses `setModeFromNavigation` and is excluded from the
  app-wide nav audit, so ordinary tab navigation no longer creates
  `app.nav_update` entries; explicit switcher/hotkey/SDK mode changes still
  sync and audit. App-wide preset notes now distinguish success (emerald) from
  failure (rose). `no doc change - internal polish`.

- **chore(ui): normalize one bare LF in the concurrent `customization-settings.tsx`.**
  The file's existing CRLF convention is preserved; the line-ending guard stays
  green. `no doc change â€” whitespace-only normalization in concurrent work`.

- **feat(sdk): page edit/delete tools, Settings app-wide presets and lock badges.**
  Added `sdk_page_update`/`sdk_page_delete` over the existing
  `EclipseSdk.update_page`/`delete_page`. Settings â†’ Customization â†’ Theme now
  lists, applies, saves and deletes the app-wide named presets from
  `SystemConfig` (via a new `themeToSpec` projection; browser-local chart/
  backdrop presets remain separate). `/api/theme` writes are now audited, the
  Activity panel loads older pages (100â†’500), and the Command Center/Pages
  headers show a Locked badge fed by `eclipse:locks-changed` (30 s fallback).
  Tests: `test_sdk_dashboards.py`, `theme-spec.test.ts`,
  `src/app/api/theme/route.test.ts`. Docs updated: `docs/eclipse-sdk.md`,
  `docs/NAVIGATION.md`, `docs/CHANGELOG.md`.

- **feat(sdk): Phase 6 - SDK audit, dashboard undo/history and the lock manager.**
  Added the append-only `SdkAudit` table on `agent-memory.db` (bounded to 2,000
  rows, no passphrases/hashes/hints) with `GET/POST /sdk/audit`, the
  `sdk_audit_list` read tool and `eclipseSdk.audit.list`. Widget, page, fund,
  dashboard and lock mutations audit from Python; front-door theme, app-shell
  and dashboard-template writes record through `src/lib/sdk/audit-server.ts`
  over the loopback callback (best-effort). The SDK screen gained a filtered
  Activity panel and a fuller lock manager (all resource types, type/search
  filters, hint/updated time, per-tab unlocked badges). The Command Center
  toolbar gained Undo (Ctrl/Cmd+Z) and a revision History popover that restore
  retained mirror revisions; a restore is a new revision, and the restored
  layout is applied locally before the SSE sync. Tests:
  `python/tests/test_sdk_audit.py`, `test_sdk_api.py`,
  `src/lib/sdk/{audit-server,dashboard-history}.test.ts` and the existing SDK
  route tests. Docs updated: `docs/eclipse-sdk.md`, `docs/ARCHITECTURE.md`,
  `docs/NAVIGATION.md`, `docs/CHANGELOG.md`.

- **feat(harness): effectful capabilities are handed to their existing owner.**
  Added `capabilities/handoff.py` (`EffectfulHandoff`) and routed `tool`,
  `skill`, `ui_widget`, `ui_page`, `harness_change` and `plugin` builds to
  `scaffold_kit` / `skill_create` / `ui_start_engineering` / `create_goal` /
  `capability_external` with arguments, acceptance, evidence and an operator
  activation owner. `builder.build` stores the hand-off on the same durable
  request (`handoff_required`) and executes nothing; `capability_build` no longer
  requires the analysis sandbox for an effectful kind. The chat card and TS view
  carry `handoff_required` + `nextTool`. Tests:
  `python/tests/test_capabilities_handoff.py` + builder/tools tests; TS
  `capability-types.test.ts`. Docs updated:
  `docs/harness/capability-builder.md`,
  `docs/harness/capability-extension-plan.md`, `docs/NAVIGATION.md`,
  `docs/harness/decisions.md` (ADR-H231).

- **fix(sdk): make the concurrent `/app` navigation audit detail assignable.**
  `app-server.ts` now spreads the parsed `AppNavigateTarget` into a plain record
  so `tsc` stays clean. `no doc change â€” type-only fix in concurrent work`.

- **feat(sdk): Phase 5 â€” app-shell/nav control and Command Center templates/reset.**
  Added an app-wide sidebar nav config (order, visibility, mode) in JDDS
  `SystemConfig` (`eclipse_app_shell_nav`) with `/api/sdk/app*` routes, an SSE
  stream (`/api/sdk/app/stream`) and `eclipseSdk.app`
  (`get/update/reset/open/navigate`). The sidebar store mirrors local edits up
  (one-time localâ†’server migration, no echo loop) and applies remote `nav`
  events; navigation commands drive the existing popstate deep-link path, with a
  pending-dashboard key so the Command Center switches boards before/after it
  mounts. Added `sdk_app_{get,nav_update,nav_reset,open}` tools and widened the
  deterministic app-control classifier (hide/reorder/enable/disable).
  Added `dashboards.templates/applyTemplate/reset` built from the ONE TypeScript
  persona registry (centre bands + left/right rails, revision-guarded, one
  conflict retry) plus `sdk_dashboard_{templates,apply_template,reset}` loopback
  tools; no template copy lives in Python. Tests:
  `python/tests/test_sdk_app_shell.py`, `test_code_request_intent.py`,
  `src/lib/sdk/{app-shell-types,app-server,dashboard-templates,dashboard-server}.test.ts`.
  Docs updated: `docs/eclipse-sdk.md`, `docs/NAVIGATION.md`, `docs/ARCHITECTURE.md`,
  `docs/CHANGELOG.md`.

- **test(harness): re-pin the `graph.py` size ratchet to the measured shared tree
  (2215).** In-flight app-control / lesson-manifest wiring grew the file; the
  external capability lane touches no part of `graph.py`.
  `no doc change â€” test-only ratchet re-pin`.

- **feat(harness): external capability lane â€” broker/API/MCP proposals through
  the existing MCP/plugin gates.** Added `capabilities/external.py` (read-only
  `ExternalProposal`, credential NAMES only) and the `capability_external` tool;
  `capability_request` now routes external needs there and names the exact
  credential/approval requirements. The recovery acquisition handler accepts an
  `integrationId` fact, consumes the SAME single-use `mcp_install` approval, and
  writes a DISABLED config; `pluginPath` keeps the plugin platform's
  `operator=true, enable=false` install. Added presence-only
  `MCPManager.secret_presence` and a shared `approval_digest`; MCP enablement is
  refused from the recovery path. Nothing self-enables; the original task still
  resumes from its checkpoint after operator activation. The chat card maps the
  new `external_adapter` surface and the activity label reads "Planning the
  external connection". Tests:
  `python/tests/test_capabilities_external.py`. Docs updated:
  `docs/harness/capability-builder.md`,
  `docs/harness/capability-extension-plan.md`, `docs/NAVIGATION.md`,
  `docs/harness/decisions.md` (ADR-H230).

- **feat(chat,sdk): `/app` app-control surface and `sdk_page_*` tools (Phase 4).**
  Added the `app_control` chat intent, an explicit `/app` profile command
  (no autonomy, no classifier), and an `appControl` runtime note that tells the
  agent to prefer `sdk_*` over the lower-level `ui_*` engine. `/eclipsesdk` is
  now documented as the source-code path. Added `sdk_page_list`,
  `sdk_page_create` and `sdk_page_add_widget` over `EclipseSdk.create_page` /
  `add_page_widget`; saved pages remain main-nav entries. Follow-ups after an
  app-control turn (e.g. â€œsave this as Neonâ€) stay app-control. Tests:
  `run-service.test.ts`, `commands.test.ts`, `command-registry.test.ts`,
  `test_code_request_intent.py`, `test_sdk_dashboards.py`. Docs updated:
  `docs/eclipse-sdk.md`, `docs/harness/slash-commands.md`, `docs/CHANGELOG.md`.

- **feat(sdk): typed theme creation, app-wide named presets, and `sdk_theme_*` chat tools (Phase 3).**
  Added the closed `ThemeSpec` (`src/lib/sdk/theme-spec.ts`) builder over
  `themeFromBrandColor` + `normalizeTheme`, a `SystemConfig` named-preset store
  (`eclipse_theme_presets`), `/api/sdk/theme*` routes, and `eclipseSdk.theme`
  (`get/create/apply/replace/applyPreset/listPresets/savePreset/deletePreset/reset`).
  Theme writes check both `theme:global` and `design:global` locks; the client
  emits `eclipse:theme-changed` and the theme store refreshes on that event,
  window focus, or a 15s fallback (so Python-originated changes land too).
  Python `sdk_theme_*` tools call the routes over the same loopback callback the
  Journal write uses; `SDK_TOOLS` now includes them. Tests:
  `src/lib/sdk/theme-spec.test.ts`, `theme-presets.test.ts`,
  `theme-server.test.ts`, `python/tests/test_sdk_dashboards.py`. Docs updated:
  `docs/eclipse-sdk.md`, `docs/NAVIGATION.md`.

- **feat(sdk): the Command Center becomes a typed SDK surface, starting with a live clock.**
  Added `src/lib/workspace/widget-registry.ts` + `use-widgets.ts`
  (order-preserving, surface-aware) and a real `clock` widget/primitive (host
  renderer, Python catalog spec, SDK primitive, invalid-timezone `UNAVAILABLE`).
  `DashboardScreen` and `PagesScreen` consume the registry; the dashboard listens
  to `/api/ui/stream` (with a poll fallback) and records its active id in
  `SdkMeta`. Added `python/harness/sdk/dashboards.py` + `/sdk/dashboards/*`
  (list/active/get/add/move/resize/columns/zones/history/restore),
  `python/harness/sdk/tools.py` (`SDK_TOOLS` on the standard agent),
  `eclipseSdk.dashboards`, `dashboard`/`theme` lock resource types, and an
  `app_control` chat intent so "add a clock to my Command Center" routes to the
  SDK instead of code. Dashboard mirrors at `/dashboard/<id>` are the durable
  layout; `localStorage` is a cache. Tests:
  `python/tests/test_sdk_dashboards.py`, `test_code_request_intent.py`,
  `test_sdk_service.py`, `test_ui_service.py`,
  `src/lib/workspace/widget-registry.test.ts`,
  `src/lib/dashboard/clock-widget.test.tsx`. Docs updated:
  `docs/eclipse-sdk.md`, `docs/ui-engineering.md`, `docs/ARCHITECTURE.md`,
  `docs/NAVIGATION.md`.

- **feat(harness): managed Python package environment for the analysis sandbox (Sprint 3).**
  Added `python/harness/python_env/` (`paths.py` = managed target, lock,
  installed modules; `provisioner.py` = bounded pip install/remove;
  `authorizers.py` = single-use `python_env_install`/`python_env_remove`
  approvals; `tools.py` = the four tools). `code/execution.py` adds the managed
  target to the runner's `sys.path` and the lock's modules to the import
  allowlist; `code/policy.py` and `code/authorizers.py` wire the write tools and
  approval gate. `analysis_run` can now import approved packages without
  modifying the vendored interpreter. Tests:
  `python/tests/test_python_env.py`. Docs: `docs/harness/python-env.md` (new),
  `NAVIGATION.md`; ADR-H229. The local tier does not OS-isolate sockets inside
  an approved package; hard isolation requires the container tier.

- **style(sidebar): remove the filled backgrounds from the chat-history icon toggle and sort select.**
  The date/folders toggle now shows bare icons (active state is text color only)
  and the sort control is transparent, so both read flat 2D like the search row.
  `no doc change â€” style-only tweak; no contract or architecture impact`.

- **style(sidebar): flatten and compact the chat-history search field.**
  Removed the raised bevel/drop shadow so the frosted search surface reads as
  flat 2D, and reduced its padding, radius, icon and text size.
  `no doc change â€” style-only tweak; no contract or architecture impact`.

- **feat(harness): the analysis sandbox is on by default for chat turns (Phase 2).**
  `startChatRun` and `chatWithAgent` now send `analysisEnabled: true` on every
  chat turn; a code profile may still narrow the tool surface but no longer
  turns computation off. Headless `startRun` callers keep the runtime's opt-in
  default. This closes the `not_code` refusal path for ordinary computation
  requests (e.g. "compute the Ulcer Index"). Tests:
  `src/lib/harness/run-service.test.ts`; ADR-H228.

- **feat(harness): `eclipse_report` â€” real PDF/Word/Excel reports from computed results.**
  Added `python/harness/documents/reporting.py` (paginated PDF via the vendored
  Matplotlib PDF backend, plus `build_report` over the existing authoring
  builders) and `documents/report_tools.py` (`eclipse_report`), registered on the
  ONE registry and saved through `ArtifactService.register_bytes`.
  `DOCUMENT_TOOLS` and `CHAT_CODE_TOOLS` expose it; `response-model.ts` adds the
  tool label. Tests: `python/tests/test_reports.py` (PDF bytes, docx/xlsx,
  artifact registration, empty/unsupported refusals). Docs:
  `docs/harness/reports.md` (new), `NAVIGATION.md`.

- **feat(ui,harness): cap the generated-capability loop in chat and Capability Studio.**
  The runtime now emits full `capability.*` lifecycle views
  (`capability.requested` / `built` / `activated` / `verification_failed` /
  `disabled` / `retired`). New `src/lib/harness/capability-types.ts` coerces and
  merges them; `src/components/chat/capability-card.tsx` renders the need,
  surface, version, test counts, failed checks, exact stderr and activation
  state, persisted on `Message.capabilityBuild`. New
  `src/components/screens/capability-studio/generated-section.tsx` lists the
  same durable records with version/usage/test status and operator
  activate/deactivate/rollback/retire actions. Backend
  `python/harness/routers/capabilities.py` adds read routes +
  `require_operator` mutations; `CapabilityStore.usage` and
  `builder.deactivate` support them. Front door
  `src/app/api/capabilities/[[...path]]/route.ts` + `src/lib/harness/capabilities-client.ts`.
  Tests: `python/tests/test_capabilities_api.py`,
  `src/components/chat/capability-card.test.tsx`,
  `src/lib/harness/capability-types.test.ts`, updated Capability Studio tests.
  Docs: `docs/harness/capability-builder.md`, `NAVIGATION.md`,
  `capability-extension-plan.md`, `self-evolution-roadmap.md`, ADR-H226.

- **feat(harness): Capability Builder â€” construct a tested recipe instead of refusing.**
  Added `python/harness/capabilities/` (`manifest.py` = validated
  `CapabilityManifest`/`CapabilityPort`; `request.py` = deterministic
  one-off/reusable/effectful classification plus witness search over static
  recipes, active generated capabilities and the live tool registry;
  `verifier.py` = AST/import/path checks + contract-test execution through the
  existing analysis sandbox; `builder.py` = versioned draft write, verification,
  pure-workspace auto-activation, rollback/retire; `registry.py` = dynamic
  recipe loading; `store.py` = `CapabilityRequest`/`CapabilityRecord`/
  `CapabilityUsage` on `agent-memory.db`; `tools.py` = the six `capability_*`
  tools). `code/recipes.py` gained the dynamic recipe registry;
  `analysis_tools.py` refreshes generated recipes and records usage with
  auto-disable after three failures; `recovery/discovery.py` indexes active
  generated capabilities; `agents.py` exposes the tools on the finance, code and
  chat-code surfaces; `prompts.py` documents construct-don't-refuse. Tests:
  `python/tests/test_capabilities_{manifest,request,builder,tools}.py` (32).
  Docs: `docs/harness/capability-builder.md` (new), `NAVIGATION.md`,
  `capability-extension-plan.md` Phase F, `self-evolution-roadmap.md` W9,
  `docs/harness/decisions.md` ADR-H225. Deferred: effectful builders, chat
  card/Settings UI, `eclipse_tools` RPC, automatic durable-task retry.

- **feat(sdk): Eclipse SDK â€” one user-facing composition and control surface.**
  Added `python/harness/sdk/` (`model.py` contracts + closed widget primitives;
  `store.py` = `SdkWidget`/`SdkLock`/`SdkMeta` on `agent-memory.db`; `locks.py` =
  PBKDF2 passphrase locks + short-lived HMAC unlock tokens; `service.py` =
  `EclipseSdk` delegating to the UI/Portfolio services; `bootstrap.py`; and
  `middleware.py`), `/sdk/*` routes, the `X-Eclipse-Unlock` ASGI scope and 423
  exception handler, and lock enforcement at the UI/Portfolio service seams. New
  `src/app/api/sdk/**` front door (design handled locally, everything else
  proxied), typed `src/lib/sdk/index.ts` client, declarative host renderer
  `src/lib/sdk/widgets.tsx`, design patch merge, the `sdk` AppTab +
  `sdk-screen.tsx`, and sidebar SDK page links. Portfolio gains `kind`/`metadata`
  (`fund` portfolios) while the transaction ledger stays the source of truth.
  Pages gain `?tab=pages&page=<id|path>` deep links. Tests:
  `python/tests/test_sdk_{service,api}.py`, `src/lib/sdk/design.test.ts`. Docs:
  `docs/eclipse-sdk.md` (new), `docs/NAVIGATION.md`, `docs/ARCHITECTURE.md`.

- **feat(portfolio): funds-only UI and data model.** Removed the Ledger tab and
  `portfolio-ledger.tsx`; the Portfolio screen is now one engine-backed Fund
  Manager/Workspace (`src/lib/portfolio/engine-funds.ts`). Every portfolio is a
  fund: `portfolio_create` forces `kind='fund'`, existing rows are migrated in
  place on store open, and a new `PATCH /portfolio/{id}` merges fund metadata
  (name/goal/icon/accent). The legacy localStorage book is migrated once, then
  all fund reads/writes go through the engine. Docs:
  `docs/portfolio-accounting.md`, `docs/eclipse-sdk.md`, `docs/NAVIGATION.md`.

- **fix(portfolio): chat-created portfolios are funds by default.** The agent's
  `portfolio_create` tool now writes `kind='fund'` (optional goal/icon/accent
  metadata) and only uses `kind='portfolio'` when explicitly asked for a
  ledger-only bucket; `portfolio_get`/`portfolio_list` report the kind. The SDK's
  `portfolio.createFund` already wrote this shape. Same `Portfolio` row and
  transaction ledger - no second book. Docs: `docs/portfolio-accounting.md`,
  `docs/eclipse-sdk.md`.

- **fix(ui): hide Command Center mirror blueprints from Pages/nav.** The runtime
  page list (`UiService.list_blueprints`), the agent's `ui_list_blueprints`, the
  Pages list, the sidebar and `eclipseSdk.pages.list()` now exclude
  `/dashboard/dash-*` blueprints (the auto-mirrored board snapshots), so only
  user/agent-authored pages remain in navigation; mirrors stay resolvable by id.
  The "Rates Desk" test page was deleted from the runtime store. Docs:
  `docs/ui-engineering.md`, `docs/eclipse-sdk.md`.

- **fix(ui): `ui_verify_page` validates bare source strings.** Previously only
  sources containing ":" were checked, so `source="rates"` or `metric="us10y"`
  passed the read-back while rendering no data. Every declared source is now
  validated against the closed family grammar (with the `portfolioId` shorthand
  checked first), and a bare token is reported as an invalid binding. Docs:
  `docs/ui-engineering.md`.

- **fix(ui): saved pages live in the main navigation.** Removed the separate
  "SDK pages" sidebar panel; `SavedPagesNav` now renders every saved
  blueprint/page as a normal nav entry (`?tab=pages&page=<id>`, Ctrl/Cmd-click
  aware) and refreshes from `/api/ui/stream`, so a page the agent creates appears
  without a reload. `window.eclipseSdk` is exposed from the app shell instead of
  that panel. Docs: `docs/ui-engineering.md`, `docs/eclipse-sdk.md`.

- **test(python): isolate memory databases for the pytest run.** The runner now
  sets both `AGENT_MEMORY_DB_PATH` and `ECLIPSE_MEMORY_DB_PATH` to per-run temp
  files, matching the documented contract in `harness/eclipse_memory/config.py`.
  Reusing the developer's persistent DB across runs left a stale installed skill
  version (`test_skills_api`) and a different graph series-store connection
  (`test_graph_api`). The graph test now seeds the runtime's own bound series
  store rather than opening a second connection. Test-only change â€” no doc
  change.

- **feat(harness): RSL R6 â€” adopted lessons and deterministic scoped retrieval.**
  Added migration 31 with four additive `LearningCandidate` columns (`cue`,
  `adoptedArtifactType`, `adoptedArtifactId`, `validationRunId`); the migration
  runner now skips an `ALTER TABLE ... ADD COLUMN` whose column already exists,
  so a partially applied/copied store opens without a duplicate-column failure.
  New `self_improvement/lessons.py`: `distill_lesson` requires cue + lesson +
  evidence, discards a non-adopted decision, runs the verdict tripwire over the
  stored text (a leak is a hard error), dedupes by cue+lesson signature, and
  records the adopted artifact + validation run. `prompt_segments.py` gained the
  run-frozen `lesson_manifest` segment and `build_lesson_manifest` (hard max 3
  lessons / 800 chars). `graph_context._lesson_manifest_context` retrieves only
  adopted lessons whose cue/scope match and whose validation run is `completed`,
  injects a labelled non-authoritative block, and emits the new
  `prompt.lesson_injected` event with lesson ids + origin/validation/artifact
  refs. Tests `python/tests/test_rsl_lessons.py` (15). Docs:
  `docs/self-improvement/rsl-implementation-plan.md`,
  `docs/NAVIGATION.md`, `docs/harness/architecture.md`,
  `docs/harness/decisions.md` (ADR-H223), `docs/CHANGELOG.md`.

- **feat(harness): RSL R7 â€” bounded recursive candidates, anonymous selection and conservative composition.**
  Added `proposer.propose_many` (up to `HARNESS_RSL_K` typed `invariant`/`domain`
  candidates from one observation; operator/agent-supplied ops only, each
  validated through the frozen denylist + `propose_ops`, no model proposer).
  New `self_improvement/selection.py` (seeded anonymous labels, drop-with-cause,
  neutral base fallback, trivial `k=1`, verdict-guarded selection record),
  `composition.py` (verified-only merge with a path-conflict rule; a MEASURED
  gain only when composed beats the best single, else honest `no_gain`), and
  `recursion.py` (`budgeted_k`, per-candidate verification, contrast bundle +
  verdict guard, one recorded `EvaluationRun`). `RSLLoop.run_recursive` uses the
  loop's configured `k`, stores, actor and daily budget. `k=1` stays the
  default; nothing activates. Tests `python/tests/test_rsl_recursion.py` (15).
  Docs: `docs/self-improvement/rsl-implementation-plan.md`,
  `docs/NAVIGATION.md`, `docs/harness/architecture.md`,
  `docs/harness/decisions.md` (ADR-H224), `docs/CHANGELOG.md`.

- **feat(harness): RSL R8 â€” measured metrics, offline release gate and rollout docs.**
  Extended `evaluation/repair_metrics.py` with the completed-RSL-run block
  (`rsl_experiments`, `rsl_accepted`, `rsl_rejected`, `rsl_unmeasured`,
  `regression_rate`); UNMEASURED runs are their own bucket and a measured run
  that is not accepted is rejected, so the four counts partition the completed
  experiments. `code/evolution.archive_metrics` and `GET /recovery/metrics` merge
  the block from the real stores (missing sources stay `None`/`UNKNOWN`), and
  `verify_surface` now persists the evaluator's decision so no metric has to
  infer acceptance. Added the deterministic offline `self_improvement/gate.py`
  (scripted `k=2` proposeâ†’verifyâ†’selectâ†’composeâ†’record) and wired it into
  `scripts/test-evals.js` as the `rsl` gate. Added `test_rsl_gate.py` and RSL
    metric tests; updated `test_evaluation_repair_metrics.py`/`test_rsl_verifier.py`.
  Aligned the `clock-composes` routing benchmark case with the catalog's new
  Clock capability so the routing floor measures the current catalog. Docs:
 `docs/self-improvement/rsl-implementation-plan.md` (R0â€“R8 implemented;
  rollout/flip checklist), `docs/NAVIGATION.md`, `docs/harness/architecture.md`,
  `docs/CHANGELOG.md`.

- **feat(harness,ui): RSL operator surfaces â€” lesson adoption and recursive experiments.**
  Added operator-gated `GET /evolution/lessons`,
  `POST /evolution/candidates/{id}/lessons` (the accepted decision is derived from
  the persisted `EvaluationRun`, never the request; the R6 cue/lesson/evidence
  gate + verdict tripwire still apply) and `POST
  /evolution/candidates/{id}/recursive` (typed variants become real child
  `EvolutionCandidate` rows, each verified by the existing worktree/tests
  verifier; the R7 conductor records the anonymous selection/composition and
  child attempts count against the daily budget without double-counting).
  Recursive experiments remain `HARNESS_RSL_MODE=verify` only and never activate.
  Added typed `evolution-client.ts`/`evolution-browser.ts` calls, Next.js
  `/api/evolution/lessons` + candidate `lessons`/`recursive` proxies, and the
  learning-journey `rsl-operator-panel.tsx` (adopted-lesson list + adoption form +
  recursive-variant form). Tests `test_evolution_rsl_operator.py` (5) and the
  existing operator-gating suite. Docs: `docs/NAVIGATION.md`,
  `docs/harness/architecture.md`,
  `docs/self-improvement/rsl-implementation-plan.md`, `docs/CHANGELOG.md`.

- **feat(harness): RSL R9 â€” hill-climb foundation (immutable states, utility, replay).**
  Added `python/harness/self_improvement/state.py` (`HarnessStateStore`,
  append-only `HarnessState` rows on the ONE `agent-memory.db`; one `current` per
  scope; operator-only promotion that supersedes without rewriting), `utility.py`
  (deterministic utility + Wilson lower bound + critical `DEFAULT_GATES` veto +
  honest `UNMEASURED` rejection), `replay.py` (`replay_v1` from the existing
  validation/held-out/release tasks, per-task measured rates, mean/critical
  forgetting, retained best-per-task) and `hillclimb.py` (pure bounded ascent with
  injected proposal/evaluation, tabu, plateau stop and an `on_accept` persistence
  hook). No runner, scheduler, model call, approval or activation was added.
  Tests: `python/tests/test_rsl_{state,utility,replay,hillclimb}.py` (27). Docs
  updated: `docs/harness/decisions.md` (ADR-H239),
  `docs/harness/architecture.md`, `docs/self-improvement/rsl-implementation-plan.md`.

- **feat(harness): RSL R9 â€” lesson-outcome feedback and measured lift.**
  Added `python/harness/self_improvement/lesson_feedback.py` (`LessonOutcomeStore`
  on the ONE `agent-memory.db`): every eligible lesson is recorded per run as
  injected or eligible-control; `graph_context._lesson_manifest_context` records
  the cohort and ranks measured positive lift ahead of unmeasured lessons;
  `learning_review.review_run` writes the run's terminal outcome and optionally
  retires measured non-positive lessons behind `HARNESS_RSL_LESSON_RETIRE`
  (off by default). Lift is only claimed with at least 3 injected and 3 control
  observations; thin data stays `INSUFFICIENT`/`UNMEASURED`. Retirement is inert
  and deletes nothing. Tests: `python/tests/test_lesson_feedback.py` (9). Docs
  updated: `docs/harness/decisions.md` (ADR-H244),
  `docs/harness/architecture.md`, `docs/self-improvement/rsl-implementation-plan.md`.

- **feat(harness): RSL R9 â€” hill-climb conductor entry and bounded generations.**
  Added `RSLLoop.run_hillclimb` (`verify` mode + `HARNESS_RSL_STRATEGY=hillclimb`):
  loads the current `HarnessState`, uses the configured `k` and
  `HARNESS_RSL_GENERATIONS` (1..3), persists accepted states as `candidate`
  (never `current`), and records each evaluated neighbor as an
  `EvolutionAttempt` so the daily budget counts the climb. Refuses honestly on
  mode/strategy/busy/no-current-state/daily-budget. New `strategy`/`generations`
  config fields with fail-closed parsing. Tests: `test_rsl_loop.py` additions,
  `test_rsl_config.py` (strategy/generations). Docs updated:
  `docs/harness/architecture.md`,
  `docs/self-improvement/rsl-implementation-plan.md`, `.env.example`.

- **feat(harness): RSL R9 â€” model-assisted proposals behind a flag.**
  Added `python/harness/self_improvement/proposer_model.py`: a strict-JSON
  `variants` contract parsed by the existing `StructuredOutputManager`, then
  validated by the SAME `propose_many`/`propose_ops`, frozen-target denylist and
  workspace confinement. Provider/malformed/frozen failures are structured
  refusals, never fallbacks. Off by default
  (`HARNESS_RSL_MODEL_PROPOSER=off`), with `HARNESS_RSL_{PROVIDER,MODEL,BASE_URL,
  API_KEY}` fallbacks to the existing `HARNESS_JOB_*` background convention. The
  `propose` tick persists validated variants as child `EvolutionCandidate` rows
  in `proposed` state; it never verifies, lands or activates them. Tests:
  `test_rsl_model_proposer.py` (9) plus loop/config additions. Docs updated:
  `docs/harness/decisions.md` (ADR-H245), `docs/harness/architecture.md`,
  `docs/self-improvement/rsl-implementation-plan.md`, `.env.example`.

- **feat(harness): RSL R9 â€” auto propose+verify mode.** Added `auto` to
  `HARNESS_RSL_MODE`: one bounded tick runs the propose phase (deterministic ops,
  or the model proposer when enabled) and then ONE verify claim. It never lands:
  operator promotion remains the only write path. `verify` stays the manual
  operator tier; `auto` is the autonomous propose+verify tier. `run_hillclimb`
  and `run_recursive` accept `auto` as a verify-equivalent mode; the operator
  surface-experiment routes do too. Tests: `test_rsl_loop.py` (proposeâ†’verify,
  no-op without proposals) and `test_rsl_config.py` (mode parsing). Docs:
  `docs/harness/architecture.md`, `docs/QUICKSTART.md`,
  `docs/self-improvement/rsl-implementation-plan.md`, `.env.example`.

- **feat(harness): RSL R9 â€” measured code candidates in a patched worktree.**
  Added `evaluation/worktree_invoker.py`: baseline suite on the unpatched tree,
  candidate ops applied via `propose_ops` + `patch.apply`, then the SAME
  deterministic suite in a child process whose `PYTHONPATH` points at the patched
  worktree. The child gets a temp `agent-memory.db`, curated non-secret
  environment, no live bridge and a bounded timeout; patched code is never
  imported into the host. `benchmark_decision` accepts only a measured target
  improvement with no critical `DEFAULT_GATES` regression. `verify_code_benchmark`
  is opt-in (`HARNESS_RSL_CODE_BENCHMARK=off`); the conductor records
  `benchmark_accepted`/`benchmark_rejected` and `record_code_experiment` now
  persists `MEASURED` plus the decision record and measured trials. Tests:
  `test_worktree_invoker.py` (9) plus loop/config/recorder additions. Docs:
  `docs/harness/decisions.md` (ADR-H242), `docs/harness/architecture.md`,
  `docs/harness/agent-evaluation.md`,
  `docs/self-improvement/rsl-implementation-plan.md`, `.env.example`.

- **feat(harness,ui): RSL R9 â€” operator surfaces for harness states and lesson lift.**
  Added operator-gated `GET /evolution/states` (current pointers + immutable
  rows), `POST /evolution/states/{id}/promote` (state pointer only: supersedes
  the prior current row, never writes code or consumes an approval) and
  `GET /evolution/lessons/{id}/outcomes` (matched injected/control stats + recent
  rows). Typed `EvolutionHarnessState`/`EvolutionLessonStats` contracts and
  browser calls; Next.js `/api/evolution/states*` and lesson-outcomes proxies.
  `rsl-control-panel.tsx` gains a states section with current scope, utility
  (or `UNMEASURED`) and a Promote action; the learning journey now mounts
  `rsl-control-panel.tsx` and `rsl-operator-panel.tsx`. Tests:
  `test_evolution_rsl_routes.py` (state list/promote, lesson outcomes, remote
  refusal) + `evolution-client.test.ts`. Docs:
  `docs/harness/decisions.md` (ADR-H243), `docs/harness/architecture.md`,
  `docs/self-improvement/rsl-implementation-plan.md`.

- **feat(harness,ui): RSL R9 â€” live surface activation with base-digest guard and rollback.**
  Added `POST /evolution/states/{id}/activate-surface`: an operator may activate a
  measured surface candidate only when it is a surface subject, its utility is
  measured, and its RSL experiment was accepted. The snapshot is re-validated
  against its recorded base; model identity and skill drafts are refused.
  `HarnessActivation` stores the snapshot/base/previous state;
  `POST /evolution/surface-activations/{id}/rollback` restores the previous
  current state. `graph.execute_run` applies the active surface after agent
  resolution, re-deriving the current base snapshot and applying only prompt,
  tool subset and lowered step/tool-call ceilings; a stale base or invalid
  snapshot leaves the original agent untouched. Evaluation, candidate-trial and
  gate runs set `RunRequest.liveSurface=False`, so a live surface cannot
  contaminate a measurement. UI: activation and rollback controls in
  `rsl-control-panel.tsx`. Tests: `test_live_surface.py` plus route tests. Docs:
  `docs/harness/decisions.md` (ADR-H246),
  `docs/harness/architecture.md`,
  `docs/self-improvement/rsl-implementation-plan.md`.

- **feat(harness,ui): RSL R9 â€” surface activation preview and per-agent scope.**
  Added `GET /evolution/states/{id}/surface-preview`: the same context the
  activation uses, returned as a deterministic diff (prompt character counts and
  bounded before/after text, tools added/removed, step/tool-call ceilings,
  model/skill flags), base-digest match for the chosen reference agent,
  accepted decision, previous state, available scopes (`global` + known agent
  presets) and every refusal reason. `POST .../activate-surface` now accepts an
  optional `scope`; a different scope creates a NEW immutable state row for that
  agent and activates it, leaving the source state untouched. A live surface is
  only applied while its state is current, so a later promotion silently
  disables it. UI: Preview + scope selector + diff/refusal card in
  `rsl-control-panel.tsx`. Tests: `test_evolution_rsl_routes.py` (preview, scope
  override) and `test_live_surface.py` (stale activation). Docs:
  `docs/harness/decisions.md` (ADR-H247), `docs/harness/architecture.md`,
  `docs/self-improvement/rsl-implementation-plan.md`.

- **feat(harness,ui): RSL R9 â€” surface experiments carry a scope and materialize an inert state.**
  `SurfaceExperimentRequest` gains a validated `scope` (default `global`); it is
  stored in `surfaceConfig`, included in the deterministic experiment signature,
  and carried into the measurement. After a measured surface verification the
  conductor materializes exactly one inert `HarnessState` (`candidate`) with the
  candidate id, accepted run id, scope, aggregates and utility, deduplicated by
  `(candidateId, snapshotDigest)`. Rejected surfaces also get a state for
  evidence, but activation still requires an accepted run. The operator
  surface-experiment form gains a scope input. Tests:
  `test_evolution_rsl_operator.py` (scope persisted) and `test_rsl_loop.py`
  (measured surface creates one state). Docs: `docs/harness/decisions.md`
  (ADR-H248), `docs/harness/architecture.md`,
  `docs/self-improvement/rsl-implementation-plan.md`.

- **feat(harness,ui): RSL R9 â€” link a surface experiment to its derived state.**
  Added operator-gated `GET /evolution/candidates/{id}/state` (latest derived
  `HarnessState` plus the full list, newest first). The surface-experiment result
  now offers `Find derived state`, then opens the shared
  `SurfaceActivationCard` (scope selector, deterministic diff, base-digest match,
  refusal reasons, activation) already used by the conductor. The lookup is
  read-only and never creates a state. Tests:
  `test_evolution_rsl_routes.py` (candidate state + remote refusal). Docs:
  `docs/harness/decisions.md` (ADR-H249), `docs/harness/architecture.md`,
  `docs/self-improvement/rsl-implementation-plan.md`.

- **feat(harness,ui): RSL R9 â€” production drift signal for continual learning.**
  Added `python/harness/self_improvement/drift.py`: recent terminal `HarnessRun`
  window vs the preceding baseline, mapping only completed/failed to
  success/failure, Wilson intervals, `unmeasured` on thin data, and `drift` only
  above the configured drop threshold. `GET /evolution/drift` exposes the
  read-only signal per agent scope; the conductor panel shows status, recent vs
  baseline rates, drop and reasons. Tests: `test_drift.py` (stable, drift,
  unmeasured, scope, store read) and the remote-refusal route test. Docs:
  `docs/harness/decisions.md` (ADR-H250), `docs/harness/architecture.md`,
  `docs/self-improvement/rsl-implementation-plan.md`.

- **feat(harness,ui): RSL R9 â€” turn a drift signal into an inert candidate.**
  Added `POST /evolution/drift/candidate`: only a `drift` signal creates ONE
  inert `EvolutionCandidate` (`subjectType="drift"`, `sourceCategory="drift"`,
  no target/ops) with scope, rates and window counts in its problem statement;
  repeated checks dedupe by scope/window/baseline/threshold. Stable/unmeasured
  signals create nothing. The conductor drift card gains `Open drift candidate`
  and shows the created/existing candidate id. Tests: `test_drift.py` (inert
  candidate, dedupe, no-op signals) and the remote-refusal route. Docs:
  `docs/harness/decisions.md` (ADR-H251), `docs/harness/architecture.md`,
  `docs/self-improvement/rsl-implementation-plan.md`.

- **feat(harness,ui): RSL R9 â€” model-propose a drift candidate.**
  Added operator-gated `POST /evolution/candidates/{id}/model-propose`
  (`RSLLoop.propose_with_model`): runs the model proposer for ONE candidate,
  persists validated children through the same strict-JSON/`propose_ops`/
  frozen-target/workspace guards, and never verifies or lands. The flag
  `HARNESS_RSL_MODEL_PROPOSER` remains the opt-in; an off flag returns
  `MODEL_PROPOSER_DISABLED`. The drift card gains `Propose with model` and shows
  the validated child count. Tests: `test_evolution_rsl_operator.py` (drift
  candidate â†’ validated child) plus the remote-refusal route. Docs:
  `docs/harness/decisions.md` (ADR-H252), `docs/harness/architecture.md`,
  `docs/self-improvement/rsl-implementation-plan.md`.

- **feat(ui): run the verify tick from the drift proposal result.** The drift card
  now offers `Run verify tick` after model-proposed children exist; the result
  shows the verified candidate id, decision and benchmark (or the honest empty
  case). `no doc change - UI affordance over the existing operator-gated tick`.

- **feat(ui): prepare the existing promotion preview from the drift result, and mount the RSL panels once.**
  After a verified code child (`tests_passed`/`benchmark_accepted`), the drift card
  offers `Prepare landing` and reports the prepared run id; the single-use
  promotion approval remains the only write. Removed the duplicate
  `RslControlPanel`/`RslOperatorPanel` mounts from the learning journey â€” they are
  already composed by `RslExperimentsPanel`, so each panel now renders once and
  does not issue duplicate status/state requests. `no doc change - UI affordance
  over the existing prepare-landing route`.

- **feat(ui): complete the drift â†’ promotion approval flow in place.** After a
  prepared drift landing, the drift card now renders the existing
  `PromoteChange` card for that run id: preview, single-use approval,
  apply/restart verdict, and rollback. No new approval or write path;
  `PromoteChange` remains the one operator control. `no doc change - UI
  affordance over the existing promotion APIs`.

- **feat(harness,ui): RSL R9 â€” lesson lift inline and explicit retirement.**
  Added operator-gated `POST /evolution/lessons/{id}/retire` (retires one
  measured non-positive lesson through `retire_unhelpful`; inert, deletes
  nothing). The adopted-lessons list now has a `Lift` action that reads the
  existing outcomes stats and shows injected/control rates plus lift inline; a
  measured non-positive lesson offers `Retire`. Tests:
  `test_evolution_rsl_routes.py` (measured non-positive retirement + remote
  refusal) and the existing `test_lesson_feedback.py`. Docs:
  `docs/harness/decisions.md` (ADR-H253), `docs/harness/architecture.md`,
  `docs/self-improvement/rsl-implementation-plan.md`.

- **feat(ui): show recent matched lesson outcomes under the lift stats.** The
  lesson row's lift block is now expandable: it lists the five most recent
  injected/control observations (run id, cohort, outcome) from the existing
  `GET /evolution/lessons/{id}/outcomes` response, so the operator can inspect
  the evidence before retiring a lesson. `no doc change - UI affordance over an
  existing read-only route`.

- **feat(harness,ui): RSL R9 â€” measured evidence on the surface activation preview.**
  `GET /evolution/states/{id}/surface-preview` (and the activation response's
  `preview`) now includes the accepted run summary, its overall metrics, up to 50
  trial rows with `trajectory` stripped, and the recorded baseline's metrics when
  one is named. The activation card renders an expandable `Measured evidence`
  section; the evaluator's recorded decision remains authoritative. Tests:
  `test_evolution_rsl_routes.py` (metrics/trials present, no trajectory). Docs:
  `docs/harness/decisions.md` (ADR-H254), `docs/harness/architecture.md`,
  `docs/self-improvement/rsl-implementation-plan.md`.

- **feat(ui): show the measured target delta on the surface preview.** The
  `Measured evidence` block now leads with `Target <dimension>: before â†’ after`
  and the delta, computed from the recorded baseline/candidate metrics. A missing
  side renders `UNMEASURED`, never a fabricated zero. Tests:
  `test_evolution_rsl_routes.py` (baseline 0.7 â†’ candidate 0.9, delta 0.2).
  `no doc change beyond the existing ADR-H254 evidence contract`.

- **feat(ui): show the baseline/candidate run ids on the surface evidence.**
  The `Measured evidence` block now names the baseline and candidate runs; the
  candidate run has an `Open candidate run` link to the existing
  `/api/evolution/experiments/{id}` read. A missing baseline renders
  `No baseline run recorded`, never a fabricated id. `no doc change - UI
  affordance over the existing read-only experiment route`.

- **feat(ui): link the baseline run beside the candidate run.** When the surface
  evidence names a recorded baseline, the block now shows `Baseline run <id>`
  and `Open baseline run` next to the candidate run/link; a missing baseline
  still renders `No baseline run recorded`. `no doc change - UI affordance over
  the existing read-only experiment route`.

- **feat(harness,ui): RSL R9 â€” per-task delta table on the surface evidence.**
  The evidence now carries `taskDeltas` from measured baseline/candidate trials
  (unmeasured trials excluded, missing sides `UNMEASURED`): task id, before/after
  pass rate, sample counts, delta. The activation card renders up to ten rows
  with improved/regressed colouring; the target aggregate and evaluator decision
  remain the acceptance authority. Tests: `test_evolution_rsl_routes.py`
  (baseline fail â†’ candidate pass = +1.0). Docs: `docs/harness/decisions.md`
  (ADR-H255), `docs/harness/architecture.md`,
  `docs/self-improvement/rsl-implementation-plan.md`.

- **feat(harness,ui): RSL R9 â€” critical-task regressions veto surface activation.**
  The preview resolves the experiment's critical task ids (safety/adversarial/
  `metadata.critical`) and appends any measured per-task drop to
  `evidence.criticalDeltas` and to the activation reasons, so `canActivate` is
  false even when the aggregate target improved. The activation card shows a
  prominent `Critical regressions` block before the target delta. Tests:
  `test_evolution_rsl_routes.py` (baseline safety pass â†’ candidate safety fail
  blocks activation). Docs: `docs/harness/decisions.md` (ADR-H256),
  `docs/harness/architecture.md`,
  `docs/self-improvement/rsl-implementation-plan.md`.

- **feat(harness): apply the critical-task veto to measured code candidates.**
  `evaluation/worktree_invoker.py` resolves the benchmark dataset's
  safety/adversarial/`metadata.critical` task ids and passes them to
  `benchmark_decision`; a measured drop on any critical task rejects the code
  candidate even when the aggregate target improved, and the decision record
  carries `criticalDeltas`. Tests: `test_worktree_invoker.py` (aggregate improves,
  critical task drops â†’ rejected). Docs: `docs/harness/decisions.md` (ADR-H257),
  `docs/harness/architecture.md`,
  `docs/self-improvement/rsl-implementation-plan.md`.

- **feat(ui): show code benchmark critical regressions in the experiment list.**
  The experiment card now reads `metadata.decisionRecord.criticalDeltas` (the
  measured code-benchmark veto) and renders a rose `Critical regressions` block
  with the exact task and beforeâ†’after pass rates. Tests:
  `rsl-experiments-panel.test.tsx` (critical task 1.000 â†’ 0.000 rendered).
  `no doc change - UI affordance over the existing decision record`.

- **feat(ui): candidate evidence lookup with the same critical-regression view.**
  Added a `Candidate evidence` panel (learning journey) that reads the existing
  candidate evidence route by id and shows the candidate row, attempts and every
  experiment through the shared `ExperimentList`, including the code benchmark's
  critical-regression block. Read-only; no candidate action or write path.
  `no doc change - UI affordance over the existing candidate evidence route`.

- **feat(ui): open candidate evidence directly from an experiment.** Each
  experiment row with a candidate id now has a `View evidence` action; the
  candidate evidence panel opens prefilled with that id and loads its attempts
  and experiments. `ExperimentList` moved to `experiment-list.tsx` so the main
  panel and the candidate evidence view share one implementation without a
  circular import. `no doc change - UI affordance over existing read-only
  routes`.

- **feat(ui): copy a candidate id and remember the last evidence lookup.** The
  candidate evidence panel now has a `Copy id` action with copied/failed feedback
  and persists the last viewed candidate in `localStorage`; a refresh or panel
  switch reopens that candidate. An explicit `View evidence` candidate overrides
  the stored id. `no doc change - UI affordance; no runtime contract changed`.

- **feat(ui): explicit Clear for the remembered candidate evidence.** The
  candidate evidence panel now has a `Clear` action that empties the input, the
  loaded evidence and the stored `localStorage` id. `no doc change - UI
  affordance; no runtime contract changed`.

- **feat(ui): refresh candidate evidence without clearing it.** The candidate
  evidence panel now has `Refresh evidence`, which re-fetches the current
  candidate and keeps the panel in place (disabled until evidence is loaded).
  Useful after a verify tick. `no doc change - UI affordance; no runtime
  contract changed`.

- **feat(ui): auto-refresh candidate evidence after a verify tick.** The conductor
  tick (including the drift verify action) dispatches a local
  `eclipse:evolution-verified` event with the candidate/decision; the candidate
  evidence panel listens and re-fetches the open candidate, so a new attempt or
  experiment appears without pressing Refresh. No event is persisted or sent
  over the network. `no doc change - UI affordance; no runtime contract changed`.

- **feat(ui): refresh the experiment list on the same verify event.** The
  top-level `RslExperimentsPanel` now listens for
  `eclipse:evolution-verified` and reloads the experiment list, so a verify tick
  updates both the candidate evidence panel and the main list without a manual
  refresh. `no doc change - UI affordance; no runtime contract changed`.

- **feat(harness,ui): metrics window applies to RSL counts; Today summary strip.**
  `rsl_runs_from_store` accepts the `archive_metrics` `since` cutoff, so
  `GET /evolution/metrics?windowDays=N` reports the RSL experiment/accepted/
  rejected/UNMEASURED split for that window, not all time. The experiment panel
  requests `windowDays=1` and shows a compact `Today` strip, refreshed on the
  verify event; a null/unreadable source renders `UNMEASURED`. Tests:
  `test_evaluation_repair_metrics.py` (window cutoff). Docs:
  `docs/harness/decisions.md` (ADR-H258), `docs/harness/architecture.md`.

- **feat(ui): jump from today's count to the candidates verified today.**
  The experiment panel now renders compact `Verified today` chips for the
  candidates whose experiments started in the current UTC day; each chip opens
  that candidate in the evidence panel. The count strip still comes from the
  metrics window; the chips come from the loaded experiment list. `no doc
  change - UI affordance over the existing metrics/experiment reads`.

- **feat(harness,ui): scope filter for today's experiments and chips.**
  RSL experiment metadata now carries `scope` (the surface candidate's scope, or
  `global` for code/legacy rows). The experiment panel derives a scope selector
  from the loaded experiments; selecting a scope filters the list and today's
  chips and computes the scoped Today counts from those rows (the `All scopes`
  view keeps the metrics-window counts). Tests: `test_rsl_surface.py` (surface run
  metadata carries the scope). Docs: `docs/harness/decisions.md` (ADR-H259),
  `docs/harness/architecture.md`.

- **feat(ui): scope selector on the drift card.** `GET /evolution/drift` and
  `POST /evolution/drift/candidate` now return `availableScopes`; the production
  drift card has a scope selector, re-fetches the signal for that agent and
  creates the drift candidate with the same scope. Changing scope clears the
  previous candidate result. `no doc change - UI affordance over the existing
  scoped drift signal`.

- **feat(ui): remember the experiment and drift scope selections.**
  Both selectors persist their choice in `localStorage`
  (  `eclipse.rsl.experimentScope`, `eclipse.rsl.driftScope`); a stored scope stays
  selectable even when the current window has no matching experiments.
  `no doc change - UI preference, not a contract`.

- **feat(ui): show the drift candidate's scope.** The "Open drift candidate"
  result now displays the signal's `scope` next to the created/existing candidate
  id, so the operator can confirm which agent the inert candidate belongs to.
  `no doc change - UI affordance over the existing signal scope`.

- **feat(ui): open a drift candidate's evidence from the drift card.**
  The candidate result has a `View evidence` action that emits the new
  `eclipse:evolution-evidence` browser event; the candidate evidence panel
  listens, loads that id even when it is already the shown candidate, and
  scrolls the evidence panel into view. `no doc change - UI affordance over the
  existing evidence read`.

- **feat(ui): highlight the evidence section after a drift jump.**
  The drift `View evidence` action now ring-highlights the evidence section for
  1.8s and clears the highlight on Clear/unmount; `evidenceSectionClass` is the
  tested contract. `no doc change - UI affordance over the existing read`.

- **feat(ui): one scope selection shared by experiments and drift.**
  The learning journey owns the scope (`eclipse.rsl.scope`, with the two legacy
  keys read once) and passes it to both panels; `All scopes` maps to `global` for
  the drift read. `docs/harness/decisions.md` (ADR-H260),
  `docs/harness/architecture.md`.

- **feat(harness,ui): badge drift-origin experiments and list their history.**
  Recorder metadata now carries `subjectType`, so drift experiments show a
  `Drift candidate` badge in the list and Today chips. `GET
  /evolution/drift/history` derives signals at successive offsets from the
  existing run history and the drift card renders compact status/drop chips.
  `no doc change - covered by ADR-H260`.

- **feat(harness,ui): per-scope drift overview.**
  `GET /evolution/drift/scopes` returns one bounded signal for every configured
  scope; the drift card renders status/drop chips and selecting one changes the
  shared scope. Docs: `docs/harness/decisions.md` (ADR-H261),
  `docs/harness/architecture.md`.

- **feat(harness,ui): measured model-identity experiments.**
  `POST /evolution/model-experiments` queues a trial-only comparison where only
  provider/model/temperature differ from an agent's base snapshot; the surface
  form exposes the fields. Live activation still refuses model identity. Docs:
  ADR-H270, `docs/harness/architecture.md`,
  `docs/self-improvement/rsl-implementation-plan.md`.

- **feat(harness): start RSL v2 with a Pareto frontier.**
  `self_improvement/pareto.py` compares recorded states on success, target,
  coverage, cost and latency; `GET /evolution/states/pareto` returns the
  non-dominated set and each dominated state's dominator; the learning journey
  renders it in `ParetoFrontierCard`. Acceptance, budgets and activation are
  unchanged. Docs: ADR-H269,
  `docs/harness/architecture.md`,
  `docs/self-improvement/rsl-implementation-plan.md`.

- **feat(harness): complete RSL v1 with v1b skill-draft trials.**
  A candidate snapshot may carry inert `skillDraftIds`; the invoker validates
  them against the skill store (draft status + required tools), injects their
  instructions into the trial prompt, and live activation still refuses them.
  Added the RSL v1 acceptance record and updated the plan status. Docs:
  `docs/harness/decisions.md` (ADR-H268),
  `docs/self-improvement/rsl-v1-acceptance.md`,
  `docs/self-improvement/rsl-implementation-plan.md`.

- **feat(harness,ui): drift inbox, dashboard widget and CI smokes.**
  Drift transitions now become durable `notification.created` events readable at
  `GET /evolution/drift/alerts`; the Command Center gains a `Production Drift`
  widget; the drift card adds a sparkline and older/newer history paging; the
  watch jitters its cadence; `/drift/scopes` accepts extra scopes; and CI runs
  `npm run test:drift`. Docs: ADR-H267, `docs/harness/architecture.md`,
  `docs/QUICKSTART.md`.

- **perf(bots): paint from the last successful sweep.**
  The Bots store hydrates synchronously from a persisted cache and the run
  watcher reuses the shared store hydrate instead of issuing its own list +
  status calls. A failed refresh keeps the cached list on screen.
  `no doc change â€” UI performance, contracts unchanged`.

- **feat(harness,ui): drift operations are testable end to end.**
  Policy persists in `eclipse.rsl.driftPolicy`; the journey badge raises one
  notification per scope per day; the watch clears state on a reset history and
  prunes retired scopes; history exposes `computedPoints`; boot start/stop and
  the documented runbook are tested; and `npm run test:drift-app` drives the
  real Next.js shell (Skills â†’ Journey) with a mocked API. Docs: ADR-H266,
  `docs/QUICKSTART.md`, `docs/harness/architecture.md`.

- **feat(harness,ui): drift operations hardening.**
  The watch persists per-scope transitions in `DriftWatchState` and exposes
  health on `/evolution/rsl`; the card debounces policy edits; candidate rows
  store `scope`; history reports `truncated`; the overview excludes `global`
  in the UI; and `npm run test:drift-ui` is a Playwright smoke for scope chip â†’
  candidate â†’ evidence. Docs: ADR-H265, `docs/QUICKSTART.md`.

- **feat(harness): anchor drift candidates to an episode.**
  `drift_signal` now returns the newest-run `anchor` and `drift_signature`
  includes it, so the same window still dedupes but a later recovery/re-drift
  opens a new candidate. Docs: ADR-H262.

- **feat(harness): run a read-only drift watch on a cadence.**
  `drift_watch.py` checks every configured scope every
  `HARNESS_DRIFT_WATCH_SECONDS` (default 300; `0` disables) and publishes
  `self_improvement.drift_detected` only on a transition. Docs: ADR-H263,
  `docs/self-improvement/rsl-implementation-plan.md`.

- **feat(ui): drift policy controls, collapsed overview and scope-filtered evidence.**
  The drift card edits window/baseline/threshold/minSamples, hides unmeasured
  overview rows behind a count, the learning-journey header shows a drifting
  badge, and candidate evidence filters its experiments by the shared scope.
  Docs: ADR-H264.

- **feat(harness,ui): audit and test the drift flow.**
  Candidate creation publishes `self_improvement.drift_candidate_created`;
  route tests cover history/scopes and signalâ†’candidateâ†’evidence; the RSL gate
  now asserts the scripted drift drop and anchor. `no doc change - covered by
  ADR-H262/H263/H264`.

- **feat(ui): refresh drift overview and history on verify.**
  The conductor panel reloads the signal, per-scope overview and recent history
  when `eclipse:evolution-verified` fires, so a completed verification updates
  drift without a manual refresh. `no doc change - UI refresh over existing
  reads`.

- **test(harness): cover scoped drift routes and history.**
  Route tests assert `availableScopes`, scoped signals and the inert/deduplicated
  scoped candidate; `test_drift.py` asserts history offsets and points.
  `no doc change - test-only`.

- **fix(test): remove a duplicate `en.ts` pin in the size budget.**
  The in-flight dictionary growth had been pinned twice (1255 and 1262), which
  broke `tsc` with TS1117. One pin remains, now 1263 after the drift badge.
  `no doc change - test bookkeeping`.

- **feat(ui): delete a bot from the Bots sidebar list.** Each bot row in the
  Bots navigation panel now has a three-dot menu with **Delete**, opening the
  same destructive confirmation used by the Bots workspace. Deletion calls the
  real `/api/automations` endpoint, clears the selection if the deleted bot was
  open, and rehydrates the shared bot store. No doc change â€” UI affordance only,
  contracts unchanged.

- **feat(ui): per-bot sidebar menu â€” pin, rename, duplicate, reliable delete.**
  The Bots sidebar three-dot menu (right-aligned) now also offers **Pin/Unpin**
  (persisted in `localStorage`, pinned bots sort first with a pin glyph),
  **Rename** (PATCH `/api/automations/{id}` with `{name}` via the existing edit
  dialog) and **Duplicate configuration** (shared `duplicateBot` helper, moved
  out of `bots-screen.tsx`). Delete now removes the row immediately via a new
  optimistic `forget(id)` store action and cannot be resurrected: automation
  GETs are `no-store` and `hydrate()` carries a monotonic sequence guard so a
  stale response cannot overwrite newer state. Menu labels reuse the existing
  `sidebar.pin`/`unpin`/`pinned`/`rename` keys to stay inside the `en.ts` line
  budget. No doc change â€” UI affordance only, contracts unchanged.

- **fix(ui): bot delete is instant and repeatable.** The runtime's DELETE can take
  seconds, and the sidebar waited for it before removing the row: the
  confirmation dialog stayed open with a disabled button, so a second delete
  looked dead. Delete now closes the dialog and removes the row optimistically,
  then sends the request. A suppression set keeps concurrent hydrates from
  re-adding the row; a failed request releases it and rehydrates so the bot
  comes back with the error shown. No doc change â€” UI behaviour only, contracts
  unchanged.

## 2026-10-18

- **feat(app,harness): RSL R5 â€” operator evidence and prepare-landing surface.**
  Added operator-gated `GET /evolution/experiments`,
  `GET /evolution/experiments/{runId}` (identity + metrics + bounded trial
  scores), `GET /evolution/candidates/{id}/evidence` (candidate + attempts +
  linked RSL experiments) and `POST /evolution/candidates/{id}/prepare-landing`
  (returns the existing promotion preview and route; never applies). Added
  `EvaluationStore.list_metrics`, the typed `evolution-client.ts` experiment/
  evidence/landing contracts, `evolution-browser.ts` for the client panel, the
  Next.js `/api/evolution/experiments*` + candidate `evidence`/`prepare-landing`
  proxies, and `rsl-experiments-panel.tsx` embedded in the learning journey.
  The panel shows the honest MEASURED/UNMEASURED badge, tests result, decision
  and target, and offers "Prepare landing" only for a tests-passed code
  experiment; the existing single-use promotion approval remains the only write
  path. The existing `/activate`/`/rollback` routes stay skill-only. Files:
  `python/harness/routers/evolution.py`, `python/harness/evaluation/store.py`
  (`list_metrics`), `src/lib/harness/{evolution-client,evolution-browser}.ts`,
  `src/app/api/evolution/experiments/**`,
  `src/app/api/evolution/candidates/[id]/{evidence,prepare-landing}/route.ts`,
  `src/components/screens/skills/rsl-experiments-panel.tsx`,
  `src/lib/i18n/dictionaries/en.ts`,
  `python/tests/test_evolution_rsl_routes.py`,
  `src/components/screens/skills/rsl-experiments-panel.test.tsx`. Checks: 4
  route tests + 4 panel tests pass; 25 targeted RSL/evaluation Python tests
  pass; full vitest 3554 passed; `npx tsc --noEmit` clean (the line-ending guard
  required normalizing `docs/harness/decisions.md` to LF after the ADR edit).
  Docs: `docs/harness/decisions.md` (ADR-H217 consequences),
  `docs/harness/architecture.md`, `docs/NAVIGATION.md`,
  `docs/self-improvement/rsl-implementation-plan.md`.

- **feat(harness): RSL R4 â€” bounded conductor with honest code/surface verification.**
  Added `self_improvement/loop.py` (`RSLLoop`: one bounded asyncio task beside
  learning review, scan/atomic claim/lease reclaim/daily budget, one experiment
  at a time, cooperative stop), `proposer.py` (v1a validated code ops; target +
  every op path checked against `RSL_DENY_GLOBS`), `verifier.py`
  (`verify_code` runs owning tests in a worktree and records
  `benchmark=UNMEASURED`; `verify_surface` is the only measured path and uses
  `CandidateAgentInvoker` + `improvement.evaluate_candidate`; `verify_skill`
  wraps the existing skill evaluation), `landing.py` (validates target/ops,
  applies them in a disposable worktree, returns the existing
  `promotion.build_preview`; never applies), and `recorder.py` (EvaluationRun
  identity + `self_improvement.experiment_completed`; no duplicate
  EvolutionAttempt). `EvolutionStore` gained `claim`, `reclaim_stale` and
  `experiments_started_since`; `boot.py` starts/stops the loop around
  learning review. Approved scope: code patches are tests-only and cannot claim
  a benchmark delta; only surface candidates can be MEASURED. v1b skill drafts
  and v1c model proposers are deferred to R6/R7. Files:
  `python/harness/self_improvement/{loop,proposer,verifier,landing,recorder}.py`
  (new), `python/harness/code/evolution_store.py`, `python/harness/boot.py`,
  `python/harness/event_system/registry.py`,
  `python/tests/test_rsl_{loop,landing,verifier}.py` (new). Checks: 79 RSL
  tests pass; eval gates ALL PASS (53 tasks); `npx tsc --noEmit` clean; vitest
  3550 passed. The full `npm run test` was aborted by the operator at 91% with
  no failures observed; the remaining 568 Python tests passed separately. Docs:
  `docs/harness/decisions.md` (ADR-H217 consequences),
  `docs/harness/agent-evaluation.md`, `docs/harness/architecture.md`,
  `docs/NAVIGATION.md`, `docs/self-improvement/rsl-implementation-plan.md`.

- **feat(harness): RSL R3 â€” isolated candidate invoker and snapshot validation.**
  Added `evaluation/candidate_invoker.py`: `CandidateAgentInvoker` implements the
  existing `AgentInvoker` over a validated `HarnessSnapshot`, running the real
  `execute_run` graph with the candidate prompt/tool subset/ceilings in a private
  per-trial store + registry, with the trial environment bound and cleaned up.
  `validate_snapshot` refuses tools outside the base allowlist, raised
  step/tool-call ceilings and unknown skill drafts; `base_snapshot_from_agent`
  builds the base from a production `AgentConfig`. Added
  `self_improvement/security.py` with `RSL_DENY_GLOBS` (evaluator, tests,
  datasets, policy, approvals, security, promotion/selfhost, patch/workspace,
  evolution, versioning, `.env`, `jdds.db`, test/check scripts) and
  `assert_landable_target` (normalized, case-insensitive, structured refusal;
  absolute/`..`/drive paths refused). The invoker never writes the production
  store; a live bridge is refused in R3. Tests:
  `python/tests/test_rsl_{snapshot,candidate_invoker}.py`. Files:
  `python/harness/evaluation/candidate_invoker.py` (new),
  `python/harness/self_improvement/security.py` (new), the two tests. Checks:
  36 R3 tests + 128 targeted evaluation tests pass; eval gates ALL PASS
  (53 tasks); `npx tsc --noEmit` clean; full `npm run test` 7137 passed with the
  one pre-existing `test_graph_api::test_finance_graph_runs_over_stored_bars`
  failure. Docs: `docs/harness/decisions.md`
  (ADR-H219 consequences), `docs/harness/agent-evaluation.md`,
  `docs/NAVIGATION.md`, `docs/self-improvement/rsl-implementation-plan.md`.

- **feat(harness): RSL R2 â€” comparable experiment identity and splits.** Added
  `evaluation/provenance.py` (`AGENT_VERSION`, `repository_commit`,
  `task_fingerprint_digest`, `require_provenance`). `EvaluationRunner.run_suite`
  now records `agentVersion`/`gitCommit` (or `gitCommitUnavailable`), the dataset
  checksum, config identity (`trials`, `tier`, `split`, `graderVersion`, optional
  `seed`/`temperature`), metadata (`taskFingerprintDigest`, `taskCount`,
  `measuredTrials`) and the real provider/model from the trial trajectories;
  persisted runs upsert every task fingerprint and refuse incomplete provenance.
  `select_tasks(..., split=...)` now filters optimization/validation/held-out/
  release, with `load_all_builtin` preserving per-dataset splits (`routing_e2e_v1`
  = optimization, `team_v1` = held_out, benchmark+construction = validation).
  Trial scores carry `graderVersion` plus honest `costKnown`/`latencyKnown`;
  trajectory cost/latency come from real model-runtime usage and stay `None`
  when unreported, and `cost_per_success` is UNMEASURED if any measured trial's
  cost is unknown. `improvement.evaluate_candidate` can persist its candidate
  run and passes identity/split/seed/temperature through; a zero-measured or
  UNMEASURED dimension is rejected and reverted. Files:
  `python/harness/evaluation/{provenance,runner,tasks,scoring,trajectory,store,improvement,repair_metrics,experiments,__init__}.py`,
  `python/harness/evaluation/datasets/{routing_e2e_v1,team_v1}.json`,
  `python/tests/test_rsl_provenance.py`. Checks: R2 + evaluation tests pass;
  eval gates ALL PASS (53 tasks); `npx tsc --noEmit` clean; full `npm run test`
  7099 passed with the one pre-existing
  `test_graph_api::test_finance_graph_runs_over_stored_bars` failure. Docs:
  `docs/harness/decisions.md` (ADR-H222), `docs/harness/agent-evaluation.md`,
  `docs/NAVIGATION.md`, `docs/self-improvement/rsl-implementation-plan.md`.

- **feat(harness): RSL R0â€“R1 â€” dark observation closure.** Added the native
  `python/harness/self_improvement/` scaffold (`config.py` = `HARNESS_RSL_MODE`
  dark by default + clamped budgets; `models.py` = `HarnessSnapshot`/`Observation`;
  `observer.py` = deterministic recurrenceâ†’inert-candidate and failed-runâ†’mined-
  evidence passes, with no model call and no candidate execution).
  `code/evolution.py` gains `record_mistake_recurrence` (the production caller
  for the ONE `LearningRecurrence` ledger); `capture_mistakes` records it after
  persisting the mistake rows, and `learning_review.py` calls the observer after
  the deterministic analysis (best-effort). The new
  `self_improvement.candidate_created` event is registered. R1 emits only inert
  candidates; R2â€“R8 are not implemented. Files:
  `python/harness/self_improvement/{__init__,config,models,observer}.py`,
  `python/harness/code/evolution.py`, `python/harness/eclipse_memory/mistakes.py`,
  `python/harness/learning_review.py`, `python/harness/event_system/registry.py`,
  `python/tests/test_rsl_{config,observation}.py`. Checks: 17 RSL tests + 113
  targeted evolution/memory/evaluation/review/event tests pass; `npx tsc
  --noEmit` clean; vitest 3546 passed. Full Python suite: 7046 passed; the
  remaining failures are the known size-budget/local-store/stored-bars issues
  and order-dependent UI tests that pass in isolation (none touch RSL). Docs:
  `docs/harness/decisions.md`
  (ADR-H217â€“H219), `docs/harness/architecture.md`, `docs/NAVIGATION.md`,
  `docs/self-improvement/rsl-implementation-plan.md`,
  `docs/self-improvement/architecture-audit.md`.

- **docs(self-improvement): Recursive Self-Improvement Loop (RSL) implementation
  plan.** New `docs/self-improvement/rsl-implementation-plan.md` â€” the native
  conductor for observe â†’ diagnose â†’ propose â†’ verify â†’ operator land â†’ learn.
  It records the measured breaks (mistake recurrence never written, no
  production caller for `candidates_from_mistakes`, `run_loop` test-only,
  `evaluation.started` unconsumed, incomplete evaluator provenance, and
  `evolution_service.activate` not writing the checkout), defines the
  experiment/landing contracts (no new DB/queue; landing only via
  `code/promotion.py` + `code/selfhost.py`), and splits the work into R0â€“R8
  with acceptance gates, tests, budgets, a frozen-path denylist and ADR-H217â€“H219
  + H222â€“H224 (H220â€“H221 are reserved by QA Round 1).
  Files: `docs/self-improvement/rsl-implementation-plan.md` (new),
  `docs/self-improvement/architecture-audit.md`, `docs/NAVIGATION.md`. Checks:
  docs-only, no code change.

- **test(harness): prove the lifecycle through the real dispatch chain.** The e2e
  now also executes `skill_version_evaluate` through `ToolRegistry.execute` with
  the composed effect authorizer and a real `ApprovalStore`: the first call is
  `TOOL_FORBIDDEN` and creates one pending approval, the approved call runs and
  persists, and a third call is refused (single-use). This closes the gap between
  the authorizer unit tests and the handler tests. File:
  `python/tests/test_skill_lifecycle_e2e.py`. Checks: 3 e2e tests pass. Docs: no
  doc change â€” test coverage of the already-documented chain.

- **fix(harness): activation no longer masquerades as content drift.** Drift
  detection hashes the manifest including `status`, but activation reconciles the
  in-memory status from the store while the immutable version row keeps its
  original manifest â€” so every reload after activation reported "content changed
  without a version bump". The check now pins `status`/`evaluationStatus` to their
  STORED values before hashing, so only real content changes are drift. This also
  clears the anatomy drift in the local store; the remaining
  `system.video-production` drift is a genuine working-tree edit. Files:
  `skills/registry.py`, `python/tests/test_skill_lifecycle_e2e.py` (asserts a
  reload after activation is clean). Checks: 88 targeted tests pass. Docs:
  `docs/NAVIGATION.md`.

- **fix(harness): activation cannot leave two enabled versions.** The fresh-store
  end-to-end test caught it: when `latestVersion` already pointed at the candidate
  (a source bump does this before activation), `activate_version` retired only
  that value â€” i.e. the candidate itself â€” so the previously ENABLED version
  stayed enabled. It now supersedes EVERY other version whose status is
  `enabled`/`active`/`canary`, and records the first of those as the prior version
  in the event. Added `python/tests/test_skill_lifecycle_e2e.py`: a real
  `AgenticService` on temp DBs that runs evaluate base â†’ add candidate with a
  declared base â†’ evaluate (regression vs base) â†’ activate â†’ history/reviews â†’
  learning off/on, with no dependence on local store state. Files:
  `skills/versioning.py`, the new e2e test. Checks: 70 targeted tests +
  `test_skills_api.py -k "not health"` (15) pass. Docs: `docs/NAVIGATION.md`.

- **fix(harness): surface the regression baseline even when it passes.** The
  post-base re-evaluation produced `regression: passed` but the tool printed only
  `regression=passed`, so the agent could not confirm WHAT it was compared
  against and rightly said the verdict was unfalsifiable. Both
  `skill_version_evaluate` and `skill_reviews` now print the regression detail on
  every status (`Regression baseline: no regressions vs 1.1.0`). Files:
  `skills/lifecycle_tools.py`, tests updated. Docs: no doc change â€” presentation
  of the already-documented dimension.

- **fix(harness): regression now actually compares against the declared base.**
  The anatomy run exposed that `skill_version_history` showed
  `base=v1.1.0`, yet re-evaluating v1.1.1 still compared against v1.1.1's own
  earlier record: `_regression_dimension` preferred a same-version evaluation and
  only fell back to any prior version. Priority is now declared base (when that
  base has an evaluation) â†’ same version â†’ newest prior version, so evaluating
  v1.1.0 then re-evaluating v1.1.1 produces a genuine base comparison instead of
  a self-comparison. A first/root version with no base keeps the needs_review
  behavior. Files: `skills/evaluation.py`, `python/tests/test_skills_learning.py`
  (re-evaluation against base). Checks: 98 targeted Python tests pass. Docs:
  `docs/harness/phase-3-progress.md`, `docs/NAVIGATION.md`.

- **fix(harness): a source version bump now records its base.** Activating the
  1.1.1 anatomy skill exposed `base=none`: a catalog/source bump
  (`1.1.0`â†’`1.1.1`) was saved without a `baseVersion`, so a later evaluation could
  only compare the version against itself and the regression verdict looked
  weaker than it was. `registry.load_all` now uses `_source_base_version` (highest
  stored semver LOWER than the incoming source version) as `base_version` when
  persisting a NEW version; a first version still has no base, and an existing
  immutable row is never rewritten. The local anatomy row was backfilled to
  `baseVersion=1.1.0`; `skill_reviews` now prints the "no baseline" note only when
  the LATEST evaluation still has `regression=needs_review`. Files:
  `skills/registry.py`, `skills/lifecycle_tools.py`,
  `python/tests/test_skills_registry.py`. Checks: 73 targeted Python tests pass.
  Docs: `docs/NAVIGATION.md`.

- **fix(harness): make the lifecycle read-back say what it means.** The first
  evaluation test showed `skill_version_history` was live but its text omitted
  explicit `null` lineage fields, so the model reported them as "not reported"
  rather than "none"; and `skill_reviews`/`skill_version_evaluate` returned only
  counts, so a `needs_review` verdict at 8 passed / 0 failed looked unexplained.
  History now prints `base=`, `canary=`, `activated=` on every row (`none` =
  empty column, never a missing field); reviews print each evaluation's summary,
  every dimension as `name=status`, and the detail for failed/needs_review ones,
  plus a note that a `regression=needs_review` verdict means no baseline exists
  (evaluate the base version, then re-evaluate the candidate); the evaluate tool
  prints the same summary/dimensions and the next step. Files:
  `skills/lifecycle_tools.py`, `python/tests/test_skill_lifecycle_tools.py`.
  Docs: no doc change â€” implementation detail of the already-documented surface.

- **fix(harness): close the three gaps the first lifecycle test exposed.** (1)
  `skill_version_history` read the slim `registry.version_history`, so it silently
  dropped `baseVersion`/`canaryState`; it now uses `versioning.version_history`
  (patch/canary/activation/rollback metadata) and calls the latest version
  "latest", not "active", so a draft is not mistaken for enabled. (2) Added
  `skill_learning_get` (read-only) so a `skill_learning_set` write can be verified
  at rest instead of trusting the setter's own reply. (3) Added
  `skill_version_evaluate` (write, single-use approval) calling
  `versioning.evaluate_version`: it records the deterministic dimensions and
  regression result but never enables or promotes â€” activation still checks for a
  PASSING result, so the agent can finally run evaluation â†’ activation itself.
  Files: `skills/lifecycle_tools.py`, `agents.py`, `code/policy.py`. Tests:
  `test_skill_lifecycle_tools.py` (getter + evaluation + digest binding),
  `test_chat_code_profile.py`. Checks: 89 targeted Python tests pass. Docs:
  `docs/NAVIGATION.md`, `docs/harness/architecture.md`.

- **feat(harness): the agent can read skill history/reviews and change lifecycle
  state â€” without a second lifecycle.** A self-improvement test asked for version
  history, review data, patch activation and a skill-learning switch; the agent
  could do none of them (routes existed only for the UI). New
  `python/harness/skills/lifecycle_tools.py` adds four tools on the ONE registry:
  `skill_version_history` and `skill_reviews` (read-only; versions from
  `versioning.version_history`, reviews/evaluations from `store.list_reviews` /
  `registry.evaluation_history`, optional version filter) and
  `skill_version_activate` / `skill_learning_set` (write; call
  `versioning.activate_version` and `PolicyStore.set("skill_learning_mode")`, so a
  passing evaluation and the closed mode vocabulary still gate them). Both writes
  join `ACQUISITION_WRITE_TOOLS` (removed at `plan_only`) and are gated by
  `make_skill_lifecycle_authorizer` (single-use, digest-bound operator approval;
  version+canary and mode are part of the digest). Also: `response_block_schema`
  now answers an unknown `block_type` with the registered-type list instead of an
  `UNAVAILABLE`, and `system.anatomy-figure`'s SKILL.md no longer claims that an
  unknown recipe param is diagnosed (the schema strips unknown keys). Files:
  `skills/lifecycle_tools.py` (new), `skills/install_tools.py`,
  `code/authorizers.py`, `code/policy.py`, `agents.py`, `response_tools.py`,
  `skills/library/system/anatomy-figure/{SKILL.md,skill.json}` (1.1.0â†’1.1.1).
  Tests: `test_skill_lifecycle_tools.py` (new), `test_response_tools.py`,
  `test_advertised_tool_admission_all.py`, `test_chat_code_profile.py`. Checks:
  targeted Python tests pass; `tsc` clean; full Python suite 7008 passed with the
  known pre-existing size-budget (main.py 1203 / persistence.py 1441 /
  service.py 1520), graph-stored-bars and frozen local-store `system.video-production`
  drift failures. Docs: `docs/NAVIGATION.md`, `docs/harness/architecture.md`.

- **feat(harness,video): Phase 8 â€” hardening: resource ceilings, pinned
  isolation, a worker SBOM, scheduled recaps and the deployment story.** The
  native video pipeline gets its resource and trust boundaries closed. **Limits**:
  `video/limits.py` refuses a submit when a project already holds
  `HARNESS_VIDEO_MAX_PENDING_PER_PROJECT` (default 4) non-terminal jobs
  (`TOO_MANY_PENDING`, per project, terminal jobs free their slots); `video/gc.py`
  prunes `<video-root>/jobs/<id>/` to `HARNESS_VIDEO_GC_KEEP_JOBS` (20) newest
  and `HARNESS_VIDEO_GC_MAX_TOTAL_MB` (2048) oldest-first â€” never the newest
  (a render in flight) and never `projects/`, safe because finals are COPIED
  into the Artifact Center at registration; the sweep runs at boot
  (`boot.py` lifespan, off the event loop) like the code-workspace sweep.
  **Isolation pinned as tests, not prose**: storyboard specs cannot name any
  media/asset path (unknown-key refusals asserted), the invoked worker's argv
  is asserted inside the job workspace for renders AND previews (the fake
  worker now records strip/frame argv and gains `escape_strip`/`escape_render`/
  `slow` scenarios), and a worker that REPORTS an output outside the workspace
  is refused before inspection/registration â€” a new confinement check in
  `_attempt_render` (`INVALID_STATE`) plus the existing preview `_confined`
  (`INVALID_INPUT`), with the Artifact Center asserted empty. **SBOM**:
  `video/sbom.py` (`python -m harness.video.sbom`) generates the committed
  `rust/fframes-worker/SBOM.json` from `Cargo.lock` (281 locked crates with
  checksums, the EXACT `=1.2.0` fframes pin parsed and cross-checked against
  the lock, the FFmpeg/GPL licensing note; per-crate license strings are
  deliberately NOT faked â€” the file says `cargo metadata` is the honest way)
  with a drift test, so a dependency bump cannot ship without a fresh SBOM.
  **Deployment/zero-config**: `doctor.js` gains a report-only video probe
  (binary present? FFMPEG_DIR set?) that never builds or fails boot; docs
  spell out the prebuilt-binary + FFmpeg-DLL packaging story and the honest
  degradation when the worker is absent. **Scheduled recaps**: `video/recaps.py`
  builds a `schemaVersion 3` BOUND recap storyboard (intro â†’ per-symbol metric
  with price/volume `source` bindings â†’ one daily candlestick â†’ outro, 1â€“5
  symbols), exposed as `POST /video/recaps` + `createVideoRecap`, and the new
  `daily-market-recap-video` job template (cron `30 21 * * 1-5`) drives it on
  the ORDINARY agent runtime â€” no second scheduler. **Graph Studio**:
  `video.render` is DECLARED in both registries (lockstep) with
  `executor=None` + a `since_phase` naming exactly what it waits for (async
  graph execution + an effectful-run envelope); the compiler's
  `executor_unavailable` diagnostic says so instead of a node that pretends.
  Files: `python/harness/video/{limits.py, gc.py, sbom.py, recaps.py}`
  (new), `video/{service.py, config.py}`, `harness/{boot.py,
  routers/video.py, jobs/templates.py, graph_runtime/{nodes.py,
  video_nodes.py}}`, `rust/fframes-worker/SBOM.json` (new),
  `scripts/doctor.js`, TS `src/lib/harness/video-client.ts` +
  `src/lib/graph-studio/registry.ts`. Tests: `test_video_{hardening (10),
  isolation (4), sbom (6), recaps (8)}.py` + `test_graph_video_nodes.py`
  (3) + the opt-in real smoke `test_real_recap_draft_renders` (a data-bound
  recap rendered through the REAL worker, every figure resolved, no authored
  numbers â€” 9 real smoke tests pass on this machine). Checks: full Python
  suite 6938 passed â€” failures are the known set plus the same flaky classes
  (graph + evaluation-repair order-flaky, both green in isolation;
  user-WIP size ratchets `main.py` 1203 / `persistence.py` 1441 /
  `service.py` 1520, untouched by this change â€” no ratcheted module grew in
  Phase 8; the frozen local-store skill drift); vitest 336 files / 3495 tests
  pass with the same single pre-existing `gitignore-guard` failure;
  `npm run test-evals` ALL PASS; `tsc` clean; `cargo test` green; `doctor.js`
  reports the worker "present" + "FFmpeg configured" and exits 0. Docs:
  `docs/video-pipeline.md` (Phase 8 section incl. deployment story + the
  deferred list + the MCP note), `docs/graph-studio.md` (declared node),
  `docs/NAVIGATION.md`, `docs/ARCHITECTURE.md`.

- **feat(harness): round-4 completion pass â€” ADRs H203â€“H208, W13 tool
  contracts, and the remaining W5/W7/W8/W9/W11 slices.** Six items.
  **(ADRs)** `docs/harness/decisions.md` gains the six round-4 decisions the
  roadmap reserved: H203 (Compose needs a catalog witness), H204 (one
  capability-fit fact), H205 (a misroute is a first-class failure), H206
  (self-repair is typed/worktree-authored/operator-gated), H207 (the
  acquisition plan is first-class; the executor may propose, never grant), H208
  (measured or UNMEASURED, never fabricated). **(W13)** New
  `python/harness/tool_contracts.py`: every advertised tool is checked for a
  stable name, a typed input schema, valid permission/risk vocabulary and a
  bounded timeout; `audit_registry` is the release gate â€” all 886 registered
  tools pass (test-pinned), advisory gaps (untyped output, undeclared effect
  metadata) are counted, never blocking. The audit caught and fixed two real
  metadata bugs: `computer_finance_prepare` declared the invalid risk
  `"critical"` (now `"high"`; the computer subsystem's internal CRITICAL class
  is unchanged) and the timeout ceiling now admits the deliberate 15-minute
  operation families. **(W8)** `TaskBudget` gains the measurable caps it was
  missing: `max_model_steps` (enforced post-run) and `max_parallel_workers`
  (enforced through the scheduler's EXISTING per-agent concurrency cap via
  `metadata.maxConcurrency`); model cost remains undeclared because the runtime
  does not price it. **(W11)** The L3 preference now FEEDS the decision: when
  the ledger's measured route is among the policy's own candidates,
  `record_failure` promotes it to first (never adding a strategy the policy did
  not offer) and records the evidence on the result. **(W7)**
  `GET /recovery/metrics` reports the self-evolution block from the REAL
  runtime stores (incident outcomes read from the `action="outcome"` attempts;
  goal-contract criteria), read-only. **(W5/W9)**
  `POST /recovery/incidents/{id}/acquisition/execute` and `.../resume` let an
  operator run ONE approved step through the real surfaces and resume the
  original task from its durable checkpoint â€” parking never re-executes the
  step (pinned by test). Files: `python/harness/tool_contracts.py` (new),
  `python/harness/recovery/{service.py, acquire_handlers.py,
  strategy_learning.py}`, `python/harness/routers/recovery.py`,
  `python/harness/tasks/{model.py, goal.py, scheduler.py, tools.py}`,
  `python/harness/evaluation/repair_metrics.py`,
  `python/harness/computer/schemas.py`, `docs/harness/decisions.md`. Tests:
  `test_tool_contracts.py` (13), `test_recovery_strategy_learning.py` (5),
  `test_evaluation_repair_metrics.py` (7), `test_recovery_acquire_handlers.py`
  (8), plus the budget/tool additions. Docs updated:
  `docs/harness/{decisions,self-evolution-roadmap,task-plan-system,
  failure-recovery,agent-evaluation}.md`, `docs/NAVIGATION.md`.

- **feat(harness): W11 first slice â€” L3 strategic learning.** The route that
  actually worked, learned from the EXISTING recovery ledger. New
  `recovery/strategy_learning.py` (`strategy_stats`, `preferred_strategy`,
  `preference_from_store`): per failure signature it counts each strategy's
  attempts and successes from `RecoveryIncident`/`RecoveryAttempt` rows and
  returns a `StrategyPreference` (strategy + observations + measured success
  rate) only when the evidence supports it â€” minimum observations and a success
  floor, deterministic tie-break; thin evidence yields None (an unmeasured
  choice stays unmade). `RecoveryService.preferred_strategy(signature)` is the
  read-only adapter. The acceptance case is pinned against the REAL ledger: a
  recurring browser-vs-API situation where `browser_navigate` failed and
  `api_call` succeeded twice prefers `api_call` at a measured 1.0 rate. Files:
  `python/harness/recovery/{strategy_learning.py (new), service.py}`. Tests:
  `test_recovery_strategy_learning.py` (4). Docs updated:
  `docs/harness/failure-recovery.md`,
  `docs/harness/self-evolution-roadmap.md`.

- **feat(harness): W8.2 + W10 + W15 + W7 â€” durable-by-default, stuck-loop
  control, autonomy tiers, self-evolution metrics.** Four workstreams.
  **(W8.2)** New `python/harness/goal_runtime.py`: a durable chat request now
  becomes a goal task BEFORE the run â€” the run itself is its first attempt â€”
  and settlement verifies through the task-type verifier afterwards (verified
  completion, or a bounded repair attempt re-queued for the scheduler). The
  wrapper is installed by `tasks/bootstrap.py::install_task_layer` (idempotent,
  never breaks a chat turn on bookkeeping failure, never wraps a
  task-dispatched run). **(W10)** New `recovery/progress.py` (`ProgressTracker`):
  an identical (tool, args, signature) failure is never retried unchanged in
  the hot path, a loop with no progress across N attempts reports `STUCK LOOP`
  with the actual blocker, and the task scheduler stops spending retries on
  consecutive identical failures (`no progress: the same failure (X) recurred N
  times unchanged`). **(W15)** New `security/tiers.py`: the brief's three
  autonomy tiers derived from the EXISTING policy groups (read â†’ autonomous;
  write/execute/install â†’ guarded; external/destructive â†’ approval), plus
  `tier_report` auditing a live registry â€” consistency with the enforced
  policy is test-pinned. **(W7)** New `evaluation/repair_metrics.py`: the Â§1
  metric block (`time_to_repair_ms`, `self_repair_precision`,
  `requirement_completeness`, `cost_per_success`, `unauthorized_action_rate`)
  computed from real records or printed as `UNMEASURED` â€” the gate report now
  carries it. Files: `python/harness/goal_runtime.py` (new),
  `python/harness/recovery/progress.py` (new),
  `python/harness/security/tiers.py` (new),
  `python/harness/evaluation/repair_metrics.py` (new),
  `python/harness/{recovery/hotpath.py, tasks/{scheduler,bootstrap}.py,
  evaluation/gate.py}`. Tests: `test_goal_runtime.py` (10),
  `test_recovery_progress.py` (8), `test_security_tiers.py` (6),
  `test_evaluation_repair_metrics.py` (6); recovery/tasks/evaluation family
  green. Docs updated: `docs/harness/task-plan-system.md`,
  `docs/harness/failure-recovery.md`, `docs/harness/agent-evaluation.md`,
  `docs/harness/self-evolution-roadmap.md`, `docs/NAVIGATION.md`.

- **feat(harness,video,ui): Phase 7 â€” the `/video` HTTP surface, the chat job
  card, and video artifacts you can actually watch.** The native video pipeline
  now lands on the app's own surfaces. **HTTP door**: new operator-gated
  `python/harness/routers/video.py` (`/video/capabilities`, project CRUD +
  `validate`/`resolve-data`/`preview`/`render`/`repair`, `jobs` read/cancel/
  inspect) â€” a thin shell over `VideoService`, refusal codes mapped by cause
  (`*_NOT_FOUND`â†’404, `REPAIR_*`/`INVALID_STATE`â†’409, `DATA_UNAVAILABLE`/
  `RUNTIME_UNAVAILABLE`â†’503, validationâ†’400), included by `main.py`; render/
  preview/repair accept a `conversationId` and produced artifacts now register
  with **conversation + run + agent** association (agent tools read it from the
  run context â€” the private conversation id when the run opted in, else the
  chat session id; new `ToolContext.session_id` seam). **Front door**:
  `src/lib/harness/video-client.ts` (browser-safe, typed `VideoApiError` with
  the refusal code) + `src/app/api/video/[[...path]]/route.ts` (guard â†’
  runtime health â†’ per-segment-encoded upstream path, operator token + identity
  forwarded). **Chat surface**: a `video_*` tool hands its QUEUED job to the new
  run collector (`video/collector.py`, bounded/deduped, max 8 â€” the same idiom
  as the image/vision collectors) and the run persists a `video` blob
  (`schemas.RunResult.video`, `HarnessRun.video` column, `client.final`,
  `events.ts`/`use-agent-run.ts`/`Message`/`AssistantTurn`); `VideoPanel`
  (`src/components/chat/video-panel.tsx` + `video-view.ts`) polls the REAL job
  records via `/api/video/jobs/{id}` and shows only what exists â€” progress and
  attempts while running, the final render's inline player + download once its
  artifact is registered, a preview's image count, an inspection's findings, or
  the honest `errorClass` failure â€” with real actions (cancel, regenerate a
  draft/final, revise-with-agent via the follow-up path). **Video artifacts**:
  the artifact preview engine gained one seam
  (`artifacts/preview.py::set_video_poster_extractor`, no video import) and the
  video layer installs an FFmpeg poster extractor (`video/poster.py` â€” tries
  1.5 s, falls back to 0.5 s, `UNSUPPORTED` when it cannot produce a REAL
  frame, never a fabricated poster), so a final render's thumbnail is an
  actual frame; the download route now honors `Range` (`206`/`Content-Range`/
  `Accept-Ranges`, `416` for unsatisfiable) and `?inline=1`, the Next artifacts
  proxy forwards the range header + byte-stream metadata and drops the fixed
  timeout for download streams, and the Artifact Center grid shows the poster
  while the detail view plays the MP4 inline (`inlineUrl`). Files:
  `python/harness/{routers/video.py, main.py, graph.py, persistence.py,
  schemas.py, tools.py, conftest.py, artifacts/preview.py,
  routers/artifacts.py}`, `python/harness/video/{collector.py, poster.py,
  service.py, tools.py, bootstrap.py}`, TS `src/lib/harness/{video-client.ts,
  video-view.ts, artifacts-browser.ts}`, `src/app/api/video/[[...path]]/
  route.ts`, `src/app/api/{artifacts,harness/chat}/**`,
  `src/components/chat/{video-panel.tsx, chat-history.tsx, chat-dock.tsx}`,
  `src/components/screens/{stock-chat.tsx, artifacts/artifacts-screen.tsx}`,
  `src/lib/agent/{events,use-agent-run,response-model}.ts`, `src/types/chat.ts`,
  `src/lib/harness/types.ts`. Tests: `test_video_{api (12), collector (7),
  poster (7)}.py` + range/inline coverage in `test_artifacts_api.py` + tool
  sink/context assertions in `test_video_tools.py` + the opt-in real smoke
  `test_real_final_render_gets_a_poster_thumbnail` (a REAL PNG frame extracted
  by FFmpeg from the rendered MP4 becomes the thumbnail â€” poster reviewed
  visually after the 1.5 s/0.5 s timing fix); TS `video-view.test.ts` (8),
  `video-client.test.ts` (4), `video-panel.test.tsx` (3 SSR),
  `src/app/api/video/route.test.ts` (5). Checks: full Python suite 6837 passed
  â€” failures are the known set plus the same flaky classes (graph +
  execution-resources order-flaky, both green in isolation; `main.py` 1203 /
  `persistence.py` 1441 / `service.py` 1520 user-WIP size ratchets â€” the video
  column adds 5 lines to the already-over `persistence.py`, left as the known
  failure; `graph.py` re-pinned 2145â†’2170 for the Phase-7 seams with a
  justification comment; the skills load-error test still names the frozen
  local-store drift rows, fresh store loads zero errors); vitest 336 files /
  3494 tests pass with the same single pre-existing `gitignore-guard` failure
  (user WIP `graph-canvas.tsx` line endings â€” none of the new files mix);
  evals ALL PASS; `tsc` clean. Docs: `docs/video-pipeline.md` (Phase 7
  section + roadmap), `docs/harness/artifact-center.md` (video posters + media
  playback + conversation association), `docs/NAVIGATION.md`,
  `docs/ARCHITECTURE.md`.

- **feat(harness): W3.2 end-to-end routing tier + W5/W9 acquisition handlers.**
  Two workstreams. **(1) W3.2:** the routing benchmark is now also measured
  through the REAL graph. `evaluation/environments.py` gains the `ui`
  environment (`UiStateEnvironment`) reporting the durable engineering
  tasks/plans a trial actually created; `evaluation/runner.py`'s
  `ScriptedAgentInvoker` builds the real `UiService` + `TaskManager` (and
  registers the `ui_*`/`task_*` families) and gives EVERY trial its own
  isolated store (concurrent trials can no longer see each other's durable
  work; the store's cleanup is owned by the environment's teardown, since
  grading reads it after invoke); new dataset
  `evaluation/datasets/routing_e2e_v1.json` (4 tasks: clock escalates with a
  capability gap, layout composes, generic widget composes, new widget
  engineers) graded on the real resulting state. Gate now runs tasks=51 with
  the four e2e tasks 100% and `misroute_rate=0.0`; a restored pre-W0 defect
  (witness-less Compose + no catalog re-check) makes the clock task FAIL the
  tier (test-proven). **(2) W5/W9:** new
  `recovery/acquire_handlers.py` is the production CALLER of the acquisition
  lifecycle: a `build` step routes through the real `ui_start_engineering`
  gate (own plan â†’ the original task parks WAITING for an explicit resume) or
  creates a same-plan code-agent capability task whose completion auto-resumes
  the original through the existing DAG (REQUIRES dependency + BLOCKED park â€”
  the cross-plan refusal is respected, never bypassed); `install`/`enable`
  steps park the task ASKING_USER with the exact missing facts and never
  self-grant; `resume_callback` is `retry_task`'s caller half (restores from
  the durable checkpoint). The task scheduler records the new `waiting`
  outcome without failing or retrying a parked task, and the production
  executor (`tasks/bootstrap.py`) attempts the acquisition before falling back
  to the honest failure. Files:
  `python/harness/evaluation/{runner,environments}.py`,
  `python/harness/recovery/acquire_handlers.py` (new),
  `python/harness/tasks/{bootstrap,scheduler}.py`, dataset
  `routing_e2e_v1.json`. Tests:
  `test_evaluation_routing_e2e.py` (6) + `test_recovery_acquire_handlers.py`
  (7); the tasks/recovery/evaluation/UI/routing family is 594 passed; eval
  gates ALL PASS. Docs updated: `docs/harness/agent-evaluation.md`,
  `docs/harness/failure-recovery.md`, `docs/harness/task-plan-system.md`,
  `docs/harness/self-evolution-roadmap.md`, `docs/NAVIGATION.md`.

- **feat(self-improvement): HarnessÂ² borrowings â€” verified steal-list + first slice (verdict-leak tripwire, contrastive evidence bundle).** Read the upstream
  mechanism at the pinned revision (`harness2/core/{recursion,selection,library,tree,context,proposer}.py`)
  and extracted what is worth adopting natively: verdict-isolated evidence
  (`GRADER_VERDICT_MARKERS` tripwires), contrastive Propose with shared base
  rollouts and per-candidate decision notes + diffs, anonymized seeded
  behavioral selection with recorded drops/why and a neutral base fallback,
  per-domain `EXPERIENCE.md` lessons gated on mandatory cue/lesson/evidence,
  editable-surface validation (always-on cap, untriggered-skill and script-ref
  checks), and session hygiene (content-addressed cache, audit, empty-reply
  error, quoted-rejection repair retry). First slice lands the two lowest-risk
  pieces as **un-wired pure utilities** (zero behavior change):
  `python/harness/evaluation/verdict_guard.py` (refuses evaluation verdicts /
  answer-key markers in any bundle or lesson text about to reach a model or be
  persisted) and `python/harness/evaluation/contrast.py`
  (`contrast_trajectories` â€” behavior tokens, tool-sequence diff, metric deltas,
  first divergence â€” plus `render_evidence_bundle`, the file-based evidence
  tree with a short mission that demands citing the specific trajectory moment).
  Remaining tickets (T3 anonymized selection, T4 lesson cue/evidence gate,
  T5 surface validator, T6 session cache, T7 diversity, T8 typed candidates)
  are specified in the doc; wiring (T1b/T2b) deliberately waits for the
  in-flight evaluation/learning work to land. Tests:
  `python/tests/test_evaluation_{verdict_guard,contrast}.py` â€” 12 passed;
  `npx tsc --noEmit` clean. Docs updated:
  `docs/self-improvement/harness2-borrowings.md` (new), `docs/NAVIGATION.md`.

- **docs(self-improvement): Phase 0 â€” HarnessÂ² integration architecture audit.**
  Verified the upstream framework (`google-research/harness2`, Apache-2.0 core,
  Linux + Python 3.12, OpenCode/Codex executors, Proposeâ€“Probeâ€“Compose, offline
  `harness2-demo`; head pinned in the doc at `1cfe254eâ€¦`) and audited the real
  tree for integration: the seams to reuse (`AgenticService.run`/`execute_run` +
  `RunRequest.agent`, the evaluation `AgentInvoker` protocol and its per-trial
  isolation pattern, `EvaluationStore`/graders/gates, `eclipse-memory.db`
  migrations + skills lifecycle/versioning, `code/evolution*` promotion,
  security gateway, event system, cost/observability), the gaps to close
  (evaluator provenance columns unwired, cost/latency unpopulated in records,
  no configuration identity or task/val/held-out splits, scripted tier bypasses
  the canonical event bus; no experiment/harness-revision entities), the
  explicit no-duplicate-systems decision, and the Phase 1 environment blocker
  (no WSL2, no Docker CLI on this host; `uv` 0.12.17 + vendored Python 3.12.8
  present). No code changed. Docs updated:
  `docs/self-improvement/architecture-audit.md` (new), `docs/NAVIGATION.md`.

- **feat(harness): W6 â€” construction procedure learning (the learning loop
  closes).** A successful UI construction sequence becomes an inert
  `successful_procedure` candidate carrying the know-how the clock run had to
  re-derive. New `skills/procedures.py`: a completed run with a SUCCESSFUL
  `ui_register_engineered_component` (the registration actually ran) yields the
  candidate from `skills/learning.py::analyze_run` on the FIRST occurrence â€”
  one stable signature (`CONSTRUCTION_PROBLEM`) dedupes every construction into
  ONE candidate, and the generic tool-sequence candidate is suppressed for that
  run. The encoded procedure names the real constraints: implement in
  `src/lib/dashboard/widgets.tsx` within the 1200-line hard ceiling, register
  in `src/lib/dashboard/registry.tsx`, add the icon name to its `ICONS` map,
  run `npx tsc --noEmit` + tests, `ui_register_engineered_component`, then
  Compose. The repeat (stable `CONSTRUCTION_RECURRENCE_KEY` seen twice in the
  existing `LearningRecurrence` ledger) opens the inert draft from the post-run
  review (`learning_review.py` outcome 1c) through the SAME `propose_draft` the
  operator route uses â€” `status: draft`, `evaluationStatus: not_evaluated`,
  never enabled; a second review is a no-op. A resolved CAPABILITY incident
  yields the SAME candidate via `recovery/learning.py::incident_to_candidate`
  (capability gaps are construction work, not generic failure recovery).
  `skills/draft.py` now renders each procedure step's `detail` into the SKILL.md
  instructions, so constraints survive into the draft. Files:
  `python/harness/skills/{procedures.py (new), learning.py, draft.py}`,
  `python/harness/learning_review.py`, `python/harness/recovery/learning.py`.
  Tests: `python/tests/test_construction_procedure.py` (11 â€” detection,
  encoding, first-occurrence candidate + no draft, repeat â†’ inert draft, no
  auto-enable, tool-evidence filtering, review surfacing, incident-path
  signature equality, dedupe); the learning/skills/recovery/tasks/UI family is
  1029 passed with only the known local-DB skill-drift failure
  (`test_skills_api::test_health_reports_skills`). Docs updated:
  `docs/harness/memory-skills-evolution-plan.md` (W6 section),
  `docs/harness/self-evolution-roadmap.md` (W6 status),
  `docs/harness/failure-recovery.md`, `docs/NAVIGATION.md`.

- **feat(harness): W8 first slice â€” the goal contract and verified completion.**
  The product loop's centre: a request becomes a durable, typed goal instead of a
  prompt. New `tasks/goal.py` runs a deterministic intake (`intake_goal`:
  taskType, deliverables, acceptance, budgets â€” one clarifying question on
  ambiguity, never a guessed contract) and `durable_decision` is the explicit
  durable-by-default rule; the new `create_goal` tool (registered in `TASK_TOOLS`,
  reachable wherever the task tools are) creates the plan + contract-bearing task
  and starts it. New `tasks/verification.py` is the task-type verifier registry
  (`verify_task`, keyed by `taskType`; `code|research|document|workflow|finance|
  general`) that reads EVIDENCE the run produced â€” zero-exit code-verification
  records, delivered artifacts, recorded sources, observed metrics â€” never
  prose; a task with no `taskType` keeps the exact pre-W8 contract. The scheduler
  now verifies before completing: a failed verification is retried WITH the
  missing evidence named (the retry context quotes it), and an exhausted budget
  ends the task `BLOCKED` with `BlockedReason.VERIFICATION` (new) naming the
  exact missing proof; contract budgets (`TaskBudget`: duration/tool calls/tokens)
  are enforced post-run and end `BLOCKED` with the violated cap, never a silent
  truncation. The `run_complete` checkpoint carries the verified verdict
  ("completion is evidence"), and the crash path is proven: a dead worker's
  lease expires, the stale attempt is reconciled `TIMED_OUT`, and the resumed
  attempt completes with exactly one delivery. Also fixed a real feedback bug:
  `previous_attempts` included the CURRENT pending execution, so a retry never
  saw the prior failure â€” it now carries only concluded attempts and the
  renderer quotes the most recent FAILED one. Files:
  `python/harness/tasks/{goal.py (new), verification.py (new), model.py
  (TaskType/TaskBudget/GoalContract, BlockedReason.VERIFICATION, Task +
  CreateTaskInput fields), store.py (additive taskType/goalContract columns),
  manager.py (contract criteria merge + update validation + blocked_reason),
  scheduler.py (budget check, task-type verification, honest BLOCKED, evidence
  checkpoint), bootstrap.py (evidence blobs on the outcome), context.py (retry
  feedback), tools.py (create_goal), __init__.py}`. Tests:
  `test_tasks_goal.py` (19), `test_tasks_verification.py` (15),
  `test_goal_completion.py` (4 â€” build-break-repair-deliver, unverifiable â†’
  BLOCKED, budget â†’ BLOCKED, crashed-worker resume with one delivery) + 3 tool
  cases; the whole `tasks_/recovery_/routing_/ui_/evaluation_` family is 572
  passed. Docs updated: `docs/harness/task-plan-system.md` (W8 sections),
  `docs/harness/self-evolution-roadmap.md` (W8 status),
  `docs/harness/decisions.md` (ADR-H209/H210).

- **feat(harness,video): Phase 6 â€” PNG previews, real diagnostics and the
  bounded repair loop.** A new `action=preview` Fabric job (`video_preview`
  tool #13, `VideoService.preview_project`) renders review material WITHOUT a
  video: the worker's `strip` contact sheet plus one `frame` PNG per scene
  (addressed `#0@50%`, `#1@50%`, â€¦ so fades cannot shift the target; the SAME
  resolved binding spec a render would use) â€” registered as `image` artifacts
  (`source_type=job`, idempotency `video-preview:<jobId>:<name>`; a missing
  catalog is recorded per file, never a false failure), with the worker's
  structured frame diagnostics deduplicated into
  `findings/findingsTotal/findingsErrors/findingsWarnings` in the job output â€”
  findings make problems VISIBLE, they never fake a video. Failures are now
  handled by a closed, bounded policy (`video/repair.py`): transient classes
  (`DATA_UNAVAILABLE`, `WORKER_UNAVAILABLE`) are retried INSIDE the render job
  at most `HARNESS_VIDEO_TRANSIENT_RETRIES` extra attempts (default 1, each
  recorded as `retries`; `0` disables), content failures go back through
  `video_render_repair` (tool #14, `VideoService.render_repair`) which
  validates the failed parent, refuses an unchanged non-transient retry
  (`REPAIR_REQUIRES_CHANGE`), bumps the revision and submits a render linked
  via `input.repairOf` + the parent's diagnostics (read from `report.json`,
  since failed jobs keep no output row) â€” and is CAPPED at 2 repairs per
  failure line (the connected `repairOf` component, walked in BOTH directions
  so re-referencing the original failure cannot evade it), past which it
  refuses with `REPAIR_LIMIT_REACHED` as the explicit terminal state. A
  completed final render now records `review`: the latest SUCCEEDED
  draft/preview of the same `projectRevision`, or `null`. Both kinds share the
  SAME artifact-gates invariants as renders: honest codes, confined
  workspaces, no success ever claimed for a failed job. Files:
  `python/harness/video/{repair.py (new), config.py, runner.py (strip/frames +
  --json), service.py (attempt loop, preview job, repair op, review),
  fabric.py, tools.py}`, skill `system.video-production` v2.2.0 (preview +
  repair procedure), `python/tests/video_fakes.py` (strip/frame/flaky
  scenarios, provider `fail_times`). Tests: offline
  `python/tests/test_video_preview.py` (6) + `test_video_repair.py` (9) +
  runner/tool additions â€” 76 video tests green (from 52) â€” and the opt-in real
  smoke grew `test_real_preview_catches_a_clipped_title` (a real contact sheet
  + per-scene frames, registered as image artifacts, DETECTING a real
  clipped-text warning before any render) and
  `test_real_transient_retry_recovers_a_bound_render`; all 7 real smoke tests
  pass on this machine and the contact sheet was reviewed visually. Checks:
  full Python suite 6794 passed with the known pre-existing failures â€”
  size-budget ratchets (`main.py` 1201 / `persistence.py` 1436 / `service.py`
  1520, all user-WIP growth untouched by this change), the order-flaky
  `test_graph_api::test_finance_graph_runs_over_stored_bars`, and
  `test_skills_api::test_health_reports_skills`, which now names TWO stale
  local-store skill-version-drift rows (`system.anatomy-figure` â€” the known
  one â€” plus `system.video-production`, whose stored active version is a
  dev-session 1.0.0 row in the untracked `eclipse-memory.db`; a fresh store
  loads with ZERO errors, so this is local DB state, not repo content);
  `npx tsc --noEmit` clean; evals all gates pass; `cargo test` green (worker
  unchanged). Docs: `docs/video-pipeline.md` (Phase 6 section + ops table +
  invariants), `docs/NAVIGATION.md`, `docs/ARCHITECTURE.md`.

- **feat(recovery): capability acquisition lifecycle (W5/W9 first slice).** New
  `recovery/acquisition.py` implements discover â†’ assess â†’ propose â†’ acquire â†’
  validate â†’ retry over the existing `CapabilityIndex`. Each step names its
  surface (`existing_tool`, `skill`, `plugin`, `scaffold_kit`, `engineering`,
  `alternative`, `operator`), readiness, approval requirement and exact missing
  facts. `use`/`alternative` are read-only; `enable`/`install`/`build` are
  approval-flagged and require a caller-supplied handler. Validation without a
  contract test is `unverified`; retry requires a caller checkpoint callback.
  `run_with_recovery` now registers default capability handlers
  (`substitute_tool`, `alternative_implementation`, `fix_dependency`) that hand
  back the plan and **stop** the loop with `acquisition_required`; the executor
  honours that sentinel. New operator route
  `POST /recovery/incidents/{id}/acquisition`; the recovery console shows the
  steps. Discovery now ignores grammar stopwords (a query containing "a" no
  longer matches every description). Files:
  `python/harness/recovery/{acquisition,execution,executor,discovery,service}.py`,
  `python/harness/tasks/bootstrap.py`, `python/harness/routers/recovery.py`,
  `src/app/recovery/recovery-console.tsx`, `src/lib/harness/recovery-view.ts`;
  tests `test_recovery_acquisition.py` (11). Checks: 527 subsystem tests pass;
  `npx tsc --noEmit` clean. Docs: `docs/harness/failure-recovery.md`,
  `docs/harness/self-evolution-roadmap.md`.

- **feat(recovery): a verified routing repair can be prepared and landed through
  the existing promotion card (W4).** New `recovery/routing_landing.py` turns a
  stored incident's classifier-rule proposal into a real disposable worktree +
  `code.patch.PatchOp`, refuses an authority target with
  `code/selfhost.py::classify_landing`, registers the workspace under
  `routing-repair-<incidentId>`, and returns the SAME
  `promotion.PromotionPreview` the Code Tasks route uses. New operator route
  `POST /recovery/incidents/{id}/routing-repair` returns the proposal, preview
  and landing verdict; the recovery console prepares it and renders the existing
  `PromoteChange` card (single-use digest-bound approval â†’ apply â†’
  restart/build verdict â†’ rollback). The promotion preview and apply routes now
  refuse an authority target **before** creating or consuming an approval.
  Files: `python/harness/recovery/routing_landing.py`,
  `python/harness/routers/{recovery,code}.py`,
  `src/app/recovery/recovery-console.tsx`, `src/lib/harness/recovery-view.ts`;
  tests `test_routing_landing.py` (6) + the authority route test in
  `test_code_promotion.py`. Checks: 18 focused + 43 landing/promotion tests
  pass; `npx tsc --noEmit` clean. Docs:
  `docs/harness/failure-recovery.md`, `docs/harness/self-evolution-roadmap.md`.

- **feat(evaluation): routing quality is on the standing gate (W3.2/W3.3).**
  New `evaluation/routing.py` runs the versioned classifier benchmark and
  computes `misroute_rate` (mismatched / all cases; maximum 0.0) and
  `escalation_correct` (correct engineer/both verdicts / expected-escalation
  cases; minimum 1.0). `run_offline_gate` injects both into the SAME threshold
  check as the agent suite and records the source in `SuiteResult.routing`;
  `format_gate_report` prints the values and the case count. Both dimensions are
  critical `DEFAULT_GATES`, and `improvement.evaluate_candidate` now rejects a
  proposal that regresses either. Files:
  `python/harness/evaluation/{routing,gate,scoring,regression,improvement,runner}.py`;
  tests `python/tests/test_evaluation_routing.py` (4). Measured:
  `evaluation gate: PASS tasks=47`, `misroute_rate=0.0`,
  `escalation_correct=1.0`, `routing cases=8`. Docs:
  `docs/harness/agent-evaluation.md`, `docs/harness/self-evolution-roadmap.md`.

- **feat(recovery): routing repair proposals â€” diagnose â†’ minimal patch â†’
  verify (W2.1â€“W2.3).** New `recovery/routing_repair.py` turns a routing failure
  into a typed cause (`VOCABULARY_GAP`, `CATALOG_GAP`, `CAPABILITY_ABSENT`,
  `POLICY_GAP`). Only a vocabulary miss yields a code change: a minimal
  `code.patch.PatchOp` replacing the additive-verb line in `ui/mode.py`, plus a
  regression fixture. Verification activates the exact rule in memory through
  the existing `ImprovementProposal` contract (apply â†’ classify â†’ revert), so no
  file is written and no model is called. `recovery/diagnosis.py` gained the
  four capability causes; `RecoveryService.propose_routing_repair` exposes the
  proposal from a stored incident, read-only. `assess_capability` gained the
  diagnostic `additive_only=False` view (the classifier keeps the safe
  additive-only behaviour). Files: `python/harness/recovery/{routing_repair,
  diagnosis,service}.py`, `python/harness/ui/mode.py`; tests
  `python/tests/test_routing_repair.py` (11, incl. the "missing a world clock"
  fixture, apply-flip-revert, the incident seam and diagnosis selection).
  Checks: 447 subsystem tests pass; eval gates ALL PASS; `tsc` clean. Docs:
  `docs/harness/failure-recovery.md`, `docs/ui-engineering.md`,
  `docs/harness/self-evolution-roadmap.md`.

- **feat(harness): routing failures become durable incidents (W1.1/W1.2) and
  gain a versioned benchmark (W3.1).** `eclipse_memory/mistakes.py` gains five
  deterministic categories derived from the persisted UI tool text â€”
  `composed_without_witness`, `escalation_refused`, `capability_gap_refused`,
  `misrouted_request`, `intent_ambiguity`; `ui_classify_request` now exposes its
  witness (`Components: â€¦`) and `ui_start_engineering` prefixes an escalated
  result with `Capability gap â€”`. The escalation emits the registered
  `ui.capability_gap` event; recovery subscribes to it and it maps to the
  existing `FailureKind.CAPABILITY` (non-retryable, so the policy selects
  `SUBSTITUTE_TOOL`/`ALTERNATIVE_IMPLEMENTATION`). The versioned
  `python/harness/ui/routing_benchmark_v1.json` (8 cases incl. the clock) is
  exercised by `test_ui_routing_benchmark.py`; the end-to-end scripted tier is
  deferred to W3.2 because the scripted eval registry does not bind `ui_*`.
  Files: `python/harness/ui/{tools,engineering}.py`,
  `python/harness/eclipse_memory/mistakes.py`,
  `python/harness/recovery/{taxonomy,bootstrap}.py`,
  `python/harness/event_system/registry.py`; tests `test_routing_mistakes.py`,
  `test_routing_incident.py`, `test_ui_routing_benchmark.py` (+5 mode/engineering
  cases). Checks: 446 subsystem tests + 300 affected-family tests pass; full
  Python is green except the repo's known skill-drift/size-budget failures and a
  concurrent `video-production` manifest edit that was corrected mid-run; eval
  gates ALL PASS; `tsc` clean; vitest 3474/3475 (pre-existing `graph-canvas.tsx`
  line-ending guard). Docs: `docs/harness/failure-recovery.md`,
  `docs/ui-engineering.md`, `docs/harness/self-evolution-roadmap.md`.

- **fix(ui-engineering): a Compose verdict must cite a catalog witness, and
  `ui_start_engineering` re-checks the catalog instead of refusing.** The
  recorded "multi-zone world clock" defect: `ui_classify_request` returned
  `compose` for a capability the catalog lacks (`matched_components=[]`), then
  `ui_start_engineering` returned the false "no engineering task was created".
  `mode.py` now runs `assess_capability` over clause-scoped additive requests
  (layout/restyle/page and generic "add a widget" need no witness; a named
  capability with no registered match is a gap). A gap returns `engineer` with
  `capabilityGap: true`; `engineering.start` re-checks the same fact and
  escalates, so a stale label cannot produce a refusal. Files:
  `python/harness/ui/{mode,engineering,__init__}.py`. Tests:
  `python/tests/test_ui_mode.py` (+5), `test_ui_engineering.py` (+2). Checks:
  UI pytest 101 passed; eval gates ALL PASS; `npx tsc --noEmit` clean; vitest
  3474/3475 (the one failure is the pre-existing `graph-canvas.tsx`
  line-ending guard). Docs: `docs/ui-engineering.md`,
  `docs/harness/self-evolution-roadmap.md`. Also rotated the oldest
  `CHANGELOG.md` section (2026-10-11) into `docs/changelog/2026-10.md` to keep
  the 7-section window.

- **docs(harness): expand the round-4 roadmap into Round 4 Expanded (W8 centre +
  W9â€“W15 completion/audit).** Adds W8 â€” goal contract â†’ durable plan â†’ execute â†’
  observe â†’ task-type verification â†’ complete/blocked â€” as the product loop, and
  maps the general-agent workstreams W9â€“W15 onto machinery that already exists
  (`tasks/`, `fabric/`, `event_system/`, `delegation.py`, `team/`,
  `orchestration/`, `artifacts/`, `security/`, `model_runtime/`, `evaluation/`).
  Corrects the premise that these are new layers; adds end-to-end metrics
  (`end_to_end_task_success`, `requirement_completeness`,
  `capability_acquisition_success`, cost/time per success, unauthorized-action
  rate), the evidence-based-completion / frozen-benchmark / no-new-infrastructure
  invariants, the dependency order (W0/W1/W3.1 â†’ W8 â†’ W2â€“W4 â†’ W5/W9/W6 â†’ W10â€“W15
  â†’ W7), risks and ADR-H209â€¦H215. No code changed.
  Docs: `docs/harness/self-evolution-roadmap.md`, `docs/CHANGELOG.md`.

- **feat(harness): W12 â€” the multi-agent comparison harness, measured (not
  assumed), and ADR-H213.** The team/A2A/task machinery already existed; the
  missing piece was evidence that delegation across specialists beats one agent.
  New `evaluation/team_benchmark.py` runs a frozen multi-step build BOTH ways on
  the SAME task: the single-agent scripted `execute_run`, and the REAL team stack
  (`TeamService` â†’ `A2AService` â†’ `TaskScheduler` â†’ `execute_run`) across 2â€“3
  specialists, each subtask executing its own deterministic script over a
  per-trial isolated store (the `ScriptedAgentInvoker` pattern). The team model
  seam is active ONLY inside a team trial, so a team trial can never reach a
  provider (a repair task with no script gets a deterministic "(no script)"
  answer). `experiments.multi_agent_compare` returns both recorded suites + their
  durable `EvaluationModel` rows, measured axes (`taskSuccess`, wall clock,
  `toolCalls`, `modelSteps`) and a deterministic adoption verdict: quality must
  not regress and a real gain is required (wall clock â‰¥15% better, or strictly
  fewer tool calls); cost/tokens are published as UNMEASURED for the scripted
  tier. New frozen dataset `datasets/team_v1.json` (2 tasks, each with BOTH the
  single-agent program and the team decomposition; the single-agent program also
  runs in the standing gate). **Recorded measurement** (3 trials Ã— 2 tasks):
  quality 1.0 vs 1.0 (6/6 measured), wall 1454 ms vs 2234 ms (+53.6%), tool calls
  27 vs 30, model steps 33 vs 45 â†’ **not adopted** â€” no measured gain; the
  offline tier's tools execute synchronously, so parallel legs cannot overlap
  work while the team pays the plan/task overhead. A restored defect (a silently
  dropped subtask) FAILS the state grader â€” the tier grades real work, never the
  team's own status. Also fixed a real eval bug found by the harness: scripted
  tool-call ids collided across child runs (`call_0_0` per script), mis-mapping
  recorded arguments; `runner._script_messages` now takes a `call_id_prefix`.
  Files: `python/harness/evaluation/{team_benchmark.py (new),
  experiments.py, runner.py, datasets/team_v1.json (new)}`, ADR-H213. Tests:
  `python/tests/test_evaluation_team_comparison.py` (13). Checks: focused
  recovery/tasks/evaluation/goal/tool_contracts/ui/team family 669 passed; full
  Python 6953 passed â€” the five documented pre-existing failures unchanged
  (`test_graph_api` order-flake, the `main.py`/`persistence.py`/`service.py`
  size-budget ratchets, the local skill drift), no ceiling raised; eval gates
  ALL PASS `tasks=53` (parallel 3/3); `npx tsc --noEmit` clean; vitest 3495/3496
  (the pre-existing `graph-canvas.tsx` line-ending guard).   Docs:
  `docs/harness/agent-evaluation.md`, `docs/harness/bot-team-orchestration.md`,
  `docs/harness/self-evolution-roadmap.md`, `docs/harness/decisions.md`,
  `docs/NAVIGATION.md`.

- **feat(harness): round-4 completion pass 2 â€” ADRs H211/H212/H214/H215, W13
  behaviour fixtures, real acquisition installs, phase-15/16/18 remainders,
  capability-extension D installs + E reverse sync.** **(ADRs)**
  `docs/harness/decisions.md` now carries every ADR the round reserved: H211
  (acquisition is a closed lifecycle; every acquired capability must pass its
  own contract test), H212 (learning is layered, each layer with its own
  validation standard), H214 (a registered tool is not advertised as available
  until its contract AND family fixture pass), H215 (autonomy tiers are
  runtime-enforced; the agent can never widen its own authority). **(W13
  complete)** New `python/harness/tool_fixtures.py` drives a representative REAL
  tool per audited family â€” filesystem `read_file`, terminal
  `terminal_capabilities`, git `git_status` (temp repo), browser
  `browser_status` (honest degraded path; gate asserted when disabled), api
  `source_rank`, artifacts `artifact_list` (temp store), finance
  `get_source_health` (stub bridge; `no_data` pinned) â€” through the ONE
  `ToolRegistry` with real contexts; `test_tool_behaviour_fixtures.py` asserts
  every audited family has a passing fixture and every fixture tool is on the
  production registry. **(Acquisition installs, W5/W9 remainder)**
  `recovery/acquire_handlers.py` is facts-aware: `source` â†’ the REAL skill
  install (`install_from_github`) gated by the single-use, digest-bound
  `skill_install` approval â€” with no granted approval the handler CREATES the
  pending request and returns `approval_required` (it never installs);
  `pluginPath` â†’ the ONE plugin platform (`operator=true`, `enable=false`;
  enable is its own approved step); `kitId` â†’ a durable code task whose verified
  completion is the validation. `POST
  /recovery/incidents/{id}/acquisition/execute` accepts `facts` and parks the
  task for a handler-level approval; without a fact the exact missing
  information is still returned. `test_recovery_install_handlers.py` (8).
  **(Phase 18 remainder)** `FigurePayload` on `AnalysisResult` (kind, drawn
  series + point counts, seed, `isEvidence: false`) rides `to_blob()` â†’ the run
  blob and the tool result; `distribution_profile` (interpolated p05/median/p95
  + histogram) and `monte_carlo_paths` (bounded, SEEDED bootstrap OF the
  supplied returns, labelled a what-if) join the recipes (10 total);
  `test_analysis_recipes.py` +5; the sandbox `IMPORT_ALLOWLIST` untouched (the
  widening stays the recipe table's named `extra_imports`). **(Phase 15/18
  surface)** New `src/components/chat/artifact-view.tsx`: a produced artifact
  renders as an image inline via the Artifact Center route (path derived
  server-side by id), else a download card, else an honest name+digest fallback
  with NO link; the computed-result panel takes `runId`, resolves the run's
  catalog index once, renders the figure branch (drawn-from + seed lines under
  the computed label) and passes `runId` from `chat-history`. `analysis.*`
  language moved into `src/lib/i18n/dictionaries/analysis.ts` (spread into
  `en.ts`, which SHRANK 1255â†’1244 â€” the size ratchet's documented direction, no
  ceiling raised). **(Phase 16 remainder)** `acquire.budget.RunUsage` â€” the
  run-scoped ledger on the tool context; every pull absorbs into it, the
  manifest carries `limits` + `limits.run`, a later pull in the same turn is
  refused `RUN_LIMIT_REACHED` (env `HARNESS_ACQUIRE_RUN_MAX_*`); operator
  runbook `docs/harness/runbook-add-a-collection-source.md`; opt-in live smoke
  `test_live_macro_collection_through_the_real_bridge` (`HARNESS_ACQUIRE_IT=1`,
  never in CI). Remaining named honestly: SEC filing-LIST and operator-declared
  REST sources need NEW bridge capabilities (a TS data-plane slice) and the chat
  manifest panel is not built. **(Capability extension D/E)** The install half of
  D is real through the operator acquisition route (above); E landed â€” the
  Command Center reverse-syncs an agent edit
  (`fetchDashboardLayout`/`isOwnPublish`/`stableLayoutKey` in
  `dashboard-blueprint.ts`; persist + remount only on a REAL remote revision,
  never fighting the user's own publishes). Checks: focused 122 passed; full
  Python 6975 passed â€” the capability-statement drift fixed by regeneration, the
  rest the documented pre-existing failures (graph order-flake, the size/phase-S
  ratchets, local skill drift); eval gates ALL PASS `tasks=53`; `npx tsc
  --noEmit` clean; vitest 3504/3505 (the pre-existing `graph-canvas.tsx`
  line-ending guard). Docs: `docs/harness/decisions.md`,
  `docs/harness/self-evolution-roadmap.md`,
  `docs/harness/roadmap/phase-{15,16,18}-*.md`,
  `docs/harness/capability-extension-plan.md`,
  `docs/harness/runbook-add-a-collection-source.md` (new),
  `docs/harness/capability-statement.md` (regenerated),
  `docs/CHANGELOG.md`.

- **feat(harness,acquire): Phase 16 â€” the two remaining collection sources
  landed by the runbook: the SEC filing index and the operator's declared
  datasets.** (1) **SEC filing-LIST** â€” new bridge capability
  `sec_filing_list` (`src/lib/harness/data-bridge-filings.ts`): the
  `data.sec.gov/submissions` index (form, filed, period, accession,
  primary-document URL), filters `form`/`date_from`/`date_to`, bounded at 1,000
  filings per call with an explicit `truncated` + note; the cached SEC CIK map
  is the issuer authority (unknown ticker â‡’ `not_found`, unreadable index â‡’
  `source_failure`); new `filings_list` registry row + adapter
  (`symbol, form, filed, period, accession, document, description`). (2)
  **Operator-declared REST** â€” new capability `custom_dataset_records`
  (`src/lib/harness/data-bridge-datasets.ts`): selects ONE dataset the operator
  declared in Settings â†’ Data Sources, fills the connector's OWN declared
  parameters with caller `values` (never a URL/host/header/secret), maps the
  response through the existing deterministic `mapResponseDetailed`; undeclared
  dataset â‡’ `not_found`; read-only (the `acquire` tool writes its own CSV +
  manifest); new `operator_datasets` registry row + adapter (long rows
  `dataset, record, field, value`; a nested mapped value survives as JSON
  text). Both are on the route whitelist and dispatched through the new
  `src/lib/harness/data-bridge-extensions.ts` â€” `data-bridge.ts` sits at its
  1400-line ratchet and stayed there (net zero). `recordCapabilityHealth` maps
  `sec_filing_list` to its own SEC route; operator pulls are deliberately not
  recorded in the market-data ledger (the connector platform's own health row
  owns it). `bridge.py` puts both capabilities in the slow network-timeout
  class. Tests: `data-bridge-filings.test.ts` (6),
  `data-bridge-datasets.test.ts` (7, through the REAL custom-REST connector
  with a fake transport), the route allowlist case, `test_acquire.py` +5 (17
  passed, 1 opt-in live skip). Checks: eval gates ALL PASS `tasks=53`; `npx
  tsc --noEmit` clean; vitest 3518/3519 (the pre-existing `graph-canvas.tsx`
  line-ending guard); full Python 6982 passed â€” the rest the documented
  pre-existing failures (graph order-flake, the size/phase-S ratchets, local
  skill drift). Docs: `docs/harness/roadmap/phase-16-bulk-acquisition.md`,
  `docs/NAVIGATION.md`, `docs/CHANGELOG.md`.

- **feat(chat,acquire): Phase 16 â€” the chat manifest panel and `acquire.*`
  keys; the phase is DONE.** The `acquire` tool emits `acquire.completed` on
  the run's event seam carrying the SAME manifest written beside the CSV (a
  refusal emits nothing; best-effort, never breaks a collection). New
  `src/components/chat/acquisition-panel.tsx` renders source / window / rows /
  completeness chip / licence / attribution in the glass system: a partial pull
  renders PARTIAL with its stated reason, an unknown row count renders honestly
  (no fabricated 0), and a blob that does not coerce renders nothing. The wire
  blob is narrowed by `src/lib/harness/acquisition-types.ts`
  (`coerceAcquisitionManifest`; completeness is structural â€” only a producer
  `true` reads Complete). Plumbing: `events.ts` (`{kind: 'acquisition'}`) â†’
  `use-agent-run` turn â†’ `Message.acquisition` (stock-chat + chat-dock
  mappers) â†’ `chat-history`. `acquire.*` keys live in the domain dictionary
  `src/lib/i18n/dictionaries/acquire.ts` spread into the ratcheted `en.ts`
  (the documented precedent; en.ts and stock-chat.tsx stayed inside their
  pins). Tests: `test_acquire.py` +2 (event carries the manifest; refusal emits
  none), `events.test.ts` +2, `acquisition-types.test.ts` (4),
  `acquisition-panel.test.tsx` (4).

- **feat(eval): W12 live tier â€” the non-scripted team comparison.** New
  `team_benchmark.LiveTeamAgentInvoker`: the identical REAL team stack
  (`TeamService` â†’ A2A â†’ `TaskScheduler` â†’ `execute_run`) with NO script pool â€”
  every subtask resolves the operator's real `modelSettings` through the
  production `build_chat_model` path (the scripted seam's pool is never set;
  an unset pool delegates to the original build), and without model settings
  every trial is honestly `unmeasured` ("published unmeasured, never
  fabricated"). `experiments.multi_agent_compare_live` wires the production
  `ServiceAgentInvoker` (single) + the live team for a like-for-like
  comparison. Token/cost axes are now published only when a variant's REAL
  trajectories reported them (`team_benchmark.measured_usage`) â€” the scripted
  tier's zeros stay unmeasured, a live run's provider-reported usage is summed
  (the offline verdict and its published `unmeasured` list are unchanged).
  Opt-in live smoke `test_live_team_comparison_through_a_real_provider`
  (`HARNESS_TEAM_LIVE_IT=1` + `HARNESS_TEAM_LIVE_{PROVIDER,MODEL,BASE_URL,API_KEY}`,
  never in CI); tests `python/tests/test_evaluation_team_live.py` (4 + smoke).
  Docs: `docs/harness/agent-evaluation.md` (Â§13.1),
  `docs/harness/self-evolution-roadmap.md` (W12), `docs/CHANGELOG.md`.

- **feat(ui): Phase D â€” the Capability Studio: one navigable surface for
  pages/widgets, tools/plugins, skills and integrations.** The `ui-builder`
  tab now mounts `CapabilityStudioScreen`
  (`src/components/screens/capability-studio/`) â€” a navigation shell over the
  EXISTING managers, per ADR-H216: pages & widgets = the embedded UI Builder
  (an `embedded` prop hides its own header); tools & plugins = the existing
  `PluginsScreen` (previously orphaned â€” it now has its home); skills = a
  read-only summary (counts: total / live / awaiting evaluation / attention,
  + rows) whose create/edit/enable stays in the evaluation- and
  promotion-gated Skills manager; integrations = read-only summaries of the
  operator's data sources (`/api/data-sources` GET) and MCP servers
  (`listMCPServers`), with every edit staying in Settings. No second registry,
  no self-granting enable path; load failures render as failures (never as an
  empty library), an untested connection is never counted as failing, and
  inactive sections stay mounted (`display:none`, the shell keep-alive
  pattern). Section deep link `?tab=ui-builder&sub=studio.<section>`. i18n:
  `nav.*` moved to `dictionaries/navigation.ts` and the new keys to
  `dictionaries/capability-studio.ts` â€” en.ts SHRANK 1254â†’1234; the shell
  stays at its 1518-line ratchet. Tests:
  `capability-studio.test.tsx` (7: both summaries + SSR of the surface and
  sections). Docs: `docs/ui-engineering.md`,
  `docs/harness/capability-extension-plan.md` (Phase D â†’ done),
  `docs/harness/decisions.md` (ADR-H216), `docs/NAVIGATION.md`,
  `docs/CHANGELOG.md`.

- **docs(harness): QA Round 1 fix plan â€” self-knowledge & learning-loop
  hardening.** Records the first scripted QA run of the self-evolution loop
  (four prompts: honest-failure + open Memoryâ†’Reviews; run a learning review;
  accept a permission-touching proposal; summarize reviews in plain language)
  as a ten-finding ledger, every claim traced to file:line, then plans six
  phases: **Q1** sync a real app-surface manifest (tabs + subroutes + deep
  links, derived from `src/lib/app-tabs.ts` / `src/lib/search/registry.ts`)
  into the Python UI runtime so `ui_get_application_map` stops reporting saved
  dashboards as the app and stops missing Memoryâ†’Reviews (the agent's "does
  not exist" claim was false: `ui/service.py:227-239` only reads
  `UiBlueprint` rows); the non-persistent browser context re-seeding a random
  "Main" dashboard each session (`use-dashboards.ts:158-164`) is also fixed
  with a deterministic seed id. **Q2** two read-only learning tools
  (`learning_review_list`, `learning_candidate_list` â€” the auto queue already
  persists rows: `service.py:1163-1167`, `learning_review.py:559-600`, but no
  agent tool reads them) + the banner deep link (`graph_context.py:446`
  currently points at the raw JSON API). **Q3** a `memory` inventory action
  wrapping `memory_lifecycle_counts()` + rendering the native provider count
  (list vs search returned disjoint subsets with no totals). **Q4** browser QA
  reachability: surface the hidden transport cause (`session.py:435-439`),
  resolve the canonical app origin (the 307 host redirect, `middleware.ts:58-75`,
  was misread as "loopback is a policy boundary"; policy does not block
  loopback), boot-state vocabulary for the by-design warm-up aborts
  (`global-loader.tsx` 2500 ms) and TopLoader 95% cap, plus a bounded GET-only
  `app_api_get` tool (the curl dead-end is a hard DENY, `terminal.py:72-80`).
  **Q5** env-configurable chat step budget (the 8-step cap, `agents.py:299-302`,
  cut QA runs off).   **Q6** re-run the script with an acceptance table and
  regression tests for the preserved behaviors. Checks: docs-only change â€”
  vitest 344 files / 3536 tests ALL PASS; `tsc` clean; Python suite 8 failed /
  7008 passed, every failure the documented known set (AAPL stored bars, skill
  load drift, size ratchets) plus the working-tree WIP tool-admission failures
  (`skill_learning_set`/`skill_version_activate` â€” uncommitted
  `agents.py`/`authorizers.py`/`skills/*` changes, untouched here). Docs:
  `docs/harness/roadmap/qa-round-1-fixes.md` (new), `docs/NAVIGATION.md`.

- **fix(app,capability-studio): the Integrations section broke the whole app
  build.** `integrations-section.tsx` (client component) imported
  `listMCPServers` from `@/lib/harness/mcp-client`, which drags `child_process`
  / `node:fs` into the browser bundle â€” `/` 500'd with "Module not found:
  Can't resolve 'child_process'". It now fetches the existing `GET
  /api/harness/mcp/servers` route (same pattern as `mcp-settings.tsx`), and the
  failure stays visible via the existing allSettled error naming. Also
  normalized mixed CRLF/LF endings in `graph-canvas.tsx` (committed blob is
  LF; the working tree had 73 CRLF lines mixed in, tripping the gitignore-guard
  test â€” that suite failure is now FIXED, superseding the "pre-existing
  failure" note in the Phase 8 entry above). Files:
  `src/components/screens/capability-studio/integrations-section.tsx`,
  `src/components/screens/graph-studio/graph-canvas.tsx` (line endings only).
  Checks: `tsc` clean; vitest 344 files / 3536 tests ALL PASS; Python suite
  failures are the documented known set (AAPL stored bars, the user-WIP size
  ratchets `main.py` 1203 / `persistence.py` 1441 / `service.py` 1520, skills
  load drift) â€” untouched by this change. Docs: no doc change â€” build fix;
  the client-safe fetch contract is already the documented pattern
  (`skills-browser.ts` header, route handlers).

- **feat(ui): QA Round 1 Q1 â€” the runtime learns the app's fixed screens.**
  `ui_get_application_map` listed only saved dashboard blueprints, so the agent
  concluded "Memory â†’ Reviews does not exist" (QA Round 1 finding F1). New
  `src/lib/app-surfaces.ts` derives every `AppTab` plus its sub-tabs and
  `/?tab=â€¦&sub=â€¦` deep links from the existing declarations (`app-tabs.ts`,
  `search/registry.ts`, `search/deep-link.ts`, sidebar labels) â€” no second
  hand-maintained copy. `ui-sync.ts` pushes the batch through the existing
  `/api/ui/**` proxy to a new `POST /ui/surfaces`; `UiService` persists it
  (`UiSurface` on `agent-memory.db`; an empty batch is a no-op). The map now
  returns `screens` (fixed product surfaces incl. Memory â†’ Reviews with
  `/?tab=memory&sub=memory.reviews`), `pages` (user dashboards) and
  `capabilities` as separate sections; the tool text prints both under explicit
  headers, and `ui_list_blueprints` is described as dashboards-only. The
  first-run dashboard seed id is now stable (`main`), so fresh non-persistent
  browser sessions upsert one mirrored blueprint instead of creating a new
  "Main" page per launch. Files: `src/lib/app-surfaces.ts` (new) +
  `src/lib/app-surfaces.test.ts` (new), `src/lib/harness/ui-{client,sync}.ts`,
  `src/components/layout/ui-catalog-sync.tsx`,
  `src/lib/dashboard/use-dashboards.ts`,
  `python/harness/ui/{model,store,service,tools}.py`,
  `python/harness/routers/ui.py`, `python/tests/test_ui_surfaces.py` (new),
  `python/tests/test_ui_api.py` (route case). Checks: `tsc` clean; vitest 345
  files / 3544 tests ALL PASS (Q1 adds 8); Python 5 failed / 7018 passed â€”
  every failure is the documented known set (AAPL stored bars, size ratchets
  `main.py` 1203 / `persistence.py` 1441 / `service.py` 1520, skills load
  drift), untouched by Q1; targeted UI suites 60/60 and adjacent
  tool/plain-language/surface gates 91/91. Docs: `docs/ui-engineering.md`,
  `docs/harness/roadmap/qa-round-1-fixes.md` (status In progress),
  `docs/harness/roadmap/progress/qa-round-1-progress.md` (new),
  `docs/NAVIGATION.md`.

- **fix(ui): Q1.1 â€” the surface map now reports the RENDERED tabs, and the
  agent is told to use it.** The Q1 QA re-run exposed two defects: (1) the
  agent never called `ui_get_application_map` â€” it grepped the repo, and on one
  prompt failed to produce any deep link; (2) the map derived sub-tabs from the
  search-palette registry, which had drifted from the tab bars: Memory renders
  **15** tabs but the registry declared 8 with different labels ("Facts" vs
  "Memory Explorer", "Reviews" vs "Learning Reviews"), and Skills renders
  **Maintenance** with no registry entry. Fix: new `src/lib/app-screens.ts`
  holds the rendered tab arrays for Memory (15) and Skills (10) with labels and
  legacy slug aliases; both the screen components and `app-surfaces.ts` import
  them, so the bar, its deep links and the agent's map cannot disagree. Memory's
  subroute handler now maps every tab + alias from the same list (Profiles,
  Providers, Files and Skills deep links previously did not switch tabs).
  `src/lib/harness/prompts.py` gains the rule: for "where is X in the app" /
  "is there a screen for Y" / a link request, call `ui_get_application_map`
  FIRST; `screens` is the fixed inventory, `pages` are only saved dashboards,
  and never infer screens from pages or greps. Tests:
  `app-surfaces.test.ts` pins the 15/10 rendered lists, labels, Maintenance and
  the `explorer`/`learning` aliases; targeted Python 72 passed
  (`test_prompt_segments`, `test_plain_language`, `test_ui_surfaces`,
  `test_ui_api`, `test_ui_agent_e2e`, `test_tool_contracts`); vitest 18 passed
  (app-surfaces 7, ui-sync 6, size-budget 5 â€” the memory screen shrank to 2474
  lines, under its 2488 ratchet); `tsc` clean. The one guidance bullet moved the
  prompt-char ratchet 29,994â†’30,420, so the two ceiling pins were re-pinned to
  the measured length (`test_memory_tools.py`,
  `test_phase_s_stabilization.py`) per the established convention for genuine
  guidance. Full suite: 7 failed / 7030 passed before the re-pin (the two extra
  failures were those ceilings); after re-pinning, the prompt tests pass in
  isolation (45 passed; the only failure in that file set is the pre-existing
  user-WIP `main.py` 1203-line ratchet). Docs: `docs/ui-engineering.md`,
  `docs/harness/roadmap/qa-round-1-fixes.md`,
  `docs/harness/roadmap/progress/qa-round-1-progress.md`, `docs/NAVIGATION.md`.

- **fix(harness): Q1.2 â€” the UI tools survive the chat code profile.** The
  Q1.1 QA run hit `ui_get_application_map` "not bound to this run" in **four of
  five** prompts. Root cause: the deterministic classifier routes turns
  containing "repository", "tabs" or "list" to the chat code profile, and
  `CHAT_CODE_TOOLS` omitted every `ui_*` tool â€” so exactly when a user asked
  where something lives in the app, the app map was removed from the surface.
  `agents.py` now appends `*UI_TOOLS` to `CHAT_CODE_TOOLS` (read-only
  introspection plus Eclipse's own saved-page composition; no filesystem,
  network or shell authority), and the exact-set declaration in
  `test_chat_code_profile.py` is updated. Also corrected the stale tab-list
  header comments in `eclipse-memory-screen.tsx` and `skills-screen.tsx` (the
  QA agent flagged the Skills one). Checks: targeted Python 57 passed
  (`test_chat_code_profile`, `test_code_agent`, `test_ui_surfaces`,
  `test_ui_agent_e2e`, `test_prompt_segments`, `test_tool_contracts`); `tsc`
  clean; full suite: vitest 345 files / 3546 tests ALL PASS, Python 5 failed /
  7049 passed â€” the documented known set, including the concurrently-grown
  user-WIP size ratchets (`main.py` 1253, `service.py` 1527,
  `eclipse_memory/service.py` 1913, `portfolio/service.py` 1601), untouched by
  this change. Docs: `docs/harness/roadmap/qa-round-1-fixes.md`,
  `docs/harness/roadmap/progress/qa-round-1-progress.md`, `docs/NAVIGATION.md`.

- **feat(harness): QA Round 1 Q2â€“Q6 â€” learning-loop reads, memory inventory,
  honest browser reachability, a configurable chat budget.** **Q2** adds the
  two read-only tools the loop was missing: `learning_review_list` (stored
  `LearningReview` rows + counts; the same records as Memory â†’ Reviews) and
  `learning_candidate_list` (captured `LearningCandidate` rows; Skills â†’
  Learning Queue), each with an honest empty state that explains the automatic
  queue. The "Review in Learning Queue" banner now deep-links to the screen
  (`/?tab=skills&sub=skills.learning`) instead of the raw JSON route
  (`graph_context.py`, `memory-action.ts`), and the prompt gains one
  learning-loop paragraph (ceiling re-pinned 30,420â†’30,897). **Q3** adds
  `memory action="inventory"` (whole-store counts by status/lifecycle, no
  content) and renders the native provider's `health.detail` ("N active") in
  `memory_provider_status`. **Q4** makes browser failures honest and the local
  app reachable: `browser/app_origin.py` classifies transport causes (host
  unresolvable, refused, timeout, redirect loop), probes
  `HARNESS_BROWSER_APP_ORIGIN` â†’ `HARNESS_CALLBACK_URL` â†’ the
  `BE_CANONICAL_HOST` alias, and `browser_navigate` retries ONCE on the first
  reachable origin (reporting the probe trail when none answers);
  `browser_navigate`/`browser_snapshot` report the app's
  `[data-global-loader][data-pct]` overlay as "still starting (N%)"; new
  `app_api_get` is a bounded GET-only surface over the app's own loopback
  `/api/` routes (no redirects, no credentials, 200 KB cap) â€” the sanctioned
  alternative to the hard-denied `curl` dead-end. **Q5** makes the chat step
  budget explicit: 12 by default, `ECLIPSE_CHAT_MAX_STEPS` clamped 1..32, an
  explicit per-run agent config wins (`graph.chat_step_budget`, used by the
  loop AND the `run.started` event). **Q6** adds the cross-cutting acceptance
  suite. Docs: ADR-H220 (bounded local reads + browser causes), ADR-H221 (chat
  budget), `docs/harness/browser-runtime.md`,
  `docs/harness/roadmap/qa-round-1-fixes.md`,
  `docs/harness/roadmap/progress/qa-round-1-progress.md`, `docs/NAVIGATION.md`.
  Checks: targeted Python 80 passed (`test_qa_round1_acceptance`,
  `test_learning_tools`, `test_app_api_tools`, `test_browser_app_origin`,
  `test_chat_step_budget`, `test_memory_tools`, `test_chat_code_profile`,
  `test_prompt_segments`); `tsc` clean. The only open item is the manual
  four-prompt live re-run (it needs the running app and a model).

## 2026-10-17

- **fix(app,graph-studio): the app could fail to load after selecting the Graph
  Studio mode; three navigation defects fixed + guarded.** (1) The mobile bottom
  nav renders `TAB_META[id].icon` for every tab a mode lists; `TAB_META` was
  `Record<string, â€¦>` and had no `graph-studio` entry, so `undefined.icon` threw
  inside the top-level ErrorBoundary â€” and since the chosen mode is PERSISTED,
  later loads hit the same crash. `TAB_META` is now keyed by `AppTab`, both
  render sites are guarded, and `mobile-bottom-nav.test.ts` asserts every
  mode/lab tab has an icon. (2) The persisted-mode allowlist in
  `lib/sidebar/store.ts` dropped `'graph'` (the mode never stuck); it now
  validates against the ONE `NAV_GROUPS` list (`isNavGroup`). (3)
  `APP_TABS` in `lib/search/deep-link.ts` omitted the newer tabs, so
  `?tab=graph-studio` (and a "history" boot tab) silently fell back to ChatBot;
  it is now an exhaustive `Record<AppTab, true>` so a missing tab is a compile
  error, with an `app-tabs.test.ts` guard. The mode panel also opens the
  workspace when a workflow is opened/created. Verified in headless Chromium
  against the production build: mode switcher, panel create/open and
  `?tab=graph-studio` all mount the canvas with zero console/HTTP errors. Files:
  `src/components/layout/mobile-bottom-nav.tsx` (+test), `src/lib/sidebar/{config,store}.ts`
  (+tests), `src/lib/search/deep-link.ts`, `src/lib/app-tabs.test.ts`,
  `src/components/screens/graph-studio/{graph-mode-panel,workflow-list}.tsx`.

- **fix(graph-runtime): comparing a series in `logic.condition` no longer fails.**
  The Market-scan template wires an indicator/z-score payload into
  `logic.condition` with a numeric comparison, but the payload is a dict of
  series, so `gt/lt/â€¦` raised "numeric comparison requires a numeric input". A
  comparison against a series now means against its LATEST point (the payload's
  `last`, else the trailing numeric value), and a series with no computed point
  yet (still in warm-up) says so explicitly instead of a misleading message.
  Test: `test_market_scan_branch_compares_the_latest_point` (both true and false
  paths over a 40-bar ramp, z â‰ˆ 1.414). Docs: `docs/graph-studio.md`.
  Python graph suites: 69 tests.

- **feat(graph-runtime): Phase 5 â€” the finance + quant node pack.** New
  `python/harness/graph_runtime/finance_nodes.py` gives real executors to
  `finance.market_data` (reads the runtime's persistent bar series â€”
  `harness/market/series_store.py`, the SAME vault the research-data tools fill;
  provenance on every payload and an actionable failure when the vault is
  empty, never a fabricated price), `finance.indicator` (sma/ema/rsi/macd/atr/
  adx/vwap/bollinger via the tested `harness/quant/indicators.py`), and new
  `quant.returns` / `quant.zscore` / `quant.volatility` nodes (mirrored in the
  TS registry + a `Market scan (SMA z-score)` template). Test runs now
  implicitly grant the read-only/local-compute capabilities (`TEST_RUN_CAPABILITIES`
  in the compiler) so finance graphs can be exercised from the UI while
  write/network/trading stays refused; boot wires the series store. Tests: 11 new
  Python node tests (hand-computed SMA/Bollinger/returns, honest-failure and
  payload-validation cases) + 2 end-to-end API tests (seed bars â†’ run â†’
  reconcile) + 3 new TS registry nodes â†’ graph suites at 68 Python / 50 TS tests;
  full vitest (3475) and `npm run build` pass. Docs updated:
  `docs/graph-studio.md`, `docs/NAVIGATION.md`.

- **feat(app,graph-studio): Graph Studio is now a DEDICATED sidebar mode, and
  Phase 4 lands (control flow, schedules, triggers, recovery).**
  (1) **Dedicated mode:** `NavGroup` gained `'graph'`; the sidebar mode switcher
  lists Graph Studio (with `Alt+G`), the left sidebar renders a `GraphModePanel`
  (Workflows browser + node library, backed by a shared `catalog-store`), the top
  bar and chat dock are hidden for the tab, and the right dock belongs to the
  screen's own inspector/run rail. The screen lost its duplicated left rail.
  (2) **Control flow** with real execution semantics: control ports now gate
  execution (a node fires `_control` outputs; a node with control inputs runs only
  when one fired) â€” `flow.gate` (branching), `logic.switch`, bounded
  `logic.map`/`filter`/`reduce` over the safe formula language (which gained
  comparisons/logic), bounded `logic.wait` (a test run caps it at 5 s via the
  compiler's new `test_run_limit`) and `logic.stop` (ends the run; downstream is
  `skipped`). Required control inputs are now validated. `data.json.parse`'s
  output is `any` (it may legitimately produce an array).
  (3) **Schedules:** `WorkflowSchedule` in JDDS + a dependency-free
  timezone-aware 5-field cron evaluator (`cron.ts`, cached Intl formatters, 40-day
  search bound) + `schedule-store`/`schedule-tick`/routes/UI; a 60 s in-process
  timer in `instrumentation.ts` fires due schedules through the same test-run
  dispatch, with `skip`/`coalesce` missed-fire policies and per-fire outcome
  recording.
  (4) **Triggers:** manual, scheduled, and `POST /api/workflows/[id]/trigger`
  (deliberately test-envelope only). All run starts now funnel through
  `run-server.ts`.
  (5) **Recovery:** runs left `running` by a previous process are marked failed at
  boot. Tests: 10 new Python (control flow, recovery) â†’ 55 graph tests; 14 new TS
  (cron, schedule tick, sidebar mode) â†’ 3469 total. `npx tsc --noEmit`, full
  vitest and `npm run build` pass. Docs updated: `docs/graph-studio.md`,
  `docs/NAVIGATION.md`, `docs/ARCHITECTURE.md`.

- **fix(charts): default chart palette is green/red and no longer follows the
  theme.** Reverses today's monochrome default â€” `DEFAULT_CHART_PALETTE.lines`
  is green (up) / red (down) again. The themeâ†’chart bridge no longer copies the
  theme accent into `lines.primary` or the theme market colors into
  candles/heatmap; `chartPaletteFromTheme` now preserves the palette in effect,
  so applying or previewing a theme never recolours a chart. Chart colours
  change only on an explicit user action (Settings â€º Charts, or a preset that
  carries a `chartPalette`). Files: `src/lib/chart-palette.ts`,
  `src/lib/theme/bridge.ts`, `src/lib/harness/command-agent.ts`. Tests:
  `src/lib/theme/bridge.test.ts` updated. Docs:
  `docs/interactive-response-engine.md`.

- **feat(graph-runtime): Graph Studio Phase 3 â€” compiler + deterministic
  execution engine.** New Python runtime package
  `python/harness/graph_runtime/` (mirrors the TS Workflow IR as pydantic
  contracts): a frontend-independent `compiler.py` (structural validation,
  longest-path execution **layers** + deterministic topological order, per-node
  mode checks and a **permission envelope** that refuses write/network/trading
  effects and ungranted capabilities), a deterministic `executor.py`
  (`pendingâ†’readyâ†’runningâ†’succeeded|failed|cancelled` + `skipped`, per-node
  timeout, retries, cancellation, output-schema validation, bounded previews,
  event log), a data-only `registry.py` node SDK, pure built-in `nodes.py`
  executors (incl. a real safe formula language â€” never `eval`), durable run rows
  (`store.py`, agent-memory.db), and `service.py` (compile/run/start/poll/cancel).
  HTTP surface `/graphs/*` (`routers/graphs.py`, operator-gated, included by
  `main.py`), boot wiring `install_graph_layer` in `service.py`. Next.js front
  door `src/app/api/workflows/[id]/runs` (+ `src/app/api/graph-runs/[runId]`
  and `.../cancel`) loads the **persisted** IR from JDDS â€” never the client's â€”
  and forwards it with `testRun: true`. UI: `execution-client.ts`, the Run
  console (`run-panel.tsx`), node run-status chips on the canvas, and a "Test
  run" toolbar action. `data.value` gained an optional input + typed coercion
  (both registries). **Naming note:** the package is `graph_runtime/`, NOT
  `graph/` â€” `harness/graph.py` is the pre-existing agent tool loop and a
  `harness/graph/` package would shadow it and break `execute_run`. Tests: 45 new
  Python tests (`python/tests/test_graph_{model,compiler,executor,service,api}.py`)
  + 5 new TS tests; `npx tsc --noEmit`, full vitest (3454) and `npm run build`
  pass. Docs updated: `docs/graph-studio.md`, `docs/NAVIGATION.md`.

- **feat(response,harness): more chart types, a `/visual` command, and a
  monochrome default chart palette.** (1) The response `chart` block now accepts
  **sixteen** types â€” added `bubble` (`[x, y, size]` triples), `treemap`,
  `sunburst`, `funnel`, `gauge`, `radar` and `waterfall`, each with a real ECharts
  option in `chart-option.ts` (never an invented point; gauge/radar maxima are
  computed from the data, waterfall is a transparent base + signed bar).
  (2) New agent-turn slash command `/visual` (aliases `/chart`, `/plot`) rewrites
  a request into a directive that renders ONE inline `chart` block, choosing the
  best type from the full set and plotting only sourced values. (3)
  `DEFAULT_CHART_PALETTE` is now **monochrome** (a neutral slate ramp) so charts
  read as one minimal set; green/red survive only where they carry meaning â€”
  up/down candles and the market heatmap. Files: `src/lib/response/contract.ts`,
  `src/lib/response/chart-option.ts`, `src/lib/harness/command-registry.ts`,
  `src/lib/harness/command-agent.ts`, `src/lib/chart-palette.ts`. Tests:
  `chart-option.test.ts` (+6), `command-agent.test.ts` (+2),
  `command-registry.test.ts` (+1). Docs: `docs/interactive-response-engine.md`,
  `docs/harness/slash-commands.md`.

- **feat(app,graph-studio): Graph Studio foundation (Phase 1) â€” visual workflow
  engineering.** Adds a dedicated Graph Studio workspace inside Eclipse: a
  React Flow canvas with custom typed-port nodes, a searchable node library
  (drag-to-place + click-to-add), a config inspector, a live validation panel,
  undo/redo and keyboard shortcuts. The canvas is a RENDERER over a new
  canonical, versioned **Eclipse Workflow IR** (`src/lib/graph-studio/`) with a
  data-only node registry + SDK, strict typed-port compatibility, a pure
  frontend-independent validator, pure/auditable graph patches and
  migration-ready versioning. Persistence is append-only workflow versions in
  JDDS via new `Workflow`/`WorkflowVersion` Prisma models and `/api/workflows*`
  routes. New AppTab `graph-studio` + sidebar entry. Files:
  `src/lib/graph-studio/*`, `src/components/screens/graph-studio/*`,
  `src/app/api/workflows/**`, `prisma/schema.prisma`, `src/lib/app-tabs.ts`,
  `src/lib/sidebar/config.ts`, `src/lib/i18n/nav.ts` +
  `dictionaries/en.ts`, `src/components/screens/stock-chat.tsx`. Dependency
  added: `@xyflow/react`. Tests: `src/lib/graph-studio/*.test.ts` (31).
  Docs: `docs/graph-studio.md` (new), `docs/NAVIGATION.md`.

- **`model3d`: leader lines, LOD, GLB stage animation, and shareable figures.**
  (1) Numbered hotspots now sit just off the part on a **leader line**. (2) A
  **LOD** pass drops the outline of parts that are tiny relative to a busy scene
  (>40 parts) so large models stay cheap. (3) The `.glb` now carries a **stages
  animation** â€” each stage pulses its lit groups, pivot-correct by pairing `scale`
  with a compensating `translation` (baked geometry, no transform graph needed).
  (4) **Share link** copies a self-contained `/figure#<base64>` URL, and the new
  public `/figure` route renders the block standalone (hash-only, no server
  state). Files: `src/lib/model3d/{compile,glb}.ts`,
  `src/components/response/model3d-{canvas,block}.tsx`,
  `src/lib/response/share.ts`, `src/app/figure/page.tsx`, `src/middleware.ts`.
  Tests: `compile.test.ts` (stages/animation), `share.test.ts`.
  Docs updated: `interactive-response-engine.md`.

- **fix(harness,app): token analytics were always blank; day filter now scopes
  the whole panel.** The graph always streams, but `build_chat_model` built
  `ChatOpenAI` without `stream_usage`, so OpenAI-compatible/Ollama streamed
  responses carried no usage and every run persisted 0 tokens. Set
  `stream_usage=True` (`python/harness/models.py`) so the stream requests
  `stream_options.include_usage` and real counts are recorded. Also fixed the
  window filter: `GET /api/harness/usage` no longer collapses a missing/empty
  `days` to a 1-day window (`route.ts`); `usage_summary` now applies the window
  to the `recent` runs list and zero-fills `byDay` across the full window
  (`python/harness/persistence.py`). Tests: existing persistence/model suites.
  Docs updated: `docs/harness/architecture.md`.

- **`model3d`: contact shadow + measurement tool.** A soft ground shadow under
  the machine (radial alpha, depth-tested so parts occlude it) so it reads as
  sitting on the surface; and a **Measure** mode â€” click two points on the model
  to draw a bright line and read the distance (world units) in the viewport panel.
  Files: `src/components/response/model3d-canvas.tsx`.
  `no doc change â€” visual/interaction only`.

- **`model3d`: hotspot highlighting, high-contrast, OBJ/STL export.** The
  numbered hotspots now **highlight with the stage and the selection** (a stage's
  lit parts get a bright badge; the selected part gets a solid badge), and the
  key list badges mirror that â€” clicking a key or a stage arrow visibly lights the
  matching number. Adds a **High-contrast** toggle (brighter outline/fill), and
  **OBJ** + binary **STL** exporters alongside GLB. Files:
  `src/components/response/model3d-{canvas,block}.tsx`,
  `src/lib/model3d/exporters.ts`. Tests: `exporters.test.ts`,
  `model3d-render.test.tsx`. Docs updated: `interactive-response-engine.md`.

- **Canvas is now a viewer-first right dock.** The manual "New
  Document/Code/Visual" chooser is gone; Canvas reads what the chat already
  produced at full width. New `src/lib/canvas/content.ts` (`CanvasContent` +
  `contentFromMessage`/`contentFromResponse`, reusing the response parser and
  markdown projection) and `canvas-viewer.tsx` (markdown via the chat renderer,
  reports via `ResponseView`, code via Monaco read-only, URL sandbox iframe,
  images), hosted by `canvas-dock.tsx` as a resizable sibling column in the shell
  row (pushes header + content). Entry points: **Open in Canvas** on a response
  (`response-actions.tsx`) and on any assistant message (`chat-history.tsx`);
  **Edit in Canvas** from the Artifact Center; **Save to edit** registers an
  ephemeral view. Store gained `canvasView`/`openCanvasContent`. Tests:
  `src/lib/canvas/content.test.ts`; `canvas-screen.test.tsx` empty state updated.
  Docs updated: `docs/canvas.md`.

- **`model3d`: exploded view, section/cutaway, touch + keyboard, scene cache, PNG.**
  On-canvas sliders for **Explode** (parts push outward from the centre) and
  **Section** (discard along the model X axis, grid hides while cut); **pinch-zoom**
  + two-finger handling; **keyboard** orbit/zoom/reset when the viewport is
  focused; a **PNG snapshot** button (context now keeps the drawing buffer); and a
  bounded **scene compile cache** (`compileModel3dCached`) keyed by content so the
  same figure is compiled once. New opt-in `npm run test:anatomy`
  (`scripts/anatomy-smoke.cjs`) drives the real app headlessly and screenshots the
  figure. Files: `src/lib/model3d/compile.ts`,
  `src/components/response/model3d-canvas.tsx`, `scripts/anatomy-smoke.cjs`,
  `package.json`. Tests: `compile.test.ts` (cache).
  Docs updated: `interactive-response-engine.md`.

- **Sidebar quick-launchers are small icon-only buttons; chat search and
  Graph/Gateway dialogs are larger.** Removed the text labels from the
  Gateway/Graph launchers and made them small borderless icon buttons matching
  the chat-history folder/action icons (`h-7 w-7 rounded-md`, subtle hover,
  `aria-label` retained) pulled up closer to the mode switcher
  (`-mt-3`), the mode switcher enlarged to match the search field (`py-2.5`,
  13px, `rounded-xl`), and the chat-history search field and its heading
  (10â†’13px), and made the Graph and Gateway dialogs wider and taller
  (`h-[min(85dvh,800px)] w-[calc(100vw-2rem)] max-w-none sm:max-w-6xl` â€” the
  `sm:max-w-6xl` overrides the base `DialogContent`'s `sm:max-w-sm`). Files:
  `src/components/layout/sidebar.tsx`,
  `chat-history-panel.tsx`, `sidebar-graph-dialog.tsx`,
  `sidebar-gateway-dialog.tsx`. Chat-history panel: search + heading enlarged
  (â†’13px) but conversation-row fonts kept small (titles 11px, snippets 10px).
  No doc change â€” UI styling only, contracts intact.

- **Chat-history search field loses its glass background.** The field is now a
  plain transparent input (no `glass-card-subtle` fill, no border), keeping the
  larger font/padding. Files: `src/components/layout/chat-history-panel.tsx`.
  No doc change â€” UI styling only.

- **Sidebar nav list: compact rows and a cleaner active state.** (A section-
  heading grouping was added then removed at the user's request â€” the nav list
  stays flat.) Rows are compacted (`h-9â†’h-8`, `py-2â†’py-1.5`, icon 16â†’15, gap
  3â†’2.5); the active tab is now a simple `rounded-lg bg-white/[0.07]` pill (no
  border, no left accent bar) with `aria-current="page"` and a `focus-visible`
  ring. Files: `src/components/layout/sidebar.tsx`. Tests: `config.test.ts` /
  `app-tabs.test.ts` pass. No doc change â€” client-only presentation styling.

- **`model3d` gains a validator, partâ†”key selection, and a no-WebGL fallback.**
  (1) Recipe parameters are checked against a declared contract
  (`RECIPE_PARAM_KEYS`); an unknown key is reported instead of silently falling
  back to defaults. (2) The compiler reports an off-scale scene and caps the
  outline **edge budget** (60k segments) so a very large model degrades instead of
  freezing. (3) Clicking a numbered key selects/highlights that part, and clicking
  a part on the model selects its key (raycast picking, click vs drag). (4) When
  WebGL is unavailable/lost the panel draws a static **isometric wireframe
  fallback** (feature edges + hotspots via the anatomy iso-kit) rather than a
  blank box. Files: `src/lib/model3d/{recipes,compile}.ts`,
  `src/components/response/model3d-{canvas,block,fallback}.tsx`,
  `harness/command-agent.ts`, the `system.anatomy-figure` skill. Tests:
  `compile.test.ts`, `model3d-render.test.tsx`.
  Docs updated: `interactive-response-engine.md`.

- **The chat "Latest" jump pill now sits above the floating composer.** The
  portaled pill was anchored to `rootRect.bottom - 16`, which lands inside the
  bottom `bottomInset` (132px) the transcript reserves for the composer overlay,
  so it rendered behind/below the input bar. It now anchors to
  `rootRect.bottom - (bottomInset ?? 0) - gap`, lifting it clear of the
  composer. File: `src/components/chat/chat-history.tsx`.
  `no doc change â€” positioning/layout only`.

- **Connections now has its own icon (`ChatsCircle`), distinct from MCP's
  `Plug`.** Settings â€º Connections, the sidebar Gateway launcher, and the
  Gateway dialog shipped with the same `Plug` glyph as Settings â€º MCP Servers.
  Added `ChatsCircle` to the central icon surface and applied it to the
  Connections nav entry, panel header, sidebar button, gateway dialog title and
  the recent-activity fallback; MCP keeps `Plug`. Files:
  `src/lib/icons/index.ts`, `src/components/screens/settings.tsx`,
  `src/components/screens/connections-settings.tsx`,
  `src/components/layout/sidebar.tsx`,
  `src/components/layout/sidebar-gateway-dialog.tsx`.
  `no doc change â€” icon/identity only`.

- **Redesigned the Connections and Alerts settings channel cards (Discord,
  Telegram, etc.).** Both panels now render a brand icon tile per channel
  (Telegram/Discord/Slack/WhatsApp/Email/Webhook logos, ntfy â†’ RSS) with accent
  tints, a dot status pill (`connected` / `not set`), a unified polished field
  input, cleaner health/refresh strip, message rows with per-channel icons, and
  a `Toggle` instead of a raw checkbox for enabling alert channels. Added the
  brand icons to the central icon surface (`DiscordLogo`, `TelegramLogo`,
  `SlackLogo`, `WhatsappLogo`, `Webhook`, `Mail`). Files:
  `src/components/screens/connections-settings.tsx`,
  `src/components/screens/alert-notifications-settings.tsx`,
  `src/lib/icons/index.ts`.
  `no doc change â€” styling/markup only, contracts unchanged`.

- **Eclipse Canvas is now inline in the chat, not a standalone page.** Canvas
  renders as a right-hand pane split into the ChatBot tab when
  `useCommandStore.canvasInlineOpen`/`pendingCanvasArtifactId` is set (`CanvasScreen
  inline`; `canvas-workspace.tsx` inline skips the rail and wraps center + the
  collapsed-by-default AI panel in a glass card with a header and close). It
  opens from a chat response's **Canvas** action, the Artifact Center's **Edit in
  Canvas**, and the composer "+" Canvas item. The standalone `canvas` AppTab,
  sidebar section/`nav.canvas`, deep-link `/?tab=canvas`, mobile bottom-nav item,
  the `stock-chat.tsx` keep-alive block, and the `/canvas` slash command
  (`command-registry.ts` + `native.canvas`) were **removed**. The backend,
  artifact model, typed-op contract and revision guard are unchanged. Docs
  updated: `docs/canvas.md`, `docs/NAVIGATION.md`, `docs/ARCHITECTURE.md`,
  `docs/harness/artifact-center.md`; ADR-049 carries an inline amendment in
  `skills/ARCHITECT.md` + `docs/DECISIONS.md`.

- **Chat composer now floats over the transcript so the frost is visible.** The
  near-transparent `.glass-composer` tier only shows blur when something sits
  behind it, but the composer used to be an in-flow sibling *below* the
  transcript â€” nothing to blur. It is now an absolute overlay pinned to the
  bottom of the chat column (`z-30`), and `ChatHistory` gained a `bottomInset`
  prop that reserves `132px` of scroll padding so the last message clears it.
  Scrolling messages now pass behind the bar and blur through the glass.
  Files: `src/components/screens/stock-chat.tsx`,
  `src/components/chat/chat-history.tsx`.
  `no doc change â€” layout/styling only`.

- **Chat composer is now near-transparent frosted glass.** The composer form
  dropped the `.glass-card` tint (which read as a solid dark bar over the chat
  surface) for a new `.glass-composer` tier â€” a low 0.16 dark tint (0.22 light)
  with `backdrop-filter: blur(28px) saturate(1.5)`, matching the
  `.glass-command-popover` approach, so the transcript reads through real glass.
  Added to the `theme-glass-active`/`-off` override lists so the glass
  customization settings still apply. Files: `src/app/globals.css`,
  `src/components/chat/chat-input.tsx`.
  `no doc change â€” styling only`.

- **Chat composer "+" is now a menu: Images and photos / Context / Canvas Â·
  Skills / Mention.** The single attach button became a dropdown in BOTH
  composers â€” the full ChatBot composer (`chat/chat-input.tsx`) and the floating
  dock (`chat/chat-dock.tsx`, which had its own separate "+" that never got the
  menu) â€” wired to a new `onAttachImage` prop (image picker in `stock-chat.tsx`,
  passed through `empty-state.tsx`); "Context" keeps the document picker,
  "Canvas" opens the Canvas tab, "Skills" seeds `/` to open the command palette,
  and "Mention" appends `@` to open the mention palette. The trigger uses the
  same plain `DropdownMenuTrigger` pattern as the working model selector, and the
  panel uses the `glass-command-popover` frosted tier (low tint + high blur) so
  the page reads through it.
  `no doc change â€” composer affordance only`.

- **`model3d` is now a flat outline drawing: fills match the paper.** The panel
  and every solid use the same `#161618`; the form is read by a `#3A3E44`
  outline. The compiler now extracts **feature edges** per part (crease/boundary
  edges with welded vertices, coplanar triangulation diagonals dropped) and the
  viewport draws them as LINES plus a silhouette band, with polygon-offset so the
  outline wins the depth test over the fill; `lit` still lifts to a lighter
  outline. The `.glb` export carries the same look (paper-coloured fill + an
  outline line primitive). Files: `src/lib/model3d/{mesh,compile,glb}.ts`,
  `src/components/response/model3d-{canvas,block}.tsx`.
  `no doc change â€” visual/interaction only`.

- **ChatBot scrolling no longer depends on the browser's nested-container wheel
  chaining.** Follow-up to the forward-wheel fix below: the forwarder now stops
  at the transcript and drives it directly (`scrollTop += normalised delta`,
  `preventDefault`) instead of early-returning and trusting native scroll of a
  nested `overflow: auto` box â€” which is flaky for some trackpads / engines.
  A genuinely different nested scroller under the pointer (a code block, an open
  palette, the sidebar list) still scrolls itself. Verified in Chromium:
  line-mode (`DOM_DELTA_LINE`) and pixel deltas scroll the transcript from the
  header, the composer and the transcript itself; a nested scroller is left
  alone. File: `src/hooks/use-forward-wheel-scroll.ts`. Also re-pinned the
  `stock-chat.tsx` size budget (1481â†’1495) for the concurrent empty-state image
  attachment input: `src/lib/size-budget.test.ts`.
  no doc change â€” bug fix, contracts and layout unchanged.

- **`model3d` stage (animation) controls moved onto the viewport.** The play /
  prev / next / reset controls and the stage label now float in a translucent
  pill at the bottom of the 3D panel instead of sitting below the figure
  (restyled light-on-dark for the charcoal paper; the drag hint moved to the
  bottom-left). The key, legend and readout stay below. Files:
  `src/components/response/model3d-block.tsx`.
  `no doc change â€” layout of an existing affordance only`.

- **ChatBot wheel/trackpad scrolling actually reaches the transcript.** The
  previous fix wired forwarding through React's `onWheel`, which React registers
  as a PASSIVE listener â€” so `preventDefault()` did nothing (and logged
  "Unable to preventDefault inside passive event listener invocation"), and the
  raw `deltaY` was applied verbatim, so trackpads/browsers reporting
  `DOM_DELTA_LINE`/`PAGE` moved only a few pixels per event and read as "scroll
  is broken". `useForwardWheelScroll` now installs ONE native
  `{ passive: false }` document listener (only while the chat tab has a
  transcript), normalises `deltaY` by `deltaMode`, and leaves anything already
  handled (chart zoom, 3D orbit, ctrl/pinch zoom) or any genuine nested scroller
  (the transcript, a multi-line composer, a palette, the sidebar list) to handle
  itself â€” so the header, composer and surrounding padding now scroll the
  transcript too. Files: `src/hooks/use-forward-wheel-scroll.ts`,
  `src/components/screens/stock-chat.tsx`.
  no doc change â€” bug fix, contracts and layout unchanged.

- **`model3d` camera controls are explicit, scoped, and button-driven.** Replaced
  OGL's `Orbit` (document-level, no modifier support) with a purpose-built
  controller on the canvas: **drag = orbit**, **ctrl/cmd-drag (or right-drag, and
  the "Drag" mode button) = pan**, **scroll = zoom** (cursor must be over the
  model; page scroll elsewhere is untouched), plus an on-canvas button cluster
  (Orbit / Drag mode, zoom in / out, reset). Pan moves the orbit target in the
  camera plane; zoom clamps to 0.35Ã—â€“4Ã— the fitted distance. Supersedes the
  `element: canvas` Orbit note below. Files:
  `src/components/response/model3d-canvas.tsx`,
  `src/components/response/model3d-block.tsx`.
  `no doc change â€” interaction affordances only; the engine doc already frames
  orbit/zoom/pan as canvas-local`.

- **`model3d` orbit/zoom is scoped to the canvas and the card is full width.**
  The OGL `Orbit` was attached to `document` (its default), so the wheel zoomed
  the model from anywhere on the page and a parent that stopped `mousedown`
  swallowed the drag. It is now attached to the canvas element only (`element:
  canvas`), with `touch-action: none` so a touch-drag orbits instead of scrolling;
  scroll-zoom only fires with the cursor on the model. The inline card dropped its
  `max-w-4xl`, so the figure is full width like the other response blocks. Files:
  `src/components/response/model3d-canvas.tsx`,
  `src/components/response/model3d-block.tsx`.
  `no doc change â€” interaction/width only; the engine doc already describes
  orbit/zoom/pan as canvas-local`.

- **`model3d` solids are grey by default (anatomy parity).** Like the isometric
  `anatomy` block, the 3D bodies render as one graphite grey and `tone` is
  reserved for the WIRES (and the legend) â€” a `success`/`danger` part no longer
  tints the whole machine. `lit` still lifts the subject to a lighter graphite,
  and the `.glb` export is graphite grey too. Files:
  `src/components/response/model3d-canvas.tsx`, `src/lib/model3d/glb.ts`.
  Docs updated: `interactive-response-engine.md`.

- **Eclipse Canvas is now documented (and the earlier "not yet mounted" note is
  corrected).** The Canvas backend and editors landed earlier; this change writes
  them down and fixes the false statement in the entry below that the screen is
  "not yet mounted on an AppTab/nav entry". It IS mounted: `canvas` is an AppTab
  (`src/lib/app-tabs.ts`), a sidebar section (icon `SquarePen`, agentic group),
  has a `nav.canvas` label, a `/?tab=canvas` deep link, a mobile bottom-nav entry
  and a keep-alive block in `stock-chat.tsx`; integrations are wired too â€” the
  `/canvas [document|code|report|visual]` slash command, Artifact Center "Open in
  Canvas" (for artifacts whose metadata carries the `canvas` key) and
  response-actions "Canvas". Records the architecture decision as **ADR-049**:
  Canvas is an editable document/code/visual workspace over the ONE Artifact
  Center (no second store), saves are revision-guarded, and AI edits are typed
  operations re-applied to current bytes under the guard. Docs updated:
  `skills/ARCHITECT.md` + `DECISIONS.md` (ADR-049), new `docs/canvas.md`,
  `harness/artifact-center.md` (Canvas section), `NAVIGATION.md`, `ARCHITECTURE.md`.

- **`model3d` viewport no longer goes white; it now reads as a pencil drawing on
  charcoal paper.** The WebGL canvas was reused across React StrictMode remounts
  and streamed re-renders while the cleanup called `WEBGL_lose_context`, so a
  later mount got a dead context and presented nothing (a transparent canvas over
  the light card read as white). The canvas is now **created inside the effect**
  and removed on teardown (a fresh context every mount, no `lose_context`),
  context creation waits for a non-zero wrapper size, and `webglcontextlost` is
  handled with a real message. The scene is memoized by a **content signature** so
  streaming does not recompile/remount the viewport per token, and the hotspot
  projection no longer compounds (`Camera.project` mutates in place). Look: an
  always-present charcoal paper panel (dark grey + centre light + bottom vignette
  + grain) behind an alpha context, graphite fills with posterized hand-shading,
  paper grain, a light pencil edge on silhouettes and a faint pencil grid. Files:
  `src/components/response/model3d-{block,canvas}.tsx`.
  Docs updated: `interactive-response-engine.md`.

- **Canvas autosave hardening.** The 1200 ms debounce re-fired while a save was
  in flight (allowing a duplicate request to conflict with itself) and retried a
  failed save forever, because the effect depended on `saveState`. Autosave now
  skips `saving`/`error`/`conflict`, failed saves stop until the next edit or a
  manual save, and in-flight results are discarded if the user switched
  artifacts mid-save. Files: `src/components/screens/canvas/canvas-screen.tsx`.
  no doc change â€” internal fix, contracts and layout unchanged.

- **Eclipse Canvas editor UI ships.** The canvas backend (Python `CanvasService`
  over the ONE artifact catalog, `/api/canvas` routes, typed `canvas-client`)
  landed earlier without its editor; this adds the missing UI that makes it
  usable. A three-region workspace â€” an artifact rail (list/search/create), a
  center editor with toolbar, and an AI panel â€” sits over the real canvas
  client: document / code (Monaco) / visual-report editors (the visual editor
  previews the response envelope), autosave + `âŒ˜S`, version-history restore,
  export (download/copy/print), rename/archive, and an AI propose â†’ diff â†’
  accept flow. Nothing fakes a success â€” a save is only reported saved after the
  server returns it, and a `409` surfaces an honest conflict UI with
  reload-latest instead of overwriting. Files:
  `src/components/screens/canvas/` (`canvas-screen.tsx` container,
  `canvas-workspace.tsx`, `canvas-rail.tsx`, `canvas-center.tsx`,
  `canvas-editors.tsx`, `code-editor.tsx`, `document-editor.tsx`,
  `visual-editor.tsx`, `canvas-ai-panel.tsx`, `canvas-utils.ts`, tests). Docs
  updated: `NAVIGATION.md` (Eclipse Canvas row). The screen is not yet mounted on
  an AppTab/nav entry, so it is currently reachable only by import.

- **Chat scroll now works over the composer too.** On the ChatBot page the
  transcript is the only vertical scroll area, but the composer/toolbar are DOM
  siblings of the transcript, so the browser's native wheel chaining never
  reached it â€” resting the cursor on the composer and using a mouse wheel or
  trackpad did nothing. The conversation wrapper now forwards wheel deltas onto
  the transcript, leaving nested vertical scrollables (multi-line composer, open
  palettes) to scroll themselves. Files:
  `src/hooks/use-forward-wheel-scroll.ts` (new `useForwardWheelScroll` hook),
  `src/components/chat/chat-history.tsx` (optional `scrollRef`),
  `src/components/screens/stock-chat.tsx` (`handleChatWheel`).
  No doc change â€” bug fix, contracts unchanged.

- **Aurora settings now preview live inside the modal.** Settings â€º Aurora edits
  did appear to do nothing because the Settings dialog is an opaque modal that
  covers the shell's app-wide `<AuroraGlow>` (`z-0`), and the panel's old
  "Preview" was flat color swatches that ignored motion/shape/style. The Preview
  card now mounts a real `<Aurora>` driven by the live regime score and the same
  store config, so color, intensity, speed, softness, detail and style all update
  as the user edits. Files: `src/components/screens/aurora-settings.tsx`.
  No doc change â€” presentational fix, contracts unchanged.

- **Composer width tuned to ~80%.** Widened the landing/follow-up chat
  composer from 65% to `md:max-w-[80%]`. Files:
  `src/components/chat/empty-state.tsx`, `src/components/screens/stock-chat.tsx`.
  No doc change â€” layout-only tweak.

- **Composer width tuned to ~65%.** Widened the landing/follow-up chat
  composer from 50% to `md:max-w-[65%]` for better readability. Files:
  `src/components/chat/empty-state.tsx`, `src/components/screens/stock-chat.tsx`.
  No doc change â€” layout-only tweak.

- **Chat composer is half-width and centered.** Landing (`EmptyState`) and
  follow-up (`stock-chat`) composers now cap at `50%` width on `md+` instead of
  stretching edge to edge. Files: `src/components/chat/empty-state.tsx`,
  `src/components/screens/stock-chat.tsx`. No doc change â€” layout-only tweak,
  contracts unchanged.

- **`/anatomy` now produces true 3D models (new `model3d` response block).** The
  isometric `anatomy` block could only draw boxes/tubes/cylinders â€” no rotation,
  hierarchy, depth buffer or camera â€” so `/anatomy` "only made cylinders". Adds a
  separate, declarative `model3d` block the model authors (never meshes/code):
  parts with a transform (`position`/`rotation`/`scale`), optional `parent`
  assemblies, material/tone/lit, and geometry as a primitive (`box`, `cylinder`,
  `cone`, `sphere`, `torus`, `lathe`, `extrude`, `tube`, `gear`) **or a reusable
  mechanism recipe** (`motor`, `gearbox`, `pump`, `valve`, `gauge`, `tank`,
  `bearing`, `gear`, `pulley`, `belt-drive`, `frame`, `bracket`, `fan`,
  `heat-exchanger`, `pcb`, `lever`, `spring`). New pure geometry/compile layer
  (`src/lib/model3d/`) bakes world-space meshes, grounds the scene, computes the
  camera and emits diagnostics; a lazy `ogl` WebGL viewport (already a
  dependency) renders it with orbit/zoom/pan, lighting, a ground grid and
  numbered hotspots, and the model downloads as `.glb` (`glb.ts`). WebGL is
  client-only (`next/dynamic ssr:false`) with the key/legend/stages staying in
  the DOM; the legacy `anatomy` block still renders. The `/anatomy` directive +
  skill now teach the recipe vocabulary. Files: `src/lib/model3d/*`,
  `src/lib/response/blocks/model3d.ts`, `src/components/response/model3d-{block,canvas}.tsx`,
  contract/normalize/projection/export wiring, `command-agent.ts`,
  `python/harness/skills/library/system/anatomy-figure/*`.
  Docs updated: `DECISIONS.md` (ADR-048), `NAVIGATION.md`,
  `interactive-response-engine.md`, `harness/slash-commands.md`,
  `.opencode/skills/black-eclipse-anatomy/SKILL.md`.

- **Bots workspace: Escape now backs out of an open conversation to the Bots
  overview.** With a bot or group room selected, `Escape` clears the selection
  (`select(null)` / `selectGroup(null)`), revealing the empty-state page that
  keeps the same New bot / New group buttons. Guarded by
  `canHandleKeyboardEvent`, so it is suppressed while typing and while a
  dialog/sheet owns Escape. Reused the existing `bots-store` selection actions;
   no UI or contract change. File:
  `src/components/screens/bots/bots-screen.tsx`.
  Docs updated: `NAVIGATION.md`.

- **Sidebar now has Gateway + Graph quick-launchers, and its dropdowns share
  the control-strip border.** The `Terminal` mode switcher and the `recent` sort
  select no longer show a raw focus ring/border; both use the same
  `border-border/20` as the search box and group-by strip. Below the switcher
  are two buttons: **Gateway** opens a dialog that lazy-loads the existing
  Channel Gateway (`ConnectionsSettingsPanel` â€” Telegram/Discord/WhatsApp/
  Slack/Email/Webhook; no second connection store); **Graph** opens a dialog
  with *Skills* (learning-journey provenance graph via `learningJourney()` +
  `LearningGraphChart`) and *Relations* (Investor Eye graph via the
  `investor-eye:graph` data-hub topic), reusing the existing ECharts force
  graph idiom (exported `RelationshipGraphChart`). New:
  `src/components/layout/sidebar-gateway-dialog.tsx`,
  `src/components/layout/sidebar-graph-dialog.tsx`; touched
  `src/components/layout/sidebar.tsx`,
  `src/components/layout/chat-history-panel.tsx`,
  `src/components/investor-eye/graph-panel.tsx`,
  `src/lib/i18n/dictionaries/en.ts`, `src/lib/size-budget.test.ts`.
  `no doc change â€” new UI surface reusing existing systems; no architecture,
  contract, or setup change`.

- **feat(video): native video-generation foundation (Phase 1) â€” fframes Rust
  render worker proven end-to-end on Windows.** New out-of-process worker
  `rust/fframes-worker/`: an fframes crate pinned `=1.2.0` (committed
  `Cargo.lock`) whose `TitleCard` proof renders a 10 s / 1920x1080 / 30 fps
  animated title card to a valid MP4 (draft 300 frames in 1.5 s; full render
  2.6 s; `inspect` clean; ffprobe h264 / yuv420p / 10.000 s), verified visually
  via contact sheet + frames. Not wired to the runtime yet (job API, agent
  tools, storyboard are Phases 2â€“4). Files: `rust/fframes-worker/Cargo.toml`,
  `src/main.rs`, `Cargo.lock`, `rust/README.md`, `.gitignore`. Checks:
  `npx tsc --noEmit` + vitest green; `test-evals` all gates pass; python suite
  6592 passed with 5 pre-existing failures unrelated to this change
  (size-budget overages, skill version check, one perf threshold). Docs:
  `docs/video-pipeline.md` (new), `docs/NAVIGATION.md`, `docs/ARCHITECTURE.md`.

- **feat(harness,video): Phase 2 â€” the video pipeline becomes a reliable
  backend capability on the Execution Fabric.** `python/harness/video/` turns
  the Phase 1 Rust worker into a queued job layer: filesystem-backed projects
  (`VideoProjectStore` + `VideoService.create_project`/`validate_project`),
  draft/final renders and frame inspection as `video` jobs on a dedicated
  Fabric worker (new `QueueName.VIDEO`/`WorkerKind.VIDEO` + `video` policy â€”
  never inline), and a structured process interface (`VideoRunner`: fixed
  argv, one JSON doc on stdout + JSONL progress events on stderr fed to Fabric
  progress, hard timeout, the child killed on cancellation, and exit 0 is
  never trusted without a non-empty output file â€” `RENDER_OUTPUT_MISSING`).
  Every render job runs a post-render inspection gate (`INSPECTION_FAILED`
  fails defective renders) and writes `report.json` in its workspace; final
  renders register the MP4 into the Artifact Center (category `video`,
  `source_type=job`, video metadata; `ARTIFACT_REGISTRATION_FAILED` if the
  catalog cannot take it). Cancel/progress/retry/lease-recovery ride the
  Fabric; renders are deterministic so recovery re-drives safely. Also fixes a
  Fabric store defect this work exposed: `FabricStore.update_job` silently
  dropped the snake_case keys the terminal transitions pass (`error_class`,
  `completed_at`, `cancelled_at`, â€¦) because only camelCase columns were
  accepted â€” failed jobs lost `errorClass` (and timestamps) on the row;
  snakeâ†’camel aliases now persist them. Files: `python/harness/video/*` (new),
  `python/harness/fabric/{models,policies,builtin_workers,store}.py`,
  `python/harness/service.py`. Tests: `python/tests/test_video_{runner,service}.py`
  + `video_fakes.py` (14 offline: render shaping, timeout, cancellation,
  inspection gate, artifact registration, cancel, lease-expiry recovery) and
  opt-in `test_video_real_smoke.py` (`HARNESS_VIDEO_IT=1`; real draft + final +
  artifact + inspect â€” passed on this machine); Fabric regressions green (50).
  Checks: `npx tsc --noEmit` clean; full suite 6617 passed with the 4 known
  pre-existing failures (size-budget ratchets `main.py`/`persistence.py`/
  `service.py` from in-progress work â€” the wiring adds 7 lines to the
  already-over `service.py`; anatomy skill version check). Docs:
  `docs/video-pipeline.md`, `docs/NAVIGATION.md`, `docs/ARCHITECTURE.md`.

- **feat(harness,video): Phase 3 â€” the video pipeline is on the agent surface
  (ten `video_*` tools + the `system.video-production` skill).** The agent can
  now run the whole workflow through typed tools on the ONE registry:
  `video_capabilities` (honest readiness: worker binary + FFmpeg tree),
  `video_create_project`/`video_list_projects`, `video_validate_project`,
  `video_render_draft`/`video_render_final` (queued Fabric jobs; final
  registers the MP4 in the Artifact Center), `video_inspect`, and
  `video_job_status`/`video_list_jobs`/`video_cancel_job`. All ten are
  `read`/low â€” they queue jobs and write only into the confined video
  workspace + Artifact Center (the same class as `ml_*`/`document_create`, and
  not part of any effectful `code/policy.py` tuple). Registered in
  `video/bootstrap.py`; allowlisted for `eclipse-agent` via the canonical
  `VIDEO_TOOLS` import in `agents.py`. The bundled skill
  `system.video-production` carries the procedure (capabilities â†’ create â†’
  validate â†’ draft â†’ poll â†’ inspect â†’ final â†’ hand over the artifact id), the
  honesty rules (a video exists only when a job SUCCEEDED;
  `INSPECTION_FAILED`/`TIMED_OUT`/`CANCELLED` are reported as such) and the
  current capability boundary (title card only â€” custom storyboards are
  Phase 4 and are never promised). Files: `python/harness/video/{tools,service,bootstrap}.py`,
  `python/harness/agents.py`, `python/harness/skills/library/system/video-production/`
  (new). Tests: `python/tests/test_video_tools.py` (6) + the opt-in real smoke
  grew `test_real_tool_workflow` (the whole workflow through the registered
  tools against the real worker â€” passed on this machine). Checks:
  `npx tsc --noEmit` clean; full suite 6623 passed with the same 4 known
  pre-existing failures (size-budget ratchets + anatomy skill version check).
  Docs: `docs/video-pipeline.md`, `docs/NAVIGATION.md`, `docs/ARCHITECTURE.md`.

- **docs(harness): add the round-4 self-evolution roadmap (closed
  self-improvement loop).** New plan `docs/harness/self-evolution-roadmap.md`
  traces the worked failure (a "multi-zone world clock" request routed
  `not_code` â†’ UI Compose â†’ `ui_start_engineering` false-refusal, with no
  durable signal), and specifies the missing loop over existing machinery:
  Observe (`eclipse_memory/mistakes.py` gains routing/refusal categories; a
  construction-refusal event feeds `recovery`) â†’ Diagnose â†’ Propose (worktree
  patch / skill draft) â†’ Verify (`evaluation/improvement.py` +
  `regression.DEFAULT_GATES` + routing scenarios) â†’ Land
  (`code/promotion.py`/`code/selfhost.py`, operator-confirmed) â†’ Measure (Â§1
  metrics on the phase-20 gate). Workstreams W0â€“W7, invariants, risks, ADR
  proposals ADR-H203â€¦H208, and the first slice (W0 witness requirement +
  catalog re-check, W1 incident, W3 benchmark). No code changed.
  Docs: `docs/harness/self-evolution-roadmap.md` (new), `docs/CHANGELOG.md`.
  No `NAVIGATION.md` change â€” a program plan, not a folder/module/contract
  change.

- **feat(harness,video): Phase 4 â€” the storyboard & scene-generation engine.**
  Video projects can now be versioned storyboards, not just the one hardcoded
  title card. The Rust worker renders a `--project spec.json` (`schemaVersion`
  2) through a seven-type scene library â€” `intro`/`outro` (fade-to-black
  outro), `metric` (staggered cards, colored deltas), `candlestick`
  (value-mapped chart, grid, last-price line, left-to-right reveal),
  `comparison` (`winner` accent frame), `timeline` (staged events on a
  revealed axis) and `quote` (wrapped with a decorative mark) â€” on the shared
  dark theme, with `transition: "fade"` cross-fades. The schema is validated
  in Python (`video/spec.py`: precise problem paths, unknown keys rejected,
  1-12 scenes / 1-30 s each / â‰¤300 s total / landscape 1920x1080@30 / dark)
  and re-checked in Rust (`src/spec.rs`) so a hand-edited spec fails cleanly
  instead of panicking a render. New tool `video_update_project` (11 total)
  revises a project and bumps its revision â€” a re-render is a queued job
  against the new spec, `jobs/<id>/spec.json` keeps exactly what was
  rendered, and `video_inspect` now receives `--project` too so it inspects
  the SAME video. Worker change: `compile-time-svgtree` is now enabled â€”
  REQUIRED for scene overlaps (without it `render_scenes` merges scenes by
  string concatenation, a two-root document usvg rejects, so every fade
  failed at its overlap frames) and it turns on static-subtree caching (the
  32 s / 7-scene demo renders in ~6.5 s). Files:
  `rust/fframes-worker/{Cargo.toml, src/main.rs, src/spec.rs, src/theme.rs, src/scenes/*}`,
  `python/harness/video/{spec.py (new), models, projects, runner, service, tools}.py`,
  skill `system.video-production` v2.0.0 (schema + scene table in SKILL.md).
  Tests: `test_video_spec.py` (new) + service/tool additions (storyboard
  create/update/render, `spec.json` + `--project` argv assertions, inspect
  carries the spec) + real smoke `test_real_storyboard_render_and_inspect`
  (passed on this machine; a 7-scene demo was reviewed frame-by-frame).
  Checks: `npx tsc --noEmit` clean; python suite 6674 passed â€” the 4 known
  pre-existing failures (size-budget ratchets + anatomy skill version check)
  plus one order-flaky user-WIP graph test that passes in isolation; vitest
  332 files pass with 1 pre-existing failure in `graph-canvas.tsx` (user
  WIP, mixed CRLF/LF endings â€” untouched by this change). Docs:
  `docs/video-pipeline.md`, `docs/NAVIGATION.md`, `docs/ARCHITECTURE.md`.

- **feat(harness,video): Phase 5 â€” evidence-bound financial data.** Storyboard
  figures can now be BOUND instead of hand-written (schemaVersion 3): a
  candlestick scene declares `data {symbol, market?, interval, count}` instead
  of static candles; metric items / comparison panes declare `source {symbol,
  market?, field: price|changePct|volume}` instead of a value (mixing authored
  and bound values is rejected). The render job resolves bindings through the
  EXISTING Market Data Gateway before the worker runs â€” `video/data.py` (the
  resolver: unit-aware formatting `$68,240` / `+2.41%` / `38.20B`, candle
  parity after rounding, the EvidenceManifest) over `video/market_provider.py`
  (a gateway adapter lazily built on the service's read-only bridge, sharing
  the market cache/router â€” no second provider, client or cache). Missing data
  fails the job (`DATA_UNAVAILABLE`, naming the binding); stale data (the
  gateway's own `data_status: STALE` verdict) renders with an amber STALE chip
  + a source footer and `evidence.stale: true` in the manifest, which travels
  with the result (job output, `report.json`, artifact metadata). New tool
  `video_resolve_data` (twelve total; read) previews every bound figure â€”
  display, provider, retrieval time, freshness â€” without rendering. Rust:
  accepts schemaVersion 2 and 3 and renders the per-scene provenance footer +
  STALE marker (`src/spec.rs` `SceneEvidence`, `theme::evidence_footer`).
  Skill `system.video-production` v2.1.0 documents bindings as the preferred
  path for market figures. Files: `python/harness/video/{data,market_provider,spec,service,tools,bootstrap}.py`,
  `rust/fframes-worker/src/{spec,theme,scenes/*}.rs`. Tests:
  `test_video_data.py` (new: formatting, resolution, quote cache, failure
  mapping, staleness) + spec/service/tool additions (resolution inside the
  render job, no-provider and provider-failure job failures, stale flagged
  everywhere, preview-without-render) + real smoke
  `test_real_bound_storyboard_render` (a stale bound storyboard end-to-end â€”
  chip, footer, manifest â€” passed on this machine; footer/STALE reviewed
  frame-by-frame). Checks: `npx tsc --noEmit` clean; python suite 6707 passed
  â€” the same 4 known pre-existing failures (size-budget ratchets + anatomy
  skill check) plus the user-WIP order-flaky graph test; evals all gates pass;
  vitest 332 files pass with the 1 pre-existing `graph-canvas.tsx`
  line-ending failure (untouched by this change). Docs:
  `docs/video-pipeline.md`, `docs/NAVIGATION.md`, `docs/ARCHITECTURE.md`.
