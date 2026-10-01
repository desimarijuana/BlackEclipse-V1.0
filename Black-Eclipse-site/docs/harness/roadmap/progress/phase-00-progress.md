---
title: "Phase 0 — Progress log (recon, policy decision, baseline freeze)"
phase: 0
status: Done
last-verified: 2026-10-01
---

# Phase 0 — Progress log

Operating loop: `docs/harness/roadmap/README.md` §5. Phase file:
`docs/harness/roadmap/phase-00-policy-and-baseline.md`.

## Baseline freeze

Run from `Black-Eclipse-site/` on 2026-10-01, before any Phase 0 edit.

### Gate checklist

- [x] G1 — `npm run check:all`
- [x] G2 — `./scripts/vendor/python/python.exe -m pytest python/tests/test_code_policy.py -q`
- [x] G3 — `npm run test`
- [x] G4 — default/operator actor prints `[]`
- [x] G5 — denylist exists as data, all lowercase
- [x] G6 — plain-language reasons gate
- [x] G7 — `git status --short` (jdds.db absent)

### G1 — raw `npm run check:all` (baseline)

```
 Test Files  168 passed (168)
      Tests  1962 passed (1962)
   Start at  10:21:13
   Duration  8.75s (transform 8.45s, setup 0ms, import 25.61s, tests 12.68s, environment 51ms)

collected 1744 items
...
python\tests\test_workflow_rollout.py ..                                 [100%]
================= 1744 passed, 1 warning in 149.44s (0:02:29) =================
...
  route_health gate: PASS
  workflow gate: PASS
  resume gate: PASS
  capability_matrix gate: PASS
eval gates: ALL PASS
[check-all] ALL GATES PASSED
```

Baseline counts (the numbers later phases compare against):
**vitest 168 files / 1962 tests; pytest 1744 nodes; eval gates ALL PASS.**

### G7 — raw `git status --short` (baseline, pre-change)

```
?? Black-Eclipse-site/scripts/scratch/
```

`jdds.db` does not appear. The only entry is a pre-existing untracked scratch
folder, not produced by this phase.

## Acceptance gates (post-change, raw output)

Run from `Black-Eclipse-site/` after the Phase 0 edits.

### G2 — raw `pytest python/tests/test_code_policy.py -q`

```
.................................                                        [100%]
33 passed in 0.22s
```

### G4 — raw default/operator actor check (from `python/`, vendored python)

```
[]
[]
```

Both print `[]`. (Note: the vendored `python312._pth` disables `cwd`/`PYTHONPATH`
resolution, so the one-liner must run from `python/` for `harness` to import.)

### G5 — raw denylist check

```
23 denylist terms
[]
```

### G6 — raw `pytest ... -k plain_language -v`

```
python\tests\test_code_policy.py::test_plain_language_every_refusal_reason_is_one_sentence PASSED [ 33%]
python\tests\test_code_policy.py::test_plain_language_every_refusal_reason_avoids_the_mechanism_denylist PASSED [ 66%]
python\tests\test_code_policy.py::test_plain_language_allowed_decision_reasons_are_also_clear PASSED [100%]
====================== 3 passed, 30 deselected in 0.10s =======================
```

### G1 / G3 — raw `npm run check:all`

```
[check-all] prisma generate: npx.cmd prisma generate
[check-all] typecheck: npx.cmd tsc --noEmit
[check-all] lint: npx.cmd eslint .
[check-all] tests (vitest + python): npm run test
 Test Files  168 passed (168)
      Tests  1962 passed (1962)
================= 1777 passed, 1 warning in 133.44s (0:02:13) =================
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

Vitest is unchanged (168/1962). Pytest rose **1744 → 1777** — exactly the +33
new policy tests, nothing else moved.

### G7 — raw `git status --short` (post-change)

```
 M Black-Eclipse-site/docs/CHANGELOG.md
 M Black-Eclipse-site/docs/NAVIGATION.md
 M Black-Eclipse-site/docs/harness/decisions.md
 M Black-Eclipse-site/docs/harness/roadmap/README.md
 M Black-Eclipse-site/docs/harness/roadmap/phase-00-policy-and-baseline.md
 M Black-Eclipse-site/python/harness/skills/manifest.py
 M Black-Eclipse-site/python/harness/skills/permissions.py
