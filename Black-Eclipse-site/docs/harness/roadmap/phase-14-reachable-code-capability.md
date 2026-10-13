---
title: "Phase 14 — The Code Capability, Reachable From Where the User Is"
status: Done
phase: 14
depends_on: [5, 12]
unlocks: [15, 18]
last-verified: 2026-10-02
---

# Phase 14 — The Code Capability, Reachable From Where the User Is

| | |
|---|---|
| **Depends on** | Phase 5 (the coding agent and its approval model — unchanged here) and Phase 12.5 (the mounted surfaces, which prove the panels render). |
| **Unlocks** | Phase 15 (attachments and produced files are worth a surface of their own once there is somewhere to put them) and Phase 18 (visualisations are artifacts of the same kind). |
| **Estimated work** | 12–16 h of agent time. Front-door + routing work; the runtime's tool set does not change. |
| **Deliverable type** | one classifier module, two new proxy routes, one chat capability panel, one action in the code task list. |
| **Decision records** | ADR-H117 (one way in: the code capability is reached from the conversation, not from a second form) |
| **Prompt to copy** | [§11 below](#11-implementation-prompt) |

---

## Contents

- [1. Goal](#1-goal)
- [2. Why this phase exists](#2-why-this-phase-exists)
- [3. In scope](#3-in-scope)
- [4. Who can use it (the non-expert obligation)](#4-who-can-use-it-the-non-expert-obligation)
- [5. Non-goals (do not do these)](#5-non-goals-do-not-do-these)
- [6. Exact contracts to create](#6-exact-contracts-to-create)
  - [6.1 The classifier (deterministic, in the runtime)](#61-the-classifier-deterministic-in-the-runtime)
  - [6.2 The chat code profile (the allowlist, as data)](#62-the-chat-code-profile-the-allowlist-as-data)
  - [6.3 The front-door contract (additive)](#63-the-front-door-contract-additive)
  - [6.4 The wire shape of the new panel](#64-the-wire-shape-of-the-new-panel)
  - [6.5 Refusal codes (existing strings, no new ones)](#65-refusal-codes-existing-strings-no-new-ones)
- [7. Work items (ordered)](#7-work-items-ordered)
- [8. Deliverables](#8-deliverables)
- [9. Acceptance gates](#9-acceptance-gates)
- [10. Definition of done](#10-definition-of-done)
- [11. Implementation prompt](#11-implementation-prompt)

---

## 1. Goal

A person asks for something built, changed or fixed **in the conversation they are
already in**, and Eclipse does it — using the code capability Phases 0–12 already
built — instead of refusing for lack of a tool, or requiring them to find a
separate screen and fill in a form that no longer exists.

The capability does not grow. What changes is that it becomes **reachable**, that
its refusal is **honest and specific**, and that a work order can be **scheduled**
(Phase 6's job model) rather than only run once, immediately.

## 2. Why this phase exists

The user's report — "Eclipse agent cannot still modify and edit its own code,
cannot create new applications, cannot build algorithms or write good code or test
or run it" — is not a claim that the modules are missing. They exist. The
capability is **unreachable**, in three concrete ways, all verified this session.

**(a) The chat agent has no code tool.** `python/harness/agents.py`:

```python
ECLIPSE_AGENT = AgentConfig(
    id="eclipse-agent", ...
    tools=[ ...18 finance/retrieval/memory tools, plus:
        "delegate",        # Phase 7
        "analysis_run",    # Phase 8 — OFF per run unless the caller enables it
        "scaffold_kit",    # Phase 9
    ],
    allowMcpTools=True,
)
```

27 names, none of which can read a file, apply a change, or run a command. The
system prompt is explicit about the consequence:

> "This agent's registered tool allowlist is its full capability boundary; do not
> claim arbitrary filesystem, shell, code execution, portfolio, broker, or trading
> access."

So the honest answer to "build me X" in chat is a refusal. The modules are
registered on the same registry (`service.py` calls `register_code_tools`), but the
allowlist for this agent removes them before the model ever sees a schema.

**(b) `plan_only` is the only profile anyone reaches, and it is a hard default.**
`python/harness/code/policy.py` removes the write/execute tools for `plan_only`;
`graph.py::resolve_run_policy` forces it for `code-agent` when the request omits an
autonomy; and the front door never sends one. Verified:

```
grep -rn "autonomy" src/lib/harness/run-service.ts src/lib/harness/python-client.ts
# no matches — RunRequestPayload has no `autonomy` field at all
```

The only caller that sets an autonomy is `src/app/api/code/tasks/route.ts`, i.e.
the separate screen. From chat, the code capability is not merely narrower; there
is no path to it.

**(c) The `analysis_run` capability is off from chat and has no control.** Verified:

```
grep -rn "analysisEnabled\|analysis_run" src | wc -l
# 0
```

`RunRequest.analysisEnabled` defaults to `False` and no front-door code sets it, so
even the Phase-8 sandbox — the module that would let Eclipse *compute* a Monte
Carlo rather than describe one — is unreachable from the product. Its own tool
description says "If a needed input is missing, ask — never invent it": the
capability is designed correctly and wired to nothing.

**(d) There is no way to hand the code capability a work order from chat.** The
task list container (`src/components/screens/code/code-screen.tsx`) fetches and
renders tasks; `createCodeTask` exists in the client and **has no caller anywhere in
`src/`**. So a user with a task in mind can look at an empty list and has no button.

**(e) The work order cannot be scheduled.** `jobs.model.JobTarget` already supports
a code job:

```python
class JobTarget(BaseModel):
    kind: JobTargetKind
    skill_id: Optional[str] = None
    objective: Optional[str] = Field(None, max_length=4000)
    agent_id: str = "eclipse-agent"
    workspace_root: Optional[str] = None
    autonomy: Optional[JobAutonomy] = None
    def is_code_job(self) -> bool:
        return self.workspace_root is not None or self.autonomy is not None
```

and the job library ships `Build or fix a finance app` among its seven templates.
Nothing in the chat surface can create one, so the only route to a scheduled code
job is the Jobs screen's editor.

## 3. In scope

1. A **request classifier** in the runtime, not in the prompt: a deterministic
   module that decides whether a chat turn is a coding request, the same way
   `research/mandate.py` decides whether a turn is a research request. It returns a
   typed verdict with a reason; ambiguous turns are **not** coding requests.
2. An **`eclipse-agent` code profile** that is still narrow: the read/navigate set
   plus `workspace_patch_apply`, `workspace_diff`, `workspace_revert`,
   `command_run`, `scaffold_kit` — **no** `code_commit`/`code_push`/`code_open_pr`/
   `code_deploy`. External actions stay on the Code Tasks surface where the
   approval panel lives. Justified by README §3.1 (one runtime, same registry) and
   §3.2 (the allowlist is the boundary).
3. The **front door learns to send a code profile**: `autonomy` and
   `analysisEnabled` on `RunRequestPayload`; `validateRunInput` accepts and validates
   them; `startChatRun` sends the resolved profile.
4. A **chat capability panel** — one new panel in `src/components/chat/` that
   renders, for a chat turn that used the code capability: what was attempted, the
   change, the check result (reusing `ChatCodeVerificationPanel`, the Phase-4
   surface), and the plain-language reason when something was refused.
5. A **"Build this" action** in the code task list that calls the existing
   `createCodeTask` with the existing `/api/code/tasks` contract — no new endpoint,
   no new validation. Plus a **schedule action** that creates a Phase-6 job with
   `JobTarget(kind="objective", objective=…, agent_id="code-agent",
   autonomy="edit_verify")`, using the existing `/api/jobs` contract (created
   **disabled**, per `jobs/templates.py`: "discovery is not activation").
6. Tests: the classifier's labelled cases, the profile's allowlist assertions
   (including a negative that external actions are absent), and the reachability
   guard for the new panel.

## 4. Who can use it (the non-expert obligation)

This is the phase where a non-engineer first asks Eclipse to change software, so the
obligation is at its sharpest. The surface names the **job**:

- The classifier's output is never shown as a category. The user sees *what Eclipse
  will do* ("I'll look at the project, make the change in a copy, and run the
  checks"), not "intent classified as code".
- Autonomy choices already have plain sentences in `en.ts`
  (`code.task.autonomy.planOnly` = "Just tell me what you'd do"). The chat surface
  **reuses those keys**; it does not invent new mechanism words.
- A refusal is one plain sentence plus the next step, mirroring
  `code/commands.py::COMMAND_REFUSAL_COPY` ("That isn't a check I'm allowed to run."
  / "I can run a check for you instead — …"). The technical code rides behind a
  details affordance.
- "I couldn't do this and here's exactly why" is a first-class answer — never a
  silent downgrade to the unconstrained path (README §3.5).
- Every new string is an i18n key under `code.chat.*`; the mechanism denylist
  (`sandbox`, `worktree`, `allowlist`, `autonomy`, `exit code`, …) is asserted by
  the plain-language gates.

## 5. Non-goals (do not do these)

- **The runtime's registered tool set does not change.** No new tool, no new
  permission noun. The phase changes an allowlist and a front-door payload.
- **No external actions from chat.** `code_commit`/`code_push`/`code_open_pr`/
  `code_deploy` are not added to `eclipse-agent` and not surfaced in the chat panel.
- **No second agent loop, no second registry, no TypeScript agent.** The classic
  "just call the model with tools directly from Next.js" is exactly what README
  §3.1 forbids.
- **No LLM-based intent classifier as a gate.** The classifier is deterministic
  code with labelled cases; a model's opinion cannot grant a capability.
- **No auto-enabled job.** A scheduled code job is created disabled, as every
  template is.
- **No change to `code/policy.py`'s frozen constants** (`AUTONOMY_PROFILES`,
  `PROTECTED_PATHS`, `WRITE_TOOLS`). If the work appears to need one, STOP and
  report it.
- Never commit, push or open a PR; do not commit `jdds.db`.

## 6. Exact contracts to create

### 6.1 The classifier (deterministic, in the runtime)

```python
# python/harness/code/request_intent.py
IntentVerdict = Literal["code_change", "code_question", "data_task", "not_code"]

@dataclass(frozen=True)
class CodeIntent:
    verdict: IntentVerdict
    confidence: Literal["certain", "likely"]   # never a float, never shown
    reason: str                                # one sentence, for the trace
    signals: tuple[str, ...]                   # which rules fired

def classify_code_request(query: str, history: list[dict] | None = None) -> CodeIntent:
    """Decide whether a chat turn is a request to CHANGE software.

    Bias: a wrong `code_change` hands the turn a narrow, workspace-confined tool
    set; a wrong `not_code` answers a code request with finance tools and refuses
    honestly. Both are visible, so the classifier prefers `not_code` when the
    turn is ambiguous — the refusal path is the safe failure.

    Rules (deterministic, no model call):
      * a directive verb + a software object in the SAME clause
        (build/create/add/fix/refactor/rename/delete/test/run + file/function/
        component/endpoint/test/script/feature/bug/type error)
      * a pasted path or a stack trace
      * data work (a data verb + a data object) ⇒ `data_task`, which activates
        the analysis sandbox on the ordinary finance surface — additive
      * a follow-up ("do it", "yes go ahead") whose PREVIOUS turn was code_change
        or data_task
      * a question ("how would you…", "what's wrong with…") ⇒ code_question
    """
```

`code_question` is the read-only profile (`workspace_status`, `workspace_list`,
`workspace_search`, `workspace_read`, `workspace_docs`, `workspace_diff`) — the
user asked *about* code, so the answer may read it.

### 6.2 The chat code profile (the allowlist, as data)

```python
# python/harness/agents.py — ADDITIVE. ECLIPSE_AGENT's declared tools are not
# touched; the chat code profile is a NARROWED SET applied per turn.
CHAT_CODE_TOOLS: tuple[str, ...] = (
    "workspace_status", "workspace_list", "workspace_search",
    "workspace_read", "workspace_docs",
    "workspace_patch_apply", "workspace_diff", "workspace_revert",
    "command_run", "scaffold_kit", "analysis_run",
    # read-only context, unchanged from ECLIPSE_AGENT
    "memory", "skill_list", "skill_view", "session_search", "session_open",
    # finance tools stay available: a code change may need the vault for a fixture
    "market_get_quote", "fundamentals_get_financials", "research_search",
)
# Deliberately ABSENT: code_commit, code_push, code_open_pr, code_deploy.
```

Applied where the run's policy is already resolved (`graph.py::resolve_run_policy`,
beside the existing `effective_autonomy` branch), so `plan_only` narrowing still
runs after it and there is one place a profile is computed.

### 6.3 The front-door contract (additive)

```ts
// src/lib/harness/python-client.ts — RunRequestPayload, additive
/** The code profile for this run, when the turn is a coding request. */
autonomy?: "plan_only" | "edit_verify";
/** Phase 8: enable the analysis sandbox for this turn. */
analysisEnabled?: boolean;
```

```ts
// src/lib/harness/validation.ts — accepted + bounded
const PROFILES = ["plan_only", "edit_verify"] as const;   // NOT approve_external
// unknown value ⇒ INVALID_INPUT (fail-closed; never silently defaulted)
```

`startChatRun` sends `autonomy: "edit_verify"` only when the classifier returned
`code_change`, `"plan_only"` for `code_question`, **no autonomy + 
`analysisEnabled: true` for `data_task`** (the finance surface is unchanged),
and `analysisEnabled: true` with the code profile for a quantitative request
(Phase 15 owns that classifier's cases).

> **Extended 2026-10-12 (ADR-H177, R3-01).** The verdict union, the bias rule
> and the front-door mapping above now include `data_task`; the excerpts were
> updated to match the code. See `docs/harness/construction-first-audit.md`.

### 6.4 The wire shape of the new panel

```ts
// src/lib/harness/types.ts — ChatCapabilityView (additive on RunResult)
export interface ChatCapabilityView {
  kind: "code";
  profile: "plan_only" | "edit_verify";
  headline: string;            // i18n KEY (e.g. 'code.chat.headline.editVerify')
  change?: { files: number; digest: string };
  verification?: CodeVerificationView;   // the existing Phase-4 shape, reused
  refusals: Array<{ code: string; reasonKey: string }>;
}
```

Rendered by `src/components/chat/chat-capability-panel.tsx`, which composes the
existing `CodeVerificationPanel` rather than re-rendering its content.

### 6.5 Refusal codes (existing strings, no new ones)

| Code | Source | Surfaced as |
|---|---|---|
| `PROFILE_DENIED` | `code/policy.py` | "this task isn't set up to make that kind of change" (existing copy) |
| `WORKSPACE_UNBOUND` | `code/tools.py` | "there is no project folder to make the change in" (existing copy) |
| `SANDBOX_UNAVAILABLE` | `code/sandbox.py` | the honest no-isolation refusal — never unsandboxed execution |
| `COMMAND_NOT_ALLOWLISTED` | `code/commands.py::COMMAND_REFUSAL_COPY` | existing plain sentence + recovery |

## 7. Work items (ordered)

1. `python/harness/code/request_intent.py` — new: `CodeIntent`,
   `classify_code_request`. Pure, no imports from `graph.py`.
2. `python/tests/test_code_request_intent.py` — the labelled cases FIRST (a wrong
   verdict is a wrong tool set, so the classifier's tests are the risky piece).
3. `python/harness/agents.py` — `CHAT_CODE_TOOLS` + the accessor the resolver uses.
4. `python/harness/graph.py` — apply the chat code profile in `resolve_run_policy`,
   after the existing autonomy narrowing; no new branch elsewhere.
5. `python/harness/schemas.py` — accept `analysisEnabled` (already present) and
   confirm `autonomy` flows from `RunRequest` (it does); nothing new.
6. `src/lib/harness/python-client.ts` + `validation.ts` + `run-service.ts` — the two
   additive payload fields and their validation.
7. `src/lib/harness/chat-capability.ts` — the classifier call + payload assembly on
   the TS side (thin: it calls the runtime's `/code/intent` route, it does not
   re-implement the rules).
8. `python/harness/routers/code.py` — `POST /code/intent` (operator-gated read),
   returning the `CodeIntent` for a query. One route, no state.
9. `src/components/chat/chat-capability-panel.tsx` + the `activity-item.tsx` wiring.
10. `src/components/screens/code/task-list.tsx` — the "Build this" and "Schedule"
    actions, both calling existing proxies.
11. `en.ts` — `code.chat.*` keys; extend the plain-language lists.
12. `docs/harness/roadmap/progress/phase-14-progress.md` — created with the gates
    unchecked, before the work.

## 8. Deliverables

| File | Change |
|---|---|
| `python/harness/code/request_intent.py` | new — the deterministic classifier |
| `python/tests/test_code_request_intent.py` | new — labelled cases incl. the ambiguous ones |
| `python/harness/agents.py` | changed — `CHAT_CODE_TOOLS` (additive) |
| `python/harness/graph.py` | changed — apply the profile in the ONE resolver |
| `python/harness/routers/code.py` | changed — `POST /code/intent` |
| `src/lib/harness/python-client.ts` | changed — additive payload fields |
| `src/lib/harness/validation.ts` | changed — bounded profile validation |
| `src/lib/harness/run-service.ts` | changed — resolve + send the profile |
| `src/components/chat/chat-capability-panel.tsx` | new — the chat surface |
| `src/components/screens/code/task-list.tsx` | changed — Build / Schedule actions |
| `src/lib/i18n/dictionaries/en.ts` | changed — `code.chat.*` |
| `docs/harness/decisions.md` | changed — ADR-H117 |

## 9. Acceptance gates

```bash
# G1 — the classifier's labelled cases (ambiguous ⇒ not_code).
./scripts/vendor/python/python.exe -m pytest python/tests/test_code_request_intent.py -v

# G2 — the profile is exactly the declared set, and external actions are absent.
./scripts/vendor/python/python.exe -m pytest python/tests/test_chat_code_profile.py -v

# G3 — a chat turn with a coding request reaches a WRITE tool; a finance turn does not.
./scripts/vendor/python/python.exe -m pytest python/tests/test_code_reachability.py -v

# G4 — the panel is mounted and every string is a key that passes the gate.
npx vitest run src/components/chat/chat-capability-panel.test.ts \
  src/lib/i18n/plain-language.test.ts
./scripts/vendor/python/python.exe -m pytest python/tests/test_plain_language.py -q

# G5 — nothing forbidden became reachable.
grep -n "code_commit\|code_push\|code_open_pr\|code_deploy" python/harness/agents.py
# expected: only inside the CODE_AGENT list, never CHAT_CODE_TOOLS

# G6 — the full release gate, and the production build for the new client surface.
npm run check:all && npm run build
```

| Gate | Assertion |
|---|---|
| G1 | The labelled set passes, including: "what's the price of AAPL" ⇒ `not_code`; "how do the checks work here" ⇒ `code_question`; "add a drawdown recipe and run the tests" ⇒ `code_change`; "do it" after a `code_change` turn ⇒ `code_change`; "do it" after a finance turn ⇒ `not_code`; "build me a report" (no software object) ⇒ `not_code`. |
| G2 | `CHAT_CODE_TOOLS` equals the §6.2 set; the four external actions are asserted **absent**; the profile is asserted to be a strict subset of what `code.policy.allowed_tools("edit_verify", …)` permits. |
| G3 | A code-change turn's bound tool schemas contain `workspace_patch_apply` and `command_run`; a finance turn's do not; a `code_question` turn has read tools and no write tool. This is the gate the user's complaint is about — assert the bound set, not the prompt. |
| G4 | The panel is imported by `activity-item.tsx` (reachability guard), every string it renders is an i18n key, and no key contains a denylisted word. |
| G5 | External actions appear nowhere outside `CODE_AGENT`/`policy.EXTERNAL_ACTION_TOOLS`. |
| G6 | `ALL GATES PASSED` and `npm run build` exits 0 — a client component importing a server-only module is a 500 on `/` and is caught by no static gate. |

**A gate not run is a gate not passed.** Paste the raw output of each into
`docs/harness/roadmap/progress/phase-14-progress.md`.

## 10. Definition of done

- A coding request typed in chat results in a bound tool set containing write and
  execute tools, and a finance request's does not — proven by G3 against the bound
  schemas.
- The classifier is deterministic, in the runtime, and its ambiguous case is
  `not_code`.
- No external action is reachable from chat; the Code Tasks surface keeps them.
- A work order can be started and scheduled from the task list using the existing
  `/api/code/tasks` and `/api/jobs` contracts; the created job is disabled.
- ADR-H117 written; changelog entry appended; NAVIGATION rows 65 and 62 updated;
  `status:` and the index row flipped; the progress log carries the raw gate output.

## 11. Implementation prompt

```text
Task: Phase 14 — make the code capability reachable from chat.

Read first, in full:
- docs/harness/roadmap/phase-14-reachable-code-capability.md (this file, verbatim)
- docs/harness/roadmap/README.md (§3.1 one runtime, §3.2 prose is not a boundary,
  §3.5 zero-config honesty, §6 non-goals)
- python/harness/{agents.py,graph.py,tools.py,schemas.py,code/policy.py,code/tools.py}
- python/harness/research/mandate.py (the deterministic-classifier pattern to mirror)
- src/lib/harness/{run-service.ts,python-client.ts,validation.ts,code-browser.ts}
- src/components/chat/{activity-item.tsx,code-verification-panel.tsx}
- src/components/screens/code/{code-screen.tsx,task-list.tsx}

Goal: a coding request made in ordinary conversation is served by the code
capability that already exists, with a narrow profile, an honest refusal, and no
external action — and a work order can be started or scheduled from the task list.

In scope:
1. New python/harness/code/request_intent.py: CodeIntent + classify_code_request,
   deterministic, ambiguous ⇒ not_code (§6.1). Tests FIRST.
2. agents.py: CHAT_CODE_TOOLS as data (§6.2). Do NOT modify ECLIPSE_AGENT's list or
   CODE_AGENT's list.
3. graph.py: apply the chat code profile inside the EXISTING resolve_run_policy, after
   the autonomy narrowing. One place, no new branch.
4. routers/code.py: POST /code/intent (operator-gated read) returning CodeIntent.
5. Front door: additive `autonomy` (plan_only|edit_verify only) and `analysisEnabled`
   on RunRequestPayload; validate with fail-closed rejection of any other value;
   startChatRun resolves and sends them from the classifier.
6. src/components/chat/chat-capability-panel.tsx composing the existing
   CodeVerificationPanel; wire it into activity-item.tsx.
7. task-list.tsx: "Build this" (existing createCodeTask) and "Schedule" (existing
   /api/jobs, created DISABLED with agent_id="code-agent", autonomy="edit_verify").
8. en.ts code.chat.* keys + the plain-language lists.

Non-goals (do NOT do these):
- No new tool, no new permission noun, no change to the registered set.
- code_commit / code_push / code_open_pr / code_deploy must NOT reach eclipse-agent
  or the chat panel.
- No LLM classifier as a gate; the classifier is deterministic code.
- No second agent loop/registry, and no TypeScript agent loop.
- No auto-enabled job.
- Do NOT modify AUTONOMY_PROFILES, PROTECTED_PATHS or WRITE_TOOLS in
  python/harness/code/policy.py. If the work seems to need one, STOP and report.
- Never commit, push or open a PR. Do not commit jdds.db.

Constraints:
- Measure before implementing: if a claim here is already true in the tree, say so
  and skip it. A corrected audit is a valid outcome.
- Every user-facing string is an i18n key; the mechanism denylist applies.
- Do not weaken an existing test; name every changed expectation with old and new.

Acceptance gates — run each from Black-Eclipse-site/ and paste the RAW output into
docs/harness/roadmap/progress/phase-14-progress.md:
  ./scripts/vendor/python/python.exe -m pytest python/tests/test_code_request_intent.py -v
  ./scripts/vendor/python/python.exe -m pytest python/tests/test_chat_code_profile.py -v
  ./scripts/vendor/python/python.exe -m pytest python/tests/test_code_reachability.py -v
  npx vitest run src/components/chat/chat-capability-panel.test.ts src/lib/i18n/plain-language.test.ts
  ./scripts/vendor/python/python.exe -m pytest python/tests/test_plain_language.py -q
  grep -n "code_commit\|code_push\|code_open_pr\|code_deploy" python/harness/agents.py
  npm run check:all && npm run build

Finish by stating: "docs updated: <files>" or "no doc change — <reason>", plus one
honest non-property: what you did NOT verify.
```

---

**Next:** [Phase 15 — Attachments In, Files Out](./phase-15-attachments-and-artifacts.md)
