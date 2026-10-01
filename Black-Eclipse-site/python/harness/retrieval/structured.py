"""Structured financial sources (Milestone 2D).

Every structured provider satisfies the SAME `RetrievalSource` contract, so the
layer can treat JDdS (the vault) and yfinance (a live provider) interchangeably.
Neither is mandatory: if one is unavailable the other, or the cache, may answer.

The providers reach their data through the read-only `DataBridge` — the one
market-data path. No Python code opens `jdds.db`, and no provider is named above
this module.
"""

from __future__ import annotations

import time
from typing import Any, Optional

from ..tools import DataBridge
from .contract import (
    DataType,
    EvidenceItem,
    FinancialRetrievalRequest,
    NormalizedFinancialObject,
    SourceReference,
)
from .normalize import (
    identity_from_payload,
    normalize_fundamentals,
    normalize_history,
    normalize_macro,
    normalize_quote,
    normalize_snapshot,
)
from .sources import SourceOutcome

# DataType → the JDdS *vault* capability that serves it. Deliberately limited to
# what the committed snapshot actually stores (universe, cached prices,
# fundamentals). A series or a live quote is NOT a vault read — claiming it here
# would mislabel live provider data as JDdS, which is a provenance lie.
_JDDS_CAPABILITY: dict[str, str] = {
    "current_quote": "market_snapshot",
    "company_profile": "fundamentals",
    "financial_statements": "financial_statements",
}

# DataType → the live-provider capability on the TS bridge.
_LIVE_CAPABILITY: dict[str, str] = {
    "current_quote": "live_quote",
    "historical_prices": "price_history",
    "macro_series": "macro_series",
}

# DataType → the SEC direct-filings capability. This is an INDEPENDENT primary
# source for US issuers' statements — separate from the JDdS vault — reached
# through the existing SEC adapter on the TS bridge.
_SEC_CAPABILITY: dict[str, str] = {
    "financial_statements": "sec_filings",
}


async def _fetch(bridge: Optional[DataBridge], capability: str, params: dict[str, Any]) -> dict[str, Any]:
    if bridge is None:
        return {"status": "UNAVAILABLE", "error": "data bridge not configured"}
    try:
        return await bridge.fetch(capability, params)
    except Exception as exc:  # noqa: BLE001 - a source failure is data
        return {"status": "UNAVAILABLE", "error": str(exc)}


