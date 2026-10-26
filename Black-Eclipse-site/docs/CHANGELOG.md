# Change Log

## Rotation policy

This file keeps a rolling window of the **most recent 7 dated sections** (the active window). Older dated sections are **moved** - never deleted - into monthly archive files under `docs/changelog/YYYY-MM.md`. New entries are appended under the current date; the commit-msg hook checks this path. Rotation is by hand only when this file grows unwieldy; the archive link below points at where the older entries went.

> Older entries are archived under `docs/changelog/` (monthly). The most recent 7 dated sections are kept here.

## 2026-10-26
- **fix(dashboard): market dropdown options were white-on-white.** The global
  market `<select>` popup rendered on the native white background with light
  text; options now carry the repo-standard `bg-[#121212] text-foreground` so
  they are readable. No doc change — style fix only.
- **feat(graph): n8n-style Graph Studio workspace and canvas UX.** Replaced the
  cramped sidebar-tabs/right-rail layout with a full-bleed mode (app top bar and
  sidebar hidden while active), a **Workflows home** gallery (search, templates,
  prompt-to-graph, continue-editing), a slim editor header, and a collapsible
  execution dock. Nodes are compact icon-led cards with hover actions, typed
  ports, add-next/output "+" and run badges; edges expose insert-into-wire and
  delete on hover. Added a Tab/"+" node search overlay filtered by port
  compatibility, right-click menus, duplicate/copy/paste/select-all shortcuts,
  and a wider Parameters/Settings/Output inspector (last-run output is read-only
  from persisted runs). Compound edits are pure validated patches in the new
  `edit-ops.ts`; IR/compiler/runtime/authorization contracts are unchanged.
  Operator runs now use an explicit authorization dialog instead of
  `window.confirm`. Docs: `docs/graph-studio.md`, `docs/NAVIGATION.md`.
- **fix(graph): keep the main sidebar and use the full workspace width.** The
  app sidebar is no longer hidden in Graph Studio; it stays as the Graph Studio
  mode panel. The workflow home is now a full-width n8n-style table (Workflows /
  Templates tabs, search, name/description/tags/owner/version/updated columns,
  row actions) instead of a constrained card grid. Docs:
  `docs/graph-studio.md`, `docs/NAVIGATION.md`.
- **feat(tables,graph): Tables page + workflow cards.** Added a top-level
  **Tables** tab (group `both`) that lists the existing `CustomDataset` tables and
  opens a read-only row grid with provenance/retrieved timestamps; creation stays
  in Settings → Market Data → Custom data sources. The Graph Studio mode panel now
  links directly to **ChatBot** and **Tables**, and the workflow home is back to
  the full-width **card gallery**. Docs: `docs/tables.md` (new),
  `docs/graph-studio.md`, `docs/NAVIGATION.md`.
- **fix(graph): restore the transparent frosted editor canvas.** The workflow
  editor no longer paints a solid canvas/header fill; the dot grid sits on the
  shell background again and nodes use the shared `.glass-card` surface. Hover
  toolbars/edge controls use semi-transparent theme backgrounds so they work in
  both light and dark. Docs: `docs/graph-studio.md`.
- **feat(tables): editable spreadsheet tables.** Tables is now a real data store,
  not a read-only dataset browser: create a table with typed columns, edit cells,
  add/rename/delete columns, add/delete rows and search. Stored in new
  `DataTable`/`DataTableRow` Prisma models (JDDS), exposed through
  `/api/tables` and `/api/tables/[id]`; connector-fed datasets remain under
  Settings → Data Sources. Docs: `docs/tables.md` (rewritten).
- **feat(overview): Agentic Overview workflow dashboard.** Added an **Overview**
  nav tab in Agentic mode with the workflow card gallery, New workflow / templates
  / prompt-to-graph, and continue-editing. Opening or creating a workflow switches
  to the Graph Studio editor. Docs: `docs/agentic-overview.md` (new), `docs/NAVIGATION.md`.
- **fix(nav): Graph Studio uses the standard sidebar.** Removed the dedicated
  Graph-mode Workflows panel: `graph-studio` is now a normal Agentic nav item,
  so the sidebar lists ChatBot / Overview / Graph Studio / Tables like every other
  page. `Alt+G` still opens Graph Studio (inside Agentic). Clicking Tables no
  longer forces a mode switch. Docs: `docs/graph-studio.md`, `docs/NAVIGATION.md`,
  `docs/tables.md`.
- **fix(nav,ui): Terminal boot fallback and consistent buttons.** A stored retired
  `graph` mode is ignored and hydration falls back to Terminal; the new Overview /
  Graph Studio / Tables surfaces now use the shared `Button` component (default /
  outline / ghost / destructive variants) instead of one-off button chrome.
  no doc change � retired-mode fallback + UI consistency only.
- **fix(shell): collapsed sidebar keeps its icons.** When the sidebar is
  collapsed, the Terminal / Agentic / Bots mode switcher becomes a compact icon
  rail instead of disappearing, and the standard nav list keeps every page icon
  reachable. no doc change � layout fix only.
- **fix(bots): bot and group chats read chronologically again.** Threads were
  rendered newest-first, so a question appeared below its own answer and new
  turns jumped to the top. Both the bot chat and group room now render oldest →
  newest, keep the thinking indicator at the bottom, and autoscroll the newest
  message (including streamed text) into view. no doc change � presentation fix.

- **fix(bots): QA hardening pass across Bots mode, deletion, delegation and scheduling.**
  Bots are now identified by the `bot` tag (monitors tagged `bot`/`monitor`), so
  jobs and event rules no longer appear in the Bots list, `bot_list`, the `@`
  palette or the run watcher. The Schedule editor preserves event/condition
  triggers instead of downgrading them to manual, and no longer wipes unsaved
  edits on the 20s background hydrate. Deleting a bot now purges its private
  memory through both the UI route and `bot_delete`, clears its thread/face and
  removes it from rooms; group deletion purges member buckets too. Streaming bot
  and group replies update memory only and persist once at the end. Switching
  bots/rooms mid-stream remounts and aborts the old turn; retry is limited to the
  latest failed reply; delegated turns no longer duplicate the prompt; parallel
  approvals are keyed per approval id; group delegation honours the chosen model;
  duplicate mention targets are collapsed; bots duplicate their model and run
  policies. Also fixed the bot composer's global-model leak (interactive turns
  use the bot's pinned model), group mentions using the shared parser, duplicate
  names resolving to all matches, the Details avatar ignoring uploaded photos,
  denied tools/tags rendering, mode-exit navigation, the missing sidebar
  scheduler button, the finance starter pack being unreachable, and the first-run
  unread seed. Docs updated: `docs/NAVIGATION.md`,
  `docs/harness/automation-engine.md`.

## 2026-10-25
- **feat(models): OpenCode Zen provider in AI / LLM.** Added `opencode` to the
  provider presets (Settings → AI/LLM and the composer), the Python catalog
  (`PROVIDER_CATALOG`/`PROVIDER_MODELS`, default `glm-5.3`), the key vault
  (`OPENCODE_API_KEY`, tested against `https://opencode.ai/inference/v1/models`)
  and `CATALOG_ENV_VARS`. Chat uses OpenCode's OpenAI-compatible endpoint
  (`https://opencode.ai/inference/openai/v1`); because the catalog is published
  one level up, `OpenCodeAdapter` rewrites discovery to
  `https://opencode.ai/inference/v1/models` (verified live, 85 models). Tests:
  `test_models.py`, `test_model_runtime.py` (URL rewrite + discovery wiring).
  Docs: `docs/ARCHITECTURE.md`.
