---
title: "Phase 22 - Self-Hosting: using Eclipse to build Eclipse"
status: Active (S1 shipped)
phase: 22
depends_on: [5, 10, 14, 15, 17, 19, 20]
unlocks: []
last-verified: 2026-11-05
---

# Phase 22 - Self-Hosting: using Eclipse to build Eclipse

**What this is.** The plan that turns "Eclipse *can* edit its own code" into
"Eclipse is the harness I use to build Eclipse". The machinery is already here:
phases 0-21 shipped, and Round 4 scores the harness at **9.01 / 9.50** against
the 2026 field. The remaining gap is not capability. It is **dogfooding**: the
few things a harness needs when the repository it edits is the repository it is
running from.

**Who this is for.** The operator who wants to stop switching to OpenCode /
Claude Code / Codex to change Eclipse, and every user who should get the same
experience for their own project.

**Status.** `Draft` - written from the merged tree on 2026-11-05. Every gap
below is read out of the source or measured, not recalled.

---

## Progress

| Workstream | State | Evidence |
|---|---|---|
| S1 Project memory | **Shipped 2026-11-05** | `python/harness/code/project_memory.py`, `python/tests/test_project_memory.py`, first-turn wiring in `graph_context._repo_map_context`, the read-only `project_rules` tool |
| S2 Durable build session | Not started | - |
| S3a Builder/target boundary | Not started | - |
| S3b Maintenance mode | Not started | - |
| S4 Land pipeline | Not started | - |
| S5 Builder surface | Not started | - |
| S6 Model roles + scorecard | Not started | - |

## 0. How the reference harness does it (and what is actually transferable)

Anthropic dogfoods Claude Code: its engineers run the same agent they ship,
inside the same repository, with the project's own rules loaded, the project's
own tests as the judge, and a human review before merge. Anthropic has said
publicly that Claude writes a large share of Claude Code's own code. The
transferable pattern is not a secret self-modifying loop. It is six ordinary
ingredients:

| Ingredient | What it means in practice |
|---|---|
| **Repo-native agent** | the agent runs where the code is; no copy/paste bridge |
| **Project memory** | `CLAUDE.md` / `AGENTS.md` is loaded automatically, so house rules are always in context |
| **Real tools** | read, search, patch, run tests, run a build, drive git, inspect a running app |
| **A judge, not a claim** | the test/build exit code decides; the model's sentence does not |
| **Human review** | a diff, a plan, a single decision, and a rollback |
| **Iteration** | evals, failure mining, prompt/tool fixes, then dogfood again |

Eclipse has ingredients 1, 3, 4 and 5 to a high standard. It is missing 2 (the
automatic project memory), and it has not yet assembled 1-6 into one loop that
is pleasant enough to replace the external harness. That is this phase.

**Honest framing.** Claude does not "build itself" autonomously. Engineers run
the agent, review the diff, and merge. Eclipse should target exactly that, not
an unsupervised loop. The repo's own non-goal still holds: no unsupervised
self-modification.

---

## 1. What already exists (the sockets - do not rebuild)

| Layer | Where | State |
|---|---|---|
| Autonomy profiles as a structural boundary | `python/harness/code/policy.py` (`allowed_tools`) | Done |
| Worktree edits, patch primitive, stale guard | `code/worktree.py`, `code/patch.py`, `code/fs/` | Done |
| Promotion, digest-bound approval, rollback | `code/promotion.py`, `routers/code.py` | Done |
| Self-host gate (restart / build flag / authority refusal) | `code/selfhost.py` | Done |
| Verify-and-repair in the graph, claim classes | `code/verify.py`, `code/repair.py`, `graph.py` | Done |
| Repo map + seeded slice | `code/intel/repo_map.py`, `graph_context.py` | Done |
| Compaction + lazy tool loading | `compaction.py` | Done |
| Code tasks, checkpoints, resume | `code/tasks.py`, `run_lineage.py` | Done |
| Jobs, delegation, parallel children | `jobs/`, `delegation.py` | Done |
| Terminal, runtimes, packages, browser, computer use | `code/terminal*`, `execution/`, `runtime/`, `browser/` | Done |
| Project rules *as a review report* | `code/review.py` (6 advisory rules) | Partial |
| Code screen, diff viewer, checks, approvals | `src/components/screens/code/**` | Done |
| Chat code surface (`/eclipsesdk`, classifier) | `agents.py::CHAT_CODE_TOOLS`, `code/request_intent.py` | Done |
| Evaluation, gates, benchmarks | `evaluation/`, `eval_gates/` | Done |

