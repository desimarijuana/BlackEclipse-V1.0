"""The Git safety engine.

Before a mutating git operation, and especially before `add`/`commit`/`push`,
this module answers three deterministic questions:

  1. **Risk** — what class is this operation? (`safe` … `critical`), and does it
     require an explicit approval? The classification is DATA on each `GitOp`
     (`catalog`), surfaced here as a machine-readable verdict.
  2. **Secrets** — does a change introduce something that looks like a
     credential? It reuses the ONE secret-pattern set (`session_index`) rather
     than inventing a second one, and optionally runs `gitleaks`/`trufflehog`
     when installed.
  3. **Large files** — does a change stage something very large, a database
     dump, or a build artifact that should not be committed?

It also enforces **protected branches** and repository **policy** from
`.black-eclipse/git.json`, and treats a cloned repository as untrusted: hooks and
repository config are inspected, never executed.

Nothing here runs a mutating git command. It only reads, so a scan can never
change the repository.
"""

from __future__ import annotations

import json
import os
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Optional

from ..session_index import secret_pattern_name
from . import errors
from .repository import Repository

# ── Risk ────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class RiskAssessment:
    operation: str
    risk: str
    requires_confirmation: bool
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "operation": self.operation,
            "risk": self.risk,
            "requires_confirmation": self.requires_confirmation,
            "reason": self.reason,
        }


_RISK_REASONS: dict[str, str] = {
    "safe": "This only reads the project and changes nothing.",
    "caution": "This changes the project's saved state.",
    "dangerous": "This can move or rewrite saved history.",
    "destructive": "This can discard unsaved work or delete saved data.",
    "critical": "This can destroy the project's history on the server and cannot be undone.",
}


def assess_risk(op_name: str, *, force_push: bool = False, hard_reset: bool = False,
                global_config: bool = False) -> RiskAssessment:
    """Classify an operation's risk from the closed catalog (plus overrides)."""
    from .catalog import CATALOG
    from .operations import requires_confirmation

    op = CATALOG.get(op_name)
    risk = op.risk if op is not None else "safe"
    # A force push is critical even though the generic `push` op is caution; the
    # caller passes `force_push=True` when the validated args request it.
    if force_push:
        risk = "critical"
    if hard_reset:
        risk = "destructive"
    # A GLOBAL config write changes the machine's git for every repository and can
    # inject a hook/ssh command: it is dangerous, whatever the local op's band.
    if global_config:
        risk = "dangerous"
    return RiskAssessment(
        operation=op_name,
        risk=risk,
        requires_confirmation=requires_confirmation(risk),
        reason=_RISK_REASONS.get(risk, _RISK_REASONS["safe"]),
    )


# ── Protected branches / repository policy ────────────────────────────────────────

POLICY_RELPATH = ".black-eclipse/git.json"

_DEFAULT_PROTECTED = ("main", "master", "production", "release")


@dataclass(frozen=True)
class RepositoryPolicy:
    default_branch: str = "main"
    pull_strategy: str = "merge"           # merge | rebase | ff-only
    conventional_commits: bool = False
    push_force_allowed: bool = False
    protected_branches: tuple[str, ...] = _DEFAULT_PROTECTED
    checks_before_commit: tuple[str, ...] = ()
    checks_before_push: tuple[str, ...] = ()
    large_file_mb: int = 10
    require_confirmation: tuple[str, ...] = ()


def load_policy(repo: Repository) -> RepositoryPolicy:
    """Read `.black-eclipse/git.json` if present; else the safe defaults."""
    path = repo.root / POLICY_RELPATH
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return RepositoryPolicy()
    if not isinstance(payload, dict):
        return RepositoryPolicy()

    commit_cfg = payload.get("commit") or {}
    push_cfg = payload.get("push") or {}
    checks = payload.get("checks") or {}
    protected = payload.get("protected_branches") or payload.get("protectedBranches")
    return RepositoryPolicy(
        default_branch=str(payload.get("default_branch") or payload.get("defaultBranch") or "main"),
        pull_strategy=str(payload.get("pull_strategy") or payload.get("pullStrategy") or "merge"),
        conventional_commits=bool(commit_cfg.get("conventional") or commit_cfg.get("conventionalCommits")),
        push_force_allowed=str(push_cfg.get("force", "forbidden")).casefold() in ("allowed", "true", "yes"),
        protected_branches=tuple(protected) if isinstance(protected, (list, tuple)) else _DEFAULT_PROTECTED,
        checks_before_commit=tuple(checks.get("before_commit") or checks.get("beforeCommit") or ()),
        checks_before_push=tuple(checks.get("before_push") or checks.get("beforePush") or ()),
        large_file_mb=int(payload.get("large_file_mb") or payload.get("largeFileMb") or 10),
        require_confirmation=tuple(payload.get("require_confirmation") or ()),
    )


