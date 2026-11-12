"""C8.3: the finance QA corpus is real, deterministic and passing."""

from __future__ import annotations

from harness.evaluation.gate import run_offline_gate
from harness.evaluation.tasks import load_builtin_dataset


def test_finance_qa_has_the_required_families():
    dataset = load_builtin_dataset("finance_qa_v1")
    ids = {task.id for task in dataset.tasks}
    assert len(ids) >= 9
    assert any("unavailable" in task_id for task_id in ids)
    assert any("margin" in task_id for task_id in ids)
    assert any("drawdown" in task_id for task_id in ids)
    assert any("position_size" in task_id for task_id in ids)


def test_finance_qa_passes_its_floors_offline():
    suite = run_offline_gate(dataset_name="finance_qa_v1")
    assert suite.passed, suite.thresholds
    assert suite.aggregates["task_success"] == 1.0
    assert suite.aggregates["financial_accuracy"] == 1.0
