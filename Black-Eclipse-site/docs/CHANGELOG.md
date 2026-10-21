# Change Log

## Rotation policy

This file keeps a rolling window of the **most recent 7 dated sections** (the active window). Older dated sections are **moved** - never deleted - into monthly archive files under `docs/changelog/YYYY-MM.md`. New entries are appended under the current date; the commit-msg hook checks this path. Rotation is by hand only when this file grows unwieldy; the archive link below points at where the older entries went.

> Older entries are archived under `docs/changelog/` (monthly). The most recent 7 dated sections are kept here.

## 2026-10-21

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

## 2026-10-20

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
  the corpus is still 53 tasks, and no replay dataset is committed yet. Files:
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

## 2026-10-16

- **Chat transcript no longer "disappears" on server restart/refresh.** The
  localStorage cache is origin-scoped and silently froze once the whole
  transcript list outgrew the quota (~5 MB; the current tree is ~5.04 MB), so
  `saveConversations` swallowed the `QuotaExceededError` and kept returning an
  old snapshot. Boot hydration merged the durable server copy into `conversations`
  but only pushed `messages` when no active chat was set, so the open transcript
  stayed stale despite the server already holding the new turns. Two fixes: (1)
  on boot the open conversation is refreshed from the merged copy (falling back
  to most-recent when it is gone); (2) the cache writer now degrades gracefully â€”
  `saveConversationsCache` evicts the least valuable chats (trashed â†’ archived â†’
  oldest unpinned) until the payload fits instead of freezing, with the server
  transcript still authoritative. Files:
  `src/lib/chat/use-conversation-persistence.ts`,
  `src/lib/chat/chat-organization.ts`, `components/screens/stock-chat.tsx`;
  regression tests in `chat-organization.test.ts`.
  `no doc change â€” bug fix, contracts unchanged`.

- **`anatomy` now draws real TURNED solids, not just boxes/tubes.** `slab`,
  `prism`, `disc` and `knob` all compile to straight extrusions/cylinders, so
  figures still read as boxes and tubes. Vendored the kit's `lathe.mjs` (with its
  `iso-kit.mjs` dep) into `src/lib/anatomy/` and wired three **turned** kinds:
  `lathe` (a turning `profile` of `[axial, radius]` â€” bells, flanges, bottles;
  `smooth: true` shades a curved profile as one body), `cone` (`radius`/`radiusTop`)
  and `sphere` (`radius`). They return the same `SolidPaths` shape, so the existing
  renderer draws them; the shade ramp now reaches the `#303032` highlight. The
  `/anatomy` directive + both Anatomy skills teach the turned vocabulary ("a
  machine of only boxes and cylinders is a diagram, not an object"). Files:
  `src/lib/anatomy/{lathe.mjs,iso-kit.mjs,tube.mjs,NOTICE}`, `scene.ts`,
  `src/lib/response/blocks/anatomy.ts`, `src/lib/harness/command-agent.ts`,
  `.opencode/skills/black-eclipse-anatomy/SKILL.md`,
  `python/harness/skills/library/system/anatomy-figure/SKILL.md`. Verified visually
  (a bell, cone, sphere, disc, knob on a base) and by compiler tests. docs updated:
  `docs/interactive-response-engine.md`.

- **`anatomy` gets a real part vocabulary + a finance-customized Anatomy skill.**
  The block only offered `slab`/`cylinder`, so figures could only be boxes and
  tubes. Added part **kinds** `prism` (an extruded `points` polygon â€” wedges,
  plates, brackets), `disc` and `knob` (a knurled control), plus craft
  **decorations** that make a part read as a real object â€” `groove` (inset top
  rule), `screws` (corner screws), `ticks` (a ruler strip) and `knurl`/`knurlCount`
  â€” all compiled in `lib/anatomy/scene.ts` via the kit (`extrude`,
  `planOutline`, `corners`, `topTicks`, `knurl`). Painter's order is the producer's
  order (base first); a naive depth sort was tried and reverted (it hid a small
  part behind a large ground slab). The `/anatomy` directive
  (`command-agent.ts`) now teaches the richer vocabulary and the base-first rule.
  Added the finance-customized skill `.opencode/skills/black-eclipse-anatomy/SKILL.md`
  and rewrote the library skill `system.anatomy-figure/SKILL.md` (finance
  mappings, craft rules, the in-chat scene). Files:
  `src/lib/response/blocks/anatomy.ts`, `src/lib/anatomy/scene.ts`,
  `src/lib/harness/command-agent.ts`, `.opencode/skills/black-eclipse-anatomy/`,
  `python/harness/skills/library/system/anatomy-figure/SKILL.md`. docs updated:
  `docs/interactive-response-engine.md`.

- **Verified `/anatomy` end-to-end against the live runtime + added a prompt
  fixture.** Ran four anatomy prompts through the running app's
  `POST /api/harness/chat` (matching engine, market-data path `--animated`,
  portfolio rebalance `--animated`, order book) â€” each returned a single
  `eclipse-response` fence whose `anatomy` block parses with **0 diagnostics**,
  does not degrade, compiles (7â€“12 parts each) and renders (screenshot-confirmed).
  The canonical prompt list now lives in `src/lib/anatomy/prompts.ts` and is
  exercised by `src/lib/anatomy/prompts.test.ts` (each prompt must route to the
  `agent.anatomy` directive carrying the schema read-back + single-fence guidance).
  no doc change â€” test/verification only.

- **`/commands` is now an alias of `/help`** in the chat composer command
  registry (`src/lib/harness/command-registry.ts`, `HELP.aliases`). Typing
  `/commands` surfaced "unknown command" because the canonical verb is `/help`;
  the alias makes the intuitive spelling work in the palette and in the command
  router. `no doc change â€” alias only, contract unchanged`.

- **`anatomy` palette: base `#141416`, highlight `#303032`.** The dark figure now
  paints solid bodies in `#141416` with `#303032` top/highlight faces (shade ramp
  stepped between), neutral-grey outlines, and the status-tone colour reserved for
  the wires/legend. `src/components/response/anatomy-block.tsx` (`DARK` palette +
  `SolidShape`). no doc change â€” theme tweak only.

- **Fix: `/anatomy` showed nothing â€” the schema rejected the model's real output
  and degraded it to text.** Inspecting a stored transcript (`chat_1792204973311`)
  showed the model DOES emit a well-formed `anatomy` block, but its field
  VOCABULARY did not match the schema: part/wire `tone: "info"|"success"|"warning"`
  (I required `hi|mid|lo|faint`), `legend[].mark: "tall cylinder"` (I required a
  fixed enum), and `stages[].lit: true` (I required an id array). Any one failed
  the all-or-nothing block, so it degraded to a JSON text blob. The block now
  speaks the same **status `tone`** vocabulary as every other response block
  (`neutral|info|success|warning|danger`), `legend[].mark` is free text (known
  shapes get a swatch, anything else a neutral one), `stages[].lit` accepts a
  boolean OR an id array, and `normalize.ts` maps tone synonyms onto anatomy
  again. Long labels are now **numbered callouts (1,2,3â€¦) with a key below the
  figure** â€” SVG text cannot wrap, so in-plane sentences overflowed. Verified end
  to end against the model's real block (parses with 0 diagnostics, 8 parts /
  9 wires, renders). Files: `src/lib/response/blocks/anatomy.ts`,
  `src/lib/response/normalize.ts`, `src/lib/anatomy/scene.ts`,
  `src/components/response/anatomy-block.tsx`. docs updated:
  `docs/interactive-response-engine.md`.

- **Fix: the `anatomy` figure rendered black-on-black and uncontained.** The kit's
  stylesheet defines its `--anatomy-*` theme variables only on an `.iso` root with
  a `data-theme`; the renderer never supplied one, so every `var()` was undefined â€”
  SVG `fill` fell back to **black** and `stroke` to **none** (the dark blobs and
  black labels), and the figure sprawled across the page instead of sitting in a
  card. `AnatomyBlock` now carries the `.iso` theme root (with `data-theme` driven
  by `useDarkScheme`), renders inside the app's **frosted-glass card** (`.glass-card`,
  width-capped), and adds a **"Full page"** full-screen overlay (portaled to
  `document.body`, Escape/backdrop/Escape to close, scroll-locked â€” the same pattern
  as the `flow` block). A scoped stylesheet (`BE_ANATOMY_CSS`) overrides the kit's
  near-black palette to a mid-grey that reads on the glass in both schemes and
  clears the kit's standalone plate chrome. **Rewrite:** the drawing is now
  SELF-CONTAINED â€” every path is painted with explicit `fill`/`stroke` SVG
  presentation attributes and an inline palette (no kit stylesheet dependency at
  all), which removes the "undefined CSS variable â†’ black-on-black" failure class
  for good and delivers a graphite-on-dark-paper look. The compiler now emits a
  **content-fitted `viewBox`** (no dead vertical space) and labels are larger,
  brighter and knocked out over any face (`fontSize 10`, panel-stroke halo).
  Regression test asserts the figure paints explicitly, not via CSS classes.
  (Verified visually with a headless-Chromium screenshot during development.)
  docs updated:
  `docs/interactive-response-engine.md`, `docs/DECISIONS.md` + `skills/ARCHITECT.md`.

- **New `/anatomy` slash command (aliases `/visualize`, `/mechanism`).** A new
  agent-turn command (like `/skill`) that rewrites `/anatomy <concept>` into a
  directive telling the agent to explain the concept as an interactive isometric
  `anatomy` figure â€” consulting `response_block_schema`, authoring a declarative
  scene (parts/wires/legend/stages), and emitting ONE `eclipse-response` fence.
  Adds a `visual` command category, the `ANATOMY` `CommandSpec`
  (`src/lib/harness/command-registry.ts`), the `agent.anatomy` instruction builder
  (`src/lib/harness/command-agent.ts`), and tests. A matching, inert Skills-library
  entry `system.anatomy-figure` (`python/harness/skills/library/system/anatomy-figure/`)
  makes the same capability discoverable/runnable from the Skills surface. docs updated:
  `docs/harness/slash-commands.md` (last-verified bumped),
  `docs/interactive-response-engine.md`.

- **Channel Gateway: remote control of Eclipse over external messaging
  (Telegram first).** A user can now connect an external account and drive the
  app from it. New core Python subsystem `python/harness/channels/`: provider
  adapters normalize inbound messages; `ChannelService.handle_inbound` enforces
  idempotency (native message ids), resolves the sender to a verified
  `ChannelBinding`, applies a per-binding rate limit, and hands the message to
  `ChannelDispatcher`, which gates by control scope (`viewer` < `assistant` <
  `operator`), routes `/commands`, agent turns (via the ONE `service.run`) and
  the operator `/do` tool bridge (via the ONE `ToolRegistry` + the Security
  Gateway effect authorizer), and requires a single-use in-channel `/confirm`
  for mutations. Links are created by short-lived single-use codes
  (`/link <code>`). Telegram ships first (long-poll â€” no public endpoint, so
  zero-config is unchanged); Discord/Email/Slack/WhatsApp follow. Router
  `python/harness/routers/channels.py` (`/channels/*`, operator-gated); boot
  wiring in `service.py` + `boot.py`; front door
  `src/app/api/channels/[[...path]]/route.ts` + `channels-{client,browser}.ts`;
  UI Settings â€º Connections `connections-settings.tsx`. Tests
  `python/tests/test_channels_{core,api}.py`. docs updated:
  `docs/harness/channel-gateway.md` (new), `docs/NAVIGATION.md`,
  `docs/ARCHITECTURE.md`, `docs/harness/decisions.md` (ADR-H199).
- **Channel Gateway providers: Discord, Email, Slack, WhatsApp, generic
  webhook.** Providers split by transport (ADR-H200). Pull channels need no
  public endpoint â€” `providers/discord.py` (bot Gateway WebSocket + REST),
  `providers/email.py` (IMAP poll + SMTP), alongside Telegram. Push channels
  cross ONE public, signature-verified boundary
  `GET|POST /channels/webhook/{kind}` â€” `providers/webhooks.py` (Slack Web API,
  WhatsApp Cloud API, generic HTTP reply) with pure payload parsers, and
  `channels/verify.py` (Slack v0 + replay window, WhatsApp `X-Hub-Signature-256`,
  generic `X-Eclipse-Signature`) verifying an HMAC over the RAW body. The Next.js
  middleware exempts `/api/channels/webhook/` from the session gate (the
  signature is the gate); the front-door route forwards the raw body + only the
  signature headers. `service.py` generalises provider building (`_POLL_KINDS`,
  outbound for any configured kind, `secret_value`); Settings â€º Connections
  renders per-kind credential fields + the inbound webhook URL. Tests
  `python/tests/test_channels_providers.py` + the webhook cases in
  `test_channels_api.py`. docs updated: `docs/harness/channel-gateway.md`,
  `docs/NAVIGATION.md`, `docs/harness/decisions.md` (ADR-H200).
- **Channel credentials are now encrypted at rest.** Saving a channel moves every
  sensitive key (tokens, passwords, signing secrets) into a Fernet-encrypted
  vault (`channels/secrets.py`, key file `.black-eclipse/channels/secret.key`,
  0600, outside the DB) and stores only ciphertext in a new `ChannelSecret` table;
  the config JSON keeps only non-sensitive keys. `describe_config` still echoes a
  configured credential as a redacted presence marker (`"botToken": "***"`) plus a
  `secrets` name list and `secretsEncrypted`, so the Settings contract is
  unchanged. Resolution is layered (vault â†’ legacy literal / `secret://`); if
  `cryptography` is unavailable it falls back to the literal config honestly.
  Deleting a channel purges its secrets. Settings â€º Connections shows "encrypted
  at rest". Tests `python/tests/test_channels_secrets.py`. docs updated:
  `docs/harness/channel-gateway.md`, `docs/harness/decisions.md` (ADR-H201).
