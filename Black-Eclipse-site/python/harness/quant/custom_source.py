"""Read backtest bars from a dataset the OPERATOR declared themselves.

Settings -> Data Sources lets an operator connect any REST API with their own
key and map the response into a dataset ("Custom REST API"). That dataset is
read through the read-only bridge capability `custom_dataset_records`.

Why this lives here and not as a market provider:

* A user-supplied source is **not** a first-class market provider. It is not
  routed, ranked, health-checked or verified alongside them, and it must not
  appear in the market-data provider vocabulary.
* A backtest uses it **only when the caller names it**. Naming a source that
  yields nothing is an honest typed error (`CUSTOM_SOURCE_UNAVAILABLE` /
  `MISSING_DATA`) - never a quiet switch to the built-in providers, because a
  result built on different data than the caller asked for is a fabrication.

The dataset's field names are the ones the operator mapped. The small alias
table below accepts the common spellings (`close`/`c`, `time`/`date`/...), so a
straightforward mapping works; anything else is reported as unusable rows rather
than guessed.
"""

from __future__ import annotations

from typing import Any, Optional

from .data import INTERVAL_SECONDS, BarSeries, series_from_rows
from .errors import (
    CustomSourceUnavailable,
    InvalidDataSource,
    MissingData,
    UnsupportedTimeframe,
)

#: The bridge refuses a bigger parameter map; fail early with a clearer message.
MAX_VALUES = 25

#: Common column spellings accepted for the OHLCV fields a backtest needs.
_TS_KEYS = ("timestamp", "date", "time", "datetime")
_FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "open": ("open", "o", "Open"),
    "high": ("high", "h", "High"),
    "low": ("low", "l", "Low"),
    "close": ("close", "c", "Close", "price", "last"),
    "volume": ("volume", "v", "Volume", "vol"),
}


def normalize_data_source(raw: Any) -> Optional[dict[str, Any]]:
    """Normalize a caller-supplied data source into ``{dataset, values}``.

    Accepted shapes:

    * ``None`` / ``""`` -> ``None`` (use the built-in market providers)
    * ``"my-dataset"`` or ``"custom:my-dataset"``
    * ``{"dataset": "my-dataset", "values": {"market": "us_stocks"}}``
    * ``{"name": "my-dataset"}`` (``name`` is accepted as a synonym)

    A malformed source raises `InvalidDataSource`; it is never ignored, because
    ignoring it would run the backtest on data the caller did not choose.
    """
    if raw is None:
        return None
    if isinstance(raw, str):
        name = raw.strip()
        if not name:
            return None
        if name.lower().startswith("custom:"):
            name = name.split(":", 1)[1].strip()
        if not name:
            raise InvalidDataSource("a data source name is required after 'custom:'")
        return {"dataset": name, "values": {}}
    if not isinstance(raw, dict):
        raise InvalidDataSource(
            "dataSource must be a dataset name or {dataset, values} object",
            detail={"received": type(raw).__name__},
        )

    raw_name = raw.get("dataset", raw.get("name", raw.get("dataSource")))
    if not isinstance(raw_name, str) or not raw_name.strip():
        raise InvalidDataSource(
            "dataSource.dataset is required (the name from Settings -> Data Sources)",
        )
    name = raw_name.strip()
    if name.lower().startswith("custom:"):
        name = name.split(":", 1)[1].strip()
    if not name:
        raise InvalidDataSource("dataSource.dataset cannot be empty")

    values_raw = raw.get("values") or {}
    if not isinstance(values_raw, dict):
        raise InvalidDataSource("dataSource.values must be a flat map of parameter name to value")
    if len(values_raw) > MAX_VALUES:
        raise InvalidDataSource(
            f"dataSource.values holds more than {MAX_VALUES} entries",
            detail={"count": len(values_raw)},
        )
    values: dict[str, Any] = {}
    for key, value in values_raw.items():
        if not isinstance(key, str) or not key.strip():
            raise InvalidDataSource("dataSource.values keys must be non-empty strings")
        if value is None:
            continue
        if isinstance(value, (dict, list, tuple, set)):
            raise InvalidDataSource(
                f"dataSource.values[{key!r}] must be a scalar (it becomes one query parameter)"
            )
        values[key.strip()] = value
    return {"dataset": name, "values": values}


def describe_source(source: Optional[dict[str, Any]]) -> Optional[str]:
    """A short, user-facing label for provenance/warning text."""
    if not source:
        return None
    return f"custom:{source.get('dataset', '')}"


def stamp_provenance(result: Any, source: Optional[dict[str, Any]]) -> None:
    """Record on a result that its bars came from the operator's own source.

    The user must be able to tell a user-supplied dataset apart from a
    provider-backed, verifiable run — so the provenance is written into
    `metadata` and a warning that survives into the rendered summary.
    """
    if not source:
        return
    name = str(source.get("dataset") or "")
    metadata = getattr(result, "metadata", None)
    if isinstance(metadata, dict):
        metadata["dataSource"] = {
            "kind": "custom",
            "dataset": name,
            "label": describe_source(source),
            "provenance": "operator_declared",
            "verified": False,
        }
    warnings = getattr(result, "warnings", None)
    if isinstance(warnings, list):
        warnings.append({
            "code": "CUSTOM_DATA_SOURCE",
            "severity": "warning",
            "message": (
                f"Bars came from your declared dataset {name!r}, not from the built-in "
                "market providers. This result is not Eclipse-verified market data."
            ),
        })


