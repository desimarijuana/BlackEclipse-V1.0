"""Deterministic Financial Analysis Engine — unit, edge-case and tool tests.

Covers the metrics added to `research.calculations` (returns, alpha, correlation,
covariance, CVaR, parametric/Monte-Carlo VaR, drawdown detail, rolling metrics,
matrices, risk contribution), the fundamentals additions
(`finance_facts.metrics`: FCF/EV/growth/FCFF/FCFE), the valuation additions
(`finance_facts.valuation`: schedule, sensitivity, scenarios), the adapter
(`research.web_finance`), the high-level analysis planner
(`research.finance_analysis`) and the agent-facing tools (`research.web_tools`).

The through-line mirrors the rest of the engine: a metric whose input is missing
is refused, never defaulted; every result carries its formula + assumptions; a
stochastic result records its seed; financial invariants hold.
"""

from __future__ import annotations

import asyncio
import math
import statistics

import pytest

from harness.finance_facts import metrics as M
from harness.finance_facts import valuation as V
from harness.finance_facts.model import FinancialFact, FinancialPeriod
from harness.research import calculations as C
from harness.research import finance_analysis as FA
from harness.research import web_finance as WF
from harness.research import web_tools as WT
from harness.tools import ToolContext, ToolRegistry


def obs(values, *, start=1, identity=None, currency=None):
    out = []
    for i, v in enumerate(values):
        o = {"date": f"2024-01-{start + i:02d}", "value": v}
        if identity:
            o["identity"] = identity
        if currency:
            o["currency"] = currency
        out.append(o)
    return out


VALS = [100.0, 102.0, 99.0, 103.0, 98.0, 105.0, 101.0, 107.0, 104.0, 110.0]


# ── returns ─────────────────────────────────────────────────────────────────────


def test_cumulative_return_simple_and_log_agree_on_small_moves():
    a = C.cumulative_return(obs([100.0, 110.0, 121.0]))
    b = C.cumulative_return(obs([100.0, 110.0, 121.0]), method="log")
    assert a.value == pytest.approx(21.0)
    assert b.value == pytest.approx(21.0)
    assert a.value == pytest.approx(b.value, rel=1e-9)


def test_log_return_rejects_non_positive_price():
    with pytest.raises(C.CalculationError):
        C.cumulative_return(obs([100.0, 0.0, 50.0]), method="log")


def test_unknown_return_method_rejected():
    with pytest.raises(C.CalculationError):
        C.cumulative_return(obs([1.0, 2.0]), method="geometric")


def test_annualized_return_known_value():
    # 100 -> 121 over exactly two years = 10%.
    result = C.annualized_return(obs([100.0, 121.0]), years=2.0)
    assert result.value == pytest.approx(10.0, abs=1e-9)


def test_annualized_return_requires_span_or_frequency():
    with pytest.raises(C.CalculationError):
        C.annualized_return(obs([100.0, 121.0]))


def test_volatility_method_is_recorded():
    simple = C.annualized_volatility(obs(VALS), frequency="daily")
    log = C.annualized_volatility(obs(VALS), frequency="daily", method="log")
    assert any("simple returns" in a for a in simple.assumptions)
    assert any("log returns" in a for a in log.assumptions)
    assert simple.value > 0 and log.value > 0


# ── correlation / covariance ────────────────────────────────────────────────────


def test_correlation_with_self_is_one():
    assert C.correlation(obs(VALS), obs(VALS)).value == pytest.approx(1.0)


def test_correlation_with_negation_is_minus_one():
    neg = [-v for v in VALS]
    assert C.correlation(obs(VALS), obs(neg)).value == pytest.approx(-1.0)


def test_correlation_is_clamped_and_in_range():
    r = C.correlation(obs(VALS), obs([3, 1, 4, 1, 5, 9, 2, 6, 5, 3])).value
    assert -1.0 <= r <= 1.0


def test_spearman_is_one_for_any_monotone_transform():
    # y = exp(x) is strictly monotone, so Spearman correlation is exactly 1.
    y = [math.exp(v) for v in VALS]
    assert C.correlation(obs(VALS), obs(y), method="spearman").value == pytest.approx(1.0)


