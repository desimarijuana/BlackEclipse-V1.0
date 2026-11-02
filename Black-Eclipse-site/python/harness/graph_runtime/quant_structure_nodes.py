"""Market-structure nodes: timeframes, regimes and position size.

These three nodes fill the gaps between the research pack and a real multi-asset
workflow. Like the validation pack they are adapters, not new math:

  * `quant.align`         → `harness/quant/transform.py` (`align_rows`)
  * `quant.regime`        → `harness/quant/regime.py` (`classify_series`)
  * `quant.position_size` → `harness/quant/sizing.py` (`compute_quantity`)

The rules the adapters enforce:

  * alignment never forward-fills unless the caller asks (`fill: ffill`) and
    every imputed value is counted, so a gap cannot masquerade as a quote;
  * a regime label is only INFORMED once the classifier has its warm-up: the
    leading `warmupBars` carry no trend signal (they are `flat`) and are reported
    as such, so a pre-warm-up label can never be mistaken for a measured trend;
  * a size that cannot be computed (no stop for `percent_risk`, no ATR for
    `atr`, no trade statistics for Kelly) is an explicit failure naming the
    missing input, not a zero or a made-up quantity.
"""

from __future__ import annotations

from typing import Any, Optional

from ..quant import data as quant_data
from ..quant.errors import QuantError
from ..quant.regime import RegimeConfig, RegimeError, classify_series
from ..quant.sizing import SizingContext, compute_quantity
from ..quant.strategy import PositionSizing
from ..quant.transform import TransformError, align_rows
from .finance_nodes import series_rows
from .model import ExecutionMode, PortDef, PortType, SideEffect
from .registry import ConfigField, NodeDef, NodeExecContext

_ALL = tuple(ExecutionMode)
MAX_BARS = 20_000
_MAX_SYMBOLS = 50
_JOINS = ("inner", "outer")
_FILLS = ("none", "ffill", "zero")
_SIZING_TYPES = (
    "fixed_quantity", "fixed_dollar", "percent_equity", "percent_risk", "atr",
    "volatility", "kelly", "fractional_kelly", "risk_parity", "equal_weight",
)
_FILL_VALUE = {"none": None, "ffill": "ffill", "zero": 0.0}


# ── Input adapters ──────────────────────────────────────────────────────────


def series_map(raw: Any, label: str = "quant.align") -> dict[str, list[dict[str, Any]]]:
    """Accept `{symbol: rows}` or `{symbol: {rows: [...]}}`; reject anything else."""
    if not isinstance(raw, dict) or not raw:
        raise ValueError(
            f"{label} needs an object mapping each symbol to its OHLCV rows"
        )
    if "rows" in raw:
        raise ValueError(
            f"{label} expects a map of {{symbol: OHLCV rows}}; wrap the single "
            "series under its symbol instead of passing it directly"
        )
    if len(raw) > _MAX_SYMBOLS:
        raise ValueError(f"{label} is bounded to {_MAX_SYMBOLS} instruments")
    out: dict[str, list[dict[str, Any]]] = {}
    for symbol, value in raw.items():
        if isinstance(value, dict):
            rows = value.get("rows")
        else:
            rows = value
        if not isinstance(rows, list) or not rows:
            raise ValueError(f"{label}: '{symbol}' has no OHLCV rows")
        if len(rows) > MAX_BARS:
            raise ValueError(
                f"{label} is bounded to {MAX_BARS} bars (got {len(rows)} for '{symbol}')"
            )
        if not all(isinstance(row, dict) for row in rows):
            raise ValueError(f"{label}: every row of '{symbol}' must be an object")
        out[str(symbol).strip().upper()] = rows
    return out


