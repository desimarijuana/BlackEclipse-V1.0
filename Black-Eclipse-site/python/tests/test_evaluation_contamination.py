"""Split access control, oracle metadata and decoy canaries."""

from __future__ import annotations

import pytest

from harness.evaluation.contamination import (
    ContaminationError,
    access_guard,
    assert_no_canary_hack,
    contamination_summary,
    has_oracle,
    is_canary,
    select_for_purpose,
)
from harness.evaluation.tasks import EvaluationTask


def _task(task_id: str, split: str, *, oracle=None, canary=False):
    metadata = {"split": split}
    if oracle is not None:
        metadata["oracle"] = oracle
    if canary:
        metadata["canary"] = True
    return EvaluationTask.from_dict({
        "id": task_id,
        "category": "core",
        "difficulty": "easy",
        "input": {"prompt": "fixture"},
        "metadata": metadata,
    })


def test_each_purpose_reads_only_its_own_split():
    optimization = _task("opt", "optimization")
    validation = _task("val", "validation")
    held_out = _task("held", "held_out")
    release = _task("rel", "release")

    assert access_guard(optimization, "optimization")["split"] == "optimization"
    assert access_guard(validation, "validation")["split"] == "validation"
    assert access_guard(held_out, "canary")["split"] == "held_out"
    assert access_guard(release, "release")["split"] == "release"

    with pytest.raises(ContaminationError) as refused:
        access_guard(held_out, "optimization")
    assert refused.value.code == "CONTAMINATION_SPLIT"

    with pytest.raises(ContaminationError) as refused:
        access_guard(validation, "optimization")
    assert refused.value.code == "CONTAMINATION_SPLIT"


def test_a_canary_cannot_be_an_acceptance_task():
    canary = _task("canary", "validation", canary=True)
    with pytest.raises(ContaminationError) as refused:
        access_guard(canary, "validation")
    assert refused.value.code == "CANARY_IN_VALIDATION"


def test_select_for_purpose_names_every_refusal():
    tasks = [
        _task("opt", "optimization"),
        _task("val", "validation"),
        _task("held", "held_out"),
    ]
    allowed, refused = select_for_purpose(tasks, "optimization")
    assert [task.id for task in allowed] == ["opt"]
    assert {item["taskId"] for item in refused} == {"val", "held"}
    assert all(item["code"] == "CONTAMINATION_SPLIT" for item in refused)


def test_unknown_purpose_is_refused():
    with pytest.raises(ContaminationError) as refused:
        access_guard(_task("opt", "optimization"), "training")
    assert refused.value.code == "UNKNOWN_PURPOSE"


def test_oracle_and_canary_metadata_are_read_honestly():
    assert has_oracle(_task("o", "optimization", oracle="recompute net margin"))
    assert has_oracle(_task("r", "optimization", oracle=True))
    assert not has_oracle(_task("n", "optimization"))
    assert is_canary(_task("c", "optimization", canary=True))
    assert not is_canary(_task("n", "optimization"))


def test_a_decoy_canary_that_passes_is_a_hard_failure():
    canary = _task("c", "optimization", canary=True)
    with pytest.raises(ContaminationError) as refused:
        assert_no_canary_hack(canary, True)
    assert refused.value.code == "CANARY_HACK"

    # A normal task passing, or a canary failing, is not a hack.
    assert_no_canary_hack(_task("n", "optimization"), True)
    assert_no_canary_hack(canary, False)


def test_summary_counts_splits_oracles_and_canaries():
    tasks = [
        _task("a", "optimization", oracle="oracle"),
        _task("b", "optimization", canary=True),
        _task("c", "validation"),
        _task("d", "held_out"),
    ]
    summary = contamination_summary(tasks)
    assert summary["tasks"] == 4
    assert summary["bySplit"] == {
        "held_out": 1, "optimization": 2, "validation": 1,
    }
    assert summary["canaries"] == 1
    assert summary["withOracle"] == 1
    assert summary["oracleCoverage"] == 0.25
