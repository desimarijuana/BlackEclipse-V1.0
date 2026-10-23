"""Deterministic held_out rotation: plan, apply, idempotence."""

from __future__ import annotations

import json

from harness.evaluation.rotation import apply_rotation, plan_rotation, render_plan


def _task(task_id, split):
    return {
        "id": task_id,
        "version": 1,
        "category": "core",
        "difficulty": "easy",
        "input": {"prompt": task_id},
        "metadata": {"split": split},
    }


def _write(tmp_path):
    a = {
        "datasetName": "a",
        "datasetVersion": "1",
        "schemaVersion": 1,
        "metadata": {"split": "optimization"},
        "tasks": [
            _task("a.opt1", "optimization"),
            _task("a.opt2", "optimization"),
            _task("a.opt3", "optimization"),
            _task("a.held1", "held_out"),
        ],
    }
    b = {
        "datasetName": "b",
        "datasetVersion": "1",
        "schemaVersion": 1,
        "metadata": {"split": "validation"},
        "tasks": [
            _task("b.opt1", "optimization"),
            _task("b.val1", "validation"),
        ],
    }
    (tmp_path / "a.json").write_text(json.dumps(a), encoding="utf-8")
    (tmp_path / "b.json").write_text(json.dumps(b), encoding="utf-8")


def test_the_plan_is_seeded_and_returns_the_current_held_out(tmp_path):
    _write(tmp_path)
    first = plan_rotation(quarter="2026Q1", count=2, datasets_dir=str(tmp_path))
    second = plan_rotation(quarter="2026Q1", count=2, datasets_dir=str(tmp_path))

    assert first["ok"] is True
    assert first["moves"] == second["moves"]
    assert first["count"] == 2
    assert first["returned"] == 1
    forward = [m for m in first["moves"] if m["to"] == "held_out"]
    back = [m for m in first["moves"] if m["to"] == "optimization"]
    assert len(forward) == 2
    assert [m["taskId"] for m in back] == ["a.held1"]
    assert all(m["from"] == "optimization" for m in forward)


def test_apply_writes_the_split_and_is_idempotent(tmp_path):
    _write(tmp_path)
    plan = plan_rotation(quarter="2026Q1", count=2, datasets_dir=str(tmp_path))

    result = apply_rotation(
        plan, datasets_dir=str(tmp_path),
        refresh_manifest=False, rotated_at="2026-10-22T00:00:00.000Z",
    )
    assert result["applied"] is True
    assert result["moved"] == 3
    assert result["skipped"] == 0

    a = json.loads((tmp_path / "a.json").read_text(encoding="utf-8"))
    by_id = {task["id"]: task for task in a["tasks"]}
    for move in plan["moves"]:
        if move["datasetFile"] != "a.json":
            continue
        task = by_id[move["taskId"]]
        assert task["metadata"]["split"] == move["to"]
        assert task["version"] == 2
        assert task["metadata"]["rotation"]["quarter"] == "2026Q1"

    # The same plan cannot move the same task twice in one quarter.
    again = apply_rotation(
        plan, datasets_dir=str(tmp_path), refresh_manifest=False,
    )
    assert again["moved"] == 0
    assert again["skipped"] == 3


def test_validation_is_never_rotated(tmp_path):
    _write(tmp_path)
    plan = plan_rotation(quarter="2026Q1", count=10, datasets_dir=str(tmp_path))
    ids = {move["taskId"] for move in plan["moves"]}
    assert "b.val1" not in ids
    assert all(move["to"] != "validation" for move in plan["moves"])


def test_a_rotation_exempt_dataset_is_skipped(tmp_path):
    _write(tmp_path)
    protected = {
        "datasetName": "protected",
        "datasetVersion": "1",
        "schemaVersion": 1,
        "metadata": {"split": "optimization", "rotationExempt": True},
        "tasks": [_task("p.opt1", "optimization"), _task("p.held1", "held_out")],
    }
    (tmp_path / "p.json").write_text(json.dumps(protected), encoding="utf-8")

    plan = plan_rotation(quarter="2026Q1", count=10, datasets_dir=str(tmp_path))
    ids = {move["taskId"] for move in plan["moves"]}
    assert "p.opt1" not in ids
    assert "p.held1" not in ids


def test_a_corpus_without_optimization_tasks_is_not_rotated(tmp_path):
    payload = {
        "datasetName": "only-validation",
        "datasetVersion": "1",
        "schemaVersion": 1,
        "tasks": [_task("v1", "validation")],
    }
    (tmp_path / "v.json").write_text(json.dumps(payload), encoding="utf-8")
    plan = plan_rotation(quarter="2026Q1", count=2, datasets_dir=str(tmp_path))
    assert plan["ok"] is False
    assert plan["reason"] == "no_optimization_tasks"


def test_render_plan_names_every_move(tmp_path):
    _write(tmp_path)
    plan = plan_rotation(quarter="2026Q1", count=2, datasets_dir=str(tmp_path))
    text = render_plan(plan)
    assert "2026Q1" in text
    for move in plan["moves"]:
        assert move["taskId"] in text
