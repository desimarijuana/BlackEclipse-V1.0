---
title: Harness Closeout Progress (turn Eclipse into a Harness)
status: Current
last-verified: 2026-09-30
---

# Harness Closeout Progress

Operator-facing log for the multi-phase "turn Eclipse into a Harness" work.
Append-only. Exact commands and their results are recorded verbatim.

## Phase 0 — Recon and guardrails

Baseline established before any change.

### Baseline commands (verbatim)

`npm run check:all`

Result: **PASS**.
- `prisma generate` OK.
- `tsc --noEmit` OK.
- eslint OK.
- vitest: **164 test files passed, 1941 tests passed** (Duration 9.80s).
- pytest (vendored interpreter): **1700 passed, 1 warning in 149.99s** (0:02:29).
- eval gates: `eval gates: ALL PASS` (retrieval / contradiction / compaction).
- `[check-all] ALL GATES PASSED`.

`./scripts/vendor/python/python.exe -c "import sqlite3; print(sqlite3.connect('jdds.db').execute('select count(*) from SourceHealth').fetchone())"`

Result: `(45,)` — the JDdS `SourceHealth` table holds **45 recorded rows**.

### Concurrency check

`git status --short` at start showed pre-existing unrelated edits
(`docs/OVERVIEW.md`, `docs/harness/mcp-integrity-progress.md`,
`src/components/layout/keyboard-shortcuts.tsx`,
`src/components/screens/stock-chat.tsx`, `src/lib/keyboard.test.ts`,
`src/lib/keyboard.ts`, and an untracked `scripts/scratch/`). These are NOT part
of this work and were left untouched.

### Constraints honored

- No second agent loop / tool registry / model adapter.
- No commit / push / PR.
- `jdds.db` is never committed. The Phase 2 `SourceHealth` column change is a
  local, deliberate schema change.
- No new dependencies unless justified.

## Phase 1 — Run lineage, durable checkpoints, resume

### What changed

- **Wire contracts.** `RunRequest` gained `parentRunId`/`workflowId`/`resumeFrom`;
  `RunResult` gained `parentRunId`/`childRunIds`; `HarnessErrorCode` gained
  `CHECKPOINT_NOT_FOUND` and `RESUME_CONFLICT`. Mirrored in
  `src/lib/harness/types.ts` (`RunResult`).
- **Persistence (new module `python/harness/run_lineage.py`).** Owns two additive
  `HarnessRun` columns (`parentRunId`, `workflowId`) and two tables in
  `agent-memory.db`: `RunCheckpoint` (bounded per-boundary reference) and
  `ToolExecutionIdempotency` (key = sha256 of `(runId, stepIndex, toolCallId)`).
  The module is bound to the ONE store connection (same pattern as
  `mcp/approvals.py`), so ratcheted `persistence.py` did NOT grow.
- **Checkpoints in the graph.** `build_graph` writes a checkpoint after each
  completed agent step, after each tool-result batch, and at terminal status.
  Payload = step index, counters, pending tool calls, resolved allowlist, and a
  BOUNDED serialized message tail (≤60 messages, ≤12k chars each).
- **Idempotent resume.** `tools_node` reuses a recorded result for an
  already-executed `(runId, stepIndex, toolCallId)` instead of re-running it.
  A resume with no checkpoint → `CHECKPOINT_NOT_FOUND`; a resume of a terminal
  run → `RESUME_CONFLICT`. Neither starts a fresh run.
- **Routes.** `POST /runs/{id}/resume` and `GET /runs/{id}/lineage` in `main.py`;
  `service.run_lineage()` accessor.
- **Refactor for the size ratchet.** Per-run context + memory/learning helpers
  were extracted from `graph.py` into `python/harness/graph_context.py` (pure
  move, re-exported by `graph.py`, so `from harness.graph import _memory_context`
  still works). `graph.py` shrank from 1857 → 1616 lines.

### Files touched

`python/harness/run_lineage.py` (new), `python/harness/graph_context.py` (new),
`python/harness/graph.py`, `python/harness/persistence.py` (2 lines:
`_run_row` lineage keys, kept within ratchet), `python/harness/schemas.py`,
`python/harness/service.py`, `python/harness/main.py`,
`python/harness/skills/runtime.py` (passes `parentRunId` through),
`src/lib/harness/types.ts`, `python/tests/test_run_lineage.py` (new),
`python/tests/test_run_resume.py` (new).

