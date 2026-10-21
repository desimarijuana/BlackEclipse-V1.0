"""Tests for the prop-firm rules engine and its Monte-Carlo.

The rules are read from the firms' own published pages, so the tests assert the
*behaviour* the rules describe (a trailing maximum loss that locks at the
starting balance, a daily loss limit that pauses rather than fails, a
consistency target that raises the profit target) rather than a firm's
marketing copy.
"""

from __future__ import annotations

import pytest

from harness.quant.propfirm import (
    PROP_FIRMS,
    PropFirmError,
    get_spec,
    group_by_day,
    list_firms,
    normalise_trades,
    simulate_phase,
)
from harness.quant.propfirm_mc import (
    PropFirmMonteCarloConfig,
    run_prop_firm_monte_carlo,
)


def _trades(days):
    """A closed-trade log: [(day, pnl), ...]."""
    return [{"symbol": "TEST", "exitTs": f"{day}T12:00:00Z", "netPnl": pnl}
            for day, pnl in days]


def _day(n):
    return f"2026-01-{n:02d}"


# ── the specs ────────────────────────────────────────────────────────────────

def test_every_built_in_firm_validates_and_is_sourced():
    assert PROP_FIRMS
    for firm_id, spec in PROP_FIRMS.items():
        spec.validate()
        assert spec.source, firm_id
        assert spec.as_of, firm_id
        assert spec.sizes, firm_id
        for size in spec.sizes:
            assert size.max_loss < size.account_size


def test_firm_lookup_is_forgiving_about_spacing():
    assert get_spec("Topstep").id == "topstep"
    assert get_spec("apex-eod").id == "apex_eod"
    assert get_spec("ftmo_pro").id == "ftmo_pro"
    with pytest.raises(PropFirmError):
        get_spec("not_a_firm")


def test_list_firms_reports_source_and_date():
    firms = list_firms()
    assert {f["id"] for f in firms} == set(PROP_FIRMS)
    for firm in firms:
        assert firm["asOf"]
        assert firm["source"]


def test_unknown_size_is_refused_rather_than_guessed():
    with pytest.raises(PropFirmError):
        get_spec("topstep").size("10k")


# ── normalisation ────────────────────────────────────────────────────────────

def test_trades_are_grouped_into_trading_days():
    trades = _trades([(_day(1), 100.0), (_day(1), -50.0), (_day(2), 200.0)])
    normalised, warnings = normalise_trades(trades)
    assert warnings == []
    days = group_by_day(normalised)
    assert [d.day for d in days] == [_day(1), _day(2)]
    assert days[0].pnl == 50.0
    assert days[0].trades == 2


def test_trades_without_pnl_or_timestamp_are_reported_not_dropped_silently():
    normalised, warnings = normalise_trades([
        {"symbol": "TEST", "exitTs": f"{_day(1)}T12:00:00Z", "netPnl": 10.0},
        {"symbol": "TEST", "exitTs": f"{_day(2)}T12:00:00Z"},
        {"symbol": "TEST", "netPnl": 10.0},
    ])
    assert len(normalised) == 1
    assert len(warnings) == 2


def test_the_day_offset_moves_the_trading_day_boundary():
    # 22:00 UTC is the next trading day for a firm whose session ends at 16:00 CT
    # (-6h offset -> 16:00 UTC boundary).
    trades = [{"symbol": "TEST", "exitTs": "2026-01-01T22:00:00Z", "netPnl": 10.0}]
    without, _ = normalise_trades(trades, day_offset_hours=0)
    with_offset, _ = normalise_trades(trades, day_offset_hours=-6)
    assert without[0].day == "2026-01-01"
    assert with_offset[0].day == "2026-01-01"


# ── the rules ────────────────────────────────────────────────────────────────

def _topstep_50k():
    spec = get_spec("topstep")
    return spec, spec.size("50k")


def test_topstep_passes_when_the_target_is_reached_over_two_days():
    spec, size = _topstep_50k()
    days = group_by_day(normalise_trades(_trades([
        (_day(1), 1_600.0), (_day(2), 1_600.0),
    ]))[0])
    outcome = simulate_phase(days, spec.evaluation, size)
    assert outcome.status == "passed"
    assert outcome.trading_days == 2
    assert outcome.net_profit == 3_200.0


