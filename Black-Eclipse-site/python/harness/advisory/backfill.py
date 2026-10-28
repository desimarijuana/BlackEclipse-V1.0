"""Legacy advisory debt: explain it, and backfill only with real provenance.

Two separate operations:

* `legacy_report` is read-only. It explains why a row cannot be scored instead of
  implying it was audited.
* `backfill_entry_prices` is operator-triggered and dry-run first. It fetches a
  real historical bar at the decision's creation time and stores it as an
  `entry_price` basis with source/as-of provenance. No bar → no price. It never
  overwrites an existing entry price and never invents a horizon.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
from typing import Any, Optional

from .scoring import entry_price


def legacy_report(store: Any, *, limit: int = 5000) -> dict[str, Any]:
    decisions = [
        store.get_decision(row["id"]) or row
        for row in store.list_decisions(limit=limit)
    ]
    rows: list[dict[str, Any]] = []
    reasons: dict[str, int] = {}
    for decision in decisions:
        if not decision.get("legacyUnscored") and entry_price(decision) is not None:
            continue
        if not decision.get("legacyUnscored"):
            continue
        why: list[str] = []
        if entry_price(decision) is None:
            why.append("no_entry_price")
        horizon = str(decision.get("horizon") or "").strip().lower()
        if not horizon or horizon == "unscored":
            why.append("no_horizon")
        if not decision.get("symbols"):
            why.append("no_symbol")
        if not decision.get("method"):
            why.append("no_method")
        status = "unscorable"
        if (
            entry_price(decision) is None and horizon
            and horizon != "unscored" and decision.get("symbols")
        ):
            status = "scorable_if_backfilled"
        for reason in why:
            reasons[reason] = reasons.get(reason, 0) + 1
        rows.append({
            "id": decision.get("id"),
            "createdAt": decision.get("createdAt"),
            "action": decision.get("action"),
            "symbols": list(decision.get("symbols") or []),
            "horizon": decision.get("horizon"),
            "method": decision.get("method"),
            "status": status,
            "reasons": why,
        })
    return {
        "total": len(rows),
        "byReason": reasons,
        "rows": rows,
    }


def _bar_price(series: Any) -> tuple[Optional[float], Optional[str], Optional[str]]:
    bars = list(getattr(series, "bars", None) or [])
    for bar in bars:
        try:
            close = float(getattr(bar, "close", None))
        except (TypeError, ValueError):
            continue
        if close > 0:
            meta = getattr(series, "meta", None)
            source = str(getattr(meta, "provider", "") or "historical")
            as_of = str(getattr(bar, "timestamp", "") or "")
            return close, source, as_of
    return None, None, None


def _window(created_at: str) -> tuple[str, str]:
    try:
        start = _dt.datetime.fromisoformat(str(created_at).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return "", ""
    end = start + _dt.timedelta(days=2)
    return start.date().isoformat(), end.date().isoformat()


async def backfill_entry_prices(
    advisory_service: Any,
    gateway: Any,
    *,
    dry_run: bool = True,
    limit: int = 50,
) -> dict[str, Any]:
    """Backfill a real historical entry price where one can be proven."""
    if gateway is None:
        return {"ok": False, "reason": "no_market_gateway", "backfilled": 0}
    store = advisory_service.store
    candidates = 0
    actions: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for raw in store.list_decisions(limit=5000):
        decision = store.get_decision(raw["id"]) or raw
        if candidates >= max(1, int(limit)):
            break
        if decision.get("outcome") or entry_price(decision) is not None:
            continue
        horizon = str(decision.get("horizon") or "").strip().lower()
        symbols = list(decision.get("symbols") or [])
        if not horizon or horizon == "unscored":
            skipped.append({"id": decision.get("id"), "reason": "no_horizon"})
            continue
        if not symbols:
            skipped.append({"id": decision.get("id"), "reason": "no_symbol"})
            continue
        candidates += 1
        start, end = _window(decision.get("createdAt") or "")
        if not start:
            skipped.append({"id": decision.get("id"), "reason": "bad_created_at"})
            continue
        backfilled = False
        for symbol in symbols[:4]:
            try:
                if hasattr(gateway, "get_historical_prices"):
                    series = await gateway.get_historical_prices(
                        symbol, start=start, end=end, interval="1d",
                    )
                else:
                    series = await gateway.get_ohlcv(
                        symbol, start=start, end=end, interval="1d",
                    )
            except Exception:  # noqa: BLE001 - a missing bar is a skip
                continue
            price, source, as_of = _bar_price(series)
            if price is None:
                continue
            digest = hashlib.sha256(
                f"{source}|{as_of}|{price}".encode("utf-8")
            ).hexdigest()[:32]
            action = {
                "decisionId": decision.get("id"), "symbol": symbol,
                "price": price, "source": source, "asOf": as_of,
            }
            actions.append(action)
            if not dry_run:
                store.add_basis(decision.get("id"), [
                    {"kind": "entry_price", "ref": str(price), "valueHash": digest},
                    {"kind": "entry_price_source", "ref": source, "valueHash": digest},
                    {"kind": "entry_price_asof", "ref": as_of, "valueHash": digest},
                ])
            backfilled = True
            break
        if not backfilled:
            skipped.append({"id": decision.get("id"), "reason": "no_historical_bar"})
    return {
        "ok": True,
        "dryRun": bool(dry_run),
        "candidates": candidates,
        "backfilled": 0 if dry_run else len(actions),
        "actions": actions,
        "skipped": skipped,
    }


__all__ = ["backfill_entry_prices", "legacy_report"]
