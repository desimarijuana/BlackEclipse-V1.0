---
title: "Phase 6 — Progress log (harness-owned jobs and event triggers)"
phase: 6
status: Done
last-verified: 2026-10-01
---

# Phase 6 — Progress log

Operating loop: `docs/harness/roadmap/README.md` §5. Phase file:
`docs/harness/roadmap/phase-06-jobs-and-triggers.md`.

Baseline before Phase 6 (Phase 5 close): vitest 171 / 1972; pytest 1971;
`check:all` ALL PASS.

## Gate checklist

- [x] G1 — `test_jobs_cron.py` (cron correctness, injected clock)
- [x] G2 — `test_jobs_scheduler.py` (injected-clock scheduler; a job fires twice)
- [x] G2b — missed window reconciled once at startup, recorded `missed=1`
- [x] G3 — `test_jobs_api.py` (every route refuses a non-operator)
- [x] G4 — `test_jobs_guardrails.py` (save-time guardrails)
- [x] G4b — breaker trips, records a reason, operator reset closes it
- [x] G4c — a disabled pinned skill makes the run fail honestly
- [x] G5 — `npm run test` && `npm run check:all`
- [x] G6 — `git status --short` (three TS schedulers unchanged; `jdds.db` absent)
- [x] G7 — plain-language gate: job editor / library / delivery strings

## Raw gate output

G1 — cron:
```
python/tests/test_jobs_cron.py  .....................  [100%]
21 passed in 1.16s
```

G2 / G2b — scheduler (injected clock; a job fires twice, running is not relaunched,
missed window recorded once with missed=1, breaker trips/resets, disabled pinned
skill fails honestly):
```
python/tests/test_jobs_scheduler.py  .......  [100%]
7 passed in 0.85s
```

G3 — every jobs route refuses a non-operator:
```
python/tests/test_jobs_api.py  .............................  [100%]
29 passed, 1 warning in 1.90s
```

G4 / G4b / G4c — guardrails:
```
python/tests/test_jobs_guardrails.py  ..........  [100%]
10 passed in 0.05s
```

Route registration (`app.openapi()['paths']`, 9 `/jobs` routes):
```
/jobs  /jobs/templates  /jobs/{job_id}  /jobs/{job_id}/disable
/jobs/{job_id}/enable  /jobs/{job_id}/reset-breaker  /jobs/{job_id}/run
/jobs/{job_id}/runs  /jobs/{job_id}/trigger
```

G5 — release gate:
```
 Test Files  172 passed (172)
      Tests  1975 passed (1975)
================= 2038 passed, 1 warning in 159.99s =================
eval gates: ALL PASS
[check-all] ALL GATES PASSED
```
Vitest 171/1972 → 172/1975 (+1 file/+3: `jobs-screens.test.ts`). Pytest
1971 → 2038 (the four new `test_jobs_*` files: 21 + 7 + 29 + 10 = 67 nodes).

G6 — the three TS schedulers are byte-unchanged; no `*.db` change:
```
git diff --stat -- src/lib/scraper/scheduler.ts \
  src/lib/connectors/refresh-scheduler.ts src/lib/investor-eye/scheduler.ts
   (empty)
git status --short | Select-String "scheduler|.db"
   (only the new python/tests/test_jobs_scheduler.py)
```

G7 — plain language:
```
src/lib/i18n/plain-language.test.ts        (4 tests) 4 passed
src/components/screens/jobs/jobs-screens.test.ts (3 tests) 3 passed
python/tests/test_plain_language.py        10 passed
```

## Recon findings / deviations (reported, not silent)

- **A job run IS a normal run.** `JobScheduler._run_job` calls the existing
  `service.run` (objective jobs) or `service.run_skill` (skill jobs); the
  `HarnessJobRun.runId` column links to the resulting `HarnessRun`, so the trace,
  events, tool executions and code verification ledger all exist. No second
  execution record.
- **Breaker reuse.** `jobs/scheduler.py` imports `FAILURE_THRESHOLD`,
  `COOLDOWN_S` and the `closed`/`open`/`half_open` names from `mcp/circuit.py`
  rather than declaring a second set of constants.
- **Model settings for a scheduled run.** A scheduled job has no request to carry
  vault-resolved model settings, so the scheduler uses a conservative env default
  (`HARNESS_JOB_PROVIDER`/`HARNESS_JOB_MODEL`, default `ollama`/`llama3.1`). A
  provider that is not configured makes the run fail honestly
  (`PROVIDER_NOT_CONFIGURED`), never a fake success.
- **Missed-run anchor.** A recorded `skipped` decision (overlap, breaker-open, or
  a startup `on_missed=skip`) touches `HarnessJob.lastRunAt` so the SAME decision
  is not recorded again on the next tick — asserted by the reconcile-twice test.
- **Persistence ownership.** The `HarnessJob`/`HarnessJobRun` DDL lives in
  `jobs/store.py` bound to the ONE `AgentMemoryStore` connection (the
  `run_lineage.py`/`code/store.py` pattern), so `persistence.py` — pinned at its
  size ratchet — did not grow.
- **`main.py` growth.** +2 lines (import + `include_router`) plus the lifespan
  `start_jobs`/`stop_jobs` calls, per README §3.7.
- **Webhook token.** Generated with `secrets.token_urlsafe(32)`; only the SHA-256
  hash is stored. The plaintext is returned ONCE at creation (top-level
  `webhookToken`) and is deliberately NOT included in the job view dict.
- **ADR numbering.** ADR-H108 was free at close (Phase 5 used H107), so no
  renumbering was needed.