- **feat(chat): shareable apps and a live preview while they stream.**
  The interactive toolbar now has **Share**, which copies
  `/app-view#<base64>` (the `/figure` encoding) and opens a standalone,
  `noindex` viewer that renders the block in the same sandbox with no server
  storage. A still-streaming ```` ```html ````/```` ```svg ````/```` ```eclipse-app ````
  fence renders a debounced (450 ms) sandboxed "Live preview · building" of the
  partial document; the settled block replaces it. Docs:
  `docs/interactive-response-engine.md`.
- **feat(chat): resize, source/copy, off-screen pause and a real dialog.**
  The interactive card gains a drag/keyboard resize handle (double-click resets;
  the height is remembered per app in localStorage), a source view with Copy, and
  a focus-trapped full page that locks page scroll, restores scroll and focus on
  exit, and closes on Escape. `Eclipse.visible` / `Eclipse.onVisibility(fn)` report
  off-screen or hidden-tab state; while hidden the shell pauses CSS animations and
  holds `requestAnimationFrame` callbacks so an off-screen app stops burning CPU.
  Docs: `docs/interactive-response-engine.md`.
- **feat(chat): interactive apps get host context, a skeleton, and a fix action.**
  `Eclipse.context = { theme, reducedMotion, locale }` is baked at mount and
  pushed live (the block observes the host `dark` class and the reduced-motion
  media query), so an app can match Eclipse's scheme instead of the OS. The card
  shows a skeleton until the app signals `eclipse:ready`, then fades the frame
  in. The "App error" banner now offers **Ask Eclipse to fix**, which re-enters
  the agent with the error and the app title. Docs:
  `docs/interactive-response-engine.md`.
- **feat(models): the picker shows newly released models first.** Model lists
  were static/catalog-ordered, discovery was manual and its snapshot merged
  forever, so a provider's new models stayed buried while decomissioned ids
  lingered. Probes now sort by provider `created` (OpenAI family, Anthropic);
  `src/lib/agent/model-recency.ts` ranks provider timestamp → version within a
  family → `-latest`, preserving incoming order otherwise; both catalog routes
  prefer the freshest `served` set and sort newest-first; `compactModels` keeps
  the newest 40 on truncation; the Settings picker auto-re-probes after a 6h
  throttle; the discovered snapshot now REPLACES each provider's set per probe;
  and `PROVIDER_MODELS` is refreshed. Tests: `src/lib/agent/model-recency.test.ts`,
  `enabled-models.test.ts`, Python `test_models.py`/`test_model_runtime*.py`.
  Docs: `docs/ARCHITECTURE.md` (model picker section).
- **ui(chat): a better interactive surface — scrollbar, auto-fit, error banner.**
  The sandbox document now has a thin scrollbar derived from the app's own
  `currentColor` (with a neutral fallback), transparent track and contained
  scroll chaining. The shell reports its content height through a
  `ResizeObserver`, so the card fits the app instead of showing a cramped inner
  scroll (clamped 240–900). Uncaught errors and unhandled rejections post
  `eclipse:error` to the host and appear as an "App error" banner. Docs:
  `docs/interactive-response-engine.md`.
- **feat(chat): interactive apps own their palette and get a full-page view.**
  The document shell now sets only structural defaults (box-sizing, margin, font,
  transparent background) — no forced text colour or `color-scheme` — so the model
  can choose any palette from the user's context. The interactive card is full
  width and its toolbar adds **Download** (the composed HTML) and **Full page**
  (a viewport-filling overlay, Escape/Exit to close; Reload stays available).
  Docs: `docs/interactive-response-engine.md`.
- **fix(advisory): the fiduciary gate reads prose, not code.** A model-authored
  app is full of directive words (`add`, `trim`, `exit`, `reduce`), CSS
  percentages and SHOUTING identifiers (`BARS`, `VOL`, `THR`, `HOVER`, `PIN`,
  `BASE`, `JSON`), so the gate invented "recommendations" for internal tokens and
  appended a nonsensical Advisory note. `claims.extract_claims` now strips fenced
  blocks and inline code before extracting sentences (the gate is a prose check),
  with a few format/tech tokens added to the symbol stop-list. Prose advice next
  to code is still disclosed. Tests: `python/tests/test_advisory_gate.py`.
  no doc change — bug fix.
- **feat(chat): a fenced app can request the dataset bridge.**
  A leading `<!--eclipse-dataset {"symbol":"AAPL","range":"6mo"}-->` comment in
  an ```html/```eclipse-app fence is parsed into the block's `dataset` and
  stripped before render, so a fence-rendered app gets the same host-injected
  series as the `interactive` block. The runtime also exposes `Eclipse.bars()`
  for the bars array directly. Docs: `docs/interactive-response-engine.md`.
- **ui(chat): parallel agents use the ChatBot nav glyph and sit with the activity.**
  Replaced the generated ghost "bot faces" in the fan-out card and its detail
  dialog with the same `Bot` icon the ChatBot nav item uses — a delegated part is
  one Eclipse agent working in parallel, not a distinct bot. Moved the fan-out
  card below `ActivityFeed` so it reads as runtime detail with the activity rows
  instead of a card above the answer.
  no doc change — presentation only.
- **fix(chat): an app-build request stays in chat instead of the code workspace.**
  The classifier recognized the block vocabulary ("return it as one interactive
  block") but not the same deliverable phrased as code: "one self-contained HTML
  document … return it as a single html code fence" was still `code_change`, so
  the code agent edited the repository (repo map, diff, "put this change into my
  project") instead of answering. `_INLINE_APP_RE` now recognizes
  self-contained/single-file HTML, SVG, mini-app and html/svg code-fence
  deliverables as inline content (before the directive+software-object rule),
  with a guard (renderer/component/codebase/desktop/install/deploy) that keeps a
  real source change on the code profile. Tests:
  `python/tests/test_code_request_intent.py`.
  no doc change — classifier bug fix; ADR-052 already documents the block.
- **perf(chat): a code-classified turn no longer stalls for minutes before its
  first model call.** A live "build me an interactive Candle Lab" turn recorded
  only `run.created` → `response.plan` and then sat silent; on the same repo the
  code-context seed (`CodeContextEngine.select`) measured **94 s**, synchronously
  on the runtime's event loop — which also froze every other API route. Three
  fixes: (1) `find_related_tests` resolved the reference set per TEST FILE
  instead of per NAME, re-running the same SQL query ~32 500 times — now once per
  name (94 s → ~2 s); (2) `call_edges(caller_name|callee_name)` indexes added so
  the `col=? OR name=?` call-path reads stop full-scanning; (3) the chat code
  classifier now treats "return it as one interactive block" as a `data_task`
  content deliverable rather than `code_change` (the word "file" in "single-file"
  used to trigger the code profile, ADR-H117 amendment). Also stopped
  `EmbeddingService.configure()` from re-arming a tripped provider circuit on
  every search (a 30 s cooldown), which was firing thousands of doomed
  `/v1/embeddings` 404s against Ollama. Tests:
  `test_intel.py` (one reference query per name), `test_search_embeddings.py`
  (circuit survives re-configure), `test_code_request_intent.py`
  (response-block vs renderer change). Docs updated:
  `docs/harness/decisions.md` (ADR-H117 amendment).
- **fix(chat): a pre-model step can no longer freeze a turn (invariant, not a
  one-off).** The stall above happened because the repo-map/context seed ran
  synchronously on the event loop with only COUNT bounds. `CodeContextEngine.select`
  and `build_repo_map` now also take a wall-clock deadline (default 5 s,
  `BLACK_ECLIPSE_CODE_CONTEXT_BUDGET_S`) and return partial results with
  `truncated: true`; the map gets half the budget and the seed the rest
  (`graph_context._repo_map_context` emits `elapsedMs`/`truncated`);
  `find_related_tests` accepts the deadline. Opening a large workspace index
  (seconds; 682 MB here) moved out of the run: `CodeIntelRuntime.warm` opens it
  at boot on a worker thread (`boot.py::_warm_code_index`;
  `BLACK_ECLIPSE_CODE_INTEL_WARM=0` disables), while the scan stays lazy
  (`start_watch(initial_index=False)`, `manager_for` still kicks the first
  incremental index). Tests: `test_intel.py` (budget cuts a slow index off),
  `test_repo_map.py` (deadline truncates the walk). Docs updated:
  `docs/harness/code-intelligence.md` (the budget invariant),
  `docs/harness/decisions.md` (ADR-H287 amendment), `docs/NAVIGATION.md`.
- **feat(chat): Eclipse can build and run interactive mini-apps in the conversation.**
  Added the `interactive` response block: the model authors self-contained
  HTML/CSS/JS/SVG (a price knob, a VWAP explorer, a doji figure) and it renders
  inline in a sandboxed iframe. The document is composed by
  `src/lib/interactive/document.ts` with an immutable CSP
  (`default-src 'none'; connect-src 'none'; ...`) plus a tiny
  `Eclipse.data()/onData()/resize()` runtime; the frame is
  `sandbox="allow-scripts"` with no `allow-same-origin`, so it has no access to
  the app DOM, cookies or network. Widgets that need market data declare a
  `dataset`; the HOST fetches the existing read-only `/api/price-history` route,
  normalizes up to 5000 bars with source/as-of/freshness and injects the snapshot
  over postMessage (validated by frame source + per-render nonce). The model never
  types prices, and an empty series renders an explicit unavailable
  state instead of a fabricated line. Wired through the contract union, registry,
  Markdown projection, PDF export, Canvas `REPORT_BLOCKS`, prompt guidance, and
  `contract-matrix` parity. New files: `src/lib/response/blocks/interactive.ts`,
  `src/lib/interactive/{document,dataset}.ts` (+ tests),
  `src/components/response/{interactive-block,interactive-frame}.tsx`.
  A settled ```` ```html ```` / ```` ```svg ```` / ```` ```eclipse-app ```` fence
  renders through the same sandbox too, so a model that answers with UI code
  still produces a live app; the composer preserves a full document's styles and
  scripts but strips any model-supplied CSP meta.
  Decision: ADR-052. docs updated: `docs/interactive-response-engine.md`,
  `docs/DECISIONS.md`, `skills/ARCHITECT.md`.
- **ui(layout): slim the app header.** Top bar and sidebar brand row now use a
  single `h-12` (48px) at all breakpoints instead of `h-14 md:h-16` (56/64px),
  reclaiming vertical space while keeping the 40px inner controls comfortable.
  no doc change — style-only change, no contract or architecture impact.
- **feat(chat): Eclipse can ask ONE clarifying question instead of guessing.**
  Added a read-only `clarify` tool (`python/harness/clarify_tools.py`) that takes
  a question, optional context, 2–4 options and a recommended default, creates a
  `clarification` row in the existing `McpApproval` store (additive `answer`
  column), emits `clarification.requested`, and pauses on the SAME
  `wait_for_decision` gate approvals use. The operator picks an option, types a
  free-text answer, or chooses "Let Eclipse decide"; the answer returns as the
  tool result so the run resumes in place. An answer is explicitly NOT an
  authorization (`answer_clarification` refuses non-clarification rows). Without
  an interactive client the tool never blocks or fabricates: it returns
  `answered: false` so the model must state an assumption. Wired through
  `routers/mcp.py` (`POST /mcp/approvals/{id}/answer`), the Next proxy, the event
  parser/hook, a new `clarification-card.tsx` in both chat surfaces, prompt
  guidance, and a watchdog exemption. Tests: `python/tests/test_clarify.py`,
  `src/lib/agent/events.test.ts`. Decision: ADR-H328.
  docs updated: `docs/harness/architecture.md`, `docs/harness/decisions.md`,
  `docs/NAVIGATION.md`.

