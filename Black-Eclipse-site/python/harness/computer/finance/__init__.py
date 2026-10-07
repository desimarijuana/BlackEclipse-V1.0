"""Finance-native Computer Use — the Eclipse-specific extension.

    fields.py     the financial field vocabulary (ticker, bid, ask, position, …)
    extractor.py  convert a screen (OCR/AX text) into structured financial state
                  with explicit screen-derived provenance (NEVER authoritative)
    firewall.py   FinanceActionFirewall: risk modes + approval boundary for every
                  financial mutation (buy/sell/order/transfer/withdraw)

Screen-derived financial data is labelled `source_type = desktop_screen` and is
never conflated with provider/official/API data. The firewall never lets the
generic engine perform an unrestricted financial mutation.
"""

from __future__ import annotations

from .extractor import FinancialExtractor
from .fields import FINANCIAL_FIELDS, extract_fields
from .firewall import FinanceActionFirewall, FinanceDecision

__all__ = [
    "FINANCIAL_FIELDS",
    "FinanceActionFirewall",
    "FinanceDecision",
    "FinancialExtractor",
    "extract_fields",
]
