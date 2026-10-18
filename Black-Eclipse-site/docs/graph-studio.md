---
title: Graph Studio — Visual Workflow Engineering
status: Current
last-verified: 2026-10-17
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
| `validation.ts` | Frontend-independent validator: types, config, required inputs, cycles, reachability, terminals, mode/capability checks. All diagnostics name a node/edge. |
| `patches.ts` | Pure, individually-validated graph mutations; `canConnect` powers the canvas connection guard. |
| `layout.ts` | Deterministic layered auto-layout (no heavy layout dependency). |
| `editor-store.ts` | Transient editor state + undo/redo; every mutation via `dispatch(patch)`. |
| `persistence-client.ts` / `server-store.ts` | `/api/workflows*` client and the Prisma/append-only-version store. |
| `templates.ts` | Real, valid starter graphs. |

### Persistence

`Workflow` (container: name, tags, owner, `currentVersion`) + immutable
`WorkflowVersion` (JSON IR + content hash), in JDDS. Saving appends the next
version; the IR is re-validated server-side before it is stored. Routes:
`/api/workflows` (list/create), `/api/workflows/[id]` (get/save/delete),
`/api/workflows/[id]/versions`.

---

## The dedicated mode

Graph Studio is a **dedicated sidebar mode** (like Bots), not a nav item inside
Agentic: `Alt+G` (or the mode switcher) switches the menu to Graph Studio, the
left sidebar becomes the mode panel (**Workflows** browser + **Nodes** library),
and the workspace opens. The shell hides the top bar and the chat dock for this
tab, so the canvas gets the whole page.

## Phase status

| Phase | Scope | Status |
| --- | --- | --- |
| **1 — Foundation** | Workspace, canvas, custom nodes, editor state, persistence, dedicated mode | **Implemented & verified** |
| 2 — Canonical IR & node system | IR, registry/SDK, typed ports, validation, patches | **Implemented in TS AND Python** (editor registry + runtime registry in lockstep); migrations seam live |
| **3 — Compiler & execution engine** | IR → plan, deterministic executor, inspection, isolation | **Implemented & verified** |
| **4 — Control flow, scheduling & triggers** | Control-flow node pack, unattended schedules, webhook trigger, run recovery | **Implemented & verified** (distributed/Fabric-backed durability is the remaining piece) |
| **5 — Finance & quant node library** | Market-data + indicator node executors | **Implemented & verified** (first pack: market data, indicator, returns, z-score, volatility) |
| 6 — Backtest & simulation | Strategy graphs, metrics | Not started (engine exists: `quant/`) |
| 7 — AI agents & Chat-to-Graph | Agent nodes, chat→IR | Not started (agent runtime exists) |
| 8 — Paper trading & safety | Execution adapter, risk controls, modes | Not started (modes + trading side-effect class already enforced by the compiler) |
| 9 — Advanced engineering | Subworkflows, debugging, diffing | Not started |
| 10 — Hardening & verification | Tests, security, observability | Partial: Phase 3/4 add runtime safety tests; observability is next |

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
| `store.py` | Run rows on `agent-memory.db` (a `running` row at start, the full result at finish). |
| `service.py` | Compile / run_sync / start-run-on-a-thread / poll / cancel. |
| `bootstrap.py` | Idempotent boot wiring; `routers/graphs.py` exposes `/graphs/*`. |

**Trust boundary.** `POST /api/workflows/[id]/runs` (Next.js) loads the
authoritative persisted version — the client never supplies the IR — and forwards
it with `testRun: true`. The runtime independently enforces the envelope: a
**test run never performs write, network or trading effects**, and a node whose
declared capabilities were not granted is refused. Editor visibility is not
authorization.

**Determinism.** Executors are pure; the scheduler orders each layer by node id;
node inputs come from succeeded upstream writers only (a node whose required
input never materialized is `skipped`, never run with a null placeholder). Two
runs of the same graph with the same inputs produce identical outputs (tested).

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
| `logic.wait` | Bounded pause; a TEST run allows at most 5 s (compiler-enforced `test_run_limit`). |
| `logic.stop` | Ends the run here; downstream nodes become `skipped`. |

