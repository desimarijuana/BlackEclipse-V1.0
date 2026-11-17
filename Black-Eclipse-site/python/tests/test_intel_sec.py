"""EDGAR parsers: the shapes are taken from real filings, not invented."""

from __future__ import annotations

import pytest

from harness.intel import sec

FORM4_XML = """<?xml version="1.0"?>
<ownershipDocument>
  <documentType>4</documentType>
  <issuer>
    <issuerCik>0000320193</issuerCik>
    <issuerName>Apple Inc.</issuerName>
    <issuerTradingSymbol>AAPL</issuerTradingSymbol>
  </issuer>
  <reportingOwner>
    <reportingOwnerId>
      <rptOwnerCik>0001780525</rptOwnerCik>
      <rptOwnerName>Newstead Jennifer</rptOwnerName>
    </reportingOwnerId>
    <reportingOwnerRelationship>
      <isDirector>false</isDirector>
      <isOfficer>true</isOfficer>
      <isTenPercentOwner>false</isTenPercentOwner>
      <officerTitle>SVP, GC and Government Affairs</officerTitle>
    </reportingOwnerRelationship>
  </reportingOwner>
  <aff10b5One>false</aff10b5One>
  <nonDerivativeTable>
    <nonDerivativeTransaction>
      <securityTitle><value>Common Stock</value></securityTitle>
      <transactionDate><value>2026-11-10</value></transactionDate>
      <transactionCoding>
        <transactionFormType>4</transactionFormType>
        <transactionCode>P</transactionCode>
      </transactionCoding>
      <transactionAmounts>
        <transactionShares><value>1000</value></transactionShares>
        <transactionPricePerShare><value>300.00</value></transactionPricePerShare>
        <transactionAcquiredDisposedCode><value>A</value></transactionAcquiredDisposedCode>
      </transactionAmounts>
    </nonDerivativeTransaction>
    <nonDerivativeTransaction>
      <securityTitle><value>Common Stock</value></securityTitle>
      <transactionDate><value>2026-11-10</value></transactionDate>
      <transactionCoding>
        <transactionFormType>4</transactionFormType>
        <transactionCode>A</transactionCode>
      </transactionCoding>
      <transactionAmounts>
        <transactionShares><value>500</value></transactionShares>
        <transactionPricePerShare><value>0</value></transactionPricePerShare>
        <transactionAcquiredDisposedCode><value>A</value></transactionAcquiredDisposedCode>
      </transactionAmounts>
    </nonDerivativeTransaction>
  </nonDerivativeTable>
</ownershipDocument>
"""

FORM4_PLANNED_XML = """<?xml version="1.0"?>
<ownershipDocument>
  <documentType>4</documentType>
  <reportingOwner>
    <reportingOwnerId><rptOwnerName>Example Director</rptOwnerName></reportingOwnerId>
    <reportingOwnerRelationship>
      <isDirector>true</isDirector>
      <isOfficer>false</isOfficer>
    </reportingOwnerRelationship>
  </reportingOwner>
  <aff10b5One>true</aff10b5One>
  <nonDerivativeTable>
    <nonDerivativeTransaction>
      <transactionDate><value>2026-11-05</value></transactionDate>
      <transactionCoding><transactionCode>S</transactionCode></transactionCoding>
      <transactionAmounts>
        <transactionShares><value>2399</value></transactionShares>
        <transactionPricePerShare><value>351.36</value></transactionPricePerShare>
        <transactionAcquiredDisposedCode><value>D</value></transactionAcquiredDisposedCode>
      </transactionAmounts>
    </nonDerivativeTransaction>
  </nonDerivativeTable>
</ownershipDocument>
"""

NAMESPACED_XML = """<?xml version="1.0"?>
<ownershipDocument xmlns="http://www.sec.gov/edgar/document/ownership/2024">
  <documentType>4</documentType>
  <reportingOwner>
    <reportingOwnerId><rptOwnerName>Namespaced Owner</rptOwnerName></reportingOwnerId>
    <reportingOwnerRelationship>
      <isOfficer>true</isOfficer>
    </reportingOwnerRelationship>
  </reportingOwner>
  <aff10b5One>0</aff10b5One>
  <nonDerivativeTable>
    <nonDerivativeTransaction>
      <transactionDate><value>2026-11-01</value></transactionDate>
      <transactionCoding><transactionCode>P</transactionCode></transactionCoding>
      <transactionAmounts>
        <transactionShares><value>100</value></transactionShares>
        <transactionPricePerShare><value>50.0</value></transactionPricePerShare>
        <transactionAcquiredDisposedCode><value>A</value></transactionAcquiredDisposedCode>
      </transactionAmounts>
    </nonDerivativeTransaction>
  </nonDerivativeTable>
</ownershipDocument>
"""

FORM4_FOOTNOTE_PLAN = """<?xml version="1.0"?>
<ownershipDocument>
  <documentType>4</documentType>
  <reportingOwner>
    <reportingOwnerId><rptOwnerName>Footnote Seller</rptOwnerName></reportingOwnerId>
    <reportingOwnerRelationship><isOfficer>true</isOfficer></reportingOwnerRelationship>
  </reportingOwner>
  <aff10b5One>false</aff10b5One>
  <nonDerivativeTable>
    <nonDerivativeTransaction>
      <transactionDate><value>2026-11-02</value></transactionDate>
      <transactionCoding><transactionCode>S</transactionCode></transactionCoding>
      <transactionAmounts>
        <transactionShares><value>10</value></transactionShares>
        <transactionPricePerShare><value>100</value></transactionPricePerShare>
        <transactionAcquiredDisposedCode><value>D</value></transactionAcquiredDisposedCode>
      </transactionAmounts>
    </nonDerivativeTransaction>
  </nonDerivativeTable>
  <footnotes>
    <footnote id="F1">This sale was made pursuant to a Rule 10b5-1 trading plan.</footnote>
  </footnotes>
</ownershipDocument>
"""


