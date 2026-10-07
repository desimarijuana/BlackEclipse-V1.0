"""Tests for the deterministic financial metrics + research-quality score.

Covers the ratio/margin/return metrics (`finance_facts.metrics`), the risk
time-series metrics (`research.calculations`), WACC/DCF valuation
(`finance_facts.valuation`), the tool adapters (`research.web_finance`) and the
internal quality score (`research.web_quality`).

The through-line: a metric whose required input is missing is REFUSED, never
defaulted; every result carries its formula + inputs; an estimate is labelled.
"""

from __future__ import annotations

import math

import pytest

from harness.finance_facts.metrics import SPECS, DerivationError, derive
from harness.finance_facts.model import FinancialFact, FinancialPeriod
from harness.finance_facts.valuation import DcfInputs, WaccInputs, dcf, wacc
from harness.research import calculations as C
from harness.research.web_quality import WEIGHTS, compute_quality


def _fact(definition: str, value, *, currency="USD", period_type="fy") -> FinancialFact:
    return FinancialFact(
        fact_id=f"{definition}:{value}", metric=definition, definition=definition, value=value,
        currency=currency, period=FinancialPeriod(period_type=period_type),
        source="test", source_type="financial_database",
    )


# ── ratio metrics ───────────────────────────────────────────────────────────────


def test_pe_ratio_and_forward_pe():
    pe = derive("pe_ratio", [_fact("price", 180, period_type="daily"), _fact("eps", 4.5)])
    assert pe.value == pytest.approx(40.0)
    fpe = derive("forward_pe", [_fact("price", 180, period_type="daily"), _fact("eps_forward", 5.0)])
    assert fpe.value == pytest.approx(36.0)


def test_pe_undefined_on_negative_eps():
    with pytest.raises(DerivationError):
        derive("pe_ratio", [_fact("price", 10, period_type="daily"), _fact("eps", -1.0)])


def test_peg_ratio_needs_growth():
    peg = derive("peg_ratio", [_fact("price", 100, period_type="daily"), _fact("eps", 2.0)], extra={"eps_growth": 25.0})
    # (100/2)/25 = 50/25 = 2.0
    assert peg.value == pytest.approx(2.0)
    with pytest.raises(DerivationError):
        derive("peg_ratio", [_fact("price", 100, period_type="daily"), _fact("eps", 2.0)])  # no growth


def test_ev_ebitda_and_margins():
    # market_cap is a point-in-time MARKET input (period-exempt); net_debt and
    # ebitda are both annual flow inputs, so they share a period type.
    ev = derive("ev_ebitda", [
        _fact("market_cap", 3e12, period_type="daily"), _fact("net_debt", 1e10), _fact("ebitda", 1.2e11),
    ])
    assert ev.value == pytest.approx((3e12 + 1e10) / 1.2e11)
    gm = derive("gross_margin", [_fact("gross_profit", 100), _fact("revenue", 400)])
    assert gm.value == pytest.approx(25.0) and gm.unit == "%"
    om = derive("operating_margin", [_fact("operating_income", 80), _fact("revenue", 400)])
    assert om.value == pytest.approx(20.0)


def test_roic_requires_tax_rate_never_defaulted():
    with pytest.raises(DerivationError):
        derive("roic", [_fact("operating_income", 8e10), _fact("invested_capital", 3e11)])
    roic = derive("roic", [_fact("operating_income", 8e10), _fact("invested_capital", 3e11)], extra={"tax_rate": 0.15})
    assert roic.value == pytest.approx(8e10 * 0.85 / 3e11 * 100.0)


def test_metric_refuses_missing_input_not_defaulted():
    with pytest.raises(DerivationError):
        derive("ev_ebitda", [_fact("market_cap", 1e9, period_type="daily")])  # no ebitda/net_debt


def test_fcf_yield_uses_point_in_time_market_cap():
    fcf = derive("fcf_yield", [_fact("free_cash_flow", 1e10), _fact("market_cap", 2e11, period_type="daily")])
    assert fcf.value == pytest.approx(5.0) and fcf.unit == "%"


# ── risk time-series metrics ────────────────────────────────────────────────────


def _series(values: list[float]) -> list[dict]:
    return [{"date": f"2024-01-{i + 1:02d}", "value": v} for i, v in enumerate(values)]


def test_sortino_and_var_and_beta():
    vals = [100, 102, 99, 103, 98, 105, 101, 107, 104, 110]
    s = C.sortino(_series(vals), frequency="daily")
    assert isinstance(s.value, float) and s.value > 0
    var = C.value_at_risk(_series(vals), confidence=0.95)
    assert var.value > 0  # VaR is reported as a positive loss
    # A benchmark that is an exact positive multiple of the asset has IDENTICAL
    # returns, so its beta against the asset is exactly 1.
    bench = [{"date": f"2024-01-{i + 1:02d}", "value": v * 2.0} for i, v in enumerate(vals)]
    b = C.beta(_series(vals), bench, frequency="daily")
    assert b.value == pytest.approx(1.0, rel=1e-9)


def test_sortino_undefined_when_monotonic_up():
    with pytest.raises(C.CalculationError):
        C.sortino(_series([1, 2, 3, 4, 5]), frequency="daily")


