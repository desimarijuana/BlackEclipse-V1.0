"""Working-copy session and read/mutate tools for the graph assistant.

The agent loop in ``assistant.py`` owns the model conversation; this module owns
the bounded edits it is allowed to make. Keeping them apart keeps each file under
the harness size ceiling and makes the tool contract testable on its own.
"""

from __future__ import annotations

import re
from typing import Any, Optional

from .assistant_constants import MAX_ASSIST_NODES, MAX_ASSIST_OPS, MAX_ASSIST_RUNS
from .model import (
    Diagnostic,
    ExecutionMode,
    NodePosition,
    PortKind,
    SideEffect,
    WorkflowEdge,
    WorkflowIR,
    WorkflowNode,
)
from .registry import (
    NodeDef,
    NodeRegistry,
    coerce_config,
    ports_compatible,
    validate_config,
)
_ID = re.compile(r"^[A-Za-z0-9_-]{1,80}$")


def _slug(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", value).strip("_")[:40] or "node"


def _dump(diagnostic: Diagnostic) -> dict[str, Any]:
    return {
        "severity": diagnostic.severity.value,
        "code": diagnostic.code,
        "message": diagnostic.message,
        "nodeId": diagnostic.node_id,
        "edgeId": diagnostic.edge_id,
    }


_ALIAS_TARGETS: dict[str, tuple[str, ...]] = {
    "api": ("integration.http",),
    "rest": ("integration.http",),
    "fetch": ("integration.http",),
    "http": ("integration.http",),
    "webhook": ("trigger.webhook",),
    "cron": ("trigger.schedule",),
    "schedule": ("trigger.schedule",),
    "sma": ("finance.indicator",),
    "ema": ("finance.indicator",),
    "rsi": ("finance.indicator",),
    "macd": ("finance.indicator",),
    "indicator": ("finance.indicator",),
    "filter": ("logic.filter",),
    "where": ("logic.filter",),
    "map": ("logic.map", "transform.select"),
    "join": ("transform.join",),
    "merge": ("logic.merge",),
    "agent": ("agent.research", "agent.bot"),
    "llm": ("agent.research",),
    "research": ("agent.research", "research.report"),
    "notify": ("output.notify",),
    "alert": ("output.notify",),
    "chart": ("output.chart",),
    "plot": ("output.chart",),
    "upload": ("data.file.attach",),
    "file": ("data.file.attach", "data.file.parse"),
}


class GraphAssistantSession:
    """One edit session over a working copy of the IR.

    Every mutating tool changes `self.ir` through the same rules as the editor's
    patch layer and records the equivalent operation in `self.ops`. The caller
    receives both, so the client can apply the ops atomically while the server
    keeps a validated document for verification.
    """

    def __init__(
        self,
        ir: WorkflowIR,
        registry: NodeRegistry,
        *,
        runner: Optional[Callable[[WorkflowIR], Awaitable[dict[str, Any]]]] = None,
    ) -> None:
        self.ir = ir
        self.registry = registry
        self.runner = runner
        self.ops: list[dict[str, Any]] = []
        self.warnings: list[str] = []
        self.question: Optional[str] = None
        self.focus: set[str] = set()
        self.run_log: list[dict[str, Any]] = []
        self.runs_used = 0
        self._added = 0

    # -- helpers ------------------------------------------------------------

    def _def(self, node_type: str, version: Optional[str] = None) -> Optional[NodeDef]:
        return self.registry.get(node_type, version or None)

    def _node(self, node_id: str) -> Optional[WorkflowNode]:
        return self.ir.node(node_id)

    def _unique_id(self, base: str) -> str:
        used = {node.id for node in self.ir.nodes}
        if base not in used and _ID.match(base):
            return base
        stem = _slug(base)[:60] or "node"
        for index in range(1, 10_000):
            candidate = f"{stem}_{index}"
            if candidate not in used:
                return candidate
        raise ValueError("could not allocate a node id")

    def _touch(self) -> None:
        caps: set[str] = set()
        for node in self.ir.nodes:
            definition = self._def(node.type, node.version)
            if definition is not None:
                caps.update(definition.capabilities)
        self.ir.required_capabilities = sorted(caps)

    def _cycle(self, source: str, target: str) -> bool:
        if source == target:
            return True
        adjacency: dict[str, list[str]] = {node.id: [] for node in self.ir.nodes}
        for edge in self.ir.edges:
            adjacency.setdefault(edge.source, []).append(edge.target)
        stack = [target]
        seen: set[str] = set()
        while stack:
            current = stack.pop()
            if current == source:
                return True
            if current in seen:
                continue
            seen.add(current)
            stack.extend(adjacency.get(current, []))
        return False

    def _over_budget(self) -> bool:
        return len(self.ops) >= MAX_ASSIST_OPS

    def _budget_error(self) -> dict[str, Any]:
        return {
            "ok": False,
            "error": f"edit limit reached ({MAX_ASSIST_OPS} operations per turn); finish with what you have",
        }

    def _edge_exists(self, source: str, source_port: str, target: str, target_port: str) -> bool:
        return any(
            edge.source == source
            and edge.source_handle == source_port
            and edge.target == target
            and edge.target_handle == target_port
            for edge in self.ir.edges
        )

    def _new_edge_id(self) -> str:
        used = {edge.id for edge in self.ir.edges}
        for index in range(1, 100_000):
            candidate = f"e_assist_{index}"
            if candidate not in used:
                return candidate
        raise ValueError("could not allocate an edge id")

    def _add_edge(self, source: str, source_port: str, target: str, target_port: str) -> str:
        edge_id = self._new_edge_id()
        edge = WorkflowEdge(
            id=edge_id,
            source=source,
            source_handle=source_port,
            target=target,
            target_handle=target_port,
        )
        self.ir.edges.append(edge)
        self.ops.append({
            "op": "add_edge",
            "edge": {
                "id": edge_id,
                "source": source,
                "sourceHandle": source_port,
                "target": target,
                "targetHandle": target_port,
            },
        })
        return edge_id

    # -- read tools ---------------------------------------------------------

    def search_nodes(self, query: str, limit: int = 8) -> dict[str, Any]:
        needle = str(query or "").strip().lower()
        if not needle:
            return {"ok": False, "error": "query is required"}
        terms = [part for part in re.split(r"\s+", needle) if len(part) >= 2]
        aliases: set[str] = set()
        for term in terms:
            aliases.update(_ALIAS_TARGETS.get(term, ()))
        ranked: list[tuple[int, NodeDef]] = []
        for definition in self.registry.definitions():
            haystack = " ".join([
                definition.type,
                definition.label,
                definition.category,
                str(getattr(definition, "metadata", {}).get("docs") or ""),
                " ".join(port.name for port in definition.inputs),
                " ".join(port.name for port in definition.outputs),
            ]).lower()
            score = 6 if definition.type in aliases else 0
            for term in terms:
                if term in definition.type.lower():
                    score += 5
                if term in definition.label.lower():
                    score += 4
                if term in haystack:
                    score += 2
            if score > 0:
                ranked.append((score, definition))
        ranked.sort(key=lambda item: (-item[0], item[1].type))
        out = [
            {
                "type": definition.type,
                "version": definition.version,
                "label": definition.label,
                "category": definition.category,
                "description": str(
                    getattr(definition, "metadata", {}).get("docs") or ""
                )[:180],
                "sideEffects": definition.side_effects.value,
            }
            for _score, definition in ranked[:max(1, min(int(limit or 8), 25))]
        ]
        if not out:
            return {
                "ok": True,
                "nodes": [],
                "note": "No registered node matched. Try a broader description or ask the user.",
            }
        return {"ok": True, "nodes": out}

    def get_node_schema(self, node_type: str, version: Optional[str] = None) -> dict[str, Any]:
        definition = self._def(str(node_type or ""), version)
        if definition is None:
            return {"ok": False, "error": f"unknown node type {node_type!r}"}
        return {
            "ok": True,
            "node": {
                "type": definition.type,
                "version": definition.version,
                "label": definition.label,
                "category": definition.category,
                "sideEffects": definition.side_effects.value,
                "capabilities": list(definition.capabilities),
                "allowedModes": [mode.value for mode in definition.allowed_modes],
                "inputs": [
                    {"id": port.id, "name": port.name, "type": port.type.value,
                     "kind": port.kind.value, "optional": port.optional}
                    for port in definition.inputs
                ],
                "outputs": [
                    {"id": port.id, "name": port.name, "type": port.type.value,
                     "kind": port.kind.value}
                    for port in definition.outputs
                ],
                "config": [
                    {
                        "name": field.name,
                        "kind": field.kind,
                        "default": field.default,
                        "enum": list(field.enum),
                        "minimum": field.minimum,
                        "maximum": field.maximum,
                        "maxLength": field.max_length,
                    }
                    for field in definition.config_fields
                ],
            },
        }

    def validate_graph(self) -> dict[str, Any]:
        diagnostics = self._compile()
        return {
            "ok": not any(item.severity.value == "error" for item in diagnostics),
            "diagnostics": [_dump(item) for item in diagnostics],
        }

    # -- write tools --------------------------------------------------------

    def add_node(
        self,
        node_type: str,
        *,
        version: Optional[str] = None,
        label: Optional[str] = None,
        config: Optional[dict[str, Any]] = None,
        node_id: Optional[str] = None,
        after_node_id: Optional[str] = None,
        source_port: Optional[str] = None,
    ) -> dict[str, Any]:
        if self._over_budget():
            return self._budget_error()
        if len(self.ir.nodes) >= MAX_ASSIST_NODES:
            return {"ok": False, "error": f"the workflow already has {MAX_ASSIST_NODES} nodes"}
        definition = self._def(str(node_type or ""), version)
        if definition is None:
            return {"ok": False, "error": f"unknown node type {node_type!r}; call search_nodes first"}
        merged = coerce_config(definition, dict(config or {}))
        problems = validate_config(definition, merged)
        if problems:
            return {"ok": False, "error": "invalid config: " + "; ".join(problems)}

        requested = str(node_id or "").strip()
        new_id = self._unique_id(requested or f"n_{_slug(definition.type)}_{self._added + 1}")
        self._added += 1

        position = self._next_position(after_node_id)
        node = WorkflowNode(
            id=new_id,
            type=definition.type,
            version=definition.version,
            label=str(label).strip()[:120] if label else None,
            config=merged,
            layout=NodePosition(x=position["x"], y=position["y"]),
        )
        self.ir.nodes.append(node)
        self.ops.append({
            "op": "add_node",
            "node": {
                "id": new_id,
                "type": node.type,
                "version": node.version,
                **({"label": node.label} if node.label else {}),
                "config": merged,
                "layout": {"x": node.layout.x, "y": node.layout.y},
            },
        })
        self.focus.add(new_id)
        self._touch()

        result: dict[str, Any] = {"ok": True, "nodeId": new_id, "type": definition.type}
        if after_node_id:
            wired = self._auto_wire(str(after_node_id), new_id, source_port)
            if wired.get("ok"):
                result["edge"] = wired["edge"]
            else:
                result["warning"] = wired.get("error", "could not auto-wire")
        return result

    def _next_position(self, after_node_id: Optional[str]) -> dict[str, float]:
        if after_node_id:
            anchor = self._node(str(after_node_id))
            if anchor is not None:
                return {"x": anchor.layout.x + 300, "y": anchor.layout.y}
        index = len(self.ir.nodes)
        return {"x": 120 + (index % 5) * 80, "y": 100 + (index // 5) * 140}

    def _auto_wire(self, source: str, target: str, source_port: Optional[str]) -> dict[str, Any]:
        source_node = self._node(source)
        target_node = self._node(target)
        if source_node is None or target_node is None:
            return {"ok": False, "error": "auto-wire needs an existing source"}
        source_def = self._def(source_node.type, source_node.version)
        target_def = self._def(target_node.type, target_node.version)
        if source_def is None or target_def is None:
            return {"ok": False, "error": "auto-wire could not resolve a node type"}
        outputs = source_def.outputs
        if source_port:
            outputs = tuple(port for port in outputs if port.id == source_port) or outputs
        # Prefer an explicit control wire, then an exact data-type match, and
        # only fall back to an `any` port. Never pick a pair merely because it is
        # the first one the registry happens to declare.
        scored: list[tuple[int, Any, Any]] = []
        for out_port in outputs:
            for in_port in target_def.inputs:
                if not ports_compatible(out_port, in_port):
                    continue
                if out_port.kind is PortKind.CONTROL and in_port.kind is PortKind.CONTROL:
                    score = 10
                elif out_port.type == in_port.type:
                    score = 5
                else:
                    score = 1
                scored.append((score, out_port, in_port))
        if not scored:
            return {"ok": False, "error": "no compatible port pair; connect manually"}
        scored.sort(key=lambda item: -item[0])
        _score, out_port, in_port = scored[0]
        edge_id = self._add_edge(source, out_port.id, target, in_port.id)
        return {
            "ok": True,
            "edge": {
                "id": edge_id,
                "source": source,
                "sourceHandle": out_port.id,
                "target": target,
                "targetHandle": in_port.id,
            },
        }

    def connect_nodes(self, source: str, source_port: str, target: str, target_port: str) -> dict[str, Any]:
        if self._over_budget():
            return self._budget_error()
        source_node = self._node(str(source))
        target_node = self._node(str(target))
        if source_node is None or target_node is None:
            return {"ok": False, "error": "source or target node does not exist"}
        source_def = self._def(source_node.type, source_node.version)
        target_def = self._def(target_node.type, target_node.version)
        if source_def is None or target_def is None:
            return {"ok": False, "error": "could not resolve a node type"}
        out_port = next((port for port in source_def.outputs if port.id == source_port), None)
        in_port = next((port for port in target_def.inputs if port.id == target_port), None)
        if out_port is None:
            return {"ok": False, "error": f"{source_node.type} has no output {source_port!r}"}
        if in_port is None:
            return {"ok": False, "error": f"{target_node.type} has no input {target_port!r}"}
        if not ports_compatible(out_port, in_port):
            return {
                "ok": False,
                "error": (
                    f"{out_port.type.value}/{out_port.kind.value} cannot connect to "
                    f"{in_port.type.value}/{in_port.kind.value}"
                ),
            }
        if self._edge_exists(source, source_port, target, target_port):
            return {"ok": False, "error": "that connection already exists"}
        if self._cycle(source, target):
            return {"ok": False, "error": "that connection would create a cycle"}
        edge_id = self._add_edge(source, source_port, target, target_port)
        return {
            "ok": True,
            "edge": {
                "id": edge_id,
                "source": source,
                "sourceHandle": source_port,
                "target": target,
                "targetHandle": target_port,
            },
        }

    def update_node_config(self, node_id: str, config: dict[str, Any]) -> dict[str, Any]:
        if self._over_budget():
            return self._budget_error()
        node = self._node(str(node_id))
        if node is None:
            return {"ok": False, "error": f"node {node_id!r} does not exist"}
        definition = self._def(node.type, node.version)
        if definition is None:
            return {"ok": False, "error": f"unknown node type {node.type!r}"}
        merged = coerce_config(definition, {**(node.config or {}), **dict(config or {})})
        problems = validate_config(definition, merged)
        if problems:
            return {"ok": False, "error": "invalid config: " + "; ".join(problems)}
        node.config = merged
        self.ops.append({"op": "update_node_config", "nodeId": node.id, "config": merged})
        self._touch()
        return {"ok": True, "nodeId": node.id, "config": merged}

    def remove_node(self, node_id: str) -> dict[str, Any]:
        if self._over_budget():
            return self._budget_error()
        node = self._node(str(node_id))
        if node is None:
            return {"ok": False, "error": f"node {node_id!r} does not exist"}
        self.ir.nodes = [item for item in self.ir.nodes if item.id != node.id]
        self.ir.edges = [
            edge for edge in self.ir.edges
            if edge.source != node.id and edge.target != node.id
        ]
        self.ops.append({"op": "remove_node", "nodeId": node.id})
        self.focus.discard(node.id)
        self._touch()
        return {"ok": True, "nodeId": node.id}

    def rename_node(self, node_id: str, label: Optional[str] = None) -> dict[str, Any]:
        if self._over_budget():
            return self._budget_error()
        node = self._node(str(node_id))
        if node is None:
            return {"ok": False, "error": f"node {node_id!r} does not exist"}
        cleaned = str(label).strip()[:120] if label else None
        node.label = cleaned or None
        self.ops.append({"op": "update_node_label", "nodeId": node.id, "label": cleaned})
        return {"ok": True, "nodeId": node.id, "label": cleaned}

    def ask_user(self, question: str) -> dict[str, Any]:
        self.question = str(question).strip()[:800]
        return {"ok": True, "question": self.question, "stop": True}

    async def run_workflow(self) -> dict[str, Any]:
        if self.runner is None:
            return {"ok": False, "error": "running the workflow is not available in this surface"}
        if self.runs_used >= MAX_ASSIST_RUNS:
            return {
                "ok": False,
                "error": f"run limit reached ({MAX_ASSIST_RUNS} test runs per turn); finish with what you have",
            }
        self.runs_used += 1
        try:
            result = await self.runner(self.ir)
        except Exception as exc:  # noqa: BLE001 - a failed run is data for the model
            result = {"ok": False, "status": "error", "error": str(exc)[:500]}
        self.run_log.append({"run": self.runs_used, **result})
        compact = {
            key: result.get(key)
            for key in ("ok", "status", "error", "failed", "diagnostics")
            if result.get(key) not in (None, [], "")
        }
        output = result.get("output")
        if output is not None:
            compact["outputPreview"] = json.dumps(output, default=str)[:2_000]
        return compact

    # -- compile ------------------------------------------------------------

    def _compile(self) -> list[Diagnostic]:
        if not self.ir.nodes:
            return []
        try:
            from .compiler import RunGrants, compile_workflow  # noqa: PLC0415

            plan = compile_workflow(
                self.ir,
                self.registry,
                RunGrants(
                    test_run=False,
                    granted_capabilities=frozenset(self.ir.required_capabilities),
                    allow_network=True,
                    allow_trading=True,
                    allow_write=True,
                ),
            )
            return list(plan.diagnostics)
        except Exception as exc:  # noqa: BLE001 - never lose the session on a compile failure
            return [
                Diagnostic(
                    severity="error",
                    code="assistant_compile_failed",
                    message=str(exc),
                )
            ]

    def finalize(self) -> tuple[bool, list[Diagnostic]]:
        self._touch()
        # A graph with trading nodes cannot validate in research/backtest mode.
        # Switch to paper explicitly and tell the user, rather than producing a
        # document the runtime will refuse.
        if any(
            (definition := self._def(node.type, node.version)) is not None
            and definition.side_effects is SideEffect.TRADING
            for node in self.ir.nodes
        ):
            if self.ir.settings.execution_mode in (ExecutionMode.RESEARCH, ExecutionMode.BACKTEST):
                self.ir.settings.execution_mode = ExecutionMode.PAPER
                self.ops.append({
                    "op": "set_settings",
                    "settings": {"executionMode": ExecutionMode.PAPER.value},
                })
                self.warnings.append("Trading nodes require paper mode; switched the workflow to paper.")

        diagnostics = self._compile()
        has_error = any(item.severity.value == "error" for item in diagnostics)
        self.ir.required_capabilities = sorted(self.ir.required_capabilities)
        return (not has_error, diagnostics)