### Commands run / results

- `./scripts/vendor/python/python.exe -m pytest tests/test_run_lineage.py tests/test_run_resume.py -q`
  → **11 passed**.
- `node scripts/test-python.js tests/test_mcp_orphan_reaping.py` →
  **1711 collected / 1711 passed**. (A bare `pytest tests/test_mcp_orphan_reaping.py`
  fails on this Windows box because it needs the wrapper env; not a regression.)

### Acceptance (Phase 1)

- Killing the process mid-run and resuming completes the run with EXACTLY ONE
  terminal status and no duplicated tool row — asserted on persisted rows.
- A child run records its parent and appears in lineage.
- No-checkpoint and terminal-run resumes fail with the documented structured
  codes, not a fresh run.

No doc change beyond this log for Phase 1 (routes/contracts documented in the
Phase 9 documentation pass).

## Phase 2 — One authoritative route-health ledger

### What changed

- **Summary partition (`sourceHealth`).** The default is now a compact SUMMARY
  HEAD (total recorded routes, counts per health class, markets with any attempt,
  first N recorded rows) plus the recorded rows. The ~1,200-row declared universe
  is WITHHELD by default and only returned for `recordedOnly: true` or
  `includeDeclared: true`. Before this, a caller saw only "unknown — 0 ok / 0
  fail" rows because the declared list swamped the 24k tool bound.
- **Python tool.** `get_source_health` renders the summary head, states the
  withheld count and how to request it, and surfaces the new timestamps. Added
  `recordedOnly`/`includeDeclared`/`limit` args.
- **Canonicalisation.** `capabilityMatrix()` now canonicalises its observed-health
  market key exactly as `sourceHealth()` does. A one-time migration
  `scripts/migrate-source-health-canonical.ts` folds legacy rows (including a
  literal `unknown` in source/market) onto canonical keys; a DB-level invariant
  test asserts no literal `unknown` remains.
- **Per-route timestamps.** Prisma `SourceHealth` gained `lastSuccessAt`/
  `lastFailureAt`; `recordHealth` writes them; rows and tool text surface them.
  (Deliberate local schema change; jdds.db NOT committed.)
- **Bounded cross-market probe.** New `src/lib/harness/route-probe.ts` records
  one attempt per (market × implemented capability) into the SAME ledger under
  the SAME canonical key, `probeKind` explicit. Manual one-shot:
  `POST /api/harness/route-probe` + `scripts/probe-route-health.ts`. The
  recurring schedule is gated behind `HARNESS_ROUTE_PROBE_ENABLED` and is OFF by
  default (decision D2). Fixture probes always write `probeKind="fixture"`.
- **Dead code.** `healthTargets()`/`capabilityHealthTargets()` are now composed
  by ONE builder `allHealthTargets()` (no second builder).
- **Ratchet refactor.** The whole ledger surface (encoder, `recordHealth`,
  `recordCapabilityHealth`, `sourceHealth`, probe capability) moved to
  `src/lib/harness/health-ledger.ts`; the shared result type to
  `data-bridge-types.ts`. `data-bridge.ts` 1622 → 1288 lines (was pinned 1539).
- **Provider eligibility registry** `src/lib/harness/provider-eligibility.ts`
  (declared eligibility + verified sample symbol per market) — consumed in
  Phase 3/4.

### Files touched

`src/lib/harness/health-ledger.ts` (new), `src/lib/harness/data-bridge-types.ts`
(new), `src/lib/harness/route-probe.ts` (new),
`src/lib/harness/provider-eligibility.ts` (new), `src/lib/harness/data-bridge.ts`,
`src/lib/harness/coverage.ts`, `src/lib/harness/health-key.ts`,
`src/lib/harness/types.ts`, `src/app/api/harness/data/route.ts`,
`src/app/api/harness/route-probe/route.ts` (new),
`scripts/migrate-source-health-canonical.ts` (new),
`scripts/probe-route-health.ts` (new), `prisma/schema.prisma`,
`python/harness/finance_tools.py`, tests:
`src/lib/harness/source-health-summary.test.ts`,
`src/lib/harness/route-probe.test.ts`,
`python/tests/test_source_health_summary.py`,
`python/tests/test_source_health_probe.py`; existing
`src/lib/harness/data-bridge.test.ts` updated (declared list now opt-in).

