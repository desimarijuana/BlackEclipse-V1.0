"""HTTP surface for Quant Research Intelligence (operator-gated, no network)."""

from __future__ import annotations

import math
import random

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from harness.persistence import AgentMemoryStore
from harness.quant.store import QuantStore


@pytest.fixture()
def client(tmp_path, monkeypatch):
    from harness.deps import require_operator
    from harness.routers import quant as quant_router
    from harness.routers.quant_research import router

    ams = AgentMemoryStore(str(tmp_path / "am.db"))
    store = QuantStore(ams, artifact_root=str(tmp_path / "art"))
    monkeypatch.setattr(quant_router.service, "quant_store", store)
    monkeypatch.setattr(quant_router.service, "artifacts", None, raising=False)

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[require_operator] = lambda: True
    return TestClient(app), store


def _ou(n=300, seed=3):
    rng = random.Random(seed)
    x, rows = 100.0, []
    for i in range(n):
        x = 100.0 + 0.88 * (x - 100.0) + rng.gauss(0, 1.0)
        rows.append({"ts": f"2024-03-{i % 28 + 1:02d}", "close": x})
    return rows


def test_live_routes_are_registered():
    from harness.routers.quant_live import router

    paths = {getattr(r, "path", "") for r in router.routes}
    for path in (
        "/quant/live/trials",
        "/quant/live/run-due",
        "/quant/live/trials/{trial_id}",
        "/quant/live/trials/{trial_id}/signal",
        "/quant/live/trials/{trial_id}/run",
        "/quant/live/trials/{trial_id}/run-due",
        "/quant/live/trials/{trial_id}/results",
        "/quant/live/trials/{trial_id}/stop",
    ):
        assert path in paths


def test_system_routes_are_registered():
    from harness.routers.quant_system import router

    paths = {getattr(r, "path", "") for r in router.routes}
    for path in (
        "/quant/system/data-quality",
        "/quant/system/data-quality/repair",
        "/quant/system/costs/calibrate",
        "/quant/system/golden",
        "/quant/system/monitor/{trial_id}/snapshot",
        "/quant/system/monitor/{trial_id}",
        "/quant/system/model-card/{strategy_id}/{version}",
        "/quant/system/parity",
        "/quant/system/lifecycle/{strategy_id}/{version}",
        "/quant/system/lifecycle/transition",
        "/quant/system/risk/check",
        "/quant/system/portfolio/allocate",
        "/quant/system/runs/{strategy_id}",
        "/quant/system/health",
        "/quant/system/report/{trial_id}",
    ):
        assert path in paths


def test_research_routes_are_registered():
    from harness.routers.quant_research import router

    paths = {getattr(r, "path", "") for r in router.routes}
    for path in (
        "/quant/research/search",
        "/quant/research/paper",
        "/quant/research/citations/{literature_id}",
        "/quant/research/extract",
        "/quant/research/compare",
        "/quant/research/evidence/{method_id}",
        "/quant/research/matrix",
        "/quant/research/visualize",
        "/quant/methods/specify",
        "/quant/methods/register",
        "/quant/methods/{method_id}/reproduce",
        "/quant/reproductions/{reproduction_id}/validate",
        "/quant/dossiers",
        "/quant/dossiers/{dossier_id}",
    ):
        assert path in paths


def test_specify_rejects_an_incomplete_method(client):
    http, _ = client
    resp = http.post("/quant/methods/specify", json={"spec": {"methodId": "x.bad"}})
    assert resp.status_code == 200
    assert resp.json()["status"] == "INCOMPLETE"


def test_reproduce_validate_and_dossier(client):
    http, store = client
    resp = http.post("/quant/methods/stats.ornstein_uhlenbeck/reproduce",
                     json={"series": _ou()})
    assert resp.status_code == 200, resp.text
    rep = resp.json()["reproduction"]
    assert rep["status"] == "partial"
    assert rep["observedMetrics"]["halfLife"] > 0

    resp = http.post(f"/quant/reproductions/{rep['id']}/validate")
    assert resp.status_code == 200, resp.text
    assert resp.json()["validation"]["status"] in ("incomplete", "pass")

    resp = http.post("/quant/dossiers", json={
        "title": "OU research",
        "question": "Is the test series mean-reverting?",
        "methodIds": ["stats.ornstein_uhlenbeck"],
        "reproductionIds": [rep["id"]],
    })
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "partial"
    assert "## Reproduction" in body["markdown"]

    resp = http.get("/quant/dossiers")
    assert resp.status_code == 200
    assert len(resp.json()["dossiers"]) == 1


def test_matrix_and_visualize_routes(client):
    http, _ = client
    resp = http.get("/quant/research/matrix")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["catalogOpen"] is True
    assert body["total"] >= 29
    assert {"intraday", "swing", "position", "long-term"} <= set(body["matrix"])

    resp = http.post("/quant/research/visualize", json={
        "methodIds": ["volatility.garch_11", "regime.hmm"],
        "objective": "forecast volatility",
        "horizon": "swing",
        "series": _ou()[:120],
        "symbol": "TEST",
    })
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["blocks"]
    assert any(block["type"] == "chart" for block in data["blocks"])
    assert any(figure["name"] == "suitability" for figure in data["figures"])


def test_attach_implementation_then_reproduce(client):
    http, store = client
    from harness.quant.research_intel.store import ResearchStore

    ResearchStore(store).seed_catalog()
    series = _ou()
    resp = http.post("/quant/methods/stats.arima/implementation", json={
        "source": "def run(rows, params):\n"
                  "    values = [float(r['close']) for r in rows]\n"
                  "    return {'mean': sum(values) / len(values), 'observations': len(values)}\n",
        "series": series,
    })
    assert resp.status_code == 200, resp.text
    assert resp.json()["implementation"]["testStatus"] == "passing"

    resp = http.post("/quant/methods/stats.arima/reproduce",
                     json={"series": series})
    assert resp.status_code == 200, resp.text
    rep = resp.json()["reproduction"]
    assert rep["observedMetrics"]["observations"] == len(series)


def test_evidence_route_seeds_the_catalog(client):
    http, _ = client
    resp = http.get("/quant/research/evidence/volatility.garch_11")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["method"]["spec"]["equations"]
    assert body["method"]["spec"]["implementationStatus"] == "builtin"
