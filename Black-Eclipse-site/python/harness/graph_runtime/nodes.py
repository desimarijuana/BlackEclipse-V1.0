"""Built-in node executors.

Each executor is a PURE function of (inputs, config): no clock, no randomness,
no network, no store. That is what makes a deterministic workflow reproducible —
running the same graph with the same inputs twice must produce identical
outputs. Executors that need the outside world (market data, HTTP, agents) are
declared here with ``executor=None`` and the phase that delivers them, so the
compiler refuses them with an actionable message instead of running a stub.

This module mirrors the TypeScript registry in
``src/lib/graph-studio/registry.ts`` node for node. Keep them in lockstep.
"""

from __future__ import annotations

import json
import math
import re
import time
from typing import Any

from .finance_nodes import build_finance_nodes
from .registry import (
    ConfigField,
    NodeDef,
    NodeExecContext,
    NodeRegistry,
)
from .model import ExecutionMode, PortDef, PortKind, PortType, SideEffect

_ALL = tuple(ExecutionMode)

# ── Safe formula language ────────────────────────────────────────────────────
# A tiny arithmetic language — never `eval`. Numbers, the variables `x`/`y` (and
# `value`/`index`/`acc` for the loop primitives), the constants pi/e, parentheses,
# a whitelist of functions, and comparisons/logic (`< <= > >= == != && || !`
# yielding 1.0/0.0 so the language stays numeric).

MAX_FORMULA_TOKENS = 256
_ALLOWED_FUNCTIONS = {
    "abs": abs, "min": min, "max": max, "round": round,
    "floor": math.floor, "ceil": math.ceil, "sqrt": math.sqrt,
    "log": math.log, "exp": math.exp,
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
        value = self._power()
        while True:
            token = self._peek()
            if token and token[0] == "op" and token[1] in ("*", "/", "%"):
                self._next()
                rhs = self._power()
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
        value = self._unary()
        token = self._peek()
        if token and token[0] == "op" and token[1] == "**":
            self._next()
            return value ** self._power()
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
        return self._atom()

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
                args: list[float] = []
                if self._peek() != ("op", ")"):
                    args.append(self._or())
                    while self._peek() == ("op", ","):
                        self._next()
                        args.append(self._or())
                closing = self._next()
                if closing != ("op", ")"):
                    raise FormulaError(f"missing closing parenthesis after {name}(")
                function = _ALLOWED_FUNCTIONS.get(name)
                if function is None:
                    raise FormulaError(f"unknown function {name!r}")
                try:
                    return float(function(*args))
                except (TypeError, ValueError, OverflowError) as exc:
                    raise FormulaError(f"{name}(): {exc}") from exc
            if name in self._vars:
                return float(self._vars[name])
            if name in _CONSTANTS:
                return _CONSTANTS[name]
            raise FormulaError(f"unknown name {name!r}")
        raise FormulaError(f"unexpected token {token[1]!r}")


def evaluate_formula(expression: str, variables: dict[str, float]) -> float:
    """Evaluate a bounded arithmetic expression. Raises FormulaError."""
    if len(expression) > 400:
        raise FormulaError("formula is too long")
    tokens = _tokenize(expression)
    if not tokens:
        raise FormulaError("formula is empty")
    try:
        numeric = float(_Parser(tokens, variables).parse())
    except OverflowError as exc:
        raise FormulaError("formula produced a value outside the supported range") from exc
    if not math.isfinite(numeric):
        raise FormulaError("formula produced a non-finite value")
    return numeric


# ── Executors ────────────────────────────────────────────────────────────────


def _exec_trigger(context: NodeExecContext) -> dict[str, Any]:
    seed = context.config.get("seed") or ""
    return {"start": seed if seed != "" else None}


def coerce_value(raw: Any, data_type: str) -> Any:
    """Explicit conversion by the node's declared dataType. Already-typed values
    pass through unchanged; strings are parsed; anything else is an error."""
    if data_type == "string":
        if isinstance(raw, str):
            return raw
        if isinstance(raw, (dict, list)):
            return json.dumps(raw, sort_keys=True)
        return "" if raw is None else str(raw)
    if data_type == "number":
        if isinstance(raw, bool):
            raise ValueError("a boolean is not a number")
        if isinstance(raw, (int, float)):
            return float(raw)
        try:
            return float(str(raw))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"value is not a number: {raw!r}") from exc
    if data_type == "boolean":
        if isinstance(raw, bool):
            return raw
        return str(raw).strip().lower() in ("1", "true", "yes", "on")
    if data_type in ("object", "array"):
        expected = dict if data_type == "object" else list
        if isinstance(raw, expected):
            return raw
        if isinstance(raw, str):
            try:
                parsed = json.loads(raw) if raw.strip() else expected()
            except json.JSONDecodeError as exc:
                raise ValueError(f"value is not valid JSON: {exc}") from exc
            if not isinstance(parsed, expected):
                raise ValueError(f"value is not a JSON {data_type}")
            return parsed
        raise ValueError(f"value is not a JSON {data_type}")
    raise ValueError(f"unsupported dataType {data_type!r}")


