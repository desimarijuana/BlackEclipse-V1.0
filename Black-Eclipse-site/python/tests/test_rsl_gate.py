"""R8 — the offline RSL release gate is deterministic and honest."""

from __future__ import annotations

from harness.self_improvement.gate import format_rsl_gate_report, run_offline_rsl_gate


def test_offline_rsl_gate_passes_and_reports_a_measured_experiment():
    result = run_offline_rsl_gate()
    assert result["passed"] is True, result["failures"]
    assert result["summary"]["k"] == 2
    assert result["summary"]["composition"] == "composed"
    assert result["summary"]["metrics"]["rsl_experiments"] == 1
    assert result["summary"]["metrics"]["rsl_accepted"] == 1

    report = format_rsl_gate_report(result)
    assert report.startswith("rsl gate: PASS")
    assert "experiments=1" in report
    assert "unmeasured=0" in report
