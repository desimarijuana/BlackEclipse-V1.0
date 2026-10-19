"""Per-source row adapters: a bridge payload → the source's declared rows.

Every adapter reads ONLY the payload's documented shape and emits rows with
exactly the source's declared columns. A call that fails or returns nothing
produces a plain `problem` sentence — never a fabricated row. No adapter opens a
transport: they all go through the ONE read-only bridge (`ctx.data_bridge.fetch`).
"""

from __future__ import annotations

import json
from typing import Any

from .budget import AcquisitionBudget
from .registry import AcquisitionSource

_MAX_PROBLEMS = 8


def _scalar(value: Any) -> bool:
    return value is None or isinstance(value, (str, int, float, bool))


async def collect(
    source: AcquisitionSource,
    *,
    symbols: list[str],
    params: dict[str, Any],
    bridge: Any,
    budget: AcquisitionBudget,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Collect rows for ONE source within the budget. Returns (rows, problems)."""
    if source.id == "prices_daily":
        return await _collect_prices(source, symbols=symbols, params=params, bridge=bridge, budget=budget)
    if source.id == "macro_series":
        return await _collect_macro(source, params=params, bridge=bridge, budget=budget)
    if source.id == "statements_annual":
        return await _collect_statements(source, symbols=symbols, params=params, bridge=bridge, budget=budget)
    if source.id == "filings_list":
        return await _collect_filings(source, symbols=symbols, params=params, bridge=bridge, budget=budget)
    if source.id == "operator_datasets":
        return await _collect_operator_datasets(source, params=params, bridge=bridge, budget=budget)
    return [], [f"{source.label} has no collector in this build"]


def _problem(problems: list[str], text: str) -> None:
    if len(problems) < _MAX_PROBLEMS:
        problems.append(text)


async def _collect_prices(
    source: AcquisitionSource, *, symbols: list[str], params: dict[str, Any],
    bridge: Any, budget: AcquisitionBudget,
) -> tuple[list[dict[str, Any]], list[str]]:
    rows: list[dict[str, Any]] = []
    problems: list[str] = []
    call_params = {
        "market": str(params.get("market") or ""),
        "range": str(params.get("range") or "2y"),
        "interval": str(params.get("interval") or "1d"),
    }
    for symbol in symbols:
        if not budget.allow_call():
            break
        payload = await bridge.fetch(source.capability, {"symbol": symbol, **call_params})
        budget.record_call()
        if not isinstance(payload, dict) or payload.get("status") != "OK":
            error = (payload or {}).get("error") if isinstance(payload, dict) else "no response"
            _problem(problems, f"{symbol}: {error or 'no data returned'}")
            continue
        series = payload.get("series") or payload.get("history") or payload.get("rows") or []
        if not isinstance(series, list):
            _problem(problems, f"{symbol}: the provider returned no usable bars")
            continue
        for bar in series:
            if not isinstance(bar, dict):
                continue
            date = bar.get("date") or bar.get("timestamp")
            if date is None:
                continue
            rows.append({
                "symbol": symbol,
                "date": date,
                "open": bar.get("open"),
                "high": bar.get("high"),
                "low": bar.get("low"),
                "close": bar.get("close"),
                "volume": bar.get("volume"),
            })
        if budget.rows + len(series) >= budget.max_rows:
            break
    return rows, problems


async def _collect_macro(
    source: AcquisitionSource, *, params: dict[str, Any],
    bridge: Any, budget: AcquisitionBudget,
) -> tuple[list[dict[str, Any]], list[str]]:
    rows: list[dict[str, Any]] = []
    problems: list[str] = []
    if not budget.allow_call():
        return rows, problems
    call_params: dict[str, Any] = {"seriesId": str(params.get("series") or "")}
    if params.get("quantity") is not None:
        call_params["quantity"] = int(params["quantity"])
    if params.get("source"):
        call_params["source"] = str(params["source"])
    payload = await bridge.fetch(source.capability, call_params)
    budget.record_call()
    if not isinstance(payload, dict) or payload.get("status") != "OK":
        error = (payload or {}).get("error") if isinstance(payload, dict) else "no response"
        _problem(problems, f"{call_params['seriesId'] or 'series'}: {error or 'no data returned'}")
        return rows, problems
    series_key = str(payload.get("seriesKey") or call_params["seriesId"] or "")
    series_rows = payload.get("rows") or payload.get("series") or payload.get("points") or []
    if not isinstance(series_rows, list):
        _problem(problems, f"{series_key}: the provider returned no usable observations")
        return rows, problems
    for point in series_rows:
        if not isinstance(point, dict):
            continue
        date = point.get("date") or point.get("timestamp")
        value = point.get("value")
        if date is None or value is None:
            continue
        rows.append({"series": series_key, "date": date, "value": value})
    return rows, problems


async def _collect_statements(
    source: AcquisitionSource, *, symbols: list[str], params: dict[str, Any],
    bridge: Any, budget: AcquisitionBudget,
) -> tuple[list[dict[str, Any]], list[str]]:
    rows: list[dict[str, Any]] = []
    problems: list[str] = []
    market = str(params.get("market") or "")
    for symbol in symbols:
        if not budget.allow_call():
            break
        payload = await bridge.fetch(source.capability, {"symbol": symbol, "market": market})
        budget.record_call()
        if not isinstance(payload, dict) or payload.get("status") != "OK":
            error = (payload or {}).get("error") if isinstance(payload, dict) else "no response"
            _problem(problems, f"{symbol}: {error or 'no statements returned'}")
            continue
        statements = payload.get("statements") or payload.get("periods") or []
        if not isinstance(statements, list):
            _problem(problems, f"{symbol}: the provider returned no usable statements")
            continue
        for statement in statements:
            if not isinstance(statement, dict):
                continue
            period = str(
                statement.get("period")
                or statement.get("fiscalDate")
                or statement.get("endDate")
                or statement.get("filed")
                or ""
            )
            for field, value in statement.items():
                if field in ("period", "fiscalDate", "endDate", "filed") or not _scalar(value):
                    continue
                rows.append({"symbol": symbol, "period": period, "field": field, "value": value})
        if budget.rows + len(rows) >= budget.max_rows:
            break
    return rows, problems


async def _collect_filings(
    source: AcquisitionSource, *, symbols: list[str], params: dict[str, Any],
    bridge: Any, budget: AcquisitionBudget,
) -> tuple[list[dict[str, Any]], list[str]]:
    """The SEC filing index, one bounded call per symbol (the filters ride each)."""
    rows: list[dict[str, Any]] = []
    problems: list[str] = []
    call_params = {
        key: str(params[key])
        for key in ("form", "date_from", "date_to")
        if str(params.get(key) or "").strip()
    }
    for symbol in symbols:
        if not budget.allow_call():
            break
        payload = await bridge.fetch(source.capability, {"symbol": symbol, **call_params})
        budget.record_call()
        if not isinstance(payload, dict) or payload.get("status") != "OK":
            error = (payload or {}).get("error") if isinstance(payload, dict) else "no response"
            _problem(problems, f"{symbol}: {error or 'no filings returned'}")
            continue
        filings = payload.get("filings") or []
        if not isinstance(filings, list) or not filings:
            _problem(problems, f"{symbol}: no filings matched the request")
            continue
        for filing in filings:
            if not isinstance(filing, dict):
                continue
            rows.append({
                "symbol": symbol,
                "form": filing.get("form"),
                "filed": filing.get("filed"),
                "period": filing.get("period"),
                "accession": filing.get("accession"),
                "document": filing.get("document"),
                "description": filing.get("description"),
            })
        if payload.get("truncated"):
            _problem(
                problems,
                f"{symbol}: reached this pull's filing ceiling — narrow the window "
                "(form / date_from / date_to) to collect the rest",
            )
        if len(rows) >= budget.max_rows:
            break
    return rows, problems


async def _collect_operator_datasets(
    source: AcquisitionSource, *, params: dict[str, Any],
    bridge: Any, budget: AcquisitionBudget,
) -> tuple[list[dict[str, Any]], list[str]]:
    """One declared dataset's records, flattened to long rows.

    The dataset NAME selects among the operator's declared datasets (the bridge
    refuses anything undeclared); `values` fills that connector's OWN declared
    parameters. A nested value is serialized as JSON text so no mapped field is
    silently dropped from the file.
    """
    rows: list[dict[str, Any]] = []
    problems: list[str] = []
    if not budget.allow_call():
        return rows, problems
    dataset = str(params.get("dataset") or "").strip()
    call_params: dict[str, Any] = {"dataset": dataset}
    values = params.get("values")
    if isinstance(values, dict):
        call_params["values"] = {str(key): value for key, value in values.items() if value is not None}
    elif isinstance(values, str) and values.strip():
        call_params["values"] = values.strip()
    payload = await bridge.fetch(source.capability, call_params)
    budget.record_call()
    if not isinstance(payload, dict):
        _problem(problems, f"{dataset or 'the dataset'}: no response from the data connection")
        return rows, problems
    if payload.get("status") != "OK":
        _problem(problems, f"{dataset or 'the dataset'}: {payload.get('error') or 'no data returned'}")
        return rows, problems
    named = payload.get("dataset")
    dataset_name = named.get("name") if isinstance(named, dict) else (str(named) if named else dataset)
    records = payload.get("records") or []
    if not isinstance(records, list):
        _problem(problems, f"{dataset_name}: the response carried no usable records")
        return rows, problems
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            continue
        key = str(record.get("recordKey") or index)
        record_values = record.get("values")
        if not isinstance(record_values, dict):
            continue
        for field, value in record_values.items():
            if isinstance(value, (dict, list)):
                value = json.dumps(value, sort_keys=True, ensure_ascii=False)
            rows.append({"dataset": dataset_name, "record": key, "field": str(field), "value": value})
        if len(rows) >= budget.max_rows:
            break
    if payload.get("truncated"):
        _problem(
            problems,
            f"{dataset_name}: reached this pull's record ceiling — ask again for a narrower set",
        )
    return rows, problems


__all__ = ["collect"]
