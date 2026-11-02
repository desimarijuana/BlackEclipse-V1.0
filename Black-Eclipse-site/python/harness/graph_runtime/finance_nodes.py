"""Finance + quant node executors (Phase 5).

Two hard rules shape this module:

  1. **Reuse the existing data path.** Bars come from the runtime's persistent
     series store (`harness/market/series_store.py`) — the same vault the
     research tools fill. There is no second ingestion path, and the node never
     invents a row: an empty vault is an HONEST failure that says how to fix it.
  2. **Reuse the tested math.** Indicator values come from
     `harness/quant/indicators.py` (causal, independently tested). This module
     only adapts payloads, never re-implements a formula.

Every market payload carries provenance (`provider`, `interval`, `adjusted`,
`rows`, `asOf`, `retrievedAt`) so a graph can label freshness instead of
implying live data.
"""

from __future__ import annotations

import asyncio
import datetime as _dt
import math
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Optional

from ..persistence import now_iso
from .model import ExecutionMode, PortDef, PortType, SideEffect
from .registry import ConfigField, NodeDef, NodeExecContext

try:  # numpy ships with the quant stack; the runtime still boots without it.
    import numpy as np

    _NUMPY_OK = True
except Exception:  # noqa: BLE001 - a trimmed install is a supported state
    np = None  # type: ignore[assignment]
    _NUMPY_OK = False

_ALL = tuple(ExecutionMode)

MAX_LOOKBACK = 5_000


class SeriesUnavailable(RuntimeError):
    """No bars could be read. The message is user-facing and actionable."""


# ── Provider seam ───────────────────────────────────────────────────────────

SeriesProvider = Callable[[str, str, int], dict[str, Any]]

_series_store: Any = None
_provider: Optional[SeriesProvider] = None
_market_gateway: Any = None


def set_series_store(store: Any) -> None:
    """Bind the runtime's series store (boot wiring). Reading it is synchronous."""
    global _series_store
    _series_store = store


def set_series_provider(provider: Optional[SeriesProvider]) -> None:
    """Override the provider (tests, or a future broker-backed source)."""
    global _provider
    _provider = provider


def set_market_gateway(gateway: Any) -> None:
    """Bind the EXISTING market gateway for live quote/history nodes."""
    global _market_gateway
    _market_gateway = gateway


def _run_gateway(factory: Callable[[], Any]) -> Any:
    """Run an async gateway call from a sync node executor.

    The graph scheduler executes nodes in its own thread, so there is normally no
    running loop. If a caller invokes the executor inside a loop, run the
    coroutine in a short-lived worker thread instead of raising.
    """
    try:
        return asyncio.run(factory())
    except RuntimeError:
        with ThreadPoolExecutor(max_workers=1, thread_name_prefix="graph-gateway") as pool:
            return pool.submit(lambda: asyncio.run(factory())).result(timeout=30)


def _gateway_result(result: Any) -> dict[str, Any]:
    from ..market.errors import MarketError  # noqa: PLC0415

    if isinstance(result, MarketError):
        raise ValueError(f"{result.code}: {result.message}")
    if hasattr(result, "to_dict"):
        payload = result.to_dict()
    elif isinstance(result, dict):
        payload = result
    else:
        raise ValueError(f"market gateway returned {type(result).__name__}")
    if not isinstance(payload, dict):
        raise ValueError("market gateway returned a non-object payload")
    return payload


def _require_gateway() -> Any:
    if _market_gateway is None:
        raise ValueError(
            "the market data gateway is not configured in this runtime; "
            "configure a provider and try again"
        )
    return _market_gateway


# Public seams for the gateway-backed read nodes in `market_read_nodes.py`.
# They are the SAME helpers the quote/history nodes already use — a new read
# node must not grow a second gateway path, a second error shape or invented
# provenance.
def require_market_gateway() -> Any:
    return _require_gateway()


def run_market_gateway(factory: Callable[[], Any]) -> Any:
    return _run_gateway(factory)


def market_gateway_result(result: Any) -> dict[str, Any]:
    return _gateway_result(result)