def _exec_value(context: NodeExecContext) -> dict[str, Any]:
    # "Constant / input": a wired input OVERRIDES the configured literal, and
    # either way the value is converted by the declared dataType — this is the
    # graph's explicit conversion node.
    override = context.inputs.get("in")
    raw = override if override is not None else context.config.get("value", "")
    return {"value": coerce_value(raw, context.config.get("dataType", "string"))}


def _exec_json_parse(context: NodeExecContext) -> dict[str, Any]:
    text = context.inputs.get("text")
    if not isinstance(text, str):
        raise ValueError("input 'text' must be a string")
    try:
        return {"value": json.loads(text)}
    except json.JSONDecodeError as exc:
        if context.config.get("strict", True):
            raise ValueError(f"input is not valid JSON: {exc}") from exc
        return {"value": text}


_PLACEHOLDER_RE = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z_0-9]*)\s*\}\}")


def render_template(template: str, values: dict[str, Any]) -> str:
    """Render ``{{name}}`` placeholders. Unknown names are an error, not silent."""
    missing: list[str] = []

    def replace(match: re.Match[str]) -> str:
        name = match.group(1)
        if name not in values:
            missing.append(name)
            return match.group(0)
        value = values[name]
        if isinstance(value, (dict, list)):
            return json.dumps(value, sort_keys=True)
        return "" if value is None else str(value)

    rendered = _PLACEHOLDER_RE.sub(replace, template)
    if missing:
        raise ValueError(f"template references unknown input(s): {', '.join(sorted(set(missing)))}")
    return rendered


def _exec_template(context: NodeExecContext) -> dict[str, Any]:
    template = context.config.get("template", "")
    values = {key: context.inputs.get(key) for key in ("a", "b")}
    return {"text": render_template(template, values)}


def _exec_formula(context: NodeExecContext) -> dict[str, Any]:
    expression = context.config.get("expression", "x")
    variables: dict[str, float] = {}
    for key in ("x", "y"):
        value = context.inputs.get(key)
        if value is None:
            continue
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"input {key!r} must be a number")
        variables[key] = float(value)
    return {"result": evaluate_formula(expression, variables)}


def _numeric_operand(value: Any) -> Any:
    """A comparison against a SERIES means against its latest point.

    An indicator payload is a dict of series; comparing it to a number is a
    legitimate, common intent ("is the latest z-score above 1?"), so resolve the
    operand to the series' last value instead of rejecting the node. Returns the
    input unchanged when it is not a series payload.
    """
    if isinstance(value, dict):
        last = value.get("last")
        if isinstance(last, (int, float)) and not isinstance(last, bool):
            return last
        values = value.get("values")
        if isinstance(values, list):
            for candidate in reversed(values):
                if isinstance(candidate, (int, float)) and not isinstance(candidate, bool):
                    return candidate
    return value


