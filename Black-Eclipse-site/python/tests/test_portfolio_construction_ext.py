"""Tests for the extended construction capabilities: factor loadings,
multi-period attribution, strategy comparison, rebalancing simulation, run
persistence, cost-aware optimization and the HTTP routes.
"""

from __future__ import annotations

import math
import os
import random
import tempfile

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

os.environ.setdefault(
    "AGENT_MEMORY_DB_PATH",
    os.path.join(tempfile.mkdtemp(prefix="be-pf-ext-"), "agent-memory.db"),
)

from harness.portfolio.attribution import multi_period_attribution
from harness.portfolio.construction import compare_allocations, construct
from harness.portfolio.estimation import estimate_factor_covariance, estimate_factor_loadings
from harness.portfolio.risk_engine import factor_risk
from harness.portfolio.simulation import rebalancing_simulation
from portfolio_helpers import make_portfolio, make_service


# ── Factor risk model ─────────────────────────────────────────────────────────

def test_factor_covariance_and_risk_decomposition():
    rng = random.Random(3)
    f1 = [rng.gauss(0.0, 0.01) for _ in range(260)]
    f2 = [rng.gauss(0.0, 0.008) for _ in range(260)]
    a = [1.0 * x + 0.5 * y + rng.gauss(0.0, 0.001) for x, y in zip(f1, f2)]
    b = [0.3 * x + 0.8 * y + rng.gauss(0.0, 0.001) for x, y in zip(f1, f2)]
    est = estimate_factor_covariance({"A": a, "B": b}, {"F1": f1, "F2": f2})
    assert est["available"] and est["diagnostics"]["positiveSemidefinite"]
    fr = factor_risk({"A": 0.5, "B": 0.5}, est["loadings"], est["factorCovariance"],
                     est["idiosyncraticVariance"])
    vol2 = fr["portfolioVolatility"] ** 2
    assert abs(fr["systematicVariance"] + fr["idiosyncraticVariance"] - vol2) < 1e-9
    assert abs(sum(fr["factorRiskContributions"].values())
               - fr["reconciliation"]["systematicVolatility"]) < 1e-9


# ── Risk caps (volatility / parametric VaR) ───────────────────────────────────

def test_max_volatility_cap_enforced_and_infeasible_detected():
    cov = [[0.04, 0, 0, 0], [0, 0.04, 0, 0], [0, 0, 0.04, 0], [0, 0, 0, 0.04]]
    # Equal-weight minimum variance has per-period vol 0.1.
    feasible = construct(symbols=["A", "B", "C", "D"], method="min_variance", covariance=cov,
                         constraints_payload={"max_volatility": 0.12})
    assert feasible["status"] == "OPTIMAL"
    assert feasible["validation"]["satisfied"]
    infeasible = construct(symbols=["A", "B", "C", "D"], method="min_variance", covariance=cov,
                           constraints_payload={"max_volatility": 0.05})
    assert infeasible["status"] == "INFEASIBLE"


def test_max_var_maps_to_a_volatility_cap():
    cov = [[0.04, 0, 0, 0], [0, 0.04, 0, 0], [0, 0, 0.04, 0], [0, 0, 0, 0.04]]
    from harness.portfolio.risk import _norm_ppf
    z = abs(_norm_ppf(0.05))
    # A VaR cap of 0.2 maps to a vol cap of 0.2/z ≈ 0.12 > 0.1 -> feasible.
    ok = construct(symbols=["A", "B", "C", "D"], method="min_variance", covariance=cov,
                   constraints_payload={"max_var": 0.2, "var_confidence": 0.95})
    assert ok["status"] == "OPTIMAL"
    assert any(c["name"] == "volatility_cap" and c["passed"] for c in ok["validation"]["checks"])
    bad = construct(symbols=["A", "B", "C", "D"], method="min_variance", covariance=cov,
                    constraints_payload={"max_var": 0.1, "var_confidence": 0.95})
    assert bad["status"] == "INFEASIBLE"
    assert z > 0


# ── Cardinality / lot constraints ─────────────────────────────────────────────

