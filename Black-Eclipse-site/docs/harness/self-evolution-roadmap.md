---
title: Self-Evolution Roadmap — Round 4 — the closed self-improvement loop
status: Draft
last-verified: 2026-10-17
---

# Self-Evolution Roadmap — Round 4

**Who this is for:** anyone implementing or reviewing the program that makes
Eclipse **learn from its own runs, diagnose why a task was not solved, propose a
change to its own machinery, verify the change on the benchmark, and land it
under operator control** — plus the reachability fixes that let it *attempt* the
task at all.

**What this is.** Round 1 (roadmap phases 0–12) built the harness machinery.
Round 2 (phases 13–20) made it reachable, sourced and producing. Round 3
(`construction-first-audit.md`) made it *construct* instead of refuse. This is
**round 4**: it closes the loop that was still open — the run itself never
becomes a diagnosed, repairable signal, so the harness cannot fix the class of
failure it just produced.

**Method.** Every claim below is traced to `file:line` in the current tree
(measured 2026-10-17). It does not rebuild what exists; it wires, closes and
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
asks" is operationalised as five numbers on the standing evaluation gate
(`python/harness/evaluation/`), each currently unmeasured:

| Metric | Definition | Target |
|---|---|---|
| `misroute_rate` | share of runs whose final surface could not satisfy the request (a refusal/wrong-method, detected deterministically) | ↓ toward 0 |
| `escalation_correct` | share of novel-capability requests that produce *some* constructive route (compose-with-witness, engineer task, or acquisition plan) rather than a bare refusal | → 1.0 |
| `self_repair_precision` | share of proposed self-changes that pass the gate without a critical regression | → 1.0 |
| `time_to_repair` | wall-clock from a durable incident to a verified promotion candidate | measured, trending down |
| `regression_rate` | share of landed self-changes that later trip a gate | → 0 |

**Non-goals (unchanged, deliberate):** unsupervised self-modification (every
change is operator-confirmed — invariant §5.3), fabricated data (never), a
second runtime (one registry, one loop), and any capability that cannot be
verified is published as **unmeasured**, never claimed.

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

---

## 3. The spine — Observe → Diagnose → Propose → Verify → Land → Measure

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
Ordering is given in §6.

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

### W7 — Measurement and the honest capability statement

- **W7.1 — Add the §1 metrics** to the phase-20 registry and the standing gate.
- **W7.2 — Publish measured/unmeasured honestly** in the capability statement
  (an unmeasured class is never claimed).
- **W7.3 — Report `time_to_repair` / `self_repair_precision`** on the recovery
  console.

**Acceptance:** the five metrics appear on the gate; the baseline is recorded
before and after each workstream.

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

---

## 6. Dependency order and the first slice

```
W0 routing fidelity  (highest user-visible payoff; unblocks everything)
  └─ W1 observation (an incident to diagnose)
       └─ W2 propose
            └─ W3 verify ─────┐
                 └─ W4 land   │
                      └─ W6 learn
  W5 acquisition rungs (needs W1; parallel with W2–W4)
  W7 measurement (needs W3; runs last, continuously)
```

**First slice (ship first, smallest, highest leverage):**

1. **W0.1 + W0.2** — the clock request must escalate instead of refusing
   (`ui/mode.py` witness requirement; `ui/engineering.py` catalog re-check).
2. **W1.1 + W1.2** — the same run must leave a `misrouted_request` incident.
3. **W3.1** — the clock and its siblings become benchmark scenarios.

Do not start W2 before W0/W1 have fixtures: without a reproducing trace there is
no way to demonstrate the behaviour changed.

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

---

## Related

- `docs/harness/construction-first-audit.md` — round 3 ground truth (routing,
  surface gate, recovery, benchmark).
- `docs/harness/self-editing-harness-plan.md` — the land/rollback/self-hosting
  floor this program reuses.
- `docs/harness/failure-recovery.md` — the failure vocabulary and envelope.
- `docs/harness/agent-evaluation.md` — the improvement/anti-regression loop.
- `docs/harness/memory-skills-evolution-plan.md` — the learning/candidate path.
- `docs/harness/roadmap/README.md` — rounds 1–2 (phases 0–20).
