---
title: Self-Evolution Roadmap — Round 4 Expanded — execution completion + the closed self-improvement loop
status: Draft
last-verified: 2026-10-19
---

# Self-Evolution Roadmap — Round 4 Expanded

**Who this is for:** anyone implementing or reviewing the program that makes
Eclipse **take an unfamiliar goal to a verified result, learn from its own runs,
diagnose why a task was not solved, propose a change to its own machinery, verify
the change on the benchmark, and land it under operator control** — plus the
reachability fixes that let it *attempt* the task at all.

**Two loops, not one.**

- **The product loop (W8):** goal → contract → plan → execute → observe →
  verify → complete/blocked, durably and across restarts. This is what makes
  Eclipse a general autonomous harness.
- **The meta loop (W0–W7):** observe → diagnose → propose → verify → land →
  measure. This is what makes the harness improve itself.

The meta loop acts on the product loop's failures. Neither replaces the other.

**What this is.** Round 1 (roadmap phases 0–12) built the harness machinery.
Round 2 (phases 13–20) made it reachable, sourced and producing. Round 3
(`construction-first-audit.md`) made it *construct* instead of refuse. Round 4
closed the self-repair loop. **Round 4 Expanded** adds the missing product-loop
centre (W8) and converts the remaining general-agent ambitions (W9–W15) into
completion and audit work on machinery that already exists.

**Corrected premise (measured 2026-10-18).** A general-agent program would build
W8–W15 as new subsystems. In this repository most of them are already present:
`tasks/` (plan/task DAG, criteria, atomic claim, checkpoints, cancel cascade),
`fabric/` (durable queue, workers, retries, DLQ, locks, crash recovery),
`event_system/` (durable journal), `orchestration/`, `delegation.py` (narrowed
child actors, budgets), `team/` (specialists, independent reviewer,
conflicts/repair), `artifacts/`, `security/` (policy, sandbox, approvals),
`model_runtime/`, `evaluation/`, and the `eclipse_memory/` +
`skills/` learning stores. The gap is **not layers**. It is that the default chat
path enforces neither a goal contract nor verified completion, and the self-repair
loop is not closed against the failures that path produces. W9–W15 are therefore
**completion/audit workstreams on existing owners**, not new infrastructure.

**Method.** Every claim below is traced to `file:line` in the current tree
(measured 2026-10-18). It does not rebuild what exists; it wires, closes and
measures. Where a program already owns a piece (evaluation, recovery,
skills-learning, self-editing), the plan cites it as the socket and adds only
the missing connector.

---

## 0. The worked example that motivates this round

A user asked for a **multi-zone world clock** ("New York, Karachi, London") on
the dashboard. The run failed, and the failure is *not* a data or model failure.
Verified chain:

| Step | Code | What happened |
|---|---|---|
| 1 | `src/lib/harness/chat-capability.ts` → `code/request_intent.py` | The turn carried no directive + software-object pair in one clause, so the verdict was `not_code` → **no `autonomy`**, so the run kept `ECLIPSE_AGENT.tools` |
| 2 | `agents.py:299-531` | `ECLIPSE_AGENT` carries `*UI_TOOLS` (`:498`) but **no** code/terminal/write tool — so `ui_*` was callable, `workspace_patch_apply` was not |
| 3 | `ui/mode.py:103-153` | `ui_classify_request` returned **`compose`** — `"dashboard"` is a `_COMPOSE_SIGNALS` entry (`:63`), and with no engineer phrase the no-signal default is also Compose (`:148-153`) |
| 4 | `ui/mode.py:148-153` | That Compose decision carried `matched_components=[]` — **a verdict with no witness** |
| 5 | `ui/engineering.py:88-96` | `ui_start_engineering` refused because it trusts the label: `if decision["mode"] == "compose": return {"created": False, … "no engineering task was created"}` |
| 6 | `ui/catalog.py` | No clock component exists; `mp-hours`/`market-status` are single-venue |

Every link is individually reasonable. The **composite** is a defect: a
misclassification became an authoritative refusal, and the turn left no durable
signal that it had, so nothing in the system could learn from it.

Two structural observations generalise this:

1. **Two independent deterministic classifiers can disagree and neither consults
   the catalog.** `code/request_intent.py` decides the *surface* (autonomy);
   `ui/mode.py` decides the *method* (compose/engineer). They share no fact.
2. **A refusal is not a failure.** `eclipse_memory/mistakes.py` detects
   `tool_failure`, `missing_source`, `unsupported_claim`, … but there is **no
   category** for "the request was routed to a path that could not satisfy it",
   and `recovery` only subscribes to `tool.failed`/`run.failed`/… — a clean
   refusal emits none of those. So the single richest signal for self-repair
   (a task that did not get done) is invisible to the learning layer.

---

## 1. Goal, stated as measurable outcomes

"Smart, autonomous, learns and solves its own problems, does what the user
asks" is operationalised as numbers on the standing evaluation gate
(`python/harness/evaluation/`), each currently unmeasured or un-gated. **Do not
judge progress by tool, skill or agent counts.**

| Metric | Definition | Target |
|---|---|---|
| `end_to_end_task_success` | benchmark tasks completed **and verified**, not merely answered | ↑ |
| `requirement_completeness` | share of the goal contract's deliverables actually produced | → 1.0 |
| `misroute_rate` | share of runs whose final surface could not satisfy the request (a refusal/wrong-method, detected deterministically) | ↓ toward 0 |
| `escalation_correct` | share of novel-capability requests that produce *some* constructive route (compose-with-witness, engineer task, acquisition plan) rather than a bare refusal | → 1.0 |
| `recovery_success` | failures that end in a verified result after bounded recovery (already gated) | → 1.0 |
| `capability_acquisition_success` | missing-capability incidents that end in a granted, validated capability or a working alternative | ↑ |
| `self_repair_precision` | share of proposed self-changes that pass the gate without a critical regression | → 1.0 |
| `time_to_repair` | wall-clock from a durable incident to a verified promotion candidate | measured, trending down |
| `regression_rate` | share of landed self-changes that later trip a gate | → 0 |
| `cost_per_success` / `time_per_success` | tokens + money + elapsed per verified task | measured, trending down |
| `unauthorized_action_rate` | policy violations in the defined suite | **0** |

**Non-goals (unchanged, deliberate):** unsupervised self-modification (every
harness change is operator-confirmed — invariant §5.3), fabricated data (never),
a second runtime/queue/database, and any capability that cannot be verified is
published as **unmeasured**, never claimed.

---

## 2. What already exists (the sockets — do not rebuild)

This program is *connective tissue*. The hard parts are built:

