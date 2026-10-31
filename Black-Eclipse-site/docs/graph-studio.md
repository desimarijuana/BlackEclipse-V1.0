---
title: Graph Studio — Visual Workflow Engineering
status: Current
last-verified: 2026-10-30
---

# Graph Studio

**What this is:** the visual graph-engineering surface inside Eclipse — a canvas
for designing, validating, versioning and (progressively) executing workflows,
quant strategies and multi-agent systems that all compile to ONE canonical
workflow model.

This document is the **living implementation tracker** for the Graph Studio
program (Phases 1–10). It records the repository audit, the architecture, what is
implemented, and what remains. It is updated as each phase lands.

---

## Repository audit (before any change)

The audit established what already exists and what must NOT be rebuilt.

### Application shell

- Next.js 15 App Router, **tabbed SPA (no router)**. Screens mount as keep-alive
  blocks in `src/components/screens/stock-chat.tsx`; the tab union is the ONE
  declaration in `src/lib/app-tabs.ts`; sidebar items in
  `src/lib/sidebar/config.ts`; nav labels in `src/lib/i18n/nav.ts` +
  `dictionaries/en.ts`. There is a compile-time + runtime guard
  (`src/lib/app-tabs.test.ts`, `sidebar/config.test.ts`).
- Test infra: vitest (node env), `npm run test` = vitest + Python suites;
  `npx tsc --noEmit`; `npm run build`.

### Backend

- **Python FastAPI harness** is the agentic runtime. The browser reaches it
  through thin **front-door proxies** `src/app/api/<name>/[[...path]]/route.ts`
  → Python `/<name>/*` (guarded by `guardMutation` + runtime auth headers). The
  TypeScript side validates, resolves config and proxies; it does NOT reimplement
  agent loops, tools or model adapters.
