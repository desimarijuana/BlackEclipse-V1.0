---
title: "Phase 5 — The Coding Agent, Autonomy Profiles and Approvals"
status: Not started
phase: 5
depends_on: [4]
unlocks: [6, 7, 8, 9]
last-verified: 2026-09-30
---

# Phase 5 — The Coding Agent, Autonomy Profiles and Approvals

| | |
|---|---|
| **Depends on** | Phase 4 (the verify-and-repair trust spine — autonomy is only safe once output is verifiable) |
| **Unlocks** | Phases 6, 7, 8, 9 (jobs, delegation, analysis sandbox, scaffold kits — all need a code-capable agent and a task lifecycle) |
| **Estimated work** | 4–6 h of agent time; one preset, one prompt, one policy field, one approval decision, routes + UI |
| **Deliverable type** | 1 agent preset + 1 prompt + policy wiring + task lifecycle on existing lineage + `routers/code.py` + TS client + 5 UI screens + tests + 1 ADR |
| **New ADRs** | ADR-H107 |
| **Prompt to copy** | [§11 below](#11-implementation-prompt-copy-this-to-opencode) |

## Contents

- [1. Goal](#1-goal)
- [2. Why this phase exists (the problem in the real code)](#2-why-this-phase-exists-the-problem-in-the-real-code)
- [3. In scope](#3-in-scope)
- [4. Who can use it (the non-expert obligation)](#4-who-can-use-it-the-non-expert-obligation)
- [5. Non-goals (do not do these)](#5-non-goals-do-not-do-these)
- [6. Exact contracts to create](#6-exact-contracts-to-create)
  - [6.1 The preset — `python/harness/agents.py`](#61-the-preset--pythonharnessagentspy)
  - [6.2 The prompt — `python/harness/prompts.py`](#62-the-prompt--pythonharnesspromptspy)
  - [6.3 The request field — `python/harness/schemas.py`](#63-the-request-field--pythonharnessschemaspy)
  - [6.4 The approval decision — the meat](#64-the-approval-decision--the-meat)
  - [6.5 Task lifecycle — `python/harness/routers/code.py` + `code/tasks.py`](#65-task-lifecycle--pythonharnessrouterscodepy--codetaskspy)
  - [6.6 Front door — `src/lib/harness/code-client.ts` + `src/app/api/code/**`](#66-front-door--srclibharnesscode-clientts--srcappapicode)
  - [6.7 UI — `src/components/screens/code/**`](#67-ui--srccomponentsscreenscode)
  - [6.8 Plain language (non-expert obligation)](#68-plain-language-non-expert-obligation)
- [7. Work items (ordered)](#7-work-items-ordered)
- [8. Deliverables](#8-deliverables)
- [9. Acceptance gates](#9-acceptance-gates)
- [10. Definition of done](#10-definition-of-done)
- [11. Implementation prompt (copy this to OpenCode)](#11-implementation-prompt-copy-this-to-opencode)

## 1. Goal

Give the runtime a **coding agent** — a second `AgentConfig` that owns the code
tools and *not* the finance tools — and a **task lifecycle** (create / resume /
cancel / discard) that a human can supervise at three explicit autonomy levels.

The boundary is the whole point. Autonomy is not a prompt instruction; it is the
**tool allowlist**. At `plan_only` the write tools are *absent from the allowlist
the model is given*, so it cannot call them — not "shouldn't", *cannot*. At
`edit_verify` it gets the full loop inside an isolated worktree and returns a
diff. At `approve_external` it may additionally commit/push/open a PR/deploy —
each gated by a **single-use operator approval bound to the exact action and the
exact workspace**, reusing the proven `mcp/approvals.py` pattern rather than
inventing a second one.

The finance agent gains nothing. README §3.1 holds: one runtime, one registry,
one loop. This phase adds a preset and a policy, not an agent framework.

## 2. Why this phase exists (the problem in the real code)

There is exactly one agent today, and its allowlist is a hardcoded list of 22
read-only tools. From `python/harness/agents.py`:

```python
ECLIPSE_AGENT = AgentConfig(
    id="eclipse-agent",
    name="Eclipse Agent",
    systemPrompt=ECLIPSE_AGENT_SYSTEM_PROMPT,
    tools=[
        # Phase-2 unified retrieval tools
        "market_get_quote", "market_get_ohlcv",
        "fundamentals_get_company_profile", "fundamentals_get_financials",
        "research_search", "research_retrieve_source", "research_search_news",
        "macro_get_series",
        ...
        "session_search", "session_open",
        "memory_search_native", "memory_search_external", "memory_provider_status",
    ],
    maxSteps=8,
    toolTimeoutMs=30_000,
    runTimeoutMs=120_000,
    allowMcpTools=True,
)

AGENT_PRESETS: dict[str, AgentConfig] = {
    ECLIPSE_AGENT.id: ECLIPSE_AGENT,
}

DEFAULT_AGENT_ID = ECLIPSE_AGENT.id
```

The registry enforces that allowlist at the single execution seam
(`graph.py` → `ToolRegistry.execute`, where `TOOL_FORBIDDEN` is returned for a
name outside it). That is the mechanism this phase leans on: **to deny a
capability at `plan_only`, the tool is simply not in the list.**

Two facts make the finance/code separation mandatory rather than stylistic:

1. `allowMcpTools=True` on the default agent. It expands *only* to registered
   `mcp_` tools with a read effect — but a coding agent must not quietly inherit
   that reach, and a finance agent must not quietly inherit code tools. Custom
   agents and skills deliberately do **not** set `allowMcpTools`:

   > Custom agents and skills do NOT set this and keep their exact allowlists.

   The code-agent preset follows that rule exactly.

2. The MCP effect machinery already refuses a non-read tool with no authorizer.
   From `python/harness/tools.py`:

   ```python
   if tool.permission != "read":
       # A non-read tool is refused unless the run explicitly authorizes THIS
       # call (bound to the server/tool/arguments). No authorizer ⇒ refused.
   ```

   The code tools Phase 1–3 registered are effectful. They ride the same gate,
   so `approve_external` has a proven seam to attach to and needs no new one.

The approval shape is the other reason this phase exists. `mcp/approvals.py`
already solved "one operator decision authorizes exactly ONE call" — ADR-H92,
its guard is a single `UPDATE ... WHERE id=? AND status='approved'` with a
rowcount check, its digest is `args_digest(canonicalized validated args)`, its
terminal state is `consumed` + `usedAt`, and its denial is terminal *for that
digest*. Phase 5's external actions are the same problem in a new domain
(external_action on a workspace instead of a server/tool). The roadmap forbids
leaving two half-systems; §6.4 decides it in the ADR.

Finally, the task lifecycle has a foundation already in the tree.
`python/harness/run_lineage.py` (landed 2026-09-30, untracked) provides:

```python
  * `RunCheckpoint` — one bounded row per durable boundary (agent step completed,
    tool result completed, terminal status). The payload is a REFERENCE …
  * `ToolExecutionIdempotency` — one row per executed `(runId, stepIndex,
    toolCallId)`, recording the outcome so a resume REUSES the recorded result
    instead of re-executing a side-effecting call.
```

with `RunCheckpoint`/`ToolExecutionIdempotency` DDL and
`save_checkpoint`/`latest_checkpoint`/`was_tool_executed` already implemented.
README §4 states the consequence directly: *"Phase 5's resume is a consumer of
those primitives, not a builder."* This phase adds **code-specific boundaries** —
after a patch apply, after a command execution — and nothing else.

## 3. In scope

1. A `code-agent` preset in `python/harness/agents.py` whose allowlist contains
   the code tools and **no** finance tool, and which does **not** set
   `allowMcpTools`.
2. A `CODE_AGENT_SYSTEM_PROMPT` in `python/harness/prompts.py`.
3. `RunRequest.autonomy` (+ `workspaceId`), resolved and enforced by
   `code/policy.py` and by the allowlist.
4. The single-use **approval decision** for external actions (commit / push /
   PR / deploy), reusing the `mcp/approvals.py` pattern.
5. A task lifecycle over `run_lineage.py`: create, resume, cancel, discard.
6. A new route group `python/harness/routers/code.py`, registered in `main.py`
   with one `app.include_router(code_router)` line — the only permitted way for
   `main.py` to grow (README §3.7).
7. Front door: `src/app/api/code/**` thin proxies + `src/lib/harness/code-client.ts`.
8. UI: `src/components/screens/code/**` — task list, task detail, plan review,
   diff viewer, check results (from the Phase 4 ledger), worktree actions.
9. An audit surface: every refusal, approval, apply and command appears in the
   run trace.
10. ADR-H107.

## 4. Who can use it (the non-expert obligation)

This capability is **not for engineers and quants**. Every finance professional —
analyst, portfolio manager, trader, advisor, accountant, risk officer, student,
journalist, small-business owner — must be able to use it without knowing Python,
git, worktrees, terminals or what an "allowlist" is. A capability only an engineer
can drive has not shipped.

**The user never sees the machinery.** They state a task in plain language
("check my portfolio for risks overnight") and get a plain result. They never see
the workspace, the policy engine or the checks. The approval machinery is
invisible; it lives in the trace, not on the screen.

**Vocabulary rule.** Every string a non-engineer can see names the *finance job*,
never the mechanism:

| Say | Never say |
|---|---|
| "Just tell me what you'd do" | "plan_only" |
| "Make the change and show me" | "edit_verify" |
| "Do it and ask me before anything outside the app" | "approve_external" |
| "New file: report_generator.py" | "diff", "patch", "tree digest" |
| "Something blocked that step" | "OUTSIDE_WORKSPACE", "SANDBOX_UNAVAILABLE" |
| "Ask the app owner" | "operator authorization" |

Mechanism words — *sandbox, worktree, workspace, allowlist, autonomy, digest,
argv, cwd, stderr, patch, diff, manifest, operator, policy engine, tool registry,
exit code, verification ledger* — stay in logs, events and the run trace. A user
sees them only through a deliberate "details" affordance that quotes the
technical reason verbatim.

**Where the strings live.** The repo already has an i18n layer:
`src/lib/i18n/` — `dictionaries/en.ts` holds the canonical keys,
`dictionaries/index.ts` the translations, `translate.ts` the lookup, `use-t.ts`
the hook. New user-facing copy — including the three autonomy labels — is added
**there as keys**, never hardcoded in a component. Hardcoded copy is
untranslatable and invisible to the jargon gate.

**Refusals a human can read.** A refused action explains, in one plain sentence,
what was blocked and what the user can do, with the technical reason behind a
"details" affordance (the event already carries the `code`):
*"I did not run that — it needs the app owner's OK. Ask them and I'll continue."*
never *"PROFILE_DENIED"*.

**This phase specifically.** The three autonomy profiles are presented as three
plain choices, never as config keys: **"Just tell me what you'd do"**
(`plan_only`), **"Make the change and show me"** (`edit_verify`), **"Do it and
ask me before anything outside the app"** (`approve_external`). A task screen
shows a task, a plain progress line ("Writing the report generator…"), a change
described in everyday words ("New file: report_generator.py"), and a result
("Done. I added it and proved it works with 3 checks."). The worktree, the check
names, `argv` and the digests sit behind "details". This is enforced by a
**jargon gate** — a vitest over the new UI strings and i18n keys,
`src/lib/i18n/plain-language.test.ts`, that fails if a new user-facing string
contains a denylisted mechanism word (see §9).

## 5. Non-goals (do not do these)

- **No second agent loop, registry, model adapter, or approval store.** The
  approval question is *decided* in the ADR (§6.4), not left open.
- **No finance tool on the code agent; no code tool on the finance agent.** The
  allowlist is the boundary; do not "helpfully" widen either.
- **No autonomy above `plan_only` offered by default.** The default stays
  `plan_only`; the operator opts in explicitly.
- **No unsandboxed execution.** `SANDBOX_UNAVAILABLE` (Phase 3) remains an
  honest refusal.
- **No background scheduling or delegation.** That is Phase 6/7 — this phase
  only makes them *possible*.
- **No trading/broker/production verbs.** `FORBIDDEN_PERMISSIONS` is untouched.
- **No new checkpoint mechanism.** `run_lineage.py` is the one mechanism.
- Do not commit, push, or open a PR. Do not commit `jdds.db`.

## 6. Exact contracts to create

### 6.1 The preset — `python/harness/agents.py`

```python
CODE_AGENT = AgentConfig(
    id="code-agent",
    name="Eclipse Code Agent",
    systemPrompt=CODE_AGENT_SYSTEM_PROMPT,
    tools=[
        # Read/navigate (Phase 1)
        "workspace_list", "workspace_read", "workspace_search", "workspace_symbols",
        # Patch (Phase 2) — effectful: only executable under an authorized profile
        "patch_propose", "patch_apply", "patch_revert", "workspace_diff",
        # Command broker (Phase 3) — effectful
        "command_run", "command_status",
        # Git READ only. There is deliberately NO git write tool here: an external
        # action is an approval-gated call, not an allowlisted tool (see §6.4).
        "git_status", "git_diff", "git_log",
        # Verification (Phase 4) — read-only view of the ledger
        "verification_ledger",
        # Memory/session recall stays available: it is read-only context, and a
        # coding agent benefits from prior decisions. It is NOT the finance family.
        "memory", "skill_list", "skill_view", "session_search", "session_open",
    ],
    maxSteps=24,               # a code task legitimately needs more turns than a query
    toolTimeoutMs=120_000,     # a unit-test/build run is slower than a data fetch
    runTimeoutMs=900_000,      # bounded to the Phase 4 repair wall-clock budget
    # Deliberately ABSENT: allowMcpTools. A coding agent must not inherit the
    # operator's MCP reach; the default agent opt-in does not generalize.
)
```

`AGENT_PRESETS` gains one entry; `DEFAULT_AGENT_ID` is unchanged (the finance
agent stays the default for chat).

**The allowlist is a function of the autonomy profile.** The preset above is the
`edit_verify` capability set. `plan_only` is the *same preset* with the write
tools removed by `effective_allowlist` before the model ever sees the schemas:

```python
# python/harness/code/policy.py (extend the Phase 0 module — ONE authority)
WRITE_TOOLS: tuple[str, ...] = (
    "patch_propose", "patch_apply", "patch_revert",   # code.write
    "command_run",                                     # code.execute
)
EXTERNAL_ACTION_TOOLS: tuple[str, ...] = (
    "code_commit", "code_push", "code_open_pr", "code_deploy",   # approve_external only
)

def allowed_tools(autonomy: str, declared: tuple[str, ...]) -> tuple[str, ...]:
    """Narrow a declared allowlist to what the autonomy profile permits.

    plan_only      → write + external tools REMOVED (the model cannot call them)
    edit_verify    → write tools present; external tools REMOVED
    approve_external → everything, but external tools are still effectful and
                       require a per-action single-use approval at execution
    unknown        → the read-only subset (fail-closed, same as code_grants)
    """
    if autonomy == "plan_only":
        banned = set(WRITE_TOOLS) | set(EXTERNAL_ACTION_TOOLS)
    elif autonomy == "edit_verify":
        banned = set(EXTERNAL_ACTION_TOOLS)
    elif autonomy == "approve_external":
        banned = set()
    else:
        banned = set(WRITE_TOOLS) | set(EXTERNAL_ACTION_TOOLS)
    return tuple(t for t in declared if t not in banned)
```

`graph.py`'s `effective_allowlist` (the existing resolution point) calls this once
per run with the resolved autonomy. This is what makes `plan_only` **structural**:
there is no tool schema to call, so a model that "decides" to write cannot.

### 6.2 The prompt — `python/harness/prompts.py`

```python
CODE_AGENT_SYSTEM_PROMPT = """You are the Eclipse Code Agent. You work on a
repository inside an isolated workspace and nothing else.

Rules that are enforced in code, not by you:
- You may only read and write inside the bound workspace. Paths outside it,
  protected paths (databases, .env, migrations, .git, the policy modules) and
  ignored directories are refused before you see them.
- You may only run commands from the allowlisted classes (typecheck, lint,
  unit_test, python_test, build, format_check, git_read). Anything else is
  refused. There is no network.
- A check is passing ONLY if the tool executed it and the exit code was zero.
  Never state that tests, a typecheck, a build or a lint passed unless a tool
  result in this conversation shows it. If you did not run it, say you did not
  run it; the answer is checked against the run's execution ledger and an
  unbacked claim is marked UNVERIFIED to the operator.
- When a check fails, read the output, make ONE focused change, and re-run the
  SAME check. You have a bounded number of repair attempts; when they are spent
  the task stops and reports the failing check, its exit code and its output
  digest. Do not pretend it passed.
- Report honestly what you changed and what you could not do.
"""
```

### 6.3 The request field — `python/harness/schemas.py`

```python
class RunRequest(BaseModel):
    ...
    # ── Code task (Phase 5, additive) ──────────────────────────────────────
    # The autonomy profile governing this run. Absent on an ordinary finance run;
    # a code run without one resolves to "plan_only" (safest, fail-closed).
    autonomy: Optional[str] = None
    # The workspace this run is bound to. A code tool called with no binding is
    # refused (Phase 0: no workspace ⇒ no code permissions, whatever the profile).
    workspaceId: Optional[str] = None  # noqa: N815
```

`RunResult` gains `autonomy`, `workspaceId`, and `codeVerification` (Phase 4's
blob) — all optional so older clients and older rows stay valid.

### 6.4 The approval decision — the meat

`mcp/approvals.py` is the proven pattern; the choice is to generalize it or add a
sibling. **ADR-H107 records the decision — here it is:**

> **Decision.** Generalize the approval *store* into one concept with a `kind`
> discriminator (`"mcp_tool"` | `"code_action"`), rather than adding a second
> `CodeApproval` table. The `McpApproval` table stays the physical home (so
> existing MCP rows need no data migration) and `kind` is an additive column
> defaulting to `"mcp_tool"`. The guarded-claim logic ADR-H92 froze is lifted into
> ONE function used by both kinds. Rejected alternative: a sibling `CodeApproval`
> table — two single-use implementations that can silently drift, exactly the
> "two half-systems" the roadmap forbids.

```python
# python/harness/mcp/approvals.py — unchanged in its existing behaviour.
# The claim primitive is extracted so a code action reuses the EXACT guard.
def claim_guarded(db: Any, *, table: str, kind: str, key_columns: dict[str, Any]) -> Optional[dict]:
    """The ADR-H92 single-use claim, in ONE place.

    A guarded `UPDATE ... WHERE id=? AND status='approved'` plus a rowcount check:
    at most one caller claims a given approval, even under concurrency. The
    `McpApproval` path and the code-action path both call THIS function, so there
    is one implementation of 'single-use', not two.
    """
    ...
```

```python
# python/harness/code/actions.py (new)
"""Operator-gated external actions for a code task (Phase 5, approve_external).

An external action — commit, push, open a PR, deploy — is NEVER run on the
model's say-so. It is an effectful tool whose effect class is `external_action`
and whose authorization is a SINGLE-USE approval bound to the exact
(kind, action, workspace, args-digest), reusing the McpApproval store and the
ONE guarded-claim primitive. A changed action or payload requires a new approval;
a denial is terminal for that digest.
"""
from __future__ import annotations
from typing import Any, Literal, Optional
from pydantic import BaseModel, Field

CodeActionKind = Literal["commit", "push", "open_pr", "deploy"]
CODE_ACTION_KINDS: tuple[str, ...] = ("commit", "push", "open_pr", "deploy")

class CodeActionRequest(BaseModel):
    """The exact action an approval is bound to. `workspaceId` is part of the
    canonicalized payload, so an approval for a commit in workspace A can NEVER
    authorize the same commit in workspace B."""
    kind: CodeActionKind
    workspaceId: str
    argv: list[str] = Field(default_factory=list)
    message: Optional[str] = None        # commit message / PR title
    baseRef: Optional[str] = None        # PR base
    headRef: Optional[str] = None        # pushed branch
    runId: str

def code_action_digest(request: CodeActionRequest) -> str:
    """sha256 over the canonicalized request INCLUDING the workspace id. Reuses
    mcp.approvals.args_digest — the SAME canonicalization, so the two kinds can
    never disagree about what 'the same payload' means."""
    ...

def request_code_action(store: Any, request: CodeActionRequest, *, run_id: str,
                        ttl_seconds: int = 900, action_summary: Optional[str] = None,
                        affected_data: Optional[str] = None) -> dict[str, Any]:
    """Create (or return the existing pending / terminal denial for) a code-action
    approval. Delegates to the shared store with kind='code_action'."""
    ...

def consume_code_action(store: Any, request: CodeActionRequest) -> Optional[dict[str, Any]]:
    """The authorizing operation. Single-use, via the ONE guarded claim."""
    ...

def make_code_action_authorizer(approvals: Any, run_id: str, workspace_id: str,
                                emitter: Any = None) -> Any:
    """The async authorizer attached to ToolContext when the profile is
    approve_external. Resolves the call to a CodeActionRequest (including the
    workspace id), consumes it ONCE, and otherwise refuses — emitting
    code.action.approval_required / code.action.approved. Uses the same
    two-seam digest-scope trick as the MCP authorizer so a legitimate call is not
    double-consumed."""
    ...
```

Table (additive — no data migration):

```sql
-- additive column on the existing McpApproval table (kind defaults to the
-- current meaning, so every existing row is correct without being touched)
ALTER TABLE McpApproval ADD COLUMN kind TEXT NOT NULL DEFAULT 'mcp_tool';
ALTER TABLE McpApproval ADD COLUMN workspaceId TEXT;   -- non-null for code_action rows
```

### 6.5 Task lifecycle — `python/harness/routers/code.py` + `code/tasks.py`

**Reuse `run_lineage.py`; do not build a parallel mechanism.** A "code task" is a
`HarnessRun` (the one run record) plus code-specific checkpoints on the existing
`RunCheckpoint` table.

```python
# python/harness/code/tasks.py (new)
"""Code-task lifecycle over the ONE run lineage.

A task IS a run. Its durable boundaries are RunCheckpoint rows written by
run_lineage.RunLineage (never a new table):
  kind="task.created"     — the bound workspace + the autonomy profile
  kind="plan.accepted"    — the plan the operator accepted (plan_only path)
  kind="patch.applied"    — a patch id + the tree digest AFTER the apply
  kind="command.executed" — the command class + idempotency key + exit code
  kind="task.cancelled"   — the reason, with the worktree released
  kind="task.discarded"   — the branch/worktree removed, nothing kept

Resume reads latest_checkpoint() and REUSES the recorded tool result for any
(runId, stepIndex, toolCallId) already in ToolExecutionIdempotency, so a resumed
task never re-applies a patch and never re-runs a side-effecting command.
"""
```

Checkpoint payloads, bounded exactly like `bound_checkpoint_payload` already
bounds them:

| Boundary | Payload keys | Why the boundary is here |
|---|---|---|
| `task.created` | `workspaceId`, `root`, `baseRevision`, `strategy`, `autonomy` | lets a resume prove it re-enters the SAME workspace |
| `plan.accepted` | `planDigest`, `files: [...]` (bounded), `checkClasses` | a `plan_only` task's deliverable |
| `patch.applied` | `patchId`, `treeDigestAfter`, `files: [...]`, `stepIndex`, `toolCallId` | **so a resume does not re-apply** |
| `command.executed` | `commandExecutionId`, `commandClass`, `exitCode`, `idempotencyKey` | **so a resume does not re-run a side-effecting command** |
| `task.cancelled` / `task.discarded` | `reason`, `worktreeReleased: bool` | proves no orphan worktree was left |

Routes (all thin; each calls a service method and returns its result):

```python
# python/harness/routers/code.py
router = APIRouter(tags=["code"])

# Task lifecycle
POST   /code/tasks                    # create: body {query, autonomy, workspaceId?}; default plan_only
GET    /code/tasks                    # list, bounded, filtered by status
GET    /code/tasks/{id}               # detail: run + latest checkpoint + ledger + diff summary
POST   /code/tasks/{id}/resume        # resume from latest_checkpoint(); CHECKPOINT_NOT_FOUND / RESUME_CONFLICT
POST   /code/tasks/{id}/cancel        # cancel mid-run; releases the worktree; no partial external effect
POST   /code/tasks/{id}/discard       # remove the worktree/branch; keep the run record as audit
POST   /code/tasks/{id}/plan/accept   # operator accepts a plan_only plan → permits an edit_verify re-run

# Workspaces
GET    /code/workspaces               # bound workspaces + baseRevision + strategy
POST   /code/workspaces               # allocate (needs workspace.admin — operator only)

# External actions — approval-gated, single-use
GET    /code/approvals                # pending + decided (kind="code_action")
POST   /code/approvals/{id}/decide    # require_operator; approve | deny
POST   /code/tasks/{id}/actions       # request an external action (commit/push/pr/deploy)

# Observability
GET    /code/tasks/{id}/checks        # the Phase 4 ledger blob, read-only
GET    /code/tasks/{id}/diff          # the worktree diff (bounded)
```

**Operator auth is not optional here.** Every mutating route and every read that
touches a workspace carries the existing dependency:

```python
from .deps import require_operator   # transport/token proof ONLY

@router.post("/code/tasks")
async def create_task(body: CreateTaskRequest, _: bool = Depends(require_operator)) -> dict[str, Any]:
    ...
```

`deps.py` is explicit that a body boolean can never authorize — *"a directly
reachable Python runtime cannot be handed an operator decision by spoofing
`{"operator": true}`"* — and `require_mcp_operator`'s docstring states the same
rule, kept on **reads AND mutations**. `routers/code.py` mirrors the MCP catalog
router: loopback is trusted, a remote caller must present the runtime secret.

`main.py` grows by exactly two lines (import + `include_router`), per README
§3.7. Shared state (`service`, `actor_for`) comes from `deps.py`; the router
never imports `main`.

### 6.6 Front door — `src/lib/harness/code-client.ts` + `src/app/api/code/**`

`code-client.ts` is thin, exactly like `python-client.ts`
(*"the only place Next.js talks to the runtime; it adds no agentic logic of its
own"*). It proxies through `ensurePythonRuntime()` and never constructs a run
itself.

```
src/app/api/code/tasks/route.ts                    GET list, POST create
src/app/api/code/tasks/[id]/route.ts               GET detail
src/app/api/code/tasks/[id]/resume/route.ts        POST
src/app/api/code/tasks/[id]/cancel/route.ts        POST
src/app/api/code/tasks/[id]/discard/route.ts       POST
src/app/api/code/tasks/[id]/plan/route.ts          POST accept
src/app/api/code/tasks/[id]/diff/route.ts          GET
src/app/api/code/tasks/[id]/checks/route.ts        GET
src/app/api/code/approvals/route.ts                GET
src/app/api/code/approvals/[id]/route.ts           POST decide
```

```ts
// src/lib/harness/code-client.ts — the only place Next.js talks to the /code routes;
// it adds no agentic logic (mirrors python-client.ts).
export type Autonomy = "plan_only" | "edit_verify" | "approve_external";
export type TaskStatus =
  | "created" | "planning" | "plan_review" | "editing"
  | "verifying" | "repairing" | "completed" | "failed"
  | "cancelled" | "discarded";

export interface CodeTask {
  id: string; status: TaskStatus; autonomy: Autonomy;
  workspaceId: string | null; query: string;
  plan: CodePlan | null;
  diffSummary: { files: number; additions: number; deletions: number } | null;
  verification: CodeVerification | null;   // the Phase 4 blob
  repair: CodeVerificationRepair | null;
  createdAt: string; updatedAt: string;
}
export interface CodePlan {
  planDigest: string;
  steps: Array<{ id: string; description: string; files: string[] }>;
  citedFiles: string[];          // real paths the runtime resolved — never invented
  checkClasses: string[];
}
```

### 6.7 UI — `src/components/screens/code/**`

Frosted-glass conventions from `.opencode/skills/black-eclipse-ui/SKILL.md`,
sitting beside `research-evidence-panel.tsx` and `run-explanation-panel.tsx`:

| File | Screen |
|---|---|
| `task-list.tsx` | every task, status, autonomy badge, workspace |
| `task-detail.tsx` | the run: plan, diff, checks, audit timeline |
| `plan-review.tsx` | a `plan_only` plan with **cites real files** + Accept / Reject |
| `diff-viewer.tsx` | the worktree diff, bounded, with the tree digest shown |
| `check-results.tsx` | the Phase 4 ledger: executions by class, pass/fail, output digest; **never** "verified" for an unsupported claim |
| `worktree-actions.tsx` | allocate / release / resume / cancel / discard |
| `code-approvals.tsx` | pending external-action approvals, approve / deny, `consumed` visible |

The autonomy badge is **not decorative**: it is rendered from the run's resolved
`autonomy` and, at `plan_only`, the write affordances are not merely disabled —
they are not rendered, because the tools are not in the allowlist.

### 6.8 Plain language (non-expert obligation)

A finance professional picks a task and reads a result; they never meet the
machinery. Concretely:

- **The choice is three plain sentences**, not config keys: *"Just tell me what
  you'd do"* (`plan_only`), *"Make the change and show me"* (`edit_verify`),
  *"Do it and ask me before anything outside the app"* (`approve_external`).
- **The task screen shows a task** — a title in the user's words, a plain
  progress line (*"Writing the report generator…"*), the change in everyday
  wording (*"New file: report_generator.py"*), and a result (*"Done. I added it
  and proved it works with 3 checks."*).
- **A refusal is one plain sentence**: *"I did not run that — it needs the app
  owner's OK. Ask them and I'll continue."* The technical code
  (`PROFILE_DENIED`, `OUTSIDE_WORKSPACE`) sits behind a **"details"** affordance,
  never in the headline.
- **The workspace, checks, `argv`, digests and the worktree are never on the
  screen.** They are behind "details" and in the trace.

Every one of these strings is a key in `src/lib/i18n/dictionaries/en.ts`
(`dictionaries/index.ts` carries translations, `translate.ts` resolves,
`use-t.ts` is the hook) — never hardcoded in a component. The vitest
`src/lib/i18n/plain-language.test.ts` fails the build if a new user-facing string
contains a denylisted mechanism word (see §9 G10).

## 7. Work items (ordered)

1. Create `docs/harness/roadmap/progress/phase-05-progress.md` with §9's gate
   commands as unchecked boxes.
2. Read `python/harness/agents.py`, `prompts.py`, `graph.py`'s
   `effective_allowlist`, `routers/mcp.py` (the router + operator-auth pattern),
   `deps.py`, and `run_lineage.py` **in full** before editing.
3. `schemas.py`: `RunRequest.autonomy` / `workspaceId`; `RunResult` additions.
4. `code/policy.py`: `WRITE_TOOLS`, `EXTERNAL_ACTION_TOOLS`, `allowed_tools()`.
   Do **not** add a second policy table elsewhere.
5. `agents.py`: `CODE_AGENT` + preset registration; export `CODE_AGENT`.
6. `prompts.py`: `CODE_AGENT_SYSTEM_PROMPT` (honest about checks, budgets and the
   workspace boundary).
7. `graph.py` wiring: resolve `autonomy` (absent ⇒ `plan_only`) and
   `workspaceId`; narrow the declared allowlist through
   `policy.allowed_tools(...)`; attach the code-action authorizer when the
   profile is `approve_external`; attach the workspace binding to the `Actor`.
   Keep the change minimal — if `graph.py` cannot absorb it under its ratchet,
   extract the resolution into `graph_context.py`.
8. `mcp/approvals.py`: extract `claim_guarded` from `_claim` so BOTH kinds share
   one guard; add the `kind` / `workspaceId` additive columns; make `request`/
   `find_active` accept `kind`. **Existing MCP behaviour must not change** —
   ADR-H92's tests are the regression suite and must stay green.
9. `code/actions.py` per §6.4; the code-action authorizer and the four effectful
   action tools (`code_commit`, `code_push`, `code_open_pr`, `code_deploy`) —
   each `permission="write"`, `effect="external_action"`, registered only when a
   workspace is bound.
10. `code/tasks.py` per §6.5 — checkpoints via `RunLineage.save_checkpoint`,
    resume via `latest_checkpoint()` + `was_tool_executed`.
11. `routers/code.py` per §6.5 + `main.py`'s two lines.
12. New tests `python/tests/test_code_agent.py`:
    - the allowlist at `plan_only` contains **no** write/external tool and the
      registry returns `TOOL_FORBIDDEN` for `patch_apply` (structural, not
      prompt-based);
    - the allowlist at `edit_verify` contains write tools and **no** external tool;
    - the allowlist at `approve_external` contains the external tools;
    - the finance agent's allowlist is **byte-identical** to before the change and
      contains no code tool, and the code agent's contains no finance tool;
    - the code agent does **not** set `allowMcpTools`;
    - an unknown autonomy value yields the read-only subset.
13. New tests `python/tests/test_code_approvals.py`:
    - a commit without an approval is refused and creates a PENDING request;
    - the same approval cannot authorize a second commit (single-use; the second
      call is refused and a fresh request is created);
    - a changed payload (different message, different `headRef`, different
      `workspaceId`) needs a NEW approval (digest mismatch);
    - a denial is terminal for that digest;
    - an `approve_external` call in the wrong workspace is refused;
    - **the existing ADR-H92 MCP tests are unchanged and still pass.**
14. New tests `python/tests/test_code_tasks.py`:
    - a cancel mid-run leaves no orphan worktree and records no partial external
      effect;
    - a restart mid-task resumes without a duplicate patch apply (assert ONE
      `patch.applied` effect for the step, reusing the recorded idempotency row);
    - a resume with no checkpoint returns `CHECKPOINT_NOT_FOUND`;
    - a resume of a terminal run returns `RESUME_CONFLICT`.
15. `src/lib/harness/code-client.ts`, the `src/app/api/code/**` proxies, and the
    `src/components/screens/code/**` screens per §6.6–5.8 + vitest. **Every
    user-facing string is a key in `src/lib/i18n/dictionaries/en.ts`** — the
    three plain choices, the progress line, the change wording, the result and the
    refusal sentence — never hardcoded in a component. Add
    `src/lib/i18n/plain-language.test.ts` (the jargon gate).
16. ADR-H107 in `docs/harness/decisions.md` (append; the series currently ends at
    ADR-H92) in the **Decision / Why / Consequences** shape — and it MUST decide
    the approval question explicitly (generalize vs sibling), not leave it open.
17. Append the dated `docs/CHANGELOG.md` entry; add the `docs/NAVIGATION.md` row
    for `routers/code.py`, `code/actions.py`, `code/tasks.py` and the UI.

## 8. Deliverables

| File | Change |
|---|---|
| `python/harness/agents.py` | `CODE_AGENT` + preset registration |
| `python/harness/prompts.py` | `CODE_AGENT_SYSTEM_PROMPT` |
| `python/harness/schemas.py` | `RunRequest.autonomy` / `workspaceId`; `RunResult` additions |
| `python/harness/code/policy.py` | `WRITE_TOOLS` / `EXTERNAL_ACTION_TOOLS` / `allowed_tools()` |
| `python/harness/graph.py` (+ `graph_context.py` if needed) | autonomy resolution + allowlist narrowing + actor binding |
| `python/harness/mcp/approvals.py` | `claim_guarded` extracted; `kind` / `workspaceId` additive columns |
| `python/harness/code/actions.py` | new — approval-gated external actions |
| `python/harness/code/tasks.py` | new — task lifecycle over `run_lineage.py` |
| `python/harness/routers/code.py` | new — the `/code/*` route group |
| `python/harness/main.py` | two lines: import + `include_router` |
| `python/tests/test_code_agent.py` | new — the allowlist boundary |
| `python/tests/test_code_approvals.py` | new — single-use, digest-bound, workspace-bound |
| `python/tests/test_code_tasks.py` | new — lifecycle, cancel, resume |
| `src/lib/harness/code-client.ts` + `types.ts` | new / additive |
| `src/app/api/code/**` | new — thin proxies |
| `src/components/screens/code/**` | new — task list, task detail, plan review, diff viewer, check results, worktree actions, approvals; the change wording and the progress/result lines live in the i18n keys |
| `src/lib/i18n/dictionaries/en.ts` (+ `index.ts` if a locale needs it) | new keys for the three choices, the progress line, the change wording, the result and the refusals |
| `src/lib/i18n/plain-language.test.ts` | new — the jargon gate over new user-facing strings |
| `docs/harness/decisions.md` | ADR-H107 |
| `docs/harness/roadmap/progress/phase-05-progress.md` | new — raw gate output |
| `docs/CHANGELOG.md`, `docs/NAVIGATION.md` | per the repo obligation |

## 9. Acceptance gates

Run each from `Black-Eclipse-site/` and paste the **raw output** into the
progress log. A gate not run is a gate not passed.

```bash
# G1 — nothing regressed (includes the ADR-H92 MCP approval tests)
npm run check:all

# G2 — the allowlist boundary is structural
./scripts/vendor/python/python.exe -m pytest python/tests/test_code_agent.py -q

# G3 — a plan_only run cannot call a write tool
PYTHONPATH=python ./scripts/vendor/python/python.exe -c "\
from harness.code.policy import allowed_tools, WRITE_TOOLS, EXTERNAL_ACTION_TOOLS; \
declared=('workspace_read','patch_apply','command_run','code_commit'); \
p=allowed_tools('plan_only', declared); \
print('plan_only allowlist:', p); \
print('no write tool present:', not any(t in p for t in WRITE_TOOLS)); \
print('no external tool present:', not any(t in p for t in EXTERNAL_ACTION_TOOLS)); \
e=allowed_tools('edit_verify', declared); \
print('edit_verify allowlist:', e); \
print('edit_verify has write:', any(t in e for t in WRITE_TOOLS)); \
print('edit_verify has external:', any(t in e for t in EXTERNAL_ACTION_TOOLS)); \
print('unknown autonomy:', allowed_tools('nonsense', declared))"
# expected: plan_only has neither; edit_verify has write but NOT external;
#           unknown autonomy is the read-only subset

# G4 — the finance agent is unchanged
./scripts/vendor/python/python.exe -c "\
from harness.agents import ECLIPSE_AGENT, CODE_AGENT; \
fin=set(ECLIPSE_AGENT.tools); code=set(CODE_AGENT.tools); \
print('finance tool count:', len(fin)); \
print('finance ∩ code:', sorted(fin & code)); \
print('finance has a code tool:', any(t.startswith(('workspace_','patch_','command_','code_')) for t in fin)); \
print('code agent allows MCP:', getattr(CODE_AGENT, 'allowMcpTools', False))"
# expected: finance ∩ code == ['memory','skill_list','skill_view','session_search','session_open']
#           (read-only context shared deliberately); finance has NO code tool;
#           code agent allows MCP: False

# G5 — single-use + digest-bound + workspace-bound approvals
./scripts/vendor/python/python.exe -m pytest python/tests/test_code_approvals.py -q

# G6 — lifecycle: cancel leaves no orphan; resume does not double-apply
./scripts/vendor/python/python.exe -m pytest python/tests/test_code_tasks.py -q

# G7 — the router is registered and operator-gated
./scripts/vendor/python/python.exe -c "\
from harness.main import app; \
paths=sorted({r.path for r in app.routes if r.path.startswith('/code')}); \
print('code routes:', len(paths)); print('\n'.join(paths))"
# expected: the /code/* routes from §6.5 present; every mutating route carries require_operator

# G8 — the whole python suite + the front door
npm run test

# G9 — the vault is untouched
git status --short        # jdds.db must NOT appear; no *.db staged

# G10 — the jargon gate: no new user-facing string names a mechanism
npx vitest run src/lib/i18n/plain-language.test.ts
# expected: passes — every new UI string / i18n key is free of the denylist
#           (sandbox, worktree, workspace, allowlist, autonomy, digest, argv,
#            cwd, stderr, patch, diff, manifest, operator, policy engine,
#            tool registry, exit code, verification ledger)
# The three choices read "Just tell me what you'd do" / "Make the change and show
# me" / "Do it and ask me before anything outside the app"; a change reads
# "New file: report_generator.py"; a result reads "Done. I added it and proved it
# works with 3 checks.".
```

**Pass criteria.** G1 all gates pass (including the unchanged ADR-H92 suites).
G2 green. G3 proves `plan_only` **structurally** lacks every write and external
tool and that an unknown autonomy fails closed. G4 proves the finance agent gained
no code tool and the code agent did not inherit MCP reach — the allowlist *is* the
boundary. G5 proves an unapproved commit is refused, the same approval cannot be
used twice, a changed payload needs a new approval, and a wrong-workspace action
is refused. G6 proves cancel leaves no orphan worktree/partial external effect and
a restart resumes without a duplicate patch apply. G7 lists the routes. G8 green.
G9 shows no `*.db` change. **G10 proves a non-engineer is never shown a mechanism
word** — the three choices, the progress line, the change summary and the result
are plain language, and the worktree/argv/digests live behind a "details"
affordance.

## 10. Definition of done

- Every gate in §9 run, raw output pasted, counts recorded.
- The autonomy profile is enforced by the **allowlist**, not by a prompt: grep
  `policy.allowed_tools` and confirm it is the only place a write/external tool is
  removed, and that `effective_allowlist` calls it before the model sees schemas.
- The finance agent's tool list is byte-identical to the pre-phase list; the code
  agent's contains no finance tool and no `allowMcpTools`.
- There is exactly ONE single-use claim implementation: `claim_guarded` is called
  by both the MCP path and the code-action path (grep for the guarded `UPDATE`).
- ADR-H107 decides the approval question explicitly and names the rejected
  alternative and why.
- Task resume reuses `run_lineage.py` — grep for a second checkpoint table or a
  second idempotency key function and expect none.
- Every refusal, approval, apply and command appears in the run trace (the events
  exist and the UI renders them).
- **Non-expert gate:** the jargon gate passes; the three autonomy choices, the
  progress line, the change summary and the result are plain language; every new
  user-facing string is an i18n key (no hardcoded copy); the mechanism lives only
  behind a "details" affordance and in the trace.
- `main.py` grew by exactly the two permitted lines; its line count is recorded in
  the progress log before and after.
- ADR-H107 written; `docs/CHANGELOG.md` entry appended; `NAVIGATION.md` updated.
- `status:` flipped to `Done` in this file's frontmatter and in the index row.

## 11. Implementation prompt (copy this to OpenCode)

```text
Task: Phase 5 — The coding agent, autonomy profiles and approvals (Eclipse-as-a-Harness roadmap).

Read first, in full:
- docs/harness/roadmap/phase-05-coding-agent.md  (this phase, verbatim)
- docs/harness/roadmap/phase-04-verify-and-repair.md  (the ledger this task renders)
- docs/harness/roadmap/README.md  (invariants §3, work in flight §5, file map §8)
- python/harness/agents.py  (AgentConfig presets + the allowMcpTools rule)
- python/harness/prompts.py
- python/harness/graph.py  (effective_allowlist + the final-answer path)
- python/harness/routers/mcp.py  (the route-group + operator-auth pattern)
- python/harness/deps.py  (require_operator / require_mcp_operator)
- python/harness/run_lineage.py  (checkpoints + idempotency — REUSE, do not rebuild)
- python/harness/mcp/approvals.py  (ADR-H92 single-use approval)
- python/harness/code/policy.py  (the ONE policy authority)

Goal: a code-agent preset whose tool allowlist IS the autonomy boundary, a task
lifecycle over the existing run lineage, and operator-gated external actions that
reuse the ONE single-use approval mechanism.

In scope:
1. schemas.py: RunRequest.autonomy + RunRequest.workspaceId (both optional; a code
   run without an autonomy resolves to "plan_only"); RunResult gains autonomy,
   workspaceId, codeVerification (all optional).
2. code/policy.py: WRITE_TOOLS, EXTERNAL_ACTION_TOOLS, allowed_tools(autonomy,
   declared). This is the ONLY place a write/external tool is removed. An unknown
   autonomy returns the read-only subset (fail-closed).
3. agents.py: CODE_AGENT (id "code-agent") with the tools listed in §6.1, NO
   finance tool, and NO allowMcpTools; register it in AGENT_PRESETS.
4. prompts.py: CODE_AGENT_SYSTEM_PROMPT per §6.2 (checks are proven, not claimed;
   repair is bounded; the workspace is the boundary).
5. graph.py: resolve autonomy (absent ⇒ plan_only) and workspaceId; narrow the
   declared allowlist through policy.allowed_tools before building the model's
   tool schemas; attach the code-action authorizer for approve_external; attach
   the workspace binding to the Actor. Keep graph.py under its ratchet — extract
   into graph_context.py if needed.
6. mcp/approvals.py: extract ONE guarded-claim function (claim_guarded) used by
   BOTH the MCP path and the code-action path; add additive columns kind
   (DEFAULT 'mcp_tool') and workspaceId. Existing MCP behaviour is UNCHANGED —
   ADR-H92's tests are the regression suite.
7. code/actions.py: CodeActionRequest (kind, workspaceId, argv, message, baseRef,
   headRef, runId), code_action_digest (reuse mcp.approvals.args_digest so the
   two kinds agree on canonicalization), request_code_action, consume_code_action,
   make_code_action_authorizer. The action tools (code_commit, code_push,
   code_open_pr, code_deploy) are permission="write", effect="external_action",
   registered only when a workspace is bound.
8. code/tasks.py: the lifecycle over RunLineage.save_checkpoint — boundaries
   task.created / plan.accepted / patch.applied / command.executed / task.cancelled
   / task.discarded. Resume reads latest_checkpoint() and REUSES the recorded tool
   result (was_tool_executed) so it never re-applies a patch or re-runs a
   side-effecting command.
9. routers/code.py: the /code/* routes in §6.5, each mutating route carrying
   require_operator (transport/token ONLY — never a body flag). main.py grows by
   exactly two lines (import + include_router). Reach shared state via deps.py;
   never import main.
10. Tests: python/tests/test_code_agent.py, test_code_approvals.py, test_code_tasks.py
    covering every case in §7.12–6.14, including the negative cases (unknown
    autonomy, wrong workspace, second use of one approval, resume without a
    checkpoint, resume of a terminal run).
11. src/lib/harness/code-client.ts + the src/app/api/code/** proxies +
    src/components/screens/code/** (task list, task detail, plan review, diff
    viewer, check results, worktree actions, approvals) using the frosted-glass
    conventions (.opencode/skills/black-eclipse-ui/SKILL.md) + vitest.
    At plan_only the write affordances are NOT RENDERED (the tools do not exist).
    NON-EXPERT OBLIGATION — every user-facing string is a key in
    src/lib/i18n/dictionaries/en.ts (dictionaries/index.ts carries translations,
    translate.ts resolves, use-t.ts is the hook); never hardcode copy. Present
    autonomy as three plain sentences: "Just tell me what you'd do" (plan_only),
    "Make the change and show me" (edit_verify), "Do it and ask me before
    anything outside the app" (approve_external). The task screen shows a task, a
    plain progress line ("Writing the report generator…"), a change in everyday
    words ("New file: report_generator.py"), and a result ("Done. I added it and
    proved it works with 3 checks."). A refusal is one plain sentence ("I did not
    run that — it needs the app owner's OK. Ask them and I'll continue."), with
    the technical code behind a "details" affordance. The worktree, checks, argv
    and digests are never on the screen. Add src/lib/i18n/plain-language.test.ts:
    a vitest that fails when a new user-facing string or i18n key contains a
    denylisted mechanism word (sandbox, worktree, workspace, allowlist, autonomy,
    digest, argv, cwd, stderr, patch, diff, manifest, operator, policy engine,
    tool registry, exit code, verification ledger).
12. docs/harness/decisions.md: ADR-H107 in the Decision / Why / Consequences
    shape. It MUST decide explicitly: generalize the approval store into one
    Approval concept with a kind discriminator (the chosen option), vs a sibling
    CodeApproval table (the rejected alternative) — and say why.
13. docs/CHANGELOG.md dated entry + docs/NAVIGATION.md rows.

Non-goals (do NOT do these):
- No second agent loop, tool registry, model adapter, checkpoint mechanism or
  approval store.
- Do not widen the finance agent's allowlist; do not give the code agent a finance
  tool; do not set allowMcpTools on the code agent.
- No autonomy above plan_only by default. No background scheduling or delegation
  (Phases 6/7).
- Never weaken trade.execute / broker.modify / production.modify.
- No unsandboxed execution: SANDBOX_UNAVAILABLE stays an honest refusal.
- Never commit, push, or open a PR. Do not commit jdds.db.

Constraints:
- One runtime; the allowlist is the autonomy boundary, never a prompt.
- Operator auth is transport/token only; a body boolean can never authorize.
- Additive persistence only; an older database must open cleanly.
- Keep the file-size ratchets: graph.py, persistence.py, eclipse_memory/store.py,
  main.py. main.py grows ONLY by include_router.

Acceptance gates — run each from Black-Eclipse-site/ and paste the RAW output:
  npm run check:all
  ./scripts/vendor/python/python.exe -m pytest python/tests/test_code_agent.py -q
  PYTHONPATH=python ./scripts/vendor/python/python.exe -c "from harness.code.policy import allowed_tools, WRITE_TOOLS, EXTERNAL_ACTION_TOOLS; d=('workspace_read','patch_apply','command_run','code_commit'); print(allowed_tools('plan_only', d)); print(allowed_tools('edit_verify', d)); print(allowed_tools('nonsense', d))"
     -> plan_only must contain NO write and NO external tool
  ./scripts/vendor/python/python.exe -m pytest python/tests/test_code_approvals.py -q
  ./scripts/vendor/python/python.exe -m pytest python/tests/test_code_tasks.py -q
  ./scripts/vendor/python/python.exe -c "from harness.main import app; print(sorted({r.path for r in app.routes if r.path.startswith('/code')}))"
  npm run test
  npx vitest run src/lib/i18n/plain-language.test.ts   -> the jargon gate passes
     (no new user-facing string contains: sandbox, worktree, workspace, allowlist,
      autonomy, digest, argv, cwd, stderr, patch, diff, manifest, operator,
      policy engine, tool registry, exit code, verification ledger)
  git status --short      -> jdds.db must NOT appear

Finish by stating: "docs updated: <files>" or "no doc change — <reason>".
```

---

**Next:** [Phase 6 — Harness-owned jobs and triggers](./phase-06-jobs-and-triggers.md)
