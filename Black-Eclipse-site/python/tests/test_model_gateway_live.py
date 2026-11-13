"""Opt-in live-provider gateway check (W1).

Skipped by default. To run it, provide a real provider:

    HARNESS_LIVE_MODEL_TEST=1 \
    HARNESS_LIVE_PROVIDER=openai \
    HARNESS_LIVE_MODEL=gpt-4o-mini \
    HARNESS_LIVE_API_KEY=... \
    HARNESS_LIVE_BASE_URL=https://api.openai.com/v1 \
    python -m pytest python/tests/test_model_gateway_live.py -q

This is deliberately separate from the offline suite: it costs money and needs
a credential. A skipped run is NOT evidence of failover; it is evidence that the
live lane was not configured.
"""

from __future__ import annotations

import os

import pytest
from langchain_core.messages import HumanMessage

from harness.model_runtime import ModelRuntime
from harness.model_runtime.gateway import GatewayRequest, ModelGateway
from harness.schemas import ModelSettings


pytestmark = pytest.mark.skipif(
    os.environ.get("HARNESS_LIVE_MODEL_TEST") != "1",
    reason="live provider not configured (set HARNESS_LIVE_MODEL_TEST=1)",
)


class _Emitter:
    async def emit(self, event_type, data=None):
        return {"type": event_type}

    def emit_sync(self, event_type, data=None):
        return None

    def emit_transient(self, event_type, data=None):
        return None


@pytest.mark.asyncio
async def test_live_provider_roundtrip_through_gateway():
    provider = os.environ.get("HARNESS_LIVE_PROVIDER", "")
    model = os.environ.get("HARNESS_LIVE_MODEL", "")
    assert provider and model, "set HARNESS_LIVE_PROVIDER and HARNESS_LIVE_MODEL"

    settings = ModelSettings(
        provider=provider,
        model=model,
        base_url=os.environ.get("HARNESS_LIVE_BASE_URL") or None,
        api_key=os.environ.get("HARNESS_LIVE_API_KEY") or None,
    )
    runtime = ModelRuntime()
    resolution = runtime.resolve_for_run(settings)
    primary = runtime.build(settings, builder=None, adapter=resolution.adapter)
    primary = runtime.prepare_model(primary, resolution)

    gateway = ModelGateway(runtime)
    result = await gateway.stream(GatewayRequest(
        model=primary,
        messages=[HumanMessage(content="Reply with exactly: gateway-ok")],
        timeout_s=60.0,
        finalizing=True,
        emitter=_Emitter(),
        resolution=resolution,
        run_id="w1-live",
        step=1,
        first_token_timeout_s=30.0,
        max_attempts=1,
    ))
    assert result.response is not None
    assert "gateway-ok" in str(getattr(result.response, "content", "")).lower()
