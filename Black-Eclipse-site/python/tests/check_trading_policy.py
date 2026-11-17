"""Executable check for the trading policy module (stdlib only).

Run with a plain interpreter:

    python python/tests/check_trading_policy.py

It exists because the agent runtime is optional on a development machine: the
pure policy rules must still be verifiable without pydantic/FastAPI installed.
`test_trading_policy.py` holds the same assertions for the pytest suite.
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

PYTHON_DIR = Path(__file__).resolve().parents[1]
if str(PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(PYTHON_DIR))

from harness.automation import trading_policy as p  # noqa: E402

NOW = datetime(2026, 11, 17, 10, 0, tzinfo=timezone.utc)
CHECKS = 0


def check(condition: object, message: str) -> None:
    global CHECKS
    CHECKS += 1
    if not condition:
        raise AssertionError(message)


def test_symbols() -> None:
    check(p.normalize_symbols(["eurusd", " EURUSD ", "GBPUSD", "EURUSD"]) ==
          ["EURUSD", "GBPUSD"], "symbols normalise + dedupe")
    check(p.normalize_symbols([""]) == [], "empty symbol is dropped")
    check(p.is_symbol_tradable("EURUSD", ["EURUSD.m"]), "broker suffix matches")
    check(p.is_symbol_tradable("BTCUSD", ["BTCUSD-ECN"]), "dash suffix matches")
    check(not p.is_symbol_tradable("EURUSD", ["EURUSDT"]), "longer symbol must not match")
    check(p.missing_symbols(["EURUSD", "USDJPY"], ["EURUSD"]) == ["USDJPY"],
          "missing symbols are reported")


def test_sessions() -> None:
    session = {
        "timezone": "UTC", "weekdays": [1, 2, 3, 4, 5],  # Mon..Fri
        "start": "08:00", "end": "20:00",
    }
    check(p.session_state(NOW, session)["open"], "inside the window")
    check(not p.session_state(NOW.replace(hour=22), session)["open"],
          "after the window is closed")
    check(not p.session_state(NOW.replace(hour=3), session)["open"],
          "before the window is closed")
    weekend = NOW + timedelta(days=5)  # Saturday
    check(not p.session_state(weekend, session)["open"], "weekend is closed")
    overnight = {"timezone": "UTC", "weekdays": [], "start": "22:00", "end": "02:00"}
    check(p.session_state(NOW.replace(hour=23), overnight)["open"], "overnight window")
    check(p.session_state(NOW.replace(hour=1), overnight)["open"], "overnight window (after midnight)")
    check(not p.session_state(NOW.replace(hour=12), overnight)["open"], "overnight window (midday)")
    unknown = {"timezone": "Mars/Olympus", "weekdays": [], "start": "00:00", "end": "23:59"}
    state = p.session_state(NOW, unknown)
    check(not state["open"] and "timezone" in (state["reason"] or ""),
          "unknown timezone refuses with a reason")
    check(p.session_state(NOW, None)["open"], "no session means always open")


def test_freshness() -> None:
    bar = (NOW - timedelta(minutes=5)).isoformat().replace("+00:00", "Z")
    check(p.is_fresh(bar, NOW, 3600), "5 minutes old on H1 is fresh")
    stale = (NOW - timedelta(hours=5)).isoformat().replace("+00:00", "Z")
    check(not p.is_fresh(stale, NOW, 3600), "5 hours old on H1 is stale")
    check(not p.is_fresh(None, NOW, 3600), "a missing bar is never fresh")
    check(p.timeframe_seconds("h1") == 3600, "timeframe lookup is case-insensitive")


def consent(**patch: object) -> dict:
    base = {
        "version": 1,
        "kind": "standing",
        "modes": ["demo"],
        "grantedAt": NOW.isoformat(),
        "expiresAt": (NOW + timedelta(days=30)).isoformat(),
        "revokedAt": None,
        "limits": {
            "symbols": ["EURUSD", "GBPUSD"],
            "maxOrdersPerDay": 4,
            "maxMarginPerOrder": 500,
            "maxOpenPositions": 2,
        },
        "phrase": "MANDATE DEMO MT5 demo",
    }
    base.update(patch)
    return base


def request(**patch: object) -> dict:
    base = {
        "mode": "demo",
        "symbols": ["EURUSD"],
        "maxOrdersPerDay": 2,
        "maxMarginPerOrder": 200,
        "maxOpenPositions": 1,
    }
    base.update(patch)
    return base


def test_consent() -> None:
    check(p.consent_status(None, NOW) == "missing", "no consent is missing")
    check(p.consent_status(consent(), NOW) == "active", "granted consent is active")
    check(p.consent_covers(consent(), request(), NOW)["covered"], "inside every limit")
    check(not p.consent_covers(consent(), request(mode="live"), NOW)["covered"],
          "live is not covered by a demo grant")
    check(p.consent_covers(consent(), request(mode="live"), NOW)["field"] == "consent",
          "the mode refusal names the field")
    check(not p.consent_covers(consent(), request(symbols=["USDJPY"]), NOW)["covered"],
          "a symbol outside the grant is refused")
    check(not p.consent_covers(consent(), request(maxOrdersPerDay=9), NOW)["covered"],
          "more orders than agreed is refused")
    check(not p.consent_covers(consent(), request(maxOpenPositions=3), NOW)["covered"],
          "more positions than agreed is refused")
    check(p.consent_covers(consent(limits={**consent()["limits"], "symbols": ["*"]}),
                           request(symbols=["XAUUSD"]), NOW)["covered"],
          "a wildcard grant covers any symbol")
    expired = consent(expiresAt=(NOW - timedelta(seconds=1)).isoformat())
    check(p.consent_status(expired, NOW) == "expired", "expiry is exact")
    check(not p.consent_covers(expired, request(), NOW)["covered"], "expired is refused")
    revoked = consent(revokedAt=NOW.isoformat())
    check(p.consent_status(revoked, NOW) == "revoked", "revocation is immediate")
    check(p.needs_phrase(None, request(mode="shadow"), NOW) is False,
          "shadow never needs a phrase")
    check(p.needs_phrase(None, request(), NOW) is True, "demo without consent needs one")
    check(p.needs_phrase(consent(), request(), NOW) is False, "a valid grant needs none")


def test_decisions() -> None:
    line = p.format_decision_line({
        "symbol": "EURUSD", "action": "buy", "outcome": "filled",
        "risk": {"quantity": 0.1}, "code": None,
    })
    check(line == "EURUSD · BUY 0.1 · filled", f"decision line: {line!r}")
    record = p.decision(
        bot_id="aut_1", bot_version=3, strategy_id="ema", strategy_version="1.0.0",
        mode="demo", tier="l1", symbol="EURUSD", action="buy",
        outcome="filled", order_id="ord_1", risk={"allowed": True, "quantity": 0.1},
    )
    check(record["botId"] == "aut_1" and record["tier"] == "l1", "decision carries identity")
    check(record["warnings"] == [], "warnings default to a list")


def main() -> int:
    for name, test in (
        ("symbols", test_symbols),
        ("sessions", test_sessions),
        ("freshness", test_freshness),
        ("consent", test_consent),
        ("decisions", test_decisions),
    ):
        test()
        print(f"  ok  {name}")
    print(f"\ntrading policy: {CHECKS} checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