**Loops are internal and bounded, never graph cycles.** The compiler still
refuses a cyclic graph; iteration is a node with a declared bound, which is what
"loops through explicitly defined runtime constructs" means.

**Schedules.** `WorkflowSchedule` (JDDS) stores cron + IANA timezone + a
precomputed `nextRunAt`; `src/lib/graph-studio/cron.ts` is a dependency-free,
timezone-aware 5-field cron evaluator (cached `Intl` formatters, 40-day search
bound). A 60 s in-process timer (started in `instrumentation.ts`) fires due
schedules through the SAME test-run dispatch as the UI. Missed fires follow the
schedule's policy — `skip` (advance only) or `coalesce` (run once now) — so a
closed app never storms on boot. Every fire records its outcome on the schedule.

**Triggers.** Manual (the toolbar / UI), scheduled (above), and a webhook-style
`POST /api/workflows/[id]/trigger`. The webhook deliberately runs inside the
TEST-RUN envelope: a trigger reachable without a secret must not be able to act
on the world (secret-signed webhooks are Phase 8/10 work).

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

**Honest data.** Every payload carries provenance (`provider`, `symbol`,
`interval`, `adjusted`, `rows`, `asOf`, `retrievedAt`). An empty vault is a
FAILURE with an actionable message ("fetch them first … the graph never
fabricates a price") — never a synthetic series, never a silent zero.

**Test-run policy.** A test run implicitly grants the read-only / local-compute
capabilities (`market.read`, `quant.compute`, `compute.safe`) so a finance graph
can be exercised from the UI, while write/network/trading nodes stay refused.

**Templates.** `Market scan (SMA z-score)` — stored bars → SMA(50) → z-score(20)
→ branch → result, plus a second output carrying the data provenance.

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
  envelope refuses trading/network/write regardless of the request). ✓
- The same workflow produces reproducible results for identical inputs. ✓

## Verification

Phase 1:

- `npx tsc --noEmit` — clean; full vitest suite green; `npm run build` succeeds.

Phases 3–4:

- `npx tsc --noEmit` — clean.
- `npx vitest run` — 332 files / 3469 tests pass (58 Graph Studio tests).
- `npm run build` — production build succeeds; `/api/graph-runs/*`,
  `/api/workflows/[id]/{runs,trigger,schedules}` and `/api/workflow-schedules/*`
  registered.
- Python: `python -m pytest python/tests/test_graph_*.py` — **55 tests pass**
  (model/registry/formula, compiler, executor, control flow, service, HTTP API),
  including full-stack API tests that boot the real service on a temp database.

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

## Known limitations (after Phase 5)

- **In-process durability.** A run is recorded before it starts and finalized
  after, and orphaned `running` rows are reconciled at boot — but a run does not
  survive a restart mid-run and is not distributed. Wrapping the executor in the
  Execution Fabric workers is the next durability step.
- Schedules tick while the app is up (a 60 s in-process timer); a fully
  headless/unattended deployment needs the same tick driven by an external cron
  (the operator route exists: `POST /api/workflow-schedules/tick`).
- `logic.wait` blocks its thread; the 30 s cap and the 5 s test-run cap keep that
  bounded, but long waits belong in the Phase 4+ durable path.
- Loop primitives operate on numeric arrays (documented); richer per-type
  iteration arrives with the finance/agent nodes.
- Execution history is still the run's result document; normalizing node
  runs/events into queryable tables is part of the Fabric work.
- `live` mode is settable in the IR but no executor honours it; the compiler
  refuses trading nodes without an explicit (paper/live) grant.

## Next milestone

**Phase 6**: quant research, backtesting and simulation — a strategy graph
(init → signal → sizing → entry/exit → portfolio simulation) compiled onto the
existing `harness/quant/` engine, with point-in-time data, costs/slippage,
trade-level accounting that reconciles with portfolio results, and a results
view whose metrics come only from the deterministic engine.
