---
name: black-eclipse-docs
description: Black-Eclipse documentation rules — docs/ is the canonical human-readable explanation of the system (OVERVIEW, QUICKSTART, ARCHITECTURE, DATA-FLOW, NAVIGATION, DECISIONS, GLOSSARY). Use when writing or updating any user/developer documentation, onboarding material, or architectural explanation, and whenever a change alters architecture, a data shape, a contract, or setup steps. Also use when the user asks "how does our system work" or for docs for new users.
---

# Black-Eclipse Docs

`Black-Eclipse-site/docs/` is the **canonical, human-readable explanation** of how
BlackEclipse works. It exists so a new user or contributor can understand the
system without reverse-engineering the whole codebase.

## The one rule

> **Document what the code cannot tell you — intent, "why", invariants, and how
> to navigate. Do not re-document what you can read from the source.**

Consequences: no per-file reference manual, no copy-pasted code dumps, no
restating what a type signature already says. Point at `path/file.ts:line`
instead.

## The doc set (flat on purpose)

| Doc | Owns |
|---|---|
| `docs/README.md` | Home, reading order, and the maintenance method itself |
| `docs/OVERVIEW.md` | Product definition + the mental model |
| `docs/QUICKSTART.md` | Prerequisites, run, first-boot sequence, config |
| `docs/ARCHITECTURE.md` | Layers, screens, DataHub, API, JDDS, workers, the two workspaces |
| `docs/DATA-FLOW.md` | Ingestion → JDDS → API → screen, and the staleness story |
| `docs/NAVIGATION.md` | "Which file do I open?" — also the **update trigger table** |
| `docs/DECISIONS.md` | ADRs (mirror of `skills/ARCHITECT.md`; that file is authoritative) |
| `docs/GLOSSARY.md` | Term definitions |
| `docs/CHANGELOG.md` | **Required** record of every change + whether docs were updated |

**Do not add numbered folders or generated indices.** Add structure only when it
is genuinely painful (roughly past ~20 docs). `DECISIONS.md` accumulates dated
ADRs (a permanent "why"); `CHANGELOG.md` accumulates dated entries for *every*
change.

## Front-matter contract (every doc)

```yaml
---
title: <human title>
status: Draft | Current | Stale
last-verified: YYYY-MM-DD
---
```

- `Draft` — written from intent, not yet confirmed against the code.
- `Current` — re-read against the code on `last-verified`.
- `Stale` — known to be behind; the body says where.

Bump `last-verified` **only** when you actually re-read the doc against the code,
never as a side effect of an unrelated edit.

## The maintenance protocol (every task)

0. **Always append a `docs/CHANGELOG.md` entry.** Required for *every* change,
   even ones needing no doc edit. Terse bullet under today's date, ending with
   the doc files updated or `no doc change — <reason>`. Append; never rewrite.
1. **Proportional obligation.** A doc *update* (beyond the changelog) is required
   when the change alters **architecture, a data shape, a contract, or setup
   steps.** Not required for bug fixes, style changes, and tests.
2. **Say so explicitly.** In the task report, state *"docs updated: <file>"* or
   *"no doc change — <reason>"*. Never leave it silent.
3. **Use `NAVIGATION.md` as the trigger table.** Map the changed path to the
   owning doc, update it, and — for a new top-level folder or major module —
   update the table itself.
4. **Mark stale, never delete.** Set `status: Stale`, leave the content, and note
   what changed.
5. **Keep authority clear.** `docs/` is canonical and points outward;
   `README.md`, `CONTRIBUTING.md`, `skills/*.md`, and `.opencode/skills/*` should
   **reference** it, not restate it. `skills/ARCHITECT.md` remains authoritative
   for ADRs and deep architecture.

## Honesty rules (a financial product)

- Never let a doc claim something works when it was not verified.
- Never present stale, simulated, or demo data as live — in docs or in code.
- If a doc and the code disagree, **the code wins**; then fix the doc.
- Prefer `status: Draft` over a confident wrong statement.

## Mirrors

This skill has a human-readable counterpart at
`Black-Eclipse-site/skills/DOCS.md`, and the enforcement checklist lives in
`Black-Eclipse-site/skills/REVIEW.md` → "Documentation Review". Keep the three in
sync when the method changes.
