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
import os
import re
import time
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from datetime import date, datetime, timezone
from typing import Any, Callable, Optional

from . import http_client
from .agent_nodes import build_agent_nodes
from .dataset_nodes import build_dataset_nodes
from .finance_nodes import build_finance_nodes
from .quant_nodes import build_quant_nodes
from .research_nodes import build_research_nodes
from .table_nodes import build_table_nodes
from .values import MISSING, coerce_number, resolve_path
from .trading_nodes import build_trading_nodes
from .registry import (
    ConfigField,
    NodeDef,
    NodeExecContext,
    NodeRegistry,
)
from .model import ExecutionMode, PortDef, PortKind, PortType, SideEffect
# Re-exported: these used to live here and are still imported from `nodes`.
from .formula import FormulaError, evaluate_formula  # noqa: F401
from .template import render_template  # noqa: F401

_ALL = tuple(ExecutionMode)


# ── Executors ────────────────────────────────────────────────────────────────


def _exec_trigger(context: NodeExecContext) -> dict[str, Any]:
    """Emit the trigger's Start value.

    A trigger is zero-config: Start is the run's input (a manual "run with
    input", a webhook body, or a parent subworkflow's input) or null.

    Legacy only: workflows authored before the zero-config trigger may still
    carry `payload`/`payloadType`/`seed` in their stored config. Those keys are
    no longer declared (so the editor never shows them), but they are still
    honoured here so an existing saved workflow does not silently change
    behaviour. New graphs should put defaults in data.value/set_variables.
    """
    if context.run_input is not None:
        return {"start": context.run_input}

    payload = context.config.get("payload")
    if payload is not None and payload != "":
        payload_type = context.config.get("payloadType") or "auto"
        if payload_type in ("auto", ""):
            return {"start": payload}
        return {"start": coerce_value(payload, payload_type)}

    seed = context.config.get("seed") or ""
    return {"start": seed if seed != "" else None}


def _exec_webhook_trigger(context: NodeExecContext) -> dict[str, Any]:
    """Emit a verified inbound webhook.

    The front door has already authenticated the request and verified the
    signature/replay window; the runtime only receives the bounded context. The
    body is also `start`, so a webhook workflow reads it exactly like a manual
    trigger's run input.
    """
    ctx = context.trigger_context or {}
    body = ctx.get("body")
    if body is None:
        body = context.run_input
    # A trigger that is executed without an inbound context (the editor's
    # single-node test, or a manual run that contains this node) still has to
    # satisfy the declared datetime port. The receive time is the only sensible
    # value; the real webhook path always supplies the front door's timestamp.
    received_at = str(ctx.get("receivedAt") or "").strip()
    if not received_at:
        received_at = datetime.now(timezone.utc).isoformat()
    return {
        "start": body,
        "headers": ctx.get("headers") or {},
        "query": ctx.get("query") or {},
        "method": str(ctx.get("method") or "POST"),
        "receivedAt": received_at,
        "meta": {
            "webhookId": str(ctx.get("webhookId") or ""),
            "deliveryId": str(ctx.get("deliveryId") or ""),
            "signatureVerified": bool(ctx.get("signatureVerified", False)),
        },
    }


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


def _exec_set_variables(context: NodeExecContext) -> dict[str, Any]:
    """Merge configured variables over an optional input object.

    Configured keys WIN over the same keys on the input, so a node can set
    defaults from an upstream context and then override them explicitly.
    """
    configured = context.config.get("variables", {})
    if not isinstance(configured, dict):
        raise ValueError("config 'variables' must be an object")
    incoming = context.inputs.get("in")
    if incoming is None:
        incoming = {}
    if not isinstance(incoming, dict):
        raise ValueError("input 'in' must be an object")
    return {"variables": {**incoming, **configured}}


def _exec_json_parse(context: NodeExecContext) -> dict[str, Any]:
    text = context.inputs.get("text")
    if text is None:
        configured = context.config.get("text")
        text = configured if isinstance(configured, str) else ""
    if not isinstance(text, str):
        raise ValueError("input 'text' must be a string")
    if text.strip() == "":
        raise ValueError("no JSON to parse: wire Text or fill the JSON field")
    try:
        return {"value": json.loads(text)}
    except json.JSONDecodeError as exc:
        if context.config.get("strict", True):
            raise ValueError(f"input is not valid JSON: {exc}") from exc
        return {"value": text}




def _exec_template(context: NodeExecContext) -> dict[str, Any]:
    template = context.config.get("template", "")
    values = {key: context.inputs.get(key) for key in ("a", "b")}
    return {"text": render_template(template, values), "_control": ["done"]}


def _formula_operand(value: Any, key: str) -> float:
    """Accept a number or a series payload (its latest computed value)."""
    resolved = _numeric_operand(value)
    if isinstance(resolved, bool) or not isinstance(resolved, (int, float)):
        if isinstance(value, dict) and "values" in value:
            raise ValueError(
                f'input "{key}" is a series with no computed value yet — '
                "its warm-up still needs more points"
            )
        raise ValueError(f'input "{key}" must be a number, got {type(value).__name__}')
    return float(resolved)


