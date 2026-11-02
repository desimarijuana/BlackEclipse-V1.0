"""Pure utility nodes: assert, fallback, extract.

No model, no network, no store — deterministic over their inputs. They are the
small primitives an unattended graph needs to stop honestly (`logic.assert`),
pick the first present value (`logic.fallback`) and read a field out of a
payload (`data.extract`).
"""

from __future__ import annotations

from typing import Any

from .model import ExecutionMode, PortDef, PortKind, PortType, SideEffect
from .registry import ConfigField, NodeDef, NodeExecContext

_ALL = tuple(ExecutionMode)
ASSERT_EXPECTATIONS = ("truthy", "falsy", "present")


def _port(port_id: str, name: str, port_type: PortType, **kwargs: Any) -> PortDef:
    return PortDef(id=port_id, name=name, type=port_type, **kwargs)


def _present(value: Any) -> bool:
    """An empty/None value is ABSENT — the same rule `logic.merge` uses."""
    return value is not None and value != "" and value != [] and value != {}


def exec_assert(context: NodeExecContext) -> dict[str, Any]:
    expect = str(context.config.get("expect") or "truthy").strip().lower()
    if expect not in ASSERT_EXPECTATIONS:
        raise ValueError(f"unsupported assert expectation {expect!r}")
    value = context.inputs.get("value")
    if expect == "truthy":
        ok = bool(value)
    elif expect == "falsy":
        ok = not bool(value)
    else:
        ok = _present(value)
    if not ok:
        message = str(
            context.inputs.get("message") or context.config.get("message") or ""
        ).strip()
        raise ValueError(message or f"assertion failed: expected the value to be {expect}")
    context.emit(f"assertion passed ({expect})")
    return {"value": value, "_control": ["done"]}


def exec_fallback(context: NodeExecContext) -> dict[str, Any]:
    for index, port_id in enumerate(("in1", "in2", "in3"), start=1):
        value = context.inputs.get(port_id)
        if _present(value):
            context.emit(f"using in{index}")
            return {"value": value, "source": port_id, "_control": ["done"]}
    context.emit("no input was present")
    return {"value": None, "source": "", "_control": ["done"]}


def exec_data_extract(context: NodeExecContext) -> dict[str, Any]:
    path = str(context.config.get("path") or "").strip()
    if not path:
        raise ValueError("data.extract needs a path (e.g. data.items.0.price)")
    on_missing = str(context.config.get("onMissing") or "null").strip().lower()
    if on_missing not in ("null", "error"):
        raise ValueError(f"unsupported onMissing {on_missing!r}")

    current = context.inputs.get("value")
    for segment in path.split("."):
        if isinstance(current, dict):
            if segment not in current:
                return _missing(context, path, segment, on_missing)
            current = current[segment]
        elif isinstance(current, list):
            if not segment.isdigit():
                return _missing(context, path, segment, on_missing)
            index = int(segment)
            if index >= len(current):
                return _missing(context, path, segment, on_missing)
            current = current[index]
        else:
            return _missing(context, path, segment, on_missing)
    context.emit(f"read {path}")
    return {"value": current, "found": True, "_control": ["done"]}


def _missing(
    context: NodeExecContext, path: str, segment: str, on_missing: str,
) -> dict[str, Any]:
    if on_missing == "error":
        raise ValueError(f"path {path!r} has no value at {segment!r}")
    context.emit(f"path {path!r} is absent at {segment!r}")
    return {"value": None, "found": False, "_control": ["done"]}


def build_utility_nodes() -> list[NodeDef]:
    return [
        NodeDef(
            type="logic.assert", version="1.0.0", label="Assert",
            category="logic",
            inputs=(
                _port("in", "Run", PortType.ANY, kind=PortKind.CONTROL, optional=True),
                _port("value", "Value", PortType.ANY, optional=True),
                _port("message", "Message", PortType.STRING, optional=True),
            ),
            outputs=(
                _port("value", "Value", PortType.ANY, nullable=True),
                _port("done", "Done", PortType.ANY, kind=PortKind.CONTROL),
            ),
            config_fields=(
                ConfigField("expect", "enum", "truthy", enum=ASSERT_EXPECTATIONS),
                ConfigField("message", "string", "", max_length=500),
            ),
            capabilities=(),
            side_effects=SideEffect.NONE,
            allowed_modes=_ALL,
            timeout_ms=60_000,
            executor=exec_assert,
            metadata={
                "docs": (
                    "Fails the node (and, with fail-fast, the run) with a named message "
                    "when the value does not meet `expect` (truthy/falsy/present). "
                    "`present` treats null, '', [] and {} as absent — the same rule "
                    "logic.merge uses. It never invents a replacement value."
                ),
            },
        ),
        NodeDef(
            type="logic.fallback", version="1.0.0", label="Fallback",
            category="logic",
            inputs=(
                _port("in", "Run", PortType.ANY, kind=PortKind.CONTROL, optional=True),
                _port("in1", "First", PortType.ANY, optional=True),
                _port("in2", "Second", PortType.ANY, optional=True),
                _port("in3", "Third", PortType.ANY, optional=True),
            ),
            outputs=(
                _port("value", "Value", PortType.ANY, nullable=True),
                _port("source", "Source", PortType.STRING),
                _port("done", "Done", PortType.ANY, kind=PortKind.CONTROL),
            ),
            config_fields=(),
            capabilities=(),
            side_effects=SideEffect.NONE,
            allowed_modes=_ALL,
            timeout_ms=60_000,
            executor=exec_fallback,
            metadata={
                "docs": (
                    "Returns the first PRESENT input (null/''/[]/{} are absent) and "
                    "which port it came from. All absent returns null and an empty "
                    "source. For two inputs, logic.merge (first_present) is equivalent."
                ),
            },
        ),
        NodeDef(
            type="data.extract", version="1.0.0", label="Extract field",
            category="data",
            inputs=(
                _port("in", "Run", PortType.ANY, kind=PortKind.CONTROL, optional=True),
                _port("value", "Value", PortType.ANY),
            ),
            outputs=(
                _port("value", "Value", PortType.ANY, nullable=True),
                _port("found", "Found", PortType.BOOLEAN),
                _port("done", "Done", PortType.ANY, kind=PortKind.CONTROL),
            ),
            config_fields=(
                ConfigField("path", "string", "", max_length=500),
                ConfigField("onMissing", "enum", "null", enum=("null", "error")),
            ),
            capabilities=(),
            side_effects=SideEffect.NONE,
            allowed_modes=_ALL,
            timeout_ms=60_000,
            executor=exec_data_extract,
            metadata={
                "docs": (
                    "Reads a dotted path out of an object/array (`data.items.0.price`). "
                    "A numeric segment indexes a list. A missing path returns "
                    "`found: false` + null, or fails by name when `onMissing` is "
                    "`error`. It never invents a value."
                ),
            },
        ),
    ]


__all__ = [
    "ASSERT_EXPECTATIONS",
    "build_utility_nodes",
    "exec_assert",
    "exec_data_extract",
    "exec_fallback",
]
