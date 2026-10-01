---
title: "Phase 10 — Self-Improvement v2: Evolving Code as well as Skills"
status: Not started
phase: 10
depends_on: [4, 9]
unlocks: [11]
last-verified: 2026-09-30
---

# Phase 10 — Self-Improvement v2: Evolving Code as well as Skills

|||
|---|---|
| **Depends on** | Phase 4 (the verification ledger) and Phase 9 (kit acceptance tests — the fixtures an attempt is graded against) |
| **Unlocks** | Phase 11 (no more surfaces before self-modification is gated) |
| **Estimated work** | 10–16 h of agent time |
| **Deliverable type** | new `code/evolution.py` + 2 tables + a bridge + a UI extension |
| **New ADRs** | ADR-H112 |
| **Prompt to copy** | [§11 below](#11-implementation-prompt-copy-this-to-opencode) |

## Contents

- [1. Goal](#1-goal)
- [2. Why this phase exists (the gap in the learning pipeline)](#2-why-this-phase-exists-the-gap-in-the-learning-pipeline)
- [3. In scope](#3-in-scope)
- [4. Who can use it (the non-expert obligation)](#4-who-can-use-it-the-non-expert-obligation)
- [5. Non-goals (do not do these)](#5-non-goals-do-not-do-these)
- [6. Exact contracts to create](#6-exact-contracts-to-create)
  - [6.1 The recurrence bridge — `python/harness/code/evolution.py`](#61-the-recurrence-bridge--pythonharnesscodeevolutionpy)
  - [6.2 The candidate and the attempt — persistence (`agent-memory.db`)](#62-the-candidate-and-the-attempt--persistence-agent-memorydb)
  - [6.3 The proposal — structured ops, the forbidden fields, the frozen set](#63-the-proposal--structured-ops-the-forbidden-fields-the-frozen-set)
  - [6.4 Evaluation — a worktree through the Phase-4 ledger](#64-evaluation--a-worktree-through-the-phase-4-ledger)
  - [6.5 Activation — `skills/versioning.py`, reused verbatim](#65-activation--skillsversioningpy-reused-verbatim)
  - [6.6 The attempt archive and the honest metrics](#66-the-attempt-archive-and-the-honest-metrics)
  - [6.7 Routes and events](#67-routes-and-events)
  - [6.8 UI — extend the existing learning journey, do not fork it](#68-ui--extend-the-existing-learning-journey-do-not-fork-it)
  - [6.9 Plain language](#69-plain-language)
- [7. Work items (ordered)](#7-work-items-ordered)
- [8. Deliverables](#8-deliverables)
- [9. Acceptance gates](#9-acceptance-gates)
- [10. Definition of done](#10-definition-of-done)
- [11. Implementation prompt (copy this to OpenCode)](#11-implementation-prompt-copy-this-to-opencode)

**ADR numbering.** This phase takes **ADR-H112** (the harness series ends at
ADR-H92 in `docs/harness/decisions.md`; the provisional ADR-H101 is superseded by
the contiguous allocation H103–H111). The text uses the repo's shape —
`## ADR-H112 — Title` then **Decision.** / **Why.** / **Consequences.**, never
"Impact".

## 1. Goal

Close the loop the harness already half-built: a mistake recorded often enough to
be evidence becomes a **reviewable candidate** — and, when it targets code, a
**proposed change** evaluated inside a worktree, canaried, activated and rolled
back by the *same* machinery that already governs skills.

Two things are deliberately not invented here: the **observation side**
(`eclipse_memory/mistakes.py` detects the deterministic categories;
`persistence.record_learning_recurrence` already counts recurrence) and the
**decision side** (`skills/versioning.py` already implements propose → evaluate →
canary → activate → **atomic rollback preserving both versions**, with automatic
rollback triggers). This phase adds the one missing piece — a bridge from
recurrence to a code-shaped candidate, and the discipline that keeps the change
inert until an operator decision — and **nothing** to the activation machinery.

## 2. Why this phase exists (the gap in the learning pipeline)

Self-improvement in this repo today is **gated for skills only**. Verified:

| Existing piece | What it already does | What it cannot do |
|---|---|---|
| `eclipse_memory/mistakes.py` | 11 deterministic categories, each carrying evidence; "a mistake is a recorded observation" | turn a repeated mistake into a change |
| `persistence.py` — `LearningRecurrence` / `LearningRecurrenceRun`, `record_learning_recurrence` | counts how many times a signature was seen, per run | anything with the count |
| `eclipse_memory/store.py` — `record_recurrence` | the memory-side recurrence counter | anything with the count |
| `skills/learning.py` | criteria-driven candidates, recurrence required for `successful_procedure` | target a file that is not a skill manifest |
| `skills/patches.py` | JSON-pointer ops, an allowed-op set, `FORBIDDEN_FIELDS` (identity / permissions / tools / risk) | patch anything but a skill manifest |
| `skills/versioning.py` | `propose_patch`, `evaluate_version`, `activate_version`, `promote_canary`, `rollback`, `check_rollback_triggers`, `version_history` | any subject other than a skill |
| `research/eval/`, `eclipse_memory/eval/` | the dataset + thresholds + report shape | a code evaluation |

The gap is therefore narrow and exact: **recurrence is recorded and never
consumed, and no candidate can name a source file.** A user can watch the app
record the same failure five times and the app will never propose that the thing
causing it be fixed.

Two failure modes this phase must not create: an **unsupervised self-modifying
loop** (a whole-roadmap non-goal, README §6; ADR-025 is extended, never repealed)
and a **second improvement mechanism** ("one runtime" §3.1, "artifacts stay inert"
§3.3 — a code candidate goes through the *existing* lifecycle, not a parallel one).

**Honesty is a hard requirement, not a tone.** This phase measures its own
success rate and must be able to say *"I cannot measure that"* — a metric that
cannot be measured renders `UNKNOWN`, **never zero**.

## 3. In scope

1. `python/harness/code/evolution.py` — the recurrence bridge and the proposal.
2. Two additive tables: `EvolutionCandidate`, `EvolutionAttempt`.
3. Evaluation inside a worktree through the **Phase-4 verification ledger**
   (owning test file(s) + any Phase-9 kit acceptance test).
4. Activation via `skills/versioning.py` **unchanged** (propose → evaluate →
   canary → activate → atomic rollback), including automatic rollback triggers.
5. A DGM-style **attempt archive**: every attempt recorded with its diff digest,
   evaluation evidence and outcome — including the failures and the rollbacks.
6. Honest metrics: attempts, success rate, regression rate, rollback count, cost
   per successful self-improvement.
7. UI: extend the EXISTING learning journey (`learning-journey.tsx` +
   `python/harness/learning_graph.py`).
8. A route group `python/harness/routers/evolution.py`, `require_operator` on
   **every** route — reads included.

## 4. Who can use it (the non-expert obligation)

A portfolio manager must be able to read *"Eclipse noticed the same problem four
times and prepared a change — review it?"* without meeting *worktree, patch, diff,
digest, evaluation ledger* or *operator*.

1. **The visible unit is the problem, not the mechanism.** The journey shows the
   repeated problem in the user's own words ("The overnight brief kept failing to
   read one source"), how often it was seen, and the plain state of the prepared
   change: *prepared · being checked · available · did not help · put back*.
2. **A candidate is a proposal, never a change.** Nothing here alters a running
   file; every state visible before *available* means *nothing has changed yet*.
3. **The states are plain sentences, not status codes.** `inert` reads *"Prepared
   — not applied"*; `refused` reads *"I could not prepare this change — it would
   alter how Eclipse checks things"*; `evaluated_ok` reads *"Checked and ready"*;
   `rolled_back` reads *"That change made things worse, so I put the previous
   version back"* — each followed by what the user can do next.
4. **A refusal is ONE plain sentence plus a next step, with the reason behind
   "details".** A structured code such as `FROZEN_PATH` is quoted verbatim there
   and nowhere else.
5. **Metrics are stated as they are, including the holes.** *"changes that helped:
   3 of 5"*, and where a figure could not be measured, *"not measured yet"* —
   never `0%`, never a blended "improvement score".
6. **Every new user-facing string is an i18n key** in `src/lib/i18n/`
   (`dictionaries/en.ts` canonical, `dictionaries/index.ts` translations,
   `translate.ts` lookup, `use-t.ts` hook) — never hardcoded in a component; that
   is also what keeps the next language cheap.
7. **A mechanism denylist exists as data**, not as reviewer taste:
   `policy.PLAIN_LANGUAGE_DENYLIST` in `python/harness/code/policy.py` contains
   `sandbox`, `worktree`, `workspace`, `allowlist`, `autonomy`, `digest`, `argv`,
   `cwd`, `stderr`, `stdout`, `patch`, `diff`, `manifest`, `operator`,
   `policy engine`, `tool registry`, `exit code`, `verification ledger`, `repo`,
   `repository`, `commit`, `branch`, `head`. The gate over it is **G8** in §9.
8. **Who sees what:**

| Who | What they meet | What they never meet |
|---|---|---|
| Analyst / journalist | "Eclipse kept getting one step wrong — here is the fix it prepared" | the target path outside "details" |
| Portfolio manager / advisor | a review card with *review it* / *leave it* | a patch, a diff, a digest |
| Trader / risk officer · accountant / controller | *"checked and ready"*, then *"put the previous version back"* after a regression | the test command, `exit code`, `rollback` (the word) |
| Student / teacher · small-business owner | why the change exists, in one sentence; a one-line note when a change helps | the candidate signature, any metric jargon |
| Software engineer in finance | the full trace, the ops, the digests, the ledger — via "details" and the run view | nothing is hidden from them on request |

## 5. Non-goals (do not do these)

- **No unsupervised self-modification.** No candidate activates itself; every
  activation is an operator decision recorded on a row.
- **No patch to a frozen file.** `python/harness/code/policy.py`,
  `python/harness/skills/permissions.py`, `python/harness/mcp/approvals.py` and
  `scripts/check-all.js` are non-patchable and a proposal that touches one is
  **refused with a structured error** — never silently skipped.
- **No second activation path.** `skills/versioning.py` is used verbatim — not
  forked, not wrapped in "v2", not reimplemented.
- **No LLM judge as the decision.** A model may propose; a deterministic check
  decides. Same rule as `skills/evaluation.py` and `code/verify.py`.
- **No second recurrence counter.** `persistence.record_learning_recurrence` /
  `LearningRecurrence` / `eclipse_memory.store.record_recurrence` are the counter.
  This phase reads them; it never maintains a rival count.
- **No new agent loop, no second tool registry, no new model adapter.**
- **No metric without measurement.** A figure that cannot be derived renders
  `UNKNOWN` in the report and "not measured yet" in the UI.
- **No change to the finance path** — `research/` and `retrieval/` are untouched.
- Do not commit, push, or open a PR. Do not commit `jdds.db`.

## 6. Exact contracts to create

### 6.1 The recurrence bridge — `python/harness/code/evolution.py`

```python
"""Turn a RECORDED recurrence into an INERT candidate. Nothing else.

A mistake is an observation (eclipse_memory/mistakes.py). This module is the one
place where an observation that keeps happening becomes a *proposal*. The
proposal is inert: it names a target and a set of structured operations, and it
changes nothing until activation succeeds through skills/versioning.py.

Two rules copied, not invented: recurrence is required (one occurrence is never
evidence — skills/learning.py), and no model call decides whether a candidate
exists.
"""
from __future__ import annotations

# A category must be observed this many times before it is evidence at all.
RECURRENCE_THRESHOLD = 3
MAX_CANDIDATES_PER_SCAN = 20   # a scan is a bounded window, not a replay

# Which mistake categories can propose a code change, and to what kind of target.
# A category absent from this table never yields a candidate — the absence is the
# policy, so it is DATA.
CATEGORY_TARGETS: dict[str, str] = {
    "invalid_output_schema":      "the schema/validator that rejected the output",
    "incorrect_tool_arguments":   "the tool argument validation that accepted a bad call",
    "repeated_failure":           "the retry/fallback path that kept failing",
    "timeout":                    "the bound that timed out",
    "unresolved_contradiction":   "the comparison rule that missed a conflict",
    "currency_mismatch":          "the unit/currency normalisation step",
    "unit_mismatch":              "the unit/currency normalisation step",
}

def candidates_from_mistakes(
    *,
    store: Any,                       # the one AgentMemoryStore connection
    since_iso: str,                   # window start; the scan is bounded
    max_candidates: int = MAX_CANDIDATES_PER_SCAN,
) -> list[EvolutionCandidate]:
    """Read the recurrence ledger; return INERT candidates for eligible
    categories whose count crosses RECURRENCE_THRESHOLD.

    Never creates a candidate: for a category missing from CATEGORY_TARGETS; from
    a single occurrence; when an identical signature already has one (dedupe on
    `signature`, as skills/learning.py does); or when the only target it can name
    is a FROZEN path (§6.3) — that becomes a `refused` candidate WITH its
    structured reason, so the refusal is visible rather than dropped.
    """
```

The bridge is **read-only against the mistake tables** and does exactly one
write: an inert `EvolutionCandidate` row — the same shape as a job's
`enabled=False` and MCP's "discovery is not activation".

### 6.2 The candidate and the attempt — persistence (`agent-memory.db`)

Additive, idempotent, in the style of `python/harness/persistence.py`, and
**old-row-safe** (a row written before these columns existed must still load). If
`persistence.py` is at its ratchet the helpers live in `code/evolution.py` bound to
the single `AgentMemoryStore` connection — the pattern `run_lineage.py` documents.

```sql
CREATE TABLE IF NOT EXISTS EvolutionCandidate (
  id                TEXT PRIMARY KEY,
  signature         TEXT NOT NULL UNIQUE,   -- category + normalized problem
  sourceCategory    TEXT NOT NULL,          -- a mistakes.CATEGORIES value
  observedCount     INTEGER NOT NULL,   -- read from LearningRecurrence
  problemStatement  TEXT NOT NULL,      -- plain, bounded, non-secret
  targetPath        TEXT,               -- NULL when refused before a target
  proposedOpsJson   TEXT,               -- code/patch.py ops, or NULL
  status            TEXT NOT NULL DEFAULT 'inert',
      -- inert|proposed|refused|evaluating|evaluated_ok|evaluated_bad|canaried
      -- |activated|rolled_back
  refusalCode       TEXT,               -- structured: FROZEN_PATH | PROTECTED | ...
  activatedVersion  TEXT,               -- the version id from versioning.py
  previousVersion   TEXT,               -- BOTH versions are preserved
  createdByRunId    TEXT,
  createdAt         TEXT NOT NULL,
  updatedAt         TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_evolution_candidate_status
  ON EvolutionCandidate(status, observedCount);

CREATE TABLE IF NOT EXISTS EvolutionAttempt (
  id             TEXT PRIMARY KEY,
  candidateId    TEXT NOT NULL,
  attemptIndex   INTEGER NOT NULL,
  targetPath     TEXT NOT NULL,
  baseDigest     TEXT NOT NULL,   -- the target's hash BEFORE the attempt
  diffDigest     TEXT NOT NULL,   -- the attempt's identity
  proposedOpsJson TEXT NOT NULL,
  evaluationJson TEXT,            -- per-check results + ledger execution ids
  outcome        TEXT NOT NULL,   -- success | failure | rolled_back | refused
  outcomeReason  TEXT,            -- non-secret, operator-facing
  costMicros     INTEGER,         -- NULL ⇒ UNKNOWN (never 0)
  tokensUsed     INTEGER,         -- NULL ⇒ UNKNOWN
  startedAt      TEXT NOT NULL,
  finishedAt     TEXT
);
CREATE INDEX IF NOT EXISTS idx_evolution_attempt_candidate
  ON EvolutionAttempt(candidateId, startedAt);
```

`costMicros` / `tokensUsed` are **nullable on purpose** so the metrics reader can
say *"not measured"*; a `0` there would be a lie the report could not detect.

### 6.3 The proposal — structured ops, the forbidden fields, the frozen set

A proposal is expressed with **`code/patch.py`'s structured operations** — the
same op vocabulary Phase 2 already defined — and is subject to the **same
forbidden-field discipline as `skills/patches.py`**, extended by the code
capability's own non-negotiables:

| Non-patchable | Why |
|---|---|
| `code/policy.py` · `skills/permissions.py` · `mcp/approvals.py` · `scripts/check-all.js` | the policy, permission, approval and release authorities — a subject cannot edit its own judge |
| everything in `policy.PROTECTED_PATHS` | already the code capability's protected set |
| identity, permissions, tool allowlists, risk class (the `skills/patches.py` `FORBIDDEN_FIELDS` set, as data) | an artifact may never widen authority (README §3.3) |

```python
class EvolutionRefusal(Exception):
    """A refusal with a STRUCTURED reason — never a bare ValueError."""
    def __init__(self, code: str, *, path: str | None = None, detail: str = "") -> None: ...

def propose_ops(candidate: EvolutionCandidate, *, actor: Actor) -> list[dict[str, Any]]:
    """Build and validate the structured ops for a candidate.

    Refuses with EvolutionRefusal and a code when: FROZEN_PATH (the target is one
    of the four frozen files); PROTECTED (policy.is_protected for another reason);
    FORBIDDEN_FIELD (the ops would set identity, permissions, a tool allowlist or a
    risk class); OUTSIDE_WORKSPACE (policy.resolve_within rejects the target);
    NOT_PATCHABLE (the op set is empty or names an op code/patch.py rejects).
    """
```

`propose_ops` performs **no model call** and is the only thing that can accept an
op set; a model-assisted proposal produces candidate ops this function validates.
Mirrors `research/claims.py` — a deterministic validator owns the decision.

### 6.4 Evaluation — a worktree through the Phase-4 ledger

A candidate is evaluated by **running the checks that own the change** inside a
Phase-2 worktree and recording every execution in the **Phase-4 verification
ledger** — so "it passed" is never a claim the model made.

```python
@dataclass
class EvaluationReport:
    candidateId: str
    targetPath: str
    checks: list[CheckOutcome]      # per-check results, never a blended score
    ledgerExecutionIds: list[str]   # the evidence, from the Phase-4 ledger
    passed: bool                    # deterministic: every owning check passed
    regression: bool                # a check that PASSED before now fails
    unmeasured: list[str]           # dimensions that could not be measured
```

| Check | Source | Required |
|---|---|---|
| the owning test file(s) of the target | derived from the target path, never guessed | yes |
| the Phase-9 kit acceptance test, when the target is inside a kit | `code/kits/` | yes, when applicable |
| "does anything else break" | the failing-check repair path of Phase 4 | yes on a regression |

**Deterministic first, always.** If any owning check fails, the candidate is
`evaluated_bad` and there is nothing for a model to overrule. Because every
execution goes through `code/verify.py`, an unbacked "everything passes" is marked
unverified — the same protection Phase 4 gives the answer path.

### 6.5 Activation — `skills/versioning.py`, reused verbatim

Activation is the **existing lifecycle applied to a code subject**:

```
propose      → versioning.propose_patch        (the §6.3 ops; a new version of the subject)
evaluate     → versioning.evaluate_version     (the §6.4 report is the evidence)
canary       → versioning.promote_canary       (+ versioning.canary_eligible)
activate     → versioning.activate_version     (operator-decided, recorded)
rollback     → versioning.rollback             (ATOMIC; BOTH versions preserved)
triggers     → versioning.check_rollback_triggers  (automatic, on a regression)
```

**This phase does not edit `skills/versioning.py`.** A small adapter in
`code/evolution.py` supplies the subject by answering the questions
`versioning.py` already asks (the current version, its metrics, a prior version).
If it cannot do so without editing `versioning.py`, the honest outcome is a partial
report naming the blocker — **not** a fork. An automatic trigger fires on a
**canary regression** (a check the canary passed and the activated version fails);
the rollback is atomic and the candidate keeps `activatedVersion` **and**
`previousVersion`, so both versions survive and the archive records why.

### 6.6 The attempt archive and the honest metrics

Every attempt is archived — success, failure and rolled back alike — with its
`diffDigest`, its evaluation evidence (`evaluationJson`, including the ledger
execution ids) and its outcome. An archive of only the successes is a marketing
document, not a record.
```python
def archive_metrics(window_days: int = 90) -> dict[str, Any]:
    """Every metric is derived from EvolutionAttempt rows.

    A metric whose inputs do not exist (no completed attempts, no cost rows)
    renders the string "UNKNOWN" — NEVER 0, and never a blended score.
    """
    return {
        "attempts": int,          # always measurable when a window is given
        "successRate": float | "UNKNOWN",
        "regressionRate": float | "UNKNOWN",
        "rollbackCount": int,
        "costPerSuccess": float | "UNKNOWN",  # UNKNOWN if any costMicros is NULL
        "perCategory": dict[str, dict[str, Any]],  # never collapsed to one number
        "unmeasured": list[str],  # named, so a reader can see the holes
    }
```
`perCategory` is mandatory: results are shown **per source mistake category**,
because one number lets a category that always fails hide behind one that always
succeeds.

### 6.7 Routes and events

New route group `python/harness/routers/evolution.py`, registered by `main.py` via
`app.include_router`; state comes from `deps.py`, never by importing `main`.

| Method + path | Auth | Purpose |
|---|---|---|
| `GET /evolution/candidates` | `require_operator` | list candidates with their plain state |
| `GET /evolution/candidates/{id}` · `/attempts` | `require_operator` | one candidate and its attempt archive |
| `POST /evolution/candidates/{id}/evaluate` | `require_operator` | run §6.4 in a worktree |
| `POST /evolution/candidates/{id}/activate` | `require_operator` | the operator decision (§6.5) |
| `POST /evolution/candidates/{id}/rollback` | `require_operator` | the manual rollback |
| `POST /evolution/candidates/{id}/dismiss` | `require_operator` | a terminal, recorded "no" |
| `GET /evolution/metrics` | `require_operator` | §6.6, with `UNKNOWN` holes named |

**Every route carries `require_operator` — reads included** (the MCP convention
ADR-H48 established): a candidate proposes a change to the app's own code, so none
of it is reachable without operator proof, and a body flag never authorizes.

Events ride the existing `RunEmitter` (no new emitter): `code.evolution.
candidate_created`, `.refused` (carrying the structured code), `.evaluated`,
`.activated`, `.rolled_back`.

### 6.8 UI — extend the existing learning journey, do not fork it

The journey already exists: `python/harness/learning_graph.py` builds it and
`src/components/screens/skills/learning-journey.tsx` renders it. This phase **adds
nodes and edges** — a repeated-problem node, its candidate node, its attempts —
behind that existing screen; a second "self-improvement screen" would split the
story the user is following and is out of scope. Front door:
`src/app/api/evolution/**` proxies → `src/lib/harness/evolution-client.ts` → the
journey components, frosted-glass conventions
(`.opencode/skills/black-eclipse-ui/SKILL.md`), sitting beside the existing research
UI (`ResearchEvidencePanel`, `src/components/chat/run-explanation-panel.tsx`).

### 6.9 Plain language

The candidate card, the plain states, every refusal and the metrics panel are new
user-visible strings: **i18n keys** in `src/lib/i18n/`, covered by §9 G8 against
`policy.PLAIN_LANGUAGE_DENYLIST`. "Details" is the only affordance allowed to quote
a mechanism word, quoting the machine value verbatim (`FROZEN_PATH`) —
paraphrasing a refusal reason is how a lie gets in.

## 7. Work items (ordered)

1. `docs/harness/roadmap/progress/phase-10-progress.md` with §9's gates as
   unchecked boxes.
2. Read in full first: `eclipse_memory/mistakes.py`,
   `skills/{learning,patches,versioning}.py`, `persistence.py` (the
   `LearningRecurrence` block), `code/{verify,worktree,patch}.py`; record the exact
   evidence line for each claim in this file.
3. §6.1 bridge + `python/tests/test_evolution_bridge.py` (pure, no clock, no model).
4. §6.2 DDL + store helpers, additive and old-row-safe, with
   `python/tests/test_evolution_persistence.py`.
5. §6.3 `propose_ops` + `python/tests/test_self_improvement_freeze.py` — the freeze
   test is a **required deliverable**.
6. §6.4 evaluation wired to the Phase-4 ledger and a Phase-2 worktree.
7. §6.5 the `versioning.py` subject adapter + activation and automatic rollback.
8. §6.6 the attempt archive + honest metrics.
9. §6.7 `routers/evolution.py` (never inline in `main.py`) + `include_router`.
10. §6.8 front door + the journey extension.
11. `python/tests/test_self_improvement_e2e.py` — the seeded journey, the canary
    rollback and the non-operator refusals (§9 G1/G2/G6).
12. ADR-H112 (Decision / Why / Consequences); `docs/CHANGELOG.md`; `NAVIGATION.md`.

## 8. Deliverables

| File | Change |
|---|---|
| `python/harness/code/evolution.py` | new — bridge, proposal, evaluation, adapter, metrics |
| `python/harness/persistence.py` | additive DDL for the two tables only |
| `python/harness/routers/evolution.py` | new route group |
| `python/harness/main.py` | `include_router` only |
| `python/harness/learning_graph.py` | new nodes/edges (extension, not a fork) |
| `python/tests/test_evolution_bridge.py` | new |
| `python/tests/test_self_improvement_freeze.py` | new — frozen/hardened targets refused |
| `python/tests/test_evolution_persistence.py` | new |
| `python/tests/test_self_improvement_e2e.py` | new — the seeded fixture journey |
| `src/app/api/evolution/**`, `src/lib/harness/evolution-client.ts` | new front door |
| `src/components/screens/skills/learning-journey.tsx`, `src/lib/i18n/dictionaries/{en,index}.ts` | journey extended; new key set |
| `docs/harness/decisions.md` | ADR-H112 |
| `docs/harness/roadmap/progress/phase-10-progress.md` | new |

## 9. Acceptance gates

```bash
# G1 — the seeded journey: mistake → candidate → proposal → evaluation → canary
./scripts/vendor/python/python.exe -m pytest python/tests/test_self_improvement_e2e.py -v

# G2 — a canary regression triggers an AUTOMATIC rollback, BOTH versions kept
./scripts/vendor/python/python.exe -m pytest python/tests/test_self_improvement_e2e.py -v -k "rollback"

# G3 — a proposal touching ANY frozen file is refused with a STRUCTURED error
./scripts/vendor/python/python.exe -m pytest python/tests/test_self_improvement_freeze.py -v

# G4 — the recurrence bridge: criteria-driven and read-only
./scripts/vendor/python/python.exe -m pytest python/tests/test_evolution_bridge.py -v

# G5 — the archive survives a restart (close, reopen: every attempt preserved)
./scripts/vendor/python/python.exe -m pytest python/tests/test_evolution_persistence.py -v

# G6 — every evolution route refuses a non-operator (reads and mutations)
./scripts/vendor/python/python.exe -m pytest python/tests/test_self_improvement_e2e.py -k non_operator -v

# G7 — the suite + the release gate
npm run test && npm run check:all

# G8 — plain-language gate (see §4): the card, the plain states, refusals, metrics
npx vitest run src/lib/i18n/plain-language.test.ts
./scripts/vendor/python/python.exe -m pytest python/tests/test_plain_language.py -q
# every new string is an i18n key, free of policy.PLAIN_LANGUAGE_DENYLIST; the
# machine reason appears ONLY inside the "details" affordance
```

| Gate | Assertion |
|---|---|
| G1 | A seeded failing-fixture mistake, observed ≥ `RECURRENCE_THRESHOLD` times, produces an inert candidate; the candidate produces structured ops; evaluation records real ledger executions; activation is canaried and operator-decided. Each of the five steps is present in the trace — asserted by reading the events, not by asserting a status string. |
| G1b | The candidate created in G1 is `inert` and **the target file on disk is byte-identical** until activation — asserted by hashing the target before and after. |
| G2 | A check that the canary passed and the activation fails triggers the automatic rollback; `activateVersion` **and** `previousVersion` are both preserved on the candidate row, and an `EvolutionAttempt` records `rolled_back` with its digest and evidence. |
| G3 | A proposal whose target is `code/policy.py`, `skills/permissions.py`, `mcp/approvals.py` or `scripts/check-all.js` raises `EvolutionRefusal` with `code="FROZEN_PATH"`; a proposal that would set a permission, a tool allowlist, a risk class or an identity field is refused with its own code; a `PROTECTED_PATHS` member is refused; nothing on disk changes on any of them. |
| G4 | Two observations do **not** produce a candidate; a category absent from `CATEGORY_TARGETS` never produces one; a duplicate signature does not produce a second; the bridge performs no write to the mistake tables (assert the row counts are unchanged). |
| G5 | Every `EvolutionCandidate` and `EvolutionAttempt` field round-trips across a store close/reopen, including `diffDigest`, `evaluationJson` and the nullable cost columns; a row written without the new columns still loads. |
| G6 | Every route in §6.7 refuses a non-operator — the `test_read_routes_refuse_a_non_operator` convention copied from the MCP route group. |
| G7 | Full suite + `check:all` green; the frozen four files are byte-unchanged. |
| G8 | Plain language: every new journey / candidate / refusal / metrics string is an i18n key and contains no term from `policy.PLAIN_LANGUAGE_DENYLIST`; each refusal is ONE plain sentence plus a next step, with the machine reason only behind "details"; a metric that cannot be measured reads "not measured yet" and renders `UNKNOWN` in the report — never 0. |

## 10. Definition of done

- Every gate run, raw output pasted, observed counts recorded.
- `skills/{versioning,patches}.py` are **byte-unchanged** — a fork or a "v2" would
  be a silent second mechanism.
- No candidate reaches `activated` without an operator decision — grep the
  activation call site and confirm `require_operator` precedes it on every path.
- The four frozen files are byte-unchanged, and `test_self_improvement_freeze.py`
  proves touching one is refused rather than dropped.
- Every attempt — failures and rollbacks included — is in `EvolutionAttempt` with
  a `diffDigest` and evaluation evidence.
- `archive_metrics` returns `UNKNOWN` (not `0`) whenever a dimension is
  unmeasurable; no blended score exists anywhere in the module.
- The UI is the EXISTING learning journey, extended; no second self-improvement
  screen was added.
- ADR-H112 written; `docs/CHANGELOG.md` + `NAVIGATION.md` updated; `status:` flipped
  here and in the index.

## 11. Implementation prompt (copy this to OpenCode)

```text
Task: Phase 10 — Self-Improvement v2: evolving CODE as well as skills
(Eclipse-as-a-Harness roadmap).

Read first, in full:
- docs/harness/roadmap/phase-10-self-improvement.md   (this phase, verbatim)
- docs/harness/roadmap/README.md  (invariants §3 — especially 3.1 one runtime,
  3.3 artifacts stay inert, and §4 work in flight)
- python/harness/skills/versioning.py  ← the lifecycle you REUSE VERBATIM
  (propose_patch, evaluate_version, activate_version, promote_canary, rollback,
  check_rollback_triggers, version_history). Do not fork it. Do not edit it.
- python/harness/skills/patches.py     ← FORBIDDEN_FIELDS and the
  forbid-identity/permission/tool/risk discipline you copy
- python/harness/skills/learning.py    ← candidate criteria + the recurrence rule
  (a single occurrence is never evidence)
- python/harness/eclipse_memory/mistakes.py  ← the deterministic categories, each
  carrying evidence; "a mistake is a recorded observation"
- python/harness/persistence.py (LearningRecurrence, record_learning_recurrence),
  python/harness/eclipse_memory/store.py (record_recurrence)  ← the ONE counter,
  read-only here
- python/harness/code/{policy,patch,worktree,verify}.py  ← the freeze set, the
  structured ops, the worktree, and the Phase-4 ledger you record into
- python/harness/routers/mcp.py  ← the route-group convention (registered by
  main.py via include_router; state from deps.py; NEVER import main)
- python/harness/learning_graph.py + src/components/screens/skills/learning-journey.tsx
  ← the journey you EXTEND (never fork)

Goal: a mistake category whose recurrence crosses a threshold becomes an INERT
learning candidate; a code-shaped candidate becomes a proposed change expressed
with code/patch.py ops; evaluation runs the owning test file(s) and any Phase-9 kit
acceptance test inside a worktree through the Phase-4 verification ledger;
activation reuses skills/versioning.py verbatim; every attempt is archived with its
diff digest, evidence and outcome; metrics are honest (UNKNOWN, never 0).

In scope:
1. code/evolution.py — candidates_from_mistakes(store=, since_iso=,
   max_candidates=) reading the existing recurrence ledger. RECURRENCE_THRESHOLD=3.
   CATEGORY_TARGETS maps eligible mistake categories to the KIND of target; a
   category absent from the table never yields a candidate. Read-only against the
   mistake tables; the only write is an inert EvolutionCandidate row. Dedupe on a
   deterministic signature (as skills/learning.py does).
2. EvolutionCandidate + EvolutionAttempt in agent-memory.db — additive,
   idempotent, OLD-ROW-SAFE. If persistence.py is at its ratchet, own the helpers
   in code/evolution.py bound to the single AgentMemoryStore connection. costMicros
   and tokensUsed are NULLABLE so "not measured" is representable.
3. propose_ops(candidate, actor) → code/patch.py op dictionaries, validated
   deterministically. Raise EvolutionRefusal(code=...) with codes FROZEN_PATH,
   PROTECTED, FORBIDDEN_FIELD, OUTSIDE_WORKSPACE, NOT_PATCHABLE. The FROZEN set is
   exactly python/harness/code/policy.py, python/harness/skills/permissions.py,
   python/harness/mcp/approvals.py, scripts/check-all.js — plus policy.PROTECTED_PATHS
   and the skills/patches.py FORBIDDEN_FIELDS (identity, permissions, tool
   allowlists, risk class). No model call decides a proposal.
4. Evaluation: run the target's owning test file(s) + any Phase-9 kit acceptance
   test inside a Phase-2 worktree and record EVERY execution in the Phase-4
   VerificationLedger. Deterministic checks first; a model may explain an outcome,
   never change one. Per-check results — never a blended score.
5. Activation through skills/versioning.py UNCHANGED, with a small subject adapter
   in code/evolution.py. Canary regression → the EXISTING automatic rollback
   trigger; the rollback must preserve BOTH versions (activatedVersion AND
   previousVersion). If the adapter cannot express a code subject without editing
   versioning.py, STOP and report the blocker — do not fork the lifecycle.
6. The attempt archive: record success, failure, refusal AND rolled_back, each with
   diffDigest, baseDigest, evaluationJson (incl. ledger execution ids) and outcome.
   archive_metrics() returns per-category results and the string "UNKNOWN" for any
   dimension it cannot measure — NEVER 0 as a stand-in, NEVER one blended score.
7. routers/evolution.py — every route behind require_operator (READS TOO, as the
   MCP group was hardened to do); register via app.include_router in main.py. Events
   ride the existing RunEmitter: code.evolution.{candidate_created, refused,
   evaluated, activated, rolled_back}.
8. UI: EXTEND python/harness/learning_graph.py and
   src/components/screens/skills/learning-journey.tsx with repeated-problem,
   candidate and attempt nodes — do NOT create a second self-improvement screen.
   Front door: src/app/api/evolution/** + src/lib/harness/evolution-client.ts.
9. All new user-facing copy is an i18n KEY in src/lib/i18n/ (en.ts canonical,
   index.ts translations, translate.ts lookup, use-t.ts hook) — never hardcoded in
   a component. Plain states read as sentences: "Prepared — not applied" /
   "Checked and ready" / "That change made things worse, so I put the previous
   version back". One plain sentence plus a next step per refusal.
10. Tests: test_evolution_bridge.py, test_evolution_persistence.py,
    test_self_improvement_freeze.py, test_self_improvement_e2e.py (the seeded
    journey, the canary rollback, the non-operator refusals).
11. ADR-H112 in docs/harness/decisions.md using the repo's shape — '## ADR-H112 — Title'
    then **Decision.** / **Why.** / **Consequences.** (NOT "Impact"). Plus a dated
    docs/CHANGELOG.md entry and docs/NAVIGATION.md rows.

Non-goals (do NOT do these):
- No unsupervised self-modification; every activation is an operator decision.
- Do NOT edit or fork skills/versioning.py, skills/patches.py,
  skills/permissions.py, code/policy.py, mcp/approvals.py or scripts/check-all.js.
- No LLM judge as the gate; no second improvement mechanism; no second recurrence
  counter; no second agent loop or tool registry.
- No metric rendered as 0 when it is unmeasurable; no blended score.
- Never commit, push, or open a PR. Do not commit jdds.db.

Acceptance gates — run each and paste the RAW output into
docs/harness/roadmap/progress/phase-10-progress.md:
  ./scripts/vendor/python/python.exe -m pytest python/tests/test_self_improvement_e2e.py -v
  ./scripts/vendor/python/python.exe -m pytest python/tests/test_self_improvement_freeze.py -v
  ./scripts/vendor/python/python.exe -m pytest python/tests/test_evolution_bridge.py -v
  ./scripts/vendor/python/python.exe -m pytest python/tests/test_evolution_persistence.py -v
  npm run test && npm run check:all
  npx vitest run src/lib/i18n/plain-language.test.ts
  ./scripts/vendor/python/python.exe -m pytest python/tests/test_plain_language.py -q

Finish by stating: "docs updated: <files>" or "no doc change — <reason>".
```

---

**Next:** [Phase 11 — Surface and scale](./phase-11-surface-and-scale.md)
