"""Dataset nodes: persist a value locally and read it back by reference.

These are the primitives a large-payload workflow needs. They deliberately do
not change how every node passes data; they let a graph opt into a reference
when a payload is too large (or too useful) to keep in a run document.

`save` is a LOCAL write (own agent-memory scratch), not an external effect:
the compiler's test-run envelope may perform it, while network/write/trading
still cannot run. A dataset is bounded by size, count and an optional TTL.
"""

from __future__ import annotations

from typing import Any

from .datasets import DatasetError, require_dataset_store
from .model import ExecutionMode, PortDef, PortType, SideEffect
from .registry import ConfigField, NodeDef, NodeExecContext

_ALL = tuple(ExecutionMode)


def exec_dataset_save(context: NodeExecContext) -> dict[str, Any]:
    value = context.inputs.get("value")
    if value is None:
        raise ValueError("no value to save: wire a value into this node")
    try:
        ttl_hours = int(context.config.get("ttlHours", 0))
    except (TypeError, ValueError) as exc:
        raise ValueError("ttlHours must be a whole number") from exc
    if ttl_hours < 0:
        raise ValueError("ttlHours cannot be negative")
    try:
        meta = require_dataset_store().save(
            str(context.config.get("name") or context.node_id),
            value,
            ttl_seconds=ttl_hours * 3600,
            owner=context.user_id,
        )
    except DatasetError as exc:
        raise ValueError(str(exc)) from exc
    context.emit(f"dataset {meta['ref']} · {meta['bytes']} bytes")
    return {"ref": meta["ref"], "meta": meta}


def exec_dataset_load(context: NodeExecContext) -> dict[str, Any]:
    ref = context.inputs.get("ref")
    if not isinstance(ref, str) or not ref.strip():
        raise ValueError("input 'ref' must be a dataset reference")
    try:
        store = require_dataset_store()
        value = store.load(ref, owner=context.user_id)
        meta = store.meta(ref, owner=context.user_id)
    except DatasetError as exc:
        raise ValueError(str(exc)) from exc
    context.emit(f"loaded dataset {meta['ref']} · {meta['bytes']} bytes")
    return {"value": value, "meta": meta}


def build_dataset_nodes() -> list[NodeDef]:
    return [
        NodeDef(
            type="data.dataset.save",
            version="1.0.0",
            label="Save dataset",
            category="data",
            inputs=(PortDef(id="value", name="Value", type=PortType.ANY),),
            outputs=(
                PortDef(id="ref", name="Ref", type=PortType.STRING),
                PortDef(id="meta", name="Meta", type=PortType.OBJECT),
            ),
            config_fields=(
                ConfigField("name", "string", "", max_length=200),
                ConfigField("ttlHours", "integer", 0, minimum=0, maximum=8760),
            ),
            capabilities=("dataset.write",),
            side_effects=SideEffect.LOCAL_WRITE,
            allowed_modes=_ALL,
            executor=exec_dataset_save,
            metadata={
                "docs": (
                    "Stores a JSON payload in the runtime's local dataset store and "
                    "returns a small ref. Bounded by size, dataset count and an optional TTL."
                ),
            },
        ),
        NodeDef(
            type="data.dataset.load",
            version="1.0.0",
            label="Load dataset",
            category="data",
            inputs=(PortDef(id="ref", name="Ref", type=PortType.STRING),),
            outputs=(
                PortDef(id="value", name="Value", type=PortType.ANY),
                PortDef(id="meta", name="Meta", type=PortType.OBJECT),
            ),
            config_fields=(),
            capabilities=("dataset.read",),
            side_effects=SideEffect.READ,
            allowed_modes=_ALL,
            executor=exec_dataset_load,
            metadata={
                "docs": "Reads a dataset by ref. A missing or expired ref is an explicit failure.",
            },
        ),
    ]


__all__ = ["build_dataset_nodes", "exec_dataset_save", "exec_dataset_load"]
