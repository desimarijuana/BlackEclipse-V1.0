---
title: Python Analysis Runtime (sandbox, recipes, persistent kernel)
status: Current
last-verified: 2026-10-19
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
