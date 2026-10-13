"""R3-07 follow-through (ADR-H184) — the registry-visibility scan.

Every tool registered on the production registry must be REACHABLE from at least
one agent allowlist — or be in the deliberate operator/console set below.
"Registered but invisible is a bug unless deliberate and documented"; this test
is that enforcement (audit §6, deferred by R3-07). It also pins the inverse:
an allowlisted tool that is not registered is a bug too (a ghost).

Dynamic surfaces (MCP tools the operator selected, plugin-contributed tools) are
expanded at resolve time by `effective_allowlist`; the scan mirrors that rule
(prefix + the agent's own allow-flag) instead of re-implementing the resolver.
"""

from __future__ import annotations

import os
import tempfile

import pytest

from harness.agents import CHAT_CODE_TOOLS, CODE_AGENT, CODE_NAVIGATOR, ECLIPSE_AGENT
from harness.tools import ToolRegistry

# ── the deliberate operator/console surface (documented, not a bug) ──────────
#
# Each family is reachable through its operator route (or is an internal
# primitive), never through an agent allowlist. R3-02/R3-07/ADR-H182 record the
# rule; ADR-H184 records this scan.
DELIBERATE_INVISIBLE: frozenset[str] = frozenset({
    # Recovery console: durable incidents are inspected via `/recovery/*`.
    "recovery_diagnose", "recovery_discover", "recovery_incident",
    "recovery_incidents", "recovery_summary",
    # Artifact Center catalog management: the operator/UI surface (`/artifacts/*`).
    "artifact_add_version", "artifact_create_collection", "artifact_get",
    "artifact_list", "artifact_register", "artifact_tag",
    # Execution Fabric admin: durable queue/job management (`/fabric/*`).
    "fabric_dlq_list", "fabric_job_cancel", "fabric_job_retry", "fabric_job_status",
    "fabric_jobs_children", "fabric_jobs_list", "fabric_stats", "fabric_submit",
    "fabric_workers",
    # Parallel-execution primitives: used INTERNALLY by the automation dispatcher
    # and the fabric manager; the operator console exposes orchestration directly.
    "dependency_graph", "execution_cancel", "execution_status", "parallel_execute",
    "task_batch", "task_fork", "task_join", "task_map", "task_quorum", "task_race",
    "task_reduce",
    # Operator context surfaces: the UI resolves world events / assembled context
    # server-side; they are not chat tool surfaces.
    "get_world_events", "search_context",
    # Cluster/infra mutations: no approval kind exists yet (recorded open item,
    # audit §6 R3-07), and port-forward/logs-follow are long-lived streams, not
    # chat-turn shaped. They stay registered-but-unreachable ON PURPOSE.
    "deploy_promote", "k8s_logs_follow", "k8s_port_forward",
})


def _dynamic_for(agent: object, registered: set[str]) -> set[str]:
    """The names `effective_allowlist` would add for this agent's open surfaces."""
    names: set[str] = set()
    if getattr(agent, "allowMcpTools", False):
        names |= {n for n in registered if n.startswith("mcp_")}
    if getattr(agent, "allowPluginTools", False):
        names |= {n for n in registered if n.startswith("plug_")}
        names |= {n for n in registered if n.startswith("plugin_")}
    return names


def compute_visibility(
    registered: set[str],
    agents: list[object],
    declared_profiles: tuple[str, ...] = (),
) -> tuple[set[str], set[str]]:
    """Pure classifier: (invisible, ghosts) for a registered tool set."""
    declared: set[str] = set(declared_profiles)
    dynamic: set[str] = set()
    for agent in agents:
        declared |= set(getattr(agent, "tools", ()) or ())
        dynamic |= _dynamic_for(agent, registered)
    invisible = registered - declared - dynamic
    ghosts = declared - registered
    return invisible, ghosts


AGENTS = [ECLIPSE_AGENT, CODE_NAVIGATOR, CODE_AGENT]


@pytest.fixture(scope="module")
def production_registry() -> set[str]:
    """Every name the production runtime registers.

    The service constructor registers the layers it owns; the boot-only families
    (recovery / orchestration / a2a / fabric) register into a throwaway registry
    so the scan sees them WITHOUT starting any runtime or global singleton.
    """
    from harness.persistence import AgentMemoryStore

    directory = tempfile.mkdtemp(prefix="be-registry-vis-")
    store = AgentMemoryStore(os.path.join(directory, "agent-memory.db"))
    try:
        from harness.service import AgenticService

        service = AgenticService(store=store)
        names = set(service.registry.names())
        from harness.a2a.tools import register_a2a_tools
        from harness.fabric.tools import register_fabric_tools
        from harness.orchestration.tools import register_orchestration_tools
        from harness.recovery.tools import register_recovery_tools

        for register in (
            register_recovery_tools, register_orchestration_tools,
            register_a2a_tools, register_fabric_tools,
        ):
            scratch = ToolRegistry()
            register(scratch)
            names |= set(scratch.names())
        return names
    finally:
        store.close()


def test_no_registered_tool_is_undocumented_invisible(production_registry: set[str]) -> None:
    invisible, _ghosts = compute_visibility(production_registry, AGENTS, CHAT_CODE_TOOLS)
    undocumented = invisible - DELIBERATE_INVISIBLE
    stale = DELIBERATE_INVISIBLE - invisible
    assert not undocumented, (
        "registered but invisible and NOT deliberate/documented — allowlist it or "
        f"document it in DELIBERATE_INVISIBLE: {sorted(undocumented)}"
    )
    assert not stale, (
        "documented as deliberately invisible but now reachable — remove it from "
        f"DELIBERATE_INVISIBLE: {sorted(stale)}"
    )


def test_no_allowlisted_tool_is_unregistered(production_registry: set[str]) -> None:
    _invisible, ghosts = compute_visibility(production_registry, AGENTS, CHAT_CODE_TOOLS)
    assert not ghosts, (
        f"allowlisted but never registered (the model is promised a tool that does "
        f"not exist): {sorted(ghosts)}"
    )


def test_the_documented_set_is_exactly_the_operator_surface() -> None:
    # The families named in ADR-H182/ADR-H184 are all here; a shrinking set is a
    # deliberate change, not an accident.
    for name in ("recovery_summary", "artifact_list", "fabric_stats",
                 "parallel_execute", "get_world_events", "search_context",
                 "deploy_promote"):
        assert name in DELIBERATE_INVISIBLE


def test_the_scan_bites_on_a_new_unregistered_or_invisible_tool() -> None:
    class _Agent:
        tools = ["workspace_read"]

    registered = {"workspace_read", "brand_new_tool", "plugin_x"}
    invisible, ghosts = compute_visibility(registered, [_Agent()])
    assert invisible == {"brand_new_tool", "plugin_x"}  # plugin_ needs the flag
    assert ghosts == set()

    class _PluginAgent:
        tools = ["workspace_read"]
        allowPluginTools = True

    invisible2, _ = compute_visibility(registered, [_PluginAgent()])
    assert invisible2 == {"brand_new_tool"}  # plugin_x is dynamically visible

    _invisible, ghost_scan = compute_visibility({"workspace_read"}, [_Agent()])
    assert ghost_scan == set()
    _invisible, ghost_scan2 = compute_visibility(set(), [_Agent()])
    assert ghost_scan2 == {"workspace_read"}