def _bar_arrays(series: Any, node_type: str) -> tuple[str, Any]:
    try:
        rows = series_rows(series)
    except ValueError as exc:
        raise ValueError(f"{node_type} needs an OHLCV series: {exc}") from exc
    if len(rows) > MAX_BARS:
        raise ValueError(f"{node_type} is bounded to {MAX_BARS} bars (got {len(rows)})")
    payload = series if isinstance(series, dict) else {}
    symbol = str(payload.get("symbol") or "").strip().upper()
    if not symbol:
        raise ValueError(f"{node_type}: the series has no symbol")
    interval = str(payload.get("interval") or "1d")
    try:
        bars = quant_data.series_from_rows(
            symbol, interval, rows,
            source=str(payload.get("provider") or "graph"),
            asset_type=str(payload.get("assetType") or "equity"),
        )
    except Exception as exc:  # noqa: BLE001 - a bad bar is an honest failure
        raise ValueError(f"{node_type}: series could not be adapted: {exc}") from exc
    return symbol, bars


# ── Executors ───────────────────────────────────────────────────────────────


def exec_align(context: NodeExecContext) -> dict[str, Any]:
    series = series_map(context.inputs.get("series"))
    join = str(context.config.get("join") or "inner")
    if join not in _JOINS:
        raise ValueError(f"join must be one of {', '.join(_JOINS)}")
    column = str(context.config.get("column") or "close").strip()
    if not column:
        raise ValueError("column must name a field of the rows")
    fill_key = str(context.config.get("fill") or "none")
    if fill_key not in _FILLS:
        raise ValueError(f"fill must be one of {', '.join(_FILLS)}")

    try:
        aligned = align_rows(series, join=join, column=column, fill=_FILL_VALUE[fill_key])
    except TransformError as exc:
        raise ValueError(str(exc)) from exc

    aligned["symbols"] = sorted(aligned.get("series", {}))
    imputed = sum(int(value) for value in (aligned.get("missing") or {}).values())
    context.emit(
        f"aligned {len(aligned['symbols'])} instrument(s) on {len(aligned['timestamps'])} "
        f"timestamp(s) ({join}), {imputed} missing value(s)"
    )
    return {
        "aligned": aligned,
        "metadata": {
            "join": join,
            "column": column,
            "fill": aligned.get("fill"),
            "imputed": bool(aligned.get("imputed")),
            "timestamps": len(aligned.get("timestamps") or []),
            "symbols": aligned["symbols"],
            "missing": aligned.get("missing") or {},
        },
    }


def exec_regime(context: NodeExecContext) -> dict[str, Any]:
    symbol, bars = _bar_arrays(context.inputs.get("series"), "quant.regime")
    config = RegimeConfig(
        fast=int(context.config.get("fast", 20)),
        slow=int(context.config.get("slow", 50)),
        atr_period=int(context.config.get("atrPeriod", 14)),
        vol_period=int(context.config.get("volPeriod", 20)),
        vol_baseline=int(context.config.get("volBaseline", 100)),
        trend_threshold=float(context.config.get("trendThreshold", 0.5)),
        high_vol_ratio=float(context.config.get("highVolRatio", 1.5)),
        low_vol_ratio=float(context.config.get("lowVolRatio", 0.67)),
    )
    try:
        classified = classify_series(
            symbol, bars.high, bars.low, bars.close, list(bars.timestamps), config,
        )
    except RegimeError as exc:
        raise ValueError(f"regime classification failed: {exc}") from exc
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"regime classification failed: {type(exc).__name__}: {exc}") from exc

    payload = classified.to_dict(include_series=True)
    counts = payload.get("counts") or {}
    dominant = max(counts, key=counts.get) if counts else "unknown"
    summary = (
        f"{symbol}: {len(payload.get('labels') or [])} bars classified, "
        f"{len(counts)} regime(s), most common {dominant}, "
        f"{payload.get('warmupBars', 0)} warm-up bar(s)"
    )
    context.emit(summary)
    return {"regimes": {symbol: payload}, "summary": summary}