class JddsSource:
    """The JDdS vault — read-only, committed seed snapshot.

    Tier `structured`: it holds the universe + cached prices/fundamentals/macro.
    It is the DEFAULT structured source because it is local, fast and always
    available, but it is not the only one.
    """

    name = "JDDS"
    tier = "structured"
    dataTypes: tuple[DataType, ...] = (
        "current_quote",
        "company_profile",
        "financial_statements",
    )

    def __init__(self, bridge: Optional[DataBridge]) -> None:
        self._bridge = bridge

    def available(self, request: FinancialRetrievalRequest) -> bool:
        # The vault holds EQUITIES/FUNDS, not FX pairs or crypto. An FX/crypto
        # quote has no vault row, so routing it through the vault records a
        # failure that cannot succeed (Harness closeout Phase 4.1). Skip the vault
        # so FX/crypto go straight to the live provider, exactly as crypto does.
        if is_fx_or_crypto(request):
            return False
        return self._bridge is not None and request.dataType in _JDDS_CAPABILITY

    async def retrieve(self, request: FinancialRetrievalRequest) -> SourceOutcome:
        started = time.monotonic()
        capability = _JDDS_CAPABILITY[request.dataType]
        params = _params_for(request)
        payload = await _fetch(self._bridge, capability, params)
        elapsed = int((time.monotonic() - started) * 1000)
        if payload.get("status") != "OK":
            return SourceOutcome(
                source=self.name,
                status="UNAVAILABLE",
                error=payload.get("error") or f"no {request.dataType} in JDdS",
                latencyMs=elapsed,
            )
        objects, references = self._normalize(request, payload)
        if not objects and request.dataType != "company_profile":
            return SourceOutcome(
                source=self.name,
                status="UNAVAILABLE",
                error=f"JDdS had no {request.dataType} for {request.instrument}",
                raw=payload,
                latencyMs=elapsed,
            )
        return SourceOutcome(
            source=self.name,
            status="OK",
            objects=objects,
            references=references,
            raw=payload,
            latencyMs=elapsed,
        )

    def _normalize(
        self, request: FinancialRetrievalRequest, payload: dict[str, Any]
    ) -> tuple[list[NormalizedFinancialObject], list[SourceReference]]:
        symbol = payload.get("symbol") or request.instrument
        updated = payload.get("updatedAt")
        # The vault capability may have served the result from a LIVE provider
        # (the persisted snapshot was empty for this market, so the bridge fetched
        # and cached it). Label the REAL provider rather than always saying
        # "JDDS" — a provenance lie would be worse than a missing value.
        provider = payload.get("provider") or payload.get("statementSource")
        source_name = self.name if not provider else f"{provider}"
        source_ref = SourceReference(
            source=source_name,
            sourceType="structured",
            publishedAt=updated or payload.get("retrievedAt"),
            query=request.objective,
            validationStatus="valid",
        )
        refs = [source_ref]
        if request.dataType == "current_quote":
            return normalize_quote(payload, source_ref), refs
        if request.dataType == "company_profile":
            return normalize_snapshot(payload, source_ref), refs
        if request.dataType == "financial_statements":
            return normalize_fundamentals(payload, source_ref), refs
        if request.dataType == "historical_prices":
            return normalize_history(payload, source_ref), refs
        if request.dataType == "macro_series":
            return normalize_macro(payload, source_ref), refs
        return [], refs


class LiveStructuredSource:
    """A live structured market-data provider (reached via the TS bridge).

    Tier `structured` as well — this is still precise quantitative data, not web
    research. Its job is to satisfy requests the vault cannot (live quotes for
    symbols outside the committed snapshot, long history series).
    """

    name = "LIVE_STRUCTURED"
    tier = "structured"
    dataTypes: tuple[DataType, ...] = ("current_quote", "historical_prices", "macro_series")

    def __init__(self, bridge: Optional[DataBridge]) -> None:
        self._bridge = bridge

    def available(self, request: FinancialRetrievalRequest) -> bool:
        return self._bridge is not None and request.dataType in _LIVE_CAPABILITY

    async def retrieve(self, request: FinancialRetrievalRequest) -> SourceOutcome:
        started = time.monotonic()
        capability = _LIVE_CAPABILITY[request.dataType]
        payload = await _fetch(self._bridge, capability, _params_for(request))
        elapsed = int((time.monotonic() - started) * 1000)
        # An ambiguous identity is terminal: another source cannot disambiguate a
        # ticker, so the outcome is AMBIGUOUS (never a guessed instrument).
        if payload.get("status") == "AMBIGUOUS":
            return SourceOutcome(
                source=self.name,
                status="AMBIGUOUS",
                error=payload.get("error") or "instrument identity is ambiguous",
                raw=payload,
                latencyMs=elapsed,
            )
        if payload.get("status") != "OK":
            return SourceOutcome(
                source=self.name,
                status="UNAVAILABLE",
                error=payload.get("error") or "live provider returned no data",
                latencyMs=elapsed,
            )
        ref = SourceReference(
            source=payload.get("provider") or self.name,
            sourceType="structured",
            publishedAt=payload.get("asOf"),
            query=request.objective,
            validationStatus="valid",
        )
        if request.dataType == "current_quote":
            return SourceOutcome(
                source=self.name, status="OK", objects=normalize_quote(payload, ref),
                references=[ref], raw=payload, latencyMs=elapsed,
            )
        if request.dataType == "historical_prices":
            return SourceOutcome(
                source=self.name, status="OK", objects=normalize_history(payload, ref),
                references=[ref], raw=payload, latencyMs=elapsed,
            )
        return SourceOutcome(
            source=self.name, status="OK", objects=normalize_macro(payload, ref),
            references=[ref], raw=payload, latencyMs=elapsed,
        )