def is_protected_branch(repo: Repository, branch: Optional[str], policy: Optional[RepositoryPolicy] = None) -> bool:
    if not branch:
        return False
    policy = policy or load_policy(repo)
    target = branch.split("/")[-1] if branch.startswith("origin/") else branch
    return any(target == p or branch == p for p in policy.protected_branches)


# ── Secret detection ─────────────────────────────────────────────────────────────

# A pragmatic, high-signal filename set. A match is a WARNING, never a block by
# itself — the caller decides; this module never stages or commits anything.
_SECRET_FILENAMES = (
    ".env", "credentials", "id_rsa", "id_ed25519", ".npmrc", ".pypirc",
    ".netrc", "secrets.json", "service-account.json",
)
_SECRET_EXTENSIONS = (".pem", ".key", ".p12", ".pfx", ".jks", ".keystore")


@dataclass
class SecretFinding:
    path: str
    kind: str                 # filename | pattern | scanner
    pattern: str = ""
    line: int = 0
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path, "kind": self.kind, "pattern": self.pattern,
            "line": self.line, "detail": self.detail,
        }


def _looks_like_secret_filename(path: str) -> Optional[str]:
    name = os.path.basename(path).casefold()
    if name in _SECRET_FILENAMES:
        return name
    for ext in _SECRET_EXTENSIONS:
        if name.endswith(ext):
            return ext
    return None


def scan_secrets(repo: Repository, paths: Iterable[str], *, max_file_bytes: int = 2_000_000) -> list[SecretFinding]:
    """Scan the given worktree-relative paths for credential-shaped content.

    Reads at most `max_file_bytes` per file, skips binary content, and returns
    findings (filename heuristics + the shared pattern set). Never raises.
    """
    findings: list[SecretFinding] = []
    root = repo.root.resolve()
    for rel in paths:
        rel_norm = str(rel).replace("\\", "/")
        target = (root / rel_norm).resolve()
        try:
            target.relative_to(root)
        except ValueError:
            continue
        name_hit = _looks_like_secret_filename(rel_norm)
        if name_hit:
            findings.append(SecretFinding(rel_norm, "filename", pattern=name_hit))
        if not target.is_file():
            continue
        try:
            if target.stat().st_size > max_file_bytes:
                continue
            raw = target.read_bytes()
        except OSError:
            continue
        if b"\x00" in raw[:4096]:
            continue  # binary; the large-file check owns this
        text = raw.decode("utf-8", "replace")
        for line_no, line in enumerate(text.splitlines(), start=1):
            pattern = secret_pattern_name(line)
            if pattern:
                findings.append(SecretFinding(rel_norm, "pattern", pattern=pattern, line=line_no))
    return findings


def external_scanners() -> list[str]:
    """Names of installed secret scanners (gitleaks/trufflehog). Discovery only."""
    found: list[str] = []
    for name in ("gitleaks", "trufflehog"):
        if shutil.which(name):
            found.append(name)
    return found


# ── Large-file detection ──────────────────────────────────────────────────────────

# Build output / bulky paths that should never be committed (a subset of the
# policy ignore set, expressed as path fragments).
_ARTIFACT_FRAGMENTS = (
    "/node_modules/", "/.next/", "/dist/", "/build/", "/target/", "/coverage/",
    "/__pycache__/", "/.venv/", "/venv/", "/.turbo/", "/.cache/",
)
_ARTIFACT_EXTENSIONS = (".log", ".tmp", ".bak", ".sqlite", ".db", ".dump", ".sql", ".zip", ".tar", ".gz")


@dataclass
class LargeFileFinding:
    path: str
    size_bytes: int
    kind: str                 # large | artifact | database
    suggestion: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path, "sizeBytes": self.size_bytes,
            "kind": self.kind, "suggestion": self.suggestion,
        }


def scan_large_files(repo: Repository, paths: Iterable[str], *, threshold_mb: int = 10) -> list[LargeFileFinding]:
    """Flag large files and known build/database artifacts among `paths`."""
    threshold = max(1, int(threshold_mb)) * 1024 * 1024
    root = repo.root.resolve()
    findings: list[LargeFileFinding] = []
    for rel in paths:
        rel_norm = str(rel).replace("\\", "/")
        target = (root / rel_norm).resolve()
        try:
            target.relative_to(root)
        except ValueError:
            continue
        lowered = ("/" + rel_norm.casefold() + "/")
        if any(frag in lowered for frag in _ARTIFACT_FRAGMENTS):
            findings.append(LargeFileFinding(
                rel_norm, _safe_size(target), "artifact",
                "This is generated output; keep it out of the saved version and add it to .gitignore.",
            ))
            continue
        if rel_norm.casefold().endswith(_ARTIFACT_EXTENSIONS):
            findings.append(LargeFileFinding(
                rel_norm, _safe_size(target), "database",
                "This looks like data or a dump; store it outside the repository or use large-file storage.",
            ))
            continue
        size = _safe_size(target)
        if size > threshold:
            findings.append(LargeFileFinding(
                rel_norm, size, "large",
                "This file is very large; keep it out or store it with large-file storage.",
            ))
    return findings


