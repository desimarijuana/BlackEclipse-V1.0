---
title: "Phase 4 — Progress log (verify-and-repair trust spine)"
phase: 4
status: Done
last-verified: 2026-10-01
---

# Phase 4 — Progress log

Operating loop: `docs/harness/roadmap/README.md` §5. Phase file:
`docs/harness/roadmap/phase-04-verify-and-repair.md`.

Baseline before Phase 4 (Phase 3 close): vitest 169 / 1966; pytest ~1889;
eval gates ALL PASS.

## Gate checklist

- [x] G1 — `npm run check:all`
- [x] G2 — ledger + renderer tests
- [x] G3 — repair-budget tests
- [x] G4 — mistake categories
- [x] G5 — eval floor (`python -m harness.code.eval`)
- [x] G6 — empty-ledger claim is enforced
- [x] G7 — repair records both executions
- [x] G8 — whole python suite
- [x] G9 — vault untouched
- [x] G10 — jargon gate

## Recon — real shapes (read before writing)

- `graph.py` measures **1650** against ratchet **1857** → ~207 lines headroom.
  The final answer is produced at `execute_run` ~line 979 (`output = final_state.get("final")`),
  then persisted via `store.update_run(..., output=output, context=...)`. The
  enforcement seam attaches immediately after `output` is read.
- `persistence.py` measures **1392** against ratchet **1393**. The `codeVerification`
  column is added via `_ADDED_COLUMNS` (1 line) and threaded through `update_run`'s
  allowed set + json branch (2 small edits) + the run-row reader (1 line) — the
  blob helpers live in `code/verify.py`, so `persistence.py` stays in budget.
- `eclipse_memory/mistakes.py`: `analyze_run_for_mistakes` reads run/events/tools;
  `capture_mistakes` is idempotent per `(category, toolName, run)`. Six additive
  categories slot in with deterministic signals from the new `codeVerification` blob.
- `research/claims.py`: the validator discipline mirrored — a deterministic check
  owns the decision; unverifiable material is marked, never asserted.

## G1 / G8 — raw `npm run check:all`

```
 Test Files  170 passed (170)
      Tests  1969 passed (1969)
================= 1935 passed, 1 warning in 156.27s (0:02:36) =================
  code_verify gate: PASS
[check-all] ALL GATES PASSED
```

Vitest **169/1966 → 170/1969** (+1 file/+3: the panel logic test). Pytest
**~1889 → 1935**.

## G2/G3/G4/G7 — raw probe suites

```
test_code_verify.py   ....................  20 passed
test_code_repair.py   ........             8 passed
test_code_mistakes.py ..............      14 passed
test_code_repair.py -k repairs_within_budget  1 passed, 7 deselected
```

## G5 — raw `python -m harness.code.eval`

```
Code verification eval — code-verify-v1
  cases=10 expectedClaims=7 foundClaims=7 falseVerified=0
  claimRecall=1.000 falseVerifiedRate=0.000
  ...
  verification gate: PASS
exit=0
```

## G6 — raw empty-ledger enforcement

```
enforced: True | marked: 1 | stripped: 0
True
verified-count-in-ledger: 0
```

An empty ledger ⇒ the claim is marked, `UNVERIFIED` appears, and the ledger holds
no verified record — a model cannot assert a passing check the runtime did not
observe.

## G10 — raw jargon gate

```
src/lib/i18n/plain-language.test.ts  (4 tests) 4 passed
```

## G9 — raw `git status --short`

No `*.db` appears; `persistence.py` stayed at its ratchet (1393) by putting the
`codeVerification` column DDL in `code/store.py`.

## Ratchet note

`graph.py` grew by the minimal wiring (ledger construction, one call, one
`enforce_run_answer` + `update_run`); it stayed far under its 1857 budget.
`code/tools.py` crossed the 1200 hard ceiling with the Phase 4 ledger hook, so the
`command_run` handler was EXTRACTED into `code/command_tools.py` (behaviour and
registration unchanged) — `tools.py` is now 1000 lines.
