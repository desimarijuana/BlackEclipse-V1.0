"""Text transform nodes: the safe formula language and the template renderer.

These are the two nodes users type into, so the contract they rely on is worth
pinning precisely: whitespace is not a syntax error, money rounds half-up,
`if()` never evaluates the branch it does not take, and a template never turns a
missing value into a silent blank.
"""

from __future__ import annotations

import time

import pytest

from harness.graph_runtime.model import ExecutionMode
from harness.graph_runtime.nodes import (
    FormulaError,
    build_default_registry,
    evaluate_formula,
    render_template,
)
from harness.graph_runtime.registry import NodeExecContext

REGISTRY = build_default_registry()


def _exec(node_type: str, inputs: dict, config: dict | None = None):
    definition = REGISTRY.get(node_type)
    assert definition is not None and definition.executor is not None
    return definition.executor(NodeExecContext(
        node_id=node_type, run_id="run", mode=ExecutionMode.RESEARCH,
        inputs=inputs, config=config or {},
    ))


# ── formula ─────────────────────────────────────────────────────────────────

def test_surrounding_whitespace_is_not_a_syntax_error():
    assert evaluate_formula("  x + 1  ", {"x": 2.0}) == 3.0
    assert evaluate_formula("\tx\t", {"x": 2.0}) == 2.0


def test_rounding_is_half_up_not_bankers():
    assert evaluate_formula("round(2.5)", {}) == 3.0
    assert evaluate_formula("round(3.5)", {}) == 4.0
    assert evaluate_formula("round(0.125, 2)", {}) == 0.13


def test_power_binds_tighter_than_unary_minus():
    assert evaluate_formula("-2 ** 2", {}) == -4.0
    assert evaluate_formula("2 ** -2", {}) == 0.25
    assert evaluate_formula("(-2) ** 2", {}) == 4.0


def test_if_is_lazy_so_the_unused_branch_cannot_fail():
    assert evaluate_formula("if(b != 0, a / b, 0)", {"a": 10.0, "b": 0.0}) == 0.0
    assert evaluate_formula("if(b != 0, a / b, 0)", {"a": 10.0, "b": 2.0}) == 5.0


def test_finance_guard_functions():
    assert evaluate_formula("div(1, 0)", {}) == 0.0
    assert evaluate_formula("div(1, 0, -1)", {}) == -1.0
    assert evaluate_formula("nz(0, 7)", {}) == 7.0
    assert evaluate_formula("nz(3, 7)", {}) == 3.0
    assert evaluate_formula("clamp(120, 0, 100)", {}) == 100.0
    assert evaluate_formula("sign(-4)", {}) == -1.0


def test_unknown_names_and_functions_explain_themselves():
    with pytest.raises(FormulaError, match=r"available:.*\bx\b"):
        evaluate_formula("close * 2", {"x": 1.0})
    with pytest.raises(FormulaError, match="available:"):
        evaluate_formula("wibble(1)", {})


def test_formula_arity_is_checked():
    with pytest.raises(FormulaError, match="takes 3"):
        evaluate_formula("if(1, 2)", {})
    with pytest.raises(FormulaError, match="takes 3 argument"):
        evaluate_formula("clamp(1, 2)", {})


def test_division_by_zero_stays_an_error_without_div():
    with pytest.raises(FormulaError, match="division by zero"):
        evaluate_formula("1 / 0", {})


def test_formula_node_accepts_a_series_payload():
    result = _exec("transform.formula", {"x": {"last": 3.0, "values": [1.0, 2.0, 3.0]}}, {"expression": "x * 2"})
    assert result["result"] == 6.0
    assert result["_control"] == ["done"]


def test_formula_node_refuses_a_series_with_no_value_yet():
    with pytest.raises(ValueError, match="warm-up"):
        _exec("transform.formula", {"x": {"values": [None, None]}}, {"expression": "x"})


# ── template ────────────────────────────────────────────────────────────────

def test_template_reads_a_dotted_path():
    assert render_template("{{a.symbol}} @ {{a.price}}", {"a": {"symbol": "AAPL", "price": 190.5}}) == "AAPL @ 190.5"


def test_template_number_formats():
    assert render_template("{{a:.2f}}", {"a": 1 / 3}) == "0.33"
    assert render_template("{{a:,.0f}}", {"a": 1234567}) == "1,234,567"