?? Black-Eclipse-site/docs/harness/roadmap/progress/
?? Black-Eclipse-site/python/harness/code/
?? Black-Eclipse-site/python/tests/test_code_policy.py
?? Black-Eclipse-site/scripts/scratch/
```

`jdds.db` does not appear; no `*.db` staged. `scripts/scratch/` was already
untracked before Phase 0 and is untouched.

### Single-authority confirmation

`grep` for the policy entry points finds exactly one definition each, all in
`python/harness/code/policy.py`: `PROTECTED_PATHS` (line 57), `resolve_within`
(239), `code_grants` (260), `decide_write` (283), `decide_command` (312).

## Recon — the real contents of the files (read in full before editing)

`python/harness/skills/manifest.py` (383 lines) really contains, at the time of
this phase:

- `Permission` `Literal[...]` already declares `code.execute`, `code.write`,
  `production.modify`, `trade.execute`, `broker.modify` (plus the safe/operator
  nouns). The Phase 0 nouns `code.read`, `git.read`, `git.write`,
  `workspace.admin`, `command.execute` are **absent** and must be added.
- The real `FORBIDDEN_PERMISSIONS` is **not** the sketch in §6.1 — it is:

  ```python
  FORBIDDEN_PERMISSIONS: frozenset[str] = frozenset(
      {"trade.execute", "broker.modify", "production.modify", "code.write"}
  )
  ```

  i.e. it carries `code.write` (matching roadmap §2). Phase 0 narrows it to the
  trade/broker/production triple and introduces `CODE_PERMISSIONS`.

`python/harness/skills/permissions.py` (171 lines) really contains:

- `SAFE_PERMISSIONS` = the 7 read-only research/analysis nouns.
- `OPERATOR_PERMISSIONS` = the 5 lifecycle/portfolio nouns.
- `BLOCKED_PERMISSIONS = FORBIDDEN_PERMISSIONS | frozenset({"code.execute"})`,
  subtracted from every actor in `Actor.granted()`. The `Actor` dataclass has
  `id` / `operator` / `grants` / `scopes` only — no workspace binding.
- `DEFAULT_ACTOR = Actor(id="local", operator=False)`;
  `OPERATOR_ACTOR = Actor(id="operator", operator=True)`.

Downstream consumers that reference the changing constants (must stay green):

- `python/harness/skills/patches.py` — `NON_CANARY_PERMISSIONS` lists
  `code.write` / `code.execute` locally (independent of the manifest), so
  narrowing `FORBIDDEN_PERMISSIONS` does not weaken the canary block.
- `python/harness/skills/evaluation.py` — permission dimension reads
  `FORBIDDEN_PERMISSIONS`; narrowing it means a skill declaring `code.write` is
  no longer auto-failed there (by design; code verbs are gated by
  `code/policy.py` + the workspace-bound actor, not by the skill manifest).
- `python/tests/test_skills_registry.py` — asserts `trade.execute` is still
  blocked, which remains true.

## ADR numbering

The prompt assumed the harness series ended at `ADR-H92`. It does **not**:
`docs/harness/decisions.md` already carries `ADR-H93` (run lineage), `ADR-H94`
(route-health report), `ADR-H95` (capability matrix) and `ADR-H96` (workflow
compiler) from the 2026-09-30 harness closeout. Per the decision recorded with
the operator, Phase 0 appends the three next free numbers — **ADR-H97,
ADR-H98, ADR-H99** — rather than duplicating the existing headers.