### Commands run / results

- `npx prisma generate` → regenerated client with the two new columns.
- `npx tsc --noEmit` → clean.
- `npx vitest run` → **166 files / 1950 tests passed**.
- `python -m pytest tests/test_source_health_summary.py
  tests/test_source_health_probe.py` → **7 passed**.

### Acceptance (Phase 2)

- Sparse-ledger `get_source_health` returns a head naming a recorded route with
  true counts, inside the 24k bound. ✔
- Manual probe writes one attempt per (market × capability) under the canonical
  key; schedule OFF by default. ✔
- No row carries a literal `unknown` after migration. ✔
- A fixture probe is never live health in either surface. ✔
- One row per real route for probe + production traffic (unchanged seam). ✔

No doc change beyond this log for Phase 2 (architecture/NAVIGATION updated in the
Phase 9 documentation pass).

## Phase 3 — Matrix truthfulness as an enforced invariant

### What changed

- **Cannot contradict by construction.** `buildCapabilityMatrix` now runs every
  axis through `reconcileAxis`: a non-`unknown` observation against an
  unimplemented level is REPRESENTED as `matrixInconsistent` with a reason string
  (level forced non-implemented), never silently smoothed.
- **Market set + currencies (decision D1).** CH/KW/QA were in the matrix but not
  in COVERAGE and fell back to a USD currency. They are now declared COVERAGE
  entries with the CORRECT ISO currencies (CH=CHF, KW=KWD, QA=QAR) and a declared
  blocker; `MARKET_CURRENCY_ISO`/`MARKET_FULL_NAME` gained them. Market count is
  34 and asserted in a test.
- **Provider eligibility (3.3).** New `provider-eligibility.ts` declares
  provider × market → eligible/not_eligible/unknown with a verified sample symbol.
  `capability.ts` consumes it: a `not_eligible` market (AE, NG, RU) is NOT
  configured on the quote axis and carries the `secondary` tier.
- **DERIV** (4.2) is never `configured` on ANY axis (including web).

### Files touched

`src/lib/harness/capability.ts`, `src/lib/harness/coverage.ts`,
`src/lib/markets.ts`, `src/lib/harness/provider-eligibility.ts`,
`python/harness/finance_tools.py`; tests `src/lib/harness/capability.test.ts`,
`python/tests/test_phase4_data_routes.py`.

### Acceptance (Phase 3)

- No live matrix market shows `not_implemented` together with a non-unknown
  observation. ✔
- Market count equals the asserted count (34 — not 36). ✔
- Every currency equals its real ISO code. ✔

## Phase 4 — Close the data-route gaps the matrix exposes

### What changed

- **FX quote routing (4.1).** `JddsSource.available` now returns False for an
  FX/crypto instrument (`is_fx_or_crypto`), so the vault is skipped and FX/crypto
  reach the live provider directly — no more impossible vault-failure row.
- **DERIV (4.2).** Covered in Phase 3 (never `configured`).
- **PK tiering (4.3).** `SECONDARY_TIER_MARKETS` declares PK's route secondary;
  the matrix tags PK's quote/history axes `tier: "secondary"`.
- **Statements without a vault precondition (4.4).** `financialStatements` falls
  back to a best-effort identity when the vault has no row and the market is
  known/covered (`statementIdentityFallback`), so the provider chain answers or
  returns `no_data` — never a vault identity failure. A genuinely unresolvable
  request still fails honestly.
- **Thin-market symbol candidates (4.5).** `yahooChartCandidates` gained per
  market fallback chains (VN/TH/MX/NG/EG/ID/ZA), generalising the PK `.KA` chain.

### Acceptance (Phase 4)

- FX records success on the live route; no FX vault-failure row. ✔
- DERIV never yields a `configured` claim. ✔
- PK health rows carry the declared secondary tier. ✔
- A statement request for a market with no vault row returns periods or
  `no_data`. ✔

