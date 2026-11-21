"""Market-recap videos (Phase 8): a bound storyboard built from symbols, the
HTTP entry point schedules call, and the cron template that drives it.

A recap NEVER authors a figure: every metric and candle is a data binding,
resolved through the Market Data Gateway by the ordinary render job.
"""

from __future__ import annotations

import asyncio

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from harness.jobs.templates import get_template, instantiate
from harness.video.models import VideoError
from harness.video.recaps import MAX_RECAP_SYMBOLS, build_recap_spec
from harness.video.service import set_video_service
from harness.video.spec import validate_storyboard

from video_fakes import make_video_env


def test_recap_spec_is_bound_and_valid():
    spec = build_recap_spec(symbols=["btc-usd", "ETH-USD"], title="Morning recap")
    assert spec["schemaVersion"] == 3
    assert validate_storyboard(spec) == []
    types = [scene["type"] for scene in spec["scenes"]]
    assert types == ["intro", "metric", "candlestick", "metric", "outro"]
    metric = spec["scenes"][1]
    assert metric["title"] == "BTC-USD TODAY"
    assert all("source" in item and "value" not in item for item in metric["metrics"])
    candle = spec["scenes"][2]
    assert candle["data"] == {"symbol": "BTC-USD", "interval": "1d", "count": 30}
    assert "candles" not in candle


def test_recap_scene_budget_holds_at_the_cap():
    symbols = [f"SYM{i}" for i in range(MAX_RECAP_SYMBOLS)]
    spec = build_recap_spec(symbols=symbols)
    assert len(spec["scenes"]) <= 12
    assert validate_storyboard(spec) == []


def test_recap_refusals_are_structured():
    cases = (
        ([], "1-"),
        (["A", "B", "C", "D", "E", "F"], "at most"),
        (["BAD SYMBOL"], "invalid symbol"),
        (["THIS-SYMBOL-IS-TOO-LONG"], "invalid symbol"),
        ("BTC-USD", "1-"),
    )
    for symbols, needle in cases:
        with pytest.raises(VideoError) as exc:
            build_recap_spec(symbols=symbols)
        assert exc.value.code == "INVALID_INPUT"
        assert needle in exc.value.message


def test_recap_dedupes_symbols():
    spec = build_recap_spec(symbols=["btc-usd", "BTC-USD", "eth-usd"])
    metric_titles = [
        scene["title"] for scene in spec["scenes"] if scene["type"] == "metric"
    ]
    assert metric_titles == ["BTC-USD TODAY", "ETH-USD TODAY"]


def test_recap_template_drives_a_cron_job():
    template = get_template("daily-market-recap-video")
    assert template is not None and template.kind == "cron"
    job = instantiate(
        "daily-market-recap-video", {"symbols": "BTC-USD, ETH-USD"}, name="Recap"
    )
    assert job.enabled is False  # discovery is not activation
    assert job.cron == "30 21 * * 1-5"
    assert job.target.kind == "objective"
    assert "BTC-USD, ETH-USD" in (job.target.objective or "")
    # G13: a scheduled prompt states the CAPABILITY, never a tool id, so a rename
    # cannot silently break the job. The flow must still be described.
    objective = job.target.objective or ""
    assert "video_create_project" not in objective
    assert "storyboard" in objective and "render" in objective


# ── HTTP entry point ─────────────────────────────────────────────────────────


@pytest.fixture()
def client(tmp_path, monkeypatch):
    env = make_video_env(tmp_path, monkeypatch)
    from harness.routers import video as video_router

    class _Stub:
        pass

    stub = _Stub()
    stub.video = env["service"]
    monkeypatch.setattr(video_router, "service", stub, raising=False)
    app = FastAPI()
    app.include_router(video_router.router)
    yield TestClient(app), env
    set_video_service(None)


def test_create_recap_over_http(client):
    http, env = client
    response = http.post(
        "/video/recaps", json={"symbols": ["BTC-USD", "ETH-USD"], "title": "Recap"}
    )
    assert response.status_code == 201, response.text
    project = response.json()["project"]
    assert project["kind"] == "storyboard" and project["revision"] == 1
    assert project["spec"]["schemaVersion"] == 3
    assert env["service"].validate_project(project["id"])["valid"] is True
    # A recap is a normal queued render away from an artifact.
    submitted = http.post(
        f"/video/projects/{project['id']}/render", json={"mode": "draft"}
    )
    assert submitted.status_code == 202


def test_create_recap_rejects_too_many_symbols(client):
    http, _env = client
    response = http.post(
        "/video/recaps", json={"symbols": ["A", "B", "C", "D", "E", "F"]}
    )
    assert response.status_code == 422  # body validation bounds the list


def test_create_recap_without_symbols_is_refused(client):
    http, _env = client
    response = http.post("/video/recaps", json={"symbols": []})
    assert response.status_code == 422
