"""Output nodes: draw a chart from a payload, and send a notification.

`output.chart` is pure and local: it turns a payload into a validated `ChartSpec`
and (when plotly is installed) the figure the front-end chart engine draws. It
never reaches the network.

`output.notify` sends through the ONE channel service (`send_outbound`), so the
stored configuration, provider transport and delivery record are the existing
ones. It declares the `network` effect: a test run can never send a message.
"""

from __future__ import annotations

import json
from typing import Any, Callable, Optional

from .model import ExecutionMode, PortDef, PortType, SideEffect
from .registry import ConfigField, NodeDef, NodeExecContext

_ALL = tuple(ExecutionMode)

# Kinds this node can build from data. A full spec passed in may use any kind
# the chart engine supports; these are the ones the payload shapes produce.
CHART_KINDS = ("line", "area", "bar", "scatter", "pie", "donut")
MAX_DATA_POINTS = 5_000

NotifyRunner = Callable[[NodeExecContext, dict[str, Any]], dict[str, Any]]
_notify: Optional[NotifyRunner] = None


def set_notify_runner(runner: Optional[NotifyRunner]) -> None:
    global _notify
    _notify = runner


def _numbers(values: Any, *, field: str) -> list[Optional[float]]:
    if not isinstance(values, list):
        raise ValueError(f"{field} must be a list of numbers")
    if len(values) > MAX_DATA_POINTS:
        raise ValueError(f"{field} exceeds {MAX_DATA_POINTS} points")
    out: list[Optional[float]] = []
    for index, value in enumerate(values):
        if value is None:
            out.append(None)
            continue
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"{field}[{index}] is not a number")
        out.append(float(value))
    return out


def _spec_payload(context: NodeExecContext, payload: Any) -> dict[str, Any]:
    """Normalize the wired payload into a ChartSpec-shaped dict."""
    if isinstance(payload, dict) and isinstance(payload.get("spec"), dict):
        return dict(payload["spec"])
    if isinstance(payload, dict) and payload.get("kind"):
        return dict(payload)

    kind = str(context.config.get("kind") or "line")
    if kind not in CHART_KINDS:
        raise ValueError(f"unsupported chart kind {kind!r}")
    spec: dict[str, Any] = {"kind": kind}
    if payload is None:
        raise ValueError("output.chart needs a payload (wire a series or a chart spec)")

    if isinstance(payload, list):
        spec["series"] = [{"name": "Value", "data": _numbers(payload, field="series")}]
        spec["categories"] = [str(index) for index, _ in enumerate(payload)]
    elif isinstance(payload, dict) and isinstance(payload.get("rows"), list):
        rows = payload["rows"]
        x_field = str(context.config.get("xField") or "").strip()
        y_field = str(context.config.get("yField") or "").strip()
        if not x_field or not y_field:
            raise ValueError("a rows payload needs X field and Y field")
        categories: list[str] = []
        values: list[Optional[float]] = []
        for index, row in enumerate(rows[:MAX_DATA_POINTS]):
            if not isinstance(row, dict):
                raise ValueError(f"rows[{index}] is not an object")
            categories.append(str(row.get(x_field, "")))
            raw = row.get(y_field)
            if raw is None:
                values.append(None)
            elif isinstance(raw, bool) or not isinstance(raw, (int, float)):
                raise ValueError(f"rows[{index}].{y_field} is not a number")
            else:
                values.append(float(raw))
        spec["categories"] = categories
        spec["series"] = [{"name": y_field, "data": values}]
    elif isinstance(payload, dict) and isinstance(payload.get("values"), list):
        spec["series"] = [{"name": "Value", "data": _numbers(payload["values"], field="values")}]
        if isinstance(payload.get("categories"), list):
            spec["categories"] = [str(item) for item in payload["categories"]]
        else:
            spec["categories"] = [str(index) for index, _ in enumerate(payload["values"])]
    elif isinstance(payload, dict) and isinstance(payload.get("series"), list):
        spec["series"] = payload["series"]
        if isinstance(payload.get("categories"), list):
            spec["categories"] = [str(item) for item in payload["categories"]]
    else:
        raise ValueError(
            "output.chart needs a chart spec, a list of numbers, "
            "{values, categories}, {series, categories} or {rows} with X/Y fields"
        )

    for key, config_key in (("title", "title"), ("xLabel", "xLabel"), ("yLabel", "yLabel")):
        configured = str(context.config.get(config_key) or "").strip()
        if configured and not spec.get(key):
            spec[key] = configured
    return spec


