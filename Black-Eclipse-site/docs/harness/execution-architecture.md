---
title: Code Execution & Verification Layer
status: Current
last-verified: 2026-10-06
---

# Code Execution & Verification Layer

**Who this is for:** anyone changing how Eclipse runs code, builds a project,
runs tests, diagnoses failures, starts a service, or reports that something
passed. This layer is what lets the agent take software from *idea* to *working,
tested, verified* without the user running every command.

## The one sentence

> Every run goes through one sandbox and one lifecycle; a runtime adapter owns
> language behaviour and the orchestrator owns everything else; and success is
> only ever claimed from actual execution evidence.

## Where it lives

```
python/harness/execution/
  state.py          ExecutionState enum + validated StateMachine
  models.py         ExecutionRequest/Context/Result + Diagnostic/TestResult/Artifact
  policy.py         ExecutionPolicyEngine (risk, network/fs narrowing, secrets)
  projects.py       ProjectDetector + detect_language (spec priority order)
  diagnostics.py    DiagnosticEngine (tsc/python/v8/eslint/pytest/generic parsers)
  build.py          BuildEngine + DependencyManager
  testing.py        TestEngine + TestDiscovery (vitest/jest/pytest/summary parsers)
  artifacts.py      ArtifactManager (bounded, hashed)
  orchestrator.py   ExecutionOrchestrator (the lifecycle)
  store.py          ExecutionStore (agent-memory.db tables)
  scheduler.py      ExecutionScheduler (bounded pool + cancellation)
  workflow.py       ExecutionPlan/Step/Workflow + RetryPolicy
  services.py       ServiceManager + PortManager + HealthChecker
  verify_loop.py    ExecutionVerifier (bounded build→test→fix loop)
  service.py        ExecutionService facade + build_request helper
  runtime.py        process-wide singleton (mirrors terminal/runtime.py)
  tools.py          the 21 agent tools
  runtimes/         base.py + python_rt/javascript/typescript/sql/shell
```

The HTTP surface is `python/harness/routers/execution.py` (`/execution/*`).

## Relationship to the other subsystems

| Subsystem | Owns | How execution uses it |
|---|---|---|
| **Terminal** (`terminal/`) | interactive shells, background process lifecycle, process trees, ports | `start_service` starts through `TerminalManager.start_process`; ports via `PortManager` over the terminal port table |
| **Sandbox** (`code/sandbox.py`) | the ONE bounded execution primitive | every one-shot run/build/test calls `sandbox.run(RunSpec)` |
| **Policy** (`code/policy.py`) | autonomy profiles, binding, command vocabulary, path safety | `ExecutionPolicyEngine` asks `code_grants`; `allowed_tools` removes write/execute tools structurally |
| **Workspace** (`code/workspace.py`) | root resolution + confinement | entrypoint/database confinement uses `resolve_within` |
| **Persistence** (`agent-memory.db`) | runtime tables | `ExecutionStore` owns `Execution*` tables on the shared connection |

The terminal is **not** replaced and **not** re-implemented. The two share the
low-level process primitive and the process manager; their responsibilities stay
distinct, exactly as the terminal doc requires.

## Lifecycle

`ExecutionOrchestrator.run()` follows one path, and a `finally` guarantees cleanup:

```
REQUEST → VALIDATE → RESOLVE PROJECT → DETECT LANGUAGE → RESOLVE RUNTIME
        → CREATE CONTEXT → PREPARE (stage workdir) → [BUILD] → [TEST] → RUN
        → COLLECT diagnostics/artifacts/metrics → CLEANUP → STORE RESULT
```

States (`state.py`): `QUEUED → VALIDATING → PREPARING → STARTING → RUNNING` then
one terminal state — `COMPLETED`, `FAILED`, `TIMED_OUT`, `CANCELLED`,
`RESOURCE_LIMIT`, `SECURITY_BLOCKED`, `RUNTIME_ERROR`, `BUILD_ERROR`,
`TEST_ERROR`. Transitions are validated; a terminal state has no outgoing edges.
An unexpected exception lands the machine on `FAILED` via `force_terminal` and the
staged working directory is always removed.

## Runtime adapters

`RuntimeAdapter` is the extension seam. To add a language, register one adapter —
the orchestrator does not change. Shipped:

- **PythonRuntime** — vendored interpreter preferred, then `sys.executable`, then
  `python3/python/py`; `PYTHONPATH=<root>` so the project's own modules import;
  build = `compileall`; test = `pytest` (or `unittest` by policy).
- **JavaScriptRuntime** — `node`; inline code staged as `.mjs` (or `.cjs` when it
  uses `require`); test = declared framework, `npm test`, or `node --test`.
- **TypeScriptRuntime** — the project's declared strategy first (`project-local
  tsx`/`ts-node`, or a `start`/`dev` npm script), then `npx tsx`/`ts-node`; build =
  the project's `build` script, then `tsc --noEmit` with the project's `tsconfig`.
- **SqlRuntime** — an embedded stdlib `sqlite3` runner; **read-only by default**;
  destructive statements are refused unless `read_only: false` (and the profile
  grants `code.write`). PostgreSQL needs an optional driver and refuses otherwise.
- **ShellRuntime** — wraps the command with the EXISTING `terminal/runtimes.py`
  argv builder and runs it through the same sandbox. No second shell management.

`Java/Go/Rust/C/C++/C#/PHP/Ruby` are in `_DECLARED_LANGUAGES` and are detected,
but report `UNAVAILABLE` honestly until an adapter ships.

