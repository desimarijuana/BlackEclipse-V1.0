"""The advanced quant endpoints are registered on the quant router.

These are thin adapters over the same core functions the agent tools use (which
are tested directly in `test_quant_vector_advanced.py`), so this asserts the
surface exists and stays wired.
"""

from __future__ import annotations


def _paths() -> set[str]:
    from harness.routers.quant import router

    return {getattr(r, "path", "") for r in router.routes}


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
    ):
        assert path in paths, path