def market_gateway_provenance(
    payload: dict[str, Any],
    *,
    kind: str,
    symbol: Optional[str] = None,
    extra: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Provenance for ANY normalized gateway record.

    The record's own ``meta`` is authoritative; a field the provider did not
    report stays ``None`` rather than being guessed. ``kind`` names the read,
    ``symbol`` is only a fallback when the record carries no identity.
    """
    meta = payload.get("meta") if isinstance(payload.get("meta"), dict) else {}
    provenance: dict[str, Any] = {
        "kind": kind,
        "provider": meta.get("provider"),
        "symbol": meta.get("symbol") or symbol,
        "assetType": meta.get("asset_type"),
        "freshness": meta.get("freshness"),
        "quality": meta.get("quality"),
        "dataStatus": meta.get("data_status"),
        "asOf": meta.get("event_time") or payload.get("timestamp"),
        "retrievedAt": meta.get("retrieved_at") or now_iso(),
        "warnings": list(meta.get("warnings") or []),
    }
    if provenance["symbol"]:
        provenance["symbol"] = str(provenance["symbol"]).upper()
    if extra:
        provenance.update(extra)
    return provenance


def numeric_series(payload: Any, label: str) -> Any:
    """The primary numeric series of an INDICATOR payload (public seam)."""
    return _numeric_series(payload, label)


def series_payload(
    kind: str,
    outputs: dict[str, Any],
    *,
    extra: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """The shared INDICATOR output shape (public seam for quant nodes)."""
    return _series_payload(kind, outputs, extra=extra)


def _default_provider(symbol: str, interval: str, limit: int) -> dict[str, Any]:
    if _series_store is None:
        raise SeriesUnavailable(
            "no market-data store is configured in this runtime; bars must be fetched "
            "through the research-data tools before a graph can read them"
        )
    rows = _series_store.get_bars(symbol, interval, limit=limit)
    if not rows:
        raise SeriesUnavailable(
            f"no stored {interval} bars for {symbol}; fetch them first "
            "(research-data tools) — the graph never fabricates a price"
        )
    coverage = _series_store.coverage(symbol, interval) if hasattr(_series_store, "coverage") else {}
    provider = str(coverage.get("provider") or "store") if coverage else "store"
    return {
        "symbol": symbol,
        "interval": interval,
        "adjusted": True,
        "provider": str(rows[-1].get("provider") or provider) if rows else provider,
        "retrievedAt": now_iso(),
        "rows": rows,
    }


def _read_series(symbol: str, interval: str, limit: int) -> dict[str, Any]:
    provider = _provider or _default_provider
    return provider(symbol, interval, limit)


# ── Payload adapters ────────────────────────────────────────────────────────

_REQUIRED_FIELDS = ("open", "high", "low", "close")


def series_rows(payload: Any) -> list[dict[str, Any]]:
    """Accept the OHLCV port's two shapes (a row list or `{rows: [...]}`)."""
    if isinstance(payload, dict):
        rows = payload.get("rows")
    elif isinstance(payload, list):
        rows = payload
    else:
        rows = None
    if not isinstance(rows, list) or not rows:
        raise ValueError("expected an OHLCV series with at least one row")
    return [row for row in rows if isinstance(row, dict)]


def ohlcv_arrays(payload: Any) -> dict[str, Any]:
    """Convert a series payload into the engine's `{field: np.ndarray}` shape."""
    if not _NUMPY_OK:  # pragma: no cover - depends on the install
        raise RuntimeError("the quant engine requires numpy, which is not installed")
    rows = series_rows(payload)
    for index, row in enumerate(rows):
        missing = [f for f in _REQUIRED_FIELDS if row.get(f) is None]
        if missing:
            raise ValueError(f"row {index} is missing {', '.join(missing)}")
    arrays = {field: np.array([float(row[field]) for row in rows], dtype=float) for field in _REQUIRED_FIELDS}
    arrays["volume"] = np.array(
        [float(row["volume"]) if row.get("volume") is not None else float("nan") for row in rows],
        dtype=float,
    )
    return arrays


def _clean(values: Any) -> list[Optional[float]]:
    """JSON-safe floats: NaN/inf → null so a warm-up is explicit, not a number."""
    out: list[Optional[float]] = []
    for value in list(values):
        number = float(value)
        out.append(number if math.isfinite(number) else None)
    return out


def _series_payload(kind: str, outputs: dict[str, Any], *, extra: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    cleaned = {key: _clean(values) for key, values in outputs.items()}
    primary_key = next(iter(cleaned), None)
    primary = cleaned.get(primary_key, []) if primary_key else []
    warmup = next((i for i, value in enumerate(primary) if value is not None), len(primary))
    payload: dict[str, Any] = {
        "kind": kind,
        "outputs": cleaned,
        "values": primary,  # the INDICATOR port's single-series shorthand
        "primary": primary_key,
        "length": len(primary),
        "warmup": warmup,
        "last": primary[-1] if primary else None,
    }
    if extra:
        payload.update(extra)
    return payload


# ── Executors ───────────────────────────────────────────────────────────────


def exec_market_data(context: NodeExecContext) -> dict[str, Any]:
    symbol = context.inputs.get("symbol") or context.config.get("symbol") or ""
    symbol = str(symbol).strip().upper()
    if not symbol:
        raise ValueError("no symbol: wire the symbol input or set the node's symbol")
    interval = str(context.config.get("interval", "1d"))
    try:
        lookback = int(context.config.get("lookback", 200))
    except (TypeError, ValueError) as exc:
        raise ValueError("lookback must be a whole number") from exc
    lookback = max(1, min(lookback, MAX_LOOKBACK))

    payload = _read_series(symbol, interval, lookback)
    rows = payload.get("rows") or []
    if not rows:
        raise SeriesUnavailable(f"no stored {interval} bars for {symbol}")
    rows = rows[-lookback:]
    provenance = {
        "provider": payload.get("provider") or "store",
        "symbol": symbol,
        "interval": interval,
        "adjusted": bool(payload.get("adjusted", True)),
        "rows": len(rows),
        "asOf": rows[-1].get("timestamp"),
        "retrievedAt": payload.get("retrievedAt") or now_iso(),
    }
    context.emit(f"{symbol} {interval}: {len(rows)} bars from {provenance['provider']}")
    return {
        "series": {"symbol": symbol, "interval": interval, "rows": rows},
        "provenance": provenance,
    }


def exec_quote(context: NodeExecContext) -> dict[str, Any]:
    symbol = str(context.inputs.get("symbol") or context.config.get("symbol") or "").strip().upper()
    if not symbol:
        raise ValueError("no symbol: wire the symbol input or set the node's symbol")
    market = str(context.config.get("market") or "").strip() or None
    freshness = str(context.config.get("freshness") or "realtime")
    gateway = _require_gateway()
    try:
        result = _run_gateway(lambda: gateway.get_quote(symbol, market, freshness=freshness))
    except ValueError:
        raise
    except Exception as exc:  # noqa: BLE001 - gateway failures are node data
        raise ValueError(f"quote unavailable: {exc}") from exc
    payload = _gateway_result(result)
    meta = payload.get("meta") or {}
    provenance = {
        "kind": "quote",
        "provider": meta.get("provider"),
        "symbol": meta.get("symbol") or symbol,
        "freshness": meta.get("freshness"),
        "quality": meta.get("quality"),
        "asOf": meta.get("event_time") or payload.get("timestamp"),
        "retrievedAt": meta.get("retrieved_at") or now_iso(),
    }
    context.emit(f"{provenance['symbol']} quote from {provenance['provider'] or 'gateway'}")
    return {"quote": payload, "provenance": provenance}


def exec_history(context: NodeExecContext) -> dict[str, Any]:
    symbol = str(context.inputs.get("symbol") or context.config.get("symbol") or "").strip().upper()
    if not symbol:
        raise ValueError("no symbol: wire the symbol input or set the node's symbol")
    market = str(context.config.get("market") or "").strip() or None
    interval = str(context.config.get("interval") or "1d")
    adjusted = bool(context.config.get("adjusted", True))
    try:
        limit = int(context.config.get("limit", 0))
    except (TypeError, ValueError) as exc:
        raise ValueError("limit must be a whole number") from exc
    gateway = _require_gateway()
    try:
        result = _run_gateway(lambda: gateway.get_historical_prices(
            symbol, market,
            start=str(context.config.get("start") or "") or None,
            end=str(context.config.get("end") or "") or None,
            interval=interval, adjusted=adjusted,
            freshness=str(context.config.get("freshness") or "slow"),
        ))
    except ValueError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"history unavailable: {exc}") from exc
    payload = _gateway_result(result)
    rows = payload.get("bars") or []
    if limit and limit > 0:
        rows = rows[-limit:]
    meta = payload.get("meta") or {}
    series = {
        "symbol": meta.get("symbol") or symbol,
        "interval": payload.get("interval") or interval,
        "rows": rows,
    }
    provenance = {
        "kind": "history",
        "provider": meta.get("provider"),
        "symbol": series["symbol"],
        "interval": series["interval"],
        "adjusted": payload.get("adjusted", adjusted),
        "rows": len(rows),
        "asOf": rows[-1].get("timestamp") if rows else None,
        "retrievedAt": meta.get("retrieved_at") or now_iso(),
        "gaps": payload.get("gaps") or [],
    }
    context.emit(f"{series['symbol']} {series['interval']}: {len(rows)} bars from {provenance['provider'] or 'gateway'}")
    return {"series": series, "provenance": provenance}


def _indicator_spec(kind: str, period: int, config: dict[str, Any]) -> Any:
    """Map the node's config onto the quant engine's catalog."""
    from ..quant.indicators import IndicatorSpec  # noqa: PLC0415 - keeps the graph runtime light

    if kind == "macd":
        params: dict[str, Any] = {}
        if config.get("fast"):
            params["fast"] = int(config["fast"])
        if config.get("slow"):
            params["slow"] = int(config["slow"])
        if config.get("signal"):
            params["signal"] = int(config["signal"])
        return IndicatorSpec(type="macd", params=params, id="macd")
    if kind == "bollinger":
        return IndicatorSpec(type="bollinger", params={"period": period, "num_std": 2}, id="bollinger")
    return IndicatorSpec(type=kind, params={"period": period}, id=kind)


def exec_indicator(context: NodeExecContext) -> dict[str, Any]:
    from ..quant.indicators import IndicatorError, compute_one  # noqa: PLC0415

    kind = str(context.config.get("kind", "sma"))
    try:
        period = int(context.config.get("period", 20))
    except (TypeError, ValueError) as exc:
        raise ValueError("period must be a whole number") from exc
    if period < 1:
        raise ValueError("period must be at least 1")

    arrays = ohlcv_arrays(context.inputs.get("series"))
    spec = _indicator_spec(kind, period, context.config)
    try:
        computed = compute_one(spec, arrays)
    except IndicatorError as exc:
        raise ValueError(str(exc)) from exc
    payload = _series_payload(kind, computed, extra={"period": period})
    context.emit(f"{kind}({period}) → {payload['length']} points, warm-up {payload['warmup']}")
    return {"values": payload}


def _numeric_series(payload: Any, label: str) -> Any:
    """The primary numeric series of an INDICATOR payload (nulls dropped)."""
    if isinstance(payload, dict) and isinstance(payload.get("values"), list):
        raw = payload["values"]
    elif isinstance(payload, list):
        raw = payload
    else:
        raise ValueError(f"{label} expects an indicator series")
    # Drop warm-up nulls but keep positions comparable across indicators.
    values = [float(v) if v is not None else float("nan") for v in raw]
    if not values:
        raise ValueError(f"{label} received an empty series")
    return np.array(values, dtype=float) if _NUMPY_OK else values


def exec_returns(context: NodeExecContext) -> dict[str, Any]:
    values = _numeric_series(context.inputs.get("values"), "quant.returns")
    kind = str(context.config.get("kind", "simple"))
    try:
        period = int(context.config.get("period", 1))
    except (TypeError, ValueError) as exc:
        raise ValueError("period must be a whole number") from exc
    if period < 1:
        raise ValueError("period must be at least 1")
    if not _NUMPY_OK:  # pragma: no cover
        raise RuntimeError("quant nodes require numpy, which is not installed")

    prior = np.full(values.shape, np.nan, dtype=float)
    prior[period:] = values[:-period]
    if kind == "log":
        with np.errstate(invalid="ignore", divide="ignore"):
            result = np.log(values / prior)
    elif kind == "simple":
        with np.errstate(invalid="ignore", divide="ignore"):
            result = values / prior - 1.0
    else:
        raise ValueError(f"unsupported return kind {kind!r}")
    return {"values": _series_payload(f"returns_{kind}", {"returns": result}, extra={"period": period})}


def exec_zscore(context: NodeExecContext) -> dict[str, Any]:
    values = _numeric_series(context.inputs.get("values"), "quant.zscore")
    try:
        period = int(context.config.get("period", 20))
    except (TypeError, ValueError) as exc:
        raise ValueError("period must be a whole number") from exc
    if period < 2:
        raise ValueError("period must be at least 2")
    if not _NUMPY_OK:  # pragma: no cover
        raise RuntimeError("quant nodes require numpy, which is not installed")

    out = np.full(values.shape, np.nan, dtype=float)
    for index in range(period - 1, len(values)):
        window = values[index - period + 1: index + 1]
        if np.isnan(window).any():
            continue
        mean = float(window.mean())
        std = float(window.std(ddof=0))
        if std == 0:
            continue
        out[index] = (values[index] - mean) / std
    return {"values": _series_payload("zscore", {"z": out}, extra={"period": period})}


def exec_volatility(context: NodeExecContext) -> dict[str, Any]:
    values = _numeric_series(context.inputs.get("values"), "quant.volatility")
    try:
        period = int(context.config.get("period", 20))
    except (TypeError, ValueError) as exc:
        raise ValueError("period must be a whole number") from exc
    if period < 2:
        raise ValueError("period must be at least 2")
    if not _NUMPY_OK:  # pragma: no cover
        raise RuntimeError("quant nodes require numpy, which is not installed")

    with np.errstate(invalid="ignore", divide="ignore"):
        returns = np.diff(np.log(values), prepend=np.nan)
    out = np.full(values.shape, np.nan, dtype=float)
    for index in range(period, len(values)):
        window = returns[index - period + 1: index + 1]
        if np.isnan(window).any():
            continue
        out[index] = float(window.std(ddof=1))
    if context.config.get("annualize"):
        out = out * math.sqrt(float(context.config.get("periodsPerYear", 252)))
    return {"values": _series_payload("volatility", {"volatility": out}, extra={"period": period})}


# ── Definitions ─────────────────────────────────────────────────────────────


def _port(port_id: str, name: str, port_type: PortType, **kwargs: Any) -> PortDef:
    return PortDef(id=port_id, name=name, type=port_type, **kwargs)


def _series_inputs() -> tuple[PortDef, ...]:
    return (_port("values", "Values", PortType.INDICATOR),)


def _series_outputs() -> tuple[PortDef, ...]:
    return (_port("values", "Values", PortType.INDICATOR),)


def build_finance_nodes() -> list[NodeDef]:
    """The finance/quant node set, with REAL executors (Phase 5)."""
    return [
        NodeDef(
            type="finance.quote", version="1.0.0", label="Live quote",
            category="finance",
            inputs=(_port("symbol", "Symbol", PortType.STRING, optional=True),),
            outputs=(
                _port("quote", "Quote", PortType.OBJECT),
                _port("provenance", "Provenance", PortType.EVIDENCE),
            ),
            config_fields=(
                ConfigField("symbol", "string", "", max_length=40),
                ConfigField("market", "string", "", max_length=20),
                ConfigField("freshness", "enum", "realtime", enum=("realtime", "intraday", "slow", "any")),
            ),
            capabilities=("market.read",),
            side_effects=SideEffect.READ,
            allowed_modes=_ALL,
            executor=exec_quote,
            metadata={"docs": "Live quote through the EXISTING market gateway; provenance on every payload."},
        ),
        NodeDef(
            type="finance.history", version="1.0.0", label="Historical prices",
            category="finance",
            inputs=(_port("symbol", "Symbol", PortType.STRING, optional=True),),
            outputs=(
                _port("series", "OHLCV", PortType.OHLCV),
                _port("provenance", "Provenance", PortType.EVIDENCE),
            ),
            config_fields=(
                ConfigField("symbol", "string", "", max_length=40),
                ConfigField("market", "string", "", max_length=20),
                ConfigField("interval", "enum", "1d", enum=("1m", "5m", "15m", "30m", "1h", "4h", "1d", "1w", "1mo")),
                ConfigField("start", "string", "", max_length=40),
                ConfigField("end", "string", "", max_length=40),
                ConfigField("adjusted", "boolean", True),
                ConfigField("limit", "integer", 0, minimum=0, maximum=MAX_LOOKBACK),
                ConfigField("freshness", "enum", "slow", enum=("realtime", "intraday", "slow", "any")),
            ),
            capabilities=("market.read",),
            side_effects=SideEffect.READ,
            allowed_modes=_ALL,
            executor=exec_history,
            metadata={"docs": "Gateway-backed OHLCV with provider provenance; feeds the indicator nodes."},
        ),
        NodeDef(
            type="finance.market_data", version="1.0.0", label="Market data",
            category="finance",
            inputs=(_port("symbol", "Symbol", PortType.STRING, optional=True),),
            outputs=(
                _port("series", "OHLCV", PortType.OHLCV),
                _port("provenance", "Provenance", PortType.EVIDENCE),
            ),
            config_fields=(
                ConfigField("symbol", "string", "", max_length=40),
                ConfigField("interval", "enum", "1d", enum=("1m", "5m", "15m", "1h", "1d")),
                ConfigField("lookback", "integer", 200, minimum=1, maximum=MAX_LOOKBACK),
            ),
            capabilities=("market.read",),
            side_effects=SideEffect.READ,
            allowed_modes=_ALL,
            executor=exec_market_data,
            metadata={"docs": "Reads the runtime's stored bars (research-data tools fill them)."},
        ),
        NodeDef(
            type="finance.indicator", version="1.0.0", label="Indicator",
            category="quant",
            inputs=(_port("series", "OHLCV", PortType.OHLCV),),
            outputs=(_port("values", "Values", PortType.INDICATOR),),
            config_fields=(
                ConfigField("kind", "enum", "sma",
                            enum=("sma", "ema", "rsi", "macd", "atr", "adx", "vwap", "bollinger")),
                ConfigField("period", "integer", 20, minimum=1, maximum=500),
                ConfigField("fast", "integer", 12, minimum=1, maximum=500),
                ConfigField("slow", "integer", 26, minimum=1, maximum=500),
                ConfigField("signal", "integer", 9, minimum=1, maximum=500),
            ),
            capabilities=("quant.compute",),
            allowed_modes=_ALL,
            executor=exec_indicator,
            metadata={"docs": "Math from harness/quant/indicators.py (causal, tested)."},
        ),
        NodeDef(
            type="quant.returns", version="1.0.0", label="Returns",
            category="quant",
            inputs=_series_inputs(),
            outputs=_series_outputs(),
            config_fields=(
                ConfigField("kind", "enum", "simple", enum=("simple", "log")),
                ConfigField("period", "integer", 1, minimum=1, maximum=500),
            ),
            capabilities=("quant.compute",),
            allowed_modes=_ALL,
            executor=exec_returns,
        ),
        NodeDef(
            type="quant.zscore", version="1.0.0", label="Z-score",
            category="quant",
            inputs=_series_inputs(),
            outputs=_series_outputs(),
            config_fields=(ConfigField("period", "integer", 20, minimum=2, maximum=500),),
            capabilities=("quant.compute",),
            allowed_modes=_ALL,
            executor=exec_zscore,
        ),
        NodeDef(
            type="quant.volatility", version="1.0.0", label="Volatility",
            category="quant",
            inputs=_series_inputs(),
            outputs=_series_outputs(),
            config_fields=(
                ConfigField("period", "integer", 20, minimum=2, maximum=500),
                ConfigField("annualize", "boolean", False),
                ConfigField("periodsPerYear", "integer", 252, minimum=1, maximum=1000),
            ),
            capabilities=("quant.compute",),
            allowed_modes=_ALL,
            executor=exec_volatility,
        ),
    ]


__all__ = [
    "SeriesUnavailable",
    "set_series_store",
    "set_series_provider",
    "set_market_gateway",
    "exec_market_data",
    "exec_quote",
    "exec_history",
    "exec_indicator",
    "series_rows",
    "ohlcv_arrays",
    "build_finance_nodes",
]
