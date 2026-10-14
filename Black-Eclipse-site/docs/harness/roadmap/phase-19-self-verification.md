---
title: "Phase 19 — Verifying What It Produced"
status: Done
phase: 19
depends_on: [14, 18]
unlocks: [20]
last-verified: 2026-10-13
---

# Phase 19 — Verifying What It Produced

> **Progress (2026-10-13) — Done, ADR-H191.** Shipped: `code/verify.py`
> (`ArtifactCheck`/`ArtifactRecord`/`verify_artifacts`; ledger artifact + review
> records, bounded and old-row-safe; the two new claim classes with the same
> narrow negation-guarded patterns), `analysis_tools.py` recording the artifact
> checks after an analysis, `code/review.py` (the six-rule table +
> `review_change`, ratchet pins read from BOTH ratchet files, `unevaluated`
> never clean), the read-only `review_change` tool registered by
> `code/review_tools.py` from `service.py` and allowlisted on the code agent +
> chat code profile, the four additive `mistakes.py` categories, the CODE-agent
> prompt paragraph, and the chat panel rendering artifact rollups + review
> findings (`code.proof.*` i18n keys). Tests:
> `python/tests/test_claim_classes.py`, `test_artifact_verification.py`,
> `test_change_review.py` (24). Recorded deviations (per `AGENTS.md`): no
> separate progress file (notes inline), the prompt paragraph is in the CODE
> agent prompt (the finance prompt is char-ratcheted), `review_change` is
> registered from `service.py` because `code/tools.py` is at its size pin, and
> the figure-specific `figure_inputs_match` runs when the producer recorded
> inputs — the figure payload itself is phase 18, still open.

