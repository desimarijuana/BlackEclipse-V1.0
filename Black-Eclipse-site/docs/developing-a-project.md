---
title: Developing a project with Eclipse
status: Current
last-verified: 2026-11-06
---

# Developing a project with Eclipse

Eclipse can work on **any** project folder you approve, not only its own source.
This page is the user-facing guide; `NAVIGATION.md` is the maintainer index.

## 1. Open a project

1. Open **Builds** (`Ctrl/Cmd+K` → "Builds", or `?tab=code`).
2. In the **This project** bar, choose **Change → Open folder…**.
3. Pick the folder. It is now an **approved** project: Eclipse may read and write
   inside it, and nothing outside it.

The selection is the project new builds belong to. The built-in repo is the
zero-config default.

## 2. Read the brief

The card under the bar tells you what Eclipse found:

| Field | Meaning |
|---|---|
| Stack | `node`, `python`, `rust`, `go`, `make` — from the project's manifests |
| Git | branch and uncommitted file count |
| Runs | the command **Run the project** would start |
| Checks | how many checks a change must pass, and where they came from |
| Rules | the project ships `AGENTS.md` / `CLAUDE.md` / `.eclipse/instructions.md` |

**Prepare** indexes the project so symbol search and repo context are ready. It
is optional; the first build would do the same work lazily.

## 3. Build, review, land

Ask for a change in chat with `/eclipsesdk <what you want>`. Eclipse edits a
disposable **worktree**, then:

- **Builds** shows the task, its session (phase, next action), the per-file diff,
  the land checks and the scorecard.
- Tick the files to keep, then **apply** — one approval puts the reviewed files
  into your project, and the change can be undone exactly.
- Python changes restart the agent runtime (deferred while a run is in flight);
  front-end changes need the build gate.

## 4. Run it

**Run the project** shows the command first, starts it, and reports the URL only
when a port actually answers. Two modes:

- **On disk** — the project as it is now.
- **Prepared change** — the task's worktree, with your installed dependencies
  linked read-only, so you can look at an unlanded change. The link is removed on
  stop.

**Restart** restarts it; switching project stops the previous project's server.

## Project files Eclipse may add

Everything lives in `<project>/.black-eclipse/`, which is **self-ignored**
(`.gitignore` containing `*`) so it never appears in your `git status`.

| File | Purpose |
|---|---|
| `land.json` | replace the discovered landing checks (`{"checks": [...]}`) |
| `preview.json` | how to run the project (`{"command": "npm run dev"}`) |
| `policy.json` | `{"denyPaths": ["db/migrations/", "*.lock"]}` — paths Eclipse must never write |
| `capabilities/` | generated recipes for this project only |
| `promotions/` | rollback backups of landed changes |

`policy.json` is **narrow-only**: it can add protected paths, never widen what
Eclipse may do. Absolute and `..` entries are ignored.

## What Eclipse will not do

- **Never fabricate data.** Unavailable data is shown as `UNAVAILABLE`.
- **Never land without review.** Files go into your project only after you
  approve the reviewed set.
- **Never touch credentials.** `.env`, `*.pem`, `*.key` and `id_rsa*` are refused
  for reads and writes.
- **Not multi-tenant.** One operator, one runtime. Run separate instances for
  separate users.
- **Not a sandbox.** Discovered checks and the run command are commands declared
  by the project; they run as you. Read them before you run them.

## Proving the check loop

Pin the checks a change must not break:

```json
// <project>/.black-eclipse/verify.json
{"checks": ["unit_test"]}
```

`unit_test`, `python_test`, `typecheck`, `lint`, `build`, `format_check` and
`git_read` are the valid classes (a plural like `unit_tests` is accepted). After
a file change, Eclipse runs the pinned class once through the same allowlisted
path a manual check uses. A failure is handed back to the agent as **data**, and
the answer is annotated if the check never passes — a passing check is never
reported as "exhausted".

To prove the loop yourself, break one assertion and ask Eclipse to fix it. You
should see `code.repair.attempt` with the failing class and output digest, then
`code.repair.passed`; the final blob's `repair.status` is `REPAIR_PASSED`. If the
check cannot run at all (profile or sandbox refusal), the status is
`REPAIR_REFUSED`, not a pass.

## Troubleshooting

| Symptom | Cause |
|---|---|
| "I could not find how to run this project" | add `.black-eclipse/preview.json` with `{"command": "..."}` |
| "Running, but nothing is listening yet" | the dev server is starting; **Check again**, or read the logs |
| "The project this build belongs to is no longer at its recorded folder" | the folder moved; reopen it |
| Land checks are empty | nothing recognisable; add `.black-eclipse/land.json` |
| A write is refused as protected | the project's `policy.json` denies it, or it is a credential file |
