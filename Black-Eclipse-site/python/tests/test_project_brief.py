"""The project brief: what Eclipse found in a project (P5)."""

from __future__ import annotations

import json

from harness.code import onboarding


def _node_project(tmp_path):
    (tmp_path / "package.json").write_text(json.dumps({"scripts": {
        "dev": "next dev", "test": "vitest", "build": "next build",
    }}), encoding="utf-8")
    (tmp_path / "tsconfig.json").write_text("{}", encoding="utf-8")


def test_the_brief_names_the_stack_run_and_checks(tmp_path):
    _node_project(tmp_path)
    brief = onboarding.project_brief(tmp_path)
    assert brief["available"] is True
    assert brief["name"] == tmp_path.name
    assert "node" in brief["stack"]
    assert brief["run"]["command"] == "npm run dev"
    assert [check["id"] for check in brief["checks"]] == ["typecheck", "tests", "build"]
    assert brief["checksSource"] == "detected"


def test_the_brief_reports_a_missing_project_honestly():
    assert onboarding.project_brief(None)["available"] is False
    assert onboarding.project_brief("/this/folder/does/not/exist")["available"] is False


def test_rules_and_python_manifests_are_detected(tmp_path):
    (tmp_path / "AGENTS.md").write_text("# rules\n", encoding="utf-8")
    (tmp_path / "requirements.txt").write_text("pytest>=8\n", encoding="utf-8")
    brief = onboarding.project_brief(tmp_path)
    assert brief["hasRules"] is True
    assert "python" in brief["stack"]
    assert [check["id"] for check in brief["checks"]] == ["tests"]


def test_an_unrecognised_project_says_so(tmp_path):
    brief = onboarding.project_brief(tmp_path)
    assert brief["checks"] == []
    assert brief["checksSource"] == "none"
    assert brief["run"]["source"] == "none"