| Concern | Owning module (exists) | Role in round 4 |
|---|---|---|
| Deterministic routing | `code/request_intent.py`, `ui/mode.py` | W0 makes the second catalog-aware and shares one capability-fit fact |
| Composable UI + engineer escalation | `ui/catalog.py`, `ui/engineering.py`, `ui/tools.py` | W0 fixes the false-refusal path |
| Run traces / observability | `persistence.py`, `run_observability.py`, `event_system/` | W1 reads the outcome envelope; W1 emits a construction refusal event |
| Deterministic mistake detection | `eclipse_memory/mistakes.py` (`CATEGORIES`, `capture_mistakes`) | W1 adds routing/refusal categories |
| Failure vocabulary + hot path | `recovery/{taxonomy,signature,controller,hotpath}.py` | W1/W2 reuse signature + incident store |
| Capability discovery | `recovery/discovery.py` (`CapabilityIndex`, `acquisition_plan`) | W5 wires it to the executor's rungs |
| Incident → inert skill | `recovery/learning.py` (`incident_to_candidate`, `promote_incidents`) | W6 |
| Self-improvement evaluation | `evaluation/improvement.py` (`ImprovementProposal`, `propose_improvements`), `evaluation/regression.py` (`DEFAULT_GATES`), `evaluation/gate.py` | W3 is the verification spine |
| Construction benchmark | `evaluation/datasets/construction_v1.json`, `scripts/test-evals.js` | W3/W7 extend with routing scenarios |
| Self-edit landing | `code/worktree.py`, `code/patch.py`, `code/promotion.py`, `code/selfhost.py` (`classify_landing`, `guarded_land`) | W4 — propose/verify/dry-run; land stays operator-confirmed |
| Learning review queue | `learning_review.py`, `skills/learning.py`, `learning_graph.py` | W6 |

### 2.1 The general-harness workstreams against the tree

Legend: **Built** = the subsystem exists and is tested; **Partial** = the pieces
exist but the lifecycle is not closed; **Missing** = genuinely new work.

| Workstream | Reality | Evidence | Round-4 work |
|---|---|---|---|
| W8 substrate: durable state, checkpoints, resume, cancellation | **Built** | `tasks/` (`manager.py`, `scheduler.py`, `dag.py`, `store.py`), `fabric/` | Use, don't rebuild; the **goal contract + verified completion** is the new part |
| W9 capability discovery/acquisition lifecycle | **Partial** | `recovery/discovery.py` (`CapabilityIndex`, `acquisition_plan`); install/build rungs return `strategy_requires_caller` | Wire validate/register/retry rungs |
| W10 replanning, recovery, budgets | **Built/partial** | `replan.py`, `recovery/{controller,hotpath,executor,envelope}.py` | Add progress/stuck metrics to the task loop |
| W11 multi-level learning (L1–L5) | **Partial** | L1/L2 `mistakes.py` + `skills/learning`; L4/L5 `evaluation/improvement.py`; L3 absent | Add L3 strategic learning + one lifecycle |
| W12 multi-agent orchestration | **Built** | `team/` (specialists, reviewer, conflicts), `delegation.py` (narrowed actors, budgets), `orchestration/` | Adopt only where the benchmark shows a gain |
| W13 tool/integration reliability | **Partial** | `test_advertised_tool_admission_all.py`, `test_registry_visibility.py`; no per-tool contract/health proof | Add capability contracts + audit |
| W14 evidence/verification | **Built for finance; partial general** | Evidence engine, receipts, advisory gate; no task-type-keyed verifier | Unify verification by task type |
| W15 autonomy tiers | **Built** | `code/policy.py` (`plan_only`, `edit_verify`, `approve_external`), `AutonomyEnvelope`, single-use approvals | Map tiers; make safe work autonomous by default |

All twelve infrastructure components named in §5 of the external brief already
exist: task store (`tasks/`), event journal (`event_system/`), task graph
(`tasks/dag.py`), tool registry, model gateway (`model_runtime/`), memory
(`eclipse_memory/`), skill lifecycle, evaluation, recovery, policy/sandbox,
observability, artifacts. **No new database, queue, runtime or orchestration
framework is introduced by this program.**

---

## 3. The two loops

### 3.1 The product loop (W8) — a goal to a verified result

```
USER GOAL
  │
  ▼
[1 CONTRACT]  objective · deliverables · constraints · acceptance tests
  │           (new: the chat path must create one before work)
  ▼
[2 PLAN]      dependency-aware tasks (tasks/dag.py), durable (tasks/store.py)
  │
  ▼
[3 EXECUTE]   tool calls on the ONE registry, inside the autonomy profile
  │           checkpoints after each durable boundary (run_lineage.py)
  ▼
[4 OBSERVE]   real tool results, errors, artifacts — never the model's claim
  │
  ▼
[5 VERIFY]    task-type verifier: tests/build/diff for code; sources for
  │           research; artifact + contents for documents; state for workflows;
  │           provenance + freshness for finance
  ▼
[6 COMPLETE]  only with recorded evidence; otherwise BLOCKED with the exact
              missing capability/access/failure — never a confident "done"
```

`execute_run` stays the executor; `tasks/`, `fabric/`, `event_system/` and
`artifacts/` stay the owners of their responsibilities. W8 adds the contract, the
explicit state machine and the **verified-completion rule**, not a second loop.

### 3.2 The meta loop (W0–W7) — Observe → Diagnose → Propose → Verify → Land → Measure

One loop, six seams, all over existing machinery:

```
   RUN (chat / task / job)
     │  outcome envelope: intent, surface, allowlist, refusal code, capability gap
     ▼
 [1 OBSERVE]  mistakes.py (new routing categories) + a construction-refusal event
     │        → durable RecoveryIncident (existing store) with a stable signature
     ▼
 [2 DIAGNOSE] recovery/diagnosis.py over the incident
     │        root cause classes: VOCABULARY_GAP · CATALOG_GAP · POLICY_GAP · CAPABILITY_ABSENT
     ▼
 [3 PROPOSE]  a HARNESS change, minimal and typed:
     │        · vocabulary addition in request_intent.py / ui/mode.py
     │        · a catalog-aware escalation rule
     │        · a new skill (procedure) via skills/learning
     │        · an acquisition plan (scaffold_kit / skill_install / engineer task)
     │        produced as a worktree patch (code/patch.py) OR an inert skill draft
     ▼
 [4 VERIFY]   evaluation/improvement.py: apply on the worktree, run the suite,
     │        accept only if target_dimension ↑ AND detect_regressions(DEFAULT_GATES) clean
     ▼
 [5 LAND]     code/promotion.py (single-use, digest-bound) + code/selfhost.py
     │        (restart/build verdict; authority files refused) — OPERATOR-CONFIRMED
     ▼
 [6 MEASURE]  phase-20 registry: misroute_rate, self_repair_precision, time_to_repair …
```

The loop **proposes and verifies autonomously** (steps 1–4 are unattended inside
the existing `AutonomyEnvelope`); it **lands only on a person's confirmation**
(step 5). That split is what makes "learns and solves its own problems" real
without violating invariant §5.3.

---

## 4. Workstreams

Each workstream names repo-mapped changes, a dependency, and a runnable gate.
Ordering is given in §6. **W8 is the product loop** (the new centre); W0–W7 are
the meta loop; W9–W15 close existing lifecycles around both.

### W8 — Goal execution completion (the new centre)

**Goal:** an ordinary request — not just a `/eclipse` code task — is carried to a
verified result, or to an honest, evidenced blocker. The model's prose is never
accepted as completion.

- **W8.1 — Goal contract.** A deterministic intake turns the request into
  `objective`, `deliverables[]`, `constraints[]`, `acceptance[]` and a
  `taskType`; ambiguous requests ask one clarifying question rather than
  guessing. It is attached to the durable task, not just the prompt.
- **W8.2 — The default durable path.** The chat runtime chooses between a single
  turn and a durable task using the contract (long-horizon, multi-deliverable,
  or resumable work ⇒ task), instead of leaving `task_create` to the model's
  discretion. Reuse `tasks/scheduler.py`; do not add a queue.