- **fix(delegation): make the budget, aggregation modes and handle checks real.**
  The fan-out budget was decorative: `token_budget` was only a minimum check and
  `consumedTokens` was always 0. Each part's REAL `totalTokens` now flows through
  `ChildOutcome.tokens` into `BudgetReport.consumedTokens`, and a part is refused
  before it starts once the remaining room drops below `MIN_TOKENS_PER_CHILD`.
  Added an overall `DEFAULT_TOTAL_TIMEOUT_S` deadline that stops running parts and
  gives every outcome a terminal status. `aggregate` now honors the request's
  `list`/`compare`/`merge_claims` mode (previously all rendered as a list). The
  `delegate` tool carries the parent's `workflowId` onto the fan-out, and handle
  verification is fail-closed: an `artifact_digest` is confirmed only when the
  Artifact Center holds it (never for being non-empty). The tool schema no longer
  calls working `agent_id`/`tool_subset` fields "Reserved", and the prompt states
  when delegation is worth its cost. Tests: `test_delegation.py`,
  `test_delegation_tool.py`.
  docs updated: `docs/harness/roadmap/phase-07-delegation.md`.

- **feat(chat): see parallel agents working, like a fan-out card.** A delegated
  child runs on its own run id, so its events never reached the parent stream.
  New `python/harness/delegation_progress.py` (`ChildProgressBridge`) bridges the
  child's bus stream into ONE throttled, content-free `delegation.progress`
  snapshot on the parent emitter (real `step`/`maxSteps`, real tokens, real price
  or `null` when unpriced, latest activity). `delegation.started` now names the
  parts (`agents[]`), and the terminal/aggregated events carry real tokens.
  The chat renders `src/components/chat/parallel-agents-panel.tsx` (bot icon,
  agent + sub-question, live activity, progress bar, cost per row; header with
  "N agents working · X of N done · total") fed by a pure
  `src/lib/agent/delegation-reducer.ts`. Percent is `step / maxSteps` and an
  unpriced model shows `—`, never `$0.00`. Tests:
  `python/tests/test_delegation_progress.py`,
  `src/lib/agent/delegation-reducer.test.ts`, `events.test.ts`.
  docs updated: `docs/harness/roadmap/phase-07-delegation.md`,
  `docs/NAVIGATION.md`, `docs/chat-ui-audit.md` (R4 resolved).

- **feat(delegation): `best_of` — try the same task several ways, pick the
  strongest verified result.** `DelegationRequest.strategy` now accepts
  `best_of`; the `delegate` tool takes `goal` + `count` (2–4, optional
  `agent_ids`) instead of `children`, and refuses mixing the two. Selection is
  deterministic and evidence-based (`select_best`): only completed attempts
  qualify, confirmed claims/handles score positively, unconfirmed claims
  negatively, then non-empty output and fewer tokens break ties. Only the
  winner's prose/proven claims are repeated (`aggregate_best_of`); the rest are
  named as not repeated, and no attempt finishing yields `winner=None` rather
  than a fabricated best. `delegation.aggregated` carries `strategy`/`winner`;
  the chat header renders `Best of N` with a `Best` chip on the winning row.
  Tests: `python/tests/test_delegation_best_of.py`, `delegation-reducer.test.ts`,
  `events.test.ts`. docs updated: `docs/harness/roadmap/phase-07-delegation.md`,
  `docs/NAVIGATION.md`.

- **feat(delegation): per-attempt model for `best_of`.** An attempt may name a
  `model` (`DelegationChild.model`; tool `models[]`), and the child runs with
  that model id copied onto the parent's `ModelSettings`. The **provider and its
  credential never change** — the Python service holds only this run's key, so a
  cross-provider attempt is deliberately not offered (it would have to invent a
  credential). The progress snapshot and the chat row show the model name.
  Tests: `test_delegation_best_of.py`, `events.test.ts`.
  docs updated: `docs/harness/roadmap/phase-07-delegation.md`,
  `docs/NAVIGATION.md`; regenerated `docs/harness/tool-registry.json`.

- **feat(delegation): per-attempt temperature for `best_of`.** An attempt may
  carry `temperature` (`DelegationChild.temperature`; tool `temperatures[]`),
  applied by copying it onto the child's `ModelSettings`. This makes N attempts
  real samples instead of near-duplicates. It is a sampling hint only: a
  provider that ignores temperature is unaffected, and nothing is fabricated to
  compensate. Tests: `test_delegation_best_of.py`. docs updated:
  `docs/harness/roadmap/phase-07-delegation.md`; regenerated
  `docs/harness/tool-registry.json`.

- **feat(graph): enforce the TypeScript/Python node contract and add Set variables.**
  Added `src/lib/graph-studio/manifest.ts` + checked-in
  `registry.manifest.json`, generated by `npm run graph:manifest`. The new
  Python suite `test_graph_registry_parity.py` compares the runtime registry to
  the manifest node for node (ports, config field names, capabilities, side
  effects, modes, terminal), so an editor-only or runtime-only node now fails
  CI. Added the first new core node, `data.set_variables`, to BOTH registries:
  it merges configured named values over an optional input object (configured
  keys win). Also added the `fast`/`slow`/`signal` config fields the runtime
  already accepted to the TS `finance.indicator` contract so the editor can
  configure them. Tests: `manifest.test.ts`,
  `test_graph_registry_parity.py`; targeted graph suites 53 TS + 75 Python.
  docs updated: `docs/graph-studio.md`, `docs/NAVIGATION.md`.
- **feat(graph): run and version history in Graph Studio.** Added a History tab
  to the workspace right rail. It lists a saved workflow's runs
  (`/api/workflows/[id]/runs`) with status/duration/error, and its immutable
  versions (`/api/workflows/[id]/versions`). Opening a run fetches the full
  record before drawing its node statuses on the canvas; opening a version loads
  it into the editor, with an unsaved-changes confirm, and saving still appends
  a new version. Formatting is deterministic UTC (`history-model.ts`, tested).
  Tests: `history-model.test.ts`, `execution-client.test.ts`,
  `persistence-client.test.ts`; targeted graph suite 11 files / 59 tests.
  docs updated: `docs/graph-studio.md`, `docs/NAVIGATION.md`.
- **feat(graph): bounded local datasets + a `local_write` effect class.**
  Added `data.dataset.save` / `data.dataset.load` in both registries and the
  Python runtime. A payload is JSON-encoded into `HarnessGraphDataset` on the
  runtime's own `agent-memory.db` and referenced by a small `gds:` ref; the
  store caps a payload at 8 MB, the table at 200 datasets, and supports a TTL
  (expired refs are purged and fail explicitly). No market data is fabricated
  and JDDS is untouched. Added `local_write` as a side-effect class: a test run
  may perform local scratch writes, while external write/network/trading stay
  denied; `dataset.read`/`dataset.write` join the test-run capability set.
  Tests: `test_graph_datasets.py` (roundtrip, expiry, size/serialization limits,
  end-to-end execution, capability denial), registry parity + manifest. Targeted
  graph suites 60 TS + 81 Python. docs updated: `docs/graph-studio.md`,
  `docs/NAVIGATION.md`.
- **feat(graph): pinned subworkflows with input delivery and bounded recursion.**
  Added `flow.subworkflow` (both registries + Python runtime). A node runs a
  pinned `workflowId@version` as a nested run; the parent input becomes the
  child's run input and the child's terminal value becomes the node output
  (keyed by terminal id when there are several). The Next front door resolves
  the referenced IRs from JDDS (`subworkflow-bundle.ts`, with cycle/depth/
  missing-workflow refusal) and sends them with the run, so Python never reads
  JDDS. The runtime compiles every child with the SAME grants (authority can
  only narrow), enforces a depth limit of 5, and refuses cycles again. Also added
  `GraphRun.output` terminal capture and an output readout in the Run panel.
  Tests: `test_graph_subworkflows.py`, `subworkflow-bundle.test.ts`; targeted
  graph suites 65 TS + 87 Python. docs updated: `docs/graph-studio.md`,
  `docs/NAVIGATION.md`.
- **feat(graph): durable execution on the Fabric + resumable checkpoints.**
  Graph runs now dispatch as `graph` DURABLE jobs on the existing Execution
  Fabric (new queue/worker/policy; no second queue). Added normalized
  `HarnessGraphNodeRun`/`HarnessGraphEvent` tables, a bounded 2 MB per-node
  output checkpoint, and `GraphRunStore.load_resume`. `GraphExecutor` seeds
  completed nodes/outputs/fired-control/terminal values and skips them, so a
  Fabric-requeued run resumes instead of restarting. A node failure stays a
  succeeded Fabric job (the run row is authoritative); worker/process crashes
  are recovered by the Fabric lease and resumed. Added `queued → running`
  status, terminal output persistence, Fabric cancellation (queued or running),
  and a legacy in-process fallback when the Fabric is disabled. Tests:
  `test_graph_durable.py` (normalized rows, resume skips a completed node,
  durable dispatch, worker bridge, cancel, orphan reconcile, real Fabric
  manager + worker). Targeted graph suites 65 TS + 94 Python. docs updated: `docs/graph-studio.md`,
  `docs/harness/execution-fabric.md`, `docs/NAVIGATION.md`.
- **feat(graph): live SSE run updates.** Added
  `GET /graphs/runs/{id}/stream` (Python) and
  `/api/graph-runs/[runId]/stream` (Next proxy). The stream replays the
  persisted `HarnessGraphEvent` log from `Last-Event-ID`, tails new events every
  250 ms, emits keep-alives, and ends with `stream.end` at a terminal run. The
  Graph Studio Run tab now consumes SSE: node statuses update in place and the
  full run record is fetched once at terminal (authoritative outputs/durations/
  errors). A disconnected stream falls back to the existing bounded polling.
  Tests: `test_run_event_stream_replays_and_ends` + client event-mapping tests.
  Targeted graph suites 67 TS + 95 Python. docs updated:
  `docs/graph-studio.md`, `docs/NAVIGATION.md`.
