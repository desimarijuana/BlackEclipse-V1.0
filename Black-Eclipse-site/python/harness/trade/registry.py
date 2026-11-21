"""Broker-kind registry: the one place a new broker is declared.

A kind is a descriptor plus a factory. The descriptor is what the UI and the
agent can see; the factory is only called when a saved connection is actually
used. `list_kinds()` reports dependency availability without touching a broker.
"""

from __future__ import annotations

from typing import Any, Callable, Optional

from .adapter import BrokerAdapter
from .model import (
    KIND_ALPACA,
    KIND_BINANCE,
    KIND_BITFINEX,
    KIND_BITGET,
    KIND_BITSTAMP,
    KIND_BYBIT,
    KIND_COINBASE,
    KIND_COINCHECK,
    KIND_DERIBIT,
    KIND_GATEIO,
    KIND_IBKR,
    KIND_KRAKEN,
    KIND_MT4_BRIDGE,
    KIND_MT5,
    KIND_OANDA,
    KIND_OKX,
    KIND_TRADING212,
    KIND_TRADIER,
    KIND_ZERODHA,
    BrokerKind,
)

_FACTORIES: dict[str, Callable[[dict[str, Any]], BrokerAdapter]] = {}
_KINDS: dict[str, BrokerKind] = {}


def register_kind(
    kind: BrokerKind,
    factory: Callable[[dict[str, Any]], BrokerAdapter],
    *,
    replace: bool = False,
) -> None:
    if kind.id in _KINDS and not replace:
        raise ValueError(f"broker kind {kind.id!r} is already registered")
    _KINDS[kind.id] = kind
    _FACTORIES[kind.id] = factory


def get_kind(kind_id: str) -> BrokerKind:
    kind = _KINDS.get(str(kind_id or "").strip().lower())
    if kind is None:
        raise KeyError(
            f"unknown broker kind {kind_id!r}; Eclipse knows "
            f"{', '.join(sorted(_KINDS)) or 'none'}"
        )
    return kind


def list_kinds() -> list[dict[str, Any]]:
    """Every kind plus whether its dependency is installed on this host."""
    out: list[dict[str, Any]] = []
    for kind in _KINDS.values():
        payload = kind.to_dict()
        factory = _FACTORIES[kind.id]
        try:
            available, reason = factory({}).availability()
        except Exception as exc:  # noqa: BLE001 - availability must never raise
            available, reason = False, f"availability check failed: {exc}"
        payload["available"] = bool(available)
        payload["unavailableReason"] = None if available else (reason or "unavailable")
        out.append(payload)
    return out


def make_adapter(kind_id: str, config: Optional[dict[str, Any]] = None) -> BrokerAdapter:
    kind = get_kind(kind_id)
    return _FACTORIES[kind.id](dict(config or {}))