- **Channel Gateway: explicit mutation verbs, the one-sender primitive, and
  notifications.** `/trade`, `/alert`, `/backtest` require the `operator` scope
  AND always ask for an in-channel `/confirm`, then run as an agent turn with a
  directive â€” a stronger gate than plain agent text, still ending on the agent's
  Security-Gateway-authorized tools. `POST /channels/send` /
  `ChannelService.send_outbound` is the ONE outbound sender any subsystem can use
  (transport built transiently when the poller is down; delivery recorded). A
  root-mounted `ChannelActivityWatcher` (+ pure `channel-diff.ts`) polls
  `GET /api/channels/messages` and raises the shared `be:alert-notify` event for
  new inbound messages (first poll seeds; outbound ignored). Consolidating the TS
  alert notifier into this sender is deliberately skipped â€” alert channels are
  webhook/notification transports owned by JDDS and must not depend on the Python
  runtime. Tests `test_channels_{core,api}.py` + `channel-diff.test.ts`. docs
  updated: `docs/harness/channel-gateway.md`, `docs/harness/decisions.md`
  (ADR-H202).
- **New `anatomy` response block: interactive isometric mechanism figures.** A
  new block type renders an "how does it work" illustration inline in chat,
  built from the MIT-licensed Anatomy-derived isometric kit (`wheresryan22/anatomy`)
  vendored into `src/lib/anatomy/` (`iso-kit.ts`/`draw.tsx`/`live.tsx` + `NOTICE`
  and `LICENSE`; upstream commit `e9488296` verified byte-for-byte by git blob
  hash for `iso-kit.ts`/`live.tsx`, with `draw.tsx` differing only by its import
  path). The model authors a **declarative scene**
  â€” slab/cylinder `parts`, `wires`, a `legend`, and deterministic `stages`
  (`{ label, note, readout, lit[] }`) â€” compiled purely by `src/lib/anatomy/scene.ts`
  (total, server-safe, no model-authored SVG/code). A stage's `readout` is the
  ONLY source of live text (model-as-source-of-truth); motion is discrete
  (no rAF), autoplay is off under `prefers-reduced-motion`, and the timer clears on
  unmount. Rides the ONE existing pipeline (ADR-043): schema extracted to
  `src/lib/response/blocks/anatomy.ts` (keeps `contract.ts` under its size ratchet),
  one registry entry, projection + PDF fallbacks, and automatic
  `response_block_schema` exposure. `normalize.ts` gained `anatomy` aliases and an
  exemption so anatomy's own shading `tone` vocabulary is not clobbered by the
  status-tone rewrite. Tests: `src/lib/anatomy/scene.test.ts`,
  `src/components/response/anatomy-render.test.tsx`, matrix
  (`contract-matrix.test.tsx`, 74 cases). docs updated:
  `docs/interactive-response-engine.md`, `docs/NAVIGATION.md`,
  `docs/DECISIONS.md` + `skills/ARCHITECT.md` (ADR-047).

- **Fix: uploaded logo kept disappearing.** The app-wide theme is mirrored to
  `/api/theme` with `fetch(..., { keepalive: true })`, but browsers cap keepalive
  request bodies at **64 KiB**. A theme carrying an embedded logo/favicon
  `data:` URL exceeds that, so the PUT was rejected (error swallowed) and the
  server never stored the logo; on the next load `hydrateFromServer` adopted the
  older, logo-less server theme and the logo vanished â€” every reload.
  `pushThemeToServer` now sends `keepalive` only for small bodies (< 60 KB) and
  a normal request otherwise (`src/lib/theme/store.ts`). Also raised the
  `normalizeTheme` `logoUrl`/`faviconUrl` cap 400 KB â†’ 500 KB so a 300 KB upload
  (whose base64 exceeds 400 K chars) is no longer silently dropped
  (`src/lib/theme/tokens.ts`). Regression test in `store.test.ts`.
  no doc change â€” bug fix, contracts unchanged.

- **Chat composer: full-width input, adaptive control row.** The composer laid
  the textarea, `+`, model selector, effort, mic and send in ONE flex row, so the
  text wrapped as soon as it reached the model picker and the box never used the
  full width. The form is now a two-row `flex-col`: the textarea spans the full
  width on its own line (up to the 120px cap) and the controls sit in a row
  beneath (`+` left, model/effort/mic/send right, wrapping when tight). The
  landing and follow-up containers also drop the `max-w-[1400px]` cap
  (`empty-state.tsx`, `stock-chat.tsx`) so the composer fills the chat panel;
  the now-moot `EmptyState` `focus` prop is removed. no doc change â€” UI layout
  only.

- **Scheduled bots no longer silently drop runs (misfire default `skip` â†’
  `run_once`).** Root cause of "bots never fire": `execution.misfire` defaulted to
  `skip`, so every fire that came due while Eclipse was closed was recorded as
  `skipped` and discarded â€” a daily bot only ran if the app happened to be open at
  that exact minute (live `agent-memory.db`: 2075 `skipped` vs 115 `completed`). A
  missed fire now runs once when the app returns. Changed the default in
  `python/harness/automation/model.py` (`ExecutionPolicy`) and the Bots draft
  (`src/lib/bots/state.ts`). Existing automations saved under the old default are
  upgraded once by a guarded migration (`AutomationStore._migrate_misfire_default`,
  marker table `AutomationMaintenance`); a later deliberate `skip` is preserved.
  Recovery is now slot-idempotent (`execution_exists_for_slot`), so repeated
  restarts cannot re-record the same missed slot. Tests:
  `test_misfire_default_runs_a_missed_fire_once`,
  `test_recovery_does_not_repeat_a_missed_slot`,
  `test_misfire_default_migration_upgrades_stored_skip`. docs updated:
  `docs/harness/automation-engine.md`.

- **Memory-action panel drops its card background.** The chat memory/learning
  outcome line under an assistant turn no longer renders as a bordered
  `glass-card-subtle` box; it is now a quiet inline column (`px-1`) that sits
  directly on the transcript, so the "Automatically captured as a learning
  candidate â€” â€¦ Review in Learning Queue" line reads as a subdued metadata
  footnote rather than a raised card. Presentation-only; no contract change.
  no doc change â€” UI styling only.

- **Bots mode: recent-first ordering + unread dots.** The Bots sidebar now sorts
  bots (and group rooms) most-recent-activity first â€” latest chat message, else
  last run, else last edit. Both the bot thread and group room render
  **newest-message-first** (the composer stays at the bottom; the thread scrolls
  to the top instead of the bottom). The sidebar's per-bot dot no longer encodes
  lifecycle (active/paused); it is now an **unread indicator** shown only when a
  bot's latest terminal run is newer than the last one the operator opened. The
  seen-run ledger (`be_bots_seen_v1`) lives in `src/lib/bots/bots-store.ts`
  (`seenRuns`/`markSeen`); `hydrate` now fetches status for every bot (not just
  active) so a paused bot with an unseen run still surfaces its dot. Opening a
  bot clears its dot like a read receipt (Instagram-style): `BotChat` marks the
  SAME id the sidebar flags â€” `statusById[id].lastExecution.id` â€” so opening
  always clears the dot (a history-derived id could differ and leave it stuck),
  and a run landing while you watch raises none. no doc change â€” UI behavior
  only; contracts and architecture unchanged.

- **Dark theme presets no longer tint the ChatBot landing â€” all dark themes land
  on `#0a0b0b`.** Applying a theme overrode the scheme-aware default because every
  dark preset pinned its own `solidColor` (Eclipse `#131615`; others an
  accent-mixed `#0f0f11`), so the landing stayed theme-specific. `preset()` now
  leaves `solidColor` unset for dark schemes (light presets keep their light
  tint); the Eclipse preset's pinned `#131615` is removed. Applying any dark theme
  now clears the landing fill to the `#0a0b0b` default. A stored landing color
  that matches a retired preset fill is also cleared on hydrate
  (`LEGACY_DARK_LANDING_COLORS` + `migrateLegacyLandingColor`), so existing users
  update without re-applying a theme; an explicit custom pick is preserved. Tests
  in `src/lib/theme/tokens.test.ts`, `src/lib/backgrounds.test.ts`. docs updated:
  `docs/ARCHITECTURE.md`.

- **ChatBot landing backdrop defaults to `#0a0b0b` in dark mode on every theme.**
  The landing backdrop (the page behind the `ECLIPSE AGENT` wordmark) followed the
  theme's `--background`, so it shifted per theme. A flat solid backdrop with no
  explicit color now resolves a scheme-aware fill: light stays `var(--background)`,
  dark defaults to `#0a0b0b` regardless of the active theme. `BackgroundCss` gains
  a `colorDark` field; `applyBackgroundToDocument` writes `--app-bg-color-dark`;
  `.app-bg-layer` consumes it under `html.dark`. An explicit pick sets both vars;
  an image backdrop keeps both transparent. New constant
  `DEFAULT_SOLID_DARK_COLOR`; tests in `src/lib/backgrounds.test.ts`. docs updated:
  `docs/ARCHITECTURE.md`.

- **One app-wide theme across every URL.** The Eclipse theme was
  `localStorage`-only, so `http://localhost:3000`, `http://127.0.0.1:3000` and
  `https://blackeclipse` â€” three browser ORIGINS â€” each showed their own saved
  theme. The theme is now an APP-WIDE server property (JDDS `SystemConfig` key
  `eclipse_theme`, `/api/theme` GET/PUT/DELETE, operator-gated), with
  `localStorage` demoted to a per-origin first-paint cache: the store hydrates
  the cache then adopts the server theme (`hydrateFromServer`); a never-initialized
  server MIGRATES the pre-existing per-origin theme up (so an existing look is
  kept, not wiped), an explicit reset clears it, edits push to the
  server, and Reset clears it. The middleware additionally enforces ONE canonical
  origin when `BE_CANONICAL_HOST` is set (the local-host launcher sets it to the
  `blackeclipse` hostname), redirecting `localhost`/`127.0.0.1` (307, path +
  query preserved) so origin-scoped storage never diverges. New
  `src/lib/theme/server.ts` + `src/app/api/theme/route.ts`; `src/lib/theme/store.ts`,
  `src/middleware.ts`, `scripts/local-host.js`, `.env.example`. Tests
  `src/app/api/theme/route.test.ts`, `store.test.ts`, `middleware.test.ts`.
  docs updated: `docs/ARCHITECTURE.md`, `docs/local-hostname.md`,
  `docs/NAVIGATION.md`, `docs/DECISIONS.md` + `skills/ARCHITECT.md` (ADR-046).

- **Fix: visualization-surface faults (bridge 500 + UI-Engineering routing).**
  **(1) Bridge 500 was a STALE dev build**, not a code defect: `contract.ts` had a
  TDZ (`inputsBlock` referenced before its declaration) that was already fixed in
  source, but the running server served the pre-fix compiled chunk. A dev-server
  restart cleared it and the live bridge now returns 200 (`schema`, `validate`);
  `validate` accepts a known-good payload and rejects a malformed one with a
  **named field error**. The `/api/harness/data` 500 body now carries a stable
  `code: "BRIDGE_ERROR"` (plus a dev-only `detail`) so a caller can branch and
  degrade to prose/tables instead of guessing field names. **(2) `classify_request`
  now treats NEW-interaction requests** (slider, input form, user-driven parameter,
  calculator) as new-capability signals â†’ Engineer, so `ui_start_engineering`
  files a durable task instead of silently no-op'ing; matched as phrases so a
  "performance" restyle is not misrouted. **(3) `UiCatalog.search` matches on word
  boundaries**, so `form` no longer returns "per**form**ance" charts. **(4)
  `ui_list_blueprints` prints widget count + first component ids**, so pages that
  share a title are distinguishable; and `create_page` now guarantees a **unique
  title** (a duplicate is suffixed "Main" â†’ "Main 2"). A title EDIT/import can
  still create a duplicate, so the tested `title_ambiguous` resolution path
  remains reachable. Also brought the Python suite fully green by aligning pins
  with in-flight work: reclaimed blank lines in `python/harness/main.py` (back
  under the hard ceiling), re-pinned `python/harness/service.py` in the size guard
  for the Channel-Gateway boot wiring, re-pinned the agent-prompt char ceiling
  (29994, the Fiduciary `<fiduciary_advice>` block) in both ceiling tests, and
  added `advisory` to the `_run_kwargs` parity expectation. Full suite: tsc clean,
  vitest 3313 passed, pytest 6507 passed / 0 failed.
  docs updated: `docs/ui-engineering.md` (naming, new-capability routing, search
  honesty).
  Tests: `test_ui_mode.py`, `test_ui_service.py` (word-boundary + summary
  disambiguation), `src/app/api/harness/data/route.test.ts`.

- **Intelligent UI: envelope state/computed + `inputs` block (deferred Phase 4)
  and telemetry (Phase 6).** `state`/`computed` landed. The envelope (v1.1) now
  carries optional `state` (typed scalars) and `computed` (safe expressions over
  state, the same evaluator as `simulation`); a new `inputs` block renders `state`
  as controls, and any figure may bind to a computed value with `{ "$computed":
  "<id>" }`. A change updates the shared state and every bound figure re-renders
  **locally with 0 model calls**; an unresolvable computed renders UNAVAILABLE.
  Resolution reuses the Phase-2 pass (`resolveResponseFigures(response, resolver,
  computed)`; `state.ts` derives values). Edits **persist per message**
  (`localStorage["eclipse-response-state:<messageId>"]`, latest-wins) via a
  `ResponseRuntimeProvider` whose `stateKey` is the message id. Telemetry: the
  server `finalize` read-back now returns a block-type histogram + figure-binding
  counts (`refs`/`computedRefs`/`stateVars`/`computedVars`) emitted on
  `onResponseBlocks`; a client seam (`lib/response/telemetry.ts`) reports
  `first_block` (time-to-first-block), `interaction`, and `partial_parse_failure`.
  docs updated: `docs/interactive-response-engine.md` (Â§3 envelope state + inputs
  catalogue row, STATE-001/002, TELEM-001, limitations 10/11);
  `docs/NAVIGATION.md`. Tests: `state.test.ts`, `refs.test.ts`,
  `envelope-state.test.tsx`, `telemetry.test.ts`, updated `contract-matrix`.