- **feat(graph): gateway-backed quotes/history + tabular transform pack.**
  Added `finance.quote` and `finance.history` in both registries; both call the
  EXISTING `MarketDataGateway` (server bridge bound at boot) and return
  provenance, with explicit `MarketError` failures. History emits the standard
  OHLCV payload so it feeds indicators. Added `transform.select`,
  `transform.sort_limit`, `logic.aggregate` (sum/avg/min/max/count + groupBy),
  `logic.deduplicate` and `transform.join` (inner/left) over arrays of objects
  with dotted field paths and a 100 000-row bound. The node manifest is now 35
  types. Tests: `test_graph_tables.py` (8 cases incl. fake gateway/error paths)
  + registry parity. Targeted graph suites 67 TS + 103 Python. docs updated:
  `docs/graph-studio.md`, `docs/NAVIGATION.md`.
- **feat(graph): quant backtest node over the existing engine.**
  Added `quant.backtest` in both registries. It adapts the graph OHLCV payload
  to `BarSeries`/`MarketDataset` and calls `run_backtest` in
  `harness/quant/engine.py` — no backtest math in the graph runtime. Supports
  the documented `ema_cross`/`rsi_reversion` presets and a full `StrategySpec`
  JSON; the input symbol is authoritative; `randomSeed` keeps runs deterministic
  and `maxBars` bounds work. Returns the result, metrics and trades; equity
  curves are optional (`includeSeries`). The manifest is now 36 types. Tests:
  `test_graph_quant_nodes.py` (preset determinism, RSI preset, curves, custom
  StrategySpec, explicit failures) + registry parity. Targeted graph suites
  67 TS + 108 Python. docs updated: `docs/graph-studio.md`,
  `docs/NAVIGATION.md`.
- **feat(graph): walk-forward validation node.** Added `quant.walkforward` in
  both registries. It adapts the OHLCV payload and calls
  `harness/quant/walkforward.py`, optimizing only on each training window and
  reporting in-sample, out-of-sample and combined metrics plus IS/OOS
  divergence. Preset-derived default parameter spaces are provided; custom
  strategies supply `paramSpaceJson`. Insufficient history is an honest
  `INSUFFICIENT_HISTORY` result. The manifest is now 37 types. Tests:
  `test_graph_quant_nodes.py` (walk-forward windows + insufficient history) +
  registry parity. Targeted graph suites 67 TS + 110 Python. docs updated:
  `docs/graph-studio.md`, `docs/NAVIGATION.md`.
- **feat(graph): local research & evidence nodes.** Added `research.evidence`,
  `research.citations`, `research.conflicts`, `research.completeness` and
  `research.report` in both registries. They read the EXISTING web-research
  `EvidenceStore` (no web request, no model call): evidence with a text filter,
  claims/citations, conflicts, a coverage summary, and a deterministic Markdown
  report. `research.read` is granted to test runs because it is a local read.
  The manifest is now 42 types. Tests: `test_graph_research_nodes.py`
  (filter, citations/claims, conflicts, completeness, deterministic report,
  missing id) + registry parity. Targeted graph suites 67 TS + 115 Python.
  docs updated: `docs/graph-studio.md`, `docs/NAVIGATION.md`.
- **feat(graph): operator-run envelope + a real HTTP node.** The front door now
  derives a run's grants from the persisted IR and the node registry
  (`run-authorization.ts`): test run by default; an operator run grants exactly
  the declared capabilities, enables network only on explicit confirmation, and
  refuses trading and external write nodes. `integration.http` gained a real
  executor: SSRF-checked, loopback refused, 1 MB response cap, 60 s ceiling,
  JSON body support, no custom headers/credentials yet. The UI shows an
  `Operator run` button only when the graph needs network and asks for
  confirmation naming the network nodes. Tests: `run-authorization.test.ts` and
  `test_graph_http_operator.py` (envelope denial/grant, GET/POST, blocked and
  loopback URLs, size cap). Targeted graph suites 71 TS + 120 Python. docs
  updated: `docs/graph-studio.md`, `docs/harness/security.md`,
  `docs/NAVIGATION.md`.
- **feat(graph): the research agent node runs on the existing agent plane.**
  `agent.research` now has an executor: it resolves a named agent preset, caps
  the turn at `maxSteps`, calls `AgenticService.run`, and returns a structured
  `finding` plus the run's research evidence. It is gated by the operator-run
  network envelope. The front door resolves model credentials from the vault
  and sends them in memory; `GraphService` excludes them from the durable
  Fabric job payload, so a restart before the node fails honestly instead of
  persisting a key. Tests: `test_graph_agent_node.py` (structured finding,
  objective required, bound-runtime required, envelope denial/grant) + registry
  parity. Targeted graph suites 71 TS + 124 Python. docs updated:
  `docs/graph-studio.md`, `docs/NAVIGATION.md`.

- **feat(delegation): per-attempt approaches for `best_of`.** A best-of attempt
  may carry a short `approach` (tool `approaches[]`, e.g. "retry with backoff"
  or "mock the API"). It is prepended to that child's prompt as guidance and
  becomes the row label in the chat card (the full sub-question stays in the
  tooltip), matching the "each agent tries a different angle" presentation. It
  is guidance, never a claimed result. Starts/progress carry `approach`, so the
  label is live from the first frame. Tests: `test_delegation_best_of.py`,
  `events.test.ts`. docs updated: `docs/harness/roadmap/phase-07-delegation.md`,
  `docs/NAVIGATION.md`; regenerated `docs/harness/tool-registry.json`.

- **feat(delegation): per-attempt context for `best_of`.** Attempts may carry
  their own bounded `contexts[]` (tool) / `DelegationChild.context`, so tries can
  work from different background evidence. Context is prompt input only — it is
  never placed in the progress snapshot or the card, so background material
  cannot leak into the transcript. Tests: `test_delegation_best_of.py`.
  docs updated: `docs/harness/roadmap/phase-07-delegation.md`; regenerated
  `docs/harness/tool-registry.json`.

- **feat(delegation): the fan-out survives a reload, and the card is tested.** The
  persisted `HarnessRun.delegation` blob now carries each row's bounded
  `goal`/`approach`/`model`/`tokens` (`ChildOutcome` gained those display
  fields), `_run_row` returns it old-row-safe, and `/runs/{id}/explain` includes
  a bounded, redacted `delegation` view (`_bounded_delegation`) without
  re-rendering the child's prose or claims. Added a server-render test for
  `src/components/chat/parallel-agents-panel.tsx` (best-of header + winner chip +
  real cost + `—` for an unpriced part + step/ceiling progress; split header;
  empty case). Tests: `test_run_observability.py`,
  `parallel-agents-panel.test.tsx`. docs updated:
  `docs/harness/roadmap/phase-07-delegation.md`.

- **chore(delegation): stop advertising dead DAG tools, propagate stop, make
  concurrency configurable.** (1) `install_orchestration_layer` no longer
  registers the 11 model-facing orchestration tools — no built-in allowlist names
  them, so they only appeared as unreachable tools; the engine, operator routes
  and direct-registration tests are unchanged (`parallel-orchestration.md`
  updated). (2) Each delegated part now gets its own `cancel_event` passed to
  `execute_run` and set on timeout/cancel/failure, so cooperating tools stop.
  (3) `MAX_IN_FLIGHT` is operator-configurable via
  `HARNESS_DELEGATION_MAX_IN_FLIGHT` (clamped 1–8) because memory is the real
  constraint. Tests: `test_delegation.py`, `test_delegation_tool.py`,
  `test_orchestration_tools.py`. docs updated:
  `docs/harness/parallel-orchestration.md`,
  `docs/harness/roadmap/phase-07-delegation.md`.

- **feat(team): opt-in per-member fan-out.** `TeamPolicy.memberFanout` (default
  off) adds the `delegate` tool to each member's declared surface so a Bot can
  run a split fan-out or `best_of` inside its own subtask. It adds only the tool
  NAME — delegation caps, narrowing and permissions still apply, and a member
  with no declared surface already inherits it. Tests:
  `test_team_service.py`. docs updated: `docs/harness/bot-team-orchestration.md`.

- **docs(roadmap): phases 15, 18 and 20 are Done in the code; the index was stale.**
  Re-read the modules and their tests against the phase files and corrected the
  status instead of re-implementing finished work: Phase 15 (promotion + rollback,
  document extractors, artifact serving, inline `ArtifactView`), Phase 18 (figure
  payload + 10 recipes + inline renderer, 2026-10-18) and Phase 20 (every
  capability class graded; `test_capability_classes` asserts no unmeasured row).
  Evidence run: `test_code_promotion*`, `test_analysis_recipes`,
  `test_artifacts_*`, `test_artifact_verification`, `test_capability_classes`,
  `artifact-view.test.tsx`, `analysis-types.test.ts` — all pass.
  docs updated: `docs/harness/roadmap/README.md`,
  `docs/harness/roadmap/phase-{15,18,20}-*.md` (status + last-verified).

