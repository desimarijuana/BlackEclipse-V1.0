"""Model Runtime tests — the provider-agnostic model layer (spec §46).

Pure/unit: registries, capability detection, routing/scoring, fallback, retry,
health/circuit/rate-limit, usage/cost/budget, structured output, error
classification. No network, no real provider.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from harness.model_runtime import (
    BudgetManager,
    CapabilityRegistry,
    CapabilityState,
    ChatRequest,
    CircuitBreaker,
    CircuitState,
    CostTracker,
    ErrorClass,
    HealthManager,
    LatencyTracker,
    ModelCapabilities,
    ModelError,
    ModelInfo,
    ModelPricing,
    ModelRegistry,
    ModelRuntime,
    PricingKind,
    PricingRegistry,
    ProviderInfo,
    ProviderRegistry,
    RateLimitManager,
    RoutingPolicy,
    StructuredOutputManager,
    Usage,
    UsageStore,
    build_default_registries,
    classify_exception,
)
from harness.model_runtime import registry as registry_mod
from harness.model_runtime.capability import (
    apply_probe,
    detect_capabilities,
    required_missing,
)
from harness.model_runtime.structured import extract_json
from harness.model_runtime.usage import UsageRecord


# ── fixtures ────────────────────────────────────────────────────────────────


def _model(provider: str, model_id: str, **kw: Any) -> ModelInfo:
    caps = kw.pop("capabilities", ModelCapabilities({"text": CapabilityState.SUPPORTED}))
    return ModelInfo(
        id=model_id, provider_id=provider, display_name=model_id,
        capabilities=caps, context_window=kw.pop("context_window", 128_000),
        performance=kw.pop("performance", None) or __import__(
            "harness.model_runtime.types", fromlist=["ModelPerformance"]
        ).ModelPerformance(),
        pricing=kw.pop("pricing", None) or ModelPricing(),
        **kw,
    )


def _caps(**states: str) -> ModelCapabilities:
    return ModelCapabilities({k: CapabilityState(v) for k, v in states.items()})


class _FakeModel:
    """A LangChain-like model whose behaviour is scripted per call."""

    def __init__(self, outcomes: list[Any], *, label: str = "fake") -> None:
        self._outcomes = list(outcomes)
        self.label = label
        self.calls = 0
        self.bound_tools: Any = None

    def bind_tools(self, tools: Any) -> "_FakeModel":
        self.bound_tools = tools
        return self

    def bind(self, **kwargs: Any) -> "_FakeModel":
        return self

    async def ainvoke(self, messages: Any) -> Any:
        self.calls += 1
        outcome = self._outcomes.pop(0) if self._outcomes else None
        if isinstance(outcome, BaseException):
            raise outcome
        if outcome is None:
            outcome = self._success_response()
        return outcome

    @staticmethod
    def _success_response() -> Any:
        class _R:
            content = "ok"
            tool_calls: list[Any] = []
            usage_metadata = {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15}
        return _R()


# ── registries ──────────────────────────────────────────────────────────────


def test_default_registries_seed_models_and_providers() -> None:
    providers, models, caps, pricing = build_default_registries()
    assert providers.get_provider("openai") is not None
    assert len(models.list_models()) > 0
    assert models.get_model("openai/gpt-4o") is not None


def test_model_registry_register_update_remove_alias() -> None:
    providers, models, _, _ = build_default_registries()
    m = _model("openai", "custom-x")
    models.register_model(m)
    assert models.get_model("openai/custom-x") is m
    models.register_alias("my-alias", "openai/custom-x")
    assert models.resolve_alias("my-alias") == "openai/custom-x"
    models.remove_model("openai/custom-x")
    assert models.get_model("openai/custom-x") is None
    assert models.resolve_alias("my-alias") is None


def test_find_by_capability_and_provider() -> None:
    providers, models, _, _ = build_default_registries()
    vision = models.findByCapability(["vision"])
    assert all(m.capabilities.is_supported("vision") for m in vision)
    assert all(m.provider_id == "openai" for m in models.findByProvider("openai"))


def test_alias_intents_present() -> None:
    _, models, _, _ = build_default_registries()
    for alias in ("eclipse-fast", "eclipse-reasoning", "eclipse-coder", "eclipse-local"):
        assert models.alias_intent(alias) is not None


def test_discover_models_registers_and_is_idempotent() -> None:
    # A live probe (Ollama /v1/models) is idempotent: clicking "discover" twice
    # must return the FULL provider set both times, not just newly-added ids.
    providers, models, _, _ = build_default_registries()
    first = models.discover_models("ollama", ["deepseek-v4.1-flash:cloud", "glm-5.3:cloud"])
    first_ids = {m.id for m in first}
    assert "deepseek-v4.1-flash:cloud" in first_ids
    assert "glm-5.3:cloud" in first_ids
    second = models.discover_models("ollama", ["deepseek-v4.1-flash:cloud", "glm-5.3:cloud"])
    # Same complete set, no duplicates, even though nothing new was added.
    assert {m.id for m in second} == first_ids
    assert len(second) == len(first_ids)


def test_provider_enable_disable() -> None:
    p = ProviderRegistry()
    p.register(ProviderInfo(id="x", label="X", kind="openai"))
    assert p.enabled_providers()
    p.disable_provider("x")
    assert not p.enabled_providers()
    p.enable_provider("x")
    assert p.enabled_providers()


# ── capabilities ────────────────────────────────────────────────────────────


def test_detect_capabilities_merges_and_unknown() -> None:
    caps = detect_capabilities(kind="openai", model_id="gpt-4o-mini")
    assert caps.state("text") is CapabilityState.SUPPORTED
    assert caps.state("vision") is CapabilityState.SUPPORTED
    assert caps.state("embeddings") is CapabilityState.UNKNOWN


def test_detect_capabilities_reasoning_override() -> None:
    caps = detect_capabilities(kind="openai", model_id="o3-mini")
    assert caps.is_supported("reasoning")


def test_embedding_family_is_not_a_chat_model() -> None:
    caps = detect_capabilities(kind="openai", model_id="text-embedding-3-small")
    assert caps.is_supported("embeddings")
    assert not caps.is_supported("text")


def test_probe_degrades_a_false_claim() -> None:
    caps = _caps(tool_calling="supported")
    degraded = apply_probe(caps, key="tool_calling", observed=CapabilityState.DEGRADED)
    assert degraded.state("tool_calling") is CapabilityState.DEGRADED
    assert not degraded.is_supported("tool_calling")


def test_required_missing_reports_unknown_as_missing() -> None:
    caps = _caps(text="supported", tool_calling="unknown")
    assert required_missing(caps, ["text", "tool_calling"]) == ["tool_calling"]


# ── error classification ────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "exc,expected",
    [
        (ModelError(ErrorClass.RATE_LIMIT, "x"), ErrorClass.RATE_LIMIT),
        (Exception("429 Too Many Requests"), ErrorClass.RATE_LIMIT),
        (Exception("401 Unauthorized"), ErrorClass.AUTHENTICATION_ERROR),
        (Exception("maximum context length exceeded"), ErrorClass.CONTEXT_OVERFLOW),
        (Exception("connection refused"), ErrorClass.NETWORK_ERROR),
        (Exception("request timed out"), ErrorClass.TIMEOUT),
        (Exception("internal server error 500"), ErrorClass.SERVER_ERROR),
        (Exception("some weird thing"), ErrorClass.UNKNOWN_ERROR),
    ],
)
def test_classify_exception(exc: BaseException, expected: ErrorClass) -> None:
    assert classify_exception(exc).error_class is expected


def test_error_retryability() -> None:
    assert classify_exception(Exception("401 Unauthorized")).retryable is False
    assert classify_exception(Exception("429")).retryable is True
    assert classify_exception(Exception("timeout")).retryable is True


def test_structured_error_has_code() -> None:
    err = classify_exception(Exception("max_tokens_exceeded"))
    assert err.raw_code is None  # message-based, no structured code
    assert err.error_class is ErrorClass.CONTEXT_OVERFLOW


# ── health / circuit / rate limit ───────────────────────────────────────────


def test_health_manager_rolling_stats() -> None:
    h = HealthManager()
    for _ in range(9):
        h.record_success("m", latency_ms=100)
    h.record_failure("m", error_class=ErrorClass.SERVER_ERROR, latency_ms=200)
    assert h.health("m") == pytest.approx(0.9)
    assert h.error_rate("m") == pytest.approx(0.1)
    p = h.latency_percentiles("m")
    assert p["p50"] is not None


def test_circuit_opens_after_threshold_then_recovers() -> None:
    now = {"t": 0.0}
    cb = CircuitBreaker(failure_threshold=2, cooldown_s=10, now=lambda: now["t"])
    cb.record_failure("m")
    assert cb.allow("m")
    cb.record_failure("m")
    assert not cb.allow("m")
    assert cb.state("m") == CircuitState.OPEN
    now["t"] = 11.0
    assert cb.allow("m")  # half-open probe
    cb.record_success("m")
    cb.record_success("m")
    assert cb.state("m") == CircuitState.HEALTHY


def test_circuit_ignores_non_provider_faults() -> None:
    cb = CircuitBreaker(failure_threshold=1)
    cb.record_failure("m", provider_fault=False)
    assert cb.allow("m")


def test_rate_limit_declared_and_observed() -> None:
    now = {"t": 0.0}
    rl = RateLimitManager(now=lambda: now["t"], backoff_s=30)
    rl.set_limits("m", requests_per_minute=2)
    rl.record_request("m")
    rl.record_request("m")
    assert rl.is_limited("m")
    rl2 = RateLimitManager(now=lambda: now["t"], backoff_s=30)
    rl2.record_429("m")
    assert rl2.is_limited("m")
    now["t"] = 31.0
    assert not rl2.is_limited("m")


# ── usage / cost / budget ───────────────────────────────────────────────────


def test_cost_tracker_per_token() -> None:
    pricing = PricingRegistry()
    info = ModelInfo(id="m", provider_id="p", pricing=ModelPricing(kind=PricingKind.PER_TOKEN))
    pricing.register("p/m", ModelPricing(
        kind=PricingKind.PER_TOKEN, input_per_million=3.0, output_per_million=15.0,
    ))
    tracker = CostTracker(pricing)
    cost = tracker.estimate(info, Usage(input_tokens=1_000_000, output_tokens=1_000_000))
    assert cost is not None
    assert cost.total_cost == pytest.approx(18.0)


def test_cost_unknown_is_none_not_zero() -> None:
    pricing = PricingRegistry()
    info = ModelInfo(id="m", provider_id="p")
    tracker = CostTracker(pricing)
    assert tracker.estimate(info, Usage(input_tokens=10, output_tokens=10)) is None


def test_cost_free_is_zero() -> None:
    pricing = PricingRegistry()
    info = ModelInfo(id="m", provider_id="ollama")
    pricing.register("ollama/m", ModelPricing(kind=PricingKind.FREE))
    cost = CostTracker(pricing).estimate(info, Usage(input_tokens=1, output_tokens=1))
    assert cost is not None and cost.total_cost == 0.0


def test_budget_manager_pressure_and_trigger() -> None:
    b = BudgetManager()
    b.set_budget("global", 10.0)
    assert b.pressure(["global"]) == 0.0
    b.record("global", 8.0)
    assert b.pressure(["global"]) == pytest.approx(0.8)
    b.record("global", 3.0)
    assert b.exceeded(["global"])


def test_usage_store_sink_and_summary() -> None:
    seen: list[UsageRecord] = []
    store = UsageStore(sink=seen.append)
    store.record(UsageRecord(request_id="1", provider_id="p", model_id="m", input_tokens=5, output_tokens=5, total_tokens=10, success=True))
    assert len(seen) == 1
    assert store.summary()["totalTokens"] == 10


def test_latency_tracker_percentiles() -> None:
    lt = LatencyTracker()
    for v in (100, 200, 300, 400, 500):
        lt.record("m", total_ms=v)
    p = lt.total_percentiles("m")
    assert p["p50"] == pytest.approx(300.0)


# ── router ──────────────────────────────────────────────────────────────────


def _runtime_with(models: list[ModelInfo], providers: Optional[list[ProviderInfo]] = None) -> ModelRuntime:
    pr = ProviderRegistry()
    for p in providers or []:
        pr.register(p)
    caps = CapabilityRegistry()
    pricing = PricingRegistry()
    mr = ModelRegistry(pr)
    for m in models:
        mr.register_model(m)
        if pr.get_provider(m.provider_id) is None:
            pr.register(ProviderInfo(id=m.provider_id, label=m.provider_id, kind="openai"))
    return ModelRuntime(
        providers=pr, models=mr, capabilities=caps, pricing=pricing,
        policy=RoutingPolicy(fallback_depth=3),
    )


def test_router_selects_capable_model_for_task() -> None:
    rt = _runtime_with([
        _model("p1", "plain", capabilities=_caps(text="supported")),
        _model("p2", "reasoner", capabilities=_caps(text="supported", reasoning="supported", tool_calling="supported")),
    ])
    decision = rt.route(task="coding")
    assert decision.selected is not None
    assert decision.selected.model.id == "reasoner"


def test_router_excludes_missing_capability() -> None:
    rt = _runtime_with([
        _model("p1", "vision-model", capabilities=_caps(text="supported", vision="supported")),
        _model("p2", "text-only", capabilities=_caps(text="supported", vision="unsupported")),
    ])
    decision = rt.route(task="vision")
    excluded = {c.model.id: c.excluded_reason for c in decision.candidates}
    assert excluded["text-only"] is not None
    assert decision.selected.model.id == "vision-model"


def test_router_explicit_model_wins() -> None:
    rt = _runtime_with([
        _model("p1", "a", capabilities=_caps(text="supported")),
        _model("p2", "b", capabilities=_caps(text="supported")),
    ])
    decision = rt.route(model="p2/b")
    assert decision.selected.model.id == "b"
    assert "Explicit" in decision.reason


def test_router_alias_resolves_dynamically() -> None:
    rt = _runtime_with([
        _model("p1", "slow", capabilities=_caps(text="supported"), performance=__import__(
            "harness.model_runtime.types", fromlist=["ModelPerformance"]
        ).ModelPerformance(speed=0.1)),
        _model("p2", "fast", capabilities=_caps(text="supported"), performance=__import__(
            "harness.model_runtime.types", fromlist=["ModelPerformance"]
        ).ModelPerformance(speed=1.0)),
    ])
    decision = rt.route(model="eclipse-fast")
    assert decision.alias == "eclipse-fast"
    assert decision.selected is not None


def test_router_local_only_excludes_remote() -> None:
    rt = _runtime_with([
        _model("openai", "gpt-4o", capabilities=_caps(text="supported")),
        _model("ollama", "llama3", capabilities=_caps(text="supported")),
    ])
    decision = rt.route(model="eclipse-local")
    assert decision.selected is not None
    assert decision.selected.model.provider_id == "ollama"


def test_router_health_aware_skips_open_circuit() -> None:
    rt = _runtime_with([
        _model("p1", "a", capabilities=_caps(text="supported")),
        _model("p2", "b", capabilities=_caps(text="supported")),
    ])
    for _ in range(5):
        rt.circuit.record_failure("p1/a")
    decision = rt.route(task="simple_chat")
    assert decision.selected.model.id != "a"


def test_router_rate_limited_deprioritized() -> None:
    rt = _runtime_with([
        _model("p1", "a", capabilities=_caps(text="supported")),
        _model("p2", "b", capabilities=_caps(text="supported")),
    ])
    rt.rate_limits.record_429("p1/a")
    decision = rt.route(task="simple_chat")
    assert decision.selected.model.id != "a"


def test_router_min_context_unknown_rejected() -> None:
    rt = _runtime_with([
        _model("p1", "unknown-window", capabilities=_caps(text="supported"), context_window=None),
        _model("p2", "known", capabilities=_caps(text="supported"), context_window=200_000),
    ])
    decision = rt.route(
        task="document_analysis",
        requirements={"min_context": 100_000},
    )
    excluded = {c.model.id: c.excluded_reason for c in decision.candidates}
    assert excluded.get("unknown-window") is not None


def test_router_budget_pressure_prefers_cheaper() -> None:
    pricing = PricingRegistry()
    cheap = _model("p1", "cheap", capabilities=_caps(text="supported"))
    pricey = _model("p2", "pricey", capabilities=_caps(text="supported"))
    pricing.register("p1/cheap", ModelPricing(kind=PricingKind.PER_TOKEN, input_per_million=1.0, output_per_million=1.0))
    pricing.register("p2/pricey", ModelPricing(kind=PricingKind.PER_TOKEN, input_per_million=100.0, output_per_million=100.0))
    budgets = BudgetManager()
    budgets.set_budget("global", 1.0)
    budgets.record("global", 1.0)
    rt = ModelRuntime(
        providers=ProviderRegistry(), models=ModelRegistry(), capabilities=CapabilityRegistry(),
        pricing=pricing, budgets=budgets, policy=RoutingPolicy(fallback_depth=3),
    )
    for m in (cheap, pricey):
        rt.providers.register(ProviderInfo(id=m.provider_id, label=m.provider_id, kind="openai"))
        rt.models.register_model(m)
    decision = rt.route(task="background_task")
    assert decision.selected.model.id == "cheap"


# ── fallback / retry ────────────────────────────────────────────────────────


def test_fallback_primary_fails_secondary_succeeds() -> None:
    rt = _runtime_with([
        _model("p1", "a", capabilities=_caps(text="supported")),
        _model("p1", "b", capabilities=_caps(text="supported")),
    ])
    rt.fallback_enabled = True
    res = rt.resolve_for_run(
        __import__("harness.schemas", fromlist=["ModelSettings"]).ModelSettings(provider="p1", model="a", api_key="k"),
        task="simple_chat",
    )
    primary = _FakeModel([RuntimeError("503 server error"), RuntimeError("503 server error")])
    secondary = _FakeModel([None])

    def fallback_build(settings: Any) -> Any:
        return secondary if settings.model == "b" else primary

    result = asyncio.run(rt.invoke(
        invoke_fn=lambda m: m.ainvoke([]),
        primary_model=primary,
        resolution=res,
        fallback_build=fallback_build,
        raise_original=False,
    ))
    assert result is not None
    assert secondary.calls == 1


def test_all_models_fail_raises() -> None:
    rt = _runtime_with([_model("p1", "a", capabilities=_caps(text="supported"))])
    res = rt.resolve_for_run(
        __import__("harness.schemas", fromlist=["ModelSettings"]).ModelSettings(provider="p1", model="a", api_key="k"),
        task="simple_chat",
    )
    primary = _FakeModel([RuntimeError("401 Unauthorized")])
    with pytest.raises(Exception):
        asyncio.run(rt.invoke(
            invoke_fn=lambda m: m.ainvoke([]),
            primary_model=primary,
            resolution=res,
            raise_original=False,
        ))


def test_retry_retryable_then_success() -> None:
    rt = _runtime_with([_model("p1", "a", capabilities=_caps(text="supported"))])
    rt.max_attempts = 3
    res = rt.resolve_for_run(
        __import__("harness.schemas", fromlist=["ModelSettings"]).ModelSettings(provider="p1", model="a", api_key="k"),
        task="simple_chat",
    )
    model = _FakeModel([RuntimeError("429 rate limit"), None])
    result = asyncio.run(rt.invoke(
        invoke_fn=lambda m: m.ainvoke([]),
        primary_model=model,
        resolution=res,
        raise_original=False,
    ))
    assert result is not None
    assert model.calls == 2


def test_non_retryable_does_not_retry() -> None:
    rt = _runtime_with([_model("p1", "a", capabilities=_caps(text="supported"))])
    rt.max_attempts = 3
    res = rt.resolve_for_run(
        __import__("harness.schemas", fromlist=["ModelSettings"]).ModelSettings(provider="p1", model="a", api_key="k"),
        task="simple_chat",
    )
    model = _FakeModel([RuntimeError("401 Unauthorized")])
    with pytest.raises(Exception):
        asyncio.run(rt.invoke(
            invoke_fn=lambda m: m.ainvoke([]),
            primary_model=model,
            resolution=res,
            raise_original=False,
        ))
    assert model.calls == 1


def test_rate_limit_fallback_uses_secondary() -> None:
    rt = _runtime_with([
        _model("p1", "a", capabilities=_caps(text="supported")),
        _model("p1", "b", capabilities=_caps(text="supported")),
    ])
    rt.fallback_enabled = True
    res = rt.resolve_for_run(
        __import__("harness.schemas", fromlist=["ModelSettings"]).ModelSettings(provider="p1", model="a", api_key="k"),
        task="simple_chat",
    )
    primary = _FakeModel([RuntimeError("429 rate limit"), RuntimeError("429 rate limit")])
    secondary = _FakeModel([None])

    def fallback_build(settings: Any) -> Any:
        return secondary if settings.model == "b" else primary

    result = asyncio.run(rt.invoke(
        invoke_fn=lambda m: m.ainvoke([]),
        primary_model=primary,
        resolution=res,
        fallback_build=fallback_build,
        raise_original=False,
    ))
    assert result is not None


def test_generate_returns_normalized_response() -> None:
    rt = _runtime_with([_model("p1", "a", capabilities=_caps(text="supported"))])

    class _Resp:
        content = "hello"
        tool_calls: list[Any] = []
        usage_metadata = {"input_tokens": 3, "output_tokens": 2, "total_tokens": 5}

    rt.build = lambda settings, builder=None, adapter=None: _FakeModel([_Resp()])  # type: ignore[assignment]
    settings = __import__("harness.schemas", fromlist=["ModelSettings"]).ModelSettings(
        provider="p1", model="a", api_key="k"
    )
    response = asyncio.run(rt.generate(settings=settings, messages=[]))
    assert response.text == "hello"
    assert response.usage.total_tokens == 5


# ── structured output ───────────────────────────────────────────────────────


def test_extract_json_fenced_and_bare() -> None:
    assert extract_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert extract_json('text before {"a": 2} after') == {"a": 2}
    assert extract_json("not json") is None


def test_structured_valid() -> None:
    mgr = StructuredOutputManager()
    schema = {"type": "object", "required": ["a"], "properties": {"a": {"type": "integer"}}}
    result = mgr.parse_and_validate('{"a": 1}', schema)
    assert result.ok and result.value == {"a": 1}


def test_structured_invalid_json() -> None:
    mgr = StructuredOutputManager()
    result = mgr.parse_and_validate("nope", {"type": "object"})
    assert not result.ok
    assert result.error.error_class is ErrorClass.STRUCTURED_OUTPUT_ERROR


def test_structured_schema_mismatch() -> None:
    mgr = StructuredOutputManager()
    schema = {"type": "object", "required": ["a"], "properties": {"a": {"type": "integer"}}}
    result = mgr.parse_and_validate('{"b": 2}', schema)
    assert not result.ok
    assert result.validation_error


def test_structured_repair_prompt_mentions_schema() -> None:
    mgr = StructuredOutputManager()
    prompt = mgr.repair_prompt("{bad}", {"type": "object"}, "missing a")
    assert "Schema" in prompt and "missing a" in prompt


# ── decision trace ──────────────────────────────────────────────────────────


def test_decision_trace_records_candidates() -> None:
    rt = _runtime_with([
        _model("p1", "a", capabilities=_caps(text="supported", tool_calling="supported")),
        _model("p2", "b", capabilities=_caps(text="supported", tool_calling="unsupported")),
    ])
    rt.route(task="coding")
    decisions = rt.recent_decisions()
    assert decisions
    trace = decisions[-1]
    assert trace["selected"] is not None
    assert any(c["excludedReason"] for c in trace["candidates"])


def test_observer_receives_routing_event() -> None:
    events: list[tuple[str, dict]] = []
    rt = _runtime_with([_model("p1", "a", capabilities=_caps(text="supported"))])
    rt.set_observer(lambda t, d: events.append((t, d)))
    rt.route(task="simple_chat")
    assert any(t == "model.routing.completed" for t, _ in events)


# ── adapter selection ───────────────────────────────────────────────────────


def test_adapter_for_provider_family() -> None:
    from harness.model_runtime.providers import adapter_for

    assert adapter_for(kind="anthropic").kind == "anthropic"
    assert adapter_for(kind="openai", provider_id="groq").kind == "openai"
    assert adapter_for(kind="openai_compatible", provider_id="ollama").kind == "openai_compatible"


def test_remote_providers_expose_dynamic_discovery() -> None:
    # A hosted API/router enumerates its own live catalog just like a local
    # server, so the operator can pull the real model ids instead of only the
    # declared sample. Every provider that CAN list its models must advertise it,
    # and every adapter it routes to must implement the probe (not inherit the
    # empty base implementation).
    from harness.models import PROVIDER_CATALOG
    from harness.model_runtime.providers import adapter_for
    from harness.model_runtime.providers.base import ProviderAdapter

    for pid in [
        "openai", "anthropic", "google", "mistral", "groq",
        "deepseek", "xai", "openrouter", "together", "perplexity",
        "fireworks", "ollama", "lmstudio", "custom",
    ]:
        spec = PROVIDER_CATALOG[pid]
        assert spec.dynamic_discovery, f"{pid} should advertise dynamic discovery"
        adapter = adapter_for(kind=spec.kind, provider_id=pid)
        # A discovery-capable provider must NOT fall back to the empty base probe.
        assert type(adapter).discover_models is not ProviderAdapter.discover_models, (
            f"{pid} has no discovery probe"
        )


def test_openai_models_parser_tolerates_wild_shapes() -> None:
    from harness.model_runtime.providers.openai import _parse_openai_models

    assert _parse_openai_models({"data": [{"id": "a"}, {"id": "b"}]}) == ["a", "b"]
    assert _parse_openai_models({"models": ["a", "b"]}) == ["a", "b"]
    assert _parse_openai_models(["a", "b"]) == ["a", "b"]
    assert _parse_openai_models({"unexpected": 1}) == []
    assert _parse_openai_models(None) == []


def test_run_is_constrained_only_for_keyless_fallback() -> None:
    rt = _runtime_with([
        _model("openai", "gpt-4o-mini", capabilities=_caps(text="supported", reasoning="supported", tool_calling="supported")),
        _model("ollama", "llama3", capabilities=_caps(text="supported", reasoning="supported", tool_calling="supported")),
    ])
    settings = __import__("harness.schemas", fromlist=["ModelSettings"]).ModelSettings(
        provider="openai", model="gpt-4o-mini", api_key="k"
    )
    res = rt.resolve_for_run(settings, task="coding")
    # An explicit provider/model is respected; it is never silently moved to a
    # provider the run has no credentials for.
    assert res.settings.provider == "openai"
    assert res.settings.model == "gpt-4o-mini"


# ── explicit (operator-configured) model must never be substituted ─────────


def _settings(provider: str, model: str, **kw: Any) -> Any:
    return __import__("harness.schemas", fromlist=["ModelSettings"]).ModelSettings(
        provider=provider, model=model, api_key="k", **kw
    )


def test_explicit_ref_qualifies_a_bare_uncatalogued_id_with_the_run_provider() -> None:
    rt = ModelRuntime()
    # A bare model id the catalog has never seen is qualified with the run's
    # provider — NOT left bare (which the router read as "unknown" and routed
    # away from), and NOT already carrying a provider prefix.
    assert rt._explicit_ref(_settings("deepseek", "deepseek-v4.1-flash")) == "deepseek/deepseek-v4.1-flash"
    assert rt._explicit_ref(_settings("ollama", "my-local-model")) == "ollama/my-local-model"


def test_explicit_ref_leaves_qualified_ids_and_aliases_untouched() -> None:
    rt = ModelRuntime()
    assert rt._explicit_ref(_settings("openai", "openai/gpt-4o")) == "openai/gpt-4o"
    assert rt._explicit_ref(_settings("openai", "eclipse-fast")) == "eclipse-fast"
    assert rt._explicit_ref(_settings("openai", "gpt-4o")) == "gpt-4o"


def test_uncatalogued_configured_model_is_not_silently_substituted() -> None:
    # Regression: the front door stores a BARE model id. An uncatalogued id used
    # to fall through to the router and select a DIFFERENT model (gemini). The
    # operator's own choice must win.
    rt = ModelRuntime()
    res = rt.resolve_for_run(_settings("deepseek", "deepseek-v4.1-flash"), task="default")
    assert res.settings.provider == "deepseek"
    assert res.settings.model == "deepseek-v4.1-flash"
    assert res.decision.selected is not None
    assert res.decision.selected.model.qualified_id == "deepseek/deepseek-v4.1-flash"


# ── reasoning shaping must not force a knob a provider cannot accept ───────


def test_reasoning_is_not_shaped_for_an_openai_compatible_endpoint() -> None:
    # DeepSeek/Groq/custom/local speak the OpenAI protocol but do NOT accept
    # `reasoning_effort`; injecting it is a hard 400. A bare id that resolves to
    # an openai-compatible endpoint must be returned untouched.
    rt = ModelRuntime()
    res = rt.resolve_for_run(_settings("deepseek", "deepseek-chat"), task="financial_research")
    model = rt.prepare_model(object(), res)
    assert not hasattr(model, "reasoning_effort")


def test_reasoning_is_shaped_only_for_a_native_reasoning_model() -> None:
    rt = _runtime_with([
        _model("openai", "o3-mini", capabilities=_caps(text="supported", reasoning="supported")),
    ])

    class _Native:
        reasoning_effort: Any = None

    res = rt.resolve_for_run(_settings("openai", "o3-mini"), task="financial_research")
    model = rt.prepare_model(_Native(), res)
    assert getattr(model, "reasoning_effort", None) == "high"


def test_operator_reasoning_effort_overrides_the_task_profile() -> None:
    # The "model variant" control: an explicit effort carried as a `reasoning`
    # routing requirement must win over the task profile's default (`medium` for
    # `default`). The runtime maps `very_high` → `high` for OpenAI's knob.
    rt = _runtime_with([
        _model("openai", "o3-mini", capabilities=_caps(text="supported", reasoning="supported")),
    ])

    class _Native:
        reasoning_effort: Any = None

    res = rt.resolve_for_run(
        _settings("openai", "o3-mini"),
        task="default",
        requirements={"reasoning": "very_high"},
    )
    model = rt.prepare_model(_Native(), res)
    assert getattr(model, "reasoning_effort", None) == "high"


def test_operator_reasoning_effort_low_leaves_the_model_untouched() -> None:
    # Selecting Minimal must not inject a reasoning knob at all (the runtime
    # leaves low/none alone) — the model is returned as-is.
    rt = _runtime_with([
        _model("openai", "o3-mini", capabilities=_caps(text="supported", reasoning="supported")),
    ])

    class _Native:
        reasoning_effort: Any = None

    res = rt.resolve_for_run(
        _settings("openai", "o3-mini"),
        task="default",
        requirements={"reasoning": "low"},
    )
    model = rt.prepare_model(_Native(), res)
    assert getattr(model, "reasoning_effort", None) is None


def test_very_high_is_normalized_to_max_for_the_adapter() -> None:
    # The UI's top stop ("Ultra") means the model's strongest thinking tier. The
    # runtime normalizes `very_high` → the runtime's `max` tier (NOT `high`), so
    # an adapter can map it to its provider's real ceiling.
    rt = _runtime_with([
        _model("anthropic", "claude-sonnet-4", capabilities=_caps(text="supported", reasoning="supported")),
    ], providers=[ProviderInfo(id="anthropic", label="Anthropic", kind="anthropic")])
    captured: dict[str, Any] = {}

    class _Capture:
        thinking: Any = None

        def _apply(self, req: Any) -> None:
            captured["effort"] = req.effort

    # Wrap the adapter's apply_reasoning to observe the normalized effort.
    res = rt.resolve_for_run(
        _settings("anthropic", "claude-sonnet-4"),
        task="default",
        requirements={"reasoning": "very_high"},
    )
    real_apply = res.adapter.apply_reasoning

    def spy(model: Any, reasoning: Any) -> Any:
        captured["effort"] = getattr(reasoning, "effort", None)
        return real_apply(model, reasoning)

    res.adapter.apply_reasoning = spy  # type: ignore[method-assign]
    model = rt.prepare_model(_Capture(), res)
    assert captured["effort"] == "max"
    # Anthropic maps max → its deepest thinking budget (16384 tokens).
    assert getattr(model, "thinking", None) == {"type": "enabled", "budget_tokens": 16384}


def test_ultra_on_native_openai_caps_at_high_because_there_is_no_higher_tier() -> None:
    # OpenAI's `reasoning_effort` tops out at `high`; sending `max` would be an
    # unknown value and a hard 400, so the adapter caps Ultra at `high`.
    rt = _runtime_with([
        _model("openai", "o3-mini", capabilities=_caps(text="supported", reasoning="supported")),
    ])

    class _Native:
        reasoning_effort: Any = None

    res = rt.resolve_for_run(
        _settings("openai", "o3-mini"),
        task="default",
        requirements={"reasoning": "very_high"},
    )
    model = rt.prepare_model(_Native(), res)
    assert getattr(model, "reasoning_effort", None) == "high"

