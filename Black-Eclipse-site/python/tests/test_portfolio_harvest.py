"""Tax-loss harvest candidates — deterministic, honest, proposal-only."""

from __future__ import annotations

from harness.portfolio.harvest import harvest_candidates
from harness.portfolio.tools import PORTFOLIO_READ_TOOLS


POSITIONS = [
    {"symbol": "AAPL", "unrealizedPnlBase": "-1500.00", "weight": 30.0,
     "quantity": "10", "currency": "USD"},
    {"symbol": "MSFT", "unrealizedPnlBase": "500.00", "weight": 40.0,
     "quantity": "5", "currency": "USD"},
    {"symbol": "TSLA", "unrealizedPnlBase": "-400.00", "weight": 20.0,
     "quantity": "2", "currency": "USD"},
    {"symbol": "NVDA", "unrealizedPnlBase": None, "weight": None,
     "quantity": "1", "currency": "USD"},
]


def test_only_losses_beyond_threshold_are_candidates():
    result = harvest_candidates(POSITIONS, threshold=1000)
    assert result["count"] == 1
    assert result["candidates"][0]["symbol"] == "AAPL"
    assert result["candidates"][0]["unrealizedPnl"] == -1500.0


def test_candidates_are_ordered_worst_loss_first():
    result = harvest_candidates(POSITIONS, threshold=100)
    symbols = [c["symbol"] for c in result["candidates"]]
    assert symbols == ["AAPL", "TSLA"]


def test_an_unpriced_position_is_skipped_not_treated_as_zero():
    result = harvest_candidates(POSITIONS, threshold=100)
    assert all(c["symbol"] != "NVDA" for c in result["candidates"])


def test_result_is_explicitly_proposal_only_with_the_wash_sale_caveat():
    result = harvest_candidates(POSITIONS, threshold=1000)
    assert result["proposalOnly"] is True
    assert "wash-sale" in result["note"].lower()


def test_limit_caps_the_candidate_list():
    result = harvest_candidates(POSITIONS, threshold=100, limit=1)
    assert result["count"] == 1


def test_the_harvest_tool_is_a_registered_read_tool():
    assert "portfolio_harvest_candidates" in PORTFOLIO_READ_TOOLS
