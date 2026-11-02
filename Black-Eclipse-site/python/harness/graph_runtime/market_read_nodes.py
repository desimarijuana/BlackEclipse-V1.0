"""Gateway-backed market-read nodes.

These complete the read surface of Graph Studio: quote/history (in
``finance_nodes.py``) were the first two gateway reads, and this module adds the
remaining capabilities the EXISTING market gateway already implements.

Hard rules, identical to ``finance_nodes.py``:

  1. **One data path.** Every executor calls ``harness.market.gateway`` through
     the same helper the quote node uses. There is no second provider router.
  2. **Provenance on every payload.** Each node returns a ``provenance`` object
     built from the record's own ``meta`` (provider, freshness, quality, as-of,
     retrieval time). A field the provider did not report stays ``None``.
  3. **Honest failure.** A gateway error is a node failure with the gateway's
     code and message — never a zero, a guessed price or a fabricated book.

All nodes are pure READS (`market.read`), so a test run may execute them.
"""

from __future__ import annotations

from typing import Any, Optional

from ..persistence import now_iso
from .finance_nodes import (
    market_gateway_provenance,
    market_gateway_result,
    require_market_gateway,
    run_market_gateway,
)
from .model import ExecutionMode, PortDef, PortType, SideEffect
from .registry import ConfigField, NodeDef, NodeExecContext

_ALL = tuple(ExecutionMode)
_FRESHNESS = ("realtime", "intraday", "daily", "slow", "any")


# ── Small config readers ────────────────────────────────────────────────────


def _text(context: NodeExecContext, key: str, default: str = "") -> str:
    return str(context.config.get(key) or default).strip()


def _opt_text(context: NodeExecContext, key: str) -> Optional[str]:
    value = _text(context, key)
    return value or None


def _whole(context: NodeExecContext, key: str, default: int) -> int:
    try:
        return int(context.config.get(key, default))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{key} must be a whole number") from exc


def _symbol(context: NodeExecContext) -> str:
    symbol = str(
        context.inputs.get("symbol") or context.config.get("symbol") or ""
    ).strip().upper()
    if not symbol:
        raise ValueError("no symbol: wire the symbol input or set the node's symbol")
    return symbol


# ── Shared execution seam ───────────────────────────────────────────────────


def _call(context: NodeExecContext, method: str, args: dict[str, Any]) -> dict[str, Any]:
    """Call one gateway method and normalize its record.

    The gateway's own structured error is surfaced verbatim (``code: message``)
    so a graph can branch on the failure instead of receiving a placeholder.
    """
    gateway = require_market_gateway()
    fn = getattr(gateway, method, None)
    if not callable(fn):
        raise ValueError(f"the market data gateway does not support {method}")
    try:
        result = run_market_gateway(lambda: fn(**args))
    except ValueError:
        raise
    except Exception as exc:  # noqa: BLE001 - a gateway failure is node data
        raise ValueError(f"{method} unavailable: {exc}") from exc
    return market_gateway_result(result)


_SUMMARY_FIELDS: dict[str, tuple[str, ...]] = {
    "instrument": ("symbol", "name", "asset_type", "market", "currency", "exchange"),
    "orderbook": ("best_bid", "best_ask", "spread", "spread_bps", "imbalance", "bid_depth", "ask_depth"),
    "trades": ("aggressive_buy_volume", "aggressive_sell_volume", "imbalance"),
    "volume": ("total_volume", "average_volume", "relative_volume", "window"),
    "market_cap": ("market_cap", "price", "shares_outstanding", "shares_basis"),
    "fx": ("base", "quote", "rate", "mid", "cross"),
    "options": ("underlying", "underlying_price", "expirations", "contracts"),
    "bond": ("price", "yield_", "yield", "coupon", "maturity", "duration", "modified_duration", "rating"),
    "funding": ("funding_rate", "annualized_funding", "next_funding_time"),
    "open_interest": ("open_interest", "open_interest_usd", "oi_change_pct", "window"),
    "supply": ("circulating_supply", "total_supply", "max_supply", "fdv"),
    "tvl": ("protocol", "chain", "tvl_usd", "change_24h_pct"),
    "onchain": ("address", "chain", "native_balance", "tx_count", "latest_block"),
    "liquidations": ("total_usd", "long_usd", "short_usd", "window", "exchange"),
    "long_short": ("long_percent", "short_percent", "long_short_ratio", "exchange", "interval"),
}


