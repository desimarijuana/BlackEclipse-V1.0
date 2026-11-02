"""The bounded graph asset store and the three file nodes."""

from __future__ import annotations

import io
import json

import pytest

from harness.graph_runtime.assets import (
    AssetNotFound,
    AssetUnsupportedType,
    GraphAssetStore,
    set_asset_store,
)
from harness.graph_runtime.file_nodes import (
    exec_file_attach,
    exec_file_export,
    exec_file_parse,
)
from harness.graph_runtime.model import ExecutionMode
from harness.graph_runtime.nodes import build_default_registry
from harness.graph_runtime.registry import NodeExecContext
from harness.persistence import AgentMemoryStore

REGISTRY = build_default_registry()


@pytest.fixture()
def assets(tmp_path):
    store = GraphAssetStore(AgentMemoryStore(str(tmp_path / "agent-memory.db")))
    set_asset_store(store)
    try:
        yield store
    finally:
        set_asset_store(None)


def _ctx(config=None, inputs=None, *, user="local", test_run=False):
    return NodeExecContext(
        node_id="file",
        run_id="run",
        mode=ExecutionMode.RESEARCH,
        inputs=inputs or {},
        config=config or {},
        user_id=user,
        test_run=test_run,
    )


def _save_csv(store, text="date,close\n2026-01-01,100\n2026-01-02,101\n", name="bars.csv"):
    return store.save(name, text.encode("utf-8"), mime="text/csv")


# ── store ────────────────────────────────────────────────────────────────────

def test_store_roundtrip_is_content_addressed_and_owner_scoped(assets):
    first = assets.save("bars.csv", b"a,b\n1,2\n", mime="text/csv")
    second = assets.save("copy.csv", b"a,b\n1,2\n", mime="text/csv")
    assert first["assetId"] == second["assetId"]  # same bytes, same owner
    assert assets.open_bytes(first["assetId"]) == b"a,b\n1,2\n"
    assert assets.get(first["ref"])["name"] == "bars.csv"

    with pytest.raises(AssetNotFound):
        assets.open_bytes(first["assetId"], owner="someone-else")


def test_store_rejects_unsupported_types_and_empty_files(assets):
    with pytest.raises(AssetUnsupportedType):
        assets.save("payload.exe", b"MZ", mime="application/x-msdownload")
    with pytest.raises(Exception, match="empty"):
        assets.save("empty.csv", b"", mime="text/csv")


def test_store_list_and_delete(assets):
    meta = assets.save("one.csv", b"x\n1\n", mime="text/csv")
    assert [item["assetId"] for item in assets.list()] == [meta["assetId"]]
    assert assets.delete(meta["assetId"]) == 1
    with pytest.raises(AssetNotFound):
        assets.get(meta["assetId"])


# ── data.file.attach ────────────────────────────────────────────────────────

def test_attach_parses_csv_into_rows_and_columns(assets):
    meta = _save_csv(assets)
    result = exec_file_attach(_ctx({"assetId": meta["assetId"], "parseAs": "auto"}))
    assert result["file"]["assetId"] == meta["assetId"]
    assert result["rows"] == [
        {"date": "2026-01-01", "close": "100"},
        {"date": "2026-01-02", "close": "101"},
    ]
    assert result["meta"]["columns"] == ["date", "close"]
    assert result["meta"]["truncated"] is False


def test_attach_truncates_at_max_rows(assets):
    meta = _save_csv(assets)
    result = exec_file_attach(_ctx({"assetId": meta["assetId"], "maxRows": 1}))
    assert len(result["rows"]) == 1
    assert result["meta"]["truncated"] is True


def test_attach_parses_json_and_text(assets):
    meta = assets.save("rows.json", json.dumps([{"a": 1}, {"a": 2}]).encode(), mime="application/json")
    result = exec_file_attach(_ctx({"assetId": meta["assetId"]}))
    assert result["rows"] == [{"a": 1}, {"a": 2}]
    assert result["meta"]["columns"] == ["a"]

    text = assets.save("notes.txt", b"hello", mime="text/plain")
    assert exec_file_attach(_ctx({"assetId": text["assetId"]}))["text"] == "hello"


def test_attach_missing_file_fails_by_name(assets):
    with pytest.raises(ValueError, match="does not exist"):
        exec_file_attach(_ctx({"assetId": "gas_missing"}))


# ── data.file.parse ─────────────────────────────────────────────────────────

def test_parse_accepts_a_file_object_wire(assets):
    meta = _save_csv(assets)
    result = exec_file_parse(_ctx({}, {"file": {"assetId": meta["assetId"]}}))
    assert result["rows"][0]["close"] == "100"
    assert result["meta"]["parseAs"] == "csv"


# ── data.file.export ────────────────────────────────────────────────────────

def test_export_csv_roundtrips_through_attach(assets):
    result = exec_file_export(_ctx(
        {"format": "csv", "name": "out"},
        {"rows": [{"date": "2026-01-01", "close": 100}, {"date": "2026-01-02", "close": 101}]},
    ))
    assert result["name"] == "out.csv"
    assert result["bytes"] > 0
    attached = exec_file_attach(_ctx({"assetId": result["artifact"]["assetId"]}))
    assert attached["rows"][1] == {"date": "2026-01-02", "close": "101"}


def test_export_json_is_a_local_write_allowed_in_a_test_run(assets):
    result = exec_file_export(_ctx(
        {"format": "json", "name": "out"},
        {"rows": [{"a": 1}]},
        test_run=True,
    ))
    assert result["artifact"]["mime"] == "application/json"
    attached = exec_file_attach(_ctx({"assetId": result["artifact"]["assetId"]}))
    assert attached["meta"]["parseAs"] == "json"


def test_export_requires_rows(assets):
    with pytest.raises(ValueError, match="no rows to export"):
        exec_file_export(_ctx({"format": "csv"}))


def test_export_xlsx_roundtrips(assets):
    result = exec_file_export(_ctx(
        {"format": "xlsx", "name": "book"},
        {"rows": [{"a": 1, "b": "x"}]},
    ))
    attached = exec_file_attach(_ctx({"assetId": result["artifact"]["assetId"]}))
    assert attached["rows"] == [{"a": 1, "b": "x"}]


# ── registry ────────────────────────────────────────────────────────────────

def test_file_nodes_are_registered_with_executors():
    for node_type in ("data.file.attach", "data.file.parse", "data.file.export"):
        definition = REGISTRY.get(node_type)
        assert definition is not None, node_type
        assert definition.executor is not None