def test_kendall_positive_for_concordant_series():
    r = C.correlation(obs(VALS), obs([1, 2, 3, 4, 5, 6, 7, 8, 9, 10])).value
    assert r > 0


def test_correlation_zero_variance_rejected():
    with pytest.raises(C.CalculationError):
        C.correlation(obs([5.0, 5.0, 5.0, 5.0]), obs([1.0, 2.0, 3.0, 4.0]))


def test_covariance_sample_vs_population_and_cov_x_x_is_variance():
    x = VALS
    y = [3.0, 1.0, 4.0, 1.0, 5.0, 9.0, 2.0, 6.0, 5.0, 3.0]
    sample = C.covariance(obs(x), obs(y), ddof=1).value
    population = C.covariance(obs(x), obs(y), ddof=0).value
    expected_sample = statistics.covariance(x, y)
    assert sample == pytest.approx(expected_sample)
    assert population == pytest.approx(expected_sample * (len(x) - 1) / len(x))
    self_cov = C.covariance(obs(x), obs(x), ddof=1).value
    assert self_cov == pytest.approx(statistics.variance(x))


def test_aligned_pairs_use_date_intersection_not_positions():
    a = [{"date": "2024-01-01", "value": 1.0}, {"date": "2024-01-02", "value": 2.0}, {"date": "2024-01-03", "value": 3.0}, {"date": "2024-01-04", "value": 4.0}]
    b = [{"date": "2024-01-02", "value": 2.0}, {"date": "2024-01-03", "value": 4.0}, {"date": "2024-01-04", "value": 8.0}, {"date": "2024-01-05", "value": 16.0}]
    result = C.correlation(a, b)
    assert result.detail["alignedDates"] == ["2024-01-02", "2024-01-03", "2024-01-04"]
    assert result.detail["observations"] == 3


def test_aligned_pairs_refuse_insufficient_overlap():
    a = [{"date": "2024-01-01", "value": 1.0}, {"date": "2024-01-02", "value": 2.0}, {"date": "2024-01-03", "value": 3.0}]
    b = [{"date": "2024-01-02", "value": 2.0}, {"date": "2024-01-03", "value": 4.0}, {"date": "2024-01-06", "value": 8.0}]
    with pytest.raises(C.CalculationError, match="date-aligned"):
        C.correlation(a, b)


# ── alpha ───────────────────────────────────────────────────────────────────────


def test_alpha_zero_when_asset_is_the_benchmark():
    result = C.alpha(obs(VALS), obs(VALS), risk_free_rate=0.0, frequency="daily")
    assert result.value == pytest.approx(0.0, abs=1e-9)
    assert result.detail["beta"] == pytest.approx(1.0)


def test_alpha_requires_explicit_risk_free_rate():
    with pytest.raises(C.CalculationError):
        C.alpha(obs(VALS), obs(VALS), risk_free_rate=None)  # type: ignore[arg-type]


# ── VaR / CVaR ──────────────────────────────────────────────────────────────────


def _cvar_ge_var(price_series, **kw):
    var = C.value_at_risk(price_series, **kw).value
    cvar = C.cvar(price_series, **kw).value
    return var, cvar


def test_historical_cvar_at_least_as_severe_as_var():
    var, cvar = _cvar_ge_var(obs(VALS))
    assert cvar >= var - 1e-9


def test_parametric_cvar_at_least_as_severe_as_parametric_var():
    pvar = C.parametric_var(obs(VALS)).value
    pcvar = C.cvar(obs(VALS), method="parametric").value
    assert pcvar >= pvar - 1e-9


def test_monte_carlo_is_reproducible_for_a_seed():
    a = C.monte_carlo_var(obs(VALS), seed=123, simulations=5000).value
    b = C.monte_carlo_var(obs(VALS), seed=123, simulations=5000).value
    c = C.monte_carlo_var(obs(VALS), seed=999, simulations=5000).value
    assert a == b
    assert a != c
    detail = C.monte_carlo_var(obs(VALS), seed=123, simulations=5000).detail
    assert detail["seed"] == 123 and detail["simulations"] == 5000


