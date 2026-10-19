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
        key = params.get("symbol") or params.get("seriesId") or params.get("dataset")
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


def test_the_phase16_remainder_sources_are_declared():
    """The SEC filing index and the operator's declared datasets are ROWS."""
    from harness.acquire.registry import get_source

    filings = get_source("filings_list")
    assert filings is not None
    assert filings.capability == "sec_filing_list"
    assert filings.accepts_symbols
    assert "form" in filings.query_params
    assert "date_from" in filings.query_params
    assert "document" in filings.columns

    datasets = get_source("operator_datasets")
    assert datasets is not None
    assert datasets.capability == "custom_dataset_records"
    assert not datasets.accepts_symbols
    assert "dataset" in datasets.query_params
    assert datasets.columns == ("dataset", "record", "field", "value")


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


def test_acquisition_is_bounded_across_calls_in_one_turn(env):
    """The per-call budget bounds one pull; the run ledger bounds the turn."""
    from harness.acquire.budget import RunUsage

    acquire_tools, memory, ctx, _ = env
    _enable(memory, True)
    ctx.data_bridge = _prices_bridge("AAPL", "MSFT")
    ctx._acquire_run_usage = RunUsage(max_calls=1, max_rows=50_000)  # test seam

    first_text, first = run(acquire_tools._acquire(
        {"source": "prices_daily", "purpose": "first pull", "params": {}, "symbols": ["AAPL"]},
        ctx,
    ))
    assert first["status"] == "ok", first
    # The manifest carries BOTH budgets: this pull's and the turn's.
    assert first["manifest"]["limits"]["run"]["callsUsed"] == 1
    assert first["manifest"]["limits"]["run"]["exhausted"]

    _, second = run(acquire_tools._acquire(
        {"source": "prices_daily", "purpose": "second pull", "params": {}, "symbols": ["MSFT"]},
        ctx,
    ))
    assert second["status"] == "refused"
    assert second["code"] == "RUN_LIMIT_REACHED"
    assert second["runUsage"]["exhausted"]
    # Nothing was fetched for the refused pull.
    assert [c["params"]["symbol"] for c in ctx.data_bridge.calls] == ["AAPL"]


def test_run_usage_accumulates_rows_and_bytes(env):
    from harness.acquire.budget import AcquisitionBudget, RunUsage

    usage = RunUsage(max_calls=10, max_rows=4)
    usage.absorb(AcquisitionBudget(calls=2, rows=3, bytes_written=100))
    assert usage.calls == 2 and usage.rows == 3
    assert usage.exhausted is None
    usage.absorb(AcquisitionBudget(calls=1, rows=2, bytes_written=50))
    assert usage.rows == 5
    assert usage.exhausted and "4 rows" in usage.exhausted
    assert usage.snapshot()["rowsUsed"] == 5


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


def test_acquire_collects_sec_filing_list(env):
    acquire_tools, memory, ctx, artifacts = env
    _enable(memory, True)
    ctx.data_bridge = _Bridge({
        "AAPL": {"status": "OK", "filings": [
            {"form": "10-K", "filed": "2024-11-01", "period": "2024-09-28",
             "accession": "0000320193-24-000123",
             "document": "https://www.sec.gov/Archives/edgar/data/320193/000032019324000123/aapl.htm",
             "description": "Annual report"},
            {"form": "8-K", "filed": "2024-08-01", "period": None,
             "accession": "0000320193-24-000100", "document": None,
             "description": "Current report"},
        ], "count": 2, "truncated": False},
    })
    _, data = run(acquire_tools._acquire(
        {"source": "filings_list", "purpose": "annual reports for the watchlist",
         "params": {"form": "10-K", "date_from": "2024-01-01"}, "symbols": ["AAPL"]},
        ctx,
    ))
    assert data["status"] == "ok", data
    source = data["manifest"]["sources"][0]
    assert source["complete"] is True
    assert source["rows"] == 2
    assert source["licence"] and source["attribution"]

    # One call per instrument, through the declared capability, with the
    # filters riding the call (the closed set only).
    assert ctx.data_bridge.calls == [{
        "capability": "sec_filing_list",
        "params": {"symbol": "AAPL", "form": "10-K", "date_from": "2024-01-01"},
    }]

    with (artifacts / source["file"]).open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert [r["form"] for r in rows] == ["10-K", "8-K"]
    assert rows[0]["document"].startswith("https://www.sec.gov/Archives/")
    # An omitted field is an empty cell — never an invented value.
    assert rows[1]["period"] == ""


