"""FactorStore persistence round-trips."""

from __future__ import annotations

import pytest

from harness.factors.store import FactorStore
from harness.persistence import AgentMemoryStore


@pytest.fixture()
def store(tmp_path) -> FactorStore:
    return FactorStore(AgentMemoryStore(str(tmp_path / "am.db")), artifact_root=str(tmp_path / "art"))


def test_factor_versions_and_lookup(store):
    store.upsert_factor(factor_id="f1", name="Mom", description=None, family="momentum", owner="me",
                        direction="positive", frequency="1d", asset_class="equity", tags=["x"],
                        latest_version="1.0.0")
    store.add_version(factor_id="f1", version="1.0.0", expression="close-1", inputs=["close"],
                      params={}, normalization="cross_sectional_zscore", missing_policy="drop",
                      lookback=1, output_type="float", pit_safe=True, changelog="init")
    assert store.get_factor_by_name("Mom")["id"] == "f1"
    assert store.get_version("f1", "1.0.0")["expression"] == "close-1"
    assert store.get_version("f1", "1.0.0")["definitionHash"]
    assert [f["name"] for f in store.list_factors()] == ["Mom"]


def test_experiment_metrics_and_runs(store):
    exp = store.create_experiment(hypothesis="mom works", factor_refs=[{"factorId": "f1"}],
                                  universe={"symbols": ["A"]}, horizons=[1, 5], splits={}, cost={},
                                  config={})
    store.set_experiment_status(exp, "completed", {"outcome": "ok"})
    store.add_metric(exp, "meanIC", 0.03, {"method": "pearson"})
    rec = store.get_experiment(exp)
    assert rec["status"] == "completed"
    assert rec["outcome"] == {"outcome": "ok"}
    assert store.list_metrics(exp)[0]["value"] == 0.03

    store.upsert_run("run1", factor_id="f1", version="1.0.0", kind="evaluate", dataset_ref={"d": 1},
                     config={"h": 1}, status="running", stage="compute", done=1, total=3)
    store.upsert_run("run1", factor_id="f1", version="1.0.0", kind="evaluate", dataset_ref={"d": 1},
                     config={"h": 1}, status="completed", stage="done", done=3, total=3)
    run = store.get_run("run1")
    assert run["status"] == "completed" and run["done"] == 3


def test_portfolio_validation_lineage_and_artifact(store):
    run_id = store.save_portfolio_run(experiment_id=None, config={"q": 5}, metrics={"sharpe": 1.2},
                                      artifact_ref=None)
    assert store.get_portfolio_run(run_id)["metrics"]["sharpe"] == 1.2

    exp = store.create_experiment(hypothesis=None, factor_refs=[], universe={}, horizons=[],
                                  splits={}, cost={}, config={})
    vid = store.record_validation(experiment_id=exp, factor_ref="f1@1.0.0", status="passed",
                                  detail={"checks": []})
    rows = store.list_validations(exp)
    assert rows[0]["id"] == vid and rows[0]["status"] == "passed"

    store.add_lineage(child_type="strategy", child_id="s1", parent_type="factorVersion",
                      parent_id="f1@1.0.0", relation="promoted_from")
    assert store.lineage_for("strategy", "s1")[0]["parentId"] == "f1@1.0.0"

    ref = store.save_artifact({"series": list(range(4))})
    assert len(ref["sha256"]) == 64
    assert store.get_artifact(ref["id"])["content"] == {"series": [0, 1, 2, 3]}
