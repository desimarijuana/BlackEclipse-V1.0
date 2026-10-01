---
title: "Phase 4 — Verify-and-Repair Loop (the Trust Spine)"
status: Done
phase: 4
depends_on: [3]
unlocks: [5]
last-verified: 2026-10-01
---

# Phase 4 — Verify-and-Repair Loop (the Trust Spine)

| | |
|---|---|
| **Depends on** | Phase 3 (the sandboxed command broker — no check can be recorded until commands can run) |
| **Unlocks** | Phase 5 (the coding agent may only be given autonomy once its own output is verifiable) |
| **Estimated work** | 3–5 h of agent time; new modules + additive persistence + one UI panel |
| **Deliverable type** | 2 new Python modules + a deterministic answer renderer + additive run persistence + 6 new mistake categories + 1 UI panel + tests + 1 ADR |
| **New ADRs** | ADR-H106 |
| **Prompt to copy** | [§11 below](#11-implementation-prompt-copy-this-to-opencode) |

## Contents

- [1. Goal](#1-goal)
- [2. Why this phase exists (the problem in the real code)](#2-why-this-phase-exists-the-problem-in-the-real-code)
- [3. In scope](#3-in-scope)
- [4. Who can use it (the non-expert obligation)](#4-who-can-use-it-the-non-expert-obligation)
- [5. Non-goals (do not do these)](#5-non-goals-do-not-do-these)
- [6. Exact contracts to create](#6-exact-contracts-to-create)
  - [6.1 The ledger — `python/harness/code/verify.py`](#61-the-ledger--pythonharnesscodeverifypy)
  - [6.2 Answer-path enforcement — the renderer (`verify.py`, same module)](#62-answer-path-enforcement--the-renderer-verifypy-same-module)
  - [6.3 The bounded repair loop — `python/harness/code/repair.py`](#63-the-bounded-repair-loop--pythonharnesscoderepairpy)
  - [6.4 Additive persistence — `python/harness/persistence.py`](#64-additive-persistence--pythonharnesspersistencepy)
  - [6.5 Mistakes — `python/harness/eclipse_memory/mistakes.py`](#65-mistakes--pythonharnesseclipse_memorymistakespy)
  - [6.6 Events (existing `RunEmitter`; no new emitter)](#66-events-existing-runemitter-no-new-emitter)
  - [6.7 Front door + UI](#67-front-door--ui)
  - [6.8 The eval pack — `python/harness/code/eval/`](#68-the-eval-pack--pythonharnesscodeeval)
- [7. Work items (ordered)](#7-work-items-ordered)
- [8. Deliverables](#8-deliverables)
- [9. Acceptance gates](#9-acceptance-gates)
- [10. Definition of done](#10-definition-of-done)
- [11. Implementation prompt (copy this to OpenCode)](#11-implementation-prompt-copy-this-to-opencode)

## 1. Goal

Make a code claim **checkable against a record of an actual execution**, so an
answer can never say "all tests pass" unless a test command really ran, in this
run, and really exited zero.

This is the highest-leverage phase in the roadmap. Phases 0–3 make it possible to
*change code*; Phase 4 is what makes the change *trustworthy*. Financial output
already has this property — retrieval → coverage → validator → receipt — and it is
the reason the finance agent can be believed. Phase 4 builds the exact same
discipline for the code domain: **a check is passing only when the executor
recorded it, and an unverified claim is marked, never asserted.**

Concretely it ships three things:

1. `python/harness/code/verify.py` — a per-run **VerificationLedger**: what the
   model *asserted* passed, what the ledger *proves* passed, and the difference.
2. `python/harness/code/repair.py` — the **plan → edit → check → repair → check**
   sub-flow with a bounded attempt count and a wall-clock/cost budget. Extracted
   out of `graph.py` on purpose (see §5 and README §3.7).
3. **Answer-path enforcement** — the final-answer renderer consults the ledger.
   A sentence asserting a passing check with no matching successful execution is
   either removed or emitted with an explicit `UNVERIFIED` marker.

## 2. Why this phase exists (the problem in the real code)

Phase 3 ends with a command broker that can run `unit_test`, `python_test`,
`typecheck`, `lint`, `build`, `format_check`, `git_read` and refuse
`dependency_install` (README §2, `COMMAND_CLASSES` in `code/policy.py`). It
records executions. Nothing *reads* those records when the answer is written.

The trust gap is visible in the runtime today. In `graph.py` the final turn is
forced, and the only instruction the model gets about honesty is about **missing
data**, not about **unchecked claims**:

```python
# python/harness/model_stream.py
FINALIZE_INSTRUCTION = (
    "You have reached the last allowed step. Tools are no longer available. "
    "Answer the user's request NOW using only the information already gathered "
    "above. Do not call tools, do not describe what you would do, and do not ask "
    "for permission. If some data was unavailable, say so plainly in the answer."
)
```

and `graph.py` uses it on the final step:

```python
        budget_spent = max_tool_calls is not None and state.get("tool_calls", 0) >= max_tool_calls
        finalizing = step >= max_steps or budget_spent
        active_model = model if finalizing else model_with_tools
        model_messages = (
            [*state["messages"], HumanMessage(content=_FINALIZE_INSTRUCTION)]
            if finalizing
            else state["messages"]
        )
```

That is a **prose** instruction. README §3.2 states the invariant plainly:
*prose is not a security boundary.* A model that skipped the test run, or whose
run failed, can still write "All tests pass." Nothing in the runtime contradicts
it.

The finance path solved this exact problem with a different discipline, and the
shape is the template. From `research/claims.py`:

> ID validation does NOT prove semantic entailment. Where meaning cannot be
> checked deterministically the claim is marked `needs_review` and presented as
> unverified. The model is never the sole gate; a deterministic check owns the
> decision.

and the renderer already refuses to echo an unsupported claim back as fact:

```python
        # Never echo an unsupported claim's text — it may embed a fabricated
        # figure. Report the failure reason and the leg/kind instead.
```

`eclipse_memory/mistakes.py` carries the matching rule for observability:

> A mistake is a *recorded observation*; it becomes a reusable improvement only
> through the existing gated learning pipeline.

README §2 names the gap directly: *"No independent verification of its own
output. Market claims are verified rigorously (retrieval → coverage → validator →
receipt); code claims have no equivalent. 'The command I say passed' has no
executor to back it."* Phase 4 closes it, in the same shape and the same
vocabulary as the research validator — new domain, identical discipline.

## 3. In scope

1. New `python/harness/code/verify.py` — `VerificationLedger`, `CheckClaim`,
   `VerificationRecord`, the deterministic claim parser, and `enforce_answer`.
2. New `python/harness/code/repair.py` — the bounded verify-and-repair sub-flow
   with `max_repair_attempts` (default 2) and a total wall-clock/cost budget.
3. Wire both into the existing `execute_run` graph — **as calls, not as graph
   nodes**: the graph keeps ownership of the loop; `repair.py` owns the
   plan/edit/check/repair policy and returns an outcome.
4. Persist the ledger additively on the run (`HarnessRun.codeVerification`),
   old-row-safe exactly like `HarnessRun.context`.
5. Extend `eclipse_memory/mistakes.py` with six deterministic code categories.
6. A new run event family (`code.verify.*`, `code.repair.*`).
7. New `src/components/chat/code-verification-panel.tsx` beside
   `research-evidence-panel.tsx`, plus the TS types it reads.
8. New `python/harness/code/eval/` — a labelled dataset of claim/ledger pairs and
   a `python -m harness.code.eval` runner (mirrors `research/eval/` and
   `eclipse_memory/eval/`: `dataset_v1.json` + `THRESHOLDS` + `check_thresholds`
   + `format_report` + `__main__.py`).
9. ADR-H106.

## 4. Who can use it (the non-expert obligation)

This capability is **not for engineers and quants**. Every finance professional —
analyst, portfolio manager, trader, advisor, accountant, risk officer, student,
journalist, small-business owner — must be able to use it without knowing Python,
git, worktrees, terminals or what an "allowlist" is. A capability only an engineer
can drive has not shipped.

**The user never sees the machinery.** They state a task in plain language
("check my portfolio for risks overnight") and get a plain result. The workspace,
the policy engine, the checks and the approval machinery are invisible; they live
in the trace, not on the screen.

**Vocabulary rule.** Every string a non-engineer can see names the *finance job*,
never the mechanism:

| Say | Never say |
|---|---|
| "Run the test suite" / "Check it still works" | "unit_test class", "exit code" |
| "Proof it works" | "verification ledger" |
| "Not checked yet" / "I could not confirm this" | "UNVERIFIED" (internal wire value only) |
| "Something blocked that step" | "OUTSIDE_WORKSPACE", "SANDBOX_UNAVAILABLE" |
| "9.8 seconds" | "duration_ms", "output digest" |

Mechanism words — *sandbox, worktree, workspace, allowlist, autonomy, digest,
argv, cwd, stderr, patch, diff, manifest, operator, policy engine, tool registry,
exit code, verification ledger* — stay in logs, events and the run trace. A user
sees them only through a deliberate "details" affordance that quotes the
technical reason verbatim.

**Where the strings live.** The repo already has an i18n layer:
`src/lib/i18n/` — `dictionaries/en.ts` holds the canonical keys,
`dictionaries/index.ts` the translations, `translate.ts` the lookup, `use-t.ts`
the hook. New user-facing copy is added **there as keys**, never hardcoded in a
component. Hardcoded copy is untranslatable and invisible to the jargon gate.

**Refusals a human can read.** A refused action explains, in one plain sentence,
what was blocked and what the user can do, with the technical reason behind a
"details" affordance (the event already carries the `code`):
*"I did not run that — it needs the app owner's OK. Ask them and I'll continue."*
never *"PROFILE_DENIED"*.

**This phase specifically.** The verification panel must not say "verification
ledger", "exit code" or "output digest". It is titled **"Proof it works"** and
lists plain lines — *"Tests passed — 1941 tests, 9.8 seconds"* / *"Could not
check — the test command was blocked"*. The marker appended to an unbacked claim
is plain too: *"not checked yet"* / *"I could not confirm this"*, never
"UNVERIFIED" in the UI. `UNVERIFIED_MARKER` stays the internal wire value on the
run event and in the persisted blob; the renderer maps it to the plain strings
declared in `en.ts`. This is enforced by a **jargon gate** — a vitest over the new
UI strings and i18n keys, `src/lib/i18n/plain-language.test.ts`, that fails if a
new user-facing string contains a denylisted mechanism word (see §9).

## 5. Non-goals (do not do these)

- **No new graph nodes, no second agent loop, no second registry.** `graph.py`
  stays the one loop; `repair.py` is a *function it calls*.
- **No unbounded retry.** A repair loop that runs until it passes is the failure
  mode this phase exists to prevent.
- **No change to the finance path.** `research/claims.py`, `retrieval/`,
  `research/receipt.py` are untouched; Phase 4 only *mirrors* their discipline.
- **No new command classes**, no widening of `COMMAND_CLASSES`, no network, no
  `dependency_install`.
- **No second approval mechanism** — that is Phase 5.
- **No LLM judge as the gate.** A model may propose a repair; it never decides
  whether a check passed. (Same rule as `skills/evaluation.py`.)
- Do not commit, push, or open a PR. Do not commit `jdds.db`.

## 6. Exact contracts to create

### 6.1 The ledger — `python/harness/code/verify.py`

```python
"""The per-run VerificationLedger: what was asserted passed vs. what is proven.

A check is passing ONLY when this module holds a record of an actual execution
whose exit code is zero. Nothing here trusts prose, a model summary, or a tool
description. Mirrors research/claims.py: a deterministic check owns the decision
and anything that cannot be checked is presented as UNVERIFIED, never as fact.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

from .policy import COMMAND_CLASSES

# Bounded so a pathological run cannot turn the ledger into a log.
MAX_LEDGER_RECORDS = 200
MAX_CLAIM_SENTENCES = 500
MAX_OUTPUT_DIGEST_CHARS = 64
# Only the head+tail of an output is ever hashed for display; the digest is over
# the FULL normalized output so a truncated view can never validate a claim.
DIGEST_HEAD = 4_000
DIGEST_TAIL = 4_000

ClaimKind = Literal["tests_pass", "typecheck_clean", "build_ok", "lint_clean"]

# The classes that may satisfy each claim kind. A claim is supported when a
# zero-exit record exists whose class is IN this set.
CLAIM_CLASSES: dict[str, tuple[str, ...]] = {
    "tests_pass": ("unit_test", "python_test"),
    "typecheck_clean": ("typecheck",),
    "build_ok": ("build",),
    "lint_clean": ("lint",),
}

# Deterministic, sentence-level patterns. Deliberately narrow: a phrase that is
# not matched is not a check claim and is left alone. A negation ("the tests did
# not run", "I could not run the build") must NOT match — that is the honest case.
CLAIM_PATTERNS: tuple[tuple[ClaimKind, "re.Pattern[str]"], ...] = (
    ("tests_pass",       re.compile(r"\b(all\s+|the\s+)?tests?\s+(pass(ed|es)?|are\s+(passing|green)|green|succeeded)\b|\btest\s+suite\s+(passes|passed|is\s+green)\b", re.I)),
    ("typecheck_clean",  re.compile(r"\btype[\s-]?check(ing)?\s+(passes|passed|is\s+clean|succeeds)\b|\bno\s+type\s+errors?\b|\btsc\b[^.\n]{0,40}\b(clean|passes)\b", re.I)),
    ("build_ok",         re.compile(r"\bbuild\s+(succeeds|succeeded|passes|passed|is\s+green)\b|\bbuilds?\s+cleanly\b|\bcompiles?\s+(cleanly|without\s+errors)\b", re.I)),
    ("lint_clean",       re.compile(r"\blint(ing)?\s+(is\s+)?(clean|passes|passed)\b|\bno\s+lint\s+(errors|warnings)\b|\beslint\b[^.\n]{0,40}\b(clean|passes)\b", re.I)),
)

# The marker appended to a claim that could not be backed. It is loud on purpose
# and is never hidden in a tooltip.
UNVERIFIED_MARKER = " [UNVERIFIED — no successful {class_list} execution in this run]"

def output_digest(output: str) -> str:
    """A stable digest of an execution's FULL normalized output.

    Normalization: CRLF→LF, trailing whitespace per line stripped, trailing
    newlines collapsed. Two identical runs share a digest; a different output
    (even by one line) does not, so a digest shown in the UI always names the
    exact output that was checked. Hashed over the FULL text, never a truncated
    view — a clipped output must never be able to validate a claim.
    """
    ...  # sha256 of the normalized text

class CheckClaim(BaseModel):
    """One sentence of the FINAL answer that asserts a check passed."""
    sentence: str
    kind: ClaimKind
    matchedClasses: list[str] = Field(default_factory=list)   # from CLAIM_CLASSES[kind]
    supported: bool = False
    evidenceExecutionId: Optional[str] = None                 # HarnessCommandExecution.id
    evidenceDigest: Optional[str] = None                      # output_digest of that execution
    charStart: int = 0
    charEnd: int = 0

@dataclass(frozen=True)
class VerificationRecord:
    """The proof: one command execution, as the executor recorded it."""
    command_execution_id: str      # HarnessCommandExecution.id (Phase 3)
    command_class: str             # must be in policy.COMMAND_CLASSES
    exit_code: int
    duration_ms: int
    output_digest: str
    argv: tuple[str, ...] = ()
    started_at: str = ""           # ISO-8601
    workspace_id: Optional[str] = None

    @property
    def passed(self) -> bool:
        return self.exit_code == 0
    @classmethod
    def from_entry(cls, entry: dict[str, Any]) -> "VerificationRecord":
        """Rebuild from a serialized blob entry; raises on a malformed row so the
        caller can DROP it rather than guess."""
        ...

class VerificationLedger:
    """Per-run ledger. Constructed by execute_run, consulted by the renderer.

    NOT a graph node and NOT a store — it is a bounded value object that a run
    fills as commands execute, then serializes to `HarnessRun.codeVerification`.
    """

    def __init__(self, run_id: str, *, max_records: int = MAX_LEDGER_RECORDS) -> None:
        self.run_id = run_id
        self._records: list[VerificationRecord] = []
        self._max_records = max(1, int(max_records))

    # ── recording ──────────────────────────────────────────────────────────
    def record(
        self,
        *,
        command_execution_id: str,
        command_class: str,                 # MUST be in policy.COMMAND_CLASSES
        exit_code: int,
        duration_ms: int,
        output: str = "",
        argv: tuple[str, ...] = (),
        started_at: str = "",
        workspace_id: Optional[str] = None,
    ) -> VerificationRecord:
        """Record an execution. Refuses (raises ValueError) on an unknown class
        so a typo in Phase 3 can never invent a class that satisfies a claim."""
        ...  # build a VerificationRecord, append; drop the OLDEST past max_records

    # ── the three questions ────────────────────────────────────────────────
    def claims(self, answer: str) -> list[CheckClaim]:
        """What the model ASSERTED passed. Deterministic; no model call."""
        ...  # split into sentences; first matching CLAIM_PATTERN wins per sentence

    def verified(self, command_class: Optional[str] = None) -> list[VerificationRecord]: ...
    def failed(self, command_class: Optional[str] = None) -> list[VerificationRecord]: ...
    #      ^ what the ledger PROVES passed / failed: zero-exit / non-zero records
    #        (optionally filtered to one class).

    def unverified_claims(self, answer: str) -> list[CheckClaim]:
        """The DIFFERENCE: asserted-passed minus proven-passed. Resolves each
        claim's support status and returns only the unsupported ones.

        A claim is supported when a ZERO-EXIT record exists whose class is in
        `claim.matchedClasses`; the most recent such record becomes its evidence
        (`evidenceExecutionId` + `evidenceDigest`). When only FAILING records
        exist for those classes, the most recent failing record is still named as
        the evidence, so the marker can say "the check ran and FAILED" rather than
        "no check ran".
        """
        ...  # per claim: set supported/evidence; return the unsupported subset

    # ── serialization (additive, bounded, old-row-safe) ────────────────────
    def to_blob(self) -> dict[str, Any]:
        """Bounded JSON for `HarnessRun.codeVerification` — one entry per record:
        commandExecutionId, commandClass, exitCode, durationMs, outputDigest,
        argv, startedAt, workspaceId; plus `recordCount` and `truncated`."""
        ...

    @classmethod
    def from_blob(cls, run_id: str, blob: Optional[dict[str, Any]]) -> "VerificationLedger":
        """Rehydrate for a resumed run. A missing/garbled blob yields an EMPTY
        ledger — never a fabricated one, so a resumed run starts unverified."""
        ...  # drop malformed rows, never guess; a missing/garbled blob ⇒ EMPTY

def _sentence_spans(text: str) -> list[tuple[str, int, int]]:
    """Sentence → (text, charStart, charEnd). Newlines and bullets each end a
    sentence, so a bulleted list is checked line-by-line, not as one blob."""
    ...

def _matches_any(sentence: str) -> Optional[str]:
    """The first CLAIM kind whose pattern matches, or None. Case-insensitive."""
    ...
```

### 6.2 Answer-path enforcement — the renderer (`verify.py`, same module)

```python
EnforcementMode = Literal["mark", "strip"]

class AnswerEnforcement(BaseModel):
    answer: str
    enforced: bool = False
    marked: list[CheckClaim] = Field(default_factory=list)     # claims kept with UNVERIFIED
    stripped: list[CheckClaim] = Field(default_factory=list)   # claims removed
    note: Optional[str] = None

def enforce_answer(
    answer: str,
    ledger: VerificationLedger,
    *,
    mode: EnforcementMode = "mark",
) -> AnswerEnforcement:
    """Make the answer consistent with the ledger. Deterministic, no model call.

    `mark` (default): keep the sentence and append UNVERIFIED_MARKER naming the
    command classes that could have supported it. `strip`: remove the sentence
    outright. Either way an unbacked pass-claim is never rendered as a fact —
    the same rule `render_prose` already applies to unsupported financial claims.
    """
```

**Chosen default: `mark`.** Stripping loses information the operator needs (the
model *believed* a check passed — that is itself a finding). Marking keeps the
sentence, states the truth next to it, and produces a visible artifact for the
UI. `strip` remains available for a caller that wants it.

### 6.3 The bounded repair loop — `python/harness/code/repair.py`

```python
"""Plan → edit → check → (fail) → repair → check, bounded and honest.

EXTRACTED out of graph.py on purpose: graph.py is at its file-size ratchet
(README §3.7) and this is policy, not loop mechanics. `execute_run` CALLS
`run_verify_repair`; it does not gain a node. On exhaustion the loop STOPS and
reports the failing check with its output digest — it never keeps trying.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Literal, Optional

from pydantic import BaseModel, Field

DEFAULT_MAX_REPAIR_ATTEMPTS = 2
DEFAULT_MAX_WALL_CLOCK_S = 900          # 15 min for the whole sub-flow
DEFAULT_MAX_COST_USD = 1.50             # per-run ceiling; None = no cost bound

RepairStatus = Literal["passed", "unrepairable", "budget_exhausted", "refused", "no_checks"]

@dataclass(frozen=True)
class RepairBudget:
    max_attempts: int = DEFAULT_MAX_REPAIR_ATTEMPTS
    max_wall_clock_s: int = DEFAULT_MAX_WALL_CLOCK_S
    max_cost_usd: Optional[float] = DEFAULT_MAX_COST_USD

    def exceeded(self, *, attempts: int, elapsed_s: float, cost_usd: float) -> Optional[str]:
        """Return the reason the budget is spent ("attempts"|"wall_clock"|"cost"),
        or None. Checked BEFORE each attempt, so the bound is never crossed."""
        ...

class RepairAttempt(BaseModel):
    attempt: int
    failingClass: Optional[str] = None
    exitCode: Optional[int] = None
    outputDigest: Optional[str] = None
    commandExecutionId: Optional[str] = None
    editSummary: Optional[str] = None
    outcome: Literal["passed", "still_failing", "edit_refused", "check_unavailable"] = "still_failing"

class RepairOutcome(BaseModel):
    status: RepairStatus
    repairAttempts: int = 0
    maxAttempts: int = DEFAULT_MAX_REPAIR_ATTEMPTS
    checks: list[str] = Field(default_factory=list)          # command classes run
    attempts: list[RepairAttempt] = Field(default_factory=list)
    failedClass: Optional[str] = None
    failedExitCode: Optional[int] = None
    failedOutputDigest: Optional[str] = None
    stoppedReason: Optional[str] = None                      # "attempts"|"wall_clock"|"cost"
    note: Optional[str] = None

@dataclass
class CheckResult:
    """The seam return: an execution's outcome, or `available=False` (no sandbox)."""
    command_execution_id: str
    command_class: str
    exit_code: int
    duration_ms: int
    output: str = ""
    available: bool = True

# The two seams this module calls. Both already exist as Phase 1–3 surfaces.
CheckFn = Callable[[str], Awaitable[CheckResult]]                  # class -> CheckResult
EditFn = Callable[[RepairAttempt, str], Awaitable[Optional[str]]]  # (attempt, reason) -> edit summary

async def run_verify_repair(
    *,
    run_id: str,
    binding: Any,                     # code.policy.WorkspaceBinding
    checks: list[str],                # command classes, ordered
    ledger: Any,                      # code.verify.VerificationLedger
    run_check: CheckFn,
    make_edit: EditFn,
    budget: RepairBudget = RepairBudget(),
    emitter: Any = None,
    clock: Callable[[], float] = __import__("time").monotonic,
) -> RepairOutcome:
    """Run the checks; if one fails, edit and re-check, bounded by `budget`.
    NEVER loops past the budget; NEVER swallows a refusal as a pass."""
```

Behaviour, in order, and it must be exactly this:

1. **Check.** Run each class in `checks` through `run_check`. Every result is
   recorded on the ledger (`ledger.record(...)`), pass *and* fail.
2. **All green** → `status="passed"`, no repair. Emit `code.repair.passed`.
3. **A check failed** → consult `budget.exceeded(...)` **before** editing.
   - Budget spent → `status="unrepairable"` (or `"budget_exhausted"` when the
     reason is a time/cost bound), `stoppedReason` set, `failedClass` +
     `failedOutputDigest` set. **Stop.** Emit `code.repair.exhausted`.
   - Budget available → `make_edit(...)`; a refused/no-op edit is recorded as
     `outcome="edit_refused"` and still counts against the attempt budget, then
     go to 1 for the SAME check set.
4. **A check could not run** (`CheckResult.available is False`) → the outcome is
   `refused` with `note=SANDBOX_UNAVAILABLE`. Honest refusal, never a pass
   (README §3.5).
5. `checks == []` → `status="no_checks"`; the answer may make no check claim.

`graph.py` calls this once per run when a task carries checks, then passes the
`RepairOutcome` to the renderer, and the ledger blob onto the run.

### 6.4 Additive persistence — `python/harness/persistence.py`

Three edits, all additive and old-row-safe (the exact pattern `context` uses):

```python
# in _ADDED_COLUMNS["HarnessRun"]
        # Phase 4 (code): the per-run VerificationLedger + repair outcome (bounded
        # JSON). NULL for ordinary chat and for older rows.
        ("codeVerification", "TEXT"),
```

```python
# in update_run(): the allowed set grows by one name …
            "context", "codeVerification",
# … and the JSON-encoded branch grows by one name:
            if key in ("error", "research", "memory", "context", "codeVerification") and value is not None:
```

```python
# in the run-row reader, alongside the existing "context" line:
        "codeVerification": json.loads(row["codeVerification"])
            if _has_column(row, "codeVerification") and row["codeVerification"] else None,
```

`RunResult` gains the matching optional field (`codeVerification:
Optional[dict[str, Any]] = None` in `schemas.py`) so the front door can render
the panel without another fetch.

### 6.5 Mistakes — `python/harness/eclipse_memory/mistakes.py`

Add six categories to `CATEGORIES` (and to `_SEVERITY`). **Every one is a
recorded observation with an evidence field; none is guessed.**

```python
    # Phase 4 (code): deterministic code-loop mistakes. Each carries evidence.
    "check_claimed_not_run",        # the answer asserts a pass with an empty match
    "check_run_failed_ignored",     # a check FAILED and the answer asserts a pass
    "scope_violation",              # a write/execute denied by code.policy
    "unbounded_retry",              # repair attempts exceeded the configured bound
    "protected_path_write_attempt", # a write to a PROTECTED_PATHS entry was refused
    "sandbox_unavailable",          # a check could not run (honest refusal)
```

```python
_SEVERITY |= {
    "check_claimed_not_run": "high",
    "check_run_failed_ignored": "high",
    "scope_violation": "high",
    "protected_path_write_attempt": "high",
    "unbounded_retry": "medium",
    "sandbox_unavailable": "medium",
}
```

Deterministic signals (all read from the run record + events/tool executions the
function already has, plus the new `codeVerification` blob):

| Category | Signal (deterministic) |
|---|---|
| `check_claimed_not_run` | `enforce_answer` marked/stripped ≥ 1 claim, **and** the ledger held no failing record for that class (nothing ran at all) |
| `check_run_failed_ignored` | the ledger holds a non-zero-exit record for class C, **and** the answer contains a claim whose `matchedClasses` includes C, **and** the answer does not state the failure |
| `scope_violation` | an event `code.policy.denied` exists, **or** a `command_run`/`patch_apply` tool execution returned `error.code` in `{"OUTSIDE_WORKSPACE", "COMMAND_NOT_ALLOWLISTED", "PROFILE_DENIED"}` |
| `unbounded_retry` | the count of `code.repair.attempt` events **exceeds** the recorded `maxAttempts` (proof the loop crossed its bound, not merely used it) |
| `protected_path_write_attempt` | an event `code.policy.denied` with `code == "PROTECTED_PATH"` and `decision == "write"` |
| `sandbox_unavailable` | a tool execution or event carries `error.code == "SANDBOX_UNAVAILABLE"`, or `RepairOutcome.status == "refused"` |

`capture_mistakes` is unchanged: it is already idempotent per
`(category, toolName, run)` and already appends `skill.mistakes_captured`.

### 6.6 Events (existing `RunEmitter`; no new emitter)

| Event | Payload (bounded) |
|---|---|
| `code.verify.recorded` | `{commandExecutionId, commandClass, exitCode, outputDigest, durationMs}` |
| `code.verify.claims` | `{claimed, supported, unverified, kinds: [...]}` |
| `code.verify.unverified` | `{count, sentences: [...]}` (bounded to 5) |
| `code.repair.attempt` | `{attempt, failingClass, exitCode, outputDigest, editSummary}` |
| `code.repair.passed` | `{repairAttempts}` |
| `code.repair.exhausted` | `{repairAttempts, maxAttempts, stoppedReason, failedClass, failedOutputDigest}` |
| `code.policy.denied` | `{code, decision, relPath?}` — no secrets, no argument values |

Events are persisted by the emitter (the trace is the audit surface). Transient
model deltas are never persisted — unchanged.

### 6.7 Front door + UI

`src/lib/harness/code-client.ts` (new, thin — same discipline as
`python-client.ts`: *the only place Next.js talks to the runtime; it adds no
agentic logic*):

```ts
export type CheckClaimKind = "tests_pass" | "typecheck_clean" | "build_ok" | "lint_clean";

export interface CodeVerificationRecord {
  commandExecutionId: string;
  commandClass: string;
  exitCode: number;
  durationMs: number;
  outputDigest: string;
  argv: string[];
  startedAt: string;
  workspaceId: string | null;
}

export interface CodeVerificationClaim {
  sentence: string;
  kind: CheckClaimKind;
  matchedClasses: string[];
  supported: boolean;
  evidenceExecutionId: string | null;
  evidenceDigest: string | null;
}

export interface CodeVerificationRepair {
  status: "passed" | "unrepairable" | "budget_exhausted" | "refused" | "no_checks";
  repairAttempts: number;
  maxAttempts: number;
  failedClass: string | null;
  failedOutputDigest: string | null;
  stoppedReason: string | null;
}

export interface CodeVerification {
  runId: string;
  records: CodeVerificationRecord[];
  claims: CodeVerificationClaim[];
  unverifiedCount: number;
  repair: CodeVerificationRepair | null;
  truncated: boolean;
}
```

`src/components/chat/code-verification-panel.tsx` — **beside**
`research-evidence-panel.tsx`, mirroring its order and its refusal to overstate:

1. **Checks** — one row per execution: class, exit code, duration, the output
   digest (short form, monospace), and a pass/fail dot.
2. **Claims** — one row per asserted pass: the sentence, and either
   `verified · <class> · <digest>` or a loud **UNVERIFIED** badge naming the
   classes that could have supported it. It never prints "verified" for a claim
   whose `supported` is false — the status word comes straight from the blob.
3. **Repair** — only when a repair ran: attempts used / max, the failing class,
   the failing output digest, and the stop reason when exhausted.
4. Collapsed by default, frosted-glass (`.opencode/skills/black-eclipse-ui/SKILL.md`
   conventions), loads from the run record the chat already has.

**Plain language (non-expert obligation).** The panel is titled **"Proof it
works"** — never "verification ledger". Every line it shows is a plain sentence:
*"Tests passed — 1941 tests, 9.8 seconds"* / *"Could not check — the test command
was blocked"*. The internal `UNVERIFIED` marker is rendered as *"not checked
yet"* / *"I could not confirm this"*; the raw token stays a wire value only. The
exit code, class name and output digest sit behind a per-row **"details"**
affordance. All copy is declared as keys in `src/lib/i18n/dictionaries/en.ts`
(never hardcoded in the component); `dictionaries/index.ts` carries translations,
`translate.ts` resolves them, `use-t.ts` is the hook. A vitest,
`src/lib/i18n/plain-language.test.ts`, fails the build if a new user-facing string
contains a denylisted mechanism word (see §9 G10).

It replaces nothing: `research-evidence-panel.tsx` and
`run-explanation-panel.tsx` are untouched and may render beside it for a run that
did both.

### 6.8 The eval pack — `python/harness/code/eval/`

Same shape as `research/eval/` and `eclipse_memory/eval/`, so it runs as
`python -m harness.code.eval`:

```
code/eval/
  __init__.py       # run_evaluation(), EvalMetrics, THRESHOLDS, check_thresholds, format_report
  __main__.py       # print(format_report(run_evaluation())); exit non-zero when a floor fails
  dataset_v1.json   # labelled (answer, ledger) → expected claims/support pairs
```

`THRESHOLDS` (a deterministic floor, not a blended score):
`falseVerifiedRate <= 0.0` (an unbacked claim marked verified is a hard fail),
`claimRecall >= 0.95`, `digestStability == 1.0`. Per-kind slices (a claim with
one class, a claim with a failing record, a claim with an empty ledger, a
sentence that is not a claim). `check_thresholds` returns the failing dimension
by name; `__main__` exits non-zero on any failure so `scripts/test-evals.js`
picks it up.

## 7. Work items (ordered)

1. Create `docs/harness/roadmap/progress/phase-04-progress.md` with §9's gate
   commands as unchecked boxes.
2. Read `python/harness/graph.py` `execute_run` in full, plus
   `python/harness/graph_context.py`, and record the **exact** call site where
   the final answer is produced. Do not assume a node name.
3. Read `python/harness/research/claims.py` in full — the validator discipline
   this module mirrors.
4. New `python/harness/code/verify.py` per §6.1 + §6.2.
5. New `python/harness/code/repair.py` per §6.3.
6. Wire into `execute_run`: construct the ledger at run start (rehydrate from
   `codeVerification` when resuming — `VerificationLedger.from_blob`, EMPTY on a
   missing blob), record every command execution, call `run_verify_repair` once
   when the run carries checks, call `enforce_answer` on the final answer, emit
   the §6.6 events, and persist the blob. **Grow `graph.py` as little as
   possible** — the loop body lives in `repair.py`/`verify.py`; if the wiring
   does not fit, extract the seam into `graph_context.py` (already the
   graph-adjacent home) rather than pushing `graph.py` past its ratchet.
7. Persistence + `RunResult` per §6.4.
8. `mistakes.py` per §6.5.
9. New tests `python/tests/test_code_verify.py`:
   - a zero-exit `unit_test` record supports "All tests pass"; a non-zero one
     does **not**;
   - an empty ledger leaves the claim unsupported and `enforce_answer` marks it;
   - `strip` mode removes the sentence and the answer does not contain the
     phrase;
   - `output_digest` is stable across CRLF/LF and trailing whitespace, and
     changes when one line changes;
   - `record()` raises on an unknown command class;
   - `claim_matches` does **not** fire on "tests were not run" or "I did not run
     the tests" (no false positive on an honest negative);
   - `to_blob`/`from_blob` round-trips, and a garbled blob yields an empty ledger;
   - the ledger is bounded at `MAX_LEDGER_RECORDS`.
10. New tests `python/tests/test_code_repair.py`:
    - a first check that fails, an edit that fixes it, and a second check that
      passes → `status="passed"`, exactly **two** executions of that class on the
      ledger, `repairAttempts == 1`;
    - a check that never passes → stops at `max_attempts`, `status` is
      `unrepairable`/`budget_exhausted`, and `failedOutputDigest` is set;
    - the wall-clock budget is checked BEFORE the edit (a zero-second budget
      never edits);
    - `available=False` → `refused` with `note="SANDBOX_UNAVAILABLE"`, never passed;
    - `checks=[]` → `no_checks`.
11. New `python/tests/test_code_mistakes.py`: each of the six categories is
    recorded from a synthetic run, and **not** recorded when its signal is
    absent (the negative cases matter as much as the positive ones).
12. `code/eval/` per §6.8; register it in `scripts/test-evals.js` the same way
    the research/eclipse-memory runners are.
13. TS types + `src/components/chat/code-verification-panel.tsx` per §6.7,
    plus a vitest suite asserting the panel never renders "verified" for an
    unsupported claim. **All user-facing copy is a key in
    `src/lib/i18n/dictionaries/en.ts`** (never hardcoded); the panel renders
    "Proof it works" and plain lines, with the mechanism behind a "details"
    affordance. Add `src/lib/i18n/plain-language.test.ts` (the jargon gate) — a
    vitest that scans the new UI strings and i18n keys for the denylist and fails
    on any hit.
14. ADR-H106 in `docs/harness/decisions.md` (append — the series
   currently ends at ADR-H92; the numbers H103…H114 are already
   assigned in the roadmap README, so append H106 in its place
   rather than renumbering). See the roadmap index for the full table.
15. Append the dated `docs/CHANGELOG.md` entry; add the `docs/NAVIGATION.md` row
    for `python/harness/code/verify.py` + `repair.py`.

## 8. Deliverables

| File | Change |
|---|---|
| `python/harness/code/verify.py` | new — the ledger, the claim parser, `enforce_answer` |
| `python/harness/code/repair.py` | new — the bounded plan→edit→check→repair loop |
| `python/harness/code/eval/__init__.py`, `__main__.py`, `dataset_v1.json` | new — deterministic eval pack |
| `python/harness/graph.py` | minimal wiring: ledger lifecycle + one call + enforcement on the answer |
| `python/harness/graph_context.py` | the wiring seam, if `graph.py` cannot absorb it under its ratchet |
| `python/harness/persistence.py` | `HarnessRun.codeVerification` (additive, old-row-safe) |
| `python/harness/schemas.py` | `RunResult.codeVerification` (optional) |
| `python/harness/eclipse_memory/mistakes.py` | six deterministic categories + severities |
| `python/tests/test_code_verify.py` | new |
| `python/tests/test_code_repair.py` | new |
| `python/tests/test_code_mistakes.py` | new |
| `src/lib/harness/code-client.ts` + `types.ts` additions | new — the TS code-verification types |
| `src/components/chat/code-verification-panel.tsx` | new — beside `research-evidence-panel.tsx`; user-visible copy is plain language ("Proof it works") and lives in the i18n keys |
| `src/lib/i18n/dictionaries/en.ts` (+ `index.ts` if a locale needs it) | new keys for the panel, the repair line and the plain "not checked yet" marker |
| `src/lib/i18n/plain-language.test.ts` | new — the jargon gate over new user-facing strings |
| `src/components/chat/code-verification-panel.test.tsx` | new |
| `scripts/test-evals.js` | register the `code.eval` runner |
| `docs/harness/decisions.md` | ADR-H106 |
| `docs/harness/roadmap/progress/phase-04-progress.md` | new — raw gate output |
| `docs/CHANGELOG.md`, `docs/NAVIGATION.md` | per the repo obligation |

## 9. Acceptance gates

Run each from `Black-Eclipse-site/` and paste the **raw output** into the
progress log. A gate not run is a gate not passed.

```bash
# G1 — nothing regressed
npm run check:all

# G2 — the ledger + renderer tests
./scripts/vendor/python/python.exe -m pytest python/tests/test_code_verify.py -q

# G3 — the repair-budget tests
./scripts/vendor/python/python.exe -m pytest python/tests/test_code_repair.py -q

# G4 — the mistake categories
./scripts/vendor/python/python.exe -m pytest python/tests/test_code_mistakes.py -q

# G5 — the eval floor (falseVerifiedRate must be 0)
./scripts/vendor/python/python.exe -m harness.code.eval
# expected: exit 0; the report names falseVerified=0 and prints per-kind slices

# G6 — a model claiming "all tests pass" with an EMPTY ledger yields no
#      unverified claim in the rendered answer
PYTHONPATH=python ./scripts/vendor/python/python.exe -c "\
from harness.code.verify import VerificationLedger, enforce_answer; \
led=VerificationLedger('run_x'); \
out=enforce_answer('I refactored the parser. All tests pass.', led); \
print('enforced:', out.enforced, '| marked:', len(out.marked), '| stripped:', len(out.stripped)); \
print('UNVERIFIED' in out.answer); \
print('verified-count-in-ledger:', len(led.verified()))"
# expected: enforced: True | marked: 1 | stripped: 0 ; True ; verified-count-in-ledger: 0

# G7 — one failing execution then a passing one shows TWO executions for the class
./scripts/vendor/python/python.exe -m pytest python/tests/test_code_repair.py -q -k "repairs_within_budget"
# expected: 1 passed, and the test asserts len(ledger.records) == 2 for that class

# G8 — the whole python suite (uses the vendored interpreter)
npm run test

# G9 — the vault is untouched
git status --short        # jdds.db must NOT appear; no *.db staged

# G10 — the jargon gate: no new user-facing string names a mechanism
npx vitest run src/lib/i18n/plain-language.test.ts
# expected: passes — every new UI string / i18n key is free of the denylist
#           (sandbox, worktree, workspace, allowlist, autonomy, digest, argv,
#            cwd, stderr, patch, diff, manifest, operator, policy engine,
#            tool registry, exit code, verification ledger)
# The verdict panel reads "Proof it works" and "Tests passed — 1941 tests, 9.8 seconds";
# an unbacked claim reads "not checked yet" / "I could not confirm this", never "UNVERIFIED".
```

**Pass criteria.** G1 all gates pass. G2/G3/G4/G8 green. G5 exits 0 with
`falseVerified == 0`. G6 prints `enforced: True`, a non-zero marked count, and
`UNVERIFIED in the answer` is `True` with an empty ledger — i.e. **a model cannot
assert a passing check the runtime did not observe**. G7 proves the repair loop
records both the failed and the repaired execution for the same class. G9 shows
no `*.db` change. **G10 proves a non-engineer is never shown a mechanism word** —
the panel and the marker are plain-language, and the technical reason lives behind
a "details" affordance.

## 10. Definition of done

- Every gate in §9 run, raw output pasted, counts recorded.
- A passing claim is provably impossible without a zero-exit record: grep for
  `supported = True` and confirm the **only** assignment site in `verify.py` is
  behind a `passing` record check.
- `repair.py` cannot loop past its budget: every iteration goes through
  `RepairBudget.exceeded` before an edit (read the code and confirm; a test
  proves the wall-clock check runs first).
- The answer renderer consults the ledger for every run that produced output;
  an unbacked claim is marked, never asserted.
- `graph.py` did not grow past its ratchet — compare its line count against the
  number recorded in the progress log **before** the change; if it grew, the
  overflow went to `graph_context.py` instead.
- `python/harness/code/eval` runs as `python -m harness.code.eval` and is wired
  into `scripts/test-evals.js`.
- **Non-expert gate:** the jargon gate passes; every new user-facing string is an
  i18n key (no hardcoded copy); the panel reads "Proof it works" and the unbacked
  marker reads "not checked yet" / "I could not confirm this", never "UNVERIFIED"
  in the UI.
- ADR-H106 written; `docs/CHANGELOG.md` entry appended; `NAVIGATION.md` updated.
- `status:` flipped to `Done` in this file's frontmatter and in the index row.

## 11. Implementation prompt (copy this to OpenCode)

```text
Task: Phase 4 — Verify-and-repair loop (the Trust Spine), Eclipse-as-a-Harness roadmap.

Read first, in full:
- docs/harness/roadmap/phase-04-verify-and-repair.md  (this phase, verbatim)
- docs/harness/roadmap/README.md  (invariants §3, work in flight §5, file map §8)
- python/harness/research/claims.py  (the validator discipline this mirrors)
- python/harness/eclipse_memory/mistakes.py
- python/harness/model_stream.py  (FINALIZE_INSTRUCTION) and the final-answer path
  in python/harness/graph.py  (execute_run)
- docs/harness/roadmap/phase-03-command-broker.md  if it exists (the executor that
  produces the executions this ledger records); otherwise the state of
  python/harness/code/commands.py + sandbox.py

Goal: a check is passing ONLY when an execution recorded it. Ship the
VerificationLedger, the bounded verify-and-repair loop, and deterministic
answer-path enforcement. This is the phase that makes coding output trustworthy
the way market data already is.

In scope:
1. New python/harness/code/verify.py: VerificationLedger (record/claims/verified/
   failed/unverified_claims/to_blob/from_blob), CheckClaim, VerificationRecord,
   output_digest, CLAIM_PATTERNS/CLAIM_CLASSES, enforce_answer(mode="mark"|"strip").
   Deterministic sentence-level claim parsing; NO model call anywhere.
2. New python/harness/code/repair.py: RepairBudget(max_attempts=2, max_wall_clock_s,
   max_cost_usd), RepairAttempt, RepairOutcome, run_verify_repair(...). The budget
   is checked BEFORE every edit. On exhaustion STOP and report the failing class +
   its output digest. available=False ⇒ status "refused", note SANDBOX_UNAVAILABLE —
   never a pass. checks=[] ⇒ "no_checks".
3. Wire into execute_run: ledger lifecycle (rehydrate from the persisted blob on
   resume, EMPTY when absent), record every command execution, one repair call,
   enforce_answer on the final answer, §6.6 events, persist the blob. Keep
   graph.py under its ratchet — extract the seam into graph_context.py if needed.
4. persistence.py: HarnessRun.codeVerification (additive, old-row-safe — exactly
   like the existing "context" column: _ADDED_COLUMNS, update_run's allowed set,
   the json.dumps branch, and the run-row reader).
5. schemas.py: RunResult.codeVerification (optional).
6. mistakes.py: add check_claimed_not_run, check_run_failed_ignored,
   scope_violation, unbounded_retry, protected_path_write_attempt,
   sandbox_unavailable — each with a deterministic signal and an evidence field.
   A mistake is a recorded observation, never a guess.
7. Tests: python/tests/test_code_verify.py, test_code_repair.py,
   test_code_mistakes.py (include the NEGATIVE cases — an honest "the tests did
   not run" must not be flagged; a malformed blob must yield an empty ledger).
8. New python/harness/code/eval/ (dataset_v1.json + __init__.py with THRESHOLDS/
   check_thresholds/format_report + __main__.py) runnable as
   `python -m harness.code.eval`; wire it into scripts/test-evals.js.
   Thresholds: falseVerifiedRate <= 0.0, claimRecall >= 0.95, digestStability == 1.0.
9. src/lib/harness/code-client.ts types + src/components/chat/code-verification-panel.tsx
   (frosted glass, beside research-evidence-panel.tsx; never prints "verified"
   for an unsupported claim) + a vitest suite for it. The panel is titled
   "Proof it works" and shows plain lines ("Tests passed — 1941 tests, 9.8
   seconds"); the internal UNVERIFIED marker renders as "not checked yet" /
   "I could not confirm this"; exit code / class / digest live behind a
   "details" affordance. Add EVERY new user-facing string to
   src/lib/i18n/dictionaries/en.ts as a key (dictionaries/index.ts carries
   translations, translate.ts resolves, use-t.ts is the hook) — never hardcode
   copy in the component. Add src/lib/i18n/plain-language.test.ts: a vitest that
   fails when a new user-facing string or i18n key contains a denylisted
   mechanism word (sandbox, worktree, workspace, allowlist, autonomy, digest,
   argv, cwd, stderr, patch, diff, manifest, operator, policy engine,
   tool registry, exit code, verification ledger).
10. docs/harness/decisions.md: append ADR-H106 in the Decision / Why / Consequences
    shape (the series currently ends at ADR-H92).
11. docs/CHANGELOG.md dated entry + docs/NAVIGATION.md rows.

Non-goals (do NOT do these):
- No new graph node, no second loop, no second registry, no second model adapter.
- No unbounded retry. No LLM judge deciding whether a check passed.
- No change to research/claims.py, retrieval/, research/receipt.py or any finance
  tool.
- No new command class; no network; no dependency_install.
- No second approval store (that is Phase 5).
- Never commit, push, or open a PR. Do not commit jdds.db.

Constraints:
- One runtime: policy and verification live in code; prose is never a boundary.
- Bounded everything: ledger rows, claim sentences, event payloads.
- Additive persistence only; an older database must open cleanly (NULL = not recorded).
- Keep the file-size ratchets: graph.py, persistence.py, eclipse_memory/store.py,
  main.py are at their limits. New logic goes in new modules.

Acceptance gates — run each from Black-Eclipse-site/ and paste the RAW output:
  npm run check:all
  ./scripts/vendor/python/python.exe -m pytest python/tests/test_code_verify.py -q
  ./scripts/vendor/python/python.exe -m pytest python/tests/test_code_repair.py -q
  ./scripts/vendor/python/python.exe -m pytest python/tests/test_code_mistakes.py -q
  ./scripts/vendor/python/python.exe -m harness.code.eval      -> exit 0, falseVerified=0
  PYTHONPATH=python ./scripts/vendor/python/python.exe -c "from harness.code.verify import VerificationLedger, enforce_answer; led=VerificationLedger('run_x'); out=enforce_answer('I refactored the parser. All tests pass.', led); print('enforced:', out.enforced, 'marked:', len(out.marked)); print('UNVERIFIED' in out.answer)"
     -> enforced must be True and the printed boolean must be True
  npm run test
  npx vitest run src/lib/i18n/plain-language.test.ts   -> the jargon gate passes
     (no new user-facing string contains: sandbox, worktree, workspace, allowlist,
      autonomy, digest, argv, cwd, stderr, patch, diff, manifest, operator,
      policy engine, tool registry, exit code, verification ledger)
  git status --short      -> jdds.db must NOT appear

Finish by stating: "docs updated: <files>" or "no doc change — <reason>".
```

---

**Next:** [Phase 5 — The Coding Agent, Autonomy Profiles and Approvals](./phase-05-coding-agent.md)
