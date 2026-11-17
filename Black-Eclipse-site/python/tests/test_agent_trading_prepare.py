"""An AGENT bot can be authorized to trade live, under the same fence.

Two halves:
  * `POST /automations/{id}/trading/prepare` turns an agent's one-time phrase into
    a bot-pinned mandate plus the standing consent (no strategy trial);
  * `trade/authority.check_live_order` is the fence that decides whether THAT bot
    may reach a live account right now.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from harness.routers import bot_trading
from harness.routers.bot_trading import PrepareBody, prepare_trading
from harness.trade.authority import check_live_order


def _definition(**patch):
    base = SimpleNamespace(
        id="aut_agent",
        version=4,
        action=SimpleNamespace(
            type="run_agent",
            config={},
            objective="trade the trend",
            agent_id="agt_trader",
        ),
        execution_authority=SimpleNamespace(
            tier="l2",
            appetite="conservative",
            sizing_mode="risk_based",
            require_stop=True,
            max_open_positions=1,
            max_margin_per_order=500,
            cooldown_s=900,
            max_daily_loss_pct=3,
            auto_mode=True,
            auto_renew=True,
            learning_enabled=True,
            improve_after_failures=3,
        ),
        public=lambda: {"id": base.id, "version": base.version},
    )
    for key, value in patch.items():
        setattr(base, key, value)
    return base


class FakeBrokers:
    def __init__(self, connection=None):
        self.connection = connection or {
            "id": "brk_live", "mode": "live", "label": "MT5 live",
        }
        self.mandates: list[dict] = []

    def get_connection(self, connection_id):
        return self.connection

    def create_mandate(self, connection_id, payload):
        self.mandates.append({"connectionId": connection_id, **payload})
        return {"id": "mnd_1", "connectionId": connection_id, **payload}


class FakeSvc:
    def __init__(self, definition):
        self.definition = definition
        self.attached: list[dict] = []

    def get(self, automation_id):
        return self.definition if automation_id == self.definition.id else None

    def attach_trading(self, automation_id, *, trial_id, consent, config_patch=None):
        self.attached.append({
            "automationId": automation_id,
            "trialId": trial_id,
            "consent": consent,
            "configPatch": config_patch,
        })
        return self.definition


@pytest.fixture()
def wiring(monkeypatch):
    definition = _definition()
    brokers = FakeBrokers()
    svc = FakeSvc(definition)
    monkeypatch.setattr(
        bot_trading, "service", SimpleNamespace(brokers=brokers),
        raising=False,
    )
    monkeypatch.setattr(bot_trading, "_svc", lambda: svc, raising=False)
    return definition, brokers, svc


def _body(**patch):
    base = dict(
        strategyId="",
        strategyVersion="",
        mode="live",
        connectionId="brk_live",
        symbols=["EURUSD"],
        maxOrders=2,
        maxMargin=200.0,
        ttlSeconds=3600,
        confirmation="MANDATE LIVE MT5 live",
    )
    base.update(patch)
    return PrepareBody(**base)


def test_an_agent_gets_a_bot_pinned_live_mandate(wiring):
    definition, brokers, svc = wiring
    result = prepare_trading(definition.id, _body(), _=True)

    assert result["success"] is True
    mandate = brokers.mandates[0]
    assert mandate["botId"] == definition.id
    assert mandate["botVersion"] == definition.version
    assert mandate["mode"] == "live"
    assert mandate["symbols"] == ["EURUSD"]
    assert mandate["maxMargin"] == 200.0
    assert mandate["confirmation"] == "MANDATE LIVE MT5 live"
    # The mandate is the whole authority: an agent has no strategy trial.
    assert "trial" not in result


def test_prepare_stores_the_standing_consent_on_the_bot(wiring):
    definition, _brokers, svc = wiring
    prepare_trading(definition.id, _body(), _=True)

    attached = svc.attached[0]
    assert attached["trialId"] == ""
    consent = attached["consent"]
    assert consent["kind"] == "standing"
    assert consent["modes"] == ["live"]
    assert consent["limits"]["symbols"] == ["EURUSD"]
    assert consent["limits"]["maxOrdersPerDay"] == 2
    assert consent["limits"]["maxMarginPerOrder"] == 200.0
    assert consent["revokedAt"] is None


def test_auto_mode_renews_without_retyping_the_phrase(wiring):
    definition, brokers, _svc = wiring
    result = bot_trading._prepare_agent(
        definition,
        _body(confirmation=""),
        stored={
            "kind": "standing",
            "modes": ["live"],
            "expiresAt": "2099-01-01T00:00:00Z",
            "revokedAt": None,
            "limits": {
                "symbols": ["*"],
                "maxOrdersPerDay": 9,
                "maxMarginPerOrder": 900,
                "maxOpenPositions": 9,
            },
        },
        auto=True,
    )
    assert result["success"] is True
    assert brokers.mandates[0]["botId"] == definition.id


def test_the_phrase_is_required_when_no_grant_covers_the_request(wiring):
    definition, brokers, _svc = wiring
    with pytest.raises(Exception) as excinfo:
        bot_trading._prepare_agent(
            definition, _body(confirmation="wrong phrase"), stored=None, auto=False,
        )
    assert "MANDATE LIVE MT5 live" in str(excinfo.value)
    assert brokers.mandates == []


def test_a_live_mandate_requires_l2_at_creation(monkeypatch):
    from harness.trade.authority import check_mandate_creation
    from harness.trade.model import TradeRefused

    monkeypatch.setattr(
        "harness.trade.authority.bot_definition",
        lambda _id: SimpleNamespace(
            version=4,
            execution_authority=SimpleNamespace(
                tier="l1", max_margin_per_order=500,
            ),
        ),
    )
    service = FenceService()
    # Demo authority is L1's job, and the version pin still applies.
    check_mandate_creation(
        service, bot_id="aut_agent", bot_version=4, max_margin=100, mode="demo",
    )
    with pytest.raises(TradeRefused) as excinfo:
        check_mandate_creation(
            service, bot_id="aut_agent", bot_version=4, max_margin=100, mode="live",
        )
    assert excinfo.value.code == "BOT_TIER_INSUFFICIENT"


# ── The live fence ───────────────────────────────────────────────────────────

def _fence_definition(tier="l2"):
    return SimpleNamespace(
        id="aut_agent",
        version=4,
        execution_authority=SimpleNamespace(
            tier=tier,
            appetite="conservative",
            require_stop=True,
            max_open_positions=2,
            cooldown_s=0,
            max_margin_per_order=500,
        ),
    )


class FenceService:
    def __init__(self):
        self.connection = SimpleNamespace(id="brk_live")

    def _connection(self, connection_id):
        return self.connection

    def _magic(self, connection):
        return 7

    def positions(self, connection_id):
        return {"available": True, "data": {"positions": []}}

    def ledger_orders(self, _unused, limit=1, automation_id=""):
        return []


def _intent(**patch):
    base = {"symbol": "EURUSD", "side": "buy", "volume": 0.1, "stopLoss": 1.08}
    base.update(patch)
    return base


def test_l2_passes_the_live_fence(monkeypatch):
    monkeypatch.setattr(
        "harness.trade.authority.bot_definition", lambda _id: _fence_definition("l2"),
    )
    refusal = check_live_order(
        FenceService(), automation_id="aut_agent", connection_id="brk_live",
        mode="live", intent=_intent(),
    )
    assert refusal is None


def test_l1_is_refused_at_the_live_fence(monkeypatch):
    monkeypatch.setattr(
        "harness.trade.authority.bot_definition", lambda _id: _fence_definition("l1"),
    )
    message, detail = check_live_order(
        FenceService(), automation_id="aut_agent", connection_id="brk_live",
        mode="live", intent=_intent(),
    )
    assert detail["reason"] == "BOT_TIER_INSUFFICIENT"
    assert "L1" in message


def test_a_live_order_without_a_stop_is_refused(monkeypatch):
    monkeypatch.setattr(
        "harness.trade.authority.bot_definition", lambda _id: _fence_definition("l2"),
    )
    _message, detail = check_live_order(
        FenceService(), automation_id="aut_agent", connection_id="brk_live",
        mode="live", intent=_intent(stopLoss=None),
    )
    assert detail["reason"] == "STOP_REQUIRED"


def test_a_demo_order_is_not_this_fence_s_business():
    assert check_live_order(
        FenceService(), automation_id="aut_agent", connection_id="brk_demo",
        mode="demo", intent=_intent(),
    ) is None


# ── Find trades (the candidate scan) ────────────────────────────────────────

class ScanLive:
    async def signal(self, trial_id, *, gateway=None, symbol=None, dataset=None):
        signal = "long_entry" if symbol == "GBPUSD" else "none"
        return {
            "symbol": symbol,
            "signal": signal,
            "reason": "breakout" if signal != "none" else "no signal",
            "bar": "2026-11-17T09:00:00Z",
            "indicators": {},
        }


@pytest.mark.asyncio
async def test_scan_returns_the_actionable_symbols(wiring, monkeypatch):
    definition, _brokers, _svc = wiring
    definition.action.config = {"trialId": "live_1", "symbols": ["EURUSD", "GBPUSD"]}
    monkeypatch.setattr(bot_trading, "_live", lambda: ScanLive(), raising=False)
    monkeypatch.setattr(
        bot_trading, "service",
        SimpleNamespace(brokers=FakeBrokers(), server_market_gateway=lambda: None),
        raising=False,
    )

    result = await bot_trading.scan_trading(
        definition.id, bot_trading.ScanBody(symbols=["EURUSD", "GBPUSD"]), _=True,
    )
    assert result["scanned"] == 2
    assert result["actionable"] == ["GBPUSD"]
    assert [row["symbol"] for row in result["results"]] == ["EURUSD", "GBPUSD"]


@pytest.mark.asyncio
async def test_scan_needs_a_prepared_trial(wiring, monkeypatch):
    definition, _brokers, _svc = wiring
    definition.action.config = {"symbols": ["EURUSD"]}
    monkeypatch.setattr(
        bot_trading, "service", SimpleNamespace(brokers=FakeBrokers()), raising=False,
    )
    with pytest.raises(Exception) as excinfo:
        await bot_trading.scan_trading(
            definition.id, bot_trading.ScanBody(symbols=["EURUSD"]), _=True,
        )
    assert "prepare trading" in str(excinfo.value)