def test_monte_carlo_cvar_at_least_as_severe_as_monte_carlo_var():
    var = C.monte_carlo_var(obs(VALS), seed=7).value
    cvar = C.cvar(obs(VALS), method="monte_carlo", seed=7).value
    assert cvar >= var - 1e-9


def test_var_rejects_too_few_simulations():
    with pytest.raises(C.CalculationError):
        C.monte_carlo_var(obs(VALS), simulations=10)


def test_cvar_rejects_bad_confidence_and_method():
    with pytest.raises(C.CalculationError):
        C.cvar(obs(VALS), confidence=1.5)
    with pytest.raises(C.CalculationError):
        C.cvar(obs(VALS), method="wishful")


# ── drawdown ────────────────────────────────────────────────────────────────────


def test_drawdown_analysis_full_detail():
    result = C.drawdown_analysis(obs([100.0, 120.0, 60.0, 90.0, 130.0]))
    assert result.value == pytest.approx(-50.0)
    d = result.detail
    assert d["peakDate"] == "2024-01-02"
    assert d["troughDate"] == "2024-01-03"
    assert d["recoveryDate"] == "2024-01-05"
    assert d["drawdownDuration"] == 1
    assert d["recoveryDuration"] == 2
    assert len(d["drawdownSeries"]) == 5
    assert d["topDrawdowns"][0]["depthPct"] == pytest.approx(-50.0)


def test_drawdown_analysis_monotonic_up_is_zero():
    result = C.drawdown_analysis(obs([100.0, 110.0, 120.0]))
    assert result.value == pytest.approx(0.0)
    assert result.detail["peakDate"] is None


# ── rolling ─────────────────────────────────────────────────────────────────────


def test_rolling_volatility_series_length():
    result = C.rolling_volatility(obs(VALS), window=4, frequency="daily")
    assert len(result.detail["series"]) == len(VALS) - 1 - 4 + 1
    assert result.value == result.detail["series"][-1]["value"]


def test_rolling_correlation_and_beta_series():
    r = C.rolling_correlation(obs(VALS), obs(VALS), window=4)
    assert all(p["value"] == pytest.approx(1.0) for p in r.detail["series"])
    b = C.rolling_beta(obs(VALS), obs(VALS), window=4)
    assert all(p["value"] == pytest.approx(1.0) for p in b.detail["series"])


def test_rolling_requires_window_large_enough():
    with pytest.raises(C.CalculationError):
        C.rolling_volatility(obs([1.0, 2.0, 3.0]), window=10)


# ── matrices + risk contribution ────────────────────────────────────────────────


def _named_series():
    return [
        {"name": "A", "observations": obs([100, 102, 99, 103, 98, 105, 101])},
        {"name": "B", "observations": obs([50, 51, 49, 52, 48, 53, 51])},
        {"name": "C", "observations": obs([10, 11, 10.5, 12, 11, 12.5, 13])},
    ]


def test_correlation_matrix_symmetric_unit_diagonal():
    result = C.correlation_matrix(_named_series())
    matrix = result.detail["matrix"]
    assert result.detail["names"] == ["A", "B", "C"]
    for i in range(3):
        assert matrix[i][i] == pytest.approx(1.0)
        for j in range(3):
            assert matrix[i][j] == pytest.approx(matrix[j][i])
            assert -1.0 <= matrix[i][j] <= 1.0


def test_covariance_matrix_symmetric_and_matches_pairwise():
    result = C.covariance_matrix(_named_series())
    matrix = result.detail["matrix"]
    expected = C.covariance(_named_series()[0]["observations"], _named_series()[1]["observations"]).value
    assert matrix[0][1] == pytest.approx(expected)
    assert matrix[0][1] == pytest.approx(matrix[1][0])


def test_risk_contribution_components_sum_to_volatility():
    cov = [[0.04, 0.01, 0.0], [0.01, 0.09, 0.0], [0.0, 0.0, 0.16]]
    result = C.risk_contribution([0.5, 0.3, 0.2], cov, names=["A", "B", "C"])
    components = [c["value"] for c in result.detail["component"]]
    assert sum(components) == pytest.approx(result.value)
    assert sum(c["pctOfRisk"] for c in result.detail["component"]) == pytest.approx(1.0)


