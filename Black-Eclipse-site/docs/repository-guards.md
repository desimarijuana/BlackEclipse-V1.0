---
title: Repository Guards
status: Current
last-verified: 2026-11-11
---

# Repository Guards

What stops an accidental `--force`, a stray secret, or an unannounced change from
reaching the remote — and what still needs a GitHub plan change.

## The gap GitHub shows you

GitHub prints **"Your main branch isn't protected"** on
`Settings → Branches` for this repository because it has **no branch protection
rule and no ruleset** on `main`. Both APIs answer `403`:

> Upgrade to GitHub Pro or make this repository public to enable this feature.

That is not a configuration mistake. The repository is **private**, and GitHub
only enforces server-side branch protection for private repositories on a paid
plan. No token, script, or workflow can turn it on for free.

Server-side protection is the only thing that stops a **deliberate** actor with
push access. Everything in this repository is a guard against **mistakes**, and
is honest about it.

## What runs today (free, per clone)

`.githooks/` is the committed hook directory; `core.hooksPath` is pointed at it by
`scripts/install-git-hooks.js`, which runs from `postinstall`, so a fresh
`npm install` installs every guard with no manual step.

| Hook | Blocks | Bypass (deliberate) |
|---|---|---|
| `pre-commit` | a commit authored by an email not linked to the GitHub account; a staged secret (`.env`, keys, `*.db`, provider tokens) | `GIT_COMMIT_ALLOWED_EMAIL` / `SKIP_SECRET_SCAN=1` |
| `commit-msg` | a non-doc change committed without a `docs/CHANGELOG.md` entry | `SKIP_CHANGELOG_CHECK=1` |
| `pre-push` | **deleting** or **rewriting** (non-fast-forward) `main` | `SKIP_PUSH_GUARD=1` |

`pre-push` covers the two operations the GitHub banner names — force push and
deletion — on the branches that matter. It reads the ref-update lines git feeds
it, so it sees the real remote tip; a normal fast-forward push is untouched.
Protected branches are `main` plus `PUSH_GUARD_BRANCHES` (space-separated).

Limits, stated plainly:

- `git push --no-verify` skips every hook. So does a clone that never ran
  `npm install`.
- If the remote tip is not present in the clone the hook cannot judge ancestry
  and defers to git, which still rejects a non-fast-forward push unless it is
  forced.
- A **worktree** shares the main clone's hooks and config, so guards apply there
  too.

## The actual fix: two options

1. **Make the repository public** — free protection, but the source is public.
   Usually the wrong trade for this project.
2. **Upgrade the account to GitHub Pro** (`Settings → Billing`, ~$4/month for an
   individual) — unlocks rulesets and branch protection on private repositories,
   which are then enforced by GitHub, not by a hook.

After the upgrade, the ruleset to create on `main`:

| Rule | Value |
|---|---|
| Restrict deletions | on |
| Block force pushes | on |
| Require a pull request | on, 0 required approvals (solo) |
| Required status check | `typecheck · lint · unit · python · evals` (the `ci` job in `.github/workflows/ci.yml`), strict |
| Bypass list | empty |

Then `main` can only move forward through a green PR, and the `main`-rewrite
recovery branches (`backup/main-wip-*`) stop being a recurring need. Creating the
ruleset is a single API call — this is a settings change, not a repository
change, so nothing about it lives in git.

Keep `git push` direct-to-`main` until the ruleset exists; the pre-push guard
allows fast-forwards, so the current workflow keeps working.
