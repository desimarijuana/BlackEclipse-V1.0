"""Money-movement guardrail routes — the operator surface.

Read the state, change the caps, and exercise a hypothetical intent. Every
mutation is operator-gated by `require_operator` (transport/token, never a body
flag): an agent can never declare impairment, enter crisis mode, or clear the
panic pause on its own.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException

from ..deps import require_operator, service
from ..finance_guardrails.intent import intent_from_payload

router = APIRouter(tags=["finance-guardrails"])


def _guardrails() -> Any:
    guardrails = getattr(service, "finance_guardrails", None)
    if guardrails is None:
        raise HTTPException(status_code=503, detail="money guardrails are unavailable")
    return guardrails


@router.get("/finance-guardrails/status")
async def finance_guardrail_status(
    limit: int = 25, _: bool = Depends(require_operator),
) -> dict[str, Any]:
    return _guardrails().status(limit=limit)


@router.get("/finance-guardrails/intents")
async def finance_guardrail_intents(
    limit: int = 100, _: bool = Depends(require_operator),
) -> dict[str, Any]:
    guardrails = _guardrails()
    return {"available": True, "intents": guardrails.store.list_intents(limit=limit)}


@router.put("/finance-guardrails/config")
async def finance_guardrail_config(
    payload: dict[str, Any] = Body(default_factory=dict),
    _: bool = Depends(require_operator),
) -> dict[str, Any]:
    guardrails = _guardrails()
    config = guardrails.update_config(payload or {})
    return {"available": True, "config": config}


@router.post("/finance-guardrails/evaluate")
async def finance_guardrail_evaluate(
    payload: dict[str, Any] = Body(default_factory=dict),
    _: bool = Depends(require_operator),
) -> dict[str, Any]:
    """Evaluate a hypothetical intent WITHOUT recording it or moving money."""
    intent = intent_from_payload(payload or {})
    if intent is None:
        raise HTTPException(status_code=400, detail="not a recognised money action")
    verdict = _guardrails().evaluate(intent)
    return {"available": True, "verdict": verdict.to_dict()}
