---
title: Git / Version-Control Subsystem
status: Current
last-verified: 2026-10-06
---

# Git / Version-Control Subsystem

A production-grade Git engine for an agentic coding environment. It is **not** a
wrapper around `git status`/`commit`/`push`: it is a layered subsystem with a
closed operation table, a structured error model, a risk/authorization engine, a
recoverable operation state machine, an operation journal, and a separate remote
collaboration (VCS provider) layer.

The single entry point for a reader who wants to change something:

```
Code (`python/harness/git/`)
  service.py        GitService — the facade every tool/route calls
  repository.py     discovery (normal/.git-file/bare/nested/worktree/submodule)
  executor.py       the ONE controlled git process (absolute argv, no shell,
                    scrubbed env, GIT_EDITOR=true, timeout, output cap)
  catalog.py        the CLOSED table of every allowed git argv (read + write)
  operations.py     GitOp/GitArg value validation + risk vocabulary
  parsers.py        machine-readable parsers (status/diff/log/blame/worktree/…)
  readers.py        read-only operations returning structured dicts
  state.py          the multi-step operation state machine + conflict markers
  safety.py         risk, secret/large-file scan, policy, protected branches,
                    untrusted-repo inspection
  journal.py        the operation journal + active-operation store (agent-memory.db)
  recovery.py       pre-op snapshot, reconcile, recovery options
  lock.py           the per-repository mutating lock
  messages.py       deterministic commit/PR drafting (no model call)
  approvals.py      the Git effect authorizer (dangerous/remote → single-use)
  tools.py          the local Git agent tools (git_*)
  vcs_tools.py      the remote VCS agent tools (vcs_*)
  register.py       one registration seam
  schemas.py        JSON input schemas for the tools

VCS (`python/harness/git/vcs/`)
  base.py           VCSProvider protocol + ProviderRegistry + remote-URL parser
  models.py         the normalized internal model (PR = MR)
  http.py           a stdlib-only authenticated JSON client
  github.py         GitHubProvider (REST v3 + Actions/Checks)
  gitlab.py         GitLabProvider (REST v4, merge requests)
  bitbucket.py      BitbucketProvider (REST 2.0, pull requests)

Routes (`python/harness/routers/git.py`)   /git/* for the front door + UI
Tests  (`python/tests/test_git_{engine,mutations,security,tools,integration}.py`)
```

## The layers

```
Agent → Tool Runtime → Git tool layer (git/tools.py, git/vcs_tools.py)
      → Git service (git/service.py)
          ├─ Repository Manager      repository.py
          ├─ Git Executor            executor.py  → code/sandbox.py
          ├─ Git Parser              parsers.py
          ├─ Git State Manager       state.py
          ├─ Git Safety Manager      safety.py
          ├─ Git Recovery Manager    recovery.py
          ├─ Git Operation Journal   journal.py
          └─ Git Lock                lock.py
      → VCS Abstraction (git/vcs/)  → GitHub / GitLab / Bitbucket
```

Local Git and remote hosting are **separate**: Git is the local VCS; GitHub/
GitLab/Bitbucket are remote collaboration providers behind `VCSProvider`.
Neither imports the other.

## Execution discipline

Every git process flows through `executor.run`:

- The argv is built by a `GitOp` from the **closed** `catalog.CATALOG`. The model
  never supplies an executable, a flag or a shell fragment. A value that looks
  like an option (`-…`), pathspec magic (`:`), contains a NUL, or fails its
  validator is refused in `operations.validate_op_args`.
- The first token is the ABSOLUTE git path with a fixed `-c core.longpaths=true`
  prefix — never model text.
- **No shell** (`shell=False`), a scrubbed environment (`policy.SECRET_ENV_ALLOWLIST`),
  `GIT_TERMINAL_PROMPT=0` (fail on a missing credential instead of hanging),
  `GIT_EDITOR=true`/`GIT_MERGE_AUTOEDIT=no` (no blocking editor), a bounded
  timeout, and a hard output cap.
- A non-zero exit is mapped to a structured `GitError` by `errors.classify_stderr`.

## Repository discovery

`repository.discover(start)` walks up to the nearest git root and reports:
normal `.git` dirs, `.git` **files** (linked worktrees/submodules), bare
repositories, nested repositories, and submodules (git dir under
`…/.git/modules/`). State is read from git every call — never cached.

