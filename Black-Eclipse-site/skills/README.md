# BlackEclipse AI Agent Skills

This folder contains a persistent engineering operating system for any AI coding agent (opencode, Claude, Cursor, etc.) working on BlackEclipse.

## The 6 skills

| File | Purpose |
|---|---|
| `ARCHITECT.md` | System architecture, tech stack, data architecture, architectural rules, ADRs |
| `REMEMBER.md` | Persistent project memory — decisions, conventions, constraints, lessons |
| `REVIEW.md` | Mandatory pre-completion checklist (8 review categories) |
| `RECOVER.md` | Failure recovery protocol — STOP→INSPECT→IDENTIFY→RECOVER→VERIFY |
| `IMPRINT.md` | Design system, visual identity, and financial UI rules |
| `DOCS.md` | Documentation system — where docs live and when they must be updated |

The **user-facing documentation** itself lives in [`../docs/`](../docs/) and is
maintained per `DOCS.md`. `docs/` is canonical for "how the system works";
`ARCHITECT.md` remains authoritative for ADRs and deep architecture.

## How to use

For a significant development task, the agent should follow:

1. Read `ARCHITECT.md` (understand the system)
2. Read `REMEMBER.md` (recall context)
3. Understand the task
4. Inspect existing code
5. Plan the change
6. Implement
7. Verify (test after every change: `npm run test` + `npx tsc --noEmit`)
8. Run `REVIEW.md` checklist
9. If something breaks → follow `RECOVER.md`
10. If new knowledge is discovered → update `REMEMBER.md`
11. If UI changes → verify against `IMPRINT.md`
12. If the change affects architecture/data shape/contract/setup → update `../docs/` per `DOCS.md`
13. Complete

## opencode registration

The same 6 skills are also registered as opencode skills in `.opencode/skills/` so opencode auto-loads them when a task matches their trigger description. The `.opencode/skills/*/SKILL.md` files reference these docs.

## Priority

Correctness > Architecture > Data integrity > Security > Maintainability > Performance > UX > Visual polish.

**Standing goal:** the site must be **simple, fast, and light** for the best user experience. This applies to every change, forever — see `GOALS.md` → "Performance & Simplicity".

Optimize for actually making BlackEclipse better — not for making the task "look complete."
