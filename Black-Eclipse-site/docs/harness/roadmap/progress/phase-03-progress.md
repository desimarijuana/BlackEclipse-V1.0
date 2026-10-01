---
title: "Phase 3 — Progress log (sandboxed command broker)"
phase: 3
status: Done
last-verified: 2026-10-01
---

# Phase 3 — Progress log

Operating loop: `docs/harness/roadmap/README.md` §5. Phase file:
`docs/harness/roadmap/phase-03-command-broker.md`.

Baseline before Phase 3 (Phase 2 close): vitest 169 / 1966; pytest 1841; eval
gates ALL PASS.

## Gate checklist

- [x] G1 — `npm run test`
- [x] G2 — probe suite, verbose
- [x] G3 — benign executions really work
- [x] G4 — no orphan processes after the kill probes
- [x] G5 — operator checkout/vault untouched
- [x] G6 — plain-language gate (vitest + pytest)
- [x] G7 — `npm run check:all`

## Recon — real shapes (read before writing)

- `persistence.py` measures **1392** against ratchet **1393** → the
  `HarnessCommandExecution` DDL and helpers go in `python/harness/code/store.py`
  (already exists from Phase 2), bound to the one `AgentMemoryStore` connection.
- `mcp/config.py` / `client.py` set the standard: argv arrays, no shell, explicit
  env allowlist, bounded timeouts, platform-appropriate reaping (Windows Job
  Object, POSIX process group). The broker matches it.
- `mcp/orphan_supervisor.py` documents the Windows Job Object
  (`KILL_ON_JOB_CLOSE`) guarantee the sandbox reuses.
- `ToolDefinition` has `permission`/`risk`/`timeout_ms`/`effect` (no
  `read_only`/`required_permissions` fields). `command_run` uses
  `permission="write"`, `effect="external_action"`; the authorizer admits it and
  the handler enforces `command.execute` from the run's autonomy profile.
- The vendored interpreter lives at `scripts/vendor/python/python.exe` (repo
  root, gitignored) — it is NOT present inside a git worktree, so `python_test`
  resolves its absolute path against the repo root while `cwd` stays the
  worktree.

## Honest limitation recorded

Network denial is enforced at the CLASS TABLE (only `dependency_install` sets
`network=True`, and it is operator-gated) plus a scrubbed environment with
proxies removed. There is no OS-level network namespace in this phase; a command
that attempts an outbound connection fails because the network is unreachable /
the class is refused, and the attempt is recorded. This is stated in ADR-H102.

## G1 / G7 — raw `npm run test` / `npm run check:all` (tail)

```
 Test Files  169 passed (169)
      Tests  1966 passed (1966)
================= 1889 passed, 1 warning in 196.53s (0:03:16) =================
[check-all] eval gates: node scripts/test-evals.js
[check-all] ALL GATES PASSED
```

Vitest unchanged (169/1966). Pytest rose **1841 → 1889** (the new
`test_code_commands.py` + `test_code_sandbox.py` + `test_plain_language.py`
nodes; the count also includes a concurrent agent's in-flight additions).

## G2 — raw probe suite (tail)

```
python\tests\test_code_commands.py::test_git_push_refused_and_recorded PASSED [ 84%]
python\tests\test_code_commands.py::test_dependency_install_refused_without_flag PASSED [ 87%]
python\tests\test_code_commands.py::test_plan_only_refused_and_recorded PASSED [ 90%]
python\tests\test_code_commands.py::test_unbound_workspace_refused PASSED [ 93%]
python\tests\test_code_commands.py::test_sandbox_unavailable_refuses_and_records PASSED [ 96%]
python\tests\test_code_commands.py::test_decide_command_grants_git_read_under_edit_verify PASSED [100%]
============================= 33 passed in 13.85s =============================
```

## G3 — raw benign probe

```
.                                                                        [100%]
1 passed, 22 deselected in 1.92s
```

## G4 — raw `tasklist //FI "IMAGENAME eq python.exe"`

```
0
```

(No residual python process after the kill probes; `test_kill_leaves_no_orphan`
also asserts the count does not grow.)

## G6 — raw plain-language gates

```
python\tests\test_plain_language.py ... 10 passed in 0.04s
src/lib/i18n/plain-language.test.ts (4 tests) 4 passed
```

## G5 — raw `git status --short`

```
 M Black-Eclipse-site/docs/CHANGELOG.md
 M Black-Eclipse-site/docs/NAVIGATION.md
 M Black-Eclipse-site/docs/harness/decisions.md
 M Black-Eclipse-site/docs/harness/roadmap/README.md
 M Black-Eclipse-site/docs/harness/roadmap/phase-03-command-broker.md
 M Black-Eclipse-site/python/harness/agents.py
 M Black-Eclipse-site/python/harness/code/store.py
 M Black-Eclipse-site/python/harness/code/tools.py
 M Black-Eclipse-site/python/harness/prompts.py
 M Black-Eclipse-site/python/harness/tools.py
 M Black-Eclipse-site/python/tests/test_code_tools.py
 M Black-Eclipse-site/src/lib/i18n/dictionaries/en.ts
 M Black-Eclipse-site/src/lib/i18n/plain-language.test.ts
 M Black-Eclipse-site/src/lib/i18n/refusal-copy.ts
?? Black-Eclipse-site/docs/harness/roadmap/progress/phase-03-progress.md
?? Black-Eclipse-site/python/harness/code/commands.py
?? Black-Eclipse-site/python/harness/code/sandbox.py
?? Black-Eclipse-site/python/tests/fixtures/code/{benign,echo_secret,failing,flood,infinite}_check.py
?? Black-Eclipse-site/python/tests/test_code_commands.py
?? Black-Eclipse-site/python/tests/test_code_sandbox.py
?? Black-Eclipse-site/python/tests/test_plain_language.py
```

`jdds.db` does not appear; no `*.db` staged; `persistence.py` untouched.

## Probe → row + event table

Every probe asserts BOTH behaviour and record:

| Probe | Behaviour | Record |
|---|---|---|
| benign `python_test` | exit 0 | `command.completed` + row `exitCode 0` |
| failing check | exit ≠ 0 | row with the real code |
| infinite loop | killed, `timedOut`, no orphan | `command.killed` + row `timedOut=1` |
| flood stdout | `truncated`, `totalChars` | `command.truncated` + row `truncated=1` |
| `rm_rf`/`curl`/`powershell`/`bash` | refused, never executed | `command.refused` + policy row |
| write outside worktree | contained (`..` arg refused) | refusal recorded |
| network fetch | denied by class | `COMMAND_NOT_ENABLED` refused |
| echo `CRON_SECRET` | finds `ABSENT` | env scrubbed |
| `git_read push` | refused (closed set) | `command.refused` |
| `dependency_install` no flag | refused | `command.refused` |
| `plan_only` | `PROFILE_DENIED` | `command.refused` + row |
| no backend | `SANDBOX_UNAVAILABLE`, not executed | `command.refused` + row |

## Concurrency note (README §4)

Mid-run, two unrelated tests (`test_graph.py::test_conversation_history…`,
`test_prompt_segments.py::test_reusable_token_accounting…`) failed. Investigation
showed a CONCURRENT agent's in-flight `runtime_context` change to
`graph.py`/`prompt_segments.py`/`context_budget.py` (files this phase never
touched); the failure was in their own tests and they fixed it. A fresh
`check:all` after it settled is green — contamination, not a Phase 3 regression.