- **Databases:** JDDS (`jdds.db`, Prisma/SQLite — market data + app tables) and
  `agent-memory.db` (Python runtime's own store). `doctor.js` runs
  `prisma db push` on boot, so adding Prisma models is zero-config.

### Existing graph / orchestration / finance infrastructure (reuse, don't rebuild)

- `python/harness/workflows/` — a bounded **step-plan** model (`Workflow`,
  `WorkflowStep`), validation, `WorkflowStore` (agent-memory.db) and a compiler
  onto the existing agent loop. This is the runtime *plan*, not a visual graph.
- `python/harness/quant/` — typed **strategy graph → IR compiler**, node registry,
  deterministic backtesting engine, indicators, costs, metrics, optimization.
- `python/harness/portfolio|factors|stats|ml/` — risk, factor, statistical and ML
  engines, each with an immutable-versioned store and a REST surface.
- `python/harness/fabric/` — durable execution fabric (modes, queues, workers,
  retries, DLQ, idempotency) — the Phase 4 orchestration substrate.
- `python/harness/tasks/`, `events/`, `automation/`, `artifacts/`, `security/`,
  `observability/` — durable plans, event bus/triggers, artifact storage,
  authorization ("ONE decision path"), telemetry.
- Market data via the **FinancialDataRouter / JDDS** — the single ingestion path;
  Graph Studio must read through it, never build a second one.

**Conclusion:** the runtime, scheduling, durability, finance engines and security
layer largely exist. The genuine gap is a **visual editor + a canonical
workflow model that unifies them**. Graph Studio is that layer.

---

## Architecture

```
 editor state (transient)         persistent document
 ┌───────────────────┐            ┌──────────────────────────┐
 │ selection, dirty  │            │ Eclipse Workflow IR      │
 │ undo/redo, errors │            │  irVersion + nodes/edges │
 └─────────┬─────────┘            │  + ports/config/modes    │
           │ dispatch(patch)      └────────────┬─────────────┘
           ▼                                   │ validate (pure)
   patches.ts (pure, validated) ──────────────►validation.ts (registry-driven)
                                               │ compile (Phase 3)
                                               ▼
                                        execution plan → runtime
```

Hard separations held by design:

- **The canvas is not the runtime.** React Flow renders the IR; edits route back
  through validated patches. React Flow's own node/edge types are never the
  canonical format.
- **Layout is non-semantic.** Node `x/y` is persisted for a usable reopen, but the
  validator/compiler ignore it — moving a node cannot change what a workflow does.
- **The editor state is transient.** Selection, dirty flag and undo history live
  in the zustand store, never in the persisted IR.
- **Authorization is runtime-side.** The IR declares required capabilities and an
  execution mode; the editor's mode selector is a *request*, enforced later by the
  security layer — a node or agent can never widen its own scope.

### Canonical Workflow IR (`src/lib/graph-studio/`)

| Module | Responsibility |
| --- | --- |
| `types.ts` | The vocabulary: `PortType`, `WorkflowNode/Edge`, `WorkflowSettings`, `NodeDefinition`, `Diagnostic`. |
| `ir.ts` | zod schema + `createWorkflowIR`/`parseWorkflowIR`; the ONE document model. |
| `migrations.ts` | Versioned migrations; `readWorkflowIR` = migrate → validate. |
| `registry.ts` | Data-only node registry + SDK contract (ports, config schema, capabilities, side-effect class, allowed modes). |
| `manifest.ts` / `registry.manifest.json` | Renders the TS registry to a deterministic cross-language manifest. Python asserts it matches its own registry node for node. |
| `validation.ts` | Frontend-independent validator: types, config, required inputs, cycles, reachability, terminals, mode/capability checks. All diagnostics name a node/edge. |
| `patches.ts` | Pure, individually-validated graph mutations; `canConnect` powers the canvas connection guard. |
| `layout.ts` | Deterministic layered auto-layout (no heavy layout dependency). |
| `editor-store.ts` | Transient editor state + undo/redo; every mutation via `dispatch(patch)`. |
| `persistence-client.ts` / `server-store.ts` | `/api/workflows*` client and the Prisma/append-only-version store. |
| `templates.ts` | Real, valid starter graphs. |

### Cross-language node contract

The editor registry (`registry.ts`) and the runtime registry
(`python/harness/graph_runtime/nodes.py`) are separate code on purpose: one
drives the palette, the other authorizes execution. They must describe the SAME
contracts.

- `manifest.ts` renders the TS registry into `registry.manifest.json` (ports,
  config field names/types, capabilities, side effects, modes, terminal).
- After changing ANY node contract run `npm run graph:manifest`.
- `src/lib/graph-studio/manifest.test.ts` fails when the checked-in JSON is
  stale; `python/tests/test_graph_registry_parity.py` fails when the Python
  registry disagrees with it. A node that exists in only one side is an error.

The manifest covers **54 node types**, and every registered type has an
executor in the runtime. `flow.subworkflow` is the one special case: the
executor handles it directly (`_run_subworkflow`) instead of binding a plain
`executor` function, so it has no executor attribute by design. The parity test
asserts that no other node is a dead contract.

`data.set_variables` is the first new core node added through this pipeline: it
merges configured named values over an optional input object (configured keys
win).

### Persistence

`Workflow` (container: name, tags, owner, `currentVersion`) + immutable
`WorkflowVersion` (JSON IR + content hash), in JDDS. Saving appends the next
version; the IR is re-validated server-side before it is stored. Routes:
`/api/workflows` (list/create), `/api/workflows/[id]` (get/save/delete),
`/api/workflows/[id]/versions`.

**One identity.** A run, a schedule and a subworkflow lookup are all addressed
by the persisted `Workflow` row id — never by the IR document id (`wf_…`). The
front door aligns the IR id to the row id before dispatching, and aligns each
bundled child IR to its pinned row id, so `/api/workflows/[id]/runs` (History)
and nested subworkflow rows use the same key.

---

## Navigation and workspace

The **Workflows** mode (`NavGroup 'graph'`, opened with `Alt+G` or the mode
switcher) is its own top-level workspace. Unlike Bots, it does **not** replace
the sidebar with a custom panel: the left sidebar uses the **standard nav list
filtered to graph sections** (**Overview**, Tables, plus the shared ChatBot
item), so the shell looks and behaves like every other page. A fresh shell still
boots in **Terminal**; a tab that chose Workflows keeps it for that session.

**Overview is the one Graph-mode page** (`overview` AppTab). There is no separate
`graph-studio` nav item: Overview hosts the whole workspace — the workflow
gallery *and* the editor. Opening/creating a workflow flips the page into the
editor in place; the editor's **Overview** back action returns to the gallery.
Old `?tab=graph-studio` links alias to `?tab=overview`. The **gallery keeps the
app top bar**; opening a workflow hides it so the **editor is full-bleed**. The
chat dock is hidden in both; the left sidebar stays visible.

The screen has two internal views (no router):

- **Workflows home** (`graph-home.tsx`) — a full-width, searchable **card
  gallery** of saved workflows (name, description, version, tags, updated time),
  the template starter set, prompt-to-graph generation, and a "continue editing"
  card when the editor still holds unsaved work. Data tables live on their own
  top-level **Tables** page (`docs/tables.md`), not inside Graph Studio.
- **Editor** (`graph-studio-screen.tsx` → `graph-canvas.tsx`) — a 48px header
  (Overview breadcrumb, a content-sized workflow name with dirty-state dot,
  version, execution mode, undo/redo, issues, Save, Test, and a More menu), the
  canvas, an optional right inspector dock and a collapsible execution dock.
  The canvas is **transparent** over the shell's frosted background, and node
  bodies use the `.node-card` material (a layered translucent surface with an inset highlight); floating
  palettes/menus stay on the glass overlay tiers.
  Nodes are **compact by default**: a 46px identity header (32px icon, 13px
  title, 9.5px category, quiet run dot, 2px black bezel) plus up to two **inline
  parameter fields**. A scalar value can therefore be read and changed without
  opening the inspector; object/array values stay panel-only. Fields whose input
  is supplied by an edge render a read-only **From wire** chip instead of an
  input, so a value cannot silently shadow the connected wire. `config-fields.ts`
  owns the presentation metadata (label, kind, select options, `inline`) and
  falls back to the definition's `defaultConfig()` shape for nodes without
  overrides — persisted config and semantics are unchanged. Auto-layout gaps keep
  enough vertical room for a node with two inline fields.

### Visual language

The editor deliberately keeps the app's frosted-glass theme rather than painting
an opaque canvas: the dot grid sits directly on the shell background, nodes are
translucent glass cards, and the small hover toolbars/edge controls use a
semi-transparent `bg-background/90` so they blend with both light and dark
themes. A solid canvas fill was removed because it flattened the rest of the
workspace and made the editor look like a separate product.

The left sidebar no longer hosts the node library. Adding a step happens **on
the canvas**, where the insertion point is known, and opens a **right-side node
library drawer** (a portaled `glass-drawer`, 400px) with search, category
sections and keyboard navigation. Picking a node inserts it at the pending
target and closes the drawer. On a phone the drawer becomes a full-width sheet.

| Gesture | Result |
| --- | --- |
| `Ctrl/Cmd+Tab` (canvas focused) / empty-state "Add first step" / right-edge **Add node** button | Search panel inserts a node under the pointer / view centre |
| Canvas controls → **Tidy up layout** (or the editor's More menu) | Deterministic auto-layout of every node |
| `+` on a node output | Search panel appends a node and wires that output |
| `+` on a hovered edge | Search panel inserts a node *into* the edge (splits it) |
| Drag on empty pane | Pan the canvas (grab/grabbing cursor) |
| Middle-mouse drag / hold `Space` + drag | Pan the canvas (same as plain drag) |
| `Shift` + drag on empty pane | Marquee selection box (crosshair cursor; n8n default) |
| Click node | Select it; the in-node widgets stay editable (drag still moves it) |
| Double-click node | Open the Parameters / Settings / Output inspector |
| `Ctrl/Cmd` + click node | Add/remove from the selection |
| Right-click pane / node | Context menu: add/paste/select-all/tidy/fit, or duplicate/copy/delete |
| Canvas controls → **?** | Canvas shortcuts panel |
| `Ctrl/Cmd+D` / `C` / `V` / `A` | Duplicate / copy / paste / select all |
| `Delete` / `Backspace` | Delete selected nodes and edges |

The search panel filters the registry to nodes that can actually be wired at
the chosen point (typed ports and acyclicity are checked by the same
`canConnect`/`portsCompatible` rules). Compound edits are expressed as ordinary
validated patches in `edit-ops.ts`, so undo/redo and the server-side revalidation
seam are unchanged.

**Node details.** **Double-clicking** a node opens a ~380px inspector dock;
a single click only selects it, so the in-node widgets can be edited without the
dock covering the canvas. Dragging still moves the node, and clicking empty
canvas closes the dock.
The card's inline fields and the inspector's Parameters tab are the **same
renderer** (`config-field.tsx`) at two densities: text/number edits commit on
blur or Enter (Escape reverts), booleans and selects commit immediately, and
consecutive edits to one control collapse into a single undo step
(`dispatch(patch, { coalesceKey })`). Inline inputs are `nodrag nopan nowheel`, so
typing never pans the canvas, drags the node, or opens the inspector mid-edit.

The Parameters tab is the full n8n-style form: the node's description and docs,
a friendly label plus one-line help for every field, required markers, selects
and booleans, a JSON editor only for object/array values, and an **Advanced: edit
config as JSON** escape hatch for fields the form does not expose. Dynamically
resolved fields (agent preset, broker connection/mandate, pinned body workflow)
render as pickers. **Settings** holds free-form **Notes** (saved with the node,
never executed), ports with types, capabilities, allowed modes and the node id.
**Output** shows the last run's bounded inputs/outputs for that node, read from
the persisted run record. Issues, History and Health are reachable from the
header instead of sharing five cramped tabs.

**Execution.** The header's **Start workflow** button is the primary run control,
inline with the other editor actions; when there are unsaved edits it becomes
**Save & run** (save, then execute the persisted version). The execution dock's
**Test run** action does the same without the save step. The bottom
**execution dock** collapses to a status strip and expands into the existing
run console; node statuses also render on the canvas (border tint, status badge,
animated edges while running). Operator runs open an explicit authorization
dialog listing only the effects this graph declared. History and Health open in
the same right dock.

While a run is active the dock consumes the run's **SSE stream**
(`GET /graphs/runs/{id}/stream` → Next proxy `/api/graph-runs/[runId]/stream`).
The stream replays the persisted event log from a cursor (`Last-Event-ID`), tails
new events from the `HarnessGraphEvent` table, updates node statuses in place,
and ends with `stream.end` once the run is terminal. The browser only fetches
the full run record at that point, so outputs/durations/errors are authoritative.
If the stream disconnects, the UI falls back to bounded polling.

## Phase status

| Phase | Scope | Status |
| --- | --- | --- |
| **1 — Foundation** | Workspace, canvas, custom nodes, editor state, persistence, dedicated mode | **Implemented & verified** |
| 2 — Canonical IR & node system | IR, registry/SDK, typed ports, validation, patches | **Implemented in TS AND Python** (editor + runtime registries in lockstep, now enforced by a generated cross-language manifest); migrations seam live |
| **3 — Compiler & execution engine** | IR → plan, deterministic executor, inspection, isolation | **Implemented & verified** |
| **4 — Control flow, scheduling & triggers** | Control-flow node pack, unattended schedules, webhook trigger, run recovery | **Implemented & verified** (distributed/Fabric-backed durability is the remaining piece) |
| **5 — Finance & quant node library** | Market-data + indicator node executors | **Implemented & verified** (first pack: market data, indicator, returns, z-score, volatility) |
| 6 — Backtest & simulation | Strategy graphs, metrics | **Implemented & verified** (backtest, walk-forward, optimizer, Monte Carlo and out-of-sample holdout; all reuse `quant/`) |
| 7 — AI agents & Chat-to-Graph | Agent nodes, chat→IR | **Implemented** (research agent, structured step planner, bounded task delegation, live web research, validated chat→IR) |
| 8 — Paper trading & safety | Execution adapter, risk controls, modes | **Implemented & verified** (`trading.risk_check` + `trading.paper_order` with a durable paper account, PAPER-only; live and ungranted trading refused) |
| 9 — Advanced engineering | Subworkflows, debugging, diffing | **Implemented** (subworkflows; post-run step inspector; structural version diff) |
| 10 — Hardening & verification | Tests, security, observability | **Implemented** (operator health telemetry: run/node counts, durations, queue wait, failure codes, slowest nodes) |

### Phase 3 — the runtime (`python/harness/graph_runtime/`)

The compiler and executor live in **Python** — the agentic runtime — not in
Next.js. The front door never executes a graph; it loads the persisted IR from
JDDS and forwards it.

> Naming trap: `python/harness/graph.py` is the EXISTING agent tool loop. The
> workflow runtime is the package `python/harness/graph_runtime/`. Do not create
> `harness/graph/` — it would shadow the module and break `execute_run`.

| Module | Responsibility |
| --- | --- |
| `model.py` | The IR contracts (pydantic, camelCase aliases mirroring the TS schema) + run/plan DTOs. Untrusted input: every field is re-validated. |
| `registry.py` | The node SDK: typed ports, config fields, capabilities, side-effect class, allowed modes, executor, timeout/retry. |
| `nodes.py` | The built-in PURE executors (incl. a real safe formula language — never `eval`) and the registered-but-unavailable contracts for later phases. |
| `compiler.py` | IR → `ExecutionPlan`: structural validation, longest-path **layers** (the parallelizable set) + deterministic topological order, mode checks and the **permission envelope**. |
| `executor.py` | Deterministic layer scheduler: `pending → ready → running → succeeded \| failed \| cancelled` (+ `skipped`), per-node timeout, retries, cancellation, output-schema validation, bounded input/output previews, event log. |
| `store.py` | Runs, **normalized node runs**, events and per-node checkpoints on `agent-memory.db`. Large node outputs stay as previews but make the run non-resumable. |
| `service.py` | Compile / run_sync / durable dispatch / execute_job / poll / cancel. |
| `worker.py` | The Fabric graph worker: runs `execute_job` in the loop's thread pool and forwards cancellation into a threading event. |
| `bootstrap.py` | Idempotent boot wiring; `routers/graphs.py` exposes `/graphs/*`. |

**Trust boundary.** `POST /api/workflows/[id]/runs` (Next.js) loads the
authoritative persisted version — the client never supplies the IR — and forwards
it with `testRun: true`. The runtime independently enforces the envelope: a
**test run never performs external write, network or trading effects**, and a
node whose declared capabilities were not granted is refused. Local scratch
writes (`local_write`, used by datasets) are allowed and bounded. Editor
visibility is not authorization.

**Run envelopes.** The default is a **test run**: no world effects, local reads
and local scratch only. An **operator run** is an explicit UI action; the front
door derives its grants from the registry and the persisted IR — never from the
caller. It grants exactly the union of node capabilities, enables network only
when the graph needs it and the user confirms, and keeps external write nodes
refused. Three effects may be enabled explicitly: PAPER trading
(`trading.paper_order` requires `executionMode: "paper"`, an explicit
confirmation and `allowTrading`), LIVE broker execution (`trading.broker_*`
requires `executionMode: "live"`, `allowLiveTrading`, an armed live connection
and a workflow-pinned live mandate), the
whitelisted LOCAL video render (`video.render` requires an explicit local-render
confirmation and `allowWrite`), and scoped file writes (`file.write` requires
the operator to confirm each named scope it uses; `allowedWriteScopes` carries
only those scopes). The Python compiler re-checks the same envelope.

**Scoped writes.** `file.write` never chooses an absolute path. A write names a
**scope** configured by the operator (`HARNESS_GRAPH_WRITE_ROOTS`, a JSON map;
`workspace` always defaults to `.black-eclipse/workspace`). The path is relative,
`..` and absolute paths are refused, the resolved target (after following
symlinks) must stay inside the scope root, the payload is capped at 8 MB, and a
normal write is atomic (temp file + replace). A test run never writes; an
operator run is granted only the scopes it explicitly confirmed.
`integration.http` is the first network node: SSRF-checked, loopback refused,
1 MB response cap, 60 s ceiling, plain custom headers (`headersJson`) and
credential REFERENCES (`credentialEnvJson`: header → env-var name, resolved by
the runtime and never stored). Transport-managed headers are refused; a header
cannot come from both sources.

**Determinism.** Executors are pure; the scheduler orders each layer by node id;
node inputs come from succeeded upstream writers only (a node whose required
input never materialized is `skipped`, never run with a null placeholder). Two
runs of the same graph with the same inputs produce identical outputs (tested).

**Durability.** A run is a DURABLE **Execution Fabric** job: the Fabric owns the
lease, retry/dead-letter and restart recovery, and the graph worker executes the
synchronous scheduler in its thread pool. The run row is `queued → running →
succeeded | failed | cancelled`; each node writes a normalized
`HarnessGraphNodeRun` row and an event, and a successful node stores a bounded
checkpoint. When the Fabric requeues a job after a crash, `execute_job` resumes:
completed nodes are seeded from their checkpoints and never re-executed. A graph
that fails a NODE is still a succeeded Fabric job (the run row is authoritative),
so the queue never retries a deterministic graph failure. If the Fabric is
disabled/unavailable the legacy in-process thread path still works, with the same
persistence but no automatic resume.

### Phase 4 — control flow, schedules and triggers

**Control ports gate EXECUTION, not values.** A node fires the control outputs it
selected by returning reserved `_control` names; a node that declares control
inputs runs only when an upstream fired one of them (`flow.gate`). Downstream
values then follow ordinary dataflow, so a branch that did not fire is `skipped`
and everything below it is skipped too — the if/else semantics fall out of the
scheduler rather than special-casing.

New nodes (both registries, Python executors, `scripts`-free and bounded):

| Node | Semantics |
| --- | --- |
| `flow.gate` | Runs only when its control input fires — the branch primitive. |
| `logic.switch` | Fires `matched`/`default` and reports `caseIndex`. |
| `logic.map` / `logic.filter` / `logic.reduce` | Bounded (`10 000` items) numeric loops over the safe formula language. |
| `logic.wait` | Bounded pause; a durable job DEFERS itself instead of blocking. A TEST run allows at most 5 s. |
| `logic.stop` | Ends the run here; downstream nodes become `skipped`. |
| `flow.subworkflow` | Runs a **pinned** saved workflow (`workflowId@version`) as a nested run. |

**Durable waits.** In a durable Fabric job, `logic.wait` checkpoints itself and
pauses the RUN (status `queued`); the worker returns a `deferred` outcome and the
Fabric requeues the job at the wake time without consuming a retry, then resumes
from the wait checkpoint. It is bounded to 24 h and never holds a worker thread.
A non-durable run (e.g. `run_sync`) still blocks, capped at 30 s; a test run is
capped at 5 s by the compiler. Model settings stay in memory across the deferral,
so a worker restart before the resume still makes agent nodes fail honestly.

**Subworkflows are pinned and authority-preserving.** The node's parent input is
delivered to the child's trigger as the run input; the child's terminal value
becomes the node output (`{nodeId: value}` when the child has several terminals).
The front door (`subworkflow-bundle.ts`) resolves every referenced workflow from
JDDS and sends the IRs with the run, so the runtime never reaches into JDDS. The
runtime compiles each child with the SAME grants, so a subworkflow can only
narrow authority, never widen it. Cycles and nesting deeper than 5 are refused
by both the bundle loader and the compiler. After a nested run finishes, the
service gives it its OWN durable run row (`<parentRunId>:<nodeId>`) with its node
runs and events, so it is inspectable from the child workflow's History; the
parent node returns that child `runId`. The inspector picks a saved workflow and
pins its version from a dropdown instead of typing ids.

**Loops are internal and bounded, never graph cycles.** The compiler still
refuses a cyclic graph. Iteration is a node with a pinned body workflow and a
declared cap:

| Node | Semantics | Bounds |
| --- | --- | --- |
| `flow.for_each` | Runs the body once per array item; returns `results` | `maxIterations` (≤ 1 000), `maxDurationMs` |
| `flow.repeat` | Runs the body `count` times, passing the previous output on | `count` (≤ 1 000), `maxDurationMs` |
| `flow.while` | Runs while a safe numeric condition holds (`value`, `index`, `iterations`) | `maxIterations`, `maxDurationMs` |

Every iteration is its own durable child run (`<parent>:<node>:i<N>`), which is
also the loop checkpoint: a parent resumed after a crash reuses a succeeded
iteration's output instead of re-running it. `flow.for_each` can continue past a
failed item (`continueOnError`) and records the error in `results`; the other
shapes fail the node. A loop without a pinned body is invalid in both the editor
and the compiler.

**Schedules.** `trigger.schedule` is **zero-config**: the node declares no cron
or timezone. Its schedule is a `WorkflowSchedule` row (JDDS) linked by `nodeId`,
edited in the node inspector's **Schedule** tab. The tab is a builder — repeat
(minutes / hourly / daily / weekly / monthly / custom), a real time picker,
weekday chips, an IANA timezone select, catch-up policy and version pin — and it
previews the next three fires with the same cron engine the tick uses. The node
and the scheduler therefore cannot drift apart; `nodeId` is null only on older
schedules created from the execution dock, which still fire.

The **node card** shows the live schedule itself: an Active/Paused dot, a human
summary (`Weekdays at 09:00 · Asia/Karachi`), the next fire in that timezone, and
the last error when a fire failed. It refreshes after any schedule mutation and
once a minute as the tick advances `nextRunAt`; a node with no linked schedule
shows “No schedule yet — open the Schedule tab”. The Schedule tab remains the
editor.

A schedule whose linked `trigger.schedule` node has been deleted is **paused**
with an error on the next tick — it can never keep firing a workflow from a
trigger the graph no longer contains. Schedules created from the old dock (no
`nodeId`) are unaffected. For an unattended host, drive the tick from system
cron as described below; otherwise schedules only fire while the Eclipse server
is running.

**Workflow bots.** A saved workflow can be the brain of a bot in Bots mode:
*New bot → Brain → Workflow*, then pick the workflow. Each chat message is sent
as the workflow's one-off `runInput` (`{ message, botId, context }`) and the
bot replies with the graph's terminal output (a string, or pretty JSON). The
bot card and chat header show a **Workflow** badge; the workflow editor shows
that bot's avatar in its header. Scheduled workflow bots run through the
automation engine's `execute_workflow` action with
`action.config.graphWorkflowId`; the Python runtime cannot read JDDS, so it
starts the run through the front door and polls the graph run record. Both chat
turns and scheduled runs use the normal **read-only TEST envelope** — a
workflow bot cannot place orders, write files or hit the network just because
it was messaged or scheduled.

`src/lib/graph-studio/cron.ts` is a dependency-free, timezone-aware 5-field cron
evaluator (cached `Intl` formatters, 40-day search bound). A 60 s in-process
timer — started early in `instrumentation.ts`, before the long boot pipeline —
fires due schedules through the SAME test-run dispatch as the UI, so a scheduled
run can read and compute but never write, trade or use network effects. Each due
fire is **claimed atomically** (compare-and-set on the exact `nextRunAt`) before
a run starts, and a process-level lock prevents overlapping ticks, so two ticks
or two server processes cannot double-fire. Missed fires follow the schedule's
policy — `skip` (advance only) or `coalesce` (run once now) — so a closed app
never storms on boot. A fire records `started`; a later tick reconciles the
terminal run status, so “last status” cannot stay stuck at `started`. **Run now**
fires one schedule immediately in the same envelope without moving its clock.

**Triggers.** All three trigger nodes are zero-config. Manual = the toolbar /
UI; schedule = a `WorkflowSchedule` linked to the node (above); webhook =
`POST /api/workflows/[id]/trigger`, where the request body becomes the trigger's
`runInput`. The webhook deliberately runs inside the TEST-RUN envelope: a trigger
reachable without a secret must not be able to act on the world (secret-signed
webhooks are Phase 8/10 work).

`trigger.manual` is deliberately **zero-config**, like n8n's Manual Trigger: it
has no declared config fields. `Start` is the one-off run input (the Execution
dock's **Run input** editor, or the webhook request body) or `null`. The input is
bounded to 64 KiB, validated on both the editor and the route, and never written
into the persisted workflow. **Stored defaults belong in a `data.value` or
`data.set_variables` node, not on the trigger.** Workflows saved before this
change may still carry `payload`/`payloadType`/`seed` in their config; those keys
are no longer shown or declared, but `_exec_trigger` still honours them so an
existing graph does not silently change behaviour.

**Per-node testing.** `POST /api/graph-runs/node-test` → Python
`POST /graphs/nodes/test` runs ONE registered node (never a graph, never a
persisted run) with explicit per-port `inputs` and the node's declared config.
The runtime re-validates the config and inputs, enforces the node's own hard
timeout, and only allows `none`/`read` side effects: network, write, trading,
model and local-write nodes are refused with a 403 and must go through an
authorized run.

Every node exposes this in three places: the inspector's **Test** tab, a **▶
Test** button in the node's hover toolbar, and the footer of the **quick edit**
panel. A test runs with the current (possibly unsaved) config, pre-fills the
last run's inputs when available, and shows outputs, logs and duration. For a
trigger, the output is exactly the `Start` value it would emit. Test state is
ephemeral: a small dot on the card (running / succeeded / failed) plus the result
in the quick edit panel; nothing is written to the workflow or JDDS.

**In-node controls.** Parameters are edited directly on the node, not in a
popover. Two priority fields are always visible; `ConfigFieldDef.quick` (1 =
highest) chooses them, otherwise declaration order wins, and a **+N more
parameters** row expands the rest *inside* the node (with **Show less** to
collapse). Controls are Blender/ComfyUI-style: number fields drag horizontally to
scrub (Shift = fine, Ctrl/Cmd = coarse, click without dragging to type), selects
are dropdowns, booleans are checkboxes, text is an input and JSON is a compact
single-line value box. Every control dispatches the same `update_node_config`
patch as the inspector, so the two surfaces cannot diverge. A **single click
selects** the node (so the in-node widgets stay usable); **double-click** opens
the inspector for advanced details.

The hover toolbar's **Test** (play) button, next to Duplicate, runs the node
through the same safe endpoint. The result renders inside the node body: running,
succeeded or failed, duration, the error, and an expandable output preview. The
toolbar also keeps Duplicate / Delete / More. Nodes with side effects show a lock
instead of Test and explain that an authorized run is required.

**Recovery.** A run left `running` by a previous process is marked failed
(`interrupted by a restart`) when the runtime boot-wires the graph layer, so a
phantom in-flight row cannot survive a crash.

### Phase 5 — the finance + quant node pack

Executors live in `python/harness/graph_runtime/finance_nodes.py` and obey two
rules: **reuse the existing data path** and **reuse the tested math**.

| Node | Data / math |
| --- | --- |
| `finance.market_data` | Reads the runtime's **persistent bar series** (`harness/market/series_store.py`) — the same vault the research-data tools fill. No second ingestion. |
| `finance.indicator` | `sma/ema/rsi/macd/atr/adx/vwap/bollinger` via `harness/quant/indicators.py` (`compute_one`), with warm-up nulls, per-output series and `last`. |
| `quant.returns` | Simple or log returns over a period. |
| `quant.zscore` | Rolling standard score. |
| `quant.volatility` | Rolling std-dev of log returns, optional annualization. |

**Gateway-backed data.** `finance.quote` and `finance.history` call the EXISTING
`MarketDataGateway` (bound to the server bridge at boot), so live quotes and
OHLCV use the same provider router, quality/freshness metadata and durable
history cache as the agent tools. A gateway error is an explicit node failure
(`DATA_NOT_AVAILABLE`, `SYMBOL_NOT_FOUND`, …), never a fabricated price.
`finance.history` emits the standard OHLCV payload, so it feeds
`finance.indicator` directly.

**Quant backtest.** `quant.backtest` adapts the graph's OHLCV payload into a
`BarSeries`/`MarketDataset` and calls `harness/quant/engine.py`. It accepts the
documented `ema_cross` and `rsi_reversion` presets, or a full `StrategySpec` JSON
(`strategyJson`). The input series symbol is authoritative (a JSON strategy
cannot backtest a different symbol). It returns the full result object, the flat
metrics, and the trade list; series curves are omitted unless `includeSeries` is
on. Runs are deterministic (`randomSeed`) and bounded by `maxBars`.

**Walk-forward.** `quant.walkforward` rolls train/test windows through
`harness/quant/walkforward.py`; parameters are optimized on the training window
only and the chosen configuration is evaluated out-of-sample. The report carries
in-sample, out-of-sample and combined metrics plus the IS/OOS divergence. A
default parameter space is derived from the preset; a custom strategy needs
`paramSpaceJson`. Insufficient history is returned as an honest
`INSUFFICIENT_HISTORY` status, not an exception.

**Optimizer, Monte Carlo and OOS holdout.** `quant.optimize` drives
`harness/quant/optimize.py` over `paramSpaceJson` (grid/random/evolutionary/
bayesian) and returns the best trial, leaderboard, stability and Pareto set -
it reports a choice, it never auto-adopts one. `quant.montecarlo` drives
`harness/quant/montecarlo.py` (trade reshuffle, return bootstrap, regime blocks,
parameter/execution perturbation) and returns return percentiles, loss/ruin
probability and drawdowns. `quant.oos` makes a chronological split (fraction or
index), backtests both sides with the SAME deterministic engine, and reports
in-sample vs out-of-sample metrics, their objective divergence and a
block-bootstrap confidence interval for the OOS mean return. A materially
weaker OOS objective is an explicit `IS_OOS_DIVERGENCE` warning, never a
silently "validated" strategy.

**Research agent.** `agent.research` is a thin adapter over the EXISTING agent
run plane (`AgenticService.run`), not a second agent loop. Its `query` input is
optional: the node runs on a wired query **or** the configured objective (a
node with neither is invalid at compile time). It resolves the named agent
preset and its tools, caps the turn at `maxSteps`, and returns a structured
`finding` plus the run's `research` evidence object. The adapter treats the run
plane's terminal `completed` status (and `succeeded` for substitutes) as
success; a failed/cancelled run reports its own error message. Agent nodes are a
**`model` side effect**, not `network`: a test/dry run may call the model while
its tool surface is narrowed to `DRY_RUN_TOOLS` (read-only finance, local
evidence, response helpers) — web research, browser, MCP, plugins, code and
broker tools are removed. An operator run keeps the preset's declared surface.
The front door resolves model credentials from the vault and sends them in
memory only; `GraphService` deliberately excludes them from the durable Fabric
job payload. A restart before the agent node runs therefore makes that node fail
honestly instead of persisting a key.

**Research & evidence.** `research.evidence`, `research.citations`,
`research.conflicts`, `research.completeness`, `research.claim_verify` and
`research.report` read the existing `EvidenceStore` from the web research
engine: evidence, claims, citations, conflicts, coverage, deterministic claim
verification and a Markdown report. They are local reads (`research.read` is
granted to test runs) - no web request and no model call.

The live half reuses the same engine instead of inventing a second web path:
`research.web_search` calls the configured search-provider chain (results are
pointers, never evidence) and `research.web_fetch` fetches one page through the
SSRF-hardened `web_fetch` bridge capability and returns its extracted text. When
`web_fetch` has a `researchId`, it saves the same `Evidence` the `web_extract`
tool saves, so a graph can search, fetch, then verify with the local nodes.
Both are declared `network` side effects: a test run refuses them and an
operator run must explicitly confirm network access. They depend on the app's
data bridge (`context.callbackBaseUrl`), so a headless runtime with no front
door fails honestly rather than fetching directly.

**Paper trading & safety.** `trading.risk_check` is a pure pre-trade gate over
`harness/quant/risk.py` (position, gross exposure, leverage, open-position,
daily-loss and risk-per-trade limits; `0` disables a limit). It may reduce an
order's size or reject it, and a rejection is an outcome with reasons, not an
exception. `trading.paper_order` is the execution adapter: it fills at a
supplied reference price with explicit slippage and commission and returns a
paper fill. By default it also records the fill in a durable PAPER account
(`GraphPaperAccount` / `GraphPaperFill` on `agent-memory.db`): cash, signed
position, average cost and realized PnL survive across runs, so a scheduled
paper graph keeps its book. Accounting is cash + cost basis, not a
mark-to-market valuation, and the fill price is always the one the graph
supplied. It never contacts a broker, never reads a live quote, and only runs
in PAPER mode behind the operator's paper-trading confirmation. There is no
live adapter; LIVE mode is refused.

`trading.broker_order` is the demo-broker adapter added in P3. It takes an
`intent` plus a `connectionId` and `mandateId`, runs only in PAPER mode, and calls
the SAME `BrokerService.submit_order` path as a manual order. The operator-created
mandate is the authorization (allowed symbols, per-order `maxMargin`, `maxOrders`,
expiry; immediate revoke), and each use is counted atomically. The connection must
be a demo MT5 connection; live trading nodes remain refused by the compiler and the
front door. See `docs/trading.md`.

**Custom agent presets.** Settings › Agents creates an operator-authored preset:
a name, system prompt, max-step bound, an explicit tool allowlist and optional
MCP/plugin expansion. Presets are stored on `agent-memory.db` by the runtime
(`AgentPreset` + immutable `AgentPresetVersion`), so a preset is runtime state,
not a Next.js setting. Every edit appends a version; the agent node pins
`agent@version` (0 = current), and a pinned run keeps its snapshot. A preset that
names a write/external tool requires the explicit “Allow effectful tools”
acknowledgement; unknown tool names are refused at save time. The three built-ins
remain code-resolved in `agents.py`.

**Planner and delegate.** `agent.plan` makes ONE bounded model call with a strict
step schema and returns 1–8 steps (stable ids, optional `dependsOn` on earlier
steps). It never executes them. `agent.delegate` runs each task as one bounded
turn on the existing agent plane (up to `maxTasks`, default 4) and returns every
finding; a failed part is reported as `failed` with its error and the summary is
`PARTIAL`, never a hidden success. Both are `agent.run` + `model` nodes, so a
test/dry run may execute them with the narrowed read-only tool surface, while an
operator run keeps the preset's declared surface. Neither re-implements the
agent loop or tool registry.

**Chat-to-graph.** `POST /api/graphs/plan` → Python `POST /graphs/plan` turns a
natural-language objective into a candidate workflow. The model receives the
runtime's ACTUAL node catalog (types, ports, config defaults, side effects) and
returns strict JSON. `graph_runtime/planner.py` accepts the canonical edge fields
plus common model aliases (`from`/`to`, `sourcePort`/`targetPort`, `{node, port}`
handles), then validates every node type,
port compatibility, config and edge, derives `requiredCapabilities` and picks
`research` mode - or `paper` when the proposal contains a trading node - and
dry-runs the compiler. Only a plan with zero errors becomes a `WorkflowIR`
(saved by the normal workflow create path, never automatically executed); a
rejected plan returns its diagnostics. Model credentials are resolved by the
front door and used in memory only. The planner is one bounded model call: no
auto-repair loop, no subworkflows, and no live mode.

**Tabular transforms.** `transform.select`, `transform.sort_limit`,
`logic.aggregate`, `logic.deduplicate` and `transform.join` operate on arrays of
JSON objects (bars, fundamentals, filings, screener rows) with dotted field
paths. They are bounded to 100 000 rows, deterministic, and refuse non-object
rows. `logic.aggregate` supports sum/avg/min/max/count with optional `groupBy`;
`transform.join` supports inner/left joins with a matched count.

**Local datasets.** `data.dataset.save` writes a JSON payload to the runtime's
own `HarnessGraphDataset` table on `agent-memory.db` and returns a small
`gds:` ref plus metadata; `data.dataset.load` reads it back. This is the
large-payload seam: a series can travel as a ref instead of being embedded in a
node's config or the run document. It is deliberately **local scratch**, not a
market-data source and not a second JDDS. Limits: 8 MB per dataset, 200
datasets, optional TTL (max 8 760 h); expired refs are purged and fail
explicitly. Datasets are OWNER-SCOPED by the run's user id: another owner's ref
is reported as not found, not as a forbidden row. The `local_write` side-effect
class exists so a test run can use datasets while external
write/network/trading remain refused.

**Honest data.** Every payload carries provenance (`provider`, `symbol`,
`interval`, `adjusted`, `rows`, `asOf`, `retrievedAt`). An empty vault is a
FAILURE with an actionable message ("fetch them first … the graph never
fabricates a price") — never a synthetic series, never a silent zero.

**Test-run policy.** A test run implicitly grants the read-only / local-compute
capabilities (`market.read`, `quant.compute`, `compute.safe`, `dataset.read`,
`dataset.write`) plus `agent.run` — a model call is not a world effect — so a
finance graph can be exercised from the UI. Agent tools are narrowed to
`DRY_RUN_TOOLS` in that run. External write/network/trading nodes stay refused.

**Templates.** `Market scan (SMA z-score)` — stored bars → SMA(50) → z-score(20)
→ branch → result, plus a second output carrying the data provenance.

### Phase 9 — inspection and diffing

**Step inspector** (`src/lib/graph-studio/run-debug.ts` + the Run panel). A
finished or partially failed run is walked step by step: node order, status
(including attempts and skips), bounded inputs/outputs, the node's own events,
and whether its checkpoint is resumable. It is a read-only inspector over the
persisted run record — no re-execution, no synthetic success. The runtime now
exposes `nodeRuns[].resumable` so the UI can say "checkpoint saved" truthfully
instead of inferring it.

**Structural diff** (`src/lib/graph-studio/ir-diff.ts` + History > Versions >
Diff). Two immutable versions are compared without running either: added,
removed and changed nodes (type, version, label, position, config), added/
removed/changed edges, changed settings and a changed workflow name. Config
comparison is key-order-insensitive. A removed node/edge is reported by id; a
first version says there is nothing to compare rather than showing an empty
diff.

### Phase 10 — run telemetry and hardening

`GET /graphs/health?windowHours=N` (operator-gated) is a BOUNDED read over the
persisted run tables: run counts by status, success/failure rate, duration
p50/p95, queue wait (created → started), throughput, failed-node codes, the
slowest node types, and checkpoint coverage. Reads are capped (1 000 runs /
5 000 node rows, 1–168 h) and the response says `truncated` when a cap was hit.
Missing values are `null`, never zero. The Graph Studio **Health** tab shows the
same figures for 1 h / 24 h / 7 d with an explicit refresh. Additive contract:
`nodeRuns[].resumable` (Phase 9) and `/graphs/health` (this phase); no new store,
queue or scheduler.

**Health watch.** `graph_runtime/health_watch.py` reads the same telemetry on a
cadence and persists one verdict (`unmeasured` / `insufficient` / `healthy` /
`degraded`) in `GraphHealthWatchState`; the health response carries it as
`watch`. It publishes `graph.health_degraded` / `graph.health_recovered` only on a
transition, never every tick; each transition is also appended to a bounded
`GraphHealthAlert` history that the Health tab lists (newest first). Thin data
is `insufficient`, not healthy. Tuning:
`HARNESS_GRAPH_HEALTH_SECONDS` (default 300; `0` disables),
`HARNESS_GRAPH_HEALTH_WINDOW_HOURS` (default 1),
`HARNESS_GRAPH_HEALTH_MIN_RUNS` (default 5),
`HARNESS_GRAPH_HEALTH_FAILURE_RATE` (default 0.5) and
`HARNESS_GRAPH_HEALTH_QUEUE_MS` (default 60000). It never creates or changes a
run.

**Headless schedules.** The in-process 60 s timer is sufficient while the app is
up. For an unattended host, drive the same tick from system cron (with
`CRON_SECRET` set):

`curl -fsS -X POST -H "Authorization: Bearer $CRON_SECRET" http://127.0.0.1:3000/api/workflow-schedules/tick`

The tick is idempotent per due schedule; missed fires still follow each
schedule's `skip`/`coalesce` policy.

### Phase 1 — acceptance criteria (verified)

- Graph Studio opens within Eclipse (new `graph-studio` AppTab + sidebar item). ✓
- Create, position, connect, configure and delete nodes. ✓
- Zoom, pan, selection (React Flow Controls + MiniMap + selection state). ✓
- A graph can be saved and reopened (append-only versions). ✓
- Existing routes/features unaffected — full vitest suite green. ✓
- `npx tsc --noEmit`, the full vitest suite (3440 tests) and `npm run build` pass. ✓

---

### Phase 3 — acceptance criteria (verified)

- A simple graph executes from its trigger through its terminal. ✓
- Node outputs are validated against their declared port schemas. ✓
- Failed nodes produce inspectable errors (message, `errorCode`, duration, the
  inputs that produced them) and downstream nodes are `skipped`. ✓
- Execution status appears on the canvas (node status chips + border tint) and in
  the Run panel. ✓
- Test execution cannot trigger live trading (no trading node is authorized; the
  envelope refuses trading/network/external-write regardless of the request).
  Local dataset scratch is the one bounded write a test run may perform. ✓
- The same workflow produces reproducible results for identical inputs. ✓

## Verification

Phase 1:

- `npx tsc --noEmit` — clean; full vitest suite green; `npm run build` succeeds.

Phases 3–4:

- `npx tsc --noEmit` — clean.
- `npx vitest run src/lib/graph-studio` — **16 files / 85 tests pass**.
- `npm run build` — production build succeeds; `/api/graph-runs/*`,
  `/api/workflows/[id]/{runs,trigger,schedules}` and `/api/workflow-schedules/*`
  registered.
- Python graph suites — **234 tests pass** (model/registry/formula, compiler,
  executor, control flow, service, HTTP API, SSE replay, finance/video nodes,
  gateway quote/history, tabular transforms, quant backtest/walk-forward/
  optimizer/Monte Carlo/OOS, paper risk gate/execution adapter and LIVE refusal,
  agent planning/delegation, chat-to-graph validation, health telemetry/watch,
  bounded crawl,
  local research/evidence + live web search/fetch/claim verification, agent
  node, operator-run/HTTP safety, registry parity, datasets, subworkflows,
  durable dispatch/resume), including a real
  Fabric manager + graph worker integration test and full-stack API tests on a
  temp database. `test_graph_agent_e2e.py` is an OPT-IN real-provider check:
  skipped unless `HARNESS_E2E=1` plus provider/model env vars (API key only for
  remote providers). It passed locally against the configured Ollama model,
  covering chat-to-graph, step planning and an agent node.

### Navigation regressions fixed (post-Phase 4)

Selecting the Graph mode blanked the app. Root cause: the mobile bottom nav
renders `TAB_META[id].icon` for every tab a mode lists, `TAB_META` was typed
`Record<string, …>`, and `graph-studio` had no entry — `undefined.icon` threw
inside the top-level ErrorBoundary. Because the chosen mode is persisted, every
subsequent load could hit the same path. Fixed by adding the entry, typing
`TAB_META` by `AppTab`, guarding both render sites, and adding a coverage test
(`mobile-bottom-nav.test.ts`). Two neighbours were fixed with the same pass: the
persisted-mode allowlist dropped `'graph'` (the mode never stuck) and
`APP_TABS` in `search/deep-link.ts` omitted the new tabs, so `?tab=`/boot-tab
links fell back to ChatBot. `APP_TABS` is now an exhaustive `Record<AppTab, true>`
(adding a tab without listing it is a compile error) and `NAV_GROUPS` is the ONE
mode list. Verified in a real browser: the mode switcher, the panel's
open/create path and `?tab=graph-studio` all mount the workspace with no console
or HTTP errors.

## Known limitations

- **Durable workers, one host.** Runs are durable Fabric jobs and resume from
  node checkpoints after a worker/process restart. Several processes on the SAME
  host may share `agent-memory.db` and split workers by
  `HARNESS_FABRIC_WORKERS` / `python -m harness.fabric.standalone`; claims are
  atomic. A multi-machine fleet is not supported by the local SQLite store. The
  legacy in-process fallback (Fabric disabled) has no automatic resume.
- **Checkpoint storage.** A successful node's output is stored in the DB up to
  2 MB by default (`HARNESS_GRAPH_CHECKPOINT_MAX_BYTES`, bounded to 16 MB).
  Above that it spills to a confined JSON file under
  `<db-dir>/graph-checkpoints/<runId>/` (up to 256 MB) and the run stays
  resumable. Above the file cap the run is non-resumable and starts fresh on a
  retry. Spilled files are deleted with the run.
- Schedules tick while the app is up (a 60 s in-process timer). A fully
  headless/unattended deployment must drive `POST /api/workflow-schedules/tick`
  from external cron (see "Headless schedules"); the app cannot tick while it is
  stopped.
- `logic.wait` defers a durable job (up to 24 h) instead of blocking. Only a
  non-durable `run_sync` still blocks, capped at 30 s; a test run is capped at 5 s.
- Loop primitives accept numeric arrays AND object rows: a row's numeric fields
  are bound by name (plus `value`, `index`, `acc`), so `close - open` works. A
  nested object/array field is not flattened; project it first.
- Run history is browsable in the History panel; node runs and events are
  normalized tables, and successful nodes have resumable checkpoints.
- Operator runs allow network, PAPER trading, LIVE broker execution under the
  two-key model, the whitelisted local `video.render`, and `file.write` only
  inside the named scopes the operator confirmed. Other external write nodes and
  ungranted trading are refused. Live orders need an armed live connection **and**
  an active workflow-pinned live mandate (24 h max TTL); a paper-only node in live
  mode is refused by the compiler. `file.write` is confined to its scope
  (relative paths, no `..`, no symlink escape, 8 MB cap, atomic replacement). The paper account persists cash,
  positions and realized PnL, but it is cost-basis accounting (no mark-to-market)
  and fills only at a supplied price - it never fetches a live quote.
  `persist: false` keeps a single-node fill stateless.
- Agent model credentials are held in memory for the run only and are never
  written into the durable job payload. After a process restart the worker
  re-resolves them from the front door (`POST /api/graph-runs/{id}/credentials`,
  operator-gated) using the persisted callback URL. If the front door is down or
  no provider is configured, that node fails honestly. Agent turns also resume
  from the agent plane's own checkpoint (`agent_run_identity`): a crashed turn
  re-enters the same run when a checkpoint exists; without one the turn restarts
  under a fresh id (safe — a model call has no world effect). The nodes remain
  bounded turns/plans (no autonomous loop). A real-provider e2e harness exists
  (`test_graph_agent_e2e.py`) but is opt-in and needs credentials.
- Web research nodes use the app's data bridge (a real operator run has one; a
  headless runtime does not). With `allowBrowser`, `research.web_fetch` escalates
  a thin/failed page to the existing Browser Runtime; without it (the default) it
  fetches exactly the URL it was given. `research.web_crawl` walks a BOUNDED
  same-site graph (1–10 pages) using the bridge's deterministic link collector,
  never a general crawler. `research.claim_verify` requires the evidence ids
  explicitly and verifies against the local EvidenceStore only.
- A nested subworkflow gets its own durable run row AFTER it finishes; a child
  interrupted by a process crash has no partial row (the parent resumes from its
  node checkpoint). The child row is keyed by `<parentRunId>:<nodeId>`.
- `live` mode is settable in the IR but no executor honours it and the compiler
  refuses a trading node in LIVE mode. Paper trading is the only trading effect
  Graph Studio can authorize today.
- **`video.render` runs the existing pipeline inline in the graph worker.** It
  builds a bound recap storyboard and calls `VideoService.run_render_job`, so it
  writes project files and an Artifact Center entry; it is not queued as a
  separate Fabric job. It requires an operator run with the explicit local-render
  grant and the fframes Rust worker installed (a missing worker is an honest
  failure).

## Next milestone

**Post-phase hardening**: the ten phases are implemented, including external-cron
guidance, health alerting and same-host multi-process Fabric workers. The
remaining item is a genuinely multi-machine fleet, which would require replacing
the local SQLite store with a shared database/queue; the rest are scoped bounds
listed under "Known limitations".

