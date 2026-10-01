---
title: Runbook — inspect a failed code task
status: Current
last-verified: 2026-10-01
---

# Runbook — inspect a failed code task

**Who this is for:** the person looking at a code task that did not finish, at
09:00 on a Monday.

A code task IS a run whose agent id is `code-agent`. Its durable boundaries are
`RunCheckpoint` rows on the ONE run lineage — never a second table. To the user it
reads as one plain sentence ("That task did not finish. Nothing was sent
anywhere."); the machinery is below.

## 1. Where the trace is

**The run.** `GET /runs/{id}` and `GET /runs/{id}/events` (Python), or the run
explanation panel in the app. The run id is the task id.

**The checkpoints.** `GET /runs/{id}/lineage`. The code-specific boundaries are
written by `python/harness/code/tasks.py`:

| Kind | Records |
|---|---|
| `task.created` | the bound workspace + the autonomy profile + the scope label |
| `plan.accepted` | the plan the operator accepted |
| `patch.applied` | a change id + the tree digest after the apply |
| `command.executed` | the command class + idempotency key + exit code |
| `task.cancelled` / `task.discarded` | the reason, with the work area released |

**The command executions.** `HarnessCommandExecution` rows (Python `code/store.py`,
`GET`-able through the store) record every command the broker ran: the class, the
argv, the exit code, the duration, the sandbox backend and the policy decision.

## 2. What the verification ledger says

`GET /code/tasks/{id}/checks` returns the run's `codeVerification`. The ledger
(`python/harness/code/verify.py`) records, for every claimed check:

- **passed** — the executor recorded a zero exit, with an output digest;
- **failed** — the executor recorded a non-zero exit;
- **not checked yet** — a claim exists with no backing execution record.

A task whose check was merely *claimed* is marked with the unverified marker; the
answer text is not trusted on its own.

## 3. What "not checked yet" means

A **claim** is a sentence that says a check passed. A **record** is the executor's
own row. "Not checked yet" means a claim has **no** matching record — the number on
the screen is not backed by anything the harness observed. It is never a pass.
Nothing marks a task complete on an unbacked claim.

## 4. The three recovery actions

1. **Fix and re-run.** Open the failing check in the app, or resume the task:
   `POST /runs/{id}/resume`. Resume re-enters at the last checkpoint and **reuses**
   any recorded tool result for a step already run, so a patch is never re-applied
   and a side-effecting command is never re-run.
2. **Stop and remove the work area.** `POST /code/tasks/{id}/cancel` stops the run
   and releases the disposable work area; `POST /code/tasks/{id}/discard` removes
   the work area and keeps the run record as an audit trail.
3. **Escalate to the operator.** A check that needs a tool the broker does not
   allow, or software that is not installed, refuses honestly. Read the refusal
   code behind "details", then either add the check class or install the tool.

## 5. Common refusals

| Code | Meaning | Next step |
|---|---|---|
| `SANDBOX_UNAVAILABLE` | no isolation primitive is available | run where Eclipse can isolate the check; it never runs uncontained |
| `COMMAND_NOT_ALLOWLISTED` | the check is outside the closed command table | use a supported check, or add a class |
| `COMMAND_EXECUTABLE_MISSING` | the tool for the check is not installed | install it, then retry |
| `PROFILE_DENIED` | the task's profile may not do that | start the task with a profile that may |
| `WORKSPACE_UNBOUND` / `UNKNOWN_WORKSPACE` | no work area is bound | create the task with one |

## 6. Where the pieces live

| Piece | File |
|---|---|
| Task lifecycle | `python/harness/code/tasks.py` |
| Command broker | `python/harness/code/commands.py`, `python/harness/code/command_tools.py` |
| Execution primitive | `python/harness/code/sandbox.py` |
| Verification ledger | `python/harness/code/verify.py` |
| Repair loop | `python/harness/code/repair.py` |
| Routes | `python/harness/routers/code.py` |
| Front door | `src/lib/harness/code-client.ts`, `src/components/chat/code-verification-panel.tsx` |