So the plan does **not** add an agent loop, a tool registry, a second approval
store, or a second checkpoint mechanism. It adds the missing connectors and the
surface that makes the loop the default.

---

## 2. The gap ledger - nine things that stop dogfooding

### D1. Project memory is not loaded (the largest gap)

A grep for `AGENTS.md` under `python/harness/` returns only `code/review.py`
advisory strings. No prompt or context builder loads the repo's house rules.
`CODE_AGENT_SYSTEM_PROMPT` is generic: it knows checks and boundaries, not that
this repo requires a `CHANGELOG.md` entry for every change, `npm run test` +
`npx tsc --noEmit`, the frosted-glass UI system, the size ratchet, or that
`docs/NAVIGATION.md` is the update trigger table.

**Consequence.** The agent rediscovers the rules by accident, or violates them.
That is the difference between a competent contractor and a new hire.

### D2. No durable build session

A chat coding turn is bounded by `chat_step_budget` (24 steps, ceiling 32) and
`run_timeout_s >= 600` (`graph.py:191-217, 434-438`). A code task is 24 steps
and 600s. Real work frequently needs 50-200 tool calls and longer wall-clock.
There are checkpoints, resume and compaction, but there is no object that says
"this is one build, continue it tomorrow".

**Consequence.** The user learns to split work into chunks the harness can
survive, which is exactly the tax that sends them back to OpenCode.

### D3. The builder and the target are the same process

The Python runtime executes the agent and runs the code being edited. Landing a
`python/harness/**` change requires a restart, and a restart kills the run that
produced it (deferred while runs are in flight, per `selfhost.py` and
`runtime-supervision.ts`). The Next front door survives, the conversation can
continue, but the in-flight turn cannot.

**Consequence.** Self-hosting works for small turns and gets awkward for the
long ones where it would pay off most.

### D4. The authority wall has no door

`selfhost.AUTHORITY_PATHS` refuses live edits to `code/policy.py`,
`code/authorizers.py`, `mcp/approvals.py`, `skills/permissions.py`, and
`Phase 10` freezes `scripts/check-all.js`. That refusal is correct. But there is
no supported "I am the operator, take the app offline, change the policy, prove
it, bring it back" path. The refusal says no, not "here is how".

**Consequence.** Eclipse can improve everything about itself except the rules
that govern it - which is the first thing a serious operator eventually needs.

### D5. Landing is not a release pipeline

Promotion applies files; `buildRequired` is a **note** in the card
(`promote-change.tsx:219`), not a build. The full repo gate (`npm run test`,
`npx tsc --noEmit`, targeted pytest, size budget, secret scan, docs obligation)
is not run as part of landing. `code_commit` / `code_push` / `code_open_pr`
exist but only on the Code surface, not in a chat turn.

**Consequence.** "It landed" and "it is good" are different facts, and the user
has to bridge them by hand - which is the external harness's job today.

### D6. Review is all-or-nothing

One preview, one digest, one approval, one rollback unit for the whole file set.
No per-file or per-hunk decisions, no line comments, no "request changes" that
becomes the next turn. The diff and check output are present but the review is
not conversational.

**Consequence.** A 12-file change is approved as a blob or rejected as a blob.

### D7. No coding-specific model policy or role split

The model router exists, and `/eclipsesdk` can pick a provider/model through the
settings vault, but nothing says "use the strongest tool-calling model for a
build", and there is no planner / editor / reviewer split. A 9.0 harness driven
by a weak model still performs weakly.

**Consequence.** Quality varies with whatever chat model is selected, and the
user cannot see or tune it.