## Security model

Three layers, all fail-closed:

1. **Structural** — `code/policy.allowed_tools` removes every write/execute
   execution tool at `plan_only`, before the model sees a schema.
2. **Policy engine** — `ExecutionPolicyEngine.evaluate_request` requires the actor's
   `code.execute` grant and a matching workspace binding; narrows the requested
   network/filesystem policy to the profile ceiling and **refuses** an explicit
   widening; refuses forbidden secrets (`.env`, cloud/SSH/GitHub tokens, API keys)
   with `SECRET_FORBIDDEN`; classifies the argv into a risk band and requires an
   approval at HIGH+.
3. **Sandbox + confinement** — entrypoints and SQLite databases are confined with
   `resolve_within` (traversal, absolute paths, symlinks, protected paths refused);
   inline programs are staged outside the workspace; the child environment is
   `sandbox.build_env` only.

Output is bounded per stream; a truncated run records `truncated: true` rather than
exhausting memory. Timeouts and cancellations kill the whole process tree.

## Diagnostics, tests and evidence

`DiagnosticEngine` turns opaque output into `Diagnostic{file,line,column,severity,
category,message,stack,source,code}`, trying the language's parsers first. `TestEngine`
normalizes vitest/jest JSON reports and pytest/go summary lines; when it cannot parse
a summary it sets `parsed: false` and never reports a pass. `ExecutionVerifier` runs
the bounded loop and returns `passed` only from a real `COMPLETED` build+test, with
the full evidence list attached. `ExecutionStore` persists the result and its
artifacts/tests/diagnostics/metrics for later reference (`execution_get`,
`execution_logs`, …).

## Agent tools

`execute_code` (universal) plus `execute_python`/`execute_javascript`/
`execute_typescript`/`execute_sql`/`execute_shell`; `build_project`/`test_project`/
`discover_tests`/`run_verification`; `start_service`/`stop_service`/
`restart_service`/`service_status`/`service_logs`/`list_services`;
`execution_get`/`execution_logs`/`execution_result`/`execution_artifacts`/
`cancel_execution`. All register on the SAME `ToolRegistry`; the execute/build/
service tools are `permission="write"` + `effect="external_action"` and are removed
at `plan_only`. The retrieval tools are prefixed `execution_`/`service_` (not
`get_`) so they do not collide with the code-agent's finance-tool guard.

## Configuration

Environment (all read at call time):

| Variable | Meaning | Default |
|---|---|---|
| `HARNESS_EXECUTION_ENABLED` | hard on/off switch | `1` |
| `HARNESS_EXEC_CPU_LIMIT` | fractional cores (advisory/monitored) | `1.0` |
| `HARNESS_EXEC_MAX_MEMORY_MB` | memory limit (reported/monitored) | `1024` |
| `HARNESS_EXEC_MAX_PROCESSES` | process-count limit | `64` |
| `HARNESS_EXEC_DEFAULT_TIMEOUT_MS` | default execution timeout | `60000` |
| `HARNESS_EXEC_STARTUP_TIMEOUT_MS` | startup timeout | `30000` |
| `HARNESS_EXEC_IDLE_TIMEOUT_MS` | idle timeout (0 = off) | `0` |
| `HARNESS_EXEC_MAX_OUTPUT_BYTES` | per-stream output cap | `1048576` |
| `HARNESS_EXEC_MAX_LOG_LINES` | log line cap | `10000` |
| `HARNESS_EXEC_MAX_CONCURRENCY` | scheduler worker count | `4` |

## Adding a language

1. Add a `RuntimeAdapter` under `execution/runtimes/` implementing
   `detect`/`available`/`resolve`/`prepare_run` (+ optional `build`/`test`/
   `discover_tests`).
2. Register it in `build_runtime_registry()`.
3. If it introduces a new argv program, add it to `_COMMAND_PROGRAMS`/the risk
   tables in `execution/policy.py` as needed.
4. Add a test in `test_execution_runtime.py`.

Do not add execution logic to the orchestrator, and do not add a second sandbox.

## Troubleshooting

- **`UNKNOWN_LANGUAGE`** — the language id is not registered; use a shipped one.
- **`SANDBOX_UNAVAILABLE`** — no isolation primitive on this platform; the run is
  refused, never executed unsandboxed.
- **`NETWORK_NOT_PERMITTED`** — the request asked for network under a no-network
  profile. This is intentional; install dependencies outside the session.
- **A test run reports `parsed: false`** — no recognizable summary was found; the
  output is in `stdout`. It is NOT a pass.
- **`INFRASTRUCTURE_ERROR`** — Eclipse could not run the check (runtime missing,
  sandbox failure). Distinct from a user-code error; do not "fix" it by editing
  code.
