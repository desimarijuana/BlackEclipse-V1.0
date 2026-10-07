"""`browser_exec` — sandboxed, programmatic multi-step browser control.

The agent can express a short program of browser operations and run it in one
call. This is NOT arbitrary code execution: there is no Python `eval`/`exec` and
no host access. A program is either

  * a JSON list of steps (`[{"op": "navigate", "url": ...}, ...]`), or
  * a restricted Python-subset source string parsed with `ast`, where every
    statement must be a call of the form `browser.<op>(...)` with literal or
    simple-keyword arguments. Any other construct (import, attribute access
    outside `browser`, assignment to non-browser names, loops, comprehensions,
    f-strings, `eval`) is REFUSED by the AST walk, never executed.

The operation vocabulary is closed and maps 1:1 to the session's own methods, so
the sandbox surface IS the browser API and nothing else. Every program is bounded
by max steps, a wall-clock timeout and a cancellation check, and it records a
trace.
"""

from __future__ import annotations

import ast
import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from .errors import BrowserExecutionError

DEFAULT_MAX_STEPS = 50
HARD_MAX_STEPS = 200
DEFAULT_TIMEOUT_S = 120
MAX_TIMEOUT_S = 900

# The closed operation vocabulary. Each maps to a session coroutine. A step may
# not call anything else.
OPS: dict[str, dict[str, Any]] = {
    "navigate": {"method": "navigate", "required": ("url",), "args": ("url", "wait_until")},
    "back": {"method": "go_back", "args": ()},
    "forward": {"method": "go_forward", "args": ()},
    "reload": {"method": "reload", "args": ()},
    "snapshot": {"method": "snapshot", "args": ()},
    "extract": {"method": "extract", "args": ()},
    "click": {"method": "click", "required": ("target",), "args": ("target",)},
    "type": {"method": "type_text", "required": ("target", "text"), "args": ("target", "text", "submit")},
    "fill": {"method": "type_text", "required": ("target", "text"), "args": ("target", "text")},
    "select": {"method": "select", "required": ("target", "value"), "args": ("target", "value")},
    "check": {"method": "check", "required": ("target",), "args": ("target", "checked")},
    "press": {"method": "press", "required": ("key",), "args": ("key", "target")},
    "hover": {"method": "hover", "required": ("target",), "args": ("target",)},
    "scroll": {"method": "scroll", "args": ("dy", "dx", "selector")},
    "wait": {"method": "wait", "args": ("ms",)},
    "wait_for_text": {"method": "wait_for_text", "required": ("text",), "args": ("text",)},
    "wait_for_url": {"method": "wait_for_url", "required": ("pattern",), "args": ("pattern",)},
    "wait_for_element": {"method": "wait_for_selector", "required": ("target",), "args": ("target", "state")},
    "wait_for_navigation": {"method": "wait_for_navigation", "args": ()},
    "wait_for_network": {"method": "wait_for_network", "args": ()},
    "wait_for_download": {"method": "wait_for_download", "args": ()},
    "download": {"method": "download", "required": ("target",), "args": ("target",)},
    "upload": {"method": "upload", "required": ("target", "files"), "args": ("target", "files")},
    "screenshot": {"method": "screenshot", "args": ("full_page",)},
    "text": {"method": "get_text", "args": ()},
    "links": {"method": "get_links", "args": ()},
    "evaluate": {"method": "evaluate", "required": ("expression",), "args": ("expression",)},
}

# Browser methods that must NOT be reachable from a program (lifecycle, vault,
# raw CDP, arbitrary storage writes). The op table already excludes them; this is
# a belt-and-braces assertion so a future edit cannot silently widen the surface.
FORBIDDEN_OPS = frozenset({
    "close", "cdp", "request_human", "pause", "resume", "set_cookie",
    "permissions", "upload_raw",
})


@dataclass
class ExecStep:
    op: str
    args: dict[str, Any] = field(default_factory=dict)


@dataclass
class ExecResult:
    success: bool
    steps_run: int
    results: list[dict[str, Any]] = field(default_factory=list)
    error: Optional[dict[str, Any]] = None
    duration_ms: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "stepsRun": self.steps_run,
            "results": self.results,
            "error": self.error,
            "durationMs": self.duration_ms,
        }


def parse_program(program: Any) -> list[ExecStep]:
    """Parse a program (JSON steps or restricted Python source) into ExecSteps."""
    if program is None:
        raise BrowserExecutionError("No browser program was given.", action="exec", code="BROWSER_EXEC_INVALID")
    if isinstance(program, (list, tuple)):
        return [_step_from_mapping(item) for item in program]
    if isinstance(program, dict):
        steps = program.get("steps") if isinstance(program.get("steps"), list) else [program]
        return [_step_from_mapping(item) for item in steps]
    if isinstance(program, str):
        return _parse_source(program)
    raise BrowserExecutionError("The browser program isn't in a supported form.", action="exec", code="BROWSER_EXEC_INVALID")


