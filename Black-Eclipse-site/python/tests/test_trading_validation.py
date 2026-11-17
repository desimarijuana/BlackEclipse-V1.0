"""Validation rules for a strategy trading bot.

Mirrors `src/lib/bots/trading/validate.ts`: a draft may be saved mid-setup, an
ACTIVE bot must be complete, and misfire catch-up is forbidden.
"""

from __future__ import annotations

from harness.automation.model import AutomationDefinition
from harness.automation.validation import validate_automation

NOW = "2026-11-17T10:00:00Z"


def definition(*, state="draft", mode="shadow", tier="l0", trial="live_1",
               consent=None, misfire="skip", symbols=None, connection="brk_1"):
    config = {
        "strategyId": "ema_trend",
        "strategyVersion": "1.0.0",
        "mode": mode,
        "connectionId": "" if mode == "shadow" else connection,
        "symbols": ["EURUSD"] if symbols is None else symbols,
        "dynamicSymbols": False,
        "maxSymbols": 4,
        "timeframe": "H1",
        "volume": 0.1,
        "stopLossPoints": 150,
        "takeProfitPoints": 300,
        "maxOrdersPerDay": 2,
        "session": None,
        "trialId": trial,
        "dryRun": False,
        "consent": consent,
        "visuals": [],
        "learning": {"enabled": True, "threshold": 3},
    }
    return AutomationDefinition(
        id="aut_1",
        name="Trend bot",
        state=state,
        trigger={"type": "manual", "timezone": "UTC"},
        action={"type": "run_strategy", "objective": "trade the trend", "config": config},
        execution={"misfire": misfire},
        execution_authority={
            "tier": tier,
            "appetite": "conservative",
            "maxOpenPositions": 1,
            "maxMarginPerOrder": 500,
            "requireStop": True,
        },
        created_at=NOW,
        updated_at=NOW,
    )


def codes(issues):
    return {issue.code for issue in issues}


def lookup(strategy_id, version):
    return {"id": strategy_id} if strategy_id == "ema_trend" else None


def test_a_complete_shadow_draft_is_valid():
    issues = validate_automation(definition(), strategy_lookup=lookup)
    assert [issue.code for issue in issues if issue.severity == "error"] == []


def test_missing_pins_are_field_errors():
    bot = definition()
    bot.action.config.pop("strategyId")
    bot.action.config.pop("strategyVersion")
    issues = validate_automation(bot, strategy_lookup=lookup)
    found = codes(issues)
    assert "STRATEGY_ID_REQUIRED" in found
    assert "STRATEGY_VERSION_REQUIRED" in found


def test_an_unknown_strategy_is_an_error_not_a_warning():
    bot = definition()
    bot.action.config["strategyId"] = "missing"
    issues = validate_automation(bot, strategy_lookup=lookup)
    assert "STRATEGY_UNAVAILABLE" in codes(issues)


def test_a_draft_may_be_saved_without_a_trial_but_an_active_bot_cannot():
    draft = validate_automation(definition(state="draft", trial=""), strategy_lookup=lookup)
    warning = next(i for i in draft if i.code == "TRADING_NOT_PREPARED")
    assert warning.severity == "warning"

    active = validate_automation(definition(state="active", trial=""), strategy_lookup=lookup)
    error = next(i for i in active if i.code == "TRADING_NOT_PREPARED")
    assert error.severity == "error"


def test_live_needs_l2():
    issues = validate_automation(
        definition(mode="live", tier="l1"), strategy_lookup=lookup,
    )
    assert "BOT_TIER_REQUIRED" in codes(issues)


def test_an_active_demo_bot_needs_covering_consent():
    active = validate_automation(
        definition(state="active", mode="demo", tier="l1"), strategy_lookup=lookup,
    )
    assert "CONSENT_REQUIRED" in codes(active)

    consent = {
        "kind": "standing",
        "modes": ["demo"],
        "grantedAt": NOW,
        "expiresAt": "2099-01-01T00:00:00Z",
        "revokedAt": None,
        "limits": {
            "symbols": ["EURUSD"],
            "maxOrdersPerDay": 2,
            "maxMarginPerOrder": 500,
            "maxOpenPositions": 1,
        },
    }
    covered = validate_automation(
        definition(state="active", mode="demo", tier="l1", consent=consent),
        strategy_lookup=lookup,
    )
    assert "CONSENT_REQUIRED" not in codes(covered)


def test_misfire_catch_up_is_refused_for_a_trading_bot():
    issues = validate_automation(
        definition(misfire="run_once"), strategy_lookup=lookup,
    )
    assert "MISTRADE_RISK" in codes(issues)


def test_a_symbol_list_is_required():
    issues = validate_automation(
        definition(symbols=[]), strategy_lookup=lookup,
    )
    assert "SYMBOLS_REQUIRED" in codes(issues)


def test_the_stop_requirement_is_enforced_when_the_authority_demands_it():
    bot = definition()
    bot.action.config["stopLossPoints"] = 0
    issues = validate_automation(bot, strategy_lookup=lookup)
    assert "STOP_REQUIRED" in codes(issues)


def test_the_appetite_band_caps_orders_and_positions():
    bot = definition()
    bot.action.config["maxOrdersPerDay"] = 9
    issues = validate_automation(bot, strategy_lookup=lookup)
    assert "ORDERS_ABOVE_BAND" in codes(issues)

    bot = definition()
    bot.execution_authority.max_open_positions = 3  # conservative band = 1
    issues = validate_automation(bot, strategy_lookup=lookup)
    assert "POSITIONS_ABOVE_BAND" in codes(issues)
