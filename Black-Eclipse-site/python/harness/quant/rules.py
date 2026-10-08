"""Deterministic rule evaluation over indicator/price arrays.

`evaluate` walks a validated `RuleNode` against an array context at a single bar
index. Any operand that is `NaN` at the required index makes its condition
`False` — the engine never acts on a value that is not yet known. `cross_above`/
`cross_below` require both the previous and current bars to be defined.
"""

from __future__ import annotations

from typing import Any, Optional

import numpy as np

from .strategy import Condition, Group, Operand, RuleNode


def resolve_operand(operand: Operand, ctx: dict[str, np.ndarray], i: int) -> Optional[float]:
    if operand.value is not None:
        return float(operand.value)
    if operand.ref is None:
        return None
    arr = ctx.get(operand.ref)
    if arr is None:
        arr = ctx.get(operand.ref.lower())
    if arr is None:
        return None
    if i < 0 or i >= len(arr):
        return None
    val = float(arr[i])
    if np.isnan(val):
        return None
    return val


def _compare(op: str, left: float, right: float) -> bool:
    if op == ">":
        return left > right
    if op == ">=":
        return left >= right
    if op == "<":
        return left < right
    if op == "<=":
        return left <= right
    if op == "==":
        return abs(left - right) < 1e-12
    if op == "!=":
        return abs(left - right) >= 1e-12
    raise ValueError(f"unsupported operator {op!r}")


def _eval_condition(cond: Condition, ctx: dict[str, np.ndarray], i: int) -> bool:
    left = resolve_operand(cond.left, ctx, i)
    if left is None:
        return False
    if cond.op in ("cross_above", "cross_below"):
        if i < 1:
            return False
        prev_left = resolve_operand(cond.left, ctx, i - 1)
        prev_right = resolve_operand(cond.right, ctx, i - 1)
        right = resolve_operand(cond.right, ctx, i)
        if right is None or prev_left is None or prev_right is None:
            return False
        if cond.op == "cross_above":
            return prev_left <= prev_right and left > right
        return prev_left >= prev_right and left < right
    right = resolve_operand(cond.right, ctx, i)
    if right is None:
        return False
    return _compare(cond.op, left, right)


def evaluate(node: RuleNode, ctx: dict[str, np.ndarray], i: int) -> bool:
    """Evaluate a rule node. Empty group with combine=all is vacuously True."""
    if isinstance(node, Condition):
        return _eval_condition(node, ctx, i)
    if not node.conditions:
        return True
    if node.combine == "any":
        return any(evaluate(child, ctx, i) for child in node.conditions)
    return all(evaluate(child, ctx, i) for child in node.conditions)


__all__ = ["evaluate", "resolve_operand"]