def _safe_size(path: Path) -> int:
    try:
        return int(path.stat().st_size)
    except OSError:
        return 0


# ── Untrusted-repository checks ─────────────────────────────────────────────────────

_ACTIVE_HOOKS = ("pre-commit", "commit-msg", "pre-push", "pre-rebase", "post-checkout", "post-merge")

# Local-config keys that can change which code Git executes. A configured value
# for any of these is reported (never executed) so the caller can warn.
_SENSITIVE_CONFIG_KEYS: frozenset[str] = frozenset({
    "core.hookspath", "core.sshcommand", "core.fsmonitor", "core.pager",
    "credential.helper", "include.path", "diff.external", "filter.lfs.process",
    "filter.lfs.clean", "filter.lfs.smudge", "core.askpass",
})


@dataclass
class UntrustedReport:
    hooks: tuple[str, ...] = ()
    local_config: tuple[str, ...] = ()
    has_lfs: bool = False
    submodules: bool = False
    symlinks: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "hooks": list(self.hooks),
            "localConfig": list(self.local_config),
            "hasLfs": self.has_lfs,
            "submodules": self.submodules,
            "symlinks": list(self.symlinks),
        }


def inspect_untrusted(repo: Repository, *, max_symlinks: int = 100) -> UntrustedReport:
    """Report repository-controlled executable/configuration surfaces.

    Never executes a hook, never sources `.gitconfig`. The report lets the caller
    warn before an operation that would run repository-supplied code.
    """
    hooks_dir = repo.git_dir / "hooks"
    hooks: list[str] = []
    if hooks_dir.is_dir():
        for name in _ACTIVE_HOOKS:
            candidate = hooks_dir / name
            # `name` is exact, so a `.sample` template never matches. A real hook
            # is any non-empty file here — it would run if git invoked it.
            if candidate.is_file():
                try:
                    if candidate.stat().st_size > 0:
                        hooks.append(name)
                except OSError:
                    continue
    local_config: list[str] = []
    local = repo.git_dir / "config"
    if local.is_file():
        section = ""
        try:
            for line in local.read_text(encoding="utf-8", errors="replace").splitlines():
                stripped = line.strip()
                if not stripped or stripped.startswith(("#", ";")):
                    continue
                if stripped.startswith("[") and stripped.endswith("]"):
                    section = stripped[1:-1].split()[0].casefold()
                    continue
                if "=" in stripped:
                    key = stripped.split("=", 1)[0].strip().casefold()
                    full = f"{section}.{key}" if section else key
                    # Surface non-default keys that can change execution.
                    if full in _SENSITIVE_CONFIG_KEYS:
                        local_config.append(full)
        except OSError:
            pass
    has_lfs = (repo.root / ".gitattributes").is_file() and _mentions_lfs(repo.root / ".gitattributes")
    submodules = (repo.root / ".gitmodules").is_file()
    symlinks = _find_symlinks(repo, max_symlinks)
    return UntrustedReport(
        hooks=tuple(hooks), local_config=tuple(local_config),
        has_lfs=has_lfs, submodules=submodules, symlinks=tuple(symlinks),
    )


def _mentions_lfs(path: Path) -> bool:
    try:
        return "filter=lfs" in path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False


def _find_symlinks(repo: Repository, limit: int) -> list[str]:
    out: list[str] = []
    for dirpath, dirnames, filenames in os.walk(repo.root, followlinks=False):
        dirnames[:] = [d for d in dirnames if d not in (".git", "node_modules", ".next")]
        for name in filenames:
            full = Path(dirpath) / name
            try:
                if full.is_symlink():
                    out.append(full.relative_to(repo.root).as_posix())
            except OSError:
                continue
            if len(out) >= limit:
                return out
    return out


# ── Conventional commit validation ─────────────────────────────────────────────────

_CONVENTIONAL_RE = re.compile(
    r"^(feat|fix|refactor|perf|docs|test|build|ci|chore|revert)(\([^)]+\))?!?: .+"
)


def is_conventional(message: str) -> bool:
    return bool(_CONVENTIONAL_RE.match((message or "").split("\n", 1)[0].strip()))


__all__ = [
    "LargeFileFinding",
    "POLICY_RELPATH",
    "RepositoryPolicy",
    "RiskAssessment",
    "SecretFinding",
    "UntrustedReport",
    "assess_risk",
    "external_scanners",
    "inspect_untrusted",
    "is_conventional",
    "is_protected_branch",
    "load_policy",
    "scan_large_files",
    "scan_secrets",
]
