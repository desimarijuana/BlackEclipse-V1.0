"""Phase 22 / S3: the offline maintenance door and the landing plan.

The point of these tests is the SAFETY ORDER, not the happy path alone:
stop -> apply -> verify -> restart -> health, with a rollback on every failure
after the apply, and no live path that can hot-swap an authority file.
"""

from __future__ import annotations

import json

import pytest

from harness.code import maintenance as maint
from harness.code import selfhost


def _preview(paths, digest="digest_abc_1234567890"):
    return {
        "previewDigest": digest,
        "files": [{"path": path} for path in paths],
    }


AUTHORITY = "python/harness/code/policy.py"


def test_plan_names_the_authority_and_the_offline_steps():
    plan = maint.plan_maintenance(_preview([AUTHORITY, "src/app/page.tsx"]))
    assert plan.authorities == (AUTHORITY,)
    assert plan.requires_offline is True
    assert plan.steps == (
        "check_tree", "stop_builder", "apply", "verify", "restart", "health",
    )


def test_an_ordinary_change_is_not_a_maintenance_change():
    with pytest.raises(maint.MaintenanceError) as excinfo:
        maint.plan_maintenance(_preview(["src/app/page.tsx"]))
    assert excinfo.value.code == "MAINTENANCE_NOT_REQUIRED"


def test_an_empty_preview_is_refused():
    with pytest.raises(maint.MaintenanceError) as excinfo:
        maint.plan_maintenance({"previewDigest": "d", "files": []})
    assert excinfo.value.code == "EMPTY_PREVIEW"


def test_a_missing_digest_is_refused():
    with pytest.raises(maint.MaintenanceError) as excinfo:
        maint.plan_maintenance({"files": [{"path": AUTHORITY}]})
    assert excinfo.value.code == "MISSING_DIGEST"


def test_a_dirty_tree_stops_before_any_side_effect():
    calls: list[str] = []
    with pytest.raises(maint.MaintenanceError) as excinfo:
        maint.run_maintenance(
            _preview([AUTHORITY]), tree_clean=False,
            stop_builder=lambda: calls.append("stop"),
            apply=lambda _p: calls.append("apply") or {"rollbackId": "rb"},
            verify=lambda: True, restart=lambda: calls.append("restart"),
            health=lambda: True, rollback=lambda _id: calls.append("rollback"),
        )
    assert excinfo.value.code == "DIRTY_TREE"
    assert calls == []


def test_the_happy_path_runs_in_order_and_never_rolls_back():
    calls: list[str] = []
    result = maint.run_maintenance(
        _preview([AUTHORITY]), tree_clean=True,
        stop_builder=lambda: calls.append("stop"),
        apply=lambda _p: (calls.append("apply"), {"rollbackId": "rb1"})[1],
        verify=lambda: calls.append("verify") or True,
        restart=lambda: calls.append("restart"),
        health=lambda: calls.append("health") or True,
        rollback=lambda _id: calls.append("rollback"),
    )
    assert calls == ["stop", "apply", "verify", "restart", "health"]
    assert result["ok"] is True
    assert result["rollbackId"] == "rb1"


def test_a_failed_verify_never_restarts_and_rolls_back():
    calls: list[str] = []
    with pytest.raises(maint.MaintenanceError) as excinfo:
        maint.run_maintenance(
            _preview([AUTHORITY]), tree_clean=True,
            stop_builder=lambda: calls.append("stop"),
            apply=lambda _p: (calls.append("apply"), {"rollbackId": "rb1"})[1],
            verify=lambda: calls.append("verify") or False,
            restart=lambda: calls.append("restart"),
            health=lambda: calls.append("health") or True,
            rollback=lambda _id: calls.append(f"rollback:{_id}"),
        )
    assert excinfo.value.code == "VERIFY_FAILED"
    assert "restart" not in calls and "health" not in calls
    assert calls[-1] == "rollback:rb1"
    assert excinfo.value.detail["rolledBack"] is True


def test_a_failed_health_check_rolls_back_after_the_restart():
    calls: list[str] = []
    with pytest.raises(maint.MaintenanceError) as excinfo:
        maint.run_maintenance(
            _preview([AUTHORITY]), tree_clean=True,
            stop_builder=lambda: calls.append("stop"),
            apply=lambda _p: (calls.append("apply"), {"rollbackId": "rb1"})[1],
            verify=lambda: True,
            restart=lambda: calls.append("restart"),
            health=lambda: calls.append("health") or False,
            rollback=lambda _id: calls.append(f"rollback:{_id}"),
        )
    assert excinfo.value.code == "HEALTH_FAILED"
    assert calls == ["stop", "apply", "restart", "health", "rollback:rb1"]


def test_an_apply_failure_is_typed_and_does_not_roll_back_nothing():
    calls: list[str] = []

    def boom(_preview):
        raise RuntimeError("worktree gone")

    with pytest.raises(maint.MaintenanceError) as excinfo:
        maint.run_maintenance(
            _preview([AUTHORITY]), tree_clean=True,
            stop_builder=lambda: calls.append("stop"),
            apply=boom, verify=lambda: True, restart=lambda: None,
            health=lambda: True, rollback=lambda _id: calls.append("rollback"),
        )
    assert excinfo.value.code == "APPLY_FAILED"
    assert "rollback" not in calls


def test_plan_landing_separates_runtime_frontend_and_authority():
    runtime = selfhost.plan_landing(["python/harness/graph.py"])
    assert runtime.steps == ("apply", "restart_builder", "health")
    assert runtime.buildRequired is False

    frontend = selfhost.plan_landing(["src/app/page.tsx"])
    assert frontend.steps == ("apply", "build_frontend", "health")
    assert frontend.restartRequired is False

    both = selfhost.plan_landing(["python/harness/graph.py", "src/app/page.tsx"])
    assert both.steps == ("apply", "restart_builder", "build_frontend", "health")

    authority = selfhost.plan_landing([AUTHORITY])
    assert authority.steps == ("maintenance",)
    assert authority.maintenanceRequired is True


def test_load_preview_is_bounded_and_typed(tmp_path):
    target = tmp_path / "preview.json"
    target.write_text(json.dumps(_preview([AUTHORITY])), encoding="utf-8")
    loaded = maint.load_preview(target)
    assert loaded["previewDigest"].startswith("digest_")

    with pytest.raises(maint.MaintenanceError) as excinfo:
        maint.load_preview(tmp_path / "missing.json")
    assert excinfo.value.code == "PREVIEW_NOT_FOUND"

    target.write_text("not json", encoding="utf-8")
    with pytest.raises(maint.MaintenanceError) as excinfo:
        maint.load_preview(target)
    assert excinfo.value.code == "INVALID_PREVIEW"