def _exec_formula(context: NodeExecContext) -> dict[str, Any]:
    expression = context.config.get("expression", "x")
    variables: dict[str, float] = {}
    for key in ("x", "y"):
        value = context.inputs.get(key)
        if value is None:
            continue
        variables[key] = _formula_operand(value, key)
    return {"result": evaluate_formula(expression, variables), "_control": ["done"]}


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
    context.emit(f"{'true' if result else 'false'} ({operator}: {_summary_value(value)})")
    return {"result": result, "_control": ["true"] if result else ["false"]}


def _summary_value(value: Any, limit: int = 40) -> str:
    """A short, single-line rendering for a node's log line."""
    text = str(value)
    return text if len(text) <= limit else text[: limit - 1] + "…"


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


def _merge_present(value: Any) -> bool:
    """A branch is PRESENT unless it is null or empty.

    `0` and `false` are real values, so they count as present; an empty list,
    string or object does not. This is what makes "one branch produced rows and
    the other produced nothing" behave the way the node name promises.
    """
    if value is None:
        return False
    if isinstance(value, (str, list, dict)) and len(value) == 0:
        return False
    return True


def _exec_merge(context: NodeExecContext) -> dict[str, Any]:
    a = context.inputs.get("a")
    b = context.inputs.get("b")
    strategy = str(context.config.get("strategy") or "first_present").strip().lower()
    if strategy == "object":
        context.emit("merged a, b into one object")
        return {"value": {"a": a, "b": b}, "_control": ["done"]}
    if strategy in ("first", "first_present"):
        # Legacy `first` shares this behaviour: an empty/None branch is ABSENT,
        # so a populated `b` is no longer shadowed by an empty `a`.
        value = a if _merge_present(a) else b
        source = "a" if _merge_present(a) else ("b" if _merge_present(b) else "none")
        context.emit(f"merged {source}" if source != "none" else "no input on a or b")
        return {"value": value, "_control": ["done"]}
    raise ValueError(f"unsupported merge strategy {strategy!r}")


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
DURABLE_MAX_WAIT_MS = 86_400_000


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


def _switch_cases(raw: Any) -> list[str]:
    """Comma-separated, or a JSON array when a case itself contains a comma."""
    text = str(raw or "").strip()
    if not text:
        return []
    if text.startswith("["):
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"cases is not valid JSON: {exc}") from exc
        if not isinstance(parsed, list):
            raise ValueError("cases must be a JSON array of strings")
        return [str(item) for item in parsed]
    return [name.strip() for name in text.split(",") if name.strip()]


def _exec_switch(context: NodeExecContext) -> dict[str, Any]:
    value = context.inputs.get("value")
    names = _switch_cases(context.config.get("cases"))
    matched = -1
    for index, name in enumerate(names):
        if _compare_equal(value, name):
            matched = index
            break
    context.emit(
        f"case {matched + 1} of {len(names)}" if matched >= 0 else "default (no case matched)"
    )
    fired = ["matched"] if matched >= 0 else ["default"]
    # A per-case output lets one Switch own a 3-way branch; older graphs that
    # only wire `matched` are unaffected (firing an unwired port is a no-op).
    if 0 <= matched < 8:
        fired.append(f"case{matched + 1}")
    return {
        "caseIndex": matched,
        "matched": matched >= 0,
        "_control": fired,
    }


_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")


