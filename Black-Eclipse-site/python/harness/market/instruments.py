"""Instrument Master — canonical identity + provider symbol mapping.

A ticker alone is not an instrument. `BTCUSDT`, `BTC-USD` and `BTC/USD` are the
SAME instrument expressed three ways; `AAPL` and `AAPL.US` (and `2330` vs
`2330.TW`) are venue-qualified forms of one identity; and a bare `AAPL` can be
ambiguous across venues. This module is the ONE place Eclipse canonicalizes an
identifier and maps it to each provider's own symbol convention.

It is deliberately pure + deterministic for the parts that can be (the
classifier + the provider symbol map). The authoritative identity (market,
currency, MIC, name) is resolved by the TS bridge's instrument master — this
module caches the resolved identity and never invents one when the bridge is
silent.

Contract terms (expiry/strike/right/maturity/coupon) are carried on the identity
so a derivative or bond can never be valued without them (the bridge enforces
the same rule).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from .models import AssetType

# FX quote suffix used by the Yahoo convention.
_FX_SUFFIX = "=X"

# A small, closed set of quote currencies used to split a concatenated crypto
# pair (`BTCUSDT` → BTC / USDT). Ordered longest-first so `USDT` wins over `USD`.
_QUOTE_CURRENCIES = (
    "USDT", "USDC", "BUSD", "TUSD", "DAI", "FDUSD",
    "USD", "EUR", "GBP", "JPY", "AUD", "CAD", "CHF", "CNY",
    "BTC", "ETH", "BNB", "SOL",
)

# Known crypto base assets. A symbol in this set with a recognised quote suffix
# is unambiguously a crypto pair (even without a dash/slash).
_KNOWN_CRYPTO_BASES = {
    "BTC", "ETH", "BNB", "SOL", "XRP", "ADA", "DOGE", "AVAX", "DOT", "MATIC",
    "LTC", "LINK", "TRX", "SHIB", "UNI", "ATOM", "XLM", "ETC", "BCH", "FIL",
    "APT", "ARB", "OP", "NEAR", "ICP", "SUI", "INJ", "PEPE", "WIF", "TON",
}

# Exchange suffix → canonical market id. Mirrors `retrieval/structured.py` and
# `src/lib/markets.ts`. Used only for ROUTING eligibility + canonical display.
SUFFIX_TO_MARKET: dict[str, str] = {
    ".us": "US", ".to": "CA", ".v": "CA", ".cn": "CA", ".ne": "CA",
    ".sa": "BR", ".mx": "MX", ".tw": "TW", ".two": "TW", ".ks": "KR",
    ".kq": "KR", ".t": "JP", ".jp": "JP", ".hk": "HK", ".ss": "CN",
    ".sz": "CN", ".in": "IN", ".ns": "IN", ".bo": "IN", ".si": "SG",
    ".kl": "MY", ".ax": "AU", ".nz": "AU", ".bk": "TH", ".jk": "ID",
    ".vn": "VN", ".l": "UK", ".lse": "UK", ".de": "DE", ".f": "DE",
    ".etr": "DE", ".pa": "FR", ".as": "NL", ".sr": "SA", ".jo": "ZA",
    ".is": "TR", ".eg": "EG", ".ng": "NG", ".me": "RU",
}

# Provider symbol conventions for crypto: base+quote → provider ticker.
_BINANCE_QUOTE = {"USD": "USDT"}


@dataclass
class ContractTerms:
    expiry: Optional[str] = None
    strike: Optional[float] = None
    right: Optional[str] = None       # "call" | "put"
    maturity: Optional[str] = None
    coupon: Optional[float] = None
    contract_month: Optional[str] = None
    seniority: Optional[str] = None

    def missing_for(self, asset_class: Optional[str]) -> list[str]:
        """Terms a given asset class requires before it can be valued."""
        required: list[str] = []
        if (asset_class or "").lower() == "option":
            if not self.expiry:
                required.append("expiry")
            if self.strike is None:
                required.append("strike")
            if not self.right:
                required.append("right")
        elif (asset_class or "").lower() == "future":
            if not self.expiry and not self.contract_month:
                required.append("expiry or contractMonth")
        elif (asset_class or "").lower() in ("bond", "debt"):
            if not self.maturity:
                required.append("maturity")
        return required


@dataclass
class CanonicalInstrument:
    """A canonical instrument identity (provider-neutral)."""

    instrument_id: str
    symbol: str                    # canonical symbol (e.g. "BTC-USD", "AAPL")
    asset_type: AssetType = "unknown"
    market: Optional[str] = None
    exchange: Optional[str] = None
    mic: Optional[str] = None
    currency: Optional[str] = None
    base_asset: Optional[str] = None
    quote_asset: Optional[str] = None
    name: Optional[str] = None
    security_type: Optional[str] = None
    contract_type: Optional[str] = None
    isin: Optional[str] = None
    cusip: Optional[str] = None
    figi: Optional[str] = None
    country: Optional[str] = None
    timezone: Optional[str] = None
    terms: ContractTerms = field(default_factory=ContractTerms)
    # provider id → that provider's symbol for this instrument
    provider_symbols: dict[str, str] = field(default_factory=dict)
    resolved: bool = True          # False when only a best-effort guess was possible
    # The identity resolver consulted the bridge (True) or is a deterministic
    # local classification (False). The gateway may cache a bridge-resolved
    # identity but never a local guess beyond the process.
    bridge_resolved: bool = True

    def provider_symbol(self, provider: str) -> Optional[str]:
        if provider in self.provider_symbols:
            return self.provider_symbols[provider]
        # Fall back to the canonical symbol (many providers accept it directly).
        return self.symbol

    def to_dict(self) -> dict[str, Any]:
        return {
            "instrumentId": self.instrument_id,
            "symbol": self.symbol,
            "assetType": self.asset_type,
            "market": self.market,
            "exchange": self.exchange,
            "mic": self.mic,
            "currency": self.currency,
            "baseAsset": self.base_asset,
            "quoteAsset": self.quote_asset,
            "name": self.name,
            "securityType": self.security_type,
            "contractType": self.contract_type,
            "isin": self.isin,
            "cusip": self.cusip,
            "figi": self.figi,
            "country": self.country,
            "timezone": self.timezone,
            "providerSymbols": dict(self.provider_symbols),
            "resolved": self.resolved,
        }


def split_crypto_pair(raw: str) -> Optional[tuple[str, str]]:
    """Split a concatenated crypto pair. `BTCUSDT` → ("BTC", "USDT")."""
    upper = raw.upper()
    for quote in _QUOTE_CURRENCIES:
        if upper.endswith(quote) and len(upper) > len(quote):
            base = upper[: -len(quote)]
            if base in _KNOWN_CRYPTO_BASES:
                return base, quote
    # A known base with no recognised quote is a bare asset → default USD pair.
    if upper in _KNOWN_CRYPTO_BASES:
        return upper, "USD"
    return None


def classify_identifier(raw: str, market: Optional[str] = None) -> dict[str, Any]:
    """Deterministically classify an identifier.

    Returns a dict with `kind` ("fx" | "crypto" | "equity"), plus `base`/`quote`
    for fx/crypto. Never guesses wildly: an unrecognised symbol is `equity`.
    """
    text = (raw or "").strip().upper()
    mkt = (market or "").strip().upper()

    # A CRYPTO-qualified request is crypto before the generic slash rule, so
    # `BTC/USD` on the crypto market is not mistaken for an FX pair.
    if mkt == "CRYPTO":
        body = text.replace("/", "-").replace("_", "-")
        if "-" in body:
            base, _, quote = body.partition("-")
            return {"kind": "crypto", "base": base, "quote": quote or "USD",
                    "canonical": f"{base}-{quote or 'USD'}"}
        pair = split_crypto_pair(text)
        if pair:
            base, quote = pair
            return {"kind": "crypto", "base": base, "quote": quote,
                    "canonical": f"{base}-{quote}"}

    # A slash form whose base is a KNOWN crypto asset and whose quote is a
    # stablecoin/fiat is crypto (`BTC/USD`), not FX.
    if "/" in text:
        base, _, quote = text.partition("/")
        if base in _KNOWN_CRYPTO_BASES and quote.upper() in _QUOTE_CURRENCIES:
            return {"kind": "crypto", "base": base, "quote": quote.upper(),
                    "canonical": f"{base}-{quote.upper()}"}

    if text.endswith(_FX_SUFFIX) or "/" in text:
        body = text[:-2] if text.endswith(_FX_SUFFIX) else text
        body = body.replace("/", "")
        if len(body) >= 6:
            return {"kind": "fx", "base": body[:3], "quote": body[3:6],
                    "canonical": f"{body[:3]}{body[3:6]}=X"}
        return {"kind": "fx", "base": body[:3], "quote": body[3:6] or None,
                "canonical": text}

    if mkt == "CRYPTO":
        if "-" in text:
            base, _, quote = text.partition("-")
            return {"kind": "crypto", "base": base, "quote": quote or "USD",
                    "canonical": f"{base}-{quote or 'USD'}"}
        pair = split_crypto_pair(text)
        if pair:
            base, quote = pair
            return {"kind": "crypto", "base": base, "quote": quote,
                    "canonical": f"{base}-{quote}"}

    # A dashed pair (`BTC-USD`) is crypto unless a market says otherwise.
    if "-" in text and mkt != "FX":
        base, _, quote = text.partition("-")
        if base in _KNOWN_CRYPTO_BASES and quote.upper() in _QUOTE_CURRENCIES:
            return {"kind": "crypto", "base": base, "quote": quote.upper(),
                    "canonical": f"{base}-{quote.upper()}"}

    pair = split_crypto_pair(text)
    if pair:
        base, quote = pair
        return {"kind": "crypto", "base": base, "quote": quote,
                "canonical": f"{base}-{quote}"}

    return {"kind": "equity", "canonical": text}


def split_exchange_suffix(raw: str) -> tuple[str, Optional[str]]:
    """`2330.TW` → ("2330", "TW"); an unknown suffix stays intact."""
    text = (raw or "").strip()
    dot = text.rfind(".")
    if dot <= 0 or dot == len(text) - 1:
        return text, None
    market = SUFFIX_TO_MARKET.get(text[dot:].lower())
    if not market:
        return text, None
    return text[:dot], market


def local_instrument(kind: dict[str, Any], requested: str) -> CanonicalInstrument:
    """Build a deterministic identity for an FX/crypto identifier.

    Used when the bridge has no vault row (FX/crypto are self-describing), so the
    request is not failed for a non-equity instrument.
    """
    if kind["kind"] == "crypto":
        base = str(kind.get("base") or requested).upper()
        quote = str(kind.get("quote") or "USD").upper()
        return CanonicalInstrument(
            instrument_id=f"CRYPTO:{base}-{quote}",
            symbol=f"{base}-{quote}",
            asset_type="crypto",
            market="CRYPTO",
            currency="USD" if quote in ("USDT", "USDC") else quote,
            base_asset=base,
            quote_asset=quote,
            provider_symbols=provider_symbols_for("crypto", base, quote, f"{base}-{quote}"),
            bridge_resolved=False,
        )
    base = str(kind.get("base") or requested[:3]).upper()
    quote = str(kind.get("quote") or requested[3:6]).upper()
    return CanonicalInstrument(
        instrument_id=f"FX:{base}{quote}",
        symbol=f"{base}{quote}",
        asset_type="fx",
        market="FX",
        currency=quote,
        base_asset=base,
        quote_asset=quote,
        provider_symbols=provider_symbols_for("fx", base, quote, f"{base}{quote}"),
        bridge_resolved=False,
    )


def provider_symbols_for(
    kind: str, base: str, quote: str, canonical: str
) -> dict[str, str]:
    """Map a canonical crypto/FX instrument to each provider's symbol form."""
    out: dict[str, str] = {}
    if kind == "crypto":
        b = base.upper()
        q = quote.upper()
        out["binance"] = f"{b}{_BINANCE_QUOTE.get(q, q)}"
        out["coingecko"] = b.lower()
        out["yahoo"] = f"{b}-{q}"
        out["crypto"] = b
    elif kind == "fx":
        bare = f"{base.upper()}{quote.upper()}"
        out["yahoo"] = f"{bare}=X"
        out["fx"] = bare
    else:
        out["yahoo"] = canonical
    return out