def _exec_condition(context: NodeExecContext) -> dict[str, Any]:
    value = _numeric_operand(context.inputs.get("value"))
    operator = context.config.get("operator", "truthy")
    compare_to = str(context.config.get("compareTo", ""))
    if operator == "truthy":
        result = bool(value)
    elif operator == "eq":
        result = _compare_equal(value, compare_to)
    elif operator == "neq":
        result = not _compare_equal(value, compare_to)
    elif operator in ("gt", "gte", "lt", "lte"):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            if isinstance(context.inputs.get("value"), dict) and "values" in (context.inputs.get("value") or {}):
                raise ValueError(
                    "the series has no computed value yet — its warm-up still needs more points"
                )
            raise ValueError("numeric comparison requires a numeric input")
        try:
            other = float(compare_to)
        except ValueError as exc:
            raise ValueError(f"comparison value {compare_to!r} is not a number") from exc
        comparisons = {
            "gt": value > other,
            "gte": value >= other,
            "lt": value < other,
            "lte": value <= other,
        }
        result = bool(comparisons[operator])
    else:
        raise ValueError(f"unsupported operator {operator!r}")
    return {"result": result, "_control": ["true"] if result else ["false"]}


def _compare_equal(value: Any, compare_to: str) -> bool:
    if isinstance(value, bool):
        return value == (compare_to.strip().lower() in ("1", "true", "yes", "on"))
    if isinstance(value, (int, float)):
        try:
            return float(value) == float(compare_to)
        except ValueError:
            return False
    if isinstance(value, (dict, list)):
        return json.dumps(value, sort_keys=True) == compare_to
    return ("" if value is None else str(value)) == compare_to


def _exec_merge(context: NodeExecContext) -> dict[str, Any]:
    a = context.inputs.get("a")
    b = context.inputs.get("b")
    if context.config.get("strategy", "first") == "object":
        return {"value": {"a": a, "b": b}}
    return {"value": a if a is not None else b}


def _exec_output(context: NodeExecContext) -> dict[str, Any]:
    return {}


# ── Control flow (Phase 4) ───────────────────────────────────────────────────
# Control ports gate EXECUTION, not values. A node fires the control outputs it
# selected via the reserved `_control` key; a node that declares control INPUTS
# runs only when an upstream fired one of them. Downstream values then follow
# ordinary dataflow: a node whose input came from a skipped gate is skipped.

MAX_LOOP_ITEMS = 10_000
MAX_WAIT_MS = 30_000
TEST_RUN_MAX_WAIT_MS = 5_000


def _as_numeric_items(value: Any, node_label: str) -> list[float]:
    if not isinstance(value, list):
        raise ValueError(f"{node_label} expects an array input")
    if len(value) > MAX_LOOP_ITEMS:
        raise ValueError(f"{node_label} is bounded to {MAX_LOOP_ITEMS} items (got {len(value)})")
    numbers: list[float] = []
    for index, item in enumerate(value):
        if isinstance(item, bool) or not isinstance(item, (int, float)):
            raise ValueError(
                f"{node_label} works on numeric arrays; item {index} is {type(item).__name__}"
            )
        numbers.append(float(item))
    return numbers


def _exec_switch(context: NodeExecContext) -> dict[str, Any]:
    value = context.inputs.get("value")
    raw_cases = str(context.config.get("cases", ""))
    names = [name.strip() for name in raw_cases.split(",") if name.strip()]
    matched = -1
    for index, name in enumerate(names):
        if _compare_equal(value, name):
            matched = index
            break
    return {
        "caseIndex": matched,
        "matched": matched >= 0,
        "_control": ["matched"] if matched >= 0 else ["default"],
    }


def _exec_map(context: NodeExecContext) -> dict[str, Any]:
    numbers = _as_numeric_items(context.inputs.get("items"), "logic.map")
    expression = context.config.get("expression", "value")
    return {"items": [evaluate_formula(expression, {"value": v, "index": float(i)}) for i, v in enumerate(numbers)]}


def _exec_filter(context: NodeExecContext) -> dict[str, Any]:
    numbers = _as_numeric_items(context.inputs.get("items"), "logic.filter")
    expression = context.config.get("expression", "value")
    kept = [
        v for i, v in enumerate(numbers)
        if evaluate_formula(expression, {"value": v, "index": float(i)}) != 0
    ]
    return {"items": kept, "dropped": len(numbers) - len(kept)}


