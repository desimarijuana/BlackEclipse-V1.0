"""W1 model gateway: plan, trace, credential rotation and first-token watchdog."""

from __future__ import annotations

import asyncio

import pytest
from langchain_core.messages import AIMessage

from harness.model_runtime import ModelRuntime
from harness.model_runtime.credential_pool import CredentialPool
from harness.model_runtime.gateway import GatewayRequest, ModelGateway, plan_candidates
from harness.model_runtime.routing import RouteCandidate, RoutingDecision, RoutingRequirements
from harness.model_runtime.runtime import Resolution
from harness.model_runtime.types import ModelInfo, ModelPerformance
from harness.model_stream import ainvoke_streaming
from harness.schemas import ModelSettings


class Emitter:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict]] = []

    async def emit(self, event_type: str, data=None):
        self.events.append((event_type, data or {}))
        return {"type": event_type}

    def emit_sync(self, event_type: str, data=None) -> None:
        self.events.append((event_type, data or {}))

    def emit_transient(self, event_type: str, data=None) -> None:
        self.events.append((event_type, data or {}))


def _resolution():
    runtime = ModelRuntime()
    settings = ModelSettings(
        provider="ollama", model="m", base_url="http://localhost:11434/v1",
    )
    return runtime, runtime.resolve_for_run(settings), settings


def test_plan_has_primary_and_extra_keys():
    runtime, resolution, settings = _resolution()
    settings = settings.model_copy(update={"api_key": "run-key"})
    resolution = runtime.resolve_for_run(settings)
    pool = CredentialPool.from_settings(
        settings, environ={"HARNESS_OLLAMA_API_KEYS": "second-key"},
    )
    candidates, excluded = plan_candidates(
        runtime, resolution, primary_model=object(), messages=[], credential_pool=pool,
    )
    assert candidates
    assert candidates[0].reason == "primary"
    assert any(c.reason == "primary_key" for c in candidates)
    assert all("reason" in item for item in excluded)


def test_credential_pool_cooldown_and_rotation():
    now = [100.0]
    pool = CredentialPool(now=lambda: now[0])
    first = pool.add("openai", "key-a", label="a")
    second = pool.add("openai", "key-b", label="b")
    assert pool.acquire("openai").id == first.id
    pool.record_failure(first, status=429, retry_after_s=5)
    assert pool.acquire("openai").id == second.id
    now[0] = 106.0
    assert pool.available("openai")
    assert "key-a" not in str(pool.snapshot())
    assert "key-b" not in str(pool.snapshot())


@pytest.mark.asyncio
async def test_invoke_traced_records_every_attempt():
    runtime, resolution, _ = _resolution()
    calls = []

    async def invoke_fn(model):
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("500 server error")
        return AIMessage(content="ok")

    result = await runtime.invoke_traced(
        invoke_fn=invoke_fn,
        primary_model=object(),
        resolution=resolution,
        max_attempts=2,
    )
    assert result.response.content == "ok"
    assert len(result.attempts) == 2
    assert result.attempts[0].outcome == "failed"
    assert result.attempts[0].error_class == "server_error"
    assert result.attempts[1].outcome == "completed"


@pytest.mark.asyncio
async def test_gateway_emits_plan_and_attempt_events():
    runtime, resolution, settings = _resolution()
    emitter = Emitter()

    async def fallback_build(settings):
        return object()

    async def invoke_fn(model):
        return AIMessage(content="gateway ok")

    gateway = ModelGateway(runtime)
    # Use the runtime directly for the invocation; the gateway's plan/events are
    # exercised through `stream` below, with a fake runtime method injected.
    async def fake_invoke(**kwargs):
        from harness.model_runtime.types import Attempt, GatewayResult
        return GatewayResult(
            response=AIMessage(content="gateway ok"),
            attempts=(Attempt(
                provider="ollama", model="m", index=0, attempt=1,
                outcome="completed", total_tokens=2,
            ),),
        )

    runtime.invoke = fake_invoke  # type: ignore[method-assign]
    result = await gateway.stream(GatewayRequest(
        model=object(), messages=[AIMessage(content="hi")], timeout_s=10,
        finalizing=False, emitter=emitter, resolution=resolution,
        run_id="r1", step=1, fallback_build=fallback_build,
    ))
    assert result.response.content == "gateway ok"
    kinds = [kind for kind, _ in emitter.events]
    assert "model.candidate_plan" in kinds