def _summary(kind: str, payload: dict[str, Any], provenance: dict[str, Any]) -> dict[str, Any]:
    """A small, readable digest for the node card and the Output tab.

    The full record stays on the value port; this is only a convenience so a
    user sees `best_bid/spread` or `funding_rate` instead of a raw JSON blob.
    Missing fields are omitted (never zero-filled).
    """
    summary: dict[str, Any] = {
        "symbol": provenance.get("symbol"),
        "provider": provenance.get("provider"),
        "asOf": provenance.get("asOf"),
    }
    for key in _SUMMARY_FIELDS.get(kind, ()):
        value = payload.get(key)
        if value is not None and key != "yield":  # `yield_` wins when both exist
            summary[key] = value
    if kind == "trades":
        summary["trades"] = len(payload.get("trades") or [])
        trades = payload.get("trades") or []
        if trades and isinstance(trades[-1], dict):
            summary["lastPrice"] = trades[-1].get("price")
    if kind == "options":
        summary["expirations"] = len(payload.get("expirations") or [])
        summary["contracts"] = len(payload.get("contracts") or [])
        contracts = payload.get("contracts") or []
        summary["greeks"] = any(
            isinstance(item, dict) and item.get("greeks_source") for item in contracts
        )
    return {key: value for key, value in summary.items() if value is not None}


def _read(
    context: NodeExecContext,
    *,
    method: str,
    kind: str,
    args: dict[str, Any],
    result_port: str,
    symbol: Optional[str] = None,
) -> dict[str, Any]:
    payload = _call(context, method, args)
    provenance = market_gateway_provenance(payload, kind=kind, symbol=symbol)
    label = provenance.get("symbol") or symbol or kind
    context.emit(f"{label} {kind} from {provenance.get('provider') or 'gateway'}")
    return {
        result_port: payload,
        "summary": _summary(kind, payload, provenance),
        "provenance": provenance,
    }


# ── Executors ───────────────────────────────────────────────────────────────


def exec_instrument(context: NodeExecContext) -> dict[str, Any]:
    symbol = _symbol(context)
    gateway = require_market_gateway()
    try:
        instrument, error = run_market_gateway(
            lambda: gateway.resolve_instrument(symbol, _opt_text(context, "market"))
        )
    except ValueError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"instrument lookup unavailable: {exc}") from exc
    if error is not None:
        code = getattr(error, "code", "error")
        message = getattr(error, "message", str(error))
        raise ValueError(f"{code}: {message}")
    if instrument is None:
        raise ValueError(f"no instrument resolved for {symbol}")
    payload = instrument.to_dict() if hasattr(instrument, "to_dict") else dict(instrument)
    bridge_resolved = bool(
        getattr(instrument, "bridge_resolved", payload.get("bridgeResolved", False))
    )
    provenance = {
        "kind": "instrument",
        "provider": None,
        "symbol": payload.get("symbol") or symbol,
        "assetType": payload.get("assetType"),
        "asOf": None,
        "retrievedAt": now_iso(),
        "bridgeResolved": bridge_resolved,
        "resolved": bool(payload.get("resolved", True)),
    }
    context.emit(
        f"{provenance['symbol']} resolves as {payload.get('assetType') or 'unknown'}"
    )
    summary = {
        key: value
        for key, value in {
            "symbol": payload.get("symbol") or symbol,
            "name": payload.get("name"),
            "assetType": payload.get("assetType"),
            "market": payload.get("market"),
            "currency": payload.get("currency"),
            "resolved": payload.get("resolved"),
        }.items()
        if value is not None
    }
    return {"instrument": payload, "summary": summary, "provenance": provenance}


def exec_orderbook(context: NodeExecContext) -> dict[str, Any]:
    return _read(
        context,
        method="get_orderbook",
        kind="orderbook",
        args={
            "symbol": _symbol(context),
            "market": _opt_text(context, "market"),
            "depth": _whole(context, "depth", 20),
            "freshness": _text(context, "freshness", "realtime"),
        },
        result_port="book",
    )


