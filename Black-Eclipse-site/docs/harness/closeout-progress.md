---
title: BlackEclipse Closeout — Progress
status: Current
last-verified: 2026-09-30
---

# BlackEclipse Closeout — Progress

Implementation log for the five items the engineering-hardening pass deliberately
left open: history hygiene, line endings, CHANGELOG forensics, CI, and this
closeout. Source code and the live repo were authoritative wherever the prompt
disagreed. Append only.

## Phase 0 — Audit: establish exactly what is left

**Current state (2026-09-30, `black eclipse/`):**

- `git log --oneline -3` -> `770028e` (engineering hardening), `ef886e5` (MCP 6.1),
  `b622285` (MCP 6).
- `git status --short` -> exactly three modified, unrelated user files:
  `Black-Eclipse-site/docs/investor-eye-architecture.md`,
  `Black-Eclipse-site/public/geo/world.geo.json`,
  `Black-Eclipse-site/scripts/fetch-world-geo.mjs`. Not touched.
- `.git` on disk: **106,336,544 bytes**. `git count-objects -vH`: `in-pack 8443`,
  `size-pack 94.53 MiB`, `garbage 0`.

**Baseline gates (all pass):**

| Gate | Result |
|---|---|
| `npx tsc --noEmit` | 0 |
| `npx vitest run` | **1891 / 159 files** |
| Python pytest | **1603 passed** |
| `npx eslint .` | 0 errors / 24 warnings |
| `npm run test:evals` | ALL PASS |

### Verified open items

| # | Verdict | Evidence |
|---|---|---|
| **I1** | **CONFIRMED, with a correction on the source.** `git rev-list --all --objects \| grep 'jdds.db$'` -> **20 unique blobs**, decompressed sizes **35 MB – 144 MB** (not all 114–144 MB; the smallest is 35,381,248 B). The 20 are: **8 shared by `main`/`backup-before-email-rewrite`/`origin/main`** (347.2 MB decompressed, 36.6 MB compressed in the main pack) **+ 12 exclusive to the `refs/codex/turn-diffs/checkpoints/*` refs** (1,528.1 MB exclusive). `.git` is ~106 MB on disk, 94.5 MiB packed. |
| **I2** | **CONFIRMED, with a correction on the cost.** `git rev-list --count main..backup-before-email-rewrite` = **289**; reverse = **302**; `git merge-base` empty (no common ancestor). Tip = **`4ded698af5c7cfb150c244b4f0256a92683622d9`**. It is not pushed (`git branch -r` shows only `origin/main`). **BUT it holds NO exclusive blob load**: all 8 of its `jdds.db` blobs are already in `main` (`orphan-exclusive = 0 objects, 0.0 MB`). The "most of the blob load" claim is **wrong** — the load is in the **12 `refs/codex/` checkpoint refs** (1.53 GB exclusive), which the prompt does not mention. |
| **I3** | **CONFIRMED.** `git config core.autocrlf` = `true`; no `.gitattributes` (`git ls-files` -> none). `git diff --stat docs/DECISIONS.md` vs `git diff -w --stat` shows the phantom-diff effect (whole-file rewrite vs the real change). `git add --renormalize --dry-run .` -> **1368** files. Worktree CRLF: **372 of 1368** tracked files carry CRLF across the whole file (338 in the first 4 KB); the rest are LF-only. |
| **I4** | **CONFIRMED, with a corrected diagnosis.** At the pre-rotation commit `ef886e5`: **48 dated sections / 343 `^- ` bullets / 314 `- **heading**` entries**. Now: `CHANGELOG.md` 7/46 + archive 41/303 = **48/349**. **Section-date occurrence multiset is EQUAL (48 = 48); zero entry headings were lost.** The +6 entries are the six engineering-hardening entries. **Finding:** four of those six were appended via `Add-Content` at the file END and the rotation swept them into the oldest `## 2026-09-15` section instead of `## 2026-09-30` — a mis-filing, not a loss. The prior doc's "347 bullets" was a miscount (the honest number is 343 pre-rotation by the `^- ` rule). See Phase 3. |
| **I5** | **CONFIRMED.** No `.github/` at the repo root (`Test-Path` false); 0 tracked `.github/` entries. `package.json` has `test:smoke` but no gate invokes it; `check:all` exists. |

### Corrections to the prior progress doc (doc edit, not history rewrite)

1. **R8 row** (`engineering-hardening-progress.md` Phase 0): its per-file line
   counts were measured with PowerShell `Measure-Object -Line` and do not match
   the shipped ratchets. Marked **SUPERSEDED** with the authoritative values the
   ratchets use (Python `graph.py` 1916 etc.; TS `market-overview.tsx` 2760). The
   ratchets are correct as shipped.