- **Intelligent UI Phase 5: deterministic Markdown projection.** New
  `src/lib/response/projection.ts` â€” `toMarkdownProjection(response)`, a total
  pure function projecting EVERY block type to readable Markdown (prose kept,
  tables as GFM, charts as their data table, a `simulation` as its expanded
  default inputs/outputs, a figure `$ref` as UNAVAILABLE never the raw reference,
  `tabs`/`report`/`carousel`/`layout` flattened). It finalizes first, is derived
  from block data (never model-authored), and the contract-matrix test asserts
  every registered type projects non-empty â€” so no block silently vanishes. Used
  by `projectContentMarkdown` (the copy button now copies readable text, not raw
  `eclipse-response` JSON), a new Markdown export (`responseToMarkdown` /
  `downloadResponseMarkdown` + an "MD" button in `response-actions`), and any
  surface that cannot render blocks.
  docs updated: `docs/interactive-response-engine.md` (Â§3 projection, PROJ-001);
  `docs/NAVIGATION.md`.
  Tests: `projection.test.ts` + contract-matrix coverage.

- **Intelligent UI Phase 4: layout primitives, design tokens & motion.** Two
  structural blocks: `layout` (a `box`/`row`/`column`/`grid` container with
  recursively-validated nested blocks) and `divider` (labelled or bare). Styling
  is driven ONLY by closed token vocabularies â€” spacing / radius / tone / align in
  `src/lib/response/tokens.ts` mapped to existing utility classes â€” so there is no
  path from model output to raw CSS or an arbitrary class. Blocks now get a
  one-shot entrance motion (`response-block-enter`) as they appear, including a
  block that streams in; it uses `backwards` fill only (no persistent backdrop
  root above glass) and `prefers-reduced-motion` disables it; the gap wrapper is
  untouched so the layout-cohesion invariant holds. Wired through the envelope
  parser, `parseNestedBlocks`, `degradeBlocks` (finalize) and `resolveBlock`
  (refs), and registered in the renderer.
  Deferred (documented): envelope-level cross-block `state`/`bind` and persisting
  a block's interaction values across reload â€” the remaining Phase-4 item.
  docs updated: `docs/interactive-response-engine.md` (Â§3 layout/tokens/motion,
  LAYOUT-001, MOTION-001, limitation 10); `docs/NAVIGATION.md`.
  Tests: `tokens.test.ts`, `layout-block.test.tsx`, updated `contract-matrix`.

- **Intelligent UI Phase 3: incremental (streaming) block rendering.** Structured
  answers now render block by block as they close instead of holding the whole
  fence. New `src/lib/response/stream-blocks.ts`: a brace/string-aware scan of the
  partial fence returns each **fully closed** `blocks[]` entry â€” **a half-written
  block is never rendered as data** (only a closed, JSON-parseable object is a
  block). `ResponseFence` renders the closed prefix and keeps the composing
  placeholder only for the open tail; the settled path stays authoritative. Each
  closed block goes through a new **block-level chokepoint** (`finalizeBlock`,
  reusing the repairâ†’degrade machinery) and is **memoized by raw JSON**
  (`finalizeBlockCached`), so a frame only re-finalizes the changed block. Blocks
  now carry a **stable key** (`id ?? index:type`) so identity (and local state
  like a slider position) survives later blocks arriving. Figure refs (Phase 2)
  stay safe: a streamed block's numbers are ref-bound or illustrative.
  docs updated: `docs/interactive-response-engine.md` (Â§3 incremental decode,
  STREAM-002/003); `docs/NAVIGATION.md`.
  Tests: `stream-blocks.test.ts`, `streaming-fence.test.tsx`.

- **Intelligent UI Phase 2: source-referenced figures (`$ref`).** A figure value
  (a `metric_grid` metric, a `stat_hero` stat) may now be a reference
  `{ "$ref": "<namespace>:<id>#/<field>" }` instead of a literal, resolved
  BEFORE render from a real surface â€” so the model never retypes a financial
  number. New `src/lib/response/refs.ts` (pure, server-safe): a namespace
  **allowlist** (`analysis`/`tool`/`jdds`/`artifact`), `parseFigureRef`,
  `resolveResponseFigures` (walks containers), and `buildFigureResolver` for the
  turn's computed-result blob. **An unresolvable reference renders UNAVAILABLE â€”
  it never becomes a literal and never falls back to the string.** Resolution is
  injected per assistant message via `FigureResolverProvider`
  (`src/components/response/figure-context.tsx`); a surface without a resolver
  renders refs UNAVAILABLE (the honest default). Resolved figures show a
  provenance chip (source/as-of/method), reusing the computed-provenance
  vocabulary. Scoped, documented remainder: only `analysis` resolves today
  (tool/jdds/artifact + server-side resolution next), and refs cover the
  KPI/hero family for now.
  docs updated: `docs/interactive-response-engine.md` (Â§3 source-referenced
  figures, REF-001/002, limitation 9); `docs/NAVIGATION.md`.
  Tests: `refs.test.ts`, `figure-ref.test.tsx`.

- **Intelligent UI Phase 1: declarative in-chat calculators + a safe shared
  evaluator.** The `simulation` block is now declarative â€” `inputs` are local
  state, `outputs` are safe expressions over it, with a `risk_reward` preset; a
  slider move recomputes locally with **0 model calls** (the hard-coded
  `computeRiskReward` is gone). New `src/lib/response/evaluate.ts`: a tiny
  recursive-descent expression language with a **closed function whitelist** and
  **no `eval`/`Function`**; division-by-zero/non-finite/unknown-name/parse-error
  â†’ UNAVAILABLE (`â€”`), never a wrong number; explicit half-away-from-zero
  rounding at the format boundary; server-safe (no React). Shipped twice for
  parity â€” `python/harness/response_eval.py` (reuses the tested
  `stats/formula.py` parser) â€” driven by ONE shared fixture corpus
  (`src/lib/response/__fixtures__/evaluate-cases.json`), so the two evaluators
  cannot drift. New contract limits `maxSimulationInputs`/`Outputs` (12).
  Deferred (documented): envelope-level cross-block `state`/`bind` â€” it would
  touch all 32 block schemas, so Phase 1 ships the self-contained calculator and
  a decimal evaluator backend is noted as a follow-up.
  docs updated: `docs/interactive-response-engine.md` (Â§3 declarative
  calculators, catalogue row, EVAL-001/002, SIM-001, limitation 8);
  `docs/NAVIGATION.md`.
  Tests: `evaluate.test.ts`, `simulation.test.ts`, `contract-matrix.test.tsx`,
  `python/tests/test_response_eval.py`.

- **Intelligent UI: the response-mode routing benchmark (Phase 6).** Added
  `python/harness/response_mode_benchmark.py`: a versioned, labelled set of
  real-shaped prompts (each with its expected mode, incl. text anti-cases and
  follow-ups) plus a pure scorer reporting overall accuracy, per-mode
  precision/recall and the confusion pairs against the SHIPPED deterministic
  classifier (so it cannot drift). `python -m harness.response_mode_benchmark`
  prints the report (v1: 100% on 42 cases); `test_response_mode_benchmark.py`
  asserts an accuracy floor (â‰¥0.95) and per-mode recall floors. The
  model-assisted path is non-deterministic and deliberately not benchmarked.
  docs updated: `docs/interactive-response-engine.md` (Â§5 + ORCH-004).

- **Intelligent UI follow-ups: mode on the client, a model-assisted fallback, and
  an in-chat calculator.** Three increments on the orchestrator. **(A) Client
  plumbing:** the `response.plan` run event is normalized in
  `src/lib/agent/events.ts` (`coerceResponsePlan`) and carried on the turn as
  `AssistantTurn.responsePlan`/`Message.responsePlan`; `chat-history.tsx` shows a
  small mode chip for non-`text` turns (display only). **(B) Model-assisted
  fallback:** when the deterministic verdict is `unsure`, an opt-in bounded model
  call may choose the mode (`python/harness/response_mode_llm.py`,
  `HARNESS_RESPONSE_MODE_MODEL`, default OFF; hard deadline; total â€” any failure
  returns the deterministic plan). **(C) New `simulation` block:** a deterministic
  in-chat calculator (risk/reward + break-even win rate) computed LOCALLY with no
  model/backend and no arbitrary code, always labelled "Illustrative" with a
  visible disclaimer; pure math in `src/lib/response/simulation.ts`. Also adds
  `calculator`/`simulator` type aliases and points the orchestrator's simulation
  directive at the new block.
  docs updated: `docs/interactive-response-engine.md` (catalogue row + Â§5 +
  ORCH-002/003 + SIM-001 + limitation 8), `docs/NAVIGATION.md`.
  Tests: `python/tests/test_response_mode.py`, `src/lib/agent/events.test.ts`,
  `src/lib/response/simulation.test.ts`, `contract-matrix.test.tsx`.

