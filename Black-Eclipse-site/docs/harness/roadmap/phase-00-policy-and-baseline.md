---
title: "Phase 0 — Recon, Policy Decision and Baseline Freeze"
status: Done
phase: 0
depends_on: []
unlocks: [1, 2, 3]
last-verified: 2026-10-01
---

# Phase 0 — Recon, Policy Decision and Baseline Freeze

| | |
|---|---|
| **Depends on** | — (first phase) |
| **Unlocks** | Phases 1, 2, 3 |
| **Estimated work** | 2–4 h of agent time, zero runtime behaviour change |
| **Deliverable type** | policy module + permission change + tests + 3 ADRs + a recorded baseline |
| **New ADRs** | ADR-H97, ADR-H98, ADR-H99 (H93–H96 were taken by the 2026-09-30 closeout) |
| **Prompt to copy** | [§11 below](#11-implementation-prompt-copy-this-to-opencode) |

## Contents

- [1. Goal](#1-goal)
- [2. Why this phase exists (the problem in the real code)](#2-why-this-phase-exists-the-problem-in-the-real-code)
- [3. In scope](#3-in-scope)
- [4. Who can use it (the non-expert obligation)](#4-who-can-use-it-the-non-expert-obligation)
- [5. Non-goals (do not do these)](#5-non-goals-do-not-do-these)
- [6. Exact contracts to create](#6-exact-contracts-to-create)
  - [6.1 Permission nouns — `python/harness/skills/manifest.py`](#61-permission-nouns--pythonharnessskillsmanifestpy)
  - [6.2 The actor rule — `python/harness/skills/permissions.py`](#62-the-actor-rule--pythonharnessskillspermissionspy)
  - [6.3 The policy module — `python/harness/code/policy.py`](#63-the-policy-module--pythonharnesscodepolicypy)
  - [6.4 Baseline artifact](#64-baseline-artifact)
- [7. Work items (ordered)](#7-work-items-ordered)
- [8. Deliverables](#8-deliverables)
- [9. Acceptance gates](#9-acceptance-gates)
- [10. Definition of done](#10-definition-of-done)
- [11. Implementation prompt (copy this to OpenCode)](#11-implementation-prompt-copy-this-to-opencode)

## 1. Goal

Make the code capability a **deliberate, tested policy decision** instead of
leaving it an accidental impossibility — and freeze the exact baseline so every
later phase can prove it did not regress anything.

Phase 0 ships **no tools**. It ships the authority that all later tools obey.

## 2. Why this phase exists (the problem in the real code)

`python/harness/skills/permissions.py` currently refuses the capability at the
source:

```python
SAFE_PERMISSIONS: frozenset[str] = frozenset({
    "data.read", "research.read", "analysis.execute",
    "report.generate", "skill.invoke", "portfolio.read",
    "external.network",
})

OPERATOR_PERMISSIONS: frozenset[str] = frozenset({
    "skill.create", "skill.review", "skill.enable", "skill.disable", "portfolio.modify",
})

BLOCKED_PERMISSIONS: frozenset[str] = FORBIDDEN_PERMISSIONS | frozenset({"code.execute"})
```

and `BLOCKED_PERMISSIONS` is subtracted from **every** actor's grant set:

```python
def granted(self) -> frozenset[str]:
    base = set(SAFE_PERMISSIONS)
    if self.operator:
        base |= OPERATOR_PERMISSIONS
        base |= set(self.grants)
    base -= BLOCKED_PERMISSIONS          # ← nothing can ever hold code.execute
    ...
```

`FORBIDDEN_PERMISSIONS` (in `skills/manifest.py`) also blocks `code.write`.
`docs/DECISIONS.md` ADR-025 states the reason plainly: *"Duplicate infrastructure
and autonomous self-modification are forbidden."*

**That reasoning is still correct.** Phase 0 does not delete it — it introduces a
*second actor class* that can hold the code permissions **only when a run is
bound to a workspace and carries an autonomy profile**, and it adds a test proving
the default actor is still blocked. A coding agent must not be able to "fix" a
failing permission test by removing the constant; after this phase such a change
fails the freeze test from Phase 10 and the policy tests added here.

## 3. In scope

1. Record the baseline gate result verbatim.
2. New `python/harness/code/policy.py` — **the single policy authority** for the
   whole code capability (mirroring how `skills/permissions.py` is the single
   authority for skills).
3. New permission nouns declared in `skills/manifest.py` and reasoned about in
   `skills/permissions.py`.
4. A `CodeActor` / workspace-scoped grant path that permits the code permissions
   **only** under a binding, while the default local actor stays blocked.
5. The protected-path list as **data** (not prose).
6. ADR-H97, ADR-H98, ADR-H99.

## 4. Who can use it (the non-expert obligation)

This phase decides policy, so it is where the audience rule must be stated first:
**the capability is for everyone in finance**, not for engineers, quants or
accountants only. An analyst, a portfolio manager, a trader, an advisor, an
accountant, a risk officer, a student, a journalist and a small-business owner
must all be able to use what later phases build, without knowing git, Python,
"worktrees", terminals, allowlists or autonomy profiles.

Three consequences that bind every later phase, decided here:

1. **Vocabulary.** The names created in this phase are *mechanism* names and stay
   internal: `plan_only` / `edit_verify` / `approve_external`, `resolve_within`,
   `PROTECTED_PATHS`, `PolicyDecision.code`. They appear in the trace, the logs and
   the ADRs — **never** in a user-facing string. The surface names the finance job
   instead ("Check my portfolio for risks overnight").
2. **The denylist is policy data.** Add the mechanism word list from
   `roadmap/README.md` §0 to `code/policy.py` as `PLAIN_LANGUAGE_DENYLIST`, so the
   later phases' plain-language gate reads it from one place instead of each
   re-typing a list.
3. **Refusal text is part of the contract.** `PolicyDecision.reason` must be
   **safe to show a human**: one plain sentence ("That file is part of Eclipse's
   own data and can't be changed by a task.") with a stable `code` for the
   machine. It must never leak a secret, a path outside the workspace, or a
   mechanism term. This is the same discipline as the MCP diagnostics layer, whose
   every refusal carries a plain-language `recovery` step.

Phase 0 ships no user-facing surface, so its own gate is only that the denylist
exists as data and the `reason` strings satisfy the rule — the enforceable
user-facing gates start in Phase 1.

## 5. Non-goals (do not do these)

- No filesystem, shell, patch or exec tool. Not even a stub.
- No UI, no route, no front-door change.
- No change to any finance tool, agent prompt, or the retrieval/research paths.
- No dependency added.
- No weakening of `trade.execute` / `broker.modify` / `production.modify`.
- Do not commit, push, or open a PR.

## 6. Exact contracts to create

### 6.1 Permission nouns — `python/harness/skills/manifest.py`

Extend the `Permission` literal (keep the existing style — a literal of strings,
validated by pydantic):

```python
Permission = Literal[
    # ... existing ...
    "code.read",          # read files inside a bound workspace
    "code.write",         # create/modify/delete inside a bound workspace
    "code.execute",       # run an allowlisted command / a bounded program
    "git.read",           # status/log/diff inside a bound workspace
    "git.write",          # stage/commit — OPERATOR ONLY, never auto-granted
    "workspace.admin",    # allocate/release a worktree — OPERATOR ONLY
    "command.execute",
]
```

Keep `FORBIDDEN_PERMISSIONS` unchanged except: `code.write` and `code.execute`
**move out** of it into a new, explicitly-named tuple so the intent is legible:

```python
# Never grantable to ANY actor, ever. Trading and production mutation.
FORBIDDEN_PERMISSIONS: tuple[str, ...] = (
    "trade.execute",
    "broker.modify",
    "production.modify",
)

# Grantable ONLY to a workspace-bound code actor (see permissions.CodeActor).
# Not part of the safe set; not part of the operator set.
CODE_PERMISSIONS: tuple[str, ...] = (
    "code.read", "code.write", "code.execute",
    "git.read", "git.write", "workspace.admin", "command.execute",
)
```

> Adjust the literal names to match what is actually in `manifest.py` today — read
> it first; do not assume the tuple above is byte-identical to the existing
> `FORBIDDEN_PERMISSIONS`.

### 6.2 The actor rule — `python/harness/skills/permissions.py`

Add a workspace binding to the actor, and only grant code permissions when it is
present **and** the profile allows the specific verb:

```python
@dataclass(frozen=True)
class Actor:
    id: str = "local"
    operator: bool = False
    grants: frozenset[str] = field(default_factory=frozenset)
    scopes: frozenset[str] = field(default_factory=frozenset)
    # NEW — set only by the code run path (Phase 1+). Absent = no code capability.
    workspace_id: Optional[str] = None
    autonomy: Optional[str] = None        # "plan_only" | "edit_verify" | "approve_external"

    def granted(self) -> frozenset[str]:
        base = set(SAFE_PERMISSIONS)
        if self.operator:
            base |= OPERATOR_PERMISSIONS
            base |= set(self.grants)
        base -= FORBIDDEN_PERMISSIONS
        if self.workspace_id and self.autonomy:
            base |= _code_grants(self.autonomy)      # from code/policy.py
        if self.scopes:
            return frozenset(base & set(self.scopes))  # scopes only ever NARROW
        return frozenset(base)
```

`_code_grants(autonomy)` lives in **`code/policy.py`** (single authority):

| autonomy | grants |
|---|---|
| `plan_only` | `code.read`, `git.read` |
| `edit_verify` | `code.read`, `code.write`, `git.read`, `code.execute`, `command.execute` |
| `approve_external` | the `edit_verify` set **plus** `git.write`, `workspace.admin` — each still requiring a per-action single-use approval (Phase 5) |

An unknown autonomy string grants **nothing** (fail-closed), exactly like the MCP
`trust` tier.

### 6.3 The policy module — `python/harness/code/policy.py`

One module, three data tables, one decision function. No other module may make
these decisions.

```python
"""The ONE authority for the code capability's policy.

Nothing here executes anything. This module answers, deterministically and without
side effects: may this run read/write/execute this thing, in this workspace, under
this autonomy profile? Every later phase calls it; none of them re-implements it.
"""

AUTONOMY_PROFILES: tuple[str, ...] = ("plan_only", "edit_verify", "approve_external")

# Absolute — even inside a workspace, even for an operator.
PROTECTED_PATHS: tuple[str, ...] = (
    "jdds.db",                     # the market-data vault
    "agent-memory.db",
    "eclipse-memory.db",
    ".env", "*.env",
    "mcp-servers.json",            # holds discovered env values
    "prisma/migrations/**",
    ".git/**",
    "python/harness/code/policy.py",        # FROZEN (Phase 10)
    "python/harness/skills/permissions.py", # FROZEN (Phase 10)
    "python/harness/mcp/approvals.py",      # FROZEN (Phase 10)
    "scripts/check-all.js",                 # FROZEN (Phase 10)
    "**/*.pem", "**/*.key", "**/id_rsa*",
)

IGNORED_DIRS: tuple[str, ...] = (
    ".git", "node_modules", "src/generated", "__pycache__",
    ".next", "_backups", ".black-eclipse", "scripts/vendor",
)

IGNORED_GLOBS: tuple[str, ...] = ("*.db", "*.sqlite", "*.png", "*.jpg", "*.woff2", "*.zip")

# The command classes Phase 3 implements. Declared here because the POLICY owns
# the vocabulary; commands.py owns the argv templates.
COMMAND_CLASSES: tuple[str, ...] = (
    "typecheck", "lint", "unit_test", "python_test",
    "build", "format_check", "git_read", "dependency_install",
)

NETWORK_DEFAULT: bool = False          # denied unless a class explicitly allows it
SECRET_ENV_ALLOWLIST: tuple[str, ...] = (
    "PATH", "HOME", "USERPROFILE", "SYSTEMROOT", "TEMP", "TMP", "TMPDIR",
    "LANG", "PYTHONIOENCODING", "NODE_OPTIONS",
)   # everything else is dropped from the child environment — never os.environ passthrough

# Words that must never appear in a user-facing string or an i18n key. The surface
# names the finance JOB, never the mechanism. Every phase that ships UI asserts
# against this list — it lives here so no phase re-types it.
PLAIN_LANGUAGE_DENYLIST: tuple[str, ...] = (
    "sandbox", "worktree", "workspace", "allowlist", "autonomy", "digest",
    "argv", "cwd", "stderr", "stdout", "patch", "diff", "manifest",
    "operator", "policy engine", "tool registry", "exit code",
    "verification ledger", "repo", "repository", "commit", "branch", "head",
)

@dataclass(frozen=True)
class WorkspaceBinding:
    id: str
    root: Path              # absolute; must be inside the allowed workspace root
    base_revision: str      # a git rev or a snapshot digest
    strategy: str           # "worktree" | "snapshot"

def is_protected(rel_path: str) -> bool: ...
def is_ignored(rel_path: str) -> bool: ...
def resolve_within(root: Path, candidate: str) -> Path: ...   # raises PolicyDenial
def decide_write(actor, binding, rel_path) -> PolicyDecision: ...
def decide_command(actor, binding, command_class, argv) -> PolicyDecision: ...
def code_grants(autonomy: str) -> frozenset[str]: ...

@dataclass(frozen=True)
class PolicyDecision:
    allowed: bool
    code: str          # "OK" | "PROTECTED_PATH" | "OUTSIDE_WORKSPACE" | "PROFILE_DENIED"
                       # | "SANDBOX_UNAVAILABLE" | "COMMAND_NOT_ALLOWLISTED" | "UNKNOWN_AUTONOMY"
    reason: str        # ONE PLAIN SENTENCE safe to show a human — no secrets, no paths
                       # outside the workspace, no mechanism term from the denylist above
```

**`resolve_within` must be path-safe by construction** — this is the single place
traversal is stopped:

1. Resolve the candidate against the root and `realpath()` it.
2. Reject if the result is not `root` itself or under `root` (prefix compare on
   **resolved** paths, never on the raw string).
3. Reject if any path component is a symlink pointing outside the root.
4. Reject protected paths and, for write decisions, ignored dirs.

### 6.4 Baseline artifact

Copy the raw output of the gate into the progress log. The exact commands:

```bash
cd "<repo>/Black-Eclipse-site"
npm run check:all
git status --short
```

## 7. Work items (ordered)

1. Create `docs/harness/roadmap/progress/phase-00-progress.md` with the gate
   commands as unchecked boxes.
2. Run the baseline gate and paste the **raw** output (see §9). Note the vitest and
   pytest counts exactly as printed.
3. Read `python/harness/skills/manifest.py` and `permissions.py` in full before
   editing. Record the real `FORBIDDEN_PERMISSIONS` contents in the progress log —
   do not trust the sketch in §6.1.
4. Create `python/harness/code/__init__.py` (docstring only, no imports) and
   `python/harness/code/policy.py` per §6.3.
5. Edit `skills/manifest.py`: permission nouns + `CODE_PERMISSIONS` +
   `FORBIDDEN_PERMISSIONS` narrowed to trade/broker/production.
6. Edit `skills/permissions.py`: `Actor.workspace_id` / `Actor.autonomy`, the
   `granted()` change, and the `code_grants` import from `code.policy`. Keep
   `DEFAULT_ACTOR` / `OPERATOR_ACTOR` **unchanged in behaviour** (no workspace =
   no code permissions).
7. New tests `python/tests/test_code_policy.py`:
   - default actor: `code.read`/`code.write`/`code.execute` all denied;
   - operator actor without a workspace: still denied;
   - `plan_only` + workspace: read yes, write **no**, execute **no**;
   - `edit_verify` + workspace: read/write/execute/command yes, `git.write` **no**;
   - `approve_external` + workspace: `git.write`/`workspace.admin` present in the
     grant set (the *approval* is Phase 5's job, not the grant's);
   - unknown autonomy string → grants nothing;
   - `resolve_within` refuses `..`, an absolute path outside the root, a symlink
     escape, and returns the real path for a legal nested file;
   - `is_protected` refuses `jdds.db`, `prisma/migrations/x.sql`, `.env`,
     `python/harness/code/policy.py`;
   - `decide_command` refuses `rm -rf /`, `curl x`, `powershell`, and an
     unlisted class; allows `typecheck`.
   - **plain language:** every `PolicyDecision.reason` produced by the refusals
     above contains no word from `PLAIN_LANGUAGE_DENYLIST` (case-insensitive,
     whole-word) and is a single sentence ending in a full stop. This test is the
     seed of the per-phase gates later phases extend.
8. Write ADR-H97, ADR-H98, ADR-H99 in `docs/harness/decisions.md` (append; the
   series currently ends at ADR-H96, not H92 — the 2026-09-30 closeout landed
   H93–H96). Each follows the existing **Decision / Why / Consequences** shape
   used by every other ADR-H in that file.
9. Append the dated `docs/CHANGELOG.md` entry. Update `docs/NAVIGATION.md` with
   one row pointing at `code/policy.py`.

## 8. Deliverables

| File | Change |
|---|---|
| `python/harness/code/__init__.py` | new |
| `python/harness/code/policy.py` | new — policy authority |
| `python/harness/skills/manifest.py` | permission nouns; `FORBIDDEN_PERMISSIONS` narrowed; `CODE_PERMISSIONS` added |
| `python/harness/skills/permissions.py` | `Actor` gains `workspace_id`/`autonomy`; `granted()` consults `code.policy` |
| `python/tests/test_code_policy.py` | new — the tests in §7.7 |
| `docs/harness/decisions.md` | ADR-H97, ADR-H98, ADR-H99 |
| `docs/harness/roadmap/progress/phase-00-progress.md` | new — raw gate output |
| `docs/CHANGELOG.md`, `docs/NAVIGATION.md` | per the repo obligation |

## 9. Acceptance gates

Run each from `Black-Eclipse-site/` and paste the **raw output** into the progress
log. A gate not run is a gate not passed.

```bash
# G1 — nothing regressed
npm run check:all

# G2 — the new policy tests
./scripts/vendor/python/python.exe -m pytest python/tests/test_code_policy.py -q

# G3 — the whole python suite (uses the vendored interpreter)
npm run test

# G4 — the default actor is still denied, proven not asserted
./scripts/vendor/python/python.exe -c "from harness.skills.permissions import DEFAULT_ACTOR, OPERATOR_ACTOR; \
g=DEFAULT_ACTOR.granted(); print('default code perms:', sorted(p for p in g if p.startswith(('code.','git.','command.','workspace.')))); \
o=OPERATOR_ACTOR.granted(); print('operator code perms:', sorted(p for p in o if p.startswith(('code.','git.','command.','workspace.'))))"
# expected: both print []

# G5 — the mechanism vocabulary exists as data, and no reason leaks it
./scripts/vendor/python/python.exe -c "from harness.code.policy import PLAIN_LANGUAGE_DENYLIST as d; print(len(d), 'denylist terms'); print([t for t in d if not t.islower()])"
# expected: a count, and no non-lowercase terms (the gate lowercases before matching)

# G6 — every reason string is plain (the test in §7.7 covers this)
./scripts/vendor/python/python.exe -m pytest python/tests/test_code_policy.py -k plain_language -v

# G7 — the vault is untouched
git status --short        # jdds.db must NOT appear; no *.db staged
```

**Pass criteria.** G1 all gates pass; G2/G3 green; G4 prints two empty lists; G5
lists the denylist terms; G6 green; G7 shows no `*.db` change. Record the observed
test counts — they are the baseline the rest of the roadmap compares against.

## 10. Definition of done

- Every gate in §9 run, raw output pasted, counts recorded.
- `code/policy.py` is the only place a code-policy decision is made (grep for
  `PROTECTED_PATHS` / `resolve_within` and confirm one definition).
- The default and operator actors are provably still incapable of code verbs.
- ADR-H97/98/99 written; `docs/CHANGELOG.md` entry appended; `NAVIGATION.md` updated.
- `status:` flipped to `Done` in this file's frontmatter and in the index.

## 11. Implementation prompt (copy this to OpenCode)

```text
Task: Phase 0 — Recon, policy decision and baseline freeze (Eclipse-as-a-Harness roadmap).

Read first, in full:
- docs/harness/roadmap/phase-00-policy-and-baseline.md  (this phase, verbatim)
- docs/harness/roadmap/README.md  (invariants §3, work already in flight §5)
- python/harness/skills/permissions.py
- python/harness/skills/manifest.py
- AGENTS.md

Goal: make the code capability a deliberate, TESTED policy decision. Ship NO tools.
Introduce the single policy authority plus a workspace-bound actor class, and prove
the default actor is still denied every code verb.

In scope:
1. Baseline the release gate and paste the RAW output into
   docs/harness/roadmap/progress/phase-00-progress.md (create the folder).
2. New python/harness/code/__init__.py + python/harness/code/policy.py exactly as
   specified in §6.3 (AUTONOMY_PROFILES, PROTECTED_PATHS, IGNORED_DIRS,
   IGNORED_GLOBS, COMMAND_CLASSES, NETWORK_DEFAULT, SECRET_ENV_ALLOWLIST,
   PLAIN_LANGUAGE_DENYLIST, WorkspaceBinding, PolicyDecision, is_protected,
   is_ignored, resolve_within, decide_write, decide_command, code_grants).
3. python/harness/skills/manifest.py: add the code permission nouns; narrow
   FORBIDDEN_PERMISSIONS to trade/broker/production only; add CODE_PERMISSIONS.
   READ THE FILE FIRST — record its real contents in the progress log, do not
   assume.
4. python/harness/skills/permissions.py: Actor gains workspace_id + autonomy;
   granted() unions code_grants(autonomy) ONLY when both are set; unknown autonomy
   grants nothing (fail-closed). DEFAULT_ACTOR and OPERATOR_ACTOR keep exactly
   today's behaviour.
5. New python/tests/test_code_policy.py covering every case listed in §7.7,
   including the path-escape cases (traversal, absolute-outside, symlink escape)
   and the command refusals (rm -rf, curl, powershell, unlisted class).
6. docs/harness/decisions.md: append ADR-H97, ADR-H98, ADR-H99 (the series
   currently ends at ADR-H96 — H93–H96 landed in the 2026-09-30 closeout) in the
   existing Decision / Why / Consequences shape.
7. docs/CHANGELOG.md dated entry + docs/NAVIGATION.md row for code/policy.py.

Non-goals (do NOT do these):
- No filesystem, shell, patch or exec tool. Not even a stub or a placeholder.
- No route, no front door, no UI, no agent preset.
- No change to finance tools, prompts, retrieval, research, or MCP.
- No new dependency.
- Never weaken trade.execute / broker.modify / production.modify.
- Never commit, push, or open a PR. Do not commit jdds.db.

Constraints:
- One runtime: no second agent loop, tool registry or model adapter.
- Policy in code only; prose is never a security boundary.
- Keep files under their size ratchets — new logic goes in new modules.
- resolve_within must compare REAL paths and refuse symlink escapes; the raw
  string must never be trusted.

Acceptance gates — run each from Black-Eclipse-site/ and paste the RAW output:
  npm run check:all
  ./scripts/vendor/python/python.exe -m pytest python/tests/test_code_policy.py -q
  npm run test
  ./scripts/vendor/python/python.exe -c "from harness.skills.permissions import DEFAULT_ACTOR, OPERATOR_ACTOR; print(sorted(p for p in DEFAULT_ACTOR.granted() if p.startswith(('code.','git.','command.','workspace.')))); print(sorted(p for p in OPERATOR_ACTOR.granted() if p.startswith(('code.','git.','command.','workspace.'))))"
     -> both must print []
  git status --short      -> jdds.db must NOT appear

Finish by stating: "docs updated: <files>" or "no doc change — <reason>".
```

---

**Next:** [Phase 1 — Repository navigator](./phase-01-repository-navigator.md)
