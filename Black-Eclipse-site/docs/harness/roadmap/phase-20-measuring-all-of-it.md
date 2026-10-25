---
title: "Phase 20 — Measuring All of It"
status: Done
phase: 20
depends_on: [13, 14, 15, 16, 17, 18, 19]
unlocks: []
last-verified: 2026-10-25
---

# Phase 20 — Measuring All of It

> **Progress (2026-10-13) — first slice shipped under ADR-H193.** Landed:
> `python/harness/code/eval/capabilities.py` (the capability-class registry —
> 20 classes incl. the four published as `not measured yet` WITH reasons; the
> runner grading through the REAL modules: 4 in-module fixtures over
> `harness.acquire.budget`/`harness.automation.delivery`/`harness.code.verify`/
> `harness.code.review`, named `pytest:`/`vitest:` test selectors for document
> attachment + figure provenance, and the seven code shapes' fixture ids checked
> against the labelled dataset; `MEASURED_BASELINE` + `check_capability_floors`),
> the generated statement's "Every capability class" section (incl. the
> published unmeasured count) with a real fix to the generator's repo-root
> constant, and the named `capability-class gate` step in `scripts/test-evals.js`
> (`PASS measured=16 unmeasured=4`). Tests:
> `python/tests/test_capability_classes.py` (7). **Remaining (not started):**
> labelled fixtures for `price_authority` and `promotion` (today honestly
> unmeasured), the bootstrap/Monte-Carlo rule fixture, the adversarial safety
> cases for the new power in `code/eval/safety_cases.py`, and per-class
> threshold tables beyond the all-or-nothing floor.

