"""The closed-form finance calculator must match the evaluation grader.

`finance_calc` is the runtime surface the agent is told to use for arithmetic.
The grader independently computes the expected value. If the two formulas drift,
one of them is wrong; this test fails loudly instead of letting a benchmark pass
or fail on a different formula than the user saw.
"""

from __future__ import annotations

import pytest

from harness.evaluation.graders.financial import compute_expected
from harness.research import web_finance
from harness.research.web_tools import finance_calc

CASES = [
    ("percentage_change", {"start": 120, "end": 96}, -20.0),
    ("percentage_change", {"start": 100, "end": 110}, 10.0),
    ("return", {"start": 80, "end": 60}, -25.0),
    ("eps", {"net_income": 500, "shares": 100}, 5.0),
    ("pe", {"price": 84, "eps": 6}, 14.0),
    ("ps", {"price": 84, "sales_per_share": 6}, 14.0),
    ("position_size", {"reward": 6, "risk": 2}, 3.0),
    ("gross_margin", {"gross_profit": 40, "revenue": 100}, 40.0),
    ("net_margin", {"net_income": 20, "revenue": 100}, 20.0),
    ("cagr", {"start": 100, "end": 121, "years": 2}, 10.0),
    ("fcf", {"operating_cash_flow": 50, "capex": 20}, 30.0),
]


@pytest.mark.parametrize("metric,inputs,expected", CASES)
def test_the_calculator_matches_the_grader(metric, inputs, expected):
    result = web_finance.compute_simple(metric, inputs)
    assert result["value"] == pytest.approx(expected, rel=1e-9, abs=1e-9)
    grader = compute_expected(metric, inputs)
    assert result["value"] == pytest.approx(grader["value"], rel=1e-9, abs=1e-9)
    assert result["formula"] == web_finance.SIMPLE_FORMULAS[metric][0]


@pytest.mark.asyncio
async def test_the_tool_reports_the_signed_value_verbatim():
    text, payload = await finance_calc(
        {"metric": "percentage_change", "inputs": {"start": 120, "end": 96}}, None
    )
    assert payload["status"] == "OK"
    assert "-20" in text
    assert "verbatim" in text
    assert payload["result"]["value"] == pytest.approx(-20.0)


@pytest.mark.asyncio
async def test_the_tool_refuses_a_missing_input_instead_of_guessing():
    text, payload = await finance_calc(
        {"metric": "eps", "inputs": {"net_income": 500}}, None
    )
    assert payload["status"] == "UNAVAILABLE"
    assert "shares" in text


def test_an_unknown_metric_is_refused():
    with pytest.raises(ValueError, match="unknown metric"):
        web_finance.compute_simple("not_a_metric", {})


def test_a_zero_denominator_is_refused():
    with pytest.raises(ValueError, match="zero"):
        web_finance.compute_simple("position_size", {"reward": 6, "risk": 0})
