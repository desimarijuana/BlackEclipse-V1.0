"""Task schema, dataset loading, versioning and selection."""

from __future__ import annotations

import pytest

from harness.evaluation.tasks import (
    Dataset,
    EvaluationTask,
    TaskValidationError,
    available_datasets,
    dataset_from_dict,
    load_all_builtin,
    load_builtin_dataset,
    select_tasks,
)


def test_task_roundtrip_and_fingerprint_stability():
    data = {
        "id": "x.001", "version": 2, "category": "finance", "difficulty": "hard",
        "input": {"prompt": "hi"}, "expected_tools": ["a", "b"],
        "limits": {"max_turns": 5, "max_tool_calls": 9},
    }
    task = EvaluationTask.from_dict(data)
    assert task.version == 2
    assert task.limits.max_turns == 5
    assert task.to_dict()["expected_tools"] == ["a", "b"]
    assert task.fingerprint() == EvaluationTask.from_dict(data).fingerprint()


def test_changing_a_task_changes_its_fingerprint():
    a = EvaluationTask.from_dict({"id": "x", "version": 1, "category": "core",
                                  "difficulty": "easy", "input": {"prompt": "a"}})
    b = EvaluationTask.from_dict({"id": "x", "version": 1, "category": "core",
                                  "difficulty": "easy", "input": {"prompt": "b"}})
    assert a.fingerprint() != b.fingerprint()


def test_unknown_category_and_difficulty_are_rejected():
    with pytest.raises(TaskValidationError):
        EvaluationTask.from_dict({"id": "x", "category": "nope", "difficulty": "easy",
                                  "input": {"prompt": "a"}})
    with pytest.raises(TaskValidationError):
        EvaluationTask.from_dict({"id": "x", "category": "core", "difficulty": "nope",
                                  "input": {"prompt": "a"}})


def test_duplicate_task_ids_are_rejected():
    with pytest.raises(TaskValidationError):
        dataset_from_dict({"tasks": [
            {"id": "dup", "category": "core", "difficulty": "easy", "input": {"prompt": "a"}},
            {"id": "dup", "category": "core", "difficulty": "easy", "input": {"prompt": "b"}},
        ]})


def test_builtin_benchmark_loads_and_is_reviewed():
    assert "benchmark_v1" in available_datasets()
    dataset = load_builtin_dataset("benchmark_v1")
    assert isinstance(dataset, Dataset)
    assert dataset.reviewed is True
    assert len(dataset.tasks) >= 25
    assert dataset.checksum


def test_checksum_is_content_addressed():
    a = load_builtin_dataset("benchmark_v1")
    b = load_builtin_dataset("benchmark_v1")
    assert a.checksum == b.checksum
    changed = Dataset(name=a.name, version=a.version,
                      tasks=a.tasks[:-1] + [EvaluationTask.from_dict({
                          "id": a.tasks[-1].id, "category": "core", "difficulty": "easy",
                          "input": {"prompt": "changed"},
                      })])
    assert changed.checksum != a.checksum


def test_selection_by_category_task_and_difficulty():
    dataset = load_all_builtin()
    finance = select_tasks(dataset, category="finance")
    assert finance and all(t.category == "finance" for t in finance)
    one = select_tasks(dataset, task_id="finance.pe.001")
    assert len(one) == 1
    hard = select_tasks(dataset, difficulty="hard")
    assert hard and all(t.difficulty == "hard" for t in hard)


def test_live_only_detection():
    dataset = load_builtin_dataset("benchmark_v1")
    research = dataset.by_id("research.live.001")
    assert research.live_only is True
    assert dataset.by_id("finance.pe.001").live_only is False


def test_live_eligible_excludes_eval_only_tools_and_synthetic_environments():
    dataset = load_all_builtin()
    assert dataset.by_id("adversarial.unavailable.001").live_eligible is False
    assert dataset.by_id("tools.memory_roundtrip.001").live_eligible is False
    # Tier 0 is still live-measurable when the prompt carries its own inputs
    # (the finance fixtures do); an explicit opt-out is the only exclusion.
    assert dataset.by_id("finance.pe.001").live_eligible is True

    eligible = [task for task in dataset.tasks if task.live_eligible]
    assert eligible
    for task in eligible:
        names = (*task.required_tools, *task.expected_tools)
        assert not any(str(name).startswith("eval_") for name in names)
        env_type = str((task.environment or {}).get("type") or "").lower()
        assert env_type not in {"mock_services", "filesystem", "database"}