def test_risk_contribution_rejects_bad_matrix():
    with pytest.raises(C.CalculationError):
        C.risk_contribution([0.5, 0.5], [[1.0]])


# ── fundamentals additions ──────────────────────────────────────────────────────


def _fact(definition, value, *, currency="USD", period_type="fy"):
    return FinancialFact(
        fact_id=f"{definition}:{value}", metric=definition, definition=definition, value=value,
        currency=currency, period=FinancialPeriod(period_type=period_type),
        source="test", source_type="financial_database",
    )


def test_free_cash_flow_handles_negative_capex_without_double_counting():
    result = M.derive("free_cash_flow", [_fact("operating_cash_flow", 500.0), _fact("capex", -120.0)])
    assert result.value == pytest.approx(380.0)
    # A positive-magnitude capex gives the same answer.
    result2 = M.derive("free_cash_flow", [_fact("operating_cash_flow", 500.0), _fact("capex", 120.0)])
    assert result2.value == pytest.approx(380.0)


def test_enterprise_value_derive_uses_optional_components():
    facts = [
        _fact("market_cap", 1000.0, period_type="daily"),
        _fact("total_debt", 200.0),
        _fact("cash", 50.0),
    ]
    ev = M.derive("enterprise_value", facts, extra={"preferred_equity": 30.0, "minority_interest": 20.0})
    assert ev.value == pytest.approx(1200.0)


def test_enterprise_value_function_records_every_component():
    ev = M.enterprise_value(1000.0, total_debt=200.0, cash=50.0)
    names = {row["name"] for row in ev.inputs}
    assert {"market_cap", "total_debt", "preferred_equity", "minority_interest", "cash"} <= names
    assert ev.value == pytest.approx(1150.0)


def test_growth_kinds_and_cagr():
    c, p = _fact("revenue", 121.0), _fact("revenue", 100.0)
    assert M.growth(c, p, kind="yoy").value == pytest.approx(21.0)
    assert M.growth(c, p, kind="qoq").value == pytest.approx(21.0)
    assert M.growth(c, p, kind="cagr", years=2.0).value == pytest.approx(10.0, abs=1e-9)


def test_growth_refuses_zero_base_and_warns_on_negative_base():
    with pytest.raises(M.DerivationError):
        M.growth(_fact("revenue", 10.0), _fact("revenue", 0.0))
    negative = M.growth(_fact("net_income", 10.0), _fact("net_income", -20.0))
    assert negative.warnings


def test_cagr_requires_positive_values_and_span():
    with pytest.raises(M.DerivationError):
        M.growth(_fact("revenue", 10.0), _fact("revenue", -5.0), kind="cagr", years=1.0)
    with pytest.raises(M.DerivationError):
        M.growth(_fact("revenue", 10.0), _fact("revenue", 5.0), kind="cagr")


def test_fcff_and_fcfe():
    fcff = M.free_cash_flow_to_firm(ebit=200.0, tax_rate=0.25, depreciation_amortization=50.0, capex=80.0, change_working_capital=10.0)
    assert fcff.value == pytest.approx(110.0)
    fcfe = M.free_cash_flow_to_equity(fcff=110.0, interest_expense=20.0, tax_rate=0.25, net_borrowing=5.0)
    assert fcfe.value == pytest.approx(110.0 - 20.0 * 0.75 + 5.0)


def test_fcff_requires_valid_tax_rate():
    with pytest.raises(M.DerivationError):
        M.free_cash_flow_to_firm(ebit=100.0, tax_rate=1.5)


# ── valuation additions ─────────────────────────────────────────────────────────


def _dcf_inputs(**over):
    base = dict(free_cash_flows=(100.0, 110.0, 121.0), discount_rate=0.10, terminal_growth=0.03, net_debt=50.0, shares_outstanding=10.0)
    base.update(over)
    return V.DcfInputs(**base)


def test_dcf_schedule_detail_reconstructs_the_value():
    result = V.dcf_schedule(_dcf_inputs())
    schedule = result.detail["schedule"]
    assert len(schedule) == 3
    pv_explicit = sum(row["presentValue"] for row in schedule)
    assert result.detail["presentValueExplicit"] == pytest.approx(pv_explicit)
    assert result.detail["enterpriseValue"] == pytest.approx(
        result.detail["presentValueExplicit"] + result.detail["presentValueTerminal"]
    )


