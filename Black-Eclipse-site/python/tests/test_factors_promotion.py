"""Factor → strategy promotion through the ONE quant store (Phase 10)."""

from __future__ import annotations

import numpy as np
import pytest

from harness.factors import service as S
from harness.factors.models import FactorDefinition
from harness.factors.promotion import promote_to_strategy
from harness.factors.store import FactorStore
from harness.persistence import AgentMemoryStore
from harness.quant.store import QuantStore
from harness.stats.base import StatsError

SYMS = ["A", "B", "C", "D", "E", "F"]


def _series(seed: int = 5, n: int = 260) -> dict[str, dict[str, list[float]]]:
    rng = np.random.default_rng(seed)
    out: dict[str, dict[str, list[float]]] = {}
    for i, sym in enumerate(SYMS):
        px = [100.0]
        for _ in range(n - 1):
            px.append(px[-1] * (1 + rng.normal(0.0003 * i, 0.012)))
        out[sym] = {"close": px}
    return out


@pytest.fixture()
def stores(tmp_path):
    ams = AgentMemoryStore(str(tmp_path / "am.db"))
    fs = FactorStore(ams, artifact_root=str(tmp_path / "fart"))
    qs = QuantStore(ams, artifact_root=str(tmp_path / "qart"))
    S.set_factor_store(fs)
    yield fs, qs
    S.set_factor_store(None)


def test_promote_persists_strategy_experiment_and_lineage(stores):
    fs, qs = stores
    saved = S.save_factor(FactorDefinition(name="Promo Mom", expression="pct_change(close, 21)",
                                           family="momentum", direction="positive"))
    fid = saved["factor"]["id"]
    assert fs.get_factor(fid)["validationStatus"] == "valid"

    res = promote_to_strategy(
        factor_id=fid, version=None,
        config={"quantiles": 3, "rebalance": 5, "costBps": 10.0, "interval": "1d"},
        symbols=SYMS, series_by_symbol=_series(), quant_store=qs, actor="tester",
    )
    assert res["strategyId"].startswith("strategy_factor_")
    assert res["execution"] == "factor_portfolio"

    strategy = qs.get_strategy(res["strategyId"], res["strategyVersion"])
    assert strategy["spec"]["metadata"]["factorId"] == fid
    assert strategy["spec"]["metadata"]["execution"] == "factor_portfolio"
    assert strategy["spec"]["universe"]["symbols"] == SYMS

    exp = qs.get_experiment(res["experimentId"])
    assert exp["kind"] == "factor_portfolio"
    assert exp["strategyId"] == res["strategyId"]

    lineage = fs.lineage_for("strategy", res["strategyId"])
    assert lineage[0]["parentId"] == f"{fid}@1.0.0"
    exp_lineage = fs.lineage_for("experiment", res["experimentId"])
    assert exp_lineage[0]["relation"] == "executed_for"

    assert res["approval"]["status"] == "requested"
    assert qs.list_approvals(res["strategyId"])[0]["status"] == "requested"


def test_promote_rejects_unvalidated_factor(stores):
    fs, qs = stores
    saved = S.save_factor(FactorDefinition(name="Broken", expression="not_a_function(close)"))
    fid = saved["factor"]["id"]
    assert fs.get_factor(fid)["validationStatus"] == "invalid"
    with pytest.raises(StatsError) as exc:
        promote_to_strategy(factor_id=fid, version=None, config={}, symbols=SYMS,
                            series_by_symbol=_series(), quant_store=qs)
    assert exc.value.code == "NOT_VALIDATED"


def test_promote_requires_quant_store(stores):
    fs, _ = stores
    saved = S.save_factor(FactorDefinition(name="No Quant", expression="pct_change(close, 5)"))
    fid = saved["factor"]["id"]
    with pytest.raises(StatsError) as exc:
        promote_to_strategy(factor_id=fid, version=None, config={}, symbols=SYMS,
                            series_by_symbol=_series(), quant_store=None)
    assert exc.value.code == "DEPENDENCY_MISSING"