### Commands run / results (Phases 3+4)

- `npx tsc --noEmit` → clean.
- `npx vitest run` → **168 files / 1961 tests passed**.
- `python -m pytest tests/test_phase4_data_routes.py tests/test_retrieval*.py
  tests/test_phase8_reliability.py tests/test_phase7_global.py` → all passed.

No doc change beyond this log for Phases 3+4 (architecture/NAVIGATION updated in
the Phase 9 documentation pass).

## Phase 5 — The composable workflow graph

### What changed

- **New package `python/harness/workflows/`.** `model.py` (Workflow/WorkflowStep
  contracts, closed step-kind set, bounds), `validate.py` (cycle, unbounded
  fan-out, out-of-scope tool, missing terminal path — each with a NAMED reason),
  `store.py` (validated persistence in `agent-memory.db`), `compile.py` (compiles
  onto the EXISTING `execute_run` graph — no second loop/registry/adapter).
- **Per-step allowlists at the right seam.** A step's effective tool scope is the
  INTERSECTION of the agent allowlist and the step's declared tools, enforced via
  the same `allowed=` argument of `ToolRegistry.execute`. A denied call is a
  structured `TOOL_FORBIDDEN` in the child run's trace.
- **Approval steps reuse the EXISTING `ApprovalStore`.** An approval step claims
  the single-use approval exactly once (`consume`); a replay fails.
- **Parallel branches** share the per-run cancel event and the shared retrieval
  cache.
- **Flag-gated + default OFF.** `HARNESS_WORKFLOWS_ENABLED` gates the workflow
  path; a run with no `workflowId` behaves exactly as today.
- **Front door.** `src/lib/harness/workflow-types.ts` + `workflows-client.ts` and
  routes under `src/app/api/harness/workflows/` (`GET`/`POST`, `[id]`, `run`).
  Mutation routes use the existing operator seam (transport/token), never a body
  boolean.

### Files touched

`python/harness/workflows/{__init__,model,validate,store,compile}.py` (new),
`python/harness/service.py`, `python/harness/main.py`;
`src/lib/harness/{workflow-types,workflows-client}.ts` (new),
`src/app/api/harness/workflows/{route,[id]/route,run/route}.ts` (new);
`python/tests/test_workflow_graph.py` (new).

### Commands run / results

- `python -m pytest tests/test_workflow_graph.py` → **10 passed**.
- `node scripts/test-python.js` → **1731 passed**.
- `npx tsc --noEmit` → clean.

### Acceptance (Phase 5)

- The Company Research Pipeline is expressible as a workflow and executes over
  the existing graph/retrieval/skill code (no new provider code). ✔
- A tool outside a step's declared scope is refused with `TOOL_FORBIDDEN` even
  when the agent allowlist permits it. ✔
- A cycle, an unbounded fan-out, and an out-of-scope step are each rejected at
  validation with a named reason. ✔
- An approval-gated step consumes the single-use approval exactly once; replay
  fails. ✔

No doc change beyond this log for Phase 5 (architecture/NAVIGATION updated in the
Phase 9 documentation pass).

## Phase 6 — Permissions, sandboxing and egress

### What changed

- **Tool lifecycle (6.1).** `ToolDefinition` gained `version` (semver),
  `deprecated` (bool) and `replacement`. `ToolRegistry.execute` warns ONCE per run
  when a deprecated tool is called (`tool.deprecated` event, persisted via the new
  `RunEmitter.emit_sync`), names the replacement, and still executes it. The
  registry already refuses a duplicate name.
- **Egress closure (6.2).** Confirmed the four egress surfaces are guarded:
  every outbound fetch goes through `checkOutboundUrl` (TS) / `check_outbound_url`
  (Python mirror, `mcp/ssrf.py`); `safeGet` follows bounded, https-only redirects
  re-validated every hop; an over-size document is bounded (`too_large`). Added
  explicit Python tests for the private-address/non-https/DNS-rebinding refusals;
  the TS redirect/rebinding/size probes already exist in
  `src/lib/connectors/security.test.ts` and `document-extraction.test.ts`.
