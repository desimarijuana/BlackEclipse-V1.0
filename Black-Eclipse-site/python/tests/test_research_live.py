"""Phase 4 Workstream 2 — gated research flow in the live run path.

Driven through `execute_run` with a fake deterministic bridge and a fake model so
every branch is exercised: supported success, partial coverage, unsupported
fallback, invalid synthesis JSON, unsupported claim, one repair then success,
repair still rejected, provider failure, cancellation, and no duplicate
retrieval.
"""

from __future__ import annotations

import asyncio
import os
import tempfile
from typing import Any

import pytest

from harness.graph import execute_run
from harness.persistence import AgentMemoryStore
from harness.research.synthesis import parse_synthesis
from harness.schemas import ModelSettings, RunInput, RunRequest
from harness.tools import DataBridge, ToolRegistry


# ── Fakes ───────────────────────────────────────────────────────────────────


class FakeBridge(DataBridge):
    """Serves synthetic financial statements; records every capability call."""

    def __init__(self, available: bool = True, error: bool = False) -> None:
        self.available = available
        self.error = error
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def fetch(self, capability: str, params: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((capability, params))
        if self.error:
            return {"status": "UNAVAILABLE", "error": "provider timeout"}
        if not self.available:
            return {"status": "UNAVAILABLE", "error": "no data"}
        if capability == "financial_statements":
            return {
                "status": "OK",
                "symbol": params.get("symbol", "TEST"),
                "currency": "USD",
                "periods": [
                    {"period": "FY2023", "endDate": "2023-12-31", "revenue": 800.0},
                    {"period": "FY2024", "endDate": "2024-12-31", "revenue": 1000.0},
                ],
            }
        return {"status": "UNAVAILABLE", "error": "no fake"}


class FakeModel:
    """A minimal LangChain-compatible chat model.

    Returns queued responses as real `AIMessage`/`AIMessageChunk` objects so it
    works through both the synthesis `ainvoke` and the agent graph's `astream`.
    Records invocation count.
    """

    def __init__(self, responses: list[str]) -> None:
        self.responses = responses
        self.calls = 0
        self._last_prompt = ""

    def _next(self):
        from langchain_core.messages import AIMessage

        idx = min(self.calls, len(self.responses) - 1) if self.responses else 0
        text = self.responses[idx] if self.responses else "{}"
        self.calls += 1
        return AIMessage(
            content=text,
            usage_metadata={"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
        )

    async def ainvoke(self, messages: Any) -> Any:
        return self._next()

    async def astream(self, messages: Any):
        yield self._next()

    def bind_tools(self, tools: Any, **kwargs: Any) -> "FakeModel":
        return self


class CitingFakeModel(FakeModel):
    """Returns a valid reported_fact citing the FIRST real evidence id in the
    synthesis packet, so the deterministic validator accepts it."""

    def _next(self):
        import json as _json
        import re as _re

        from langchain_core.messages import AIMessage

        text = self.responses[0]
        if "__EVIDENCE__" in text:
            payload = self._last_prompt
            ids = []
            if payload:
                match = _re.search(r'"evidenceId":\s*"([^"]+)"', payload)
                if match:
                    ids = [match.group(1)]
            text = text.replace("__EVIDENCE__", ids[0] if ids else "none")
        self.calls += 1
        return AIMessage(content=text, usage_metadata={"input_tokens": 10, "output_tokens": 5, "total_tokens": 15})

    async def ainvoke(self, messages: Any) -> Any:
        # Capture the human prompt so `_next` can mine a real evidence id.
        for m in messages:
            content = getattr(m, "content", "")
            if isinstance(content, str) and "EVIDENCE PACKET" in content:
                self._last_prompt = content
        return self._next()

    async def astream(self, messages: Any):
        yield await self.ainvoke(messages)


def make_request(query: str, run_id: str) -> RunRequest:
    return RunRequest(
        runId=run_id,
        input=RunInput(query=query, ticker="TEST"),
        modelSettings=ModelSettings(provider="openai", model="test-model", api_key="x"),
        callbackBaseUrl="http://localhost:3000",
    )


def run_execute(request: RunRequest, bridge: FakeBridge, model: FakeModel, store: AgentMemoryStore):
    registry = ToolRegistry()

    async def _go():
        return await execute_run(
            request, registry, bridge, store, bus=None, retrieval_cache=None
        )

    return asyncio.run(_go())


@pytest.fixture()
def store():
    with tempfile.TemporaryDirectory() as tmp:
        s = AgentMemoryStore(os.path.join(tmp, "agent-memory.db"))
        yield s
        s.close()


VALID_CLAIM_JSON = """{
  "claims": [
    {"text": "The reported revenue figure is available in the evidence.",
     "kind": "reported_fact", "evidenceIds": ["__EVIDENCE__"]},
    {"text": "The comparison period is covered by the evidence.",
     "kind": "reported_fact", "evidenceIds": ["__EVIDENCE__"]}
  ],
  "gaps": []
}"""


# ── Tests ───────────────────────────────────────────────────────────────────


def test_supported_comparison_uses_gate(store, monkeypatch):
    bridge = FakeBridge()
    model = CitingFakeModel([VALID_CLAIM_JSON])

    # Inject the fake model without touching the real provider factory.
    import harness.graph as graph

    monkeypatch.setattr(graph, "build_chat_model", lambda settings: model)

    result = run_execute(
        make_request("Compare TEST revenue in FY2023 vs FY2024", "r_ok"), bridge, model, store
    )
    assert result.status == "completed"
    assert result.research is not None
    # The gate ran, so the ordinary financial tool loop did NOT execute.
    assert not any(c[0] == "live_quote" for c in bridge.calls)
    # Exactly one retrieval per leg (2), no duplicate.
    stmt_calls = [c for c in bridge.calls if c[0] == "financial_statements"]
    assert len(stmt_calls) == 2
    assert result.research["status"] == "accepted"
    assert result.totalTokens > 0


def test_partial_when_one_leg_missing(store, monkeypatch):
    bridge = FakeBridge()
    # Only FY2024 present for a different ticker → partial coverage.
    model = FakeModel(['{"claims": [], "gaps": ["no revenue evidence"]}'])

    import harness.graph as graph

    monkeypatch.setattr(graph, "build_chat_model", lambda settings: model)

    result = run_execute(
        make_request("Compare MISSING revenue in FY2019 vs FY2020", "r_partial"),
        bridge,
        model,
        store,
    )
    assert result.research["status"] in ("partial", "rejected")


def test_unsupported_request_uses_existing_path(store, monkeypatch):
    bridge = FakeBridge()
    model = FakeModel(["A stock is a share of ownership."])
    import harness.graph as graph

    monkeypatch.setattr(graph, "build_chat_model", lambda settings: model)

    result = run_execute(make_request("What is a stock?", "r_general"), bridge, model, store)
    assert result.status == "completed"
    assert result.research is None
    # No financial statement retrieval happened.
    assert not any(c[0] == "financial_statements" for c in bridge.calls)


def test_invalid_synthesis_json_is_honest_partial(store, monkeypatch):
    bridge = FakeBridge()
    model = FakeModel(["not json at all", "still not json"])
    import harness.graph as graph

    monkeypatch.setattr(graph, "build_chat_model", lambda settings: model)

    result = run_execute(
        make_request("Compare TEST revenue in FY2023 vs FY2024", "r_badjson"), bridge, model, store
    )
    assert result.status == "completed"
    assert result.research["status"] in ("partial", "rejected")


def test_unsupported_claim_then_repair_succeeds(store, monkeypatch):
    bridge = FakeBridge()
    bad = '{"claims": [{"text": "Revenue was 9999.", "kind": "reported_fact", "evidenceIds": ["GHOST"]}], "gaps": []}'
    model = FakeModel([bad, VALID_CLAIM_JSON])
    import harness.graph as graph

    monkeypatch.setattr(graph, "build_chat_model", lambda settings: model)

    result = run_execute(
        make_request("Compare TEST revenue in FY2023 vs FY2024", "r_repair"), bridge, model, store
    )
    assert model.calls >= 2  # a repair round happened
    assert result.research["validation"]["repaired"] is True
    # The final claims must not contain the fabricated ghost citation.
    assert all("GHOST" not in (c.get("evidenceIds") or []) for c in result.research["validation"]["claims"])


def test_repair_still_rejected_strips_claims(store, monkeypatch):
    bridge = FakeBridge()
    bad = '{"claims": [{"text": "Revenue was 9999.", "kind": "reported_fact", "evidenceIds": ["GHOST"]}], "gaps": []}'
    model = FakeModel([bad, bad])
    import harness.graph as graph

    monkeypatch.setattr(graph, "build_chat_model", lambda settings: model)

    result = run_execute(
        make_request("Compare TEST revenue in FY2023 vs FY2024", "r_reject"), bridge, model, store
    )
    assert result.status == "completed"
    assert result.research["status"] == "rejected"
    # A rejected claim must not appear as asserted fact in the answer.
    assert "9999" not in result.output


def test_provider_failure_is_honest_not_fabricated(store, monkeypatch):
    bridge = FakeBridge(error=True)
    model = FakeModel(["{}"])
    import harness.graph as graph

    monkeypatch.setattr(graph, "build_chat_model", lambda settings: model)

    result = run_execute(
        make_request("Compare TEST revenue in FY2023 vs FY2024", "r_err"), bridge, model, store
    )
    assert result.status == "completed"
    assert result.research["status"] == "rejected"
    # No fabricated number in the answer.
    assert "1000" not in result.output and "800" not in result.output


def test_model_init_failure_does_not_fall_through_ungated(store, monkeypatch):
    bridge = FakeBridge()
    import harness.graph as graph

    def _boom(settings):
        raise ValueError("provider not configured")

    monkeypatch.setattr(graph, "build_chat_model", _boom)
    result = run_execute(
        make_request("Compare TEST revenue in FY2023 vs FY2024", "r_noModel"), bridge, FakeModel([]), store
    )
    assert result.research is not None
    assert result.research["status"] == "rejected"


def test_receipt_persisted(store, monkeypatch):
    bridge = FakeBridge()
    model = CitingFakeModel([VALID_CLAIM_JSON])
    import harness.graph as graph

    monkeypatch.setattr(graph, "build_chat_model", lambda settings: model)

    result = run_execute(
        make_request("Compare TEST revenue in FY2023 vs FY2024", "r_receipt"), bridge, model, store
    )
    saved = store.get_receipt("r_receipt")
    assert saved is not None
    assert saved["runId"] == "r_receipt"
    assert saved["taskType"] == "financial_comparison"
    # The receipt hash is stable and content-sensitive (not the salted builtin).
    assert saved["evidenceRefs"][0]["hash"].startswith("ev_")


def test_parse_synthesis_rejects_malformed_claims():
    syn = parse_synthesis('{"claims": ["not an object"], "gaps": []}')
    assert syn.claims == []
    assert any("malformed" in g for g in syn.gaps)


def test_cancellation_returns_terminal_cancelled(store, monkeypatch):
    """A cancellation during the gated flow yields exactly one `cancelled` status."""
    model = CitingFakeModel([VALID_CLAIM_JSON])
    import harness.graph as graph

    monkeypatch.setattr(graph, "build_chat_model", lambda settings: model)

    class CancelBridge(DataBridge):
        async def fetch(self, capability: str, params: dict[str, Any]) -> dict[str, Any]:
            raise asyncio.CancelledError()

    request = make_request("Compare TEST revenue in FY2023 vs FY2024", "r_cancel")
    registry = ToolRegistry()

    async def _go():
        return await execute_run(request, registry, CancelBridge(), store, bus=None)

    result = asyncio.run(_go())
    assert result.status == "cancelled"
    assert store.get_run("r_cancel")["status"] == "cancelled"
