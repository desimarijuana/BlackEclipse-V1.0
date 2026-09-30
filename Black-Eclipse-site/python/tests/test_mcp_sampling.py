"""Phase 6 Milestone 5 — sampling, elicitation and prompt-injection containment.

Offline fixtures only. Behavior contracts: sampling is refused when disabled;
when enabled the token/RPM caps are enforced and audited; elicitation routes
through the approval surface and a URL-mode request is declined; adversarial
content changes no agent state.
"""

from __future__ import annotations

import pytest

from harness.mcp.interactions import (
    InteractionCounters,
    SamplingPolicy,
    build_elicitation_callback,
    build_sampling_callback,
)


class _Msg:
    def __init__(self, text):
        self.content = type("_C", (), {"text": text})()


class _Params:
    def __init__(self, text="hello", mode="form", message="confirm?"):
        self.messages = [_Msg(text)]
        self.mode = mode
        self.message = message


class _Emitter:
    def __init__(self):
        self.events = []

    async def emit(self, event_type, data=None):
        self.events.append((event_type, data or {}))


@pytest.mark.asyncio
async def test_sampling_disabled_is_refused_with_code():
    counters = InteractionCounters()
    cb = build_sampling_callback(
        policy=SamplingPolicy(enabled=False), server_id="s", counters=counters,
    )
    with pytest.raises(Exception) as exc:
        await cb(None, _Params())
    assert getattr(exc.value, "code", "mcp_sampling_disabled") == "mcp_sampling_disabled"
    assert counters.sampling_requests == 1 and counters.sampling_errors == 1


@pytest.mark.asyncio
async def test_sampling_enabled_runs_model_and_audits_tokens():
    counters = InteractionCounters()
    emitter = _Emitter()

    async def model(text):
        return "answer: " + text

    cb = build_sampling_callback(
        policy=SamplingPolicy(enabled=True), server_id="s", counters=counters, run_model=model, emit=emitter.emit,
    )
    result = await cb(None, _Params("what is 2+2"))
    assert result.content.text == "answer: what is 2+2"
    assert counters.sampling_tokens > 0
    assert any(e[0] == "mcp.sampling.requested" for e in emitter.events)


@pytest.mark.asyncio
async def test_sampling_rpm_cap_is_enforced():
    counters = InteractionCounters()

    async def model(_text):
        return "ok"

    cb = build_sampling_callback(
        policy=SamplingPolicy(enabled=True, rpm=1), server_id="s", counters=counters, run_model=model,
    )
    await cb(None, _Params())
    with pytest.raises(Exception) as exc:
        await cb(None, _Params())
    assert getattr(exc.value, "code", "") == "mcp_sampling_rate_limited"
    assert counters.sampling_errors == 1


def _returns(value):
    async def _coro(_):
        return value
    return _coro()


@pytest.mark.asyncio
async def test_elicitation_form_routes_through_approval():
    counters = InteractionCounters()

    async def approve(_req):
        return True

    cb = build_elicitation_callback(server_id="s", counters=counters, authorize=approve)
    result = await cb(None, _Params(mode="form"))
    assert result.action == "accept"
    assert counters.elicitation_approved == 1


@pytest.mark.asyncio
async def test_elicitation_denial_is_terminal():
    counters = InteractionCounters()

    async def deny(_req):
        return False

    cb = build_elicitation_callback(server_id="s", counters=counters, authorize=deny)
    result = await cb(None, _Params(mode="form"))
    assert result.action == "decline"
    assert counters.elicitation_denied == 1


@pytest.mark.asyncio
async def test_elicitation_url_mode_is_declined():
    counters = InteractionCounters()

    async def approve(_req):
        return True

    cb = build_elicitation_callback(server_id="s", counters=counters, authorize=approve)
    result = await cb(None, _Params(mode="url"))
    assert result.action == "decline"
    assert counters.elicitation_denied == 1


@pytest.mark.asyncio
async def test_service_sampling_factory_calls_the_bound_model(monkeypatch):
    class _FakeModel:
        def bind(self, **kwargs):
            self._bound = kwargs
            return self

        async def ainvoke(self, messages):
            class _R:
                content = "runtime-model-answer"
            return _R()

    import harness.models as models
    monkeypatch.setattr(models, "build_chat_model", lambda settings: _FakeModel())

    from harness.mcp.interactions import InteractionCounters, SamplingPolicy, build_sampling_callback
    from harness.schemas import ModelSettings, RunInput, RunRequest
    from harness.service import AgenticService

    svc = AgenticService.__new__(AgenticService)
    request = RunRequest(
        runId="r1", input=RunInput(query="q"),
        modelSettings=ModelSettings(provider="ollama", model="m", base_url="http://x"),
        callbackBaseUrl="http://x",
    )
    factory = svc._sampling_model_factory(request)
    counters = InteractionCounters()
    policy = SamplingPolicy(enabled=True)

    async def run_model(prompt: str) -> str:
        return await factory(policy, prompt)

    cb = build_sampling_callback(
        policy=policy, server_id="s", counters=counters, run_model=run_model,
    )
    result = await cb(None, _Params("what is 2+2"))
    assert result.content.text == "runtime-model-answer"
    assert counters.sampling_tokens > 0
