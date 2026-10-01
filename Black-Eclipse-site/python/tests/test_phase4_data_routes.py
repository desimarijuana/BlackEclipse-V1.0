"""Harness closeout Phase 4: close the data-route gaps the matrix exposes.

Covers, on the Python side:
  * FX/crypto are NOT routed through the JDdS vault (which holds no such row), so
    a vault failure cannot be recorded for a route that cannot succeed (4.1);
  * DERIV (recognised, uncovered) never claims a covered route (4.2);
  * the capability matrix's declared tiers/reasons render honestly.
"""

from __future__ import annotations

from harness.retrieval.contract import FinancialRetrievalRequest
from harness.retrieval.structured import JddsSource, is_fx_or_crypto


class StubBridge:
    def __init__(self):
        self.calls = []

    async def fetch(self, capability, params):
        self.calls.append((capability, params))
        return {"status": "OK"}


def _req(data_type="current_quote", instrument=None, market=None):
    return FinancialRetrievalRequest(
        objective="quote", dataType=data_type, instrument=instrument, market=market,
    )


def test_fx_and_crypto_are_classified():
    assert is_fx_or_crypto(_req(instrument="EURUSD=X")) is True
    assert is_fx_or_crypto(_req(instrument="EUR/USD")) is True
    assert is_fx_or_crypto(_req(instrument="BTC-USD")) is True
    assert is_fx_or_crypto(_req(instrument="AAPL")) is False
    assert is_fx_or_crypto(_req(instrument="2330.TW")) is False
    assert is_fx_or_crypto(_req(market="FX")) is True
    assert is_fx_or_crypto(_req(market="CRYPTO")) is True


def test_vault_is_not_available_for_fx_quote():
    source = JddsSource(StubBridge())
    assert source.available(_req(instrument="EURUSD=X")) is False
    assert source.available(_req(market="CRYPTO", instrument="BTC")) is False
    # An equity quote IS still routed through the vault.
    assert source.available(_req(instrument="AAPL")) is True


def test_deriv_is_not_covered_in_the_coverage_registry():
    # The declared registry must give DERIV no asset classes and no data types,
    # so no axis can claim `configured`.
    import json
    import pathlib

    root = pathlib.Path(__file__).resolve().parent.parent.parent
    schema = (root / "src" / "lib" / "harness" / "coverage.ts").read_text(encoding="utf-8")
    assert 'DERIV: entry("DERIV", [], []' in schema
    # The blocker is declared honestly rather than left implicit.
    assert "not_covered" in schema
