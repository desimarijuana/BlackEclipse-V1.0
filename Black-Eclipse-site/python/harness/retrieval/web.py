"""Web research as a first-class retrieval method (Milestone 2E).

Web research is NOT "the structured provider failed, go search". It is a path the
planner selects when the objective is qualitative, current, or primary-source
oriented. This module implements:

    search → rank/select → retrieve underlying source → extract evidence →
    capture metadata → normalize → return evidence

It reaches the web through the TS bridge (`web_search` / `web_fetch`), which owns
the existing SSRF-hardened transport and search implementation. No second search
system is created here.

Evidence always carries provenance. Missing metadata is `None` — never guessed.
A snippet is never presented as a verified page when the page itself could not be
retrieved.
"""

from __future__ import annotations

import time
from typing import Any, Optional

from ..tools import DataBridge
from .contract import (
    DataType,
    EvidenceItem,
    EvidenceKind,
    FinancialRetrievalRequest,
    NormalizedFinancialObject,
    SourceReference,
    SourceTier,
)
from .sources import SourceOutcome

# Hosts that are primary/official sources for financial research. Used only to
# LABEL provenance (never to fabricate it) — the page's real host is recorded.
_PRIMARY_HOST_HINTS = (
    "sec.gov",
    "investor.",
    "ir.",
    "/investor",
    "federalreserve.gov",
    "bls.gov",
    "bea.gov",
    "treasury.gov",
    "europa.eu",
    "ecb.europa.eu",
    "imf.org",
    "worldbank.org",
    "oecd.org",
    "stats.",
    # Local regulators / exchanges / filing systems (global-by-design). Labelling
    # only — a match never fabricates provenance; it records the real host.
    "mops.twse.com.tw",       # Taiwan MOPS (公開資訊觀測站)
    "twse.com.tw",            # Taiwan Stock Exchange
    "dart.fss.or.kr",         # Korea DART
    "kind.krx.co.kr",         # Korea KIND
    "krx.co.kr",
    "tdnet.info",             # Japan TDnet
    "jpx.co.jp",              # Japan Exchange Group
    "release.tdnet.info",
    "hkexnews.hk",            # Hong Kong Exchange news
    "hkex.com.hk",
    "sse.com.cn",             # Shanghai
    "szse.cn",                # Shenzhen
    "bseindia.com",           # India BSE
    "nseindia.com",           # India NSE
    "companieshouse.gov.uk",  # UK Companies House
    "londonstockexchange.com",
    "cvm.gov.br",             # Brazil CVM
    "b3.com.br",              # Brazil B3
    "sedar.com",              # Canada SEDAR
    "sedarplus.ca",
    "tsx.com",
    "asx.com.au",             # Australia ASX
    "sgx.com",                # Singapore
    "bursamalaysia.com",
    "set.or.kr",
    "set.or.th",              # Thailand
    "idx.co.id",              # Indonesia
    "moex.com",               # Russia
    "borsaistanbul.com",      # Turkey
    "jse.co.za",              # South Africa
    "psx.com.pk",             # Pakistan
    "tadawul.com.sa",         # Saudi Arabia
    "adx.ae",
    "dfm.ae",
    "egx.com.eg",
)

_SECONDARY_HOST_HINTS = ("reuters.com", "bloomberg.com", "wsj.com", "ft.com", "cnbc.com", "apnews.com")

# Market → a locally authoritative source hint used to build a market-aware
# filing query. Keyed by canonical market id; a market absent here gets the
# generic "annual report regulatory filing" hint. Hosts name the real local
# regulator/exchange filing system, never a fabricated document.
LOCAL_FILING_HINTS: dict[str, str] = {
    "US": "10-K filing SEC EDGAR",
    "TW": "年報 公開資訊觀測站 MOPS filing",
    "KR": "사업보고서 DART filing",
    "JP": "有価証券報告書 TDnet filing",
    "HK": "annual report HKEXnews filing",
    "CN": "annual report SSE/SZSE filing",
    "IN": "annual report BSE/NSE filing",
    "UK": "annual report Companies House filing",
    "DE": "Geschäftsbericht Bundesanzeiger filing",
    "FR": "rapport annuel AMF filing",
    "NL": "jaarverslag AFM filing",
    "CA": "annual report SEDAR filing",
    "BR": "demonstrações financeiras CVM filing",
    "AU": "annual report ASX filing",
    "SG": "annual report SGX filing",
    "MY": "annual report Bursa Malaysia filing",
    "TH": "annual report SET filing",
    "ID": "annual report IDX filing",
    "TR": "annual report Borsa Istanbul filing",
    "ZA": "annual report JSE filing",
    "PK": "annual report PSX filing",
    "SA": "annual report Tadawul filing",
    "AE": "annual report ADX/DFM filing",
    "MX": "reporte anual BMV filing",
}


def local_filing_hint(market: Optional[str]) -> str:
    """A market-aware filing query hint (never a fabricated document name)."""
    key = (market or "").strip().upper()
    return LOCAL_FILING_HINTS.get(key, "annual report regulatory filing")


def _classify_source(host: str, url: str) -> SourceTier:
    probe = f"{host}{url}".lower()
    if any(h in probe for h in _PRIMARY_HOST_HINTS):
        return "primary"
    if any(h in probe for h in _SECONDARY_HOST_HINTS):
        return "secondary"
    return "secondary" if host else "unknown"