def test_template_date_formats():
    assert render_template("{{a:date}}", {"a": "2026-10-31T15:00:00Z"}) == "2026-10-31"
    assert render_template("{{a:date:%d/%m/%Y}}", {"a": "2026-10-31"}) == "31/10/2026"


def test_template_optional_placeholder_renders_blank():
    assert render_template("[{{a?}}]", {"a": None}) == "[]"
    assert render_template("[{{a.missing?}}]", {"a": {}}) == "[]"


def test_a_null_required_placeholder_is_an_error_not_a_blank():
    with pytest.raises(ValueError, match="has no value"):
        render_template("price={{a}}", {"a": None})
    with pytest.raises(ValueError, match="has no value"):
        render_template("price={{a.missing}}", {"a": {"symbol": "AAPL"}})


def test_unknown_placeholder_names_the_available_inputs():
    with pytest.raises(ValueError, match="unknown input"):
        render_template("{{c}}", {"a": 1, "b": 2})


def test_bad_format_specs_fail_honestly():
    with pytest.raises(ValueError, match="needs a number"):
        render_template("{{a:.2f}}", {"a": "not a number"})
    with pytest.raises(ValueError, match="not an ISO date"):
        render_template("{{a:date}}", {"a": "soon"})


def test_template_node_renders_and_fires_its_control_output():
    result = _exec("transform.template", {"a": {"symbol": "AAPL"}, "b": 2},
                   {"template": "{{a.symbol}} x{{b}}"})
    assert result["text"] == "AAPL x2"
    assert result["_control"] == ["done"]


def test_template_renders_one_block_per_row():
    rows = [{"symbol": "AAPL", "close": 190.5}, {"symbol": "MSFT", "close": 410}]
    text = render_template("{{#each a}}{{symbol}} {{close:.2f}}\n{{/each}}", {"a": rows})
    assert text == "AAPL 190.50\nMSFT 410.00\n"


def test_template_block_exposes_index_and_this_for_scalars():
    assert render_template("[{{#each a}}{{index}}:{{this}} {{/each}}]", {"a": ["x", "y"]}) == "[0:x 1:y ]"
    rows = [{"symbol": "AAPL"}, {"symbol": "MSFT"}]
    assert render_template("{{#each a}}{{index}}{{symbol}}{{/each}}", {"a": rows}) == "0AAPL1MSFT"


def test_template_block_an_empty_or_null_array_renders_nothing():
    assert render_template("[{{#each a}}x{{/each}}]", {"a": []}) == "[]"
    assert render_template("[{{#each a}}x{{/each}}]", {"a": None}) == "[]"


def test_template_blocks_nest():
    rows = [{"symbol": "A", "bars": [{"c": 1}, {"c": 2}]}]
    text = render_template(
        "{{#each a}}{{symbol}}:{{#each bars}}{{c}}{{/each}};{{/each}}",
        {"a": rows},
    )
    assert text == "A:12;"


def test_template_block_errors_are_explicit():
    with pytest.raises(ValueError, match="not closed"):
        render_template("{{#each a}}x", {"a": []})
    with pytest.raises(ValueError, match="without a matching"):
        render_template("x{{/each}}", {})
    with pytest.raises(ValueError, match="needs an array"):
        render_template("{{#each a}}x{{/each}}", {"a": {"not": "a list"}})


def test_a_backslash_escapes_a_literal_brace():
    assert render_template(r"\{{a}} is text", {"a": 1}) == "{{a}} is text"


def test_template_row_blocks_are_bounded():
    rows = [{"i": index} for index in range(10_001)]
    with pytest.raises(ValueError, match="bounded to 10000 rows"):
        render_template("{{#each a}}{{i}}{{/each}}", {"a": rows})


def test_nested_blocks_hit_the_output_cap_while_rendering():
    """The cap must stop the loop, not just reject the finished string."""
    rows = [{"v": 1} for _ in range(2_000)]
    started = time.monotonic()
    with pytest.raises(ValueError, match="exceeds 50000"):
        render_template("{{#each a}}{{#each a}}x{{/each}}{{/each}}", {"a": rows})
    assert time.monotonic() - started < 2.0
