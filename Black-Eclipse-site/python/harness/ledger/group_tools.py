"""Agent tools for entity groups, consolidation and exports.

Third and last tool module in the `ledger_*` family (the ledger itself, the AR/AP
subledger, and this). It registers on the SAME registry, and its mutations carry
effect `ledger.write`, so the existing authorizer owns them.
"""

from __future__ import annotations

from typing import Any

from .errors import LedgerError
from .exports import export as _export
from .tools import READ, WRITE, WRITE_EFFECT, _actor, _fail, _guarded, _ledger_id, _service

GROUP_READ_TOOLS = ["ledger_group_list", "ledger_consolidate", "ledger_export"]
GROUP_WRITE_TOOLS = ["ledger_group_create", "ledger_group_add_member"]

GROUP_TOOLS = GROUP_READ_TOOLS + GROUP_WRITE_TOOLS


async def ledger_group_create(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    service = _service(ctx)
    try:
        payload = service.consolidation.create_group(
            str(args.get("name") or ""),
            base_currency=str(args.get("base_currency") or args.get("baseCurrency") or "USD"),
            owner_id=args.get("owner_id") or getattr(ctx, "user_id", None),
            notes=args.get("notes"),
            actor=getattr(ctx, "user_id", None),
        )
    except LedgerError as exc:
        return _fail(exc)
    return (
        f"Created group {payload['id']} ({payload['name']}, {payload['baseCurrency']})."
    ), payload


async def ledger_group_add_member(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    service = _service(ctx)
    try:
        payload = service.consolidation.add_member(
            str(args.get("group_id") or args.get("groupId") or ""),
            str(args.get("ledger_id") or args.get("ledgerId") or ""),
            ownership_pct=args.get("ownership_pct") or args.get("ownershipPct") or "100",
            actor_id=_actor(ctx),
        )
    except LedgerError as exc:
        return _fail(exc)
    return (
        f"Added ledger {payload['ledgerId']} to the group at {payload['ownershipPct']}%."
    ), payload


async def ledger_group_list(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    service = _service(ctx)
    rows = service.consolidation.list_groups(
        args.get("owner_id") or getattr(ctx, "user_id", None)
    )
    lines = [f"{len(rows)} group(s):"]
    for row in rows:
        lines.append(
            f"  {row['id']}  {row['name']}  ({row['baseCurrency']}, "
            f"{len(row.get('members') or [])} member(s))"
        )
    return "\n".join(lines), {"groups": rows}


async def ledger_consolidate(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    service = _service(ctx)
    try:
        payload = service.consolidation.consolidate(
            str(args.get("group_id") or args.get("groupId") or ""),
            as_of=args.get("as_of") or args.get("asOf"),
            start=args.get("start"),
            rates=args.get("rates") or {},
            actor_id=_actor(ctx),
        )
    except LedgerError as exc:
        return _fail(exc)
    text = (
        f"Consolidation of {payload['groupName']!r} at {payload['asOf']} "
        f"({payload['groupCurrency']}): {payload['status']}."
    )
    if payload.get("balanceSheet"):
        text += (
            f" Assets {payload['balanceSheet']['assets']['total']}, liabilities "
            f"{payload['balanceSheet']['liabilities']['total']}, equity "
            f"{payload['balanceSheet']['equity']['total']}."
        )
    for finding in payload["findings"][:4]:
        text += f"\n  [{finding['severity']}] {finding['code']}: {finding['detail']}"
    return text, payload


async def ledger_export(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    service = _service(ctx)
    try:
        payload = _export(
            service,
            _ledger_id(args),
            fmt=str(args.get("format") or "journal_csv"),
            start=args.get("start"),
            end=args.get("end"),
            limit=int(args.get("limit") or 5000),
            actor_id=_actor(ctx),
        )
    except LedgerError as exc:
        return _fail(exc)
    size = len(payload["content"])
    text = (
        f"Exported {payload['format']} for {payload['ledgerId']}: "
        f"{payload['filename']} ({size} bytes, {payload['entryCount']} entries)."
    )
    if payload.get("warning"):
        text += f" {payload['warning']}"
    return text, payload


def register_group_tools(registry: Any) -> None:
    from ..tools import ToolDefinition  # noqa: PLC0415

    def _def(name: str, description: str, handler: Any, schema: dict[str, Any],
             permission: str, effect: Any = None, timeout: int = 20_000) -> None:
        registry.register(ToolDefinition(
            name=name, description=description, input_schema=schema,
            handler=_guarded(handler),
            permission=permission, risk="low" if permission == READ else "medium",
            timeout_ms=timeout, effect=effect,
        ))

    _def("ledger_group_create",
         "Create an entity group (a consolidation scope) in a reporting currency. "
         "A group owns no journal; it aggregates member ledgers.",
         ledger_group_create,
         {"type": "object", "properties": {
             "name": {"type": "string"},
             "base_currency": {"type": "string", "description": "Reporting currency."},
             "notes": {"type": "string"}, "owner_id": {"type": "string"}},
          "required": ["name"]},
         WRITE, WRITE_EFFECT)
    _def("ledger_group_add_member",
         "Add a ledger to a group at an ownership percentage (proportionate "
         "consolidation; there is no non-controlling-interest line).",
         ledger_group_add_member,
         {"type": "object", "properties": {
             "group_id": {"type": "string"}, "ledger_id": {"type": "string"},
             "ownership_pct": {"type": "string", "description": "0 < pct <= 100."}},
          "required": ["group_id", "ledger_id"]},
         WRITE, WRITE_EFFECT)
    _def("ledger_group_list", "List entity groups and their members.",
         ledger_group_list,
         {"type": "object", "properties": {"owner_id": {"type": "string"}}},
         READ)
    _def("ledger_consolidate",
         "Consolidate a group: sum member account nets (scaled by ownership and a "
         "supplied rate per foreign currency), eliminate intercompany pairs by "
         "subtype, and produce consolidated balance sheet + P&L with checks. An "
         "unmatched intercompany balance is reported, never force-balanced.",
         ledger_consolidate,
         {"type": "object", "properties": {
             "group_id": {"type": "string"}, "as_of": {"type": "string"},
             "start": {"type": "string"},
             "rates": {"type": "object",
                       "description": "currency → rate, for members not in the group currency."}},
          "required": ["group_id"]},
         READ)
    _def("ledger_export",
         "Export a ledger as `journal_csv`, `trial_balance_csv`, `json` or `xbrl`. "
         "The XBRL instance is well formed but NOT taxonomy-conformant (no IFRS/GAAP "
         "mapping); SAF-T is refused because its schema is jurisdiction-specific.",
         ledger_export,
         {"type": "object", "properties": {
             "ledger_id": {"type": "string"},
             "format": {"type": "string",
                        "enum": ["journal_csv", "trial_balance_csv", "json", "xbrl"]},
             "start": {"type": "string"}, "end": {"type": "string"},
             "limit": {"type": "integer"}},
          "required": ["ledger_id", "format"]},
         READ)


__all__ = [
    "GROUP_READ_TOOLS",
    "GROUP_TOOLS",
    "GROUP_WRITE_TOOLS",
    "register_group_tools",
]
