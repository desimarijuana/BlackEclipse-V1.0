"""Structured agent nodes: one bounded model call, contract checked by the node."""

from __future__ import annotations

import pytest

from harness.graph_runtime.agent_structured import normalize_labels, validate_extraction
from harness.graph_runtime.agent_structured_nodes import set_structured_runner
from harness.graph_runtime.model import ExecutionMode
from harness.graph_runtime.nodes import build_default_registry
from harness.graph_runtime.registry import NodeExecContext

REGISTRY = build_default_registry()


def _exec(node_type: str, config: dict, inputs: dict):
    definition = REGISTRY.get(node_type)
    assert definition is not None and definition.executor is not None
    return definition.executor(NodeExecContext(
        node_id=node_type, run_id="run", mode=ExecutionMode.RESEARCH,
        inputs=inputs, config=config,
    ))


@pytest.fixture()
def model():
    state: dict = {"result": {}}

    def runner(context, op, args):
        state["op"] = op
        state["args"] = args
        state["model"] = context.model_settings
        return state["result"]

    set_structured_runner(runner)
    try:
        yield state
    finally:
        set_structured_runner(None)


# ── classify ─────────────────────────────────────────────────────────────────

def test_classify_returns_the_declared_label_case_insensitively(model):
    model["result"] = {"label": "bull", "confidence": 0.82, "scores": {"bull": 0.82, "bear": 0.18}}
    result = _exec("agent.classify", {"labels": "Bull, Bear"}, {"text": "margins expanding"})
    assert result == {"label": "Bull", "confidence": 0.82, "scores": {"bull": 0.82, "bear": 0.18}}
    assert model["op"] == "classify"
    assert model["args"]["labels"] == ["Bull", "Bear"]


def test_classify_rejects_a_label_outside_the_declared_set(model):
    model["result"] = {"label": "sideways", "confidence": 0.5}
    with pytest.raises(ValueError, match="not one of the declared labels"):
        _exec("agent.classify", {"labels": "Bull, Bear"}, {"text": "hmm"})


def test_classify_requires_two_labels(model):
    model["result"] = {"label": "Bull", "confidence": 0.5}
    with pytest.raises(ValueError, match="at least two labels"):
        _exec("agent.classify", {"labels": "Bull"}, {"text": "hmm"})


def test_classify_requires_text(model):
    with pytest.raises(ValueError, match="empty text"):
        _exec("agent.classify", {"labels": "Bull, Bear"}, {"text": "   "})
    with pytest.raises(ValueError, match="needs a text input"):
        _exec("agent.classify", {"labels": "Bull, Bear"}, {})


def test_classify_rejects_an_out_of_range_confidence(model):
    model["result"] = {"label": "Bull", "confidence": 1.4}
    with pytest.raises(ValueError, match="confidence in 0..1"):
        _exec("agent.classify", {"labels": "Bull, Bear"}, {"text": "hmm"})


def test_classify_needs_a_bound_runner():
    set_structured_runner(None)
    with pytest.raises(ValueError, match="not configured"):
        _exec("agent.classify", {"labels": "Bull, Bear"}, {"text": "hmm"})


def test_normalize_labels_dedupes_case_insensitively_and_bounds():
    assert normalize_labels(" Bull , bear , BULL ,, ") == ["Bull", "bear"]
    with pytest.raises(ValueError, match="at most"):
        normalize_labels(",".join(f"l{i}" for i in range(31)))
    with pytest.raises(ValueError, match="exceeds"):
        normalize_labels("x" * 81)


# ── extract ──────────────────────────────────────────────────────────────────

SCHEMA = {
    "type": "object",
    "required": ["symbol", "rating"],
    "properties": {"symbol": {"type": "string"}, "rating": {"type": "string"}},
}


def test_extract_marks_a_matching_object_valid(model):
    model["result"] = {"data": {"symbol": "AAPL", "rating": "hold"}}
    result = _exec("agent.extract", {"schemaJson": '{"required": ["symbol", "rating"]}'},
                   {"text": "AAPL is a hold", "schema": SCHEMA})
    assert result["valid"] is True
    assert result["data"] == {"symbol": "AAPL", "rating": "hold"}
    assert result["raw"] == '{"symbol": "AAPL", "rating": "hold"}'
    assert model["args"]["schema"] == SCHEMA


def test_extract_reports_a_shape_mismatch_instead_of_pretending(model):
    model["result"] = {"data": {"symbol": "AAPL"}}
    result = _exec("agent.extract", {}, {"text": "AAPL", "schema": SCHEMA})
    assert result["valid"] is False
    assert result["data"] == {"symbol": "AAPL"}


