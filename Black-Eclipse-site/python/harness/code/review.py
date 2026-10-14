"""Change-quality rules — the repo's own rules, evaluated over a diff (Phase 19).

The rules are DATA (`RULES`), each naming the real repository rule it encodes.
`review_change` evaluates them over a `DiffView` and returns findings with
file:line plus the plain `summary` a user reads. A rule that cannot be evaluated
(a binary file, a bounded scan that ran out) lands in `unevaluated` — never
silently reported as clean.

One rule (`protected-path`) is ALSO enforced in code (`code/policy.py`,
`patch.apply` refuses it): this module only REPORTS that fact, and the test
asserts the two agree. One mechanism plus a report — never two mechanisms.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Optional

from . import policy

Severity = Literal["blocking", "advisory"]


@dataclass(frozen=True)
class ReviewRule:
    id: str
    summary: str                 # plain words — this is what the user reads
    severity: Severity
    source: str                  # the real repo rule this encodes


RULES: tuple[ReviewRule, ...] = (
    ReviewRule("new-module-reachable", "A new module nothing uses yet",
               "advisory", "AGENTS.md — reuse before rebuild"),
    ReviewRule("size-ratchet", "A changed file is past its size limit",
               "advisory", "src/lib/size-budget.test.ts, python/tests/test_size_budget.py"),
    ReviewRule("string-is-key", "A user-facing sentence isn't a translatable key",
               "advisory", "src/lib/i18n/plain-language.test.ts"),
    ReviewRule("protected-path", "The change touches a file it must not",
               "blocking", "python/harness/code/policy.py — PROTECTED_PATHS"),
    ReviewRule("doc-obligation", "A non-test change has no change-log entry",
               "advisory", "AGENTS.md — documentation obligation"),
    ReviewRule("test-touched", "The change changed a test's expectation",
               "advisory", "AGENTS.md — never weaken a test to make it pass"),
)

MAX_SCAN_FILES = 6_000
_SCAN_SKIP_DIRS = {
    ".git", "node_modules", ".next", ".next-dev", "__pycache__", "generated",
    "dist", "build", ".black-eclipse", "_backups", "vendor", ".venv",
}
_NEW_MODULE_EXTENSIONS = (".py", ".ts", ".tsx")
_TEST_MARKERS = ("/tests/", "\\tests\\", ".test.", ".spec.", "/test_")
_JSX_TEXT_RE = re.compile(r">\s*[A-Z][A-Za-z0-9 ,.'’!?&:;-]{14,}\s*<")
_HARD_CEILING_LINES = 1200


@dataclass(frozen=True)
class DiffFile:
    path: str                              # repo-relative, forward slashes
    status: Literal["added", "modified", "deleted"]
    added_lines: tuple[str, ...] = ()
    unreadable: bool = False               # binary / undecodable


@dataclass
class DiffView:
    files: list[DiffFile] = field(default_factory=list)
    strategy: str = ""


@dataclass(frozen=True)
class Finding:
    rule: str
    summary: str
    severity: Severity
    path: str
    line: Optional[int] = None
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule": self.rule, "summary": self.summary, "severity": self.severity,
            "path": self.path, "line": self.line, "detail": self.detail,
        }


@dataclass
class ReviewResult:
    findings: list[Finding] = field(default_factory=list)
    unevaluated: list[str] = field(default_factory=list)
    files_reviewed: int = 0

    @property
    def blocking(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == "blocking"]

    def to_dict(self) -> dict[str, Any]:
        return {
            "findings": [f.to_dict() for f in self.findings],
            "unevaluated": list(self.unevaluated),
            "filesReviewed": self.files_reviewed,
        }


# ── building the view from a worktree diff ───────────────────────────────────


def diff_view_from_worktree(result: dict[str, Any], *, root: Path) -> DiffView:
    """Build a `DiffView` from `code/worktree.py::diff`'s result dict."""
    status_by_path: dict[str, str] = {}
    for path in result.get("added") or []:
        status_by_path[_norm(path)] = "added"
    for path in result.get("modified") or []:
        status_by_path[_norm(path)] = "modified"
    for path in result.get("deleted") or []:
        status_by_path[_norm(path)] = "deleted"

    added_lines: dict[str, list[str]] = {}
    current: Optional[str] = None
    for line in str(result.get("unified") or "").splitlines():
        if line.startswith("diff --git "):
            current = _path_from_diff_header(line)
            continue
        if current and line.startswith("+") and not line.startswith("+++"):
            added_lines.setdefault(current, []).append(line[1:])
    # A `+++ b/<path>` header also names a file the hunk belongs to (rename-safe).
    for path, lines in added_lines.items():
        status_by_path.setdefault(path, "modified")

    files: list[DiffFile] = []
    for path, status in sorted(status_by_path.items()):
        unreadable = False
        if status != "deleted":
            full = Path(root) / path
            if full.exists():
                try:
                    full.read_text(encoding="utf-8")
                except (UnicodeDecodeError, OSError):
                    unreadable = True
        files.append(DiffFile(
            path=path, status=status,  # type: ignore[arg-type]
            added_lines=tuple(added_lines.get(path, ())),
            unreadable=unreadable,
        ))
    return DiffView(files=files, strategy=str(result.get("strategy") or ""))


