# DOCS.md — Documentation System ("Docs-as-Code with a proportional obligation")

> Read this **before writing or updating any documentation**. It defines where
> docs live, what belongs in them, and exactly when they must be updated.
> The canonical docs themselves are in [`../docs/`](../docs/).

---

## Principle

Documentation dies for one reason: **nobody knows which doc their change
touches.** We fix that with a small, flat, clearly-owned doc set and a trigger
table — not with a promise that docs are always perfect.

### The one rule

> **Document what the code cannot tell you — intent, "why", invariants, and how
> to navigate. Do not re-document what you can read from the source.**

So: no per-file reference manual, no pasted code blocks that rot, no restating a
type signature. Reference `path/file.ts:line` instead.

---

## The doc set (canonical: `Black-Eclipse-site/docs/`)

| Doc | Owns |
|---|---|
| `README.md` | Home, reading order, and this method |
| `OVERVIEW.md` | Product definition + mental model |
| `QUICKSTART.md` | Prerequisites, run, first-boot sequence, config, data location |
| `ARCHITECTURE.md` | Layers, shell, DataHub, API, JDDS, workers, the two workspaces, UI system |
| `DATA-FLOW.md` | Ingestion → JDDS → API → screen; provenance and staleness |
| `NAVIGATION.md` | "Which file do I open?" — **the update trigger table** |
| `DECISIONS.md` | ADR log (mirror of `ARCHITECT.md`; that file is authoritative) |
| `GLOSSARY.md` | Terms |
| `CHANGELOG.md` | **Required** record of every change + whether docs were updated |

**Deliberately no numbered folders or generated index.** Add structure only when
the pain is real (~20+ docs). `CHANGELOG.md` is the exception to "git is the
changelog" — it exists so the documentation obligation is *verifiable*, not just
aspirational.

---

## Front-matter contract

Every doc begins with exactly:

```yaml
---
title: <human title>
status: Draft | Current | Stale
last-verified: YYYY-MM-DD
---
```

- **Draft** — written from intent, not yet confirmed against the code.
- **Current** — re-read against the code on `last-verified`.
- **Stale** — known to be behind; the body says where.

Bump `last-verified` only when you actually re-read the doc against the code.

---

## The one thing required for EVERY change

Append an entry to `docs/CHANGELOG.md`. Even changes that need no doc update.
Terse bullet under today's date, ending with the doc files updated or
`no doc change — <reason>`. This is what makes the whole system checkable.

## When a doc update is REQUIRED (in addition to the changelog)

Update the owning doc when a change alters:

- **Architecture** — new layer, module, worker, or engine; a retired subsystem.
- **A data shape or contract** — API response shape, a JDDS model, a topic
  vocabulary, a widget/ops signature.
- **Setup or operations** — prerequisites, npm scripts, env vars, boot sequence,
  DB handling.
- **A top-level folder or major module** — also update `NAVIGATION.md`.
- **An architectural decision** — add an ADR to `ARCHITECT.md`, mirror it in
  `DECISIONS.md`.

## When a doc *update* is NOT required (the changelog entry still is)

- Bug fixes that restore documented behavior.
- Internal refactors that do not change a contract.
- Style, copy, or test-only changes.
- Adding a normal file inside an already-documented module.

## Required reporting

Every task report ends with one of:

- `docs updated: <file(s)>`, or
- `no doc change — <reason>`.

Silence is not acceptable. This is checked in `REVIEW.md`.

---

## Maintenance rules

1. **Proportional obligation** — see above; do not write docs for optics.
2. **Stale, never deleted** — mark it and say what changed.
3. **`NAVIGATION.md` is the trigger table** — keep the path→doc mapping current.
4. **Code beats docs** — when they disagree, the code is the source of truth;
   then fix the doc. Use `Draft`/`Stale` rather than confident wrong statements.
5. **One authority per fact.** `docs/` is canonical and points outward;
   `README.md`, `CONTRIBUTING.md`, and `.opencode/skills/*` should reference it,
   not restate it. `ARCHITECT.md` stays authoritative for ADRs and deep
   architecture.
6. **Honesty first** — never present stale, simulated, or demo data as live.

---

## opencode registration

`.opencode/skills/black-eclipse-docs/SKILL.md` registers this method so opencode
auto-loads it when a task involves documentation or a change to architecture,
data shapes, contracts, or setup. Keep this file and that skill in sync.

## Future (only when the pain is real)

Not now: a dead-link/front-matter check script, CI enforcement, or an in-app docs
viewer. The enforcement that matters today is the **Documentation Review**
section in `REVIEW.md`.