def exec_trades(context: NodeExecContext) -> dict[str, Any]:
    return _read(
        context,
        method="get_trades",
        kind="trades",
        args={
            "symbol": _symbol(context),
            "market": _opt_text(context, "market"),
            "limit": _whole(context, "limit", 100),
            "start": _opt_text(context, "start"),
            "end": _opt_text(context, "end"),
            "freshness": _text(context, "freshness", "realtime"),
        },
        result_port="trades",
    )


def exec_volume(context: NodeExecContext) -> dict[str, Any]:
    return _read(
        context,
        method="get_volume",
        kind="volume",
        args={
            "symbol": _symbol(context),
            "market": _opt_text(context, "market"),
            "window": _text(context, "window", "1d"),
            "freshness": _text(context, "freshness", "intraday"),
        },
        result_port="volume",
    )


def exec_market_cap(context: NodeExecContext) -> dict[str, Any]:
    return _read(
        context,
        method="get_market_cap",
        kind="market_cap",
        args={
            "symbol": _symbol(context),
            "market": _opt_text(context, "market"),
            "freshness": _text(context, "freshness", "daily"),
        },
        result_port="marketCap",
    )


def exec_fx_rate(context: NodeExecContext) -> dict[str, Any]:
    pair = str(
        context.inputs.get("symbol") or context.config.get("symbol") or ""
    ).strip().upper()
    base = _opt_text(context, "base")
    quote = _opt_text(context, "quote")
    if not pair and not (base and quote):
        raise ValueError("set an fx pair, or both a base and a quote currency")
    return _read(
        context,
        method="get_fx_rate",
        kind="fx",
        args={
            "base": base,
            "quote": quote,
            "symbol": pair or None,
            "freshness": _text(context, "freshness", "realtime"),
        },
        result_port="rate",
        symbol=pair or (f"{base}{quote}" if base and quote else None),
    )


def exec_options_chain(context: NodeExecContext) -> dict[str, Any]:
    return _read(
        context,
        method="get_options_chain",
        kind="options",
        args={
            "symbol": _symbol(context),
            "market": _opt_text(context, "market"),
            "expiration": _opt_text(context, "expiration"),
            "greeks": bool(context.config.get("greeks", False)),
            "freshness": _text(context, "freshness", "daily"),
        },
        result_port="chain",
    )


def exec_bond(context: NodeExecContext) -> dict[str, Any]:
    return _read(
        context,
        method="get_bond_data",
        kind="bond",
        args={
            "symbol": _symbol(context),
            "market": _opt_text(context, "market"),
            "series_type": _opt_text(context, "seriesType"),
            "freshness": _text(context, "freshness", "slow"),
        },
        result_port="bond",
    )


def exec_funding_rate(context: NodeExecContext) -> dict[str, Any]:
    return _read(
        context,
        method="get_funding_rate",
        kind="funding",
        args={
            "symbol": _symbol(context),
            "market": _opt_text(context, "market"),
            "exchange": _opt_text(context, "exchange"),
            "history": _whole(context, "history", 0),
            "freshness": _text(context, "freshness", "realtime"),
        },
        result_port="funding",
    )


def exec_open_interest(context: NodeExecContext) -> dict[str, Any]:
    return _read(
        context,
        method="get_open_interest",
        kind="open_interest",
        args={
            "symbol": _symbol(context),
            "market": _opt_text(context, "market"),
            "exchange": _opt_text(context, "exchange"),
            "window": _text(context, "window", "24h"),
            "freshness": _text(context, "freshness", "intraday"),
        },
        result_port="openInterest",
    )


def exec_supply(context: NodeExecContext) -> dict[str, Any]:
    return _read(
        context,
        method="get_supply",
        kind="supply",
        args={
            "symbol": _symbol(context),
            "market": _opt_text(context, "market"),
            "freshness": _text(context, "freshness", "daily"),
        },
        result_port="supply",
    )


