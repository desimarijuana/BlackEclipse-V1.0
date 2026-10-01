---
title: "Phase 2 — Isolated Worktree Patch Authoring"
status: Done
phase: 2
depends_on: [1]
unlocks: [3]
last-verified: 2026-10-01
---

# Phase 2 — Isolated Worktree Patch Authoring

| | |
|---|---|
| **Depends on** | Phase 1 (the read-only navigator + workspace confinement), Phase 0 (policy) |
| **Unlocks** | Phase 3 (sandboxed command broker) |
| **Estimated work** | 6–9 h of agent time, real write capability against a disposable tree |
| **Deliverable type** | worktree lifecycle + structured patch engine + 3 write tools + 1 table + 1 ADR |
| **New ADRs** | ADR-H101 |
| **Prompt to copy** | [§11 below](#11-implementation-prompt-copy-this-to-opencode) |

## Contents

- [1. Goal](#1-goal)
- [2. Why this phase exists (the gap in the real code)](#2-why-this-phase-exists-the-gap-in-the-real-code)
- [3. In scope](#3-in-scope)
- [4. Who can use it (the non-expert obligation)](#4-who-can-use-it-the-non-expert-obligation)
- [5. Non-goals (do not do these)](#5-non-goals-do-not-do-these)
- [6. Exact contracts to create](#6-exact-contracts-to-create)
  - [6.1 Worktree lifecycle (worktree.py)](#61-worktree-lifecycle-worktreepy)
  - [6.2 The patch engine (patch.py)](#62-the-patch-engine-patchpy)
  - [6.3 The three tools (tools.py)](#63-the-three-tools-toolspy)
  - [6.4 Persistence (agent-memory.db)](#64-persistence-agent-memorydb)
  - [6.5 Permissions and the authorizer](#65-permissions-and-the-authorizer)
  - [6.6 Events, and the plain-language mapping](#66-events-and-the-plain-language-mapping)
- [7. Work items (ordered)](#7-work-items-ordered)
- [8. Deliverables](#8-deliverables)
- [9. Acceptance gates](#9-acceptance-gates)
- [10. Definition of done](#10-definition-of-done)
- [11. Implementation prompt (copy this to OpenCode)](#11-implementation-prompt-copy-this-to-opencode)

## 1. Goal

Let Eclipse **author a change** — create a file, replace a span, delete a file,
move one — inside a **disposable copy of the repository**, and produce a reviewable
unified diff, without ever touching the operator's working checkout.

Phase 2 closes the write half of the roadmap's first structural gap: after it, "I
wrote you a report generator and here is the change" is a claim backed by a real
artifact and a real diff. Maps to `agentic-plan-implementaion.md` §15.3 gate
**7B**.

## 2. Why this phase exists (the gap in the real code)

Phase 1 gave the agent eyes. It still cannot change a single byte, and the runtime
says so in its own words — `python/harness/prompts.py`:

> *"If you find yourself wanting a tool that is not listed here — a shell, a file
> reader, a general web search — it does not exist in this environment: say so
> plainly…"*

There is no patch vocabulary in the runtime at all: a grep for `write_text`,
`open(..., "w")` or a diff producer under `python/harness/` returns nothing
outside the persistence layer's own SQLite writes. So this phase invents the
vocabulary — and the repo already contains the **exact model to copy**, which is
why the patch engine below is a deliberate analogue rather than a fresh design.

`python/harness/skills/patches.py` is a structured, versioned, reversible patch
engine, and its hard rules are the reason it is trustworthy:

```python
# only the allowed operation set (`replace`/`add`/`remove`) and the allowed
# JSON-pointer paths are accepted;
# the base version must still be the skill's latest, or the patch is rejected
#   (stale/concurrent edits cannot silently overwrite);
# a patch may not widen permissions, add forbidden permissions, add a tool the
#   registry does not know, or change the skill id;
```

Two of those translate directly to files, and Phase 2 keeps them:

1. **A closed operation set, validated structurally before anything is applied.**
   `ALLOWED_OPS = frozenset({"replace", "add", "remove"})` becomes
   `{create, replace, delete, move}` — a set, not a parser.
2. **A stale-base refusal.** `version_conflict()` refuses a patch whose
   `baseVersion` is no longer the skill's latest — *"a concurrent edit happened
   and the patch must be recomputed (never silently rebased)"*. The file
   equivalent is the **content hash**: every op records `contentHashBefore` /
   `contentHashAfter`, and an op whose `expectHash` does not match the file on
   disk is refused rather than applied. Nothing is ever silently rebased.

**And the isolation rule is already the repo's standing law**, in the roadmap
README §3: *"Workspace isolation: disposable worktrees, snapshot fallback, no
writes to the operator's checkout."* The concurrency rule from README §4 makes
this concrete rather than theoretical: *"OpenCode edits this tree concurrently. …
never write to a file modified in the last few seconds."* A write tool that
touched the operator's checkout would collide with a live OpenCode session on the
same working tree. A detached worktree makes that impossible by construction.

**Why the scratch root is `.black-eclipse/`.** The path is already the repo's
per-run scratch convention and is already ignored — `.gitignore` line 78
(`/.black-eclipse/`), described as *"Per-conversation session workspaces (user
uploads + agent output). Runtime data, never committed — same tier as
agent-memory.db."* Phase 2 puts code worktrees at
`<repo>/.black-eclipse/code-workspaces/<id>`, i.e. inside an ignored directory, so
a leaked worktree can never become a tracked artifact, and `git status --short`
on the operator's checkout stays clean.

## 3. In scope

1. **`python/harness/code/worktree.py`** — `allocate(root, base_revision)` →
   `git worktree add --detach` under the ignored scratch root;
   `snapshot-copy` fallback when `git worktree` is unavailable, with the chosen
   strategy reported honestly; `release(id)` that refuses to delete anything
   outside the scratch root; `diff(id, base)` returning a unified diff plus
   added/modified/deleted lists.
2. **`python/harness/code/patch.py`** — modelled deliberately on
   `skills/patches.py`: ops `create` (whole file) / `replace` (exact, unique
   old→new) / `delete` / `move`, each carrying `path` + `reason`; hard rejections
   for absolute paths, `..` traversal, symlink targets, protected paths, oversize
   writes, and writes outside the declared scope; **every applied op records
   `contentHash` before and after**.
3. **Three tools** in `code/tools.py` — `workspace_patch_apply`, `workspace_diff`,
   `workspace_revert`.
4. **A `CodeWorkspace` table** in `agent-memory.db`, added additively and
   idempotently through `python/harness/persistence.py`.
5. **Permissions**: `git.read` + `code.write`, inside the worktree only.
   `git.write` (staging/committing in the operator's checkout) is **operator-only
   and is NOT implemented here**.
6. **Tests** for every gate in §9, and **ADR-H101**.

## 4. Who can use it (the non-expert obligation)

This capability is for **every finance professional** — analyst, PM, trader,
advisor, accountant, risk officer, student, journalist, small-business owner — not
for engineers or quants. Nobody should have to learn what a worktree, a patch, a
diff or a terminal is in order to have Eclipse build them something. That is a
contract on this phase, not a nicety.

| Role | What they ask for | What they get |
|---|---|---|
| Analyst | *"Build me a monthly cash-flow summary"* | A working summary tool, plus a plain "done" and a way to see what changed |
| Portfolio manager | *"Add a page that shows each holding's risk"* | The new page, plus a plain result and an optional undo |
| Trader | *"Change the fee on the execution report"* | The change, described in one plain sentence |
| Advisor / accountant | *"Fix the way the report rounds currency"* | The fix, with "See what changed" in readable before/after form |
| Risk officer | *"Make the stress-test output show the worst case first"* | The change, plus a plain line saying it was checked |
| Student / small-business owner | *"Add a simple invoice summary to my dashboard"* | The feature, described as a result — never as a file change |

The rules, in order:

1. **User-visible vocabulary rule.** Every string a non-engineer *sees* names the
   **finance job**, never the mechanism. So: *"Build me a monthly cash-flow
   summary"*, *"Add a page that shows each holding's risk"*, *"Change the fee on
   the advisory report"* — never "worktree", "patch", "diff", "hunk", "commit",
   "revert", "checkout", "branch", "sandbox", "allowlist", "autonomy profile",
   "policy engine", "operator". Mechanism words stay in the logs, the run trace
   and the operator diagnostics, where they are useful; they do not appear in the
   chat, a button, a tooltip, an error banner, a progress line or a notification.
2. **Where the strings live.** User-facing copy is **never** hardcoded in a
   component. The repo already has the layer: add the canonical key to
   `src/lib/i18n/dictionaries/en.ts` (the English source of truth), an optional
   translation beside it in `src/lib/i18n/dictionaries/index.ts`, and read it in
   the component with `useT()` from `src/lib/i18n/use-t.ts` (lookup + fallback
   live in `src/lib/i18n/translate.ts`). Phase 2's strings are progress and result
   lines, so they go under the `task.*`, `progress.*` and `refusal.*` prefixes —
   and **no new raw literals** anywhere in a component.
3. **Refusals must be readable by a human.** A refused change says what was
   blocked and what the user can do, in one plain sentence — *"I didn't change the
   shared settings file because other work is using it, so I left it alone. Ask me
   to prepare the change separately and you can approve it."* — with the technical
   reason (the policy code) available behind a **details** affordance. The trace
   already carries the code and the change record; the UI never leads with it. The
   code → plain-sentence map is **data** (a dictionary keyed by code), not a chain
   of `if`s in a component, so it can be tested.
4. **Jargon gate (an acceptance gate, §9).** A small check fails the build when a
   new user-facing string contains a mechanism word. This phase's surface is
   progress/result copy and the code → sentence map, both TypeScript, so the gate
   belongs in **`src/lib/i18n/plain-language.test.ts`** (vitest, beside the
   existing `catalog.test.ts`) — the same file Phase 1 creates; this phase extends
   it with the change/progress keys. It scans `en.ts` and the new map against a
   denylist — `sandbox`, `worktree`, `workspace`, `allowlist`, `autonomy`,
   `digest`, `argv`, `cwd`, `stderr`, `patch`, `diff`, `manifest`, `operator`,
   `policy engine`, `tool registry`, `sandbox backend`, `exit code` —
   case-insensitively, over the keys this phase adds.
5. **What the non-expert path looks like here — the whole point of the phase.**
   They never see a worktree, a file list, a patch operation or a check. They see
   a **task**, a **plain progress line**, and a **plain result**:

   > **You:** "Build me a report generator for our monthly portfolio review."
   >
   > **Eclipse:** *Writing the report generator…*
   > *Checking it works…*
   > **Done. I added a report generator and proved it works with 3 checks.**
   > `See what changed` · `Undo this change`

   The two affordances are plain-language views of `workspace_diff` and
   `workspace_revert`: "See what changed" shows a readable before/after (the
   unified diff rendered for a human, with a details toggle for the raw form), and
   "Undo this change" calls `workspace_revert`. Neither names a mechanism. A
   technical user can still open the raw change record — the same record the plain
   view is built from, so the two can never disagree.

## 5. Non-goals (do not do these)

- **No command execution.** No `subprocess` for model-chosen commands, no
  `shell=True`. `worktree.py` may spawn **only** the fixed `git worktree …` argv
  constants in §6.1, with no model-supplied argument — Phase 3 owns running checks.
- **No `git.write`.** No `git add`, `commit`, `checkout`, `reset`, `stash`, `push`,
  `clean` anywhere. Staging and committing the operator's checkout stays
  operator-only and is not implemented in this phase.
- **No write of any kind outside the workspace root** — not a log, not a temp
  file, not a backup. The scratch root has to be the only writable surface.
- No sandbox, no network, no dependency installation, no package registry.
- No route group and no change to `main.py`. Phase 3's `routers/code.py` is not
  this phase's deliverable.
- No diff/merge UI framework, no three-way merge, no conflict resolution. A
  conflicting op is **refused**, not merged.
- No change to any finance tool, the retrieval layer, research, memory or MCP.
- No new dependency in the runtime.
- Never weaken `trade.execute` / `broker.modify` / `production.modify`.
- Do not commit, push, or open a PR. Do not commit `jdds.db` or any `*.db`.

## 6. Exact contracts to create

### 6.1 Worktree lifecycle (worktree.py)

One module owns allocation, release and the diff for a code workspace. It is the
only module in the phase allowed to spawn a process.

```python
"""Disposable code workspaces (Phase 2).

A code workspace is a throwaway copy of the repository the agent may write to.
The operator's checkout is never a target: `allocate` creates the workspace, and
`release` can only delete something inside the scratch root — a path check, not a
convention.

Two strategies, chosen honestly and reported:

  * "worktree" — `git worktree add --detach <dir> <base>` under
    <repo>/.black-eclipse/code-workspaces/<id>. The repo's .gitignore already
    ignores /.black-eclipse/ (line 78), so a leaked worktree is never a tracked
    artifact. A detached HEAD means no branch is created, moved or deleted.
  * "snapshot" — a bounded recursive copy of the tracked tree, used when
    `git worktree` is unavailable (no git on PATH, a non-git root, a bare
    sandbox). It is SLOWER and uses more disk, and the strategy string on the
    returned record and on the code.workspace.created event says "snapshot" — the
    runtime never claims a git worktree it did not create.
"""

SCRATCH_RELPATH = ".black-eclipse/code-workspaces"
MAX_SNAPSHOT_FILES = 20_000
MAX_SNAPSHOT_BYTES = 512 * 1024 * 1024
MAX_DIFF_BYTES = 2 * 1024 * 1024
GIT_WORKTREE_TIMEOUT_S = 60
WORKSPACE_TTL_SECONDS = 24 * 60 * 60

# The ONLY argv this module may run. No model-supplied argument reaches any of
# them; `base_revision` and `dir` come from validated internal values only.
GIT_WORKTREE_ARGV = {
    "add": ("git", "worktree", "add", "--detach"),
    "remove": ("git", "worktree", "remove", "--force"),
    "rev_parse": ("git", "rev-parse", "HEAD"),
}
BASE_REVISION_PATTERN = r"[0-9a-fA-F]{7,40}|HEAD(~\d+)?"

@dataclass(frozen=True)
class CodeWorkspace:
    id: str                 # "cw_" + 16 hex chars
    root: Path              # <scratch>/<id> — the worktree root
    strategy: str           # "worktree" | "snapshot"
    base_revision: str      # resolved git sha, or the snapshot digest
    created_at: str
    released_at: Optional[str] = None
    diff_digest: Optional[str] = None    # set by diff(), sha256 of the unified diff

class WorkspaceError(Exception):
    """A structured workspace failure. `code` is stable and testable."""
    # WORKSPACE_ROOT_UNAVAILABLE | GIT_WORKTREE_UNAVAILABLE |
    # SNAPSHOT_TOO_LARGE | RELEASE_OUTSIDE_SCRATCH | UNKNOWN_WORKSPACE |
    # GIT_FAILED
    def __init__(self, code: str, reason: str) -> None: ...

def scratch_root(repo_root: Path) -> Path:
    """<repo_root>/.black-eclipse/code-workspaces — created lazily, 0700 on POSIX."""

def allocate(repo_root: Path, base_revision: str = "HEAD") -> CodeWorkspace:
    """Create a disposable workspace. Deterministic, bounded, honest about strategy.

    Order of attempts, all inside the locked scratch root:
      1. `git worktree add --detach <dir> <base>` with cwd=repo_root, no shell.
      2. On failure OR when `git worktree` is unavailable: snapshot copy of the
         tree produced by `git ls-files -z` (when git is present) or a bounded
         os.walk that skips policy.IGNORED_DIRS. Honest refusal
         (`SNAPSHOT_TOO_LARGE`) past MAX_SNAPSHOT_FILES / MAX_SNAPSHOT_BYTES —
         never a partial copy silently used as if complete.
    `base_revision` must match BASE_REVISION_PATTERN; it is echoed into the argv,
    never interpolated into a shell string.
    """

def release(workspace_id: str) -> dict:
    """Remove a workspace. Idempotent. Refuses to delete anything outside scratch.

    `os.path.realpath(workspace_root)` must be under
    `realpath(scratch_root(repo_root))`, else `RELEASE_OUTSIDE_SCRATCH` and
    nothing is deleted — the check that makes "disposable" safe rather than
    hopeful. A git worktree is deregistered with `git worktree remove --force`
    and then, if the directory still exists, removed with `shutil.rmtree`. A
    release of an already-released workspace returns
    `{"released": True, "alreadyReleased": True}` — idempotent by contract.
    """

def diff(workspace_id: str, base: Optional[str] = None) -> dict:
    """The unified diff plus added/modified/deleted lists.

    Returns `{"available": bool, "strategy": str, "base": str, "unified": str,
    "truncated": bool, "totalChars": int, "added": [...], "modified": [...],
    "deleted": [...], "digest": str, "filesChanged": int, "additions": int,
    "deletions": int}`.

    For a "worktree" workspace the unified diff comes from
    `git -C <root> diff <base> --no-color --no-ext-diff` (a read-only argv built
    from the workspace record, not from the model). For a "snapshot" workspace
    there is no git object database to diff against, so the module walks the
    manifest recorded at allocation time and produces a unified diff itself —
    and says so by leaving `strategy: "snapshot"` on the result, so no caller can
    mistake a synthesized diff for a git one.

    `digest` is sha256 of the unified text; it is persisted on the CodeWorkspace
    row and appears on the `code.diff` event, so a later phase can prove which
    diff an operator reviewed. A diff over MAX_DIFF_BYTES is truncated with
    `truncated: true` and the honest `totalChars`.
    """

def sweep_expired() -> list[str]:
    """Release workspaces past WORKSPACE_TTL_SECONDS. Best-effort, never raises.

    Called from the existing startup lifespan (the same place retention and skill
    maintenance already run) — not a new daemon or thread. Returns released ids.
    """
```

**Rules the module encodes, and a reviewer must check:**

- The operator checkout is **never** an argument to any function here. There is no
  parameter through which a caller could name it.
- `shell=False` for every argv. The one place a revision string is used, it is
  regex-validated against `BASE_REVISION_PATTERN` first.
- Everything writable lives under `scratch_root`, which is already gitignored.
- A failure to allocate is an honest refusal with a code — never a silent fall
  back to "write to the checkout instead".

### 6.2 The patch engine (patch.py)

The deliberate analogue of `skills/patches.py`. Same shape: a closed op set, a
structural validator, a rejection vocabulary, and an apply step that re-validates.

```python
"""Structured, reversible file patches inside a code workspace (Phase 2).

Modelled deliberately on skills/patches.py:

  * a closed operation set, validated structurally BEFORE anything is touched;
  * every operation carries a `reason`, so a change record explains itself;
  * a stale-base refusal — here the base is a CONTENT HASH, not a version string,
    so a concurrent edit is refused rather than silently rebased;
  * the applied result is re-checked (the write is inside the workspace and the
    resulting hash is what was reported) before the op is reported as done.

Nothing here decides whether a write is ALLOWED — code/policy.py owns that. This
module owns whether the write is WELL-FORMED and whether its base is still intact.
"""

ALLOWED_OPS = frozenset({"create", "replace", "delete", "move"})

MAX_OPERATIONS = 50
MAX_FILE_BYTES = 1_000_000        # per created/replaced file
MAX_TOTAL_BYTES_PER_APPLY = 4_000_000
MAX_OLD_SPAN_CHARS = 20_000
MAX_PATH_CHARS = 512
MAX_REASON_CHARS = 500

# Paths a patch may never touch, in addition to policy.PROTECTED_PATHS.
PATCH_FORBIDDEN_RELPATHS = frozenset({
    ".git", ".gitmodules", ".gitignore",
    "agent-memory.db", "eclipse-memory.db", "jdds.db",
    "mcp-servers.json", ".env",
})

class PatchError(ValueError):
    """A patch was rejected. `code` is stable; `reason` is operator-facing."""
    # PATCH_MALFORMED | PATCH_UNKNOWN_OP | PATCH_PATH_ABSOLUTE |
    # PATCH_PATH_TRAVERSAL | PATCH_PATH_SYMLINK | PATCH_PROTECTED_PATH |
    # PATCH_OUTSIDE_SCOPE | PATCH_TOO_LARGE | PATCH_BASE_MISMATCH |
    # PATCH_SPAN_NOT_FOUND | PATCH_SPAN_AMBIGUOUS | PATCH_FILE_EXISTS |
    # PATCH_FILE_MISSING | PATCH_TOO_MANY_OPERATIONS
    def __init__(self, code: str, reason: str) -> None: ...

@dataclass(frozen=True)
class PatchOp:
    op: str                  # "create" | "replace" | "delete" | "move"
    path: str                # workspace-relative; for "move", the DESTINATION
    reason: str
    content: Optional[str] = None       # create
    old: Optional[str] = None           # replace
    new: Optional[str] = None           # replace
    expect_hash: Optional[str] = None   # the hash the caller believes the base is
    from_path: Optional[str] = None     # move

@dataclass(frozen=True)
class AppliedOp:
    op: str
    path: str
    reason: str
    content_hash_before: Optional[str]   # None for create
    content_hash_after: Optional[str]    # None for delete
    bytes_written: int
    created: bool
    deleted: bool
    moved_from: Optional[str] = None

def parse_patch(payload: dict) -> list[PatchOp]:
    """Parse + structurally validate an untrusted patch. Raises PatchError.

    Rejections, in the fixed order a test asserts:
      1. more than MAX_OPERATIONS operations;
      2. an op not in ALLOWED_OPS;
      3. an absolute path (POSIX or Windows drive/UNC), a path with a drive
         letter, or any `..` component;
      4. a path over MAX_PATH_CHARS, or with a NUL;
      5. a declared `scope` the path is outside (see `apply`);
      6. a content/old/new span over the size caps.
    Structural only: filesystem and policy checks happen in `apply`.
    """

def apply(
    binding,                       # the Phase-0 WorkspaceBinding
    repo_root: Path,
    workspace_root: Path,
    operations: list[PatchOp],
    *,
    scope: tuple[str, ...] = (),    # declared, workspace-relative prefixes
    emitter=None,
) -> dict:
    """Apply an ordered patch inside the code workspace. Returns an audit record.

    For EACH op, in order, and ALL BEFORE the first write:
      1. `policy.decide_write(actor, binding, rel_path)` — an `allowed: False`
         decision refuses with the policy's own code and applies NOTHING (the
         whole patch is atomic: a refusal at op 5 leaves ops 1–4 unapplied too,
         because a half-applied patch is exactly the "silently rebased" failure
         skills/patches.py exists to prevent).
      2. `workspace.confine(...)` against the WORKSPACE root, mapping its codes
         (PATH_TRAVERSAL / PATH_OUTSIDE_WORKSPACE / SYMLINK_ESCAPE /
         PROTECTED_PATH / IGNORED_PATH) 1:1.
      3. scope check: the path must begin with a declared prefix, else
         PATCH_OUTSIDE_SCOPE. An empty scope means "the whole workspace, minus
         every protected path" and is only reachable under `edit_verify`+ — it is
         NOT the default.
      4. `PATCH_FORBIDDEN_RELPATHS` and `policy.PROTECTED_PATHS`.
      5. base integrity: when `expect_hash` is given it must equal the file's
         current sha256, else PATCH_BASE_MISMATCH (refuse, never rebase). When it
         is absent, the op proceeds but the recorded `content_hash_before` is what
         the file actually was — the audit is complete either way.

    Per-op semantics:
      * create — the path must not exist (PATCH_FILE_EXISTS otherwise).
      * replace — `old` must appear EXACTLY ONCE in the decoded text; zero
        occurrences is PATCH_SPAN_NOT_FOUND, two or more is PATCH_SPAN_AMBIGUOUS.
        A blind `.replace()` is never used: ambiguity is a refusal, not a choice.
      * delete — the file must exist and its content hash is recorded first.
      * move — source confined and read, destination confined and must not exist;
        recorded as one move, with the source hash on both sides.

    Returns `{"ok": bool, "workspaceId": str, "applied": [AppliedOp...],
    "refused": Optional[{op, path, code, reason}], "filesChanged": int,
    "totalBytes": int}`. The emitter records one `code.patch.applied` per applied
    op (path, op, hashes, bytes) and one `code.patch.refused` for a refusal (code,
    path, op) — content-free.
    """

def revert(
    binding, repo_root: Path, workspace_root: Path, applied: list[dict], *, emitter=None,
) -> dict:
    """Undo an applied patch exactly, newest op first.

    Each op is inverted from its own recorded hashes: delete a created file,
    recreate a deleted file from the recorded content, swap `new` back to `old`,
    move back. An op whose `content_hash_after` no longer matches the file is
    REFUSED (`PATCH_BASE_MISMATCH`) rather than inverted over a concurrent edit —
    the same rule as forward application, in both directions.
    """
```

**Rules the engine encodes, and a reviewer must check:**

- **Atomicity.** A refusal anywhere applies nothing. There is no partial patch.
- **A unique span or nothing.** `str.replace` is never the mechanism; count must
  be exactly one.
- **A hash on both sides of every op**, so a later phase can prove what changed.
- **Content, not shell.** No `git apply`, no `patch(1)`. The bytes are written by
  `Path.write_text(..., encoding="utf-8", newline="")` after a confined-path
  check — the same "one seam" discipline as the policy module.

### 6.3 The three tools (tools.py)

Added to the existing `register_code_tools(registry)` from Phase 1. All three
declare `permission="write"`, so the registry's non-read gate applies and each is
refused unless the run's effect authorizer approves the exact call. Phase 2
supplies that authorizer through the **autonomy profile** (`edit_verify` grants
`code.write`), not through an operator approval — operator approvals arrive in
Phase 5.

```python
class PatchApplyInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    operations: list[PatchOpModel] = Field(..., min_length=1, max_length=MAX_OPERATIONS)
    scope: list[str] = Field(default_factory=list, max_length=16)
    note: str = Field("", max_length=MAX_REASON_CHARS)

class WorkspaceDiffInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    base: Optional[str] = Field(default=None, max_length=128)   # defaults to the workspace base
    includeUnified: bool = True

class WorkspaceRevertInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    applied: list[dict] = Field(..., min_length=1)   # the record returned by a prior apply
```

| Tool | `ToolDefinition` | Behaviour |
|---|---|---|
| `workspace_patch_apply` | `permission="write"`, `effect="write"`, `risk="medium"`, `timeout_ms=60_000` | Validates → confines → policy-decides → applies atomically → records. Refusals carry a structured code. |
| `workspace_diff` | `permission="read"`, `risk="low"`, `timeout_ms=30_000` | Unified diff + added/modified/deleted + digest. Never writes. Reads the workspace, so it is callable under `plan_only` too. |
| `workspace_revert` | `permission="write"`, `effect="write"`, `risk="medium"`, `timeout_ms=60_000` | Inverts a recorded apply, newest first, refusing on a changed base. |

`workspace_patch_apply` refuses before touching anything when: the autonomy
profile does not grant `code.write` (`plan_only` → `PROFILE_DENIED`); no workspace
is bound (`WORKSPACE_UNBOUND`); the policy denies the path (`PROTECTED_PATH` /
`OUTSIDE_WORKSPACE` / `IGNORED_PATH`); the base hash does not match
(`PATCH_BASE_MISMATCH`); or the total exceeds the caps (`PATCH_TOO_LARGE`). Every
refusal emits `code.patch.refused` — a tool that refuses without a record is a
failure, not a pass.

### 6.4 Persistence (agent-memory.db)

Added **additively and idempotently** through `python/harness/persistence.py`'s
existing `_migrate()` on open — the same pattern as `SessionMessage`, and the same
pattern `run_lineage.py` documents for its own tables. **Never**
`eclipse-memory.db`, **never** `jdds.db`. No new schema file.

```sql
CREATE TABLE IF NOT EXISTS CodeWorkspace (
  id           TEXT PRIMARY KEY,
  root         TEXT NOT NULL,
  baseRevision TEXT NOT NULL,
  strategy     TEXT NOT NULL,          -- "worktree" | "snapshot"
  createdAt    TEXT NOT NULL,
  releasedAt   TEXT,
  diffDigest   TEXT,
  runId        TEXT,                   -- the run that allocated it (nullable)
  fileCount    INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_code_workspace_created ON CodeWorkspace(createdAt);
CREATE INDEX IF NOT EXISTS idx_code_workspace_run     ON CodeWorkspace(runId);
```

**Size-ratchet rule.** `python/harness/persistence.py` is pinned at **1 393 lines**
in `python/tests/test_size_budget.py` and measures 1 392 today — the table may be
added there (a few lines, under budget only if the count stays ≤ 1 393), but the
**helpers must not**: they belong in a new `python/harness/code/store.py` bound to
the single `AgentMemoryStore` connection, exactly as `run_lineage.py` documents
doing (*"That keeps `persistence.py` from growing past its size ratchet while
keeping ONE database and ONE connection"*). `code/store.py` owns
`save_workspace` / `get_workspace` / `list_workspaces` / `mark_released` /
`set_diff_digest`. **Do not edit `persistence.py` at all unless the DDL genuinely
fits; if it does not, put the DDL in `code/store.py` too** — `run_lineage.py`
already ships `CREATE TABLE IF NOT EXISTS` from its own module, so the precedent
exists.

### 6.5 Permissions and the authorizer

- `workspace_patch_apply` / `workspace_revert` require `code.write` **inside the
  bound workspace only**. The grant comes from the run's autonomy profile (Phase
  0's `code_grants("edit_verify")`), which is set only when a workspace is bound.
- `git.read` is already available to `plan_only`; Phase 2 uses it for
  `workspace_diff`'s worktree path and for the allocation probe.
- **`git.write` is not granted to any profile here.** The grant set for
  `approve_external` *contains* `git.write`, but no tool in this phase consumes it:
  staging/committing the operator's checkout remains an operator action
  (`src/lib/git/service.ts`, invoked from the Git panel), and Phase 5 is where an
  agent-side `git.write` would be introduced behind a single-use approval. Phase 2
  must not create that path.
- The run's effect authorizer for a Phase-2 write is
  `code/policy.decide_write(actor, binding, rel_path)`. It returns
  `PolicyDecision{allowed, code, reason}`; a `False` decision is a refusal with a
  recorded code, never a silent skip.

### 6.6 Events, and the plain-language mapping

| Event | Payload (content-free) |
|---|---|
| `code.workspace.created` | `{workspaceId, strategy, baseRevision, fileCount}` |
| `code.workspace.released` | `{workspaceId, alreadyReleased}` |
| `code.patch.applied` | `{workspaceId, op, path, bytes, hashBefore, hashAfter}` |
| `code.patch.refused` | `{workspaceId, op, path, code}` |
| `code.diff` | `{workspaceId, filesChanged, additions, deletions, digest, truncated}` |
| `code.reverted` | `{workspaceId, ops, ok}` |

On the front door, every refusal code maps to one plain sentence in the i18n
dictionary (data, keyed by code), with the code itself shown only behind
**details**. The progress lines a user sees — `task.working.*` — are fixed,
human strings chosen by the *task*, not by the mechanism: *"Writing the report
generator…"*, *"Checking it works…"*, *"Done. I added a report generator and
proved it works with 3 checks."* A user never sees the word "worktree".

## 7. Work items (ordered)

1. `docs/harness/roadmap/progress/phase-02-progress.md` with §9's gates as
   unchecked boxes.
2. Read `python/harness/code/workspace.py`, `code/policy.py`, `code/tools.py` (all
   as shipped by Phases 0–1), `skills/patches.py`, `mcp/approvals.py`,
   `run_lineage.py`, and the `_migrate()` / `_ensure_fts_index` region of
   `persistence.py` in full before writing. Confirm the real `persistence.py` line
   count and the ratchet entry in the progress log — do not trust §6.4's numbers.
3. `code/worktree.py` per §6.1 (`allocate` / `release` / `diff` / `sweep_expired`,
   `CodeWorkspace`, `WorkspaceError`, the argv constants).
4. `code/patch.py` per §6.2 (`parse_patch` / `apply` / `revert`, `PatchOp`,
   `AppliedOp`, `PatchError` with the full code list).
5. `code/store.py` per §6.4 + the `CodeWorkspace` DDL (in `persistence.py` only if
   it fits the ratchet; otherwise in `code/store.py`).
6. The three tools in `code/tools.py` per §6.3, plus their pydantic input models.
7. `workspace_diff` and the diff digest; wire `sweep_expired` into the existing
   startup lifespan path in `service.py` (best-effort, never blocks boot — the
   same contract as `run_maintenance`).
8. i18n: the `task.*`, `progress.*` and `refusal.*` keys in `en.ts`; the code →
   plain-sentence map as data; `useT()` where the progress/result lines render
   (`src/components/chat/activity-item.tsx` / `activity-feed.tsx`); and the
   jargon-gate additions to `src/lib/i18n/plain-language.test.ts`.
9. Tests `python/tests/test_code_worktree.py` and `python/tests/test_code_patch.py`
   plus fixtures under `python/tests/fixtures/code/` — one test per gate in §9.
10. ADR-H101, `docs/CHANGELOG.md`, `docs/NAVIGATION.md`.

## 8. Deliverables

| File | Change |
|---|---|
| `python/harness/code/worktree.py` | new — allocate / release / diff / sweep, honest strategy |
| `python/harness/code/patch.py` | new — the structured patch engine with before/after hashes |
| `python/harness/code/store.py` | new — `CodeWorkspace` rows bound to the one store connection |
| `python/harness/code/tools.py` | add `workspace_patch_apply`, `workspace_diff`, `workspace_revert` |
| `python/harness/persistence.py` | the `CodeWorkspace` DDL **only if** it fits the ratchet |
| `python/harness/service.py` | wire `sweep_expired` into the existing startup maintenance |
| `python/harness/agents.py` | `code-navigator` gains the three new tools (still no finance tool) |
| `python/harness/prompts.py` | the authoring section: plain task → change → proof, and the boundary |
| `src/lib/i18n/dictionaries/en.ts` (+ `index.ts`) | new `task.*` / `progress.*` / `refusal.*` keys |
| `src/lib/i18n/plain-language.test.ts` | extend the jargon gate with this phase's keys |
| `src/components/chat/{activity-item,activity-feed}.tsx` | render the plain progress/result lines via `useT()` |
| `python/tests/test_code_worktree.py`, `test_code_patch.py`, `fixtures/code/*` | new — §9 as tests |
| `docs/harness/decisions.md` | ADR-H101 |
| `docs/harness/roadmap/progress/phase-02-progress.md` | new — raw gate output |

## 9. Acceptance gates

Run each from `Black-Eclipse-site/` and paste the **raw** output into the progress
log. A gate not run is a gate not passed.

```bash
# G1 — the release gate (the definition of done)
npm run check:all

# G2 — the new tests, verbose so every refusal is visible
./scripts/vendor/python/python.exe -m pytest python/tests/test_code_worktree.py python/tests/test_code_patch.py -v

# G3 — a fixture task edits the intended file, and only that file
./scripts/vendor/python/python.exe -m pytest python/tests/test_code_patch.py -k "intended_file or unrelated_untouched" -q

# G4 — the operator's checkout is byte-identical after the run
./scripts/vendor/python/python.exe -m pytest python/tests/test_code_worktree.py -k "operator_checkout_untouched or preexisting_dirty" -v
git status --short          # jdds.db must NOT appear; no new untracked artifact

# G5 — every rejection vector is refused with its OWN code
./scripts/vendor/python/python.exe -m pytest python/tests/test_code_patch.py -k "traversal or symlink or protected or oversize or absolute or outside_scope or ambiguous_span or base_mismatch" -v

# G6 — cancellation leaves no orphan workspace, and release is idempotent
./scripts/vendor/python/python.exe -m pytest python/tests/test_code_worktree.py -k "cancel or orphan or release_idempotent or outside_scratch" -v
ls -d .black-eclipse/code-workspaces/* 2>/dev/null | wc -l    # expect 0 residual

# G7 — no user-facing string names a mechanism
npx vitest run src/lib/i18n/plain-language.test.ts

# G8 — git.write is implemented nowhere
grep -rn "\"git\", \"add\"\|\"git\", \"commit\"\|\"git\", \"push\"\|\"git\", \"checkout\"\|\"git\", \"reset\"" python/harness/code/ ; echo "exit=$?  (expect no matches)"
```

**Pass criteria.**

| Probe | Expected |
|---|---|
| a fixture task that edits one file | that file changed in the worktree; the intended change present |
| unrelated files in the worktree | unchanged, byte-identical |
| a pre-existing dirty file in the operator checkout | hash-identical before and after the run |
| `../x`, an absolute path, a symlink target leaving the root | refused: `PATCH_PATH_TRAVERSAL` / `PATCH_PATH_ABSOLUTE` / `PATCH_PATH_SYMLINK` |
| `jdds.db`, `agent-memory.db`, `.git/config`, `mcp-servers.json` | refused `PATCH_PROTECTED_PATH` |
| a write over `MAX_FILE_BYTES` / over the per-apply total | refused `PATCH_TOO_LARGE`, nothing written |
| a path outside the declared scope | refused `PATCH_OUTSIDE_SCOPE` |
| a `replace` whose `old` appears twice | refused `PATCH_SPAN_AMBIGUOUS` (never a chosen occurrence) |
| an op whose `expectHash` no longer matches | refused `PATCH_BASE_MISMATCH` |
| a refusal at op N after a valid op 1 | **nothing applied** (atomic) |
| cancellation mid-apply | no orphan worktree, no partial file, `code.workspace.released` |
| `release` twice | second call `{"alreadyReleased": true}`, no error |
| `release` pointed at a path outside the scratch root | refused `RELEASE_OUTSIDE_SCRATCH`, nothing deleted |
| `workspace_patch_apply` under `plan_only` | refused `PROFILE_DENIED`, nothing written |

G1 all gates pass with the counts recorded; G3–G6 green as tabulated; G7 passes;
G8 prints no matches; `git status --short` shows no `*.db` change and no unexpected
artifact.

## 10. Definition of done

- Every gate in §9 run, raw output pasted — including the operator-checkout and
  hash-identity probes, which are the reason this phase exists.
- The patch engine applies **atomically**: a refusal anywhere applies nothing, and
  a test proves it.
- Every applied op carries `contentHash` before and after; the record is persisted
  and appears on the `code.patch.applied` event.
- `release` provably cannot delete outside the scratch root, and is idempotent.
- `git.write` is implemented nowhere; `grep` over `python/harness/code/` returns no
  mutating git verb.
- The strategy a workspace used is reported honestly (`"worktree"` vs
  `"snapshot"`), and a snapshot diff is never presented as a git diff.
- Every user-visible string added by this phase lives in `src/lib/i18n/` and passes
  the jargon gate; the refusal code → plain sentence map is data, not branching UI.
- ADR-H101 written; `docs/CHANGELOG.md` entry appended; `docs/NAVIGATION.md`
  updated; `status:` flipped in this file and in the index row.

## 11. Implementation prompt (copy this to OpenCode)

```text
Task: Phase 2 — Isolated worktree patch authoring (Eclipse-as-a-Harness roadmap).

Read first, in full:
- docs/harness/roadmap/phase-02-worktree-patching.md  (this phase, verbatim)
- docs/harness/roadmap/README.md  (invariants §3, work in flight §4, file map §7)
- docs/harness/roadmap/phase-00-policy-and-baseline.md  (§6.3 — the policy you obey)
- docs/harness/roadmap/phase-01-repository-navigator.md  (the workspace you extend)
- python/harness/code/{workspace,policy,tools}.py  (as shipped by Phases 0–1)
- python/harness/skills/patches.py  ← THE MODEL. Copy its discipline: closed op
  set, structural validation before anything is applied, a stale-base refusal,
  re-validation of the result.
- python/harness/run_lineage.py  ← the pattern for owning your own table without
  growing the ratcheted persistence.py.
- python/harness/persistence.py  (_migrate / _ensure_fts_index only; measure it)

Goal: let Eclipse author a change inside a DISPOSABLE copy of the repo and show a
reviewable diff — never touching the operator's checkout. Gate 7B of
agentic-plan-implementaion.md §15.3.

In scope:
1. python/harness/code/worktree.py per §6.1. allocate() → `git worktree add
   --detach` under <repo>/.black-eclipse/code-workspaces/<id> (already gitignored,
   .gitignore line 78); snapshot-copy fallback when git worktree is unavailable,
   with the chosen strategy reported HONESTLY on the record and the event.
   release() refuses to delete anything whose realpath is not under the scratch
   root, and is idempotent. diff() returns unified + added/modified/deleted +
   digest; a snapshot workspace gets a synthesized diff that SAYS it is one.
   sweep_expired() for the startup maintenance path. The ONLY argv constants are
   the fixed git worktree/rev-parse ones — no model-supplied argument, shell=False,
   revision validated against BASE_REVISION_PATTERN.
2. python/harness/code/patch.py per §6.2, modelled on skills/patches.py. Ops
   create/replace/delete/move, each with path + reason. Hard rejections: absolute
   path, .. traversal, symlink target, protected/forbidden path, oversize, outside
   declared scope. replace requires the old span to appear EXACTLY ONCE (0 →
   PATCH_SPAN_NOT_FOUND, 2+ → PATCH_SPAN_AMBIGUOUS); never a blind .replace().
   Every applied op records contentHashBefore/After. ATOMIC: a refusal at any op
   applies NOTHING. expectHash mismatch → PATCH_BASE_MISMATCH (refuse, never
   rebase). revert() inverts newest-first and refuses over a changed base.
3. Persistence per §6.4: a CodeWorkspace table (id, root, baseRevision, strategy,
   createdAt, releasedAt, diffDigest, runId, fileCount) in agent-memory.db via the
   existing _migrate() pattern, added additively and idempotently. Keep
   persistence.py under its pinned ratchet — put the DDL + helpers in a new
   python/harness/code/store.py bound to the single AgentMemoryStore connection,
   exactly as run_lineage.py documents doing for its own tables. NEVER
   eclipse-memory.db. NEVER jdds.db. NO new schema file for agent-memory.db.
4. Three tools in code/tools.py per §6.3: workspace_patch_apply (permission="write",
   effect="write"), workspace_diff (permission="read"), workspace_revert
   (permission="write"). Refusals: PROFILE_DENIED (plan_only), WORKSPACE_UNBOUND,
   PROTECTED_PATH/OUTSIDE_WORKSPACE/IGNORED_PATH, PATCH_BASE_MISMATCH,
   PATCH_TOO_LARGE — each emitting code.patch.refused. A refusal with no record is
   a FAILURE.
5. Permissions: code.write ONLY inside the bound workspace, granted by the run's
   autonomy profile (edit_verify). git.write is NOT implemented here — do not add
   git add/commit/checkout/reset/stash/push/clean anywhere.
6. Events per §6.6 on the existing RunEmitter (content-free payloads).
7. i18n + plain language: every new user-facing string is a key in
   src/lib/i18n/dictionaries/en.ts (canonical; optional translations in
   dictionaries/index.ts) read via useT() (src/lib/i18n/use-t.ts; lookup/fallback
   in translate.ts). Never hardcode copy in a component. Refusal codes map to ONE
   plain sentence each, as DATA, with the code behind a details affordance.
   Progress lines name the TASK ("Writing the report generator…", "Checking it
   works…", "Done. I added a report generator and proved it works with 3 checks."),
   never the mechanism. Forbidden in any user-visible string: sandbox, worktree,
   workspace, allowlist, autonomy, digest, argv, cwd, stderr, patch, diff,
   manifest, operator, policy engine, tool registry, sandbox backend, exit code.
   Extend src/lib/i18n/plain-language.test.ts (the jargon gate) with this phase's
   keys.
8. Tests: python/tests/test_code_worktree.py + python/tests/test_code_patch.py +
   fixtures under python/tests/fixtures/code/. One test per probe in §9.
9. ADR-H101 in docs/harness/decisions.md (Decision / Why / Consequences shape; the series
   ended at ADR-H100 after Phases 0-1, so this one is H101).
   docs/CHANGELOG.md dated entry + docs/NAVIGATION.md rows for code/worktree.py,
   code/patch.py and code/store.py.

Audience obligation (non-negotiable): this is for every finance professional, not
for engineers. The non-expert path is a TASK, a plain progress line and a plain
result with "See what changed" and "Undo this change" — they never see a worktree,
a patch, a diff or a check. Refusals are one plain sentence plus a details
affordance. All copy lives in src/lib/i18n/ and the jargon gate must pass.

Non-goals (do NOT do these):
- No command execution for model-chosen commands; no shell=True. The only argv is
  the fixed git worktree/rev-parse set in worktree.py.
- NO git.write: no add/commit/checkout/reset/stash/push/clean anywhere.
- No write of any kind outside the workspace root — not a log, not a temp file.
- No three-way merge, no conflict resolution: a conflicting op is REFUSED.
- No routers/code.py, no main.py change. No sandbox, no network, no dependency
  install. No change to finance tools, retrieval, research, memory or MCP.
- Do not edit persistence.py beyond what genuinely fits its ratchet.
- Never weaken trade.execute / broker.modify / production.modify. Never commit,
  push, or open a PR. Do not commit jdds.db.

Constraints:
- One runtime: register on the existing ToolRegistry, driven by the existing
  execute_run. No second loop/registry/adapter.
- Policy in code only; prose is never a security boundary.
- The operator's checkout is NEVER an argument to any function in worktree.py.

Acceptance gates — run each and paste the RAW output into
docs/harness/roadmap/progress/phase-02-progress.md:
  npm run check:all
  ./scripts/vendor/python/python.exe -m pytest python/tests/test_code_worktree.py python/tests/test_code_patch.py -v
  ./scripts/vendor/python/python.exe -m pytest python/tests/test_code_patch.py -k "intended_file or unrelated_untouched" -q
  ./scripts/vendor/python/python.exe -m pytest python/tests/test_code_worktree.py -k "operator_checkout_untouched or preexisting_dirty" -v
  ./scripts/vendor/python/python.exe -m pytest python/tests/test_code_patch.py -k "traversal or symlink or protected or oversize or absolute or outside_scope or ambiguous_span or base_mismatch" -v
  ./scripts/vendor/python/python.exe -m pytest python/tests/test_code_worktree.py -k "cancel or orphan or release_idempotent or outside_scratch" -v
  ls -d .black-eclipse/code-workspaces/* 2>/dev/null | wc -l    -> 0 residual
  npx vitest run src/lib/i18n/plain-language.test.ts
  git status --short     -> jdds.db must NOT appear; no unexpected artifact
  grep -rn '"git", "add"\|"git", "commit"\|"git", "push"' python/harness/code/   -> no matches
Required probes: intended file edited and unrelated files untouched; a
pre-existing dirty file in the operator checkout hash-identical after the run;
traversal/symlink/protected/oversize/outside-scope/ambiguous-span/base-mismatch
each refused with a DISTINCT code; a refusal at op N after a valid op 1 applies
NOTHING; cancellation leaves no orphan worktree; release is idempotent and refuses
outside the scratch root; plan_only refused with PROFILE_DENIED.

Finish by stating: "docs updated: <files>" or "no doc change — <reason>".
```

---

**Next:** [Phase 3 — Sandboxed command broker](./phase-03-command-broker.md)