def _exec_reduce(context: NodeExecContext) -> dict[str, Any]:
    numbers = _as_numeric_items(context.inputs.get("items"), "logic.reduce")
    expression = context.config.get("expression", "acc + value")
    try:
        accumulator = float(context.config.get("initial", 0))
    except (TypeError, ValueError) as exc:
        raise ValueError("initial must be a number") from exc
    for index, item in enumerate(numbers):
        accumulator = evaluate_formula(expression, {"acc": accumulator, "value": item, "index": float(index)})
    return {"value": accumulator}


def _exec_wait(context: NodeExecContext) -> dict[str, Any]:
    try:
        milliseconds = int(context.config.get("ms", 0))
    except (TypeError, ValueError) as exc:
        raise ValueError("ms must be a whole number of milliseconds") from exc
    if milliseconds < 0:
        raise ValueError("ms cannot be negative")
    if milliseconds > MAX_WAIT_MS:
        raise ValueError(f"ms is bounded to {MAX_WAIT_MS}")
    if milliseconds:
        time.sleep(milliseconds / 1000.0)
    return {"waitedMs": milliseconds}


def _exec_stop(context: NodeExecContext) -> dict[str, Any]:
    context.emit(str(context.config.get("message", "")) or "run stopped")
    return {"stopped": True}


def _exec_gate(context: NodeExecContext) -> dict[str, Any]:
    # The executor only runs a gate when its control input fired (see
    # `executor.GraphExecutor._control_satisfied`), so a gate is pure passthrough.
    return {"value": context.inputs.get("value")}


# ── Definitions ──────────────────────────────────────────────────────────────


def _port(port_id: str, name: str, port_type: PortType, **kwargs: Any) -> PortDef:
    return PortDef(id=port_id, name=name, type=port_type, **kwargs)


