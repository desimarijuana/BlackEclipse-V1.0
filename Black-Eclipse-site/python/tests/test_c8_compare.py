"""C8.6: two releases are comparable only on the same measurement contract."""

from __future__ import annotations

from harness.evaluation.compare_release import CompareError, compare


def _report(**overrides):
    dataset = {"version": "1.0.0", "checksum": "abc", "tier": 0, "graderVersion": 1}
    data = {
        "release": "0.4.0",
        "datasets": {"finance_qa_v1": dict(dataset)},
        "metrics": {"task_success": 0.9, "financial_accuracy": 0.95},
    }
    data.update(overrides)
    return data


def test_same_contract_produces_deltas():
    current = _report(release="0.4.1", metrics={"task_success": 0.92, "financial_accuracy": 0.95})
    result = compare(current, _report())
    assert result["comparable"] is True
    assert result["deltas"]["task_success"] == {"previous": 0.9, "current": 0.92, "delta": 0.02}


def test_a_changed_checksum_is_incomparable():
    changed = _report()
    changed["datasets"]["finance_qa_v1"]["checksum"] = "def"
    result = compare(changed, _report())
    assert result["comparable"] is False
    assert any("checksum" in reason for reason in result["reasons"])


def test_a_changed_tier_or_grader_is_incomparable():
    changed = _report()
    changed["datasets"]["finance_qa_v1"]["tier"] = 2
    assert compare(changed, _report())["comparable"] is False
    changed = _report()
    changed["datasets"]["finance_qa_v1"]["graderVersion"] = 2
    assert compare(changed, _report())["comparable"] is False


def test_a_changed_dataset_set_is_incomparable():
    changed = _report()
    changed["datasets"]["extra"] = {"version": "1", "checksum": "x", "tier": 0, "graderVersion": 1}
    result = compare(changed, _report())
    assert result["comparable"] is False
    assert any("dataset set" in reason for reason in result["reasons"])


def test_malformed_reports_raise():
    try:
        compare({"datasets": {}}, _report())
    except CompareError:
        pass
    else:  # pragma: no cover
        raise AssertionError("expected CompareError")
