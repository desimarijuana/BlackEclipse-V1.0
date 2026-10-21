"""Apply an operator-activated surface snapshot to a live run.

The activation was measured and validated against a specific base snapshot.
At run time this module re-derives the current agent's base and applies the
snapshot ONLY if the base digest still matches. A stale base, a missing
activation, an unsupported field or any validation failure leaves the original
agent untouched: a live run never inherits a half-applied surface.

Only prompt, tool subset and step/tool-call ceilings are applied live. Model
identity and skill drafts are refused at activation, so this module never
changes which provider/credentials a run uses.
"""

from __future__ import annotations

from typing import Any, Optional

from .models import HarnessSnapshot


def _loads(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def apply_active_surface(
    store: Any,
    agent: Any,
    *,
    scope: Optional[str] = None,
) -> tuple[Any, Optional[dict[str, Any]]]:
    """Return `(agent, activation)`; on any failure return the agent unchanged.

    `activation` is the applied row (or None). The caller may emit it for
    observability; it is never evidence that the change was measured again.
    """
    if store is None or agent is None:
        return agent, None
    try:
        from ..evaluation.candidate_invoker import (  # noqa: PLC0415
            base_snapshot_from_agent,
            validate_snapshot,
        )
        from .state import HarnessStateStore  # noqa: PLC0415

        state_store = HarnessStateStore(store)
        activation = state_store.active_activation(scope or getattr(agent, "id", "global"))
        if activation is None:
            return agent, None
        snapshot = HarnessSnapshot(**(_loads(activation.get("snapshot"))))
        saved_base = HarnessSnapshot(**(_loads(activation.get("base"))))
        current_base = base_snapshot_from_agent(agent)
        if current_base.sourceDigest != saved_base.sourceDigest:
            return agent, {"skipped": "base_changed", "activationId": activation.get("id")}
        validate_snapshot(saved_base, snapshot)
        updated = agent.model_copy(update={
            "systemPrompt": snapshot.effective_prompt(),
            "tools": list(snapshot.toolNames),
            "maxSteps": min(
                int(getattr(agent, "maxSteps", snapshot.maxSteps) or snapshot.maxSteps),
                int(snapshot.maxSteps),
            ),
            "maxToolCalls": min(
                int(getattr(agent, "maxToolCalls", snapshot.maxToolCalls) or snapshot.maxToolCalls),
                int(snapshot.maxToolCalls),
            ),
        })
        return updated, activation
    except Exception:  # noqa: BLE001 - a bad activation must never break a run
        return agent, None


__all__ = ["apply_active_surface"]
