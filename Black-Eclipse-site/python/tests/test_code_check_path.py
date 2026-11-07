"""Defects found by the LIVE failing-check acceptance run (2026-11-06).

Every case here happened in a real chat turn against a real project:

  * the model asked `command_run` for `unit_tests` (plural) -> the check path was
    abandoned and the agent shelled out;
  * `package_test` refused with "exit 1" and DROPPED the failing output, so the
    agent re-ran the suite through `terminal_run` to see it;
  * a project's `.black-eclipse/verify.json` written with a BOM silently pinned
    NO checks, so the verify-and-repair node never ran;
  * `shell_run` crashed with `name 'redact_output' is not defined`.
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

import pytest

from harness.code.policy import WorkspaceBinding
from harness.code.worktree import CodeWorkspace
from harness.code.workspace import ResolvedWorkspace
from harness.persistence import now_iso
from harness.tools import ToolContext


def test_resolve_class_accepts_the_obvious_plural():
    from harness.code import commands

    assert commands.resolve_class("unit_tests").name == "unit_test"
    assert commands.resolve_class("python_tests").name == "python_test"
    assert commands.resolve_class("unit_test").name == "unit_test"


def test_pinned_checks_are_read_through_a_bom(tmp_path):
    from harness.code.repair_graph import read_pinned_checks

    (tmp_path / ".black-eclipse").mkdir()
    payload = json.dumps({"checks": ["unit_test"]}).encode("utf-8")
    (tmp_path / ".black-eclipse" / "verify.json").write_bytes(b"\xef\xbb\xbf" + payload)

    pinned = read_pinned_checks(tmp_path)
    assert pinned.classes == ("unit_test",)


def test_a_refusal_carries_the_failing_output():
    from harness.execution.application._tool_common import refusal

    text, data = refusal("SCRIPT_FAILED", "npm reported a failure (exit 1)", output="1 !== 2")
    assert "REFUSED (SCRIPT_FAILED)" in text
    assert "1 !== 2" in text          # the agent must SEE why it failed
    assert data["output"] == "1 !== 2"  # and the structured copy is unchanged


def _shell_context(project: Path) -> ToolContext:
    ws_id = "cw_shell"
    binding = WorkspaceBinding(id=ws_id, root=project, base_revision="HEAD", strategy="direct")
    resolved = ResolvedWorkspace(
        id=ws_id, root=project, base_revision="HEAD", strategy="direct", binding=binding,
    )
    cw = CodeWorkspace(id=ws_id, root=project, strategy="direct", base_revision="HEAD", created_at=now_iso())
    ctx = ToolContext(run_id="run_shell", log=lambda *_: None, workspace=resolved, autonomy="edit_verify")
    ctx._code_workspace = (cw, binding, resolved, None)
    return ctx


def test_shell_run_redacts_instead_of_crashing(tmp_path):
    """`redact_output` was used but never imported: every shell_run raised."""
    from harness.code.shell_tools import shell_run

    ctx = _shell_context(Path(os.path.realpath(tmp_path)))
    command = 'node -e "console.log(\'hi from the shell\')"'
    text, data = asyncio.run(shell_run({"command": command}, ctx))

    assert "REFUSED" not in text, text
    assert data["status"] == "success"
    assert data["exitCode"] == 0
    assert "hi from the shell" in text