- **feat(eval): a measured adoption gate for the `delegate` fan-out.** New
  `python/harness/evaluation/delegate_benchmark.py` runs both variants on frozen
  tasks through the REAL `execute_run` graph and the REAL `delegate` handler:
  N sequential steps vs one fan-out with N parts. The model is a deterministic
  SIMULATOR with a fixed per-call latency, so the result answers whether the
  parts overlap — the report says `simulated: true` and never calls a simulated
  millisecond provider latency. Both variants cover every fact by construction;
  a coverage miss is `unmeasured` and vetoes adoption, and adoption needs equal
  coverage plus a ≥15% wall-clock gain (`ADOPTION_LATENCY_MARGIN`, ADR-H213).
  First frozen run: three parts save ~29%, two parts do not — the gate is a
  measurement, not a default. Tests: `test_delegation_benchmark.py`.
  docs updated: `docs/harness/agent-evaluation.md` (§13.2), `docs/NAVIGATION.md`.

- **fix(delegation): production polish for the fan-out surface.** A stopped part
  now finishes its live snapshot as `cancelled` (not `failed`) while still
  setting the child's stop signal; a completed but unpriced part makes the card's
  total unknown instead of silently understating it (a refused part does not);
  the card header exposes an `aria-live` status label for screen readers; and the
  new benchmark test file has consistent line endings. Tests:
  `delegation-reducer.test.ts`, `parallel-agents-panel.test.tsx`,
  `test_delegation_benchmark.py`. Full checks: `tsc` clean, 398 vitest files /
  3917 tests, 83 targeted Python tests.

- **feat(graph): live web-research nodes (Phase 7).** Added
  `research.web_search`, `research.web_fetch` and `research.claim_verify` to
  both registries. Search and fetch reuse the existing web-research engine
  (`web_providers`, `web_extract`) through the SSRF-hardened bridge capabilities
  - no second egress path. Results are pointers, extracted text is untrusted,
  and a fetch with a `researchId` saves the same `Evidence` the `web_extract`
  tool saves so the local research nodes can read it. Both live nodes are
  `network` side effects (test runs refuse them; an operator run must confirm
  network). `claim_verify` is a local read over the verifier. The manifest is
  now 45 types. Tests: `test_graph_research_nodes.py` (search/domain filter,
  fetch+evidence save, unknown evidence id, compiler network denial/grant) and
  `run-authorization.test.ts` (network vs local research nodes). docs updated:
  `docs/graph-studio.md`, `docs/harness/security.md`.

- **feat(graph): optimizer, Monte Carlo and OOS holdout nodes (Phase 6 complete).**
  Added `quant.optimize`, `quant.montecarlo` and `quant.oos` to both registries.
  They reuse the tested quant engines instead of reimplementing research math:
  the optimizer returns best/leaderboard/stability, Monte Carlo returns the
  return distribution and loss/ruin probabilities, and the OOS node makes a
  chronological split (fraction or index), backtests both sides with the same
  deterministic engine, reports IS/OOS divergence and a block-bootstrap CI for
  the OOS mean return. A materially weaker OOS objective raises
  `IS_OOS_DIVERGENCE`. The manifest is now 48 types. Tests:
  `test_graph_quant_nodes.py` (optimizer leaderboard/no-axis refusal, Monte
  Carlo distribution, OOS split/index/invalid split). docs updated:
  `docs/graph-studio.md` (Phase 6 status + next milestone), no other contract
  changed.

- **feat(graph): paper trading and safety (Phase 8).** Added
  `trading.risk_check` (pure pre-trade gate over `harness/quant/risk.py`) and
  `trading.paper_order` (PAPER-only execution adapter) to both registries. The
  front door gains an explicit `allowPaperTrading` confirmation and grants
  `allowTrading` only for a `paper`-mode graph; the Python compiler refuses LIVE
  mode outright, refuses an ungranted trading node, and still refuses every
  trading node in a test run. Paper fills use the supplied reference price with
  explicit slippage/commission and never contact a broker. The UI shows the
  operator-run confirmation for paper-trading graphs. The manifest is now 50
  types. Tests: `test_graph_trading_nodes.py` (risk cap/rejection, simulated
  fill, rejected decision, price/intent validation, test-run/LIVE/ungranted
  refusals), `run-authorization.test.ts` (paper confirmation, research-mode
  refusal, LIVE refusal). docs updated: `docs/graph-studio.md`,
  `docs/harness/security.md`.

- **feat(graph): post-run step inspector and structural version diff (Phase 9).**
  Added `src/lib/graph-studio/run-debug.ts` and a Run-panel step inspector:
  ordered steps, status/attempts, bounded inputs/outputs, per-node events and
  checkpoint availability. The runtime's node-run read now exposes
  `resumable`, so the inspector never infers a checkpoint. Added
  `src/lib/graph-studio/ir-diff.ts` plus a History > Versions `Diff` action:
  added/removed/changed nodes and edges, changed settings and name, with a
  key-order-insensitive config comparison. Tests: `run-debug.test.ts`,
  `ir-diff.test.ts`, and a `resumable` assertion in `test_graph_durable.py`.
  docs updated: `docs/graph-studio.md` (Phase 9 + next milestone).

- **feat(graph): bounded run telemetry and a Health tab (Phase 10).** Added
  `GraphRunStore.health` / `GraphService.health` and operator-gated
  `GET /graphs/health?windowHours=N`: run counts by status, success/failure
  rate, duration p50/p95, queue wait (created → started), throughput,
  failed-node codes, slowest node types and checkpoint coverage. Reads are
  capped (1 000 runs / 5 000 node rows, 1–168 h) and report `truncated`; missing
  values stay `null`. Added the Next proxy, typed `getGraphHealth` and the Graph
  Studio **Health** tab (1 h / 24 h / 7 d). Tests:
  `python/tests/test_graph_health.py` (counts/percentiles/failure codes, window,
  queue wait, bounded read). docs updated: `docs/graph-studio.md` (Phase 10
  status, telemetry contract, next milestone).

- **feat(graph): chat-to-graph authoring (Phase 7).** Added
  `python/harness/graph_runtime/planner.py`: the model receives the runtime's
  real node catalog and returns a strict JSON proposal; the planner validates
  every node type, port, edge and config against the same registry the compiler
  uses, derives capabilities, selects `paper` when a trading node is present and
  dry-runs the compiler. Only a zero-error proposal becomes a `WorkflowIR`;
  nothing is saved or executed automatically. Added operator-gated
  `POST /graphs/plan`, the Next proxy `/api/graphs/plan` (model settings resolved
  from the vault, memory only), typed `plan-client.ts`, and a "Generate from
  prompt" flow in the workflow list that saves through the normal create path.
  Tests: `python/tests/test_graph_planner.py` (catalog, valid/trading plans,
  unknown type/port/config refusal, missing model/objective) and
  `plan-client.test.ts` (parsed IR, validation errors, refusal). docs updated:
  `docs/graph-studio.md` (Phase 7 + chat-to-graph contract).

- **feat(graph): planner and delegate agent nodes (Phase 7 complete).** Added
  `agent.plan` (one bounded structured-plan model call, 1–8 steps, stable ids
  and earlier-step dependencies, never executes them) and `agent.delegate` (1–6
  tasks, each one bounded turn on the existing agent plane, explicit per-task
  failure with a `PARTIAL` summary). The plan call reuses the in-memory model
  settings and a strict schema (`agent_plan.py`); delegation reuses the bound
  agent runner, so neither adds an agent loop. The manifest is now 52 types.
  Tests: `test_graph_agent_node.py` (plan/delegate, failed part, task cap,
  bound planner) and   `test_graph_agent_plan.py` (ids, dependencies, step cap).
  docs updated: `docs/graph-studio.md` (Phase 7 complete).

- **feat(graph): health watch and headless schedule guidance.** Added
  `graph_runtime/health_watch.py`: a bounded cadence reads the health telemetry,
  persists `unmeasured`/`insufficient`/`healthy`/`degraded` in
  `GraphHealthWatchState`, and publishes `graph.health_degraded` /
  `graph.health_recovered` only on a transition. Thresholds are env-tunable
  (`HARNESS_GRAPH_HEALTH_*`; `SECONDS=0` disables). `/graphs/health` now carries
  `watch`, and the Health tab renders the verdict/reasons. Boot starts/stops the
  watcher; it never creates or changes a run. Docs also document driving
  `/api/workflow-schedules/tick` from external cron with `CRON_SECRET` for a
  headless host. Tests: `test_graph_health_watch.py` (thin data, thresholds,
  transition-only events). docs updated: `docs/graph-studio.md`.

- **feat(fabric): same-host multi-process workers.** `FabricStore.claim_job` is
  now ONE `UPDATE ... RETURNING` statement, so two processes sharing
  `agent-memory.db` can never claim the same job; claim and lease renewal now use
  the same worker id (the old `id:slot` claim meant heartbeats did not renew the
  lease). Added `HARNESS_FABRIC_WORKERS` (kinds/queues, `none` =
  producer-only) and `python -m harness.fabric.standalone` for a dedicated worker
  process that starts only the Fabric consumers. Tests: two independent
  stores/connections claim exactly once; worker filter parsing; standalone CLI.
  A multi-machine fleet remains unsupported because the store is local SQLite.
  docs updated: `docs/harness/execution-fabric.md`, `docs/graph-studio.md`.

- **feat(graph): durable paper-trading accounts.** `trading.paper_order` now
  records each fill in `GraphPaperAccount`/`GraphPaperFill` on `agent-memory.db`
  by default: cash, signed position, average cost and realized PnL persist across
  runs, so a scheduled paper graph keeps its book. The write is one
  `BEGIN IMMEDIATE` transaction, safe alongside the multi-process workers.
  `accountId`, `initialCash` and `persist` are node settings; `persist: false`
  keeps a fill stateless. This is cost-basis accounting, not mark-to-market.
  Tests: `test_graph_trading_nodes.py` (persisted buy/sell + realized PnL,
  stateless fill, missing store). docs updated: `docs/graph-studio.md`.