2. **"four unrelated modified files"** at the start of that phase: corrected to
   note that by the END of the phase it was **three** (`jdds.db` became
   untracked+ignored).

### Phase 1 risk note (history rewrite — NOT executed)

Phase 1B (orphan-branch disposition) and 1C (`jdds.db` history purge) are
**destructive and prepared only**. Risks, stated plainly:

- **1C rewrites every commit hash** in every ref, including the 12
  `refs/codex/turn-diffs/checkpoints/*` refs and `backup-before-email-rewrite`.
  The remote needs a **force-push** (the user's call; I must not perform it) and
  collaborators must re-clone.
- **No undo without a mirror backup.** A `git clone --mirror . <path>` (verified)
  plus a working-tree archive must exist first.
- **Ordering:** the 1B branch decision must happen BEFORE the 1C purge, or the
  purge must re-run afterwards.
- **1A (this phase) is safe**: `git gc --prune=now` only removes provably
  unreachable objects and rewrites no history.

## Phase 1 — History hygiene (1A executed; 1B/1C prepared, NOT executed)

### 1A — Measure honestly, then reclaim what is safe (done)

**Blob-load measurements** (decompressed blob bytes referenced by each ref set;
`git rev-list <ref> --objects` + `git cat-file --batch-check`):

| Ref set | Blob bytes referenced | Notes |
|---|---|---|
| `main` alone | **452.5 MB** (4221 objects) | includes 8 `jdds.db` blobs = 347.2 MB |
| `backup-before-email-rewrite` | **443.7 MB** (3994 objects) | same 8 `jdds.db` blobs; **0 exclusive** vs `main` |
| `refs/codex/...` checkpoints (12 refs) | **1,528.1 MB exclusive** vs `main` | the real orphan load |
| all refs (union) | **1,982.7 MB** (8503 objects) | 424 objects / 1530.3 MB exclusive vs `main` |

**On-disk reality (scratch clones):**

| Case | `.git` on disk / pack |
|---|---|
| (a) all refs (mirror clone) | **99,354,886 B .git**, `size-pack 94.69 MiB` |
| (b) `main` only (`--single-branch`) | **44,056,608 B .git**, `size-pack 41.90 MiB` |
| (c) `main` with no `jdds.db` blobs | **~7.0 MB** in-pack estimate (43.6 MB pack − 8 jdds blobs at 36.6 MB compressed) |

So the `jdds.db` compression is dramatic (347 MB decompressed -> 36.6 MB packed),
and the branch is **not** the load: **the 12 `refs/codex/turn-diffs/checkpoints/*`
refs hold ~1.53 GB of exclusive `jdds.db` blobs**. (The scratch clones were
deleted after measuring.)

**Branch tip recorded:** `backup-before-email-rewrite` =
`4ded698af5c7cfb150c244b4f0256a92683622d9` (289 commits not in main, 302 in main,
no merge base). `refs/original/refs/heads/main` points at the same SHA.

**Safe reclaim (executed):** `git gc --prune=now --aggressive`.
`git count-objects -vH`: **before** `size-pack 94.53 MiB`, `count 80`, `garbage 0`;
**after** `size-pack 90.17 MiB`, `count 0`, `garbage 0`. `.git` 106.3 MB ->
101.3 MB. `git fsck` clean. The gain is **modest (~4.4 MiB)** because the 12
checkpoint refs still pin the big blobs — that is the honest number, not an
oversell.

**Key finding (corrects the prompt's framing):** deleting
`backup-before-email-rewrite` alone would reclaim **~0 MB** (it has no exclusive
blobs). The space is held by the `refs/codex/turn-diffs/checkpoints/*` refs and by
the reachable `jdds.db` history on `main`.

### 1B — Orphan-branch disposition (prepared, NOT executed)

Recommended: **(b) archive out of the repo.** None of these is reversible without
the bundle (b) or the original clone (c).

- **(a) Keep it.** Zero risk. Cost: it is a 289-commit no-merge-base tree that
  shares its entire blob set with `main`, so it adds refs/commits but no exclusive
  blob bytes (~0 MB reclaim).
- **(b) Archive out of the repo (recommended).**
  ```
  git bundle create ../black-eclipse-backup-before-email-rewrite.bundle backup-before-email-rewrite
  git bundle verify ../black-eclipse-backup-before-email-rewrite.bundle
  git branch -D backup-before-email-rewrite
  ```
  Preserves the pre-rewrite history off-repo; local reclaim ~0 MB here (see 1A),
  but it removes a confusing no-merge-base branch.
- **(c) Delete outright.** Only if the user confirms the pre-rewrite history is
  useless. Irreversible without the original clone.

**Because the branch has no exclusive blobs, none of (a)-(c) meaningfully reduces
`.git`.** The size lives in the codex checkpoint refs and `main`'s `jdds.db`
history — which 1C targets.

### 1C — `jdds.db` history purge (prepared, NOT executed)

**Do not run without the user's written go-ahead.** Rewrites every commit hash.

**Step 0 — mandatory mirror backup (verify before proceeding):**
```
git clone --mirror . ../black-eclipse-pre-purge.git
git --git-dir=../black-eclipse-pre-purge.git show-ref | wc -l   # expect 17
git archive --format=zip -o ../black-eclipse-worktree-<date>.zip HEAD
```
**Step 1 — obtain the tool (operator tool, NOT an app dependency):**
`pipx install git-filter-repo` (or `pip install git-filter-repo`);
`git-filter-repo` is **not installed** today.
**Step 2 — purge:**
```
git filter-repo --path Black-Eclipse-site/jdds.db --invert-paths
# or, size-scoped:
git filter-repo --strip-blobs-bigger-than 50M
```
Note: `--path ... --invert-paths` removes the path from history but the
`refs/codex/...` checkpoint refs also carry `jdds.db`; a purge that leaves those
refs unchanged will not reclaim their 1.53 GB. Decide whether the codex refs are
kept/removed **first** (`git for-each-ref 'refs/codex/*'`), then run the purge on
what remains — otherwise re-run.

**Ordering:** do the 1B disposition and the codex-ref decision **before** the 1C
purge, or the purge must re-run after them.

**Consequences:** every commit hash changes; all refs are rewritten; the remote
needs a **force-push** (the user's call — I must not perform it); collaborators
re-clone. **Estimated recovery:** `main`-with-no-jdds is ~7 MB packed vs ~44 MB
with them (~37 MB on `main` alone); a full purge across `main` + codex refs would
recover on the order of **1.5 GB of decompressed blob load**, but the realistic
packed reclaim depends on which refs remain and must be re-measured after 1B.
Not executed.

## Phase 2 — End the line-ending churn

**Status:** complete. The renormalization is STAGED in isolation
(`.gitattributes` + `skills/ARCHITECT.md`); the guard test and this doc are
separate working-tree changes, so the staged renormalize can be committed alone.

**What changed**

- **New root `.gitattributes`.** `* text=auto eol=lf`; Windows script types
  (`.bat`/`.cmd`/`.ps1`) pinned `eol=crlf`; explicit LF for the text types the
  repo has; **binary** for the real binaries. The binary list was **determined
  from the tracked files**, not guessed: extension census of all 1368 tracked
  files showed exactly two binary types — `.wav` (63) and `.ico` (1). `*.db` and
  `*.db-*` are declared `binary` too so a future tracked DB cannot be corrupted.
- **Renormalized in a dedicated change.** `git add --renormalize .` affected
  **1 tracked text file** — `skills/ARCHITECT.md` (the only text blob whose stored
  bytes were CRLF; the other 28 CRLF-containing blobs are `.wav`/`.ico`
  binaries). Staged together with `.gitattributes` and nothing else.
- **`.db` question decided explicitly.** `git check-attr binary text eol --
  Black-Eclipse-site/jdds.db` -> `binary: set`, `text: unset`, so git never
  normalizes it. `jdds.db` stays on disk at 156,966,912 bytes (unchanged) and the
  existing `gitignore-guard.test.ts` db assertions still pass.

**Evidence**

- Phantom-diff fixed: before, a 1-line edit to `docs/DECISIONS.md` read as
  `706+/694-` raw vs `22+/10-` with `-w`. After the attributes, the same 1-line
  edit reads `1/0` **both** raw and `-w`. (Probe reverted with `git checkout --`.)
- **Content-unchanged proof:** SHA-256 of 62 representative files (`.ts`, `.tsx`,
  `.py`, `.md`, `.json`, `.css`, `.html`, `.svg`, `.js`, `.prisma`, plus
  `world.geo.json`, `schema.prisma`, both `.gitignore`s), both raw and
  CRLF-normalized. After renormalizing: **0 files changed logical content**
  (normalized SHA identical); only **1 file** changed raw bytes (line endings) —
  `ARCHITECT.md`. `.json`/`.sql` verified unchanged.
- **Regression guard:** extended `src/lib/gitignore-guard.test.ts` with a
  `line-ending normalization` block that asks git's own attribute engine
  (`git check-attr`): 5 text files must resolve `eol: lf`; `.wav`/`.ico` must be
  `binary: set`; a `.ts` must not be binary. If the attributes regress, this
  fails. (7 tests in the file, all green.)

**Checks:** `tsc` 0; vitest **1894 / 159** (was 1891; +3 eol tests); eslint
0 errors / 24 warnings.

## Phase 3 — CHANGELOG forensic reconciliation

**Status:** complete.

**Method (from git, not prose).** Compared the pre-rotation state
`git show ef886e5:Black-Eclipse-site/docs/CHANGELOG.md` against the current
`CHANGELOG.md` + `docs/changelog/2026-09.md`, using each file's real entry
definition (a `- **Heading**` bullet; continuation paragraphs are body, not
entries).

**Disposition (section-date and entry-heading multisets):**

| Measure | Pre-rotation (`ef886e5`) | Now (CHANGELOG + archive) |
|---|---|---|
| Dated section occurrences | 48 | 48 |
| `- **heading**` entries | 314 | 320 |
| `^- ` bullets | 343 | 349 |
| **Entries lost** | — | **0** |

**No entry was lost.** The heading multiset difference is **+6 added, 0 removed**
— exactly the six engineering-hardening entries.

**The real defect found and fixed:** four of the six hardening entries were
appended with `Add-Content` at the file END, and the rotation then swept them into
the OLDEST dated section, `## 2026-09-15`, instead of `## 2026-09-30`. I moved
them verbatim into the `## 2026-09-30` section of `CHANGELOG.md`; the archive now
ends correctly at its `2026-09-15` section. Re-verified: heading multiset
difference is now **+6 at `2026-09-30`, 0 lost**.

**The "347" claim is corrected.** The prior doc's "48 sections and 347 bullets
before == after" was a **miscount**: by the file's `^- **` entry rule the
pre-rotation total was **314**, and by the broader `^- ` rule it was **343**, not
347. The post-rotation total is 320 entries / 349 bullets. The +6 delta is fully
accounted for by the six hardening entries; nothing is unaccounted.

**Two honest non-properties (documented, not "fixed"):**
- The CHANGELOG legitimately has **multiple sections with the same date** (several
  work sessions per day), so "no duplicate date" is false and is not asserted.
- One section, `## 2026-09-24`, is an **empty heading that pre-dates the rotation**
  (present in `ef886e5`). It is a prior data-quality blemish, not a rotation loss;
  left as-is (moving/rewriting history prose is out of scope).

**Executable guard added:** `src/lib/changelog-guard.test.ts` (4 tests) asserts the
active window (<= 7 dated sections), a gap-free contiguous date range, the archive
link, and an **append-only entry floor** (measured 349; floor 320, so a rotation
that drops entries trips it). It reads the docs as data, never source text.

## Phase 4 — Decide CI honestly, and gate the smoke path

**Status:** complete. Chose **option (a): restore CI at the true root.**

**Why the earlier blockers no longer apply** (ADR-H75 chose local-only):
1. `jdds.db` is now untracked and ignored, so a root workflow's sibling
   `backup.yml` (a daily `sqlite3 jdds.db` cron) would reference a file a checkout
   does not have — it would always fail. **Resolved by not restoring `backup.yml`**;
   `jdds.db` is runtime state, not a CI artifact.
2. There was no local gate for CI to mirror. Now `scripts/check-all.js` is a real,
   green gate, so the workflow mirrors it **step-for-step** with no divergence.

**What changed**

- **`.github/workflows/ci.yml` at the repository root** (the only path GitHub
  reads). Steps: checkout → Node 20 (`cache: npm`, `cache-dependency-path:
  Black-Eclipse-site/package-lock.json`) → Python 3.12 (`cache: pip`) → `pip
  install -r python/requirements.txt` → `npm ci --ignore-scripts` → `npx prisma
  generate` → `npx tsc --noEmit` → `npx eslint .` → `npm test` → `npm run
  test:evals`, with `defaults.run.working-directory: Black-Eclipse-site`.
  `concurrency` cancels superseded runs.
- **`backup.yml` fate: dropped, deliberately.** The daily `sqlite3 jdds.db` job is
  obsolete (untracked file); a local DB backup belongs in `scripts/`, not CI.
  Stated in the workflow header and ADR-H76.
- **ADR-H76** added to `docs/harness/decisions.md`, amending ADR-H75 (harness
  series, not mirrored — correct per the rule).
- **`test:smoke` given a home.** It stays operator-only (it hits the network). The
  trigger is documented in `CONTRIBUTING.md`: a human must run it **before a
  release tag**. It is never in `npm test` or CI.
- `CONTRIBUTING.md` also corrected its stale `jdds.db` claim ("committed seed
  snapshot") and documented the release gate + `.gitattributes`.

**Local transcript of the would-be CI steps** (run in order from
`Black-Eclipse-site/`, all exit 0):

```
npx prisma generate   -> exit 0
npx tsc --noEmit      -> exit 0
npx eslint .          -> exit 0
npm test              -> vitest 1898/160 + Python 1603 passed, exit 0
npm run test:evals    -> retrieval/contradiction/compaction PASS, ALL PASS, exit 0
```

**Honest caveat.** A root-level `.github/workflows/ci.yml` is **unverified against
GitHub Actions until it is pushed** — I cannot push. The steps are validated
locally in the same order; the user must observe the first real run.

**`.gitignore` still covers the runtime stores:** `gitignore-guard.test.ts` passes
unchanged (7 tests) after Phases 2–3.

## Phase 5 — Closeout

**All gates green (2026-09-30):**

| Gate | Baseline (prompt) | Final |
|---|---|---|
| `npx tsc --noEmit` | 0 | **0** |
| `npx eslint .` | 0 err / 24 warn | **0 err / 24 warn** |
| `npx vitest run` | 1891 / 159 | **1898 / 160** |
| Python pytest | 1603 | **1603** |
| `npm run test:evals` | ALL PASS | **ALL PASS** |
| `npm run check:all` | ALL GATES PASSED | **ALL GATES PASSED** |

The only moved gate is vitest **+7 tests / +1 file** (`gitignore-guard.test.ts`
gained 3 line-ending tests; `changelog-guard.test.ts` added, 4 tests). No test was
loosened or skipped.

**NAVIGATION updated** for: the CI workflow (`/.github/workflows/ci.yml`), the
`.gitattributes`/line-ending guard, the CHANGELOG rotation guard, and this closeout
doc.

**Prior progress doc** updated with a one-line pointer to this doc; its two stale
statements (Phase 0 R8 line counts; "four unrelated modified files") were corrected
in Phase 0 above.

**Invariants re-confirmed:** one `MCPManager` (`git grep` count 1); one
`ToolRegistry` (1); one `ApprovalStore` (1); one secret vault (`mcp_secrets_v1` +
the provider-key vault); MCP results carry `eclipseVerified: false` and are never
labelled Eclipse-verified; JDdS is not an authority (MCP/other sources are
labelled external); operator authorization is transport/token on every mutation
(unchanged from the hardening pass — the four R7 routes remain guarded); a server
save cannot silently widen authority (`test_mcp_config_roundtrip.py`); no
fabricated financial data; zero-config preserved (`npm install && npm run dev`,
`doctor.js` provisions `jdds.db`).

**`jdds.db`:** on disk (156,966,912 bytes), untracked, ignored
(`.gitignore:59`), never touched. The three unrelated user files remain modified
exactly as found.

## Phase 3 addendum — CHANGELOG section consolidation (limitations fixed)

The two documented "non-properties" are now fixed rather than documented:

- **Malformed headings fixed.** The archive had two single-hash date headings
  (`# 2026-09-24`, `# 2026-09-28`) that the parser did not match, mis-attaching
  their entries. Corrected to `##`. The guard now fails on any
  `^# YYYY-MM-DD` heading.
- **Duplicate dates eliminated.** All same-date sections were **consolidated by
  date**, so each date occupies exactly ONE section (active or archive). The
  CHANGELOG now keeps exactly the 7 most recent **dates**; the archive holds the
  remaining 9. The guard now asserts "each date is in exactly one file" — a real
  property.
- **Empty duplicate heading removed** (a `## 2026-09-24` immediately followed by
  another — pre-existing in `ef886e5`).
- **Entry count preserved: 350 before, 350 after.** A forensic diff-vs-HEAD now
  shows the two previously "mis-swept" entries (`Agentic roadmap (MCP Phase 5
  plan)`, `Memory/skills system review`) correctly re-dated to `2026-09-24` /
  `2026-09-28`; net heading entries 314 -> 321 = +6 hardening +1 closeout, **0
  truly lost**. UTF-8 valid, 0 U+FFFD.
- Guard strengthened to **6 tests** (window, per-date uniqueness, gap-free range,
  append-only floor, no malformed heading, archive link). vitest now **1900 / 160**.
