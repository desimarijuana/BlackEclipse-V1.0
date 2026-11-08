"""Agent-facing decision tools.

`decision_ask` is the only way a model can request a typed judgment. It is
read-permission and risk "none": an answer is information, never an
authorization, and it can never move money or change a portfolio.

The ledger tools are read-only for the same reason the Advisory Ledger tools are:
the runtime writes the audit record, not a model call.
"""

from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from ..tools import ToolDefinition
from .contracts import DecisionRequest, DecisionResult
from .policy import DecisionPolicy

READ = "read"


def _service(ctx: Any) -> Any:
    service = getattr(ctx, "decision_service", None)
    if service is None:
        raise RuntimeError("the decision layer is not available in this run")
    return service


def _render(result: DecisionResult) -> str:
    if result.status == "unavailable":
        return (
            "Decision unavailable"
            + (f": {result.reason}" if result.reason else "")
            + ". Nothing was inferred."
        )
    lines = [f"{len(result.answers)} typed answer(s) [{result.status}]:",]
    for question_id, answer in result.answers.items():
        verdict = (result.policy.get(question_id) or {}).get("verdict", "review")
        if answer.type == "choice":
            probability = answer.probabilities.get(answer.choice)
            detail = f"p={probability:.2f}" if probability is not None else ""
            if answer.confidence is not None:
                detail = (detail + " " if detail else "") + f"confidence={answer.confidence:.2f}"
            lines.append(f"  - {question_id}: {answer.choice} ({detail or 'no probability'}) [{verdict}]")
        elif answer.type == "score":
            detail = (
                f"confidence={answer.confidence:.2f}"
                if answer.confidence is not None
                else "no confidence"
            )
            lines.append(f"  - {question_id}: {answer.score:g} ({detail}) [{verdict}]")
        else:
            lines.append(f"  - {question_id}: {answer.noul:.2f} probability [{verdict}]")
    if result.status == "review":
        lines.append("At least one answer sits inside the abstain band: treat it as a hint, not a decision.")
    lines.append("These are model judgments, not verified financial facts.")
    return "\n".join(lines)


async def decision_ask(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    try:
        service = _service(ctx)
    except RuntimeError as exc:
        return f"Decision unavailable: {exc}. Nothing was inferred.", {"status": "UNAVAILABLE"}
    try:
        request = DecisionRequest.model_validate(
            {
                "state": args.get("state"),
                "questions": args.get("questions"),
                "model": args.get("model"),
                "timeout_ms": args.get("timeout_ms") or 15_000,
            }
        )
    except ValidationError as exc:
        return (
            "Invalid decision request: " + "; ".join(
                f"{'.'.join(str(p) for p in error['loc'])}: {error['msg']}"
                for error in exc.errors()
            ),
            {"status": "INVALID", "errors": exc.errors(include_url=False)},
        )

    policy = None
    if args.get("min_confidence") is not None or args.get("min_probability") is not None:
        policy = DecisionPolicy(
            min_confidence=float(args.get("min_confidence", 0.6)),
            min_probability=float(args.get("min_probability", 0.6)),
        )

    result = await service.ask(
        request,
        provider=args.get("provider"),
        policy=policy,
        run_id=getattr(ctx, "run_id", None),
        owner_id=getattr(ctx, "user_id", None),
        conversation_id=getattr(ctx, "conversation_id", None),
        tool="decision_ask",
    )
    return _render(result), result.model_dump(mode="json")


async def decision_list(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    try:
        service = _service(ctx)
    except RuntimeError as exc:
        return f"Decision unavailable: {exc}.", {"status": "UNAVAILABLE", "decisions": []}
    records = service.list_records(
        owner_id=args.get("owner_id") or getattr(ctx, "user_id", None),
        status=args.get("status"),
        limit=int(args.get("limit") or 50),
    )
    lines = [f"{len(records)} recorded decision(s):"]
    for record in records:
        outcome = record.get("outcome")
        scored = f", outcome={outcome['verdict']}" if outcome else ", unscored"
        lines.append(
            f"  - [{record['status']}] {record['provider']}/{record['model'] or '-'} "
            f"questions={record['questionHash'][:8]}… "
            f"latency={record['latencyMs']}ms{scored} ({record['createdAt']})"
        )
    return "\n".join(lines), {"decisions": records}


async def decision_scorecard(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    try:
        service = _service(ctx)
    except RuntimeError as exc:
        return f"Decision unavailable: {exc}.", {"status": "UNAVAILABLE"}
    card = service.scorecard(
        owner_id=args.get("owner_id") or getattr(ctx, "user_id", None)
    )
    accuracy = card.get("accuracy")
    lines = [
        f"{card['total']} decision request(s): "
        f"{card['byStatus']['answered']} answered, "
        f"{card['byStatus']['review']} review, "
        f"{card['byStatus']['unavailable']} unavailable; "
        f"{card['evaluated']} evaluated"
        + (f", accuracy {accuracy:.0%}" if accuracy is not None else "")
        + "."
    ]
    for provider, count in (card.get("byProvider") or {}).items():
        lines.append(f"  provider {provider}: {count} request(s)")
    if card.get("byOutcome"):
        lines.append(
            "  outcomes: "
            + ", ".join(f"{key}={value}" for key, value in card["byOutcome"].items())
        )
    return "\n".join(lines), card


def register_decision_tools(registry: Any) -> None:
    def _def(name: str, description: str, handler: Any, schema: dict[str, Any]) -> None:
        registry.register(
            ToolDefinition(
                name=name,
                description=description,
                input_schema=schema,
                handler=handler,
                permission=READ,
                risk="none",
            )
        )

    _def(
        "decision_ask",
        "Ask one or more TYPED decision questions about a state (choice/score/noul) "
        "and get typed answers with probabilities and confidence. Use for bounded "
        "judgments (route, classify, score, does-this-support-that), not for "
        "writing prose. Returns 'unavailable' rather than guessing.",
        decision_ask,
        {
            "type": "object",
            "properties": {
                "state": {"type": ["string", "object"]},
                "questions": {
                    "type": "object",
                    "description": (
                        "Map of stable question id -> question. Each question is "
                        "{type: choice|score|noul, instructions, criteria?}. "
                        "choice criteria is {option: description}; score criteria is "
                        "an ordered list of level descriptions."
                    ),
                },
                "provider": {
                    "type": "string",
                    "description": "Optional provider name (e.g. rules, typesafe).",
                },
                "model": {"type": "string"},
                "min_confidence": {"type": "number"},
                "min_probability": {"type": "number"},
                "timeout_ms": {"type": "integer"},
            },
            "required": ["state", "questions"],
        },
    )
    _def(
        "decision_list",
        "List the typed decision requests this agent has recorded, with their "
        "status and any appended outcome.",
        decision_list,
        {
            "type": "object",
            "properties": {
                "owner_id": {"type": "string"},
                "status": {"type": "string", "enum": ["answered", "review", "unavailable"]},
                "limit": {"type": "integer"},
            },
        },
    )
    _def(
        "decision_scorecard",
        "Summarise recorded decisions and outcomes: counts by status, provider and "
        "outcome, plus accuracy over evaluated records.",
        decision_scorecard,
        {"type": "object", "properties": {"owner_id": {"type": "string"}}},
    )


# The canonical tool names, imported by `agents.py` so the allowlist cannot drift.
DECISION_TOOLS: tuple[str, ...] = (
    "decision_ask",
    "decision_list",
    "decision_scorecard",
)


__all__ = [
    "DECISION_TOOLS",
    "decision_ask",
    "decision_list",
    "decision_scorecard",
    "register_decision_tools",
]
