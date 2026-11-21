"""OpenBB HTTP surface: agent card, refusals, and a stream that always answers.

The route is exercised through FastAPI's TestClient with the runtime service
swapped for a fake, so nothing here needs a provider, a network or a database.
What is pinned:

  * `modelSettings` is required — no silent default provider;
  * the composed run body replays history and carries the caller's model block;
  * an empty transcript is impossible: when a run ends without streaming text,
    its `output` is emitted once, and a run with no output says so;
  * the stream ends with `[DONE]` and always closes the bus subscription.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from harness.openbb_bridge import BridgeError, build_run_request, prepare
from harness.openbb_bridge.stream import openbb_frames
from harness.routers import openbb as openbb_router

SETTINGS = {"provider": "openai", "model": "gpt-4o-mini"}


# -- pure composition -------------------------------------------------------


def _payload(**extra):
    body = {
        "messages": [
            {"role": "user", "content": "how is NVDA?"},
            {"role": "assistant", "content": "Let me check."},
            {"role": "user", "content": "and its margin?"},
        ],
        "modelSettings": dict(SETTINGS),
    }
    body.update(extra)
    return body


def test_the_run_body_replays_history_and_keeps_the_model_block():
    prepared = prepare(_payload())
    body = build_run_request(_payload(), prepared, "run_abc")
    assert body["runId"] == "run_abc"
    assert body["modelSettings"] == SETTINGS
    assert body["input"]["query"] == "and its margin?"
    assert body["input"]["history"] == [
        {"role": "user", "content": "how is NVDA?"},
        {"role": "assistant", "content": "Let me check."},
    ]


def test_a_missing_model_block_is_a_named_refusal():
    payload = _payload()
    payload.pop("modelSettings")
    with pytest.raises(BridgeError) as exc:
        build_run_request(payload, prepare(payload), "run_x")
    assert exc.value.code == "NO_MODEL_SETTINGS"


def test_an_explicit_agent_id_is_forwarded():
    payload = _payload(agentId="quant-desk")
    body = build_run_request(payload, prepare(payload), "run_x")
    assert body["agentId"] == "quant-desk"


# -- the stream -------------------------------------------------------------


class _Bus:
    def __init__(self):
        self.closed = False

    def close_stream(self, _run_id, _queue):
        self.closed = True


class _Service:
    def __init__(self, events, *, output="", active=False):
        self._events = events
        self.output = output
        self.active = active
        self.bus = _Bus()

    def list_events(self, _run_id):
        return list(self._events)

    def is_active(self, _run_id):
        return self.active

    def get_run(self, _run_id):
        return {"status": "completed", "output": self.output}


def _frames(service):
    async def collect():
        out = []
        async for frame in openbb_frames(service, "run_1", object()):
            out.append(frame)
        return out

    import asyncio

    return asyncio.run(collect())


def _objects(frames):
    objs = []
    for frame in frames:
        if frame.startswith("data: ") and "[DONE]" not in frame:
            objs.append(json.loads(frame[len("data: "):]))
    return objs


def test_tool_activity_becomes_a_reasoning_step_and_the_answer_a_chunk():
    service = _Service(
        [
            {"type": "tool_call", "seq": 1, "data": {"name": "market_quote"}},
            {"type": "run.completed", "seq": 2, "data": {}},
        ],
        output="Margin expanded 200bp.",
    )
    frames = _frames(service)
    assert frames[-1] == "data: [DONE]\n\n"
    objects = _objects(frames)
    assert objects[0] == {"type": "reasoning_step", "content": "called market_quote"}
    assert objects[-1] == {"type": "message_chunk", "content": "Margin expanded 200bp."}
    assert service.bus.closed is True


def test_a_run_with_no_output_says_so_instead_of_inventing_an_answer():
    service = _Service([{"type": "run.completed", "seq": 1, "data": {}}], output="")
    objects = _objects(_frames(service))
    assert objects == [
        {"type": "reasoning_step", "content": "run ended with no output (status: completed)"}
    ]


def test_a_failed_run_surfaces_status_not_an_empty_transcript():
    service = _Service(
        [{"type": "run.failed", "seq": 1, "data": {"message": "provider 401"}}],
        output="",
    )
    objects = _objects(_frames(service))
    assert objects[0]["type"] == "reasoning_step"
    assert "run.failed" in objects[0]["content"]


# -- the route --------------------------------------------------------------


class _RouteService(_Service):
    def __init__(self):
        super().__init__(
            [{"type": "run.completed", "seq": 1, "data": {}}], output="42% margin."
        )
        self.started: list = []

    async def run_background(self, request):
        self.started.append(request)

    class _StreamBus(_Bus):
        def open_stream(self, _run_id):
            return object()


def _client(service) -> TestClient:
    app = FastAPI()
    app.include_router(openbb_router.router)
    monkeypatch_target = openbb_router
    monkeypatch_target.service = service
    return TestClient(app)


def test_the_agent_card_points_at_the_real_query_path():
    client = _client(_RouteService())
    card = client.get("/openbb/agents.json").json()
    assert card["name"] == "Eclipse"
    assert card["endpoints"]["query"] == openbb_router.QUERY_PATH
    assert card["features"]["streaming"] is True


def test_a_query_starts_a_run_and_streams_the_answer(monkeypatch):
    service = _RouteService()
    service.bus = _RouteService._StreamBus()
    client = _client(service)
    # The route gates on the operator dependency; a TestClient is loopback.
    with client.stream("POST", openbb_router.QUERY_PATH, json=_payload()) as res:
        assert res.status_code == 200
        body = "".join(res.iter_text())
    assert "data: [DONE]" in body
    assert '"message_chunk"' in body and "42% margin." in body
    assert len(service.started) == 1
    started = service.started[0]
    assert started.input.query == "and its margin?"
    assert started.modelSettings.model == "gpt-4o-mini"
    # The route supplies the front-door origin for the read-only data bridge.
    assert started.callbackBaseUrl


def test_a_query_without_model_settings_is_refused_before_any_run():
    service = _RouteService()
    service.bus = _RouteService._StreamBus()
    client = _client(service)
    payload = _payload()
    payload.pop("modelSettings")
    res = client.post(openbb_router.QUERY_PATH, json=payload)
    assert res.status_code == 400
    assert res.json()["detail"]["code"] == "NO_MODEL_SETTINGS"
    assert service.started == []


def test_an_empty_conversation_is_refused():
    service = _RouteService()
    client = _client(service)
    res = client.post(openbb_router.QUERY_PATH, json={"messages": [], "modelSettings": SETTINGS})
    assert res.status_code == 400
    assert res.json()["detail"]["code"] == "NO_MESSAGES"
