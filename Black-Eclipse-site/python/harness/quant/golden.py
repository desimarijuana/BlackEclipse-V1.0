"""Freeze a repaired series as an immutable golden dataset.

A golden dataset is the reference every backtest and test can cite. It is
content-hashed and versioned by the existing `DatasetStore`.
"""

from __future__ import annotations

from typing import Any, Iterable

from .data_quality import inspect_bars, repair_bars


def freeze_golden(
    dataset_store: Any, *,
    name: str, symbol: str, interval: str,
    rows: Iterable[dict[str, Any]], request: dict[str, Any] | None = None,
) -> dict[str, Any]:
    raw = list(rows or [])
    repair = repair_bars(raw, interval=interval, symbol=symbol)
    if not repair["after"]["gate"]["allowed"]:
        return {
            "status": "BLOCKED",
            "reason": "the repaired series still has critical findings",
            "after": repair["after"],
            "repair": {k: v for k, v in repair.items() if k != "rows"},
        }
    manifest = dataset_store.build_version(
        series={symbol.upper(): repair["rows"]},
        request={"interval": interval, "symbol": symbol.upper(),
                 **(request or {})},
        name=name,
        quality={"report": repair["after"]},
        lineage={"source": "golden-freeze", "repair": {
            "removedExact": repair["removedExact"],
            "conflictsKeptFirst": repair["conflictsKeptFirst"],
        }},
        created_by="operator",
    )
    return {
        "status": "OK",
        "datasetId": manifest.get("datasetId") or manifest.get("id"),
        "version": manifest.get("version"),
        "manifest": manifest,
        "quality": inspect_bars(repair["rows"], interval=interval, symbol=symbol),
        "repair": {k: v for k, v in repair.items() if k != "rows"},
    }


__all__ = ["freeze_golden"]