- **W8.3 — Explicit state machine + checkpoints.** `queued → planning → running
  → verifying → completed`, with `blocked | failed | cancelled |
  awaiting_approval`; checkpoints at each durable boundary (`run_lineage.py`);
  resume after a process restart is proven by test.
- **W8.4 — Verified completion.** A `TaskVerifier` keyed by `taskType`:
  code ⇒ diff + tests + build; research ⇒ sources + claims; document ⇒ artifact
  exists + required sections; workflow ⇒ observed state change; finance ⇒
  provenance + freshness. `task_completed` is refused without evidence.
- **W8.5 — Honest blocked state.** When verification cannot pass, the task ends
  `BLOCKED` with the exact missing capability/access/failure and the permitted
  next routes — the same construction-first rule, applied to completion.
- **W8.6 — Budgets.** Contract-level caps for elapsed time, tool calls, tokens,
  model cost, parallel workers and external requests; exceeding a cap is a
  `BLOCKED` outcome with evidence, never a silent truncation.

**Acceptance (the round's headline test):** ask Eclipse to build a small app,
run it, discover a deliberate defect, repair it, rerun its tests and deliver the
artifact; then kill the process mid-run and prove it resumes from a checkpoint
without repeating side effects. Gates: new `python/tests/test_goal_completion.py`
+ the benchmark families in §6.1.

**Status — W8.1/W8.4/W8.5/W8.6 landed 2026-10-18 (first slice).** The goal
contract is data on the task (`GoalContract` + `taskType`, additive columns);
`goal.py::intake_goal` is the deterministic intake (one clarifying question on
ambiguity; `durable_decision` is the W8.2 rule) and the `create_goal` tool
creates + starts a contract-bearing task. `verification.py::verify_task` is the
task-type verifier (code/research/document/workflow/finance/general) reading
run-produced evidence — zero-exit verification records, delivered artifacts,
recorded sources — never prose; a task without a `taskType` keeps the exact
pre-W8 contract. The scheduler refuses `task_completed` without the evidence: a
failed verification retries with the missing evidence named and then ends
`BLOCKED` (`BlockedReason.VERIFICATION`); contract budgets end `BLOCKED` with
the violated cap. The `run_complete` checkpoint carries the verdict, and the
build-break-repair-deliver + crashed-worker-resume acceptance runs in
`test_goal_completion.py` (4 cases; the tasks/recovery/UI/evaluation family is
572 passed). **W8.2 landed 2026-10-18:** `goal_runtime.py` + the wrapper
installed by `install_task_layer` make the chat path durable-by-default — a
durable request creates the goal task before the run (the run is its first
attempt) and settlement verifies afterwards, re-queueing a bounded repair
attempt for the scheduler (`test_goal_runtime.py`, 10). **Cap classes completed
2026-10-18:** `max_model_steps` is enforced post-run and `max_parallel_workers`
rides the scheduler's EXISTING per-agent cap (`metadata.maxConcurrency`); model
cost and external requests remain deliberately UNDECLARED because the runtime
cannot measure them — an unenforceable cap is not invented.

### W0 — Reachability and routing fidelity (the observed defect class)

**Goal:** a request that needs a component the catalog does not have can never
end in a false "nothing to engineer" refusal.

- **W0.1 — A Compose verdict must cite a witness.** In `ui/mode.py`, a
  `compose` result is invalid unless `matched_components` is non-empty (at least
  one registered id plausibly satisfies the request). No witness ⇒
  `capabilityGap` (a new outcome), never Compose.
- **W0.2 — `ui_start_engineering` re-checks the catalog itself.** In
  `ui/engineering.py::start` (and the `ui/tools.py` wrapper), Compose *plus* an
  empty witness set must **escalate**, never return the current
  `"no engineering task was created"` (`engineering.py:95`).
- **W0.3 — One capability-fit fact, two consumers.** Add a deterministic
  `capability_fit(request) -> {satisfied, witness, gap}` in the UI catalog layer
  that `ui/mode.py` and, where relevant, `code/request_intent.py` both read, so
  a "software object the catalog cannot satisfy" is a construction signal in
  **both** classifiers. (No model calls; the catalog is data.)
- **W0.4 — Classifier vocabulary for novel UI.** Add the missing engineer
  signals for a *named* thing the catalog lacks (e.g. any request naming a
  widget/component/page that resolves to no id ⇒ Engineer/Both), keeping
  "restyle/rearrange an existing widget" as Compose.
- **W0.5 — The prompt names the loop.** `prompts.py` already says "a missing
  tool is a routing problem"; add the UI-specific sentence: if a requested
  widget/page is not in the catalog, escalate — do not answer "cannot".

**Acceptance:** the exact clock request files an engineering task (or composes a
witness); a unit test asserts `ui_start_engineering` cannot return the false
refusal while `matchedComponents == []`; the existing Compose cases (add/move a
registered widget) still classify Compose. Gates: new routing fixtures + `tsc`,
`vitest`, `pytest`.

**Status — W0.1 + W0.2 landed 2026-10-18.** `mode.py` gained
`assess_capability` (clause-scoped additive detection + catalog witness) and a
`capabilityGap` decision field; `engineering.py::start` re-checks the catalog and
escalates instead of refusing; clock fixtures live in `test_ui_mode.py` and
`test_ui_engineering.py`. Evidence: UI pytest family 101 passed; eval gates ALL
PASS; vitest 3474/3475 (the one failure is the pre-existing `graph-canvas.tsx`
line-ending guard).

### W1 — Observation: every run becomes a diagnosable trace

**Goal:** a task that did not get done leaves a durable, signed, root-causable
incident — without inventing failures.

- **W1.1 — New mistake categories** in `eclipse_memory/mistakes.py`:
  `misrouted_request`, `capability_gap_refused`, `composed_without_witness`,
  `escalation_refused`, `intent_ambiguity`. Each is derived from the run's
  persisted classification payload + outcome, deterministic, evidence-bearing
  (same rule as the existing nine categories).
- **W1.2 — A construction-refusal event.** Emit a canonical event when a run
  ends in a refusal of a *constructible* request, and subscribe `recovery` to it
  (`recovery/bootstrap.py`), so it becomes a `RecoveryIncident` like any other.
- **W1.3 — The outcome envelope.** Persist per run: intent verdict, resolved
  surface/allowlist, the refusal code, and the capability-gap id (mostly
  present across `run_observability.py`/events — this names it as one record).

**Acceptance:** replaying the clock trace (scripted, offline) produces one
incident with a stable `failure_signature`, category `misrouted_request`, no
model call. Gate: `node scripts/test-python.js`.

**Status — W1.1 + W1.2 landed 2026-10-18.** Five categories are declared and
detected from the persisted UI tool texts (`test_routing_mistakes.py`); the
`ui.capability_gap` event is registered (`event_system/registry.py`), maps to
`FailureKind.CAPABILITY` (`recovery/taxonomy.py`), is subscribed by
`recovery/bootstrap.py`, and is emitted by an escalation
(`test_routing_incident.py`, `test_ui_engineering.py`). The classifier/tool text
now exposes its witness so the detection is deterministic.

**Status — W1.3 landed 2026-10-19 (the outcome envelope).** The four facts are
now ONE record: `python/harness/run_outcome.py` builds a derived, read-only
envelope naming the intent verdict, the resolved surface + allowlist, the
refusal code and the capability gap (`GET /runs/{id}/outcome`). Three of the
four were already persisted (the run row's agent and terminal error code, the
`prompt.plan` event's surface/allowlist summary, the `ui.capability_gap` event
plus its `recovery.decided` incident id); the **intent verdict had no home**
(it died with the tool result), so the `ui_classify_request` tool now records
it once per run — the FIRST verdict wins, because it is the routing. The
module owns its own `RunOutcome` table (the `run_lineage.py` pattern), so the
ratcheted `persistence.py` does not grow. A fact that was never recorded is
`null`: the envelope never guesses and never infers from prose. Tests:
`python/tests/test_run_outcome.py` (12). Owning doc
`docs/harness/architecture.md` (the execution graph); ADR-H241.

### W2 — Diagnosis → a typed, minimal harness change

**Goal:** the incident yields a *specific* proposed change, not a vague "try
again".

- **W2.1 — Root-cause classes** in `recovery/diagnosis.py` vocabulary:
  `VOCABULARY_GAP` (a word the classifier does not know), `CATALOG_GAP` (a
  component the UI layer lacks), `POLICY_GAP` (an allowlist/autonomy rule),
  `CAPABILITY_ABSENT` (no tool/system can do it).
- **W2.2 — `RoutingRepairProposer`** (new, small module under `recovery/` or
  `code/`): maps an incident to the minimal edit — a vocabulary addition in
  `request_intent.py`/`ui/mode.py`, an escalation rule, a skill draft
  (`skills/learning`), or an acquisition plan (`recovery/discovery.py`). The
  code edit is produced **on a worktree via `code/patch.py`**, never in place.
- **W2.3 — Reuse the improvement contract.** Express the proposal as
  `evaluation/improvement.py::ImprovementProposal` (target dimension + `apply` /
  `revert`), where `apply` runs the worktree patch.

**Acceptance:** a synthetic misroute fixture yields a proposed patch; applying
it flips the classification on the fixture; reverting restores the baseline.
Gate: `python/tests/test_self_repair_propose.py`.

**Status — W2.1–W2.3 landed 2026-10-18.** `recovery/routing_repair.py`
diagnoses `VOCABULARY_GAP` / `CATALOG_GAP` / `CAPABILITY_ABSENT` / `POLICY_GAP`,
emits a typed proposal with a `code.patch.PatchOp` for a vocabulary miss, and
verifies by activating the exact additive rule in memory through the existing
`ImprovementProposal` contract, then reverting. `recovery/diagnosis.py` gained
the four capability causes; `RecoveryService.propose_routing_repair` exposes the
proposal from a stored incident, read-only. Tests: `test_routing_repair.py` (11)
— the "missing a world clock" fixture, apply-flip-revert, the incident seam and
the diagnosis selection. (The file is `test_routing_repair.py`, not the planned
`test_self_repair_propose.py`.)

### W3 — Verification: no self-change lands without evidence

**Goal:** a proposed change is accepted only when the target metric improves and
nothing critical regresses — the existing anti-regression rule, now applied to
harness self-changes.

- **W3.1 — Routing scenarios in the benchmark.** Extend
  `evaluation/datasets/construction_v1.json` with the routing/refusal cases
  (novel widget, multi-zone clock, "scrape this site", "add a page", "restyle"),
  each a deterministic scripted trace through the real `execute_run`.
- **W3.2 — New dimensions + gates.** `misroute_rate` and `escalation_correct`
  in `evaluation/scoring.py`, gated in `evaluation/regression.py::DEFAULT_GATES`
  alongside `task_success`/`recovery_success`/safety/hallucination.
- **W3.3 — The loop runs the gate.** `evaluation/improvement.py` already does
  apply → suite → `detect_regressions`; point it at a worktree change and record
  the comparison as the proposal's evidence.

**Acceptance:** a proposal is accepted **iff** the suite comparison proves it;
a deliberately harmful proposal is rejected. Gate: `node scripts/test-evals.js`.

**Status — W3.1–W3.3 landed 2026-10-18 (classifier tier).** The versioned
`python/harness/ui/routing_benchmark_v1.json` (eight cases, including the clock)
is exercised by `test_ui_routing_benchmark.py`. `evaluation/routing.py` computes
`misroute_rate` and `escalation_correct`; `run_offline_gate` injects them into
the SAME threshold check and records the source in `SuiteResult.routing`. Both
are critical regression gates (`test_evaluation_routing.py`) and appear in the
release report.

**Status — the end-to-end tier landed 2026-10-18 (W3.2 complete).** Four of the
scenarios now also run through the REAL `execute_run` graph as evaluation tasks
(`datasets/routing_e2e_v1.json`, category `recovery`/`tools`): the invoker binds
the trial's real `UiService` + `TaskManager` (its own isolated store per trial),
registers the `ui_*`/`task_*` families, and the `ui` environment grades the REAL
resulting state — the engineering task the escalation created (with
`capabilityGap`), or its absence for a Compose verdict. A restored pre-W0 defect
fails the clock task on the real state, so a routing regression now fails the
release through the full path (`test_evaluation_routing_e2e.py`). Gate:
tasks=51, the four e2e tasks 100%, `misroute_rate=0.0`.

### W4 — Landing under operator control (wire the trigger; keep the floor)

**Goal:** a verified self-repair surfaces as a reviewable change with proof, and
lands only through the existing single-use, digest-bound promotion.

- **W4.1 — Surface the pending self-repair.** In the Code Tasks / recovery
  console, show the proposal, the suite comparison, and the touched files.
- **W4.2 — Land through `code/promotion.py`** (`build_preview` →
  single-use approval → `apply_promotion`) with `code/selfhost.py::guarded_land`
  deciding restart/build and **refusing authority files** (the frozen set:
  `code/policy.py`, `skills/permissions.py`, `mcp/approvals.py`,
  `scripts/check-all.js`).
- **W4.3 — Rollback receipt.** Reuse `rollback_promotion`; report the outcome.

**Acceptance:** a verified self-repair appears as a promotion card; landing a
change to an authority file is refused; rollback restores the tree.

**Status — W4 landed 2026-10-18.** `recovery/routing_landing.py` prepares a real
disposable worktree + patch, refuses an authority target with
`selfhost.classify_landing`, registers the workspace under
`routing-repair-<incidentId>`, and returns the existing promotion preview.
`POST /recovery/incidents/{id}/routing-repair` exposes it; the recovery console
renders the existing `PromoteChange` card (single-use approval → apply →
restart/build verdict → rollback). The promotion preview/apply routes now refuse
an authority target before creating or consuming an approval. Tests:
`test_routing_landing.py` (6: prepare, reuse, apply + rollback, authority refusal,
non-landable proposal, missing incident) and the route refusal in
`test_code_promotion.py`.

### W5 — Acquisition rungs: when the capability is genuinely absent

**Goal:** "no component/tool for X" leads to a constructive route, never a bare
refusal.

- **W5.1 — Wire `recovery/discovery.py::acquisition_plan`** into the executor's
  strategy handlers (currently `strategy_requires_caller`), so
  `CAPABILITY_ABSENT` produces an ordered plan (`use` → `enable` → `install` →
  `build` → `alternative`), mutations approval-flagged.
- **W5.2 — Route to real surfaces:** `scaffold_kit` (a kit shape),
  `skill_create`/`skill_install` (a procedure), `ui_start_engineering` (a UI
  component), the plugin SDK (a tool). Each keeps its own gate.

**Acceptance:** a missing-capability scenario produces an acquisition plan with
at least one permitted route; nothing self-grants.

**Status — W5.1/W5.2 landed 2026-10-18 (first slice).** `recovery/acquisition.py`
implements the ordered lifecycle and names every step's surface
(`existing_tool`, `skill`, `plugin`, `scaffold_kit`, `engineering`,
`alternative`, `operator`). `run_with_recovery` now passes default capability
handlers (`substitute_tool`, `alternative_implementation`, `fix_dependency`);
they hand back the typed plan and **stop** the loop with
`acquisition_required` instead of repeating the same failed call. The executor
honours the handler's `stop` sentinel and records the plan on the operation
ledger. `POST /recovery/incidents/{id}/acquisition` exposes the plan; the
recovery console shows it. Tests: `test_recovery_acquisition.py` (11), including
approval gating, honest `unverified` validation, the stop path and the
`run_with_recovery` wiring. Remaining: the caller-bound `install`/`build`
handlers (skill/plugin/scaffold_kit/engineering) are named surfaces that return
`requires_caller` until a caller supplies the handler and the original task
checkpoint.

### W6 — Closing the learning loop (skills + memory)

**Goal:** the *same* class of request is handled faster next time by a learned,
inert-until-promoted procedure.

- **W6.1 — Encode procedures.** When a construction/escalation succeeds,
  `recovery/learning.py::incident_to_candidate` (already wired to the existing
  learning store) yields an inert `LearningCandidate`; a successful widget-add
  becomes a `successful_procedure` skill (including the size-budget constraint
  and the `registry.tsx` registration shape — the thing the clock run had to
  re-derive).
- **W6.2 — Surface + promote** through `learning_review.py` and the existing
  evaluation/operator gate.

**Acceptance:** a repeated novel request hits the learned procedure; the
candidate is inert until promoted; measured.

**Status — W6 landed 2026-10-18.** `skills/procedures.py` encodes a successful
UI construction sequence (a run whose `ui_register_engineered_component`
succeeded — the registration actually ran) as an inert `successful_procedure`
candidate on the EXISTING learning store, carrying the re-derived know-how:
implement in `src/lib/dashboard/widgets.tsx` within the 1200-line ceiling,
register in `registry.tsx`, add the icon name to its `ICONS` map, verify, then
register in the catalog and Compose. First occurrence → candidate (one stable
signature dedupes every construction); repeat (the `LearningRecurrence` ledger
sees the construction key twice) → the post-run review opens the draft through
the SAME `propose_draft` the operator route uses (`draft`/`not_evaluated`,
never enabled); a second review is a no-op. A resolved CAPABILITY incident
yields the SAME candidate via `recovery/learning.py::incident_to_candidate`
(capability gaps are construction work, not generic failure recovery).
`draft.py` now renders each step's `detail` into the SKILL.md instructions, so
the constraints survive into the draft. Tests:
`test_construction_procedure.py` (11: detection, encoding, first-occurrence
candidate, repeat → inert draft, no auto-enable, tool-evidence filtering,
review surfacing, incident-path signature equality, dedupe). Measured
acceptance: the repeated request class finds and drafts the learned procedure;
no skill is enabled anywhere in the automatic path (operator promotion
unchanged).

### W7 — Measurement and the honest capability statement

- **W7.1 — Add the §1 metrics** to the phase-20 registry and the standing gate.
- **W7.2 — Publish measured/unmeasured honestly** in the capability statement
  (an unmeasured class is never claimed).
- **W7.3 — Report `time_to_repair` / `self_repair_precision`** on the recovery
  console.

**Acceptance:** the metrics in §1 appear on the gate; the baseline is recorded
before and after each workstream.

**Status — W7 landed 2026-10-18 (metric block).**
`evaluation/repair_metrics.py` computes the metric block from real records —
`time_to_repair_ms` and `self_repair_precision` from recovery incidents,
`requirement_completeness` from goal-contract task criteria, `cost_per_success`
and `unauthorized_action_rate` from evaluation trials — and the gate report
prints it, with every dimension that has no samples rendered `UNMEASURED`
(never fabricated). `test_evaluation_repair_metrics.py` (6) pins the arithmetic,
the unmeasured rule and the report line. **Operator surface added 2026-10-18:**
`GET /recovery/metrics` reports the block from the REAL runtime stores
(incident outcomes from the `action="outcome"` attempts; goal-contract
criteria), read-only.

### W9 — Capability acquisition lifecycle (complete W5)

Discovery already plans; the lifecycle is not closed. Extend
`recovery/discovery.py` into the ordered stages **discover → assess → propose →
acquire → validate → register → retry the original task from its checkpoint**.
Search existing tools, skills, installed integrations and alternatives before
building anything. New capabilities need a typed contract, permissions, a health
check and an executable acceptance test; a failure preserves the task state and
names the exact dependency, credential, licence or OS permission missing. No
stage self-grants; each mutation keeps its approval gate.

**Acceptance:** a missing-capability benchmark task ends in a granted + validated
capability or a working alternative, and the original task resumes.

**Status — W9 first slice landed 2026-10-18.** The lifecycle
(discover → assess → propose → acquire → validate → retry) is implemented over
the existing `CapabilityIndex`; a proposal carries surfaces, readiness, approvals
and exact missing facts (`unknown: no source, credential or dependency was
supplied` when the caller supplied none). Discovery now ignores grammar
stopwords. `validate_step` reports `unverified` without a contract test, and
`retry_task` requires a caller callback/checkpoint rather than inventing a
resume. The read-only use/alternative path is complete.

**Status — the production caller landed 2026-10-18 (W5/W9 complete for the
routable surfaces).** `recovery/acquire_handlers.py` binds the caller half: a
`build` step routes through the real `ui_start_engineering` gate (its own plan →
the original task parks WAITING for an explicit checkpoint resume) or creates a
same-plan code-agent capability task; the original task gains a REQUIRES
dependency and is parked BLOCKED, so the existing DAG resumes it when the
capability task completes — the completion IS the validation. The scheduler
records the new `waiting` outcome without retrying a parked task. **Operator
surface added 2026-10-18:** `POST
/recovery/incidents/{id}/acquisition/execute` runs ONE step through the real
surfaces (approval-gated for mutations; parking never re-executes the step) and
`.../resume` resumes the original task from its durable checkpoint. **Real
install routes added 2026-10-18 (W5/W9 remainder):** an operator-supplied fact
selects the existing gate — `source` (GitHub) → the REAL `install_from_github`
after consuming its single-use, digest-bound `skill_install` approval (the
handler creates the pending request and returns `approval_required` when it is
not granted), `pluginPath` → the ONE plugin platform (`operator=true`,
`enable=false`; enable is its own approved step), `kitId` → a durable code task
whose verified completion is the validation. Without a fact the step still hands
back the exact missing information; nothing self-installs or self-enables
(`test_recovery_install_handlers.py`, 8).

**Status — the Capability Builder landed 2026-10-19 (W9 build rung).** A
missing reusable analysis now goes through `capability_request` →
`capability_build`: a validated manifest, implementation and contract test are
written under `.black-eclipse/capabilities/`, verified in the existing PTC
sandbox, and a pure workspace recipe auto-activates only on a pass. Active
recipes join the existing `code/recipes.py` registry, so `analysis_run` reuses
them immediately; three consecutive failures disable the version. Effectful
kinds (tool/skill/UI/plugin/harness) route to their existing approval-gated
surfaces. Rollback/retire are versioned. **UI loop landed 2026-10-19:** the chat
`capability.*` lifecycle renders as one `CapabilityCard` (need, surface, version,
test counts, failed checks, exact stderr, activation state) and Capability
Studio › Generated lists the same records with operator activation /
deactivation / rollback / retire routes. **Effectful hand-offs + retry landed
2026-10-19:** `capability_build` routes tool/skill/UI/harness/plugin kinds to
their existing owner (`capabilities/handoff.py`), and activation resumes the
original durable task from its checkpoint when it is parked; a failed generated
recipe records a `capability_failure` recurrence for the learning loop.
**Sandbox tool RPC landed 2026-10-19:** analysis programs can call the three
read-only `eclipse_tools` bindings through validated, memoized replay; fetched
payloads stay in the sandbox (ADR-H235). **Adapter authoring landed 2026-10-19:**
`capability_adapter` writes a reviewable, disabled broker/API plugin draft
(validated manifest, generated code, README) and never installs or enables;
activation stays operator-owned (ADR-H238). **Built-in catalogue landed
2026-10-19:** `GET /capabilities/builtins` + the Studio read-only built-in
listing. Owning doc `docs/harness/capability-builder.md`;
ADR-H225/H226/H231/H232/H235/H238.

### W10 — Adaptive planning and stuck-loop control

Extend `replan.py` and the recovery controller so the loop distinguishes routing
errors, missing capabilities, invalid arguments, tool/infrastructure failures,
bad assumptions, implementation defects, failed verification, external outages,
policy blocks and ambiguity. A repeated failed action must never repeat unchanged:
the next attempt is materially different, and **stuck-loop detection** (no
progress across N attempts, exhausted budget) escalates with the actual blocker.
Reuse `RecoveryBudget`; add progress metrics to the task loop.

**Acceptance:** a benchmark failure with a flaky dependency recovers with a
different strategy; an impossible one stops with an evidenced blocker, not a loop.

**Status — W10 landed 2026-10-18 (stuck-loop slice).** `recovery/progress.py`
tracks each attempt's (tool, args, failure-signature) triple and the failures
since the last success: the hot path never retries an identical failed call
again, a loop with no progress across N attempts appends a `STUCK LOOP`
directive naming the actual blocker, and the task scheduler refuses to spend
retries on consecutive identical failures (`no progress: the same failure (X)
recurred N times unchanged`), so an impossible task stops with its real blocker
instead of looping (`test_recovery_progress.py`, 8).

### W11 — Multi-level self-evolution (L1–L5)

One measurable lifecycle over the existing stores, not a second learning engine:

| Level | Improves | Owner (existing) |
|---|---|---|
| L1 episodic | records what happened | `mistakes.py`, run traces |
| L2 procedural | reusable skills | `skills/learning.py`, `learning_review.py` |
| L3 strategic | planning / routing / tool selection | **new** small strategy layer over `recovery/` + routing |
| L4 harness | routing/recovery/tool orchestration code | `evaluation/improvement.py` + `code/promotion.py` |
| L5 evaluation | which changes actually help | `evaluation/` frozen benchmark |

Each level has its own validation standard. A failed attempt is **evidence, not
proof of the fix** — no prompt rewriting or code change after every task.

**Acceptance:** a repeated browser-vs-API choice is learned at L3 and measured;
L4 proposals still require the W3 gate; L5 reports the delta.

**Status — W11 first slice landed 2026-10-18 (L3 strategic learning).**
`recovery/strategy_learning.py` derives a `StrategyPreference` (strategy +
observations + measured success rate) per failure signature from the EXISTING
`RecoveryIncident`/`RecoveryAttempt` ledger — minimum observations and a success
floor, deterministic tie-break, `None` on thin evidence (an unmeasured choice
stays unmade). `RecoveryService.preferred_strategy(signature)` exposes it
read-only; the browser-vs-API acceptance is pinned against the real ledger
(`test_recovery_strategy_learning.py`, 4). L1/L2 (mistakes + skills), L4
(`evaluation/improvement.py` + the W3 gate) and L5 (the frozen benchmark)
already exist. **Fed into the decision 2026-10-18:** `record_failure` promotes
the ledger's measured route to FIRST among the policy's own candidates — it
never adds a strategy the policy did not offer, so every safety invariant
(auth denials, non-retryable kinds, approval gating) is unchanged — and records
the evidence (`strategyPreference`) on the result (`test_recovery_strategy_learning.py`, 5).

### W12 — Multi-agent orchestration (adopt, do not expand)

`team/`, `delegation.py` and `orchestration/` already provide specialists,
dependency-aware subtasks, independent review, conflict resolution and narrowed
budgets. The remaining work is **adoption and measurement**: select a specialist
by capability, isolate context, reconcile structured results, cancel redundant
work, and use parallelism **only where the benchmark shows a quality/latency/cost
gain** over one agent.

**Acceptance:** a multi-step build delegated across 2–3 specialists scores better
than the single-agent baseline on the same frozen task; otherwise it is not used.

**Status — W12 landed 2026-10-18 (comparison harness + first measurement).**
`evaluation/team_benchmark.py` runs a frozen multi-step build BOTH ways on the
SAME task — one scripted `execute_run`, and the REAL team stack (`TeamService` →
A2A → `TaskScheduler` → `execute_run`) across 2–3 specialists, each subtask
executing its own deterministic script over a per-trial isolated store — and
grades both on the REAL resulting state. `experiments.multi_agent_compare`
returns both recorded suites, measured axes and a deterministic adoption
verdict: adopt only when quality does not regress AND wall clock improves by
≥15% or tool calls fall; an unmeasured variant decides nothing; cost/tokens are
published `UNMEASURED` for the scripted tier. Dataset `datasets/team_v1.json`
(2 tasks, each with both variants; the single-agent program also runs in the
standing gate). **First frozen-set measurement** (3 trials × 2 tasks): quality
1.0 vs 1.0 (6/6 measured), wall 1454 ms vs 2234 ms (+53.6%), tool calls 27 vs
30, model steps 33 vs 45 → **not adopted** — no measured gain. That is the
honest offline result: the evaluation tools execute synchronously in one event
loop, so parallel legs cannot overlap work while the team pays the plan/task
overhead. The harness is the gate for re-measurement on the live tier; nothing
in the default path routes work to a team. A restored defect (a silently
dropped subtask) FAILS the state grader, so the tier grades real work, never the
team's own status. Tests `test_evaluation_team_comparison.py` (13). ADR-H213.
**Live-tier wiring landed 2026-10-18:** `LiveTeamAgentInvoker` (the same real
stack with NO script pool — every subtask resolves the operator's real
`modelSettings` through the production `build_chat_model` path; without settings
every trial is `unmeasured`, never fabricated) and
`experiments.multi_agent_compare_live` (production `ServiceAgentInvoker` for the
single variant + the live team); token/cost axes are now published only when a
variant's REAL trajectories reported them (`measured_usage` — the scripted tier
still publishes unmeasured, never 0). Opt-in live smoke
`test_live_team_comparison_through_a_real_provider` (`HARNESS_TEAM_LIVE_IT=1`,
never in CI); tests `test_evaluation_team_live.py` (4 + smoke). The OFFLINE
verdict stands (not adopted); the live verdict is open until a run with a
configured provider and is published unmeasured until then.

