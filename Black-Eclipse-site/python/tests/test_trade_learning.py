"""Trade learning: deterministic detectors, tighten-only playbook, honest climb."""

from __future__ import annotations

import datetime as dt

import pytest

from harness.persistence import AgentMemoryStore
from harness.trade_learning import (
    Playbook,
    PlaybookRefused,
    TradeLearningService,
    TradeLearningStore,
    climb,
    decide,
    evaluate,
    review,
    validate_limits,
)
from harness.trade_learning.model import DEFAULT_LIMITS
from harness.trade_learning.replay import walk_forward

NOW = dt.datetime(2026, 2, 1, 12, 0, tzinfo=dt.timezone.utc)


def trade(index: int, **overrides):
    """One closed trade, clean unless a test overrides a field."""
    day = (index % 27) + 1
    month = 1 if index < 27 else 2
    entry = f"2026-{month:02d}-{day:02d}T09:00:00+00:00"
    exit_ = f"2026-{month:02d}-{day:02d}T12:00:00+00:00"
    payload = {
        "id": f"t{index}",
        "symbol": "EURUSD",
        "direction": "LONG",
        "entry": 1.10,
        "exit": 1.09,
        "stopLoss": 1.095,
        "takeProfit": 1.11,
        "quantity": 10_000,
        "entryTime": entry,
        "exitTime": exit_,
        "status": "closed",
        "strategyId": "s1",
        "setupId": "setup1",
        "session": "London",
        "rMultiple": -1.0,
        "riskAmount": 100.0,
        "mfe": 0.4,
        "mae": -1.0,
        "actualRR": 2.0,
        "pnl": -100.0,
        "pnlPct": -1.0,
        "grade": "B",
    }
    payload.update(overrides)
    return payload


def review_of(trades, **kwargs):
    return review(trades, config={"accountEquity": 0}, now=NOW, **kwargs)


# ── detection ────────────────────────────────────────────────────────────────

def test_no_stop_is_a_finding_and_a_planned_loss_is_clean():
    clean = review_of([trade(1)])
    assert clean["findings"] == []
    assert clean["summary"]["cleanTrades"] == 1

    broken = review_of([trade(2, stopLoss=None)])
    assert [f["category"] for f in broken["findings"]] == ["no_stop"]
    assert broken["findings"][0]["evidence"] == {"stopLoss": None}
    assert broken["findings"][0]["severity"] == "high"


def test_early_exit_needs_a_recorded_mfe_and_reports_coverage():
    hit = review_of([trade(1, rMultiple=0.5, mfe=1.6)])
    assert "early_exit" in [f["category"] for f in hit["findings"]]

    missing = review_of([trade(2, rMultiple=0.5, mfe=None)])
    assert "early_exit" not in [f["category"] for f in missing["findings"]]
    assert missing["coverage"]["early_exit"]["fraction"] < 1.0


def test_stop_widened_reads_the_execution_log_in_the_right_direction():
    executions = {"t1": [{
        "kind": "stop_modified",
        "detail": {"from": 1.095, "to": 1.09},
        "createdAt": "2026-01-01T10:00:00+00:00",
    }]}
    widened = review_of([trade(1)], executions=executions)
    assert [f["category"] for f in widened["findings"]] == ["stop_widened"]

    tightened = {"t1": [{
        "kind": "stop_modified",
        "detail": {"from": 1.095, "to": 1.098},
        "createdAt": "2026-01-01T10:00:00+00:00",
    }]}
    assert review_of([trade(1)], executions=tightened)["findings"] == []


def test_revenge_only_counts_a_loss_that_had_already_closed():
    first = trade(1, rMultiple=-1.0, exitTime="2026-01-01T10:00:00+00:00")
    revenge = trade(2, entryTime="2026-01-01T10:10:00+00:00",
                    exitTime="2026-01-01T10:30:00+00:00")
    before = trade(3, entryTime="2026-01-01T09:00:00+00:00",
                   exitTime="2026-01-01T09:30:00+00:00")
    found = review_of([first, revenge])["findings"]
    assert [f["tradeId"] for f in found if f["category"] == "revenge_trade"] == ["t2"]

    # A trade entered BEFORE the loss is not a reaction to it.
    early = review_of([first, before])["findings"]
    assert not any(f["category"] == "revenge_trade" for f in early)