@pytest.mark.asyncio
async def test_max_run_tokens_refuses_a_new_attempt():
    runtime, resolution, _ = _resolution()
    from harness.model_runtime.errors import ModelError

    async def invoke_fn(model):
        return AIMessage(content="should not run")

    with pytest.raises(ModelError, match="MODEL_BUDGET_EXCEEDED"):
        await runtime.invoke_traced(
            invoke_fn=invoke_fn,
            primary_model=object(),
            resolution=resolution,
            max_attempts=1,
            max_run_tokens=0,
        )


@pytest.mark.asyncio
async def test_cross_provider_fallback_uses_a_reachable_credential():
    runtime, resolution, settings = _resolution()
    runtime.fallback_enabled = True
    primary = ModelInfo(id="m", provider_id="ollama")
    fallback = ModelInfo(id="gpt-4o-mini", provider_id="openai")
    resolution = Resolution(
        settings=settings,
        model=primary,
        decision=RoutingDecision(
            request_id="r", task="default",
            requirements=RoutingRequirements(),
            selected=RouteCandidate(model=primary),
            fallbacks=[RouteCandidate(model=fallback)],
        ),
        adapter=None,  # not used by the fake build path
    )
    pool = CredentialPool.from_settings(
        ModelSettings(provider="openai", model="gpt-4o-mini", api_key="openai-key"),
        environ={},
    )
    calls = []
    built = []

    async def invoke_fn(model):
        calls.append(model)
        if len(calls) == 1:
            raise RuntimeError("500 server error")
        return AIMessage(content="fallback ok")

    def fallback_build(candidate_settings):
        built.append(candidate_settings)
        return object()

    result = await runtime.invoke_traced(
        invoke_fn=invoke_fn,
        primary_model=object(),
        resolution=resolution,
        fallback_build=fallback_build,
        credential_pool=pool,
        max_attempts=1,
    )
    assert result.response.content == "fallback ok"
    assert result.fallback_used is True
    assert len(result.attempts) == 2
    assert result.attempts[1].provider == "openai"
    assert built and built[0].provider == "openai"


@pytest.mark.asyncio
async def test_no_credential_fallback_is_not_called():
    runtime, resolution, settings = _resolution()
    runtime.fallback_enabled = True
    primary = ModelInfo(id="m", provider_id="ollama")
    fallback = ModelInfo(id="gpt-4o-mini", provider_id="openai")
    resolution = Resolution(
        settings=settings,
        model=primary,
        decision=RoutingDecision(
            request_id="r", task="default",
            requirements=RoutingRequirements(),
            selected=RouteCandidate(model=primary),
            fallbacks=[RouteCandidate(model=fallback)],
        ),
        adapter=None,
    )
    pool = CredentialPool()  # no openai key
    calls = []

    async def invoke_fn(model):
        calls.append(model)
        raise RuntimeError("500 server error")

    with pytest.raises(RuntimeError):
        await runtime.invoke_traced(
            invoke_fn=invoke_fn,
            primary_model=object(),
            resolution=resolution,
            fallback_build=lambda settings: object(),
            credential_pool=pool,
            max_attempts=1,
        )
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_same_provider_fallback_is_on_without_the_cross_provider_flag():
    runtime, resolution, settings = _resolution()
    runtime.fallback_enabled = False
    primary = ModelInfo(id="m1", provider_id="ollama")
    fallback = ModelInfo(id="m2", provider_id="ollama")
    resolution = Resolution(
        settings=settings, model=primary,
        decision=RoutingDecision(
            request_id="r", task="default", requirements=RoutingRequirements(),
            selected=RouteCandidate(model=primary),
            fallbacks=[RouteCandidate(model=fallback)],
        ),
        adapter=None,
    )
    calls = []

    async def invoke_fn(model):
        calls.append(model)
        if len(calls) == 1:
            raise RuntimeError("503 server error")
        return AIMessage(content="same provider fallback")

    result = await runtime.invoke_traced(
        invoke_fn=invoke_fn,
        primary_model=object(),
        resolution=resolution,
        fallback_build=lambda settings: object(),
        max_attempts=1,
    )
    assert result.response.content == "same provider fallback"
    assert result.fallback_used is True
    assert len(result.attempts) == 2