def test_acquire_filings_partial_and_ceiling_are_stated(env):
    acquire_tools, memory, ctx, _ = env
    _enable(memory, True)
    ctx.data_bridge = _Bridge({
        "AAPL": {"status": "OK", "truncated": True,
                 "filings": [{"form": "8-K", "filed": "2024-01-01", "accession": "a1"}]},
        # MSFT missing → UNAVAILABLE from the stub
    })
    _, data = run(acquire_tools._acquire(
        {"source": "filings_list", "purpose": "watchlist filings",
         "params": {}, "symbols": ["AAPL", "MSFT"]},
        ctx,
    ))
    assert data["status"] == "partial"
    source = data["manifest"]["sources"][0]
    assert source["complete"] is False
    assert source["rows"] == 1
    # Both causes are stated: the missing symbol and the per-call ceiling.
    assert any("MSFT" in p for p in data["problems"])
    assert any("ceiling" in p for p in data["problems"])
    assert source["stoppedReason"]


def test_acquire_operator_dataset_writes_long_rows(env):
    acquire_tools, memory, ctx, artifacts = env
    _enable(memory, True)
    ctx.data_bridge = _Bridge({
        "orders": {"status": "OK",
                   "dataset": {"id": "ds1", "name": "orders"},
                   "connector": {"id": "custom:c1", "name": "Test API"},
                   "records": [
                       {"recordKey": "BTC", "values": {"symbol": "BTC", "qty": 2.5,
                                                       "meta": {"venue": "spot"}}},
                   ], "count": 1, "truncated": False},
    })
    _, data = run(acquire_tools._acquire(
        {"source": "operator_datasets", "purpose": "the desk's order feed",
         "params": {"dataset": "orders", "values": {"symbol": "BTC"}}},
        ctx,
    ))
    assert data["status"] == "ok", data
    assert ctx.data_bridge.calls[0]["capability"] == "custom_dataset_records"
    assert ctx.data_bridge.calls[0]["params"] == {"dataset": "orders", "values": {"symbol": "BTC"}}

    source = data["manifest"]["sources"][0]
    with (artifacts / source["file"]).open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert [(r["dataset"], r["record"], r["field"]) for r in rows] == [
        ("orders", "BTC", "symbol"), ("orders", "BTC", "qty"), ("orders", "BTC", "meta"),
    ]
    # A nested mapped value survives as JSON text — not silently dropped.
    assert rows[2]["value"] == '{"venue": "spot"}'


def test_acquire_operator_dataset_accepts_a_values_json_string(env):
    acquire_tools, memory, ctx, _ = env
    _enable(memory, True)
    ctx.data_bridge = _Bridge({
        "orders": {"status": "OK", "dataset": "orders",
                   "records": [{"recordKey": "ETH", "values": {"symbol": "ETH"}}],
                   "count": 1, "truncated": False},
    })
    _, data = run(acquire_tools._acquire(
        {"source": "operator_datasets", "purpose": "desk feed",
         "params": {"dataset": "orders", "values": '{"symbol": "ETH"}'}},
        ctx,
    ))
    assert data["status"] == "ok", data
    assert ctx.data_bridge.calls[0]["params"]["values"] == '{"symbol": "ETH"}'


