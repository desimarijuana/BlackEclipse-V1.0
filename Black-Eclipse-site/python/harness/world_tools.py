"""World-state event tools — Python-owned contracts, JDdS-backed data.

Investor Eye ("God's Eye") normalizes world events (conflict, sanctions, trade,
energy, hazards, …) into the `GeopoliticalEvent` table. These tools expose that
feed to the agentic runtime through the SAME read-only `DataBridge` the finance
tools use — there is no second event store and nothing is fabricated.

Honesty contract (mirrors finance_tools): an unreadable store is a
`source_failure` — NEVER "no events happened". An empty result from a reachable
store is a genuine `no_data`, but it is explicitly NOT proof the world was calm;
the tool says so, because the event feed is a filtered observation, not a census.
"""

from __future__ import annotations

from typing import Any

from .finance_tools import _fetch
from .tools import ToolContext, ToolDefinition, ToolRegistry


def _fmt_event(e: dict[str, Any]) -> str:
    countries = ",".join(e.get("countries") or []) or "—"
    place = e.get("placeName") or "—"
    return (
        f"[{e.get('eventType')}/{e.get('severity')}] {e.get('title')}\n"
        f"    where: {place} ({countries}) · when: {e.get('publishedAt')} · "
        f"relevance {e.get('relevance')} · sources {e.get('sourceCount')} · primary {e.get('primarySource')}"
    )


def _fmt_detail(e: dict[str, Any]) -> str:
    lines = [
        f"{e.get('title')}",
        f"  type: {e.get('eventType')}" + (f" ({e.get('category')})" if e.get("category") else ""),
        f"  severity: {e.get('severity')}",
        f"  where: {e.get('placeName') or '—'} ({', '.join(e.get('countries') or []) or '—'})",
        f"  when: {e.get('publishedAt')}",
        f"  corroboration: {e.get('sourceCount')} source(s)",
    ]
    if e.get("summary"):
        lines.append(f"  summary: {e.get('summary')}")
    if e.get("channels"):
        lines.append(f"  economic channels (derived): {', '.join(e['channels'])}")
    if e.get("commodities"):
        lines.append(f"  commodities (derived): {', '.join(e['commodities'])}")
    if e.get("sectors"):
        lines.append(f"  sectors (derived): {', '.join(e['sectors'])}")
    srcs = e.get("sources") or []
    if srcs:
        lines.append("  sources:")
        for s in srcs[:8]:
            lines.append(f"    - {s.get('name') or s.get('id')}: {s.get('url') or ''}")
    return "\n".join(lines)


async def get_world_events(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    params: dict[str, Any] = {}
    for key in ("hours", "type", "severity", "iso2", "text", "limit", "id"):
        value = args.get(key)
        if value not in (None, ""):
            params[key] = value

    payload = await _fetch(ctx, "world_events", params)
    failure_class = payload.get("failureClass")

    if payload.get("status") != "OK":
        return (
            "SOURCE FAILURE — the world-state store could not be read "
            f"({failure_class or 'error'}).\n"
            "This is an infrastructure state, NOT evidence that no events happened. "
            "Do not report it as 'nothing is happening'.",
            {"status": "UNAVAILABLE", "failureClass": failure_class or "error"},
        )

    if "event" in payload:
        event = payload.get("event")
        if not event:
            return (
                f"Event not found for id {params.get('id')!r}.",
                {"status": "OK", "failureClass": "not_found"},
            )
        return _fmt_detail(event), {"status": "OK", "event": event}

    events = payload.get("events") or []
    hours = payload.get("hours")
    if not events:
        return (
            f"No world-state events matched (window {hours}h; store reachable, no match).\n"
            "This is a genuine no-match over a FILTERED feed — it is NOT proof the "
            "world was calm. If the absence matters, check source health / coverage.",
            {"status": "OK", "failureClass": "no_data", "count": 0},
        )

    lines = [f"{len(events)} world-state event(s) in the last {hours}h:"]
    lines.extend(_fmt_event(e) for e in events)
    lines.append("")
    lines.append(
        "Each event is a normalized, deduplicated record; `severity` is a "
        "classification and `relevance` is investor-relevance — neither is a "
        "probability. Derived channels/commodities are potential exposure, not "
        "causation. Absence of a type in this window is not proof of calm."
    )
    return "\n".join(lines), {"status": "OK", "count": len(events), "events": events}


def register_world_tools(registry: ToolRegistry) -> None:
    registry.register(
        ToolDefinition(
            name="get_world_events",
            description=(
                "Read normalized world-state events (geopolitical conflict, military, sanctions, "
                "trade, tariff, energy, shipping, monetary, natural-disaster, …) from JDdS — the "
                "same feed Investor Eye renders. Filter by window (hours), type, severity, ISO2 "
                "country or free text; pass `id` to fetch ONE event's full record. An unreadable "
                "store is reported as a source failure, never as 'no events'; an empty result is "
                "a no-match over a filtered feed, not proof the world was calm."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "hours": {"type": "integer", "description": "Look-back window in hours (default 168, max 2160)."},
                    "type": {"type": "string", "description": "Event type, e.g. conflict, sanction, trade, energy, natural_disaster."},
                    "severity": {"type": "string", "description": "Severity floor exact match: low | medium | high | critical."},
                    "iso2": {"type": "string", "description": "ISO-3166 alpha-2 country filter, e.g. UA, IR."},
                    "text": {"type": "string", "description": "Free-text filter over title/place."},
                    "limit": {"type": "integer", "description": "Max events (default 60, max 200)."},
                    "id": {"type": "string", "description": "Return ONE event by id or dedupKey instead of a list."},
                },
            },
            handler=get_world_events,
            permission="read",
            risk="low",
        )
    )


__all__ = ["register_world_tools"]
