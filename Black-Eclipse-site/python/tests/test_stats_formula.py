"""Safe formula language — correctness and security."""

from __future__ import annotations

import math

import numpy as np
import pytest

from harness.stats.formula import FormulaError, evaluate, parse


def test_arithmetic_and_precedence():
    out, _ = evaluate("close * 2 + 1", {"close": [1.0, 2.0, 3.0]})
    assert out.tolist() == [3.0, 5.0, 7.0]


def test_unary_and_power():
    out, _ = evaluate("-close ^ 2", {"close": [1.0, 2.0, 3.0]})
    assert out.tolist() == [-1.0, -4.0, -9.0]


def test_functions_and_lag():
    out, _ = evaluate("lag(close, 1)", {"close": [10.0, 20.0, 30.0]})
    assert np.isnan(out[0])
    assert out[1] == pytest.approx(10.0)
    assert out[2] == pytest.approx(20.0)


def test_sma_rolling():
    out, _ = evaluate("sma(close, 3)", {"close": [1.0, 2.0, 3.0, 4.0]})
    assert np.isnan(out[1])
    assert out[2] == pytest.approx(2.0)
    assert out[3] == pytest.approx(3.0)


def test_rsi_bounds():
    prices = list(np.linspace(100, 150, 80))
    out, _ = evaluate("rsi(close, 14)", {"close": prices})
    finite = out[np.isfinite(out)]
    assert finite.size > 0
    assert finite.min() >= 0.0 and finite.max() <= 100.0


def test_where_and_comparison():
    out, _ = evaluate("where(greater_than(close, 2), 1, 0)", {"close": [1.0, 2.0, 3.0]})
    assert out.tolist() == [0.0, 0.0, 1.0]


def test_correlation_function():
    out, _ = evaluate("correlation(a, b)", {"a": [1.0, 2.0, 3.0, 4.0], "b": [2.0, 4.0, 6.0, 8.0]})
    assert out[0] == pytest.approx(1.0)


def test_parse_reports_variables_and_functions():
    parsed = parse("sma(close, 20) / lag(close, 1) - 1")
    assert "close" in parsed.variables
    assert set(parsed.functions) == {"sma", "lag"}


# ── security ─────────────────────────────────────────────────────────────────

def test_unknown_function_rejected():
    with pytest.raises(FormulaError) as exc:
        parse("__import__(x)")
    assert exc.value.code == "UNKNOWN_FUNCTION"


def test_builtin_open_rejected():
    with pytest.raises(FormulaError) as exc:
        parse("open(x)")
    assert exc.value.code == "UNKNOWN_FUNCTION"


def test_attribute_access_rejected():
    with pytest.raises(FormulaError):
        parse("close.__class__")


def test_unknown_variable_rejected_at_eval():
    with pytest.raises(FormulaError) as exc:
        evaluate("close + missing_var", {"close": [1.0, 2.0]})
    assert exc.value.code == "MISSING_INPUT"


def test_empty_formula_rejected():
    with pytest.raises(FormulaError):
        parse("")


def test_overlong_formula_rejected():
    with pytest.raises(FormulaError) as exc:
        parse("close + " * 400 + "close")
    assert exc.value.code in ("TOO_LONG", "TOO_COMPLEX")


def test_log_return_domain_error():
    with pytest.raises(FormulaError) as exc:
        evaluate("log_return(close, 1)", {"close": [0.0, 10.0]})
    assert exc.value.code == "DOMAIN"


def test_no_eval_code_execution_markers_allowed():
    for bad in ["eval('1')", "exec('x=1')", "getattr(close, 'x')", "close; close"]:
        with pytest.raises(FormulaError):
            parse(bad)
