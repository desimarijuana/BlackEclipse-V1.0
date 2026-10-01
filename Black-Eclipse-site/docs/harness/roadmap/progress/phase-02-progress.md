---
title: "Phase 2 — Progress log (isolated worktree patch authoring)"
phase: 2
status: Done
last-verified: 2026-10-01
---

# Phase 2 — Progress log

Operating loop: `docs/harness/roadmap/README.md` §5. Phase file:
`docs/harness/roadmap/phase-02-worktree-patching.md`.

Baseline before Phase 2 (Phase 1 close): vitest 169 files / 1966 tests; pytest
1808 nodes; eval gates ALL PASS.

## Gate checklist

- [x] G1 — `npm run check:all`
- [x] G2 — new tests, verbose
- [x] G3 — fixture task edits only the intended file
- [x] G4 — operator checkout untouched + pre-existing dirty hash-identical
- [x] G5 — every rejection vector refused with its own code
- [x] G6 — cancel/orphan/release-idempotent/outside-scratch
- [x] G7 — jargon gate
- [x] G8 — no `git add/commit/push` under `code/`

## Recon — real shapes (read before writing)

- `persistence.py` measures **1392** lines against the ratchet entry **1393** in
  `test_size_budget.py` — only 1 line of headroom. Therefore the `CodeWorkspace`
  DDL **and** all helpers go in the new `python/harness/code/store.py`, bound to
  the one `AgentMemoryStore._db` connection (the `run_lineage.py` precedent).
  `persistence.py` is NOT edited.
- `skills/patches.py`: closed `ALLOWED_OPS`, structural validation before apply,
  stale-base refusal, re-validation of the result — the model copied here.
- `run_lineage.py`: owns its own tables via `_store._db`; keeps ONE database and
  ONE connection.
- `workspace.confine(ws, rel, for_write=)` raises `WorkspaceDenial` with distinct
  codes; `patch.py` maps them to `PATCH_*` codes and never calls `realpath`.
- `graph.py` builds ONE `ToolContext(...)` and one effect authorizer; the code
  authorizer is composed there.

## G1 — raw `npm run check:all` (tail)

```
 Test Files  169 passed (169)
      Tests  1966 passed (1966)
================= 1841 passed, 1 warning in 150.30s (0:02:30) =================
  retrieval gate: PASS
  contradiction gate: PASS
  compaction gate: PASS
  route_health gate: PASS
  workflow gate: PASS
  resume gate: PASS
  capability_matrix gate: PASS
eval gates: ALL PASS
[check-all] ALL GATES PASSED
```

Vitest unchanged (169/1966). Pytest rose **1808 → 1841** (+33: the new
`test_code_worktree.py` + `test_code_patch.py` nodes).

## G2 — raw `pytest test_code_worktree.py test_code_patch.py -v` (tail)

```
python\tests\test_code_worktree.py::test_snapshot_fallback_reports_snapshot_strategy PASSED [ 38%]
python\tests\test_code_patch.py::test_intended_file_edited_and_only_that_file PASSED [ 41%]
...
python\tests\test_code_patch.py::test_revert_of_create_deletes_the_file PASSED [100%]
============================= 33 passed in 4.07s ==============================
```

## G3 — raw fixture-task probe

```
.                                                                        [100%]
1 passed, 18 deselected in 0.07s
```

## G4 — raw operator-checkout probes

```
python\tests\test_code_worktree.py::test_operator_checkout_untouched_by_allocate_and_release PASSED [ 50%]
python\tests\test_code_worktree.py::test_preexisting_dirty_file_is_hash_identical PASSED [100%]
====================== 2 passed, 10 deselected in 0.76s =======================
```

## G5 — raw rejection vectors (distinct codes)

```
python\tests\test_code_patch.py::test_traversal_refused PASSED           [ 11%]
python\tests\test_code_patch.py::test_absolute_refused PASSED            [ 22%]
python\tests\test_code_patch.py::test_windows_absolute_refused PASSED    [ 33%]
python\tests\test_code_patch.py::test_symlink_escape_refused PASSED      [ 44%]
python\tests\test_code_patch.py::test_protected_path_refused PASSED      [ 55%]
python\tests\test_code_patch.py::test_oversize_refused PASSED            [ 66%]
python\tests\test_code_patch.py::test_outside_scope_refused PASSED       [ 77%]
python\tests\test_code_patch.py::test_ambiguous_span_refused PASSED      [ 88%]
python\tests\test_code_patch.py::test_base_mismatch_refused PASSED       [100%]
====================== 9 passed, 10 deselected in 0.19s =======================
```

## G6 — raw cancel / orphan / release probes

```
python\tests\test_code_worktree.py::test_release_idempotent PASSED       [ 20%]
python\tests\test_code_worktree.py::test_release_outside_scratch_refused PASSED [ 40%]
python\tests\test_code_worktree.py::test_release_outside_scratch_absolute_path_refused PASSED [ 60%]
python\tests\test_code_worktree.py::test_cancelled_run_sweep_leaves_no_orphan PASSED [ 80%]
python\tests\test_code_worktree.py::test_orphan_workspace_is_removed_by_release PASSED [100%]
======================= 5 passed, 7 deselected in 1.06s =======================
```

`ls -d .black-eclipse/code-workspaces/* | wc -l` → **0 residual**.

## G8 — raw `git.write` grep under `code/`

```
(no matches)
```

## G7 — jargon gate

```
src/lib/i18n/plain-language.test.ts (4 tests) 4 passed
```

## G9 — raw `git status --short`

```
 M Black-Eclipse-site/python/harness/agents.py
 M Black-Eclipse-site/python/harness/code/tools.py
 M Black-Eclipse-site/python/harness/graph.py
 M Black-Eclipse-site/python/harness/prompts.py
 M Black-Eclipse-site/python/harness/schemas.py
 M Black-Eclipse-site/python/harness/service.py
 M Black-Eclipse-site/python/harness/tools.py
 M Black-Eclipse-site/python/tests/test_code_tools.py
 M Black-Eclipse-site/src/lib/agent/response-model.ts
 M Black-Eclipse-site/src/lib/i18n/dictionaries/en.ts
 M Black-Eclipse-site/src/lib/i18n/plain-language.test.ts
 M Black-Eclipse-site/src/lib/i18n/refusal-copy.ts
?? Black-Eclipse-site/docs/harness/roadmap/progress/phase-02-progress.md
?? Black-Eclipse-site/python/harness/code/patch.py
?? Black-Eclipse-site/python/harness/code/store.py
?? Black-Eclipse-site/python/harness/code/worktree.py
?? Black-Eclipse-site/python/tests/test_code_patch.py
?? Black-Eclipse-site/python/tests/test_code_worktree.py
?? Black-Eclipse-site/scripts/scratch/
```

`jdds.db` does not appear; no `*.db` staged; no `.black-eclipse/` artifact is
tracked.
