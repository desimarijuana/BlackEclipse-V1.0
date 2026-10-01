---
title: "Phase 1 — Repository Navigator (Read-Only)"
status: Not started
phase: 1
depends_on: [0]
unlocks: [2]
last-verified: 2026-09-30
---

# Phase 1 — Repository Navigator (Read-Only)

| | |
|---|---|
| **Depends on** | Phase 0 (the policy authority in `code/policy.py`) |
| **Unlocks** | Phase 2 (isolated worktree patch authoring) |
| **Estimated work** | 4–7 h of agent time, zero write capability, zero execution |
| **Deliverable type** | 5 read-only tools on the existing registry + workspace confinement + one agent preset + one optional request field + 1 ADR |
| **New ADRs** | ADR-H103 |
| **Prompt to copy** | [§11 below](#11-implementation-prompt-copy-this-to-opencode) |

## Contents

- [1. Goal](#1-goal)
- [2. Why this phase exists (the gap in the real code)](#2-why-this-phase-exists-the-gap-in-the-real-code)
- [3. In scope](#3-in-scope)
- [4. Who can use it (the non-expert obligation)](#4-who-can-use-it-the-non-expert-obligation)
- [5. Non-goals (do not do these)](#5-non-goals-do-not-do-these)
- [6. Exact contracts to create](#6-exact-contracts-to-create)
  - [6.1 Workspace resolution and confinement (workspace.py)](#61-workspace-resolution-and-confinement-workspacepy)
  - [6.2 The five tools (tools.py)](#62-the-five-tools-toolspy)
  - [6.3 Events on the existing emitter](#63-events-on-the-existing-emitter)
  - [6.4 The request field and the agent preset](#64-the-request-field-and-the-agent-preset)
- [7. Work items (ordered)](#7-work-items-ordered)
- [8. Deliverables](#8-deliverables)
- [9. Acceptance gates](#9-acceptance-gates)
- [10. Definition of done](#10-definition-of-done)
- [11. Implementation prompt (copy this to OpenCode)](#11-implementation-prompt-copy-this-to-opencode)

## 1. Goal

Give Eclipse **eyes**: it can see the repository it lives in — list it, search it,
read a file with line numbers, and find the answer in `docs/**` — and it can do
*nothing else* with it.

Phase 1 opens the first of the four structural gaps in the roadmap README (*"No
code capability at all. Every 'build me X' ends at prose about X."*) by exactly
one half: the read half. There is no write tool, no patch tool, no command, no
sandbox, no execution of any kind. Maps to `agentic-plan-implementaion.md` §15.3
gate **7A**.

## 2. Why this phase exists (the gap in the real code)

The runtime's system prompt currently admits the gap out loud, in
`python/harness/prompts.py`:

> *"If you find yourself wanting a tool that is not listed here — a shell, a file
> reader, a general web search — it does not exist in this environment: say so
> plainly and use the closest available tool instead of pretending."*

That sentence is correct today. The read tools do not exist. The agent's
allowlist in `python/harness/agents.py` is the financial surface and the
memory/skill-read surface, and nothing else:

```python
ECLIPSE_AGENT = AgentConfig(
    id="eclipse-agent",
    tools=[
        "market_get_quote", "market_get_ohlcv", ... ,
        "get_capability_matrix", "get_research_health",
        "memory", "skill_list", "skill_view", "skill_invoke",
        "session_search", "session_open",
        "memory_search_native", "memory_search_external", "memory_provider_status",
    ],
)
```

All 18 tools are read-only (README §1). The registration site is explicit about
one registry, in `python/harness/service.py`:

```python
register_finance_tools(self.registry)
register_retrieval_tools(self.registry)
register_memory_tools(self.registry)
```

Phase 1 adds one more line to that block — `register_code_tools(self.registry)` —
and nothing else about the runtime changes.

**Why read-only is a whole phase, not a warm-up.** The registry in
`python/harness/tools.py` already encodes the rule that separates a write tool
from a read tool:

```python
if tool.permission != "read":
    # A non-read tool is refused unless the run explicitly authorizes THIS call
    # (bound to the server/tool/arguments). No authorizer ⇒ refused.
    ...
    if not approved:
        return self._failure(call_id, name, "TOOL_FORBIDDEN", ...)
```

A tool declared `permission="read"` needs no approval; any other declaration is
refused until Phase 2 supplies a workspace-scoped authorizer and Phase 5 supplies
operator approvals. So Phase 1 ships **only** the kind of tool that cannot need an
approval, and the whole phase is auditable by one property: *no file content is
ever modified, and no process is spawned except one fixed, argument-free `git`
read probe* (§6.1).

**Confinement and redaction must be reused, not re-invented.** Phase 0 already
built the one place traversal is stopped — `code/policy.py`'s
`resolve_within(root, candidate)`, whose contract is *"Reject if the result is not
`root` itself or under `root` (prefix compare on **resolved** paths, never on the
raw string). Reject if any path component is a symlink pointing outside the
root."* Phase 1 calls it; it never re-implements it. Likewise the secret-pattern
set already lives in exactly one place and is already reused rather than
duplicated — `python/harness/session_index.py` opens with *"Reuse the ONE privacy
pattern set rather than inventing a second one"* and imports `looks_like_secret`
from `eclipse_memory/decision.py`. A file reader that can print `.env`-shaped
lines is a new leak path, so its redaction goes through that same set.

**The docs search must not become an indexer.** The README's whole-roadmap
non-goals include *"A new vector DB / second indexer. Reuse existing retrieval and
FTS."* The runtime already has FTS5 with an honest LIKE fallback and a documented
hybrid ranking in `persistence.search_session_messages` (exact phrase → BM25 →
kind boost → recency). `workspace_docs` reuses that **approach** — same
tokenization (`re.findall(r"[A-Za-z0-9]+", query)[:12]`), same AND semantics, same
deterministic ordering — as a bounded per-call scan over `docs/**`, and reports
`engine` honestly. It adds no table, no vector store, no second index.

## 3. In scope

1. **`python/harness/code/workspace.py`** — workspace resolution (which root is
   legal), the ONE confinement seam that calls `policy.resolve_within`, the fixed
   argument-free `git` read probe, and the bounded, ignore-aware file walker.
2. **`python/harness/code/tools.py`** — `register_code_tools(registry)` exposing
   five read-only tools: `workspace_status`, `workspace_list`, `workspace_search`,
   `workspace_read`, `workspace_docs`. Called once, from `service.py`.
3. **Line-numbered reads with a continuation offset**, binary refusal, and
   secret-shaped-line redaction marked `«redacted»` plus a `code.redacted` event.
4. **`RunRequest.workspace`** (`{root, baseRevision}`, optional) in
   `python/harness/schemas.py`, validated on the front door in
   `src/lib/harness/validation.ts`, forwarded by `src/lib/harness/run-service.ts`
   and typed in `python-client.ts`.
5. **A new agent preset** `code-navigator` in `python/harness/agents.py` with a
   prompt in `python/harness/prompts.py`, whose allowlist is **only** the five read
   tools — it must not inherit the finance agent's tools.
6. **`code.*` events** on the existing `RunEmitter` (`python/harness/events.py`).
7. **Tests** for every gate in §9, and **ADR-H103**.

## 4. Who can use it (the non-expert obligation)

This capability is for **every finance professional** — analyst, PM, trader,
advisor, accountant, risk officer, student, journalist, small-business owner — not
for engineers or quants. A person who does not know Python, git, worktrees,
terminals or "allowlists" must be able to use it and must never be asked to learn
one to do so. That is a contract on this phase, not a nicety.

| Role | What they ask for | What they get |
|---|---|---|
| Analyst | *"Where do we document how we value a bank?"* | A plain answer with a citation they can click |
| Portfolio manager | *"Which of our research notes mention rate risk?"* | A short ranked list of the matching passages |
| Advisor | *"Find our fee schedule in the project"* | The passage, with the file and line it came from |
| Student / journalist | *"What does this project say about dividends?"* | The relevant passages, plainly summarised |
| Small-business owner | *"Where are the settings for my invoices?"* | The location, in plain words — never a file tree |

The rules, in order:

1. **User-visible vocabulary rule.** Every string a non-engineer *sees* names the
   **finance job**, never the mechanism. So: *"Check my portfolio for risks
   overnight"*, *"Run the test suite"*, *"Look through the project's notes for the
   valuation method"* — never "sandbox", "worktree", "workspace", "allowlist",
   "autonomy profile", "policy engine", "diff digest", "operator". Mechanism words
   stay in the logs, the run trace and the operator diagnostics, where they are
   useful; they do not appear in the chat, a button, a tooltip, an error banner or
   a notification.
2. **Where the strings live.** User-facing copy is **never** hardcoded in a
   component. The repo already has the layer: add the canonical key to
   `src/lib/i18n/dictionaries/en.ts` (the English source of truth), an optional
   translation beside it in `src/lib/i18n/dictionaries/index.ts`, and read it in
   the component with `useT()` from `src/lib/i18n/use-t.ts` (lookup + fallback
   live in `src/lib/i18n/translate.ts`). Phase 1 adds keys under the `task.*` and
   `refusal.*` prefixes and **no new raw literals**.
3. **Refusals must be readable by a human.** A refused action says what was
   blocked and what the user can do, in one plain sentence — *"I couldn't read
   that file because it holds private account data, so I left it alone."* — with
   the technical reason (the policy code) available behind a **details**
   affordance. The trace already carries the code; the UI never leads with it. The
   code → plain-sentence map is data (a dictionary), not a chain of `if`s in a
   component, so it is testable.
4. **Jargon gate (an acceptance gate, §9).** A small check fails the build when a
   new user-facing string contains a mechanism word. This phase's surface is the
   i18n keys plus the code → sentence map, both TypeScript, so the gate belongs in
   **`src/lib/i18n/plain-language.test.ts`** (vitest, beside the existing
   `catalog.test.ts`), not in pytest: it scans `en.ts` and the new map against a
   denylist — `sandbox`, `worktree`, `workspace`, `allowlist`, `autonomy`,
   `digest`, `argv`, `cwd`, `stderr`, `patch`, `diff`, `manifest`, `operator`,
   `policy engine`, `tool registry`, `sandbox backend`, `exit code` — case-
   insensitively, over the keys this phase adds.
5. **What the non-expert path looks like here.** They never see a file tree, a
   line range or a search pattern. They ask a question — *"Where in the project do
   we document how we value a bank?"* — and they get a plain answer with a
   citation they can click. If something could not be read, they get one plain
   sentence and a way to see more, never a policy code.

## 5. Non-goals (do not do these)

- **No write tool, no patch tool, no edit of any file. Ever.** Not even a stub.
- **No command execution.** No `subprocess` for model-chosen commands, no
  `shell=True`, no `os.system`, no `exec`. The single fixed `git` read probe in
  §6.1 is the only child process this phase may spawn, and it takes no
  model-supplied argument.
- No worktree allocation, no scratch directory, no `workspace.admin`.
- No dependency installation, no network, no package registry.
- No route group and no change to `main.py` (Phase 2 adds `routers/code.py`; this
  phase needs `app.include_router` for nothing).
- No second indexer, no vector store, no new retrieval path. `workspace_docs`
  scans `docs/**` per call.
- No change to any finance tool, the retrieval layer, research, memory or MCP.
- No new dependency in the runtime.
- Never weaken `trade.execute` / `broker.modify` / `production.modify`.
- Do not commit, push, or open a PR. Do not commit `jdds.db` or any `*.db`.

## 6. Exact contracts to create

### 6.1 Workspace resolution and confinement (workspace.py)

`python/harness/code/workspace.py` — one module owns three things: which root is
legal, the only confinement seam, and the bounded walker. It imports the policy
authority; it does not duplicate it.

```python
"""Workspace resolution, path confinement and bounded reading (Phase 1, read-only).

The ONE place a code path is turned into a real file path. `code/policy.py` owns
the decision rules; this module asks it and maps its answer to a tool error the
model can read. There is no second confinement implementation anywhere — a grep
for `realpath` under python/harness/code/ must return only this file.
"""

# Hard bounds. Every one of these is a refusal or an honest truncation, never a
# silent partial answer.
MAX_READ_LINES = 2_000          # per call
MAX_MATCHES = 200               # per search call
MAX_SCAN_FILES = 5_000          # files opened by one search/docs call
MAX_SCAN_BYTES = 8 * 1024 * 1024
MAX_SEARCH_MS = 5_000           # wall-clock deadline, checked every 200 lines
MAX_PATTERN_CHARS = 200
MAX_LIST_ENTRIES = 1_000
MAX_BINARY_PROBE_BYTES = 8_192
GIT_PROBE_TIMEOUT_S = 10
GIT_PROBE_OUTPUT_CAP_BYTES = 2 * 1024 * 1024

@dataclass(frozen=True)
class ResolvedWorkspace:
    """A legal, confirmed workspace root."""
    id: str                      # stable digest of the resolved root path
    root: Path                   # realpath'd, absolute
    base_revision: str           # git HEAD sha, or "unknown" — never invented
    strategy: str                # "checkout" in Phase 1; "worktree" in Phase 2
    binding: WorkspaceBinding    # the Phase-0 dataclass

def default_root() -> Optional[Path]:
    """The server-resolved root. BLACK_ECLIPSE_CODE_ROOT, else the repo root.

    Mirrors `AgenticService._project_root()`: an env override wins, otherwise the
    repo containing the harness. Returns None when neither resolves — a missing
    root is a REFUSAL (`WORKSPACE_UNAVAILABLE`), never a guess at a directory.
    """

def resolve_workspace(request_workspace: Optional[RunWorkspace]) -> Optional[ResolvedWorkspace]:
    """Resolve and confirm the workspace for a run.

    Phase 1 binds only the SERVER-RESOLVED root. An optional `request.workspace`
    is a NARROWING/confirmation, never a widening: when present, its `root` must
    realpath to exactly the server-resolved root, otherwise the run gets no
    workspace at all and a `code.refused` event with `WORKSPACE_UNBOUND`. A
    caller-supplied path can therefore never point the tools at a different
    directory — that is what makes an optional request field safe here.
    """

class WorkspaceDenial(Exception):
    """A refusal with a stable, structured code (never a bare string)."""
    def __init__(self, code: str, reason: str, *, path: str = "") -> None: ...

CONFINEMENT_ORDER = (
    "PATH_TRAVERSAL",        # a '..' component, or an absolute path
    "PATH_OUTSIDE_WORKSPACE",  # resolved path is not the root or under it
    "SYMLINK_ESCAPE",        # a component (or the target) is a link leaving the root
    "PROTECTED_PATH",        # policy.is_protected(rel)
    "IGNORED_PATH",          # policy.is_ignored(rel) — refused on direct read,
                             #   skipped in listings/searches
    "NOT_FOUND",
    "TOO_LARGE",
    "BINARY_FILE",
)

def confine(ws: ResolvedWorkspace, rel_path: str, *, for_write: bool = False) -> Path:
    """Turn a model-supplied relative path into a confined real path.

    Calls `policy.resolve_within(ws.root, rel_path)` — it does NOT re-implement
    the checks — and maps `PolicyDenial` to a `WorkspaceDenial` 1:1 so a test can
    assert a DISTINCT code per escape vector. The check order above is fixed and
    covered by a test, so the code a caller sees for `jdds.db` is always
    `PROTECTED_PATH` and never `BINARY_FILE`.
    """

def git_probe(ws: ResolvedWorkspace, kind: Literal["head", "branch", "status"]) -> dict:
    """One fixed, argument-free git read. The ONLY child process in Phase 1.

    `GIT_READONLY_ARGV` is a module constant of complete argv tuples
    (`("git", "rev-parse", "HEAD")`, `("git", "status", "--porcelain=v1", "-z",
    "--untracked-files=all")`). `shell=False`. `cwd=ws.root`. A scrubbed
    environment from `policy.SECRET_ENV_ALLOWLIST`. 10 s timeout, 2 MB output cap.
    NO model-supplied argument ever reaches this call — which is exactly why it is
    not Phase 3's command broker (that broker exists for model-chosen commands and
    is not open yet). When `git` is absent the result is `{"available": False,
    "reason": ...}` — the tool then reports "I can't tell" instead of inventing a
    branch or a revision.

    Returns `{"available": bool, "head": str, "branch": str, "dirty": [{"path",
    "status", "owner"}]}`. `owner` is `"pre-existing"` for every entry in Phase 1:
    nothing this run could have changed a file, and the tool text says so in
    words, so a dirty checkout is never misread as the agent's own work.
    """

def walk(ws, base: str, *, depth: int, max_entries: int) -> tuple[list[dict], bool]:
    """A bounded, ignore-aware tree walk (uses `os.walk` with pruning).

    `policy.IGNORED_DIRS` prune the walk (`.git`, `node_modules`, `src/generated`,
    `__pycache__`, `.next`, `_backups`, `.black-eclipse`, `scripts/vendor`);
    `policy.IGNORED_GLOBS` (incl. `*.db`) filter files. Returns `(entries,
    truncated)`; `truncated` is true when the bound stopped the walk.
    """
```

**Additive change to the policy authority:** `policy.PolicyDenial` gains a
`code: str` field (defaulted, additive) and `resolve_within` sets it from the
check that fired. This is allowed — `code/policy.py` is in `PROTECTED_PATHS`
against **agent** writes (Phase 10's freeze), not against the phase implementer —
and it is preferable to matching on a message string. `PolicyDenial` keeps
`reason` for the operator-facing text.

### 6.2 The five tools (tools.py)

`python/harness/code/tools.py`. All five tools declare `permission="read"`, so the
registry's non-read gate (`if tool.permission != "read": ... refused unless
authorized`) never fires for them: a read tool is callable by an allowlisted run
and needs no approval. That is the whole reason this phase can ship without an
authorizer.

```python
def register_code_tools(registry: ToolRegistry) -> list[str]:
    """Register the five read tools. Returns the names added."""
```

Every input model is pydantic with `model_config = ConfigDict(extra="forbid")`, so
an unexpected field is a `TOOL_VALIDATION_FAILED` rather than a silently ignored
typo. Every handler returns `(text, data)`, where `data` is the structured record
the front door reads and `text` is the bounded, model-facing text (already bounded
again at the registry seam by `MAX_TOOL_RESULT_CHARS`, ADR-H91).

```python
class WorkspaceStatusInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

class WorkspaceListInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    path: str = "."
    depth: int = Field(2, ge=1, le=4)
    includeSizes: bool = False
    maxEntries: int = Field(200, ge=1, le=MAX_LIST_ENTRIES)

class WorkspaceSearchInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    pattern: str = Field(..., min_length=1, max_length=MAX_PATTERN_CHARS)
    path: str = "."
    maxMatches: int = Field(50, ge=1, le=MAX_MATCHES)
    contextLines: int = Field(2, ge=0, le=5)
    caseSensitive: bool = False

class WorkspaceReadInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    path: str = Field(..., min_length=1, max_length=1024)
    startLine: int = Field(1, ge=1)          # the continuation offset
    maxLines: int = Field(400, ge=1, le=MAX_READ_LINES)

class WorkspaceDocsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str = Field(..., min_length=1, max_length=200)
    path: str = "docs"
    maxResults: int = Field(5, ge=1, le=20)
    maxChars: int = Field(4_000, ge=200, le=8_000)
```

| Tool | `ToolDefinition` fields | Behaviour |
|---|---|---|
| `workspace_status` | `permission="read"`, `risk="low"`, `timeout_ms=15_000` | Branch + HEAD + dirty files, each marked `owner: "pre-existing"`. Absent git → `available: false` with a reason. |
| `workspace_list` | `permission="read"`, `risk="low"`, `timeout_ms=15_000` | Bounded tree, ignore-aware, sizes only when asked, honest `truncated`. |
| `workspace_search` | `permission="read"`, `risk="low"`, `timeout_ms=20_000` | Regex; **always** `path:line`; bounded matches, files, bytes and wall-clock; deadline → `truncated: true` with partial results. |
| `workspace_read` | `permission="read"`, `risk="low"`, `timeout_ms=15_000` | Line-numbered; `nextStartLine` continuation offset; refuses binary; redacts secret-shaped lines as `«redacted»`. |
| `workspace_docs` | `permission="read"`, `risk="low"`, `timeout_ms=25_000` | Ranked excerpts from `docs/**` with `path:line` ranges; adds no table and no index. |

**`workspace_read` contract (the one with a leak surface).**

1. `confine(...)` first — escapes and protected paths refuse before a byte is read.
2. Binary refusal: a NUL byte in the first `MAX_BINARY_PROBE_BYTES`, or a
   `UnicodeDecodeError` on strict decode → `BINARY_FILE`. `jdds.db` never reaches
   this check: `PROTECTED_PATH` fires first because of the fixed order in §6.1,
   and the gate asserts exactly that code.
3. Redaction: every returned line passes through `redact_span(line, "«redacted»")`
   — a new, thin, public wrapper in `session_index.py` that reuses the ONE pattern
   set from `eclipse_memory.decision` and takes the marker as a parameter;
   `session_index.redact` delegates to it with its existing `[redacted]` marker, so
   its current behaviour and tests are unchanged. A line that *is* a secret-shaped
   assignment becomes `KEY=«redacted»`; the value is never returned, never logged,
   never emitted.
4. When any line was redacted the result carries `redactedLines: [n, ...]` and the
   emitter records **one** `code.redacted` event with the line numbers and the
   pattern *name* only.
5. `nextStartLine` is present only when the file continues past `maxLines`.

**`workspace_docs` contract (reuse, do not re-index).** Tokenize exactly as
`search_session_messages` does (`re.findall(r"[A-Za-z0-9]+", query)[:12]`, joined
with `AND`), score candidates with the same deterministic ordering (exact-phrase
hit first, then a simple term-frequency/BM25-shaped score, then recency of the
file's docs position), and return bounded excerpts with their `path:line` range.
The result names its `engine` honestly (`"scan"` here; the session index's own
`"fts5"`/`"like"` semantics are the model). No table is written. If a persistent
docs index is ever wanted, it must be built on the existing `SessionMessageFts`
pattern — a parallel indexer is a documented non-goal.

### 6.3 Events on the existing emitter

`RunEmitter` (`python/harness/events.py`) is the only event path; Phase 1 adds no
bus and no new event store.

| Event | Payload (content-free) |
|---|---|
| `code.workspace.bound` | `{workspaceId, strategy, baseRevision}` |
| `code.listed` | `{path, entries, truncated}` |
| `code.searched` | `{pattern, matches, filesScanned, truncated, ms}` |
| `code.read` | `{path, startLine, lines, nextStartLine, redactedLines}` |
| `code.docs` | `{query, results, engine}` |
| `code.redacted` | `{path, lines, patternName}` — **never the value** |
| `code.refused` | `{tool, code, path}` — the policy/tool code, no path contents |

Emission is a small helper in `code/tools.py`
(`async def emit_code_event(ctx, event_type, data)`) that degrades to `ctx.log`
when no emitter is attached (tests, direct calls) — graph.py is not touched for
events.

### 6.4 The request field and the agent preset

**`python/harness/schemas.py`** — additive, optional, so every existing caller is
unaffected:

```python
class RunWorkspace(BaseModel):
    """An optional narrowing/confirmation of the server-resolved workspace root."""
    root: str = Field(min_length=1, max_length=1024)
    baseRevision: Optional[str] = Field(default=None, max_length=128)  # noqa: N815

class RunRequest(BaseModel):
    ...
    # Phase 1 (additive, optional): bind this run to a read-only workspace. Absent
    # ⇒ the run has no code capability at all (the default-actor rule, Phase 0).
    workspace: Optional[RunWorkspace] = None
```

**`python/harness/agents.py`** — a separate preset, not the finance agent widened:

```python
CODE_NAVIGATOR = AgentConfig(
    id="code-navigator",
    name="Repository Navigator",
    systemPrompt=CODE_NAVIGATOR_SYSTEM_PROMPT,
    tools=[                       # ONLY these five — no finance tool, no MCP
        "workspace_status", "workspace_list", "workspace_search",
        "workspace_read", "workspace_docs",
    ],
    maxSteps=10,
    toolTimeoutMs=30_000,
    runTimeoutMs=180_000,
    # allowMcpTools is NOT set: this preset keeps its exact, closed allowlist.
)
AGENT_PRESETS[CODE_NAVIGATOR.id] = CODE_NAVIGATOR
DEFAULT_AGENT_ID = ECLIPSE_AGENT.id          # unchanged
```

**`python/harness/prompts.py`** — `CODE_NAVIGATOR_SYSTEM_PROMPT` states the
boundary honestly in the same voice as the finance prompt:

- what it can do: list, search, read with line numbers, find things in the docs;
- what it cannot do, in plain words: *"You cannot change any file, run any
  command, install anything, or reach the network. Say so plainly rather than
  implying you did something you did not."*;
- every claim must carry `path:line`, and a search it did not run is never
  implied;
- the audience paragraph: answer in the user's own terms, describe the *job*
  (*"I looked through the project's notes for the valuation method"*), never the
  mechanism (no "workspace", "allowlist", "policy", "sandbox"), and when
  something is refused give one plain sentence plus the option to see details.

**Front door (all additive).**

| File | Change |
|---|---|
| `src/lib/harness/validation.ts` | new exported `validateWorkspaceRef(raw): { ok, value?, issues }` — string, trimmed, ≤ 1024 chars, no control characters or NUL; `baseRevision` ≤ 128 chars, same character rule. Called by `run-service.ts` before forwarding; `validateRunInput` itself is unchanged. |
| `src/lib/harness/run-service.ts` | `StartRunOptions` gains `workspace?: { root: string; baseRevision?: string }`; it is validated and placed on the payload. |
| `src/lib/harness/python-client.ts` | `RunRequestPayload` gains `workspace?: { root: string; baseRevision?: string }`. |
| `src/lib/harness/types.ts` | `RunWorkspaceRef` interface exported through `index.ts`. |

**`python/harness/service.py`** — one line, in the existing registration block:
`register_code_tools(self.registry)`.

**`python/harness/graph.py`** — the binding must be reachable from a tool handler,
so `ToolContext` (`tools.py`) gains one additive field
`workspace: Optional[Any] = None`, set in `build_graph`'s existing
`ToolContext(...)` construction from `resolve_workspace(request.workspace)`. That
is the entire graph change (≤ 4 lines). Verified headroom: `graph.py` measures
1 615 lines against its pinned ratchet of 1 857, so this does not trip
`python/tests/test_size_budget.py`; all logic nonetheless lives in the new
modules.

## 7. Work items (ordered)

1. `docs/harness/roadmap/progress/phase-01-progress.md` with §9's gates as
   unchecked boxes.
2. Read `python/harness/code/policy.py`, `tools.py`, `service.py`, `agents.py`,
   `prompts.py`, `graph.py` (the `ToolContext(...)` construction and
   `effective_allowlist`), and `session_index.py` in full before editing. Record
   the real `resolve_within` signature and `PolicyDenial` shape in the progress
   log — do not trust the sketch in §6.1.
3. `code/workspace.py` — `ResolvedWorkspace`, `default_root`, `resolve_workspace`,
   `WorkspaceDenial`, `CONFINEMENT_ORDER`, `confine`, `git_probe`, `walk`.
4. `code/policy.py` — the additive `PolicyDenial.code` and its assignment in
   `resolve_within` (three escape codes + protected/ignored/not-found).
5. `session_index.py` — `redact_span(text, marker)`, with `redact` delegating to it
   so existing behaviour is byte-identical; run `test_session_search.py` to prove it.
6. `code/tools.py` — the five input models, the handlers, `register_code_tools`,
   and `emit_code_event`.
7. `service.py` + `agents.py` + `prompts.py` + `schemas.py` + the one `graph.py`
   wiring line, per §6.4.
8. Front door: `validation.ts`, `run-service.ts`, `python-client.ts`, `types.ts`,
   `index.ts`.
9. i18n: the `task.*` / `refusal.*` keys in `dictionaries/en.ts`, the code→sentence
   map, `useT()` wiring where the new status lines render, and
   `src/lib/i18n/plain-language.test.ts` (§9 G8).
10. `python/tests/test_code_workspace.py` and `python/tests/test_code_tools.py`
    plus fixtures under `python/tests/fixtures/code/` — one test per gate in §9.
11. ADR-H103, `docs/CHANGELOG.md`, `docs/NAVIGATION.md`.

## 8. Deliverables

| File | Change |
|---|---|
| `python/harness/code/workspace.py` | new — resolution, confinement seam, probe, bounded walker |
| `python/harness/code/tools.py` | new — `register_code_tools` + the five read tools |
| `python/harness/code/policy.py` | additive `PolicyDenial.code` |
| `python/harness/session_index.py` | `redact_span(..., marker)`; `redact` delegates |
| `python/harness/tools.py` | additive `ToolContext.workspace` field |
| `python/harness/service.py` | one registration line |
| `python/harness/agents.py` | `code-navigator` preset (five read tools only) |
| `python/harness/prompts.py` | `CODE_NAVIGATOR_SYSTEM_PROMPT` |
| `python/harness/schemas.py` | `RunWorkspace`; `RunRequest.workspace` |
| `python/harness/graph.py` | ≤ 4 lines: bind the workspace onto the run's `ToolContext` |
| `src/lib/harness/{validation,run-service,python-client,types,index}.ts` | the optional `workspace` field + `RunWorkspaceRef` |
| `src/lib/i18n/dictionaries/en.ts` (+ `index.ts`) | new `task.*` / `refusal.*` keys |
| `src/lib/i18n/plain-language.test.ts` | new — the jargon gate (G8) |
| `python/tests/test_code_workspace.py`, `python/tests/test_code_tools.py`, `python/tests/fixtures/code/*` | new — §9 as tests |
| `docs/harness/decisions.md` | ADR-H103 |
| `docs/harness/roadmap/progress/phase-01-progress.md` | new — raw gate output |

## 9. Acceptance gates

Run each from `Black-Eclipse-site/` and paste the **raw** output into the progress
log. A gate not run is a gate not passed.

```bash
# G1 — the release gate (the definition of done)
npm run check:all

# G2 — the new tests, verbose so every refusal is visible
./scripts/vendor/python/python.exe -m pytest python/tests/test_code_workspace.py python/tests/test_code_tools.py -v

# G3 — a fixture-repo question returns the right path:line
./scripts/vendor/python/python.exe -m pytest python/tests/test_code_tools.py -k "path_line or fixture_question" -q

# G4 — the three escape vectors are refused with DISTINCT codes
./scripts/vendor/python/python.exe -m pytest python/tests/test_code_workspace.py -k "traversal or absolute_outside or symlink" -v
#   expect: PATH_TRAVERSAL, PATH_OUTSIDE_WORKSPACE, SYMLINK_ESCAPE respectively

# G5 — the vault is refused before it is opened
./scripts/vendor/python/python.exe -m pytest python/tests/test_code_tools.py -k "jdds or protected" -q
#   expect: code PROTECTED_PATH (NOT BINARY_FILE) for jdds.db

# G6 — a secret-shaped line comes back redacted, and says so in the trace
./scripts/vendor/python/python.exe -m pytest python/tests/test_code_tools.py -k "redact" -v
#   expect: «redacted» in the text, no value anywhere, one code.redacted event

# G7 — the navigator cannot reach a finance tool, proven not asserted
./scripts/vendor/python/python.exe -c "from harness.agents import AGENT_PRESETS; \
a=AGENT_PRESETS['code-navigator']; print(sorted(a.tools)); \
print('finance tools present:', [t for t in a.tools if not t.startswith('workspace_')])"
#   expect: the five workspace_* names, and []

# G8 — no user-facing string names a mechanism
npx vitest run src/lib/i18n/plain-language.test.ts

# G9 — nothing was disturbed
git status --short          # jdds.db must NOT appear; no *.db change
```

**Pass criteria.** G1 all gates pass, with the vitest/pytest counts recorded;
G2/G3 green; G4 prints three distinct codes; G5 gives `PROTECTED_PATH`;
G6 shows `«redacted»` with a `code.redacted` event and no secret value in the text,
`data`, or the persisted event row; G7 prints the five read tool names and an empty
list; G8 passes; G9 shows no `*.db` change. Additionally, a grep for `subprocess`
under `python/harness/code/` returns exactly one module (`workspace.py`, the fixed
git probe) and a grep for `realpath` returns only `workspace.py` (plus any hit in
`policy.py`, which is the Phase-0 authority it calls).

## 10. Definition of done

- Every gate in §9 run, raw output pasted, counts recorded.
- Exactly five tools added, all `permission="read"`; a test asserts the set and
  that `code-navigator` holds nothing else.
- Traversal, absolute-outside and symlink-escape each produce their own distinct
  structured code, and `confine` is the only place a path is resolved.
- `jdds.db` (protected + binary) reports `PROTECTED_PATH`, deterministically.
- No file is written and no process is spawned except the fixed, argument-free
  `git` read probe.
- Every user-visible string added by this phase lives in `src/lib/i18n/` and passes
  the jargon gate; the plain-language refusal map is data, not branching UI code.
- ADR-H103 written; `docs/CHANGELOG.md` entry appended; `docs/NAVIGATION.md`
  updated; `status:` flipped in this file and in the index row.

## 11. Implementation prompt (copy this to OpenCode)

```text
Task: Phase 1 — Repository navigator, read-only (Eclipse-as-a-Harness roadmap).

Read first, in full:
- docs/harness/roadmap/phase-01-repository-navigator.md  (this phase, verbatim)
- docs/harness/roadmap/README.md  (invariants §3, work in flight §4, file map §7)
- docs/harness/roadmap/phase-00-policy-and-baseline.md  (§6.3 — the policy module
  you obey)
- python/harness/code/policy.py (as shipped by Phase 0)
- python/harness/tools.py (ToolRegistry/ToolDefinition/ToolContext/ToolResult)
- python/harness/service.py (the registration block), agents.py, prompts.py
- python/harness/graph.py (the ToolContext(...) construction; effective_allowlist)
- python/harness/session_index.py (the ONE privacy pattern set, reused)
- src/lib/harness/{validation,run-service,python-client,types}.ts
- src/lib/i18n/{dictionaries/en.ts,dictionaries/index.ts,translate.ts,use-t.ts}

Goal: let Eclipse SEE the repository — list, search, read with line numbers, find
things in docs — and do nothing else with it. No write, no patch, no command, no
sandbox. This is gate 7A of agentic-plan-implementaion.md §15.3.

In scope:
1. python/harness/code/workspace.py per §6.1: ResolvedWorkspace, default_root
   (BLACK_ECLIPSE_CODE_ROOT else the repo root), resolve_workspace (the request's
   root may only CONFIRM the server-resolved root; a mismatch means no workspace),
   WorkspaceDenial(code, reason), CONFINEMENT_ORDER, confine() delegating to
   policy.resolve_within, git_probe() over a module-constant argv table with
   shell=False / cwd=worktree root / SECRET_ENV_ALLOWLIST env / 10s / 2MB cap, and
   a bounded ignore-aware walk() using policy.IGNORED_DIRS + IGNORED_GLOBS.
   Do NOT re-implement traversal checks: call the Phase-0 authority. A grep for
   `realpath` under python/harness/code/ must hit only this file.
2. code/policy.py: add the additive `code` field to PolicyDenial and set it in
   resolve_within (PATH_TRAVERSAL / PATH_OUTSIDE_WORKSPACE / SYMLINK_ESCAPE /
   PROTECTED_PATH / IGNORED_PATH / NOT_FOUND). Keep `reason` for operators.
3. session_index.py: add redact_span(text, marker) reusing the EXISTING pattern
   source (eclipse_memory.decision) and make redact() delegate with its current
   marker. Do not start a second pattern set.
4. code/tools.py per §6.2: register_code_tools(registry) with EXACTLY five
   read-only tools — workspace_status, workspace_list, workspace_search,
   workspace_read, workspace_docs — each permission="read", risk="low", with the
   pydantic input models and bounds in §6.2, and emit_code_event(ctx, ...) helper.
   Rules:
   - workspace_read: line-numbered, nextStartLine continuation offset, refuses
     binary (NUL/unreadable), redacts secret-shaped lines to «redacted», reports
     redactedLines, emits ONE code.redacted (line numbers + pattern name only).
   - jdds.db must return PROTECTED_PATH, not BINARY_FILE (fixed check order).
   - workspace_search: bounded matches/files/bytes/wall-clock (MAX_SEARCH_MS),
     always path:line, deadline ⇒ truncated with partial results.
   - workspace_docs: tokenize EXACTLY as persistence.search_session_messages does
     and rank the same way, as a bounded per-call scan of docs/**. NO new table,
     NO new index, NO vector store; report engine honestly.
5. schemas.py: RunWorkspace {root, baseRevision} + RunRequest.workspace (optional,
   additive). agents.py: a NEW preset code-navigator whose tools are ONLY the five
   workspace_* names (do NOT widen eclipse-agent, do NOT set allowMcpTools).
   prompts.py: CODE_NAVIGATOR_SYSTEM_PROMPT — state the read-only boundary in
   plain words and require path:line for every claim. Front door per §6.4.
6. service.py: one line, register_code_tools(self.registry). graph.py: ≤ 4 lines to
   set ToolContext.workspace from resolve_workspace(request.workspace) in the
   EXISTING ToolContext(...) construction. All logic stays in the new modules.
7. Events on the existing RunEmitter per §6.3 (content-free payloads).
8. Front door (additive): validateWorkspaceRef in validation.ts, the optional
   field on StartRunOptions + payload in run-service.ts, RunRequestPayload +
   RunWorkspaceRef in python-client.ts/types.ts/index.ts.
9. i18n: add every new user-facing string as a key in src/lib/i18n/dictionaries/
   en.ts (canonical) with optional translations in dictionaries/index.ts, and read
   them with useT() (src/lib/i18n/use-t.ts; lookup/fallback in translate.ts).
   Add a code→plain-sentence refusal map as DATA. Never hardcode copy in a
   component. Vocabulary rule: name the FINANCE JOB, never the mechanism —
   forbidden in any user-visible string: sandbox, worktree, workspace, allowlist,
   autonomy, digest, argv, cwd, stderr, patch, diff, manifest, operator, policy
   engine, tool registry, sandbox backend, exit code.
10. Tests: python/tests/test_code_workspace.py + python/tests/test_code_tools.py +
    fixtures under python/tests/fixtures/code/. Add
    src/lib/i18n/plain-language.test.ts (vitest, beside catalog.test.ts) as the
    jargon gate over the keys this phase adds.
11. ADR-H103 in docs/harness/decisions.md (Decision / Why / Consequences; the series
    currently ends at ADR-H92). docs/CHANGELOG.md dated entry + docs/NAVIGATION.md
    rows for code/workspace.py and code/tools.py.

Audience obligation (non-negotiable): this is for every finance professional, not
for engineers. A user who does not know git or Python asks a question and gets a
plain answer with a citation. Refusals are one plain sentence ("I couldn't read
that because it holds private account data") with the technical reason behind a
details affordance. All copy lives in src/lib/i18n/; the jargon gate G8 must pass.

Non-goals (do NOT do these):
- No write tool, no patch tool, no file modification of any kind. Not even a stub.
- No command execution for model-chosen commands; no shell=True; the ONLY child
  process is the fixed, argument-free git_probe.
- No worktree allocation, no scratch dir, no routers/code.py, no main.py change.
- No second indexer, no vector DB, no new retrieval path.
- No change to finance tools, retrieval, research, memory, or MCP.
- No new runtime dependency. Never weaken trade.execute / broker.modify /
  production.modify. Never commit, push, or open a PR. Do not commit jdds.db.

Constraints:
- One runtime: register on the existing ToolRegistry, driven by the existing
  execute_run. No second loop/registry/adapter.
- Policy in code only. Prose is never a security boundary.
- New logic goes in new modules; graph.py/persistence.py/main.py stay under their
  ratchets (persistence.py is FROZEN at its pinned 1393 lines — do not edit it).

Acceptance gates — run each and paste the RAW output into
docs/harness/roadmap/progress/phase-01-progress.md:
  npm run check:all
  ./scripts/vendor/python/python.exe -m pytest python/tests/test_code_workspace.py python/tests/test_code_tools.py -v
  ./scripts/vendor/python/python.exe -m pytest python/tests/test_code_workspace.py -k "traversal or absolute_outside or symlink" -v
     -> three DISTINCT codes: PATH_TRAVERSAL, PATH_OUTSIDE_WORKSPACE, SYMLINK_ESCAPE
  ./scripts/vendor/python/python.exe -m pytest python/tests/test_code_tools.py -k "jdds or protected" -q
     -> PROTECTED_PATH for jdds.db
  ./scripts/vendor/python/python.exe -m pytest python/tests/test_code_tools.py -k redact -v
     -> «redacted» + one code.redacted event, no value anywhere
  ./scripts/vendor/python/python.exe -c "from harness.agents import AGENT_PRESETS; print(sorted(AGENT_PRESETS['code-navigator'].tools))"
     -> only the five workspace_* tools
  npx vitest run src/lib/i18n/plain-language.test.ts
  git status --short     -> jdds.db must NOT appear

Finish by stating: "docs updated: <files>" or "no doc change — <reason>".
```

---

**Next:** [Phase 2 — Isolated worktree patch authoring](./phase-02-worktree-patching.md)