def test_max_positions_is_enforced():
    cov = [[0.04 if i == j else 0 for j in range(4)] for i in range(4)]
    r = construct(symbols=["A", "B", "C", "D"], method="mean_variance", covariance=cov,
                  expected_returns=[0.10, 0.09, 0.02, 0.01],
                  constraints_payload={"max_positions": 2})
    active = [s for s, w in r["weights"].items() if w > 1e-8]
    assert len(active) == 2
    assert r["status"] in ("FEASIBLE_LIMIT_REACHED", "OPTIMAL")
    assert r["validation"]["satisfied"]


def test_lot_size_rounds_to_multiples():
    cov = [[0.04 if i == j else 0 for j in range(3)] for i in range(3)]
    r = construct(symbols=["A", "B", "C"], method="min_variance", covariance=cov,
                  constraints_payload={"lot_size": 0.1})
    assert abs(sum(r["weights"].values()) - 1.0) < 1e-6
    for w in r["weights"].values():
        assert abs(w / 0.1 - round(w / 0.1)) < 1e-4
    assert r["validation"]["satisfied"]


# ── Factor-model estimation ───────────────────────────────────────────────────

def test_factor_loadings_recover_known_beta():
    rng = random.Random(1)
    factor = [rng.gauss(0.0, 0.01) for _ in range(300)]
    asset = [2.0 * f + rng.gauss(0.0, 0.001) for f in factor]
    res = estimate_factor_loadings({"A": asset}, {"MKT": factor})
    assert res["available"]
    assert abs(res["loadings"]["A"]["MKT"] - 2.0) < 0.05
    assert res["r2"]["A"] > 0.95


# ── Multi-period attribution ──────────────────────────────────────────────────

def test_multi_period_attribution_reconciles():
    def segs(pw, bw):
        return [{"group": "A", "portfolioWeight": pw, "benchmarkWeight": bw,
                 "portfolioReturn": 0.03, "benchmarkReturn": 0.02},
                {"group": "B", "portfolioWeight": 1 - pw, "benchmarkWeight": 1 - bw,
                 "portfolioReturn": 0.01, "benchmarkReturn": 0.015}]
    periods = [{"name": "p1", "segments": segs(0.6, 0.5)},
               {"name": "p2", "segments": segs(0.55, 0.5)}]
    res = multi_period_attribution(periods)
    assert res["available"] and res["reconciles"]
    assert abs(sum(res["effects"][k] for k in ("allocation", "selection", "interaction"))
               - res["activeReturn"]) < 1e-8


# ── Strategy comparison ───────────────────────────────────────────────────────

def test_compare_allocations_common_yardstick():
    cov = [[0.04, 0.0], [0.0, 0.09]]
    res = compare_allocations(symbols=["A", "B"], covariance=cov,
                              expected_returns=[0.08, 0.05],
                              methods=["equal_weight", "min_variance", "risk_parity"])
    rows = {r["method"]: r for r in res["comparison"]}
    assert set(rows) == {"equal_weight", "min_variance", "risk_parity"}
    # Every method is scored on the SAME covariance -> min-variance is the least volatile.
    vols = {m: rows[m]["expectedVolatility"] for m in rows}
    assert vols["min_variance"] <= min(vols["equal_weight"], vols["risk_parity"]) + 1e-9


# ── Cost-aware optimization ───────────────────────────────────────────────────

def test_transaction_cost_penalty_reduces_turnover():
    cov = [[0.04, 0.0], [0.0, 0.04]]
    current = {"A": 0.5, "B": 0.5}
    base = compare_allocations(symbols=["A", "B"], covariance=cov,
                               expected_returns=[0.10, 0.02],
                               methods=["mean_variance"],
                               constraints_payload={"current_weights": current})
    costly = compare_allocations(symbols=["A", "B"], covariance=cov,
                                 expected_returns=[0.10, 0.02],
                                 methods=["mean_variance"],
                                 constraints_payload={"current_weights": current,
                                                      "transaction_cost": 0.05})
    assert costly["comparison"][0]["turnover"] <= base["comparison"][0]["turnover"] + 1e-9


# ── Rebalancing simulation ────────────────────────────────────────────────────

def _walk_series(seed, n=420):
    rng = random.Random(seed)
    out = {}
    for i, symbol in enumerate(("A", "B", "C")):
        price = 100.0
        rows = []
        for t in range(n):
            price *= 1.0 + rng.gauss(0.0003, 0.01)
            rows.append({"date": f"2024-{1 + t // 28:02d}-{1 + t % 28:02d}", "close": round(price, 4)})
        out[symbol] = rows
    return out


