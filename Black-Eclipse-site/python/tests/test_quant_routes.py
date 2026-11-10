"""The advanced quant endpoints are registered on the quant router.

These are thin adapters over the same core functions the agent tools use (which
are tested directly in `test_quant_vector_advanced.py`), so this asserts the
surface exists and stays wired.
"""

from __future__ import annotations


def _paths() -> set[str]:
    from harness.routers.pine import router as pine_router
    from harness.routers.projects import router as projects_router
    from harness.routers.quant import router
    from harness.routers.quant_reports import router as reports_router

    return ({getattr(r, "path", "") for r in router.routes}
            | {getattr(r, "path", "") for r in reports_router.routes}
            | {getattr(r, "path", "") for r in pine_router.routes}
            | {getattr(r, "path", "") for r in projects_router.routes})


def test_costs_route_executes():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from harness.deps import require_operator
    from harness.routers.quant import router

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[require_operator] = lambda: True
    client = TestClient(app)
    resp = client.post("/quant/costs", json={
        "orders": [{"side": "buy", "quantity": 10, "price": 100.0}],
        "execution": {"commission": {"type": "percentage", "value": 0.1}},
    })
    assert resp.status_code == 200, resp.text
    body = resp.json()["simulations"]
    assert body["transaction"]["total"] == 1.0


def test_advanced_quant_routes_registered():
    paths = _paths()
    for path in (
        "/quant/vectorized-backtest",
        "/quant/costs",
        "/quant/out-of-sample",
        "/quant/bootstrap",
        "/quant/multiple-testing",
        "/quant/compare",
        "/quant/backtest",
        "/quant/optimize",
        "/quant/walk-forward",
        "/quant/monte-carlo",
        "/quant/sensitivity",
        "/quant/robustness",
        "/quant/option-price",
        "/quant/implied-volatility",
        "/quant/option-strategy",
        "/quant/continuous-contract",
        "/quant/strategy-approvals",
        "/quant/strategies/{strategy_id}/approvals",
        "/quant/approvals/{approval_id}/decide",
        "/quant/strategies/{strategy_id}/deployments",
        "/quant/deployments/{deployment_id}/paper-runs",
        "/quant/paper-runs",
        "/quant/regime-monte-carlo",
        "/quant/edge-verdict",
        "/quant/trade-log",
        "/quant/prop-firm",
        "/quant/prop-firm/firms",
        "/quant/edge-report",
        "/quant/experiments/{experiment_id}/figures",
        "/quant/experiments/{experiment_id}/figures/{figure}",
        "/quant/pine",
        "/quant/pine/report",
        "/projects",
        "/projects/{project_id}",
        "/projects/{project_id}/digest",
        "/projects/{project_id}/proposals",
        "/projects/{project_id}/proposals/{proposal_id}/run",
        "/projects/{project_id}/auto",
        "/projects/auto/run",
    ):
        assert path in paths, path


def test_paper_governance_routes(tmp_path, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    import harness.routers.quant as quant_router
    from harness.deps import require_operator
    from harness.persistence import AgentMemoryStore
    from harness.quant import strategy as S
    from harness.quant.store import QuantStore

    store = QuantStore(AgentMemoryStore(str(tmp_path / "am.db")),
                       artifact_root=str(tmp_path / "artifacts"))
    spec = S.parse_strategy({
        "strategy": {"id": "gov-route", "name": "Gov Route", "version": "1.0.0"},
        "universe": {"symbols": ["X"]},
        "indicators": [{"id": "ema", "type": "ema", "params": {"period": 5}}],
        "rules": {"entry": {"long": {"conditions": [
            {"left": {"ref": "close"}, "op": ">", "right": {"ref": "ema"}}]}}, "exit": {}},
        "position_sizing": {"type": "percent_equity", "value": 50},
    })
    store.save_strategy(spec)
    monkeypatch.setattr(quant_router.service, "quant_store", store, raising=False)

    app = FastAPI()
    app.include_router(quant_router.router)
    app.dependency_overrides[require_operator] = lambda: True
    client = TestClient(app)

    requested = client.post("/quant/strategies/gov-route/approvals",
                            json={"version": "1.0.0", "actor": "studio"}).json()
    approval = requested["approval"]
    assert approval["status"] == "requested"

    decided = client.post(f"/quant/approvals/{approval['id']}/decide",
                          json={"approve": True, "actor": "studio"}).json()
    assert decided["approval"]["status"] == "approved"

    deployment = client.post("/quant/strategies/gov-route/deployments",
                             json={"version": "1.0.0", "mode": "paper"}).json()
    assert deployment["deployment"]["status"] == "active"
    assert deployment["deployment"]["liveExecution"] is False

    listed = client.get("/quant/strategies/gov-route/deployments").json()
    assert len(listed["deployments"]) == 1

    approvals = client.get("/quant/strategy-approvals?strategyId=gov-route").json()
    assert approvals["approvals"][0]["status"] == "approved"


def test_the_report_routes_are_mounted_on_the_running_app():
    """A route on a router is not a route until the app includes it."""
    from harness.main import app

    mounted = set(app.openapi().get("paths", {}))
    for path in ("/quant/edge-report", "/quant/prop-firm", "/quant/regime-monte-carlo",
                 "/quant/experiments/{experiment_id}/figures",
                 "/quant/experiments/{experiment_id}/figures/{figure}"):
        assert path in mounted, path
