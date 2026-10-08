"""Crypto market data as a first-class retrieval source (Financial Data Gateway).

Crypto assets are not equities: a bare `BTC` is ambiguous across quote currencies
(`BTC-USD`, `BTC-USDT`, `BTC-EUR`), and a crypto ticker can collide with an equity
ticker. This source resolves a crypto request through the read-only bridge's
`crypto_market_data` capability, which owns the keyless public market-data path
and the pair normalization.

It satisfies the SAME `RetrievalSource` contract as every other provider, so the
planner can select it without the agent naming Binance/CoinGecko. It carries the
crypto asset identity (base/quote) on every object so a consumer can prove which
pair a price is for — never a bare number.
"""

from __future__ import annotations

import time
from typing import Any, Optional

from ..tools import DataBridge
from .contract import (
    DataType,
    FinancialRetrievalRequest,
    InstrumentIdentity,
    NormalizedFinancialObject,
    SourceReference,
)
from .sources import SourceOutcome

# The crypto data types this source serves. `crypto_market_data` is the gateway's
# own capability id; `current_quote` lets a crypto request also satisfy a generic
# quote ask (the planner routes crypto requests here via `is_fx_or_crypto`).
_CRYPTO_TYPES: tuple[DataType, ...] = ("current_quote",)  # type: ignore[assignment]


class CryptoSource:
    """Keyless crypto market data behind one interface.

    Tier `structured`: a crypto ticker is precise quantitative data, not web
    research. It reaches the TS bridge's `crypto_market_data` capability, which
    reuses the existing crypto connector transport (no second HTTP client).
    """

    name = "CRYPTO"
    tier = "structured"
    dataTypes: tuple[DataType, ...] = _CRYPTO_TYPES

    def __init__(self, bridge: Optional[DataBridge]) -> None:
        self._bridge = bridge

    def available(self, request: FinancialRetrievalRequest) -> bool:
        # This source owns crypto ONLY. It must never answer an equity/FX request,
        # and the vault/live provider must never be asked to answer crypto (they
        # have no row). The classifier is shared, so the two cannot disagree.
        from .structured import is_fx_or_crypto

        if not is_fx_or_crypto(request):
            return False
        # An FX pair (`EURUSD=X`, `EUR/USD`) is not crypto.
        market = (request.market or "").strip().upper()
        if market == "FX":
            return False
        return self._bridge is not None

    async def retrieve(self, request: FinancialRetrievalRequest) -> SourceOutcome:
        started = time.monotonic()
        symbol = (request.instrument or "").strip().upper()
        if not symbol:
            return SourceOutcome(
                source=self.name, status="UNAVAILABLE", error="crypto symbol is required",
                latencyMs=int((time.monotonic() - started) * 1000),
            )
        params: dict[str, Any] = {"symbol": symbol}
        # An explicit quote currency (from metadata) selects the pair precisely.
        metadata = request.metadata or {}
        if metadata.get("quoteCurrency"):
            params["quoteCurrency"] = metadata["quoteCurrency"]
        try:
            payload = await self._bridge.fetch("crypto_market_data", params)  # type: ignore[union-attr]
        except Exception as exc:  # noqa: BLE001 - a source failure is data
            payload = {"status": "UNAVAILABLE", "error": str(exc)}
        elapsed = int((time.monotonic() - started) * 1000)

        if payload.get("status") == "AMBIGUOUS":
            return SourceOutcome(
                source=self.name, status="AMBIGUOUS",
                error=payload.get("error") or "crypto pair could not be resolved",
                raw=payload, latencyMs=elapsed,
            )
        if payload.get("status") != "OK":
            diagnostics = payload.get("diagnostics")
            return SourceOutcome(
                source=self.name, status="UNAVAILABLE",
                error=payload.get("error") or "crypto provider returned no data",
                raw=payload, latencyMs=elapsed,
                diagnostics=diagnostics if isinstance(diagnostics, list) else [],
            )
        objects = self._normalize(payload)
        if not objects:
            return SourceOutcome(
                source=self.name, status="UNAVAILABLE",
                error=f"crypto provider had no market data for {symbol}",
                raw=payload, latencyMs=elapsed,
            )
        return SourceOutcome(
            source=self.name, status="OK", objects=objects,
            references=[objects[0].source], raw=payload, latencyMs=elapsed,
        )

    @staticmethod
    def _normalize(payload: dict[str, Any]) -> list[NormalizedFinancialObject]:
        base = str(payload.get("base") or payload.get("symbol") or "").upper()
        quote = str(payload.get("quote") or "").upper()
        pair = payload.get("pair") or (f"{base}-{quote}" if base and quote else base)
        currency = quote or None
        as_of = payload.get("observationTime") or payload.get("asOf")
        obs_source = payload.get("observationSource") or "unknown"
        identity = InstrumentIdentity(
            market="CRYPTO",
            symbol=str(pair or base),
            currency=currency,
            assetClass="crypto",
            securityType="crypto",
            name=payload.get("name") or pair,
        )
        source = SourceReference(
            source=payload.get("provider") or "CRYPTO",
            sourceType="structured",
            publishedAt=as_of,
            query=payload.get("query"),
            validationStatus="valid",
        )

        fields = (
            ("price", payload.get("price"), "currency"),
            ("changePct", payload.get("changePct"), "%"),
            ("volume", payload.get("volume"), "shares"),
            ("marketCap", payload.get("marketCap"), "currency"),
            ("high24h", payload.get("high24h"), "currency"),
            ("low24h", payload.get("low24h"), "currency"),
        )
        out: list[NormalizedFinancialObject] = []
        for name, value, unit in fields:
            if value is None:
                continue
            out.append(
                NormalizedFinancialObject(
                    name=name,
                    value=value,
                    unit=unit,
                    currency=currency if unit == "currency" else None,
                    dataTimestamp=as_of,
                    instrument=identity.symbol,
                    identity=identity,
                    source=source,
                    observation_time=as_of,
                    observation_source=obs_source,
                    quality="valid",
                )
            )
        return out


__all__ = ["CryptoSource"]
