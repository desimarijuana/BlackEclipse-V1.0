"""Chat-to-graph: turn a natural-language objective into a validated WorkflowIR.

The model only proposes STRUCTURE. This module owns the contract: it advertises
the runtime's actual node catalog, validates node types/ports/configs against the
same registry the compiler uses, and derives capabilities and the execution mode
from the nodes actually selected. A proposal that does not compile is returned
with its diagnostics and no IR; nothing is saved or run here.
"""

from __future__ import annotations

import json
import re
import uuid
from typing import Any, Optional

from ..model_runtime import get_runtime
from ..schemas import ModelSettings
from .model import ExecutionMode, SideEffect, WorkflowIR
from .registry import (
    NodeRegistry,
    coerce_config,
    ports_compatible,
    validate_config,
)

MAX_NODES = 24
MAX_EDGES = 64
_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")

PLAN_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "name": {"type": "string", "maxLength": 120},
        "title": {"type": "string", "maxLength": 120},
        "summary": {"type": "string", "maxLength": 800},
        "nodes": {
            "type": "array",
            "maxItems": MAX_NODES,
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "type": {"type": "string"},
                    "version": {"type": "string"},
                    "label": {"type": "string"},
                    "config": {"type": "object"},
                },
                "required": ["type"],
                "additionalProperties": False,
            },
        },
        "edges": {
            "type": "array",
            "maxItems": MAX_EDGES,
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    # Canonical names plus the aliases models commonly emit.
                    "source": {"type": ["string", "object"]},
                    "from": {"type": ["string", "object"]},
                    # A handle may be a plain id or `{node, port}`.
                    "sourceHandle": {"type": ["string", "object"]},
                    "sourcePort": {"type": ["string", "object"]},
                    "fromPort": {"type": ["string", "object"]},
                    "fromHandle": {"type": ["string", "object"]},
                    "target": {"type": ["string", "object"]},
                    "to": {"type": ["string", "object"]},
                    "targetHandle": {"type": ["string", "object"]},
                    "targetPort": {"type": ["string", "object"]},
                    "toPort": {"type": ["string", "object"]},
                    "toHandle": {"type": ["string", "object"]},
                },
                "required": [],
                "additionalProperties": False,
            },
        },
        "warnings": {"type": "array", "items": {"type": "string"}, "maxItems": 10},
    },
    # A model that omits a friendly title/summary is still a usable plan; the
    # structure (nodes/edges) is what must be present.
    "required": ["nodes", "edges"],
    "additionalProperties": False,
}

SYSTEM_PROMPT = (
    "You design Eclipse workflow graphs. Return ONLY the strict JSON object the "
    "schema describes. Use node types from the supplied catalog and no others. "
    "Every graph starts with one trigger node and ends with at least one "
    "output.result node. Connect typed ports only (a control port to a control "
    "port; matching data types; 'any' accepts anything). Keep ids short, unique "
    "and stable. Put node settings in `config` using the catalog defaults as a "
    "base. Never invent node types, ports or config keys. Prefer the fewest "
    "nodes that satisfy the objective. The graph is NOT executed or saved: your "
    "output is reviewed by the user."
)


def _catalog(registry: NodeRegistry) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for definition in sorted(registry.definitions(), key=lambda item: (item.category, item.type)):
        out.append({
            "type": definition.type,
            "version": definition.version,
            "category": definition.category,
            "label": definition.label,
            "description": str(definition.metadata.get("docs") or "")[:180],
            "inputs": [
                {"id": port.id, "type": port.type.value, "kind": port.kind.value,
                 "optional": port.optional}
                for port in definition.inputs
            ],
            "outputs": [
                {"id": port.id, "type": port.type.value, "kind": port.kind.value}
                for port in definition.outputs
            ],
            "config": {
                field.name: field.default
                for field in definition.config_fields
            },
            "sideEffects": definition.side_effects.value,
        })
    return out


def _slug(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_-]+", "-", value.strip()).strip("-")
    return cleaned[:64] or "node"


def _error(message: str, **detail: Any) -> dict[str, Any]:
    return {"message": message, **detail}


def _handle(value: Any) -> str:
    """A handle id from `"series"` or `{node, port}`; never a guessed port."""
    if isinstance(value, dict):
        return str(value.get("port") or value.get("handle") or value.get("id") or "")
    return str(value or "")