def test_extract_rejects_bad_schema_json_and_non_object_data(model):
    with pytest.raises(ValueError, match="not valid JSON"):
        _exec("agent.extract", {"schemaJson": "{not json"}, {"text": "AAPL"})
    model["result"] = {"data": ["AAPL"]}
    with pytest.raises(ValueError, match="no `data` object"):
        _exec("agent.extract", {}, {"text": "AAPL"})


def test_validate_extraction_checks_array_items_and_types():
    schema = {
        "required": ["tags"],
        "properties": {"tags": {"type": "array", "items": {"type": "string"}}},
    }
    ok, issues = validate_extraction({"tags": ["a", "b"]}, schema)
    assert ok is True and issues == []
    ok, issues = validate_extraction({"tags": ["a", 2]}, schema)
    assert ok is False and "not string" in issues[0]
    # No schema means nothing was checked, which is reported as valid.
    assert validate_extraction({"anything": 1}, {}) == (True, [])


# ── summarize ────────────────────────────────────────────────────────────────

def test_summarize_returns_a_summary_and_key_points(model):
    model["result"] = {"summary": "Margins improved.", "keyPoints": ["Revenue up", "Costs flat"]}
    result = _exec("agent.summarize", {"maxWords": 120, "style": "bullets"}, {"text": "long text"})
    assert result == {"summary": "Margins improved.", "keyPoints": ["Revenue up", "Costs flat"]}
    assert model["args"]["maxWords"] == 120
    assert model["args"]["style"] == "bullets"


def test_summarize_accepts_an_array_and_clamps_max_words(model):
    model["result"] = {"summary": "Two items.", "keyPoints": []}
    result = _exec("agent.summarize", {"maxWords": 1}, {"text": ["a", "b"]})
    assert result["summary"] == "Two items."
    # Never below the documented floor.
    assert model["args"]["maxWords"] == 10


def test_summarize_fails_by_name_on_empty_input(model):
    model["result"] = {"summary": "x"}
    with pytest.raises(ValueError, match="empty text"):
        _exec("agent.summarize", {}, {"text": "   "})
    with pytest.raises(ValueError, match="empty collection"):
        _exec("agent.summarize", {}, {"text": []})
    with pytest.raises(ValueError, match="string, array or object"):
        _exec("agent.summarize", {}, {"text": 42})


def test_summarize_rejects_an_unknown_style(model):
    model["result"] = {"summary": "x"}
    with pytest.raises(ValueError, match="style"):
        _exec("agent.summarize", {"style": "haiku"}, {"text": "a"})


# ── critique ─────────────────────────────────────────────────────────────────

def test_critique_returns_verdict_issues_and_score(model):
    model["result"] = {"verdict": "weak", "score": 0.4, "issues": ["no source for the margin claim"]}
    result = _exec("agent.critique", {}, {
        "finding": {"text": "AAPL is expensive"},
        "evidence": {"evidence": []},
        "rubric": "must cite a filing",
    })
    assert result == {"verdict": "weak", "issues": ["no source for the margin claim"], "score": 0.4}
    assert model["op"] == "critique"
    assert model["args"]["finding"] == "AAPL is expensive"
    assert model["args"]["rubric"] == "must cite a filing"


def test_critique_rejects_a_verdict_outside_the_set(model):
    model["result"] = {"verdict": "probably fine"}
    with pytest.raises(ValueError, match="expected one of"):
        _exec("agent.critique", {}, {"finding": "x"})


def test_critique_score_is_null_when_the_model_omits_it(model):
    model["result"] = {"verdict": "supported"}
    result = _exec("agent.critique", {}, {"finding": "x"})
    assert result["score"] is None
    assert result["issues"] == []


def test_critique_rejects_an_out_of_range_score(model):
    model["result"] = {"verdict": "supported", "score": 2}
    with pytest.raises(ValueError, match="score outside 0..1"):
        _exec("agent.critique", {}, {"finding": "x"})


def test_critique_accepts_a_plain_string_finding_and_requires_one():
    set_structured_runner(lambda _context, _op, _args: {"verdict": "supported"})
    try:
        assert _exec("agent.critique", {}, {"finding": "a bare string"})["verdict"] == "supported"
        with pytest.raises(ValueError, match="needs a finding"):
            _exec("agent.critique", {}, {})
        with pytest.raises(ValueError, match="empty finding"):
            _exec("agent.critique", {}, {"finding": {"text": "   "}})
    finally:
        set_structured_runner(None)
