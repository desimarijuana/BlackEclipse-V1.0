"""Tests for the project proposer — what a project should do next.

The rule under test throughout: a proposal must cite evidence the project
actually holds, and a project with nothing to propose must say so rather than
invent advice.
"""

from __future__ import annotations

import pytest

from harness.persistence import AgentMemoryStore
from harness.projects import ProjectStore


@pytest.fixture()
def store(tmp_path) -> ProjectStore:
    ams = AgentMemoryStore(str(tmp_path / "am.db"))
    return QuantStoreProxy(ams)


class QuantStoreProxy:
    """A stand-in for the quant store, with just the reads the proposer does."""

    def __init__(self, ams) -> None:
        self.ams = ams
        self.strategies: dict[str, dict] = {}
        self.artifacts: dict[str, dict] = {}

    def get_strategy(self, strategy_id, version=None):
        if strategy_id not in self.strategies:
            raise KeyError(strategy_id)
        return {"id": strategy_id, "version": "1.0.0", "spec": self.strategies[strategy_id]}

    def read_artifact(self, experiment_id):
        if experiment_id not in self.artifacts:
            raise KeyError(experiment_id)
        return self.artifacts[experiment_id]


def _project_store(tmp_path) -> ProjectStore:
    ams = AgentMemoryStore(str(tmp_path / "am.db"))
    return ProjectStore(ams)


def _backtest_artifact(trade_count=120, strategy_id="ema_cross", regimes=None,
                       probability_of_loss=None):
    artifact = {
        "metadata": {"strategyId": strategy_id, "symbols": ["NQ"], "interval": "1d"},
        "metrics": {"trade_count": trade_count, "sharpe": 1.4, "total_return": 20.0},
        "trades": [{"id": f"t{i}", "netPnl": 10.0, "exitTs": f"2026-01-{i % 28 + 1:02d}T12:00:00Z"}
                   for i in range(trade_count)],
    }
    if regimes is not None:
        artifact["regimeAttribution"] = {"regimes": regimes}
    if probability_of_loss is not None:
        artifact["probabilityOfLoss"] = probability_of_loss
        artifact["returnPercentiles"] = {"p5": -3.0}
    return artifact


# ── the rules ────────────────────────────────────────────────────────────────

def test_a_strategy_with_no_result_is_proposed_for_a_backtest(tmp_path):
    from harness.projects.propose import propose_next

    store = _project_store(tmp_path)
    quant = QuantStoreProxy(None)
    quant.strategies["ema_cross"] = {"universe": {"symbols": ["NQ", "ES"]}}
    project = store.create("NQ momentum", symbols=["NQ"])
    store.attach(project.id, "strategy", "ema_cross")

    report = propose_next(store, project.id, quant_store=quant)
    assert report["available"] is True
    titles = [p["title"] for p in report["proposals"]]
    assert any("never been run" in t for t in titles)
    proposal = next(p for p in report["proposals"] if p["id"].startswith("result:"))
    assert proposal["action"]["tool"] == "run_backtest"
    assert proposal["action"]["args"]["strategyId"] == "ema_cross"
    assert proposal["action"]["args"]["symbols"] == ["NQ", "ES"]
    assert "strategy:ema_cross" in proposal["evidence"]


def test_a_thin_sample_is_proposed_for_a_wider_window(tmp_path):
    from harness.projects.propose import propose_next

    store = _project_store(tmp_path)
    quant = QuantStoreProxy(None)
    project = store.create("p")
    store.attach(project.id, "experiment", "exp_1")
    quant.artifacts["exp_1"] = _backtest_artifact(trade_count=8)

    report = propose_next(store, project.id, quant_store=quant)
    proposal = next(p for p in report["proposals"] if p["id"].startswith("sample:"))
    assert "8 trade(s)" in proposal["title"]
    assert any("trade_count=8" in e for e in proposal["evidence"])


def test_a_ample_sample_proposes_no_sample_fix(tmp_path):
    from harness.projects.propose import propose_next

    store = _project_store(tmp_path)
    quant = QuantStoreProxy(None)
    project = store.create("p")
    store.attach(project.id, "experiment", "exp_1")
    quant.artifacts["exp_1"] = _backtest_artifact(trade_count=200)

    report = propose_next(store, project.id, quant_store=quant)
    assert not [p for p in report["proposals"] if p["id"].startswith("sample:")]


def test_a_regime_blind_spot_is_proposed(tmp_path):
    from harness.projects.propose import propose_next

    store = _project_store(tmp_path)
    quant = QuantStoreProxy(None)
    project = store.create("p")
    store.attach(project.id, "experiment", "exp_1")
    quant.artifacts["exp_1"] = _backtest_artifact(
        trade_count=120, regimes={"down_normal": {"trades": 40, "netPnl": 100.0}})

    report = propose_next(store, project.id, quant_store=quant)
    proposal = next(p for p in report["proposals"] if p["id"].startswith("regimes:"))
    assert "1 of the 9 market regimes" in proposal["title"]
    assert any(e.startswith("regime:") for e in proposal["evidence"])


def test_an_unsafe_tail_is_proposed_for_a_cost_test(tmp_path):
    from harness.projects.propose import propose_next

    store = _project_store(tmp_path)
    quant = QuantStoreProxy(None)
    project = store.create("p")
    store.attach(project.id, "experiment", "exp_1")
    quant.artifacts["exp_1"] = _backtest_artifact(trade_count=120, probability_of_loss=48.0)

    report = propose_next(store, project.id, quant_store=quant)
    proposal = next(p for p in report["proposals"] if p["id"].startswith("tail:"))
    assert "tail" in proposal["title"]
    assert proposal["action"]["tool"] == "run_robustness_analysis"


