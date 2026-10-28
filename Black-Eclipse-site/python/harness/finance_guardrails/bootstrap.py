"""Money-guardrail boot wiring.

Constructs the ONE `FinanceGuardrailService`, attaches it to the process-wide
service, and exposes it to handlers (computer/browser/agent) through a module
singleton. Best-effort: a failure leaves the capability unavailable rather than
blocking boot — the capability's own approvals still apply.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from .service import FinanceGuardrailService

log = logging.getLogger("harness.finance_guardrails")

_SERVICE: Optional[FinanceGuardrailService] = None


def install_finance_guardrail_layer(service: Any) -> Optional[FinanceGuardrailService]:
    global _SERVICE
    try:
        guardrails = FinanceGuardrailService(
            service.store, approvals=getattr(service, "approvals", None)
        )
        service.finance_guardrails = guardrails
        _SERVICE = guardrails
        from .tools import register_finance_guardrail_tools  # noqa: PLC0415

        register_finance_guardrail_tools(service.registry)
        return guardrails
    except Exception:  # noqa: BLE001 - never block boot
        service.finance_guardrails = None
        _SERVICE = None
        log.warning("money guardrails unavailable", exc_info=True)
        return None


def get_service() -> Optional[FinanceGuardrailService]:
    return _SERVICE


def set_service(service: Optional[FinanceGuardrailService]) -> None:
    """Explicit setter for tests and the operator API."""
    global _SERVICE
    _SERVICE = service


__all__ = [
    "FinanceGuardrailService",
    "get_service",
    "install_finance_guardrail_layer",
    "set_service",
]
