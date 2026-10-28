"""Agent-facing money-guardrail tools (read-only).

The agent may READ its guardrail state and ASK what would happen to a
hypothetical intent. It can never change the configuration, declare impairment,
or clear crisis/panic — those are operator routes only.
"""

from __future__ import annotations

from typing import Any

from .intent import intent_from_payload

READ = "read"


def _service(ctx: Any) -> Any:
    service = getattr(ctx, "finance_guardrails", None)
    if service is None:
        from .bootstrap import get_service  # noqa: PLC0415

        service = get_service()
    if service is None:
        raise RuntimeError("money guardrails are not available in this run")
    return service


async def finance_guardrail_status(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    service = _service(ctx)
    status = service.status(limit=int(args.get("limit") or 10))
    config = status["config"]
    aggregates = status["aggregates"]
    lines = [
        f"Money guardrails: mode={config.get('mode')} "
        f"impaired={config.get('impairedMode')} crisis={config.get('crisisMode')} "
        f"paused={config.get('panicPaused')}",
        f"Today: {aggregates['spendToday']:,.2f}; last hour: {aggregates['countLastHour']} "
        f"movement(s); 30 days: {aggregates['spend30d']:,.2f}",
        f"Caps: per-transaction={config.get('perTxnCap') or 'none'} "
        f"daily={config.get('dailyCap') or 'none'} "
        f"velocity={config.get('velocityPerHour') or 'none'}/hour",
    ]
    return "\n".join(lines), status


async def finance_guardrail_check(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    service = _service(ctx)
    intent = intent_from_payload(args)
    if intent is None:
        return (
            "Not a recognised money action. Give an action such as buy, sell, "
            "transfer, withdraw or payment.",
            {"status": "not_a_money_action"},
        )
    verdict = service.evaluate(intent)
    reasons = "; ".join(verdict.reasons) or "no guardrail friction"
    return (
        f"Guardrail verdict for {intent.action}: {verdict.decision} "
        f"(risk={verdict.risk}). {reasons}",
        verdict.to_dict(),
    )


def register_finance_guardrail_tools(registry: Any) -> None:
    from ..tools import ToolDefinition

    def _def(name: str, description: str, handler: Any, schema: dict[str, Any]) -> None:
        registry.register(ToolDefinition(
            name=name, description=description, input_schema=schema, handler=handler,
            permission=READ, risk="none",
        ))

    _def(
        "finance_guardrail_status",
        "Read the active money-movement guardrails: mode, caps, spend aggregates, "
        "impaired/crisis/panic state and recent decisions. Read-only.",
        finance_guardrail_status,
        {"type": "object", "properties": {"limit": {"type": "integer"}}},
    )
    _def(
        "finance_guardrail_check",
        "Ask what the money guardrails would decide for a hypothetical action "
        "(buy/sell/transfer/withdraw/payment) without performing it or recording it.",
        finance_guardrail_check,
        {"type": "object", "properties": {
            "action": {"type": "string"},
            "amount": {"type": "number"},
            "currency": {"type": "string"},
            "counterparty": {"type": "string"},
            "instrument": {"type": "string"},
            "account": {"type": "string"},
            "channel": {"type": "string"},
            "text": {"type": "string"},
        }, "required": ["action"]},
    )


FINANCE_GUARDRAIL_TOOLS: tuple[str, ...] = (
    "finance_guardrail_status", "finance_guardrail_check",
)


__all__ = [
    "FINANCE_GUARDRAIL_TOOLS",
    "finance_guardrail_check",
    "finance_guardrail_status",
    "register_finance_guardrail_tools",
]