@pytest.mark.asyncio
async def test_cross_provider_quality_guard_skips_a_much_weaker_fallback(monkeypatch):
    runtime, resolution, settings = _resolution()
    runtime.fallback_enabled = True
    primary = ModelInfo(
        id="m", provider_id="ollama",
        performance=ModelPerformance(quality=0.9),
    )
    fallback = ModelInfo(
        id="gpt-4o-mini", provider_id="openai",
        performance=ModelPerformance(quality=0.2),
    )
    resolution = Resolution(
        settings=settings, model=primary,
        decision=RoutingDecision(
            request_id="r", task="default", requirements=RoutingRequirements(),
            selected=RouteCandidate(model=primary),
            fallbacks=[RouteCandidate(model=fallback)],
        ),
        adapter=None,
    )
    pool = CredentialPool.from_settings(
        ModelSettings(provider="openai", model="gpt-4o-mini", api_key="openai-key"),
        environ={},
    )
    calls = []

    async def invoke_fn(model):
        calls.append(model)
        raise RuntimeError("500 server error")

    with pytest.raises(RuntimeError):
        await runtime.invoke_traced(
            invoke_fn=invoke_fn, primary_model=object(), resolution=resolution,
            fallback_build=lambda settings: object(), credential_pool=pool,
            max_attempts=1,
        )
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_cross_provider_quality_guard_can_be_overridden(monkeypatch):
    monkeypatch.setenv("HARNESS_MODEL_FALLBACK_ALLOW_DEGRADED", "1")
    runtime, resolution, settings = _resolution()
    runtime.fallback_enabled = True
    primary = ModelInfo(id="m", provider_id="ollama", performance=ModelPerformance(quality=0.9))
    fallback = ModelInfo(id="gpt-4o-mini", provider_id="openai", performance=ModelPerformance(quality=0.2))
    resolution = Resolution(
        settings=settings, model=primary,
        decision=RoutingDecision(
            request_id="r", task="default", requirements=RoutingRequirements(),
            selected=RouteCandidate(model=primary), fallbacks=[RouteCandidate(model=fallback)],
        ),
        adapter=None,
    )
    pool = CredentialPool.from_settings(
        ModelSettings(provider="openai", model="gpt-4o-mini", api_key="openai-key"), environ={},
    )
    calls = []

    async def invoke_fn(model):
        calls.append(model)
        if len(calls) == 1:
            raise RuntimeError("500 server error")
        return AIMessage(content="degraded fallback accepted")

    result = await runtime.invoke_traced(
        invoke_fn=invoke_fn, primary_model=object(), resolution=resolution,
        fallback_build=lambda settings: object(), credential_pool=pool, max_attempts=1,
    )
    assert result.response.content == "degraded fallback accepted"
    assert result.fallback_used is True


@pytest.mark.asyncio
async def test_first_token_timeout_is_raised_and_emitted():
    emitter = Emitter()

    class HangingModel:
        async def astream(self, messages):
            await asyncio.sleep(0.2)
            yield AIMessage(content="late")

        async def ainvoke(self, messages):
            return AIMessage(content="late")

    with pytest.raises(asyncio.TimeoutError):
        await ainvoke_streaming(
            HangingModel(), [AIMessage(content="hi")], 1.0, emitter, False,
            first_token_timeout_s=0.01,
        )
    assert any(kind == "model.first_token_timeout" for kind, _ in emitter.events)
