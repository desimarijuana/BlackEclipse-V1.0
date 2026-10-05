---
title: Terminal, Shell & Process Subsystem
status: Current
last-verified: 2026-10-05
---

# Terminal, Shell & Process Subsystem

**Who this is for:** anyone changing how Eclipse executes commands, keeps a shell
open, manages background processes, detects ports, or exposes any of that to the
agent or the UI.

This is the **execution backbone**. It is not a terminal widget: the agent tools
and the terminal UI are two thin adapters over one shared runtime, so they can
never disagree about whether a process is running.

## The one sentence

> A command is classified before it runs; a process's state is owned by the
> runtime, never the UI; and an unimplemented capability refuses honestly rather
> than pretending.

## Layering

```
python/harness/terminal/
  manager.py         TerminalManager  — the ONE facade (tools + router call it)
  session.py         persistent shells (cwd/env/stdin/dimensions/Ctrl+C)
  process_manager.py background processes, trees, signals, crash detection, restart
  spawn.py           per-process isolation (Windows Job Object / POSIX group)
  proctree.py        OS parent map (tasklist equivalent) for real trees + port ownership
  buffer.py          RingBuffer (sequenced, bounded) + head/tail model truncation
  port_manager.py    listening ports + conflicts (OS table, never a hard-coded list)
  shell_detect.py    shells / WSL / capabilities
  runtimes.py        Local, WSL (real); Docker, SSH (honest NOT_IMPLEMENTED)
  redaction.py       secrets never reach the model/log
  store.py           TerminalSession / ProcessRecord / TerminalCommand rows
  recovery.py        reconcile persisted state on boot
  runtime.py         the process-wide singleton + EventBus bridge
  tools.py           the agent tool surface + effect authorizer
python/harness/routers/terminal.py    the operator-gated HTTP surface
```

The agent reaches it through the ONE `ToolRegistry`; the UI through
`/api/terminal/**` → `routers/terminal.py` → the same `TerminalManager`. There is no
second execution path.

## Two primitives, deliberately

* **`execute_command`** — one-shot, bounded, cancellable. Runs through
  `code/sandbox.py` (unchanged), so the wall-clock/output/process-tree bounds and
  the scrubbed environment apply. It blocks only its own worker, never the agent
  loop (handlers call it via `asyncio.to_thread`).
* **`start_process`** — a long-running process the runtime keeps alive and
  monitors. It has NO ordinary execution timeout; only an explicit stop/kill, a
  crash, or a `timeoutMs` the caller chose ends it.

`open_shell` + `run_shell_command` are the third shape: a **persistent shell** whose
`cd` and `export` survive across commands. A real PTY is used when a PTY library
(`pywinpty`/`ptyprocess`) is installed; otherwise a piped persistent shell is used
and `capabilities.pty` reports `false` — the fallback is never called a PTY.

## Process lifecycle

`CREATED → STARTING → RUNNING → {STOPPING →} {STOPPED|EXITED|CRASHED|KILLED|TIMEOUT|FAILED}`.
State is applied once, under a lock, by the monitor thread that reaps the real OS
exit — never inferred from "does a PID exist". A non-zero exit becomes `CRASHED`
with a `CommandError` (`category: PROCESS_CRASH`, or `COMMAND_NOT_FOUND` for
`127`/`9009`) and the last output tail.

Output is pumped per stream into **separate** `RingBuffer`s, so stdout and stderr
are never silently merged. Every line carries a monotonic `sequence`; an agent
polls `read_process_output(cursor=…)` and never sees a line twice.

## Ports

`port_manager` reads the OS listening table (`netstat -ano` / `ss -ltnp`). A
process's ports are collected over its **whole OS tree**, because a shell wrapper
does not itself listen — the dev server it launched does. A conflict reports the
owner pid/process; the runtime never kills an unrelated process.

## Security

Enforced at three layers, matching the existing code capability:

1. **Allowlist** — `code/policy.py` removes every terminal *write* tool at
   `plan_only`, so the autonomy boundary is structural, not a prompt (`allowed_tools`
   now includes `WRITE_TOOLS` + `EXTERNAL_ACTION_TOOLS` + `TERMINAL_WRITE_TOOLS`).
2. **Effect authorizer** — `terminal/tools.py::make_terminal_tool_authorizer` is
   composed into the graph's chain. An `allow` command runs; an `ask` command
   requires a single-use, workspace-bound approval; a `deny` is refused.
3. **Handler** — the executing handlers re-classify (defense in depth) and confine
   `cwd` to the workspace root.

Secrets are redacted on every model-facing and logged path (`redaction.redact`),
reusing `session_index.redact_span`. The environment is the scrubbed
`sandbox.build_env` (never `os.environ` passthrough).

## Persistence & recovery

`store.py` owns three additive tables on the ONE `agent-memory.db`
connection: `TerminalSession`, `ProcessRecord`, `TerminalCommand`. No process
output is stored relationally; only the metadata and cursors needed to recover.

On boot `service.start_terminal()` runs `RecoveryManager.reconcile()`: a persisted
process whose pid is gone is marked `EXITED`; one whose pid still exists is marked
`UNKNOWN` (owned but no longer managed) — never `RUNNING`. Persisted sessions are
closed. Nothing is fabricated and nothing is silently adopted.

## Events

`TerminalManager` publishes onto the shared `EventBus` as `terminal.*`
(`terminal.session.created`, `terminal.process.started`, `terminal.process.output`,
`terminal.process.crashed`, `terminal.port.*`, …), carrying `runId` when known so a
run's SSE consumer sees them.

## Adding a runtime

Implement the `ExecutionRuntime` protocol in `runtimes.py` (`available`,
`describe`, `build_argv`, `map_path`) and add a branch to `select_runtime`. An
unavailable runtime MUST raise `RuntimeUnavailable`; `select_runtime` never
degrades. Docker and SSH are declared this way and currently refuse with
`NOT_IMPLEMENTED`.

## Why the shell tool still exists

`terminal_run`/`shell_run`/`shell_spawn` predate this subsystem and remain for
backward compatibility. The new `terminal/*` tools are the general surface; both
share the same classifier (`code/shell_tools.py::_verdict`) and approval model.

## Tests

`python/tests/test_terminal_*.py` — buffer, shell/runtimes/ports, process
lifecycle, sessions, store/recovery, tools-through-the-registry, HTTP router, and
`test_terminal_e2e.py` (create → serve → detect port → health-check → modify →
restart → verify → stop → confirm the port is released).