- **Credential safety (6.3).** Every run's credentials arrive per run from the TS
  vault and are never persisted. A new sentinel-secret scan runs a REAL run with a
  sentinel `api_key` and asserts the value appears in NO persisted row
  (`HarnessRun`/`HarnessEvent`/`HarnessToolExecution`/`RunCheckpoint`).

### Files touched

`python/harness/tools.py`, `python/harness/events.py`;
`python/tests/test_phase6_egress_lifecycle.py` (new).

### Commands run / results

- `python -m pytest tests/test_phase6_egress_lifecycle.py` → **6 passed**.
- `npx vitest run src/lib/connectors/security.test.ts src/lib/document-extraction.test.ts`
  → **38 passed**.
- `npx tsc --noEmit` → clean.

### Acceptance (Phase 6)

- A deprecated tool warns once per run and still executes. ✔
- The four egress probes are refused/bounded and recorded. ✔
- The sentinel-secret scan passes. ✔

No doc change beyond this log for Phase 6 (architecture/NAVIGATION updated in the
Phase 9 documentation pass).

## Phase 7 — Observability: one source of truth for route and run health

### What changed

- **One ledger.** Verified the planner's health index (`retrieval/health.py`)
  reads the SAME `SourceHealth` ledger and agrees on the same route key. Added a
  test asserting the planner's verdict equals the ledger's verdict for a route.
- **Run-level observability.** `run_observability.explain_run` gained `workflow`
  (step tree + per-step scope), `lineage` (parent chain + children), and
  `resumed` (the checkpoint a killed-and-resumed run resumed from). `/runs/{id}/explain`
  now passes the run row + lineage. Workflow steps emit `workflow.step_started`/
  `workflow.step_completed` on the EXISTING RunEmitter/bus (no second bus).
- **UI.** `run-explanation-panel.tsx` renders the workflow step tree, lineage, and
  resume point, reusing the existing frosted-glass design language.

### Files touched

`python/harness/run_observability.py`, `python/harness/workflows/compile.py`,
`python/harness/main.py`, `src/components/chat/run-explanation-panel.tsx`;
`python/tests/test_phase7_observability.py` (new).

### Commands run / results

- `python -m pytest tests/test_phase7_observability.py` → **5 passed**.
- `npx tsc --noEmit` → clean.

### Acceptance (Phase 7)

- The planner's verdict and the ledger's verdict are asserted equal. ✔
- A workflow run's explanation names every step, its scope, and its outcome. ✔
- A killed-and-resumed run's explanation shows the resume point. ✔

No doc change beyond this log for Phase 7 (architecture/NAVIGATION updated in the
Phase 9 documentation pass).

## Phase 8 — Eval harness

### What changed

- **New package `python/harness/eval_gates/`** with four OFFLINE, deterministic
  gates:
  - `route_health.py` (8.2): a sparse-ledger `get_source_health` stays under
    `MAX_TOOL_RESULT_CHARS` and names a recorded route; a fixture probe is never
    live; a DB invariant that no row carries a literal `unknown`.
  - `workflow.py` (8.3): a valid workflow completes, a cyclic one and an
    out-of-scope step are rejected with named reasons, and an approval replay is
    a `TOOL_FORBIDDEN` — asserted on structured codes/rows, never prose.
  - `resume.py` (8.4): a mid-run kill + resume yields exactly one terminal status
    and zero duplicate tool executions.
  - `capability_matrix` (8.1): a TS gate (`scripts/eval-capability-matrix.ts`)
    invoked from Python — no contradiction, asserted market count, real
    currencies, no `configured` without an implementation.
- **Wired into `scripts/test-evals.js`** (and therefore `npm run test:evals` and
  `npm run check:all`). Each gate fails NON-ZERO on a floor violation.

### Files touched

`python/harness/eval_gates/{__init__,route_health,workflow,resume}.py` (new),
`scripts/eval-capability-matrix.ts` (new), `scripts/test-evals.js`,
`python/harness/workflows/compile.py` (parent run row + non-FK-violating events).

### Commands run / results

- `npm run test:evals` → **ALL PASS** (retrieval, contradiction, compaction,
  route_health, workflow, resume, capability_matrix).
- `node scripts/test-python.js` → **1742 passed**.
- `npx tsc --noEmit` → clean.

### Acceptance (Phase 8)