### W13 — Tool and integration reliability

A registered name is not proof. Add a **capability contract** to every advertised
tool: stable identity, typed input/output, permission and side-effect metadata,
timeout/output bounds, error classification, health status and a test fixture.
Audit filesystem, terminal/process, code exec, Git, browser, API, database,
documents/OCR, vision, artifacts, scheduling and finance tools against it. The
existing advertised-but-dead guards stay; this extends them from *admission* to
*behaviour*.

**Acceptance:** a contract test per audited family; no tool is advertised as
available while its contract test fails.

**Status — W13 landed 2026-10-18 (contract audit + behaviour fixtures).**
`python/harness/tool_contracts.py` checks every registered tool: stable name,
typed input schema, valid permission/risk vocabulary, bounded timeout;
`audit_registry` is the release gate and all 886 registered tools pass
(`test_tool_contracts.py`, 13). Advisory gaps (untyped output, undeclared
effect metadata) are counted and named, never blocking. The audit found and
fixed two real metadata bugs (`computer_finance_prepare`'s invalid
`"critical"` risk; the timeout ceiling vs the deliberate 15-minute families).
**Behaviour fixtures landed 2026-10-18 (W13 complete):**
`python/harness/tool_fixtures.py` drives a representative REAL tool per audited
family (filesystem `read_file`, terminal `terminal_capabilities`, git
`git_status`, browser `browser_status`, api `source_rank`, artifacts
`artifact_list`, finance `get_source_health`) through the ONE `ToolRegistry`
with real contexts — offline, deterministic, and honest about degraded
environments (the browser fixture accepts a structured unavailable; the finance
fixture pins the `no_data` path). `test_tool_behaviour_fixtures.py` asserts
every audited family has a passing fixture AND every fixture's tool is on the
production registry. A live dependency health probe remains the operator-facing
check (`get_source_health`, MCP verify) — a static contract cannot probe a live
dependency, so it is not faked.