def validate_plan(
    raw: dict[str, Any],
    registry: NodeRegistry,
    *,
    workflow_id: Optional[str] = None,
) -> dict[str, Any]:
    """Build a WorkflowIR from a model proposal, or return diagnostics.

    Returns `{ok, ir?, errors, warnings}`. The IR is only present when every node,
    port, edge and config validated AND the compiler found no structural error.
    """
    errors: list[dict[str, Any]] = []
    warnings: list[str] = []
    if not isinstance(raw, dict):
        return {"ok": False, "errors": [_error("the plan is not a JSON object")], "warnings": []}

    raw_nodes = raw.get("nodes")
    raw_edges = raw.get("edges")
    if not isinstance(raw_nodes, list) or not raw_nodes:
        return {"ok": False, "errors": [_error("the plan has no nodes")], "warnings": []}
    if len(raw_nodes) > MAX_NODES:
        return {"ok": False, "errors": [_error(f"the plan exceeds {MAX_NODES} nodes")], "warnings": []}
    if not isinstance(raw_edges, list):
        raw_edges = []

    nodes: list[dict[str, Any]] = []
    used_ids: set[str] = set()
    needs_paper = False
    capabilities: set[str] = set()

    for index, item in enumerate(raw_nodes):
        if not isinstance(item, dict):
            errors.append(_error(f"node {index + 1} is not an object", index=index))
            continue
        node_type = str(item.get("type") or "").strip()
        definition = registry.get(node_type, str(item.get("version") or "") or None)
        if definition is None:
            errors.append(_error(f"unknown node type {node_type!r}", index=index))
            continue
        node_id = str(item.get("id") or "").strip()
        if not _ID.match(node_id) or node_id in used_ids:
            node_id = _slug(node_type) if _slug(node_type) not in used_ids else f"n{index + 1}"
        used_ids.add(node_id)
        config = coerce_config(definition, item.get("config") if isinstance(item.get("config"), dict) else {})
        problems = validate_config(definition, config)
        if problems:
            errors.append(_error(
                f'node "{node_id}" has an invalid config: {"; ".join(problems)}',
                index=index, nodeId=node_id,
            ))
            continue
        capabilities.update(definition.capabilities)
        needs_paper = needs_paper or definition.side_effects == SideEffect.TRADING
        nodes.append({
            "id": node_id,
            "type": definition.type,
            "version": definition.version,
            "label": str(item.get("label") or definition.label)[:120],
            "config": config,
            "layout": {"x": (index % 6) * 220, "y": (index // 6) * 160},
        })

    by_id = {node["id"]: node for node in nodes}
    edges: list[dict[str, Any]] = []
    used_edges: set[str] = set()
    for index, item in enumerate(raw_edges):
        if not isinstance(item, dict):
            errors.append(_error(f"edge {index + 1} is not an object", index=index))
            continue
        source_ref = item.get("source") or item.get("from") or ""
        target_ref = item.get("target") or item.get("to") or ""
        if isinstance(source_ref, dict):
            source = str(source_ref.get("node") or source_ref.get("id") or "")
        else:
            source = str(source_ref)
        if isinstance(target_ref, dict):
            target = str(target_ref.get("node") or target_ref.get("id") or "")
        else:
            target = str(target_ref)
        if source not in by_id or target not in by_id:
            errors.append(_error(f"edge {index + 1} references a missing node", index=index))
            continue
        source_handle = _handle(
            item.get("sourceHandle") or item.get("sourcePort")
            or item.get("fromPort") or item.get("fromHandle")
            or (source_ref.get("port") if isinstance(source_ref, dict) else None)
        )
        target_handle = _handle(
            item.get("targetHandle") or item.get("targetPort")
            or item.get("toPort") or item.get("toHandle")
            or (target_ref.get("port") if isinstance(target_ref, dict) else None)
        )
        source_def = registry.get(by_id[source]["type"])
        target_def = registry.get(by_id[target]["type"])
        source_port = source_def.output_port(source_handle) if source_def else None
        target_port = target_def.input_port(target_handle) if target_def else None
        if source_port is None or target_port is None:
            errors.append(_error(
                f"edge {index + 1} uses a port that does not exist on its node",
                index=index,
            ))
            continue
        if not ports_compatible(source_port, target_port):
            errors.append(_error(
                f"edge {index + 1} connects {source_port.type.value} to {target_port.type.value}",
                index=index,
            ))
            continue
        edge_id = str(item.get("id") or "").strip()
        if not _ID.match(edge_id) or edge_id in used_edges:
            edge_id = f"e{index + 1}"
        used_edges.add(edge_id)
        edges.append({
            "id": edge_id, "source": source, "sourceHandle": source_port.id,
            "target": target, "targetHandle": target_port.id,
        })

    if errors:
        return {"ok": False, "errors": errors, "warnings": warnings}

    mode = ExecutionMode.PAPER if needs_paper else ExecutionMode.RESEARCH
    ir = {
        "irVersion": 1,
        "id": workflow_id or f"wf_{uuid.uuid4().hex[:12]}",
        "name": str(raw.get("name") or raw.get("title") or "Generated workflow")[:120],
        "description": str(raw.get("summary") or "")[:800],
        "meta": {"createdAt": "", "updatedAt": "", "tags": ["generated"]},
        "nodes": nodes,
        "edges": edges,
        "settings": {
            "executionMode": mode.value,
            "failFast": False,
            "maxConcurrency": 4,
            "timeoutMs": 0,
        },
        "requiredCapabilities": sorted(capabilities),
    }
    raw_warnings = raw.get("warnings")
    if isinstance(raw_warnings, list):
        warnings.extend(str(item)[:300] for item in raw_warnings[:10])

    try:
        model = WorkflowIR.model_validate(ir)
    except Exception as exc:  # noqa: BLE001 - a schema failure is a proposal error
        errors.append(_error(f"the plan is not a valid workflow: {exc}"))
        return {"ok": False, "errors": errors, "warnings": warnings}

    from .compiler import RunGrants, compile_workflow  # noqa: PLC0415

    plan = compile_workflow(
        model, registry,
        RunGrants(
            test_run=False,
            granted_capabilities=frozenset(capabilities),
            allow_network=True,
            allow_trading=True,
        ),
    )
    structural = [item for item in plan.diagnostics if item.severity == "error"]
    for item in structural:
        errors.append(_error(item.message, code=item.code, nodeId=item.node_id))
    if errors:
        return {"ok": False, "errors": errors, "warnings": warnings}

    return {
        "ok": True,
        "ir": model.model_dump(by_alias=True),
        "errors": [],
        "warnings": warnings,
        "nodeCount": len(nodes),
        "edgeCount": len(edges),
        "executionMode": mode.value,
    }


async def plan_graph(
    objective: str,
    *,
    model_settings: Optional[dict[str, Any]],
    registry: NodeRegistry,
    workflow_id: Optional[str] = None,
) -> dict[str, Any]:
    text = str(objective or "").strip()
    if not text:
        raise ValueError("objective is required")
    if len(text) > 4_000:
        raise ValueError("objective exceeds 4 000 characters")
    if not model_settings:
        raise ValueError(
            "no model provider is configured; chat-to-graph needs a configured model"
        )
    try:
        settings = ModelSettings(**model_settings)
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"invalid model settings: {exc}") from exc

    from langchain_core.messages import HumanMessage, SystemMessage  # noqa: PLC0415

    catalog = _catalog(registry)
    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=json.dumps({
            "objective": text,
            "nodeCatalog": catalog,
            "limits": {"maxNodes": MAX_NODES, "maxEdges": MAX_EDGES},
        })),
    ]
    response = await get_runtime().generate(
        settings=settings,
        messages=messages,
        task="graph_plan",
        response_schema=PLAN_SCHEMA,
        timeout_s=120.0,
        temperature=0.1,
    )
    structured = (response.decision or {}).get("structured") or {}
    if not structured.get("ok"):
        reason = structured.get("validationError") or "the model returned no valid JSON plan"
        raise ValueError(f"graph plan was not a valid proposal: {reason}")
    result = validate_plan(structured.get("value") or {}, registry, workflow_id=workflow_id)
    result["model"] = {"provider": response.provider_id, "model": response.model_id}
    return result
