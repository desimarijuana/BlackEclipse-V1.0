---
title: BlackEclipse Terminal Cleanup — Progress
status: Current
last-verified: 2026-09-30
---

# BlackEclipse Terminal Cleanup — Progress

The last pass: close the eight remaining items. Append only. Source and the live
repo are authoritative wherever the prompt disagrees; the previous closeout doc
(`closeout-progress.md`) corrected three things in an earlier prompt and was right
each time, so it was read first.

## Baseline (2026-09-30, before any change)

- HEAD = `770028e` (engineering hardening); `ef886e5` (MCP 6.1); `b622285` (MCP 6).
- `.git` on disk = **101,428,986 bytes** (matches the prompt exactly).
- 17 refs: 12 `refs/codex/turn-diffs/checkpoints/*`, `refs/heads/main`,
  `refs/heads/backup-before-email-rewrite`, `refs/original/refs/heads/main`,
  `refs/remotes/origin/{HEAD,main}`.
- CHANGELOG entries: **125 in `CHANGELOG.md` + 226 in `docs/changelog/2026-09.md`
  = 351** (matches the prompt).
- Gates: `tsc` 0; eslint **0 errors / 24 warnings**; vitest **1900 / 160**; Python
  **1603 passed**; `npm run test:evals` ALL PASS.
- Working tree: 3 protected user files modified + the closeout change set
  (uncommitted). `.gitattributes` and `skills/ARCHITECT.md` are staged.

## Item 1 — Delete the codex checkpoint refs

**Why.** 12 `refs/codex/turn-diffs/checkpoints/*` refs pin 12 `jdds.db` blobs that
are exclusive to them; `git gc` cannot reclaim a pinned object.

**Pre-state (recorded before deleting).** `git for-each-ref 'refs/codex/*'` -> 12
refs. `git rev-list --all --objects | grep jdds.db` -> 20 unique blobs; the codex
refs carry **12 exclusive**:

| Blob SHA | Decompressed bytes |
|---|---|
| `1a7f6a38c840aa0a0277c7c0cf046393fe75b745` | 125,165,568 |
| `1b3e6b1909cc6c1e58abeed1e36d7b1f42355a09` | 126,435,328 |
| `3512094a6fa7ad4538676ffdb1e2e00b8f0357f9` | 130,551,808 |
| `40f43303e4d8f3fb8c8863ec067932beea65c419` | 144,412,672 |
| `61fc3c87a9317a1064e8b9ead6b3c2834c8d326d` | 117,669,888 |
| `63d09767ea6d8b02c77215a885a22e33aff72f88` | 130,912,256 |
| `789a734777ef44dffd7563e8aa5d94f130dedd87` | 138,481,664 |
| `7e5d9df906de15a428a79e61e818b0aad96ea630` | 114,466,816 |
| `84c8475f21ab17bc7d1fe76c597cffe576aed23d` | 140,320,768 |
| `bdf0de2228a313e747b65228a0428eb41526866d` | 123,207,680 |
| `c28405c1dd0bbff03485f850c7a822bf0d42f3b6` | 121,139,200 |
| `e469f27629515da1b65e9da6ef352d07cb96cdb6` | 115,302,400 |

**Exclusive decompressed total: 1,528,066,048 bytes (1528.1 MB)** — matches the prompt.

**Disposability check (step 3).** `codex` appears nowhere in
`Black-Eclipse-site/package.json`, `Black-Eclipse-site/scripts/`, or `.opencode/`
(only an unrelated `node_modules/zod` test named `codec.test.ts`, and our own docs).
No `.codex` config dir exists. The refs are unscheduled automatic checkpoints left
by the codex CLI on 2026-09-28, not something any workflow or app code depends on.
**Disposable.**

**Rollback path.** The 12 ref names and their SHAs are recorded in the table above
(ref -> tip SHA); they could be recreated with
`git update-ref <refname> <sha>` **only while the objects still exist**. After
`git gc --prune=now` the blobs are gone, so rollback requires the (nonexistent)
backup. **Nothing else points at these 12 blobs** (verified: they are exclusive to
the codex refs; `main` and both branches do not reference them).

**Destructive command (stated before running):**
```
git for-each-ref --format='%(refname)' refs/codex/ | xargs -n1 git update-ref -d
git gc --prune=now
```
Expected effect: the 12 refs are removed; their 12 exclusive `jdds.db` blobs become
unreachable; `git gc --prune=now` deletes them; `.git` shrinks by roughly the
packed size of those blobs. No history is rewritten; `main` and both branches are
untouched. Verified targets: 12 refs exist, 12 exclusive blobs exist.

**Executed and measured:**

| | `.git` bytes | `size-pack` | `count` | `garbage` |
|---|---|---|---|---|
| Before | 101,428,986 | 90.17 MiB | 5 | 0 |
| After | **46,889,626** | **38.30 MiB** | 0 | 0 |

**Real delta: -54,539,360 bytes (-54.5 MB, -51.9 MiB packed).** `git fsck` clean;
`main` unchanged (`770028e7eaad59b5038e69d529d9d2cc47b4d73c`). Refs dropped from 17
to 5. Gates unchanged (tsc 0, vitest 1900/160).

## Item 2 — Leftover filter ref and stale lock

**Pre-state.** `refs/original/refs/heads/main` and
`.git/objects/maintenance.lock` (a 0-byte stale lock dated 2026-09-28 16:33).

**Disposability.** `refs/original/refs/heads/main` -> `4ded698af5c7cfb150c244b4f0256a92683622d9`
(the same tip as `backup-before-email-rewrite`, which is kept), so deleting the
`refs/original/` remnant reclaims 0 objects but removes a confusing duplicate ref.
The lock is a 0-byte file from a maintenance run that died mid-write. No git
process is running (verified with `Get-Process -Name git*` -> empty).

**Destructive commands (stated before running):**
```
git update-ref -d refs/original/refs/heads/main
rm .git/objects/maintenance.lock
git gc --prune=now
```
Expected: the remnant ref and the stale lock are gone; `backup-before-email-rewrite`
and `main` are untouched; gc runs without complaint.

**Executed and measured:**

- `refs/original/refs/heads/main` deleted; `git for-each-ref 'refs/original/'` -> empty.
- `.git/objects/maintenance.lock` deleted (absent after).
- `git gc --prune=now` -> exit 0, no complaint; `git maintenance run --task=gc` ->
  exit 0, no lock recreated, no complaint.
- `.git` bytes: **46,889,626 -> 46,889,484** (the ref file itself was 142 bytes;
  the pinned objects were already shared with the kept branch, so 0 blob reclaim —
  honest). `size-pack` unchanged at 38.30 MiB. `git fsck` clean.
- Refs now: `backup-before-email-rewrite`, `main`, `origin/HEAD`, `origin/main`
  (4 refs; the codex debris and the filter remnant are gone).