def _as_items(value: Any, node_label: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError(f"{node_label} expects an array input")
    if len(value) > MAX_LOOP_ITEMS:
        raise ValueError(f"{node_label} is bounded to {MAX_LOOP_ITEMS} items (got {len(value)})")
    out: list[Any] = []
    for index, item in enumerate(value):
        if isinstance(item, bool) or not isinstance(item, (int, float, dict)):
            raise ValueError(
                f"{node_label} works on numeric arrays or object rows; "
                f"item {index} is {type(item).__name__}"
            )
        out.append(item)
    return out


def _item_scope(item: Any, index: int) -> dict[str, float]:
    """Bind `index`, `value` and an object's numeric fields for the formula.

    A row field that is absent or non-numeric is NOT bound — referencing it is an
    error ("unknown name") instead of silently reading 0. A silent zero made
    `filter` drop every row of a text field and made `map` emit zeros, which is
    the one thing this runtime must never do.
    """
    scope: dict[str, float] = {"index": float(index)}
    if isinstance(item, dict):
        for key, value in item.items():
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                continue
            if _IDENT.match(str(key)):
                scope[str(key)] = float(value)
    else:
        scope["value"] = float(item)
    return scope


def _exec_map(context: NodeExecContext) -> dict[str, Any]:
    items = _as_items(context.inputs.get("items"), "logic.map")
    expression = context.config.get("expression", "value")
    mapped = [
        evaluate_formula(expression, _item_scope(item, index))
        for index, item in enumerate(items)
    ]
    context.emit(f"mapped {len(mapped)} item(s)")
    return {"items": mapped, "_control": ["done"]}


def _exec_filter(context: NodeExecContext) -> dict[str, Any]:
    items = _as_items(context.inputs.get("items"), "logic.filter")
    expression = context.config.get("expression", "value != 0")
    kept = [
        item for index, item in enumerate(items)
        if evaluate_formula(expression, _item_scope(item, index)) != 0
    ]
    context.emit(f"kept {len(kept)} of {len(items)} item(s)")
    return {"items": kept, "dropped": len(items) - len(kept), "_control": ["done"]}


def _exec_reduce(context: NodeExecContext) -> dict[str, Any]:
    items = _as_items(context.inputs.get("items"), "logic.reduce")
    expression = context.config.get("expression", "acc + value")
    try:
        accumulator = float(context.config.get("initial", 0))
    except (TypeError, ValueError) as exc:
        raise ValueError("initial must be a number") from exc
    for index, item in enumerate(items):
        scope = _item_scope(item, index)
        scope["acc"] = accumulator
        accumulator = evaluate_formula(expression, scope)
    context.emit(f"reduced {len(items)} item(s) → {accumulator:g}")
    return {"value": accumulator, "_control": ["done"]}


def _exec_wait(context: NodeExecContext) -> dict[str, Any]:
    try:
        milliseconds = int(context.config.get("ms", 0))
    except (TypeError, ValueError) as exc:
        raise ValueError("ms must be a whole number of milliseconds") from exc
    if milliseconds < 0:
        raise ValueError("ms cannot be negative")
    if milliseconds > DURABLE_MAX_WAIT_MS:
        raise ValueError(f"ms is bounded to {DURABLE_MAX_WAIT_MS}")
    if context.allow_defer and milliseconds:
        # Durable job: checkpoint this node and requeue the job at the wake
        # time instead of occupying a worker thread.
        from .model import DeferredWait  # noqa: PLC0415

        raise DeferredWait(milliseconds / 1000.0, {"waitedMs": milliseconds, "_control": ["done"]})
    if milliseconds > MAX_WAIT_MS:
        raise ValueError(
            f"ms is bounded to {MAX_WAIT_MS} in a non-durable run "
            f"(durable jobs may wait up to {DURABLE_MAX_WAIT_MS})"
        )
    # Poll in short slices so a cancelled run does not hold a worker for the whole
    # requested duration, and report the time actually waited rather than the time
    # asked for.
    waited_ms = 0
    if milliseconds:
        deadline = time.monotonic() + milliseconds / 1000.0
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                waited_ms = milliseconds
                break
            if context.should_cancel():
                waited_ms = max(0, milliseconds - int(remaining * 1000))
                context.emit(f"wait cancelled after {waited_ms} ms")
                break
            time.sleep(min(0.1, remaining))
    context.emit(f"waited {waited_ms} ms")
    return {"waitedMs": waited_ms, "_control": ["done"]}


def _exec_stop(context: NodeExecContext) -> dict[str, Any]:
    message = str(context.config.get("message") or "") or "run stopped"
    status = str(context.config.get("status") or "succeeded").strip().lower()
    if status not in ("succeeded", "failed"):
        raise ValueError(f"unsupported stop status {status!r}")
    context.emit(message)
    # `_stop` is read by the executor: the node still SUCCEEDS (so `stops_run`
    # skips the rest of the graph), and the requested status becomes the run's.
    return {"stopped": True, "_stop": {"status": status, "message": message}}


def _exec_gate(context: NodeExecContext) -> dict[str, Any]:
    # The executor only runs a gate when at least one control input fired (see
    # `executor.GraphExecutor._control_satisfied`). `require: all` turns it into
    # a join: every WIRED control input must have fired.
    require = str(context.config.get("require") or "any").strip().lower()
    if require not in ("any", "all"):
        raise ValueError(f"unsupported gate requirement {require!r}")
    fired = context.control_fired
    if require == "all":
        missing = sorted(port for port, ok in fired.items() if not ok)
        if missing:
            return {"_skip": f"not all control inputs fired (missing: {', '.join(missing)})"}
    wired = len(fired)
    context.emit(
        f"gate passed ({sum(fired.values())}/{wired} control inputs fired)"
        if wired else "gate passed"
    )
    return {"value": context.inputs.get("value"), "_control": ["done"]}


# ── Definitions ──────────────────────────────────────────────────────────────


MAX_HTTP_RESPONSE_BYTES = http_client.MAX_RESPONSE_BYTES
MAX_HTTP_HEADERS = http_client.MAX_HEADERS


def _legacy_http_body(result: http_client.HttpResult) -> Any:
    """`1.0.0` wrapped non-JSON text as `{text, contentType}`. Keep that exact
    shape for saved graphs; `1.1.0` emits the parsed value directly."""
    if isinstance(result.body, (dict, list)) or result.body is None:
        return result.body
    return {"text": result.body, "contentType": result.content_type}


def _exec_http(context: NodeExecContext) -> dict[str, Any]:
    """A bounded, SSRF-checked HTTP call.

    The permission envelope already gates this node behind an explicit network
    grant. `http_client` adds the second layer: a check on the URL and on every
    redirect hop, no loopback, no embedded credentials, retries, a hard timeout
    and a response size cap.
    """
    config = context.config
    method = str(config.get("method") or "GET").strip().upper()
    result = http_client.request(
        url=str(context.inputs.get("url") or config.get("url") or ""),
        method=method,
        query_json=str(config.get("queryJson") or ""),
        headers_json=str(config.get("headersJson") or ""),
        credential_env_json=str(config.get("credentialEnvJson") or ""),
        payload=context.inputs.get("body"),
        body_json=str(config.get("bodyJson") or ""),
        body_mode=str(config.get("bodyMode") or "json"),
        response_type=str(config.get("responseType") or "auto"),
        max_response_bytes=int(config.get("maxResponseBytes") or MAX_HTTP_RESPONSE_BYTES),
        on_oversize=str(config.get("onOversize") or "error"),
        follow_redirects=bool(config.get("followRedirects", False)),
        max_redirects=int(config.get("maxRedirects", 3)),
        # `1.0.0` treated every HTTP status as a successful node result.
        fail_on_http_error=bool(config.get("failOnHttpError", False)),
        retries=int(config.get("retries") or 0),
        retry_backoff_ms=int(config.get("retryBackoffMs") or 500),
        retry_unsafe=bool(config.get("retryUnsafe", False)),
        timeout_ms=int(config.get("timeoutMs") or 10_000),
    )
    context.emit(
        f"{method} {http_client.redact_url(result.url)} -> {result.status} "
        f"({result.duration_ms} ms)"
    )
    if context.node_version in ("", "1.0.0"):
        return {"status": result.status, "body": _legacy_http_body(result)}
    return {
        "status": result.status,
        "body": result.body,
        "headers": result.headers,
        "ok": result.ok,
        "contentType": result.content_type,
        "durationMs": result.duration_ms,
        "truncated": result.truncated,
    }


def _exec_webhook_send(context: NodeExecContext) -> dict[str, Any]:
    """POST a JSON payload signed with an HMAC-SHA256 webhook signature.

    The secret is an ENV VAR NAME in the config; the value is read here and
    never stored in the graph, the run record or an error.
    """
    import uuid  # noqa: PLC0415 - effectful node, keeps the core imports pure

    config = context.config
    secret_env = str(config.get("secretEnv") or "").strip()
    if not secret_env:
        raise ValueError("secretEnv is required")
    secret = os.environ.get(secret_env)
    if not secret:
        raise ValueError(f"secret variable {secret_env} is not set in the runtime environment")
    payload = context.inputs.get("body")
    if payload is None:
        raw = str(config.get("bodyJson") or "").strip()
        if raw:
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise ValueError(f"bodyJson is not valid JSON: {exc}") from exc
    if payload is None:
        payload = {}
    try:
        body_bytes = json.dumps(payload, sort_keys=True).encode("utf-8")
        plain = http_client.plain_headers(str(config.get("headersJson") or ""))
    except http_client.HttpRequestError as exc:
        raise ValueError(str(exc)) from exc
    if len(body_bytes) > http_client.MAX_REQUEST_BYTES:
        raise ValueError(f"request body exceeds {http_client.MAX_REQUEST_BYTES} bytes")
    timestamp = str(int(time.time()))
    delivery = str(config.get("deliveryId") or uuid.uuid4())
    signed = dict(plain)
    signed["X-Eclipse-Signature"] = http_client.sign_webhook(secret, timestamp, body_bytes)
    signed["X-Eclipse-Timestamp"] = timestamp
    signed["X-Eclipse-Delivery"] = delivery
    result = http_client.request(
        url=str(context.inputs.get("url") or config.get("url") or ""),
        method="POST",
        headers_json=json.dumps(signed),
        payload=payload,
        body_mode="json",
        response_type="auto",
        max_response_bytes=int(config.get("maxResponseBytes") or MAX_HTTP_RESPONSE_BYTES),
        on_oversize="truncate",
        follow_redirects=False,
        fail_on_http_error=bool(config.get("failOnHttpError", True)),
        retries=int(config.get("retries") or 0),
        retry_backoff_ms=int(config.get("retryBackoffMs") or 500),
        retry_unsafe=True,
        timeout_ms=int(config.get("timeoutMs") or 10_000),
    )
    context.emit(
        f"webhook {delivery} -> {http_client.redact_url(result.url)} {result.status}"
    )
    return {
        "status": result.status,
        "ok": result.ok,
        "body": result.body,
        "durationMs": result.duration_ms,
    }


def _port(port_id: str, name: str, port_type: PortType, **kwargs: Any) -> PortDef:
    return PortDef(id=port_id, name=name, type=port_type, **kwargs)


def build_default_registry() -> NodeRegistry:
    """The built-in node set. Mirrors the TS registry exactly."""
    registry = NodeRegistry()

    registry.register(NodeDef(
        type="trigger.manual", version="1.0.0", label="Manual trigger",
        category="trigger",
        outputs=(_port("start", "Start", PortType.ANY),),
        # Zero-config, like n8n's Manual Trigger. Legacy seed/payload keys from
        # older saved graphs still work (see _exec_trigger) even though they are
        # no longer declared here.
        config_fields=(),
        allowed_modes=_ALL, timeout_ms=5_000, executor=_exec_trigger,
    ))
    registry.register(NodeDef(
        type="trigger.schedule", version="1.0.0", label="Schedule",
        category="trigger",
        outputs=(_port("start", "Start", PortType.ANY),),
        # Zero-config like trigger.manual: the WorkflowSchedule linked to this
        # node owns cron/timezone/enabled. The front door fires the run.
        config_fields=(),
        capabilities=("schedule.manage",),
        allowed_modes=_ALL, timeout_ms=5_000, executor=_exec_trigger,
    ))
    registry.register(NodeDef(
        type="trigger.webhook", version="1.0.0", label="Webhook",
        category="trigger",
        outputs=(
            _port("start", "Start", PortType.ANY),
            _port("headers", "Headers", PortType.OBJECT),
            _port("query", "Query", PortType.OBJECT),
            _port("method", "Method", PortType.STRING),
            _port("receivedAt", "Received at", PortType.DATETIME),
            _port("meta", "Meta", PortType.OBJECT),
        ),
        # Zero-config at the node: the WorkflowWebhook linked by nodeId owns the
        # endpoint, secret, method filter, response mode and armed grants.
        config_fields=(),
        capabilities=("webhook.receive",),
        allowed_modes=_ALL, timeout_ms=5_000, executor=_exec_webhook_trigger,
        metadata={"docs": "Inbound HTTP webhook verified by the front door (HMAC + timestamp or token)."},
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
        type="data.set_variables", version="1.0.0", label="Set variables",
        category="data",
        inputs=(_port("in", "In", PortType.OBJECT, optional=True),),
        outputs=(_port("variables", "Variables", PortType.OBJECT),),
        config_fields=(ConfigField("variables", "object", {}),),
        allowed_modes=_ALL, executor=_exec_set_variables,
        metadata={
            "docs": (
                "Configured keys win over the same keys on the input object. Use it "
                "to carry named settings across a branch."
            ),
        },
    ))
    registry.register(NodeDef(
        type="data.json.parse", version="1.0.0", label="Parse JSON",
        category="data",
        inputs=(_port("text", "Text", PortType.STRING),),
        # JSON.parse may yield an object, an array, a number, a string or a
        # boolean — declaring `object` would be wrong (and would block arrays).
        outputs=(_port("value", "Value", PortType.ANY),),
        config_fields=(
            ConfigField("text", "string", "", max_length=20_000),
            ConfigField("strict", "boolean", True),
        ),
        allowed_modes=_ALL, executor=_exec_json_parse,
    ))
    registry.register(NodeDef(
        type="transform.template", version="1.0.0", label="Template",
        category="transform",
        inputs=(
            _port("in", "Run", PortType.ANY, kind=PortKind.CONTROL, optional=True),
            _port("a", "A", PortType.ANY, optional=True),
            _port("b", "B", PortType.ANY, optional=True),
        ),
        outputs=(
            _port("text", "Text", PortType.STRING),
            _port("done", "Done", PortType.ANY, kind=PortKind.CONTROL),
        ),
        config_fields=(ConfigField("template", "string", "{{a}}", max_length=4_000),),
        allowed_modes=_ALL, executor=_exec_template,
        metadata={
            "docs": (
                "Render {{a}}, {{a.price}} or {{a.price:.2f}}; {{a?}} is blank "
                "when the value is null, while a bare {{a}} fails. "
                "{{#each a}}…{{/each}} renders one block per row."
            ),
        },
    ))
    registry.register(NodeDef(
        type="transform.formula", version="1.0.0", label="Formula",
        category="transform",
        inputs=(
            _port("in", "Run", PortType.ANY, kind=PortKind.CONTROL, optional=True),
            # ANY, not number: a series payload ("{last, values}") resolves to
            # its latest point, exactly like logic.condition does.
            _port("x", "X", PortType.ANY),
            _port("y", "Y", PortType.ANY, optional=True),
        ),
        outputs=(
            _port("result", "Result", PortType.NUMBER),
            _port("done", "Done", PortType.ANY, kind=PortKind.CONTROL),
        ),
        config_fields=(ConfigField("expression", "string", "x", max_length=400),),
        capabilities=("compute.safe",),
        allowed_modes=_ALL, executor=_exec_formula,
        metadata={
            "docs": (
                "Safe arithmetic over x/y (numbers or series). Functions: if, div, "
                "nz, clamp, min, max, abs, round, floor, ceil, sqrt, log, log10, "
                "exp, pow, sign. round() is half-up."
            ),
        },
    ))
    registry.register(NodeDef(
        type="logic.condition", version="1.0.0", label="If / else",
        category="logic",
        inputs=(
            _port("in", "Run", PortType.ANY, kind=PortKind.CONTROL, optional=True),
            _port("value", "Value", PortType.ANY),
        ),
        outputs=(
            # The label IS the sentence: dragging from "If false" is unambiguous
            # in a way that a dot called `false` never was. Ids are unchanged.
            _port("true", "If true", PortType.ANY, kind=PortKind.CONTROL),
            _port("false", "If false", PortType.ANY, kind=PortKind.CONTROL),
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
            _port("in", "Run", PortType.ANY, kind=PortKind.CONTROL, optional=True),
            _port("a", "A", PortType.ANY),
            _port("b", "B", PortType.ANY, optional=True),
        ),
        outputs=(
            _port("value", "Value", PortType.ANY),
            _port("done", "Done", PortType.ANY, kind=PortKind.CONTROL),
        ),
        config_fields=(ConfigField(
            "strategy", "enum", "first_present",
            enum=("first", "first_present", "object"),
        ),),
        allowed_modes=_ALL, executor=_exec_merge,
        metadata={"docs": (
            "A branch is PRESENT unless it is null or empty, so a populated `b` is "
            "no longer shadowed by an empty `a`. `first` is the legacy name for "
            "`first_present`; `object` returns {a, b}."
        )},
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
            _port("in", "Run", PortType.ANY, kind=PortKind.CONTROL),
            _port("in2", "Run 2", PortType.ANY, kind=PortKind.CONTROL, optional=True),
            _port("in3", "Run 3", PortType.ANY, kind=PortKind.CONTROL, optional=True),
            _port("value", "Value", PortType.ANY, optional=True),
        ),
        outputs=(
            _port("value", "Value", PortType.ANY),
            _port("done", "Done", PortType.ANY, kind=PortKind.CONTROL),
        ),
        config_fields=(ConfigField("require", "enum", "any", enum=("any", "all")),),
        allowed_modes=_ALL, executor=_exec_gate,
        metadata={
            "docs": (
                "Runs when a control input fires. `require: all` makes it a join: "
                "every WIRED control input must have fired, otherwise it is skipped."
            ),
        },
    ))
    registry.register(NodeDef(
        type="logic.switch", version="1.0.0", label="Switch",
        category="logic",
        inputs=(
            _port("in", "Run", PortType.ANY, kind=PortKind.CONTROL, optional=True),
            _port("value", "Value", PortType.ANY),
        ),
        outputs=(
            # "Any match" (not "Matched"): it fires on EVERY match, which read as
            # the matched-branch output. The id stays `matched` for saved graphs.
            _port("matched", "Any match", PortType.ANY, kind=PortKind.CONTROL),
            _port("default", "No match", PortType.ANY, kind=PortKind.CONTROL),
            _port("caseIndex", "Case index", PortType.NUMBER),
            *(
                _port(f"case{index}", f"Case {index}", PortType.ANY, kind=PortKind.CONTROL)
                for index in range(1, 9)
            ),
        ),
        config_fields=(ConfigField("cases", "string", "", max_length=400),),
        allowed_modes=_ALL, executor=_exec_switch,
        metadata={
            "docs": (
                "Fires `matched` plus `caseN` (first match wins), or `default`. "
                "Up to eight per-case outputs; `cases` is comma-separated or a JSON array."
            ),
        },
    ))
    registry.register(NodeDef(
        type="logic.map", version="1.0.0", label="Map",
        category="logic",
        inputs=(
            _port("in", "Run", PortType.ANY, kind=PortKind.CONTROL, optional=True),
            _port("items", "Items", PortType.ARRAY),
        ),
        outputs=(
            _port("items", "Items", PortType.ARRAY),
            _port("done", "Done", PortType.ANY, kind=PortKind.CONTROL),
        ),
        config_fields=(ConfigField("expression", "string", "value", max_length=400),),
        capabilities=("compute.safe",),
        allowed_modes=_ALL, executor=_exec_map,
    ))
    registry.register(NodeDef(
        type="logic.filter", version="1.0.0", label="Filter",
        category="logic",
        inputs=(
            _port("in", "Run", PortType.ANY, kind=PortKind.CONTROL, optional=True),
            _port("items", "Items", PortType.ARRAY),
        ),
        outputs=(
            _port("items", "Items", PortType.ARRAY),
            _port("dropped", "Dropped", PortType.NUMBER),
            _port("done", "Done", PortType.ANY, kind=PortKind.CONTROL),
        ),
        config_fields=(ConfigField("expression", "string", "value != 0", max_length=400),),
        capabilities=("compute.safe",),
        allowed_modes=_ALL, executor=_exec_filter,
    ))
    registry.register(NodeDef(
        type="logic.reduce", version="1.0.0", label="Reduce",
        category="logic",
        inputs=(
            _port("in", "Run", PortType.ANY, kind=PortKind.CONTROL, optional=True),
            _port("items", "Items", PortType.ARRAY),
        ),
        outputs=(
            _port("value", "Value", PortType.NUMBER),
            _port("done", "Done", PortType.ANY, kind=PortKind.CONTROL),
        ),
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
        inputs=(_port("in", "Run", PortType.ANY, kind=PortKind.CONTROL, optional=True),),
        outputs=(
            _port("waitedMs", "Waited", PortType.NUMBER),
            _port("done", "Done", PortType.ANY, kind=PortKind.CONTROL),
        ),
        config_fields=(ConfigField("ms", "integer", 0, minimum=0, maximum=DURABLE_MAX_WAIT_MS),),
        allowed_modes=_ALL, executor=_exec_wait,
        test_run_limits={"ms": TEST_RUN_MAX_WAIT_MS},
    ))
    registry.register(NodeDef(
        type="flow.subworkflow", version="1.0.0", label="Subworkflow",
        category="logic",
        inputs=(
            _port("in", "Run", PortType.ANY, kind=PortKind.CONTROL, optional=True),
            _port("input", "Input", PortType.ANY, optional=True),
        ),
        outputs=(
            _port("output", "Output", PortType.ANY),
            _port("runId", "Run id", PortType.STRING),
            _port("done", "Done", PortType.ANY, kind=PortKind.CONTROL),
        ),
        config_fields=(
            ConfigField("workflowId", "string", "", max_length=80),
            ConfigField("version", "integer", 1, minimum=1, maximum=1_000_000),
        ),
        allowed_modes=_ALL, orchestrated=True, timeout_ms=600_000,
        metadata={
            "docs": (
                "Runs a PINNED saved workflow (id@version) as a nested run with the "
                "parent's grants. The parent input is delivered to the child trigger; "
                "the child's terminal output is returned. Cycles/depth are refused."
            ),
        },
    ))
    registry.register(NodeDef(
        type="logic.stop", version="1.0.0", label="Stop",
        category="logic",
        inputs=(
            _port("in", "Run", PortType.ANY, kind=PortKind.CONTROL, optional=True),
            # Carrying a value through Stop makes it usable as a run terminal:
            # the executor reads `inputs["value"]` for the run output.
            _port("value", "Output", PortType.ANY, optional=True),
        ),
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
            ConfigField("method", "enum", "GET", enum=("GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS")),
            ConfigField("bodyJson", "string", "", max_length=20_000),
            ConfigField("headersJson", "string", "", max_length=10_000),
            ConfigField("credentialEnvJson", "string", "", max_length=10_000),
            ConfigField("timeoutMs", "integer", 10_000, minimum=1_000, maximum=60_000),
        ),
        capabilities=("network.egress",),
        side_effects=SideEffect.NETWORK,
        allowed_modes=_ALL,
        executor=_exec_http,
        metadata={"docs": "SSRF-checked, no loopback, bounded response; requires an explicit network grant."},
    ))
    registry.register(NodeDef(
        type="integration.http", version="1.1.0", label="HTTP request",
        category="integration",
        inputs=(
            _port("url", "URL", PortType.STRING, optional=True),
            _port("body", "Body", PortType.ANY, optional=True),
        ),
        outputs=(
            _port("status", "Status", PortType.NUMBER),
            _port("body", "Body", PortType.ANY),
            _port("headers", "Headers", PortType.OBJECT),
            _port("ok", "OK", PortType.BOOLEAN),
            _port("contentType", "Content type", PortType.STRING),
            _port("durationMs", "Duration", PortType.NUMBER),
            _port("truncated", "Truncated", PortType.BOOLEAN),
        ),
        config_fields=(
            ConfigField("url", "string", "", max_length=2_000),
            ConfigField("method", "enum", "GET", enum=("GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS")),
            ConfigField("queryJson", "string", "", max_length=8_000),
            ConfigField("bodyJson", "string", "", max_length=20_000),
            ConfigField("bodyMode", "enum", "json", enum=("json", "text", "form")),
            ConfigField("headersJson", "string", "", max_length=10_000),
            ConfigField("credentialEnvJson", "string", "", max_length=10_000),
            ConfigField("responseType", "enum", "auto", enum=("auto", "json", "text")),
            ConfigField("maxResponseBytes", "integer", 1_000_000, minimum=1_000, maximum=10_000_000),
            ConfigField("onOversize", "enum", "error", enum=("error", "truncate")),
            ConfigField("followRedirects", "boolean", False),
            ConfigField("maxRedirects", "integer", 3, minimum=0, maximum=5),
            ConfigField("failOnHttpError", "boolean", True),
            ConfigField("retries", "integer", 0, minimum=0, maximum=3),
            ConfigField("retryBackoffMs", "integer", 500, minimum=100, maximum=10_000),
            ConfigField("retryUnsafe", "boolean", False),
            ConfigField("timeoutMs", "integer", 10_000, minimum=1_000, maximum=60_000),
        ),
        capabilities=("network.egress",),
        side_effects=SideEffect.NETWORK,
        allowed_modes=_ALL,
        executor=_exec_http,
        metadata={"docs": "SSRF-checked on every redirect hop; retries, query/body modes, headers and bounded response. Requires an explicit network grant."},
    ))
    registry.register(NodeDef(
        type="integration.webhook_send", version="1.0.0", label="Send webhook",
        category="integration",
        inputs=(
            _port("url", "URL", PortType.STRING, optional=True),
            _port("body", "Body", PortType.ANY, optional=True),
        ),
        outputs=(
            _port("status", "Status", PortType.NUMBER),
            _port("ok", "OK", PortType.BOOLEAN),
            _port("body", "Body", PortType.ANY),
            _port("durationMs", "Duration", PortType.NUMBER),
        ),
        config_fields=(
            ConfigField("url", "string", "", max_length=2_000),
            ConfigField("bodyJson", "string", "", max_length=20_000),
            ConfigField("secretEnv", "string", "", max_length=128),
            ConfigField("headersJson", "string", "", max_length=10_000),
            ConfigField("deliveryId", "string", "", max_length=200),
            ConfigField("failOnHttpError", "boolean", True),
            ConfigField("retries", "integer", 0, minimum=0, maximum=3),
            ConfigField("retryBackoffMs", "integer", 500, minimum=100, maximum=10_000),
            ConfigField("maxResponseBytes", "integer", 1_000_000, minimum=1_000, maximum=10_000_000),
            ConfigField("timeoutMs", "integer", 10_000, minimum=1_000, maximum=60_000),
        ),
        capabilities=("network.egress",),
        side_effects=SideEffect.NETWORK,
        allowed_modes=_ALL,
        executor=_exec_webhook_send,
        metadata={"docs": "Signed outbound webhook (X-Eclipse-Signature/Timestamp/Delivery); the secret is an env-var reference."},
    ))
    # Local dataset refs (large-payload seam). The store is bound at boot.
    for definition in build_dataset_nodes():
        registry.register(definition)
    # Deterministic tabular transforms over arrays of objects.
    for definition in build_table_nodes():
        registry.register(definition)
    # Finance + quant nodes carry REAL executors (Phase 5). They live in
    # `finance_nodes.py` so this file stays the pure/deterministic core; the
    # same contracts are mirrored in the TS registry.
    for definition in build_finance_nodes():
        registry.register(definition)
    # The remaining gateway READ capabilities (order book, options, FX, bonds,
    # crypto metrics). Same gateway, same provenance, same honest failure.
    from .market_read_nodes import build_market_read_nodes  # noqa: PLC0415

    for definition in build_market_read_nodes():
        registry.register(definition)
    # Quant research nodes reuse the tested engine; no backtest math here.
    for definition in build_quant_nodes():
        registry.register(definition)
    # Pure risk/return metrics over an indicator series (no engine, no state).
    from .quant_metrics_nodes import build_quant_metric_nodes  # noqa: PLC0415

    for definition in build_quant_metric_nodes():
        registry.register(definition)
    # Validation over what the research nodes measured: the edge verdict, a
    # benchmark comparison and a timeframe aggregation. Adapters only.
    from .quant_validation_nodes import build_quant_validation_nodes  # noqa: PLC0415

    for definition in build_quant_validation_nodes():
        registry.register(definition)
    # Structure: multi-instrument alignment, regime labels and position sizing.
    from .quant_structure_nodes import build_quant_structure_nodes  # noqa: PLC0415

    for definition in build_quant_structure_nodes():
        registry.register(definition)
    # Portfolio accounting: several strategies on one book, one engine.
    from .quant_portfolio_nodes import build_quant_portfolio_nodes  # noqa: PLC0415

    for definition in build_quant_portfolio_nodes():
        registry.register(definition)
    # Instrument-specific: multi-leg options and continuous futures.
    from .quant_instruments_nodes import build_quant_instrument_nodes  # noqa: PLC0415

    for definition in build_quant_instrument_nodes():
        registry.register(definition)
    # Local research/evidence reads over the existing EvidenceStore.
    for definition in build_research_nodes():
        registry.register(definition)
    # Paper-trading safety: a pure risk gate + a PAPER-only execution adapter.
    for definition in build_trading_nodes():
        registry.register(definition)
    # Video-production node declarations (Phase 8): executor-less ON PURPOSE —
    # a render is an async Fabric job behind an effectful-node policy the graph
    # runtime does not have yet; the compiler names that honestly.
    from .video_nodes import build_video_nodes  # noqa: PLC0415

    for definition in build_video_nodes():
        registry.register(definition)
    # The agent node is a thin adapter over the existing run plane.
    for definition in build_agent_nodes():
        registry.register(definition)
    # Bounded loops (Phase 4): a body subworkflow + an explicit cap, never a
    # graph cycle.
    from .loop_nodes import build_loop_nodes  # noqa: PLC0415

    for definition in build_loop_nodes():
        registry.register(definition)
    # Scoped local writes (Phase 5): a named scope, a relative path, a cap.
    from .write_nodes import build_write_nodes  # noqa: PLC0415

    for definition in build_write_nodes():
        registry.register(definition)
    # Broker reads + risk-reducing exits (Phase 6). Orders stay in trading_nodes.
    from .broker_nodes import build_broker_nodes  # noqa: PLC0415

    for definition in build_broker_nodes():
        registry.register(definition)
    return registry


__all__ = [
    "FormulaError",
    "evaluate_formula",
    "render_template",
    "build_default_registry",
]