def _path_from_diff_header(line: str) -> str:
    parts = line.split(" ")
    # `diff --git a/<path> b/<path>` — prefer the b-side, fall back to a-side.
    candidate = parts[-1] if len(parts) >= 4 else ""
    if candidate.startswith("b/"):
        return _norm(candidate[2:])
    if len(parts) >= 3 and parts[-2].startswith("a/"):
        return _norm(parts[-2][2:])
    return _norm(candidate)


def _norm(path: str) -> str:
    return str(path).replace("\\", "/").strip()


def _is_test_path(path: str) -> bool:
    lowered = f"/{path.lower()}"
    return any(marker in lowered for marker in ("/tests/", ".test.", ".spec."))


# ── the rules ────────────────────────────────────────────────────────────────


def review_change(diff: DiffView, *, repo_root: Path) -> ReviewResult:
    """Evaluate every rule over the diff. Findings carry file:line + plain words."""
    result = ReviewResult(files_reviewed=len(diff.files))
    if not diff.files:
        result.unevaluated.append("there was no change to review")
        return result

    ratchets = _ratchet_budgets(repo_root)
    doc_touched = any("changelog" in f.path.lower() for f in diff.files)
    non_test_change = any(not _is_test_path(f.path) for f in diff.files)

    for file in diff.files:
        if file.unreadable:
            result.unevaluated.append(f"{file.path}: it is not readable text")
            continue
        if not Path(repo_root, file.path).exists() and file.status != "deleted":
            result.unevaluated.append(f"{file.path}: it is not present in the project")

        # protected-path — BLOCKING (the same rule `patch.apply` enforces).
        try:
            if policy.is_protected(file.path):
                result.findings.append(Finding(
                    rule="protected-path", severity="blocking", path=file.path,
                    summary=f"This change touches a protected file: {file.path}.",
                    detail="It must be made deliberately, outside a task's own copy.",
                ))
        except Exception:  # noqa: BLE001 - an unevaluable rule is never "clean"
            result.unevaluated.append(f"{file.path}: the protected-file rule could not be evaluated")

        if file.status == "deleted":
            continue

        full = Path(repo_root) / file.path

        # size-ratchet — over the hard ceiling and over its pin (or unpinned).
        if file.path.endswith(_NEW_MODULE_EXTENSIONS):
            try:
                lines = len(full.read_text(encoding="utf-8").splitlines())
            except (OSError, UnicodeDecodeError):
                result.unevaluated.append(f"{file.path}: its size could not be measured")
                lines = 0
            if lines > _HARD_CEILING_LINES:
                budget = ratchets.get(file.path)
                if budget is None:
                    result.findings.append(Finding(
                        rule="size-ratchet", severity="advisory", path=file.path,
                        summary=f"This file is past the size limit ({lines:,} lines).",
                        detail="Split it, or pin it in the size ratchet with a reason.",
                    ))
                elif lines > budget:
                    result.findings.append(Finding(
                        rule="size-ratchet", severity="advisory", path=file.path,
                        summary=f"This file grew past its pinned size ({lines:,} > {budget:,} lines).",
                        detail="A ratcheted file may only shrink from the pin.",
                    ))

        # new-module-reachable — a NEW module the project never mentions.
        if file.status == "added" and file.path.endswith(_NEW_MODULE_EXTENSIONS):
            stem = Path(file.path).stem
            if stem not in ("index", "__init__", "conftest", "setup"):
                found, bounded = _mentioned_in_repo(stem, repo_root, exclude=file.path)
                if not found and bounded:
                    result.unevaluated.append(
                        f"{file.path}: the use scan was bounded before it checked every file"
                    )
                elif not found:
                    result.findings.append(Finding(
                        rule="new-module-reachable", severity="advisory", path=file.path,
                        summary=f"This adds {file.path}, but nothing uses it yet.",
                        detail="Wire it in, or remove it.",
                    ))

        # string-is-key — user-facing JSX text that is not a translatable key.
        if file.path.endswith(".tsx"):
            for offset, line in enumerate(file.added_lines, start=1):
                if "{t(" in line or "aria-" in line:
                    continue
                if _JSX_TEXT_RE.search(line):
                    result.findings.append(Finding(
                        rule="string-is-key", severity="advisory", path=file.path,
                        line=offset,
                        summary="A user-facing sentence isn't a translatable key.",
                        detail="Put it in the i18n dictionary and reference the key.",
                    ))

    # doc-obligation — a non-test change with no change-log entry.
    if non_test_change and not doc_touched:
        result.findings.append(Finding(
            rule="doc-obligation", severity="advisory", path="",
            summary="This change has no change-log entry.",
            detail="Append one under today's date (AGENTS.md), or say why none is needed.",
        ))

    # test-touched — expectations changed; never weakened to pass.
    for file in diff.files:
        if file.status != "deleted" and _is_test_path(file.path):
            result.findings.append(Finding(
                rule="test-touched", severity="advisory", path=file.path,
                summary="This change changed a test.",
                detail="Tests must not be weakened to make a change pass.",
            ))

    return result