def test_rebalancing_simulation_is_deterministic_and_point_in_time():
    series = _walk_series(7)
    a = rebalancing_simulation(series, schedule="quarterly", method="risk_parity", lookback=100)
    b = rebalancing_simulation(series, schedule="quarterly", method="risk_parity", lookback=100)
    assert a["available"] and a["rebalances"] > 0
    assert a["equityCurve"] == b["equityCurve"]  # deterministic
    assert a["methodology"]["noLookAhead"] is True


def test_rebalancing_simulation_costs_reduce_final_value():
    series = _walk_series(11)
    free = rebalancing_simulation(series, schedule="monthly", method="risk_parity",
                                  lookback=100, cost_rate=0.0)
    costly = rebalancing_simulation(series, schedule="monthly", method="risk_parity",
                                    lookback=100, cost_rate=0.002)
    assert costly["totalCostFraction"] > 0
    assert costly["finalValue"] < free["finalValue"]


# ── Run persistence ───────────────────────────────────────────────────────────

async def test_construct_persists_an_immutable_run(tmp_path):
    svc = make_service(tmp_path)
    pid = make_portfolio(svc)
    result = await svc.construct({
        "portfolio_id": pid, "symbols": ["A", "B"], "method": "min_variance",
        "covariance": [[0.04, 0.0], [0.0, 0.09]]})
    assert result["runId"]
    run = svc.store.get_construction_run(result["runId"])
    assert run is not None
    assert run["method"] == "min_variance"
    assert run["dataVersion"].startswith("sha256:")
    assert run["engineVersion"]
    listed = svc.store.list_construction_runs(pid)
    assert any(r["id"] == result["runId"] for r in listed)


# ── HTTP routes ───────────────────────────────────────────────────────────────

@pytest.fixture()
def client(tmp_path, monkeypatch):
    import harness.routers.portfolio as portfolio_router

    class _Stub:
        pass

    stub = _Stub()
    stub.portfolio = make_service(tmp_path)
    monkeypatch.setattr(portfolio_router, "service", stub, raising=False)
    app = FastAPI()
    app.include_router(portfolio_router.router)
    return TestClient(app)


def test_construct_route_and_run_retrieval(client):
    pid = client.post("/portfolio/create", json={"name": "C"}).json()["id"]
    resp = client.post(f"/portfolio/{pid}/construct",
                       json={"symbols": ["A", "B"], "method": "min_variance",
                             "covariance": [[0.04, 0.0], [0.0, 0.09]]})
    assert resp.status_code == 200
    body = resp.json()
    assert body["runId"] and body["weights"]
    runs = client.get(f"/portfolio/{pid}/construction-runs").json()["runs"]
    assert any(r["id"] == body["runId"] for r in runs)
    one = client.get(f"/portfolio/runs/{body['runId']}").json()
    assert one["id"] == body["runId"]


def test_stress_and_costs_routes(client):
    pid = client.post("/portfolio/create", json={"name": "S"}).json()["id"]
    stress = client.post(f"/portfolio/{pid}/stress-test",
                         json={"weights": {"A": 0.6, "B": 0.4},
                               "scenarios": [{"name": "dd", "type": "hypothetical",
                                              "shocks": {"A": -0.3, "B": -0.1}}]}).json()
    assert stress["scenarios"][0]["portfolioReturn"] == pytest.approx(-0.22, abs=1e-9)
    costs = client.post(f"/portfolio/{pid}/transaction-costs",
                        json={"current_weights": {"A": 0.5, "B": 0.5},
                              "target_weights": {"A": 0.6, "B": 0.4},
                              "commission_rate": 0.001}).json()
    assert abs(costs["turnover"]["oneWayTurnover"] - 0.1) < 1e-9


def test_estimate_inputs_route(client):
    resp = client.post("/portfolio/estimate-inputs",
                       json={"returns": {"A": [0.01, -0.01, 0.02], "B": [0.0, 0.01, -0.01]}})
    assert resp.status_code == 200
    body = resp.json()
    assert body["covariance"]["available"]
    assert body["expectedReturns"]["available"]