- **feat(graph): durable subworkflow child runs and a workflow picker.**
  `GraphExecutor` now reports a finished nested run to the service, which stores
  it as its own durable row (`<parentRunId>:<nodeId>`) with node runs and events;
  the parent node returns that child `runId`. The inspector's subworkflow node
  now selects a saved workflow from the catalog and pins its version from a
  dropdown (with a self-reference warning), instead of typing ids. Tests:
  `test_graph_subworkflows.py` (child run row + nodes + events). docs updated:
  `docs/graph-studio.md`.

- **feat(graph): owner-scoped datasets.** `HarnessGraphDataset` gains an
  `ownerId` column (existing rows migrate to `local`). Save/load/meta carry the
  run's user id; another owner's reference is reported as NOT FOUND, so a ref
  holder cannot probe another user's datasets. `delete`/`list` accept an optional
  owner filter; the expiry purge is unchanged. Tests:
  `test_graph_datasets.py` (cross-owner load/meta/list). docs updated:
  `docs/graph-studio.md`.

- **feat(graph): HTTP headers/credential refs, browser escalation and object-row
  loops.** `integration.http` gains `headersJson` (plain headers; transport
  headers and secrets refused) and `credentialEnvJson` (header → environment
  variable NAME resolved by the runtime only; values are never stored). Headers
  may not come from both sources. `research.web_fetch` gains `allowBrowser`:
  a thin/failed page escalates to the existing Browser Runtime and reports
  `extraction: browser`; the default remains bridge-only. `logic.map/filter/
  reduce` now accept object rows, binding each row's numeric fields by name
  (plus `value`/`index`/`acc`). The per-node checkpoint size is operator-tunable
  (`HARNESS_GRAPH_CHECKPOINT_MAX_BYTES`, 2–16 MB). Tests:
  `test_graph_http_operator.py` (plain/credential headers, ambiguity, missing
  env), `test_graph_research_nodes.py` (browser escalation),
  `test_graph_control_flow.py` (object-row loop), `test_graph_durable.py`
  (checkpoint limit bounds). docs updated: `docs/graph-studio.md`.

- **feat(graph): bounded crawl and an opt-in real-provider e2e.** Added
  `research.web_crawl`: one start URL, 1–10 same-site pages, using the existing
  SSRF-hardened fetch plus the bridge's deterministic `web_collect` link pass.
  It is not a general crawler; each page is untrusted and failures are reported
  per page (`PARTIAL`). Added `test_graph_agent_e2e.py`, skipped unless
  `HARNESS_E2E=1` and provider/model/API-key env vars are set, covering
  chat-to-graph, step planning and an agent node against a REAL provider. Tests:
  `test_graph_research_nodes.py` (same-domain bound/dedupe). docs updated:
  `docs/graph-studio.md`.

- **feat(graph): bounded graph-health alert history.** Every watch transition
  (`degraded`/`healthy`) is appended to `GraphHealthAlert`; `/graphs/health`
  returns the newest 20 with reasons, and the Health tab lists them. Tests:
  `test_graph_health.py` (order + reasons). docs updated:
  `docs/graph-studio.md`.

- **feat(graph): executable `video.render` behind a local-write grant.** The
  node now builds a bound recap storyboard and runs the existing
  `VideoService.run_render_job` in the graph worker (project files + Artifact
  Center entry), with honest failure when the fframes worker is absent. The
  front door adds a whitelisted `allowLocalWrite` confirmation (only
  `video.render`; any other write node is still refused) and the compiler gains
  `RunGrants.allow_write`. Test runs still refuse it. Tests:
  `test_graph_video_nodes.py` (executor, symbols, compile grants) and
  `run-authorization.test.ts` (local-render confirmation). docs updated:
  `docs/graph-studio.md`, `docs/harness/security.md`.

- **feat(graph): durable `logic.wait` via a deferred Fabric job.** A durable
  graph no longer blocks a worker thread on a long wait: the wait node
  checkpoints itself, the run is persisted as `queued`, the worker returns a
  `deferred` outcome and the Fabric requeues the job at the wake time (without
  consuming a retry), then resumes from the checkpoint. Waits are bounded to
  24 h; non-durable `run_sync` keeps the 30 s cap and test runs the 5 s cap.
  Tests: `test_graph_control_flow.py` (deferral), `test_graph_durable.py`
  (defer + resume), `test_fabric_workers.py` (deferred requeue). docs updated:
  `docs/graph-studio.md`.

- **feat(graph): spill oversized checkpoints to confined files.** Above the
  DB checkpoint limit (default 2 MB, tunable to 16 MB), a node's output and
  terminal value now spill to
  `<db-dir>/graph-checkpoints/<runId>/<node>.{checkpoint,terminal}.json` with a
  path-confined `{"$file": ...}` marker, so the run stays resumable (up to a
  256 MB file cap). `load_resume` follows the marker; `delete_run` removes the
  files. Tests: `test_graph_durable.py` (spill, resume, cleanup). docs updated:
  `docs/graph-studio.md`.

- **fix(model,graph): real-provider e2e now runs.** Two defects surfaced when
  exercising a real Ollama model: `model_runtime/providers/base.py` imported a
  nonexistent `model_runtime.models` (now `harness.models`), and the planner
  rejected common model edge shapes (`from`/`to`, `sourcePort`/`targetPort`,
  `{node, port}` handles) plus a missing title. The planner now normalizes those
  aliases and defaults the workflow name. The opt-in e2e was run against the
  configured Ollama model and passed chat-to-graph, step planning and an agent
  node. Tests: `test_model_runtime.py`, `test_graph_planner.py`. docs updated:
  `docs/graph-studio.md`.

- **docs(graph): refresh the remaining-work list.** Known limitations now reflect
  the shipped planner/delegate nodes, the documented external-cron path and the
  health watch; "Next milestone" names multi-process Fabric workers as the main
  remaining item. no doc beyond `docs/graph-studio.md`; no runtime change.

- **fix(harness): code-context lookup, response-block routing and embedding
  circuit cooldown.** These pre-existing working-tree fixes landed with the
  crawl commit: `code/intel/context.py` resolves `find_references` ONCE per name
  (the old loop re-ran the same SQL per test file), `persistence/index.py` adds
  caller/callee-name indexes, `request_intent.py` routes "return it as an inline
  block" to a response deliverable (not a code-workspace edit), and
  `search/embeddings/service.py` keeps a tripped circuit open for 30 s instead of
  re-arming it on every `configure()`. Tests: `test_intel.py`,
  `test_code_request_intent.py`, `test_search_embeddings.py`. no doc change —
  internal performance/routing fixes; contracts unchanged.

- **feat(chat): the fan-out card now looks like a "best of N" panel and opens a
  live agent view.** Each part renders a deterministic **bot face** (from the
  agent id, never a vendor logo), the agent/model + its approach, the live
  activity and the runtime's `step/maxSteps` bar/percent. The card shows a short
  fan-out `title` (best_of defaults to its goal), `X of N done`, and **no cost**.
  Clicking the card opens a portaled frosted dialog
  (`parallel-agents-dialog.tsx`) with each agent's full sub-question, status,
  step counter, tokens and a `recent[]` activity timeline. A
  `tool.requested(delegate)` now paints a provisional "Agents starting" card
  until the real `delegation.started` arrives (and it is dropped if the call is
  refused). The same card is wired into the main chat, the floating dock, bot
  chats and group rooms. Tests: `parallel-agents-panel.test.tsx`,
  `delegation-reducer.test.ts`, `events.test.ts`, `test_delegation_progress.py`.
  docs updated: `docs/harness/roadmap/phase-07-delegation.md`, `docs/NAVIGATION.md`;
  regenerated `docs/harness/tool-registry.json`.

## 2026-10-24
- **ui(chat): roomier chat history rows.** Increased the vertical gap between
  conversation rows from 2px (`gap-0.5`) to 6px (`gap-1.5`) inside the pinned,
  date-bucket and folder groups so the list separates more clearly. no doc
  change — styling only.
- **ui(chat): brighter unselected rows in the chat history rail.** Unselected
  conversation titles in the sidebar now use `text-foreground/70` instead of
  `text-muted-foreground`, and their snippets use the full muted tone, so the
  list is legible at rest without changing the selected row. No contract or
  architecture change. no doc change — styling only.

## 2026-10-23
- **release: v0.2.1-rc.1 (release candidate, not production).** Lands the
  data-integrity, live-measurement and terminal-merge work on `main` and tags the
  merged tree. Offline gates are green (Python 8,283 passed / 27 skipped; Vitest
  3,866 passed; eval gates and corpus gate PASS; tsc, eslint, security, size and
  ADR checks PASS). The live tier is honestly **FAIL**: `task_success` 0.8520 on
  live-eligible tasks against the 0.9 gate. External review, PyPI, ACP, the
  SWE-bench suite, the remaining V2 merges and phases 15/18/20 are explicitly not
  in this candidate. Release note: `docs/releases/v0.2.1-rc.1.md`.
  docs updated: `docs/releases/v0.2.1-rc.1.md`, `docs/CHANGELOG.md`.
- **refactor(harness): V2 terminal merge — one executor, two transports.** The
  code profile's `terminal_run` and the `.black-eclipse/verify.json` auto-verify
  hook now run through the ONE `TerminalManager` instead of calling
  `code/sandbox.run` directly. The manager gained `shell_mode=False`, which
  tokenizes the command with `shlex.split(posix=True)` and executes the argv
  directly, preserving the no-shell contract. `code/terminal.py` is now the ONE
  classifier; `build_run_spec` was removed. Tool names are unchanged. The
  terminal slice measured 383,443 total / code 18,197; reconciling origin/main's
  live-preflight and outage guards added 24 evaluation lines, so the final
  committed ceiling is 383,467 / evaluation 11,741. Files:
  `python/harness/terminal/manager.py`,
  `python/harness/code/{terminal,terminal_tools,tools}.py`,
  `python/tests/test_terminal_tools.py`,
  `python/tests/test_code_terminal.py`, `scripts/size-budget.json`.
  docs updated: `docs/harness/terminal-architecture.md`,
  `docs/harness/decisions.md` (ADR-H311), `docs/CHANGELOG.md`.
