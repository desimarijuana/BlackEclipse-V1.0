"""Phase 9 G6 — a generated research workflow loads and stays INERT."""

from __future__ import annotations

from pathlib import Path

from harness.code.kits import render_kit
from harness.skills.loader import load_skill_folder

_INPUTS = {"workflow_name": "margin_review", "description": "Compare two companies' margins."}


def _write_flat(tmp_path: Path, rendered: dict[str, str]) -> Path:
    """Write the rendered skill files into one flat folder (as the loader expects)."""
    folder = tmp_path / "skills/research/margin_review"
    folder.mkdir(parents=True, exist_ok=True)
    for rel, text in rendered.items():
        (folder / Path(rel).name).write_text(text, encoding="utf-8")
    return folder


def test_generated_workflow_loads_and_is_a_draft(tmp_path):
    rendered = render_kit("research_workflow", _INPUTS)
    loaded = load_skill_folder(str(_write_flat(tmp_path, rendered)))
    manifest = loaded.manifest
    assert manifest.id == "research.margin_review"
    assert manifest.status == "draft"        # INERT — never auto-enabled
    assert manifest.is_executable is False
    assert loaded.load_instructions()         # the prose ships too


def test_generated_manifest_validates_and_declares_safe_permissions(tmp_path):
    rendered = render_kit("research_workflow", _INPUTS)
    loaded = load_skill_folder(str(_write_flat(tmp_path, rendered)))
    assert loaded.manifest.permissions == ["data.read", "research.read"]
    assert loaded.manifest.is_active is False


def test_rendered_paths_are_within_the_declared_set():
    rendered = render_kit("research_workflow", _INPUTS)
    assert set(rendered) == {
        "python/harness/skills/library/research/margin_review/skill.json",
        "python/harness/skills/library/research/margin_review/SKILL.md",
    }