def _step_from_mapping(item: Any) -> ExecStep:
    if not isinstance(item, dict):
        raise BrowserExecutionError("Each browser step must be an object.", action="exec", code="BROWSER_EXEC_INVALID")
    op = str(item.get("op") or item.get("action") or "").strip()
    if op not in OPS or op in FORBIDDEN_OPS:
        raise BrowserExecutionError(
            f"Eclipse doesn't recognise the browser step {op!r}.",
            action="exec", code="BROWSER_EXEC_UNKNOWN_OP", metadata={"op": op},
        )
    args = {k: v for k, v in item.items() if k not in ("op", "action")}
    _validate_args(op, args)
    return ExecStep(op=op, args=args)


def _validate_args(op: str, args: dict[str, Any]) -> None:
    spec = OPS[op]
    for required in spec.get("required", ()):
        if required not in args or args[required] in (None, ""):
            raise BrowserExecutionError(
                f"The {op!r} step needs a {required!r}.",
                action="exec", code="BROWSER_EXEC_INVALID", metadata={"op": op, "missing": required},
            )
    allowed = set(spec.get("args", ()))
    for key in args:
        if key not in allowed:
            raise BrowserExecutionError(
                f"The {op!r} step doesn't accept {key!r}.",
                action="exec", code="BROWSER_EXEC_INVALID", metadata={"op": op, "extra": key},
            )


def _parse_source(source: str) -> list[ExecStep]:
    """Translate restricted `browser.<op>(...)` calls into steps, REFUSING the rest.

    The AST walk is the security boundary: any node that is not a top-level
    expression statement of a single call on the `browser` object with literal
    arguments is rejected. No import, loop, comprehension, f-string, attribute
    chain, subscript or name reference is permitted.
    """
    try:
        tree = ast.parse(source, mode="exec")
    except SyntaxError as exc:
        raise BrowserExecutionError(
            "The browser program has a syntax error.", action="exec",
            code="BROWSER_EXEC_SYNTAX", metadata={"error": str(exc)[:200]},
        ) from exc

    steps: list[ExecStep] = []
    for node in tree.body:
        if isinstance(node, ast.Expr):
            call = node.value
        else:
            call = None
        if not isinstance(call, ast.Call):
            raise BrowserExecutionError(
                "A browser program may only contain operations like browser.click(...).",
                action="exec", code="BROWSER_EXEC_FORBIDDEN",
            )
        func = call.func
        if not (isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name)
                and func.value.id in ("browser", "page", "session")):
            raise BrowserExecutionError(
                "A browser program may only call the browser's own operations.",
                action="exec", code="BROWSER_EXEC_FORBIDDEN",
            )
        op = func.attr
        if op not in OPS or op in FORBIDDEN_OPS:
            raise BrowserExecutionError(
                f"Eclipse doesn't recognise the browser operation {op!r}.",
                action="exec", code="BROWSER_EXEC_UNKNOWN_OP", metadata={"op": op},
            )
        args, kwargs = _literal_args(call)
        merged = {**args, **kwargs}
        _validate_args(op, merged)
        steps.append(ExecStep(op=op, args=merged))
    if not steps:
        raise BrowserExecutionError("The browser program is empty.", action="exec", code="BROWSER_EXEC_INVALID")
    return steps


def _literal_args(call: ast.Call) -> tuple[dict[str, Any], dict[str, Any]]:
    spec = OPS.get(getattr(call.func, "attr", ""), {})
    names = list(spec.get("args", ()))
    positional: dict[str, Any] = {}
    for index, arg in enumerate(call.args):
        if index >= len(names):
            raise BrowserExecutionError(
                "That browser operation got too many values.", action="exec", code="BROWSER_EXEC_INVALID",
            )
        positional[names[index]] = _literal_value(arg)
    kwargs: dict[str, Any] = {}
    for keyword in call.keywords:
        if keyword.arg is None:
            raise BrowserExecutionError("A browser operation can't take **kwargs.", action="exec", code="BROWSER_EXEC_FORBIDDEN")
        kwargs[keyword.arg] = _literal_value(keyword.value)
    return positional, kwargs


_ALLOWED_LITERAL_NODES = (
    ast.Constant, ast.List, ast.Tuple, ast.Dict,
)