def test_ticker_map_normalises_cik_and_uppercases_ticker():
    mapping = sec.parse_company_tickers({
        "0": {"cik_str": 320193, "ticker": "aapl", "title": "Apple Inc."},
        "1": {"cik_str": "1045810", "ticker": "NVDA", "title": "NVIDIA CORP"},
        "2": {"ticker": "BAD"},  # no CIK
    })
    assert mapping["AAPL"] == {"cik": "0000320193", "name": "Apple Inc."}
    assert mapping["NVDA"]["cik"] == "0001045810"
    assert "BAD" not in mapping


def test_submissions_flatten_and_window_filter():
    payload = {"filings": {"recent": {
        "form": ["4", "8-K", "13D/A", "10-K"],
        "filingDate": ["2026-11-12", "2026-11-09", "2026-10-20", "2020-01-01"],
        "accessionNumber": ["a", "b", "c", "d"],
        "primaryDocument": ["f4.xml", "8k.htm", "d.htm", "k.htm"],
    }}}
    filings = sec.parse_submissions(payload)
    assert [f.form for f in filings] == ["4", "8-K", "13D/A", "10-K"]
    assert filings[0].accession_dir == "a"
    recent = sec.filings_since(filings, "2026-01-01")
    assert [f.form for f in recent] == ["4", "8-K", "13D/A"]
    assert [f.form for f in sec.filings_since(filings, "2026-01-01", ["8-K"])] == ["8-K"]
    assert sec.count_filings(filings, "2026-01-01", "2026-11-10") == 2


def test_form4_parses_only_non_derivative_rows_with_codes():
    trades = sec.parse_form4(FORM4_XML, accession="acc-1")
    assert len(trades) == 2
    buy = next(t for t in trades if t.code == "P")
    assert buy.owner == "Newstead Jennifer"
    assert buy.is_officer and not buy.is_director
    assert buy.dollars == pytest.approx(300_000)
    assert buy.discretionary_buy
    assert trades[1].code == "A"
    assert not trades[1].discretionary_buy


def test_form4_handles_xml_namespaces():
    trades = sec.parse_form4(NAMESPACED_XML)
    assert len(trades) == 1
    assert trades[0].owner == "Namespaced Owner"
    assert trades[0].discretionary_buy
    assert trades[0].dollars == pytest.approx(5_000)


def test_planned_sales_are_excluded_from_conviction_both_ways():
    flagged = sec.parse_form4(FORM4_PLANNED_XML)
    assert flagged[0].planned is True

    footnote = sec.parse_form4(FORM4_FOOTNOTE_PLAN)
    assert footnote[0].planned is True

    summary = sec.summarize(flagged + footnote, window_days=90)
    assert summary.buy_usd == 0 and summary.sell_usd == 0
    assert summary.planned_excluded == 2
    assert not summary.has_any


def test_summarize_clusters_buyers_and_tracks_seniority():
    trades = list(sec.parse_form4(FORM4_XML, accession="acc-1"))
    second = sec.InsiderTrade(
        owner="Second Officer", is_officer=True, is_director=False,
        is_ten_percent=False, title="CFO", code="P", shares=100.0, price=300.0,
        acquired=True, traded_on="2026-11-11", planned=False, accession="acc-2",
    )
    summary = sec.summarize([*trades, second], window_days=90)
    assert summary.buy_usd == pytest.approx(330_000)
    assert summary.buyer_count == 2
    assert summary.cluster is True
    assert set(summary.officer_buyers) == {"Newstead Jennifer", "Second Officer"}
    assert summary.last_buy == "2026-11-11"
    assert summary.filings_scanned == 2


def test_a_single_buyer_is_not_a_cluster():
    trades = sec.parse_form4(FORM4_XML)
    summary = sec.summarize(trades, window_days=90)
    assert summary.buyer_count == 1
    assert summary.cluster is False


def test_unpriced_buy_is_counted_but_not_priced():
    trade = sec.InsiderTrade(
        owner="No Price", is_officer=True, is_director=False, is_ten_percent=False,
        title="", code="P", shares=500.0, price=None, acquired=True,
        traded_on="2026-11-01", planned=False,
    )
    summary = sec.summarize([trade], window_days=30)
    assert summary.buy_usd == 0
    assert summary.unpriced_buys == 1
    assert summary.has_any is False


def test_xml_document_name_prefers_the_raw_filing_not_the_xsl_render():
    items = [{"name": "xslF345X06/form4.xml"}, {"name": "form4.xml"}]
    assert sec.xml_document_name(items) == "form4.xml"
    assert sec.xml_document_name(items, "xslF345X06/form4.xml") == "form4.xml"
    assert sec.xml_document_name([{"name": "xslF345X06/form4.xml"}]) == "xslF345X06/form4.xml"


def test_empty_ownership_document_is_not_an_error():
    empty = """<?xml version="1.0"?><ownershipDocument><documentType>4</documentType></ownershipDocument>"""
    assert sec.parse_form4(empty) == []
    assert sec.parse_form4("") == []
