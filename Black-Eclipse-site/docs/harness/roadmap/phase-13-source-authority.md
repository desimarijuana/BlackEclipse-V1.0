---
title: "Phase 13 — Source Authority and Freshness Arbitration"
status: Done
phase: 13
depends_on: [0, 2]
unlocks: [16, 20]
last-verified: 2026-10-02
---

# Phase 13 — Source Authority and Freshness Arbitration

| | |
|---|---|
| **Depends on** | Phase 0 (the policy authority this phase extends) and Phase 2 (the worktree/branch discipline the tests run under). No phase 5+ dependency — this is a correctness fix, not new power. |
| **Unlocks** | Phase 16 (bulk acquisition is only worth building once the runtime can say which source won) and Phase 20 (the eval gate grades the arbitration). |
| **Estimated work** | 10–14 h of agent time. Changes runtime behaviour for every price-shaped answer. |
| **Deliverable type** | one policy module (`retrieval/authority.py`) + a changed planner/layer seam + per-observation age + a labelled fixture set. |
| **Decision records** | ADR-H115 (a source is never the authority; agreement is arbitrated), ADR-H116 (an observation's age is a property of the observation, not of the payload) |
| **Prompt to copy** | [§11 below](#11-implementation-prompt) |

---

## Contents

- [1. Goal](#1-goal)
- [2. Why this phase exists](#2-why-this-phase-exists)
- [3. In scope](#3-in-scope)
- [4. Who can use it (the non-expert obligation)](#4-who-can-use-it-the-non-expert-obligation)
- [5. Non-goals (do not do these)](#5-non-goals-do-not-do-these)
- [6. Exact contracts to create](#6-exact-contracts-to-create)
  - [6.1 The authority table (data, one row per data type)](#61-the-authority-table-data-one-row-per-data-type)
  - [6.2 The decision function (pure, testable)](#62-the-decision-function-pure-testable)
  - [6.3 Per-observation age](#63-per-observation-age)
  - [6.4 What the bridge must provide (no schema change)](#64-what-the-bridge-must-provide-no-schema-change)
  - [6.5 Wire / refusal codes (stable strings)](#65-wire--refusal-codes-stable-strings)
- [7. Work items (ordered)](#7-work-items-ordered)
- [8. Deliverables](#8-deliverables)
- [9. Acceptance gates](#9-acceptance-gates)
- [10. Definition of done](#10-definition-of-done)
- [11. Implementation prompt](#11-implementation-prompt)

---

## 1. Goal

A price, a series or a macro reading is answered by **whichever eligible source is
both fresh enough and strongest for that fact**, with the disagreement between
sources preserved and shown — instead of by whichever source the table happens to
list first. The market-data vault stops being the default answer for a *current*
value; it becomes one candidate, and its age is stated per value.

Nothing new becomes writable. This phase changes only which existing source
answers, and what the answer says about itself.

## 2. Why this phase exists

The vault is first in the source table for every price-shaped data type, and the
single-best path returns the first success without consulting the others.

`python/harness/retrieval/planner.py` — the ordering, as data:

```python
_PLAN: dict[str, list[str]] = {
    "current_quote": [STRUCTURED_VAULT, STRUCTURED_LIVE, WEB],
    "historical_prices": [STRUCTURED_VAULT, STRUCTURED_LIVE],
    "company_profile": [STRUCTURED_VAULT, STRUCTURED_LIVE, WEB],
    "macro_series": [STRUCTURED_VAULT, STRUCTURED_LIVE],
    ...
}
```

`python/harness/retrieval/layer.py` — the types for which the first success wins,
and the loop that returns immediately:

```python
_SINGLE_BEST = {
    "current_quote", "historical_prices", "macro_series",
    "company_profile", "financial_statements",
}
...
async def _execute_single(...):
    """Try planned sources in order; first OK result wins (then validate)."""
    for name in plan.sources:
        ...
        if outcome.status == "OK" and (outcome.objects or outcome.evidence):
            return self._finalize_single(request, outcome, ...)
```

Consequences, each verified this session:

- `retrieval/conflicts.py` (`detect_conflicts`, `DEFAULT_REL_TOLERANCE = 0.005`) is
  reachable for a single-best type only over the objects of the ONE answering
  source. A vault-vs-live disagreement cannot occur, because the live source is
  never called once the vault answers. The 0.5 % tolerance exists and is
  unreachable for the case it was written for.
- `retrieval/validate.py` measures staleness as a **dataset** property —
  `newest = _newest_timestamp(objects)` — so one instrument's stale row inside a
  payload whose newest row is fresh produces no warning at all.
- `retrieval/policies.py` has no cadence entry for prices
  (`DEFAULT_CADENCE_SECONDS` covers `financial_statements`, `earnings`,
  `macro_series` only), so a `realtime` request is measured against
  `max_age_seconds("realtime") == 60`.
- The vault's own freshness, measured from the live `jdds.db` this session:

  | Measure | Value |
  |---|---|
  | `Price` rows | 55 195 |
  | rows ≤ 15 min old | **0** |
  | rows ≤ 24 h old | 37 940 |
  | rows > 7 days old | **12 252 (22.2 %)** |
  | median age | 0.8 days |
  | 90th-percentile age | 38.5 days |

  `Price.updatedAt` is the **snapshot write timestamp** (max observed
  `2026-10-02T02:58:50Z`); the schema has no market as-of column. So a vault answer
  reports a write time, and a stale row carries no age signal of its own.

- `src/lib/harness/data-bridge.ts` hard-codes the cadence on the vault path
  (`cadenceSeconds: 24 * 60 * 60`) and `layer.py` reads
  `outcome.raw.get("cadenceSeconds")` — but only in the multi-source path, never in
  `_finalize_single`.

The system prompt already states the correct rule ("JDdS is one source, not the
authority — stale or incomplete. If it lacks something, try other eligible
routes"). The planner and the single-best loop contradict it. **The prompt is
right; the code is wrong.** A prompt cannot fix this — the live source is not
merely deprioritised, it is never called.

## 3. In scope

1. One policy module, `python/harness/retrieval/authority.py`, holding per data
   type: the ordered candidate list, the tier, and whether the type is
   `single_best` (first success) or `arbitrated` (top-N then resolve).
2. `current_quote`, `historical_prices`, `macro_series` and `company_profile` become
   **arbitrated**: every eligible structured candidate runs (reusing
   `retrieval/parallel.run_parallel`), then `layer._resolve` /
   `retrieval/conflicts.detect_conflicts` chooses with a stated reason or reports
   `CONFLICTING`. No second conflict mechanism.
3. A **freshness ceiling per source**, so a `realtime` request cannot be satisfied
   by a 22-day-old vault row: a candidate whose newest observation is older than the
   request window is not eligible to answer, and the refusal names the age.
4. Per-observation age: `NormalizedFinancialObject` carries the observation time and
   an `observationTimeSource` (`provider_asof` | `snapshot_write`) so a value whose
   only time is a snapshot write is labelled `DELAYED`, never presented as live.
5. `decide_source` — a pure function returning the chosen source, the reason, and
   every rejected candidate with its reason.
6. A labelled fixture set + regression tests, including the vault-vs-live
   disagreement that is unreachable today.

## 4. Who can use it (the non-expert obligation)

This phase ships no new screen, but it changes text a user reads on every price
answer: the source line and the age label. Those strings are **i18n keys** in
`src/lib/i18n/dictionaries/en.ts` (`source.*` / staleness wording), never literals,
and they name the **job** — "as of 3 pm today, from the exchange feed", "this is a
saved snapshot from 12 September" — never the mechanism. The mechanism denylist
(`python/harness/code/policy.py` → `PLAIN_LANGUAGE_DENYLIST`) governs them, and the
phrase "vault", "JDdS", "arbitration", "tier" must not appear in a user-facing
string. The user's question is *"is this number current?"*; the answer must be a
sentence about the number, not about the plumbing.

## 5. Non-goals (do not do these)

- **No new data source.** This phase reorders and arbitrates the existing ones
  (`JDDS`, `LIVE_STRUCTURED`, `SEC`, `WEB`, declared MCP sources).
- **No schema change to `prisma/schema.prisma` or `jdds.db`.** No new column, no
  re-import. `jdds.db` must remain byte-unchanged.
- **No change to the research mandate / claims / receipt pipeline** (Phase 4's
  contract). `research/` is a consumer of retrieval and must keep working
  unchanged.
- **No new conflict-resolution algorithm.** Reuse `retrieval/conflicts.py` and
  `layer._resolve` verbatim.
- **No widening of the web route for precise types.** `historical_prices`,
  `macro_series` and `derived_metric` keep web forbidden.
- No second agent loop, tool registry or model adapter (README §3.1).
- Never commit, push or open a PR; do not commit `jdds.db` (README §3.6).

## 6. Exact contracts to create

### 6.1 The authority table (data, one row per data type)

```python
# python/harness/retrieval/authority.py
SourcePolicy = Literal["single_best", "arbitrated"]

@dataclass(frozen=True)
class DataTypeAuthority:
    data_type: str
    candidates: tuple[str, ...]   # ordered preference, strongest first
    policy: SourcePolicy
    require_precise: bool          # web may never satisfy it
    web_allowed: bool
    request_window_s: int          # the freshness ceiling for THIS type
```

```python
AUTHORITY: dict[str, DataTypeAuthority] = {
    # A current price is arbitrated: a fresh live reading must be able to beat a
    # saved snapshot, and a disagreement between the two must be shown.
    "current_quote": DataTypeAuthority(
        "current_quote", (STRUCTURED_LIVE, STRUCTURED_VAULT, WEB),
        "arbitrated", require_precise=True, web_allowed=True,
        request_window_s=900,          # 15 min: fresher than a saved snapshot
    ),
    # A history series: live provider first (it carries the real series), the
    # snapshot second as an honest fallback with its age stated.
    "historical_prices": DataTypeAuthority(
        "historical_prices", (STRUCTURED_LIVE, STRUCTURED_VAULT),
        "arbitrated", require_precise=True, web_allowed=False,
        request_window_s=6 * 3600,
    ),
    "macro_series": DataTypeAuthority(
        "macro_series", (STRUCTURED_LIVE, STRUCTURED_VAULT),
        "arbitrated", require_precise=True, web_allowed=False,
        request_window_s=12 * 3600,
    ),
    "company_profile": DataTypeAuthority(
        "company_profile", (STRUCTURED_LIVE, STRUCTURED_VAULT, WEB),
        "arbitrated", require_precise=False, web_allowed=True,
        request_window_s=24 * 3600,
    ),
    # Statements stay single-best: an issuer filing is not a race with a snapshot.
    "financial_statements": DataTypeAuthority(
        "financial_statements", (SEC_FILINGS, STRUCTURED_VAULT, WEB),
        "single_best", require_precise=False, web_allowed=True,
        request_window_s=400 * 24 * 3600,
    ),
    # ... one row per DataType; a new type gets exactly one row here.
}
```

`plan_retrieval` reads this table instead of `_PLAN`, and keeps its current
signature. `planner._PLAN` and `layer._SINGLE_BEST` are **deleted** and their
readers repointed, so there is one ordering in the tree, not three.

### 6.2 The decision function (pure, testable)

```python
@dataclass(frozen=True)
class SourceDecision:
    chosen: Optional[str]
    reason: str                       # a sentence, safe to show behind "details"
    rejected: list[tuple[str, str]]   # (source, why it did not answer)

def decide_source(
    authority: DataTypeAuthority,
    outcomes: list[SourceOutcome],
    request: FinancialRetrievalRequest,
    *,
    now: Optional[float] = None,
) -> SourceDecision: ...
```

Rules, in order — each returns with its reason:

1. A candidate that did not run is not a rejection (it was ineligible) — it is
   recorded as `skipped`.
2. `require_precise` + `not web_allowed` ⇒ `WEB` is rejected for the type.
3. A candidate whose newest observation is older than
   `min(authority.request_window_s, request.freshness window)` is rejected with the
   measured age in the reason.
4. Among survivors, `retrieval/conflicts.detect_conflicts` decides: `consistent` →
   the highest-tier newest value; `resolved` → the resolver's stated reason;
   `conflicting` → **no chosen value**, status `CONFLICTING`, every candidate
   returned.

### 6.3 Per-observation age

```python
# python/harness/retrieval/contract.py — ADDITIVE fields on
# NormalizedFinancialObject (old rows / payloads must still load):
observation_time: Optional[str] = None      # ISO-8601, the MARKET time
observation_source: Literal["provider_asof", "snapshot_write", "unknown"] = "unknown"
```

`validate.py` gains a per-observation check beside the existing dataset check:

```python
def validate_observations(
    objects: list[NormalizedFinancialObject],
    freshness: str,
    *,
    now: Optional[float] = None,
) -> tuple[list[NormalizedFinancialObject], list[str]]:
    """Flag ONE stale observation inside an otherwise fresh payload.

    The dataset-level check (`validate_objects`) answers "is this batch current?";
    a payload of 40 rows where 3 are a month old passes it. This answers "is THIS
    value current?" and is the check that stops a stale row riding a fresh batch.
    """
```

A value with `observation_source == "snapshot_write"` is never described as live:
its `transformations` gains `saved snapshot, not a live reading` and its quality
becomes `warning` when the request is `realtime`.

### 6.4 What the bridge must provide (no schema change)

`src/lib/harness/data-bridge.ts` `marketSnapshot` gains two additive fields and
stops asserting a cadence for a value it cannot date:

```ts
observationTime: asset.price?.updatedAt?.toISOString() ?? null,
observationSource: "snapshot_write",     // the vault writes the row when it fetches
// cadenceSeconds stays, but is now a HINT; the runtime decides eligibility.
```

`liveQuote` returns `observationSource: "provider_asof"` with the provider's own
timestamp when it has one, and `"unknown"` when it does not — never a fabricated
as-of.

### 6.5 Wire / refusal codes (stable strings)

| Code | Meaning |
|---|---|
| `STALE_SOURCE` | the only eligible candidate's newest observation is outside the window; reason carries the measured age |
| `CONFLICTING` | existing status: candidates disagree beyond 0.5 %; no value is chosen |
| `NO_FRESH_SOURCE` | every candidate was stale (distinct from `UNAVAILABLE`, which means none answered at all) |

## 7. Work items (ordered)

1. `python/harness/retrieval/authority.py` — new: `DataTypeAuthority`, `AUTHORITY`,
   `decide_source`, `SourceDecision`. No I/O; import nothing from `layer.py`.
2. `python/harness/retrieval/planner.py` — read `AUTHORITY`; keep `plan_retrieval`'s
   signature and its web-forbidding rules; delete `_PLAN`.
3. `python/harness/retrieval/layer.py` — delete `_SINGLE_BEST`; dispatch on
   `authority.policy`; route arbitrated types through the existing `_execute_multi`
   + `_resolve` path; pass `authority.request_window_s` into `_finalize_single`.
4. `python/harness/retrieval/validate.py` — add `validate_observations` beside
   `validate_objects`; wire it into `_finalize_single` and `_execute_multi`.
5. `python/harness/retrieval/contract.py` — the two additive fields + a
   `render_age`-style helper if one does not already exist in `policies.py`.
6. `src/lib/harness/data-bridge.ts` — the two additive fields on `marketSnapshot`
   and `liveQuote`; keep `cadenceSeconds` as a hint.
7. `src/lib/i18n/dictionaries/en.ts` — `source.asOf.*`, `source.delayed.*`,
   `source.conflict.*` keys; extend `src/lib/i18n/plain-language.test.ts`'s key
   prefix list.
8. `python/tests/test_source_authority.py` + `fixtures/retrieval/authority_*.json`
   — the labelled cases in §9.
9. `docs/harness/roadmap/progress/phase-13-progress.md` — created with the gates as
   unchecked boxes before the work starts.

## 8. Deliverables

| File | Change |
|---|---|
| `python/harness/retrieval/authority.py` | new — the one ordering + decision authority |
| `python/harness/retrieval/planner.py` | changed — reads `AUTHORITY`; `_PLAN` deleted |
| `python/harness/retrieval/layer.py` | changed — arbitrated dispatch; `_SINGLE_BEST` deleted |
| `python/harness/retrieval/validate.py` | changed — per-observation staleness |
| `python/harness/retrieval/contract.py` | changed — additive observation fields |
| `src/lib/harness/data-bridge.ts` | changed — additive `observationTime`/`observationSource` |
| `src/lib/i18n/dictionaries/en.ts` | changed — `source.*` keys |
| `python/tests/test_source_authority.py` | new — the labelled arbitration cases |
| `docs/harness/decisions.md` | changed — ADR-H115, ADR-H116 |
| `python/harness/retrieval/__init__.py` | changed — export `AUTHORITY`, `decide_source` |

## 9. Acceptance gates

```bash
# G1 — the arbitration cases, including the vault-vs-live disagreement that is
#      unreachable on the current code (this test FAILS before the change).
./scripts/vendor/python/python.exe -m pytest python/tests/test_source_authority.py -v

# G2 — the retrieval regression suite (existing behaviour must not move except
#      the single-best types this phase deliberately re-routes).
./scripts/vendor/python/python.exe -m pytest python/tests/test_retrieval.py \
  python/tests/test_retrieval_scenarios.py python/tests/test_retrieval_health.py -q

# G3 — exactly one ordering table survives.
grep -rn "_PLAN\|_SINGLE_BEST" python/harness/retrieval/ | wc -l
# expected: 0

# G4 — the vault is untouched.
git status --short jdds.db prisma/
# expected: no output

# G5 — the full release gate.
npm run check:all
```

| Gate | Assertion |
|---|---|
| G1 | Each of these cases passes: (a) a fresh live reading beats a saved snapshot for `current_quote`; (b) a snapshot older than the request window is rejected with `STALE_SOURCE` and the age in the reason — never returned as the answer; (c) two structured candidates 1.2 % apart return `CONFLICTING` with both candidates and their provenance; (d) two candidates 0.2 % apart return the higher-tier newest value with reason `sources agree`; (e) with no bridge, the vault still answers and its value is labelled a saved snapshot, not live; (f) a 3-of-40 stale-row payload produces a per-observation warning (today: none); (g) `historical_prices` never returns a web result. |
| G2 | The three suites pass; every assertion whose expected value changed is listed in the progress log with its old and new value and why. |
| G3 | 0 hits — a second ordering table is the defect this phase removes. |
| G4 | `jdds.db` and `prisma/` unmodified — the phase adds no schema and re-imports nothing. |
| G5 | `ALL GATES PASSED`; vitest and pytest counts reported as observed, not as predicted. |

**A gate not run is a gate not passed.** Paste the raw output of each into
`docs/harness/roadmap/progress/phase-13-progress.md`.

## 10. Definition of done

- One ordering table (`AUTHORITY`) and one decision function (`decide_source`) in
  the tree; `_PLAN` and `_SINGLE_BEST` exist nowhere.
- A `realtime` price request cannot be answered by a vault row older than the
  window, and the refusal names the age.
- A vault answer carries a snapshot-write observation and is never worded as live.
- A cross-source disagreement is `CONFLICTING` with both candidates — proven by a
  test that fails on the pre-change code.
- The user-facing strings are i18n keys and pass the plain-language gate
  (`python/tests/test_plain_language.py`, `src/lib/i18n/plain-language.test.ts`).
- ADR-H115 and ADR-H116 written; dated `docs/CHANGELOG.md` entry appended;
  `docs/NAVIGATION.md` rows 149/150 updated in the same change; this file's
  `status:` and the index row flipped.

## 11. Implementation prompt

```text
Task: Phase 13 — Source authority and freshness arbitration.

Read first, in full:
- docs/harness/roadmap/phase-13-source-authority.md (this file, verbatim)
- docs/harness/roadmap/README.md (§3 invariants, §6 non-goals)
- python/harness/retrieval/{planner,layer,conflicts,validate,policies,contract,sources,parallel}.py
- src/lib/harness/data-bridge.ts (marketSnapshot, liveQuote)
- docs/harness/decisions.md (the ADR-Hnn shape you must match)

Goal: a price/series/macro answer is chosen by freshness-then-strength across all
eligible sources with the disagreement preserved, not by the first source in a
static table — and no value is ever worded as live when its only timestamp is a
snapshot write.

In scope:
1. New python/harness/retrieval/authority.py: DataTypeAuthority, AUTHORITY (one row
   per DataType, exact shape in §6.1), SourceDecision, decide_source (§6.2).
2. planner.py reads AUTHORITY; delete _PLAN. Keep plan_retrieval's signature and
   the existing web-forbidding rules for historical_prices / macro_series /
   derived_metric.
3. layer.py: delete _SINGLE_BEST; dispatch on authority.policy; arbitrated types run
   their candidates through the EXISTING run_parallel + _resolve + detect_conflicts
   path; pass authority.request_window_s through to _finalize_single.
4. validate.py: add validate_observations (per-observation staleness) beside the
   existing dataset-level validate_objects; wire both in.
5. contract.py: additive observation_time / observation_source on
   NormalizedFinancialObject, defaulting so old payloads still load.
6. data-bridge.ts: additive observationTime / observationSource on marketSnapshot
   ("snapshot_write") and liveQuote ("provider_asof" or "unknown" — never invented).
7. en.ts: source.* i18n keys for the as-of / delayed / disagreement wording; extend
   the plain-language key-prefix list.
8. python/tests/test_source_authority.py + python/tests/fixtures/retrieval/*.

Non-goals (do NOT do these):
- No new data source; no change to prisma/schema.prisma or jdds.db; no re-import.
- No new conflict algorithm — reuse retrieval/conflicts.py and layer._resolve.
- No change to research/ (its mandate, claims, receipt contract is frozen here).
- No web route for precise types.
- One runtime: no second loop/registry/adapter. New logic in new modules.
- Never commit, push or open a PR. Do not commit jdds.db.

Constraints:
- Policy in code, never in prose. A prompt claiming a rule is not the rule.
- Every user-facing string is an i18n key; the mechanism denylist in
  python/harness/code/policy.py applies to it.
- Read the real files and MEASURE before implementing: if a claim in this prompt is
  already true in the tree, say so and skip it — a corrected audit is a valid
  outcome. Do not implement a phantom.
- Do not weaken any existing test. Name every test whose expectation you changed,
  with the old and new value and why.

Acceptance gates — run each from Black-Eclipse-site/ and paste the RAW output into
docs/harness/roadmap/progress/phase-13-progress.md:
  ./scripts/vendor/python/python.exe -m pytest python/tests/test_source_authority.py -v
  ./scripts/vendor/python/python.exe -m pytest python/tests/test_retrieval.py python/tests/test_retrieval_scenarios.py python/tests/test_retrieval_health.py -q
  grep -rn "_PLAN\|_SINGLE_BEST" python/harness/retrieval/ | wc -l      # expect 0
  git status --short jdds.db prisma/                                    # expect empty
  npx vitest run src/lib/i18n/plain-language.test.ts
  ./scripts/vendor/python/python.exe -m pytest python/tests/test_plain_language.py -q
  npm run check:all

Finish by stating: "docs updated: <files>" or "no doc change — <reason>", plus one
honest non-property: what you did NOT verify.
```

---

**Next:** [Phase 14 — The code capability, reachable from chat](./phase-14-reachable-code-capability.md)
