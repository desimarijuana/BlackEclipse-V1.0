"""Desk surfaces: research sessions, trial ledger, manifests, benchmark and routes."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from harness.persistence import AgentMemoryStore
from harness.quant import data as D
from harness.quant import engine as E
from harness.quant import fixtures as F
from harness.quant import strategy as S
from harness.quant.store import QuantStore
from harness.quant_bench.runner import run_benchmark


def _store(tmp_path):
    return QuantStore(AgentMemoryStore(str(tmp_path / "am.db")),
                      artifact_root=str(tmp_path / "art"))


def _spec():
    return S.parse_strategy({
        "strategy": {"id": "desk", "name": "Desk", "version": "1.0.0"},
        "universe": {"symbols": ["X"]},
        "indicators": [{"id": "ema", "type": "ema", "params": {"period": 5}}],
        "rules": {"entry": {"long": {"conditions": [
            {"left": {"ref": "close"}, "op": ">", "right": {"ref": "ema"}}]}}, "exit": {}},
        "position_sizing": {"type": "percent_equity", "value": 50},
    })


def _result():
    rows = F.bull_market("X", n=120)
    dataset = D.build_dataset({"X": D.series_from_rows("X", "1d", rows, source="synthetic")})
    return E.run_backtest(_spec(), dataset, E.BacktestConfig())


def test_research_session_trial_ledger(tmp_path):
    store = _store(tmp_path)
    session = store.create_research_session(title="Momentum study", question="Does trend work on X?")
    hyp = store.pre_register_hypothesis(
        session["id"], statement="EMA crossover has positive OOS Sharpe on X",
        universe=["X"], metric="sharpe", acceptance="OOS Sharpe > 0.5",
    )
    trial = store.record_trial(session["id"], kind="backtest", hypothesis_id=hyp["id"],
                               metrics={"sharpe": 0.8})
    journal = store.session_journal(session["id"])
    assert journal["trialCount"] == 1
    assert journal["testedHypotheses"] == 1
    assert journal["hypotheses"][0]["status"] == "tested"
    assert store.get_research_session(session["id"])["trials"][0]["id"] == trial["id"]


def test_manifest_round_trip_and_compare(tmp_path):
    store = _store(tmp_path)
    result = _result()
    exp_id = store.save_experiment(result, strategy_id="desk", strategy_version="1.0.0",
                                   kind="backtest")
    manifest = store.get_run_manifest(exp_id)
    assert manifest["digest"] == result.manifest["digest"]
    assert manifest["schemaVersion"].startswith("quant-run-manifest-")


def test_quant_bench_passes_its_graded_suite():
    report = run_benchmark()
    assert report["status"] == "PASS", report["failures"]
    assert report["passRate"] == 1.0
    assert report["skipped"] >= 0


def test_discovery_routes_are_registered(tmp_path, monkeypatch):
    from harness.routers import quant_desk

    store = _store(tmp_path)
    monkeypatch.setattr(quant_desk.service, "quant_store", store, raising=False)
    app = FastAPI()
    app.include_router(quant_desk.router)
    from harness.deps import require_operator
    app.dependency_overrides[require_operator] = lambda: True
    client = TestClient(app)

    methods = client.get("/quant/methods").json()["methods"]
    assert len(methods) >= 12
    card = client.get("/quant/methods/trend_ema_cross?symbol=AAPL").json()
    assert card["id"] == "trend_ema_cross"

    rec = client.post("/quant/methods/recommend",
                      json={"assetClass": "equities", "horizon": "swing",
                            "symbol": "AAPL", "limit": 3}).json()
    assert len(rec["recommendations"]) == 3

    synth = client.post("/quant/methods/synthesize",
                        json={"methodId": "trend_ema_cross", "symbol": "AAPL"}).json()
    assert synth["valid"] is True

    session = client.post("/quant/sessions", json={"title": "Route study"}).json()
    assert session["id"].startswith("ses_")
    hyp = client.post(f"/quant/sessions/{session['id']}/hypotheses",
                      json={"statement": "test"}).json()
    assert hyp["id"].startswith("hyp_")
    journal = client.get(f"/quant/sessions/{session['id']}/journal").json()
    assert journal["hypothesisCount"] == 1
