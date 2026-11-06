"""The unified model catalog is a read-only aggregation of the real registries."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from harness.model_catalog import build_catalog, model_catalog


class _Quant:
    def list_strategies(self, include_archived: bool = False):
        return [
            {"id": "strat_gold", "name": "Gold momentum", "latestVersion": "2",
             "archived": 0, "updatedAt": "2026-11-06T10:00:00Z"},
        ]

    def list_experiments(self, limit: int = 50):
        return [
            {"id": "exp_gold_1", "kind": "walk_forward", "strategyId": "strat_gold",
             "strategyVersion": "2", "status": "completed",
             "createdAt": "2026-11-06T11:00:00Z"},
        ]


class _ML:
    def list_models(self, limit: int = 100):
        return [
            {"id": "mdl_gold", "name": "Gold direction", "family": "classification",
             "latestVersion": "1", "status": "evaluated",
             "updatedAt": "2026-11-06T12:00:00Z"},
        ]

    def list_datasets(self, limit: int = 100):
        return [
            {"id": "ds_gold", "name": "Gold features", "latestVersion": "1",
             "updatedAt": "2026-11-06T09:00:00Z"},
        ]


class _Stats:
    def list_features(self):
        return [
            {"id": "feat_vol", "name": "realized vol", "latestVersion": "1",
             "updatedAt": "2026-11-05T09:00:00Z"},
        ]


class _Factors:
    def list_factors(self, include_archived: bool = False):
        return [
            {"id": "fac_value", "name": "value", "latestVersion": "1",
             "archived": 0, "updatedAt": "2026-11-04T09:00:00Z"},
        ]


def test_catalog_aggregates_every_registry() -> None:
    result = build_catalog(
        quant_store=_Quant(), ml_store=_ML(), stats_store=_Stats(),
        factor_store=_Factors(),
    )
    assert result["status"] == "OK"
    assert result["total"] == 6
    assert result["counts"] == {
        "experiment": 1, "factor": 1, "feature": 1,
        "ml_dataset": 1, "ml_model": 1, "strategy": 1,
    }
    assert result["truncated"] is False


def test_catalog_filters_by_kind_and_query() -> None:
    only_models = build_catalog(
        quant_store=_Quant(), ml_store=_ML(), kind="ml_model",
    )
    assert only_models["total"] == 1
    assert only_models["entries"][0]["id"] == "mdl_gold"

    query = build_catalog(
        quant_store=_Quant(), ml_store=_ML(), stats_store=_Stats(),
        factor_store=_Factors(), query="gold",
    )
    assert query["total"] == 4
    assert all("gold" in (
        str(entry.get("id")) + str(entry.get("name"))
    ).lower() for entry in query["entries"])


def test_a_saved_strategy_is_immediately_discoverable(tmp_path) -> None:
    from harness.persistence import AgentMemoryStore
    from harness.quant import strategy as S
    from harness.quant.store import QuantStore

    store = QuantStore(
        AgentMemoryStore(str(tmp_path / "am.db")),
        artifact_root=str(tmp_path / "art"),
    )
    store.save_strategy(S.parse_strategy({
        "strategy": {"id": "catalog_ema", "name": "Catalog EMA", "version": "1.0.0"},
        "universe": {"symbols": ["TESTUSDT"]},
        "indicators": [
            {"id": "ema_f", "type": "ema", "params": {"period": 5}},
            {"id": "ema_s", "type": "ema", "params": {"period": 20}},
        ],
        "rules": {"entry": {"long": {"conditions": [
            {"left": {"ref": "ema_f"}, "op": "cross_above",
             "right": {"ref": "ema_s"}}]}}, "exit": {}},
        "position_sizing": {"type": "percent_equity", "value": 90},
    }))
    result = build_catalog(quant_store=store, kind="strategy")
    assert result["total"] == 1
    assert result["entries"][0]["id"] == "catalog_ema"


def test_catalog_bounds_the_result() -> None:
    result = build_catalog(
        quant_store=_Quant(), ml_store=_ML(), limit=2,
    )
    assert result["total"] == 4
    assert len(result["entries"]) == 2
    assert result["truncated"] is True


@pytest.mark.asyncio
async def test_the_tool_reads_the_stores_from_the_context() -> None:
    ctx = SimpleNamespace(
        quant_store=_Quant(), ml_store=_ML(), stats_store=_Stats(),
        factor_store=_Factors(),
    )
    text, data = await model_catalog({"limit": 10}, ctx)  # type: ignore[arg-type]
    assert "Model catalog: 6 artifact(s)" in text
    assert data["total"] == 6


@pytest.mark.asyncio
async def test_an_empty_catalog_is_honest_not_an_unavailable_capability() -> None:
    text, data = await model_catalog({}, SimpleNamespace(  # type: ignore[arg-type]
        quant_store=None, ml_store=None, stats_store=None, factor_store=None,
    ))
    assert data["total"] == 0
    assert "empty registry, not an unavailable capability" in text