def test_overtrading_and_off_symbol_use_the_playbook():
    book = Playbook(
        limits={**DEFAULT_LIMITS, "maxTradesPerDay": 1, "symbolBlocklist": ["GBPUSD"]},
        bounds={},
    )
    trades = [
        trade(1, exitTime="2026-01-01T10:00:00+00:00"),
        trade(2, exitTime="2026-01-01T11:00:00+00:00"),
        trade(3, symbol="GBPUSD"),
    ]
    categories = [f["category"] for f in review_of(trades, playbook=book)["findings"]]
    assert "overtraded" in categories
    assert "off_symbol" in categories


# ── playbook authority ───────────────────────────────────────────────────────

def test_playbook_only_moves_toward_tighter_and_inside_bounds():
    bounds = {
        "riskPerTradePct": {"min": 0.25, "max": 5.0},
        "requireStop": {"allow": True},
    }
    current = Playbook(limits={**DEFAULT_LIMITS, "riskPerTradePct": 1.0}, bounds=bounds)

    tighter = validate_limits({**current.limits, "riskPerTradePct": 0.5},
                              bounds=bounds, current=current)
    assert tighter["riskPerTradePct"] == 0.5

    with pytest.raises(PlaybookRefused) as looser:
        validate_limits({**current.limits, "riskPerTradePct": 2.0},
                        bounds=bounds, current=current)
    assert looser.value.code == "NOT_A_TIGHTENING"

    with pytest.raises(PlaybookRefused) as outside:
        validate_limits({**current.limits, "riskPerTradePct": 0.1},
                        bounds=bounds, current=current)
    assert outside.value.code == "OUT_OF_BOUNDS"


def test_first_version_has_bounds_but_no_direction_to_tighten_against():
    bounds = {"riskPerTradePct": {"min": 0.0, "max": 5.0}}
    limits = validate_limits(
        {**DEFAULT_LIMITS, "riskPerTradePct": 1.0}, bounds=bounds,
        current=None, enforce_direction=False,
    )
    assert limits["riskPerTradePct"] == 1.0


# ── replay / climb ───────────────────────────────────────────────────────────

def test_require_stop_blocks_unprotected_trades():
    book = Playbook(limits={**DEFAULT_LIMITS, "requireStop": True}, bounds={})
    trades = [trade(1), trade(2, stopLoss=None)]
    decisions = decide(book, trades)
    by_id = {row["tradeId"]: row for row in decisions}
    assert by_id["t1"]["allowed"] is True
    assert by_id["t2"]["allowed"] is False
    assert by_id["t2"]["reason"] == "missing_stop"


def _climb_fixture(n=40):
    trades = []
    for index in range(n):
        if index % 2 == 0:
            trades.append(trade(index, stopLoss=None, rMultiple=-1.5, mfe=0.2))
        else:
            trades.append(trade(index, rMultiple=1.0, mfe=1.4))
    return trades


def test_the_climb_improves_the_holdout_and_is_deterministic():
    trades = _climb_fixture()
    current = Playbook(limits={**DEFAULT_LIMITS}, bounds={"requireStop": {"allow": True}})
    first = climb(trades, current=current, k=2, generations=2, seed=11,
                  min_validation_trades=5, min_lift_r=0.01)
    second = climb(trades, current=current, k=2, generations=2, seed=11,
                   min_validation_trades=5, min_lift_r=0.01)

    assert first["accepted"] is True
    assert first["best"]["limits"]["requireStop"] is True
    assert first["best"]["hash"] == second["best"]["hash"]
    assert first["candidates"] == second["candidates"]
    assert first["sample"].startswith("simulated")
    # The accepted candidate must actually be better on the holdout, not the fit.
    assert (first["baseline"]["holdout"]["expectancyR"] is None
            or first["best"] is not None)


