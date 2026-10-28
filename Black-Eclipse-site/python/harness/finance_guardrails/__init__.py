"""Money-movement guardrails: scam/coercion, impaired spending, crisis, limits.

One evaluation pipeline and one confirmation gate over the existing single-use
approval store. Deterministic, explainable, augment-only.
"""

from __future__ import annotations

from .bootstrap import (
    FinanceGuardrailService,
    get_service,
    install_finance_guardrail_layer,
    set_service,
)
from .intent import intent_from_payload, intent_from_tool
from .models import GuardrailVerdict, MoneyIntent

__all__ = [
    "FinanceGuardrailService",
    "GuardrailVerdict",
    "MoneyIntent",
    "get_service",
    "install_finance_guardrail_layer",
    "intent_from_payload",
    "intent_from_tool",
    "set_service",
]
