"""Durable background factor promotion through the Execution Fabric.

Submits a `quant` job that the fabric's quant worker delegates to the REAL
`promote_factor_to_strategy` tool, and asserts the strategy + experiment persist.
"""

from __future__ import annotations

import numpy as np

from harness.events import EventBus
from harness.fabric import JobState
from harness.fabric.bootstrap import install_fabric_layer, start_fabric, stop_fabric
from harness.factors import service as S
from harness.factors.models import FactorDefinition
from harness.factors.store import FactorStore
from harness.factors.tools import register_factor_tools
from harness.persistence import AgentMemoryStore
from harness.quant.store import QuantStore
from harness.tools import ToolRegistry

from fabric_helpers import make_store, wait_terminal

SYMS = ["AAA", "BBB", "CCC", "DDD", "EEE", "FFF"]


class FakeGateway:
    def __init__(self, series: dict[str, dict[str, list[float]]]) -> None:
        self._series = series

    async def get_historical_prices(self, symbol, *_a, start=None, end=None, interval="1d",
                                    adjusted=True, **_kw):
        s = self._series[str(symbol).upper()]
        bars = [{"timestamp": f"t{i}", "close": c, "volume": v}
                for i, (c, v) in enumerate(zip(s["close"], s["volume"]))]
        return {"bars": bars, "provider": "fake", "symbol": symbol}


def _series(seed: int = 3, n: int = 240) -> dict[str, dict[str, list[float]]]:
    rng = np.random.default_rng(seed)
    out: dict[str, dict[str, list[float]]] = {}
    for i, sym in enumerate(SYMS):
        px = [100.0]
        for _ in range(n - 1):
            px.append(px[-1] * (1 + rng.normal(0.0004 * i, 0.011)))
        out[sym] = {"close": px, "volume": [1_000_000.0] * n}
    return out


class StubService:
    def __init__(self, store: AgentMemoryStore, qs: QuantStore) -> None:
        self.store = store
        self.registry = ToolRegistry()
        register_factor_tools(self.registry)
        self.bus = EventBus()
        self.market_gateway = FakeGateway(_series())
        self.quant_store = qs


async def test_background_factor_promotion_persists(tmp_path):
    ams = make_store(tmp_path)
    fs = FactorStore(ams, artifact_root=str(tmp_path / "fart"))
    qs = QuantStore(ams, artifact_root=str(tmp_path / "qart"))
    S.set_factor_store(fs)
    saved = S.save_factor(FactorDefinition(name="BG Momentum", expression="pct_change(close, 21)",
                                           family="momentum", direction="positive"))
    fid = saved["factor"]["id"]

    service = StubService(ams, qs)
    manager = install_fabric_layer(service)
    await start_fabric(service)
    try:
        submitted = await manager.submit(
            "quant",
            {"tool": "promote_factor_to_strategy",
             "args": {"factorId": fid, "symbols": SYMS, "quantiles": 3, "rebalance": 5, "costBps": 10.0}},
            mode="background",
        )
        job = await wait_terminal(manager, submitted["jobId"])
        assert job["status"] == JobState.SUCCEEDED.value, job
        promotion = job["output"]["promotion"]
        assert promotion["execution"] == "factor_portfolio"
        assert promotion["experimentId"]
        exp = qs.get_experiment(promotion["experimentId"])
        assert exp["kind"] == "factor_portfolio"
        lineage = fs.lineage_for("strategy", promotion["strategyId"])
        assert lineage and lineage[0]["parentId"] == f"{fid}@1.0.0"
    finally:
        await stop_fabric(service)
        S.set_factor_store(None)