# Global exchange-suffix → canonical market id. Mirrors the TS table in
# `src/lib/markets.ts` (`EXCHANGE_SUFFIX_ALIASES`). Used only for ROUTING
# eligibility (should we send this request to a US-only provider?); canonical
# identity is still decided by the bridge's instrument master.
_SUFFIX_TO_MARKET: dict[str, str] = {
    ".us": "US", ".to": "CA", ".v": "CA", ".cn": "CA", ".ne": "CA",
    ".sa": "BR", ".mx": "MX",
    ".tw": "TW", ".two": "TW", ".ks": "KR", ".kq": "KR",
    ".t": "JP", ".jp": "JP", ".hk": "HK",
    ".ss": "CN", ".sz": "CN", ".in": "IN", ".ns": "IN", ".bo": "IN",
    ".si": "SG", ".kl": "MY", ".ax": "AU", ".nz": "AU",
    ".bk": "TH", ".jk": "ID", ".vn": "VN",
    ".l": "UK", ".lse": "UK", ".de": "DE", ".f": "DE", ".etr": "DE",
    ".pa": "FR", ".as": "NL", ".sr": "SA", ".jo": "ZA", ".is": "TR",
    ".eg": "EG", ".ng": "NG", ".me": "RU",
}


# FX-pair shape: `EURUSD=X`, `EUR/USD`, `GBPJPY`. Crypto: `BTC-USD`, `ETHUSDT`.
# A cheap, deterministic classifier used ONLY for routing eligibility (does the
# vault even hold this?); canonical identity is still decided by the bridge.
_FX_SUFFIX = "=X"


def is_fx_or_crypto(request: FinancialRetrievalRequest) -> bool:
    """True when the request instrument is an FX pair or a crypto asset.

    The JDdS vault holds equities/funds only, so a vault attempt for FX/crypto
    cannot succeed and must not be recorded (Phase 4.1). Never guesses: an
    unmatched instrument stays eligible for the vault.
    """
    market = (request.market or "").strip().upper()
    if market in ("FX", "CRYPTO"):
        return True
    symbol = (request.instrument or "").strip().upper()
    if not symbol:
        return False
    if symbol.endswith(_FX_SUFFIX) or "/" in symbol:
        return True
    # Crypto is usually quoted against a fiat/stablecoin suffix.
    if symbol.endswith("-USD") or symbol.endswith("USDT"):
        return True
    return False


def infer_market_from_symbol(symbol: Optional[str]) -> Optional[str]:
    """The market implied by a recognised exchange suffix, else None.

    `2330.TW` → "TW". A symbol with no recognised suffix → None (the caller's
    explicit market, if any, still applies). Never guesses.
    """
    if not symbol:
        return None
    text = str(symbol).strip()
    dot = text.rfind(".")
    if dot <= 0 or dot == len(text) - 1:
        return None
    return _SUFFIX_TO_MARKET.get(text[dot:].lower())


