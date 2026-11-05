"""Phase 22 / S4: the landing pipeline.

The exit code is the judge; a check that did not run is never "passed".
"""

from __future__ import annotations

import json

from harness.code import land


def _runner(codes):
    seen: list[str] = []

    def run(check, _root):
        seen.append(check.id)
        code = codes.get(check.id, 0)
        if isinstance(code, Exception):
            raise code
        return {"exitCode": code, "output": f"{check.id}: {code}"}

    return run, seen


def test_default_checks_are_ordered_and_frontend_build_is_conditional():
    backend = land.plan_land_checks(["python/harness/graph.py"])
    assert [c.id for c in backend.checks] == [
        "typecheck", "tests", "size", "secrets", "docs",
    ]
    frontend = land.plan_land_checks(["src/app/page.tsx"])
    assert "build" in [c.id for c in frontend.checks]
    assert frontend.source == "defaults"


def test_the_docs_obligation_is_a_real_check():
    ok, _ = land.docs_obligation(["docs/CHANGELOG.md", "src/app/page.tsx"])
    assert ok is True
    missing, reason = land.docs_obligation(["src/app/page.tsx"])
    assert missing is False
    assert "CHANGELOG" in reason
    assert land.docs_obligation([])[0] is False


def test_a_project_override_replaces_the_defaults(tmp_path):
    override = tmp_path / ".black-eclipse"
    override.mkdir()
    (override / "land.json").write_text(json.dumps({"checks": [
        {"id": "typecheck", "label": "Typecheck", "argv": ["npx", "tsc", "--noEmit"]},
        {"id": "docs", "label": "Change log", "kind": "docs"},
    ]}), encoding="utf-8")
    plan = land.plan_land_checks(["src/app/page.tsx"], root=tmp_path)
    assert plan.source == "project"
    assert [c.id for c in plan.checks] == ["typecheck", "docs"]


def test_an_invalid_override_falls_back_with_a_warning(tmp_path):
    override = tmp_path / ".black-eclipse"
    override.mkdir()
    (override / "land.json").write_text("{not json", encoding="utf-8")
    plan = land.plan_land_checks(["src/app/page.tsx"], root=tmp_path)
    assert plan.source == "defaults"
    assert plan.warnings
    assert "build" in [c.id for c in plan.checks]


def test_a_failed_required_check_stops_the_pipeline():
    plan = land.plan_land_checks(["python/harness/graph.py"])
    run, seen = _runner({"typecheck": 0, "tests": 1, "size": 0})
    result = land.run_land_plan(plan, root=__import__("pathlib").Path("."), runner=run)
    assert result.ok is False
    assert result.failed == "tests"
    assert seen == ["typecheck", "tests"]
    statuses = {item.id: item.status for item in result.results}
    assert statuses["typecheck"] == "passed"
    assert statuses["tests"] == "failed"
    assert statuses["size"] == "skipped"
    assert statuses["docs"] == "skipped"


def test_a_failed_optional_check_does_not_stop_the_pipeline():
    checks = (
        land.LandCheck("a", "A", "command", ("x",), required=False),
        land.LandCheck("b", "B", "command", ("y",)),
    )
    plan = land.LandPlan(("src/app/page.tsx",), checks, "project")
    run, seen = _runner({"a": 1, "b": 0})
    result = land.run_land_plan(plan, root=__import__("pathlib").Path("."), runner=run)
    assert result.ok is True
    assert seen == ["a", "b"]


def test_an_unrunnable_check_is_an_error_not_a_pass():
    plan = land.LandPlan(
        ("python/harness/graph.py",),
        (land.LandCheck("a", "A", "command", ("missing",)),),
        "project",
    )
    run, _ = _runner({"a": RuntimeError("no such program")})
    result = land.run_land_plan(plan, root=__import__("pathlib").Path("."), runner=run)
    assert result.ok is False
    assert result.results[0].status == "error"
    assert result.results[0].exit_code is None


def test_the_docs_check_passes_only_when_the_changelog_is_in_the_change():
    checks = (land.LandCheck("docs", "Change log", "docs"),)
    good = land.run_land_plan(
        land.LandPlan(("docs/CHANGELOG.md",), checks, "project"),
        root=__import__("pathlib").Path("."),
    )
    assert good.ok is True
    bad = land.run_land_plan(
        land.LandPlan(("src/app/page.tsx",), checks, "project"),
        root=__import__("pathlib").Path("."),
    )
    assert bad.ok is False
    assert bad.results[0].status == "failed"
