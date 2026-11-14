---
title: Open-Source Publication Readiness
status: Current
last-verified: 2026-11-14
---

# Open-Source Publication Readiness

**Who this is for:** whoever is about to make this repository public, and whoever
has to prove the public tree is safe.

This doc owns the **publication mechanics** (what makes a private working
repository safe to publish). It does not repeat the product gate or the
deployment gate:

| Question | Owning doc |
|---|---|
| Is this build releasable, and what is still open for production? | [`PRODUCTION-READINESS.md`](./PRODUCTION-READINESS.md) |
| What stops an accidental force-push or secret commit? | [`repository-guards.md`](./repository-guards.md) |
| What is the licence, and what is different about `pine-engine/`? | [`../LICENSE`](../../LICENSE), [`../pine-engine/NOTICE.md`](../pine-engine/NOTICE.md) |
| What legal documents exist and what is still Draft? | [`legal/README.md`](./legal/README.md) |

The app is **MIT** and already markets itself as open source; the repository is
currently **private**. Publication is therefore a repository operation, not a
licence change.

---

## 1. The one-screen answer

Most of the public surface already exists: `LICENSE`, `SECURITY.md`,
`CONTRIBUTING.md`, `DCO`, `CODEOWNERS`, CI, Dependabot, hooks, and a canonical
docs tree. What is missing is **history hygiene** and a small set of community
files.

