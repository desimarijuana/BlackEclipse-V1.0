"""Evidence release gate — deterministic citation integrity at the answer seam.

The gate checks an ordinary run's final answer against the sources the run
ACTUALLY retrieved, and discloses any cited link with no runtime provenance.
These tests exercise the pure gate and the SourceCollector accessor it reads.
"""

from __future__ import annotations

from harness.research.release_gate import (
    CitationIntegrity,
    enforce_evidence_answer,
    extract_urls,
)
from harness.source_collector import SourceCollector

SEC_URL = "https://www.sec.gov/Archives/edgar/data/320193/0000320193-24-000123/x.htm"


def _collector_with_web(url: str, *, ok: bool = True) -> SourceCollector:
    collector = SourceCollector()
    collector.add_web_source(url=url, title="filing", tier="primary", ok=ok)
    return collector


# ── extraction ───────────────────────────────────────────────────────────────


def test_extract_urls_reads_markdown_and_bare_and_dedupes():
    text = "See [10-K](https://www.sec.gov/a) and https://www.sec.gov/a plus http://x/y."
    assert extract_urls(text) == ["https://www.sec.gov/a", "http://x/y"]


def test_extract_urls_strips_trailing_punctuation():
    assert extract_urls("fetch https://example.com/report).") == ["https://example.com/report"]


# ── no citations ─────────────────────────────────────────────────────────────


def test_no_citations_is_a_noop():
    verdict = enforce_evidence_answer("AAPL trades at 237.42.", SourceCollector())
    assert verdict.status == "no_citations"
    assert verdict.disclosure is None
    assert verdict.released is True


def test_private_and_localhost_urls_are_not_checked():
    verdict = enforce_evidence_answer(
        "The app runs at http://localhost:3000 and http://192.168.1.5/x",
        _collector_with_web(SEC_URL),
    )
    assert verdict.status == "no_citations"


# ── verified ─────────────────────────────────────────────────────────────────


def test_exact_retrieved_url_is_verified():
    verdict = enforce_evidence_answer(f"Revenue rose. Source: {SEC_URL}", _collector_with_web(SEC_URL))
    assert verdict.status == "ok"
    assert verdict.verified == 1
    assert verdict.disclosure is None


def test_same_host_different_path_is_domain_known_not_flagged():
    collector = _collector_with_web("https://www.reuters.com/markets/apple-q4")
    verdict = enforce_evidence_answer("See https://reuters.com/other-path", collector)
    assert verdict.status == "ok"
    assert verdict.domainKnown == 1
    assert verdict.unverified == []


def test_consulted_but_failed_route_is_not_flagged_as_invented():
    # A failed fetch is not evidence, but mentioning it is not an invented link.
    collector = _collector_with_web("https://www.sec.gov/x", ok=False)
    verdict = enforce_evidence_answer("See https://www.sec.gov/x", collector)
    assert verdict.status == "ok"
    assert verdict.unverified == []


# ── unverified / fabricated ───────────────────────────────────────────────────


def test_unretrieved_url_is_flagged_with_a_disclosure():
    collector = _collector_with_web(SEC_URL)
    verdict = enforce_evidence_answer("See https://totally-made-up.example/report", collector)
    assert verdict.status == "unverified"
    assert verdict.unverified == ["https://totally-made-up.example/report"]
    assert "totally-made-up.example" in (verdict.disclosure or "")
    assert "unverified" in (verdict.disclosure or "").lower()
    assert verdict.released is False


def test_citation_with_zero_retrieved_evidence_is_unverifiable():
    verdict = enforce_evidence_answer("Per https://news.example/story, earnings beat.", SourceCollector())
    assert verdict.status == "no_evidence"
    assert verdict.unverified == ["https://news.example/story"]
    assert verdict.disclosure is not None


def test_a_mixed_answer_flags_only_the_unretrieved_link():
    collector = _collector_with_web(SEC_URL)
    answer = f"Per {SEC_URL} and https://fake.example/z, revenue rose."
    verdict = enforce_evidence_answer(answer, collector)
    assert verdict.status == "unverified"
    assert verdict.unverified == ["https://fake.example/z"]
    assert verdict.verified == 1


def test_user_supplied_url_is_admissible():
    collector = _collector_with_web(SEC_URL)
    verdict = enforce_evidence_answer(
        "See https://example.com/user-provided",
        collector,
        user_text="check https://example.com/user-provided please",
    )
    assert verdict.status == "ok"
    assert verdict.unverified == []


# ── SourceCollector accessor ──────────────────────────────────────────────────


def test_known_urls_gathers_citations_sources_and_failed_fetches():
    collector = SourceCollector()
    collector.add_web_source(url="https://a.example/ok", ok=True)
    collector.add_web_source(url="https://b.example/fail", ok=False)
    collector.add_fetched_source(url="https://c.example/fetched")
    known = collector.known_urls()
    assert {"https://a.example/ok", "https://b.example/fail", "https://c.example/fetched"} <= known


def test_gate_tolerates_a_broken_collector():
    class Broken:
        def known_urls(self):
            raise RuntimeError("boom")

    verdict = enforce_evidence_answer("See https://x.example/a", Broken())
    assert isinstance(verdict, CitationIntegrity)
    assert verdict.status == "no_evidence"
