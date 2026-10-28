---
title: "Phase 5 — Progress log (coding agent, autonomy, approvals)"
phase: 5
status: Done
last-verified: 2026-10-01
---

# Phase 5 — Progress log

Operating loop: `docs/harness/roadmap/README.md` §5. Phase file:
`docs/harness/roadmap/phase-05-coding-agent.md`.

Baseline before Phase 5 (Phase 4 close): vitest 170 / 1969; pytest 1935; eval
gates ALL PASS.

## Gate checklist

- [x] G1 — `npm run check:all`
- [x] G2 — allowlist boundary tests
- [x] G3 — plan_only structural refusal probe
- [x] G4 — finance agent unchanged probe
- [x] G5 — approvals tests
- [x] G6 — task lifecycle tests
- [x] G7 — routes registered
- [x] G8 — `npm run test`
- [x] G9 — vault untouched
- [x] G10 — jargon gate

## Recon — real shapes (read before writing)

- **Tool-name reality check.** The roadmap sketch names tools that do NOT exist
  (`patch_apply`, `command_status`, `git_status`, `verification_ledger`,
  `workspace_symbols`). The tools Phases 1–3 actually registered are:
  `workspace_status/list/search/read/docs`, `workspace_patch_apply`,
  `workspace_diff`, `workspace_revert`, `command_run`. Phase 5 binds the
  ALLOWLIST to the REAL names (binding fictional names would make the boundary a
  no-op). `WRITE_TOOLS` = the effectful code tools; `EXTERNAL_ACTION_TOOLS` = the
  four new `code_*` action tools.
- `graph.py` measures **1674** against ratchet **1857** (~183 lines headroom).
  `main.py` is 1039 with no ratchet entry — it grows by exactly two lines
  (import + `include_router`).
- `mcp/approvals.py` owns `McpApproval`; the guarded claim is `_claim` (a single
  `UPDATE ... WHERE status='approved'` + rowcount check). Phase 5 lifts it into
  `claim_guarded` and adds `kind`/`workspaceId` additive columns.
- `deps.py` provides `require_operator` (transport/token only) and `service`; the
  router reaches shared state through it, never `main`.
- `run_lineage.RunLineage` already owns `RunCheckpoint` +
  `ToolExecutionIdempotency`; Phase 5's task lifecycle is a CONSUMER.

## G1 / G8 — raw `npm run check:all`

```
 Test Files  171 passed (171)
      Tests  1972 passed (1972)
================= 1971 passed, 1 warning in 164.52s (0:02:44) =================
  code_verify gate: PASS
[check-all] ALL GATES PASSED
```

Vitest 170/1969 → 171/1972 (+1 file/+3: the new `code-screens.test.ts`). Pytest
1935 → 1971 (the new `test_code_agent` / `test_code_approvals` /
`test_code_tasks` nodes). The ADR-H92 MCP approval tests are unchanged and green.

## G2/G5/G6 — raw probe suites

```
test_code_agent.py      .............  13 passed
test_code_approvals.py  .........       9 passed
test_code_tasks.py      .........       9 passed
```

## G3 — raw allowlist narrowing probe

```
plan_only allowlist: ('workspace_read',)
no write tool present: True
no external tool present: True
edit_verify allowlist: ('workspace_read', 'workspace_patch_apply', 'command_run')
edit_verify has write: True
edit_verify has external: False
unknown autonomy: ('workspace_read',)
```

## G4 — raw finance-unchanged probe

```
finance tool count: 24
finance n code: ['memory', 'session_open', 'session_search', 'skill_list', 'skill_view']
finance has a code tool: False
code agent allows MCP: False
```

## G7 — raw route registration

```
code routes: 12
  /code/approvals
  /code/approvals/{approval_id}/decide
  /code/tasks
  /code/tasks/{task_id}
  /code/tasks/{task_id}/actions
  /code/tasks/{task_id}/cancel
  /code/tasks/{task_id}/checks
  /code/tasks/{task_id}/diff
  /code/tasks/{task_id}/discard
  /code/tasks/{task_id}/plan/accept
  /code/tasks/{task_id}/resume
  /code/workspaces
```

## G10 — raw jargon gate

```
src/lib/i18n/plain-language.test.ts        (4 tests) 4 passed
src/components/screens/code/code-screens.test.ts (3 tests) 3 passed
```

## G9 — raw `git status --short`

No `*.db` appears; no `*.db` staged.

## Recon findings / deviations (reported, not silent)

- **Tool-name reality.** The roadmap sketch names tools that do not exist
  (`patch_apply`, `command_status`, `git_status`, `verification_ledger`,
  `workspace_symbols`). Phase 5 binds the allowlist to the REAL Phase 1–3 tools
  (`workspace_patch_apply`, `workspace_revert`, `command_run`, the read tools);
  `WRITE_TOOLS`/`EXTERNAL_ACTION_TOOLS` reflect those. Binding fictional names
  would have made the boundary a no-op.
- **`runTimeoutMs` ceiling.** `AgentConfig` caps `runTimeoutMs` at 600_000, so the
  code agent uses 600_000 (the Phase 4 repair wall-clock budget is enforced inside
  the loop, separately).
- **G7 enumeration.** Under the installed FastAPI (0.141) a router included via
  `include_router` is a lazy `_IncludedRouter`, so the roadmap's
  `{r.path for r in app.routes if r.path.startswith('/code')}` raises
  `AttributeError` — for the MCP routes too (a PRE-EXISTING environment condition,
  not a Phase 5 regression). The reliable enumeration is
  `app.openapi()['paths']`, which lists the 12 `/code` routes above.
- **ADR numbering.** ADR-H103/H104/H106 were consumed by concurrent prompt work,
  so Phase 5's ADR is **ADR-H107** (the next free number; the README table was
  shifted to match).
- **`main.py` growth.** 1039 → 1041 lines: +2 (import + `include_router`), per
  README §3.7 (the only permitted growth).

## Re-audit 2026-10-28

- Code-agent/finance separation holds: code-agent contains no finance tools and
  llowMcpTools is absent/false; finance contains no external code action
  (code_commit/code_push/code_open_pr/code_deploy).
- The allowlist boundary is structural: all 389 tools allowed at plan_only are
  permission=read and effect read/None across the real registry; edit_verify`n  removes every EXTERNAL_ACTION_TOOLS; unknown autonomy equals plan_only.
- Single-use claim is shared (mcp.approvals.claim_guarded; code/actions.py uses
  consume_kind). Task lifecycle reuses RunLineage checkpoints.
- Targeted gates: 38 passed (	est_phase5_audit.py + code agent/approvals/tasks).
- Correction: G4's literal 'finance has NO code tool' is stale. Later phases
  deliberately added scaffold_kit, capability_* and python_env_* to the
  finance agent; those are effect/approval-gated. The Phase 5 boundary that
  matters � no external code action on finance � still holds.