def exec_position_size(context: NodeExecContext) -> dict[str, Any]:
    price = context.inputs.get("price")
    try:
        price_value = float(price)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        raise ValueError("quant.position_size needs a numeric price input") from None
    if price_value <= 0:
        raise ValueError("quant.position_size needs a positive price")

    method = str(context.config.get("method") or "percent_equity")
    if method not in _SIZING_TYPES:
        raise ValueError(f"method must be one of {', '.join(_SIZING_TYPES)}")

    def optional(key: str) -> Optional[float]:
        raw = context.inputs.get(key)
        if raw is None:
            return None
        try:
            return float(raw)
        except (TypeError, ValueError):
            raise ValueError(f"'{key}' must be a number") from None

    precision = int(context.config.get("quantityPrecision", 0))
    sizing = PositionSizing(
        type=method,  # type: ignore[arg-type]
        value=float(context.config.get("value", 1.0)),
        atr_multiplier=float(context.config.get("atrMultiplier", 1.0)),
        max_fraction=float(context.config.get("maxFraction", 1.0)),
        kelly_fraction=float(context.config.get("kellyFraction", 0.5)),
        min_quantity=float(context.config.get("minQuantity", 0.0)),
        lot_size=float(context.config.get("lotSize", 0.0)),
        quantity_precision=precision or None,
        contract_multiplier=float(context.config.get("contractMultiplier", 1.0)),
    )
    sizing_ctx = SizingContext(
        equity=float(context.config.get("equity", 100_000.0)),
        price=price_value,
        stop_distance=optional("stop"),
        atr=optional("atr"),
        realized_vol=float(context.config.get("realizedVol", 0.0)) or None,
        kelly_win_rate=float(context.config.get("winRate", 0.5)),
        kelly_payoff=float(context.config.get("payoff", 2.0)),
        weight=float(context.config.get("weight", 0.0)) or None,
    )
    try:
        quantity, detail = compute_quantity(sizing, sizing_ctx)
    except QuantError as exc:
        raise ValueError(f"position size failed: {exc}") from exc
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"position size failed: {type(exc).__name__}: {exc}") from exc

    if quantity is None:
        reason = detail.get("reason") or "the sizing method's inputs are unavailable"
        raise ValueError(f"{method} sizing is not computable: {reason}")

    size = {
        **detail,
        "quantity": quantity,
        "price": price_value,
        "equity": sizing_ctx.equity,
    }
    context.emit(
        f"{method}: {quantity:g} unit(s) at {price_value:g} "
        f"(notional {size.get('notional')})"
    )
    return {"size": size, "quantity": quantity}


# ── Definitions ─────────────────────────────────────────────────────────────


def _port(port_id: str, name: str, port_type: PortType, *, optional: bool = False) -> PortDef:
    return PortDef(id=port_id, name=name, type=port_type, optional=optional)