### D8. Self-builds are not measured

Evaluation measures capability classes and benchmark tasks. Nothing measures
"self-edits that landed and stayed landed", rollback rate, time-to-first-diff,
or how much a human had to repair the agent's work.

**Consequence.** The claim "Eclipse can build Eclipse" stays an anecdote.

### D9. The default surface is still finance-first

The Code screen is capable but separate; `/eclipsesdk` is obscure; a coding
request only reaches the code profile if the deterministic classifier recognizes
it (`request_intent.py`), and an ambiguous turn stays on the finance surface.
There is no first-class Builder surface that a user would choose over an
external terminal.

**Consequence.** Even when the machinery works, the product does not invite the
workflow.

---

## 3. The plan - six workstreams, three waves

### Wave A - make it trustworthy (P0)

#### S1. Project memory: load the house rules (D1)

**Contract.** A bounded, deterministic loader with one job: put the project's
own rules into the first turn, and name where they came from.

```python
# python/harness/code/project_memory.py (new)
@dataclass(frozen=True)
class ProjectRules:
    sources: tuple[str, ...]        # repo-relative paths actually read
    text: str                       # rendered, budget-bounded
    digest: str                     # sha256 of text
    truncated: bool
    missing: tuple[str, ...]        # named, never silent

def load_project_rules(root: Path, *, budget_chars: int) -> ProjectRules:
    """Priority order, first match wins per section, never raises.

    1. <root>/AGENTS.md
    2. <root>/.eclipse/instructions.md      (project override)
    3. <root>/CLAUDE.md                     (compatibility)
    4. <root>/docs/NAVIGATION.md            (only the update-trigger table)
    """
```

Rules:

- **Bounded.** One shared budget from `code/intel/context.py`, split across
  sources; a truncated block says so.
- **Deterministic.** Same files -> same digest -> same block. No model call.
- **Never a boundary.** Rules are context, not permission. A rule that says
  "you may push" cannot grant a push.
- **Cache, not authority.** Cache by `(path, mtime, size)` under
  `<repo>/.black-eclipse/project-rules/`. A changed file is re-read.
- **No secrets.** Reuse the existing redaction path; a `.env` is never a source.

**Wiring.**

- `graph_context.py`: a new `_project_rules_context(...)` adjacent to
  `_repo_map_context`, included on code turns only (an autonomy is present).
- `code/tools.py`: a read-only `project_rules` tool so the agent can re-read
  after a change; add it to `CHAT_CODE_TOOLS` and `CODE_AGENT_TOOLS`.
- `prompts.py`: one paragraph in `CODE_AGENT_SYSTEM_PROMPT` - the project rules
  are the project's, and a conflict between a rule and the enforced floor is
  resolved by the floor.

**UX.** A "Project rules" chip on the Builder surface: `AGENTS.md + NAVIGATION`,
"view", "refresh". Plain language, machinery behind details.

**Gates.** Missing file -> empty block, no error. 200 KB file -> truncated at the
budget, marked. Changed file -> new digest. A secret-looking token is redacted.
No rule changes an allowlist.

#### S2. A durable build session (D2)

**Contract.** One object that survives turns, restarts and days.

```python
# python/harness/code/session.py (new)
@dataclass
class BuildSession:
    id: str
    goal: str                      # the user's words
    acceptance: list[str]          # what "done" means, checkable
    plan: list[PlanStep]           # ordered, bounded, each with files
    status: Literal["planning", "editing", "checking", "waiting_on_user",
                    "done", "blocked", "cancelled"]
    budget: SessionBudget          # steps, wall-clock, tokens, cost
    workspace_id: str
    base_revision: str
    last_checkpoint: str | None
```

- **Reuse, do not rebuild.** A session is a `HarnessRun` plus `RunCheckpoint`
  rows (the `code/tasks.py` pattern) plus a plan. `run_lineage.py` stays the one
  checkpoint mechanism; `compaction.py` stays the one compactor.