## Status, diff, history

`readers.status` parses `status --porcelain=v2 -z --branch` into staged/unstaged/
untracked/ignored/conflicts/renamed/deleted plus branch tracking, ahead/behind
and detached HEAD. `readers.diff_*` return the patch, per-file insertions/
deletions, binary files, and (for the worktree) untracked files. History uses a
NUL-delimited `--format` so commits parse exactly.

## Safety and authorization

`catalog` classifies each operation SAFE / CAUTION / DANGEROUS / DESTRUCTIVE /
CRITICAL. The **autonomy profile** is the grant (`code.policy.allowed_tools`):
`plan_only` removes local writes AND remote actions; `edit_verify` keeps local
writes; `approve_external` keeps remote. Independently, the **Git effect
authorizer** (`git/approvals.py`) requires a single-use operator approval for any
`dangerous`/`destructive`/`critical` operation (hard reset, clean, force-delete,
rebase, tag delete) and for **every** remote action. A force push is `critical`
and is never the default.

Before a commit, `safety.scan_secrets` (reusing the ONE `session_index` pattern
set) and `safety.scan_large_files` run over the staged paths; a detection is a
warning, and a secret is a structured refusal unless explicitly overridden.

Repository policy lives in `.black-eclipse/git.json` (default/release branches,
pull strategy, conventional commits, protected branches, pre-commit/pre-push
checks, large-file threshold). A cloned repository is **untrusted**:
`safety.inspect_untrusted` reports hooks, sensitive local config, LFS and
submodules — and never executes a hook.

Additional hardening:

- **Worktree containment** — a worktree path is realpath-confined to the
  repository root or a sibling under its parent (the normal `git worktree`
  layout). A climb above the parent, a system path, or a traversal is refused, so
  a created tree and a later `worktree remove --force` stay inside the project's
  area.
- **Global-config escalation** — a `config_set` targeting the global scope is
  `dangerous` and needs a single-use approval (a machine-wide write can set
  `core.hooksPath`/`core.sshCommand` for every repository).
- **No refspec force** — a leading-`+` refspec is rejected; a force is only ever
  the explicit `--force-with-lease` flag.
- **No cross-host credential leak** — the VCS HTTP client drops the
  `Authorization` header when a redirect changes host, and a fetched CI job log is
  redacted before it reaches the model.

## Recovery

Multi-step operations (merge/rebase/cherry-pick/revert/bisect) are detected from
the repository's own sentinel files on every call (`state.active_operation`),
never a cached flag. A conflict is a structured `{code, files}` failure plus a
persisted active-operation record; the agent resolves, continues, or aborts.
`recovery.reconcile` reports a mismatch between the repository and the journal;
`recovery.recovery_options` reads the reflog for the honest next moves. Nothing
discards work automatically.

## Operation journal

`journal.GitJournal` (on `agent-memory.db`) records every mutating operation:
id, repository, type, **sanitized** argv (credential URLs and token shapes
redacted), risk, timestamps, status, exit code, error code, affected files and
recovery state. It never stores a token.

## Remote providers

`vcs.base.parse_remote` infers the provider from a remote URL. `ProviderRegistry`
constructs one provider per host, reading the token from an operator-declared
**environment variable** (never a value). `describe()` never exposes the token.
`VCSPullRequest` is the normalized model (GitLab MRs map onto it); provider
extras ride in `extra`. `vcs_tools` maps repositories/branches/commits/PRs/
reviews/comments/CI onto the agent; remote mutations are `external_action` tools
behind the single-use approval. A remote result is never faked: no credentials or
no provider ⇒ a structured failure.

## Error model

One closed code vocabulary (`errors.ALL_CODES`), each with a plain one-sentence
recovery hint: `MERGE_CONFLICT`, `REBASE_CONFLICT`, `NON_FAST_FORWARD`,
`AUTHENTICATION_FAILED`, `PROTECTED_BRANCH`, `FORCE_PUSH_REQUIRES_AUTHORIZATION`,
`SECRET_DETECTED`, `LOCKED_REPOSITORY`, … A tool result is always
`{success, operation, repository, result, warnings, error}`.

## Configuration

