---
title: "Phase 10 — Progress log (self-improvement v2: evolving code as well as skills)"
phase: 10
status: Done
last-verified: 2026-10-01
---

# Phase 10 — Progress log

Operating loop: `docs/harness/roadmap/README.md` §5. Phase file:
`docs/harness/roadmap/phase-10-self-improvement.md`.

Baseline before Phase 10 (Phase 9 close): vitest 173 / 1981; pytest 2178;
`check:all` ALL PASS.

## Gate checklist

- [x] G1 — the seeded journey: mistake → candidate → proposal → evaluation → canary
- [x] G1b — the target file is byte-identical until activation
- [x] G2 — a canary regression triggers an automatic rollback, both versions kept
- [x] G3 — a proposal touching any frozen file is refused with a structured error
- [x] G4 — the recurrence bridge: criteria-driven and read-only
- [x] G5 — the archive survives a restart
- [x] G6 — every evolution route refuses a non-operator (reads and mutations)
- [x] G7 — the suite + the release gate
- [x] G8 — plain-language gate

## Raw gate output

G1 / G1b — the seeded journey:
```
python/tests/test_self_improvement_e2e.py  ...........  [100%]
11 passed in 2.05s
```

G2 — canary regression → automatic rollback, both versions preserved:
```
python/tests/test_self_improvement_e2e.py -k rollback  ..  [100%]
2 passed, 9 deselected
```

G3 — frozen files refused with a structured error:
```
python/tests/test_self_improvement_freeze.py  .............  [100%]
13 passed in 0.07s
```

G4 — the recurrence bridge (criteria-driven, read-only):
```
python/tests/test_evolution_bridge.py  ..........  [100%]
10 passed
```

G5 — the archive survives a restart:
```
python/tests/test_evolution_persistence.py  ...  [100%]
3 passed
```

G6 — every route refuses a non-operator:
```
python/tests/test_self_improvement_e2e.py -k non_operator  ........  [100%]
8 passed, 3 deselected
```

G7 — release gate:
```
 Test Files  174 passed (174)
      Tests  1983 passed (1983)
python: 2218 passed, 1 warning
eval gates: ALL PASS
[check-all] ALL GATES PASSED
```
Vitest 173/1981 → 174/1983 (+1 file/+2: `evolution-client.test.ts`). Pytest
2178 → 2218 (the four new evolution/self-improvement files: 11 + 13 + 10 + 3 + 2
plain-language = 39, plus the 1 new `test_learning_graph` node).
Frozen files byte-unchanged: `skills/versioning.py`, `skills/patches.py`,
`skills/permissions.py`, `code/policy.py`, `mcp/approvals.py`, `scripts/check-all.js`
(`git status --short` on those paths is empty).

G8 — plain language:
```
src/lib/i18n/plain-language.test.ts  4 passed
python/tests/test_plain_language.py  19 passed (3 new evolution nodes)
```

## Recon findings / deviations (reported, not silent)

- **Activation via a subject adapter (§6.5).** A code target is registered as a
  thin MANAGED skill (its proposed change carried in the patchable `/description`
  field) so `skills/versioning.py` drives propose → evaluate → canary → activate →
  rollback UNCHANGED. No fork, no edit. The §6.4 worktree report is recorded on the
  version as the evaluation evidence; `activate_version`'s gate is then satisfied
  by the existing `evaluationStatus == "passed"` check. Both `activatedVersion` and
  `previousVersion` are recorded on the candidate row.
- **Recurrence is read from the ONE ledger.** `candidates_from_mistakes` reads
  `LearningRecurrence` (agent-memory.db), category-scoped. The MistakeRecord table
  lives in `eclipse-memory.db`, so it is NOT a cross-database fallback here —
  `skills/learning.py` remains the only place that combines ledger + scan. No rival
  counter.
- **`checks` in the eval.** `owning_test_paths` DERIVES the owning test from the
  target path (a python module → `python/tests/test_<name>.py`; a kit file →
  `python/tests/test_kit_<id>.py`; a TS module → its `.test.ts` sibling). When
  nothing is derivable, the dimension is recorded `unmeasured` and the candidate
  stays `evaluated_bad` — never a fabricated pass.
- **Null cost columns.** `costMicros` / `tokensUsed` are nullable; a `0` would be a
  lie the report cannot detect. `archive_metrics` returns `"UNKNOWN"` (never `0`)
  for any dimension whose inputs are absent, and `perCategory` is mandatory.
- **Journey extension.** `learning_graph.py` gained `evolution_candidate` /
  `evolution_attempt` node kinds and the `attempted_on` relation. The existing
  `learning-journey.tsx` screen renders them; no second self-improvement screen.
- **`main.py` growth.** +2 lines (import + `include_router`).
- **Line-ending sweep.** Two `Add-Content` appends introduced CRLF; the touched
  files were normalized to LF (the `gitignore-guard` gate bites on a mix).
