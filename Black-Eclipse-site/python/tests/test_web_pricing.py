"""Provider cost estimation honesty.

An unpriced provider is UNKNOWN, never 0; the keyless providers are genuinely
free (0.0). The budget is enforced only when every used provider is priced.
"""

from __future__ import annotations

import os

from harness.research.web_pricing import CostLedger, price_for


def test_free_providers_are_zero_known():
    for name in ("duckduckgo-html", "openalex", "gdelt", "mojeek", "crossref"):
        price = price_for(name)
        assert price.known is True
        assert price.per_query == 0.0


def test_unpriced_provider_is_unknown_not_zero():
    os.environ.pop("HARNESS_WEB_PRICE_TAVILY_QUERY", None)
    price = price_for("tavily")
    assert price.known is False
    assert price.per_query is None


def test_configured_price_is_used(monkeypatch):
    monkeypatch.setenv("HARNESS_WEB_PRICE_TAVILY_QUERY", "0.008")
    price = price_for("tavily")
    assert price.known is True
    assert price.per_query == 0.008


def test_ledger_flags_unknown_totals_as_inexact(monkeypatch):
    monkeypatch.delenv("HARNESS_WEB_PRICE_TAVILY_QUERY", raising=False)
    ledger = CostLedger()
    ledger.record("tavily", kind="query")  # unpriced
    ledger.record("duckduckgo-html", kind="query")  # free
    snap = ledger.snapshot()
    assert snap["estimatedCost"] == 0.0
    assert snap["exact"] is False
    assert "tavily" in snap["unknownProviders"]


def test_ledger_is_exact_when_all_priced(monkeypatch):
    monkeypatch.setenv("HARNESS_WEB_PRICE_TAVILY_QUERY", "0.01")
    ledger = CostLedger()
    ledger.record("tavily", kind="query", count=3)
    snap = ledger.snapshot()
    assert snap["estimatedCost"] == 0.03
    assert snap["exact"] is True
    assert snap["byProvider"]["tavily"] == 0.03
