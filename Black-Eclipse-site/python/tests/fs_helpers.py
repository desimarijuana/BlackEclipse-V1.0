"""Shared fixtures for the file-system subsystem tests.

Every test builds a real temp workspace and a `FileSystemService` bound to it, so
the tests exercise the SAME code path the tools use (confinement → permissions →
operations), not a mock.
"""

from __future__ import annotations

import os
from pathlib import Path

from harness.code.fs.service import FileSystemService
from harness.code.policy import WorkspaceBinding
from harness.code.workspace import ResolvedWorkspace
from harness.skills.permissions import Actor


def make_ws(root: Path, *, ws_id: str = "ws_t", strategy: str = "checkout") -> ResolvedWorkspace:
    real = Path(os.path.realpath(root))
    binding = WorkspaceBinding(id=ws_id, root=real, base_revision="abc1234", strategy=strategy)
    return ResolvedWorkspace(
        id=ws_id, root=real, base_revision="abc1234", strategy=strategy, binding=binding,
    )


def make_service(root: Path, autonomy: str = "edit_verify", *, config=None) -> FileSystemService:
    ws = make_ws(root)
    actor = Actor(id="coder", workspace_id=ws.id, autonomy=autonomy)
    return FileSystemService(ws, ws.binding, actor, config=config)


def tree(tmp_path: Path) -> Path:
    """A small, deterministic project tree."""
    root = tmp_path / "ws"
    (root / "src").mkdir(parents=True)
    (root / "src" / "app.py").write_text("alpha\nbeta\ngamma\n", encoding="utf-8")
    (root / "src" / "other.py").write_text("UNTOUCHED = True\n", encoding="utf-8")
    (root / "src" / "nested").mkdir()
    (root / "src" / "nested" / "util.py").write_text(
        "def calculateTotal():\n    return 42\n", encoding="utf-8",
    )
    (root / "docs").mkdir()
    (root / "docs" / "readme.md").write_text("# Docs\nA valuation method.\n", encoding="utf-8")
    (root / "node_modules").mkdir()
    (root / "node_modules" / "pkg.js").write_text("module.exports = 1\n", encoding="utf-8")
    return root


def make_escape_link(link: Path, target: Path) -> bool:
    """A symlink where allowed, else a Windows junction. False when neither works."""
    import subprocess
    import sys

    try:
        os.symlink(target, link, target_is_directory=True)
        return True
    except (OSError, NotImplementedError):
        pass
    if sys.platform == "win32":
        result = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(link), str(target)],
            capture_output=True, text=True,
        )
        return result.returncode == 0
    return False


__all__ = ["make_escape_link", "make_service", "make_ws", "tree"]