def _register_builtins() -> None:
    from .adapters.alpaca import AlpacaAdapter  # noqa: PLC0415 - avoids import cycles
    from .adapters.bitfinex import BitfinexAdapter  # noqa: PLC0415 - avoids import cycles
    from .adapters.bitget import BitgetAdapter  # noqa: PLC0415 - avoids import cycles
    from .adapters.bitstamp import BitstampAdapter  # noqa: PLC0415 - avoids import cycles
    from .adapters.bybit import BybitAdapter  # noqa: PLC0415 - avoids import cycles
    from .adapters.coinbase import CoinbaseAdapter  # noqa: PLC0415 - avoids import cycles
    from .adapters.coincheck import CoincheckAdapter  # noqa: PLC0415 - avoids import cycles
    from .adapters.deribit import DeribitAdapter  # noqa: PLC0415 - avoids import cycles
    from .adapters.binance import BinanceAdapter  # noqa: PLC0415 - avoids import cycles
    from .adapters.gateio import GateioAdapter  # noqa: PLC0415 - avoids import cycles
    from .adapters.ibkr import IBKRAdapter  # noqa: PLC0415 - avoids import cycles
    from .adapters.kraken import KrakenAdapter  # noqa: PLC0415 - avoids import cycles
    from .adapters.mt4_bridge import MT4BridgeAdapter  # noqa: PLC0415 - avoids import cycles
    from .adapters.mt5 import MT5Adapter  # noqa: PLC0415 - avoids import cycles
    from .adapters.oanda import OandaAdapter  # noqa: PLC0415 - avoids import cycles
    from .adapters.okx import OkxAdapter  # noqa: PLC0415 - avoids import cycles
    from .adapters.trading212 import Trading212Adapter  # noqa: PLC0415 - avoids import cycles
    from .adapters.tradier import TradierAdapter  # noqa: PLC0415 - avoids import cycles
    from .adapters.zerodha import ZerodhaAdapter  # noqa: PLC0415 - avoids import cycles

    register_kind(
        BrokerKind(
            id=KIND_ALPACA,
            label="Alpaca",
            auth="credentials",
            modes=("demo", "live"),
            asset_classes=("stocks", "etf", "crypto"),
            capabilities=("account", "positions", "orders", "quote"),
            execution=False,
            notes=(
                "Read-only. US equities/ETFs/crypto via Alpaca's REST API. "
                "Configure a credentialRef (a secret NAME) containing KEY:SECRET. "
                "Journal P&L is FIFO-computed from filled orders."
            ),
        ),
        AlpacaAdapter,
    )

    register_kind(
        BrokerKind(
            id=KIND_IBKR,
            label="Interactive Brokers",
            auth="credentials",
            modes=("demo", "live"),
            asset_classes=("stocks", "etf", "options", "futures", "fx"),
            capabilities=("account", "positions", "orders", "quote"),
            execution=False,
            notes=(
                "Read-only via the local Client Portal Gateway (CPAPI). "
                "credentialRef names the gateway session cookie. Journal P&L is "
                "FIFO-computed from executions."
            ),
        ),
        IBKRAdapter,
    )

    register_kind(
        BrokerKind(
            id=KIND_MT4_BRIDGE,
            label="MetaTrader 4 (bridge)",
            auth="bridge",
            modes=("demo", "live"),
            asset_classes=("fx", "cfd", "futures", "stocks", "metals"),
            capabilities=("account", "positions", "orders", "quote"),
            execution=False,
            notes=(
                "Read-only. Attaches to a local HTTP bridge that already runs "
                "next to MT4; Eclipse never stores a password or places an order "
                "through this adapter."
            ),
        ),
        MT4BridgeAdapter,
    )

    register_kind(
        BrokerKind(
            id=KIND_MT5,
            label="MetaTrader 5",
            auth="attach",
            modes=("demo", "live"),
            asset_classes=("fx", "cfd", "futures", "stocks", "crypto", "metals"),
            capabilities=("account", "positions", "orders", "quote"),
            execution=True,
            execution_modes=("demo", "live"),
            notes=(
                "Attaches to a running, logged-in terminal64.exe over local IPC. "
                "Demo execution is always available; live execution requires a "
                "time-boxed arm, a positive maxMargin and a non-zero magic."
            ),
        ),
        MT5Adapter,
    )

    register_kind(
        BrokerKind(
            id=KIND_TRADING212,
            label="Trading212",
            auth="credentials",
            modes=("demo", "live"),
            asset_classes=("stocks", "etf"),
            # No `quote`: the public API has no quote endpoint, so the capability
            # is declared absent rather than faked. No execution either.
            capabilities=("account", "positions", "orders"),
            execution=False,
            notes=(
                "Read-only. Equities/ETFs via Trading212's public REST API "
                "(cash, portfolio, open orders). No quote endpoint and no fill "
                "history: quote() raises TRADING212_QUOTE_UNSUPPORTED and the "
                "journal never invents a fill. credentialRef names the env var or "
                "secret holding the API key."
            ),
        ),
        Trading212Adapter,
    )

    register_kind(
        BrokerKind(
            id=KIND_ZERODHA,
            label="Zerodha Kite",
            auth="credentials",
            modes=("live",),
            asset_classes=("stocks", "etf", "futures", "options"),
            capabilities=("account", "positions", "orders", "quote"),
            execution=False,
            notes=(
                "Read-only. NSE/BSE equities and F&O via Kite Connect's REST API "
                "(profile, margins, net positions, orders, quotes). Quotes take "
                "EXCHANGE:SYMBOL; the ticker stream is not implemented. "
                "credentialRef names the env var or secret holding "
                "`API_KEY:ACCESS_TOKEN`."
            ),
        ),
        ZerodhaAdapter,
    )

    register_kind(
        BrokerKind(
            id=KIND_TRADIER,
            label="Tradier",
            auth="credentials",
            modes=("live", "demo"),
            asset_classes=("stocks", "etf", "options"),
            capabilities=("account", "positions", "orders", "quote"),
            execution=False,
            notes=(
                "Read-only. US equities/ETFs/options via Tradier's brokerage REST "
                "API (balances, positions, orders, snapshot quotes). Sandbox is a "
                "baseUrl, not a mode flag. Positions are the broker's rows; the "
                "adapter does not mark to market. credentialRef names the env var "
                "or secret holding the access token."
            ),
        ),
        TradierAdapter,
    )

    register_kind(
        BrokerKind(
            id=KIND_OKX,
            label="OKX",
            auth="credentials",
            modes=("live",),
            asset_classes=("crypto",),
            capabilities=("account", "positions", "orders", "quote"),
            execution=False,
            notes=(
                "Read-only. OKX spot/perpetuals via the v5 REST API (balance, "
                "positions, pending orders, ticker snapshot). HMAC-signed; "
                "credentialRef names an env var or secret holding "
                "`API_KEY:SECRET:PASSPHRASE`. No order placement and no ticker "
                "stream."
            ),
        ),
        OkxAdapter,
    )

    register_kind(
        BrokerKind(
            id=KIND_BINANCE,
            label="Binance (spot)",
            auth="credentials",
            modes=("live",),
            asset_classes=("crypto",),
            capabilities=("account", "positions", "orders", "quote"),
            execution=False,
            notes=(
                "Read-only. Binance spot via v3 REST (account balances, open "
                "orders, ticker price). `positions` are non-zero spot balances, "
                "NOT margin positions, and are not marked to market; "
                "credentialRef names an env var or secret holding `KEY:SECRET`. "
                "No order placement and no stream."
            ),
        ),
        BinanceAdapter,
    )

    register_kind(
        BrokerKind(
            id=KIND_KRAKEN,
            label="Kraken",
            auth="credentials",
            modes=("live",),
            asset_classes=("crypto",),
            capabilities=("account", "positions", "orders", "quote"),
            execution=False,
            notes=(
                "Read-only. Kraken spot via the private/public REST API (balances, "
                "open orders, ticker). HMAC-SHA512 signed; credentialRef names an "
                "env var or secret holding `KEY:SECRET` (base64 secret). "
                "`positions` are non-zero spot balances, not margin positions and "
                "not marked to market. No order placement and no stream."
            ),
        ),
        KrakenAdapter,
    )

    register_kind(
        BrokerKind(
            id=KIND_COINBASE,
            label="Coinbase Exchange",
            auth="credentials",
            modes=("live",),
            asset_classes=("crypto",),
            capabilities=("account", "positions", "orders", "quote"),
            execution=False,
            notes=(
                "Read-only. Coinbase Exchange via REST (balances, open orders, "
                "product ticker). HMAC-SHA256 signature: credentialRef names an env "
                "var or secret holding `KEY:SECRET:PASSPHRASE`. `positions` are "
                "non-zero spot balances, not margin positions and not marked to "
                "market. No order placement and no stream."
            ),
        ),
        CoinbaseAdapter,
    )

    register_kind(
        BrokerKind(
            id=KIND_BYBIT,
            label="Bybit (unified)",
            auth="credentials",
            modes=("live",),
            asset_classes=("crypto", "derivatives"),
            capabilities=("account", "positions", "orders", "quote"),
            execution=False,
            notes=(
                "Read-only. Bybit v5 REST: unified wallet balance, linear positions "
                "(size, avg entry, mark, uPnL), real-time orders, spot tickers. "
                "Signature is HMAC-SHA256 over ts+key+recvWindow+query; credentialRef "
                "names an env var or secret holding `KEY:SECRET`. No order placement "
                "and no stream."
            ),
        ),
        BybitAdapter,
    )

    register_kind(
        BrokerKind(
            id=KIND_DERIBIT,
            label="Deribit (derivatives)",
            auth="credentials",
            modes=("live",),
            asset_classes=("crypto", "derivatives", "options"),
            capabilities=("account", "positions", "orders", "quote"),
            execution=False,
            notes=(
                "Read-only. Deribit v2 JSON-RPC over GET: account summary per "
                "currency, positions, open orders and instrument tickers. "
                "Signature is HMAC-SHA256 over ts/nonce/data/query; credentialRef "
                "names an env var or secret holding `CLIENT_ID:CLIENT_SECRET`. "
                "Account equity is per currency and is reported as such. No order "
                "placement and no stream."
            ),
        ),
        DeribitAdapter,
    )

    register_kind(
        BrokerKind(
            id=KIND_OANDA,
            label="OANDA v20 (FX/CFD)",
            auth="credentials",
            modes=("live",),
            asset_classes=("fx", "cfd", "metals"),
            capabilities=("account", "positions", "orders", "quote"),
            execution=False,
            notes=(
                "Read-only. OANDA v20 REST: account summary (NAV, margin), "
                "openPositions (long and short halves reported separately), "
                "pendingOrders and pricing. Bearer-token auth, no request signing. "
                "accountId is configured or discovered from /v3/accounts; a missing "
                "id is a refusal, never a default. No order placement and no stream."
            ),
        ),
        OandaAdapter,
    )

    register_kind(
        BrokerKind(
            id=KIND_BITGET,
            label="Bitget v2",
            auth="credentials",
            modes=("live",),
            asset_classes=("crypto", "derivatives"),
            capabilities=("account", "positions", "orders", "quote"),
            execution=False,
            notes=(
                "Read-only. Bitget v2 REST: spot balances, USDT-margined positions, "
                "unfilled spot orders, spot tickers. Signature is base64"
                "(HMAC-SHA256(ts+method+path+body)) plus ACCESS-PASSPHRASE; "
                "credentialRef names an env var or secret holding "
                "`KEY:SECRET:PASSPHRASE`. No order placement and no stream."
            ),
        ),
        BitgetAdapter,
    )

    register_kind(
        BrokerKind(
            id=KIND_GATEIO,
            label="Gate.io v4",
            auth="credentials",
            modes=("live",),
            asset_classes=("crypto", "derivatives"),
            capabilities=("account", "positions", "orders", "quote"),
            execution=False,
            notes=(
                "Read-only. Gate.io v4 REST: spot balances, USDT-settled perpetual "
                "positions, spot open orders and tickers. Signature is hex "
                "HMAC-SHA512 over method/path/query/sha512(body)/timestamp; "
                "credentialRef names an env var or secret holding `KEY:SECRET`. "
                "No order placement and no stream."
            ),
        ),
        GateioAdapter,
    )

    register_kind(
        BrokerKind(
            id=KIND_BITSTAMP,
            label="Bitstamp v2",
            auth="credentials",
            modes=("live",),
            asset_classes=("crypto",),
            capabilities=("account", "positions", "orders", "quote"),
            execution=False,
            notes=(
                "Read-only. Bitstamp v2 REST: balances, all open orders, tickers. "
                "Auth travels in the FORM BODY (key/nonce/signature), not headers; "
                "signature is hex HMAC-SHA256 over nonce+customer_id+api_key, so "
                "credentialRef names an env var or secret holding "
                "`KEY:SECRET:CUSTOMER_ID`. `positions` are non-zero spot balances, "
                "not marked to market. No order placement and no stream."
            ),
        ),
        BitstampAdapter,
    )

    register_kind(
        BrokerKind(
            id=KIND_COINCHECK,
            label="Coincheck",
            auth="credentials",
            modes=("live",),
            asset_classes=("crypto",),
            capabilities=("account", "positions", "orders", "quote"),
            execution=False,
            notes=(
                "Read-only. Coincheck REST: balances, open orders, tickers. "
                "Signature is hex HMAC-SHA256 over nonce + the FULL request URL "
                "(scheme and query included), sent as ACCESS-KEY/ACCESS-NONCE/"
                "ACCESS-SIGN; credentialRef names an env var or secret holding "
                "`KEY:SECRET`. `positions` are non-zero spot balances, not marked "
                "to market. No order placement and no stream."
            ),
        ),
        CoincheckAdapter,
    )

    register_kind(
        BrokerKind(
            id=KIND_BITFINEX,
            label="Bitfinex v2",
            auth="credentials",
            modes=("live",),
            asset_classes=("crypto", "derivatives"),
            capabilities=("account", "positions", "orders", "quote"),
            execution=False,
            notes=(
                "Read-only. Bitfinex v2 REST: wallets, positions, orders, tickers. "
                "Signature is hex HMAC-SHA384 over the SIGNED path + nonce + body, "
                "sent as bfx-apikey/bfx-nonce/bfx-signature; credentialRef names an "
                "env var or secret holding `KEY:SECRET`. v2 answers with positional "
                "arrays, so fields are read by documented index. No order placement "
                "and no stream."
            ),
        ),
        BitfinexAdapter,
    )


_register_builtins()

__all__ = ["get_kind", "list_kinds", "make_adapter", "register_kind"]