def _as_evidence(item: dict[str, Any], query: str, *, retrieved: bool, validation: str) -> EvidenceItem:
    url = item.get("url") or None
    host = ""
    if url:
        try:
            from urllib.parse import urlparse

            host = urlparse(url).netloc.replace("www.", "")
        except Exception:  # noqa: BLE001
            host = ""
    title = item.get("title") or None
    snippet = item.get("snippet") or item.get("text") or ""
    published = item.get("publishedAt") or item.get("date") or None

    source = SourceReference(
        source=host or "web",
        sourceType=_classify_source(host, url or ""),
        url=url,
        title=title,
        publishedAt=published,        # None when unknown — never guessed
        query=query,
        validationStatus=validation,  # type: ignore[arg-type]
    )
    kind: EvidenceKind = "filing" if source.sourceType == "primary" else "web"
    summary = title or url or "(untitled result)"
    if snippet:
        summary = f"{summary} — {snippet[:280]}"

    objects = [
        NormalizedFinancialObject(
            name="web_evidence",
            value=snippet or title,
            unit=None,
            source=source,
            quality="valid" if retrieved else "warning",
            warnings=[] if retrieved else ["only a search snippet was available; the page was not retrieved"],
        )
    ]
    return EvidenceItem(
        id=f"web_{abs(hash((url, title, query))) % 10**10}",
        kind=kind,
        summary=summary,
        data=item,
        objects=objects,
        source=source,
        quality="valid" if retrieved else "warning",
        warnings=[] if retrieved else ["unverified: snippet only"],
    )


class WebResearchSource:
    """Search + retrieve, with primary-source preference.

    Also serves `financial_statements` as a *qualitative/primary-source* path:
    when the structured vault is empty/stale/missing a requested period, the
    planner may select this source to search filings/IR pages. It returns
    provenance-carrying pages, not fabricated numbers — the research escalation
    layer extracts and deterministically validates any numeric fact from the
    fetched text.
    """

    name = "WEB"
    tier = "secondary"
    dataTypes: tuple[DataType, ...] = ("news", "web_research", "earnings", "financial_statements")

    def __init__(self, bridge: Optional[DataBridge]) -> None:
        self._bridge = bridge

    def available(self, request: FinancialRetrievalRequest) -> bool:
        return self._bridge is not None and request.allowWeb and request.dataType in self.dataTypes

    async def retrieve(self, request: FinancialRetrievalRequest) -> SourceOutcome:
        started = time.monotonic()
        query = request.query or self._default_query(request)
        search = await self._call("web_search", {"query": query, "limit": 8})
        elapsed = int((time.monotonic() - started) * 1000)
        diagnostics = search.get("diagnostics") if isinstance(search.get("diagnostics"), list) else []
        if search.get("status") != "OK":
            return SourceOutcome(
                source=self.name, status="UNAVAILABLE",
                error=search.get("error") or "web search returned no results",
                latencyMs=elapsed,
                diagnostics=diagnostics,
            )
        results = search.get("results") or []
        ranked = self._rank(results)
        evidence: list[EvidenceItem] = []

        # Retrieve the underlying page for the best candidates so a snippet is
        # never treated as final evidence when the page itself is reachable.
        for item in ranked[:3]:
            page = await self._call("web_fetch", {"url": item.get("url")})
            if page.get("diagnostics"):
                diagnostics = [*diagnostics, *page["diagnostics"]]
            if page.get("status") == "OK":
                merged = {**item, "text": page.get("text") or item.get("snippet"), "publishedAt": item.get("publishedAt")}
                evidence.append(_as_evidence(merged, query, retrieved=True, validation="valid"))
            else:
                evidence.append(_as_evidence(item, query, retrieved=False, validation="unverified"))

        # Remaining results are snippet-only, explicitly unverified.
        for item in ranked[3:]:
            evidence.append(_as_evidence(item, query, retrieved=False, validation="unverified"))

        references = [e.source for e in evidence]
        return SourceOutcome(
            source=self.name,
            status="OK" if evidence else "UNAVAILABLE",
            evidence=evidence,
            references=references,
            warnings=[] if evidence else ["no web evidence parsed"],
            raw=search,
            latencyMs=int((time.monotonic() - started) * 1000),
            diagnostics=diagnostics,
        )

    async def _call(self, capability: str, params: dict[str, Any]) -> dict[str, Any]:
        if self._bridge is None:
            return {"status": "UNAVAILABLE", "error": "data bridge not configured"}
        try:
            return await self._bridge.fetch(capability, params)
        except Exception as exc:  # noqa: BLE001
            return {"status": "UNAVAILABLE", "error": str(exc)}

    @staticmethod
    def _rank(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Deterministic ranking: primary sources first, then result order.

        No LLM here — the ranking must be explainable and reproducible.
        """
        def score(item: dict[str, Any]) -> int:
            url = (item.get("url") or "").lower()
            host = ""
            try:
                from urllib.parse import urlparse

                host = urlparse(item.get("url") or "").netloc.lower()
            except Exception:  # noqa: BLE001
                host = ""
            tier = _classify_source(host, url)
            base = {"primary": 0, "official": 1, "secondary": 2, "unknown": 3}.get(tier, 3)
            return base

        return sorted(results, key=score)

    @staticmethod
    def _default_query(request: FinancialRetrievalRequest) -> str:
        parts = [request.objective]
        if request.instrument:
            parts.append(request.instrument)
        return " ".join(p for p in parts if p)


__all__ = ["WebResearchSource", "classify_source_tier", "PRIMARY_TIER", "SECONDARY_TIER", "local_filing_hint", "LOCAL_FILING_HINTS"]

# Public aliases for the research escalation layer (one classifier, no fork).
classify_source_tier = _classify_source
PRIMARY_TIER: SourceTier = "primary"
SECONDARY_TIER: SourceTier = "secondary"