### W14 — Verification by task type

Make W8.4's verifier the one authority for "done", with the finance Evidence
Engine remaining the financial authority. Software ⇒ tests/build/diff; research
⇒ traceable sources + uncertainty; data ⇒ reproducible inputs/calculations;
documents ⇒ artifact + required sections; workflows ⇒ resulting state; finance ⇒
provenance, freshness and claim-to-evidence. Verification is independent of the
agent's self-report wherever a deterministic check exists.

**Acceptance:** each benchmark family has a verifier that can reject a plausible
but incomplete answer.

**Status — W14 landed 2026-10-19 (unified verification by task type).** The
verifiers now read the evidence the runtime REALLY writes, and each type has
the rule W14 states: `research` ⇒ traceable sources, a claim backed by recorded
evidence and the uncertainty RECORDED (a partial answer that names no open gap
is refused); `document` ⇒ the artifact AND every section the contract required
(the sections are named deterministically — `goal.parse_required_sections` —
and the delivered document records the headings it wrote); `workflow` ⇒ observed
steps AND an observable state change (the stored run id is not a result, so a
workflow that produced nothing is refused — the old check could never fail);
`finance` ⇒ provenance, freshness and claim-to-evidence, deferring to the
Evidence Engine's own verdict instead of re-deriving a value; `data` is a NEW
task type ⇒ a reproducible calculation (a recorded formula with its inputs, or
an analysis that pinned the program it ran and the inputs it read — a number in
prose is not a computation). Three recordings were added so those rules can be
checked at all: the required sections of a document, the sandbox's
`AnalysisRecord` rows as bounded run evidence, and the authored document's
headings. The Evidence Engine stays the financial authority. Tests:
`python/tests/test_tasks_verification.py` (37) and
`python/tests/test_w14_verification_evidence.py` (9). Owning doc
`docs/harness/task-plan-system.md`; ADR-H240.