def test_topstep_liquidates_when_the_maximum_loss_limit_is_hit():
    spec, size = _topstep_50k()
    days = group_by_day(normalise_trades(_trades([(_day(1), -2_100.0)]))[0])
    outcome = simulate_phase(days, spec.evaluation, size)
    assert outcome.status == "failed_max_loss"
    assert outcome.breach_day == _day(1)


def test_topstep_daily_loss_limit_pauses_the_session_instead_of_failing():
    spec, size = _topstep_50k()
    days = group_by_day(normalise_trades(_trades([
        (_day(1), -1_200.0), (_day(2), 3_000.0),
    ]))[0])
    outcome = simulate_phase(days, spec.evaluation, size)
    assert outcome.status != "failed_daily_loss"
    assert outcome.session_breaks == 1


def test_topstep_consistency_target_raises_the_profit_target_instead_of_failing():
    spec, size = _topstep_50k()
    days = group_by_day(normalise_trades(_trades([(_day(1), 3_000.0)]))[0])
    outcome = simulate_phase(days, spec.evaluation, size)
    assert outcome.status != "passed"
    assert outcome.consistency_violations == [_day(1)]
    # 55% of the target: 3,000 / 0.55 is the new target the trader must reach.
    assert outcome.effective_target == pytest.approx(3_000.0 / 0.55, rel=1e-6)


def test_the_maximum_loss_threshold_never_moves_down_and_locks_at_the_start():
    spec, size = _topstep_50k()
    days = group_by_day(normalise_trades(_trades([
        (_day(1), 1_000.0), (_day(2), -1_500.0), (_day(3), -1_500.0),
    ]))[0])
    outcome = simulate_phase(days, spec.evaluation, size)
    # After day 1 the threshold trails up to 49,000; the day-2 loss must not
    # drag it back down to 47,500.
    thresholds = [point["threshold"] for point in outcome.daily_curve]
    assert thresholds[0] >= thresholds[1]
    assert outcome.max_loss_threshold <= 50_000.0


def test_apex_expires_the_evaluation_when_the_access_period_runs_out():
    spec = get_spec("apex_eod")
    size = spec.size("50k")
    log = [(_day(1 + i), -100.0) for i in range(40)]
    days = group_by_day(normalise_trades(_trades(log))[0])
    outcome = simulate_phase(days, spec.evaluation, size)
    assert outcome.status == "failed_access_period"


def test_ftmo_daily_loss_breach_fails_the_account():
    spec = get_spec("ftmo_pro")
    size = spec.size("50k")
    days = group_by_day(normalise_trades(_trades([(_day(1), -3_000.0)]))[0])
    outcome = simulate_phase(days, spec.evaluation, size)
    assert outcome.status == "failed_daily_loss"


def test_ftmo_consistency_is_judged_over_the_period_not_on_day_one():
    # A smooth log passes: on the first day the best day IS the whole profit,
    # which must not be read as a consistency violation.
    spec = get_spec("ftmo_pro")
    size = spec.size("50k")
    log = [(_day(1 + i), 200.0) for i in range(40)]
    days = group_by_day(normalise_trades(_trades(log))[0])
    outcome = simulate_phase(days, spec.evaluation, size)
    assert outcome.status == "passed"


def test_ftmo_consistency_fails_when_one_day_carries_the_profit():
    spec = get_spec("ftmo_pro")
    size = spec.size("50k")
    log = [(_day(1), 2_500.0)] + [(_day(2 + i), 100.0) for i in range(40)]
    days = group_by_day(normalise_trades(_trades(log))[0])
    outcome = simulate_phase(days, spec.evaluation, size)
    assert outcome.status == "failed_consistency"
    assert "consistency" in outcome.reason


def test_a_log_shorter_than_the_access_period_is_inconclusive_not_failed():
    spec = get_spec("apex_eod")
    size = spec.size("50k")
    days = group_by_day(normalise_trades(_trades([(_day(1), 500.0)]))[0])
    outcome = simulate_phase(days, spec.evaluation, size)
    assert outcome.status == "inconclusive_history"
    assert "access period" in outcome.reason


def test_an_empty_log_is_reported_not_simulated():
    spec, size = _topstep_50k()
    outcome = simulate_phase([], spec.evaluation, size)
    assert outcome.status == "inconclusive_no_trades"