def _pick(values: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        if key in values and values[key] is not None:
            return values[key]
    return None


def _row_from_record(record: Any) -> Optional[dict[str, Any]]:
    """Flatten a bridge record into the row shape `series_from_rows` expects."""
    if not isinstance(record, dict):
        return None
    values = record.get("values")
    if not isinstance(values, dict):
        return None
    row: dict[str, Any] = {}
    ts = _pick(values, _TS_KEYS)
    if ts is not None:
        row["timestamp"] = ts
    for field, aliases in _FIELD_ALIASES.items():
        value = _pick(values, aliases)
        if value is not None:
            row[field] = value
    return row or None


def _in_window(row: dict[str, Any], start: Optional[str], end: Optional[str]) -> bool:
    """Filter locally when the caller asked for a window.

    The declared source may or may not forward `from`/`to`; the backtest window
    is a hard promise, so rows outside it are dropped here rather than trusted
    to the endpoint.
    """
    if not start and not end:
        return True
    from .data import _parse_ts  # local import: private helper, same package

    try:
        stamp = _parse_ts(row.get("timestamp"))
    except Exception:  # noqa: BLE001 - an unparsable stamp is kept for the normalizer's finding
        return True
    try:
        if start and stamp < _parse_ts(start):
            return False
        if end and stamp > _parse_ts(end):
            return False
    except Exception:  # noqa: BLE001 - a passed-in date is the caller's; keep the row
        return True
    return True


def _status_of(result: Any) -> str:
    if not isinstance(result, dict):
        return ""
    return str(result.get("status") or "").upper()


async def fetch_custom_series(
    bridge: Any,
    source: dict[str, Any],
    symbol: str,
    interval: str,
    *,
    start: Optional[str] = None,
    end: Optional[str] = None,
) -> BarSeries:
    """Read one symbol's bars from the named operator-declared dataset."""
    name = str(source.get("dataset") or "")
    if interval not in INTERVAL_SECONDS:
        raise UnsupportedTimeframe(f"unsupported timeframe {interval!r}")
    if bridge is None:
        raise CustomSourceUnavailable(
            "a custom data source needs the desktop data bridge, and none is attached "
            "to this run",
            detail={"dataset": name},
        )

    values: dict[str, Any] = dict(source.get("values") or {})
    # A superset of the common declared-parameter names. The bridge fills only
    # the parameters the operator actually declared; anything else is ignored,
    # so one backtest call serves datasets with different parameter spellings.
    values["symbol"] = symbol
    values["interval"] = interval
    values["timeframe"] = interval
    if start:
        values["start"] = start
        values["from"] = start
    if end:
        values["end"] = end
        values["to"] = end

    try:
        result = await bridge.fetch(
            "custom_dataset_records", {"dataset": name, "values": values}
        )
    except Exception as exc:  # noqa: BLE001 - any transport failure is the same honest refusal
        raise CustomSourceUnavailable(
            f"could not read dataset {name!r}: {exc}", detail={"dataset": name}
        ) from exc

    status = _status_of(result)
    if status not in ("OK", "STALE"):
        message = ""
        if isinstance(result, dict):
            message = str(result.get("error") or result.get("message") or "")
        raise CustomSourceUnavailable(
            f"dataset {name!r} could not serve {symbol} {interval}"
            + (f": {message}" if message else ""),
            detail={"dataset": name, "status": status or "UNKNOWN", "symbol": symbol},
        )

    records = result.get("records") if isinstance(result, dict) else None
    if not isinstance(records, list) or not records:
        raise MissingData(
            f"dataset {name!r} returned no records for {symbol}",
            detail={"dataset": name, "symbol": symbol, "interval": interval},
        )

    rows: list[dict[str, Any]] = []
    for record in records:
        row = _row_from_record(record)
        if row is not None and _in_window(row, start, end):
            rows.append(row)
    if not rows or not any(row.get("close") is not None for row in rows):
        raise MissingData(
            f"dataset {name!r} returned {len(records)} record(s) for {symbol}, none with a "
            "usable timestamp plus close inside the requested window. Map the dataset's "
            "fields to timestamp/open/high/low/close/volume in Settings -> Data Sources.",
            detail={"dataset": name, "symbol": symbol, "records": len(records)},
        )

    series = series_from_rows(
        symbol, interval, rows, source=f"custom:{name}"
    )
    if series.length < 2:
        raise MissingData(
            f"dataset {name!r} produced {series.length} bar(s) for {symbol}; a backtest "
            "needs at least two",
            detail={"dataset": name, "symbol": symbol},
        )
    return series


__all__ = [
    "describe_source",
    "fetch_custom_series",
    "normalize_data_source",
    "stamp_provenance",
]