def build_default_registry() -> NodeRegistry:
    """The built-in node set. Mirrors the TS registry exactly."""
    registry = NodeRegistry()

    registry.register(NodeDef(
        type="trigger.manual", version="1.0.0", label="Manual trigger",
        category="trigger",
        outputs=(_port("start", "Start", PortType.ANY),),
        config_fields=(ConfigField("seed", "string", "", max_length=4_000),),
        allowed_modes=_ALL, timeout_ms=5_000, executor=_exec_trigger,
    ))
    registry.register(NodeDef(
        type="trigger.schedule", version="1.0.0", label="Schedule",
        category="trigger",
        outputs=(_port("start", "Start", PortType.ANY),),
        config_fields=(
            ConfigField("cron", "string", "0 9 * * 1-5", max_length=120),
            ConfigField("timezone", "string", "UTC", max_length=60),
        ),
        capabilities=("schedule.manage",),
        allowed_modes=_ALL, timeout_ms=5_000, executor=_exec_trigger,
    ))
    registry.register(NodeDef(
        type="data.value", version="1.0.0", label="Constant / input",
        category="data",
        inputs=(_port("in", "In", PortType.ANY, optional=True),),
        outputs=(_port("value", "Value", PortType.ANY),),
        config_fields=(
            ConfigField("value", "string", "", max_length=8_000),
            ConfigField("dataType", "enum", "string",
                        enum=("string", "number", "boolean", "object", "array")),
        ),
        allowed_modes=_ALL, executor=_exec_value,
    ))
    registry.register(NodeDef(
        type="data.json.parse", version="1.0.0", label="Parse JSON",
        category="data",
        inputs=(_port("text", "Text", PortType.STRING),),
        # JSON.parse may yield an object, an array, a number, a string or a
        # boolean — declaring `object` would be wrong (and would block arrays).
        outputs=(_port("value", "Value", PortType.ANY),),
        config_fields=(ConfigField("strict", "boolean", True),),
        allowed_modes=_ALL, executor=_exec_json_parse,
    ))
    registry.register(NodeDef(
        type="transform.template", version="1.0.0", label="Template",
        category="transform",
        inputs=(
            _port("a", "A", PortType.ANY, optional=True),
            _port("b", "B", PortType.ANY, optional=True),
        ),
        outputs=(_port("text", "Text", PortType.STRING),),
        config_fields=(ConfigField("template", "string", "{{a}}", max_length=4_000),),
        allowed_modes=_ALL, executor=_exec_template,
    ))
    registry.register(NodeDef(
        type="transform.formula", version="1.0.0", label="Formula",
        category="transform",
        inputs=(
            _port("x", "X", PortType.NUMBER),
            _port("y", "Y", PortType.NUMBER, optional=True),
        ),
        outputs=(_port("result", "Result", PortType.NUMBER),),
        config_fields=(ConfigField("expression", "string", "x", max_length=400),),
        capabilities=("compute.safe",),
        allowed_modes=_ALL, executor=_exec_formula,
    ))
    registry.register(NodeDef(
        type="logic.condition", version="1.0.0", label="If / else",
        category="logic",
        inputs=(_port("value", "Value", PortType.ANY),),
        outputs=(
            _port("true", "True", PortType.ANY, kind=PortKind.CONTROL),
            _port("false", "False", PortType.ANY, kind=PortKind.CONTROL),
            _port("result", "Result", PortType.BOOLEAN, optional=True),
        ),
        config_fields=(
            ConfigField("operator", "enum", "truthy",
                        enum=("eq", "neq", "gt", "gte", "lt", "lte", "truthy")),
            ConfigField("compareTo", "string", "", max_length=400),
        ),
        allowed_modes=_ALL, executor=_exec_condition,
    ))
    registry.register(NodeDef(
        type="logic.merge", version="1.0.0", label="Merge",
        category="logic",
        inputs=(
            _port("a", "A", PortType.ANY),
            _port("b", "B", PortType.ANY, optional=True),
        ),
        outputs=(_port("value", "Value", PortType.ANY),),
        config_fields=(ConfigField("strategy", "enum", "first", enum=("first", "object")),),
        allowed_modes=_ALL, executor=_exec_merge,
    ))
    registry.register(NodeDef(
        type="output.result", version="1.0.0", label="Result",
        category="output",
        inputs=(_port("value", "Value", PortType.ANY),),
        config_fields=(ConfigField("label", "string", "Result", max_length=120),),
        allowed_modes=_ALL, terminal=True, executor=_exec_output,
    ))

    # ── Control flow (Phase 4) ─────────────────────────────────────────────
    registry.register(NodeDef(
        type="flow.gate", version="1.0.0", label="Gate",
        category="logic",
        inputs=(
            _port("in", "In", PortType.ANY, kind=PortKind.CONTROL),
            _port("value", "Value", PortType.ANY, optional=True),
        ),
        outputs=(_port("value", "Value", PortType.ANY),),
        allowed_modes=_ALL, executor=_exec_gate,
        metadata={"docs": "Runs only when its control input fires — the if/else branch primitive."},
    ))
    registry.register(NodeDef(
        type="logic.switch", version="1.0.0", label="Switch",
        category="logic",
        inputs=(_port("value", "Value", PortType.ANY),),
        outputs=(
            _port("matched", "Matched", PortType.ANY, kind=PortKind.CONTROL),
            _port("default", "Default", PortType.ANY, kind=PortKind.CONTROL),
            _port("caseIndex", "Case index", PortType.NUMBER),
        ),
        config_fields=(ConfigField("cases", "string", "", max_length=400),),
        allowed_modes=_ALL, executor=_exec_switch,
    ))
    registry.register(NodeDef(
        type="logic.map", version="1.0.0", label="Map",
        category="logic",
        inputs=(_port("items", "Items", PortType.ARRAY),),
        outputs=(_port("items", "Items", PortType.ARRAY),),
        config_fields=(ConfigField("expression", "string", "value", max_length=400),),
        capabilities=("compute.safe",),
        allowed_modes=_ALL, executor=_exec_map,
    ))
    registry.register(NodeDef(
        type="logic.filter", version="1.0.0", label="Filter",
        category="logic",
        inputs=(_port("items", "Items", PortType.ARRAY),),
        outputs=(
            _port("items", "Items", PortType.ARRAY),
            _port("dropped", "Dropped", PortType.NUMBER),
        ),
        config_fields=(ConfigField("expression", "string", "value != 0", max_length=400),),
        capabilities=("compute.safe",),
        allowed_modes=_ALL, executor=_exec_filter,
    ))
    registry.register(NodeDef(
        type="logic.reduce", version="1.0.0", label="Reduce",
        category="logic",
        inputs=(_port("items", "Items", PortType.ARRAY),),
        outputs=(_port("value", "Value", PortType.NUMBER),),
        config_fields=(
            ConfigField("expression", "string", "acc + value", max_length=400),
            ConfigField("initial", "number", 0),
        ),
        capabilities=("compute.safe",),
        allowed_modes=_ALL, executor=_exec_reduce,
    ))
    registry.register(NodeDef(
        type="logic.wait", version="1.0.0", label="Wait",
        category="logic",
        inputs=(_port("in", "In", PortType.ANY, kind=PortKind.CONTROL, optional=True),),
        outputs=(_port("waitedMs", "Waited", PortType.NUMBER),),
        config_fields=(ConfigField("ms", "integer", 0, minimum=0, maximum=MAX_WAIT_MS),),
        allowed_modes=_ALL, executor=_exec_wait,
        test_run_limits={"ms": TEST_RUN_MAX_WAIT_MS},
    ))
    registry.register(NodeDef(
        type="logic.stop", version="1.0.0", label="Stop",
        category="logic",
        inputs=(_port("in", "In", PortType.ANY, kind=PortKind.CONTROL, optional=True),),
        outputs=(_port("stopped", "Stopped", PortType.BOOLEAN),),
        config_fields=(
            ConfigField("message", "string", "", max_length=400),
            ConfigField("status", "enum", "succeeded", enum=("succeeded", "failed")),
        ),
        allowed_modes=_ALL, terminal=True, stops_run=True, executor=_exec_stop,
    ))

    # Registered contracts whose executors arrive in later phases. They compile
    # to an explicit, actionable diagnostic instead of running a stub.
    registry.register(NodeDef(
        type="integration.http", version="1.0.0", label="HTTP request",
        category="integration",
        inputs=(_port("body", "Body", PortType.OBJECT, optional=True),),
        outputs=(
            _port("status", "Status", PortType.NUMBER),
            _port("body", "Body", PortType.OBJECT),
        ),
        config_fields=(
            ConfigField("url", "string", "", max_length=2_000),
            ConfigField("method", "enum", "GET", enum=("GET", "POST", "PUT", "PATCH", "DELETE")),
        ),
        capabilities=("network.egress",),
        side_effects=SideEffect.NETWORK,
        allowed_modes=_ALL, since_phase="Phase 4 (egress policy)",
    ))
    # Finance + quant nodes carry REAL executors (Phase 5). They live in
    # `finance_nodes.py` so this file stays the pure/deterministic core; the
    # same contracts are mirrored in the TS registry.
    for definition in build_finance_nodes():
        registry.register(definition)
    # Video-production node declarations (Phase 8): executor-less ON PURPOSE —
    # a render is an async Fabric job behind an effectful-node policy the graph
    # runtime does not have yet; the compiler names that honestly.
    from .video_nodes import build_video_nodes  # noqa: PLC0415

    for definition in build_video_nodes():
        registry.register(definition)
    registry.register(NodeDef(
        type="agent.research", version="1.0.0", label="Research agent",
        category="agent",
        inputs=(_port("query", "Query", PortType.STRING),),
        outputs=(
            _port("finding", "Finding", PortType.RESEARCH_FINDING),
            _port("evidence", "Evidence", PortType.EVIDENCE),
        ),
        config_fields=(
            ConfigField("agent", "string", "eclipse-agent", max_length=80),
            ConfigField("objective", "string", "", max_length=2_000),
            ConfigField("maxSteps", "integer", 8, minimum=1, maximum=32),
        ),
        capabilities=("agent.run",),
        side_effects=SideEffect.NETWORK,
        allowed_modes=_ALL, since_phase="Phase 7 (agent nodes)",
    ))
    return registry


__all__ = [
    "FormulaError",
    "evaluate_formula",
    "render_template",
    "build_default_registry",
]
