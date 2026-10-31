"""Graph compiler — IR → execution plan.

Pure and side-effect free: it reads the IR + registry and returns a plan plus
every diagnostic it found. It never runs anything, never touches the network and
never writes to a store, so it is trivially testable and safe to call on
untrusted input.

The compiler is where AUTHORIZATION first bites on the runtime side: a node whose
side-effect class or capabilities exceed the run's granted envelope is refused
with an explicit diagnostic, regardless of what the editor showed the user.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .model import (
    Diagnostic,
    ExecutionMode,
    ExecutionPlan,
    MAX_SUBWORKFLOW_DEPTH,
    NodeStatus,  # noqa: F401 - re-exported for convenience by callers importing from compiler
    PlanNode,
    PortType,
    Severity,
    SideEffect,
    SUPPORTED_IR_VERSIONS,
    WorkflowIR,
)
from .registry import (
    NodeDef,
    NodeRegistry,
    coerce_config,
    ports_compatible,
    validate_config,
)

# The side-effect classes a plain TEST run may never perform, no matter what the
# caller asks for. Test runs exist to prove a graph works, not to act on the
# world.
_ALWAYS_DENIED_IN_TEST = (SideEffect.WRITE, SideEffect.NETWORK, SideEffect.TRADING)

# Capabilities a TEST run grants implicitly: reading market data and computing
# locally cannot change anything, so they do not need an operator grant. Every
# capability that implies an EFFECT still must be granted explicitly.
TEST_RUN_CAPABILITIES = frozenset({
    "compute.safe",
    "quant.compute",
    "market.read",
    # Local scratch datasets are not world effects. The store enforces size,
    # count and TTL limits, so a test run may use them.
    "dataset.read",
    "dataset.write",
    # Local evidence reads cannot affect the world.
    "research.read",
    # A model call is not a world effect. Its tool surface is narrowed by the
    # agent runner for a test run, so it cannot reach web/write/trade tools.
    "agent.run",
    # Broker reads (account/quote/bars) cannot change anything.
    "trading.broker.read",
})


@dataclass(frozen=True)
class RunGrants:
    """The authority a run carries. Defaults are the weakest possible: a test
    run with no capabilities, no network, no trading."""

    test_run: bool = True
    granted_capabilities: frozenset[str] = field(default_factory=frozenset)
    allow_network: bool = False
    allow_trading: bool = False
    # A LOCAL write (video render → files + artifact). The front door only grants
    # it for the whitelisted local render node, never for an external write.
    allow_write: bool = False
    # Named scopes a file.write node may use. The front door derives this from
    # the IR + the operator's explicit confirmation; an empty set writes nothing.
    allowed_write_scopes: frozenset[str] = field(default_factory=frozenset)
    # The explicit operator confirmation for LIVE broker execution. Paper remains
    # governed by `allow_trading`.
    allow_live_trading: bool = False


def _error(code: str, message: str, node_id: Optional[str] = None, edge_id: Optional[str] = None) -> Diagnostic:
    return Diagnostic(severity=Severity.ERROR, code=code, message=message, nodeId=node_id, edgeId=edge_id)


def _warn(code: str, message: str, node_id: Optional[str] = None, edge_id: Optional[str] = None) -> Diagnostic:
    return Diagnostic(severity=Severity.WARNING, code=code, message=message, nodeId=node_id, edgeId=edge_id)


def _layers(ir: WorkflowIR, order: list[str]) -> list[list[str]]:
    """Longest-path layering over the given topological order. Nodes in one
    layer have no dependency between them and are the parallelizable set."""
    depth: dict[str, int] = {node.id: 0 for node in ir.nodes}
    incoming: dict[str, list[str]] = {node.id: [] for node in ir.nodes}
    for edge in ir.edges:
        if edge.source in incoming and edge.target in incoming:
            incoming[edge.target].append(edge.source)
    for node_id in order:
        for parent in incoming.get(node_id, []):
            depth[node_id] = max(depth[node_id], depth.get(parent, 0) + 1)
    grouped: dict[int, list[str]] = {}
    for node_id in order:
        grouped.setdefault(depth[node_id], []).append(node_id)
    return [sorted(grouped[level]) for level in sorted(grouped)]


def _topological_order(ir: WorkflowIR) -> Optional[list[str]]:
    """Kahn's algorithm with a deterministic (sorted) tie-break. Returns None if
    the graph contains a cycle."""
    indegree: dict[str, int] = {node.id: 0 for node in ir.nodes}
    adjacency: dict[str, list[str]] = {node.id: [] for node in ir.nodes}
    for edge in ir.edges:
        if edge.source in adjacency and edge.target in indegree:
            adjacency[edge.source].append(edge.target)
            indegree[edge.target] += 1
    ready = sorted(node_id for node_id, degree in indegree.items() if degree == 0)
    order: list[str] = []
    while ready:
        node_id = ready.pop(0)
        order.append(node_id)
        for child in adjacency.get(node_id, []):
            indegree[child] -= 1
            if indegree[child] == 0:
                ready.append(child)
                ready.sort()
    return order if len(order) == len(ir.nodes) else None


def compile_workflow(
    ir: WorkflowIR,
    registry: NodeRegistry,
    grants: Optional[RunGrants] = None,
    subworkflows: Optional[dict[str, WorkflowIR]] = None,
    *,
    _depth: int = 0,
    _stack: tuple[str, ...] = (),
) -> ExecutionPlan:
    """Validate + analyze a workflow and produce its execution plan.

    ``subworkflows`` is the front-door bundle (``id@version`` -> IR). A
    subworkflow node is compiled recursively with the SAME grants, so it can
    never widen authority; cycles and excessive nesting are diagnostics.
    """
    grants = grants or RunGrants()
    subworkflows = subworkflows or {}
    diagnostics: list[Diagnostic] = []
    mode = ir.settings.execution_mode

    if ir.ir_version not in SUPPORTED_IR_VERSIONS:
        diagnostics.append(_error(
            "unsupported_ir_version",
            f"Workflow IR version {ir.ir_version} is not supported by this runtime "
            f"(supported: {', '.join(map(str, SUPPORTED_IR_VERSIONS))}).",
        ))

    # ── Identifiers ────────────────────────────────────────────────────────
    seen_nodes: set[str] = set()
    for node in ir.nodes:
        if node.id in seen_nodes:
            diagnostics.append(_error("duplicate_node_id", f'Duplicate node id "{node.id}".', node_id=node.id))
        seen_nodes.add(node.id)
    seen_edges: set[str] = set()
    for edge in ir.edges:
        if edge.id in seen_edges:
            diagnostics.append(_error("duplicate_edge_id", f'Duplicate edge id "{edge.id}".', edge_id=edge.id))
        seen_edges.add(edge.id)

    # ── Nodes: registry, config, mode, permissions ─────────────────────────
    defs: dict[str, Optional[NodeDef]] = {}
    plan_nodes: list[PlanNode] = []
    required_capabilities: set[str] = set()

    for node in ir.nodes:
        definition = registry.get(node.type, node.version)
        defs[node.id] = definition
        if definition is None:
            diagnostics.append(_error(
                "missing_node_type",
                f'Node type "{node.type}" @ {node.version} is not registered.',
                node_id=node.id,
            ))
            continue

        problems = validate_config(definition, node.config)
        if problems:
            diagnostics.append(_error(
                "invalid_config",
                f'Invalid config for "{node.id}": {"; ".join(problems)}.',
                node_id=node.id,
            ))

        # A test run tightens declared limits (e.g. `logic.wait`), so a test can
        # never stall on a long sleep.
        if grants.test_run and definition.test_run_limits:
            merged = coerce_config(definition, node.config)
            for field_name, limit in definition.test_run_limits.items():
                value = merged.get(field_name)
                if isinstance(value, (int, float)) and not isinstance(value, bool) and value > limit:
                    diagnostics.append(_error(
                        "test_run_limit",
                        f'Node "{node.id}" uses {field_name}={value}, but a test run allows at most {limit:g}.',
                        node_id=node.id,
                    ))

        required_capabilities.update(definition.capabilities)

        if mode not in definition.allowed_modes:
            diagnostics.append(_error(
                "invalid_execution_mode",
                f'Node "{node.id}" ({definition.label}) is not permitted in {mode.value} mode.',
                node_id=node.id,
            ))

        # Permission envelope — the runtime's own decision.
        if definition.side_effects == SideEffect.TRADING and not grants.test_run:
            if mode == ExecutionMode.LIVE:
                live_ok = definition.type in (
                    "trading.broker_order", "trading.broker_close",
                    "trading.broker_modify", "trading.broker_cancel",
                )
                if not live_ok:
                    diagnostics.append(_error(
                        "live_trading_unavailable",
                        f'Node "{node.id}" is a paper-only trading node; switch the workflow to paper mode.',
                        node_id=node.id,
                    ))
                elif not grants.allow_live_trading:
                    diagnostics.append(_error(
                        "permission_denied",
                        f'Node "{node.id}" can place live trades; live trading is not authorized for this run.',
                        node_id=node.id,
                    ))
                else:
                    connection_id = str(node.config.get("connectionId") or "").strip()
                    if not connection_id:
                        diagnostics.append(_error(
                            "invalid_trading_config",
                            f'Node "{node.id}" needs a connectionId for live execution.',
                            node_id=node.id,
                        ))
                    if definition.type == "trading.broker_order" and not str(
                        node.config.get("mandateId") or ""
                    ).strip():
                        diagnostics.append(_error(
                            "invalid_trading_config",
                            f'Node "{node.id}" needs a live mandateId for unattended execution.',
                            node_id=node.id,
                        ))
            elif not (grants.allow_trading and mode == ExecutionMode.PAPER):
                diagnostics.append(_error(
                    "permission_denied",
                    f'Node "{node.id}" can place trades; paper trading is not authorized for this run.',
                    node_id=node.id,
                ))
        if grants.test_run and definition.side_effects in _ALWAYS_DENIED_IN_TEST:
            diagnostics.append(_error(
                "permission_denied",
                f'Node "{node.id}" has the "{definition.side_effects.value}" side effect, which a test run never performs.',
                node_id=node.id,
            ))
        elif definition.side_effects == SideEffect.NETWORK and not grants.allow_network:
            diagnostics.append(_error(
                "permission_denied",
                f'Node "{node.id}" requires network access, which this run was not granted.',
                node_id=node.id,
            ))
        elif definition.side_effects == SideEffect.WRITE:
            if definition.type == "file.write":
                scope = str(node.config.get("scope") or "workspace").strip()
                if scope not in grants.allowed_write_scopes:
                    diagnostics.append(_error(
                        "write_scope_denied",
                        f'Node "{node.id}" writes to the {scope!r} scope, which this run was not granted.',
                        node_id=node.id,
                    ))
            elif not grants.allow_write:
                diagnostics.append(_error(
                    "permission_denied",
                    f'Node "{node.id}" writes locally, which this run was not granted.',
                    node_id=node.id,
                ))
        # Capabilities gate EFFECTS: a pure node (side_effects "none") cannot
        # affect anything, so its declared capabilities are descriptive and are
        # not required to be granted. Any node that touches the world must have
        # every capability it declares explicitly granted — except the
        # read-only/local-compute set a test run carries implicitly.
        granted = grants.granted_capabilities
        if grants.test_run:
            granted = granted | TEST_RUN_CAPABILITIES
        missing_caps = (
            [c for c in definition.capabilities if c not in granted]
            if definition.side_effects != SideEffect.NONE
            else []
        )
        if missing_caps:
            diagnostics.append(_error(
                "capability_denied",
                f'Node "{node.id}" requires the {", ".join(missing_caps)} capability, which this run was not granted.',
                node_id=node.id,
            ))

        if definition.type in (
            "flow.subworkflow", "flow.for_each", "flow.repeat", "flow.while",
        ):
            workflow_id = str(node.config.get("workflowId") or "").strip()
            try:
                version = int(node.config.get("version", 0))
            except (TypeError, ValueError):
                version = 0
            if not workflow_id or version < 1:
                diagnostics.append(_error(
                    "invalid_subworkflow",
                    f'Node "{node.id}" needs a pinned subworkflow (workflowId and version >= 1).',
                    node_id=node.id,
                ))
            else:
                key = f"{workflow_id}@{version}"
                if key in _stack:
                    diagnostics.append(_error(
                        "subworkflow_cycle",
                        f'Subworkflow cycle detected at "{key}" (node "{node.id}").',
                        node_id=node.id,
                    ))
                elif _depth >= MAX_SUBWORKFLOW_DEPTH:
                    diagnostics.append(_error(
                        "subworkflow_depth",
                        f'Subworkflow nesting exceeds the maximum depth ({MAX_SUBWORKFLOW_DEPTH}) at "{key}".',
                        node_id=node.id,
                    ))
                elif key not in subworkflows:
                    diagnostics.append(_error(
                        "missing_subworkflow",
                        f'Subworkflow "{key}" was not supplied to this run.',
                        node_id=node.id,
                    ))
                else:
                    sub_plan = compile_workflow(
                        subworkflows[key], registry, grants, subworkflows,
                        _depth=_depth + 1, _stack=(*_stack, key),
                    )
                    required_capabilities.update(sub_plan.required_capabilities)
                    for diagnostic in sub_plan.diagnostics:
                        if diagnostic.severity == Severity.ERROR:
                            # Preserve the safety codes (cycle/depth) so a caller
                            # can assert them; everything else is a nested-graph
                            # failure reported against this node.
                            code = (
                                diagnostic.code
                                if diagnostic.code in ("subworkflow_cycle", "subworkflow_depth")
                                else "subworkflow_invalid"
                            )
                            diagnostics.append(_error(
                                code,
                                f'Subworkflow "{key}" (node "{node.id}"): {diagnostic.message}',
                                node_id=node.id,
                            ))

        if not definition.available:
            since = f" It arrives with {definition.since_phase}." if definition.since_phase else ""
            diagnostics.append(_error(
                "executor_unavailable",
                f'Node "{node.id}" ({definition.label}) has no executor in this runtime yet.{since}',
                node_id=node.id,
            ))
            continue

        plan_nodes.append(PlanNode(
            nodeId=node.id,
            nodeType=definition.type,
            version=definition.version,
            layer=0,
            capabilities=list(definition.capabilities),
            sideEffects=definition.side_effects,
            timeoutMs=definition.timeout_ms,
            maxAttempts=definition.max_attempts,
        ))

    # ── Edges ──────────────────────────────────────────────────────────────
    by_id = {node.id: node for node in ir.nodes}
    connected_inputs: set[str] = set()
    input_writers: dict[str, int] = {}
    for edge in ir.edges:
        source = by_id.get(edge.source)
        target = by_id.get(edge.target)
        if source is None or target is None:
            diagnostics.append(_error(
                "invalid_edge_endpoints",
                f'Edge "{edge.id}" references a missing node.',
                edge_id=edge.id,
            ))
            continue
        source_def = defs.get(edge.source)
        target_def = defs.get(edge.target)
        out_port = source_def.output_port(edge.source_handle) if source_def else None
        in_port = target_def.input_port(edge.target_handle) if target_def else None
        if out_port is None or in_port is None:
            diagnostics.append(_error(
                "invalid_edge_handles",
                f'Edge "{edge.id}" references an unknown port.',
                edge_id=edge.id,
            ))
            continue
        if not ports_compatible(out_port, in_port):
            diagnostics.append(_error(
                "incompatible_ports",
                f'Cannot connect {out_port.type.value} → {in_port.type.value} (edge "{edge.id}").',
                edge_id=edge.id,
            ))
            continue
        key = f"{edge.target}:{edge.target_handle}"
        connected_inputs.add(key)
        input_writers[key] = input_writers.get(key, 0) + 1

    for key, writers in input_writers.items():
        if writers > 1:
            node_id, handle = key.split(":", 1)
            diagnostics.append(_warn(
                "multiple_edges_into_input",
                f'Input "{handle}" of "{node_id}" has {writers} incoming connections; the last one in document order wins.',
                node_id=node_id,
            ))

    # ── Required inputs ────────────────────────────────────────────────────
    for node in ir.nodes:
        definition = defs.get(node.id)
        if definition is None:
            continue
        for input_port in definition.inputs:
            if input_port.optional:
                continue
            # Required CONTROL inputs must also be wired (e.g. a gate's trigger).
            if f"{node.id}:{input_port.id}" not in connected_inputs:
                diagnostics.append(_error(
                    "missing_required_input",
                    f'Node "{node.id}" is missing required input "{input_port.name}".',
                    node_id=node.id,
                ))

    # ── Input-or-config requirements ───────────────────────────────────────
    # Some nodes accept their core value from EITHER a wire OR a config field
    # (the agent nodes' objective). The port is optional so a config-only node
    # validates; the value itself is still mandatory.
    _input_or_config = {
        "agent.research": ("query", "objective", "a query or an objective"),
        "agent.plan": ("objective", "objective", "an objective"),
    }
    for node in ir.nodes:
        rule = _input_or_config.get(node.type)
        if rule is None:
            continue
        port_id, config_key, label = rule
        wired = f"{node.id}:{port_id}" in connected_inputs
        configured = node.config.get(config_key)
        if not wired and (not isinstance(configured, str) or not configured.strip()):
            diagnostics.append(_error(
                "missing_objective",
                f'Node "{node.id}" needs {label}: wire "{port_id}" or type it in the node settings.',
                node_id=node.id,
            ))

    # ── Structure: cycles, reachability, terminals ─────────────────────────
    order = _topological_order(ir)
    if order is None:
        diagnostics.append(_error("illegal_cycle", "The graph contains a cycle; Phase 1 graphs must be acyclic."))
        order = sorted(node.id for node in ir.nodes)

    reachable: set[str] = set()
    if ir.nodes:
        adjacency: dict[str, list[str]] = {node.id: [] for node in ir.nodes}
        for edge in ir.edges:
            if edge.source in adjacency:
                adjacency[edge.source].append(edge.target)
        triggers = [n.id for n in ir.nodes if (defs.get(n.id) and defs[n.id].category == "trigger")]  # type: ignore[union-attr]
        queue = list(triggers)
        reachable.update(triggers)
        while queue:
            current = queue.pop(0)
            for child in adjacency.get(current, []):
                if child not in reachable:
                    reachable.add(child)
                    queue.append(child)
        if not triggers:
            diagnostics.append(_error("missing_trigger", "The graph has no trigger node, so it can never start."))
        for node in ir.nodes:
            if node.id not in reachable:
                diagnostics.append(_warn(
                    "unreachable_node",
                    f'Node "{node.id}" is not reachable from any trigger.',
                    node_id=node.id,
                ))
        terminals = [n.id for n in ir.nodes if (defs.get(n.id) and defs[n.id].terminal)]  # type: ignore[union-attr]
        if not terminals:
            diagnostics.append(_error("missing_terminal", "The graph has no terminal (output) node."))
        elif not any(t in reachable for t in terminals):
            diagnostics.append(_warn("unreachable_terminal", "No terminal node is reachable from a trigger."))

    # ── Capability declaration consistency ─────────────────────────────────
    declared = set(ir.required_capabilities)
    for capability in sorted(required_capabilities - declared):
        diagnostics.append(_warn(
            "undeclared_capability",
            f'Required capability "{capability}" is not declared on the workflow.',
        ))

    # ── Layers ─────────────────────────────────────────────────────────────
    layers = _layers(ir, order) if order else []
    layer_of: dict[str, int] = {}
    for index, layer in enumerate(layers):
        for node_id in layer:
            layer_of[node_id] = index
    plan_nodes = [
        PlanNode(
            nodeId=plan.node_id,
            nodeType=plan.node_type,
            version=plan.version,
            layer=layer_of.get(plan.node_id, 0),
            capabilities=plan.capabilities,
            sideEffects=plan.side_effects,
            timeoutMs=plan.timeout_ms,
            maxAttempts=plan.max_attempts,
        )
        for plan in plan_nodes
    ]
    plan_nodes.sort(key=lambda p: (p.layer, p.node_id))

    executable = not any(d.severity == Severity.ERROR for d in diagnostics)
    return ExecutionPlan(
        workflowId=ir.id,
        irVersion=ir.ir_version,
        mode=mode,
        testRun=grants.test_run,
        executable=executable and bool(ir.nodes),
        layers=layers,
        order=order,
        nodes=plan_nodes,
        requiredCapabilities=sorted(required_capabilities),
        diagnostics=diagnostics,
    )


def plan_inputs(ir: WorkflowIR) -> dict[str, list[tuple[str, str]]]:
    """For each `target:handle`, the ordered list of `(source, sourceHandle)`
    that write it. Exposed for the executor and for UI inspection."""
    mapping: dict[str, list[tuple[str, str]]] = {}
    for edge in ir.edges:
        mapping.setdefault(f"{edge.target}:{edge.target_handle}", []).append((edge.source, edge.source_handle))
    return mapping


__all__ = ["RunGrants", "compile_workflow", "plan_inputs", "PortType", "coerce_config"]
