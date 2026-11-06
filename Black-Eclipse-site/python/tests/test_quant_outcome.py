"""The quant outcome is derived from the run's own records — never guessed."""

from __future__ import annotations

from harness.run_outcome import build_outcome_envelope


def test_a_quant_plan_produces_a_quant_outcome() -> None:
    envelope = build_outcome_envelope(
        run_id="run_q",
        run={"agentId": "eclipse-agent", "output": "Chart and experiment exp_abcd1234."},
        events=[{"type": "quant.plan", "data": {"tier": "standard", "kind": "forecast"}}],
        tool_executions=[{"name": "analysis_run"}],
    )
    assert envelope["quant"]["tier"] == "standard"
    assert envelope["quant"]["kind"] == "forecast"
    assert envelope["quant"]["complete"] is True
    assert envelope["quant"]["artifacts"] == ["exp_abcd1234"]


def test_a_run_without_a_quant_plan_has_no_quant_outcome() -> None:
    envelope = build_outcome_envelope(run_id="run_plain", run={"agentId": "eclipse-agent"})
    assert envelope["quant"] is None