`.black-eclipse/git.json` (repository policy, above). Provider tokens come from
standard env vars (`GITHUB_TOKEN`/`GH_TOKEN`, `GITLAB_TOKEN`, `BITBUCKET_TOKEN`)
or an operator-declared name. No new runtime setting is required for
zero-config: with no remote and no token, the local Git engine works fully and
every remote action reports honestly.

## Testing

`test_git_engine.py` (discovery, table validation, parsers), `test_git_mutations.py`
(stage/commit/branch/checkout-safety/merge/rebase/cherry-pick/revert/reset/stash/
tags/remotes/worktree/bisect/clean/journal/recovery), `test_git_security.py`
(injection, traversal, credential leakage, malicious hooks, untrusted config),
`test_git_tools.py` (registration, the autonomy boundary, the effect authorizer,
end-to-end tool calls), `test_git_integration.py` (the acceptance workflow + the
provider layer with a mocked HTTP client). Every test uses an **isolated
temporary repository**; none touches the Eclipse source repository.

## Selective staging and automated rebase (no TTY required)

Git's interactive features normally need a terminal. Both are driven
machine-first here:

- **Hunk staging** — `git/diffs.py` parses a unified diff into files and hunks
  and re-renders a patch containing only the chosen subset, which
  `git apply --cached` stages. Tools: `git_list_hunks`, `git_stage_hunks`,
  `git_unstage_hunks`, `git_apply_patch`. `git add -p` is not needed and no
  terminal is opened.
- **Interactive rebase** — `git/rebase_plan.py` builds the environment for
  `git rebase -i` with a machine SEQUENCE EDITOR (`_sequence_editor.py`) and a
  machine MESSAGE EDITOR (`_message_editor.py`), so `git_rebase_plan` performs
  `pick`/`reword`/`edit`/`squash`/`fixup`/`drop` and reordering from a structured
  plan, deterministically. A PARTIAL plan never reorders or drops an unnamed
  commit.

## Full capability surface

Beyond the core engine, `git/tools_extra.py` exposes the long tail so no
capability is missing: `git_move_path` (`git mv`), `git_remove_paths`
(`git rm`), `git_restore` (discard worktree changes), `git_unset_upstream`,
`git_stash_branch`, `git_stash_clear`, `git_tag_show`, `git_worktree_prune`,
`git_worktree_move`, `git_submodule_init`, `git_submodule_sync`, `git_lfs_fetch`,
`git_lfs_pull`. Every one is classified by the same risk engine and gated by the
same authorizer.

## Live provider tests (opt-in)

`test_git_provider_live.py` exercises a REAL GitHub/GitLab/Bitbucket account. It
is skipped unless the operator opts in:

```
BLACK_ECLIPSE_PROVIDER_IT=1
BLACK_ECLIPSE_PROVIDER_REPO=owner/repo
GITHUB_TOKEN=...          # or GITLAB_TOKEN / BITBUCKET_TOKEN
```

It creates a throwaway branch, opens/reads/closes a PR/MR and cleans up; it never
merges. It is deliberately NOT in `npm test` (a real credential and network call
must never gate the offline suite). The mocked-HTTP tests in
`test_git_integration.py` cover the mapping deterministically.

## IDE / UI integration

`/api/git` (Next.js) is a THIN proxy over the runtime's `/git/*` routes — it holds
no Git logic. `src/lib/git/service.ts` forwards to the Python engine (discovery,
journal, lock, risk/authorization); `src/lib/git/client.ts` is the browser-safe
wrapper the Settings Git panel (`src/components/screens/git-panel.tsx`) uses.
Types live in the client-safe `src/lib/git/types.ts`, so the client bundle never
imports a server-only module. When the runtime is unavailable the route returns
503 honestly — there is no fallback to a second (TypeScript) Git implementation.
This corrects an earlier standalone TS git wrapper that bypassed the engine.

## Known limitations

- A provider operation is only as capable as its host: GitLab/Bitbucket surface
  reviews/checks differently from GitHub and are mapped where they fit (e.g.
  GitLab expresses review as approvals; Bitbucket reviewers are account uuids).
  Functionality a host does not offer raises `NOT_IMPLEMENTED` rather than being
  faked.
- The live provider tests need a real token; they are skipped by default so the
  offline suite never depends on the network.


