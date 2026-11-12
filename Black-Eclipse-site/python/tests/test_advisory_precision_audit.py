"""Precision regressions for the Fiduciary Gate.

The audit found two false positives on pure arithmetic answers. The fix must not
simply disable the gate: a directive with a resolved ticker, or with a numeric
target in a position/portfolio context, is still a claim.
"""

from __future__ import annotations

from harness.advisory.claims import extract_claims


def test_dcf_metric_prose_is_not_advice():
    text = (
        "The terminal value is 72% of enterprise value. Exit FCFF to 3% in the "
        "sensitivity grid and add PV of the terminal value."
    )
    assert extract_claims(text) == []


def test_ml_metric_prose_is_not_advice():
    text = (
        "Add ADV to the feature set, then compare the AUC. Trim the feature "
        "count to 120 to reduce variance."
    )
    assert extract_claims(text) == []


def test_number_only_claim_needs_position_context():
    assert extract_claims("Trim 5% to reduce risk.") == []
    claims = extract_claims("Trim the position by 5% to reduce risk.")
    assert len(claims) == 1
    assert claims[0].action == "trim"


def test_ticker_claim_still_fires():
    claims = extract_claims("Sell AAPL here.")
    assert len(claims) == 1
    assert claims[0].symbols == ("AAPL",)


def test_portfolio_weight_claim_still_fires():
    claims = extract_claims("Reduce the portfolio weight to 10%.")
    assert len(claims) == 1
    assert claims[0].action == "reduce"
    assert claims[0].values == (10.0,)
