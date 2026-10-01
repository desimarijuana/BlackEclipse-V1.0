"""The ONE authority for the code capability's policy.

Nothing here executes anything. This module answers, deterministically and
without side effects: may this run read/write/execute this thing, in this
workspace, under this autonomy profile? Every later phase calls it; none of
them re-implement it.

The decisions are DATA plus small pure functions:

  * ``PROTECTED_PATHS``   — never touchable, even by an operator.
  * ``IGNORED_DIRS`` / ``IGNORED_GLOBS`` — generated or bulky paths a write
    never targets.
  * ``COMMAND_CLASSES``   — the closed command vocabulary (Phase 3 owns argv).
  * ``AUTONOMY_PROFILES`` — what each profile may do (the actor consults this).
  * ``PLAIN_LANGUAGE_DENYLIST`` — mechanism words that must never reach a
    user-facing string; the later phases' plain-language gates read it here.

Path safety is enforced by ``resolve_within``: it compares REAL paths and
refuses an escape (traversal, an absolute path outside the root, or a symlink
that leaves the root). The raw string is never trusted.
"""

from __future__ import annotations

import fnmatch
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, FrozenSet, Optional, Sequence

# ── Autonomy profiles ───────────────────────────────────────────────────────

AUTONOMY_PROFILES: tuple[str, ...] = ("plan_only", "edit_verify", "approve_external")

# The per-profile grant table. Unknown autonomy grants nothing (fail-closed),
# exactly like the MCP trust tier.
_PROFILE_GRANTS: dict[str, FrozenSet[str]] = {
    "plan_only": frozenset({"code.read", "git.read"}),
    "edit_verify": frozenset(
        {"code.read", "code.write", "git.read", "code.execute", "command.execute"}
    ),
    "approve_external": frozenset(
        {
            "code.read",
            "code.write",
            "git.read",
            "code.execute",
            "command.execute",
            "git.write",
            "workspace.admin",
        }
    ),
}

# ── Protected paths — absolute, even inside a workspace, even for an operator ─

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

# ── Command vocabulary ──────────────────────────────────────────────────────
#
# The command classes Phase 3 implements. Declared here because the POLICY owns
# the vocabulary; commands.py owns the argv templates. Every class maps to the
# set of programs it may invoke; a program outside its class's set is refused.
COMMAND_CLASSES: tuple[str, ...] = (
    "typecheck", "lint", "unit_test", "python_test",
    "build", "format_check", "git_read", "dependency_install",
)

_COMMAND_PROGRAMS: dict[str, frozenset[str]] = {
    "typecheck": frozenset({"npm", "npx", "pnpm", "yarn", "bun", "node", "tsc"}),
    "lint": frozenset({"npm", "npx", "pnpm", "yarn", "eslint", "ruff"}),
    "unit_test": frozenset({"npm", "npx", "pnpm", "yarn", "vitest", "jest", "pytest"}),
    "python_test": frozenset({"python", "python3", "pytest", "uv"}),
    "build": frozenset({"npm", "npx", "pnpm", "yarn", "node", "next"}),
    "format_check": frozenset({"npx", "prettier", "ruff"}),
    "git_read": frozenset({"git"}),
    "dependency_install": frozenset({"npm", "npx", "pnpm", "yarn", "pip", "pip3", "uv"}),
}