### W15 — Autonomy tiers and operational control

Map the external brief's tiers onto the existing profiles, and make the safe
tier the default:

- **Tier 1 (autonomous):** read, search, analyze, draft, permitted tests inside
  the authorized workspace — `edit_verify`-equivalent, no approval per call.
- **Tier 2 (guarded):** dependency install, config change, expensive workflow —
  policy + resource caps + `AutonomyEnvelope`.
- **Tier 3 (approval):** deploy, external publication, destructive action,
  credential change, live financial transaction — single-use operator approval.

Keep workspace confinement, secret redaction, skill/dependency scanning, network
restrictions, quotas, audit and kill switches. **The agent may never grant itself
permissions by changing policy, approvals or evaluation gates.**

**Acceptance:** the three tiers are enforced by the runtime (not the prompt), and
the unauthorized-action rate stays 0 on the suite.

**Status — W15 landed 2026-10-18 (tier mapping).** `security/tiers.py` maps the
brief's tiers onto the EXISTING policy groups the authorizer enforces: read →
Tier 1 autonomous; workspace write/execute/install → Tier 2 guarded; external/
destructive/credential/live-transaction actions → Tier 3 approval
(`tier_requires_approval`). `tier_report` audits a live registry (counts +
approval-tier names), and a test pins that the mapping agrees with the policy
groups (an approval-group tool can never classify below Tier 3), so the tiers
are the runtime's, not the prompt's (`test_security_tiers.py`, 6).