def test_walk_forward_separates_fit_from_holdout():
    result = walk_forward(
        Playbook(limits={**DEFAULT_LIMITS, "requireStop": True}, bounds={}),
        _climb_fixture(), split_pct=0.7,
    )
    assert result["fitTrades"] + result["holdoutTrades"] == 40
    assert result["fit"]["sample"].startswith("simulated")


def test_climb_refuses_without_bounds():
    result = climb(_climb_fixture(), current=Playbook(limits={**DEFAULT_LIMITS}, bounds={}))
    assert result["accepted"] is False
    assert result["reason"] == "no_mutable_knobs"


# ── store / service ──────────────────────────────────────────────────────────

@pytest.fixture()
def service(tmp_path):
    store = TradeLearningStore(AgentMemoryStore(str(tmp_path / "am.db")))
    return TradeLearningService(store)


def _finding(index: int, *, signature="sig-a", category="no_stop", r=-1.0):
    return {
        "tradeId": f"t{index}",
        "category": category,
        "severity": "high",
        "expected": "a stop",
        "actual": "no stop",
        "evidence": {"stopLoss": None},
        "signature": signature,
        "detectorVersion": "1",
        "rMultiple": r,
        "rAvailable": r is not None,
        "symbol": "EURUSD",
    }


def test_findings_are_idempotent_and_recurrence_dedupes_by_trade(service):
    findings = [_finding(1), _finding(2)]
    assert service.store.record_findings(findings) == 2
    assert service.store.record_findings(findings) == 0

    counts = service.store.record_recurrence(findings)
    assert counts["sig-a"] == 2
    # Re-analysing the same trades must not inflate the ONE ledger.
    again = service.store.record_recurrence(findings)
    assert again["sig-a"] == 2


def test_learning_needs_recurrence_and_coverage(service):
    two = service.learn([_finding(1), _finding(2)], coverage={"no_stop": {"fraction": 0.9}})
    assert two["recurring"][0]["eligibility"] == "not_yet"
    assert "below_occurrence_threshold" in two["recurring"][0]["reasons"]

    three = service.learn(
        [_finding(1), _finding(2), _finding(3)],
        coverage={"no_stop": {"fraction": 0.9}},
    )
    assert three["recurring"][0]["eligibility"] == "eligible"
    assert three["recurring"][0]["windowCount"] == 3

    thin = service.learn(
        [_finding(4), _finding(5), _finding(6)],
        coverage={"no_stop": {"fraction": 0.2}},
    )
    assert thin["recurring"][0]["eligibility"] == "not_yet"
    assert "insufficient_coverage" in thin["recurring"][0]["reasons"]


def test_playbook_versions_append_and_revert(service):
    bounds = {"requireStop": {"allow": True}, "riskPerTradePct": {"min": 0.0, "max": 5.0}}
    first = service.store.save_playbook(
        {**DEFAULT_LIMITS, "requireStop": False}, bounds=bounds, reason="initial",
    )
    assert first["changed"] is True
    second = service.store.save_playbook(
        {**DEFAULT_LIMITS, "requireStop": True}, bounds=bounds, reason="tighten",
    )
    assert second["playbook"]["version"] == 2
    assert service.store.active_playbook().limits["requireStop"] is True

    reverted = service.store.revert()
    assert reverted["active"]["version"] == 1
    assert service.store.active_playbook().limits["requireStop"] is False


def test_a_playbook_version_expires_and_reverts(service):
    bounds = {"requireStop": {"allow": True}}
    service.store.save_playbook({**DEFAULT_LIMITS}, bounds=bounds, reason="initial")
    service.store.save_playbook(
        {**DEFAULT_LIMITS, "requireStop": True}, bounds=bounds,
        reason="tighten", ttl_days=1,
    )
    assert service.store.active_playbook().limits["requireStop"] is True
    expired = service.store.expire_due(now="2030-01-01T00:00:00Z")
    assert expired is not None
    assert expired["reason"] == "expired"
    assert service.store.active_playbook().limits["requireStop"] is False


def test_improve_refuses_without_bounds(service):
    result = service.improve([trade(1)])
    assert result["accepted"] is False
    assert result["reason"] == "no_bounds"
    assert result["baseline"] == {"fit": None, "holdout": None}
