"""Learning-research tool adapter tests (fake bridge, real eclipse-memory store)."""

from __future__ import annotations

import os
from typing import Any

import pytest

from harness.eclipse_memory.db import EclipseMemoryDb
from harness.eclipse_memory.store import EclipseMemoryStore
from harness.research import education_tools as et
from harness.research.learning_store import LearningStore
from harness.tools import ToolContext, ToolRegistry


class FakeBridge:
    async def fetch(self, capability: str, params: dict[str, Any]) -> dict[str, Any]:
        q = params.get("query", "")
        if capability == "video_search":
            return {"status": "OK", "provider": "youtube-data-api", "results": [
                {"title": f"{q} tutorial", "url": "https://www.youtube.com/watch?v=abc", "snippet": "d",
                 "videoId": "abc", "channel": "Chan", "durationSeconds": 3600, "thumbnail": "https://i.ytimg.com/x.jpg"},
            ]}
        if capability == "playlist_search":
            return {"status": "OK", "provider": "youtube-data-api", "results": [
                {"title": f"{q} playlist", "url": "https://www.youtube.com/playlist?list=PL1"},
            ]}
        if capability == "course_search":
            return {"status": "OK", "provider": "course-allowlist", "results": [
                {"title": f"{q} course", "url": "https://www.coursera.org/learn/x"},
            ]}
        if capability == "github_search":
            return {"status": "OK", "provider": "github-rest", "results": [
                {"title": "example/backtrader", "url": "https://github.com/example/backtrader"},
            ]}
        if capability == "academic_search":
            return {"status": "OK", "provider": "openalex", "results": [
                {"title": f"{q} paper", "url": "https://doi.org/10.1/x"},
            ]}
        if capability == "web_search":
            return {"status": "OK", "provider": "duckduckgo-html", "results": [
                {"title": f"{q}", "url": "https://docs.python.org/3/", "snippet": "official docs"},
            ]}
        if capability == "video_metadata":
            return {"status": "OK", "video": {"videoId": "abc", "title": "V", "channel": "Chan", "durationSeconds": 120, "url": "https://www.youtube.com/watch?v=abc"}}
        if capability == "transcript_fetch":
            return {"status": "UNAVAILABLE", "failureClass": "not_configured", "error": "transcripts require an authorized method"}
        if capability == "web_fetch":
            return {"status": "OK", "url": params.get("url"), "title": "Page", "text": "A sufficiently long body of readable text for verification. " * 8}
        return {"status": "UNAVAILABLE"}


@pytest.fixture()
def ctx(tmp_path):
    db = EclipseMemoryDb(os.path.join(str(tmp_path), "eclipse-memory.db"))
    ls = LearningStore(EclipseMemoryStore(db=db))
    return ToolContext(run_id="r", log=lambda m, d=None: None, data_bridge=FakeBridge(), learning_store=ls)


def test_registration_is_idempotent():
    reg = ToolRegistry()
    added = et.register_learning_tools(reg)
    assert len(added) == 10
    assert et.register_learning_tools(reg) == []
    for name in added:
        assert reg.get(name) is not None


@pytest.mark.asyncio
async def test_video_metadata_and_transcript_honesty(ctx):
    text, payload = await et.video_metadata({"video_id": "abc"}, ctx)
    assert payload["status"] == "OK" and payload["video"]["durationSeconds"] == 120
    text, payload = await et.transcript_fetch({"video_id": "abc"}, ctx)
    # Captions unavailable by a permitted method are reported honestly, never faked.
    assert payload["status"] == "UNAVAILABLE"


@pytest.mark.asyncio
async def test_search_adapters(ctx):
    _, payload = await et.playlist_search({"query": "quant trading"}, ctx)
    assert payload["status"] == "OK" and payload["results"][0]["url"].endswith("PL1")
    _, payload = await et.course_search({"query": "python"}, ctx)
    assert payload["status"] == "OK" and "coursera.org" in payload["results"][0]["url"]
    _, payload = await et.github_search({"query": "backtesting"}, ctx)
    assert payload["status"] == "OK" and "github.com" in payload["results"][0]["url"]


@pytest.mark.asyncio
async def test_resource_verify_reports_reachability_only(ctx):
    _, payload = await et.resource_verify({"url": "https://docs.python.org/3/"}, ctx)
    assert payload["status"] == "OK"
    record = payload["resource"]
    assert record["accessible"] is True and record["verified"] is True
    # Reachability is not presented as a quality judgement.
    assert record["sourceType"] == "documentation"


@pytest.mark.asyncio
async def test_resource_rank(ctx):
    _, payload = await et.resource_rank({
        "learning_objective": "python backtesting",
        "resources": [
            {"url": "https://youtube.com/x", "title": "python backtesting", "sourceType": "video"},
            {"url": "https://docs.x/y", "title": "python backtesting", "sourceType": "documentation"},
        ],
    }, ctx)
    assert payload["status"] == "OK"
    assert payload["ranking"][0]["resourceId"]


@pytest.mark.asyncio
async def test_learning_path_build_discovers_and_persists(ctx):
    _, payload = await et.learning_path_build({
        "goal": "quantitative trading from scratch",
        "current_level": "beginner",
        "skills": [
            {"id": "python", "name": "Python", "objectives": ["python"], "assessment": "script"},
            {"id": "quant", "name": "Quant trading", "objectives": ["quant trading backtesting"], "prerequisites": ["python"]},
        ],
    }, ctx)
    assert payload["status"] == "OK"
    assert payload["path"]["persisted"] is True
    path_id = payload["pathId"]
    assert path_id
    nodes = payload["path"]["graph"]["nodes"]
    assert len(nodes) == 2
    assert payload["path"]["resources"]  # real discovered (fake bridge) resources attached

    # Progress persists and round-trips.
    _, upd = await et.learning_progress_update({"path_id": path_id, "node_id": "python", "status": "completed"}, ctx)
    assert upd["status"] == "OK" and upd["record"]["status"] == "completed"
    _, got = await et.learning_progress_get({"path_id": path_id}, ctx)
    assert got["status"] == "OK"
    assert "python" in got["completed"]
    assert got["nextStep"] == "quant"

    # A second build for the same goal updates the SAME path (version bumped).
    _, payload2 = await et.learning_path_build({"goal": "quantitative trading from scratch", "skills": [{"id": "python", "name": "Python"}]}, ctx)
    assert payload2["pathId"] == path_id
    assert payload2["path"]["persisted"] is True


@pytest.mark.asyncio
async def test_progress_update_requires_existing_path(ctx):
    _, payload = await et.learning_progress_update({"path_id": "nope", "node_id": "a", "status": "completed"}, ctx)
    assert payload["status"] == "NOT_FOUND"
