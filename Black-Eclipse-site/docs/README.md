---
title: Documentation Home
status: Current
last-verified: 2026-11-15
---

# BlackEclipse Documentation

Start here. This folder is the **canonical, human-readable explanation of how
BlackEclipse works**. It is written for someone who just cloned the repo and
wants to understand the system — not for the compiler.

> **Code is the source of truth for *what* happens. These docs are the source of
> truth for *why*, *how it fits together*, and *where to look*.** When they
> disagree, the code wins — then fix the doc.

## Read in this order

| # | Doc | Answers |
|---|-----|---------|
| 1 | [OVERVIEW.md](./OVERVIEW.md) | What is this product, and what is the mental model? |
| 2 | [QUICKSTART.md](./QUICKSTART.md) | How do I run it and see something working? |
| 3 | [ARCHITECTURE.md](./ARCHITECTURE.md) | What are the layers and the big moving parts? |
| 4 | [DATA-FLOW.md](./DATA-FLOW.md) | Where does data come from, and how does it reach the screen? |
| 5 | [NAVIGATION.md](./NAVIGATION.md) | Which file do I open to change X? |
| 6 | [DECISIONS.md](./DECISIONS.md) | Why is it built this way? (ADRs) |
| 7 | [GLOSSARY.md](./GLOSSARY.md) | What does this word mean here? |
| 8 | [CHANGELOG.md](./CHANGELOG.md) | What changed recently, and were the docs updated? |
| 9 | [OPEN-SOURCE-READINESS.md](./OPEN-SOURCE-READINESS.md) | Is the repository safe to make public? (readiness, not an intro) |
| 10 | [public-readme.md](./public-readme.md) | What does the public README claim, and what evidence backs each claim? |

Related, outside this folder: [`../README.md`](../README.md) (project intro),
[`../CONTRIBUTING.md`](../CONTRIBUTING.md) (dev setup), and
[`../skills/`](../skills/) (the engineering operating system for AI agents).

---

## The documentation method

Documentation dies for one reason: **nobody knows which doc their change
touches.** This folder exists to make that question cheap to answer, not to
promise that docs are always perfect.

### One rule

> **Document what the code cannot tell you — intent, "why", invariants, and how
> to navigate. Do not re-document what you can read from the source.**

That is why there is no per-file reference manual here. If you can learn it by
opening a file, the docs stay out of the way and point you at the file instead.

### The rules of maintenance

1. **Proportional obligation.** A doc update is required when a change alters
   **architecture, a data shape, a contract, or setup steps**. It is *not*
   required for every commit. A bug fix, a style change, or a new test usually
   needs no doc edit.
2. **Say so explicitly.** Every task report states either *"docs updated"* or
   *"no doc change — <reason>"*. Silence is not acceptable.
3. **Stale is not deleted — stale is marked.** Set `status: Stale` and leave the
   content. A wrong doc that admits it is stale is useful; a deleted doc loses
   the history.
4. **Facts get dated.** `last-verified` is bumped only when a human or agent
   actually re-reads the doc against the code. Do not bump it as a side effect
   of an unrelated edit.
5. **`NAVIGATION.md` is the trigger table.** If you add or move a top-level
   folder or a major module, update it there in the same change.
6. **Every change is recorded in `CHANGELOG.md`.** Even changes that needed no
   doc update. The entry states the change and whether docs were updated. This is
   what makes the obligation verifiable instead of aspirational.
7. **`DECISIONS.md` accumulates dated ADRs.** An ADR is a permanent "why".

### Front-matter contract

Every doc starts with exactly these keys:

```yaml
---
title: <human title>
status: Draft | Current | Stale
last-verified: YYYY-MM-DD
---
```

- `status: Draft` — written from intent, not yet confirmed against the code.
- `status: Current` — re-read against the code on `last-verified`.
- `status: Stale` — known to be behind reality; the body says where.

### When this method should grow

The flat set is deliberately small. **Add structure only when the pain is
real** — roughly when this folder passes ~20 documents or when one doc exceeds
a comfortable read. Until then, numbered folders, generated indices, and CI
link-checkers are scaffolding for a problem that does not exist yet. The
enforcement that matters today is the Documentation section of
[`../skills/REVIEW.md`](../skills/REVIEW.md).
