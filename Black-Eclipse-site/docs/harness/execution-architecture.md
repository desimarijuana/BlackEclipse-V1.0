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
  autofix.py        opt-in model repair (schema-validated, confined)
  telemetry.py      real CPU/memory sampling (no psutil)
  service.py        ExecutionService facade + build_request helper
  runtime.py        process-wide singleton (mirrors terminal/runtime.py)
  tools.py          the 21 agent tools
  runtimes/         base.py + python_rt/javascript/typescript/sql/shell/extra
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

> **Above this layer sits the Application Runtime** (`execution/application/`,
> ADR-H131, `docs/harness/application-runtime.md`): it discovers an application,
> installs dependencies, starts services (local, Docker, Compose), checks health,
> diagnoses and recovers it. It *uses* this layer's sandbox, diagnostic parsers and
> telemetry — it does not re-implement them.

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
the orchestrator does not change. Every argv an adapter returns BEGINS with an
absolute, resolved executable path (never a bare `npm`/`npx`/`tsc`, which Windows
cannot spawn); the JS/TS adapters also prepend the project's and the app's
`node_modules/.bin` to the scrubbed `PATH`, so `npm run build`, `tsc` and a local
test runner resolve WITHOUT a network install. Manifests are read tolerant of a
UTF-8 BOM. Shipped:

- **PythonRuntime** — vendored interpreter preferred, then `sys.executable`, then
  `python3/python/py`; `PYTHONPATH=<root>` so the project's own modules import;
  build = `compileall`; test = `pytest` (or `unittest` by policy).
- **JavaScriptRuntime** — `node`; inline code staged as `.mjs` (or `.cjs` when it
  uses `require`); test = declared framework, `npm test`, or `node --test`.
- **TypeScriptRuntime** — the project's declared strategy first (`project-local
  tsx`/`ts-node`, or a `start`/`dev` npm script), then the app's own bundled `tsx`
  (`<repo>/node_modules/.bin`, offline), then `npx tsx`/`ts-node`; build =
  the project's `build` script, then `tsc --noEmit` with the project's `tsconfig`.
- **SqlRuntime** — an embedded stdlib `sqlite3` runner; **read-only by default**;
  destructive statements are refused unless `read_only: false` (and the profile
  grants `code.write`). A script is split into statements (quote/comment aware) and
  executed in order; **writes are committed** so a later `SELECT` sees them (an
  earlier bug rolled them back). PostgreSQL needs an optional driver and refuses
  otherwise. A database file (`.db`/`.sqlite`) named explicitly is accepted via
  `resolve_within(..., allow_ignored=True)` — the index ignore-globs are relaxed for
  an operator-chosen file, never traversal/symlink/outside-root/protected.
- **ShellRuntime** — wraps the command with the EXISTING `terminal/runtimes.py`
  argv builder and runs it through the same sandbox. No second shell management.

`Java/Go/Rust/C/C++/C#/PHP/Ruby` each have a registered adapter. Inline execution
is supported where the language has a single-file mode (Go `go run`, Java's
single-file source mode, PHP, Ruby); Rust/C/C++/C# refuse inline honestly and run
from a project/file. `build`/`test` are wired for `go build`/`go test`,
`cargo build`/`cargo test`, Maven/Gradle, `dotnet build`/`dotnet test`,
`cmake`/`make`, PHPUnit and RSpec; for a bare C/C++ source with no build system,
`build` compiles the primary source into a runnable binary. Each adapter sets the
toolchain's own cache/home env (Go `GOCACHE`/`GOTMPDIR`; .NET `DOTNET_CLI_HOME`/
`NUGET_PACKAGES` plus a curated non-secret Windows platform env), because the
sandbox scrubs the environment. An adapter whose toolchain is absent reports
`UNAVAILABLE` — it never routes the source through a different interpreter.

## Databases

SQLite is stdlib. DuckDB and PostgreSQL run through optional PEP-249 drivers
(`duckdb`, `pg8000`/`psycopg`/`psycopg2`), installed by default via
`python/requirements.txt`; MySQL uses `pymysql`/`MySQLdb` when present. A missing
driver refuses with `SQL_DRIVER_MISSING`; a failed *connection* is
`SQL_CONNECT_FAILED` — never conflated.

## Resource telemetry

`execution/telemetry.py` measures real usage with no third-party dependency:
CPU time via `GetProcessTimes`/`/proc/<pid>/stat` and peak RSS via
`GetProcessMemoryInfo`/`/proc/<pid>/statm`, summed over the process tree. The
sandbox samples while a command runs (and once immediately after spawn) and
records the peak; the values reach `RawResult` → `ResourceUsage` → the
`ExecutionMetric` rows (`cpuMs`, `memoryPeakMb`, `processCount`). An unmeasurable
value is `None`, never `0`.

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
| `HARNESS_EXEC_AUTOFIX` | let `run_verification` ask the run's model for one confined fix | off |

PostgreSQL/MySQL/DuckDB connect through whichever PEP-249 driver is installed;
without one, the run refuses with `SQL_DRIVER_MISSING` (never a fake connection).

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
- **`SQL_DRIVER_MISSING`** — no PostgreSQL/MySQL/DuckDB driver is installed. This
  is a refusal, not a connection error; install the driver or use SQLite.

## OS resource limits

Every execution carries CPU/memory/process/wall-clock budgets. Wall-clock and
output caps are always enforced by the parent. Memory (peak RSS), cumulative CPU
time and process count are enforced by the parent monitor AND, where the OS
supports it, by the kernel itself: POSIX `setrlimit` (`RLIMIT_CPU`/`AS`/`NPROC`)
and Windows Job Object limits (`ProcessMemoryLimit`, `JobMemoryLimit`,
`ActiveProcessLimit`). A breach kills the whole tree and reports
`RESOURCE_LIMIT` with the breached limit named — including when the kernel
DENIES an operation at the limit (`MemoryError`, WinError 1816) rather than
letting the process climb past it. An unmeasurable value never causes a kill.

## Autonomous repair

`run_verification` runs the bounded build→test→fix→rebuild→retest loop. A fix step
is attached ONLY when `HARNESS_EXEC_AUTOFIX=1` AND the run carries model settings.
The fix (`autofix.py`) reads the first diagnostic's file, asks the run's own model
for ONE JSON edit (`{"file","old","new"}` or `{"file","content"}`), and applies it
through the filesystem service after `resolve_within` confinement. A
security/infrastructure failure is never autofixed; an unparseable or aborting
reply stops the loop instead of retrying forever.
