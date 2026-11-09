"""Graph nodes for typed decisions (System One-shaped judgments).

Two adapters, one capability:

  * `decision.ask`  — the general node: a wired/configured `state` plus a
    declared question template in, typed answers + policy verdicts out.
  * `decision.demo` — a zero-config demonstration so a workflow can exercise the
    whole layer (contract → provider → confidence policy → audit) without a key.

An answer is INFORMATION, never an authorization. These nodes cannot move money,
place a trade or widen a run's grants; they return a judgment plus the policy
verdict that says whether it may be acted on (`answered`), must be treated as a
hint (`review`), or does not exist (`unavailable`).

The runtime side of the pair is `src/lib/graph-studio/registry-decisions.ts`.
Keep the two in lockstep and regenerate the manifest (`npm run graph:manifest`).
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from .model import ExecutionMode, PortDef, PortType, SideEffect
from .registry import ConfigField, NodeDef, NodeExecContext

_ALL = tuple(ExecutionMode)

#: The process-wide decision service, bound at boot to the ONE layer that owns
#: the provider registry, the confidence policy and the audit store.
_service: Any = None


def set_decision_service(service: Any) -> None:
    global _service
    _service = service


def _require_service() -> Any:
    if _service is None:
        raise ValueError(
            "the decision layer is not available in this runtime; typed decisions "
            "cannot be evaluated"
        )
    return _service


def _json_object(raw: Any, *, field: str) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    text = str(raw or "").strip()
    if not text:
        return {}
    try:
        parsed = json.loads(text)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be valid JSON") from exc
    if not isinstance(parsed, dict):
        raise ValueError(f"{field} must be a JSON object")
    return parsed


def _state(context: NodeExecContext) -> Any:
    wired = context.inputs.get("state")
    if isinstance(wired, dict) and wired:
        return wired
    if isinstance(wired, str) and wired.strip():
        return wired
    configured = _json_object(context.config.get("stateJson"), field="stateJson")
    if not configured:
        raise ValueError(
            "decision.ask needs a state: wire the `state` input or set `stateJson`"
        )
    return configured


def _questions(context: NodeExecContext) -> dict[str, Any]:
    configured = _json_object(context.config.get("questionsJson"), field="questionsJson")
    if not configured:
        raise ValueError(
            "decision.ask needs a question template: set `questionsJson` to an object "
            "of {id: {type: choice|score|noul, instructions, criteria?}}"
        )
    return configured


def _summary(result: Any) -> str:
    if result.status == "unavailable":
        return f"Decision unavailable: {result.reason or 'no provider answered'}."
    parts = [
        f"{question_id}={_answer_text(answer)}"
        for question_id, answer in result.answers.items()
    ]
    verdict = "usable as a decision" if result.status == "answered" else "a hint only"
    return f"{result.status} via {result.provider or 'unknown'}: " + ", ".join(parts) + f" ({verdict})."


def _answer_text(answer: Any) -> str:
    if answer.type == "choice":
        return answer.choice
    if answer.type == "score":
        return f"{answer.score:g}"
    return f"{answer.noul:.2f}"


async def _ask(
    context: NodeExecContext,
    *,
    state: Any,
    questions: dict[str, Any],
    tool: str,
) -> Any:
    from ..decisions.contracts import DecisionRequest  # noqa: PLC0415

    request = DecisionRequest.model_validate(
        {
            "state": state,
            "questions": questions,
            "timeout_ms": int(context.config.get("timeoutMs", 15_000)),
        }
    )
    provider = str(context.config.get("provider") or "").strip() or None
    return await _require_service().ask(
        request,
        provider=provider,
        policy=_policy(context.config),
        run_id=context.run_id or None,
        owner_id=context.user_id,
        conversation_id=None,
        tool=tool,
    )


def _policy(config: dict[str, Any]) -> Any:
    from ..decisions.policy import DecisionPolicy  # noqa: PLC0415

    return DecisionPolicy(
        min_confidence=float(config.get("minConfidence", 0.6)),
        min_probability=float(config.get("minProbability", 0.6)),
    )


def _payload(result: Any) -> dict[str, Any]:
    body = result.model_dump(mode="json")
    return {
        "answers": body.get("answers") or {},
        "status": body.get("status") or "unavailable",
        "provider": body.get("provider") or "",
        "recordId": body.get("record_id") or "",
        "reason": body.get("reason") or "",
        "summary": _summary(result),
    }


def exec_ask(context: NodeExecContext) -> dict[str, Any]:
    result = asyncio.run(
        _ask(
            context,
            state=_state(context),
            questions=_questions(context),
            tool="graph.decision.ask",
        )
    )
    return _payload(result)


# ── the demo ────────────────────────────────────────────────────────────────

# Each scenario is a real (tiny) typed-decision request whose questions carry a
# declared `rule`. The rules provider is deterministic and fully offline, so the
# demo needs no key and no network — and still exercises the same request →
# policy → audit pipeline a TypeSafe/LLM provider would go through.
_SCENARIOS: dict[str, dict[str, Any]] = {
    "risk_gate": {
        "state": {"marginRatio": 0.18, "drawdownPct": 6.5},
        "questions": {
            "margin_within_limit": {
                "type": "noul",
                "instructions": "Is the margin ratio at or below the 0.25 limit?",
                "rule": {"fact": "marginRatio", "op": "lte", "value": 0.25},
            },
            "drawdown_alert": {
                "type": "noul",
                "instructions": "Has drawdown reached the 10% alert level?",
                "rule": {"fact": "drawdownPct", "op": "gte", "value": 10.0},
            },
        },
    },
    "route_ticket": {
        "state": {"ticketKind": "billing"},
        "questions": {
            "team": {
                "type": "choice",
                "instructions": "Which team should handle this ticket?",
                "criteria": {
                    "billing": "Payments, invoices or refunds",
                    "technical": "A bug or an outage",
                },
                "rule": {"fact": "ticketKind", "op": "eq", "value": "billing"},
            }
        },
    },
}


def exec_demo(context: NodeExecContext) -> dict[str, Any]:
    name = str(context.config.get("scenario") or "risk_gate")
    scenario = _SCENARIOS.get(name)
    if scenario is None:
        raise ValueError(
            f"unknown demo scenario {name!r}; use one of: {', '.join(sorted(_SCENARIOS))}"
        )
    # A wired state overrides the built-in sample so the demo can be pointed at
    # real data; with nothing wired it stays truly zero-config.
    wired = context.inputs.get("state")
    state = wired if isinstance(wired, dict) and wired else scenario["state"]
    result = asyncio.run(
        _ask(
            context,
            state=state,
            questions=scenario["questions"],
            tool="graph.decision.demo",
        )
    )
    payload = _payload(result)
    payload["scenario"] = name
    return payload


# ── definitions ─────────────────────────────────────────────────────────────

def _port(port_id: str, name: str, port_type: PortType, *, optional: bool = False) -> PortDef:
    return PortDef(id=port_id, name=name, type=port_type, optional=optional)


def build_decision_nodes() -> list[NodeDef]:
    """The typed-decision pack. Read-only in intent; the audit record is local."""
    return [
        NodeDef(
            type="decision.ask",
            version="1.0.0",
            label="Typed decision",
            category="decision",
            inputs=(
                _port("state", "State", PortType.OBJECT, optional=True),
            ),
            outputs=(
                _port("answers", "Typed answers", PortType.OBJECT),
                _port("status", "Status", PortType.STRING),
                _port("summary", "Summary", PortType.STRING),
                _port("provider", "Provider", PortType.STRING),
                _port("recordId", "Audit record", PortType.STRING),
                _port("reason", "Reason", PortType.STRING),
            ),
            config_fields=(
                ConfigField("provider", "string", "", max_length=80),
                ConfigField("questionsJson", "string", "", max_length=20_000),
                ConfigField("stateJson", "string", "", max_length=20_000),
                ConfigField("minConfidence", "number", 0.6, minimum=0.0, maximum=1.0),
                ConfigField("minProbability", "number", 0.6, minimum=0.0, maximum=1.0),
                ConfigField("timeoutMs", "integer", 15_000, minimum=100, maximum=120_000),
            ),
            capabilities=("decision.ask",),
            side_effects=SideEffect.MODEL,
            allowed_modes=_ALL,
            timeout_ms=130_000,
            executor=exec_ask,
        ),
        NodeDef(
            type="decision.demo",
            version="1.0.0",
            label="Typed decision (demo)",
            category="decision",
            inputs=(
                _port("state", "State (optional)", PortType.OBJECT, optional=True),
            ),
            outputs=(
                _port("answers", "Typed answers", PortType.OBJECT),
                _port("status", "Status", PortType.STRING),
                _port("summary", "Summary", PortType.STRING),
                _port("provider", "Provider", PortType.STRING),
                _port("recordId", "Audit record", PortType.STRING),
                _port("reason", "Reason", PortType.STRING),
            ),
            config_fields=(
                ConfigField(
                    "scenario", "enum", "risk_gate",
                    enum=("risk_gate", "route_ticket"),
                ),
            ),
            capabilities=("decision.ask",),
            side_effects=SideEffect.LOCAL_WRITE,
            allowed_modes=_ALL,
            timeout_ms=20_000,
            executor=exec_demo,
        ),
    ]


__all__ = [
    "build_decision_nodes",
    "exec_ask",
    "exec_demo",
    "set_decision_service",
]