def build_quant_structure_nodes() -> list[NodeDef]:
    return [
        NodeDef(
            type="quant.align",
            version="1.0.0",
            label="Align instruments",
            category="quant",
            inputs=(_port("series", "Series map", PortType.OBJECT),),
            outputs=(
                _port("aligned", "Aligned", PortType.OBJECT),
                _port("metadata", "Metadata", PortType.OBJECT),
            ),
            config_fields=(
                ConfigField("join", "enum", "inner", enum=_JOINS),
                ConfigField("column", "string", "close", max_length=20),
                ConfigField("fill", "enum", "none", enum=_FILLS),
            ),
            capabilities=("quant.compute",),
            side_effects=SideEffect.NONE,
            allowed_modes=_ALL,
            executor=exec_align,
            metadata={
                "docs": (
                    "Aligns instruments onto one timestamp axis through "
                    "harness/quant/transform.py. `fill: none` leaves a missing value "
                    "null and counts it per symbol; `ffill` and `zero` impute on "
                    "explicit request only, and `imputed` records that they did."
                ),
            },
        ),
        NodeDef(
            type="quant.regime",
            version="1.0.0",
            label="Regime labels",
            category="quant",
            inputs=(_port("series", "OHLCV", PortType.OHLCV),),
            outputs=(
                _port("regimes", "Regimes", PortType.OBJECT),
                _port("summary", "Summary", PortType.STRING),
            ),
            config_fields=(
                ConfigField("fast", "integer", 20, minimum=1, maximum=500),
                ConfigField("slow", "integer", 50, minimum=2, maximum=500),
                ConfigField("atrPeriod", "integer", 14, minimum=1, maximum=500),
                ConfigField("volPeriod", "integer", 20, minimum=1, maximum=500),
                ConfigField("volBaseline", "integer", 100, minimum=1, maximum=2_000),
                ConfigField("trendThreshold", "number", 0.5, minimum=0, maximum=10),
                ConfigField("highVolRatio", "number", 1.5, minimum=1, maximum=10),
                ConfigField("lowVolRatio", "number", 0.67, minimum=0.01, maximum=1),
            ),
            capabilities=("quant.compute",),
            side_effects=SideEffect.NONE,
            allowed_modes=_ALL,
            executor=exec_regime,
            metadata={
                "docs": (
                    "Trend/volatility regime labels per bar through "
                    "harness/quant/regime.py (fast/slow trend filter plus an ATR and "
                    "a volatility baseline). `warmupBars` counts the leading bars "
                    "before the first informed trend label; those bars are `flat` and "
                    "are never presented as a measured trend."
                ),
            },
        ),
        NodeDef(
            type="quant.position_size",
            version="1.0.0",
            label="Position size",
            category="quant",
            inputs=(
                _port("price", "Price", PortType.NUMBER),
                _port("atr", "ATR", PortType.NUMBER, optional=True),
                _port("stop", "Stop distance", PortType.NUMBER, optional=True),
            ),
            outputs=(
                _port("size", "Size", PortType.OBJECT),
                _port("quantity", "Quantity", PortType.NUMBER),
            ),
            config_fields=(
                ConfigField("method", "enum", "percent_equity", enum=_SIZING_TYPES),
                ConfigField("value", "number", 1.0),
                ConfigField("equity", "number", 100_000.0, minimum=0, maximum=1_000_000_000),
                ConfigField("atrMultiplier", "number", 1.0, minimum=0.1, maximum=20),
                ConfigField("maxFraction", "number", 1.0, minimum=0, maximum=10),
                ConfigField("kellyFraction", "number", 0.5, minimum=0, maximum=1),
                ConfigField("winRate", "number", 0.5, minimum=0, maximum=1),
                ConfigField("payoff", "number", 2.0, minimum=0.1, maximum=100),
                ConfigField("realizedVol", "number", 0.0, minimum=0, maximum=10),
                ConfigField("weight", "number", 0.0, minimum=0, maximum=1),
                ConfigField("minQuantity", "number", 0.0, minimum=0),
                ConfigField("lotSize", "number", 0.0, minimum=0),
                ConfigField("quantityPrecision", "integer", 0, minimum=0, maximum=12),
                ConfigField("contractMultiplier", "number", 1.0, minimum=0.0001, maximum=10_000),
            ),
            capabilities=("quant.compute",),
            side_effects=SideEffect.NONE,
            allowed_modes=_ALL,
            executor=exec_position_size,
            metadata={
                "docs": (
                    "Position size from harness/quant/sizing.py using the same "
                    "PositionSizing contract the engine executes. A method whose "
                    "input is missing (no stop for percent_risk, no ATR for atr, no "
                    "trade statistics for Kelly) is an explicit failure, never a "
                    "guessed quantity."
                ),
            },
        ),
    ]


__all__ = [
    "build_quant_structure_nodes",
    "exec_align",
    "exec_regime",
    "exec_position_size",
    "series_map",
]