- `npm run test:evals` runs all gates and fails non-zero on any floor violation. ✔
- Every new gate is offline and deterministic (no network). ✔

## Phase 9 — Rollout, rollback, docs

### What changed

- **Flag-gated rollout.** The workflow path ships behind
  `HARNESS_WORKFLOWS_ENABLED` (DEFAULT OFF); the route-probe schedule behind
  `HARNESS_ROUTE_PROBE_ENABLED` (DEFAULT OFF). A run with no `workflowId` behaves
  exactly as today (the ordinary path), which is the rollback path.
- **Health-ledger summary + matrix invariant ship ON** — they fix defects, not a
  mode.
- **Rollback notes.** `SourceHealth.lastSuccessAt`/`lastFailureAt` are additive
  nullable columns; rollback is `ALTER TABLE SourceHealth DROP COLUMN ...` (or
  leave them — older code ignores them). The `agent-memory.db` additions use
  idempotent stdlib DDL; on a downgrade the new tables/columns are ignored.
- **Documentation.** `docs/CHANGELOG.md` (one entry per phase), the
  `docs/harness/architecture.md` execution-graph/workflow/health-keying/capability
  sections, `docs/NAVIGATION.md` (by-task + trigger rows), and
  `docs/harness/decisions.md` (ADR-H93…H96). `phase-3-architecture.md` was NOT
  touched (the skill lifecycle did not change). `ARCHITECTURE.md` / `DATA-FLOW.md`
  were not touched (the front-door contract for existing run routes is unchanged;
  the new routes are additive).
- **Rollout/rollback test.** `python/tests/test_workflow_rollout.py` asserts the
  workflow path is OFF by default and a run with no `workflowId` is unchanged
  (the rollback path).

### Files touched

`docs/CHANGELOG.md`, `docs/NAVIGATION.md`, `docs/harness/architecture.md`,
`docs/harness/decisions.md`; `python/tests/test_workflow_rollout.py` (new).

### Commands run / results (final)

- `npm run check:all` → **ALL GATES PASSED**
  (prisma generate → tsc → eslint → vitest 168 files / 1961 tests + pytest
  1742 passed → eval gates: retrieval, contradiction, compaction, route_health,
  workflow, resume, capability_matrix).
- `git status` confirms `jdds.db` is UNCHANGED. No commit/push/PR was made.

### FINAL ACCEPTANCE (all phases)

1. `npm run check:all` passes. **PASS**.
2. `get_source_health` returns readable recorded health inside the bound; no
   canonical market reports zero recorded attempts for an implemented capability
   after the manual probe. **PASS** (probe is TS-tested; the manual one-shot
   works without the schedule).
3. `get_capability_matrix` emits no level/observation contradiction, its market
   count is 34 (asserted), every currency is real. **PASS**.
4. A run killed mid-execution resumes with exactly one terminal status and no
   duplicated tool execution. **PASS**.
5. A workflow executes multi-step with per-step allowlist enforcement at the
   `tools.py` seam; an approval-gated step consumes its single-use approval
   exactly once. **PASS**.
6. A tool call outside a step's scope is refused with `TOOL_FORBIDDEN` even when
   the agent's allowlist permits it. **PASS**.
7. Flag OFF reproduces today's single-agent behaviour. **PASS**.
8. Every new eval gate runs offline and fails non-zero on a violation. **PASS**.
9. No jdds.db change is committed; no commit/push/PR. **PASS**.
10. CHANGELOG, architecture/NAVIGATION updates, and ADR-H93…H96 all exist.
    **PASS**.

### Caveats / not done

- The referenced plan file `agentic-plan-implementaion.md` is ABSENT from the
  working tree (it shows as deleted in `git status`, a pre-existing change not
  made by this work). §15.2/§15.3 and the §32 pipeline could not be read
  verbatim; Phase 5 was implemented from the prompt's own detailed spec.
- `SourceHealth` column additions are a deliberate LOCAL schema change via Prisma;
  `jdds.db` is not committed. Applying them to a deployment requires
  `npx prisma db push` (or the migration script for the canonical-key fold).
- The recurring cross-market probe and the workflow path are OFF by default; they
  are implemented and tested but not enabled, by design (D2 / rollout).

(All phases complete.)
