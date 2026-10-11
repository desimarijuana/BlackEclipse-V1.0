"""End-to-end Factor Lab workflow through the REAL agent tool handlers.

Exercises: create factor → evaluate (IC/rank-IC/decay) → quantile portfolio →
validation gate → promote to a quant strategy + experiment. Uses the real
handlers, real `FactorStore`/`QuantStore` and a deterministic fake market
gateway (no network).
"""

from __future__ import annotations

import numpy as np
import pytest

from harness.factors import service as S
from harness.factors.store import FactorStore
from harness.factors.tools import (
    FACTOR_TOOLS,
    create_factor_definition,
    promote_factor_to_strategy,
    run_factor_evaluation,
    run_quantile_portfolio,
    validate_alpha_experiment,
)
from harness.persistence import AgentMemoryStore
from harness.quant.store import QuantStore
from harness.tools import ToolContext

SYMS = ["AAA", "BBB", "CCC", "DDD", "EEE", "FFF"]


class FakeGateway:
    """A deterministic in-memory stand-in for the Market Data Gateway."""

    def __init__(self, series: dict[str, dict[str, list[float]]]) -> None:
        self._series = series

    async def get_historical_prices(self, symbol, *_args, start=None, end=None, interval="1d",
                                    adjusted=True, **_kw):
        s = self._series[str(symbol).upper()]
        bars = [{"timestamp": f"t{i}", "close": c, "volume": v}
                for i, (c, v) in enumerate(zip(s["close"], s.get("volume", [1.0] * len(s["close"]))))]
        return {"bars": bars, "provider": "fake", "symbol": symbol, "interval": interval}


def _mk_series(seed: int = 7, n: int = 260) -> dict[str, dict[str, list[float]]]:
    rng = np.random.default_rng(seed)
    out: dict[str, dict[str, list[float]]] = {}
    for i, sym in enumerate(SYMS):
        px = [100.0]
        for _ in range(n - 1):
            px.append(px[-1] * (1 + rng.normal(0.0004 * i, 0.011)))
        out[sym] = {"close": px, "volume": [1_000_000.0 + 1000 * (j % 7) for j in range(n)]}
    return out


@pytest.fixture()
def ctx(tmp_path):
    ams = AgentMemoryStore(str(tmp_path / "am.db"))
    fs = FactorStore(ams, artifact_root=str(tmp_path / "fart"))
    qs = QuantStore(ams, artifact_root=str(tmp_path / "qart"))
    S.set_factor_store(fs)
    context = ToolContext(run_id="e2e", log=lambda *_: None,
                          market_gateway=FakeGateway(_mk_series()), quant_store=qs)
    context._factor_store = fs  # noqa: SLF001 - test handle
    yield context, fs, qs
    S.set_factor_store(None)


async def test_full_workflow_create_evaluate_portfolio_validate_promote(ctx):
    context, fs, qs = ctx
    expression = "pct_change(close, 21)"

    text, created = await create_factor_definition(
        {"name": "E2E Momentum", "expression": expression, "family": "momentum",
         "direction": "positive"}, context)
    assert created["status"] == "ok"
    fid = created["factor"]["id"]
    assert created["factor"]["validationStatus"] == "valid"

    text, ev = await run_factor_evaluation(
        {"expression": expression, "symbols": SYMS, "horizons": [1, 5, 21]}, context)
    evaluation = ev["evaluation"]
    assert evaluation["ic"]["summary"]["available"] is True
    assert len(evaluation["decay"]["curve"]) == 3
    assert evaluation["symbols"] == SYMS

    text, pf = await run_quantile_portfolio(
        {"expression": expression, "symbols": SYMS, "quantiles": 3, "rebalance": 5, "costBps": 10.0},
        context)
    portfolio = pf["portfolio"]
    assert portfolio["longShortMetrics"]["available"] is True

    text, val = await validate_alpha_experiment(
        {"evaluation": evaluation, "portfolio": portfolio, "expectedDirection": "positive",
         "trialCount": 20, "srVariance": 0.0001}, context)
    assert val["validation"]["outcome"] in {"passed", "warning", "failed"}
    assert len(val["validation"]["checks"]) >= 5
    # the outcome is persisted as a first-class, auditable record
    assert val["validationId"]
    assert val["multipleTesting"]["deflatedSharpe"]["available"] is True

    text, pr = await promote_factor_to_strategy(
        {"factorId": fid, "symbols": SYMS, "quantiles": 3, "rebalance": 5, "costBps": 10.0}, context)
    assert pr["status"] == "ok", pr
    promotion = pr["promotion"]
    assert promotion["execution"] == "factor_portfolio"

    exp = qs.get_experiment(promotion["experimentId"])
    assert exp["kind"] == "factor_portfolio"
    assert exp["strategyId"] == promotion["strategyId"]

    lineage = fs.lineage_for("strategy", promotion["strategyId"])
    assert lineage and lineage[0]["parentId"] == f"{fid}@1.0.0"
    assert qs.list_approvals(promotion["strategyId"])[0]["status"] == "requested"


async def test_all_factor_tools_registered(ctx):
    from harness.tools import ToolRegistry

    from harness.factors.tools import register_factor_tools

    registry = ToolRegistry()
    names = register_factor_tools(registry)
    assert set(names) == set(FACTOR_TOOLS)
    assert set(FACTOR_TOOLS) <= set(registry.names())
