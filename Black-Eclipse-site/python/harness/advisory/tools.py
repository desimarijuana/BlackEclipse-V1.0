"""Agent-facing Advisory Ledger tools (flat `advisory_*` names, all read-only).

The ledger is a record of what the agent recommended and how it turned out; the
tools let the agent recall its own past calls. Nothing here mutates it — outcomes
are recorded by the runtime, never by a model tool call.
"""

from __future__ import annotations

from typing import Any

READ = "read"


def _service(ctx: Any) -> Any:
    service = getattr(ctx, "advisory_service", None)
    if service is None:
        raise RuntimeError("the advisory ledger is not available in this run")
    return service


def _owner(ctx: Any) -> Any:
    return getattr(ctx, "user_id", None)


async def advisory_list(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    service = _service(ctx)
    rows = service.list_decisions(
        portfolio_id=args.get("portfolio_id"),
        owner_id=args.get("owner_id") or _owner(ctx),
        status=args.get("status"),
        limit=int(args.get("limit") or 50),
    )
    lines = [f"{len(rows)} recorded recommendation(s):"]
    for r in rows:
        symbols = " ".join(r.get("symbols") or []) or "-"
        outcome = r.get("outcome")
        scored = f", {outcome['verdict']}" if outcome else ", unscored"
        lines.append(
            f"  - [{r['status']}] {r['action']} {symbols} "
            f"method={r.get('method') or 'MISSING'} "
            f"horizon={r.get('horizon') or 'MISSING'} "
            f"dueAt={r.get('dueAt') or '-'}{scored} ({r['createdAt']})"
        )
    return "\n".join(lines), {"decisions": rows}


async def advisory_get(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    service = _service(ctx)
    record = service.get_decision(args["decision_id"])
    if record is None:
        return f"No recommendation {args['decision_id']}.", {"status": "NOT_FOUND"}
    outcome = record.get("outcome")
    verdict = f"; outcome {outcome['verdict']}" if outcome else ""
    return (
        f"Recommendation {record['id']}: {record['action']} "
        f"{' '.join(record.get('symbols') or []) or 'the portfolio'} "
        f"[{record['status']}]{verdict}.",
        record,
    )


async def advisory_scorecard(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    service = _service(ctx)
    card = service.scorecard(
        portfolio_id=args.get("portfolio_id"),
        owner_id=args.get("owner_id") or _owner(ctx),
    )
    hit = card["hitRate"]
    lines = [
        f"{card['total']} recommendation(s): {card['byStatus']['computed']} computed, "
        f"{card['byStatus']['sourced']} sourced, {card['byStatus']['unverified']} unverified; "
        f"{card['evaluated']} evaluated"
        + (f", hit rate {hit:.0%}" if hit is not None else "") + "; "
        f"{card.get('unscored', 0)} without a horizon, "
        f"{card.get('overdueCount', 0)} overdue, "
        f"{card.get('needsBackfill', 0)} need backfill."
    ]
    for bucket in card.get("byMethod") or []:
        rate = bucket.get("hitRate")
        lines.append(
            f"  method {bucket['method']}: {bucket['total']} total, "
            f"{bucket['evaluated']} evaluated, "
            f"hit rate {'n/a' if rate is None else f'{rate:.0%}'}"
            + (", DEMOTED" if bucket.get("demoted") else "")
        )
    if card.get("demotedMethods"):
        lines.append("Demoted methods: " + ", ".join(card["demotedMethods"]) + ".")
    return "\n".join(lines), card


async def advisory_evaluate_outcomes(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    """Fetch current prices via the market gateway and record decision outcomes."""
    service = _service(ctx)
    gateway = getattr(ctx, "market_gateway", None)
    result = await service.auto_evaluate(
        gateway, benchmark_return=args.get("benchmark_return"), horizon=args.get("horizon"),
    )
    text = (
        f"Evaluated {result['evaluated']} recommendation(s)"
        + (f"; {len(result['skipped'])} skipped (no price)." if result.get("skipped") else ".")
    )
    return text, result


def register_advisory_tools(registry: Any) -> None:
    from ..tools import ToolDefinition

    def _def(name: str, description: str, handler: Any, schema: dict[str, Any]) -> None:
        registry.register(ToolDefinition(
            name=name, description=description, input_schema=schema, handler=handler,
            permission=READ, risk="none",
        ))

    _def("advisory_list",
         "List the recommendations this agent has recorded (the Advisory Ledger), "
         "with each one's verification status (computed/sourced/unverified).",
         advisory_list,
         {"type": "object", "properties": {
             "portfolio_id": {"type": "string"}, "owner_id": {"type": "string"},
             "status": {"type": "string", "enum": ["computed", "sourced", "unverified"]},
             "limit": {"type": "integer"}}})
    _def("advisory_get",
         "Read one recorded recommendation: what was advised, on what basis, and how it turned out.",
         advisory_get,
         {"type": "object", "properties": {"decision_id": {"type": "string"}},
          "required": ["decision_id"]})
    _def("advisory_scorecard",
         "Summarise recorded recommendations and their outcomes: counts by status, "
         "evaluated count, hit rate and average realized vs benchmark return.",
         advisory_scorecard,
         {"type": "object", "properties": {
             "portfolio_id": {"type": "string"}, "owner_id": {"type": "string"}}})
    _def("advisory_evaluate_outcomes",
         "Fetch current prices and record the outcome (right/wrong/neutral) of open "
         "recommendations that captured an entry price. Deterministic; skips any "
         "recommendation with no price.",
         advisory_evaluate_outcomes,
         {"type": "object", "properties": {
             "benchmark_return": {"type": "number"}, "horizon": {"type": "string"}}})


# The canonical tool names, imported by `agents.py` so the allowlist cannot drift.
ADVISORY_TOOLS: tuple[str, ...] = (
    "advisory_list", "advisory_get", "advisory_scorecard", "advisory_evaluate_outcomes",
)

__all__ = [
    "ADVISORY_TOOLS",
    "advisory_evaluate_outcomes", "advisory_get", "advisory_list",
    "advisory_scorecard", "register_advisory_tools",
]
