"""Phase 16 (first slice) — bounded bulk acquisition: registry, budget, writer,
the `acquire` tool, and the default-denied `data.collect` grant.

Hermetic: an isolated memory policy store, a stub data bridge (no network), and
a temp artifact directory.
"""

from __future__ import annotations

import asyncio
import csv
import os

import pytest


def run(coro):
    return asyncio.run(coro)


class _Bridge:
    """A stub of the read-only data bridge. Records every call."""

    def __init__(self, payloads=None):
        self.payloads = payloads or {}
        self.calls: list[dict] = []

    async def fetch(self, capability, params):
        self.calls.append({"capability": capability, "params": params})
        key = params.get("symbol") or params.get("seriesId")
        return self.payloads.get(key, {"status": "UNAVAILABLE", "error": "no data returned"})


@pytest.fixture()
def env(monkeypatch, tmp_path):
    from harness.eclipse_memory.service import EclipseMemoryService
    from harness.eclipse_memory.store import EclipseMemoryStore
    from harness.tools import ToolContext
    from harness.acquire import tools as acquire_tools

    memory = EclipseMemoryService(EclipseMemoryStore(os.path.join(str(tmp_path), "eclipse-memory.db")))
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    monkeypatch.setattr(acquire_tools, "artifact_dir_for", lambda run_id: artifacts)

    ctx = ToolContext(run_id="test-acquire", log=lambda *a, **k: None)
    ctx.memory_service = memory
    try:
        yield acquire_tools, memory, ctx, artifacts
    finally:
        memory.close()


def _enable(memory, on: bool = True) -> None:
    memory.policy.set("acquisition_enabled", on)


def _prices_bridge(*symbols: str) -> _Bridge:
    series = [
        {"date": "2024-01-02", "open": 1, "high": 2, "low": 0.5, "close": 1.5, "volume": 100},
        {"date": "2024-01-03", "open": 1.5, "high": 2.5, "low": 1, "close": 2, "volume": 200},
    ]
    return _Bridge({
        symbol: {"status": "OK", "symbol": symbol, "currency": "USD", "series": list(series)}
        for symbol in symbols
    })


def test_registry_rows_are_complete_and_declared():
    from harness.acquire.registry import registry_issues

    assert registry_issues() == []


def test_budget_bounds_are_enforced_and_recorded():
    from harness.acquire.budget import AcquisitionBudget

    budget = AcquisitionBudget(max_calls=1, max_rows=2, max_bytes_written=10_000, max_seconds=60)
    assert budget.allow_call() is True
    budget.record_call()
    assert budget.allow_call() is False
    assert "1 requests" in str(budget.exhausted)

    rows = AcquisitionBudget(max_rows=2)
    rows.record_rows(2)
    assert rows.exhausted and "2 rows" in rows.exhausted


def test_writer_stops_at_the_row_ceiling_and_marks_partial(tmp_path):
    from harness.acquire.budget import AcquisitionBudget
    from harness.acquire.writer import write_csv

    budget = AcquisitionBudget(max_rows=5)
    rows = [{"a": i} for i in range(10)]
    path = tmp_path / "out.csv"
    written, complete, stopped = write_csv(path, ("a",), rows, budget)

    assert written == 5
    assert complete is False
    assert "5 rows" in stopped
    # The count equals what is REALLY in the file (read it back).
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 6  # header + 5 rows
    # And the budget itself names the limit.
    assert budget.exhausted == stopped


def test_grant_is_default_denied():
    from harness.code.policy import acquisition_grants
    from harness.skills.permissions import DATA_PERMISSIONS, OPERATOR_PERMISSIONS, SAFE_PERMISSIONS

    assert "data.collect" not in acquisition_grants("none")
    assert acquisition_grants("unknown-profile") == frozenset()
    assert "data.collect" in acquisition_grants("declared_sources")
    # The noun is neither in the safe set nor in the operator set.
    assert not (DATA_PERMISSIONS & SAFE_PERMISSIONS)
    assert not (DATA_PERMISSIONS & OPERATOR_PERMISSIONS)


def test_acquire_refused_when_the_switch_is_off(env):
    acquire_tools, memory, ctx, _ = env
    _enable(memory, False)
    _, data = run(acquire_tools._acquire(
        {"source": "prices_daily", "purpose": "watchlist history", "params": {}, "symbols": ["AAPL"]},
        ctx,
    ))
    assert data["status"] == "refused"
    assert data["code"] == "ACQUISITION_OFF"