def _mentioned_in_repo(stem: str, repo_root: Path, *, exclude: str) -> tuple[bool, bool]:
    """Whether `stem` appears anywhere in the project. Returns (found, bounded).

    `bounded` is True when the scan stopped at the file cap without finding it —
    the caller reports that as unevaluated rather than as a finding.
    """
    scanned = 0
    for dirpath, dirnames, filenames in _walk(repo_root):
        dirnames[:] = [d for d in dirnames if d not in _SCAN_SKIP_DIRS and not d.startswith(".")]
        for name in filenames:
            if not name.endswith((".py", ".ts", ".tsx", ".js", ".jsx", ".md", ".json")):
                continue
            rel = _norm(str(Path(dirpath, name).relative_to(repo_root)))
            if rel == exclude:
                continue
            scanned += 1
            if scanned > MAX_SCAN_FILES:
                return False, True
            try:
                text = Path(dirpath, name).read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            if stem in text:
                return True, False
    return False, False


def _walk(root: Path):
    import os  # noqa: PLC0415

    for entry in os.walk(root):
        yield entry


def _ratchet_budgets(repo_root: Path) -> dict[str, int]:
    """The pinned sizes, read from the two ratchet files. Empty when unreadable."""
    budgets: dict[str, int] = {}
    pair_re = re.compile(r'"([^"]+\.(?:py|tsx|ts))"\s*:\s*(\d+)')
    ts_file = repo_root / "src" / "lib" / "size-budget.test.ts"
    try:
        for match in pair_re.finditer(ts_file.read_text(encoding="utf-8")):
            budgets[_norm(match.group(1))] = int(match.group(2))
    except OSError:
        pass
    py_file = repo_root / "python" / "tests" / "test_size_budget.py"
    try:
        for match in pair_re.finditer(py_file.read_text(encoding="utf-8")):
            budgets[f"python/harness/{_norm(match.group(1))}"] = int(match.group(2))
    except OSError:
        pass
    return budgets


__all__ = [
    "DiffFile",
    "DiffView",
    "Finding",
    "RULES",
    "ReviewResult",
    "ReviewRule",
    "diff_view_from_worktree",
    "review_change",
]
