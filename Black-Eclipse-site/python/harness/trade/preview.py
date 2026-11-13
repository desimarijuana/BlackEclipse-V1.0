"""Order preview: validate, price-check and (optionally) request an approval.

Extracted from `trade/service.py` to keep that file inside the size ceiling. The
behavior is unchanged: the broker's own `order_check`, the connection policy, the
money guardrails and (optionally) a typed-confirmation phrase. Nothing is sent.

`record_approval=False` is the graph dry-run path: the SAME validation without an
approval row, so previewing a workflow never leaves approval cards behind.
"""

from __future__ import annotations

from typing import Any

from .adapter import AdapterUnavailable
from .authorizer import evaluate_guardrails, money_intent_for, request_approval
from .model import OrderIntent, TradeRefused
from .policy import TradePolicy


def preview_order(
    service: Any,
    connection_id: str,
    payload: dict[str, Any],
    *,
    record_approval: bool = True,
    run_id: str = "",
) -> dict[str, Any]:
    """The preview implementation; `BrokerService.preview_order` delegates here."""
    try:
        connection, execution_mode = service._execution_connection(connection_id)
    except TradeRefused as exc:
        return {
            "available": True,
            "allowed": False,
            "status": "REFUSED",
            "mode": None,
            "connectionId": connection_id,
            "approval": None,
            "error": exc.to_dict(),
            "reasons": [exc.message],
        }
    intent = OrderIntent.from_payload(
        payload, connection_id=connection.id, magic_default=service._magic(connection)
    )
    adapter = service._trading_adapter(connection)
    try:
        preview = adapter.order_preview(intent)
    except AdapterUnavailable as exc:
        raise TradeRefused(exc.code, exc.reason, status_code=503) from exc
    except TradeRefused:
        raise
    except Exception as exc:  # noqa: BLE001
        raise TradeRefused(
            "ADAPTER_ERROR", f"{connection.kind} adapter failed: {exc}", status_code=502
        ) from exc
    finally:
        try:
            adapter.close()
        except Exception:  # noqa: BLE001
            pass

    try:
        service._assert_account_mode(preview, execution_mode)
    except TradeRefused as exc:
        service.connections.record_event(
            connection.id, "preview", "refused",
            {"digest": intent.digest, "code": exc.code},
        )
        return {
            "available": True,
            "allowed": False,
            "status": "REFUSED",
            "mode": execution_mode,
            "connectionId": connection.id,
            "intent": intent.to_dict(),
            "digest": intent.digest,
            "preview": preview,
            "policy": None,
            "guardrail": None,
            "approval": None,
            "requiresTypedConfirmation": False,
            "confirmPhrase": None,
            "error": exc.to_dict(),
            "reasons": [exc.message],
        }
    policy = TradePolicy.from_connection(connection).evaluate(preview)
    money_intent = money_intent_for(connection, intent, preview)
    verdict = evaluate_guardrails(service.guardrails, money_intent, record=False)
    reasons = (
        list(preview.get("reasons") or [])
        + list(policy.get("reasons") or [])
        + list(getattr(verdict, "reasons", []) or [])
    )
    allowed = (
        bool(preview.get("ok"))
        and bool(policy.get("allowed"))
        and str(verdict.decision) not in ("deny", "escalate")
    )
    if execution_mode == "live":
        requires_typed = True
        confirm_phrase = (
            f"LIVE {intent.side.upper()} "
            f"{float(preview.get('volume') or intent.volume):g} "
            f"{preview.get('symbol') or intent.symbol}"
        )
    else:
        requires_typed = bool(verdict.requires_typed_confirmation)
        confirm_phrase = str(verdict.confirm_phrase) if requires_typed else None
    approval = None
    if allowed and record_approval:
        approval = request_approval(
            service.approvals,
            connection,
            intent,
            preview,
            verdict,
            risk="critical" if execution_mode == "live" else "high",
            run_id=run_id,
        )
        if str(approval.get("status")) == "denied":
            allowed = False
            reasons.append(
                "this exact order was denied; change the order to request a new decision"
            )
    service.connections.record_event(
        connection.id,
        "preview",
        "allowed" if allowed else "refused",
        {"digest": intent.digest, "rules": policy.get("rules") or []},
    )
    return {
        "available": True,
        "allowed": allowed,
        "mode": execution_mode,
        "connectionId": connection.id,
        "intent": intent.to_dict(),
        "digest": intent.digest,
        "preview": preview,
        "policy": policy,
        "guardrail": verdict.to_dict(),
        "approval": service._public_approval(approval),
        "requiresTypedConfirmation": requires_typed,
        "confirmPhrase": confirm_phrase,
        "reasons": reasons,
    }


__all__ = ["preview_order"]
