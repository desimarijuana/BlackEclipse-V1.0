"""The proactive-monitor catalogue — portfolio conditions that run unattended.

A monitor is an ordinary Automation Engine `condition` automation: a
`pf.<portfolioId>.<field>` condition over the run's portfolio facts, plus a
`run_agent` action that explains the trigger and proposes (never executes) a
response. Building one here means a user can arm a monitor without hand-writing a
condition expression, and the shape is DATA — a closed, validated catalogue.

Monitors are created **switched off** (`state="disabled"`): like every scheduled
automation, only the operator turns it on. Nothing here places a trade.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, Optional

from ..persistence import now_iso


@dataclass(frozen=True)
class MonitorSpec:
    """One monitor shape. `condition`/`objective` carry `{param}` placeholders."""

    id: str
    label: str
    description: str
    params: tuple[str, ...]
    condition: str
    objective: str
    delivery: str = "in_app"


MONITORS: dict[str, MonitorSpec] = {
    "position_weight_breach": MonitorSpec(
        id="position_weight_breach",
        label="Position weight breach",
        description="Alert when a symbol's share of the portfolio rises above a threshold.",
        params=("portfolio_id", "symbol", "threshold"),
        condition="pf.{portfolio_id}.weight.{symbol} > {threshold}",
        objective=(
            "The position {symbol} has breached its target weight. Explain the breach and "
            "propose (do not execute) a rebalance to bring it back within {threshold}, "
            "using the portfolio engine's own numbers."
        ),
    ),
    "tax_loss_harvest": MonitorSpec(
        id="tax_loss_harvest",
        label="Tax-loss harvest watch",
        description="Alert when a symbol's unrealized loss falls below a threshold.",
        params=("portfolio_id", "symbol", "threshold"),
        condition="pf.{portfolio_id}.unrealized.{symbol} < {threshold}",
        objective=(
            "The position {symbol} has an unrealized loss beyond {threshold}. Report it and "
            "propose (do not execute) a tax-loss harvest. State that wash-sale rules are not "
            "modelled and must be checked across all accounts."
        ),
    ),
    "cash_buffer_watch": MonitorSpec(
        id="cash_buffer_watch",
        label="Cash buffer watch",
        description="Alert when cash falls below a share of the portfolio.",
        params=("portfolio_id", "threshold"),
        condition="pf.{portfolio_id}.cash_pct < {threshold}",
        objective=(
            "The portfolio's cash buffer has fallen below {threshold}. Explain the shortfall "
            "and propose (do not execute) how to restore it."
        ),
    ),
    "concentration_watch": MonitorSpec(
        id="concentration_watch",
        label="Concentration watch",
        description="Alert when the portfolio's concentration (HHI) rises above a cap.",
        params=("portfolio_id", "threshold"),
        condition="pf.{portfolio_id}.concentration_hhi > {threshold}",
        objective=(
            "The portfolio's concentration (Herfindahl index) has risen above {threshold}. "
            "Explain the concentration risk and propose (do not execute) a diversification path."
        ),
    ),
}


def get_monitor(monitor_id: str) -> Optional[MonitorSpec]:
    return MONITORS.get(str(monitor_id or "").strip())


def list_monitors() -> list[dict[str, Any]]:
    return [
        {
            "id": spec.id, "label": spec.label, "description": spec.description,
            "requiredParams": list(spec.params), "condition": spec.condition,
            "delivery": spec.delivery,
        }
        for spec in MONITORS.values()
    ]


def monitor_issues() -> list[str]:
    """Consistency problems, empty when the catalogue is sound."""
    issues: list[str] = []
    for spec in MONITORS.values():
        for param in spec.params:
            token = "{" + param + "}"
            if token not in spec.condition:
                issues.append(f"{spec.id}: condition does not use parameter {param!r}")
        if spec.delivery not in ("in_app", "artifact", "messaging"):
            issues.append(f"{spec.id}: unknown delivery {spec.delivery!r}")
    return issues


def build_definition(
    monitor_id: str,
    params: dict[str, Any],
    *,
    name: Optional[str] = None,
    objective: Optional[str] = None,
    delivery: Optional[str] = None,
) -> Any:
    """Build an (off) `AutomationDefinition` for a monitor.

    Raises `ValueError` when the monitor id is unknown or a required parameter is
    missing, so a bad request fails loudly instead of arming a broken monitor.
    """
    from ..automation.model import Action, AutomationDefinition, ConditionSpec, Trigger

    spec = get_monitor(monitor_id)
    if spec is None:
        raise ValueError(f"unknown monitor {monitor_id!r}")
    missing = [p for p in spec.params if p not in params or params[p] in (None, "")]
    if missing:
        raise ValueError(f"monitor {monitor_id!r} requires {', '.join(missing)}")

    condition = spec.condition.format(**{p: params[p] for p in spec.params})
    text = (objective or spec.objective).format(**{p: params[p] for p in spec.params})
    now = now_iso()
    return AutomationDefinition(
        id=f"mon_{uuid.uuid4().hex[:16]}",
        name=name or spec.label,
        description=spec.description,
        state="disabled",
        trigger=Trigger(type="condition", condition=ConditionSpec(expression=condition, edge=True)),
        condition=ConditionSpec(expression=condition, edge=True),
        action=Action(type="run_agent", objective=text),
        delivery={"adapter": delivery or spec.delivery},
        tags=["bot", "monitor"],
        created_at=now,
        updated_at=now,
    )


__all__ = [
    "MONITORS",
    "MonitorSpec",
    "build_definition",
    "get_monitor",
    "list_monitors",
    "monitor_issues",
]
