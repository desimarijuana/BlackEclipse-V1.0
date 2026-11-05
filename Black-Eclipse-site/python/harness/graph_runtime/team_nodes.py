"""Team node: run the institution committee and return its terminal decision.

The node is a thin adapter over the EXISTING team runtime
(`TeamService.run` → `wait` → `finalize` → `synthesize`), the same sequence the
automation dispatcher uses for a scheduled committee run. It never places an
order and never registers a trigger.
"""

from __future__ import annotations

from typing import Any, Callable, Optional

from .model import ExecutionMode, PortDef, PortType, SideEffect
from .registry import ConfigField, NodeDef, NodeExecContext

_ALL = tuple(ExecutionMode)
TEAM_SUCCESS_STATUSES = frozenset({"COMPLETED", "PARTIAL"})

TeamRunner = Callable[[NodeExecContext, dict[str, Any]], dict[str, Any]]
_runner: Optional[TeamRunner] = None


def set_team_runner(runner: Optional[TeamRunner]) -> None:
    global _runner
    _runner = runner


def exec_team(context: NodeExecContext) -> dict[str, Any]:
    if context.test_run:
        # A committee run costs many model calls and writes tasks/A2A state; a
        # test run must not start one.
        raise ValueError(
            "agent.team starts a multi-agent committee run; run it as an operator "
            "run (a test run never starts one)"
        )
    objective = str(
        context.inputs.get("objective") or context.config.get("objective") or ""
    ).strip()
    if not objective:
        raise ValueError("agent.team needs an objective (wire one or fill Objective)")
    if _runner is None:
        raise ValueError("the team runtime is not configured in this graph runtime")
    try:
        timeout_s = int(context.config.get("timeoutS", 600))
    except (TypeError, ValueError) as exc:
        raise ValueError("Timeout must be a whole number of seconds") from exc
    args = {
        "objective": objective,
        "universe": str(context.config.get("universe") or "").strip(),
        "horizon": str(context.config.get("horizon") or "").strip(),
        "timeoutS": max(30, min(timeout_s, 3_600)),
    }
    result = _runner(context, args)
    if not isinstance(result, dict):
        raise ValueError("the team runner returned no structured result")
    status = str(result.get("status") or "").strip().upper()
    if status not in TEAM_SUCCESS_STATUSES:
        detail = result.get("error") or "no detail reported"
        raise ValueError(f"team run did not complete ({status or 'unknown'}): {detail}")
    synthesis = result.get("synthesis")
    context.emit(f"team {status} · {result.get('teamRunId') or ''}".strip())
    return {
        "decision": result.get("decision") or {},
        "synthesis": "" if synthesis is None else str(synthesis),
        "status": status,
    }


def build_team_nodes() -> list[NodeDef]:
    return [
        NodeDef(
            type="agent.team", version="1.0.0", label="Run committee",
            category="agent",
            inputs=(PortDef(id="objective", name="Objective", type=PortType.STRING, optional=True),),
            outputs=(
                PortDef(id="decision", name="Decision", type=PortType.OBJECT),
                PortDef(id="synthesis", name="Synthesis", type=PortType.STRING),
                PortDef(id="status", name="Status", type=PortType.STRING),
            ),
            config_fields=(
                ConfigField("objective", "string", "", max_length=2_000),
                ConfigField("universe", "string", "", max_length=200),
                ConfigField("horizon", "string", "", max_length=100),
                ConfigField("timeoutS", "integer", 600, minimum=30, maximum=3_600),
            ),
            capabilities=("agent.run", "team.run"),
            side_effects=SideEffect.MODEL,
            allowed_modes=_ALL,
            timeout_ms=3_700_000,
            executor=exec_team,
            metadata={
                "docs": (
                    "Runs the Institution committee through the existing team "
                    "runtime and returns its reconciled decision, deterministic "
                    "synthesis and terminal status (COMPLETED/PARTIAL succeed; "
                    "anything else fails with the status). It never places an order "
                    "and never registers a trigger. Operator runs only."
                ),
            },
        ),
    ]


__all__ = [
    "TEAM_SUCCESS_STATUSES",
    "build_team_nodes",
    "exec_team",
    "set_team_runner",
]