def test_dcf_sensitivity_marks_invalid_cells_none():
    result = V.dcf_sensitivity(_dcf_inputs(), discount_rates=[0.05, 0.12], terminal_growths=[0.03, 0.06])
    ev = result.detail["enterpriseValue"]
    # rate 0.05 with growth 0.06 is invalid -> None; every other cell is a number.
    assert ev[0][1] is None
    assert isinstance(ev[0][0], float) and isinstance(ev[1][1], float)


def test_dcf_sensitivity_default_grid_is_a_number_grid():
    result = V.dcf_sensitivity(_dcf_inputs())
    assert len(result.detail["discountRates"]) == 5
    assert len(result.detail["enterpriseValue"]) == 5


def test_dcf_scenarios_record_explicit_assumptions():
    scenarios = {
        "bear": {"discount_rate": 0.12, "free_cash_flows": (90.0, 95.0, 100.0)},
        "base": {},
        "bull": {"terminal_growth": 0.04, "free_cash_flows": (110.0, 125.0, 140.0)},
    }
    result = V.dcf_scenarios(_dcf_inputs(), scenarios)
    assert set(result.detail["scenarios"]) == {"bear", "base", "bull"}
    assert result.detail["scenarios"]["bear"]["assumptions"]["discountRate"] == pytest.approx(0.12)
    # Base must equal the standalone DCF.
    standalone = V.dcf(_dcf_inputs())
    assert result.detail["scenarios"]["base"]["valuePerShare"] == pytest.approx(standalone.value)


def test_dcf_scenarios_reject_unknown_fields():
    with pytest.raises(V.DerivationError):
        V.dcf_scenarios(_dcf_inputs(), {"bear": {"not_a_field": 1}})


# ── web_finance adapter ─────────────────────────────────────────────────────────


def test_compute_series_dispatches_new_metrics():
    assert WF.compute_series("cvar", obs(VALS))["metric"] == "cvar"
    assert WF.compute_series("correlation", obs(VALS), benchmark=obs(VALS))["value"] == pytest.approx(1.0)
    assert WF.compute_series("cumulative_return", obs(VALS))["value"] > 0
    rolling = WF.compute_series("rolling_volatility", obs(VALS), options={"window": 4})
    assert rolling["detail"]["window"] == 4


def test_compute_series_refuses_missing_benchmark():
    with pytest.raises(C.CalculationError):
        WF.compute_series("correlation", obs(VALS))


def test_compute_series_matrix_via_options():
    result = WF.compute_series("correlation_matrix", [], options={"series": _named_series()})
    assert result["value"] is None
    assert len(result["detail"]["matrix"]) == 3


def test_compute_growth_and_fcf_and_ev():
    assert WF.compute_growth(121.0, 100.0, kind="cagr", years=2.0)["value"] == pytest.approx(10.0, abs=1e-9)
    assert WF.compute_fcf("free_cash_flow", {"operating_cash_flow": 500.0, "capex": -120.0})["value"] == pytest.approx(380.0)
    assert WF.compute_enterprise_value({"market_cap": 1000.0, "total_debt": 200.0, "cash": 50.0})["value"] == pytest.approx(1150.0)


# ── high-level analysis planner ─────────────────────────────────────────────────


def test_security_analysis_composes_and_flags_unavailable():
    payload = {
        "priceObservations": obs(VALS),
        "benchmarkObservations": obs([100, 99, 101, 100, 99, 102, 101, 100, 103, 102]),
        "riskFreeRate": 0.02,
        "fundamentals": {"price": 110.0, "eps": 5.0, "market_cap": 1000.0, "total_debt": 200.0, "cash": 50.0},
    }
    result = FA.security_analysis(payload)
    assert result["status"] == "OK"
    assert result["sections"]["returns"]["annualizedReturn"]["status"] == "OK"
    assert result["sections"]["market"]["beta"]["status"] == "OK"
    assert result["sections"]["fundamentals"]["pe_ratio"]["status"] == "OK"
    # A ratio with no inputs is reported unavailable, never fabricated.
    assert result["sections"]["fundamentals"]["ps_ratio"]["status"] == "UNAVAILABLE"
    assert result["quality"]["state"] in ("PARTIAL", "DEGRADED", "GOOD", "COMPLETE")


