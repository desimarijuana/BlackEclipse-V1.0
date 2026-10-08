"""Structured aggregation for aggregate/join nodes.

Aggregation is NOT string concatenation. An aggregate node receives the structured
output of each of its dependencies, keyed by node id, alongside the per-dependency
status, and returns a structured object. A failed dependency is represented as
data (`errors`), never dropped and never converted into a success.
"""

from __future__ import annotations

from typing import Any, Optional

from .models import ExecutionGraph, ExecutionNode, TaskStatus


def collect_inputs(graph: ExecutionGraph, node: ExecutionNode) -> dict[str, Any]:
    """The structured inputs an aggregate/join node receives."""
    items: list[dict[str, Any]] = []
    outputs: dict[str, Any] = {}
    errors: dict[str, Any] = {}
    for dep_id in node.dependencies:
        dep = graph.nodes.get(dep_id)
        if dep is None:
            continue
        entry = {
            "id": dep_id,
            "kind": dep.kind.value,
            "status": dep.status.value,
            "output": dep.output,
            "error": dep.error.to_dict() if dep.error else None,
        }
        items.append(entry)
        if dep.status is TaskStatus.COMPLETED:
            outputs[dep_id] = dep.output
        elif dep.error is not None:
            errors[dep_id] = dep.error.to_dict()
    completed = sum(1 for i in items if i["status"] == TaskStatus.COMPLETED.value)
    return {
        "items": items,
        "outputs": outputs,
        "errors": errors,
        "total": len(items),
        "completed": completed,
        "complete": completed == len(items) and len(items) > 0,
    }


def aggregate(graph: ExecutionGraph, node: ExecutionNode, collected: Optional[dict[str, Any]] = None) -> Any:
    """Combine dependency outputs per the node's declared `mode`.

    Modes (node.input['mode']):
      * `list` (default) — the structured collection above;
      * `merge` — outputs merged into one dict (later dependencies win on conflict);
      * `concat` — outputs joined as text for a prose answer, with errors noted;
      * `claims` — a claim/evidence-shaped collection for research pipelines.
    """
    data = collected if collected is not None else collect_inputs(graph, node)
    mode = str((node.input or {}).get("mode") or "list").lower()
    if mode == "merge":
        merged: dict[str, Any] = {}
        for value in data["outputs"].values():
            if isinstance(value, dict):
                merged.update(value)
        return {"merged": merged, "sources": sorted(data["outputs"].keys()),
                "errors": data["errors"], "complete": data["complete"]}
    if mode == "concat":
        parts: list[str] = []
        for entry in data["items"]:
            if entry["status"] == TaskStatus.COMPLETED.value and entry["output"] is not None:
                parts.append(str(entry["output"]))
            elif entry["error"]:
                parts.append(f"[{entry['id']} failed: {entry['error'].get('code', 'ERROR')}]")
        text = "\n\n".join(parts)
        if not data["complete"] and data["errors"]:
            text += f"\n\n[{len(data['errors'])} part(s) could not be completed.]"
        return {"text": text, "complete": data["complete"], "errors": data["errors"]}
    if mode == "claims":
        claims: list[dict[str, Any]] = []
        for entry in data["items"]:
            claims.append({
                "sourceId": entry["id"],
                "status": entry["status"],
                "claims": entry["output"],
                "error": entry["error"],
            })
        return {"claims": claims, "complete": data["complete"],
                "coverage": (data["completed"] / data["total"]) if data["total"] else 1.0,
                "errors": data["errors"]}
    return data


__all__ = ["aggregate", "collect_inputs"]
