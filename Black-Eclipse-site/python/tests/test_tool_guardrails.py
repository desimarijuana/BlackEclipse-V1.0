"""W3.2: deterministic tool-loop guardrails (warn first, then controlled halt)."""

from __future__ import annotations

from harness.tool_guardrails import ToolGuardrail, is_repeatable, request_reset, result_digest


def _run(guard: ToolGuardrail, name: str, args: dict, result: str, *, ok: bool = True):
    guard.after(name, args, ok=ok, text=result)


def test_three_identical_successful_calls_halt_before_the_third_dispatch():
    guard = ToolGuardrail(mode="halt")
    guard.after("market_get_quote", {"symbol": "AAPL"}, ok=True, text="quote 100")
    guard.after("market_get_quote", {"symbol": "AAPL"}, ok=True, text="quote 100")

    decision = guard.before("market_get_quote", {"symbol": "AAPL"})
    assert decision.should_halt
    assert decision.rule == "identical_call"
    assert decision.count == 3


def test_changed_arguments_are_allowed_and_different_results_are_not_a_loop():
    guard = ToolGuardrail(mode="halt")
    guard.after("market_get_quote", {"symbol": "AAPL"}, ok=True, text="quote 100")
    guard.after("market_get_quote", {"symbol": "AAPL"}, ok=True, text="quote 101")
    assert guard.before("market_get_quote", {"symbol": "AAPL"}).action == "allow"

    guard.after("market_get_quote", {"symbol": "MSFT"}, ok=True, text="quote 100")
    assert guard.before("market_get_quote", {"symbol": "TSLA"}).action == "allow"


def test_pollers_and_result_getters_are_exempt():
    for name in ("read_tool_output", "process_manage", "job_poll", "run_get_result", "clarify"):
        assert is_repeatable(name)
        guard = ToolGuardrail(mode="halt")
        for _ in range(3):
            guard.after(name, {}, ok=True, text="same")
        assert guard.before(name, {}).action == "allow"


def test_warn_mode_returns_a_directive_but_never_halts():
    guard = ToolGuardrail(mode="warn")
    guard.after("t", {}, ok=True, text="same")
    guard.after("t", {}, ok=True, text="same")
    decision = guard.before("t", {})
    assert decision.action == "warn"
    assert "already returned the same result" in decision.message
    assert decision.directive().startswith("\n\n[guardrail]")


def test_off_mode_never_decides_or_records():
    guard = ToolGuardrail(mode="off")
    guard.after("t", {}, ok=True, text="same")
    guard.after("t", {}, ok=True, text="same")
    assert guard.before("t", {}).action == "allow"
    assert guard.observations == []


def test_cycle_is_detected_after_two_full_repetitions():
    guard = ToolGuardrail(mode="halt")
    for name, args, text in (
        ("a", {}, "1"), ("b", {}, "2"),
        ("a", {}, "1"), ("b", {}, "2"),
    ):
        guard.after(name, args, ok=True, text=text)
    decision = guard.before("a", {})
    assert decision.rule == "cycle"
    assert decision.should_halt


def test_failure_streak_halts_the_next_call():
    guard = ToolGuardrail(mode="halt", max_failure_streak=3)
    for index in range(3):
        guard.after(f"t{index}", {}, ok=False, text=f"fail {index}")
    decision = guard.before("t9", {})
    assert decision.rule == "failure_streak"
    assert decision.should_halt


def test_a_success_resets_the_failure_streak():
    guard = ToolGuardrail(mode="halt", max_failure_streak=3)
    guard.after("a", {}, ok=False, text="x")
    guard.after("b", {}, ok=False, text="y")
    guard.after("c", {}, ok=True, text="ok")
    guard.after("d", {}, ok=False, text="z")
    assert guard.before("e", {}).action == "allow"


def test_operator_reset_clears_the_ledger_on_the_next_decision():
    guard = ToolGuardrail(mode="halt")
    guard.after("t", {}, ok=True, text="same")
    guard.after("t", {}, ok=True, text="same")
    request_reset("run-reset-1")
    assert guard.before("t", {}, run_id="run-reset-1").action == "allow"
    assert guard.observations == []


def test_result_digest_is_stable_and_does_not_embed_raw_text():
    first = result_digest("secret-ish text", True, {"a": 1})
    second = result_digest("secret-ish text", True, {"a": 1})
    assert first == second
    assert "secret" not in first
    assert result_digest("other", True, {"a": 1}) != first
