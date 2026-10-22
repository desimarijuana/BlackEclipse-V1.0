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
    assert set(GUARDRAILS) == {
        "require_tool_before_answer", "require_citation",
        "no_fabricated_url", "require_source_for_numbers",
    }
    with pytest.raises(ValueError):
        from harness.schemas import AgentConfig

        AgentConfig(id="x", name="x", systemPrompt="p", guardrails=("invent",))


def test_a_url_no_tool_returned_is_a_fabrication():
    violations = evaluate_guardrails(
        ["no_fabricated_url"],
        output="See https://example.com/made-up for details.",
        tool_texts=["the tool said 42.0 and nothing else"],
    )
    assert violations[0]["code"] == "GUARDRAIL_FABRICATED_URL"
    assert "made-up" in violations[0]["detail"]

    clean = evaluate_guardrails(
        ["no_fabricated_url"],
        output="See https://example.com/real for details.",
        tool_texts=["the tool returned https://example.com/real"],
    )
    assert clean == []


def test_a_number_without_a_source_is_refused():
    violations = evaluate_guardrails(
        ["require_source_for_numbers"],
        output="The revenue is 120.0.",
        tool_texts=["revenue 120.0"],
    )
    assert violations[0]["code"] == "GUARDRAIL_NUMBER_WITHOUT_SOURCE"

    sourced = evaluate_guardrails(
        ["require_source_for_numbers"],
        output="The revenue is 120.0 ([source](https://example.com/x)).",
        tool_texts=["revenue 120.0"],
    )
    assert sourced == []

    honest = evaluate_guardrails(
        ["require_source_for_numbers"],
        output="The revenue is unavailable; the service did not return it.",
        tool_texts=["error"],
    )
    assert honest == []
