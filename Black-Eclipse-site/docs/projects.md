---
title: Projects — a named scope for the work that belongs together
status: Current
last-verified: 2026-10-20
---

# Projects — a named scope for the work that belongs together

**Who this is for:** anyone working on `python/harness/projects/`, or anyone
asking "where does Eclipse keep the things that belong to *this* piece of
work?"

**The one rule:** a project is a **scope**, not an opinion and not a container
of pointers. It names a piece of work, the instruments it covers, and the
members that belong to it. Every member keeps its own home; the project only
remembers where to look.

## What it is

Before projects, Eclipse could already *label* work — `RunRequest.projectId`
existed on the wire, `HarnessRun.projectId` and `SessionMessage.projectId`
were persisted, `HarnessArtifact.projectId` had an index — but nothing
resolved the label. A project id was a string with no entity behind it, so
"the same project" could not be listed, shown, or extended.

A project closes that gap with three pieces:

| Piece | Where | What it does |
|---|---|---|
| the entity | `python/harness/projects/store.py` | `Project` and `ProjectMember` on the ONE `agent-memory.db` connection |
| the tools | `python/harness/projects/tools.py` | `project_create`, `project_list`, `project_show`, `project_attach`, `project_detach` |
| the binding | `python/harness/graph.py` | a run that names a project gets the project's members as a per-run context note |

## The store

`ProjectStore` owns two tables and nothing else:

- **Project** — `id`, `name`, `description`, `symbolsJson`, `tagsJson`,
  `status`, `createdAt`, `updatedAt`, `lastActivityAt`, `archivedAt`.
- **ProjectMember** — `id`, `projectId`, `kind`, `ref`, `label`, `metaJson`,
  `createdAt`.

Three properties, enforced rather than assumed:

1. **One store, one connection.** The tables live on `agent-memory.db`, the
   runtime's own database, owned by this module alone — never
   `eclipse-memory.db`, never `jdds.db`.
2. **The DDL is idempotent.** `CREATE TABLE IF NOT EXISTS` on first use, so a
   store can be constructed in any order and a migration is a no-op.
3. **A member is a reference, not a copy.** The member kinds are `strategy`,
   `experiment`, `dataset`, `artifact`, `chat` and `note`; the `ref` is owned by
   its own subsystem (a strategy id, an experiment id, an artifact id), and the
   project remembers where to look.

`project_list` orders by `lastActivityAt DESC, rowid DESC` — most recently
active first, with a deterministic tie-break.

## The run binding

A run that carries `projectId` gets a **project brief** in its `runtime_context`
— the per-run, cache-key-excluded block that already carries the run's date
and the page the user is on. The brief says what the project *holds*:

```
## Project: NQ momentum (`proj_1a2b3c`)
Instruments: NQ, ES
Members:
- strategy: `ema_cross v1.0.0` — the cross
- experiment: `exp_9f8e7d`
```

Two rules:

- **A brief is never an opinion.** It lists members; it never says what the run
  should conclude.
- **An unknown project id is reported, never ignored.** A run that names
  `proj_missing` is told so in its context, so a typo cannot masquerade as
  "no project".

The brief is *not* a hard grant: it changes what the model knows, not what it
may do. The tool surface is still resolved by policy.

## The surfaces

| Surface | Entry point |
|---|---|
| The agent | the five `project_*` tools, allowlisted in `agents.py` |
| The runtime | `python/harness/routers/projects.py` — `GET/POST /projects`, `GET /projects/{id}`, `POST/DELETE /projects/{id}/members` (operator-gated) |
| The front door | `src/app/api/harness/projects/route.ts` — a thin proxy onto the runtime |
| The app | the **Project Scope widget** (`src/lib/dashboard/project-widget.tsx`, on the Command Center) — lists the projects, creates one, and pins the chat to it |
| A chat turn | `projectId` in the `/api/harness/chat` and `/api/harness/chat/stream` bodies, forwarded to the runtime |

## The active project

The widget does one thing beyond listing: it decides **which project the next
chat turn is scoped to**. That choice is a local preference
(`localStorage: be_active_project`, `src/lib/projects/project-client.ts`), not a
grant — the runtime still resolves the id, and an unknown one is reported in
the run's context rather than ignored.

`src/lib/agent/registry.ts` adds the active id to the chat payload, so both
the streaming and the one-shot path inherit it without a second code path. A
blocked `localStorage` must never break the chat, so the read is guarded and
returns `null`.

## What it is not

- **Not a workspace.** A project does not pin a folder, a git revision or a
  code root. The code workspace keeps its own trusted-root model
  (`code/workspace.py`), and the two are independent.
- **Not a data vault.** A project holds *references*; the data stays in the
  vault it belongs to (JDdS, the quant store, the Artifact Center).
- **Not a permission.** Membership grants nothing. A member is a pointer.

## The curated view

A member list is a filing cabinet. The **curated** view is a summary: what this
project is about, which members matter most, and what it does not have yet.

`python/harness/projects/curate.py` does it deterministically and explainably:

- **Ranking** is by a fixed priority per kind - an `experiment` (a tested
  result) outranks a `strategy` (an intent to trade), which outranks a `dataset`
  (an input), which outranks an `artifact` (an output), which outranks a run
  record. The newest member breaks a tie. Every promoted member carries **the
  reason it was promoted**, so the ranking can be argued with rather than
  merely trusted.
- **The headline** is derived from what the project actually holds: "NQ momentum
  on NQ, ES - 1 strategy, 2 results."
- **The gaps** are named plainly. A project with a strategy and no result is not
  finished, and it says so: *no result has been attached yet - a strategy with
  no tested outcome is an intention, not a finding.*

The curated view is what the **agent** sees: the run's per-run project context
is the digest, not a flat member list, so a turn inside a project starts from
"where does this stand?" rather than from a wall of references.

Surfaces: the tool `project_digest`; the route `GET /projects/{id}/digest`; and
the **Project Scope widget**, which shows the active project's headline, its
top members with their reasons, and what it still lacks.

## How a project fills itself up

`python/harness/projects/attach.py` is the policy, and it is deliberately
conservative:

- a run that names a project **records itself** in that project (a `note`
  member carrying the run id, its status and a bounded excerpt of its answer);
- every **artifact the run produced** joins the project as an `artifact`
  member;
- a run that produced nothing adds nothing but its own note.

It attaches what the run **made**, never what the run **mentioned**. The
user's own `project_attach` calls are untouched, and attaching the same run
twice does not duplicate a member.

Nothing here can fail a run: a project that does not exist, an artifact
service that is not configured, a member that cannot be written - all of it is
reported and swallowed, because a finished answer must not be lost to a
bookkeeping step.

## The remaining slice

The entity, the tools, the binding, the app surface, the auto-populate policy
and the curated view are in place. What is **not** built is a project that can
*answer* something - the curated view says where the project stands, but
nothing yet reads its members and proposes the next experiment. That is a
design question (what would the project want to know?), not a plumbing one.

Tests: `python/tests/test_projects.py`, `src/lib/projects/project-client.test.ts`.