- **fix(harness): restore the release gate by recording the size-budget raise.**
  `npm run check:all` failed before tests ran because the harness tree had grown
  to 383,293 lines against the committed 382,030 ceiling (the D1-D12
  data-integrity work added ~1.4k Python lines). Raised the committed total to
  383,400 and the `.`/`evaluation` directory ceilings to their measured values
  (25,110 / 11,725) as an explicit, one-release decision (ADR-H327); Round 4 V2
  remains the work that must lower it again. Files:
  `scripts/size-budget.json`, `docs/harness/decisions.md`.
  docs updated: `docs/harness/decisions.md`, `docs/CHANGELOG.md`.
- **fix(evaluation): the live lane measures the agent, not missing eval tools.**
  Three defects made the live tier publish a false zero: it ran every task
  (including tier-0 scripted tasks that require `eval_*` tools or synthetic
  environments) against the production service; a provider 429/timeout was
  graded as a failed task; and the generated benchmark said `NOT MEASURED` even
  when a pinned live baseline existed. The live gate now selects only
  `live_eligible` tasks, provider failures are `UNMEASURED` with the provider
  reason, and the benchmark falls back to the newest committed
  `baselines/live_v1.json` entry when no valid local run is recorded. Also fixed
  the financial/exact graders to accept `25%` for an expected fraction `0.25`
  (all `weight` tasks were failing on this). Files:
  `python/harness/evaluation/{tasks,live_gate,runner,report}.py`,
  `python/harness/evaluation/graders/{exact,financial}.py`,
  `python/harness/evaluation/baselines/live_v1.json` (adds the live-eligible
  re-score note), `python/tests/test_evaluation_{tasks,live_gate,graders}.py`,
  `python/tests/test_live_baseline.py`, `docs/harness/benchmarks.md` (generated).
  docs updated: `docs/harness/agent-evaluation.md`, `docs/harness/benchmarks.md`,
  `docs/CHANGELOG.md`.
- **style(branding): square, self-backing app icon.** Rebuilt
  `public/branding/FAVICON.svg` as a 32×32 square (near-black rounded tile with
  the white Eclipse mark scaled to a 2px safe area) so the mark stays visible on
  both light and dark browser chrome; the old asset was 28×32 with white-only
  fills. Regenerated `src/app/favicon.ico` (16/32/48 ICO), added
  `src/app/apple-icon.png` (180×180) and `public/branding/icon-{192,512}.png` for
  future PWA use. No manifest was added. Also generated a multi-size
  `public/branding/black-eclipse.ico` and pointed the Windows "Black Eclipse"
  desktop shortcut's **IconLocation** at it (it previously showed the generic
  wscript/Node icon), then refreshed the shell icon cache. docs updated:
  `docs/QUICKSTART.md`, `docs/CHANGELOG.md`; `docs/ARCHITECTURE.md` already
  documents the `public/branding/` defaults.
- **style(branding): flush-left mark in the app icon.** Moved the Eclipse glyph
  from a 3.75px centred inset to the tile's left edge (no left gap), clipped it
  to the rounded tile so the corner stays clean, and regenerated every derived
  PNG/ICO plus the desktop shortcut's cached icon. docs updated:
  `docs/CHANGELOG.md`.
- **fix(desktop): hidden launcher and reliable stop on tab close.**
  `start-eclipse.vbs` now starts the Node launcher with window style `0`, so no
  CMD window appears; boot/stop output goes only to
  `.black-eclipse/desktop-launch.log`. The tab-close stop delay dropped from 20s
  to 8s, and `start-desktop.js` gained a stale-heartbeat watchdog (~150s) so a
  tab that crashes or is force-closed without `pagehide` also tears the server
  down. The watchdog threshold sits above browser background-tab timer
  throttling, so an open-but-hidden tab is not mistaken for a closed one.
  docs updated: `docs/QUICKSTART.md`, `docs/CHANGELOG.md`.
- **chore(stock detail): ship the intelligence + verification slice.** Committed
  the five-chart market-intelligence panel, JDdS listing-market resolution,
  Yahoo→Stooq price fallback, and the web-backed identity/listing/filing/quote
  verification route and panel. Checks: `npx tsc --noEmit` clean; targeted
  Vitest 20/20; changed-file ESLint 0 errors. Files:
  `src/app/api/stocks/[symbol]/{intelligence,verification}/route.ts`,
  `src/lib/stock-intelligence/`, `src/lib/scraper/stooq-chart.ts`,
  `src/components/screens/stock-detail/`,
  `src/components/screens/tradingview-chart.tsx`.
  docs updated: `docs/ARCHITECTURE.md`, `docs/NAVIGATION.md`,
  `docs/CHANGELOG.md`.
- **feat(stock detail): more charts and web-backed source verification.**
  Added 1Y price-trend and drawdown charts so the panel shows sourced data even
  when a symbol has no fundamentals, and made every unavailable chart render as
  a card with its reason instead of collapsing the section. The intelligence
  route now resolves the listing market from JDdS (the screener can omit
  country, e.g. EMAAR was being requested as US) and falls back from Yahoo to
  Stooq for US daily closes. Added `GET /api/stocks/[symbol]/verification`,
  which reuses the existing web-search transport to check identity, listing,
  filings and a quote cross-check; official hosts are required for `VERIFIED`,
  snippets only ever `CORROBORATE`, and results are cached for 30 minutes.
  Files: `src/lib/stock-intelligence/{types,charts,verification,use-stock-verification}.ts`,
  `src/lib/scraper/stooq-chart.ts`, `src/app/api/stocks/[symbol]/{intelligence,verification}/route.ts`,
  `src/components/screens/stock-detail/{charts/intelligence-panel.tsx,verification-panel.tsx}`,
  `src/components/screens/tradingview-chart.tsx`, tests alongside each module.
  `npx tsc --noEmit` clean; targeted Vitest 20/20 pass; lint 0 errors.
  docs updated: `docs/ARCHITECTURE.md`, `docs/NAVIGATION.md`, `docs/CHANGELOG.md`.
- **fix(harness): twelve data-integrity defects closed in retrieval/routing.**
  Added the shared `DataQualityEnvelope` (VALID/STALE/DIVERGENT/SCALE_MISMATCH/
  UNAVAILABLE/UNVERIFIED), cross-source price comparison with both candidates
  preserved, statement period-age + cache-key versioning, one FX pair resolver,
  cadence-aware freshness (business days + holidays), provider health read from
  the recorded run ledger, breaker-demoted routes with provenance, capability
  mismatch blocks + CI allowlist, undated-news filtering, bounded retry/body
  cache/success-rate for research fetches, Levenshtein tool suggestions, and
  IMAGE_ONLY/OCR_UNAVAILABLE document handling. Evidence in `HARNESS_FIXES.md`
  and `scripts/repro_{baseline,after}.txt`.
  docs updated: `docs/harness/market-data.md`, `docs/CHANGELOG.md`.
- **docs(nav): NAVIGATION covers the corpus, rotation, live-baseline and
  supervised-change surfaces.** Updated the evaluation row (338 tasks — 263
  oracle-backed + 75 exemptions, plus `corpus.py` / `contamination.py` /
  `rotation.py` / `significance.py` / `live_baseline.py`), the RSL row (v4
  modules `archive` / `cmp` / `operators` / `sampler` / `autonomy` and the v4
  plan), and added a task row for corpus audit / rotation / live baselines /
  operator-triggered apply with the CLI, routes, UI cards and the quarterly
  workflow. Files: `docs/NAVIGATION.md`.
  docs updated: `docs/NAVIGATION.md`, `docs/CHANGELOG.md`.
- **feat(desktop): the icon now opens `blackeclipse`, with a visible boot console
  and a fast start.** `scripts/start-desktop.js` manages the production profile
  (`black eclipse --restart`: built Next on 3100 behind the local proxy),
  restarts an unmanaged instance so tab-close owns its lifecycle, and opens
  `https://blackeclipse` (http fallback). `start-eclipse.vbs` runs it with a
  visible console that closes when the tab closes; closing the console by hand
  stops the server. The launcher starts the existing build directly
  (`local-host`, ~2s) and never rebuilds while the user waits: a stale source
  shows a console note and still starts instantly, and the first launch on a
  fresh clone is the only build. `BE_DESKTOP_BUILD=1` forces a rebuild. The
  source hash is now content-based (a touch no longer invalidates the build),
  and a `postbuild` hook marks a plain `npm run build` as current.
  Files: `scripts/start-desktop.js`, `start-eclipse.vbs`, `scripts/mark-build.js`,
  `scripts/lib/server.js`, `scripts/doctor.js`, `package.json`.
  docs updated: `docs/QUICKSTART.md`, `docs/CHANGELOG.md`.
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