| # | Blocker | Evidence |
|---|---|---|
| O1 | Git history contains `jdds.db` snapshots | A 60 MB historical blob contains 106 trades, 58 journal days, 1 journal profile, 40 tags. See §2. |
| O2 | ~~History has never been scanned for credentials~~ **resolved in the mirror** | `scripts/scan-secrets.js` scans **tracked HEAD only**. A `gitleaks` 8.30.1 scan over `--all` found **two real hardcoded tokens** in old commits; both were scrubbed with `--replace-text` and **must still be rotated**. The final mirror scans clean with `.gitleaks.toml` (reviewed allowlist for fixtures). |
| O3 | Tracked files contain absolute home-directory paths | `docs/harness/baselines/*.json`, `docs/harness/roadmap/phase-00-policy-and-baseline.md`, some `media/` artifacts. |
| O4 | Personal author e-mail is in history | Publishing history publishes every `%ae`. |
| O5 | Community files were incomplete | Fixed: root `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, issue/PR templates, `check:oss`. |
| O6 | Legal/IP review for public distribution | `docs/legal/*` are Draft; the `cfa-*` skills and "Bloomberg-inspired" wording need a trademark read. |
| O7 | Branch protection is unavailable here | Private + Free plan returns `403`; making the repository public unlocks it for free. |
| O8 | No code scanning | Fixed: `.github/workflows/codeql.yml`. |

**Do not flip the existing private repository to public.** That publishes O1–O4.
Create the public repository from a rewritten history (§2), or from a fresh
snapshot with a deliberate initial commit.

---

## 2. Scrub the history (the hard blocker)

`jdds.db` is untracked now (`git ls-files` shows none), but it is still in every
old commit. A clone gets the blobs and the journal inside them.

Confirm for yourself:

```bash
git log --all --oneline -- Black-Eclipse-site/jdds.db
git rev-list --objects --all \
  | git cat-file --batch-check='%(objecttype) %(objectname) %(objectsize) %(rest)' \
  | sort -k3 -n -r | head
```

### Recommended: publish a rewritten mirror

`git filter-repo` is the maintained tool (install it separately; it is not a
repo dependency). A helper wraps the same steps and never touches the live
clone:

```powershell
pwsh -File scripts/scrub-public-history.ps1 -SourceUrl <private-clone-url>
# optional: -Replacements .\replacements.txt
```

It clones a mirror to a temp directory, strips the database paths, verifies
they are gone, and prints the push steps. It does **not** push.

```bash
# 1. Work on a mirror, never on the live clone.
git clone --mirror <private-clone-url> BlackEclipse-public.git
cd BlackEclipse-public.git

# 2. Remove every database snapshot from every commit.
git filter-repo \
  --invert-paths \
  --path Black-Eclipse-site/jdds.db \
  --path-glob 'Black-Eclipse-site/*.db' \
  --path-glob 'Black-Eclipse-site/*.db-wal' \
  --path-glob 'Black-Eclipse-site/*.db-shm'

# 3. Rewrite personal paths and author e-mail. Keep this file OUTSIDE the repo.
#    Use placeholders in the doc; the real values live only in your shell.
cat > ../replacements.txt <<'EOF'
C:\\Users\\<your-user>\\==>C:\\Users\\<user>\\
/Users/<your-user>/==>/Users/<user>/
<personal-email>==><id>+<handle>@users.noreply.github.com
EOF
git filter-repo --replace-text ../replacements.txt

# 4. Prove the result before pushing.
git log --all --oneline -- '*jdds.db'        # must print nothing
git rev-list --objects --all \
  | git cat-file --batch-check='%(objecttype) %(objectname) %(objectsize) %(rest)' \
  | sort -k3 -n -r | head                    # no multi-MB .db blobs

# 5. Push the rewritten mirror to the NEW public repository.
git remote add public <public-repo-url>
git push --mirror public
```

Notes:

- **Every commit hash and tag changes.** Re-create annotated tags on the
  rewritten commits (`v0.4.0` etc.) rather than pushing the old tag objects.
- **The mirror is a snapshot.** Re-run the script after the last commit you
  intend to publish; do not push a mirror built from an earlier tree.
- The old private repository keeps its history; do not delete it. It is the
  provenance record.
- If a rewrite is too risky, the alternative is a **fresh repository with one
  initial commit** of the current tree. You lose history but the public snapshot
  is trivially clean. Say which one you chose in the release note.

### After the rewrite

Run the credential scan over history, not just HEAD:

```bash
gitleaks detect --source . --log-opts="--all" --redact
# or
trufflehog git file://. --only-verified
```

Use the committed config so the scan is repeatable:

```bash
gitleaks detect --source <mirror-or-worktree> --config .gitleaks.toml \
  --log-opts="--all" --redact
```

The config allowlists only triaged non-secrets (test fixtures, `STORAGE_KEY`
constants, eval `"key"` fields, a generated cache hash, and the fake
`AKIA...EXAMPLE` string). A hit outside that list is a real finding.

Any hit is a real incident: **rotate the credential before pushing**, then
scrub it with `--replace-text`. Deleting a token from history does not make it
un-leaked; the scan found two live service tokens in this repository's past, so
rotation is mandatory even after the mirror is clean.

---

## 3. The re-runnable public-release preflight

`npm run check:oss` (from `Black-Eclipse-site/`) checks the things a release
gate does not:

- no tracked `.env`, `*.db`, key, or connector artifact;
- the community files above exist;
- `package.json` has `repository`, `homepage`, and `bugs`;
- **history** has no `.db` or secret-bearing path;
- tracked files have no absolute home-directory path;
- personal author e-mails are reported;
- the normal `scan-secrets.js` track scan passes.

It is intentionally **not** part of `check:all`: a private working repository
legitimately fails O1 until it is rewritten. Run `check:oss` on the public
snapshot; it must exit 0 before you flip visibility.

```bash
cd Black-Eclipse-site
npm run check:oss          # human output; exit 1 means do not publish
npm run check:oss -- --json
```

---

## 4. Publication-day checklist

Repository content:

- [ ] `npm run check:oss` exits 0 on the public snapshot.
- [ ] `git status --short` is empty; the tree is a tagged commit.
- [ ] `npm run check:all` exits 0 on that commit.
- [ ] `gitleaks`/`trufflehog` over `--all` is clean.
- [ ] `docs/releases/<version>.md` and the `CHANGELOG.md` entry exist.
- [ ] Root `README.md` names the current version and the measured live number.
- [ ] `CONTRIBUTING.md` → `Black-Eclipse-site/CONTRIBUTING.md` → `DCO` resolves.
- [ ] Issue templates, PR template, and Code of Conduct are present.
- [ ] `media/` contains no generated build artifacts or machine-local paths.

GitHub settings (all free once public):

- [ ] Enable **secret scanning** and **push protection**.
- [ ] Enable **Dependabot alerts** (`.github/dependabot.yml` is already committed).
- [ ] Import `.github/ruleset.json` on `main` (see `repository-guards.md`).
- [ ] Turn on **private vulnerability reporting** (`SECURITY.md` depends on it).
- [ ] Confirm the first **CodeQL** run is green.
- [ ] Create the `@BlackEclipse/maintainers` team or replace it in `CODEOWNERS`.
- [ ] Set repository description, topics, and the social preview.
- [ ] Publish the release note and tag.

---

## 5. Legal and IP review before public distribution

These are judgement calls for the owner, not code defects. They are listed so
they are not discovered after launch.

- **MIT + AGPL scoping.** Root `LICENSE` scopes the repository to MIT and carves
  out `pine-engine/` as AGPL-3.0-only. Keep that carve-out in every public
  mirror and in the release assets.
- **Contract pack is Draft.** `docs/legal/*` is not legal advice and is not
  reviewed. A **source-only, self-hosted, single-operator** release can ship with
  the README saying so; a hosted service cannot (C11/C12 in
  `PRODUCTION-READINESS.md`).
- **`cfa-*` skills.** `.black-eclipse/skills/cfa-*` are original study notes, but
  "CFA" is a CFA Institute trademark and the module list tracks their
  curriculum. Add a clear "not affiliated with CFA Institute" notice or rename
  the skills before public distribution.
- **"Bloomberg-inspired".** Descriptive comparison is usually nominative, but do
  not use the Bloomberg name or trade dress as branding. Keep the wording
  descriptive.
- **Market-data redistribution.** Do not ship a seeded `jdds.db`. The app
  fetches and stores data locally at runtime; that is a different act from
  redistributing a snapshot. This is the same reason O1 must be scrubbed.
- **Third-party dependency licences.** `pine-engine/` is the only known copyleft
  component. If a dependency audit is required, generate a notices file from the
  locked tree rather than hand-writing claims.

---

## 6. What is outside this doc

- The **production** gates (soak, alert webhook, container, secrets, second
  reviewer) live in `PRODUCTION-READINESS.md`. Publication does not close them;
  a public repository is not a production sign-off.
- The **organisation** actions (creating the team, buying a plan, counsel) are
  inputs only a person can supply.
- The **website/browser lane** is retired. Do not restore it while preparing a
  public release; the desktop app is the product.

---

## 7. Progress log (append-only)

| Date | State | Evidence |
|---|---|---|
| 2026-11-14 | History credential scan | **2 real tokens found and scrubbed** | `gitleaks 8.30.1` over `--all` on the first clean mirror found two hardcoded service tokens in old commits (not present at HEAD). A second mirror was produced with `--replace-text` and a mailmap; the tokens are absent (`git log -S` empty) and the history scan is green with the new `.gitleaks.toml`. **Both tokens must be rotated**; history removal is not revocation. Remaining findings were triaged false positives (test fixtures, storage-key literals, eval `"key"` fields, a cache hash, the fake `AKIA...EXAMPLE`). |
| 2026-11-14 | Clean mirror produced and verified | Ran `scripts/scrub-public-history.ps1` on a mirror of this repository: `jdds.db`/`eclipse-memory.db`/`agent-memory.db` are absent from every commit, pack size fell from 79.9 MiB to 40.3 MiB, and a clone of the mirror passes `npm run check:oss` with **0 warnings** after a mailmap rewrite of the personal author email. The live private history is unchanged and must not be flipped to public. Not pushed. Remaining before push: O2 (gitleaks/trufflehog over `--all`), create the new public repository, re-create/push tags. |
| 2026-11-14 | Scaffolding added | Root `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, issue/PR templates, `package.json` metadata, CodeQL workflow, `scripts/oss-preflight.js` (`npm run check:oss`), and the mirror-only `scripts/scrub-public-history.ps1`. Personal absolute paths were removed from the bulk importers (now `BE_IMPORT_ROOT`, default `/data/imports/`, gitignored) and the roadmap/media docs. `check:oss` now reports exactly one blocker: `jdds.db` in history (O1). O2 (history credential scan) and the history rewrite remain operator steps. |
