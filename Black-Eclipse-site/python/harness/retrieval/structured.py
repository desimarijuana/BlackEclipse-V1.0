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
    "financial_statements": "fundamentals",
}

# DataType → the live-provider capability on the TS bridge.
_LIVE_CAPABILITY: dict[str, str] = {
    "current_quote": "live_quote",
    "historical_prices": "price_history",
    "macro_series": "macro_series",
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
        source_ref = SourceReference(
            source=self.name,
            sourceType="structured",
            publishedAt=updated,
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


__all__ = ["JddsSource", "LiveStructuredSource"]