---

## 5. Invariants preserved (do not weaken)

1. **One runtime.** Every change is tools/rules on the existing registry and
   the existing `execute_run`. No second loop.
2. **Prose is not a boundary.** All routing/policy stays deterministic Python;
   no model call ever grants a capability or authorises a land.
3. **Artifacts stay inert.** A proposed patch, a learned skill, and an
   acquisition plan are inert until evaluation + an operator decision. Round 4
   automates *proposal and verification*, never *activation*.
4. **Never fabricate.** A refused task stays refused; "collected"/"computed"
   labels are untouched.
5. **No unasked-for git.** The loop never commits, pushes or opens a PR.
6. **File-size ratchets.** New logic goes in new modules; `graph.py`, the big
   core files and `main.py` (via `include_router`) stay within budget.
7. **The release gate is definition of done.** `npm run test` +
   `npx tsc --noEmit` + `node scripts/test-python.js` + `node scripts/test-evals.js`.
8. **Completion is evidence, not prose.** A task is complete only when its
   task-type verifier recorded the evidence; a model's confident answer is not a
   completion signal.
9. **One benchmark, frozen.** The release benchmark is read-only to the agent;
   the development set exists for experiments. A proposal that edits acceptance
   criteria is itself a proposal under the same gate.
10. **No new infrastructure without proof.** A new database, queue, runtime,
    scheduler, event bus or evaluation framework requires an audit demonstrating
    the existing owner cannot satisfy the requirement. The default is reuse.
11. **The agent never grants itself authority.** Policy, approvals, the
    autonomy envelope and the evaluation gates are outside the self-edit surface.

---

## 6. Dependency order and the first slice

Dependency-driven, not a feature list:

```
[1] W0 routing fidelity + W1 observation + W3.1 fixtures   ← first slice
      │
[2] W8.1–W8.4 goal contract + durable default + verified completion
      │        (start with the execution/recovery audit; fix, don't rebuild)
      ├─ W10 progress/stuck control        (rides W8)
      └─ W14 verifiers by task type        (rides W8)
[3] W2 → W3 → W4 self-repair loop          (needs W1's incidents)
[4] W5 + W9 acquisition lifecycle → W6 procedural learning
[5] W11 L3 strategic learning + W15 autonomy tiers
[6] W12 multi-agent adoption (only if measured) + W13 tool contracts
[7] W7 measurement (continuous from [1]; gated at the end)
```

**First slice (ship first, smallest, highest leverage):**

1. **W0.1 + W0.2** — the clock request must escalate instead of refusing
   (`ui/mode.py` witness requirement; `ui/engineering.py` catalog re-check).
2. **W1.1 + W1.2** — the same run must leave a `misrouted_request` incident.
3. **W3.1** — the clock and its siblings become benchmark scenarios.

**Second slice (the product loop's foundation):** W8.1 + W8.4 with W8.3's
checkpoint/resume, proven by the build-run-break-repair-resume acceptance test.
Then continue down the list.

Do not start W2 before W0/W1 have fixtures: without a reproducing trace there is
no way to demonstrate the behaviour changed. Do not start W12 before W8 and the
single-agent baseline are green: parallelism must beat a measured baseline.

---

## 7. Risks

| # | Risk | L/M/H | Mitigation |
|---|---|---|---|
| 1 | Self-repair edits verdict logic and weakens routing → over-fires code/network | H/H | Changes are proposals; authority files frozen; gate + operator land |
| 2 | "Construction" becomes fabrication | M/H | computed/collected/retrieved labels untouched; honesty dimension gated |
| 3 | The loop burns budget chasing unreproducible failures | M/M | Reuse `RecoveryBudget`/`max_total_ms`; reproducer registry is caller-seeded; no reproducer ⇒ observation only |
| 4 | A verification-suite edit games its own gate | M/H | Gate weights + safety floors are authority files; scenario edits are proposals like any other |
| 5 | Memory/skill pollution from mis-diagnosed incidents | M/M | Candidates inert; recurrence evidence required for `successful_procedure` |
| 6 | Doc drift repeats | H/L | Each workstream updates its owning doc + `CHANGELOG.md` per `AGENTS.md` |
| 7 | W8's goal contract misreads an ambiguous request and launches the wrong work | H/M | One clarifying question on ambiguity; the contract is shown before durable work begins |
| 8 | Verified completion becomes "blocked" for everything → the agent looks less capable | M/H | Task-type verifiers are tested against known-good fixtures; `BLOCKED` requires evidence and names the next permitted route |
| 9 | Multi-agent parallelism adds cost/latency without quality | M/M | Adoption is gated on beating the single-agent baseline on the frozen set |
| 10 | The benchmark is overfit ("learns the tests") | M/H | Frozen release set + separate dev set; new scenarios authored from production incidents, not from passing traces |

---

## 8. ADR proposals (harness series continues after ADR-H202)

| ADR | Subject | Workstream |
|---|---|---|
| ADR-H203 | A Compose verdict must cite a catalog witness; a witness-less Compose escalates | W0 |
| ADR-H204 | One capability-fit fact is shared by the surface and method classifiers | W0 |
| ADR-H205 | A request that was routed to a path that cannot satisfy it is a first-class failure with a stable signature | W1 |
| ADR-H206 | Self-repair proposals are typed, minimal, worktree-authored and benchmark-verified; activation stays operator-gated | W2/W3 |
| ADR-H207 | The acquisition plan is a first-class incident outcome; the executor may *propose* install/build, never grant it | W5 |
| ADR-H208 | The self-evolution loop owns its own measured dimensions; an unmeasured dimension is published as unmeasured | W7 |
| ADR-H209 | A goal becomes a durable contract (objective, deliverables, constraints, acceptance) before multi-step work starts | W8 |
| ADR-H210 | Completion is evidence: a task-type verifier must record proof; prose is never a completion signal | W8/W14 |
| ADR-H211 | Acquisition is a closed lifecycle (discover→…→retry), and every acquired capability must pass its own contract test | W9 |
| ADR-H212 | Learning is layered (episodic/procedural/strategic/harness/evaluation), each with its own validation standard | W11 |
| ADR-H213 | Parallel agents are adopted only where a measured benchmark beats the single-agent baseline | W12 |
| ADR-H214 | A registered tool is not advertised as available until its capability contract and fixture pass | W13 |
| ADR-H215 | Autonomy tiers are enforced by the runtime, and the agent can never widen its own authority | W15 |

**Status — H203–H210 written 2026-10-18.** The six earlier proposals
(H203–H208) and the two W8 decisions (H209/H210) are recorded in
`docs/harness/decisions.md`; the subjects above are unchanged. **H213 written
2026-10-18** with the W12 comparison harness: parallel agents are adopted only
where a measured benchmark beats the single-agent baseline, and the first
frozen-set measurement did not meet that bar. **H211, H212, H214 and H215
written 2026-10-18** (completion pass) — every ADR the round reserved now
exists in `decisions.md`.

---

## 9. Open questions (resolve by running, not reading)

1. Does the clock request, phrased several ways, defeat `W0.1`'s witness
   requirement — i.e. is "witness" deterministically computable from a phrase as
   loose as "add a world clock"? (Prototype the `capability_fit` matcher against
   20 real phrasings before committing the rule.)
2. Can the SSE/trace stream reconstruct the intent verdict and refusal code at
   `W1.3` without a new `graph.py` seam? (`recovery/hotpath.py` set a precedent.)
3. Does `code/selfhost.py::classify_landing` correctly treat
   `code/request_intent.py` and `ui/mode.py` as **non-authority** (repairable) —
   confirm before W2 authors their patches.
4. Is `evaluation/improvement.py`'s `apply`/`revert` contract sufficient for a
   multi-file worktree change, or does it need a worktree handle parameter?
5. Can `taskType` be inferred deterministically from the goal contract, or does
   W8 need an explicit per-task declaration (and what happens when it is wrong)?
6. Does the task scheduler already resume safely after a process kill, or does
   `fabric/` recovery only reconcile queued/claimed work? Prove it before W8.3.
7. Are `AcceptanceCriterionInput` plus task artifacts sufficient for
   deliverable-level verification, or does W8.4 need a typed evidence record?
8. Which tool families have the weakest real contracts today? Audit (W13) before
   writing contract tests, so the work targets measured breakage, not breadth.

---

## Related

- `docs/harness/construction-first-audit.md` — round 3 ground truth (routing,
  surface gate, recovery, benchmark).
- `docs/harness/self-editing-harness-plan.md` — the land/rollback/self-hosting
  floor this program reuses.
- `docs/harness/failure-recovery.md` — the failure vocabulary and envelope.
- `docs/harness/agent-evaluation.md` — the improvement/anti-regression loop.
- `docs/harness/memory-skills-evolution-plan.md` — the learning/candidate path.
- `docs/harness/task-plan-system.md` — the durable task/plan owner W8 reuses.
- `docs/harness/execution-fabric.md` — the durable queue/worker owner W8 reuses.
- `docs/harness/agent-to-agent.md` + `docs/harness/bot-team-orchestration.md` —
  the specialists/reviewer machinery W12 adopts.
- `docs/harness/roadmap/README.md` — rounds 1–2 (phases 0–20).