class SecFilingsSource:
    """Direct SEC EDGAR filings/XBRL for US issuers (Phase 6).

    An INDEPENDENT primary-source route for `financial_statements`: it reaches
    `data.sec.gov` through the existing SEC adapter on the read-only bridge and
    returns issuer-reported annual periods with filing provenance (form + filed
    date). It is deliberately separate from the JDdS vault so a stale or
    incomplete vault does not leave the leg unanswerable, and separate from WEB so
    a numeric fact is never sourced from a search snippet.

    Tier `primary`: an SEC filing is authoritative. ELIGIBILITY: SEC covers US
    issuers; a request whose market (explicit or suffix-implied) is a recognised
    non-US market is NOT eligible here. That is a routing decision, not an outage
    — the provider is skipped so the next eligible route runs, and the skip is
    recorded.
    """

    name = "SEC"
    tier = "primary"
    dataTypes: tuple[DataType, ...] = ("financial_statements",)

    def __init__(self, bridge: Optional[DataBridge]) -> None:
        self._bridge = bridge

    def eligible(self, request: FinancialRetrievalRequest) -> bool:
        """True when this US-only route may be attempted for the request."""
        implied = (request.market or "").strip().upper() or infer_market_from_symbol(request.instrument)
        # No market info at all → the bridge decides (it defaults a bare US
        # ticker to US and returns not_covered otherwise). An explicit non-US
        # market, or a non-US suffix, makes this route ineligible up front.
        if implied and implied != "US":
            return False
        return True

    def available(self, request: FinancialRetrievalRequest) -> bool:
        return (
            self._bridge is not None
            and request.dataType in _SEC_CAPABILITY
            and self.eligible(request)
        )

    async def retrieve(self, request: FinancialRetrievalRequest) -> SourceOutcome:
        started = time.monotonic()
        capability = _SEC_CAPABILITY[request.dataType]
        payload = await _fetch(self._bridge, capability, _params_for(request))
        elapsed = int((time.monotonic() - started) * 1000)
        diagnostics = payload.get("diagnostics")
        if payload.get("status") != "OK":
            return SourceOutcome(
                source=self.name,
                status="UNAVAILABLE",
                error=payload.get("error") or "SEC EDGAR returned no statements",
                raw=payload,
                latencyMs=elapsed,
                diagnostics=diagnostics if isinstance(diagnostics, list) else [],
            )
        ref = SourceReference(
            source="SEC EDGAR",
            sourceType="primary",
            publishedAt=payload.get("retrievedAt"),
            query=request.objective,
            validationStatus="valid",
        )
        objects = normalize_fundamentals(payload, ref)
        if not objects:
            return SourceOutcome(
                source=self.name,
                status="UNAVAILABLE",
                error=f"SEC EDGAR had no statement periods for {request.instrument}",
                raw=payload,
                latencyMs=elapsed,
            )
        return SourceOutcome(
            source=self.name,
            status="OK",
            objects=objects,
            references=[ref],
            raw=payload,
            latencyMs=elapsed,
        )


# Interval/range vocabularies the bridge understands (mirrors the yfinance
# bridge's VALID_INTERVALS / VALID_PERIODS). A `quantity` is classified against
# these so the layer never confuses an interval ("1d") with a range ("6mo") —
# a real bug that silently disabled the entire historical path.
_INTERVALS = {
    "1m", "2m", "5m", "15m", "30m", "60m", "90m", "1h", "1d", "5d", "1wk", "1mo", "3mo",
}
_RANGES = {"1d", "5d", "1mo", "3mo", "6mo", "1y", "2y", "5y", "10y", "ytd", "max"}


def _params_for(request: FinancialRetrievalRequest) -> dict[str, Any]:
    params: dict[str, Any] = {}
    if request.instrument:
        params["symbol"] = request.instrument
    if request.market:
        params["market"] = request.market
    if request.dateRange:
        params["range"] = request.dateRange.get("range") or request.dateRange.get("start")
    # `quantity` is overloaded by data type: for price history it is a range
    # ("6mo"); for macro it is a series id. Map it to the right bridge param.
    if request.quantity and request.dataType == "macro_series":
        params["series"] = request.quantity
        # A macro source id is an implementation hint passed through metadata,
        # not part of the agent-facing contract.
        if request.metadata and request.metadata.get("source"):
            params["source"] = request.metadata["source"]
    elif request.quantity:
        q = request.quantity.strip().lower()
        if q in _RANGES:
            params["range"] = q
        elif q in _INTERVALS:
            params["interval"] = q
        else:
            params["range"] = q
    if request.query:
        params["query"] = request.query
    return params


__all__ = ["JddsSource", "LiveStructuredSource", "SecFilingsSource"]
