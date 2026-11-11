"""Phase 9 G2/G7 — scaffolding into a worktree, the closed output set, and that
the user's checkout is untouched.

The scaffold tool writes only into the disposable workspace (Phase 2), never the
user's checkout, and only the kit's declared `produces` set.
"""

from __future__ import annotations

import asyncio
import os
import subprocess
from pathlib import Path

import pytest

from harness.code import sandbox as sandbox_mod
from harness.code.kits import get_kit, render_kit
from harness.code.tools import register_code_tools
from harness.schemas import ModelSettings
from harness.tools import ToolContext, ToolRegistry


def _git_repo(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    env = {**os.environ}
    subprocess.run(["git", "init", "-q"], cwd=path, env=env, capture_output=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=path, env=env, capture_output=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=path, env=env, capture_output=True)
    (path / "README.md").write_text("seed\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=path, env=env, capture_output=True)
    subprocess.run(["git", "commit", "-qm", "seed"], cwd=path, env=env, capture_output=True)


def _ctx(monkeypatch, repo: Path, **overrides) -> ToolContext:
    monkeypatch.setenv("BLACK_ECLIPSE_CODE_ROOT", str(repo))
    from harness.code.workspace import resolve_workspace

    base = dict(
        run_id="run_scaffold",
        log=lambda *_: None,
        user_id="local",
        model_settings=ModelSettings(provider="ollama", model="llama3.1"),
        tool_registry=ToolRegistry(),
        memory_store=None,
        workspace=resolve_workspace(None),
        autonomy="edit_verify",
    )
    base.update(overrides)
    return ToolContext(**base)


def test_scaffold_kit_is_registered():
    registry = ToolRegistry()
    register_code_tools(registry)
    assert registry.get("scaffold_kit") is not None


def test_unknown_kit_is_refused(monkeypatch, tmp_path):
    from harness.scaffold_tools import scaffold_kit

    repo = tmp_path / "repo"
    _git_repo(repo)
    _, data = asyncio.run(scaffold_kit({"kit_id": "nope", "inputs": {}}, _ctx(monkeypatch, repo)))
    assert data["status"] == "refused"
    assert data["code"] == "KIT_UNKNOWN"


def test_missing_input_is_refused(monkeypatch, tmp_path):
    from harness.scaffold_tools import scaffold_kit

    repo = tmp_path / "repo"
    _git_repo(repo)
    _, data = asyncio.run(scaffold_kit(
        {"kit_id": "ratio_calculator", "inputs": {"ratio_name": "roe"}}, _ctx(monkeypatch, repo),
    ))
    assert data["status"] == "refused"
    assert data["code"] == "KIT_INPUT_MISSING"


def test_default_off_without_the_write_profile(monkeypatch, tmp_path):
    from harness.scaffold_tools import scaffold_kit

    repo = tmp_path / "repo"
    _git_repo(repo)
    _, data = asyncio.run(scaffold_kit(
        {"kit_id": "ratio_calculator", "inputs": {"ratio_name": "roe", "description": "x"}},
        _ctx(monkeypatch, repo, autonomy="plan_only"),
    ))
    assert data["status"] == "refused"
    assert data["code"] == "PROFILE_DENIED"
    # A refusal must name the surface that can do it, never dead-end the user.
    assert "skill_create" in data["reason"] and "bot_create" in data["reason"]


def test_scaffold_writes_only_the_declared_set_and_leaves_the_checkout_untouched(monkeypatch, tmp_path):
    from harness.scaffold_tools import scaffold_kit

    repo = tmp_path / "repo"
    _git_repo(repo)
    # A pre-existing dirty file in the user's checkout: its bytes must be identical
    # afterwards (the scaffold never writes into the checkout).
    dirty = repo / "pre_existing.txt"
    dirty.write_text("do not touch\n", encoding="utf-8")
    before = dirty.read_bytes()

    _, data = asyncio.run(scaffold_kit(
        {"kit_id": "ratio_calculator", "inputs": {"ratio_name": "roe", "description": "return on equity"}},
        _ctx(monkeypatch, repo),
    ))
    if data["status"] == "refused" and data["code"] == "SANDBOX_UNAVAILABLE":
        pytest.skip("sandbox unavailable")
    assert data["status"] == "ok", data
    assert set(data["files"]) == {
        "python/harness/research/ratios_roe.py",
        "python/tests/test_ratios_roe.py",
    }
    # The user's checkout is untouched.
    assert dirty.read_bytes() == before
    assert not (repo / "python/harness/research/ratios_roe.py").exists()


def test_render_is_closed_to_the_declared_set():
    # The renderer itself cannot emit an undeclared path (the closed-set check).
    rendered = render_kit("ratio_calculator", {"ratio_name": "roa", "description": "return on assets"})
    assert set(rendered) == {
        "python/harness/research/ratios_roa.py",
        "python/tests/test_ratios_roa.py",
    }