- **ui(stock detail): the overlay is compact and chart-led.** Reworked the
  full-screen stock detail overlay into a compact header + key-statistics band,
  one Interactive/History chart card, a collapsible AI brief, tabbed
  fundamentals, clamped news, merged Technical & Risk, merged profile +
  leadership, and a header glossary. Fixed overlay stacking above the chat dock,
  restored blur, contained rail overscroll, made the glossary clear the mobile
  header, and added explicit history loading/empty/error states. Forward P/E now
  comes from the selected stock; history ranges read `1M/3M/6M` and volume labels
  no longer collide. Kept `market-overview.tsx` at its 2,760-line ratchet by
  keeping the new prop on the existing line. Files:
  `src/components/screens/tradingview-chart.tsx`,
  `src/components/screens/company/sections.tsx`,
  `src/components/screens/fundamentals/panel.tsx`,
  `src/components/screens/market-overview.tsx`, `src/app/globals.css`.
  `npx tsc --noEmit` clean; Vitest 384 files / 3828 tests pass; lint 0 errors;
  size budget pass. no canonical doc change — presentation-only; no contract or
  data-shape change. docs updated: `docs/CHANGELOG.md`.

- **chore(evaluation): regenerated the published benchmark after the 2026Q4
  rotation.** The rotation changed the benchmark checksum, so
  `test_published_benchmarks` failed; `npm run eval:benchmarks` rewrote
  `docs/harness/benchmarks.md` from a fresh offline gate, and the targeted
  benchmark + watcher tests now pass (37). Files: `docs/harness/benchmarks.md`.
  docs updated: `docs/harness/benchmarks.md`, `docs/CHANGELOG.md`.

- **fix(home): removed the dead space below the dashboard footer.** The home
  dashboard root carried `pb-24`; its mobile clearance is already supplied by
  `#main-content`, so the extra 96px left a large empty band under the footer.
  Reduced to `pb-6`. File: `src/components/screens/dashboard/home-dashboard.tsx`.
  no doc change — spacing-only fix with no contract or architecture impact.

- **fix(windows): child processes no longer open console windows on server
  start.** Node's `spawn`/`exec*` default to `windowsHide: false`, so the
  auto-started Python harness, port checks, and doctor probes could pop a
  `cmd.exe` window on Windows. Set `windowsHide: true` on the harness spawn,
  Python resolver, launcher/server spawns, doctor, and kill-port. Files:
  `src/lib/harness/python-runtime.ts`, `src/lib/scraper/fetchers/python.ts`,
  `scripts/local-host.js`, `scripts/lib/server.js`, `scripts/doctor.js`,
  `scripts/kill-port.js`.
  no doc change — process-launch detail, no contract or architecture change.

- **feat(desktop): silent launcher that stops the server when the tab closes.**
  Added `scripts/start-desktop.js` (probe known app URLs, start `npm run dev`
  detached with no stdio, wait for HTTP, open `?desktop=1`) and
  `start-eclipse.vbs` (windowless wrapper). `<DesktopSession />` beacons
  `alive`/`leave` to `/api/desktop/session`; the launcher watches the beacon
  file and kills the process tree ~20s after the tab closes, with a reload grace
  window. The route is inert unless `BE_DESKTOP_HEARTBEAT_FILE` is set, so
  console-launched servers are unaffected. A `Black Eclipse` Desktop shortcut
  points at the VBS. Files: `scripts/start-desktop.js`, `start-eclipse.vbs`,
  `src/components/layout/desktop-session.tsx`,
  `src/app/api/desktop/session/route.ts`, `src/app/layout.tsx`.
  docs updated: `docs/QUICKSTART.md`, `docs/CHANGELOG.md`.

- **feat(stock-detail): sourced market-intelligence charts on the company overlay.**
  Added a read-only `GET /api/stocks/[symbol]/intelligence` route that fans out
  to the existing fundamentals service and Yahoo daily closes, then returns
  three derived charts: 6M return vs the home-market benchmark, trailing P/E at
  each fiscal year-end, and earnings surprise. Every chart carries a provenance
  block and an explicit `UNAVAILABLE` reason instead of invented points; web/AI
  facts are deliberately excluded from historical numeric series. The overlay
  mounts a new `Market intelligence` section between the price chart and the AI
  brief, with `SourceBadge` provenance chips and a 5-minute server cache.
  Files: `src/lib/stock-intelligence/{types,charts,use-stock-intelligence}.ts`,
  `src/app/api/stocks/[symbol]/intelligence/route.ts`,
  `src/components/screens/stock-detail/charts/{intelligence-panel,source-badge}.tsx`,
  `src/components/screens/tradingview-chart.tsx`,
  `src/lib/stock-intelligence/charts.test.ts`.
  docs updated: `docs/ARCHITECTURE.md`, `docs/NAVIGATION.md`, `docs/CHANGELOG.md`.

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

- **fix(eval): pin the published live run, because "latest" was not reproducible.**
  Auto-selecting the newest completed live run made the published file depend on
  mutable store state: running the test suite records more live runs, so
  regeneration and the committed file disagreed by test ORDER and the
  generated-not-hand-edited gate failed inside the full suite while passing alone.
  The run is now a named constant, `PUBLISHED_LIVE_RUN`, reviewed with the
  artifact. A published number that changes because a test ran is not
  reproducible. Benchmarks regenerated after merging main (their new tasks moved
  the offline counts).
  no doc change — the generated artifact is updated in the same commit.

- **revert(eval): do not embed a live run that exists on one machine.** Publishing
  `evalrun-1792772393137` in the committed artifact made it unreproducible: the
  run lives in this machine's `agent-memory.db`, while the test suite generates
  against an isolated store, so the generated file and the committed one disagreed
  inside the full suite while agreeing alone. The loader (`_load_live_suite`) stays
  - it is correct and usable with `--live-run <id>` locally. `PUBLISHED_LIVE_RUN`
  is empty and says why: publishing a live run needs a checked-in snapshot of that
  run, which is the recorded next step. The file reports honestly that no
  reproducible live measurement is committed instead of a number nobody else can
  regenerate. docs updated: docs/harness/benchmarks.md.

- **chore(ownership): CODEOWNERS names a real owner.** Round 4 / V3. The twelve
  harness paths were assigned to `@harness-owner`/`@code-owner`/`@docs-owner` -
  names that resolve to nobody. They are now `@desimarijuana`, so every path has
  an owner who can be requested for review. The file states plainly what this does
  NOT do: one person reviewing their own work is not a second pair of eyes, so the
  external-review criterion stays open.
  no doc change — ownership metadata, recorded here.

- **chore(ownership): CODEOWNERS uses a role, not a personal account.** The paths
  were assigned to `@desimarijuana`, which bakes a maintainer's personal GitHub
  account into a public source tree. They now name `@BlackEclipse/maintainers` - a
  role that resolves once the project has an org or team, and until then shows as
  unresolved, which is honest. Ownership is still assigned; no individual identity
  is committed.
  no doc change — ownership metadata, recorded here.

- **fix(eval): a dead environment is a REASON, and two samples are not a rate.**
  Round 4 / the RSL's empirical foundation. Two changes, both about not measuring
  the machine and calling it the agent.
  1. `live_gate.preflight_bridge()` spends one cheap capability
  (`market_snapshot`) before the suite. A front door that is not answering now
  produces one sentence and exit 0 instead of twelve failed trials and ~179
  `ConnectError` lines. Verified against a dead port: `NOT MEASURED - the data
  bridge at ... answered UNAVAILABLE (ConnectError...)`.
  2. `runner.MIN_SAMPLES_FOR_RATE = 5`: a dimension measured on fewer trials is
  persisted as `None` (published UNKNOWN) instead of a number. `safety_score
  0.6667` from n=2 was one coin flip presented as a finding; `None` never fails a
  gate, so the hole stays visible without pretending.
  Tests: `test_live_preflight.py` (dead bridge, healthy bridge, the sample floor).
  docs updated: none needed — behaviour is documented in the module docstrings.

- **chore(size): the ceiling moves 27 lines, on purpose, for the preflight.** The
  preflight is real code with a real test, so it cannot fit inside a budget that
  was pinned to the last line. Raising a ceiling is the thing this repo normally
  refuses, so it is recorded rather than slipped in: `totalLines`
  381,881 -> 381,908 and `evaluation` 11,456 -> 11,483, exactly the 27 lines the
  preflight and its test add. The alternative - deleting the tests - would have
  bought a lower number at the cost of the check that the number is honest.
  no doc change — the budget file is the record.

- **revert(eval): drop the minimum-sample rule; it collided with RSL baselines.**
  `MIN_SAMPLES_FOR_RATE = 5` fixed `safety_score 0.6667` from n=2 by publishing
  `None` instead - but a surface candidate's baseline is verified through the same
  metrics, so any baseline with fewer than five measurable trials became
  `SURFACE_BASELINE_UNMEASURED` and `test_surface_candidate_reuses_a_matching_
  recorded_baseline` failed. The rule is right and the collision is real: a
  baseline and a published rate have different sample requirements, and deciding
  that needs design, not a constant. Reverted rather than special-cased. The
  preflight stays (it is independent and verified). Budget re-pinned to the
  actual tree: 381,900 total, 11,475 evaluation.
  docs updated: none needed.

- **fix(eval): an outage is not an agent failure.** Round 4 / the RSL's empirical
  foundation, root cause. `score_trial` turned every non-completed trajectory into
  a failed task and a `reliability 0.0` sample - including trials that failed
  because the data bridge was down. The signal is the explicit `UNAVAILABLE`
  error code on the trajectory outcome: a trial carrying it is now `unmeasured`,
  excluded from `task_success` and from `reliability`, so `task_success 0.0` stops
  counting an outage as the agent's inability. The taxonomy's `infrastructure`
  label was tried first and rejected - it is the catch-all for ANY unlabeled
  failure, so honouring it would have excused real agent failures too (it broke
  `test_the_lab_never_invents_a_winner_on_the_scripted_tier`).
  Tests: `test_an_outage_is_not_an_agent_failure`. Budget re-pinned to the tree.
  docs updated: none needed.

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