| | |
|---|---|
| **Depends on** | Phase 14 (a diff exists to review) and Phase 18 (a figure exists to check). Phase 4's ledger is the spine this extends. |
| **Unlocks** | Phase 20 (the gate grades the new checks). |
| **Estimated work** | 12–16 h of agent time. One new module, one new tool, and the honest limit on both. |
| **Deliverable type** | one artifact-verification module + one diff-review module + their recorded results. |
| **Decision records** | ADR-H124 (a claim about a produced artifact needs a recorded check, exactly like a claim about a command) |
| **Prompt to copy** | [§11 below](#11-implementation-prompt) |

---

## Contents

- [1. Goal](#1-goal)
- [2. Why this phase exists](#2-why-this-phase-exists)
- [3. In scope](#3-in-scope)
- [4. Who can use it (the non-expert obligation)](#4-who-can-use-it-the-non-expert-obligation)
- [5. Non-goals (do not do these)](#5-non-goals-do-not-do-these)
- [6. Exact contracts to create](#6-exact-contracts-to-create)
  - [6.1 Artifact verification](#61-artifact-verification)
  - [6.2 The change-quality rules (data)](#62-the-change-quality-rules-data)
  - [6.3 The tool and the claim classes](#63-the-tool-and-the-claim-classes)
  - [6.4 Mistake categories (additive, into the existing vocabulary)](#64-mistake-categories-additive-into-the-existing-vocabulary)
- [7. Work items (ordered)](#7-work-items-ordered)
- [8. Deliverables](#8-deliverables)
- [9. Acceptance gates](#9-acceptance-gates)
- [10. Definition of done](#10-definition-of-done)
- [11. Implementation prompt](#11-implementation-prompt)

---

## 1. Goal

Eclipse checks the things it produced — a written change and a rendered figure —
against rules that are recorded and re-runnable, so "I added that and it works" is
backed by a ledger entry rather than by prose; and when a check cannot be run, the
answer says that instead of implying it was.

Phase 4 gave the runtime exactly this spine for **command** claims. This phase gives
it one for **artifact** claims and **change-quality** claims, and nothing more.

## 2. Why this phase exists

**(a) The ledger covers commands, and its claim vocabulary is closed to them.**
`code/verify.py`:

```python
CLAIM_CLASSES: dict[str, tuple[str, ...]] = {
    "tests_pass": ("unit_test", "python_test"),
    "typecheck_clean": ("typecheck",),
    "build_ok": ("build",),
    "lint_clean": ("lint",),
}

CLAIM_PATTERNS: tuple[tuple[ClaimKind, "re.Pattern[str]"], ...] = (...)
UNVERIFIED_MARKER = " [UNVERIFIED — no successful {class_list} execution in this run]"
```

Every class is a **command class** from Phase 3's closed table. So a sentence like
"The chart shows the drawdown over two years" or "I added the recipe and it follows
the existing pattern" is matched by no pattern and backed by no record. The
enforcement machinery (`enforce_answer`, `UNVERIFIED_MARKER`) is exactly the right
mechanism and is pointed at half the surface.

**(b) A produced artifact is asserted, never checked.** `analysis_tools.py` returns
the artifacts in its result text:

```python
if result.artifacts:
    names = ", ".join(a.name for a in result.artifacts)
    lines.append(f"Saved: {names}")
```

and `ArtifactRef` carries a `sha256` and a MIME guess. Nothing checks that the file
is readable, that its size is non-trivial, that a figure's plotted values match the
recorded inputs, or that the digest in the result is the digest on disk. `_collect_artifacts`
records a reference; the reference is then trusted.

**(c) The repo already states the rules a change must satisfy, in machine-checkable
form — and nothing consults them for the agent's own diffs.** `AGENTS.md` carries the
standing rules; `docs/NAVIGATION.md` carries the trigger table; `src/lib/size-budget.test.ts`
and `python/tests/test_size_budget.py` carry the size ratchets;
`.githooks/commit-msg` enforces the changelog obligation. A change authored in a
disposable copy is checked only by whatever command the agent chose to run. The
rules exist; the loop back into the agent does not.

**(d) Self-improvement already consumes failures, so the input shape matters.**
`code/evolution.py::candidates_from_mistakes` bridges the ONE `LearningRecurrence`
counter into reviewable candidates. A new check that does not record a
*mistake category* cannot drive that loop — so this phase records into the existing
`eclipse_memory/mistakes.py` vocabulary, it does not invent a parallel one.

## 3. In scope

1. **Artifact verification** as a recorded check: for each artifact a run produced —
   the file exists at the recorded path, its digest matches the recorded one, its
   size is above a floor and below the cap, and (for a figure) its declared series
   match the recorded inputs. Results go into the existing `VerificationLedger` as a
   new record kind.
2. **Change-quality rules** as a declared, data-driven list, evaluated over the
   diff: the repo's own rules where they are mechanical — a new module is reachable
   (imported by something), a changed file is not above its size ratchet, a
   user-facing string is an i18n key, no protected path was touched, a doc-obligation
   marker (a changelog entry) exists when the change is not test-only.
3. One tool, `review_change`, that runs the rules over the current diff and returns
   findings with file:line and the rule that fired — and **refuses honestly** when a
   rule cannot be evaluated (e.g. no diff, no workspace).
4. The claim patterns extended by exactly two classes — `artifacts_verified` and
   `change_reviewed` — so an unbacked sentence about either is marked
   `[UNVERIFIED …]` by the existing enforcement path.
5. `mistakes.py` gains the categories these checks can emit, so a repeated failure
   reaches the existing self-improvement bridge.
6. A documented, honest limit: which rules are **not** mechanically checkable (style,
   naming, whether the change is the right change) and how the answer must phrase
   those — as a judgement, never as a verified fact.

## 4. Who can use it (the non-expert obligation)

The user is anyone who has asked Eclipse to change their code or draw them a chart,
and who now needs to know whether to trust it. They never see a ledger, a digest, a
rule id or a lint. What they see:

- "Checked: the chart reads from the two years of prices you collected, and the file
  is intact." — a sentence about the work, with the mechanism behind details.
- "I couldn't verify this one — the figure's inputs aren't recorded" is a first-class
  answer (README §3.5), and it is the answer that makes the other sentences worth
  reading.
- A finding reads like a colleague's note: "This adds a `render.py` module, but
  nothing uses it yet." — never "unreachable module: R-07".

## 5. Non-goals (do not do these)

- **No LLM judge as a gate.** A model's opinion of its own diff can be *advisory
  text* in the answer; it can never satisfy a check. (Phase 12 already forbids an LLM
  judge in the eval gate; this is the same rule at the tool level.)
- **No vision check.** Nothing in the runtime can look at an image today — there is
  no vision capability in the harness and the provider catalog is text-only. A pixel
  check is out of scope and is named as a limitation; the figure check is structural
  (readable image, declared series match inputs), which is what can be honestly
  checked now. Adding a vision model is a separate capability decision, not a
  silent extension of this phase.
- **No new ledger, no new store.** Extend `code/verify.py`; do not create a second
  record of checks.
- **No auto-fix.** Findings are reported. `repair.py` already owns plan→edit→check→repair
  and is untouched here.
- **No blocking of a run on a review finding.** A review finding is information; the
  only hard blocks stay where they already are (policy, permission, approval).
- Never commit, push or open a PR; do not commit `jdds.db`.

## 6. Exact contracts to create

### 6.1 Artifact verification

```python
# python/harness/code/verify.py — ADDITIVE
ArtifactCheck = Literal[
    "artifact_exists",       # the file is where the reference says
    "artifact_digest",       # sha256 on disk == the recorded sha256
    "artifact_size",         # above MIN_ARTIFACT_BYTES, below the run's cap
    "artifact_readable",     # a figure opens as an image; csv/json parse
    "figure_inputs_match",   # the plotted series == the recorded inputs
]

@dataclass(frozen=True)
class ArtifactRecord:
    """One VERIFIED artifact fact. Never a claim, always an observation."""
    artifact_name: str
    kind: str
    check: ArtifactCheck
    passed: bool
    detail: str                 # a plain sentence; the mechanism stays in the trace
    observed: dict[str, Any]    # digest, bytes, series length, …
```

`verify_artifacts(references, output_dir, recorded_inputs) -> list[ArtifactRecord]` —
runs the checks, records them on the ledger, and returns the records. A check that
cannot run (a missing file) is a **failed** record with its reason, never an absence.

### 6.2 The change-quality rules (data)

```python
# python/harness/code/review.py
@dataclass(frozen=True)
class ReviewRule:
    id: str                     # stable, used in findings and tests
    summary: str                # plain words, this is what the user reads
    severity: Literal["blocking", "advisory"]   # blocking means the RELEASE gate, not this tool
    source: str                 # which repo rule this encodes (a real path)

RULES: tuple[ReviewRule, ...] = (
    ReviewRule("new-module-reachable", "A new module nothing uses yet",
               "advisory", "AGENTS.md — reuse before rebuild"),
    ReviewRule("size-ratchet", "A changed file is past its size limit",
               "advisory", "src/lib/size-budget.test.ts, python/tests/test_size_budget.py"),
    ReviewRule("string-is-key", "A user-facing sentence isn't a translatable key",
               "advisory", "src/lib/i18n/plain-language.test.ts"),
    ReviewRule("protected-path", "The change touches a file it must not",
               "blocking", "python/harness/code/policy.py — PROTECTED_PATHS"),
    ReviewRule("doc-obligation", "A non-test change has no change-log entry",
               "advisory", "AGENTS.md — documentation obligation"),
    ReviewRule("test-touched", "The change changed a test's expectation",
               "advisory", "AGENTS.md — never weaken a test to make it pass"),
)

def review_change(diff: DiffView, *, repo_root: Path) -> list[Finding]:
    """Evaluate every rule over the diff. Returns findings with file:line, the rule
    id, and the plain `summary` a user reads. A rule that cannot be evaluated
    (no diff, an unreadable file) returns NO finding for that file and is counted in
    `unevaluated` — never silently reported as clean."""
```

`protected-path` is the only blocking rule, and it is **already enforced** by
`patch.apply`; the rule here is a *report* of that fact, and the test asserts the two
agree (a change the policy refuses must also produce the finding). Two mechanisms for
one rule is the defect; one mechanism plus a report is the contract.

### 6.3 The tool and the claim classes

```python
# registered by register_code_tools (additive), permission="read"
async def review_change_tool(args, ctx) -> tuple[str, Any]:
    """Review the change made in this task's own copy against the project's rules.

    Returns the findings in plain words and records the review on the ledger so the
    final answer can be checked. Refuses when there is no change to review or no
    project folder is bound.
    """
```

```python
# code/verify.py — the two new claim classes
CLAIM_CLASSES |= {
    "artifacts_verified": ("artifact_check",),
    "change_reviewed":    ("change_review",),
}
# and the matching CLAIM_PATTERNS, narrow like the existing four:
#   r"\b(the|every|all)?\s*(chart|figure|file)s?\s+(is|are)\s+(intact|verified)\b"
#   r"\bI\s+(reviewed|checked)\s+the\s+change\b"
```

### 6.4 Mistake categories (additive, into the existing vocabulary)

```python
# python/harness/eclipse_memory/mistakes.py — ADDITIVE categories
"artifact_missing",         # a produced artifact was not where it was reported
"artifact_digest_mismatch", # the reported digest does not match the file
"unreachable_module",       # a new module nothing imports
"unstated_limitation",      # a limitation that existed and was not reported
```

## 7. Work items (ordered)

1. `python/harness/code/verify.py` — `ArtifactCheck`, `ArtifactRecord`,
   `verify_artifacts`, the two new claim classes and patterns. Tests first: the
   claim enforcement is the risky part (a false positive marks a true sentence).
2. `python/harness/analysis_tools.py` — call `verify_artifacts` after a run and put
   the records on the ledger.
3. `python/harness/code/review.py` — `ReviewRule`, `RULES`, `Finding`, `review_change`.
4. `python/harness/code/tools.py` — register `review_change`.
5. `python/harness/eclipse_memory/mistakes.py` — the four additive categories.
6. `python/harness/prompts.py` — one paragraph in `CODE_AGENT_SYSTEM_PROMPT` telling
   the agent that its artifact and review sentences are checked, and that naming a
   limitation it did not state is the failure mode. (Prompt text is not a boundary —
   the ledger is.)
7. `en.ts` — `review.*`; the finding wording.
8. `src/components/chat/code-verification-panel.tsx` — render the artifact records and
   the findings (the existing panel, extended; no new surface).
9. `python/tests/test_artifact_verification.py`, `test_change_review.py`,
   `test_claim_classes.py`.
10. `docs/harness/roadmap/progress/phase-19-progress.md` — created, gates unchecked.

## 8. Deliverables

| File | Change |
|---|---|
| `python/harness/code/verify.py` | changed — artifact checks + two claim classes |
| `python/harness/code/review.py` | new — the rule table + `review_change` |
| `python/harness/code/tools.py` | changed — register `review_change` |
| `python/harness/analysis_tools.py` | changed — verify what was produced |
| `python/harness/eclipse_memory/mistakes.py` | changed — additive categories |
| `python/harness/prompts.py` | changed — the checked-sentences paragraph |
| `src/components/chat/code-verification-panel.tsx` | changed — artifacts + findings |
| `src/lib/i18n/dictionaries/en.ts` | changed — `review.*` |
| `python/tests/test_{artifact_verification,change_review,claim_classes}.py` | new |
| `docs/harness/decisions.md` | changed — ADR-H124 |

## 9. Acceptance gates

```bash
# G1 — an artifact claim without a recording is marked UNVERIFIED.
./scripts/vendor/python/python.exe -m pytest python/tests/test_claim_classes.py -v

# G2 — artifact checks are real observations.
./scripts/vendor/python/python.exe -m pytest python/tests/test_artifact_verification.py -v

# G3 — the review rules fire, and an unevaluable rule is not reported as clean.
./scripts/vendor/python/python.exe -m pytest python/tests/test_change_review.py -v

# G4 — the review rule and the enforcement mechanism AGREE (no second mechanism).
./scripts/vendor/python/python.exe -m pytest python/tests/test_change_review.py -k protected -v

# G5 — the full release gate, and the existing verification eval.
./scripts/vendor/python/python.exe -m harness.code.eval
npm run check:all
```

| Gate | Assertion |
|---|---|
| G1 | A sentence "the figure is intact" with no artifact record gains `[UNVERIFIED — no successful artifact check execution in this run]`; the same sentence after a recorded check does not; a **negated** sentence ("I could not check the figure") never matches; a sentence about an unrelated file never matches. |
| G2 | A missing file, a changed digest, a zero-byte file, an unreadable figure and a figure whose plotted series differ from the recorded inputs each produce a **failed** record with a plain reason; a clean artifact produces passing records for each check. A check that could not run at all is recorded as failed, never omitted. |
| G3 | Each of the six rules fires on a constructed diff that violates it; a clean diff produces zero findings and `unevaluated: []`; an unreadable file lands in `unevaluated` and is reported as such. |
| G4 | A change touching `python/harness/code/policy.py` is refused by `patch.apply` **and** produces the `protected-path` finding — asserted together, so a future drift between them fails the test. |
| G5 | The Phase-4 verification eval still passes unchanged (the two new claim classes do not loosen it), and `ALL GATES PASSED`. |

**A gate not run is a gate not passed.** Paste the raw output of each into
`docs/harness/roadmap/progress/phase-19-progress.md`.

## 10. Definition of done

- A produced artifact is checked against its recorded reference, and a claim about it
  is backed or marked unresolved by the existing enforcement path.
- The change-quality rules are data, each naming the real repo rule it encodes, and
  the one rule that is also enforced in code is proven to agree with its enforcement.
- An unevaluable check is never reported as a pass.
- The limitation is stated: style, naming and intent are not mechanically checked and
  the answer must phrase them as judgement.
- The two new claim classes do not loosen the Phase-4 eval.
- ADR-H124 written; changelog appended; NAVIGATION row 84 updated; `status:` and the
  index row flipped.

## 11. Implementation prompt

```text
Task: Phase 19 — verifying what Eclipse produced.

Read first, in full:
- docs/harness/roadmap/phase-19-self-verification.md (this file, verbatim)
- docs/harness/roadmap/README.md (§3.3 artifacts inert, §3.4 never fabricate, §3.5
  honest refusal, §6 non-goals)
- python/harness/code/{verify.py,review* does not exist*,patch.py,tools.py}
- python/harness/code/eval/__init__.py (the verification eval you must not loosen)
- python/harness/analysis_tools.py, python/harness/eclipse_memory/mistakes.py
- src/components/chat/code-verification-panel.tsx
- AGENTS.md + docs/NAVIGATION.md (the real rules your rule table encodes)
- src/lib/size-budget.test.ts + python/tests/test_size_budget.py (the ratchets)

Goal: a claim about a produced artifact or about a reviewed change is backed by a
recorded check or marked unresolved — using Phase 4's ONE ledger and enforcement path,
never a second mechanism.

In scope: §3 items 1–6 and the ordered work items in §7.

Non-goals (do NOT do these):
- No LLM judge as a gate. A model's opinion may appear as advisory text and can never
  satisfy a check.
- No vision check: the runtime has no vision capability and the provider catalog is
  text-only. The figure check is structural. State this as a limitation; do not fake a
  pixel check.
- No new ledger or store — extend code/verify.py.
- No auto-fix; repair.py is untouched.
- No blocking of a run on an advisory finding.
- Do NOT weaken the existing claim classes or the code verification eval.
- Never commit, push or open a PR. Do not commit jdds.db.

Constraints:
- A check that cannot run is recorded as failed with a reason, never omitted.
- One rule, one mechanism: `protected-path` reports what policy.py already enforces,
  and the test asserts the two agree.
- Every user-facing string is an i18n key; findings read as plain sentences, never as
  rule ids.
- Measure before implementing; a corrected audit is a valid outcome.

Acceptance gates — run each from Black-Eclipse-site/ and paste the RAW output into
docs/harness/roadmap/progress/phase-19-progress.md:
  ./scripts/vendor/python/python.exe -m pytest python/tests/test_claim_classes.py -v
  ./scripts/vendor/python/python.exe -m pytest python/tests/test_artifact_verification.py -v
  ./scripts/vendor/python/python.exe -m pytest python/tests/test_change_review.py -v
  ./scripts/vendor/python/python.exe -m pytest python/tests/test_change_review.py -k protected -v
  ./scripts/vendor/python/python.exe -m harness.code.eval
  npm run check:all

Finish by stating: "docs updated: <files>" or "no doc change — <reason>", plus one
honest non-property: what you did NOT verify.
```

---

**Next:** [Phase 20 — Measuring All of It](./phase-20-measuring-all-of-it.md)