def test_var_rejects_bad_confidence():
    with pytest.raises(C.CalculationError):
        C.value_at_risk(_series([1, 2, 3, 4, 5, 6]), confidence=1.5)


def test_beta_requires_aligned_series():
    with pytest.raises(C.CalculationError):
        C.beta(_series([1, 2, 3, 4]), _series([1, 2, 3, 4, 5]), frequency="daily")


def test_calculators_include_new_metrics():
    for name in ("sortino", "value_at_risk", "beta"):
        assert name in C.CALCULATORS


# ── WACC / DCF ─────────────────────────────────────────────────────────────────


def test_wacc_all_equity_reduces_to_capm():
    w = wacc(WaccInputs(market_cap=1e9, total_debt=0.0, risk_free_rate=0.04, beta=1.2, equity_risk_premium=0.05))
    assert w.value == pytest.approx((0.04 + 1.2 * 0.05) * 100.0)
    assert any("no debt" in note for note in w.warnings)


def test_wacc_requires_debt_inputs():
    with pytest.raises(DerivationError):
        wacc(WaccInputs(market_cap=1e9, total_debt=5e8, risk_free_rate=0.04, beta=1.2, equity_risk_premium=0.05))


def test_wacc_levered():
    w = wacc(WaccInputs(market_cap=3e12, total_debt=1e10, risk_free_rate=0.04, beta=1.7,
                        equity_risk_premium=0.05, cost_of_debt=0.045, tax_rate=0.15))
    e, d = 3e12, 1e10
    v = e + d
    expected = (e / v) * (0.04 + 1.7 * 0.05) + (d / v) * 0.045 * 0.85
    assert w.value == pytest.approx(expected * 100.0)


def test_dcf_gordon_growth_per_share():
    d = dcf(DcfInputs(free_cash_flows=(5e10, 6e10, 7e10, 8e10, 9e10), discount_rate=0.10,
                      terminal_growth=0.03, net_debt=-2e10, shares_outstanding=2.45e10))
    assert d.metric == "dcf_equity_value_per_share"
    assert d.value > 0
    assert any("ESTIMATE" in w for w in d.warnings)


def test_dcf_requires_exactly_one_terminal_method():
    with pytest.raises(DerivationError):
        dcf(DcfInputs(free_cash_flows=(5e10,), discount_rate=0.1))
    with pytest.raises(DerivationError):
        dcf(DcfInputs(free_cash_flows=(5e10,), discount_rate=0.1, terminal_growth=0.03, exit_multiple=20, terminal_metric=1e10))


def test_dcf_rejects_terminal_growth_above_discount():
    with pytest.raises(DerivationError):
        dcf(DcfInputs(free_cash_flows=(5e10,), discount_rate=0.05, terminal_growth=0.06))


def test_dcf_exit_multiple():
    d = dcf(DcfInputs(free_cash_flows=(5e10, 6e10), discount_rate=0.10, exit_multiple=25, terminal_metric=1e11))
    assert d.value > 0


# ── quality score ────────────────────────────────────────────────────────────────


class _Ev:
    def __init__(self, fresh=True):
        self._fresh = fresh


class _Claim:
    def __init__(self, status="SUPPORTED", kind="FACT"):
        self.status = status
        self.kind = kind


class _Conflict:
    def __init__(self, status="UNRESOLVED", material=True):
        self.status = status
        self.material = material


def test_quality_weights_sum_to_one():
    assert math.isclose(sum(WEIGHTS.values()), 1.0, abs_tol=1e-9)


def test_quality_high_when_everything_is_strong():
    coverage = {"status": "COMPLETE", "unmet": [], "answeredQuestions": 4, "questionsTotal": 4}
    sources = [{"sourceType": "official_filing"}, {"sourceType": "investor_relations"}]
    quality = compute_quality(
        coverage=coverage, sources=sources, evidence=[_Ev()], claims=[_Claim(), _Claim("CALCULATED")],
        conflicts=[_Conflict("EXPLAINED", material=False)],
        citation_report={"ok": True, "coverage": 1.0},
    )
    assert quality["score"] >= 0.8
    assert quality["band"] == "HIGH"
    assert quality["verdict"] == "COMPLETE"


def test_quality_low_and_needs_more_when_weak():
    coverage = {"status": "NEEDS_MORE_RESEARCH", "unmet": ["no evidence"], "answeredQuestions": 0, "questionsTotal": 5}
    quality = compute_quality(
        coverage=coverage, sources=[{"sourceType": "blog"}], evidence=[],
        claims=[_Claim("UNSUPPORTED")], conflicts=[_Conflict("UNRESOLVED", material=True)],
        citation_report={"ok": False, "coverage": 0.0},
    )
    assert quality["score"] < 0.4
    assert quality["verdict"] == "NEEDS_MORE_RESEARCH"


def test_quality_is_explainable_with_full_attribution():
    quality = compute_quality(
        coverage={"status": "PARTIAL", "unmet": [], "answeredQuestions": 2, "questionsTotal": 4},
        sources=[{"sourceType": "news"}], evidence=[_Ev()], claims=[_Claim()],
        conflicts=[], citation_report={"ok": True, "coverage": 0.5},
    )
    assert set(quality["components"]) == set(WEIGHTS)
    assert set(quality["contributions"]) == set(WEIGHTS)
    assert "not a measure of truth" in quality["disclaimer"]
