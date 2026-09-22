"""Skill lifecycle event vocabulary.

Skill events ride the SAME `RunEmitter` as Phase-1/Phase-2 events, so they land
on the live SSE stream and in the persisted trace exactly like `tool.*` — no
second event bus. The registry/store additionally records a `SkillEvent` row for
lifecycle events that are not tied to a run (enable/disable/promotion), which is
the audit trail the UI reads.

Events emitted during execution use the `skill.*` namespace. `src/lib/agent/
registry.ts` maps unknown event types to a neutral status, so adding these does
not break the existing stream parser.
"""

from __future__ import annotations

from typing import Any, Optional

# The full Phase-3 vocabulary (documented in phase-3-architecture.md).
SKILL_EVENTS: tuple[str, ...] = (
    "skill.discovered",
    "skill.selected",
    "skill.started",
    "skill.dependency_resolved",
    "skill.tool_requested",
    "skill.step_completed",
    "skill.validation_failed",
    "skill.permission_denied",
    "skill.completed",
    "skill.failed",
    "skill.cancelled",
    "skill.learning_candidate_created",
    "skill.evaluation_started",
    "skill.evaluation_completed",
    "skill.promotion_requested",
    "skill.enabled",
    "skill.disabled",
)


async def emit_skill_event(
    emitter: Optional[Any],
    event_type: str,
    data: dict[str, Any],
) -> None:
    """Emit a skill event through a RunEmitter when one is attached.

    No-op when there is no emitter (e.g. a pure unit test) — the caller never
    has to guard. Never raises: an event is diagnostics, not control flow.
    """
    if emitter is None:
        return
    try:
        await emitter.emit(event_type, data)
    except Exception:  # noqa: BLE001 - an event must never break execution
        pass


__all__ = ["SKILL_EVENTS", "emit_skill_event"]