def _literal_value(node: ast.AST) -> Any:
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, (ast.List, ast.Tuple)):
        return [_literal_value(el) for el in node.elts]
    if isinstance(node, ast.Dict):
        return {_literal_value(k): _literal_value(v) for k, v in zip(node.keys, node.values) if k is not None}
    raise BrowserExecutionError(
        "A browser program may only use fixed values (no variables or expressions).",
        action="exec", code="BROWSER_EXEC_FORBIDDEN",
    )


async def run_program(
    session: Any,
    steps: list[ExecStep],
    *,
    max_steps: int = DEFAULT_MAX_STEPS,
    timeout_s: int = DEFAULT_TIMEOUT_S,
    cancel: Optional[Any] = None,
    trace: Any = None,
) -> ExecResult:
    """Execute a parsed program against a live session, bounded and cancellable."""
    started = time.monotonic()
    cap = max(1, min(int(max_steps), HARD_MAX_STEPS))
    deadline = started + max(1, min(int(timeout_s), MAX_TIMEOUT_S))
    results: list[dict[str, Any]] = []
    for index, step in enumerate(steps[:cap]):
        if time.monotonic() > deadline:
            return ExecResult(
                success=False, steps_run=index, results=results, duration_ms=_ms(started),
                error={"code": "BROWSER_EXEC_TIMEOUT", "message": "The browser program ran out of time."},
            )
        if cancel is not None:
            is_set = getattr(cancel, "is_set", None)
            if callable(is_set) and is_set():
                return ExecResult(
                    success=False, steps_run=index, results=results, duration_ms=_ms(started),
                    error={"code": "CANCELLED", "message": "The run was cancelled."},
                )
        trace_step = trace.next_step(f"exec.{step.op}", step.args, provider=session.provider.id) if trace else None
        try:
            outcome = await _run_step(session, step)
        except Exception as exc:  # noqa: BLE001 - a step failure is data, not a crash
            from .errors import BrowserError  # noqa: PLC0415

            error = exc.to_dict() if isinstance(exc, BrowserError) else {"code": "BROWSER_EXEC_STEP_FAILED", "message": str(exc)[:300]}
            if trace_step is not None:
                trace_step.error = error
                trace.finish_step(trace_step)
            results.append({"op": step.op, "ok": False, "error": error})
            return ExecResult(success=False, steps_run=index + 1, results=results, duration_ms=_ms(started), error=error)
        if trace_step is not None:
            trace_step.observation = _bounded_observation(outcome)
            trace.finish_step(trace_step)
        results.append({"op": step.op, "ok": True, "result": _bounded_observation(outcome)})
    if len(steps) > cap:
        results.append({"note": f"Only the first {cap} of {len(steps)} steps ran."})
    return ExecResult(success=True, steps_run=min(len(steps), cap), results=results, duration_ms=_ms(started))


async def _run_step(session: Any, step: ExecStep) -> Any:
    import inspect  # noqa: PLC0415

    spec = OPS[step.op]
    method = getattr(session, spec["method"], None)
    if method is None:
        raise BrowserExecutionError(
            f"Eclipse can't run the {step.op!r} step right now.", action="exec", code="BROWSER_EXEC_UNSUPPORTED",
        )
    kwargs = {k: v for k, v in step.args.items() if k in spec.get("args", ())}
    # The op vocabulary uses the model-friendly `target`; the session methods name
    # that parameter `raw_target` (and `type` maps to `type_text` via `method`).
    # Translate to the method's real parameter names so a step can never fail on
    # a naming mismatch.
    try:
        params = inspect.signature(method).parameters
        if "target" in kwargs and "target" not in params and "raw_target" in params:
            kwargs["raw_target"] = kwargs.pop("target")
    except (TypeError, ValueError):
        pass
    result = method(**kwargs)
    if asyncio.iscoroutine(result):
        return await result
    return result


def _bounded_observation(value: Any) -> Any:
    """Bound a step result for the model and the trace (never a full DOM)."""
    if value is None:
        return None
    if hasattr(value, "summary"):
        return value.summary()
    if isinstance(value, str):
        return value[:2_000]
    if isinstance(value, dict):
        return {k: _bounded_observation(v) for k, v in list(value.items())[:30]}
    if isinstance(value, (list, tuple)):
        return [_bounded_observation(v) for v in list(value)[:30]]
    if isinstance(value, (int, float, bool)):
        return value
    return str(value)[:500]


def _ms(started: float) -> int:
    return int((time.monotonic() - started) * 1000)


__all__ = [
    "DEFAULT_MAX_STEPS",
    "ExecResult",
    "ExecStep",
    "FORBIDDEN_OPS",
    "HARD_MAX_STEPS",
    "OPS",
    "parse_program",
    "run_program",
]
