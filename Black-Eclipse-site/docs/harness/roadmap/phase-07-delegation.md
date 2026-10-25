---
title: "Phase 7 — Delegation and Child Runs"
status: Done
phase: 7
depends_on: [5]
unlocks: [9, 10]
last-verified: 2026-10-25
---

# Phase 7 — Delegation and Child Runs

| | |
|---|---|
| **Depends on** | Phase 5 (a settled agent/approval surface) |
| **Unlocks** | Phase 9 (kits), Phase 10 (self-improvement) |
| **Estimated work** | 5–8 h of agent time |
| **Deliverable type** | new `delegation.py` + a `delegate` tool + aggregation rules |
| **New ADRs** | ADR-H109 |
| **Prompt to copy** | [§11 below](#11-implementation-prompt-copy-this-to-opencode) |

## Contents

- [1. Goal](#1-goal)
- [2. Why this phase exists (the real gap)](#2-why-this-phase-exists-the-real-gap)
- [3. In scope](#3-in-scope)
- [4. Who can use it (the non-expert obligation)](#4-who-can-use-it-the-non-expert-obligation)
- [5. Non-goals (do not do these)](#5-non-goals-do-not-do-these)
- [6. Exact contracts to create](#6-exact-contracts-to-create)
  - [6.1 The request and the result — `python/harness/delegation.py`](#61-the-request-and-the-result--pythonharnessdelegationpy)
  - [6.2 The narrowing rule](#62-the-narrowing-rule)
  - [6.3 The tool — `delegate`](#63-the-tool--delegate)
  - [6.4 Aggregation — verified handles only](#64-aggregation--verified-handles-only)
  - [6.5 Workspace strategy for writing children](#65-workspace-strategy-for-writing-children)
  - [6.6 Persistence and events](#66-persistence-and-events)
- [7. Work items (ordered)](#7-work-items-ordered)
- [8. Deliverables](#8-deliverables)
- [9. Acceptance gates](#9-acceptance-gates)
- [10. Definition of done](#10-definition-of-done)
- [11. Implementation prompt (copy this to OpenCode)](#11-implementation-prompt-copy-this-to-opencode)

## 1. Goal

Let one run **fan out bounded parallel workstreams** and aggregate only what each
child actually proved — so a large question ("review these five companies",
"check every holding") finishes in one pass instead of five sequential turns.

This is the phase that makes the harness feel like a *staff*, not a single
assistant.

## 2. Why this phase exists (the real gap)

The **linkage already exists and is being extended** — the parent already knows
its children:

- `python/harness/persistence.py` has `HarnessRun.parentRunId` and
  `list_child_runs(parent_run_id)`.
- A skill invocation already creates a child run (`skills/runtime.py` →
  `SkillExecutionRequest.parentRunId`), and `run_lineage.py` — landed in the tree
  while this roadmap was written — adds `HarnessRun.workflowId`, `RunCheckpoint`
  and `ToolExecutionIdempotency` (so a resumed run **reuses** a recorded result
  instead of re-executing a side-effecting call).

What does **not** exist is any **fan-out**: nothing runs two children at once,
nothing bounds them, nothing aggregates them, and nothing checks whether a child's
claim is true before the parent repeats it.

Two existing rules are the direct precedent, and both are reused rather than
reinvented:

1. **Narrowing is already modelled.** `permissions.Actor` has `scopes`, which can
   only ever *narrow* a grant set (`granted()` returns `base & scopes`). A child is
   an actor built that way.
2. **A self-report is never proof.** The MCP layer already holds this line — an
   external server's result is *"never labelled Eclipse-verified unless a separate
   verification flow actually checked it."* A child run's summary is exactly such
   a self-report.

## 3. In scope

1. `python/harness/delegation.py` — request/result contracts, the budget, the
   fan-out executor, the aggregator.
2. A `delegate` tool on the existing registry.
3. The narrowing rule, enforced in code.
4. Aggregation that admits only verifiable handles.
5. Per-writer-child workspace isolation.
6. Persistence/events on the existing tables and bus.

## 4. Who can use it (the non-expert obligation)

Nobody asks for "delegation". They ask a question with a plural in it.

1. **The user's words are the trigger, not a tool name.** *"Compare these five
   companies"*, *"check my whole portfolio"*, *"go through last quarter's
   filings"* — Eclipse decides how much to do in parallel. The user never picks a
   child count, a budget, or a model.
2. **Progress reads as a plain list of the things, not of the machinery.** *"I'm
   looking at 5 companies at once — 3 done, 2 to go."* Never "3 child runs
   completed, 2 pending".
3. **A partial answer is a normal answer.** If two of five children fail, the user
   gets the three that worked, named plainly, plus one sentence about the rest —
   never a collapsed "I couldn't do that".
4. **No orchestration vocabulary on the surface.** The words *child*, *parent*,
   *subagent*, *fan-out*, *budget*, *concurrency* and *depth* live in the trace
   and this document only.
5. **All new user-facing copy is an i18n key** in `src/lib/i18n/`
   (`dictionaries/en.ts` canonical, `dictionaries/index.ts` translations,
   `translate.ts` lookup, `use-t.ts` hook) — never a hardcoded component string.
6. **The plain-language gate** (§9 G7) covers the progress strings and the
   aggregation summary against `policy.PLAIN_LANGUAGE_DENYLIST`.

## 5. Non-goals (do not do these)

- **No unbounded recursion.** Depth is capped and a child cannot spawn past it.
- **No widening, ever.** A child may never hold a permission its parent lacks, or
  reach a tool its parent cannot call.
- No autonomous merge of conflicting child work — a conflict is surfaced, not
  resolved.
- No second execution path: a child IS `execute_run` with a parent link.
- No new agent loop, registry, or model adapter.
- Do not commit, push, or open a PR.

## 6. Exact contracts to create

### 6.1 The request and the result — `python/harness/delegation.py`

```python
"""Bounded fan-out of child runs, and honest aggregation of their results.

A child is a normal run: same graph, same registry, same policy engine, same
persistence. The only things this module owns are the BUDGET, the NARROWING, and
the AGGREGATION rule. It never executes anything itself and never talks to a
model.
"""

MAX_CHILDREN: int = 4          # per delegation
MAX_DEPTH: int = 2             # parent → child → grandchild; beyond this, refused
DEFAULT_CHILD_TIMEOUT_S: int = 900
DEFAULT_CHILD_TOKEN_BUDGET: int = 120_000

class DelegationChild(BaseModel):
    goal: str = Field(..., max_length=2000)
    context: str = Field("", max_length=8000)     # background THIS child needs
    approach: Optional[str] = None                # short angle (best_of row label)
    agent_id: Optional[str] = None                # defaults to the parent's agent
    model: Optional[str] = None                   # same provider as the parent
    tool_subset: Optional[list[str]] = None       # must be ⊆ the parent's allowlist
    workspace_id: Optional[str] = None            # writing children only

class DelegationRequest(BaseModel):
    children: list[DelegationChild] = Field(..., min_length=1, max_length=MAX_CHILDREN)
    aggregate: Literal["list", "compare", "merge_claims"] = "list"
    strategy: Literal["split", "best_of"] = "split"
    token_budget: int = DEFAULT_CHILD_TOKEN_BUDGET

class ChildOutcome(BaseModel):
    child_index: int
    run_id: Optional[str]                      # None when the child never started
    status: Literal["completed", "failed", "timed_out", "refused", "cancelled"]
    summary: str                               # the child's own words — UNTRUSTED
    tokens: int = 0                            # REAL usage the child reported
    handles: list[VerifiableHandle] = []       # what the parent may safely repeat
    reason: Optional[str] = None               # plain sentence on failure/refusal

class DelegationResult(BaseModel):
    strategy: Literal["split", "best_of"] = "split"
    outcomes: list[ChildOutcome]
    aggregate: str                             # the rendered, handle-backed summary
    dropped_claims: list[str] = []             # child claims with NO handle
    budget: BudgetReport                       # requested vs consumed (REAL usage)
    winner: Optional[int] = None               # best_of only: the selected part
```

`aggregate` is rendered according to the request's own mode: `list` (one line
per confirmed claim), `compare` (each item under its own heading), or
`merge_claims` (the same confirmed claims, de-duplicated across items).

### 6.2 The narrowing rule

Enforced in code, at child construction — a child is never handed the parent's
actor:

```python
def child_actor(parent: Actor, child: DelegationChild) -> Actor:
    """A child holds the parent's grants INTERSECTED with the child's scope.

    - never a superset: scopes only ever narrow (permissions.Actor.granted)
    - never a new permission class: code.* only if the parent held it
    - never a wider workspace: the child's workspace_id must be one the parent
      already had (or one this delegation allocated, §6.5)
    - `operator` is NEVER inherited: a child is never an operator, so it can
      never approve its own effectful action or enable a skill
    """
```

The last line is the important one. An operator flag is proof of *who called*; a
child did not make that call, so inheriting it would launder authority. A child
that needs an effectful action returns the request to the parent, which asks the
operator.

### 6.3 The tool — `delegate`

`ToolDefinition`: `name="delegate"`, `read_only=False`,
`required_permissions=("skill.invoke",)` — reusing the existing sub-run
permission rather than inventing one — `timeout_ms` derived from the child budget.

It refuses, with a structured code, when: the child count exceeds `MAX_CHILDREN`
(`DELEGATION_WIDTH_EXCEEDED`); the depth would exceed `MAX_DEPTH`
(`DELEGATION_DEPTH_EXCEEDED`); a requested tool is not in the parent's allowlist
(`DELEGATION_TOOL_NOT_HELD`); a requested permission is not held
(`DELEGATION_PERMISSION_NOT_HELD`); the budget is exhausted
(`DELEGATION_BUDGET_EXHAUSTED`); or the Phase 3 sandbox is unavailable for a
writing child (`SANDBOX_UNAVAILABLE` — the child is refused, never run outside
isolation).

The budget is **enforced, not merely declared**: each part's real token usage is
accumulated into `BudgetReport.consumedTokens`, and once the remaining room is
below `MIN_TOKENS_PER_CHILD` a part is refused before it is started (and before
its `started` event). The whole fan-out also carries an overall
`DEFAULT_TOTAL_TIMEOUT_S` deadline; parts still running at that point are stopped
and every outcome gets an honest terminal status.

In-flight work is bounded by `MAX_IN_FLIGHT` (default 4), which the operator can
set per machine with `HARNESS_DELEGATION_MAX_IN_FLIGHT` (clamped 1–8) because
memory, not CPU, is the real constraint. Each part also gets its own
`asyncio.Event` passed to `execute_run` as `cancel_event`; when the part times
out, is cancelled, or fails, the event is set so cooperating tools (sandbox,
browser, shell) stop instead of leaving work running.

### 6.4 Aggregation — verified handles only

```python
@dataclass(frozen=True)
class VerifiableHandle:
    kind: Literal["path", "run_id", "artifact_digest", "check_record_id", "citation"]
    value: str
```

The aggregator's rule, and the whole reason this phase is safe:

> **A child's prose is quoted; a child's CLAIM is only repeated when it carries a
> handle the parent can re-check.**

- A research child's finding carries a `citation` handle (the existing
  `research/citations.py` / receipt evidence).
- A code child's "the tests pass" carries a `check_record_id` pointing at a row in
  the Phase 4 verification ledger — a child claim with no ledger row is **dropped**
  into `dropped_claims` and rendered as unconfirmed.
- A produced file carries an `artifact_digest`.

The parent re-reads each handle before the aggregate is rendered. `dropped_claims`
is surfaced, never silently discarded — the same discipline as
`research/coverage.py`, where a successful retrieval is not the same thing as
coverage.

Verification is **fail-closed**: `run_id` and `check_record_id` are checked
against the real run store and verification ledger; an `artifact_digest` is
confirmed only when the Artifact Center holds it, and is refused (not admitted)
when no artifact service is bound. A non-empty value is never treated as proof.

### 6.5 Workspace strategy for writing children

- A **read-only** child (research, analysis) needs no workspace.
- A **writing** child gets **its own worktree** from Phase 2. Two children editing
  the same file therefore cannot corrupt each other.
- Integration is **explicit**: the parent lists each child's diff and any
  conflicting hunks. It never merges. Merging is a Phase 5 `approve_external`
  action with an operator approval, and a conflict is reported as a conflict.

### 6.6 Persistence and events

No new table. A child is a `HarnessRun` with `parentRunId` set (already exists),
and `workflowId` groups one delegation's children (`run_lineage.py`). The
delegation itself is recorded on the parent run's additive blob
(`HarnessRun.delegation`, old-row-safe like `HarnessRun.context`) so the fan-out
is explainable after the fact.

Events on the existing `RunEmitter`: `delegation.started`,
`delegation.child.started`, `delegation.child.completed`,
`delegation.child.failed`, `delegation.child.refused`, `delegation.aggregated`
(counts + dropped-claim count only), plus the live `delegation.progress`
snapshots described below. Each event names the child's `runId`, so the existing
`explain_run` view and the session trace already cover it — no new observability
surface.

### 6.7 Live progress in the chat

A child runs on its OWN run id, so its events are published there and never reach
the parent's SSE stream. `python/harness/delegation_progress.py`
(`ChildProgressBridge`) bridges that: it opens the child's bus stream, folds the
events into one bounded, content-free snapshot, and re-emits it on the PARENT's
emitter as `delegation.progress` (throttled, one row per `childIndex`).

The snapshot carries the runtime's own `step` / `maxSteps`, the REAL tokens, the
REAL price (or `null` when the model has no declared price), and the latest plain
activity phrase. The UI (`src/components/chat/parallel-agents-panel.tsx`, fed by
`src/lib/agent/delegation-reducer.ts`) draws one row per part: bot icon, agent +
sub-question, live activity, a bar driven by `step / maxSteps` (indeterminate
when the ceiling is unknown), and the cost. A percentage is never invented, and
an unpriced model shows `—`, never `$0.00`.

`delegation.started` therefore names the parts (`agents: [{childIndex, goal,
agentId?, model?, approach?}]`) so the rows exist before the first snapshot
arrives. The persisted blob (`HarnessRun.delegation` via `_run_row`) carries the
same bounded row fields (`goal`, `approach`, `model`, `tokens`), and
`/runs/{id}/explain` returns a bounded, redacted `delegation` view
(`run_observability._bounded_delegation`) so the fan-out stays reviewable after
a reload — without re-rendering the child's prose or claims.

### 6.8 `best_of` — N tries at the same task

`strategy="best_of"` runs the SAME goal several ways (2–4 attempts, optionally
different `agent_ids`) and selects ONE result. The tool's input is `goal` +
`count`, not `children`; mixing them is refused. Selection is deterministic and
evidence-based (`select_best`):

1. only a `completed` attempt can win;
2. confirmed claims and verified handles score positively, unconfirmed claims
   score negatively (a loud child cannot win by claiming more);
3. a non-empty answer breaks a tie;
4. fewer tokens breaks the next tie;
5. the earliest part breaks the last tie.

`aggregate_best_of` quotes ONLY the winner's prose and proven claims; the other
attempts are named as "not repeated as fact" (and how many also finished). When
none finished, `winner` is `None` and the answer says so — no fabricated "best".
`delegation.aggregated` carries `strategy` and `winner`, and the chat header
renders `Best of N` with a `Best` chip on the winning row.

Attempts may also name a **model** (`DelegationChild.model` / the tool's
`models[]`). This is deliberately limited to the parent's provider: the Python
service holds only this run's credential, so a cross-provider attempt would need
a key it must not invent. The provider (and its credential) stays fixed; only
the model id changes, and the row shows that model's name.

An attempt may also set its own **temperature** (`DelegationChild.temperature` /
the tool's `temperatures[]`), so N attempts are genuinely different samples
rather than near-duplicates. Temperature is only a sampling hint: a provider
that ignores it behaves exactly as before, and nothing in the result is
fabricated to compensate.

Each attempt may name a short **approach** (`DelegationChild.approach` / the
tool's `approaches[]`, e.g. "retry with backoff", "mock the API"). It is
prepended to that child's prompt as guidance and is what the card shows as the
row label; the full sub-question stays in the tooltip. It is never a claimed
result.

Each attempt may also carry its own bounded **context** (`contexts[]` in the
tool, `DelegationChild.context`), so tries can work from different background
evidence. Context is prompt input only: it is not put in the progress snapshot
or shown in the card, so background material does not leak to the transcript.

## 7. Work items (ordered)

1. `docs/harness/roadmap/progress/phase-07-progress.md` with §9's gates as
   unchecked boxes.
2. `delegation.py` — contracts (§6.1), `child_actor` (§6.2), the fan-out executor
   with bounded concurrency and per-child timeout, the aggregator (§6.4).
3. The `delegate` tool registered in the code agent's `register_code_tools` (and
   available to `eclipse-agent` — it is a research capability too).
4. Narrowing tests first (§6.2 has the subtle rules; write the negatives before
   the happy path).
5. Aggregation tests with a deliberately lying child fixture (a child whose summary
   claims a passing check with no ledger row).
6. Workspace allocation for writing children, reusing Phase 2's `worktree.allocate`.
7. Parent blob + events (§6.6).
8. Prompt guidance: when to delegate (independent sub-questions), when **not** to
   (one question, or children that need each other's output).
9. ADR-H109; `docs/CHANGELOG.md`; `docs/NAVIGATION.md`.

## 8. Deliverables

| File | Change |
|---|---|
| `python/harness/delegation.py` | new — contracts, narrowing, fan-out, aggregation |
| `python/harness/code/tools.py` | register `delegate` |
| `python/harness/persistence.py` | additive `HarnessRun.delegation` blob (old-row-safe) |
| `python/harness/prompts.py`, `agents.py` | delegation guidance + tool in both allowlists |
| `python/tests/test_delegation.py`, `test_delegation_narrowing.py`, `test_delegation_aggregation.py` | new |
| `python/tests/fixtures/delegation/*` | new — honest and lying child fixtures |
| `python/tests/test_plain_language.py` | extend for the progress/aggregation strings |
| `docs/harness/decisions.md` | ADR-H109 |
| `docs/harness/roadmap/progress/phase-07-progress.md` | new |

## 9. Acceptance gates

```bash
# G1 — narrowing: a child can never widen (the negatives matter most)
./scripts/vendor/python/python.exe -m pytest python/tests/test_delegation_narrowing.py -v

# G2 — fan-out + aggregation
./scripts/vendor/python/python.exe -m pytest python/tests/test_delegation.py python/tests/test_delegation_aggregation.py -v

# G3 — the caps, proven not asserted
./scripts/vendor/python/python.exe -m pytest python/tests/test_delegation.py -k "width or depth or budget" -q
# expected: 5 children refused DELEGATION_WIDTH_EXCEEDED; depth 3 refused
#           DELEGATION_DEPTH_EXCEEDED; an unheld tool refused DELEGATION_TOOL_NOT_HELD

# G4 — a child's unbacked claim never reaches the parent's answer
./scripts/vendor/python/python.exe -m pytest python/tests/test_delegation_aggregation.py -k dropped_claims -v
# expected: the lying child's "tests pass" lands in dropped_claims and is rendered
#           as unconfirmed; the parent answer contains no unbacked claim

# G5 — no orphan child after a cancel, and no second execution path
./scripts/vendor/python/python.exe -m pytest python/tests/test_delegation.py -k cancel -q

# G6 — the whole suite + the release gate
npm run test && npm run check:all

# G7 — plain language: progress and summary strings
npx vitest run src/lib/i18n/plain-language.test.ts
./scripts/vendor/python/python.exe -m pytest python/tests/test_plain_language.py -k delegation -q

# G8 — nothing else moved
git status --short        # jdds.db must NOT appear; no unexpected artefact
```

| Gate | Assertion |
|---|---|
| G1 | A child holding a permission the parent lacks is impossible; `operator` is never inherited; a child's tool set ⊆ the parent's allowlist; a wider workspace is refused. |
| G2 | Three parallel research children complete; each `ChildOutcome` names its `runId` and terminal status; the parent blob records the fan-out. |
| G4 | A child claiming "all tests pass" with no ledger row is dropped and rendered unconfirmed; the parent cannot assert it. |
| G5 | Cancel mid-fan-out leaves no running child and no orphan worktree; every child reaches exactly one terminal status. |
| G6 | Full suite + `check:all` green. |
| G8 | No `*.db` change; no unexpected artefact. |

## 10. Definition of done

- Every gate run, raw output pasted, counts recorded.
- A child is provably a normal `HarnessRun` with `parentRunId` (the row links; the
  trace exists) — no second execution path anywhere.
- The `operator` flag is provably not inherited (asserted in G1).
- `dropped_claims` is surfaced to the user, not silently discarded.
- ADR-H109 written; CHANGELOG + NAVIGATION updated; `status:` flipped.

## 11. Implementation prompt (copy this to OpenCode)

```text
Task: Phase 7 — Delegation and child runs (Eclipse-as-a-Harness roadmap).

Read first, in full:
- docs/harness/roadmap/phase-07-delegation.md  (this phase, verbatim)
- docs/harness/roadmap/README.md  (invariants §3 incl. the 3.1–3.8 index, work in flight §4)
- python/harness/run_lineage.py   ← parentRunId/workflowId + RunCheckpoint +
  ToolExecutionIdempotency. REUSE these; do not build a parallel linkage.
- python/harness/persistence.py   ← HarnessRun.parentRunId, list_child_runs()
- python/harness/skills/permissions.py ← Actor.scopes narrowing (granted() = base & scopes)
- python/harness/skills/runtime.py ← how a skill already creates a child run
- python/harness/code/verify.py (Phase 4) ← the ledger a code child's claim must cite
- python/harness/mcp/approvals.py ← the "a self-report is never proof" precedent
- python/harness/research/coverage.py ← the "successful retrieval is not coverage"
  precedent for dropping unbacked claims

Goal: bounded fan-out of child runs, with honest aggregation. A child IS a normal
run (same graph, registry, policy, persistence) — this module owns ONLY the budget,
the narrowing and the aggregation rule.

In scope:
1. delegation.py per §6.1: MAX_CHILDREN=4, MAX_DEPTH=2, DelegationChild,
   DelegationRequest (children 1..4, aggregate: list|compare|merge_claims),
   ChildOutcome (run_id, status, summary, handles, reason), DelegationResult
   (outcomes, aggregate, dropped_claims, budget), VerifiableHandle.
2. child_actor(parent, child) per §6.2 — grants are the INTERSECTION with the
   child's scope, never a superset; `operator` is NEVER inherited (that is how a
   child would launder authority); code.* only if the parent held it; a wider
   workspace is refused. Write the NEGATIVE tests first.
3. The `delegate` tool: read_only=False, required_permissions=("skill.invoke",)
   (reuse the existing sub-run permission — do not invent one), refusing with the
   structured codes DELEGATION_WIDTH_EXCEEDED / DEPTH_EXCEEDED / TOOL_NOT_HELD /
   PERMISSION_NOT_HELD / BUDGET_EXHAUSTED, and SANDBOX_UNAVAILABLE for a writing
   child when Phase 3's sandbox is unavailable (refuse, never run unisolated).
4. Aggregation per §6.4: a child's PROSE is quoted; a child's CLAIM is repeated
   ONLY with a re-checkable handle (citation / check_record_id from the Phase 4
   ledger / artifact_digest / path). Re-read every handle before rendering. A
   claim with no handle goes to dropped_claims and renders as unconfirmed.
5. Writing children get their OWN worktree via Phase 2's worktree.allocate. The
   parent lists diffs and conflicting hunks; it NEVER merges (merging is a Phase 5
   approve_external action with an operator approval).
6. Persistence per §6.6: NO new table. A child is a HarnessRun with parentRunId;
   workflowId groups one delegation. Add an additive, old-row-safe
   HarnessRun.delegation blob (follow the HarnessRun.context pattern exactly).
   Events on the existing RunEmitter: delegation.started / child.started /
   child.completed / child.failed / child.refused / aggregated (counts only).
7. Prompt guidance in prompts.py: when to delegate (independent sub-questions) and
   when NOT to (one question, or children needing each other's output). Register
   `delegate` in the eclipse-agent and code-agent allowlists.
8. Tests: test_delegation.py, test_delegation_narrowing.py,
   test_delegation_aggregation.py, plus honest and LYING child fixtures under
   python/tests/fixtures/delegation/.
9. ADR-H109 in docs/harness/decisions.md (Decision / Why / Consequences shape; use
   ADR-H109 exactly).
10. docs/CHANGELOG.md dated entry + docs/NAVIGATION.md rows.

Non-goals (do NOT do these):
- No unbounded recursion; no child wider than its parent; no inherited operator flag.
- No autonomous merge of conflicting child work — surface the conflict.
- No second execution path: a child is execute_run with a parent link.
- No new observability surface (events + explain_run already cover it).
- Never commit, push, or open a PR. Do not commit jdds.db.

Constraints:
- One runtime: no second agent loop, tool registry or model adapter.
- Policy and permissions stay in code.
- New logic in a new module; keep graph.py/persistence.py/main.py under their ratchets.
- The user sees the finance job and a plain progress list, never orchestration
  vocabulary (child/parent/fan-out/budget/concurrency/depth).

Acceptance gates — run each and paste the RAW output into
docs/harness/roadmap/progress/phase-07-progress.md:
  ./scripts/vendor/python/python.exe -m pytest python/tests/test_delegation_narrowing.py -v
  ./scripts/vendor/python/python.exe -m pytest python/tests/test_delegation.py python/tests/test_delegation_aggregation.py -v
  ./scripts/vendor/python/python.exe -m pytest python/tests/test_delegation.py -k "width or depth or budget" -q
  ./scripts/vendor/python/python.exe -m pytest python/tests/test_delegation_aggregation.py -k dropped_claims -v
  ./scripts/vendor/python/python.exe -m pytest python/tests/test_delegation.py -k cancel -q
  npm run test && npm run check:all
  npx vitest run src/lib/i18n/plain-language.test.ts
  ./scripts/vendor/python/python.exe -m pytest python/tests/test_plain_language.py -k delegation -q
  git status --short

Finish by stating: "docs updated: <files>" or "no doc change — <reason>".
```

---

**Next:** [Phase 8 — Analysis sandbox](./phase-08-analysis-sandbox.md)