def test_acquire_collects_and_manifests_a_complete_pull(env):
    acquire_tools, memory, ctx, artifacts = env
    _enable(memory, True)
    ctx.data_bridge = _prices_bridge("AAPL", "MSFT")

    text, data = run(acquire_tools._acquire(
        {"source": "prices_daily", "purpose": "two years for the watchlist",
         "params": {"range": "2y"}, "symbols": ["AAPL", "MSFT"]},
        ctx,
    ))
    assert data["status"] == "ok", data
    source = data["manifest"]["sources"][0]
    assert source["complete"] is True
    assert source["rows"] == 4
    assert source["file"]

    path = artifacts / source["file"]
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 5  # header + 4 rows
    assert source["rows"] == len(lines) - 1  # the manifest equals the real file

    # One call per instrument, through the declared capability, with the closed
    # parameters only.
    assert [c["capability"] for c in ctx.data_bridge.calls] == ["price_history", "price_history"]
    assert ctx.data_bridge.calls[0]["params"]["range"] == "2y"
    assert ctx.data_bridge.calls[0]["params"]["symbol"] == "AAPL"

    # The manifest carries the licence and attribution.
    assert source["licence"]
    assert source["attribution"]


def test_acquire_marks_a_partial_pull(env):
    acquire_tools, memory, ctx, artifacts = env
    _enable(memory, True)
    ctx.data_bridge = _prices_bridge("AAPL")  # MSFT will be UNAVAILABLE

    _, data = run(acquire_tools._acquire(
        {"source": "prices_daily", "purpose": "watchlist",
         "params": {}, "symbols": ["AAPL", "MSFT"]},
        ctx,
    ))
    assert data["status"] == "partial"
    source = data["manifest"]["sources"][0]
    assert source["complete"] is False
    assert source["rows"] == 2
    assert "MSFT" in str(source["stoppedReason"])
    assert any("MSFT" in p for p in data["problems"])


def test_acquire_refusals_name_the_reason(env):
    acquire_tools, memory, ctx, _ = env
    _enable(memory, True)

    _, unknown = run(acquire_tools._acquire(
        {"source": "nope", "purpose": "x", "params": {}}, ctx))
    assert unknown["code"] == "UNKNOWN_SOURCE"

    _, bad_param = run(acquire_tools._acquire(
        {"source": "prices_daily", "purpose": "x", "params": {"url": "https://evil"}, "symbols": ["AAPL"]},
        ctx))
    assert bad_param["code"] == "UNKNOWN_PARAM"

    _, bad_range = run(acquire_tools._acquire(
        {"source": "prices_daily", "purpose": "x", "params": {"range": "forever"}, "symbols": ["AAPL"]},
        ctx))
    assert bad_range["code"] == "INVALID_PARAM_VALUE"

    _, missing = run(acquire_tools._acquire(
        {"source": "prices_daily", "purpose": "x", "params": {}}, ctx))
    assert missing["code"] == "MISSING_SYMBOLS"

    _, no_purpose = run(acquire_tools._acquire(
        {"source": "macro_series", "purpose": "", "params": {"series": "CPIAUCSL"}}, ctx))
    assert no_purpose["code"] == "MISSING_PURPOSE"

    _, no_bridge = run(acquire_tools._acquire(
        {"source": "prices_daily", "purpose": "x", "params": {}, "symbols": ["AAPL"]}, ctx))
    assert no_bridge["code"] == "BRIDGE_UNAVAILABLE"


def test_acquire_macro_series_writes_long_rows(env):
    acquire_tools, memory, ctx, artifacts = env
    _enable(memory, True)
    ctx.data_bridge = _Bridge({
        "CPIAUCSL": {"status": "OK", "seriesKey": "CPIAUCSL", "rows": [
            {"date": "2024-01-01", "value": 308.4},
            {"date": "2024-02-01", "value": 309.1},
        ]},
    })
    _, data = run(acquire_tools._acquire(
        {"source": "macro_series", "purpose": "inflation study",
         "params": {"series": "CPIAUCSL", "quantity": 24}},
        ctx,
    ))
    assert data["status"] == "ok", data
    source = data["manifest"]["sources"][0]
    with (artifacts / source["file"]).open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert [r["series"] for r in rows] == ["CPIAUCSL", "CPIAUCSL"]
    assert [r["value"] for r in rows] == ["308.4", "309.1"]
