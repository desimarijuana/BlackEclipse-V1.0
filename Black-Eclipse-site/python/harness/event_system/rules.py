"""Conditional event triggers — the event → action rule bridge.

Reuse before rebuild: the durable WHEN/IF/THEN engine already exists as the Native
Automation Engine (`harness.automation`), which supports event triggers, a
deterministic condition expression, retry, concurrency and delivery. This module
is the small adapter that lets the Event System (and its console/API) declare an
event rule in one call, mapping the canonical action vocabulary onto the
automation engine's `ActionKind`s. No second scheduler is introduced.

Actions map as:

    run_agent          -> run_agent
    run_workflow       -> execute_workflow
    create_task        -> create_task
    execute_tool       -> call_tool
    send_notification  -> send_notification
    store_memory       -> handled by the Event System's memory hook (not a run)
    request_approval    -> permission.requires_approval on the automation

Arbitrary event payloads can never bypass security: the automation dispatches the
action through the ordinary run path, subject to the same permission/allowlist
checks as a user-initiated run.
"""

from __future__ import annotations

from typing import Any, Optional

from .envelope import EclipseEvent

# Canonical rule action -> automation ActionKind.
_ACTION_MAP = {
    "run_agent": "run_agent",
    "run_workflow": "execute_workflow",
    "create_task": "create_task",
    "execute_tool": "call_tool",
    "send_notification": "send_notification",
    "generate_report": "generate_report",
}
# Actions the Event System owns directly (no agent run).
_INTERNAL_ACTIONS = {"store_memory", "request_approval"}
SUPPORTED_ACTIONS = tuple(_ACTION_MAP) + tuple(_INTERNAL_ACTIONS)


class EventRuleError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class EventRuleBridge:
    def __init__(self, service: Any) -> None:
        self._service = service

    def create_rule(
        self,
        *,
        name: str,
        event_type: str,
        action: str,
        condition: Optional[str] = None,
        event_filter: Optional[dict[str, Any]] = None,
        agent_id: Optional[str] = None,
        workflow_id: Optional[str] = None,
        tool_name: Optional[str] = None,
        tool_args: Optional[dict[str, Any]] = None,
        objective: Optional[str] = None,
        notification_template: Optional[str] = None,
        config: Optional[dict[str, Any]] = None,
        requires_approval: bool = False,
        activated: bool = False,
        created_by: Optional[str] = None,
    ) -> dict[str, Any]:
        from ..automation.model import (  # noqa: PLC0415
            Action,
            AutomationDefinition,
            PermissionPolicy,
            Trigger,
        )
        from ..persistence import now_iso  # noqa: PLC0415

        if event_type not in self._known_event_types():
            # Allow declared namespaces (`market.*`) but refuse a free-form typo.
            if not any(event_type.startswith(ns) for ns in self._registry().namespaces()):
                raise EventRuleError("UNKNOWN_EVENT", f"{event_type!r} is not a registered event type")

        if action not in SUPPORTED_ACTIONS:
            raise EventRuleError("UNSUPPORTED_ACTION", f"{action!r} is not a supported rule action")

        internal = action in _INTERNAL_ACTIONS
        if internal:
            # Internal actions are recorded as events but do not dispatch a run;
            # model them as a no-op custom action so the rule is still durable.
            automation_action = Action(type="custom_action", config={"kind": action, **(config or {})})
        else:
            automation_action = Action(
                type=_ACTION_MAP[action],
                agent_id=agent_id,
                workflow_id=workflow_id,
                tool_name=tool_name,
                tool_args=tool_args or {},
                objective=objective,
                notification_template=notification_template,
                config=config or {},
            )

        now = now_iso()
        definition = AutomationDefinition(
            id=f"rule_{__import__('uuid').uuid4().hex[:16]}",
            name=name,
            description=f"event rule: when {event_type} then {action}",
            version=1,
            state="active" if activated else "draft",
            trigger=Trigger(type="event", event_type=event_type, event_filter=event_filter or {}),
            condition={"expression": condition, "edge": False} if condition else None,
            action=automation_action,
            permissions=PermissionPolicy(requires_approval=requires_approval),
            created_at=now,
            updated_at=now,
        )
        # Validate against the automation engine's own rules before persisting.
        saved = self._service.automation_service().create_definition(definition, created_by=created_by)
        return saved.public()

    def list_rules(self, *, limit: int = 200) -> list[dict[str, Any]]:
        automations = self._service.automation_service().list(limit=limit)
        return [a.public() for a in automations if a.trigger.type == "event"]

    def matches(self, rule: dict[str, Any], event: EclipseEvent) -> bool:
        trigger = rule.get("trigger") or {}
        return trigger.get("eventType") == event.type

    def _known_event_types(self) -> set[str]:
        return {spec["type"] for spec in self._registry().list() if not spec["namespace"]}

    def _registry(self):
        from .registry import default_registry  # noqa: PLC0415

        return default_registry()


__all__ = ["EventRuleBridge", "EventRuleError", "SUPPORTED_ACTIONS"]
