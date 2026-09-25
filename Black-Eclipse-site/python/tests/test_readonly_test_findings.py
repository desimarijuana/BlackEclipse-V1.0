"""Regression tests for the read-only-test findings (Issues 4, 5, 6).

  * Issue 6 — memory search `None` conversion: ranking a memory whose
    importance/confidence is NULL must not raise.
  * Issue 5 — web/news duplication: the same article (differing only by tracking
    params) must collapse to one evidence item.
  * Issue 5 — evidence count vs shown list: the tool summary must state the true
    total when the list is bounded.
  * Issue 4 — periodic data freshness: a within-cadence statement is delayed, not
    stale, while a price keeps its strict window.
"""

from __future__ import annotations

import asyncio
import datetime as dt

from harness.eclipse_memory.retrieval import _score
from harness.retrieval.policies import cadence_for
from harness.retrieval.web import WebResearchSource, _normalize_url_for_dedup
from harness.retrieval.validate import validate_objects
from harness.retrieval.contract import NormalizedFinancialObject, SourceReference


# ── Issue 6: memory ranking with NULL importance/confidence ─────────────────


def test_score_tolerates_null_importance_and_confidence():
    # The store columns are NOT NULL, but `_score` is also called on
    # suggestion/partial dicts, so it must not raise if a value is absent.
    memory = {
        "id": "m1",
        "content": "prefers concise answers",
        "subject": None,
        "importance": None,
        "confidence": None,
        "verification": "unverified",
        "accessCount": None,
    }
    # Must not raise "unsupported format string passed to NoneType.__format__".
    score, reasons = _score(memory, ["concise"], None)
    assert score >= 0
    assert any("importance" in r for r in reasons)


# ── Issue 5: web dedup ───────────────────────────────────────────────────────


def test_url_dedup_collapses_tracking_variants():
    a = "https://example.com/article?id=7&utm_source=news&utm_medium=email"
    b = "https://example.com/article?id=7&gclid=abc"
    c = "https://example.com/article?id=8"
    assert _normalize_url_for_dedup(a) == _normalize_url_for_dedup(b)
    assert _normalize_url_for_dedup(a) != _normalize_url_for_dedup(c)


def test_web_evidence_deduplicates_same_article():
    class FakeBridge:
        async def fetch(self, capability, params):
            if capability == "web_search":
                return {
                    "status": "OK",
                    "results": [
                        {"url": "https://a.com/story?utm_source=x", "title": "A", "snippet": "s1"},
                        {"url": "https://a.com/story?gclid=y", "title": "A", "snippet": "s1"},
                        {"url": "https://b.com/story", "title": "B", "snippet": "s2"},
                    ],
                }
            return {"status": "UNAVAILABLE"}

    from harness.retrieval.contract import FinancialRetrievalRequest

    source = WebResearchSource(FakeBridge())
    request = FinancialRetrievalRequest(objective="news", dataType="news", query="news", allowWeb=True)
    outcome = asyncio.run(source.retrieve(request))
    # Two distinct URLs → two evidence items (the duplicate collapsed).
    assert len(outcome.evidence) == 2


# ── Issue 5: evidence count vs shown list ───────────────────────────────────


def test_landing_pages_rank_below_real_articles():
    # Issue 5: a brokerage quote/landing page must not outrank a real article.
    from harness.retrieval.web import _looks_like_landing_page

    assert _looks_like_landing_page("https://www.interactivebrokers.com/en/home.php", "www.interactivebrokers.com")
    assert _looks_like_landing_page("https://x.com/quote/AAPL", "x.com")
    assert not _looks_like_landing_page("https://reuters.com/news/apple-earnings", "reuters.com")

    ranked = WebResearchSource._rank([
        {"url": "https://www.interactivebrokers.com/en/home.php", "title": "landing"},
        {"url": "https://reuters.com/news/aapl", "title": "real"},
    ])
    assert ranked[0]["title"] == "real"


def test_summary_states_total_when_list_bounded():
    from harness.retrieval_tools import _summarize

    class Result:
        status = "OK"
        dataType = "news"
        strategy = ["WEB"]
        freshness = "intraday"
        quality = "valid"
        identity = None
        cached = False
        data = None
        retrievedAt = "2026-09-24T00:00:00Z"
        warnings: list = []

        def __init__(self, n):
            self.evidence = [_ev(i) for i in range(n)]

    def _ev(i):
        obj = NormalizedFinancialObject(name="x", value="v", source=SourceReference(source="web"))
        from harness.retrieval.contract import EvidenceItem

        return EvidenceItem(id=f"e{i}", kind="web", summary=f"item {i}", objects=[obj], source=SourceReference(source="web"))

    text = _summarize(Result(9))
    # 6 shown of 9, and the total is stated.
    assert "6 of 9 shown" in text
    assert "3 more evidence item(s) not shown" in text


# ── Issue 4: periodic cadence ───────────────────────────────────────────────


def test_statements_have_a_periodic_cadence_and_prices_do_not():
    assert cadence_for("financial_statements") is not None
    assert cadence_for("current_quote") is None
    assert cadence_for("historical_prices") is None


def test_annual_statement_within_cadence_is_not_stale():
    # Newest observation ~362 days old; freshness "slow" (7 days) but the annual
    # cadence covers it → delayed, not a staleness warning.
    newest = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=362)).isoformat()
    obj = NormalizedFinancialObject(
        name="revenue", value=1000, dataTimestamp=newest, source=SourceReference(source="sec")
    )
    _, warnings = validate_objects(
        [obj], "slow", source_cadence_seconds=cadence_for("financial_statements")
    )
    assert not any("stale" in w for w in warnings)


def test_price_beyond_its_window_is_still_stale():
    old = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=3)).isoformat()
    obj = NormalizedFinancialObject(
        name="price", value=10, dataTimestamp=old, source=SourceReference(source="scraper")
    )
    _, warnings = validate_objects([obj], "realtime", source_cadence_seconds=None)
    assert any("stale" in w for w in warnings)
