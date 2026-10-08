"""Plugin health tracking and reporting.

Health is derived from measured counters (tool/event/hook/http failures, crashes,
restarts, latency) — never fabricated. A plugin with no recorded activity reports
`unknown` rather than a fake `healthy`.
"""

from __future__ import annotations

from typing import Any

from .model import PluginState


def derive_status(counts: dict[str, Any]) -> str:
    """Classify health from counters. `unknown` when nothing has happened yet."""
    calls = int(counts.get("toolCalls", 0) or 0)
    failures = int(counts.get("toolFailures", 0) or 0)
    event_failures = int(counts.get("eventFailures", 0) or 0)
    hook_failures = int(counts.get("hookFailures", 0) or 0)
    http_failures = int(counts.get("httpFailures", 0) or 0)
    crashes = int(counts.get("crashes", 0) or 0)
    total_calls = calls
    total_failures = failures + event_failures + hook_failures + http_failures
    if crashes > 0:
        return "unhealthy"
    if total_calls == 0 and total_failures == 0:
        return "unknown"
    if total_failures == 0:
        return "healthy"
    ratio = total_failures / max(1, total_calls + total_failures)
    if ratio >= 0.5:
        return "unhealthy"
    return "degraded"


def health_report(store: Any, plugin_id: str, state: PluginState | None = None) -> dict[str, Any]:
    counts = store.get_health(plugin_id)
    status = "disabled" if state in (PluginState.DISABLED,) else derive_status(counts)
    return {
        "pluginId": plugin_id,
        "status": status,
        "state": state.value if state else None,
        "uptimeS": counts.get("uptimeS", 0.0),
        "toolCalls": counts.get("toolCalls", 0),
        "toolFailures": counts.get("toolFailures", 0),
        "eventFailures": counts.get("eventFailures", 0),
        "hookFailures": counts.get("hookFailures", 0),
        "httpFailures": counts.get("httpFailures", 0),
        "crashes": counts.get("crashes", 0),
        "restarts": counts.get("restarts", 0),
        "latencyMs": counts.get("latencyMs", 0.0),
        "authStatus": counts.get("authStatus"),
        "lastError": counts.get("lastError"),
        "startedAt": counts.get("startedAt"),
    }


def summarize(store: Any, records: list[Any]) -> dict[str, Any]:
    by_status: dict[str, int] = {}
    enabled = 0
    unhealthy = 0
    for record in records:
        if record.enabled:
            enabled += 1
        report = health_report(store, record.plugin_id, record.status)
        by_status[report["status"]] = by_status.get(report["status"], 0) + 1
        if report["status"] == "unhealthy":
            unhealthy += 1
    return {
        "installed": len(records),
        "enabled": enabled,
        "unhealthy": unhealthy,
        "byStatus": by_status,
    }


__all__ = ["derive_status", "health_report", "summarize"]
