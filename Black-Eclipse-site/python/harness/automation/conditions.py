"""The deterministic condition engine (§8, §9).

A condition is a small, safe expression language over NAMED VARIABLES (e.g.
``BTC.price``). It is parsed to an AST by a hand-written recursive-descent parser
and evaluated against a supplied fact context. There is no ``eval``, no attribute
access, no function calls beyond a fixed, domain-safe helper whitelist, and no way
to reach the filesystem, network, or process.

Evaluation is THREE-VALUED (Kleene logic): a comparison whose operand is missing
is ``UNAVAILABLE`` — never silently false. This matters because a condition
trigger must never fire (or refuse to fire) on fabricated data; "we don't know"
is distinct from "no".

Edge triggering (§9): ``edge=True`` fires only on a FALSE→TRUE transition. The
previous decided result is supplied by the caller (persisted by the store), so
edge detection is restart-safe. ``UNAVAILABLE`` does not overwrite the previous
decided result, so a transient data gap cannot manufacture a re-trigger.

Operators: ``== != > >= < <= AND OR NOT IN NOT_IN CONTAINS MATCHES`` plus the
domain helpers ``crosses_above crosses_below changed increased_by decreased_by``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable, Optional

# ── Errors ───────────────────────────────────────────────────────────────────


class ConditionError(ValueError):
    """A parse/validation error with a stable code and a useful position."""

    def __init__(self, code: str, message: str, *, position: Optional[int] = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.position = position


# ── Result ───────────────────────────────────────────────────────────────────

TRUE = "true"
FALSE = "false"
UNAVAILABLE = "unavailable"

# Domain-safe helper functions (the ONLY callable identifiers).
HELPERS = frozenset({
    "crosses_above", "crosses_below", "changed", "increased_by", "decreased_by",
})
KEYWORDS = frozenset({"AND", "OR", "NOT", "IN", "NOT_IN", "CONTAINS", "MATCHES", "TRUE", "FALSE"})
COMPARATORS = frozenset({"==", "!=", ">", ">=", "<", "<="})

_VAR_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z0-9_]+)*$")
_MAX_PATTERN_LEN = 200


@dataclass(frozen=True)
class EvalResult:
    """The result of evaluating a condition."""

    state: str                       # TRUE | FALSE | UNAVAILABLE
    reason: Optional[str] = None     # why UNAVAILABLE, when it is

    @property
    def truthy(self) -> bool:
        return self.state == TRUE


# ── Tokenizer ────────────────────────────────────────────────────────────────

_TOKEN_RE = re.compile(
    r"""
    (?P<ws>\s+)
  | (?P<num>\d+(?:\.\d+)?)
  | (?P<str>'[^']*'|"[^"]*")
  | (?P<op>>=|<=|==|!=|>|<|[()\[\],+\-*/])
  | (?P<ident>[A-Za-z_][A-Za-z0-9_.]*)
    """,
    re.VERBOSE,
)


@dataclass(frozen=True)
class _Token:
    kind: str
    value: Any
    pos: int


def _tokenize(expression: str) -> list[_Token]:
    tokens: list[_Token] = []
    pos = 0
    length = len(expression)
    while pos < length:
        match = _TOKEN_RE.match(expression, pos)
        if match is None:
            raise ConditionError(
                "INVALID_SYNTAX",
                f"unexpected character {expression[pos]!r} at position {pos}",
                position=pos,
            )
        pos = match.end()
        kind = match.lastgroup or ""
        if kind == "ws":
            continue
        text = match.group()
        if kind == "num":
            value: Any = float(text) if "." in text else int(text)
        elif kind == "str":
            value = text[1:-1]
        else:
            value = text
        tokens.append(_Token(kind=kind, value=value, pos=match.start()))
    return tokens


# ── Parser (recursive descent → tuple AST) ───────────────────────────────────


class _Parser:
    def __init__(self, tokens: list[_Token]) -> None:
        self._tokens = tokens
        self._i = 0

    def _peek(self) -> Optional[_Token]:
        return self._tokens[self._i] if self._i < len(self._tokens) else None

    def _next(self) -> _Token:
        token = self._peek()
        if token is None:
            raise ConditionError("INVALID_SYNTAX", "unexpected end of expression")
        self._i += 1
        return token

    def _accept_keyword(self, word: str) -> bool:
        token = self._peek()
        if token is not None and token.kind == "ident" and str(token.value).upper() == word:
            self._i += 1
            return True
        return False

    def _expect(self, value: str) -> None:
        token = self._peek()
        if token is None or token.value != value:
            raise ConditionError("INVALID_SYNTAX", f"expected {value!r}")
        self._i += 1

    def parse(self) -> Any:
        node = self._or()
        if self._peek() is not None:
            token = self._peek()
            raise ConditionError(
                "INVALID_SYNTAX", f"unexpected token {token.value!r}", position=token.pos
            )
        return node

    def _or(self) -> Any:
        node = self._and()
        while self._accept_keyword("OR"):
            node = ("binary", "OR", node, self._and())
        return node

    def _and(self) -> Any:
        node = self._not()
        while self._accept_keyword("AND"):
            node = ("binary", "AND", node, self._not())
        return node

    def _not(self) -> Any:
        if self._accept_keyword("NOT"):
            return ("unary", "NOT", self._not())
        return self._comparison()

    def _comparison(self) -> Any:
        left = self._additive()
        token = self._peek()
        if token is None:
            return left
        if token.kind == "op" and token.value in COMPARATORS:
            self._next()
            return ("binary", token.value, left, self._additive())
        if token.kind == "ident":
            upper = str(token.value).upper()
            if upper in ("IN", "CONTAINS", "MATCHES", "NOT_IN"):
                self._next()
                op = "NOT_IN" if upper == "NOT_IN" else upper
                if op == "NOT_IN" and self._accept_keyword("IN"):
                    pass
                return ("binary", op, left, self._additive())
        return left

    def _additive(self) -> Any:
        node = self._term()
        token = self._peek()
        while token is not None and token.kind == "op" and token.value in ("+", "-"):
            self._next()
            node = ("binary", token.value, node, self._term())
            token = self._peek()
        return node

    def _term(self) -> Any:
        node = self._factor()
        token = self._peek()
        while token is not None and token.kind == "op" and token.value in ("*", "/"):
            self._next()
            node = ("binary", token.value, node, self._factor())
            token = self._peek()
        return node

    def _factor(self) -> Any:
        token = self._next()
        if token.kind == "num":
            return ("num", token.value)
        if token.kind == "str":
            return ("str", token.value)
        if token.kind == "op" and token.value == "(":
            node = self._or()
            self._expect(")")
            return node
        if token.kind == "op" and token.value == "[":
            items: list[Any] = []
            if not (self._peek() and self._peek().value == "]"):
                items.append(self._or())
                while self._peek() and self._peek().value == ",":
                    self._next()
                    items.append(self._or())
            self._expect("]")
            return ("list", items)
        if token.kind == "ident":
            text = str(token.value)
            upper = text.upper()
            if upper == "TRUE":
                return ("bool", True)
            if upper == "FALSE":
                return ("bool", False)
            if self._peek() and self._peek().value == "(":
                self._next()
                args: list[Any] = []
                if not (self._peek() and self._peek().value == ")"):
                    args.append(self._or())
                    while self._peek() and self._peek().value == ",":
                        self._next()
                        args.append(self._or())
                self._expect(")")
                if text not in HELPERS:
                    raise ConditionError(
                        "UNKNOWN_FUNCTION", f"{text!r} is not a supported function",
                        position=token.pos,
                    )
                return ("call", text, args)
            if not _VAR_RE.match(text):
                raise ConditionError("INVALID_VARIABLE", f"invalid variable {text!r}", position=token.pos)
            return ("var", text)
        raise ConditionError("INVALID_SYNTAX", f"unexpected token {token.value!r}", position=token.pos)


def parse_condition(expression: str) -> Any:
    """Parse a condition expression to an AST, or raise ``ConditionError``."""
    if expression is None or not str(expression).strip():
        raise ConditionError("EMPTY_EXPRESSION", "the condition is empty")
    return _Parser(_tokenize(str(expression))).parse()


def extract_variables(expression: str) -> list[str]:
    """Every variable path referenced, in first-seen order. Raises on bad syntax."""
    ast = parse_condition(expression)
    seen: list[str] = []

    def walk(node: Any) -> None:
        if not isinstance(node, tuple):
            return
        if node[0] == "var":
            if node[1] not in seen:
                seen.append(node[1])
            return
        for child in node[1:]:
            if isinstance(child, list):
                for item in child:
                    walk(item)
            else:
                walk(child)

    walk(ast)
    return seen


# ── Evaluation context ───────────────────────────────────────────────────────


@dataclass
class ConditionContext:
    """The facts a condition evaluates against.

    ``values`` maps a variable path to its current value. ``history`` maps a path
    to its previous value (for the domain helpers). A path absent from ``values``
    is UNAVAILABLE.
    """

    values: dict[str, Any]
    history: dict[str, Any] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.history is None:
            self.history = {}

    def value(self, path: str) -> Any:
        return self.values.get(path, _MISSING)

    def previous(self, path: str) -> Any:
        return self.history.get(path, _MISSING)


class _Missing:
    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return "<missing>"


_MISSING = _Missing()


def _numeric(value: Any) -> Optional[float]:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _eval_node(node: Any, ctx: ConditionContext) -> tuple[str, Any]:
    """Evaluate to ``(kind, value)`` where kind ∈ {value, unavailable}."""
    if not isinstance(node, tuple):
        return ("unavailable", None)
    head = node[0]
    if head == "num" or head == "str" or head == "bool":
        return ("value", node[1])
    if head == "var":
        value = ctx.value(node[1])
        if value is _MISSING:
            return ("unavailable", node[1])
        return ("value", value)
    if head == "list":
        items = []
        for item in node[1]:
            kind, value = _eval_node(item, ctx)
            if kind == "unavailable":
                return ("unavailable", value)
            items.append(value)
        return ("value", items)
    if head == "unary":
        kind, value = _eval_node(node[2], ctx)
        if kind == "unavailable":
            return ("unavailable", value)
        return ("value", not _as_bool(value))
    if head == "binary":
        return _eval_binary(node[1], node[2], node[3], ctx)
    if head == "call":
        return _eval_call(node[1], node[2], ctx)
    return ("unavailable", None)


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in ("true", "1", "yes")
    return bool(value)


def _eval_binary(op: str, left_node: Any, right_node: Any, ctx: ConditionContext) -> tuple[str, Any]:
    if op == "AND" or op == "OR":
        lk, lv = _eval_node(left_node, ctx)
        if op == "AND" and lk == "value" and not _as_bool(lv):
            return ("value", False)
        if op == "OR" and lk == "value" and _as_bool(lv):
            return ("value", True)
        rk, rv = _eval_node(right_node, ctx)
        if op == "AND":
            if rk == "value" and not _as_bool(rv):
                return ("value", False)
            if lk == "unavailable" or rk == "unavailable":
                return ("unavailable", None)
            return ("value", _as_bool(lv) and _as_bool(rv))
        if rk == "value" and _as_bool(rv):
            return ("value", True)
        if lk == "unavailable" or rk == "unavailable":
            return ("unavailable", None)
        return ("value", _as_bool(lv) or _as_bool(rv))

    lk, lv = _eval_node(left_node, ctx)
    rk, rv = _eval_node(right_node, ctx)
    if lk == "unavailable" or rk == "unavailable":
        return ("unavailable", None)

    if op in ("+", "-", "*", "/"):
        ln, rn = _numeric(lv), _numeric(rv)
        if ln is None or rn is None:
            return ("unavailable", None)
        if op == "+":
            return ("value", ln + rn)
        if op == "-":
            return ("value", ln - rn)
        if op == "*":
            return ("value", ln * rn)
        if rn == 0:
            return ("unavailable", None)
        return ("value", ln / rn)

    if op == "==":
        return ("value", _equals(lv, rv))
    if op == "!=":
        return ("value", not _equals(lv, rv))
    if op in (">", ">=", "<", "<="):
        ln, rn = _numeric(lv), _numeric(rv)
        if ln is None or rn is None:
            if isinstance(lv, str) and isinstance(rv, str):
                ln, rn = lv, rv  # type: ignore[assignment]
            else:
                return ("unavailable", None)
        return ("value", {">": ln > rn, ">=": ln >= rn, "<": ln < rn, "<=": ln <= rn}[op])
    if op in ("IN", "NOT_IN"):
        if isinstance(rv, (list, tuple, set)):
            member = lv in rv
        elif isinstance(rv, str):
            member = str(lv) in rv
        else:
            return ("unavailable", None)
        return ("value", member if op == "IN" else not member)
    if op == "CONTAINS":
        if isinstance(lv, str):
            return ("value", str(rv) in lv)
        if isinstance(lv, (list, tuple, set)):
            return ("value", rv in lv)
        return ("unavailable", None)
    if op == "MATCHES":
        if not isinstance(rv, str) or len(rv) > _MAX_PATTERN_LEN:
            return ("unavailable", None)
        try:
            return ("value", re.search(rv, str(lv)) is not None)
        except re.error:
            return ("unavailable", None)
    return ("unavailable", None)


def _equals(a: Any, b: Any) -> bool:
    an, bn = _numeric(a), _numeric(b)
    if an is not None and bn is not None:
        return an == bn
    return a == b


def _eval_call(name: str, args: list[Any], ctx: ConditionContext) -> tuple[str, Any]:
    def resolved(index: int) -> tuple[str, Any]:
        return _eval_node(args[index], ctx)

    if name == "changed":
        if len(args) != 1 or args[0][0] != "var":
            return ("unavailable", None)
        path = args[0][1]
        current, previous = ctx.value(path), ctx.previous(path)
        if current is _MISSING or previous is _MISSING:
            return ("unavailable", None)
        return ("value", not _equals(current, previous))

    if name in ("crosses_above", "crosses_below"):
        if len(args) != 2 or args[0][0] != "var":
            return ("unavailable", None)
        path = args[0][1]
        current, previous = ctx.value(path), ctx.previous(path)
        if current is _MISSING or previous is _MISSING:
            return ("unavailable", None)
        _tk, threshold = resolved(1)
        if threshold is _MISSING:
            return ("unavailable", None)
        cn, pn, tn = _numeric(current), _numeric(previous), _numeric(threshold)
        if cn is None or pn is None or tn is None:
            return ("unavailable", None)
        if name == "crosses_above":
            return ("value", pn <= tn < cn)
        return ("value", pn >= tn > cn)

    if name in ("increased_by", "decreased_by"):
        if len(args) != 2 or args[0][0] != "var":
            return ("unavailable", None)
        path = args[0][1]
        current, previous = ctx.value(path), ctx.previous(path)
        if current is _MISSING or previous is _MISSING:
            return ("unavailable", None)
        _tk, pct = resolved(1)
        cn, pn, pn_pct = _numeric(current), _numeric(previous), _numeric(pct)
        if cn is None or pn is None or pn_pct is None or pn == 0:
            return ("unavailable", None)
        change_pct = (cn - pn) / pn * 100.0
        if name == "increased_by":
            return ("value", change_pct >= pn_pct)
        return ("value", change_pct <= -pn_pct)

    return ("unavailable", None)


def evaluate(expression: str, ctx: ConditionContext) -> EvalResult:
    """Evaluate a condition against a context. Never raises for data gaps."""
    try:
        ast = parse_condition(expression)
    except ConditionError as exc:
        return EvalResult(state=UNAVAILABLE, reason=exc.message)
    kind, value = _eval_node(ast, ctx)
    if kind == "unavailable":
        return EvalResult(state=UNAVAILABLE, reason="a referenced value is unavailable")
    return EvalResult(state=TRUE if _as_bool(value) else FALSE)


def evaluate_ast(ast: Any, ctx: ConditionContext) -> EvalResult:
    kind, value = _eval_node(ast, ctx)
    if kind == "unavailable":
        return EvalResult(state=UNAVAILABLE, reason="a referenced value is unavailable")
    return EvalResult(state=TRUE if _as_bool(value) else FALSE)


def decide_edge(current: str, previous: Optional[str]) -> bool:
    """Whether a FALSE→TRUE transition occurred (§9).

    ``UNAVAILABLE`` never counts as a transition and never overwrites the
    previous decided result (the caller keeps the old value in that case).
    """
    if current != TRUE:
        return False
    return previous != TRUE


def validate_condition(expression: str, *, known_variables: Optional[Iterable[str]] = None) -> list[str]:
    """Validate syntax + referenced variables; return the variable list.

    Raises ``ConditionError`` with a useful message when invalid or when a
    referenced variable is not in ``known_variables`` (when supplied).
    """
    variables = extract_variables(expression)
    if known_variables is not None:
        known = set(known_variables)
        unknown = [v for v in variables if v not in known]
        if unknown:
            raise ConditionError(
                "UNKNOWN_VARIABLE", f"unknown variable {unknown[0]!r}"
            )
    return variables


__all__ = [
    "ConditionContext",
    "ConditionError",
    "EvalResult",
    "FALSE",
    "HELPERS",
    "TRUE",
    "UNAVAILABLE",
    "decide_edge",
    "evaluate",
    "evaluate_ast",
    "extract_variables",
    "parse_condition",
    "validate_condition",
]
