"""The Python half of the safe scalar evaluator (parity with TS).

The evaluator behind declarative `simulation` outputs exists twice — TypeScript
(`src/lib/response/evaluate.ts`, used by the renderer) and here — because the
renderer is TS and the harness validates server-side. To stop the two drifting,
both run the SAME fixture corpus
(`src/lib/response/__fixtures__/evaluate-cases.json`); see
`python/tests/test_response_eval.py`. Same grammar, same whitelist, same
edge behaviour (division by zero, unknown name, parse error → `None`).

It reuses the tested tokenizer/parser of the stats formula engine
(`stats/formula.py`) and supplies a scalar evaluator + a closed function
whitelist — no `eval`, no `exec`, no imports, no attribute access, no I/O.
"""

from __future__ import annotations

import math
from typing import Any, Optional

from .stats.formula import FormulaError, _Parser, _tokenize

# The closed scalar function whitelist, mirroring `EVAL_FUNCTIONS` in the TS
# evaluator. `round` is half-away-from-zero (NOT Python's banker's rounding) so
# the two implementations agree.
_MAX_ARGS = 64


def _round_half_away(value: float, digits: float = 0) -> float:
    factor = 10.0 ** int(digits)
    return math.copysign(math.floor(abs(value) * factor + 0.5) / factor, value)


_FUNCTIONS = {
    "abs": (1, 1, lambda a: abs(a[0])),
    "sqrt": (1, 1, lambda a: math.sqrt(a[0])),
    "floor": (1, 1, lambda a: float(math.floor(a[0]))),
    "ceil": (1, 1, lambda a: float(math.ceil(a[0]))),
    "sign": (1, 1, lambda a: float((a[0] > 0) - (a[0] < 0))),
    "round": (1, 2, lambda a: _round_half_away(a[0], a[1] if len(a) > 1 else 0)),
    "clamp": (3, 3, lambda a: min(max(a[0], a[1]), a[2])),
    "pow": (2, 2, lambda a: math.pow(a[0], a[1])),
    "min": (1, _MAX_ARGS, lambda a: min(a)),
    "max": (1, _MAX_ARGS, lambda a: max(a)),
    "sum": (1, _MAX_ARGS, lambda a: sum(a)),
    "avg": (1, _MAX_ARGS, lambda a: sum(a) / len(a)),
    "if": (3, 3, lambda a: a[1] if a[0] != 0 else a[2]),
}

EVAL_FUNCTIONS = sorted(_FUNCTIONS)


def _parse(expr: str) -> tuple:
    if not isinstance(expr, str) or not expr.strip():
        raise FormulaError("EMPTY", "expression is empty")
    return _Parser(_tokenize(expr)).parse()


def _collect(node: tuple, variables: set, functions: set) -> None:
    kind = node[0]
    if kind == "var":
        variables.add(node[1])
    elif kind == "call":
        functions.add(node[1])
        for arg in node[2]:
            _collect(arg, variables, functions)
    elif kind == "bin":
        _collect(node[2], variables, functions)
        _collect(node[3], variables, functions)
    elif kind == "unary":
        _collect(node[2], variables, functions)


def validate_expression(expr: str, known_variables: Optional[set] = None) -> dict:
    """Parse + check known functions/variables. Never raises."""
    try:
        ast = _parse(expr)
    except Exception as exc:  # noqa: BLE001 - a bad expression is a real outcome
        return {"ok": False, "error": str(exc), "variables": [], "functions": []}
    variables: set = set()
    functions: set = set()
    _collect(ast, variables, functions)
    unknown_fn = sorted(functions - set(_FUNCTIONS))
    if unknown_fn:
        return {"ok": False, "error": f"unknown function(s): {unknown_fn}", "variables": sorted(variables), "functions": sorted(functions)}
    if known_variables is not None:
        unknown_var = sorted(variables - set(known_variables))
        if unknown_var:
            return {"ok": False, "error": f"unknown variable(s): {unknown_var}", "variables": sorted(variables), "functions": sorted(functions)}
    return {"ok": True, "variables": sorted(variables), "functions": sorted(functions)}


def _eval(node: tuple, variables: dict) -> Optional[float]:
    kind = node[0]
    if kind == "num":
        value = float(node[1])
        return value if math.isfinite(value) else None
    if kind == "var":
        value = variables.get(node[1])
        if not isinstance(value, (int, float)) or not math.isfinite(float(value)):
            return None
        return float(value)
    if kind == "unary":
        value = _eval(node[2], variables)
        if value is None:
            return None
        return -value if node[1] == "-" else value
    if kind == "bin":
        a = _eval(node[2], variables)
        b = _eval(node[3], variables)
        if a is None or b is None:
            return None
        op = node[1]
        if op == "+":
            out = a + b
        elif op == "-":
            out = a - b
        elif op == "*":
            out = a * b
        elif op == "/":
            if b == 0:
                return None
            out = a / b
        elif op == "^":
            try:
                out = math.pow(a, b)
            except (ValueError, OverflowError):
                return None
        elif op == "<":
            return 1.0 if a < b else 0.0
        elif op == ">":
            return 1.0 if a > b else 0.0
        elif op == "<=":
            return 1.0 if a <= b else 0.0
        elif op == ">=":
            return 1.0 if a >= b else 0.0
        elif op == "==":
            return 1.0 if a == b else 0.0
        elif op == "!=":
            return 1.0 if a != b else 0.0
        else:
            return None
        return out if math.isfinite(out) else None
    if kind == "call":
        spec = _FUNCTIONS.get(node[1])
        if spec is None:
            return None
        lo, hi, fn = spec
        args = [_eval(a, variables) for a in node[2]]
        if len(args) < lo or len(args) > hi or any(a is None for a in args):
            return None
        try:
            out = float(fn(args))
        except (ValueError, TypeError, ZeroDivisionError, OverflowError):
            return None
        return out if math.isfinite(out) else None
    return None


def evaluate_expression(expr: str, variables: dict) -> Optional[float]:
    """Evaluate over scalar variables. Returns None for any UNAVAILABLE case."""
    try:
        ast = _parse(expr)
    except Exception:  # noqa: BLE001 - a parse failure is UNAVAILABLE, never a raise
        return None
    try:
        return _eval(ast, variables)
    except Exception:  # noqa: BLE001 - the compute boundary never raises
        return None


__all__ = ["EVAL_FUNCTIONS", "evaluate_expression", "validate_expression"]
