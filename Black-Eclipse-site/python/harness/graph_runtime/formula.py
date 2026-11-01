"""The bounded, safe formula language used by the graph nodes.

Evaluate arithmetic over a numeric scope WITHOUT ``eval``/``exec``: a hand-written
tokenizer and recursive-descent parser, a fixed function table, a hard token and
length bound, and a float result. `if()` is evaluated lazily so the branch that is
not taken is never computed (which is what makes `if(b != 0, a / b, 0)` safe).

Shared by `transform.formula`, `logic.map`, `logic.filter`, `logic.reduce` and
`flow.while`. Re-exported by ``nodes.py`` for back-compatibility.
"""

from __future__ import annotations

import math
import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Callable

# ── Safe formula language ────────────────────────────────────────────────────
# A tiny arithmetic language — never `eval`. Numbers, the variables `x`/`y` (and
# `value`/`index`/`acc` for the loop primitives), the constants pi/e, parentheses,
# a whitelist of functions, and comparisons/logic (`< <= > >= == != && || !`
# yielding 1.0/0.0 so the language stays numeric).

MAX_FORMULA_TOKENS = 256
MAX_FORMULA_LENGTH = 400
MAX_ROUND_DIGITS = 10


def _round_half_up(value: float, digits: float = 0) -> float:
    """Half-up rounding, not Python's banker's rounding.

    Money math is the whole point of this language: ``round(2.5)`` must be 3,
    not 2. ``Decimal(repr())`` avoids reintroducing binary noise before rounding.
    """
    try:
        places = int(digits)
    except (TypeError, ValueError) as exc:
        raise ValueError("round() digits must be a whole number") from exc
    if places < 0 or places > MAX_ROUND_DIGITS:
        raise ValueError(f"round() digits must be between 0 and {MAX_ROUND_DIGITS}")
    try:
        quantum = Decimal(1).scaleb(-places)
        return float(Decimal(repr(float(value))).quantize(quantum, rounding=ROUND_HALF_UP))
    except (InvalidOperation, ValueError):  # pragma: no cover - extreme magnitudes
        return float(value)


def _sign(value: float) -> float:
    return 0.0 if value == 0 else (1.0 if value > 0 else -1.0)


def _clamp(value: float, low: float, high: float) -> float:
    if low > high:
        raise ValueError("clamp() lower bound is greater than its upper bound")
    return min(max(value, low), high)


def _safe_div(numerator: float, denominator: float, fallback: float = 0.0) -> float:
    return fallback if denominator == 0 else numerator / denominator


def _nz(value: float, fallback: float = 0.0) -> float:
    """Zero-or-fallback guard ("null zero"): the financial ratio idiom."""
    return fallback if value == 0 else value


# name -> (callable, min args, max args). `if` is deliberately absent: it is
# evaluated lazily in the parser so the branch that is not taken is never
# computed (that is what makes `if(b != 0, a / b, 0)` safe).
_FUNCTIONS: dict[str, tuple[Callable[..., float], int, int]] = {
    "abs": (abs, 1, 1),
    "min": (min, 1, 16),
    "max": (max, 1, 16),
    "round": (_round_half_up, 1, 2),
    "floor": (math.floor, 1, 1),
    "ceil": (math.ceil, 1, 1),
    "sqrt": (math.sqrt, 1, 1),
    "log": (math.log, 1, 2),
    "log10": (math.log10, 1, 1),
    "exp": (math.exp, 1, 1),
    "pow": (pow, 2, 2),
    "sign": (_sign, 1, 1),
    "clamp": (_clamp, 3, 3),
    "div": (_safe_div, 2, 3),
    "nz": (_nz, 1, 2),
}
_CONSTANTS = {"pi": math.pi, "e": math.e}

_TOKEN_RE = re.compile(
    r"\s*(?:(\d+\.?\d*|\.\d+)|([A-Za-z_][A-Za-z_0-9]*)"
    r"|(\*\*|<=|>=|==|!=|&&|\|\||[+\-*/%(),<>!]))"
)


class FormulaError(ValueError):
    """A formula could not be parsed or evaluated. Never a crash—always a
    node-level failure the user can read."""


def _tokenize(expression: str) -> list[tuple[str, str]]:
    tokens: list[tuple[str, str]] = []
    pos = 0
    while pos < len(expression):
        match = _TOKEN_RE.match(expression, pos)
        if not match:
            raise FormulaError(f"unexpected character at position {pos}")
        number, name, symbol = match.group(1), match.group(2), match.group(3)
        if number:
            tokens.append(("number", number))
        elif name:
            tokens.append(("name", name))
        else:
            tokens.append(("op", symbol))
        pos = match.end()
        if len(tokens) > MAX_FORMULA_TOKENS:
            raise FormulaError("formula is too long")
    return tokens