# Programs that are never allowed, whatever the class. Belt and braces beside
# the per-class allowlist: a shell, a downloader, or a destructive tool.
DENIED_PROGRAMS: frozenset[str] = frozenset(
    {"rm", "rmdir", "del", "erase", "format", "mkfs", "shutdown", "curl",
     "wget", "invoke-webrequest", "powershell", "pwsh", "cmd", "sh", "bash",
     "zsh", "reg", "diskpart"}
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


# ── Contracts ───────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class WorkspaceBinding:
    id: str
    root: Path              # absolute; must be inside the allowed workspace root
    base_revision: str      # a git rev or a snapshot digest
    strategy: str           # "worktree" | "snapshot"


@dataclass(frozen=True)
class PolicyDecision:
    allowed: bool
    code: str          # "OK" | "PROTECTED_PATH" | "OUTSIDE_WORKSPACE" | "PROFILE_DENIED"
                       # | "SANDBOX_UNAVAILABLE" | "COMMAND_NOT_ALLOWLISTED" | "UNKNOWN_AUTONOMY"
    reason: str        # ONE PLAIN SENTENCE safe to show a human — no secrets, no paths
                       # outside the workspace, no mechanism term from the denylist above


class PolicyDenial(Exception):
    """Raised by ``resolve_within`` — carries a machine code and a plain reason.

    ``code`` is the stable, structured refusal code (`PATH_TRAVERSAL`,
    `PATH_OUTSIDE_WORKSPACE`, `SYMLINK_ESCAPE`, `PROTECTED_PATH`, `IGNORED_PATH`,
    `NOT_FOUND`). ``reason`` is the operator/human-facing plain sentence.
    """

    def __init__(self, code: str, reason: str) -> None:
        super().__init__(reason)
        self.code = code
        self.reason = reason


# Plain, single-sentence reasons. Safe to show a human: no secret, no outside
# path, no mechanism term. This is the only place a refusal sentence is written.
_REASON_PROTECTED = "That file is part of Eclipse's own data and can't be changed by a task."
_REASON_OUTSIDE = "That location is outside the task's own folder, so Eclipse can't use it there."
_REASON_TRAVERSAL = "That location points above the task's own folder, so Eclipse can't use it there."
_REASON_IGNORED = "That file is generated automatically, so Eclipse leaves it out."
_REASON_NOT_FOUND = "That file isn't there, so there's nothing for Eclipse to read."
_REASON_NO_BINDING = "This kind of work isn't available on this computer right now."
_REASON_PROFILE = "This task isn't set up to make that kind of change."
_REASON_UNKNOWN = "This task's permissions aren't recognized, so Eclipse won't continue."
_REASON_COMMAND = "That command isn't one Eclipse is allowed to run."
_REASON_ALLOWED = "This change is allowed inside the task's own folder."
_REASON_COMMAND_OK = "That command is allowed for this task."


# ── Path helpers ────────────────────────────────────────────────────────────


def _normalize(rel_path: str) -> str:
    """A posix-style relative path with no leading `./`, for pattern matching."""
    text = str(rel_path).replace("\\", "/").strip()
    while text.startswith("./"):
        text = text[2:]
    return text


def _matches(rel_path: str, pattern: str) -> bool:
    """Case-insensitive glob match over a normalized relative path.

    ``fnmatch`` treats ``*`` as crossing ``/`` so a nested ``**`` pattern also
    matches its descendants; the explicit ``/**`` forms and a bare directory
    pattern are both handled here.
    """
    rel = _normalize(rel_path).casefold()
    pat = pattern.replace("\\", "/").casefold()
    if fnmatch.fnmatchcase(rel, pat):
        return True
    # A directory pattern also covers everything beneath it.
    if not pat.endswith("/**") and fnmatch.fnmatchcase(rel, pat + "/**"):
        return True
    return False


def is_protected(rel_path: str) -> bool:
    """Whether a workspace-relative path is protected (never writable)."""
    return any(_matches(rel_path, pattern) for pattern in PROTECTED_PATHS)


def is_ignored(rel_path: str) -> bool:
    """Whether a workspace-relative path is generated/bulky and never written."""
    rel = _normalize(rel_path)
    parts = rel.split("/")
    for directory in IGNORED_DIRS:
        if directory in parts:
            return True
        if _matches(rel, directory + "/**"):
            return True
    return any(_matches(rel, glob) for glob in IGNORED_GLOBS)


def _is_within(root_real: Path, candidate: Path) -> bool:
    try:
        candidate.relative_to(root_real)
        return True
    except ValueError:
        return False


def _is_junction(path: Path) -> bool:
    """Whether ``path`` is a Windows junction/directory reparse point.

    A junction is NOT reported by ``Path.is_symlink()`` on Windows, so a
    junction that points outside the root would otherwise escape the symlink
    check. ``os.path.isjunction`` exists on 3.12; treat its absence as False.
    """
    checker = getattr(os.path, "isjunction", None)
    if checker is None:
        return False
    try:
        return bool(checker(path))
    except OSError:
        return False


def _symlink_escape(root_real: Path, absolute: Path) -> bool:
    """Whether a component of ``absolute`` is a link whose target leaves ``root``.

    ``absolute`` is the lexical (unresolved) candidate path. Only components
    lexically under the root are examined; a path that is already outside the
    root is reported as ``PATH_OUTSIDE_WORKSPACE`` instead, so the two escape
    vectors keep DISTINCT codes.
    """
    try:
        relative = absolute.relative_to(root_real)
    except ValueError:
        return False
    current = root_real
    for part in relative.parts:
        current = current / part
        try:
            is_link = current.is_symlink() or _is_junction(current)
        except OSError:
            is_link = False
        if is_link:
            target = Path(os.path.realpath(current))
            if not _is_within(root_real, target):
                return True
    return False


def resolve_within(root: Path, candidate: str) -> Path:
    """Resolve ``candidate`` inside ``root`` or raise ``PolicyDenial``.

    The comparison is always on REAL, resolved paths — never the raw string.
    Distinct codes are produced per escape vector so a caller (and a test) can
    tell them apart:

      * ``PATH_TRAVERSAL``         — a ``..`` component in the request;
      * ``SYMLINK_ESCAPE``         — a link/junction component leaving the root;
      * ``PATH_OUTSIDE_WORKSPACE`` — the resolved path is not the root or under
        it (covers an absolute path outside the root);
      * ``PROTECTED_PATH``         — ``is_protected(rel)``;
      * ``IGNORED_PATH``           — ``is_ignored(rel)``.
    """
    root_real = Path(os.path.realpath(root))
    raw = Path(str(candidate).replace("\\", os.sep))
    # A `..` component is refused by the raw shape, before any resolution.
    if ".." in str(candidate).replace("\\", "/").split("/"):
        raise PolicyDenial("PATH_TRAVERSAL", _REASON_TRAVERSAL)
    absolute = raw if raw.is_absolute() else root_real / raw
    if _symlink_escape(root_real, absolute):
        raise PolicyDenial("SYMLINK_ESCAPE", _REASON_OUTSIDE)
    resolved = Path(os.path.realpath(absolute))
    if not _is_within(root_real, resolved):
        raise PolicyDenial("PATH_OUTSIDE_WORKSPACE", _REASON_OUTSIDE)
    rel = resolved.relative_to(root_real).as_posix() if resolved != root_real else "."
    if is_protected(rel):
        raise PolicyDenial("PROTECTED_PATH", _REASON_PROTECTED)
    if is_ignored(rel):
        raise PolicyDenial("IGNORED_PATH", _REASON_IGNORED)
    return resolved


# ── Grants ──────────────────────────────────────────────────────────────────


def code_grants(autonomy: str) -> frozenset[str]:
    """The code permissions a profile may hold. Unknown profile → nothing."""
    return _PROFILE_GRANTS.get(autonomy, frozenset())


# ── Tool-allowlist narrowing (Phase 5) ──────────────────────────────────────
#
# The autonomy profile is enforced by the TOOL ALLOWLIST, not by a prompt: a
# disallowed tool is REMOVED before the model sees its schema, so it cannot call
# it — not "shouldn't", cannot. This is the ONE place a write/external tool is
# removed; `graph.effective_allowlist` calls it before building the model tools.

# Effectful code-write / execute tools (the REAL names Phases 1–9 registered).
WRITE_TOOLS: tuple[str, ...] = (
    "workspace_patch_apply", "workspace_revert",   # code.write
    "command_run",                                  # code.execute / command.execute
    "scaffold_kit",                                 # code.write (Phase 9)
)

# External actions — commit / push / open a PR / deploy. approve_external only,
# and each is STILL an effectful external_action requiring a single-use approval.
EXTERNAL_ACTION_TOOLS: tuple[str, ...] = (
    "code_commit", "code_push", "code_open_pr", "code_deploy",
)

# Tools that are always available regardless of profile (read-only).
READ_ONLY_TOOLS: tuple[str, ...] = (
    "workspace_status", "workspace_list", "workspace_search",
    "workspace_read", "workspace_docs", "workspace_diff",
)


def allowed_tools(autonomy: str, declared: tuple[str, ...]) -> tuple[str, ...]:
    """Narrow a declared allowlist to what the autonomy profile permits.

    plan_only        → write + external tools REMOVED (the model cannot call them)
    edit_verify      → write tools present; external tools REMOVED
    approve_external → everything, but external tools are still effectful and
                       require a per-action single-use approval at execution
    unknown          → the read-only subset (fail-closed, same as code_grants)
    """
    if autonomy == "plan_only":
        banned = set(WRITE_TOOLS) | set(EXTERNAL_ACTION_TOOLS)
    elif autonomy == "edit_verify":
        banned = set(EXTERNAL_ACTION_TOOLS)
    elif autonomy == "approve_external":
        banned = set()
    else:
        banned = set(WRITE_TOOLS) | set(EXTERNAL_ACTION_TOOLS)
    return tuple(t for t in declared if t not in banned)


# ── Decisions ───────────────────────────────────────────────────────────────


def _gate(actor: Any, binding: Optional[WorkspaceBinding], verb: str) -> Optional[PolicyDecision]:
    """The shared binding/profile gate. ``None`` means the verb passed the gate."""
    if binding is None:
        return PolicyDecision(False, "SANDBOX_UNAVAILABLE", _REASON_NO_BINDING)
    workspace_id = getattr(actor, "workspace_id", None)
    autonomy = getattr(actor, "autonomy", None)
    if not workspace_id or not autonomy or workspace_id != binding.id:
        return PolicyDecision(False, "PROFILE_DENIED", _REASON_PROFILE)
    if autonomy not in AUTONOMY_PROFILES:
        return PolicyDecision(False, "UNKNOWN_AUTONOMY", _REASON_UNKNOWN)
    if verb not in code_grants(autonomy):
        return PolicyDecision(False, "PROFILE_DENIED", _REASON_PROFILE)
    return None


def decide_write(actor: Any, binding: Optional[WorkspaceBinding], rel_path: str) -> PolicyDecision:
    """May ``actor`` write ``rel_path`` inside ``binding``?"""
    gate = _gate(actor, binding, "code.write")
    if gate is not None:
        return gate
    assert binding is not None  # narrowed by the gate
    # Protected is stricter than ignored: a protected path reports PROTECTED_PATH
    # even when it also matches an ignored pattern (e.g. `policy.py` under a
    # vendor-like dir, or `jdds.db` matching `*.db`).
    if is_protected(rel_path):
        return PolicyDecision(False, "PROTECTED_PATH", _REASON_PROTECTED)
    if is_ignored(rel_path):
        return PolicyDecision(False, "PROFILE_DENIED", _REASON_IGNORED)
    try:
        resolve_within(binding.root, rel_path)
    except PolicyDenial as denial:
        return PolicyDecision(False, denial.code, denial.reason)
    return PolicyDecision(True, "OK", _REASON_ALLOWED)


def _program_of(argv: Sequence[str]) -> str:
    first = argv[0] if argv else ""
    name = os.path.basename(str(first).replace("\\", "/")).casefold()
    for suffix in (".exe", ".cmd", ".bat", ".com", ".py"):
        if name.endswith(suffix):
            name = name[: -len(suffix)]
    return name


def decide_command(
    actor: Any,
    binding: Optional[WorkspaceBinding],
    command_class: str,
    argv: Any,
) -> PolicyDecision:
    """May ``actor`` run ``argv`` as ``command_class`` inside ``binding``?"""
    verb = "git.read" if command_class == "git_read" else "command.execute"
    gate = _gate(actor, binding, verb)
    if gate is not None:
        return gate
    if command_class not in COMMAND_CLASSES:
        return PolicyDecision(False, "COMMAND_NOT_ALLOWLISTED", _REASON_COMMAND)
    tokens = argv.split() if isinstance(argv, str) else list(argv or [])
    if not tokens:
        return PolicyDecision(False, "COMMAND_NOT_ALLOWLISTED", _REASON_COMMAND)
    program = _program_of(tokens)
    if not program or program in DENIED_PROGRAMS:
        return PolicyDecision(False, "COMMAND_NOT_ALLOWLISTED", _REASON_COMMAND)
    if program not in _COMMAND_PROGRAMS[command_class]:
        return PolicyDecision(False, "COMMAND_NOT_ALLOWLISTED", _REASON_COMMAND)
    return PolicyDecision(True, "OK", _REASON_COMMAND_OK)


__all__ = [
    "AUTONOMY_PROFILES",
    "COMMAND_CLASSES",
    "DENIED_PROGRAMS",
    "EXTERNAL_ACTION_TOOLS",
    "IGNORED_DIRS",
    "IGNORED_GLOBS",
    "NETWORK_DEFAULT",
    "PLAIN_LANGUAGE_DENYLIST",
    "PROTECTED_PATHS",
    "READ_ONLY_TOOLS",
    "SECRET_ENV_ALLOWLIST",
    "WRITE_TOOLS",
    "PolicyDecision",
    "PolicyDenial",
    "WorkspaceBinding",
    "allowed_tools",
    "code_grants",
    "decide_command",
    "decide_write",
    "is_ignored",
    "is_protected",
    "resolve_within",
]