| | |
|---|---|
| **Depends on** | Every phase 13–19. This is the phase that grades them; it has no dependents because everything is measured by it. |
| **Unlocks** | — (it is the standing gate) |
| **Estimated work** | 14–20 h of agent time. Fixtures and a runner; no new product surface. |
| **Deliverable type** | one labelled dataset, one runner, one thresholds module, one generated capability statement, one gate step. |
| **Decision records** | ADR-H125 (the capability statement covers every capability class, and an unmeasured class is published as unmeasured) |
| **Prompt to copy** | [§11 below](#11-implementation-prompt) |

---

## Contents

- [1. Goal](#1-goal)
- [2. Why this phase exists](#2-why-this-phase-exists)
- [3. In scope](#3-in-scope)
- [4. Who can use it (the non-expert obligation)](#4-who-can-use-it-the-non-expert-obligation)
- [5. Non-goals (do not do these)](#5-non-goals-do-not-do-these)
- [6. Exact contracts to create](#6-exact-contracts-to-create)
  - [6.1 The capability-class registry (data)](#61-the-capability-class-registry-data)
  - [6.2 The runner](#62-the-runner)
  - [6.3 The gate step (added inside the existing runner)](#63-the-gate-step-added-inside-the-existing-runner)
  - [6.4 The statement, extended honestly](#64-the-statement-extended-honestly)
- [7. Work items (ordered)](#7-work-items-ordered)
- [8. Deliverables](#8-deliverables)
- [9. Acceptance gates](#9-acceptance-gates)
- [10. Definition of done](#10-definition-of-done)
- [11. Implementation prompt](#11-implementation-prompt)

---

## 1. Goal

Every capability this round claimed to add is measured against labelled fixtures and
published in the generated capability statement — and any capability that is **not**
measured is published as `not measured yet`, in the strongest form of that word,
rather than implied. The statement a finance professional reads stops being a claim
and becomes a measurement, including the parts that say "no".

## 2. Why this phase exists

**(a) The existing eval covers code shapes only, and the statement says so.**
`python/harness/code/eval/dataset_tasks_v1.json` grades seven shapes
(`one-file`, `cross-file`, `test-first`, `repair`, `job`, `kit`, `refusal`), and
`docs/harness/capability-statement.md` is generated from it. Every row in that
statement is a code-writing shape. Verified in the published file: no row mentions a
price answer, a document attachment, a bulk dataset, a figure, a scheduled job
created by the agent, or a verified artifact. The `route_health`, `workflow`,
`resume`, `capability_matrix` gates in `scripts/test-evals.js` cover their own
subsystems and are not part of the statement.

**(b) The statement's own honesty rule is already correct and only half-applied.**
Its footer reads:

> "`yes` means fixtures ran and their gold outcome held… `partial` means a fixture
> exists but does not yet prove the whole shape. `not measured yet` means there is
> **no fixture** — a different, weaker claim than `not yet`, and never 'probably
> fine'."

That rule is exactly right. The gap is coverage: seven of the ~twenty capability
classes a user can ask for have no row at all, so they are not published as
`not measured yet` — they are simply absent, which reads as "fine".

**(c) The honesty requirements the new phases ship are individually testable and
collectively unmeasured.** Phase 13's "a stale source is never returned as the
answer", Phase 16's "a partial dataset is never presented as complete", Phase 17's
"a degraded unattended run states its limits", Phase 19's "an unbacked claim is
marked" — each has its own unit test and none is graded end-to-end as a *capability
class*. A capability class no gate measures is where the work goes silent.

**(d) The gate structure to extend already exists.** `scripts/test-evals.js` runs the
floors and `scripts/check-all.js` runs `test-evals.js` as its last step: one addition
point, no new pipeline. `code/eval/statement.py` already generates the published
file from the dataset, and ADR-H114 pins "regenerating produces identical bytes".
Both are reused exactly.

## 3. In scope

1. **A capability-class registry** as data: the classes a user can ask for (the seven
   code shapes plus the ones this round added), each naming the fixtures that grade it
   or declaring itself unmeasured.
2. **Labelled fixtures** for the new classes, in the existing dataset format —
   offline, deterministic, with a gold outcome per case:
   - a price answer that must prefer the fresh source, and one that must refuse a
     stale one;
   - a document attachment round-trip and a truncation case;
   - a bulk collection bounded at the ceiling, and a partial one;
   - a figure's provenance and the Monte Carlo's bootstrap rule;
   - an unattended degraded report;
   - an artifact claim that must be marked unresolved.
3. **A runner** (`code/eval/capabilities.py`) that executes the fixtures through the
   real modules — not through mocks of the thing being graded — and produces a
   per-class report with per-category metrics and a threshold table.
4. **The generated statement gains the new rows**, and any class with no fixtures is
   emitted as `capability.status.notMeasured` — the count of unmeasured classes is
   published in the statement itself.
5. **One gate step** added inside `scripts/test-evals.js`, printing the counts and
   failing when a class falls below its floor **or when a class is unmeasured and was
   previously measured** (a capability may not silently regress to unmeasured).
6. **Safety cases for the new power**, in the existing adversarial shape
   (`code/eval/safety_cases.py`): an acquisition over its ceiling, a scheduling call
   with the operator switch off, a promotion outside its approved file set, a figure
   over unrecorded inputs — each blocked **and recorded**.

## 4. Who can use it (the non-expert obligation)

The reader is the finance professional who asks "can you do X?" — and, secondarily,
the operator deciding whether to trust the system. The statement must be readable by
both without engineering vocabulary: a row says what the user can ask for ("Collect a
dataset from a declared source"), whether it works today, the proof, and what is
missing — and the unmeasured rows say so in the same plain voice. No mechanism word
appears in a row (`acquisition`, `arbitration`, `ratchet`, `digest` are trace
vocabulary). Rows are i18n keys, as they already are (`capability.shape.*`), and the
plain-language gate covers the new ones.

## 5. Non-goals (do not do these)

- **No blended score, ever, and no LLM judge.** Per-class, per-category metrics with
  explicit floors — the rule Phase 12 already states.
- **No weakening of an existing gate to make a new one pass.** If the new eval fails,
  that IS the finding; report it.
- **No new pipeline.** The gate stays `scripts/check-all.js` → `scripts/test-evals.js`.
- **No live-model dependency in the gate.** A class whose fixture needs a model runs
  in an opt-in live suite (the existing `test:smoke` / `test:presets` precedent), and
  the class is published as measured-with-a-live-fixture and named as such.
- **No claim of completeness.** A class nobody thought of is not in the registry —
  that limitation is stated in the document, not hidden by a total.
- Never commit, push or open a PR; do not commit `jdds.db`.

## 6. Exact contracts to create

### 6.1 The capability-class registry (data)

```python
# python/harness/code/eval/capabilities.py
@dataclass(frozen=True)
class CapabilityClass:
    id: str                      # i18n key stem, e.g. "price_authority"
    label_key: str               # capability.class.<id> — plain words
    fixtures: tuple[str, ...]    # fixture ids in the dataset; EMPTY ⇒ unmeasured
    module: str                  # the real module the fixture exercises
    live: bool = False           # needs a model/network ⇒ opt-in suite only
    floor: Optional[float] = None  # required pass rate when measured

CLASSES: tuple[CapabilityClass, ...] = (
    # The seven Phase-12 shapes (fixtures already exist; this phase registers them)
    CapabilityClass("one_file", "capability.class.oneFile", ("one-file-change",),
                    "harness.code.patch", floor=1.0),
    CapabilityClass("cross_file", "capability.class.crossFile", ("cross-file-change",),
                    "harness.code.patch", floor=1.0),
    CapabilityClass("test_first", "capability.class.testFirst", ("test-first",),
                    "harness.code.repair", floor=1.0),
    CapabilityClass("repair", "capability.class.repair", ("failing-check-repair",),
                    "harness.code.repair", floor=1.0),
    CapabilityClass("job", "capability.class.job", ("job-definition",),
                    "harness.jobs.model", floor=1.0),
    CapabilityClass("kit", "capability.class.kit", ("kit-scaffold",),
                    "harness.code.kits.loader", floor=1.0),
    CapabilityClass("refusal", "capability.class.refusal", ("refusal-protected-write",),
                    "harness.code.policy", floor=1.0),
    # Added by this round
    CapabilityClass("price_authority", "capability.class.priceAuthority",
                    ("fresh-source-wins", "stale-source-refused"),
                    "harness.retrieval.authority", floor=1.0),
    CapabilityClass("document_attachment", "capability.class.documentAttachment",
                    ("docx-round-trip", "truncation-stated"),
                    "lib/chat/extract", floor=1.0),
    CapabilityClass("bulk_collection", "capability.class.bulkCollection",
                    ("collection-at-ceiling", "collection-partial"),
                    "harness.acquire.budget", floor=1.0),
    CapabilityClass("figure_provenance", "capability.class.figureProvenance",
                    ("figure-labelled", "monte-carlo-bootstrap"),
                    "harness.code.render", floor=1.0),
    CapabilityClass("unattended_report", "capability.class.unattendedReport",
                    ("degraded-report-states-limits",),
                    "harness.jobs.delivery", floor=1.0),
    CapabilityClass("artifact_verification", "capability.class.artifactVerification",
                    ("unbacked-claim-marked",),
                    "harness.code.verify", floor=1.0),
    # Declared and NOT measured — published as such
    CapabilityClass("promotion", "capability.class.promotion", (),
                    "harness.code.actions"),
    CapabilityClass("scraping_breadth", "capability.class.scrapingBreadth", (),
                    "harness.acquire.registry"),
)
```

**The two `fixtures=()` rows matter more than the measured ones.** They are the point
of the phase: a capability the user asked for that this round did not grade is
published as `not measured yet`, with its reason, instead of being absent.

### 6.2 The runner

```python
# python/harness/code/eval/capabilities.py
def run_capability_eval(
    *, only: Optional[tuple[str, ...]] = None, now: Optional[float] = None,
) -> CapabilityReport:
    """Grade every class through its REAL module.

    For each class: load its fixtures, drive the real code, compare to the fixture's
    gold outcome, and record pass/fail with the observed value. A class with no
    fixtures is reported `unmeasured` WITH ITS REASON — never as a pass, never as a
    failure. Never a mock of the module under test: a fixture that stubs the thing it
    grades measures the stub.
    """

@dataclass(frozen=True)
class CapabilityReport:
    classes: list[ClassResult]
    measured: int
    unmeasured: int
    failed: int
    def format_report(self) -> str: ...      # engineering-facing
    def statement_rows(self) -> list[Row]: ...  # what the published statement prints
```

### 6.3 The gate step (added inside the existing runner)

```js
// scripts/test-evals.js — ONE added step, printed like its siblings
//   capability gate: PASS
//     measured=13 unmeasured=2 failed=0
//     unmeasured: promotion, scraping_breadth
// Fails when a class is below its floor, OR when a class that was measured in the
// committed statement is now unmeasured (regression to unmeasured is a failure).
```

### 6.4 The statement, extended honestly

`code/eval/statement.py` already generates `docs/harness/capability-statement.md`
from the dataset. It gains the new rows **and** a published count:

```
Measured: 13 capability classes · Not measured: 2 (promotion, scraping breadth)
```

plus, per unmeasured row, the reason in plain words ("no labelled fixtures yet —
built but not graded"). Regenerating produces identical bytes (ADR-H114's rule,
asserted by the existing test).

## 7. Work items (ordered)

1. `python/harness/code/eval/capabilities.py` — the registry + `CapabilityReport`.
2. The fixtures, in the existing dataset format:
   `dataset_capabilities_v1.json` (+ per-class files where a fixture needs real input
   bytes, e.g. a tiny `.xlsx` under `python/tests/fixtures/office/`).
3. The runner: one driver per class, each driving the REAL module. Order by risk —
   `price_authority` and `bulk_collection` first (their bounds are the ones a silent
   regression would break).
4. `code/eval/statement.py` — the new rows + the measured/unmeasured count.
5. `code/eval/safety_cases.py` — the four new adversarial cases, in the existing
   shape (blocked **and** recorded).
6. `scripts/test-evals.js` — the one added step + the regression-to-unmeasured check.
7. `python/tests/test_capability_eval.py`, `test_capability_eval_safety.py` — incl.
   the injected-regression proof (break a fixture's gold outcome, watch the gate fail,
   paste that output in the progress log).
8. `en.ts` — `capability.class.*` keys; the plain-language gate extended.
9. `docs/harness/roadmap/progress/phase-20-progress.md` — created, gates unchecked.

## 8. Deliverables

| File | Change |
|---|---|
| `python/harness/code/eval/capabilities.py` | new — the registry + runner |
| `python/harness/code/eval/dataset_capabilities_v1.json` | new — the labelled fixtures |
| `python/harness/code/eval/statement.py` | changed — the new rows + counts |
| `python/harness/code/eval/safety_cases.py` | changed — four new adversarial cases |
| `scripts/test-evals.js` | changed — one gate step |
| `docs/harness/capability-statement.md` | regenerated |
| `python/tests/test_capability_eval*.py` | new |
| `src/lib/i18n/dictionaries/en.ts` | changed — `capability.class.*` |
| `docs/harness/decisions.md` | changed — ADR-H125 |

## 9. Acceptance gates

```bash
# G1 — the capability eval runs and every measured class meets its floor.
./scripts/vendor/python/python.exe -m harness.code.eval.capabilities

# G2 — the unmeasured classes are published, with reasons, not omitted.
grep -c "not measured" docs/harness/capability-statement.md    # ≥ the registry count
grep -n "promotion\|scraping breadth" docs/harness/capability-statement.md

# G3 — the safety cases are blocked AND recorded.
./scripts/vendor/python/python.exe -m pytest python/tests/test_capability_eval_safety.py -v

# G4 — the injected-regression proof (paste the FAILING output; it is the evidence).
./scripts/vendor/python/python.exe -m pytest python/tests/test_capability_eval.py -v

# G5 — the gate is in the standing chain, and the statement regenerates identically.
node scripts/test-evals.js
git diff --exit-code docs/harness/capability-statement.md

# G6 — the full release gate.
npm run check:all
```

| Gate | Assertion |
|---|---|
| G1 | Each measured class reports its pass count and meets its floor; the report names the real module per class; no fixture stubs the module it grades. |
| G2 | Every `fixtures=()` class appears in the statement as `not measured yet` **with its reason**; the published measured/unmeasured counts equal the registry's own numbers (asserted, not typed). |
| G3 | The four new cases each assert the block **and** the recorded reason: an acquisition over its row/byte ceiling, a scheduling call with the operator switch off, a promotion outside the approved file set, a figure over unrecorded inputs. A block with no record fails. |
| G4 | The injected regression (one fixture's gold outcome deliberately broken) makes the gate fail, and that failing output is in the progress log. The gate passing on a broken fixture would be the whole phase's failure. |
| G5 | `node scripts/test-evals.js` prints the capability step and passes; the committed statement is byte-identical to a fresh regeneration. |
| G6 | `ALL GATES PASSED`; vitest and pytest counts reported as observed, with the delta from the Phase-0 baseline in this round's progress log. |

**A gate not run is a gate not passed.** Paste the raw output of each into
`docs/harness/roadmap/progress/phase-20-progress.md`.

## 10. Definition of done

- Every capability class a user can ask for is either measured with labelled fixtures
  or published as `not measured yet` with its reason.
- No class can regress to unmeasured without failing the gate.
- The safety cases for every capability that adds power are adversarial, and each
  proves both the block and the record.
- The statement is generated, byte-stable, plain-language, and its counts are derived
  from the registry rather than typed.
- ADR-H125 written; changelog appended; NAVIGATION row 81 updated; `status:` and the
  index row flipped; the roadmap index's status table shows phases 13–20 closed.

## 11. Implementation prompt

```text
Task: Phase 20 — measure every capability this round added.

Read first, in full:
- docs/harness/roadmap/phase-20-measuring-all-of-it.md (this file, verbatim)
- docs/harness/roadmap/README.md (§3 invariants, §6 non-goals)
- python/harness/code/eval/ (tasks.py, statement.py, safety.py, safety_cases.py,
  dataset_tasks_v1.json, __init__.py)
- docs/harness/capability-statement.md (the generated file and its honesty rule)
- scripts/test-evals.js + scripts/check-all.js (the ONE chain you extend)
- docs/harness/roadmap/progress/phase-12-progress.md (how the last gate was closed)

Goal: every capability class a user can ask for is graded by labelled fixtures through
the REAL module, published in the generated statement — and any class without fixtures
is published as "not measured yet" with its reason, never omitted.

In scope: §3 items 1–6 and the ordered work items in §7.

Non-goals (do NOT do these):
- No blended score and no LLM judge. Per-class floors only.
- Do NOT weaken or remove an existing gate, fixture or floor to make a new one pass.
  If the new eval fails, that is the finding — report it.
- No new pipeline: the chain stays check-all.js → test-evals.js.
- No live-model dependency in the standing gate; a model-dependent class runs in the
  existing opt-in suite and is published as such.
- A fixture must drive the real module; never stub the thing being graded.
- Never commit, push or open a PR. Do not commit jdds.db.

Constraints:
- One runtime, one eval shape, one statement generator. Extend; do not fork.
- The measured/unmeasured counts in the statement are DERIVED from the registry.
- Every new user-facing string is an i18n key and passes the plain-language gates.
- Measure before implementing; a corrected audit is a valid outcome. Do not weaken any
  existing test — name every changed expectation with its old and new value.

Acceptance gates — run each from Black-Eclipse-site/ and paste the RAW output into
docs/harness/roadmap/progress/phase-20-progress.md (INCLUDING the failing output from
the injected-regression proof — that failing run is the evidence):
  ./scripts/vendor/python/python.exe -m harness.code.eval.capabilities
  ./scripts/vendor/python/python.exe -m pytest python/tests/test_capability_eval.py -v
  ./scripts/vendor/python/python.exe -m pytest python/tests/test_capability_eval_safety.py -v
  node scripts/test-evals.js
  git diff --exit-code docs/harness/capability-statement.md
  npx vitest run src/lib/i18n/plain-language.test.ts
  ./scripts/vendor/python/python.exe -m pytest python/tests/test_plain_language.py -q
  npm run check:all

Finish by stating: "docs updated: <files>" or "no doc change — <reason>", plus one
honest non-property: what you did NOT verify.
```

---

**Next:** the round closes here — re-read [the index](./README.md), keep the standing
gate green, and update the status tracker.