def exec_tvl(context: NodeExecContext) -> dict[str, Any]:
    return _read(
        context,
        method="get_tvl",
        kind="tvl",
        args={
            "symbol": _symbol(context),
            "market": _opt_text(context, "market"),
            "chain": _opt_text(context, "chain"),
            "freshness": _text(context, "freshness", "daily"),
        },
        result_port="tvl",
    )


def exec_onchain(context: NodeExecContext) -> dict[str, Any]:
    address = str(
        context.inputs.get("address") or context.config.get("address") or ""
    ).strip()
    if not address:
        raise ValueError("no address: wire the address input or set the node's address")
    return _read(
        context,
        method="get_onchain_metric",
        kind="onchain",
        args={
            "address": address,
            "chain": _text(context, "chain", "ethereum"),
            "freshness": _text(context, "freshness", "intraday"),
        },
        result_port="metrics",
    )


def exec_liquidations(context: NodeExecContext) -> dict[str, Any]:
    return _read(
        context,
        method="get_liquidations",
        kind="liquidations",
        args={
            "symbol": _symbol(context),
            "market": _opt_text(context, "market"),
            "exchange": _opt_text(context, "exchange"),
            "window": _text(context, "window", "24h"),
            "freshness": _text(context, "freshness", "intraday"),
        },
        result_port="liquidations",
    )


def exec_long_short_ratio(context: NodeExecContext) -> dict[str, Any]:
    return _read(
        context,
        method="get_long_short_ratio",
        kind="long_short",
        args={
            "symbol": _symbol(context),
            "market": _opt_text(context, "market"),
            "exchange": _opt_text(context, "exchange"),
            "interval": _text(context, "interval", "1h"),
            "limit": _whole(context, "limit", 48),
            "freshness": _text(context, "freshness", "intraday"),
        },
        result_port="ratio",
    )


# ── Definitions ─────────────────────────────────────────────────────────────


def _port(port_id: str, name: str, port_type: PortType, **kwargs: Any) -> PortDef:
    return PortDef(id=port_id, name=name, type=port_type, **kwargs)


def _symbol_inputs() -> tuple[PortDef, ...]:
    return (_port("symbol", "Symbol", PortType.STRING, optional=True),)


def _read_outputs(value_id: str, value_name: str) -> tuple[PortDef, ...]:
    return (
        _port(value_id, value_name, PortType.OBJECT),
        # A compact digest so the node card / Output tab is readable.
        _port("summary", "Summary", PortType.OBJECT),
        _port("provenance", "Provenance", PortType.EVIDENCE),
    )


def _symbol_fields(*extra: ConfigField) -> tuple[ConfigField, ...]:
    return (
        ConfigField("symbol", "string", "", max_length=40),
        ConfigField("market", "string", "", max_length=20),
        *extra,
    )


def _freshness(default: str) -> ConfigField:
    return ConfigField("freshness", "enum", default, enum=_FRESHNESS)


def _gateway_node(
    *,
    type: str,
    label: str,
    description: str,
    executor: Any,
    inputs: tuple[PortDef, ...],
    outputs: tuple[PortDef, ...],
    config_fields: tuple[ConfigField, ...],
    docs: str,
) -> NodeDef:
    return NodeDef(
        type=type,
        version="1.0.0",
        label=label,
        category="finance",
        inputs=inputs,
        outputs=outputs,
        config_fields=config_fields,
        capabilities=("market.read",),
        side_effects=SideEffect.READ,
        allowed_modes=_ALL,
        executor=executor,
        metadata={"docs": docs},
    )


