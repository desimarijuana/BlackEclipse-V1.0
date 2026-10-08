"""Bridges that make the Execution Fabric the common substrate.

Event rules: a selected event type creates a job on the fabric, so an event
producer (market, research, tasks, plugins) never learns about worker
implementations. The rule table is DATA, not code spread across producers.

The reverse direction (job lifecycle -> live event stream) is already handled by
the ExecutionManager publishing `fabric.job.*` on the shared bus and the Event
System, so both surfaces stay coherent.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

log = logging.getLogger("harness.fabric.integrations")


@dataclass
class EventRule:
    event_type: str
    job_type: str
    priority: Optional[str] = None
    description: str = ""
    payload: Callable[[Any], dict[str, Any]] = field(default=lambda event: {})


def _event_payload(event: Any) -> dict[str, Any]:
    return dict(getattr(event, "payload", {}) or {})


def _market_alert_job(event: Any) -> dict[str, Any]:
    payload = _event_payload(event)
    return {
        "title": payload.get("title") or "Market alert",
        "message": payload.get("message") or payload.get("detail") or str(payload)[:500],
        "level": payload.get("level") or "warning",
        "target": "in_app",
    }


def _earnings_research_job(event: Any) -> dict[str, Any]:
    payload = _event_payload(event)
    symbol = payload.get("symbol") or payload.get("ticker") or "the reporting company"
    return {"query": f"Research the fresh earnings release for {symbol} and summarize the key results.",
            "agentId": payload.get("agentId") or "eclipse-agent"}


def _plugin_sync_job(event: Any) -> dict[str, Any]:
    payload = _event_payload(event)
    plugin_id = payload.get("pluginId") or payload.get("plugin") or "a newly connected plugin"
    return {"query": f"Synchronize data for the newly connected integration {plugin_id}."}


def _task_completed_job(event: Any) -> dict[str, Any]:
    payload = _event_payload(event)
    return {
        "title": payload.get("title") or "Task completed",
        "message": payload.get("summary") or f"Task {payload.get('taskId', '')} finished.",
        "level": "info", "target": "in_app",
    }


# The default rule set. Names include the canonical Event System vocabulary and
# the older uppercase aliases that some producers still emit.
DEFAULT_RULES: tuple[EventRule, ...] = (
    EventRule("market.alert.triggered", "notification", "TRADING_ALERT",
              "price/alert -> notification", _market_alert_job),
    EventRule("PRICE_THRESHOLD_REACHED", "notification", "TRADING_ALERT",
              "price/alert -> notification", _market_alert_job),
    EventRule("price.threshold.reached", "notification", "TRADING_ALERT",
              "price/alert -> notification", _market_alert_job),
    EventRule("earnings.released", "research", "RESEARCH",
              "earnings -> research", _earnings_research_job),
    EventRule("EARNINGS_RELEASED", "research", "RESEARCH",
              "earnings -> research", _earnings_research_job),
    EventRule("plugin.connected", "market", "INGESTION",
              "plugin connect -> sync", _plugin_sync_job),
    EventRule("PLUGIN_CONNECTED", "market", "INGESTION",
              "plugin connect -> sync", _plugin_sync_job),
    EventRule("task.completed", "notification", "AGENT_INTERACTIVE",
              "task done -> notification", _task_completed_job),
    EventRule("TASK_COMPLETED", "notification", "AGENT_INTERACTIVE",
              "task done -> notification", _task_completed_job),
)


def rule_for(event_type: str, rules: tuple[EventRule, ...] = DEFAULT_RULES) -> Optional[EventRule]:
    for rule in rules:
        if rule.event_type == event_type:
            return rule
    return None


def build_event_handler(manager: Any, rules: tuple[EventRule, ...] = DEFAULT_RULES,
                        *, service: Any = None) -> Callable[[Any], Any]:
    """Return an async handler that turns a matching event into a fabric job."""
    index = {rule.event_type: rule for rule in rules}

    async def handle(event: Any) -> None:
        rule = index.get(getattr(event, "type", ""))
        if rule is None:
            return
        try:
            payload = rule.payload(event)
            await manager.submit(
                rule.job_type, payload, priority=rule.priority,
                correlation_id=getattr(event, "correlation_id", None),
                task_id=getattr(event, "task_id", None),
                agent_id=getattr(event, "agent_id", None),
                session_id=getattr(event, "session_id", None),
                metadata={"sourceEventId": getattr(event, "id", None),
                          "sourceEventType": getattr(event, "type", None),
                          "source": "event-rule"},
            )
        except Exception:  # noqa: BLE001 - a rule must never break the bus consumer
            log.warning("fabric event rule failed for %s", getattr(event, "type", "?"), exc_info=True)

    return handle


def install_event_rules(manager: Any, service: Any,
                        rules: tuple[EventRule, ...] = DEFAULT_RULES) -> Optional[Any]:
    """Subscribe the fabric event rules to the process-wide Event System."""
    system = getattr(service, "_event_system", None)
    if system is None:
        return None
    types = [rule.event_type for rule in rules]
    try:
        subscription = system.bus.subscribe(
            types, build_event_handler(manager, rules, service=service),
            consumer_id="fabric.event_rules", idempotent=True,
        )
    except Exception:  # noqa: BLE001 - rules are best-effort
        log.warning("fabric event rules could not be installed", exc_info=True)
        return None
    return subscription


__all__ = [
    "DEFAULT_RULES",
    "EventRule",
    "build_event_handler",
    "install_event_rules",
    "rule_for",
]
