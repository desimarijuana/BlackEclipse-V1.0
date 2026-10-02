"""Universal Financial Data Accuracy — point-in-time, research router and
corporate-action ingestion (§15/§17/§24). Rules, not tickers. All synthetic.
"""

from __future__ import annotations

from harness.finance_facts import corporate_actions as ca
from harness.finance_facts import point_in_time as pit
from harness.finance_facts import router
from harness.finance_facts.model import FinancialFact, FinancialPeriod


def _fact(metric, value, *, period_end="2025-12-31", pub=None, retrieved=None, revision=None):
    return FinancialFact(
        fact_id=f"{metric}:{period_end}:{pub or revision or 'x'}",
        metric=metric, definition=metric, value=value, currency="USD", unit="USD",
        entity_id="US:X",
        period=FinancialPeriod(period_type="fy", period_end=period_end, fiscal_year=2025),
        publication_timestamp=pub, retrieved_timestamp=retrieved,
    )


# ── §15: point-in-time / known-at ──────────────────────────────────────────────


def test_a_later_report_is_not_admissible_at_an_earlier_cutoff():
    # FY2025 report published Feb 2026 must not be used for a Dec 2025 cutoff.
    report = _fact("revenue", 100.0, pub="2026-02-11T00:00:00Z")
    assert not pit.is_admissible_at(report, "2025-12-31T00:00:00Z")
    assert pit.is_admissible_at(report, "2026-03-01T00:00:00Z")


def test_a_fact_with_no_known_time_is_refused_under_a_cutoff():
    unknown = _fact("revenue", 100.0)
    assert not pit.is_admissible_at(unknown, "2025-12-31T00:00:00Z")
    assert pit.is_admissible_at(unknown, None)


def test_latest_known_returns_the_revision_available_at_the_cutoff():
    original = _fact("revenue", 100.0, pub="2025-06-01T00:00:00Z", revision="o")
    restated = _fact("revenue", 110.0, pub="2026-03-01T00:00:00Z", revision="r")
    # As of Dec 2025 only the original was known.
    known = pit.latest_known_per_metric([original, restated], "2025-12-31T00:00:00Z")
    assert known["revenue"].value == 100.0
    # Today the restated value is known.
    now = pit.latest_known_per_metric([original, restated], "2026-06-01T00:00:00Z")
    assert now["revenue"].value == 110.0


# ── §24: research router ───────────────────────────────────────────────────────


def test_health_question_routes_to_a_broad_evidence_set():
    plan = router.route("Is this company financially healthy?")
    assert plan.intent == "health"
    for area in ("revenue_growth", "profitability", "debt", "cash_flow"):
        assert area in plan.evidence


def test_a_bank_question_adds_sector_metrics():
    plan = router.route("How profitable is the bank?", sector="bank", contains_financial=True)
    assert "net_income_parent" in plan.evidence or "margins" in plan.evidence
    assert "cet1" in plan.evidence or "nim" in plan.evidence
    assert plan.financial_framework


def test_a_debt_question_asks_for_all_debt_definitions():
    plan = router.route("How much debt does it have?")
    assert plan.intent == "debt"
    for area in ("gross_debt", "net_debt", "financial_debt", "lease_liabilities"):
        assert area in plan.evidence


def test_an_unknown_question_gets_a_broad_default_not_a_guess():
    plan = router.route("Tell me something arbitrary.")
    assert plan.intent == "general"
    assert plan.evidence  # the broad default, never empty


# ── §17: corporate-action ingestion ────────────────────────────────────────────


def test_split_and_dividend_are_extracted_from_a_price_series():
    rows = [
        {"date": "2026-01-02", "close": 100.0},
        {"date": "2026-03-01", "close": 50.0, "split": 2.0},
        {"date": "2026-05-01", "close": 51.0, "dividend": 0.5},
    ]
    actions = ca.extract_from_series(rows)
    kinds = {a.kind for a in actions}
    assert "split" in kinds and "dividend" in kinds
    split = next(a for a in actions if a.kind == "split")
    assert split.ratio == 2.0 and split.effective_date == "2026-03-01"


def test_a_reverse_split_is_labelled_as_such():
    actions = ca.extract_from_series([{"date": "2026-01-01", "split": 0.2}])
    assert actions[0].kind == "reverse_split"


def test_no_actions_in_a_plain_series():
    actions = ca.extract_from_series([{"date": "2026-01-01", "close": 10.0}])
    assert actions == []
