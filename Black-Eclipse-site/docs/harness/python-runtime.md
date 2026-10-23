---
title: Python Analysis Runtime (sandbox, recipes, persistent kernel)
status: Current
last-verified: 2026-10-22
---

# Python Analysis Runtime

**Who this is for:** anyone changing how `analysis_run` programs execute — the
sandbox gate, the recipe runner, or the persistent kernel that reuses a
conversation's worker across turns.

The code is authoritative for exact shapes: `python/harness/code/sandbox.py`
(process isolation), `python/harness/code/execution.py` (gate + one-shot
runner), `python/harness/code/kernel.py` (persistent kernel), `code/recipes.py`
(named recipes), `analysis_tools.py` (the agent tool).

## One runtime, two execution paths

Every analysis program passes the SAME pre-execution gate first:
`execution.prepare_analysis` validates the source digest, imports
(`IMPORT_ALLOWLIST` + named recipe widening), inputs, tool allowlist and package
lock, returning either a refused `AnalysisResult` or a prepared bundle. Only
then does execution continue:

| Path | When | Behavior |
|---|---|---|
| One-shot | kernel disabled, unavailable, or spawn failed | Spawn a fresh sandbox process, run the program, resolve tool requests by deterministic replay, return. Exactly the Phase 3 contract. |
| Kernel | ordinary chat turns (default) | Reuse one sandbox process per conversation across turns; commands move over JSON lines; tool requests still replay against a per-kernel stage directory. |

A kernel is never a live data pipe and never a second sandbox implementation:
it is the same prelude, the same `resolve_tool_request`, the same
`eclipse_tools` allowlist and bounds (ADR-H235), and the same provenance model.
Fetched payloads still stay inside the worker; only final outputs cross back.

## Keying and lifecycle

- `kernel_for_context(ctx)` derives the key: `session:<session_id>|agent:<id>`
  for an ordinary chat turn, `run:<run_id>|agent:<id>` for a delegated or
  session-less run. Different conversations never share a kernel, and a
  delegated subagent never joins its parent's kernel.
- `KernelPool`: default max 4 kernels, idle timeout 300 s, LRU eviction of
  non-busy kernels when the pool is full. Idle sweep runs on acquire/execute.
- A timeout or a dead process kills the whole tree, marks the kernel dead and
  returns `KERNEL_CRASHED`; the next turn spawns a fresh kernel.
- `reset_kernel_pool()` closes everything (tests, shutdown); an `atexit` hook
  does the same.

## Worker protocol

The stage directory holds `kernel_worker.py`, `command.json`, `response.json`,
`pending.json` and `output/`. Each command writes the program, then the worker
acknowledges with a JSON line `{id, command, response}`. The worker either:

- finishes with `status: ok`,
- asks for a read-only tool with `status: tool_request` and exits `75`, or
- fails with `status: error`.

The host resolves a pending tool request through the existing read-only
DataBridge, memoizes it under the raw argument key and replays the command; the
memoized reply is already in the stage, so the replay is deterministic. Globals
are fresh per command while the process (and its imports) persists, which is
the point of the kernel. `sys.modules["eclipse_tools"]` is rebuilt per command
so a program cannot smuggle a cached module.

## Bounds (unchanged from Phase 3 unless noted)

- Import allowlist + AST gate as before; `eclipse_tools` only through a host
  resolver.
- 8 distinct tool calls, 4 KiB of arguments per call, 16 KiB pending request
  read cap, 1 MB per result, 4 MB total memo.
- Command file cap 8 MB; worker result cap 2 MB; interactive stdout line cap
  1 MB (overflow kills the tree with `SandboxStreamError`).
- `RunSpec`: memory limit, process limit, `network=False`, no cumulative
  `cpu_seconds` (it would eventually kill a long-lived kernel); the wall-clock
  deadline per command is the real bound.

## Environment

| Variable | Default | Meaning |
|---|---|---|
| `ECLIPSE_ANALYSIS_KERNEL` | on | `0`/`false` forces the one-shot path. |
| `ECLIPSE_ANALYSIS_KERNEL_MAX` | 4 | Max live kernels per process. |
| `ECLIPSE_ANALYSIS_KERNEL_IDLE_S` | 300 | Idle seconds before a kernel is closed. |

Python genuinely unavailable still fails honestly: no kernel and no one-shot
means a refusal, never a simulated result.

### The interpreter the code actually runs in

The sandbox NEVER runs the harness's Python: it runs the **vendored**
interpreter (`scripts/vendor/python/python.exe`, resolved by
`code/commands.py::VENDORED_RELPATH`). Two consequences are now explicit:

- **The environment is pinned, not incidental.** The numerical stack the
  programs may import is pinned in `python/analysis-requirements.txt`
  (numpy, pandas, matplotlib) and installed INTO that interpreter by
  `scripts/setup-python.js` — which, on Windows, provisions the vendored
  interpreter FIRST (a system Python cannot serve the sandbox).
  `scripts/doctor.js` reports the stack's versions, so a stale or missing
  stack is visible instead of guessed.
- **The provenance digest describes the right environment.**
  `code/execution.py::package_lock_digest` hashes the INTERPRETER's installed
  distributions, not the harness process's: the harness's environment is not
  the environment the computation ran in, and a digest that describes it would
  be a false provenance claim.

A program that needs a package the interpreter does not have fails with its
own `ModuleNotFoundError` (returned to the model, so it can adapt) — never a
fabricated result.

### The runtime guard (round 4, W14)

The AST walk in `code/execution.py::check_imports` is a **first filter**, not
the enforcement point: a source check can be talked around. The enforcement
point is `code/sandbox_guard.py`, which is executed **inside the child** before
the program runs (both the one-shot runner and the persistent kernel):

| Guard | What it stops |
|---|---|
| a **guarded `__import__`** | only the allowlist (plus the stdlib support the allowed numerical stack needs internally) — an alias (`f = __import__`) buys nothing |
| a **safe `os` / `sys` / `importlib` / `builtins`** | `os.system`, `os.popen`, frame walking (`sys._getframe` → a proxy with no globals), `importlib.import_module`, and the real `exec`/`eval` (a safe pair re-applies the source rules to a dynamic string) |
| **denied privilege modules** | `subprocess`, `socket`, `ssl`, `ctypes`, `multiprocessing` — importable by a library, unusable by the program |
| an **audit hook** (`sys.addaudithook`) | a socket, another process, native code, and any file outside the program's own folder (writes) or its folder + the interpreter's tree (reads) |
| **confined readers/writers** | `numpy.fromfile` / `pandas.read_csv` / `to_csv` — a source check cannot see inside a library |

**Honest scope.** This is a *Python-level* confinement. The child still runs as
the host user, so the accurate statement is: **the program cannot reach the
network, another process, native code, or a file outside its own folder** — not
"the sandbox is an OS boundary". The OS bounds (memory, process count, wall
clock, tree kill) sit on top of it.

### The operator's switch, cancellation and telemetry

- **The operator decides.** `HARNESS_ANALYSIS_ENABLED=0` switches the surface
  off for the whole runtime. The per-run `analysisEnabled` flag is a *request*:
  it can no longer switch on what the operator switched off.
- **Cancellation is real.** The run's cancel event is mirrored into the sandbox's
  `threading.Event`, so a cancelled or timed-out analysis kills its process
  tree (a child never outlives its run) and the verdict says `CANCELLED`.
- **The telemetry is kept.** The backend's measured CPU time, peak RSS, process
  count, the breached limit name and the exit code ride the `AnalysisResult`
  and its blob — a memory kill is reported as a memory kill, not as a generic
  program error. The result file and each collected artifact are size-checked
  **before** they are read, so a program cannot make the host allocate without
  limit.

## Notebook cells (Phase 21)

A chat notebook cell is a **user-authored** program, not an agent analysis. It
runs through the SAME `analysis_run` and kernel, with two host-fixed additions:

- `routers/notebook.py` sets `extra_imports=("io", "matplotlib")` itself; a
  request body cannot widen the allowlist.
- `persist_namespace=True` reuses one worker globals dict across the
  conversation's cells. The kernel only keeps that dict when a command carries
  `persist`; `analysis_run` never sends it, so agent analyses still start clean.
- `POST /notebook/kernel/restart` drops the conversation's kernel (and therefore
  its variables) through the existing `reset_kernel_for_context`.
- Chart data reaches a cell as an input (`kind="json"`), never as source text.

The cell document itself (source, inputs, outputs, artifact metadata) is owned by
the chat side (`src/lib/chat/notebook-store.ts`), not by the runtime. A rerun
clears the cell's output directory first, so a stale picture is never collected
as if the current program made it.

## Recipes and generated capabilities

`recipes.run_recipe(name, inputs, kernel=...)` passes the kernel through; active
generated recipes register themselves in the same dynamic registry, so they get
kernel reuse automatically and their contract test still runs through the same
gate. Failed invocations keep recording `capability_failure` recurrences.

## Testing

`python/tests/test_analysis_kernel.py` covers pid reuse in one conversation,
isolation across conversations, tool replay across rounds, crash → respawn,
LRU eviction, idle sweep, spawn-failure fallback, network refusal, key
semantics and the disable flag; the one-shot suites
(`test_analysis_execution.py`, `test_analysis_sandbox_tools.py`,
`test_analysis_recipes.py`, `test_analysis_tool.py`) must stay green unchanged.
The `python/tests/test_size_budget.py` ratchet applies to `kernel.py` like any
other harness module.