def test_acquire_operator_dataset_failure_is_honest(env):
    acquire_tools, memory, ctx, artifacts = env
    _enable(memory, True)
    ctx.data_bridge = _Bridge({})  # every dataset key → UNAVAILABLE
    text, data = run(acquire_tools._acquire(
        {"source": "operator_datasets", "purpose": "desk feed",
         "params": {"dataset": "orders"}},
        ctx,
    ))
    assert data["status"] != "ok"
    assert data["file"] is None
    assert data["manifest"]["sources"][0]["complete"] is False
    assert data["manifest"]["sources"][0]["rows"] == 0
    assert text.startswith("I couldn't collect")
    # Whatever reached disk carries no fabricateable row: header only.
    for path in artifacts.glob("*.csv"):
        assert len(path.read_text(encoding="utf-8").strip().splitlines()) <= 1


class _Emitter:
    """A stub of the run's event emitter. Records every event."""

    def __init__(self):
        self.events: list[tuple[str, dict]] = []

    async def emit(self, event_type, data):
        self.events.append((event_type, data))


def test_acquire_emits_its_manifest_for_the_chat_panel(env):
    """`acquire.completed` carries the SAME manifest written beside the CSV."""
    acquire_tools, memory, ctx, _ = env
    _enable(memory, True)
    ctx.data_bridge = _prices_bridge("AAPL")
    ctx.emitter = _Emitter()

    _, data = run(acquire_tools._acquire(
        {"source": "prices_daily", "purpose": "watchlist", "params": {}, "symbols": ["AAPL"]},
        ctx,
    ))
    assert data["status"] == "ok"
    assert [e[0] for e in ctx.emitter.events] == ["acquire.completed"]
    event = ctx.emitter.events[0][1]
    assert event["status"] == "ok"
    assert event["file"] == data["file"]
    assert event["manifest"] == data["manifest"]
    source = event["manifest"]["sources"][0]
    assert source["complete"] is True
    assert source["rows"] == 2
    assert source["licence"] and source["attribution"]


def test_acquire_refusals_emit_no_manifest_event(env):
    acquire_tools, memory, ctx, _ = env
    _enable(memory, False)
    ctx.emitter = _Emitter()
    _, data = run(acquire_tools._acquire(
        {"source": "prices_daily", "purpose": "watchlist", "params": {}, "symbols": ["AAPL"]},
        ctx,
    ))
    assert data["status"] == "refused"
    assert ctx.emitter.events == []


_LIVE = os.environ.get("HARNESS_ACQUIRE_IT") == "1"


@pytest.mark.skipif(
    not _LIVE,
    reason="opt-in live smoke: set HARNESS_ACQUIRE_IT=1 (needs the running front door)",
)
def test_live_macro_collection_through_the_real_bridge(env):
    """The opt-in live smoke: the REAL read-only bridge, one tiny macro pull.

    Deliberately never in CI (`npm test`); run it from `Black-Eclipse-site/` with
    the dev server up and `HARNESS_ACQUIRE_IT=1` (plus
    `HARNESS_LIVE_BRIDGE_URL`/`HARNESS_LIVE_BRIDGE_TOKEN` when they differ from
    the defaults / `CRON_SECRET`).
    """
    from harness.bridge import HttpDataBridge

    acquire_tools, memory, ctx, artifacts = env
    _enable(memory, True)
    base = os.environ.get("HARNESS_LIVE_BRIDGE_URL", "http://127.0.0.1:3000")
    token = os.environ.get("HARNESS_LIVE_BRIDGE_TOKEN") or os.environ.get("CRON_SECRET") or None
    ctx.data_bridge = HttpDataBridge(base, token)
    _, data = run(acquire_tools._acquire(
        {"source": "macro_series", "purpose": "live smoke (opt-in)",
         "params": {"series": "CPIAUCSL", "quantity": 12}},
        ctx,
    ))
    assert data["status"] in ("ok", "partial"), data
    assert data["manifest"]["sources"][0]["rows"] >= 1
