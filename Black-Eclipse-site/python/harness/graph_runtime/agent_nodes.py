"""Agent nodes.

The graph node is a thin adapter over the EXISTING agent run plane
(`AgenticService.run`): it does not create a second agent loop, model adapter or
tool registry. `bootstrap.py` binds a runner at boot so tests can substitute a
fake and the runtime does not import the whole service here.

Model credentials are held in memory for the run and are never written into the
durable Fabric job payload.
"""

from __future__ import annotations

from typing import Any, Callable, Optional

from .model import ExecutionMode, PortDef, PortType, SideEffect
from .registry import ConfigField, NodeDef, NodeExecContext

_ALL = tuple(ExecutionMode)

AgentRunner = Callable[[NodeExecContext, dict[str, Any], str], dict[str, Any]]
_runner: Optional[AgentRunner] = None


def set_agent_runner(runner: Optional[AgentRunner]) -> None:
    global _runner
    _runner = runner


def exec_research_agent(context: NodeExecContext) -> dict[str, Any]:
    objective = str(
        context.inputs.get("query") or context.config.get("objective") or ""
    ).strip()
    if not objective:
        raise ValueError("agent.research needs a query input or a configured objective")
    if _runner is None:
        raise ValueError("the agent runtime is not configured in this graph runtime")
    config = {
        "agent": str(context.config.get("agent") or "eclipse-agent"),
        "objective": objective,
        "maxSteps": int(context.config.get("maxSteps", 8)),
    }
    result = _runner(context, config, objective)
    if not isinstance(result, dict):
        raise ValueError("the agent runner returned no structured result")
    return result


def build_agent_nodes() -> list[NodeDef]:
    return [
        NodeDef(
            type="agent.research", version="1.0.0", label="Research agent",
            category="agent",
            inputs=(PortDef(id="query", name="Query", type=PortType.STRING),),
            outputs=(
                PortDef(id="finding", name="Finding", type=PortType.RESEARCH_FINDING),
                PortDef(id="evidence", name="Evidence", type=PortType.EVIDENCE),
            ),
            config_fields=(
                ConfigField("agent", "string", "eclipse-agent", max_length=80),
                ConfigField("objective", "string", "", max_length=2_000),
                ConfigField("maxSteps", "integer", 8, minimum=1, maximum=32),
            ),
            capabilities=("agent.run",),
            side_effects=SideEffect.NETWORK,
            allowed_modes=_ALL,
            timeout_ms=600_000,
            executor=exec_research_agent,
            metadata={
                "docs": (
                    "Runs the EXISTING agent runtime for one bounded turn. Requires "
                    "an operator run with network + agent.run grants; the front door "
                    "resolves model settings into memory, never into the durable job."
                ),
            },
        ),
    ]


__all__ = ["build_agent_nodes", "set_agent_runner", "exec_research_agent"]
