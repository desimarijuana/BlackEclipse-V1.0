"""The strategy catalog: every strategy with its latest evidence, in one call.

This is what Strategy Studio and the New-bot picker read. Evidence is never
invented: a strategy with no backtest/approval/paper run returns `None` for that
field, and archived rows stay hidden unless asked for.
"""

from __future__ import annotations

from harness.persistence import AgentMemoryStore
from harness.quant import data as D
from harness.quant import engine as E
from harness.quant import fixtures as F
from harness.quant import strategy as S
from harness.quant.store import QuantStore


def _spec():
    return S.parse_strategy({
        "strategy": {"id": "cat_test", "name": "Catalog test", "version": "1.0.0"},
        "universe": {"symbols": ["TESTUSDT"]},
        "rules": {
            "entry": {"long": {"conditions": [
                {"left": {"ref": "close"}, "op": ">", "right": {"value": 0}},
            ]}},
            "exit": {},
        },
        "position_sizing": {"type": "percent_equity", "value": 10},
    })


def _dataset():
    return D.build_dataset({
        "TESTUSDT": D.series_from_rows("TESTUSDT", "1d", F.bull_market("TESTUSDT", n=120),
                                       source="synthetic"),
    })


def _store(tmp_path):
    ams = AgentMemoryStore(str(tmp_path / "am.db"))
    store = QuantStore(ams, artifact_root=str(tmp_path / "art"))
    store.save_strategy(_spec())
    return store


def test_a_strategy_with_no_evidence_reports_none(tmp_path):
    store = _store(tmp_path)
    [row] = store.list_strategy_catalog()
    assert row["id"] == "cat_test"
    assert row["latestVersion"] == "1.0.0"
    assert row["latestBacktest"] is None
    assert row["approval"] is None
    assert row["lastPaperRun"] is None


def test_the_latest_backtest_and_approval_are_attached(tmp_path):
    store = _store(tmp_path)
    result = E.run_backtest(_spec(), _dataset(), E.BacktestConfig())
    store.save_experiment(result, strategy_id="cat_test",
                          strategy_version="1.0.0", kind="backtest")
    approval = store.request_approval("cat_test", "1.0.0")
    store.decide_approval(approval["id"], approve=True)

    [row] = store.list_strategy_catalog()
    assert row["latestBacktest"]["status"] == result.status
    assert row["latestBacktest"]["id"]
    assert row["approval"]["status"] == "approved"
    assert row["approval"]["version"] == "1.0.0"


def test_archived_strategies_are_hidden_unless_requested(tmp_path):
    store = _store(tmp_path)
    store.archive_strategy("cat_test", archived=True)

    assert store.list_strategy_catalog() == []
    [row] = store.list_strategy_catalog(include_archived=True)
    assert row["archived"] is True
