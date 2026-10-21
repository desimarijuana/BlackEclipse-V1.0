"""Surface guardrails: the runtime checks the finished answer, not the prompt."""

from __future__ import annotations

import pytest

from harness.self_improvement.guardrails import (
    GUARDRAILS,
    evaluate_guardrails,
    guardrail_error,
)


def test_no_guardrails_means_no_violation():
    assert evaluate_guardrails([], output="anything") == []
    assert evaluate_guardrails(None, output="anything") == []


def test_an_answer_without_a_tool_call_breaks_the_tool_guardrail():
    violations = evaluate_guardrails(
        ["require_tool_before_answer"], output="done", tool_calls=0,
    )
    assert violations[0]["code"] == "GUARDRAIL_TOOL_REQUIRED"
    error = guardrail_error(violations)
    assert error["code"] == "GUARDRAIL_TOOL_REQUIRED"
    assert "require_tool_before_answer" in (error["detail"] or "")


def test_a_tool_call_satisfies_the_tool_guardrail():
    assert evaluate_guardrails(
        ["require_tool_before_answer"], output="done", tool_calls=1,
    ) == []


def test_the_citation_guardrail_uses_the_evaluators_citation_format():
    without = evaluate_guardrails(["require_citation"], output="no source here")
    assert without[0]["code"] == "GUARDRAIL_CITATION_MISSING"

    with_link = evaluate_guardrails(
        ["require_citation"], output="see [source](https://example.com/x)",
    )
    assert with_link == []


def test_the_answer_length_bound_is_a_separate_rule():
    violations = evaluate_guardrails(
        [], output="x" * 50, max_answer_chars=10,
    )
    assert violations[0]["code"] == "GUARDRAIL_ANSWER_TOO_LONG"
    assert evaluate_guardrails([], output="x" * 5, max_answer_chars=10) == []


def test_the_guardrail_set_is_closed():
    assert set(GUARDRAILS) == {"require_tool_before_answer", "require_citation"}
    with pytest.raises(ValueError):
        from harness.schemas import AgentConfig

        AgentConfig(id="x", name="x", systemPrompt="p", guardrails=("invent",))