def from_bridge_payload(payload: dict[str, Any], requested: str) -> CanonicalInstrument:
    """Build a canonical instrument from a bridge identity payload.

    The bridge is authoritative; this lifts its fields without inventing any.
    When the bridge resolves an FX/crypto asset class but the requested symbol
    was a concatenated pair, the provider symbol map is filled so downstream
    adapters receive the right per-provider ticker.
    """
    asset_class = (payload.get("assetClass") or "").lower()
    symbol = str(payload.get("symbol") or requested).upper()
    market = payload.get("market") or payload.get("country")
    classification = classify_identifier(symbol, market)

    if asset_class in ("crypto",) or classification["kind"] == "crypto":
        base = classification.get("base") or symbol.split("-")[0]
        quote = classification.get("quote") or "USD"
        asset_type: AssetType = "crypto"
        psym = provider_symbols_for("crypto", base, quote, symbol)
    elif asset_class in ("fx",) or classification["kind"] == "fx":
        base = classification.get("base") or symbol[:3]
        quote = classification.get("quote") or symbol[3:6]
        asset_type = "fx"
        psym = provider_symbols_for("fx", base, quote, symbol)
    else:
        base = quote = None
        asset_type = _asset_type_from(asset_class, payload.get("securityType"))
        psym = provider_symbols_for("equity", "", "", symbol)

    return CanonicalInstrument(
        instrument_id=str(payload.get("instrumentId") or f"{market or '?'}:{symbol}"),
        symbol=symbol,
        asset_type=asset_type,
        market=str(market).upper() if market else None,
        exchange=payload.get("exchange"),
        mic=payload.get("mic"),
        currency=payload.get("currency"),
        base_asset=base,
        quote_asset=quote,
        name=payload.get("name"),
        security_type=payload.get("securityType"),
        provider_symbols=psym,
        resolved=True,
    )


def _asset_type_from(asset_class: str, security_type: Optional[str]) -> AssetType:
    ac = (asset_class or "").lower()
    mapping = {
        "equity": "equity", "stock": "equity", "etf": "etf", "fund": "fund",
        "crypto": "crypto", "fx": "fx", "commodity": "commodity",
        "index": "index", "derivative": "derivative", "bond": "bond",
        "debt": "bond", "option": "option", "future": "future", "macro": "macro",
    }
    if ac in mapping:
        return mapping[ac]  # type: ignore[return-value]
    st = (security_type or "").lower()
    if "etf" in st:
        return "etf"
    if "bond" in st or "note" in st:
        return "bond"
    if "option" in st:
        return "option"
    return "equity" if ac else "unknown"


__all__ = [
    "CanonicalInstrument",
    "ContractTerms",
    "classify_identifier",
    "from_bridge_payload",
    "local_instrument",
    "provider_symbols_for",
    "split_crypto_pair",
    "split_exchange_suffix",
]