def test_a_strategy_is_tested_against_a_firms_rules(tmp_path):
    from harness.projects.propose import propose_next

    store = _project_store(tmp_path)
    quant = QuantStoreProxy(None)
    project = store.create("p")
    store.attach(project.id, "experiment", "exp_1")
    quant.artifacts["exp_1"] = _backtest_artifact(trade_count=120)

    report = propose_next(store, project.id, quant_store=quant, firm="topstep",
                          firm_size="50k")
    proposal = next(p for p in report["proposals"] if p["id"].startswith("firm:"))
    assert "Topstep" in proposal["title"]
    assert proposal["action"]["tool"] == "run_prop_firm_simulation"
    assert proposal["action"]["args"]["firm"] == "topstep"
    assert any(e.startswith("passProbability=") for e in proposal["evidence"])


def test_a_complete_project_proposes_nothing_rather_than_inventing(tmp_path):
    from harness.projects.propose import propose_next

    store = _project_store(tmp_path)
    quant = QuantStoreProxy(None)
    project = store.create("p")
    store.attach(project.id, "strategy", "ema_cross")
    store.attach(project.id, "experiment", "exp_1")
    quant.strategies["ema_cross"] = {"universe": {"symbols": ["NQ"]}}
    quant.artifacts["exp_1"] = _backtest_artifact(trade_count=200)

    report = propose_next(store, project.id, quant_store=quant)
    # A firm fit may still be proposed (it is a real measurement), but nothing
    # may be proposed WITHOUT evidence.
    for proposal in report["proposals"]:
        assert proposal["evidence"], proposal
        assert proposal["rationale"]


def test_an_unknown_project_has_no_proposals(tmp_path):
    from harness.projects.propose import propose_next

    store = _project_store(tmp_path)
    report = propose_next(store, "proj_nope")
    assert report["available"] is False
    assert report["proposals"] == []


def test_a_note_that_names_an_untested_strategy_is_proposed(tmp_path):
    """A finding the project wrote down is evidence the proposer must read."""
    from harness.projects.propose import propose_next

    store = _project_store(tmp_path)
    quant = QuantStoreProxy(None)
    quant.strategies["ema_cross"] = {"universe": {"symbols": ["NQ"]}}
    project = store.create("NQ momentum")
    store.attach(project.id, "strategy", "ema_cross")
    store.attach(project.id, "note", "run:1",
                 label="ema_cross has never been traded in up_high")

    report = propose_next(store, project.id, quant_store=quant)
    proposal = next(p for p in report["proposals"] if p["id"].startswith("note-regime:"))
    assert "up_high" in proposal["title"]
    assert proposal["action"]["tool"] == "run_backtest"
    assert proposal["action"]["args"]["strategyId"] == "ema_cross"
    assert any(e.startswith("note:") for e in proposal["evidence"])


def test_a_note_about_a_regime_a_result_already_covered_proposes_nothing(tmp_path):
    from harness.projects.propose import propose_next

    store = _project_store(tmp_path)
    quant = QuantStoreProxy(None)
    quant.strategies["ema_cross"] = {"universe": {"symbols": ["NQ"]}}
    project = store.create("p")
    store.attach(project.id, "strategy", "ema_cross")
    store.attach(project.id, "note", "run:1", label="up_high was a bad month")
    store.attach(project.id, "experiment", "exp_1")
    quant.artifacts["exp_1"] = _backtest_artifact(
        trade_count=120, regimes={"up_high": {"trades": 10, "netPnl": 50.0}})

    report = propose_next(store, project.id, quant_store=quant)
    assert not [p for p in report["proposals"] if p["id"].startswith("note-regime:")]


def test_a_broken_rule_is_reported_rather_than_silently_skipped(tmp_path, monkeypatch):
    """A rule that cannot be evaluated must be visible, not quietly absent."""
    from harness.projects import propose as propose_module

    store = _project_store(tmp_path)
    quant = QuantStoreProxy(None)
    project = store.create("p")
    store.attach(project.id, "experiment", "exp_1")
    quant.artifacts["exp_1"] = _backtest_artifact(trade_count=120)

    def _boom(*_a, **_k):
        raise RuntimeError("the firm engine is offline")

    monkeypatch.setattr(propose_module, "_propose_firm_fit", _boom)
    report = propose_module.propose_next(store, project.id, quant_store=quant)
    assert report["skipped"], "a broken rule must be reported"
    assert "the firm engine is offline" in report["skipped"][0]["error"]
    assert "could not be evaluated" in report["summary"]


def test_the_proposals_are_ordered_by_importance(tmp_path):
    from harness.projects.propose import propose_next

    store = _project_store(tmp_path)
    quant = QuantStoreProxy(None)
    project = store.create("p")
    store.attach(project.id, "strategy", "ema_cross")
    store.attach(project.id, "experiment", "exp_1")
    quant.strategies["ema_cross"] = {"universe": {"symbols": ["NQ"]}}
    quant.artifacts["exp_1"] = _backtest_artifact(trade_count=5)

    report = propose_next(store, project.id, quant_store=quant)
    priorities = [p["priority"] for p in report["proposals"]]
    assert priorities == sorted(priorities, reverse=True)
