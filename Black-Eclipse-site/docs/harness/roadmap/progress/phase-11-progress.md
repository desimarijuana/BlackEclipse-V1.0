---
title: "Phase 11 — Progress log (surface and scale)"
phase: 11
status: Done
last-verified: 2026-10-01
---

# Phase 11 — Progress log

Operating loop: `docs/harness/roadmap/README.md` §5. Phase file:
`docs/harness/roadmap/phase-11-surface-and-scale.md`.

Baseline before Phase 11 (Phase 10 close): vitest 174 / 1983; pytest 2218;
`check:all` ALL PASS.

## Gate checklist

- [x] G1 — every configured delivery target receives the job, with a PER-TARGET outcome
- [x] G1b — no destination configured refuses with `NO_DESTINATION`
- [x] G2 — cross-tenant isolation for jobs / code tasks / artifacts / workspaces
- [x] G3 — an unavailable backend refuses with `SANDBOX_UNAVAILABLE`, never degrades
- [x] G3b — the `local` backend's declared guarantees match the enforced policy constants
- [x] G4 — `doctor.js` reports the four new probes honestly
- [x] G5 — a fresh clone still runs with no manual steps (no dependency added)
- [x] G6 — the suite + the release gate
- [x] G7 — plain-language gate

## Raw gate output

G1 / G1b — delivery adapters, per-target outcomes, artifact contract:
```
python\tests\test_delivery_adapters.py  .........  [100%]
9 passed in 0.11s
```

G2 — cross-tenant isolation for the four surfaces:
```
python\tests\test_surface_tenancy_isolation.py  .......  [100%]
7 passed, 1 warning in 2.06s
```

G3 / G3b — the honest-failure rule + the `local` declaration:
```
python\tests\test_sandbox_backends.py  .........  [100%]
9 passed in 0.07s
```

G4 — doctor reports the four probes honestly:
```
[db-guard] database healthy ✓
[setup] vendored python: present
[setup] artifact directory: writable (.black-eclipse\artifacts)
[setup] container backend: not available (jobs that need one will decline)
[setup] remote backend: not configured
```

G5 — a fresh clone still runs with no manual steps: no new REQUIRED dependency
(`git status --short package.json package-lock.json` is empty); the container and
remote backends are probes only and never installed. The default path is `local`.

G6 — the suite + the release gate:
```
vitest:  Test Files  174 passed (174);  Tests  1983 passed (1983)
pytest:  2246 passed, 1 warning  (one flaky orphan-count test passed in isolation)
eval gates: ALL PASS
[check-all] ALL GATES PASSED
```

G7 — plain-language gate:
```
src/lib/i18n/plain-language.test.ts  4 passed
python/tests/test_plain_language.py  22 passed (3 new Phase-11 nodes)
```

## Recon findings / deviations (reported, not silent)

- **Multiple targets, one label each (§6.1/§6.3).** G1 requires all three targets
  on ONE job, so `JobDelivery` gained additive `targets: [JobDeliveryTarget]` beside
  the older `adapter`/`destination`. `effective_targets()` derives a single target
  from the old fields when `targets` is absent, so a job saved before Phase 11
  delivers exactly as it did. Every target records its own `DeliveryOutcome`.
- **The message key lives in `scheduler._message_for`.** The runtime sends a KEY +
  params (`jobs.delivery.message.done` / `.doneCount` / `.trouble`); a count is only
  included when the run actually reported one — never fabricated.
- **Artifact path confinement.** `artifact_dir_for` sanitizes the leaf and calls
  `policy.resolve_within` against the artifacts parent when no explicit root is
  given, so a malformed run id can never traverse. The scheduler passes an explicit
  root in tests; the route derives from the server-assigned run id.
- **`persistence.py` is ratcheted.** The scope filter for code tasks reads the
  existing `HarnessRun.userId` column in `TaskStore` (which owns the code-agent
  filter anyway) rather than growing the ratcheted `persistence.py` — the module is
  back at its pinned 1393 lines.
- **`/code/tasks` was never operator-gated.** Phase 5 gated the code *mutations*;
  the plain task list was not. G2's "every read refuses a non-operator" is asserted
  for the operator-gated reads (`/jobs`, `/code/workspaces`); `/code/tasks` is a
  scope filter and is not claimed as gated, so the boundary statement stays honest.
- **`decisions.md` / `CHANGELOG.md` appends are byte-exact.** The files carry
  non-ASCII em-dashes; the ADR and changelog entries were appended with a binary
  copy so no existing byte was re-encoded.
- **One flaky test, not a regression.** `test_kill_leaves_no_orphan_python_process`
  compares a process count and failed once under the full parallel suite (3 vs 2);
  it passes in isolation. No Phase-11 file is involved.

## 2026-10-01 — front-door surface closure

Status flipped to Done. The Python runtime for this phase was complete and its
gates green, but its user-facing surfaces were unreachable from the running app:
`src/app/api/jobs/**` and `src/lib/harness/jobs-client.ts` were reachable, yet
nothing imported `src/components/screens/jobs/**`, so no user could create a job.
The front-door surface closure (tracked in `surface-closure-progress.md`) mounted
the jobs screen (AppTab `jobs`, sidebar section, dynamic import + keep-alive block
in `stock-chat.tsx`, palette rows), which is what finished this phase's user-facing
obligation. No runtime behaviour changed.
