"""C8.2: external adapters are honest, normalized and gate-able offline."""

from __future__ import annotations

from harness.evaluation.adapters import ADAPTERS, adapter_by_name, run_external_gate


def test_every_adapter_is_available_with_a_provenance_and_license():
    assert {adapter.name for adapter in ADAPTERS} == {
        "swe-bench-lite", "gaia", "tau-bench", "financebench",
    }
    for adapter in ADAPTERS:
        info = adapter.info()
        assert info.available, info.unmeasured_reason
        assert info.cases >= 2
        assert info.source.startswith("http")
        assert info.license


def test_adapters_normalize_to_evaluation_tasks_with_provenance():
    for adapter in ADAPTERS:
        tasks = adapter.load(limit=5)
        assert tasks
        for task in tasks:
            external = task.metadata.get("external") or {}
            assert external["benchmark"] == adapter.name
            assert external["caseId"] == task.id
            assert external["license"] == adapter.info().license


def test_an_unknown_adapter_is_none():
    assert adapter_by_name("not-a-benchmark") is None


def test_the_offline_external_gate_passes():
    result = run_external_gate()
    assert result["ok"], result
    assert result["available"] == 4
    assert result["failed"] == []
    assert all(row["suiteOk"] for row in result["adapters"])