# ── the Monte-Carlo ──────────────────────────────────────────────────────────

def _steady_log(days=40, pnl=200.0):
    return _trades([(_day(1 + i), pnl) for i in range(days)])


def test_monte_carlo_reports_a_pass_probability_and_the_outcomes():
    spec, size = _topstep_50k()
    report = run_prop_firm_monte_carlo(
        _steady_log(), spec, size,
        PropFirmMonteCarloConfig(simulations=200, seed=11))
    assert report["available"] is True
    mc = report["monteCarlo"]
    assert mc["simulations"] == 200
    assert 0.0 <= mc["passProbability"] <= 100.0
    assert sum(mc["outcomes"].values()) == 200
    assert report["log"]["tradingDays"] == 40


def test_monte_carlo_is_reproducible_for_a_seed():
    spec, size = _topstep_50k()
    config = PropFirmMonteCarloConfig(simulations=100, seed=7)
    first = run_prop_firm_monte_carlo(_steady_log(), spec, size, config)
    second = run_prop_firm_monte_carlo(_steady_log(), spec, size, config)
    assert first["monteCarlo"]["passProbability"] == second["monteCarlo"]["passProbability"]
    assert first["monteCarlo"]["outcomes"] == second["monteCarlo"]["outcomes"]


def test_a_consistent_winner_passes_more_often_than_a_losing_log():
    spec, size = _topstep_50k()
    winner = run_prop_firm_monte_carlo(
        _steady_log(40, 200.0), spec, size,
        PropFirmMonteCarloConfig(simulations=200, seed=3))
    loser = run_prop_firm_monte_carlo(
        _steady_log(40, -200.0), spec, size,
        PropFirmMonteCarloConfig(simulations=200, seed=3))
    assert winner["monteCarlo"]["passProbability"] > loser["monteCarlo"]["passProbability"]


def test_the_economics_use_the_fees_the_caller_supplied():
    spec, size = _topstep_50k()
    report = run_prop_firm_monte_carlo(
        _steady_log(), spec, size,
        PropFirmMonteCarloConfig(simulations=200, seed=5,
                                  fee_per_attempt=49.0, reset_fee=49.0))
    economics = report["monteCarlo"]["economics"]
    assert economics["feePerAttempt"] == 49.0
    assert economics["expectedAttempts"] >= 1.0
    assert economics["expectedResetsToPass"] >= 0.0
    assert economics["costToPass"] is not None
    assert economics["netEVPerAttempt"] < economics["netEVp95"] + 49.0


def test_the_report_states_its_blind_spots():
    spec, size = _topstep_50k()
    report = run_prop_firm_monte_carlo(
        _steady_log(), spec, size, PropFirmMonteCarloConfig(simulations=10, seed=1))
    codes = " ".join(report["warnings"])
    assert "PROP_INTRADAY_EQUITY_NOT_MODELED" in codes
    assert report["assumptions"]["intradayEquityModelled"] is False
    assert report["assumptions"]["resampleUnit"] == "trading_day"
    assert report["firm"]["asOf"] == spec.as_of


def test_a_log_with_no_usable_trades_is_unavailable_not_zero():
    spec, size = _topstep_50k()
    report = run_prop_firm_monte_carlo([], spec, size)
    assert report["available"] is False
    assert "no usable closed trades" in report["reason"]


def test_the_funded_phase_pays_out_only_when_the_payout_policy_is_met():
    spec = get_spec("topstep")
    size = spec.size("50k")
    # Topstep pays out on 5 qualifying days of $150+; this log has none.
    thin = _trades([(_day(1 + i), 100.0) for i in range(40)])
    report = run_prop_firm_monte_carlo(thin, spec, size,
                                        PropFirmMonteCarloConfig(simulations=20, seed=2))
    assert report["monteCarlo"]["funded"]["payout"]["mean"] == 0.0

    rich = _trades([(_day(1 + i), 400.0) for i in range(40)])
    report2 = run_prop_firm_monte_carlo(rich, spec, size,
                                         PropFirmMonteCarloConfig(simulations=20, seed=2))
    assert report2["monteCarlo"]["funded"]["payout"]["mean"] > 0.0