def test_security_analysis_without_prices_is_honest():
    result = FA.security_analysis({"fundamentals": {"price": 10.0, "eps": 1.0}})
    assert result["sections"]["fundamentals"]["pe_ratio"]["status"] == "OK"
    assert any("priceObservations" in w for w in result["warnings"])


def test_portfolio_analysis_risk_contribution_and_concentration():
    payload = {
        "assets": [
            {"name": "A", "weight": 0.6, "observations": obs(VALS)},
            {"name": "B", "weight": 0.4, "observations": obs([50, 51, 49, 52, 48, 53, 51, 54, 52, 55])},
        ],
        "benchmarkObservations": obs([100, 99, 101, 100, 99, 102, 101, 100, 103, 102]),
        "riskFreeRate": 0.02,
    }
    result = FA.portfolio_analysis(payload)
    assert result["status"] == "OK"
    assert result["sections"]["risk"]["riskContribution"]["status"] == "OK"
    assert result["sections"]["concentration"]["herfindahlHirschmanIndex"] == pytest.approx(0.52)
    assert result["sections"]["market"]["beta"]["status"] == "OK"


def test_portfolio_analysis_rejects_zero_weights():
    result = FA.portfolio_analysis({"assets": [{"name": "A", "weight": 0.0, "observations": obs(VALS)}]})
    assert result["status"] == "ERROR"


# ── tool surface ────────────────────────────────────────────────────────────────


def _ctx():
    return ToolContext(run_id="r", log=lambda *_: None)


def test_register_research_engine_tools_includes_new_finance_tools():
    registry = ToolRegistry()
    added = WT.register_research_engine_tools(registry)
    for name in ("finance_growth", "finance_fcf", "finance_security_analysis", "finance_portfolio_analysis"):
        assert name in added
        assert registry.get(name) is not None


def test_finance_growth_tool():
    _text, data = asyncio.run(WT.finance_growth({"current": 121.0, "prior": 100.0, "kind": "cagr", "years": 2.0}, _ctx()))
    assert data["status"] == "OK"
    assert data["result"]["value"] == pytest.approx(10.0, abs=1e-9)


def test_finance_series_tool_reports_error_not_fabrication():
    _text, data = asyncio.run(WT.finance_series({"metric": "sharpe", "observations": obs(VALS)}, _ctx()))
    assert data["status"] == "UNAVAILABLE"
    assert "risk_free_rate" in data["error"]


def test_finance_valuation_sensitivity_tool():
    _text, data = asyncio.run(WT.finance_valuation({
        "kind": "dcf_sensitivity",
        "inputs": {"free_cash_flows": [100.0, 110.0, 121.0], "discount_rate": 0.10, "terminal_growth": 0.03},
        "discount_rates": [0.09, 0.11],
        "terminal_growths": [0.02, 0.04],
    }, _ctx()))
    assert data["status"] == "OK"
    assert len(data["result"]["detail"]["enterpriseValue"]) == 2


def test_finance_security_analysis_tool():
    _text, data = asyncio.run(WT.finance_security_analysis({"payload": {
        "priceObservations": obs(VALS), "riskFreeRate": 0.02,
    }}, _ctx()))
    assert data["status"] == "OK"
    assert data["result"]["sections"]["risk"]["sharpe"]["status"] == "OK"


def test_finance_portfolio_analysis_tool():
    _text, data = asyncio.run(WT.finance_portfolio_analysis({"payload": {
        "assets": [
            {"name": "A", "weight": 0.5, "observations": obs(VALS)},
            {"name": "B", "weight": 0.5, "observations": obs([50, 51, 49, 52, 48, 53, 51, 54, 52, 55])},
        ],
    }}, _ctx()))
    assert data["status"] == "OK"
    assert data["result"]["sections"]["risk"]["portfolioVolatility"]["status"] == "OK"