def build_market_read_nodes() -> list[NodeDef]:
    """The remaining gateway read capabilities, all with real executors."""
    return [
        _gateway_node(
            type="finance.instrument",
            label="Instrument",
            description="Resolves a symbol to its canonical identity through the data bridge.",
            executor=exec_instrument,
            inputs=_symbol_inputs(),
            outputs=_read_outputs("instrument", "Instrument"),
            config_fields=(
                ConfigField("symbol", "string", "", max_length=40),
                ConfigField("market", "string", "", max_length=20),
            ),
            docs=(
                "The bridge's instrument master is authoritative; an unknown symbol "
                "fails instead of guessing an identity. FX and crypto identities are "
                "self-describing and resolve without a vault row."
            ),
        ),
        _gateway_node(
            type="finance.orderbook",
            label="Order book",
            description="Reads the top-of-book depth and spread through the market gateway.",
            executor=exec_orderbook,
            inputs=_symbol_inputs(),
            outputs=_read_outputs("book", "Order book"),
            config_fields=_symbol_fields(
                ConfigField("depth", "integer", 20, minimum=1, maximum=200),
                _freshness("realtime"),
            ),
            docs="Bids/asks plus derived spread and imbalance. A missing book is an explicit failure.",
        ),
        _gateway_node(
            type="finance.trades",
            label="Trade tape",
            description="Reads recent trades (with provider or inferred side) from the gateway.",
            executor=exec_trades,
            inputs=_symbol_inputs(),
            outputs=_read_outputs("trades", "Trades"),
            config_fields=_symbol_fields(
                ConfigField("limit", "integer", 100, minimum=1, maximum=1_000),
                ConfigField("start", "string", "", max_length=40),
                ConfigField("end", "string", "", max_length=40),
                _freshness("realtime"),
            ),
            docs="Aggressor side is labelled `side_inferred` when Eclipse inferred it; never presented as provider data.",
        ),
        _gateway_node(
            type="finance.volume",
            label="Volume stats",
            description="Reads windowed volume with native/derived field labels.",
            executor=exec_volume,
            inputs=_symbol_inputs(),
            outputs=_read_outputs("volume", "Volume"),
            config_fields=_symbol_fields(
                ConfigField("window", "string", "1d", max_length=20),
                _freshness("intraday"),
            ),
            docs="Relative volume and averages are marked derived when the provider did not supply them.",
        ),
        _gateway_node(
            type="finance.market_cap",
            label="Market cap",
            description="Reads market capitalisation and the share basis it uses.",
            executor=exec_market_cap,
            inputs=_symbol_inputs(),
            outputs=_read_outputs("marketCap", "Market cap"),
            config_fields=_symbol_fields(_freshness("daily")),
            docs="`shares_basis` states basic/diluted/current/float — a cap is never mixed silently.",
        ),
        _gateway_node(
            type="finance.fx_rate",
            label="FX rate",
            description="Reads a foreign-exchange rate (pair, or base + quote).",
            executor=exec_fx_rate,
            inputs=_symbol_inputs(),
            outputs=_read_outputs("rate", "FX rate"),
            config_fields=(
                ConfigField("symbol", "string", "", max_length=40),
                ConfigField("base", "string", "", max_length=8),
                ConfigField("quote", "string", "", max_length=8),
                _freshness("realtime"),
            ),
            docs="A cross rate is labelled `cross` with its derivation; it is never passed off as a native quote.",
        ),
        _gateway_node(
            type="finance.options_chain",
            label="Options chain",
            description="Reads an options chain; Greeks are provider-sourced or calculated, never zero-filled.",
            executor=exec_options_chain,
            inputs=_symbol_inputs(),
            outputs=_read_outputs("chain", "Chain"),
            config_fields=_symbol_fields(
                ConfigField("expiration", "string", "", max_length=20),
                ConfigField("greeks", "boolean", False),
                _freshness("daily"),
            ),
            docs="With `greeks` on, the gateway enriches with Black-Scholes and labels `greeks_source=calculated`.",
        ),
        _gateway_node(
            type="finance.bond",
            label="Bond data",
            description="Reads price/yield and derives duration and convexity when inputs exist.",
            executor=exec_bond,
            inputs=_symbol_inputs(),
            outputs=_read_outputs("bond", "Bond"),
            config_fields=_symbol_fields(
                ConfigField("seriesType", "string", "", max_length=20),
                _freshness("slow"),
            ),
            docs="A resolve miss does not refuse a yield request; duration is derived only from supplied inputs and labelled.",
        ),
        _gateway_node(
            type="finance.funding_rate",
            label="Funding rate",
            description="Reads a perpetual funding rate, optionally with its history.",
            executor=exec_funding_rate,
            inputs=_symbol_inputs(),
            outputs=_read_outputs("funding", "Funding"),
            config_fields=_symbol_fields(
                ConfigField("exchange", "string", "", max_length=20),
                ConfigField("history", "integer", 0, minimum=0, maximum=500),
                _freshness("realtime"),
            ),
            docs="An annualized figure is always derived and labelled; the raw per-interval rate is preserved.",
        ),
        _gateway_node(
            type="finance.open_interest",
            label="Open interest",
            description="Reads futures open interest with native/derived field labels.",
            executor=exec_open_interest,
            inputs=_symbol_inputs(),
            outputs=_read_outputs("openInterest", "Open interest"),
            config_fields=_symbol_fields(
                ConfigField("exchange", "string", "", max_length=20),
                ConfigField("window", "string", "24h", max_length=20),
                _freshness("intraday"),
            ),
            docs="Open interest in contracts and USD; a change figure is labelled derived when computed here.",
        ),
        _gateway_node(
            type="finance.supply",
            label="Crypto supply",
            description="Reads circulating/total/max supply and FDV for a crypto asset.",
            executor=exec_supply,
            inputs=_symbol_inputs(),
            outputs=_read_outputs("supply", "Supply"),
            config_fields=_symbol_fields(_freshness("daily")),
            docs="Crypto only: a non-crypto instrument is an explicit unsupported-capability failure.",
        ),
        _gateway_node(
            type="finance.tvl",
            label="DeFi TVL",
            description="Reads total value locked for a protocol or chain.",
            executor=exec_tvl,
            inputs=_symbol_inputs(),
            outputs=_read_outputs("tvl", "TVL"),
            config_fields=_symbol_fields(
                ConfigField("chain", "string", "", max_length=40),
                _freshness("daily"),
            ),
            docs="Per-chain figures are kept as supplied and never silently summed into the headline value.",
        ),
        _gateway_node(
            type="finance.onchain",
            label="On-chain metrics",
            description="Reads account-scoped on-chain metrics for an EVM address.",
            executor=exec_onchain,
            inputs=(_port("address", "Address", PortType.STRING, optional=True),),
            outputs=_read_outputs("metrics", "Metrics"),
            config_fields=(
                ConfigField("address", "string", "", max_length=100),
                ConfigField("chain", "string", "ethereum", max_length=30),
                _freshness("intraday"),
            ),
            docs="The address is the identity; a malformed address or unknown chain is reported, never zero-filled.",
        ),
        _gateway_node(
            type="finance.liquidations",
            label="Liquidations",
            description="Reads forced-liquidation totals for a coin on one futures exchange.",
            executor=exec_liquidations,
            inputs=_symbol_inputs(),
            outputs=_read_outputs("liquidations", "Liquidations"),
            config_fields=_symbol_fields(
                ConfigField("exchange", "string", "", max_length=20),
                ConfigField("window", "string", "24h", max_length=20),
                _freshness("intraday"),
            ),
            docs="Per-window breakdowns stay as supplied; the headline is the requested window, not a sum across windows.",
        ),
        _gateway_node(
            type="finance.long_short_ratio",
            label="Long/short ratio",
            description="Reads the global long/short account ratio history for a futures pair.",
            executor=exec_long_short_ratio,
            inputs=_symbol_inputs(),
            outputs=_read_outputs("ratio", "Ratio"),
            config_fields=_symbol_fields(
                ConfigField("exchange", "string", "", max_length=20),
                ConfigField("interval", "string", "1h", max_length=10),
                ConfigField("limit", "integer", 48, minimum=1, maximum=500),
                _freshness("intraday"),
            ),
            docs="Account-ratio history from the futures provider; the series is returned as supplied.",
        ),
    ]


__all__ = [
    "build_market_read_nodes",
    "exec_instrument",
    "exec_orderbook",
    "exec_trades",
    "exec_volume",
    "exec_market_cap",
    "exec_fx_rate",
    "exec_options_chain",
    "exec_bond",
    "exec_funding_rate",
    "exec_open_interest",
    "exec_supply",
    "exec_tvl",
    "exec_onchain",
    "exec_liquidations",
    "exec_long_short_ratio",
]
