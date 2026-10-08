"""Reconciliation — compare an external statement to the ledger (§34).

A broker / exchange / wallet / manual-import statement is supplied as a set of
`{symbol, quantity}` (and optionally `value`) rows. Each row is classified:

  * MATCHED   — present in both, within tolerance
  * MISMATCH  — present in both, beyond tolerance
  * MISSING   — present in one side only
  * UNKNOWN   — present but not comparable (e.g. no quantity on both)

Deterministic; the tolerance is explicit so a match is never implied.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Optional, Sequence

from .money import D, ZERO


def _dec(value: Any) -> Optional[Decimal]:
    if value is None or value == "":
        return None
    try:
        return D(value)
    except ValueError:
        return None


def reconcile(
    internal: Sequence[dict[str, Any]],
    external: Sequence[dict[str, Any]],
    *,
    tolerance: Optional[str] = None,
    relative_tolerance: float = 0.0,
) -> dict[str, Any]:
    tol = _dec(tolerance) or ZERO
    internal_map = {str(r.get("symbol", "")).upper(): r for r in internal if r.get("symbol")}
    external_map = {str(r.get("symbol", "")).upper(): r for r in external if r.get("symbol")}

    items: list[dict[str, Any]] = []
    counts = {"MATCHED": 0, "MISMATCH": 0, "MISSING": 0, "UNKNOWN": 0}

    for symbol in sorted(set(internal_map) | set(external_map)):
        i = internal_map.get(symbol)
        e = external_map.get(symbol)
        iq = _dec(i.get("quantity")) if i else None
        eq = _dec(e.get("quantity")) if e else None
        if i is not None and e is not None:
            if iq is None or eq is None:
                status = "UNKNOWN"
            else:
                diff = iq - eq
                allowed = tol + (abs(iq) * Decimal(str(relative_tolerance)))
                status = "MATCHED" if abs(diff) <= allowed else "MISMATCH"
        else:
            status = "MISSING"
            diff = None
        counts[status] += 1
        items.append({
            "symbol": symbol,
            "status": status,
            "internalQuantity": str(iq) if iq is not None else None,
            "externalQuantity": str(eq) if eq is not None else None,
            "difference": str(diff) if i is not None and e is not None and iq is not None and eq is not None else None,
        })

    overall = "MATCHED" if counts["MISMATCH"] == 0 and counts["MISSING"] == 0 and counts["UNKNOWN"] == 0 \
        else ("UNKNOWN" if counts["MISMATCH"] == 0 and counts["MISSING"] == 0 and counts["UNKNOWN"] > 0
              else "MISMATCH")
    return {
        "status": overall,
        "tolerance": str(tol),
        "counts": counts,
        "items": items,
        "clean": counts["MISMATCH"] == 0 and counts["MISSING"] == 0,
    }


__all__ = ["reconcile"]
