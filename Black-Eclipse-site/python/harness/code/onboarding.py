"""What Eclipse found in a project, before the first build (Phase 24 / P5).

Opening a folder used to be implicit: the selected root was whatever the last
call happened to use, and the user learned the project's stack, run command and
checks only by watching a build. This module answers those questions in one
bounded read, so the surface can show them BEFORE anything runs.

Pure data. No writes, no model calls, no new store.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from .land import plan_land_checks
from .preview import plan_preview
from .workspace import git_probe_kind

#: Files that make a project's rules discoverable by `code/project_memory.py`.
RULE_FILES: tuple[str, ...] = ("AGENTS.md", "CLAUDE.md", ".eclipse/instructions.md")


def _stack(root: Path) -> list[str]:
    found: list[str] = []
    manifest = {
        "node": ("package.json",),
        "python": ("pyproject.toml", "requirements.txt", "setup.py", "Pipfile"),
        "rust": ("Cargo.toml",),
        "go": ("go.mod",),
        "make": ("Makefile",),
    }
    for name, files in manifest.items():
        if any((root / marker).is_file() for marker in files):
            found.append(name)
    return found


def project_brief(root: Path | str | None) -> dict[str, Any]:
    """The project's stack, run command, checks and git state. Never raises."""
    if root is None:
        return {"available": False, "reason": "there is no project folder selected"}
    base = Path(root)
    if not base.is_dir():
        return {"available": False, "reason": "the project folder is no longer there"}

    branch = git_probe_kind(base, "branch")
    status = git_probe_kind(base, "status")
    dirty = status.get("dirty") if status.get("available") else []
    plan = plan_preview(base)
    checks = plan_land_checks((), root=base)

    return {
        "available": True,
        "name": base.name,
        "path": str(base),
        "stack": _stack(base),
        "git": {
            "available": bool(branch.get("available")),
            "branch": branch.get("branch") if branch.get("available") else None,
            "dirty": len(dirty) if isinstance(dirty, list) else 0,
        },
        "run": {"command": plan.command, "source": plan.source},
        "checks": [{"id": check.id, "label": check.label} for check in checks.checks],
        "checksSource": checks.source,
        "warnings": list(checks.warnings),
        "hasRules": any((base / name).is_file() for name in RULE_FILES),
        "isHarnessRepo": (base / "python" / "harness" / "main.py").is_file(),
    }


__all__ = ["RULE_FILES", "project_brief"]
