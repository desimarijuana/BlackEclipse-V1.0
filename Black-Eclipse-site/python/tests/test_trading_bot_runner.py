"""The strategy-bot runner: one decision per run, no second order path.

These tests inject a fake live service, so they exercise the runner's own
contract (consent, session, freshness, multi-symbol, refusal mapping) without a
broker, MT5 or a market gateway.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from harness.automation.trading_runner import run_strategy
from harness.trade.model import TradeRefused

NOW = datetime.now(timezone.utc)


def _iso(moment: datetime) -> str:
    return moment.isoformat().replace("+00:00", "Z")


def _consent(**patch):
    base = {
        "version": 1,
        "kind": "standing",
        "modes": ["demo", "live"],
        "grantedAt": _iso(NOW - timedelta(days=1)),
        "expiresAt": _iso(NOW + timedelta(days=29)),
        "revokedAt": None,
        "autoRenew": True,
        "limits": {
            "symbols": ["EURUSD", "GBPUSD"],
            "maxOrdersPerDay": 4,
            "maxMarginPerOrder": 500,
            "maxOpenPositions": 1,
        },
        "phrase": "MANDATE DEMO MT5 demo",
    }
    base.update(patch)
    return base


def _definition(*, mode="demo", tier="l1", symbols=None, consent="default",
                session=None, dynamic=False, dry_run=False, version=3,
                timeframe="H1"):
    if consent == "default":
        consent = _consent() if mode != "shadow" else None
    return SimpleNamespace(
        id="aut_1",
        version=version,
        action=SimpleNamespace(
            type="run_strategy",
            config={
                "strategyId": "ema_trend",
                "strategyVersion": "1.0.0",
                "mode": mode,
                "connectionId": "" if mode == "shadow" else "brk_1",
                "symbols": symbols or ["EURUSD"],
                "dynamicSymbols": dynamic,
                "timeframe": timeframe,
                "volume": 0.1,
                "stopLossPoints": 150,
                "takeProfitPoints": 300,
                "maxOrdersPerDay": 2,
                "session": session,
                "trialId": "live_1",
                "dryRun": dry_run,
                "consent": consent,
            },
        ),
        execution_authority=SimpleNamespace(
            tier=tier,
            appetite="conservative",
            sizing_mode="risk_based",
            require_stop=True,
            max_open_positions=1,
            max_margin_per_order=500,
            cooldown_s=900,
            max_daily_loss_pct=3,
        ),
    )


class FakeStore:
    def __init__(self, exists=True):
        self.exists = exists

    def get_strategy(self, strategy_id, version):
        return {"id": strategy_id, "version": version} if self.exists else None


class FakeLive:
    def __init__(self, *, signals=None, result=None, trial=None, raises=None,
                 signal="none"):
        self.signals = signals or {}
        self.result = result
        self.signal_kind = signal
        self.trial = trial or {
            "id": "live_1", "botId": "aut_1", "botVersion": 3, "status": "running",
        }
        self.raises = raises
        self.signal_calls: list[str] = []
        self.run_calls: list[dict] = []

    def get(self, trial_id):
        return self.trial

    def _reading(self, symbol):
        return self.signals.get(symbol, {
            "symbol": symbol,
            "signal": self.signal_kind,
            "reason": "cross" if self.signal_kind != "none" else "no signal on the last closed bar",
            "bar": _iso(NOW),
            "indicators": {},
        })

    async def signal(self, trial_id, *, gateway=None, symbol=None, dataset=None):
        self.signal_calls.append(symbol)
        return self._reading(symbol)

    async def run_once(self, trial_id, *, gateway=None, symbol=None,
                       automation_id="", bot_version=None, dry_run=False):
        self.run_calls.append({
            "trialId": trial_id, "symbol": symbol,
            "automationId": automation_id, "botVersion": bot_version,
            "dryRun": dry_run,
        })
        if self.raises:
            raise self.raises
        if self.result is not None:
            return self.result
        reading = self._reading(symbol)
        return {
            "signal": reading,
            "order": {"status": "filled", "volume": 0.1, "orderId": "ord_1"},
            "closed": [],
            "risk": {"allowed": True, "reasons": []},
        }


def service(*, store=None, live=None, gateway=None):
    return SimpleNamespace(
        quant_store=store if store is not None else FakeStore(),
        live_strategy=live if live is not None else FakeLive(),
        brokers=None,
        server_market_gateway=lambda: gateway,
    )


async def run(definition, *, store=None, live=None, gateway=None):
    return await run_strategy(
        service(store=store, live=live, gateway=gateway),
        definition,
        run_id="run_1",
        execution_id="exec_1",
    )


@pytest.mark.asyncio
async def test_missing_strategy_is_an_honest_refusal():
    result = await run(_definition(), store=FakeStore(exists=False))
    assert result.state == "blocked"
    assert result.detail["decision"]["code"] == "STRATEGY_UNAVAILABLE"
    assert result.detail["decision"]["outcome"] == "failed"


@pytest.mark.asyncio
async def test_a_demo_bot_without_consent_does_not_trade():
    result = await run(_definition(consent=None))
    assert result.state == "blocked"
    assert result.detail["decision"]["code"] == "CONSENT_REQUIRED"


@pytest.mark.asyncio
async def test_a_closed_session_is_skipped_not_failed():
    today = (NOW.weekday() + 1) % 7  # python Mon=0 → repo Sun=0
    session = {
        "timezone": "UTC",
        "weekdays": [(today + 1) % 7],
        "start": "00:00",
        "end": "23:59",
    }
    result = await run(_definition(session=session))
    assert result.state == "skipped"
    assert result.detail["decision"]["code"] == "SESSION_CLOSED"


@pytest.mark.asyncio
async def test_a_stale_bar_is_skipped():
    stale = (NOW - timedelta(hours=10)).isoformat().replace("+00:00", "Z")
    live = FakeLive(signals={
        "EURUSD": {"symbol": "EURUSD", "signal": "long_entry",
                   "reason": "cross", "bar": stale, "indicators": {}},
    })
    result = await run(_definition(), live=live)
    assert result.state == "skipped"
    assert result.detail["decision"]["code"] == "STALE_MARKET_DATA"
    assert live.run_calls == []


@pytest.mark.asyncio
async def test_no_signal_is_a_completed_decision():
    result = await run(_definition())
    assert result.state == "completed"
    decision = result.detail["decision"]
    assert decision["outcome"] == "none"
    assert decision["code"] is None
    assert "no actionable signal" in decision["reason"]


@pytest.mark.asyncio
@pytest.mark.asyncio
async def test_a_failed_signal_explains_itself_in_the_decision():
    """A blocked signal must not collapse into a bare 'no actionable signal'."""
    live = FakeLive()

    async def boom(*_args, **_kwargs):
        raise RuntimeError("no 1d data for EURUSD")

    live.signal = boom
    result = await run(_definition(), live=live)
    reason = result.detail["decision"]["reason"]
    assert "no actionable signal" in reason
    assert "EURUSD: signal failed: no 1d data for EURUSD" in reason


async def test_shadow_records_a_preview_and_never_calls_the_broker_path():
    live = FakeLive(signals={
        "EURUSD": {"symbol": "EURUSD", "signal": "long_entry",
                   "reason": "cross", "bar": _iso(NOW), "indicators": {"ema_fast": 1.1}},
    })
    result = await run(_definition(mode="shadow", tier="l0"), live=live)
    assert result.state == "completed"
    decision = result.detail["decision"]
    assert decision["outcome"] == "preview"
    assert decision["code"] == "SHADOW"
    assert decision["action"] == "buy"
    assert "nothing was sent" in decision["reason"]
    assert live.run_calls == []


@pytest.mark.asyncio
async def test_demo_executes_through_the_existing_path_with_bot_attribution():
    live = FakeLive(signal="long_entry")
    result = await run(_definition(), live=live)
    assert result.state == "completed"
    assert result.detail["decision"]["outcome"] == "filled"
    assert result.detail["decision"]["orderId"] == "ord_1"
    assert live.run_calls == [{
        "trialId": "live_1",
        "symbol": "EURUSD",
        "automationId": "aut_1",
        "botVersion": 3,
        "dryRun": False,
    }]


@pytest.mark.asyncio
async def test_l0_cannot_fill_a_demo_account():
    result = await run(_definition(tier="l0"))
    assert result.state == "blocked"
    assert result.detail["decision"]["code"] == "BOT_TIER_REQUIRED"


@pytest.mark.asyncio
async def test_live_needs_l2_even_with_consent():
    result = await run(_definition(mode="live", tier="l1"))
    assert result.state == "blocked"
    assert result.detail["decision"]["code"] == "BOT_TIER_REQUIRED"


@pytest.mark.asyncio
async def test_a_stale_bot_version_pin_refuses():
    live = FakeLive(trial={"id": "live_1", "botId": "aut_1", "botVersion": 2, "status": "running"})
    result = await run(_definition(version=3), live=live)
    assert result.state == "blocked"
    assert result.detail["decision"]["code"] == "BOT_VERSION_STALE"


@pytest.mark.asyncio
async def test_a_risk_refusal_is_blocked_with_its_code():
    live = FakeLive(signal="long_entry", result={
        "signal": {"symbol": "EURUSD", "signal": "long_entry",
                   "reason": "cross", "bar": _iso(NOW), "indicators": {}},
        "order": None,
        "closed": [],
        "risk": {"allowed": False, "reasons": ["risk per trade above the cap"]},
    })
    result = await run(_definition(), live=live)
    assert result.state == "blocked"
    assert result.detail["decision"]["code"] == "RISK_REFUSED"
    assert "risk per trade" in " ".join(result.detail["decision"]["risk"]["reasons"])


@pytest.mark.asyncio
async def test_a_typed_trade_refusal_keeps_its_code():
    live = FakeLive(signal="long_entry",
                    raises=TradeRefused("ORDER_REFUSED", "the broker said no"))
    result = await run(_definition(), live=live)
    assert result.state == "blocked"
    assert result.detail["decision"]["code"] == "ORDER_REFUSED"
    assert "the broker said no" in result.detail["decision"]["reason"]


@pytest.mark.asyncio
async def test_pinned_symbols_scan_only_the_first_symbol():
    live = FakeLive(signals={
        "GBPUSD": {"symbol": "GBPUSD", "signal": "short_entry",
                   "reason": "break", "bar": _iso(NOW), "indicators": {}},
    })
    result = await run(_definition(symbols=["EURUSD", "GBPUSD"], dynamic=False), live=live)
    assert live.signal_calls == ["EURUSD"]
    assert result.detail["decision"]["outcome"] == "none"


@pytest.mark.asyncio
async def test_dynamic_scan_takes_the_actionable_symbol():
    live = FakeLive(signals={
        "GBPUSD": {"symbol": "GBPUSD", "signal": "short_entry",
                   "reason": "break", "bar": _iso(NOW), "indicators": {}},
    })
    result = await run(_definition(symbols=["EURUSD", "GBPUSD"], dynamic=True), live=live)
    assert live.signal_calls == ["EURUSD", "GBPUSD"]
    assert result.detail["decision"]["symbol"] == "GBPUSD"
    assert result.detail["decision"]["action"] == "sell"


@pytest.mark.asyncio
async def test_a_decision_is_persisted_even_when_nothing_happens():
    result = await run(_definition())
    assert result.detail["decision"]["botId"] == "aut_1"
    assert result.detail["decision"]["strategyId"] == "ema_trend"
    assert result.detail["decision"]["mode"] == "demo"
    assert result.detail["decision"]["tier"] == "l1"


# ── EUR/USD on 1-minute bars ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_an_m1_bar_is_fresh_within_its_window():
    # 2.5 × 60s = 150s; a bar 90s old is still the freshest closed M1 bar.
    # Use the REAL clock: the runner compares against `datetime.now()`, and a
    # module-level NOW ages while the suite runs.
    bar = _iso(datetime.now(timezone.utc) - timedelta(seconds=90))
    live = FakeLive(signals={
        "EURUSD": {"symbol": "EURUSD", "signal": "long_entry",
                   "reason": "EMA(9) crossed above EMA(21)", "bar": bar, "indicators": {}},
    })
    result = await run(
        _definition(symbols=["EURUSD"], timeframe="M1"), live=live,
    )
    assert result.state == "completed"
    assert result.detail["decision"]["symbol"] == "EURUSD"
    assert result.detail["decision"]["action"] == "buy"
    assert len(live.run_calls) == 1


@pytest.mark.asyncio
async def test_a_stale_m1_bar_is_skipped():
    bar = _iso(NOW - timedelta(minutes=5))
    live = FakeLive(signals={
        "EURUSD": {"symbol": "EURUSD", "signal": "long_entry",
                   "reason": "cross", "bar": bar, "indicators": {}},
    })
    result = await run(
        _definition(symbols=["EURUSD"], timeframe="M1"), live=live,
    )
    assert result.state == "skipped"
    assert result.detail["decision"]["code"] == "STALE_MARKET_DATA"
    assert live.run_calls == []
