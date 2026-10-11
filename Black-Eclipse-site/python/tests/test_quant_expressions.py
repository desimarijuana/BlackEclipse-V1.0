"""Expression DSL: arithmetic, min/max, negation, abs, and causal lag."""

from __future__ import annotations

import numpy as np
import pytest

from harness.quant import rules as R
from harness.quant import strategy as S


def _spec_with_condition(left, op, right):
    return S.parse_strategy({
        "strategy": {"id": "expr", "name": "Expr", "version": "1.0.0"},
        "universe": {"symbols": ["X"]},
        "indicators": [{"id": "ema", "type": "ema", "params": {"period": 3}}],
        "rules": {"entry": {"long": {"conditions": [
            {"left": left, "op": op, "right": right}]}}, "exit": {}},
        "position_sizing": {"type": "percent_equity", "value": 50},
    })


def test_arithmetic_expression_evaluates():
    ctx = {"close": np.array([1.0, 2.0, 3.0]), "ema": np.array([2.5, 2.5, 2.5])}
    cond = S.Condition(
        left=S.Operand(expr=S.BinaryExpr(op="*", left=S.Operand(ref="close"),
                                         right=S.Operand(value=2.0))),
        op=">", right=S.Operand(ref="ema"))
    assert R.evaluate(cond, ctx, 0) is False   # 2 > 2.5 no
    assert R.evaluate(cond, ctx, 1) is True    # 4 > 2.5 yes
    assert R.evaluate(cond, ctx, 2) is True    # 6 > 2.5 yes


def test_min_max_neg_abs_and_division_by_zero():
    ctx = {"a": np.array([3.0]), "b": np.array([7.0])}
    def operand(op, l, r=None, unary=False):
        if unary:
            return S.Operand(expr=S.UnaryExpr(op=op, operand=l))
        return S.Operand(expr=S.BinaryExpr(op=op, left=l, right=r))
    assert R.resolve_operand(operand("min", S.Operand(ref="a"), S.Operand(ref="b")), ctx, 0) == 3.0
    assert R.resolve_operand(operand("max", S.Operand(ref="a"), S.Operand(ref="b")), ctx, 0) == 7.0
    assert R.resolve_operand(operand("neg", S.Operand(ref="a"), unary=True), ctx, 0) == -3.0
    assert R.resolve_operand(operand("abs", S.Operand(value=-4.0), unary=True), ctx, 0) == 4.0
    # division by zero → no value (condition becomes False, never inf)
    assert R.resolve_operand(operand("/", S.Operand(ref="a"), S.Operand(value=0.0)), ctx, 0) is None


def test_lag_is_causal():
    ctx = {"close": np.array([10.0, 11.0, 12.0])}
    lag = S.Operand(expr=S.LagExpr(operand=S.Operand(ref="close"), bars=1))
    assert R.resolve_operand(lag, ctx, 0) is None
    assert R.resolve_operand(lag, ctx, 1) == 10.0
    assert R.resolve_operand(lag, ctx, 2) == 11.0


def test_expression_in_a_full_spec_compiles_and_validates():
    spec = _spec_with_condition(
        {"expr": {"op": "*", "left": {"ref": "close"}, "right": {"value": 2}}},
        ">", {"ref": "ema"})
    assert not S.errors_only(S.validate_strategy(spec))
    text = None
    # The describe helper renders the expression.
    from harness.quant.copilot import describe_rules
    text = describe_rules(spec)["entry"]["long"]
    assert "*" in text and "close" in text


def test_unknown_reference_inside_expression_is_flagged():
    spec = _spec_with_condition(
        {"expr": {"op": "+", "left": {"ref": "nope"}, "right": {"value": 1}}},
        ">", {"value": 0})
    issues = S.validate_strategy(spec)
    assert any(i.code == "UNKNOWN_REFERENCE" for i in issues)


def test_negative_lag_is_rejected():
    spec = _spec_with_condition(
        {"expr": {"op": "lag", "operand": {"ref": "close"}, "bars": 0}},
        ">", {"value": 0})
    assert any(i.code == "BAD_LAG" for i in S.validate_strategy(spec))