- **Budget ladder, explicit.** `small` (≤ 24 steps / 10 min), `standard`
  (≤ 80 / 45 min), `deep` (≤ 240 / 3 h). The ladder is data in one table; the
  operator can cap it. Exceeding it degrades to "checkpoint and ask", never a
  silent `MAX_STEPS_EXCEEDED`.
- **Resume.** `POST /code/sessions/{id}/resume` continues from the last
  checkpoint; `ToolExecutionIdempotency` means no double patch and no double
  command.
- **Compaction.** When context crosses the model's window, compact with the
  existing path; a deterministic fallback always exists; the session records
  that it compacted.
- **One thread.** The chat can attach to a session id; the next message
  continues the same plan instead of starting a new turn.

**UX.** "Continue build" on the Builder surface; a plan checklist that persists;
a resume banner after a restart ("Picking up where we stopped - 3 of 7 steps
done").

**Gates.** A 60-step fixture session resumes after a forced process restart with
exactly one patch apply per step. A budget-exhausted session checkpoints and
reports the next step, not `MAX_STEPS_EXCEEDED`. A compaction event preserves
the goal, the acceptance list and the open failing check.

#### S3. Separate the builder from the target (D3) and open the authority door (D4)

**S3a - the process boundary.**

The target is already two processes (Next front door + Python runtime). Make the
boundary explicit:

- **Builder runtime** = the Python process that runs the agent.
- **Target app** = the dev server (`npm run dev`, separate ports) or the prod
  server (`npm run start`).
- A landed change to `python/harness/**` restarts **only the builder**; a landed
  change to `src/**` rebuilds **only the target**. The user's chat lives in the
  front door, which survives both.
- **Land on a boundary.** A self-edit lands when the run reaches a safe
  boundary (a completed turn or an accepted checkpoint), never mid-tool-call.
  `selfhost.guarded_land` keeps its refuse/apply/restart/verify/rollback order.
- **Health evidence.** After restart: `/health`, one tool call, one model
  round-trip. Failure -> automatic rollback, and the session says so.

**S3b - maintenance mode for authority files.**

A deliberate, offline path - not a hot swap:

```text
npm run self:maintenance -- --preview <id>
```

1. refuses unless the tree is clean and the operator types the change id;
2. stops the builder runtime (the agent is not running while its judge changes);
3. applies the preview;
4. runs the full gate (`npm run test`, `npx tsc --noEmit`, targeted pytest,
   size budget, secret scan);
5. restarts with `scripts/doctor.js` and health-checks;
6. rolls back atomically on any failure, and says which gate failed.

The UI's authority refusal becomes: *"That file is one of the rules Eclipse
checks itself against, so it cannot be changed while the app is running. Here is
the maintenance step."* - one plain sentence plus the next action.

**Gates.** A runtime edit restarts only the builder and the chat survives. A
front-end edit is built before it is reported landed. An authority edit through
the live path is refused with the maintenance instruction. A failed gate rolls
back and leaves the tree byte-identical. Recovery from a deliberately broken
harness file ends in a healthy app with the previous file restored.

### Wave B - make it a pleasure (P1)

#### S4. Landing is a pipeline, not a copy (D5)

**Contract.** One ordered, visible pipeline per landing.

```python
# python/harness/code/land.py (new)
@dataclass(frozen=True)
class LandCheck:
    id: str
    label: str                 # plain words for the UI
    command: tuple[str, ...]   # fixed argv; nothing model-supplied
    required: bool
    timeout_s: int

def default_checks(root: Path) -> list[LandCheck]:
    """Data, not code: .black-eclipse/land.json overrides the defaults."""
```

Default order:

1. `npx tsc --noEmit`
2. targeted `pytest` for touched Python packages (derived from the diff)
3. `npm run test` (or the affected vitest files)
4. `npm run check:size`
5. `npm run check:secrets`
6. `npm run build` when `src/**` changed
7. docs obligation: a dated `CHANGELOG.md` entry, or a stated reason

Rules:

- **The exit code is the judge.** `run_verification` records each check in the
  existing ledger; the UI renders "3 of 5 checks passed", never "verified"
  without evidence.
- **Stop at the first required failure.** Show the failing line, offer "let the
  agent repair it" as the next turn.
- **No silent skip.** A check that cannot run is `failed` with a reason.
- **Git stays approval-gated.** `code_commit` / `code_push` / `code_open_pr`
  remain `external_action` with a single-use approval; expose them in the
  Builder surface, not only the Code screen. Local branch/commit is allowed at
  `edit_verify`; push/PR never without the approval.

**UX.** A check list with live states (queued / running / passed / failed /
skipped), the command behind "details", and a **Land** button that is disabled
until the required checks pass. "Land" = apply + restart/build + health +
rollback, one decision.

#### S5. One Builder surface (D9)

Reuse the Code screen and the chat; do not create a fourth editor.

**The surface.** A `Builder` mode with a three-pane layout:

```
+----------------------+--------------------------------+-------------------+
| sessions / plans     | conversation + plan checklist   | diff / checks     |
| (left)               | (center)                        | (right, tabbed)   |
+----------------------+--------------------------------+-------------------+
```

- **Center**: the conversation, with the plan as a live checklist ("Read the
  route", "Add the widget", "Run checks") and one honest state machine:
  `planning -> editing -> checking -> waiting on you -> done | blocked`.
- **Right**: tabs for **Changes** (per-file diff), **Checks** (the pipeline),
  **Preview** (the running app, when it has one), **Details** (the trace).
- **Left**: sessions, so "continue yesterday's build" is one click.
- **Per-file / per-hunk review** (D6): accept, reject, or comment on a line.
  A comment becomes a follow-up turn with the file and line attached.
- **Every refusal has a next action.** "That file is protected" -> "open
  maintenance", "this needs your OK" -> "review the action".
- **Fast feedback.** Stream tool activity as it happens; no spinners that hide
  what is being run; a step counter and elapsed time.
- **Take me there.** Every cited file/line is a deep link; the app opens it.
- **Undo is always visible.** Landed changes keep a rollback id and an "Undo
  this build" action.

**Wiring.** Extend `src/components/screens/code/**` and the mounted tab; add
`sessionId` to `run-service.ts`; add `src/app/api/code/sessions/**` proxies; all
copy as i18n keys. Frosted-glass classes only (`.opencode/skills/black-eclipse-ui/SKILL.md`).
The plain-language gate covers the new strings.

**Non-goal.** No Monaco-based full editor in this phase; the diff view and the
external editor remain the editing surfaces.

#### S6. Coding model policy, roles, and self-build measurement (D7, D8)

- **Roles.** Resolve three optional roles from settings: `code.planner`,
  `code.editor`, `code.reviewer`; fall back to the chat model. The router's
  existing `modelPolicy` seam is the only place this is decided (no second
  router).
- **A coding profile.** A named profile ("Best for building") that prefers
  tool-calling strength, a large context window, and a provider with reliable
  structured output. It is a setting, not a hard-coded model id.
- **Self-build scorecard.** Derive from existing runs + landings: landed,
  rolled back, human edits after landing, checks passed first time, steps,
  tokens, cost, time-to-first-diff. Render `UNKNOWN`, never `0`, where a
  dimension is unmeasured. One dashboard widget, no new store.
- **A small repo eval.** 6-10 real self-build tasks ("add a settings toggle",
  "fix a named failing test", "add a docs row"), each with a deterministic
  acceptance check and a human diff grade. Run it before a release; publish the
  number with provenance.

### Wave C - make it the default (P2)

- `npm run self:build` / a desktop shortcut that opens the Builder surface on
  the app's own repo.
- An onboarding card: "Build Eclipse with Eclipse" with the model requirement,
  the workspace, and the first safe task.
- Keep a documented fallback: the first month still keeps a terminal, because
  authority changes and bootstrap recovery need it. Say so honestly.

---

## 4. What "best experience" means here (the product rules)

1. **One place.** Session, conversation, plan, diff, checks, preview and undo
   live together. No tab-hopping to understand one change.
2. **One decision that matters.** Approve a reviewable change, not 14 prompts.
   Everything else is automatic or behind details.
3. **Reversible by default.** Every landing has a rollback id; every session can
   be resumed or cancelled without orphaning a workspace.
4. **Honest state.** The UI never says "verified" without a recorded check, never
   says "done" while a required check is red, and never hides a skipped check.
5. **No dead ends.** A refusal is one plain sentence plus the next action, with
   the machine code behind "details".
6. **You keep your place.** Restart, close the laptop, come back: the session,
   the plan and the failing check are still there.
7. **Explain, don't perform.** "Why this file" cites the path and line; "why
   this failed" quotes the output.
8. **Progressive disclosure.** Plain language first; worktree, digest, argv and
   ledger behind "details".
9. **Fast.** First useful activity in seconds; checks stream; no silent waiting.
10. **Safe.** Worktree by default, authority wall intact, no autonomous merge,
    no fabricated success.

---

## 5. What we deliberately do not do

- **No unsupervised self-modification.** No candidate activates or lands itself.
  Every landing is an operator decision.
- **No live authority hot-swap.** Authority files change only in maintenance
  mode, offline, with the full gate and rollback.
- **No second agent loop, tool registry, approval store or checkpoint table.**
  Sessions reuse `HarnessRun` + `run_lineage.py`; approvals reuse the one store;
  verification reuses `code/verify.py`.
- **No widening of the autonomy floor.** The allowlist stays the boundary.
- **No LLM judge as a gate.** It may explain; a deterministic check decides.
- **No auto-commit/push/PR.** External actions stay single-use approved.
- **No unbounded budget.** A session that exceeds its ladder checkpoints and
  asks; it never burns silently.
- **No fourth editor surface.** Extend the Code screen.

---

## 6. Work items (ordered)

1. `docs/harness/roadmap/progress/phase-22-progress.md` with the gates below as
   unchecked boxes.
2. Read in full: `code/selfhost.py`, `code/promotion.py`, `code/tasks.py`,
   `graph_context.py`, `graph.py` (`chat_step_budget`, `_repo_map_context`),
   `compaction.py`, `run_lineage.py`, `routers/code.py`, `routers/code.py`'s
   front-door proxies, `src/components/screens/code/**`,
   `src/components/chat/promote-change.tsx`, `scripts/doctor.js`,
   `scripts/lib/profiles.js`.
3. **S1**: `code/project_memory.py` + `test_project_memory.py` + the
   `graph_context.py` wiring + the `project_rules` tool + prompt paragraph.
4. **S2**: `code/session.py` + `test_build_session.py` + the `sessionId` request
   field + resume route + budget ladder table + compaction assertion.
5. **S3a**: `scripts/lib/self-build.js` (builder/target split and land-on-boundary)
   + the restart/survive test; **S3b**: `npm run self:maintenance` +
   `test_authority_maintenance.py` (refuse live, apply offline, roll back on a
   failed gate).
6. **S4**: `code/land.py` + `test_land_pipeline.py` + the UI check list.
7. **S5**: the Builder surface (extend `screens/code/**`), per-file review,
   `sessionId` in `run-service.ts`, the session proxies, i18n keys + the
   plain-language gate.
8. **S6**: role resolution in `models.py` + the coding profile + the scorecard
   derivation + the repo eval fixtures.
9. ADRs: ADR-H324 (project memory is context, never authority), ADR-H325
   (builder/target process boundary and land-on-boundary), ADR-H326
   (maintenance mode is the only authority path), ADR-H327 (sessions reuse the
   run lineage). Use the Decision / Why / Consequences shape.
10. `docs/CHANGELOG.md`, `docs/NAVIGATION.md` rows, and the roadmap index row.

---

## 7. Acceptance gates

```bash
# G1 - project rules are loaded, bounded, deterministic and never grant a tool
./scripts/vendor/python/python.exe -m pytest python/tests/test_project_memory.py -q

# G2 - a long session survives a restart without a duplicate side effect
./scripts/vendor/python/python.exe -m pytest python/tests/test_build_session.py -q

# G3 - the builder/target boundary: the chat survives a runtime landing
node scripts/check-self-build.js

# G4 - authority files refuse live, and maintenance mode applies + rolls back
./scripts/vendor/python/python.exe -m pytest python/tests/test_authority_maintenance.py -q

# G5 - the land pipeline stops on a red check and reports the failure
./scripts/vendor/python/python.exe -m pytest python/tests/test_land_pipeline.py -q

# G6 - the surface: per-file review, resume, and no "verified" without a check
npx vitest run src/components/screens/code

# G7 - nothing regressed
npm run test && npx tsc --noEmit

# G8 - the plain-language gate covers the new copy
npx vitest run src/lib/i18n/plain-language.test.ts
```

| Gate | Assertion |
|---|---|
| G1 | `AGENTS.md` is in the first-turn block; the digest is stable across calls; a changed file changes it; a 200 KB source truncates and says so; a missing file is named; no rule can add a tool name to an allowlist. |
| G2 | A 60-step fixture checkpoints at the ladder and resumes after a forced restart; one apply per step; compaction preserves goal, acceptance and the open failing check; an exhausted budget reports the next step. |
| G3 | A `python/harness/**` landing restarts only the builder; the front door and the chat reconnect; a `src/**` landing builds before "landed"; a broken harness file is rolled back and the app is healthy. |
| G4 | The live path refuses an authority file with the maintenance instruction; maintenance mode refuses on a dirty tree; a failed gate leaves the target byte-identical; a success starts healthy. |
| G5 | A required check failing stops the pipeline and names the output; a check that cannot run is failed, not skipped; `Land` is unavailable until required checks pass; a docs-less non-test change is flagged. |
| G6 | A per-file decision is recorded and a comment becomes the next turn's context; a resume restores the plan; no UI string claims verification without a ledger record. |
| G7 | The full suite and typecheck are green; the finance agent's allowlist is byte-identical. |
| G8 | No new user-facing string names a mechanism term; every new string is an i18n key. |

**A gate not run is a gate not passed.** Paste raw output into the progress log.

---

## 8. Definition of done

- A user can open the Builder surface on this repo, describe a change, watch a
  plan, review a per-file diff, land it, see the checks, and undo it - without
  leaving the app.
- `AGENTS.md` is loaded on the first turn and the agent obeys the docs
  obligation without being reminded.
- A build survives a restart and resumes on the same plan.
- A runtime change restarts only the builder; the conversation survives.
- An authority change has a documented, offline, proven path.
- "Landed" means the required checks passed and a health probe answered.
- The self-build scorecard reports landed/rolled-back/human-edit/steps/cost with
  `UNKNOWN` where unmeasured.
- The harness still has one loop, one registry, one approval store, one
  checkpoint mechanism, and the same autonomy floor.
- The finance surface is unchanged; the new surface is opt-in.

---

## 9. Sequencing - the first slice

Do these three, in this order, and the external harness stops being the default
for ordinary work:

| Slice | Work | Why first | Effort |
|---|---|---|---|
| 1 | **S1 project memory** | cheapest, biggest quality lift, no UX change | 1-2 days |
| 2 | **S5 minimal Builder surface** (sessions + per-file review + checks) | makes the loop visible and reviewable | 3-5 days |
| 3 | **S2 durable session** | removes the "chunk the work" tax | 3-5 days |

Then S4 (land pipeline), then S3 (builder/target boundary + maintenance mode),
then S6 (model roles + scorecard).

**The honest milestone.** "I have not opened OpenCode for a normal feature in
two weeks" - not "Eclipse is fully autonomous". Authority changes and bootstrap
recovery will still want a terminal, by design.

---

## 10. Open questions (resolve by running, not reading)

1. Does the configured model actually sustain 80+ tool calls without losing the
   plan? Measure before choosing the ladder.
2. Is a second Python runtime (builder on another port) worth the complexity,
   or is land-on-boundary plus a deferred restart enough? Prototype S3a and
   compare.
3. Which checks belong in the default land pipeline without making a small
   change slow? Start with typecheck + affected tests; add the rest behind the
   project config.
4. Should a per-file rejection feed the same session or open a child session?
   Start with the same session and one follow-up turn.
