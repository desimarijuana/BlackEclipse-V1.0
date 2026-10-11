"""The strategy graph compiler: a typed node graph → the canonical Strategy IR.

Pipeline (deterministic for equivalent graphs + compiler version):

  1. parse & shape-check the graph,
  2. resolve node types + versions from the registry,
  3. validate ports, connections and port types,
  4. topologically order nodes (cycle detection),
  5. compile each node to an IR fragment,
  6. assemble the `StrategySpec` and run the shared `validate_strategy`,
  7. return diagnostics + a source map (spec path → node id).

The output is the SAME `StrategySpec` the Python lab and AI copilot produce — the
graph is only an authoring front. This is deliberately NOT a general workflow
engine: strategy schemas, compilation and validation stay separate from the
future workflow editor.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional, Union

from .graph_model import GRAPH_SCHEMA_VERSION, StrategyGraph, parse_graph
from .nodes import (
    CompileContext,
    Diagnostic,
    NodeDef,
    NodeRegistry,
    REGISTRY,
    T_ANY,
)
from .schema import parse_schema_version
from .strategy import (
    EntryRules,
    ExecutionAssumptions,
    ExitRules,
    PositionSizing,
    Rules,
    StrategySpec,
    Timeframes,
    Universe,
    validate_strategy,
)


@dataclass
class CompileResult:
    ok: bool
    spec: Optional[StrategySpec]
    diagnostics: list[Diagnostic] = field(default_factory=list)
    source_map: dict[str, str] = field(default_factory=dict)
    ordering: list[str] = field(default_factory=list)
    graph: Optional[StrategyGraph] = None

    def errors(self) -> list[Diagnostic]:
        return [d for d in self.diagnostics if d.severity == "error"]

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "spec": self.spec.to_dict() if self.spec else None,
            "diagnostics": [d.to_dict() for d in self.diagnostics],
            "sourceMap": self.source_map,
            "ordering": self.ordering,
        }


def _graph_schema_ok(version: str) -> bool:
    try:
        return parse_schema_version(version)[0] == parse_schema_version(GRAPH_SCHEMA_VERSION)[0]
    except ValueError:
        return False


def _resolve_nodes(graph: StrategyGraph, registry: NodeRegistry,
                   diags: list[Diagnostic]) -> dict[str, NodeDef]:
    defs: dict[str, NodeDef] = {}
    seen: set[str] = set()
    for node in graph.nodes:
        if node.id in seen:
            diags.append(Diagnostic("DUPLICATE_NODE_ID", f"duplicate node id {node.id!r}", node.id))
            continue
        seen.add(node.id)
        definition = registry.get(node.type)
        if definition is None:
            diags.append(Diagnostic(
                "UNKNOWN_NODE_TYPE",
                f"unknown node type {node.type!r}; known: {registry.types()}", node.id))
            continue
        if not NodeRegistry.version_supported(node.version, definition.version):
            diags.append(Diagnostic(
                "UNSUPPORTED_NODE_VERSION",
                f"node {node.type!r} version {node.version!r} unsupported "
                f"(runtime has {definition.version})", node.id))
            continue
        defs[node.id] = definition
    return defs


def _topo_order(graph: StrategyGraph, defs: dict[str, NodeDef],
                incoming: dict[str, set[str]], diags: list[Diagnostic]) -> list[str]:
    """Deterministic topological order; detects cycles. Only known nodes."""
    ids = sorted(defs)
    indeg = {nid: len(incoming.get(nid, set())) for nid in ids}
    ready = sorted([nid for nid in ids if indeg[nid] == 0])
    order: list[str] = []
    adjacency: dict[str, list[str]] = {nid: [] for nid in ids}
    for edge in graph.edges:
        if edge.from_node in defs and edge.to_node in defs:
            adjacency[edge.from_node].append(edge.to_node)
    while ready:
        nid = ready.pop(0)
        order.append(nid)
        for nxt in sorted(adjacency[nid]):
            indeg[nxt] -= 1
            if indeg[nxt] == 0:
                ready.append(nxt)
                ready.sort()
    if len(order) != len(ids):
        cyclic = sorted(set(ids) - set(order))
        diags.append(Diagnostic("CYCLE_DETECTED",
                                f"cycle detected among nodes: {cyclic}", cyclic[0] if cyclic else ""))
    return order


def _validate_edges(graph: StrategyGraph, defs: dict[str, NodeDef],
                    diags: list[Diagnostic]) -> tuple[dict[str, set[str]], dict[str, dict[str, list[Any]]]]:
    """Validate edges; return incoming-id sets and a per-target input map."""
    incoming: dict[str, set[str]] = {}
    # target_node -> input_port -> list of source nodes (order preserved)
    input_map: dict[str, dict[str, list[str]]] = {}
    for i, edge in enumerate(graph.edges):
        src = defs.get(edge.from_node)
        dst = defs.get(edge.to_node)
        if edge.from_node not in defs:
            diags.append(Diagnostic("UNKNOWN_EDGE_NODE",
                                    f"edge {i} source {edge.from_node!r} is not a known node",
                                    edge.from_node))
            continue
        if dst is None:
            diags.append(Diagnostic("UNKNOWN_EDGE_NODE",
                                    f"edge {i} target {edge.to_node!r} is not a known node",
                                    edge.to_node))
            continue
        out_port = src.out_port(edge.from_port)  # type: ignore[union-attr]
        in_port = dst.in_port(edge.to_port)
        if out_port is None:
            diags.append(Diagnostic("UNKNOWN_PORT",
                                    f"node {edge.from_node!r} has no output {edge.from_port!r}",
                                    edge.from_node))
            continue
        if in_port is None:
            diags.append(Diagnostic("UNKNOWN_PORT",
                                    f"node {edge.to_node!r} has no input {edge.to_port!r}",
                                    edge.to_node))
            continue
        if in_port.type != T_ANY and out_port.type != in_port.type:
            diags.append(Diagnostic(
                "TYPE_MISMATCH",
                f"cannot connect {out_port.type} output {edge.from_node}.{edge.from_port} "
                f"to {in_port.type} input {edge.to_node}.{edge.to_port}", edge.to_node))
            continue
        incoming.setdefault(edge.to_node, set()).add(edge.from_node)
        input_map.setdefault(edge.to_node, {}).setdefault(edge.to_port, []).append(edge.from_node)
    return incoming, input_map


def compile_graph(
    source: Union[str, dict[str, Any], StrategyGraph],
    *,
    registry: NodeRegistry = REGISTRY,
) -> CompileResult:
    """Compile a strategy graph into a `StrategySpec`, with diagnostics."""
    diags: list[Diagnostic] = []
    if isinstance(source, StrategyGraph):
        graph = source
    else:
        try:
            graph = parse_graph(source)
        except Exception as exc:  # noqa: BLE001
            return CompileResult(False, None,
                                 [Diagnostic("INVALID_GRAPH", str(exc))])

    if not _graph_schema_ok(graph.schema_version):
        return CompileResult(False, None, [Diagnostic(
            "UNSUPPORTED_GRAPH_SCHEMA",
            f"graph schema {graph.schema_version!r} is not supported "
            f"(runtime {GRAPH_SCHEMA_VERSION})")], graph=graph)

    defs = _resolve_nodes(graph, registry, diags)
    incoming, input_map = _validate_edges(graph, defs, diags)
    order = _topo_order(graph, defs, incoming, diags)

    # Compile in dependency order, threading resolved output values.
    ctx = CompileContext()
    outputs: dict[str, dict[str, Any]] = {}
    node_by_id = {n.id: n for n in graph.nodes}
    for nid in order:
        node = node_by_id[nid]
        definition = defs[nid]
        # Gather resolved inputs (variadic ports collect every connected value).
        resolved: dict[str, list[Any]] = {}
        for port_name, sources in input_map.get(nid, {}).items():
            resolved[port_name] = [
                outputs.get(src, {}).get(next(
                    (e.from_port for e in graph.edges
                     if e.from_node == src and e.to_node == nid and e.to_port == port_name), "out"))
                for src in sources
            ]
        # Required-input check.
        for port in definition.inputs:
            if port.required and not port.variadic and not resolved.get(port.name):
                ctx.error("MISSING_INPUT", f"node {definition.type_id} input {port.name!r} "
                                           "is not connected", nid)
        try:
            outputs[nid] = definition.compile(ctx, node, resolved) or {}
        except Exception as exc:  # noqa: BLE001
            ctx.error("NODE_COMPILE_ERROR",
                      f"{definition.type_id} failed to compile: {exc}", nid)

    diags.extend(ctx.diagnostics)

    # Assemble the IR.
    try:
        execution = ExecutionAssumptions.model_validate(graph.metadata.get("execution") or {})
    except Exception:  # noqa: BLE001
        execution = ExecutionAssumptions()
        diags.append(Diagnostic("BAD_CONFIG", "invalid execution assumptions in metadata",
                                severity="warning"))
    spec = StrategySpec(
        id=graph.strategy.id, name=graph.strategy.name, version=graph.strategy.version,
        description=graph.strategy.description, asset_class=graph.strategy.asset_class,
        universe=Universe(asset_classes=ctx.asset_classes, symbols=ctx.symbols),
        timeframes=Timeframes(primary=ctx.primary_tf, confirmation=ctx.confirmation_tfs),
        indicators=ctx.indicators,
        rules=Rules(
            entry=EntryRules(long=ctx.entry.get("long"), short=ctx.entry.get("short")),
            exit=ExitRules(long=ctx.exit.get("long"), short=ctx.exit.get("short"),
                           stop_loss=ctx.stop_loss, take_profit=ctx.take_profit,
                           trailing_stop=ctx.trailing_stop, time_stop_bars=ctx.time_stop_bars),
        ),
        risk=ctx.risk,
        position_sizing=ctx.sizing or PositionSizing(),
        execution=execution,
    )
    for issue in validate_strategy(spec):
        diags.append(Diagnostic(issue.code, issue.message, "", issue.path, issue.severity))

    ok = not [d for d in diags if d.severity == "error"]
    return CompileResult(ok, spec, diags, dict(ctx.source_map), order, graph)


__all__ = ["CompileResult", "compile_graph"]