def exec_output_chart(context: NodeExecContext) -> dict[str, Any]:
    from ..charts.service import build_chart_figure  # noqa: PLC0415
    from ..charts.spec import ChartSpec  # noqa: PLC0415

    payload = context.inputs.get("series")
    spec_payload = _spec_payload(context, payload)
    try:
        spec = ChartSpec.model_validate(spec_payload)
    except Exception as exc:  # noqa: BLE001 - a pydantic error is the honest reason
        raise ValueError(f"invalid chart spec: {exc}") from exc
    figure = build_chart_figure(spec)
    context.emit(
        f"{spec.kind} chart"
        + ("" if figure else " (plotly unavailable: spec only)")
    )
    return {
        "spec": spec.model_dump(by_alias=True),
        "figure": figure,
        "rendered": figure is not None,
    }


def exec_output_notify(context: NodeExecContext) -> dict[str, Any]:
    if context.test_run:
        raise ValueError(
            "output.notify sends a message off this machine; run it as an operator run"
        )
    channel = str(context.config.get("channel") or "").strip().lower()
    destination = str(context.config.get("destination") or "").strip()
    if not channel:
        raise ValueError("output.notify needs a channel (e.g. telegram, slack, webhook)")
    if not destination:
        raise ValueError("output.notify needs a destination (chat/channel id)")
    message = str(
        context.inputs.get("message") or context.config.get("message") or ""
    ).strip()
    if not message:
        raise ValueError("output.notify needs a message (wire one or fill Message)")
    title = str(context.config.get("title") or "").strip()
    if title and not message.startswith(title):
        message = f"{title}\n{message}"
    extra = context.inputs.get("data")
    if extra is not None:
        message = f"{message}\n\n{json.dumps(extra, ensure_ascii=False)[:2_000]}"
    if len(message) > 8_000:
        raise ValueError("notification exceeds 8 000 characters")
    if _notify is None:
        raise ValueError("the channel service is not configured in this graph runtime")
    result = _notify(context, {
        "channel": channel,
        "destination": destination,
        "message": message,
    })
    if not isinstance(result, dict):
        raise ValueError("the channel service returned no structured result")
    if not result.get("ok"):
        raise ValueError(f"delivery failed: {result.get('reason') or 'no reason reported'}")
    context.emit(f"sent via {channel}")
    return {"delivered": True, "detail": result}


def build_output_nodes() -> list[NodeDef]:
    return [
        NodeDef(
            type="output.chart", version="1.0.0", label="Chart",
            category="output",
            inputs=(PortDef(id="series", name="Series", type=PortType.ANY),),
            outputs=(
                PortDef(id="spec", name="Spec", type=PortType.OBJECT),
                PortDef(id="figure", name="Figure", type=PortType.OBJECT, nullable=True),
                PortDef(id="rendered", name="Rendered", type=PortType.BOOLEAN),
            ),
            config_fields=(
                ConfigField("kind", "enum", "line", enum=CHART_KINDS),
                ConfigField("title", "string", "", max_length=200),
                ConfigField("xLabel", "string", "", max_length=120),
                ConfigField("yLabel", "string", "", max_length=120),
                ConfigField("xField", "string", "", max_length=120),
                ConfigField("yField", "string", "", max_length=120),
            ),
            capabilities=(),
            side_effects=SideEffect.NONE,
            allowed_modes=_ALL,
            timeout_ms=120_000,
            executor=exec_output_chart,
            metadata={
                "docs": (
                    "Builds a validated ChartSpec from a spec, a number list, "
                    "{values, categories}, {series, categories} or {rows} + X/Y "
                    "fields, then the plotly figure the chart engine draws. Plotly "
                    "missing is reported as `rendered: false` with the spec still "
                    "returned — never a fake image."
                ),
            },
        ),
        NodeDef(
            type="output.notify", version="1.0.0", label="Notify",
            category="output",
            inputs=(
                PortDef(id="message", name="Message", type=PortType.STRING, optional=True),
                PortDef(id="data", name="Data", type=PortType.ANY, optional=True),
            ),
            outputs=(
                PortDef(id="delivered", name="Delivered", type=PortType.BOOLEAN),
                PortDef(id="detail", name="Detail", type=PortType.OBJECT),
            ),
            config_fields=(
                ConfigField("channel", "string", "", max_length=40),
                ConfigField("destination", "string", "", max_length=200),
                ConfigField("title", "string", "", max_length=200),
                ConfigField("message", "string", "", max_length=4_000),
            ),
            capabilities=("notification.send",),
            side_effects=SideEffect.NETWORK,
            allowed_modes=_ALL,
            timeout_ms=60_000,
            executor=exec_output_notify,
            metadata={
                "docs": (
                    "Sends one message through the ONE channel service "
                    "(`send_outbound`) to a configured channel + destination. A "
                    "delivery failure fails the node with the provider's reason. "
                    "Network effect: a test run can never send."
                ),
            },
        ),
    ]


__all__ = [
    "CHART_KINDS",
    "build_output_nodes",
    "exec_output_chart",
    "exec_output_notify",
    "set_notify_runner",
]