class _Parser:
    def __init__(self, tokens: list[tuple[str, str]], variables: dict[str, float]) -> None:
        self._tokens = tokens
        self._pos = 0
        self._vars = variables

    def _peek(self) -> tuple[str, str] | None:
        return self._tokens[self._pos] if self._pos < len(self._tokens) else None

    def _next(self) -> tuple[str, str]:
        token = self._peek()
        if token is None:
            raise FormulaError("unexpected end of formula")
        self._pos += 1
        return token

    def parse(self) -> float:
        value = self._or()
        if self._peek() is not None:
            raise FormulaError(f"unexpected {self._peek()[1]!r}")
        return value

    # Comparisons and logic yield 1.0 / 0.0 so the language stays numeric
    # (a filter keeps an item when its expression is non-zero).

    def _or(self) -> float:
        value = self._and()
        while self._peek() == ("op", "||"):
            self._next()
            rhs = self._and()
            value = 1.0 if (value != 0 or rhs != 0) else 0.0
        return value

    def _and(self) -> float:
        value = self._comparison()
        while self._peek() == ("op", "&&"):
            self._next()
            rhs = self._comparison()
            value = 1.0 if (value != 0 and rhs != 0) else 0.0
        return value

    def _comparison(self) -> float:
        value = self._expr()
        while True:
            token = self._peek()
            if not (token and token[0] == "op" and token[1] in ("<", "<=", ">", ">=", "==", "!=")):
                return value
            self._next()
            rhs = self._expr()
            operations = {
                "<": value < rhs,
                "<=": value <= rhs,
                ">": value > rhs,
                ">=": value >= rhs,
                "==": value == rhs,
                "!=": value != rhs,
            }
            value = 1.0 if operations[token[1]] else 0.0

    def _expr(self) -> float:
        value = self._term()
        while True:
            token = self._peek()
            if token and token[0] == "op" and token[1] in ("+", "-"):
                self._next()
                rhs = self._term()
                value = value + rhs if token[1] == "+" else value - rhs
            else:
                return value

    def _term(self) -> float:
        value = self._unary()
        while True:
            token = self._peek()
            if token and token[0] == "op" and token[1] in ("*", "/", "%"):
                self._next()
                rhs = self._unary()
                if token[1] == "*":
                    value *= rhs
                elif token[1] == "/":
                    if rhs == 0:
                        raise FormulaError("division by zero")
                    value /= rhs
                else:
                    if rhs == 0:
                        raise FormulaError("modulo by zero")
                    value %= rhs
            else:
                return value

    def _power(self) -> float:
        # `**` binds tighter than unary minus, so `-2 ** 2` is -4 as in maths.
        value = self._atom()
        if self._peek() == ("op", "**"):
            self._next()
            return value ** self._unary()
        return value

    def _unary(self) -> float:
        token = self._peek()
        if token and token[0] == "op" and token[1] in ("-", "+", "!"):
            self._next()
            value = self._unary()
            if token[1] == "-":
                return -value
            if token[1] == "!":
                return 0.0 if value != 0 else 1.0
            return value
        return self._power()

    def _collect_args(self) -> list[list[tuple[str, str]]]:
        """Split the argument tokens of a call, positioned just after `(`.

        Args are returned as token spans so a callee can decide whether to
        evaluate them (this is how `if()` stays lazy).
        """
        depth = 0
        args: list[list[tuple[str, str]]] = [[]]
        while True:
            token = self._next()
            if token == ("op", "("):
                depth += 1
            elif token == ("op", ")"):
                if depth == 0:
                    if len(args) == 1 and not args[0]:
                        return []
                    return args
                depth -= 1
            elif token == ("op", ",") and depth == 0:
                args.append([])
                continue
            args[-1].append(token)

    def _sub(self, tokens: list[tuple[str, str]]) -> float:
        if not tokens:
            raise FormulaError("missing function argument")
        return _Parser(tokens, self._vars).parse()

    def _atom(self) -> float:
        token = self._next()
        if token[0] == "number":
            return float(token[1])
        if token[0] == "op" and token[1] == "(":
            value = self._or()
            closing = self._next()
            if closing != ("op", ")"):
                raise FormulaError("missing closing parenthesis")
            return value
        if token[0] == "name":
            name = token[1]
            if self._peek() == ("op", "("):
                self._next()
                spans = self._collect_args()
                if name == "if":
                    if len(spans) != 3:
                        raise FormulaError("if() takes 3 arguments: if(condition, whenTrue, whenFalse)")
                    condition = self._sub(spans[0])
                    return self._sub(spans[1] if condition != 0 else spans[2])
                entry = _FUNCTIONS.get(name)
                if entry is None:
                    available = ", ".join(sorted(["if", *_FUNCTIONS]))
                    raise FormulaError(f"unknown function {name!r} (available: {available})")
                function, low, high = entry
                if not low <= len(spans) <= high:
                    expected = f"{low}" if low == high else f"{low} to {high}"
                    raise FormulaError(f"{name}() takes {expected} argument(s), got {len(spans)}")
                args = [self._sub(span) for span in spans]
                try:
                    return float(function(*args))
                except FormulaError:
                    raise
                except (TypeError, ValueError, OverflowError, InvalidOperation, ZeroDivisionError) as exc:
                    raise FormulaError(f"{name}(): {exc}") from exc
            if name in self._vars:
                return float(self._vars[name])
            if name in _CONSTANTS:
                return _CONSTANTS[name]
            known = ", ".join(sorted({*self._vars, *_CONSTANTS}))
            raise FormulaError(f"unknown name {name!r} (available: {known})")
        raise FormulaError(f"unexpected token {token[1]!r}")


def evaluate_formula(expression: str, variables: dict[str, float]) -> float:
    """Evaluate a bounded arithmetic expression. Raises FormulaError."""
    if not isinstance(expression, str):
        raise FormulaError("formula must be text")
    expression = expression.strip()
    if len(expression) > MAX_FORMULA_LENGTH:
        raise FormulaError("formula is too long")
    tokens = _tokenize(expression)
    if not tokens:
        raise FormulaError("formula is empty")
    try:
        numeric = float(_Parser(tokens, variables).parse())
    except OverflowError as exc:
        raise FormulaError("formula produced a value outside the supported range") from exc
    except TypeError as exc:
        raise FormulaError("formula produced a non-real value") from exc
    if not math.isfinite(numeric):
        raise FormulaError("formula produced a non-finite value")
    return numeric



__all__ = ["FormulaError", "evaluate_formula"]
