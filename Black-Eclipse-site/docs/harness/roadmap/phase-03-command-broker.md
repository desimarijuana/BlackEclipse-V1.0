---
title: "Phase 3 — Sandboxed Command Broker"
status: Done
phase: 3
depends_on: [2]
unlocks: [4]
last-verified: 2026-10-01
---

# Phase 3 — Sandboxed Command Broker

| | |
|---|---|
| **Depends on** | Phase 2 (isolated worktrees), Phase 0 (policy) |
| **Unlocks** | Phase 4 (verify-and-repair), Phase 8 (analysis sandbox) |
| **Estimated work** | 6–10 h of agent time — the largest single step in the roadmap |
| **Deliverable type** | command table + execution primitive + table + tool + events |
| **New ADRs** | ADR-H105 |
| **Prompt to copy** | [§11 below](#11-implementation-prompt-copy-this-to-opencode) |

## Contents

- [1. Goal](#1-goal)
- [2. Why this phase exists (the real gap)](#2-why-this-phase-exists-the-real-gap)
- [3. In scope](#3-in-scope)
- [4. Who can use it (the non-expert obligation)](#4-who-can-use-it-the-non-expert-obligation)
- [5. Non-goals (do not do these)](#5-non-goals-do-not-do-these)
- [6. Exact contracts to create](#6-exact-contracts-to-create)
  - [6.1 The command table — `python/harness/code/commands.py`](#61-the-command-table--pythonharnesscodecommandspy)
  - [6.2 The execution primitive — `python/harness/code/sandbox.py`](#62-the-execution-primitive--pythonharnesscodesandboxpy)
  - [6.3 The tool — `command_run` (in `code/tools.py`)](#63-the-tool--command_run-in-codetoolspy)
  - [6.4 Persistence — `HarnessCommandExecution` (in `agent-memory.db`)](#64-persistence--harnesscommandexecution-in-agent-memorydb)
  - [6.5 Dependency policy](#65-dependency-policy)
- [7. Work items (ordered)](#7-work-items-ordered)
- [8. Deliverables](#8-deliverables)
- [9. Acceptance gates](#9-acceptance-gates)
- [10. Definition of done](#10-definition-of-done)
- [11. Implementation prompt (copy this to OpenCode)](#11-implementation-prompt-copy-this-to-opencode)

## 1. Goal

Let Eclipse **run checks** — typecheck, lint, tests, build, read-only git — under
a policy engine, with every execution recorded as a fact the answer path can
trust.

**This phase has the strictest gates in the roadmap.** Phase 2 lets the agent
*change files* in a disposable worktree; Phase 3 lets it *execute code*. That is
the step where a mistake stops being a bad diff and becomes a bad side effect, so
the gates below are adversarial by design and every probe must be **blocked *and*
recorded**.

## 2. Why this phase exists (the real gap)

The harness today has **no way to execute anything**. Verified: across
`python/harness/*.py` and `python/harness/*/*.py` there is no `subprocess` call
outside the MCP client, no `exec`, no sandbox module. The only process the runtime
spawns is an MCP server, and that path is already the most hardened code in the
repo — which is the point: it shows the repo's own standard for spawning child
processes, and Phase 3 must meet it.

Three properties of the existing MCP child-process handling are the direct
precedents for this phase:

1. **argv arrays, no shell.** `mcp/config.py` takes `command` + `args` and launches
   with no shell, because a shell string is an injection surface.
2. **Only an explicit per-server env allowlist reaches the child** — *"never the
   Eclipse process environment, settings vault, model credentials or callback
   token"* (`docs/harness/architecture.md`). Phase 3 must not invent a weaker rule.
3. **Platform-appropriate reaping.** *"on POSIX a single stdlib-only supervisor
   (`mcp/orphan_supervisor.py`) reaps registered process groups on parent death via
   pipe EOF; on Windows the SDK's Job Object (`KILL_ON_JOB_CLOSE`) already does."*

And the honesty rule is already the repo's law, in the zero-config invariant:

> *"If Python is genuinely unavailable, agent runs must fail honestly (503
> "runtime unavailable") — never silently fall back to a fake agent."* — `AGENTS.md`

Phase 3 applies the same rule to isolation: **if no isolation primitive is
available, refuse.** Never execute unsandboxed.

## 3. In scope

1. A **command-class table** (`code/commands.py`) — argv templates, not a string
   matcher.
2. A bounded **execution primitive** (`code/sandbox.py`) — cwd pinning, scrubbed
   environment, timeouts, output caps, process-tree kill, network denial.
3. A `command_run` tool on the existing registry.
4. A `HarnessCommandExecution` table in `agent-memory.db` + `command.*` events.
5. A dependency-install class that is off by default and operator-grantable.
6. Adversarial tests for every escape vector.

## 4. Who can use it (the non-expert obligation)

Running commands is the most dangerous capability in the roadmap and also the one
most likely to *leak mechanism* at a user. An accountant asked Eclipse to "check my
numbers" must never be shown `argv`, `exit code 128`, `cwd`, a sandbox backend
name, or the word "allowlist". Rules for this phase:

1. **The user sees the finance job, never the command.** Surface wording names the
   outcome: *"Checking the numbers…"*, *"Running the checks on your report
   generator…"*. The class name, argv, backend and exit code live on the run row
   and in the trace, behind a "details" affordance — they are never the headline.
2. **A refusal is one plain sentence plus a next step.** A blocked command renders
   as: *"That command isn't one Eclipse is allowed to run. You can ask for a check
   (tests, types, lint) instead."* The machine code (`COMMAND_NOT_ALLOWLISTED`,
   `SANDBOX_UNAVAILABLE`, `PROTECTED_PATH`) stays on the event; a plain-language
   `recovery` line accompanies it, mirroring the MCP diagnostics pattern where
   every diagnostic carries a recovery step.
3. **`SANDBOX_UNAVAILABLE` must be explainable to a non-expert.** Its plain form is
   *"I can't run checks safely on this computer right now, so I won't run them"* —
   not a silent failure and not an unsandboxed fallback. Honesty is the same rule
   as `UNAVAILABLE` market data.
4. **Every new user-facing string is an i18n key** in `src/lib/i18n/`
   (`dictionaries/en.ts` canonical, `dictionaries/index.ts` translations,
   `translate.ts` lookup, `use-t.ts` hook) — never a hardcoded component string.
5. **The plain-language gate** (§9 G7) asserts no new user-facing string or i18n key
   contains a mechanism word from `policy.PLAIN_LANGUAGE_DENYLIST`.

## 5. Non-goals (do not do these)

- **No shell.** No `bash -c`, no `cmd /c`, no `sh -c`, no string interpolation of
  args. Not even "just for the allowlisted commands".
- No arbitrary executable. The executable list is closed and small.
- No deployment, no publishing, no network by default.
- No touching the operator's checkout, `jdds.db`, the settings vault, or any
  credential.
- No `git.write` (stage/commit) — that is Phase 5, behind a single-use approval.
- No new dependency in the runtime.
- Do not commit, push, or open a PR.

## 6. Exact contracts to create

### 6.1 The command table — `python/harness/code/commands.py`

A table, deliberately. The model supplies **a class plus typed args**; it never
supplies an argv.

```python
"""The command-class table — the ONLY place a command is defined.

A command class names an intent (typecheck this worktree), not a program. The
argv is assembled here from a fixed template plus validated arguments. The model
never supplies an executable, a flag, or a shell fragment.

Why a table and not a matcher: a matcher over user-supplied strings is a policy
surface that grows with every new string. A table is closed, reviewable, diffable
in code review, and its size is the size of the capability.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional, Sequence

@dataclass(frozen=True)
class ArgSpec:
    name: str
    # A closed set of allowed values, or None for a pattern-validated string.
    allowed: tuple[str, ...] = ()
    pattern: Optional[str] = None          # re.fullmatch, applied in code
    required: bool = False

@dataclass(frozen=True)
class CommandClass:
    name: str                              # must be in policy.COMMAND_CLASSES
    executable: str                        # a key into EXECUTABLES below
    argv_template: Callable[[dict], list[str]]
    args: tuple[ArgSpec, ...] = ()
    timeout_s: int = 300
    output_cap_bytes: int = 2_000_000
    network: bool = False
    cwd: str = "workspace"                 # always the worktree root
    effect: str = "read"                   # "read" | "write" | "external_action"

# The closed executable list. Resolved to absolute paths at import time; a missing
# executable makes its classes UNAVAILABLE, never silently substituted.
EXECUTABLES: dict[str, str] = {
    "node": "node",
    "npm": "npm",
    "npx": "npx",
    # The VENDORED interpreter — the repo's own rule: the bare `python` shim lacks
    # langgraph/pytest. Never `python` from PATH.
    "python": "scripts/vendor/python/python.exe",
    "pytest": "scripts/vendor/python/python.exe",   # invoked as: python -m pytest
    "git": "git",
}

COMMAND_CLASSES: dict[str, CommandClass] = {
    "typecheck": CommandClass(
        name="typecheck", executable="npx",
        argv_template=lambda a: ["npx", "tsc", "--noEmit"],
        timeout_s=300,
    ),
    "lint": CommandClass(
        name="lint", executable="npx",
        argv_template=lambda a: ["npx", "eslint", "."],
        timeout_s=300,
    ),
    "unit_test": CommandClass(
        name="unit_test", executable="npm",
        argv_template=lambda a: ["npm", "run", "test", "--", *a.get("files", [])],
        args=(ArgSpec(name="files", pattern=r"[\w./\\-]{1,200}", required=False),),
        timeout_s=600,
    ),
    "python_test": CommandClass(
        name="python_test", executable="pytest",
        argv_template=lambda a: [
            "scripts/vendor/python/python.exe", "-m", "pytest",
            *a.get("paths", []), "-q",
        ],
        args=(ArgSpec(name="paths", pattern=r"[\w./\\-]{1,200}", required=False),),
        timeout_s=900,
    ),
    "build": CommandClass(
        name="build", executable="npm",
        argv_template=lambda a: ["npm", "run", "build"],
        timeout_s=900,
    ),
    "format_check": CommandClass(
        name="format_check", executable="npx",
        argv_template=lambda a: ["npx", "prettier", "--check", *a.get("files", [])],
        args=(ArgSpec(name="files", pattern=r"[\w./\\-]{1,200}", required=False),),
        timeout_s=120,
    ),
    "git_read": CommandClass(
        name="git_read", executable="git",
        argv_template=lambda a: ["git", a["subcommand"], *a.get("extra", [])],
        args=(
            # CLOSED set: no `config`, no `remote`, no `push`, no `reset`.
            ArgSpec(name="subcommand", required=True,
                    allowed=("status", "log", "diff", "show", "ls-files", "rev-parse", "worktree")),
            ArgSpec(name="extra", pattern=r"[\w./\\^~:@{}[\\]-]{1,200}", required=False),
        ),
        timeout_s=60,
    ),
    # OFF by default. Requires an operator grant AND records the resolved lock digest.
    "dependency_install": CommandClass(
        name="dependency_install", executable="npm",
        argv_template=lambda a: ["npm", "install", "--no-save", "--ignore-scripts", *a["packages"]],
        args=(ArgSpec(name="packages", pattern=r"[@\w./\\-]{1,200}", required=True),),
        timeout_s=600,
        network=True,
        effect="external_action",
    ),
}

class CommandUnavailable(RuntimeError):
    """Raised when a class's executable is not present. Never silently substituted."""

def resolve_class(name: str) -> CommandClass:
    """Return the class, or raise CommandUnavailable with the missing executable."""
```

**Rules the table encodes, and a reviewer must check:**

- `--ignore-scripts` on the install class. A postinstall script is arbitrary code;
  the sandbox's whole point is that the agent's commands are known.
- `git_read.subcommand` is a closed allowlist. `push`, `reset`, `clean`,
  `checkout`, `commit`, `config` are **absent by construction**, so they cannot be
  reached by any argument.
- The vendored interpreter is named in exactly one place. Nothing resolves
  `python` from `PATH`.
- Every `argv_template` is a pure function of validated args; no `f-string` ever
  builds a command from raw model output without a regex check first.

### 6.2 The execution primitive — `python/harness/code/sandbox.py`

```python
"""One bounded execution primitive. Everything that runs, runs through here.

There is no second execution path in the harness. `mcp/client.py` owns MCP
subprocesses; this owns the code capability's commands. Both follow the same
rules: argv arrays with no shell, an explicitly constructed environment, a
bounded lifetime, and a hard cap on what comes back.
"""

@dataclass(frozen=True)
class SandboxBackend:
    name: str                  # "windows-job" | "posix-rlimit" | ...
    guarantees: tuple[str, ...]  # e.g. ("process_tree_kill", "env_scrub", "output_cap")
    def run(self, spec: RunSpec) -> RawResult: ...

@dataclass(frozen=True)
class RunSpec:
    argv: list[str]                 # already resolved + validated
    cwd: Path                       # the worktree root — never the operator checkout
    env: dict[str, str]             # built from policy.SECRET_ENV_ALLOWLIST ONLY
    timeout_s: int
    output_cap_bytes: int
    network: bool

def build_env(policy, extra: dict[str, str] | None = None) -> dict[str, str]:
    """ONLY policy.SECRET_ENV_ALLOWLIST keys are copied from the parent.

    Never os.environ passthrough. Never the settings vault. Never the callback
    token (HARNESS_* secrets are absent by construction, so a command that tries
    to read CRON_SECRET / HARNESS_CALLBACK_TOKEN finds nothing to read).
    """
    env = {k: os.environ[k] for k in policy.SECRET_ENV_ALLOWLIST if k in os.environ}
    env["PYTHONIOENCODING"] = "utf-8"      # the repo's own Windows lesson
    return env

def select_backend() -> SandboxBackend:
    """Prefer OS-level isolation; report exactly what was chosen.

    Windows: Job Objects with KILL_ON_JOB_CLOSE (the pattern mcp/client.py already
    relies on via the SDK). POSIX: resource limits + a process group.
    If neither is available: raise SandboxUnavailable. There is no 'unbounded'
    fallback — see §2 and AGENTS.md's honest-failure rule.
    """
```

**Non-negotiable behaviours:**

| Behaviour | Rule |
|---|---|
| cwd | The resolved worktree root, `realpath`-checked against the binding. Never the repo root, never the operator's checkout. |
| shell | `shell=False` always. argv is a list. |
| environment | Constructed from the allowlist. `HARNESS_*`, `CRON_SECRET`, provider keys, vault values are **absent**, not blanked. |
| timeout | Wall clock, and on expiry the **whole process tree** is killed. Assert no orphan in the test. |
| output | Capped at `min(class.output_cap_bytes, policy ceiling)`. Truncation is honest: `truncated: true` + `totalChars`. |
| network | Denied unless the class sets `network=True` **and** the actor holds `command.execute` for an `external_action` class. |
| cancellation | A run cancellation propagates and kills the tree; no retry. |
| missing backend | `SANDBOX_UNAVAILABLE` refusal — the command does not run. |

### 6.3 The tool — `command_run` (in `code/tools.py`)

```python
class CommandRunInput(BaseModel):
    command_class: Literal["typecheck", "lint", "unit_test", "python_test",
                           "build", "format_check", "git_read",
                           "dependency_install"]
    args: dict[str, object] = {}
    note: str = Field("", max_length=200)     # why the agent wants this; goes in the trace
```

`ToolDefinition` fields: `name="command_run"`, `read_only=False` (it executes),
`required_permissions=("command.execute",)`, `timeout_ms` derived from the class,
`risk="medium"`. It refuses when the actor's autonomy profile does not grant
`command.execute` (`plan_only`), when the class is unlisted, when the executable is
missing (`CommandUnavailable` → a structured error, not a crash), or when the
backend is unavailable (`SANDBOX_UNAVAILABLE`).

The returned `ToolResult.data` carries the structured record; the model-facing
text carries the bounded output plus an explicit line naming the class, exit code,
duration, and truncation state.

### 6.4 Persistence — `HarnessCommandExecution` (in `agent-memory.db`)

Added additively and idempotently in `python/harness/persistence.py` — the same
pattern every other table in that file uses (`_migrate()` adds post-release columns
on open). **Never** in `eclipse-memory.db`, **never** in `jdds.db`.

```sql
CREATE TABLE IF NOT EXISTS HarnessCommandExecution (
  id            TEXT PRIMARY KEY,
  runId         TEXT NOT NULL,
  stepIndex     INTEGER,
  toolCallId    TEXT,
  commandClass  TEXT NOT NULL,
  argv          TEXT NOT NULL,      -- JSON array; secrets are absent, not masked
  cwd           TEXT NOT NULL,
  exitCode      INTEGER,            -- NULL when killed/timed out
  durationMs    INTEGER NOT NULL,
  timedOut      INTEGER NOT NULL DEFAULT 0,
  output        TEXT NOT NULL,      -- bounded
  truncated     INTEGER NOT NULL DEFAULT 0,
  totalChars    INTEGER NOT NULL,
  sandboxBackend TEXT NOT NULL,
  network       INTEGER NOT NULL DEFAULT 0,
  policyDecision TEXT NOT NULL,     -- JSON: {allowed, code, reason}
  createdAt     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_cmd_run ON HarnessCommandExecution(runId, createdAt);
```

`stepIndex` / `toolCallId` exist so the row composes with the in-flight
`run_lineage.py` `ToolExecutionIdempotency` mechanism — a resumed run reuses a
recorded command result instead of re-executing it.

Events on the existing `RunEmitter`: `command.started`, `command.completed`,
`command.refused` (with the policy code), `command.truncated`, `command.killed`.

### 6.5 Dependency policy

- `dependency_install` is **off by default** and is the only class with
  `network=True`.
- It requires the actor to hold `command.execute` **and** the class to be enabled
  by an operator (a policy flag, default false).
- The resolved lockfile digest is recorded on the row, so a later phase can prove
  what was installed.
- The repo's standing rule still governs the agent's *behaviour*: *"Do not add
  dependencies without justification; prefer the lighter option"* (`AGENTS.md`).
  The tool's default answer is no.

## 7. Work items (ordered)

1. `docs/harness/roadmap/progress/phase-03-progress.md` with §9's probes as
   unchecked boxes.
2. `code/commands.py` (§6.1), including `CommandUnavailable` and the CLOSED
   `git_read` subcommand set.
3. `code/sandbox.py` (§6.2) — `RunSpec`, `build_env`, `select_backend`, the
   Windows Job Object backend, the POSIX backend, and the
   `SandboxUnavailable` refusal path.
4. Register `command_run` in `code/tools.py`'s `register_code_tools`; wire
   `service.py` if not already wired by Phase 1.
5. `persistence.py`: the table + `record_command_execution` /
   `list_command_executions(run_id)`. Keep `persistence.py` under its ratchet — if
   it is at the limit, put the read/write helpers in `code/store.py` bound to the
   single `AgentMemoryStore` connection, exactly as `run_lineage.py` documents
   doing for its own tables.
6. Events in the graph's tool-execution path (extracted helper, not inline in
   `graph.py`).
7. Tests `python/tests/test_code_commands.py` and
   `python/tests/test_code_sandbox.py`, one test per probe in §9, each asserting
   **both** the refusal and the recorded row/event.
8. ADR-H105.
9. `docs/CHANGELOG.md` + `docs/NAVIGATION.md`.

## 8. Deliverables

| File | Change |
|---|---|
| `python/harness/code/commands.py` | new — the command-class table |
| `python/harness/code/sandbox.py` | new — the one execution primitive |
| `python/harness/code/tools.py` | add `command_run` |
| `python/harness/code/store.py` | new (if needed for the ratchet) — command-execution rows |
| `python/harness/persistence.py` | additive idempotent DDL for `HarnessCommandExecution` |
| `python/tests/test_code_commands.py`, `test_code_sandbox.py` | new — §9 as tests |
| `python/tests/fixtures/code/*` | new — the malicious/benign fixture programs |
| `docs/harness/decisions.md` | ADR-H105 |
| `docs/harness/roadmap/progress/phase-03-progress.md` | new — raw probe output |

## 9. Acceptance gates

Every probe must be **blocked *and* recorded**. A probe that is blocked but leaves
no row and no event is a **fail** — the point is auditability, not just safety.

```bash
# G1 — the suite, with the new tests
npm run test

# G2 — the probe suite, verbose so every refusal is visible
./scripts/vendor/python/python.exe -m pytest python/tests/test_code_sandbox.py python/tests/test_code_commands.py -v

# G3 — benign executions really work (exit code must match reality)
./scripts/vendor/python/python.exe -m pytest python/tests/test_code_commands.py -k benign -q

# G4 — no orphan processes after the kill probes
#     Windows: count our python processes before/after; expect the same number.
tasklist //FI "IMAGENAME eq python.exe" | wc -l

# G6 — the operator's checkout and the vault are untouched by every probe
git status --short          # jdds.db must NOT appear; no new untracked artifact

# G7 — plain language: no new user-facing string leaks mechanism vocabulary
npx vitest run src/lib/i18n/plain-language.test.ts
./scripts/vendor/python/python.exe -m pytest python/tests/test_plain_language.py -q
# asserts every new string/key and every command refusal reason against
# policy.PLAIN_LANGUAGE_DENYLIST, and that each refusal carries a recovery line

# G8 — the release gate
npm run check:all
```

| Probe | Expected | Recorded as |
|---|---|---|
| `typecheck` / `lint` / `python_test` on a clean fixture | pass, exit code matches | `command.completed`, row with `exitCode: 0` |
| a fixture whose check genuinely fails | exit code ≠ 0, output captured | `command.completed`, row with the real code |
| infinite-loop fixture | killed, `timedOut: true`, **no orphan** | `command.killed` event |
| 50 MB stdout | `truncated: true`, `totalChars` reported | `command.truncated` |
| `rm -rf /`, `curl http://…`, `powershell -c …`, bare `bash -c` | refused, never executed | `command.refused`, row with the policy code |
| a command writing outside the worktree | contained or refused | `command.refused` |
| a network fetch attempt | fails by default | `command.refused` or a failed exit code, row present |
| a fixture echoing `CRON_SECRET` / `HARNESS_*` | nothing to echo (absent) | row's `argv`/`env` shows no secret |
| `git_read` with `subcommand: "push"` | refused (not in the closed set) | `command.refused` |
| `dependency_install` without the operator flag | refused | `command.refused` |
| `command_run` under `plan_only` | refused (no `command.execute`) | `command.refused` |
| `command_run` with no sandbox backend available | `SANDBOX_UNAVAILABLE`, **not executed** | `command.refused` with that code |

**Pass criteria.** Every probe above behaves as stated; `git status --short` shows
no `*.db` change and no unexpected artifact; process count is unchanged after the
kill probes; the full suite and `check:all` are green.

## 10. Definition of done

- Every probe run, raw output pasted, and **each refusal traceable to a row and an
  event**.
- `git_read`'s subcommand set provably excludes every mutating verb.
- No code path constructs a command from unvalidated model text (`grep` for
  `shell=True` and for `f"git {` style interpolation → zero hits).
- The vendored interpreter is referenced in exactly one module.
- ADR-H105 written; CHANGELOG + NAVIGATION updated; `status:` flipped.

## 11. Implementation prompt (copy this to OpenCode)

```text
Task: Phase 3 — Sandboxed command broker (Eclipse-as-a-Harness roadmap).

Read first, in full:
- docs/harness/roadmap/phase-03-command-broker.md  (this phase, verbatim)
- docs/harness/roadmap/README.md  (invariants §3, work in flight §5)
- docs/harness/roadmap/phase-00-policy-and-baseline.md (§6.3 — the policy module you obey)
- docs/harness/roadmap/phase-02-worktree-patching.md (the workspace you run inside)
- python/harness/mcp/config.py and python/harness/mcp/client.py  ← the repo's own
  standard for spawning a child process. MATCH IT: argv arrays with no shell, an
  explicit per-child env allowlist, bounded lifetime, platform-appropriate reaping.
- python/harness/tools.py (ToolRegistry/ToolDefinition/ToolContext/ToolResult)

Goal: let the agent run allowlisted checks inside the Phase-2 worktree, under a
policy engine, with every execution recorded as a fact. This phase has the
STRICTEST gates in the roadmap — treat every probe below as a required test.

In scope:
1. python/harness/code/commands.py — the command-class TABLE per §6.1. A closed
   EXECUTABLES map (npm, npx, node, the VENDORED scripts/vendor/python/python.exe,
   pytest via -m, and git), one CommandClass per class in policy.COMMAND_CLASSES,
   ArgSpec validation with re.fullmatch, and CommandUnavailable when an executable
   is absent. git_read.subcommand is a CLOSED allowlist containing only status,
   log, diff, show, ls-files, rev-parse, worktree — push/reset/clean/checkout/
   commit/config must be UNREACHABLE. dependency_install is off by default, uses
   --ignore-scripts, and is the only class with network=True.
2. python/harness/code/sandbox.py — RunSpec, build_env (ONLY
   policy.SECRET_ENV_ALLOWLIST, never os.environ passthrough, PYTHONIOENCODING=utf-8),
   select_backend (Windows Job Object KILL_ON_JOB_CLOSE as mcp/client.py does;
   POSIX resource limits + process group), run() with cwd pinned to the resolved
   worktree root, shell=False, wall-clock timeout, process-TREE kill,
   output byte cap with honest truncated/totalChars, network denied by default,
   cancellation propagation with no retry. If no isolation primitive is available,
   raise SandboxUnavailable and REFUSE — never execute unsandboxed. Same honesty
   rule as the 503 "runtime unavailable" contract in AGENTS.md.
3. command_run tool in python/harness/code/tools.py per §6.3
   (read_only=False, required_permissions=("command.execute",), refusal when the
   autonomy profile does not grant it, structured errors for unlisted class /
   missing executable / unavailable sandbox).
4. Persistence per §6.4: HarnessCommandExecution in agent-memory.db, additive and
   idempotent, plus record/list helpers. Keep persistence.py under its size ratchet
   — if it is at the limit, put the helpers in a new python/harness/code/store.py
   bound to the single AgentMemoryStore connection, exactly as run_lineage.py does.
   NEVER eclipse-memory.db. NEVER jdds.db.
5. Events on the existing RunEmitter: command.started / completed / refused /
   truncated / killed. Extract the emission helper rather than growing graph.py.
6. Tests test_code_commands.py + test_code_sandbox.py, one per probe in §9, each
   asserting BOTH the behaviour AND the recorded row/event. Add the malicious and
   benign fixture programs under python/tests/fixtures/code/.
7. ADR-H105 in docs/harness/decisions.md (Decision / Why / Consequences shape; the series
   currently ends at ADR-H92).
8. docs/CHANGELOG.md dated entry + docs/NAVIGATION.md rows for code/commands.py and
   code/sandbox.py.

Non-goals (do NOT do these):
- NO shell. No bash -c / cmd /c / sh -c / shell=True. No argv built from raw model
  text without a regex validation step.
- No arbitrary executable beyond the closed EXECUTABLES map.
- No network by default; no deployment; no publishing.
- No git.write (stage/commit) — Phase 5.
- No touching jdds.db, the settings vault, .env, mcp-servers.json, or any credential.
- No new runtime dependency.
- Never commit, push, or open a PR. Do not commit jdds.db.

Constraints:
- One runtime: command_run registers on the existing ToolRegistry and is driven by
  the existing execute_run graph. No second loop/registry/adapter.
- Policy in code only. Prose is never a security boundary.
- New logic goes in new modules; keep graph.py/persistence.py/main.py under their
  ratchets.

Acceptance gates — run each and paste the RAW output into
docs/harness/roadmap/progress/phase-03-progress.md. A probe that is blocked but
leaves no row and no event is a FAILURE, not a pass:
  npm run test
  ./scripts/vendor/python/python.exe -m pytest python/tests/test_code_sandbox.py python/tests/test_code_commands.py -v
  ./scripts/vendor/python/python.exe -m pytest python/tests/test_code_commands.py -k benign -q
  tasklist //FI "IMAGENAME eq python.exe" | wc -l        (unchanged after the kill probes)
  git status --short                                     (jdds.db must NOT appear)
  npm run check:all
Probes that must all be blocked AND recorded: infinite loop killed with no orphan;
50MB stdout capped with truncated+totalChars; rm -rf / curl powershell bash -c
refused; a write outside the worktree contained; a network fetch failing by
default; a fixture echoing CRON_SECRET finding nothing; git_read push refused;
dependency_install refused without the operator flag; command_run refused under
plan_only; SANDBOX_UNAVAILABLE refusing rather than executing unsandboxed.

Finish by stating: "docs updated: <files>" or "no doc change — <reason>".
```

---

**Next:** [Phase 4 — Verify-and-repair loop](./phase-04-verify-and-repair.md)
