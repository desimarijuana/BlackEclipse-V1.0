"""Per-root-run resource budgets — the guard against recursive agent explosions.

Every root run gets ONE durable `AgentBudget`. A child task/agent receives a
SUB-budget that can only narrow the parent's remaining allowance. Reservations are
checked BEFORE the action and incremented immediately, so a burst of parallel
delegations cannot each observe the same headroom and collectively overshoot.

The tracker persists through `A2AStore`; the policy (limits) lives on the budget.
"""

from __future__ import annotations

from typing import Any, Optional

from .model import AgentBudget


class BudgetExceeded(RuntimeError):
    """A budget of the named kind is exhausted. ``kind`` is stable."""

    def __init__(self, kind: str, reason: str) -> None:
        super().__init__(reason)
        self.kind = kind
        self.reason = reason


#: The counter column each budget kind increments when reserved.
_RESERVE_FIELD: dict[str, str] = {
    "agents": "agents_spawned",
    "tasks": "tasks_created",
    "tokens": "tokens_used",
    "cost": "cost_used",
    "runtime": "runtime_ms",
    "toolCalls": "tool_calls",
}

_LABEL: dict[str, str] = {
    "agents": "agents",
    "depth": "delegation depth",
    "tasks": "tasks",
    "tokens": "tokens",
    "cost": "cost",
    "runtime": "runtime",
    "toolCalls": "tool calls",
}


class BudgetTracker:
    """Durable budget accounting for root runs."""

    def __init__(self, store: Any) -> None:
        self._store = store

    def get(self, root_run_id: str) -> AgentBudget:
        budget = self._store.get_budget(root_run_id)
        if budget is None:
            budget = AgentBudget()
            self._store.save_budget(root_run_id, budget)
        return budget

    def snapshot(self, root_run_id: str) -> dict[str, Any]:
        budget = self.get(root_run_id)
        return {
            "rootRunId": root_run_id,
            **budget.model_dump(by_alias=True),
            "remaining": {
                "agents": budget.remaining("agents"),
                "depth": budget.remaining("depth"),
                "tasks": budget.remaining("tasks"),
                "tokens": budget.remaining("tokens"),
                "cost": budget.remaining("cost"),
                "runtime": budget.remaining("runtime"),
                "toolCalls": budget.remaining("toolCalls"),
            },
        }

    def reserve(self, root_run_id: str, kind: str, amount: float = 1) -> AgentBudget:
        """Atomically check + consume `amount` of `kind`. Raises when exhausted."""
        budget = self.get(root_run_id)
        if kind == "depth":
            if budget.depth + amount > budget.max_depth:
                raise BudgetExceeded(kind, f"delegation would exceed the depth limit of {budget.max_depth}")
            budget.depth += int(amount)
        else:
            field = _RESERVE_FIELD.get(kind)
            if field is None:
                raise BudgetExceeded(kind, f"unknown budget kind {kind!r}")
            remaining = budget.remaining(kind)
            if remaining < amount:
                raise BudgetExceeded(
                    kind,
                    f"the run has no {_LABEL.get(kind, kind)} left "
                    f"({remaining:g} of {_LIMITISH(budget, kind):g} remaining)",
                )
            current = getattr(budget, field)
            setattr(budget, field, type(current)(current + amount))
        self._store.save_budget(root_run_id, budget)
        return budget

    def record_usage(
        self, root_run_id: str, *, tokens: int = 0, cost: float = 0.0,
        runtime_ms: int = 0, tool_calls: int = 0,
    ) -> AgentBudget:
        """Record consumed resources WITHOUT refusing (post-hoc accounting)."""
        budget = self.get(root_run_id)
        budget.tokens_used += max(0, int(tokens))
        budget.cost_used += max(0.0, float(cost))
        budget.runtime_ms += max(0, int(runtime_ms))
        budget.tool_calls += max(0, int(tool_calls))
        self._store.save_budget(root_run_id, budget)
        return budget

    def child_budget(self, root_run_id: str, *, depth_delta: int = 1) -> AgentBudget:
        """A narrowed child budget derived from the parent's remaining allowance."""
        return self.get(root_run_id).sub_budget(depth_delta=depth_delta)

    def set_limits(self, root_run_id: str, **limits: Any) -> AgentBudget:
        budget = self.get(root_run_id)
        for key, value in limits.items():
            if value is not None and hasattr(budget, key):
                setattr(budget, key, value)
        self._store.save_budget(root_run_id, budget)
        return budget


def _LIMITISH(budget: AgentBudget, kind: str) -> float:
    return float({
        "agents": budget.max_agents, "tasks": budget.max_tasks, "tokens": budget.max_tokens,
        "cost": budget.max_cost, "runtime": budget.max_runtime_ms,
        "toolCalls": budget.max_tool_calls,
    }.get(kind, 0))


__all__ = ["BudgetExceeded", "BudgetTracker"]