- **Intelligent Response Orchestrator: a deterministic presentation planner.**
  The Interactive Response Engine already rendered structured blocks, but nothing
  *decided* the presentation â€” the model volunteered an `eclipse-response` fence or
  it did not. Added `python/harness/response_mode.py`, a pure model-free classifier
  (modeled on `code/request_intent.py`) that maps a turn to ONE mode â€” `text`,
  `explanation`, `visualization`, `simulation`, `workflow`, `composite` â€” and
  returns a prompt directive (bias: ambiguous/short turns stay `text`; a follow-up
  inherits the prior turn's mode). Wired into `graph.execute_run` on the same
  surface that may emit blocks, right after the schema digest: the directive is
  appended to the byte-stable head and the mode is emitted as the `response.plan`
  run event. Best-effort, never blocks a run, never fabricates data. No new block
  type, wire contract, or renderer.
  docs updated: `docs/interactive-response-engine.md` (new Â§5 + ORCH-001),
  `docs/NAVIGATION.md` (structured-answers row). Tests: `python/tests/test_response_mode.py`.

- **Perf: chat transcript no longer ships ~5MB uncompressed on every page.**
  `/api/chat/transcript` returns EVERY conversation's full message history and the
  ChatBot hydrates from it on every app boot â€” 126 files / ~5MB, re-read and
  re-parsed each load, and served UNcompressed (route-handler responses bypass
  `next start`'s built-in compression). `listTranscripts` now caches the parsed
  list in-process (invalidated on write/delete; 15s TTL for external edits), and
  the route gzips large JSON responses ASYNC (non-blocking). Wire size drops
  ~4.9MB â†’ ~0.9MB; every route/tab now measures 0.5â€“1.7s.
  no doc change â€” internal response optimisation, contract unchanged.

- **Fiduciary Gate: closing the loop + the front door.** Four follow-ups landed.
  **(1) Auto outcome evaluation:** the run captures entry prices from the
  portfolio computations it performed (`AdvisoryCollector.prices()` â†’
  `AdvisoryBasis` kind `entry_price`), and `AdvisoryService.evaluate_decisions` /
  `evaluate_outcome` / `auto_evaluate(gateway)` record a decision's realized
  return vs benchmark deterministically (right/wrong/neutral) â€” a decision with no
  entry price or no quote is skipped, never fabricated. Exposed as the
  `advisory_evaluate_outcomes` tool and `POST /advisory/evaluate`.
  **(2) Prompt guidance:** the finance prompt gains a `<fiduciary_advice>` block so
  the agent grounds recommendations in a portfolio computation (fewer
  false "unverified" flags). **(3) Capability class:** registered
  `advisory_verification` (test_gate â†’ the advisory suites) + its dictionary name;
  capability gate 13â†’14 measured. **(4) Front door + UI:** `advisory-client.ts` /
  `advisory-browser.ts`, the `/api/advisory/[[...path]]` proxy, a **Decisions**
  view in the Journal (`advisory-decisions.tsx`), and a **Monitors** panel in the
  Bots scheduler dock (`monitor-panel.tsx` + monitor client + `/api/automations/monitors`).
  Plus `/advisory/*` operator-gating route tests and a seam-level pipeline test.
  `tsc` clean; advisory/automation/capability/size suites green; eval gates ALL
  PASS. docs updated: `docs/fiduciary-advice.md`, `docs/NAVIGATION.md`,
  `docs/harness/decisions.md` (ADR-H197/H198).

- **Dev/ops: `next dev` now runs on Turbopack; production is the fast path.**
  Running the app under the webpack `next dev` server compiled ~19k modules on
  demand AND ballooned the process to ~6.6GB, pushing the host to its commit
  limit (25/30GB) so a page load took MINUTES. Added `--turbopack` to the dev
  commands (`dev:next`, `dev:local`, and the `local-host.js` dev spawn): ready in
  ~3s (vs ~10s) and first-page compile ~34s (vs ~71s) with a small heap.
  Production (`npm run up` / `black eclipse`) remains the recommended way to USE
  the app â€” prebuilt chunks serve in ~40â€“130ms with a ~430MB process.
  docs updated: `docs/QUICKSTART.md` (dev commands + dev-vs-up note).

- **Fix: boot build error `Module not found: Can't resolve 'fs'`.** The boot
  refactor moved the deferred pipeline's dynamic imports out of the constant
  `if (process.env.NEXT_RUNTIME === "nodejs")` block into a top-level helper, so
  webpack followed `investor-eye/scheduler â†’ @/lib/db â†’
  @prisma/adapter-better-sqlite3 â†’ better-sqlite3/bindings â†’ fs` into the Edge
  bundle (the app ships a middleware). Rewrapped the whole helper body in the
  constant `nodejs` guard so webpack's ConstPlugin drops the server-only import
  graph from the Edge build; deferred-boot behaviour is unchanged.
  no doc change â€” build-config bug fix, no architecture or contract change.

- **Proactive monitors (Fiduciary Gate, Phase 3): portfolio conditions that run
  unattended.** The Automation Engine's condition triggers gained a portfolio
  lens: a `CompositeFactProvider` now composes the market provider with a new
  `PortfolioFactProvider` (`python/harness/automation/facts.py`) that resolves
  `pf.<portfolioId>.<field>` (`weight`, `unrealized`, `cash_pct`,
  `concentration_hhi`, `total_value`, `position_count`) through the ONE portfolio
  engine â€” a failed read yields NO fact, so a condition evaluates UNAVAILABLE and
  never fires on a guess. Added a closed monitor catalogue
  (`python/harness/advisory/monitors.py`: `position_weight_breach`,
  `tax_loss_harvest`, `cash_buffer_watch`, `concentration_watch`) that builds
  ordinary `condition` + `run_agent` automations, always saved OFF; exposed via
  `AutomationService.list_monitors`/`create_monitor` and `GET/POST
  /automations/monitors`. Added `portfolio/harvest.py` + the read tool
  `portfolio_harvest_candidates` (proposal-only, wash-sale limitation stated).
  No second scheduler, no second analysis engine; nothing places a trade.
  Tests `test_automation_facts.py` (7), `test_advisory_monitors.py` (8),
  `test_portfolio_harvest.py` (6), plus monitor API cases. docs updated:
  `docs/fiduciary-advice.md`, `docs/harness/decisions.md` (ADR-H198),
  `docs/NAVIGATION.md`, `docs/portfolio-accounting.md`.

- **Advisory Ledger (Fiduciary Gate, Phase 2): every recommendation is now a
  durable, auditable decision.** The Fiduciary Gate's verdict is persisted on the
  ONE `agent-memory.db` connection as `AdvisoryDecision` / `AdvisoryBasis` /
  `AdvisoryOutcome` (new `python/harness/advisory/{store,service,tools,bootstrap}.py`),
  recorded idempotently at the answer seam (a resumed run never double-counts). A
  decision carries what was advised, its basis (the `portfolio_*` computation
  and/or the consulted source URLs, or `none`), and an appended outcome
  (realized vs benchmark â†’ right/wrong/neutral, caller-supplied â€” never
  invented). Read back via `advisory_list`/`advisory_get`/`advisory_scorecard`
  agent tools and operator-gated `/advisory/*` routes; boot wiring
  `install_advisory_layer` in `service.py`; router registered in `main.py`; a
  deterministic `advisory_scorecard` (counts by status, hit rate, avg realized vs
  benchmark). Never places a trade. Tests `python/tests/test_advisory_ledger.py`
  (12); size budgets re-pinned for the seam (graph.py, service.py; main.py kept
  under the hard ceiling by a reclaimed blank line).
  docs updated: `docs/fiduciary-advice.md`, `docs/harness/decisions.md` (ADR-H197),
  `docs/NAVIGATION.md`.

- **Fix: chat conversations no longer vanish when the server restarts or the app
  origin changes.** Transcripts lived only in browser `localStorage` (`chats_guest`),
  which is origin-scoped â€” closing the server, opening the app at a different
  host/port (http vs https, hostname vs IP), or clearing storage silently dropped
  every conversation, and a follow-up then had no thread. Conversations are now
  also persisted server-side to `.black-eclipse/sessions/<chatId>/transcript.json`
  (reusing the existing per-conversation session folder). New
  `src/lib/chat/transcript-client.ts` + `src/app/api/chat/transcript/route.ts`
  (GET one/all, POST upsert, DELETE) over `readTranscript`/`writeTranscript`/
  `listTranscripts`/`deleteTranscript` in `src/lib/chat/session-store.ts`;
  `src/components/screens/stock-chat.tsx` hydrates from the server on boot, merges
  with the localStorage cache (server wins per id, local-only chats are pushed up),
  and debounces writes/deletes. `localStorage` writes are now guarded so a blocked
  cache can never break a send. Verified live: a chat created at one origin
  restores in a fresh, empty-storage context; `tsc` clean; vitest 3149 passed.
  docs updated: `docs/ARCHITECTURE.md`.

- **Perf: `/api/regime` now caches its raw components (SWR).** The route rebuilt
  all five regime components on EVERY request â€” index quotes, up to 2000
  asset-sector rows, 400 news rows and the economics calendar (~0.8s of
  synchronous better-sqlite3 work on the single thread). Added a 60s
  stale-while-revalidate cache of the components (`src/app/api/regime/route.ts`),
  keyed by market; `assembleRegime()` still runs per request so `builtAt`/ages
  stay honest. Response contract unchanged. Covered by a new
  `src/app/api/regime/route.test.ts` (cache hit + per-market isolation).
  no doc change â€” internal cache, no architecture/data-shape/contract change.

- **Perf: widget data polling pauses while the tab is hidden.** The `DataHub`
  (`src/lib/workspace/data-hub.ts`) started an auto-refresh `setInterval` per
  subscribed topic (the dashboard registers ~20, many every 30â€“120 s), so a
  backgrounded tab kept hammering the single-threaded SQLite server forever. The
  interval callback now skips its tick while `document.hidden` (the interval
  itself keeps running, so it resumes instantly on return), and a
  `visibilitychange` handler runs a one-shot `refreshVisible()` that catches up
  ONLY the topics that currently have listeners â€” dormant topics are never
  woken. Covered by a new `refreshVisible` test in `data-hub.test.ts`.
  no doc change â€” internal polling behaviour, no architecture/contract change.

- **Perf: command-palette search no longer ships FlexSearch on every route.**
  `src/lib/search/universe.ts` statically imported `flexsearch`, and the root
  layout pulls that module in on every route (`search/store` â†’ `universe` via
  `GlobalSearch`), so the whole FlexSearch bundle sat on the initial critical
  path even though it is only needed once the palette first loads the universe.
  Made the import dynamic inside `buildIndex` (cached ctor promise), so
  FlexSearch is now a lazy chunk fetched on first palette open. Behaviour is
  unchanged; `searchUniverse`/`getUniverseBySymbol` still return `[]` until the
  index loads. Covered by a new `src/lib/search/universe.test.ts`.
  no doc change â€” internal code-splitting, no architecture/contract change.

- **Perf: server boot no longer waits on the heavy pipeline.** `instrumentation
  .register()` was awaited by Next during startup and awaited `seedUniverse`, the
  six cron `start*` registrations, provider-key apply, the journal seed, the
  production warm-up and the ingests â€” so every boot delayed the moment the app
  could answer its FIRST request (the ~10s "Ready" in the dev log was largely
  this). Split boot into a short awaited critical path (deployment-exposure log +
  the LLM-config flag the client reads) and `runBackgroundBootTasks()`, which now
  runs AFTER `register()` resolves. Same jobs, same order, same guards â€” just off
  the readiness path. Measured behaviour changes require a rebuild to observe.
  docs updated: `docs/DEPLOYMENT.md` (health/boot wording),
  `docs/ARCHITECTURE.md` (Background workers section).

- **Perf: command-palette overlay is code-split off every route.** The root
  layout statically imported the whole `GlobalSearch` (the dialog UI + the search
  library), so all of it shipped on every route's initial bundle. Split the two
  lightweight keybinds into a new always-mounted `GlobalSearchMount`
  (`src/components/layout/global-search-mount.tsx`) which lazily loads the heavy
  palette as `GlobalSearchOverlay` (`global-search.tsx`) via `next/dynamic`
  (`ssr: false`). `âŒ˜K` and `/` still work on the first keypress; the overlay only
  reacts to `store.open`. Layout now renders `GlobalSearchMount`.
  docs updated: `docs/ARCHITECTURE.md` (command-center section).

- **Perf: UI cue pack no longer decoded on first paint.** `SoundProvider` called
  `sound.preload()` on mount, which warmed (fetched + decoded) the whole active
  pack â€” ~340KB of WAV, ~20% of the first-load bytes â€” even if the user never
  triggers a sound. `preload()` now only creates the `AudioContext` (so it is
  armed before the first gesture) and a new `warmIdle()` decodes the pack once
  the browser is idle. The first gesture (`unlock`) still warms immediately, and
  `play()` loads a cue on demand if it is not warm yet.
  docs updated: `docs/ARCHITECTURE.md` (UI sounds section).

- **The Fiduciary Gate: an actionable recommendation is now disclosed unless a
  computation backs it.** Added `python/harness/advisory/` â€” a deterministic,
  no-model-call gate at the answer seam that extracts actionable claims (a
  directive verb + a symbol or numeric target) and labels each `COMPUTED` (a
  `portfolio_*` computation the run actually performed backs it), `SOURCED` (a
  symbol the run consulted), or `UNVERIFIED` (neither â†’ an appended
  `Advisory note: â€¦` disclosure; never stripped, never a trade). A new
  `AdvisoryCollector` records every `portfolio_*` tool call through
  `ToolContext.advisory_sink` (wired in `graph.py`), and the verdict is emitted
  as `advisory.gate` and attached to the run blob as `metadata.advisoryIntegrity`.
  Sits alongside the finance-fact and citation gates â€” one verifies figures, one
  advice, one citations. Tests `python/tests/test_advisory_gate.py` (18);
  `tsc` clean; graph/tools/portfolio/finance/release-gate suites green.
  docs updated: `docs/fiduciary-advice.md` (new), `docs/harness/decisions.md`
  (ADR-H196), `docs/NAVIGATION.md`.

- **Fix: Command Center board collapsed on mobile.** Section columns
  (`workspace-canvas.tsx`) applied `flexBasis:0` + `flexGrow:weight` inline at
  every breakpoint while the section row flipped to `flex-col` below `md`. In a
  column-direction parent `flex-basis:0` is a *height* of 0, clamped only by
  `min-h-[40px]`, so each stacked column became a 40px box whose widgets
  overflowed and overlapped the next column. Scoped the track weights to `md+`
  via a `--col-w` CSS var (`md:grow-[var(--col-w)] md:basis-0`) and made stacked
  columns `w-full` with `items-stretch` on the row, so they size to content on
  phones and remain weighted horizontal tracks from `md` up. Shared engine, so
  portfolio fund workspaces are fixed too.
  no doc change â€” responsive bug fix, layout contract unchanged.

- **Perf: stop the per-page widget-catalog request storm.** `UiCatalogSync`
  (mounted on the main app route) pushed the dashboard widget specs one POST at a
  time (`syncCoreCatalog()` â†’ `POST /ui/components`), so every full page load
  fired ~80 sequential browserâ†’Nextâ†’Python round-trips and saturated the runtime.
  Added a batched `POST /ui/components/batch` (`python/harness/routers/ui.py`,
  `src/lib/harness/ui-client.ts`) and switched `syncCoreCatalog` to it, collapsing
  a page-load seed to ONE idempotent request. `src/lib/harness/ui-sync.test.ts`
  updated to the batch contract.
  docs updated: docs/ui-engineering.md.

- **Perf: background pollers back off when the tab is hidden.** The three
  root-mounted watchers (`alert-notification-provider`, `task-watcher`,
  `bots-run-watcher`) polled every 10/15/30 s unconditionally; each now throttles
  while `document.hidden` (60/60/120 s), cutting idle server load on the
  single-threaded SQLite backend without changing visible-tab behaviour.
  no doc change â€” internal throttle, no architecture or contract change.

- **Repo hygiene: removed an 825 MB stray installer from the web root.** Deleted
  `public/backgrounds/local-10.1.2-windows.exe`, a mis-placed Windows installer
  sitting in the served `public/` directory; it is not part of the UI.
  no doc change â€” removal of a non-code stray asset.

- **UI composition: certified end to end and repo-wide.** Added two proofs on
  top of the earlier hardening: (1) a cross-subsystem HTTP test
  (`python/tests/test_ui_portfolio_e2e.py`) that drives the REAL `harness.main`
  app â€” create an engine portfolio, add a position, read it via the same route
  the browser resolver calls (`/portfolio/{id}/query`), then create a UI page
  with a `data-table` + `metric-card` bound to it and confirm
  `/ui/blueprints/{id}/verify` reports it renderable; (2) a server-render test
  (`src/lib/workspace/generic-widgets.render.test.tsx`) proving resolved source
  data actually becomes table rows and a metric value on screen.
  Certification run: `npx tsc --noEmit` clean; `vitest run` â€” 3146 passed / 297
  files (the single-process full-Python run hit a native OOM at ~49%, so it was
  run in two file-halves: 3484 + 2847 = **6331 passed, 16 skipped, 0 failed**).
  no doc change â€” tests + verification only; no architecture, data-shape,
  contract or setup change.

- **Composer `/` and `@` palettes: keyboard highlight now scrolls into view.**
  Arrowing through a long, scrollable command/mention palette left the scroll
  position fixed, so the highlighted option could move off-screen. Added an
  effect keyed on the highlight index + menu-open state that calls
  `scrollIntoView({ block: 'nearest' })` on the `[aria-selected="true"]` option
  inside each portaled listbox (`src/components/chat/chat-input.tsx`, both the
  command and mention palettes).
  no doc change â€” bug fix, no architecture or contract change.

- **Chat transcripts: durable server copy + shell kept within its size budget.**
  The ChatBot transcript store gained a server copy (`GET/POST/DELETE
  /api/chat/transcript`, `src/lib/chat/transcript-client.ts`): on boot the shell
  hydrates from the server, unions it with the localStorage cache (server wins on
  a newer timestamp, local-only rows are migrated up), and mirrors subsequent
  changes with a debounced upsert/delete diff gated on a successful load so a
  failed load can never delete server rows. The localStorage write is now
  guarded (private mode / sandboxed origin) so a cache failure can never break
  the in-memory chat. Because that logic (and the pre-existing local-cache load)
  pushed `src/components/screens/stock-chat.tsx` past its pinned 1474-line
  budget, both were EXTRACTED, behavior-preserving, to
  `src/lib/chat/use-conversation-persistence.ts`; the shell now sits at 1457 and
  the size-budget guard passes. Also gave the whole-repo line-ending scan in
  `src/lib/gitignore-guard.test.ts` a 30 s budget (it reads every tracked file
  and was timing out under load, not detecting a real mixed-ending file).
  no doc change â€” internal persistence/refactor; API route contract is new but
  no architecture or setup step changes.

## 2026-10-15

- **Chat/response table headings: premium, more legible, clearer sort.**
  Redesigned the header rows of the three chat/response table surfaces to a
  consistent frosted treatment: `DataTableBlock`
  (`src/components/response/data-table-block.tsx`) now sits on a
  `glass-card-subtle` panel with a tinted header strip, 12.5px semibold labels
  (was 12px medium), a primary-tinted active column, and a sort glyph that
  fades in on hover and highlights on the active column; `ComparisonGridBlock`
  (`src/components/response/visual-blocks.tsx`) gets the same tinted strip and
  12.5px semibold labels with a primary top-accent on the highlighted column;
  GFM tables (`src/components/chat/markdown.tsx`) get a quiet tinted header
  strip + semibold labels. No test/DOM-contract change
  (`src/components/response/render.test.tsx` still passes).
  no doc change â€” presentation only, no architecture or contract change.

- **UI composition hardening: verify every source family + no silent widget
  drops.** `verify_page` now validates a declared source against ALL families
  via `catalog.validate_source` (portfolio, market, news, agent, tasks,
  artifacts, research, jdds), not just portfolio. The Pages surface no longer
  silently drops a blueprint widget whose id the host registry does not render
  yet: it passes the workspace a `knownWidgetIds` set = host registry + every id
  present in the blueprint, and `renderDashboardWidget` draws an explicit "Needs
  a renderer" card for it (the Engineer path can add the real renderer). Added a
  route test for the SSE stream. Tests:
  `python/tests/test_ui_service.py`, `src/app/api/ui/stream/route.test.ts`. Docs
  updated: `docs/ui-engineering.md`, ADR-045 amendment 4 (`docs/DECISIONS.md` +
  `skills/ARCHITECT.md`).

- **Bot scheduling, batch 3 â€” drain fix, per-bot model, execution timeout, more tests.**
  Engine (`python/harness/automation/`): fixed `queue_if_running` never draining â€”
  `_drain_queue` counted the queued run ITSELF toward the concurrency cap, so the
  queue looked permanently full; it now uses a new `AutomationStore.in_flight_count`
  (triggered/running/waiting/retrying only). `execution.timeoutS`, when set, is now
  honored as a tighter per-attempt cap than `maxRuntimeS`. A bot can PIN its own
  provider/model (`action.config.modelSettings`), honored by the dispatcher via
  `_model_settings_for` while credentials stay on the runtime default. UI: a
  `BotModelPicker` in the create dialog + detail editor stores that override
  (`buildModelConfig` in `state.ts`). Docs: `automation-engine.md`. Tests:
  `test_automation_engine.py` (+5), `test_automation_core.py` (+2 DST),
  `test_jobs_cron.py` (+1 impossible cron â†’ no next fire), `state.test.ts` (+2).
  en.ts re-pinned 1238â†’1240. `send_notification`/`delegate_agent`/`credential_ref`
  remain documented limits (not fabricated).

- **UI composition: the remaining gaps closed â€” more source families, push
  updates, and the engineer loop proven.** The data-source resolver gained four
  allow-listed families, each backed by an existing read route and tested:
  `tasks:list` / `tasks:plans`, `artifacts:list`, `research:list`, and
  `jdds:search:<QUERY>` (JDDS instrument search). Live page updates moved from a
  blind poll to Server-Sent Events: `GET /api/ui/stream` watches the runtime's
  most-recently-updated blueprint (`id:revision:updatedAt`) and pushes a
  `changed` event, so Pages reloads the open blueprint only when its durable
  revision moves (window focus + a slow 60s poll remain as fallbacks; a user's
  unsaved arrangement is never yanked). The Engineer â†’ Compose closure is now
  proven end to end in `test_ui_api.py`: register an engineered component,
  discover it via `GET /ui/components`, add it to a page, and
  `GET /ui/blueprints/{id}/verify` (new route, mirroring `ui_verify_page`)
  reports it renderable. Tests: `src/lib/workspace/data-source.test.ts`,
  `python/tests/test_ui_api.py`. Docs updated: `docs/ui-engineering.md`,
  ADR-045 amendment 3 (`docs/DECISIONS.md` + `skills/ARCHITECT.md`).

- **UI composition is production-ready: the full renderable vocabulary, more
  data-source families, cross-language parity, page icons, and non-disruptive
  page refresh.** Builds on the source-driven render path (below). The catalog
  seed (`builtin_specs`) is now EXACTLY `RENDERABLE_COMPONENTS` â€” the ids the
  host registry defines: `metric-card`, `data-table`, `list`,
  `line-chart`/`area-chart`/`bar-chart`/`pie-chart`, `markdown`,
  `status-indicator`, `empty-state`, `error-state`. The nine never-renderable
  foundational kinds (`filter-bar`, `form`, `timeline`, `tree`, `log-viewer`,
  `agent-graph`, `task-board`, `artifact-preview`, `plugin-panel`) were removed
  so the runtime never advertises a widget that cannot appear; parity is
  enforced by `python/tests/test_ui_service.py` and
  `src/lib/workspace/generic-widgets.test.ts`. The resolver
  (`src/lib/workspace/data-source.ts`) gained allow-listed families â€”
  `market:quote:<SYMBOLS>`, `market:indices:<MARKET>`, `market:price:<SYMBOL>`
  (series), `news:latest`, `agent:activity` â€” each backed by an existing read
  route and still never fetching an arbitrary URL. Charts/list/markdown/status/
  empty/error widgets added (`generic-charts.tsx`, `generic-content.tsx`).
  Page-level icons implemented (the previously scoped Defect 6):
  `UiBlueprint.icon`/`BlueprintSummary.icon`, an idempotent add-column
  migration, agent (`ui_create_page`/`ui_update_page icon`) + HTTP + TS support,
  and Pages list/header rendering. Pages now reloads the open page when its
  durable revision changes (focus + 20s poll) without disrupting a local
  arrangement. Tests: `src/lib/workspace/{data-source,generic-widgets}.test.ts`,
  `python/tests/test_ui_service.py`, `test_ui_api.py`. Docs updated:
  `docs/ui-engineering.md`, ADR-045 amendment (`docs/DECISIONS.md` +
  `skills/ARCHITECT.md`).

- **Bot scheduling, batch 2 â€” engine robustness + run-behaviour controls.**
  Engine (`python/harness/jobs/cron.py`, `automation/timeutil.py`,
  `automation/engine.py`): `CronExpression.next_fire` now returns `None` for an
  expression that can never match (Feb 30) instead of a phantom ~4-year-out date,
  so such a schedule has no next run rather than a bogus distant one; interval
  triggers now honor `startAt`/`endAt` (not just cron); and `eventFilter` is
  honored generically (each key must match the event's `data`, bare or
  `data.`-prefixed, before the event's dedup slot is consumed). UI: a new
  `RunBehaviourEditor` (shared by the create dialog and the detail editor) exposes
  the engine policy the backend always supported but never surfaced â€” misfire
  policy, catch-up cap, concurrency on-conflict, max concurrent runs, retry
  attempts and per-run timeout â€” via `buildPolicies(draft)` in
  `src/lib/bots/state.ts`, threaded into `createAutomation`/`updateAutomation`.
  Tests: `test_jobs_cron.py`, `test_automation_engine.py` (+3), `state.test.ts`
  (+2). en.ts re-pinned 1225â†’1238. Docs updated:
  `docs/harness/automation-engine.md`.

- **Bot scheduling hardening â€” closed the correctness gaps found in the audit.**
  Frontend (`src/lib/bots/state.ts`, `schedule-editor.tsx`, `create-bot-dialog.tsx`,
  `bots-screen.tsx`): editing a bot now PRESERVES its trigger timezone
  (`draftFromBot` reads `trigger.timezone`; `buildTrigger` uses the draft's zone)
  instead of silently re-stamping it to the browser zone; deleting the schedule
  phrase from a description reverts the bot to on-demand instead of leaving a
  phantom schedule; the interval builder now SHOWS the 30s floor it already
  clamped to; `cronSummary` no longer mislabels `* * * * *`/`*/5 * * * *` as
  "Every day" or render `0 8 * * 7` as "Every undefined"; invalid one-time dates
  are caught by validation and no longer throw in `buildTrigger`; added a
  **monthly** schedule choice (day-of-month + time) and a real **timezone picker**
  (`Intl.supportedValuesOf('timeZone')`); `duplicateBot` now carries
  event/condition/start/end fields instead of dropping them. Engine
  (`python/harness/automation/engine.py`): `catch_up` now actually honors
  `catchUpMax` (it `break`ed after one launch); a fire due within a 60s
  `MISFIRE_GRACE_S` of startup runs on time instead of being recorded as a
  spurious skip; a manual "Run now"/recovery no longer advances `nextRunAt` (only
  a scheduling trigger type does); and the execution lease is renewed mid-run so
  a long/retrying run cannot outlive it. Tests: `state.test.ts`,
  `test_automation_engine.py` (+4). en.ts re-pinned 1222â†’1225. Docs updated:
  `docs/harness/automation-engine.md`.

- **The floating Assistant (ChatDock) can now change its AI model.** The
  always-on bottom composer rendered a read-only model pill and never sent a
  per-turn model, so it was stuck on whatever model Settings last saved â€”
  only the full ChatBot tab and bot chats had a working picker. Wired the same
  `useChatModel()` + `ModelSelector` into `src/components/chat/chat-dock.tsx`
  (replacing the read-only pill) and pass `model: chatModel.displayModel` to
  `agentRun.start`, so the choice persists to the settings vault and is sent
  per-turn, exactly as on the ChatBot tab. The composer also gained the shared
  per-question reasoning-effort `EffortControl` (ChatBot parity). The selector is
  available on mobile too (the trigger self-hides its label on small screens).
  Regression guard: `src/components/chat/chat-dock.test.ts`. Docs updated:
  `docs/ARCHITECTURE.md` (ChatDock model/effort bullet).

- **Pages can now render source-driven widgets end to end â€” a portfolio
  included.** Follow-up to the page-targeting fix (below): naming a page and
  declaring a `portfolio:<id>:<view>` source was contract-only â€” Pages/UI
  Builder render host widget ids and `source` config was inert, so an
  agent-composed widget showed "Unknown widget" or was dropped by the workspace
  kernel. Added the two universal host primitives **`data-table`** and
  **`metric-card`** (`src/lib/workspace/generic-widgets.tsx`, registered in
  `src/lib/dashboard/registry.tsx` with ids matching the runtime catalog) and
  the ONE allow-listed resolver **`src/lib/workspace/data-source.ts`** that
  parses the source, fetches through the existing portfolio front door
  (`src/lib/portfolio/engine-read.ts` â†’ `/api/portfolio/{id}/query|history|tax-lots`),
  caches it on a dynamic DataHub topic, and returns rows/value or an explicit
  UNAVAILABLE (never a fabricated number, never an arbitrary URL). Removed the
  six bespoke `portfolio-*` catalog kinds so every advertised component is
  renderable. Pages now cache their arrangement by blueprint revision
  (`pageStorageKey(id, revision)`) so an agent edit seeds fresh instead of being
  shadowed, and Refresh reloads the open page. New `ui_verify_page` tool /
  `UiService.verify_page` reads a page back and reports per-widget
  renderability. Tests: `src/lib/workspace/data-source.test.ts`,
  `src/lib/ui-engineering/live-page.test.ts`, `python/tests/test_ui_service.py`.
  Docs updated: `docs/ui-engineering.md`, `docs/portfolio-accounting.md`,
  ADR-045 amendment (`docs/DECISIONS.md` + `skills/ARCHITECT.md`).

- **Price alerts hardened for production.** (1) The watch's **Data source**
  choice (TradingView / yfinance / Auto) was stored but ignored â€”
  `fetchSnapshots` now honors it (`TradingView` = scan only, no bridge;
  `yfinance` = bridge only; `Auto` = scan then bridge). (2) The edge gate is now
  **durable** (`SystemConfig["alerts:armed:<id>"]`): a restart or edit no longer
  re-fires a condition that was already true, and firing clears it so re-enabling
  a one-shot watch starts a fresh arm. (3) The in-app notice feed is now backed
  by the durable `PriceAlertEvent` rows instead of an in-process ring buffer that
  reset on restart and diverged across workers (`notifier.ts` / `api/alerts/live`).
  (4) The builder groups OPEN/HIGH/LOW with the candle-backed indicators (they
  are) and offers HIGH/LOW. Tests: dataSource selection, durable re-arm,
  `/api/news/alert`. Alerts slice 50 passed; `tsc` clean; eslint clean.
  docs updated: `docs/ARCHITECTURE.md`, `docs/NAVIGATION.md`.

- **Existing manual bots that name a cadence get a one-click fix.** The
  description parser only runs at creation, so a bot made before it existed (e.g.
  "Janu", objective "â€¦every 3 mins") stays on a MANUAL trigger and never fires.
  The bot chat now detects a cadence in a manual bot's own instructions and shows
  an inline prompt â€” *This bot says "Every 3 minutes" but only runs on demand* â€”
  with a **Schedule it** button that patches the real trigger through
  `updateAutomation` (never a silent reschedule). Added keys
  `bots.scheduleSuggestion` / `bots.scheduleApply` (en.ts re-pinned 1220â†’1222).
  no doc change â€” bot-detail behaviour only; trigger contract unchanged.

- **Creating a bot now honours a schedule written in its description.** Every new
  bot defaulted to a MANUAL trigger, so a description like "check my portfolio
  every 5 minutes" produced a bot that never ran on its own â€” the schedule lived
  only in the optional Advanced panel. Added a deterministic
  `detectSchedule(text)` (`src/lib/bots/state.ts`, no model call) that reads
  common phrasings (every N seconds/minutes/hours/days/weeks; daily/weekly/
  monthly; weekdays; a named weekday; hourly; "every morning"; `at 9am`/`08:30`/
  noon/evening) and returns the draft patch. `create-bot-dialog.tsx` applies it as
  the description is typed and shows a live `Schedule: â€¦` line; a manual edit in
  Advanced wins and is never overwritten. An unrecognised phrase stays manual
  (no guessed cadence). Tests: `state.test.ts`.
  no doc change â€” creation UX only; trigger contract unchanged.

- **UI page targeting: a resolvable current-page default, distinguishable page
  summaries, one owner policy, and a portfolio data-source registry.** Fixes
  five defects found while trying to point an agent at ONE of fifteen
  blueprints all titled "Main" and surface a portfolio book on it.
  `get_current_page` now resolves by `blueprintId`/`path`/`title` and, with
  none, falls back to the owner's most recently updated page â€” always reporting
  `resolution` + `candidates`, never silently row 1; a new `GET /ui/current-page`
  route exposes it. Path matching is normalised and `None` never matches, with a
  distinct `UI_BLUEPRINT_PATH_UNASSIGNED` vs `UI_BLUEPRINT_NOT_FOUND`.
  `BlueprintSummary` gained `path` + `componentIds` (and `q` searches path). A
  scope mismatch is now `UI_BLUEPRINT_OWNER_MISMATCH` (HTTP 403), never "unknown
  blueprint", and the read tools no longer scope owners (matching the HTTP read
  routes) so `preview` accepts ids `get_current_page` accepted. The runtime now
  advertises valid structured data sources â€” `portfolio:<portfolio_id>:<view>` â€”
  via `get_capabilities()["dataSourceRegistry"]`, with Ledger component kinds
  and a `portfolioId` field. Page-level icons are scoped as a documented gap
  (need a model field + renderer), not built. Docs updated:
  `docs/ui-engineering.md`, `docs/portfolio-accounting.md`, ADR-045
  (`docs/DECISIONS.md` + `skills/ARCHITECT.md`). Tests:
  `python/tests/test_ui_{service,tools,api}.py`.

- **Scheduled/autonomous bot runs now post their output INTO the bot chat
  thread.** A bot's answer from a schedule/event/condition/"Run now" execution
  finished inside the runtime and was readable only in Details â†’ Run history and
  a toast â€” the conversation itself only ever showed turns you typed, so the bot
  looked like it "ran in the background with no output". `bot-chat.tsx` now polls
  the selected bot's execution history and appends each terminal run that
  produced an answer into the thread as a tagged **Scheduled run** assistant turn
  (`useBotChatStore.appendScheduled`, idempotent by execution id; the first sweep
  seeds from history and surfaces only the latest so an old thread is not dumped
  in). Autonomous turns carry no regenerate/retry. Added key `bots.chat.autoRun`
  (en.ts re-pinned 1219â†’1220; `size-budget.test.ts` + `chat-store.test.ts`).
  docs updated: `docs/ARCHITECTURE.md`.

- **Price alerts: fixed two defects found while testing, added integration
  coverage.** (1) `GET /api/alerts/:id` returned EVERY watch's event history â€”
  the `priceAlertEvent.findMany` query had no `where: { alertId }`, so one
  watch's detail page showed unrelated events. (2) `OPEN`/`HIGH`/`LOW`
  conditions could never fire: they were classified as *snapshot* indicators, but
  no snapshot ever carried OHL (TradingView scan rows have none), so every such
  alert reported `error`. They are now candle-backed (`needsCandles` treats them
  as candle data) and `indicatorWindow` exposes O/H/L series from the candle
  cache. Also removed a dead duplicate `rising`/`falling` `switch` case in
  `conditionEvaluator.ts`. New tests: `alertMonitor.test.ts` (pollâ†’evaluateâ†’
  edge/one-shot/warmup/errorâ†’dispatch, previously untested),
  `dataFeeds.test.ts` (OHL classification + series), and `api/alerts/[id]/route
  .test.ts` (per-watch event filter). Verified: alerts slice 41 passed (was 34),
  `tsc` clean, eslint clean.
  no doc change â€” bug fixes and tests; no architecture, data-shape, contract or
  setup change.

- **Desktop notifications on Windows: the local hostname now serves HTTPS.**
  The browser's Web Notification API only exists in a *secure context* â€”
  `https://â€¦` or the loopback names `localhost`/`127.0.0.1`/`[::1]`. The
  `http://blackeclipse` hosts-file alias is NOT one, so
  Settings â€º Alerts/Notifications showed the toggle unsupported
  (`window.Notification` undefined) and no OS notification could ever fire.
  Added a one-command local certificate (`npm run setup:tls` â†’
  `scripts/setup-tls.ps1`: a self-signed cert for `blackeclipse` in the current
  user's `My` + `Root` stores â€” no admin, and it adds to Root via the .NET store
  API so it never blocks on the Windows trust dialog) exporting
  `PFX + passphrase` under `.black-eclipse/certs/` (gitignored), plus TLS
  termination in `scripts/local-proxy.js` (serves `https://blackeclipse` on
  :443, 301-redirects plain http on :80, and sets `x-forwarded-proto: https`).
  `scripts/local-host.js` auto-detects the certificate â€” HTTPS when present,
  plain HTTP otherwise, so zero-config is preserved; `scripts/lib/tls.js` is the
  shared resolver. `src/lib/alerts/browser-notifier.ts` gained `secureContext()`
  and the Settings panel now explains the insecure-origin case instead of a bare
  "not supported". Auth session cookies are marked `Secure` over the local HTTPS
  front door (`src/lib/auth/handlers.ts`). Verified: `npm run setup:tls` is
  idempotent; live `https://blackeclipse` â†’ `200` with `isSecureContext === true`
  and `typeof Notification === "function"` (previously `undefined` over http);
  `http://blackeclipse` â†’ `301` to https. 3085 Vitest passed, `tsc` clean. Docs
  updated: `docs/local-hostname.md`, `docs/ARCHITECTURE.md`, `docs/NAVIGATION.md`.

- **Redesigned the response `callout` block.** The old look was a flat
  tone-tinted box with a full border and tone-coloured body text, which read as
  a heavy, low-contrast block. Callouts now use the frosted `.glass-card-subtle`
  surface with a 3px tone accent bar on the left, a small tone-tinted icon chip,
  a tone-coloured title, and neutral `text-foreground/85` body copy for
  readability. Style-only; contract/tone vocabulary unchanged.
  no doc change â€” visual block styling only.

- **Unified every response-renderer notice/warning surface on one design.**
  Added an exported `NoticeCard` (tone accent bar + tone-tinted icon chip +
  tone title on a frosted `.glass-card-subtle` surface) and routed the
  `callout` block, `UnknownBlockCard`, `DiagnosticsPanel`, the `BlockBoundary`
  render-failure card (`response-view.tsx`), the Mermaid error card, the
  node-graph node-detail card and the learning-map curriculum-gap list through
  it â€” replacing the flat `border-<tone>-500/30 bg-<tone>-500/[0.06]` boxes.
  Style-only; contract/tone vocabulary unchanged.
  no doc change â€” visual block styling only.

- **Stripped the response data-table chrome (ChatGPT-style, honest table).**
  `DataTableBlock` no longer sits in a `rounded-xl border border-white/10`
  container and the header row lost its `bg-accent/20` fill; the header is now
  quiet `text-muted-foreground` with a single hairline underneath and rows keep
  only a faint separator â€” matching the borderless markdown-table style already
  used in the chat renderer. Sort affordance kept via a hover text shift.
  Style-only; no contract/interaction change.
  no doc change â€” visual table styling only.

- **Added per-tone depth to the notice cards.** The five callout tones
  (`info` sky, `note` violet, `success` emerald, `warning` amber, `danger`
  rose) now each carry a soft corner glow, a gradient accent bar and a ringed
  icon chip instead of a flat colour bar â€” so the yellow (warning) and purple
  (note/tip) notices read as distinct, finished surfaces. Each card also got a
  left-to-right tone wash, an inset rounded accent bar (no longer a hard
  full-height stripe), a slightly larger shadowed icon chip, and a hairline
  inset ring. Style-only.
  no doc change â€” visual block styling only.

- **Restyled the bot chat composer to match the app's canonical frosted-glass
  composer.** The bot chat input was a flat bordered textarea with detached
  model selector and send button, so it looked out of place next to the main
  chat surface. It now uses the same single `glass-card rounded-3xl` container
  with the textarea, model selector and round send/stop buttons nested inside,
  matching `chat-input.tsx`. Style-only; no contract change.
  no doc change â€” visual/composer styling only.

- **Fixed scheduled bot runs producing no visible output.** A completed
  unattended run produced an answer but it was never persisted: `finish_execution`
  dropped `DispatchResult.output`, and the default `in_app` delivery only
  published a template key â€” so the run history and the completion notice showed
  "completed" with nothing to read. The engine now persists the bounded run
  `output` on the execution (`AutomationExecution.output`, additive column +
  idempotent `_ensure_column` migration), the `ExecutionView` carries it, the Bots
  run history renders it under **Summary**, and the completion notification uses
  it as the body. Also fixed `Dispatcher._call_tool` calling
  `ToolRegistry.execute` with the wrong arity (missing `call_id`), which made
  every `call_tool`/`run_code`/`browser_action`/`custom_action` automation fail
  with `INTERNAL_ERROR`. Verified live end-to-end: a `call_tool` bot run
  completed and its output is returned by `/automations/{id}/history` and
  `/automations/executions/{id}`. Tests:
  `test_completed_run_stores_its_output`, `bots-run-diff.test.ts`.
  docs updated: `docs/harness/automation-engine.md`.

- **Size-budget ratchet re-pinned for the new seconds-cadence key.** The
  sub-minute scheduler added one i18n key (`bots.seconds`) to `en.ts`, taking it
  to 1219 lines â€” one over its 1218 pin â€” so the graduated size guard failed
  (`findOversized`). Re-pinned `src/lib/i18n/dictionaries/en.ts` 1218â†’1219,
  following the existing re-pin convention; the file may only shrink again.
  `npx tsc --noEmit` clean; vitest 3084 passed.
  no doc change â€” size-budget ratchet only; no architecture, data-shape,
  contract, setup or folder change.

- **Fixed bot interval schedules drifting by the run duration.** An interval
  automation's next fire was anchored to `lastRunAt` â€” a timestamp written at run
  *completion* â€” so every run pushed the next slot out by its own duration: a
  "1 minute" bot silently became "1 minute + runtime" (verified live: a 60s
  interval with a 20s run fired every **80s**). `AutomationEngine._advance_next_run`
  now anchors the interval grid on the scheduled slot that is firing
  (`next_run_at`), so the cadence is fixed and immune to run duration; also added
  `docs/harness/automation-engine.md` regression test
  `test_interval_cadence_is_not_drifted_by_run_duration`. Sub-minute schedules
  are now supported: `MIN_INTERVAL_S` lowered 60s â†’ 30s and the Bots schedule
  editor gained a **seconds** unit. Verified live end-to-end: a 30s bot created
  via `/automations` fired every 30s on a fixed grid.
  docs updated: `docs/harness/automation-engine.md`.

- **Mobile navigation now follows the menu mode (Terminal / Agentic / Bots).**
  The phone bottom bar and its "More" sheet were a fixed list; they now mirror
  the desktop sidebar's mode: the first four enabled tabs of the active mode sit
  in the bar and the rest move into More (`MobileBottomNav` reads
  `useSidebarConfigStore.mode` + the sidebar config, with a per-mode tab order
  and a `bots` list). The More sheet gained a **Terminal / Agentic / Bots**
  switcher (switching to Bots also opens the Bots tab), so the menu can be
  changed entirely on a phone. Verified live at 390px: Terminal â†’
  ChatBot/Command Center/Market Discover/Portfolio; Agentic â†’
  ChatBot/Skills/Eclipse Memory/Artifacts; Bots â†’ Bots/ChatBot/Tasks/Artifacts.
  `tsc` clean; vitest 3082 passed.
  no doc change â€” UI-only; no architecture, data-shape, contract or setup change.

- **ChatBot-landing Aurora no longer lags the sidebar/dock.** The landing-only
  in-panel `<AuroraGlow />` was `absolute` inside the main panel, so it
  shrank and re-centered whenever the sidebar expanded/collapsed or the right
  dock resized the panel. It is now pinned to the viewport (`fixed`) â€” full
  width and centered regardless of panel width, still behind the sidebar
  (z-50) and the Agent Workspace dock (z-20) via the panel's `z-10` stacking
  context. `stock-chat.tsx` held at its 1474-line ratchet. `tsc` clean;
  size-budget + reachability tests pass.
  no doc change â€” UI positioning fix; no architecture, data-shape, contract,
  setup or folder change.

- **Group rooms: each speaker wears its turn.** The group chat now shows mood
  per member, not just per bot chat. `group-chat-room.tsx` tracks a
  `memberId â†’ GhostMood` map updated from each member's own turn (via
  `moodFromEvent`/`onDelta` in `runMember`), so while bots answer in parallel
  each roster face lights up with its own state (thinking â†’ working â†’ speaking â†’
  happy/sad, auto-resting to idle after ~1.8s; pending rest timers are cancelled
  when a member re-runs and cleared on unmount). The room's own header face
  shows the busiest member (speaking > working > thinking > waiting > happy >
  sad). Roster avatars are now `live`; message avatars stay static to bound the
  number of animated faces. No new dependency. `tsc` clean; eslint 0 errors;
  vitest 3082 passed.
  docs updated: `docs/NAVIGATION.md` (Bots row).

- **Sidebar: mobile drawer no longer shows the collapse chevron beside the X.**
  The collapse/expand chevron is a desktop-only affordance (the drawer is
  dismissed with its own close button). The sidebar's collapsed state is now
  `desktopCollapsed && !isMobile`, so the mobile drawer is always full-width and
  the collapse button renders only on `md+`; the expand chevron can no longer
  appear in the drawer. Verified live at 390px: drawer shows the brand + nav + a
  single X, zero visible collapse/expand buttons. `tsc` clean; vitest 3082
  passed.
  no doc change â€” UI-only; no architecture, data-shape, contract or setup change.

- **Bots: removed the "Add finance starter pack" entry points and default the
  page to the most recent chat.** Dropped the seed button from the Bots empty
  state and all sidebar variants (expanded header, collapsed rail, labeled
  bottom button); the empty state now offers only New bot / New group. The Bots
  page now auto-selects the most recent conversation on open â€” the bot with the
  latest `lastRunAt` (falling back to `updatedAt`) â€” unless a deep link
  (`?bot=`/`?group=`) or an explicit selection exists. `tsc` clean; vitest
  finance-bots passed. no doc change â€” UI/behaviour change only; no architecture,
  data-shape, contract or setup change.

- **Command Center fix: side rails no longer crush the board at 1024â€“1280px.**
  The mobile program had changed the Watchlist rail from `hidden xl:block` to
  `w-full lg:w-64`, so between `lg` and `xl` BOTH rails showed while the app
  sidebar was also present, squeezing the centre board's columns down to ~53px
  (widgets overlapped/clipped). `WorkspaceCanvas` now only applies a zone's
  breakpoint/width classes when the zones are actually side-by-side (`lg+`); when
  stacked it forces `w-full` and visible, so a host `hidden xl:block` never
  hides a stacked rail. Added `WorkspaceZoneConfig.resizerClassName` so each
  drag-resizer matches its zone's own breakpoint (left `hidden xl:block`, right
  `hidden lg:block`), and restored the dashboard rails to their original
  breakpoints. Verified live on the rebuilt production server: 1024px min column
  53â†’198, 1280/1440 unchanged, 390px both rails stack full-width. `tsc` clean;
  vitest 3082 passed.
  no doc change â€” layout fix; no architecture, data-shape, contract or setup
  change.

- **Mobile navigation program (phase 2: remaining screens sweep).** Finished the
  per-screen pass. ML Lab's training control rows and model-action buttons now
  wrap, and the active-job row truncates instead of pushing Cancel off-screen;
  the Investor Eye full-page map's top strip wraps and hides the event/market
  counter + `Esc` hint on phones; the data-source wizard footer wraps; the Chart
  Workspace header hides its keyboard-shortcut hints (keeping the panel count)
  below `md`. Audited and confirmed already-mobile-safe: Market Discover (its
  Advanced Filters panel is a responsive grid, reachable from the always-visible
  button; quick-filter rows scroll), Chart Workspace (single column below `md`,
  pinned widths gated to `lg`), Investor Eye toolbar (wraps), Skills (drill-down
  detail, `wrap` TabBar), Bots (single conversation page), Eclipse Memory
  (responsive grids), Research Data / Factor Lab (tables + tab strips scroll).
  Labs keep their "best on desktop" notices. Verified: `npx tsc --noEmit`
  clean; vitest 3077 passed.
  no doc change â€” layout/hide-only; no architecture, data-shape, contract or
  setup change.

- **Mobile navigation program (phase 1: foundation + shell + core pages).**
  Added a phone bottom tab bar (`layout/mobile-bottom-nav.tsx`) with Chat /
  Command Center / Market Discover / Portfolio plus a "More" bottom sheet
  listing every remaining tab, and wired it into the shell with reserved
  bottom padding so content never hides behind it. Consolidated the scattered
  `window.matchMedia` calls into `hooks/use-media-query.ts` (`useIsMobile` /
  `useIsDesktop`). The Agent Workspace / Bots scheduler docks now render as a
  bottom sheet on phones (`layout/mobile-dock-host.tsx`) instead of a fixed
  side column. Hid non-core mobile chrome: the Aurora WebGL glow, the Command
  Center status bar, and Export/Import/Reset (kept Fullscreen). The chat jump
  rail is desktop-only and the floating assistant dock now clears the bottom
  nav and the safe-area inset. Added a dismissible "best on desktop" notice
  (`ui/desktop-only-notice.tsx`) to UI Builder, ML Lab, Factor Lab and
  Backtest, and made the bubbles canvas height responsive. Added `.safe-bottom`
  / `.touch-target` CSS helpers. `en.ts` kept at its ratchet; `stock-chat.tsx`
  re-pinned 1460â†’1474 (mounts only). Verified: `npx tsc --noEmit` clean;
  vitest 3077 passed.
  no doc change â€” navigation/layout only; no architecture, data-shape,
  contract or setup change.

- **Bot faces wear their turn (status-driven moods).** Building on the live
  avatar, the face now reflects what the agent is doing. Added `GhostMood`
  (`idle | thinking | working | speaking | waiting | happy | sad`) with two pure
  mappers in `src/lib/bots/ghost-mood.ts` â€” `moodFromStatus` (the shared
  `ResponseStatus` lifecycle) and `moodFromEvent` (a normalized `HarnessUiEvent`)
  â€” plus a `mood` prop threaded through `GhostAvatar` â†’ `LiveGhostAvatar` â†’
  `BotAvatar`, rendered as `data-mood` and animated in `globals.css` (eyes lift
  for thinking, dart for working, mouth moves for speaking, hop+squint on happy,
  droop on sad). `bot-chat.tsx` drives it from the live turn: `thinking` on send,
  `working` on tool/activity events, `speaking` on deltas, `happy`/`sad` on the
  final, auto-resting to `idle` after ~1.8s. Mood transforms are scoped
  `:not([data-interactive])` so a cursor-tracking face keeps following the
  pointer; `data-mood` only applies while `data-active` (on-screen). New unit
  test `ghost-mood.test.ts`. No new dependency. `tsc` clean; eslint 0 errors;
  vitest 3082 passed.
  docs updated: `docs/NAVIGATION.md` (Bots row).

- **Bot faces come alive (ambient animation + cursor gaze).** The ghost face was
  a fully static SVG. Added stable class hooks to `GhostAvatar` (body/eyes/gaze/
  mouth + a `data-eyes-closed` flag) and layered a new `LiveGhostAvatar` wrapper
  on top of the unchanged drawing: a subtle breathe, a blink (suppressed for
  already-closed eye styles), and â€” when `interactive` â€” eyes that ease toward
  the cursor plus a click bounce. Gaze uses one ref-counted page-wide
  `pointermove` listener (`src/lib/bots/use-ghost-gaze.ts`) writing `--look-x/-y`
  custom properties, so N faces cost one listener and no React re-renders. An
  IntersectionObserver pauses off-screen faces. All CSS is scoped under
  `.be-ghost-live[data-active]` in `globals.css`, so the static `GhostAvatar`
  used across lists/rows/icons never animates, and every effect sits inside the
  existing reduce-motion / animations-off kill switches (no exemption). Wired in
  two places only: the bot-chat header (`BotAvatar ... live` â€” ambient only, so a
  click still opens the identity drawer) and the customizer preview
  (`LiveGhostAvatar ... interactive` â€” gaze + poke on a non-button); `BotAvatar` gained
  opt-in `live`/`interactive`/`inViewOnly` props. No new dependency. `tsc`
  clean; eslint clean; every touched file is far under the size ceiling.
  docs updated: `docs/NAVIGATION.md` (Bots row).

- **Chat composer stays one line when empty.** The auto-grow counted the
  (wrapped) placeholder in `scrollHeight`, so on a phone-width composer the
  empty bar inflated into a 3-line block and the placeholder spilled below the
  rounded box. The resize now short-circuits when the value is empty (clears the
  inline height back to `rows={1}`) and the textarea sets `wrap="off"` while
  empty so the placeholder clips on one line; typed content still soft-wraps and
  grows as before. Measured live: textarea 141px @360, 171px @390, 624px @1280,
  all single-line. `tsc` clean; vitest 3077 passed.
  no doc change â€” UI bug fix; no contract/architecture change.

- **Aurora glow restored on the ChatBot landing.** The app-wide responsive pass
  (commit 5062aeab) deleted the in-panel `<AuroraGlow />` gated to the empty
  transcript, leaving only the shell-level glow at the root (`z-0`). The chat
  panel is `relative z-10` and, on the landing, `.app-bg-layer` fills it with the
  opaque default solid backdrop, so the shell glow was covered â€” while the
  conversation view (no wallpaper layer, chat surface defaulting to `opacity: 0`)
  showed it through. Re-mounted the landing-only in-panel glow between
  `.app-bg-layer` and `<ChatWordmark />`. Re-pinned the `stock-chat.tsx` size
  ratchet 1455â†’1460. no doc change â€” UI fix only; no architecture, data-shape,
  contract, setup or folder change.

- **Responsive pass across the shell and screens.** Fixed the app-wide mobile
  breakage: the Agent Workspace dock's inline `width` (300â€“760px) no longer
  overrides `w-full` below `md`; removed the duplicate floating hamburger in the
  sidebar that overlapped the TopBar's menu button on phones; made the TopBar
  search flex-grow and capped the model selector/dropdowns; the Command Center's
  Watchlist/Market rails now stack below the board instead of `hidden`, its
  header actions collapse to icons, and the workspace canvas only applies pinned
  zone widths + resizers from `lg` up. Shared `DialogContent` now scrolls
  (`max-h-[calc(100dvh-2rem)]`) and `TabsList` scrolls horizontally. Settings
  gained a mobile search field and a filtering pill row, the F-key shortcut
  selector is no longer hidden on phones, and several non-wrapping grids/rows
  (security approvals, background OptionGrid, density, data-source/providers/MCP
  headers) were made wrap or responsive. Chat: the composer no longer clips the
  input, popovers are viewport-capped, the approval card is height-clamped, the
  message-rail ticks got a touch hit-area, and the dock respects safe-area.
  Market screens: the Chart Workspace reflows to a single column below `md`,
  month/mini calendars no longer squeeze, volume-analytics hides columns, and
  several unwrapped tables/tab strips now scroll. Terminal pop-out clamps its
  width on mount. Verified: `npx tsc --noEmit` clean; vitest 3077 passed.
  (Python/evals scripts exceeded the run window in this env.)
  no doc change â€” UI/layout fixes only; no architecture, data-shape, contract,
  setup or folder change.

- **Investor Eye map/globe and embedded charts now follow light mode.** The
  world map is canvas/WebGL and the TradingView widget hardcoded `theme: 'dark'`,
  so both stayed black on a white page. `WorldMap` now observes the app's `dark`
  class (`useDarkScheme`) and drives a light geo palette, sky backdrop, tooltip
  and globe surface when the scheme is light (the starfield is not mounted); the
  TradingView embed follows the scheme too. Also hardened `--glass-tint-light`
  (`lightGlassTint`) so a stored dark glass tint can no longer render dark
  widget-card glass in light mode. `tsc` clean; theme + investor-eye vitest
  suites pass. docs updated: `docs/investor-eye-architecture.md`.

- **Command Center popups: fixed the cramped, cut-off persona pickers.** The
  onboarding "Build your workspace" dialog and the "New layout" preset dialog
  inherited `sm:max-w-sm` from the shared `DialogContent` base, which â€” because
  Tailwind emits responsive variants last â€” overrode the page's `max-w-2xl` /
  `max-w-lg`, collapsing the preset grid to ~384px (3 skinny columns of
  wrapped-to-death text). Both are now explicitly `sm:max-w-*` and constrained to
  `max-h-[calc(100dvh-2rem)]` as a flex column whose body scrolls, so a tall
  grid no longer pushes the title and confirm button off-screen (previously the
  dialog measured 1106px tall at `top:-153px` with no scroll). Verified live
  against the running dev server: onboarding 672px, new-layout 512px, both fit
  the viewport and scroll internally. `tsc` clean; vitest 3077 passed.
  no doc change â€” bug fix, no contract/architecture change.

- **`blackeclipse` is now the default start.** Added `scripts/local-host.js`, a
  combined launcher that starts the Next.js app bound to `127.0.0.1` **and** the
  local proxy on `:80` together, and rewrites the child's output so the only
  address shown is `http://blackeclipse` (Next's own `Local:`/`Network:` lines are
  rewritten on the fly). Wired into `npm run dev`, `npm run up`, and the `black` /
  `black dev` CLI; `Ctrl+C` stops both. The original raw server is preserved as
  `npm run dev:next` (all interfaces) alongside `npm run dev:local` (loopback, no
  proxy). Hardened `scripts/local-proxy.js` so a transient post-listen server
  error no longer kills the proxy. Verified live: default launcher binds `:80`,
  banner shows only `blackeclipse`, and `curl http://blackeclipse/` â†’ `200`.
  docs updated: `docs/local-hostname.md`, `docs/QUICKSTART.md`,
  `docs/NAVIGATION.md`, this file.

- **Sidebar mode switcher: added the missing Bots hotkey and surfaced all three
  shortcuts on the tabs.** The switcher offered `Alt+T` (Terminal) and `Alt+A`
  (Agentic) but no key for Bots; added `Alt+B` to `MODE_SHORTCUTS`, which sets the
  mode and opens the Bots workspace (mirroring the dropdown click), and allowed
  `bots` to persist/restore on hydrate. Each switcher entry now shows its key
  badge, and the keyboard-shortcuts help dialog lists a Bots row.
  docs updated: this file. No architecture/contract change, so no other doc edit.

- **`npm run setup:hostname` â€” one-command, self-elevating local hostname.**
  Added `scripts/setup-hostname.ps1` (re-launches itself via UAC, appends
  `127.0.0.1 blackeclipse` to the Windows hosts file only when missing, flushes
  DNS) and the npm script `setup:hostname`. Root cause of "cannot see
  `blackeclipse`": the hosts entry is required for the name to resolve and a
  normal shell cannot write the protected file. Verified on this machine: entry
  added, `ping blackeclipse` â†’ `127.0.0.1`, and `http://blackeclipse/` â†’
  `200` (`x-powered-by: Next.js`) with `localhost:3000` still `200`.
  docs updated: `docs/local-hostname.md`, `docs/QUICKSTART.md`,
  `docs/NAVIGATION.md`, this file.

- **Redesigned the global crash screen (`ErrorBoundary`).** The full-page
  "Something went wrong" fallback dropped its âš ï¸ emoji and flat layout for a
  frosted `.glass-card` with a rose wash, an `AlertTriangle` icon badge, and
  primary "Try again" + secondary "Reload" actions; the panel is centred over a
  `min-h-[100dvh]` region. Same treatment as the chat error card.
  no doc change â€” visual/UI only, no contract change.

- **Local hostname front door: reach the app at `http://blackeclipse`.** Added a
  zero-dependency, loopback-only reverse proxy (`scripts/local-proxy.js`; Node's
  built-in `http`/`net`) that listens on `127.0.0.1:80` and forwards to the
  unchanged Next.js server on `:3000`, preserving the original `Host` and adding
  `X-Forwarded-*`, and forwarding WebSocket/HMR upgrades. Paired with a
  `scripts/local-proxy-stop.js`, the npm scripts `proxy` / `proxy:stop`, and a
  LAN-safe `dev:local` (`next dev -H 127.0.0.1`); `dev` is unchanged. Because the
  new hostname changes the browser origin, three small code points were made
  hostname-aware: `src/lib/api-guard.ts` treats `blackeclipse` as a loopback
  alias AND resolves the request host from the `Host`/`x-forwarded-host` header
  instead of `request.url` (which Next rebuilds from its own bind address in dev,
  so a fronted same-origin POST otherwise 403'd); `src/lib/auth/handlers.ts` uses
  the shared `isLocalRequest` so the session cookie is not marked `Secure` over
  plain http; `next.config.ts` lists `allowedDevOrigins` so Next dev does not flag
  `/_next/*`/HMR as cross-origin. Verified live (homepage 200, `/api/news` 200,
  same-origin POST 200, cross-site 403, HMR `101`, localhost:3000 still 200). docs
  updated: `docs/local-hostname.md` (new), `docs/NAVIGATION.md`,
  `docs/QUICKSTART.md`, this file.

- **Redesigned the chat error/warning surface.** The assistant error card in
  `chat-history.tsx` is now a frosted `.glass-card` with a rose wash, an icon
  badge, a heading, an optional error-code chip and a clearer Retry action; the
  separate "Something went wrong" status line is suppressed when the card shows,
  and a new `restatesError` guard stops a failed command from printing the same
  sentence twice (the router streams both a readable `output` and an
  `error.message`). no doc change â€” visual/UI only, no contract change.

- **Global "New chat" shortcut (Ctrl/Cmd+Alt+N).** Replaces the ChatBot-tab-only
  `mod+n` page shortcut (`usePageShortcuts(chatRootRef, â€¦)` in `stock-chat.tsx`)
  with a shell-wide keydown handler: it switches to the ChatBot tab, clears the
  transcript, and drops the caret in the composer via the existing `be:focus-chat`
  event. `Ctrl/Cmd+N` was unusable for this â€” browsers reserve it for "new window".
  The shortcuts overlay gained the row; the shell's size-budget pin was re-pinned
  1441â†’1455 with justification.
  no doc change â€” keybinding/UX only, no architecture or contract change.

- **Search: embeddings are stored at boot, not only after a query.** The boot
  warm-index now resolves the embedding provider from the front-door environment
  (`HARNESS_JOB_*`, via `SearchService._boot_settings`) and EMBEDS at index time,
  so `vectors` is non-zero as soon as the runtime boots with a provider â€”
  previously the boot ran `configure(None)`, so every document stayed `vectors: 0`
  until a later query re-configured a provider and triggered the backfill. A bare
  runtime (no front-door env) still indexes honestly keyword-only. Tests:
  `python/tests/test_search_code_source.py` (+2). docs updated:
  `docs/harness/search-retrieval.md`.

- **Plain `/` now focuses the chat composer; global search stays on Ctrl/Cmd+K.**
  `useCommandCenterKeybind` dropped its `slashShortcut` handling so the command
  center is toggled by `Ctrl/Cmd+K` alone; a new `useChatFocusKeybind`
  (`src/hooks/use-chat-focus-keybind.ts`) broadcasts a `be:focus-chat` window
  event on `/`, which the visible composer answers (`ChatInput` guards with
  `isKeyboardScopeVisible`, `ChatDock` ignores while suppressed and restores from
  the minimized pill first). Mounted once with `GlobalSearch`, so it covers every
  route. The shortcuts overlay row was relabeled accordingly.
  no doc change â€” keybinding/UX only, no architecture or contract change.

- **Focus mode (Ctrl/Cmd+Alt+X) now fills the page instead of a centered
  column.** The chat tab's focus branch dropped its `max-w-[860px]` caps, so the
  transcript, follow-up composer and the landing composer (`empty-state.tsx`)
  use `max-w-none` and span the full main panel; the shortcuts-overlay
  description was corrected to say "full-width focus view".
  no doc change â€” layout/UX only, no architecture or contract change.

- **Focus mode now also tucks away the right-docked Agent Workspace.** With the
  left sidebar, header and terminal already hidden there, the still-docked
  workspace was the last column splitting the page in two; it now unmounts in
  focus mode (state lives in its store, so it returns on exit), giving the chat
  the whole width. Same change scope as above.
  no doc change â€” layout/UX only, no architecture or contract change.

- **Startup hardening: stop the spurious "runtime unavailable" 503 loop and the
  dev chunk-load overlay.** The Python runtime is now pre-started (non-blocking)
  by `src/instrumentation.ts` instead of only lazily on the first harness
  request, and the cold-start readiness budget is configurable via
  `HARNESS_PY_START_TIMEOUT_MS` with the default raised 30s â†’ 120s
  (`src/lib/harness/python-runtime.ts` + pure `resolveStartTimeoutMs` /
  `DEFAULT_START_TIMEOUT_MS` in `src/lib/harness/runtime-supervision.ts`). A cold
  start imports the whole agent stack; the old 30s budget let the front door kill
  a still-starting process and respawn it forever under load, so every route
  503'd. Separately, the dev-only webpack `output.chunkLoadTimeout` is raised to
  300s in `next.config.ts` so a slow `next dev` first compile no longer surfaces
  as a `ChunkLoadError` / "Invalid or unexpected token" overlay (a slow compile,
  not a syntax error â€” `tsc`/`next build` pass; `npm run up` serves prebuilt
  chunks). Tests: `src/lib/harness/runtime-supervision.test.ts` (+4 cases).
  docs updated: `docs/harness/architecture.md`, `docs/QUICKSTART.md`, this file.

- **Bot Team Orchestration: run a team of Bots on one objective.** A new
  composition layer (`python/harness/team/`) gives the existing Bot system five
  native multi-agent capabilities without forking anything: capability-routed
  Bot-to-Bot delegation through the A2A layer (least privilege + budgets +
  durable messages), dependency-aware concurrent execution on the existing
  `TaskScheduler` (new per-Bot `task.metadata.maxConcurrency` /
  `HARNESS_TASK_MAX_PER_AGENT` and per-plan `plan.metadata.maxConcurrency` caps),
  a validated task graph (cycle/unknown-dependency detection), deterministic
  evidence-based conflict reconciliation (never voting or averaging; benign
  causes classified, genuine conflicts disclosed), and an independent reviewer
  with bounded targeted repair + re-verification (a producing Bot can never
  approve its own work). Also fixed a real A2A dispatch gap: `delegate_task` now
  starts the plan so a delegated task is actually picked up (additive
  `autostart`/`plan_id`/`dependencies` params, defaults preserve old behaviour).
  Reachable from the chatbot via `TEAM_TOOLS` (on the default agent allowlist) and
  from `POST /team/runs`; front door `src/lib/harness/team-client.ts` +
  `src/app/api/team/[[...path]]/route.ts`. Tests:
  `python/tests/test_team_{graph,conflicts,review,service,e2e}.py` (43 cases incl.
  measured concurrency, cancellation, restart durability, reviewâ†’repair,
  `requireApproval` gate, budget usage accounting). Also enforced the documented
  gaps: `TeamPolicy.requireApproval` is now a hard gate against the A2A approval
  store, and the task executor meters/limits A2A token+tool-call usage
  (`tasks/bootstrap.py`). docs updated: `docs/harness/bot-team-orchestration.md`
  (new), `docs/NAVIGATION.md`, this file.

- **Chat: `@`-mention a bot or group chat from the main composer to delegate the
  turn.** Typing `@` in the main chat opens a palette of the user's bots and group
  rooms (`src/components/chat/chat-input.tsx`); selecting one inserts `@Name ` and
  shows a chip. On send the message is DELEGATED to each mentioned target over the
  SAME runtime path the Bots workspace uses â€” a bot answers as itself (persona +
  private `bot-<id>` memory), and a mentioned room has every member answer in its
  own voice. Replies stream into the transcript attributed to their author
  (`Message.author`, rendered in `chat-history.tsx`). A completed exchange is
  MIRRORED into the bot's/room's own Bots-tab thread (`useBotChatStore` /
  `useBotGroupsStore`), and a mid-run approval is surfaced on the message and
  decided by the delegation hook â€” the invoker now forwards typed harness events
  via `onEvent`, and `stock-chat.tsx` routes the ApprovalCard decision to the
  delegated run when the pending approval belongs to it. Pure mention
  registry/parser `src/lib/bots/mentions.ts` (+ `mentions.test.ts`); shared turn
  invoker `src/lib/bots/invoke.ts` (extracted from `bot-chat.tsx` /
  `group-chat-room.tsx`, which now call it); lifecycle hook
  `src/lib/bots/use-bot-delegation.ts`; routing through `dispatchTurn` in
  `stock-chat.tsx` (send / follow-up / edit / injected prompts). `stock-chat.tsx`
  re-pinned 1399â†’1441 in the size ratchet (the bulk was extracted to the hook).
  docs updated: `docs/harness/mentions.md` (new),
  `docs/harness/slash-commands.md`, `docs/NAVIGATION.md`.

- **ChatBot landing: fresh install now defaults to a Solid backdrop, not a
  wallpaper.** `DEFAULT_BACKGROUND.mode` flipped `'image'` â†’ `'solid'`, so a new
  instance paints the theme fill plus the wordmark and loads **no** image
  until the user opts into one (Settings â€º General â€º Background â†’ Image, where
  Eclipse I stays pre-selected). Fixes the wallpaper appearing by default.
  Updated `backgrounds.test.ts` (customized-flag now keys off image mode).
  docs updated: `docs/ARCHITECTURE.md`.

- **ChatBot landing: simpler backdrop, smaller default wordmark.** Dropped the
  in-panel `AuroraGlow` from the ChatBot landing (`stock-chat.tsx`) so the new
  Solid default reads as a clean fill + wordmark instead of a cluttered
  glow-over-backdrop; the shell-level Aurora is untouched and still shows on the
  other tabs. Shrank the shipped default wordmark `textScale` 16 â†’ 7 (vw), so it
  reads as a modest centered label rather than a full-bleed backdrop.
  docs updated: `docs/ARCHITECTURE.md`.

- **Fix React 19 hydration mismatches on the chat landing.** (1) `activeTab` no
  longer reads localStorage inside its `useState` initializer (`stock-chat.tsx`):
  it starts on `chat` for both the server and the first client render and applies
  the saved start screen in the boot effect after mount, so a custom start tab no
  longer desyncs SSR. (2) `suppressHydrationWarning` added to `<html>`
  (`layout.tsx`) â€” the pre-paint theme script mutates its `dark` class before React
  hydrates. (3) `suppressHydrationWarning` added to the two Base UI triggers that
  lacked it â€” `SelectTrigger` (`ui/select.tsx`) and the Effort `PopoverTrigger`
  (`chat/effort-control.tsx`) â€” matching the existing pattern on
  `DropdownMenuTrigger`/`TooltipTrigger` and silencing the spurious `base-ui-*`
  id diffs. Reproduced and verified fixed with headless Chromium across
   fresh / light-theme / custom-start-tab / conversation scenarios (zero errors).
   no doc change â€” bug fix, no contract change.

- **Fix spurious `RUN_ORPHANED` on every chat output.** When the Python runtime
  port was silent but had answered `/health` inside the busy-grace window, the
  supervisor warned "treating it as busy, not killing it" and then *fell through
  to spawn a second uvicorn anyway*. That child could not bind the still-held
  port (`WinError 10048`), yet uvicorn runs the FastAPI lifespan (`_boot` â†’
  `run_startup_maintenance` â†’ `fail_orphaned_runs`) *before* the bind â€” so each
  doomed spawn marked the run the real runtime was actively executing as
  `RUN_ORPHANED`. `src/lib/harness/python-runtime.ts` now `return true` in the
  busy branch so a recently-healthy runtime is treated as up and no duplicate
  spawn (nor its boot-time reconciliation) occurs; a genuinely hung listener is
  still cleared once it is past the grace window.
  no doc change â€” bug fix, no contract change.

- **Harden the two remaining paths that could still force a spurious runtime
  restart.** (1) `harness/security/store.py` `audit_counts` coerced aggregates
  with a bare `int(...)`; a single NULL/malformed group row threw `TypeError`, so
  `GET /health` returned 500 â€” which the front door reads as "runtime down" and
  restarts. Counts now coerce via a NULL-safe `_as_int` and skip bad rows, and
  `harness/routers/security.py` exposes `security_health_safe()` (the guarded
  entry `/health` now calls, keeping `main.py` under its hard size ceiling) so no
  security fault can 500 the liveness probe (honest `{ok:false}` instead). (2)
  Orphan reconciliation ran in the FastAPI lifespan, which fires *before* uvicorn
  binds; the new `run_recovery.reconcile_orphaned_runs` proceeds only when the
  bind port is free, so a duplicate process that is about to fail its bind can no
  longer orphan the runs a live runtime is executing. (3) Production/start
  hygiene: `scripts/kill-port.js` now also clears the Python runtime port
  (resolved from `HARNESS_PY_URL`/`HARNESS_PY_PORT`/`.env`, default 8765) in
  addition to 3000, and `prestart` runs it too â€” so a runtime orphaned by a
  previous `npm run dev`/`npm start` (which survives on Windows) can no longer
  hold the port and trigger the `WinError 10048` duplicate-spawn path. Tests:
  `python/tests/test_security_audit_counts.py`, added cases in
  `python/tests/test_run_recovery.py`. Verified: `next build` succeeds; full
  Python suite 6311 passed.
  docs updated: `docs/harness/architecture.md`, `docs/DEPLOYMENT.md`.

- **Portfolio header no longer collides with the Funds/Ledger view toggle.** The
  screen-level toggle is absolutely positioned at the top-right
  (`portfolio/index.tsx`), so it was covering the right edge of the fund-manager
  toolbar (hiding the "Create fund" button) and the fund-workspace top bar
  (covering the "Transaction" button). Reserved space in both right-hand control
  groups (`pr-40`) so the toggle floats clear of them.
  no doc change â€” presentation-only fix, no contract/architecture change.

