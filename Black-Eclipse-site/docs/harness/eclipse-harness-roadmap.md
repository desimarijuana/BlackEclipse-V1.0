---
title: Eclipse as a Harness — Build Roadmap (SUPERSEDED)
status: Stale
superseded_by: docs/harness/roadmap/README.md
last-verified: 2026-09-30
---

# Eclipse as a Harness — Build Roadmap — **STALE**

This single-file roadmap was superseded on 2026-09-30 by the split, one-file-per-phase
version. It is kept only so old links resolve.

**Go to [docs/harness/roadmap/README.md](./roadmap/README.md)** — the index lists all
13 phase files (0–12), each self-contained with its exact contracts, runnable
acceptance gates and a paste-ready implementation prompt.

**What changed in the split**

- One file per phase under `docs/harness/roadmap/`, so a reader can open just the
  phase they are running.
- A canonical heading scheme in every phase file (numbered §1–§11, a `## Contents`
  table, numbered `### 6.x` contracts).
- A new §4 "Who can use it (the non-expert obligation)" in every phase: the
  capability is for the whole finance field — analysts, PMs, traders, advisors,
  accountants, risk officers, students — not engineers or quants only. User-facing
  text names the finance job, never the mechanism, and a plain-language gate
  enforces it against `policy.PLAIN_LANGUAGE_DENYLIST`.
- The ADR series was renumbered contiguously: **ADR-H93 … ADR-H114**.
