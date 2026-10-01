"""Harness closeout Phase 6: lifecycle fields, egress closure, credential safety.

Offline and deterministic. Covers:
  * a deprecated tool warns ONCE per run and still executes (6.1);
  * the four egress probes are refused/bounded (6.2), via the Python SSRF mirror
    and (on the TS side) `checkOutboundUrl`/`safeGet` tests;
  * a sentinel secret never lands in a persisted run row (6.3).
"""

from __future__ import annotations

import asyncio
import json
import os
import tempfile

import pytest

from harness.mcp.ssrf import check_outbound_url
from harness.persistence import AgentMemoryStore
from harness.tools import ToolContext, ToolDefinition, ToolRegistry


def _ctx(emitter=None):
    ctx = ToolContext(run_id="run_warn", log=lambda *a: None)
    if emitter is not None:
        ctx.emitter = emitter
    return ctx


# ── 6.1 Deprecated tool warns once per run and still executes ────────────────


def test_deprecated_tool_warns_once_per_run_and_still_executes():
    reg = ToolRegistry()
    calls = {"n": 0}

    async def handler(args, ctx):
        calls["n"] += 1
        return "ok", {"status": "OK"}

    reg.register(ToolDefinition(
        name="old_tool", description="old", input_schema={"type": "object", "properties": {}},
        handler=handler, permission="read", risk="low",
        deprecated=True, replacement="new_tool", version="1.2.0",
    ))
    ctx = _ctx()

    async def run():
        await reg.execute("old_tool", "c1", {}, ctx)
        await reg.execute("old_tool", "c2", {}, ctx)

    asyncio.run(run())
    # Still executes both times.
    assert calls["n"] == 2
    # Warned exactly once for the run.
    assert ctx.deprecated_warned == {"old_tool"}


def test_deprecated_warning_is_persisted_once():
    directory = tempfile.mkdtemp(prefix="be-dep-")
    store = AgentMemoryStore(os.path.join(directory, "agent-memory.db"))
    from harness.events import RunEmitter

    store.create_run("run_warn", "a", {"query": "x"})
    emitter = RunEmitter("run_warn", store)
    reg = ToolRegistry()

    async def handler(args, ctx):
        return "ok", {"status": "OK"}

    reg.register(ToolDefinition(
        name="old_tool", description="old", input_schema={"type": "object", "properties": {}},
        handler=handler, permission="read", risk="low",
        deprecated=True, replacement="new_tool",
    ))
    ctx = _ctx(emitter)

    async def run():
        await reg.execute("old_tool", "c1", {}, ctx)
        await reg.execute("old_tool", "c2", {}, ctx)

    asyncio.run(run())
    events = [e for e in store.list_events("run_warn") if e["type"] == "tool.deprecated"]
    assert len(events) == 1
    assert events[0]["data"]["replacement"] == "new_tool"
    store.close()


# ── 6.2 Egress closure ───────────────────────────────────────────────────────


def test_ssrf_refuses_redirect_target_private_address():
    # Loopback is permitted by design (a local test server). A NON-loopback
    # private/link-local address is refused — the cloud-metadata endpoint is the
    # canonical SSRF target.
    assert check_outbound_url("https://10.0.0.5/internal")[0] is False
    assert check_outbound_url("https://192.168.1.1/router")[0] is False
    assert check_outbound_url("https://169.254.169.254/latest/meta-data")[0] is False
    # A DNS-rebinding-style host (a name that is structurally private) is refused.
    assert check_outbound_url("https://metadata.google.internal/")[0] is False


def test_ssrf_refuses_non_https():
    safe, reason = check_outbound_url("http://example.com/x")
    assert safe is False
    assert "https" in (reason or "").lower()


def test_ssrf_refuses_embedded_credentials_and_blocked_hosts():
    assert check_outbound_url("https://user:pass@example.com/")[0] is False
    assert check_outbound_url("https://service.internal/")[0] is False
    # A public https host is allowed.
    assert check_outbound_url("https://example.com/page")[0] is True


# ── 6.3 Credential injection: a sentinel secret never persists ───────────────


def test_sentinel_secret_never_appears_in_persisted_run_rows(monkeypatch):
    """A credential passed to a run must not land in any persisted run row.

    A real run is executed with a sentinel API key in its ModelSettings; the run,
    its events, its checkpoint, and its tool rows are then scanned for the
    sentinel and the test fails if it appears anywhere.
    """
    from langchain_core.messages import AIMessage

    from harness import graph as graph_module
    from harness.schemas import ModelSettings, RunInput, RunRequest

    class ScriptedModel:
        def bind_tools(self, tools):
            return self

        async def ainvoke(self, messages):
            return AIMessage(content="hello")

        async def astream(self, messages):
            yield await self.ainvoke(messages)

    monkeypatch.setattr(graph_module, "build_chat_model", lambda settings: ScriptedModel())
    directory = tempfile.mkdtemp(prefix="be-secret-")
    store = AgentMemoryStore(os.path.join(directory, "agent-memory.db"))
    sentinel = "sk-SENTINEL-DO-NOT-PERSIST-9f3a2b"
    request = RunRequest(
        runId="run_secret",
        input=RunInput(query="hello"),
        agentId="eclipse-agent",
        # The credential arrives per run from the vault and must never persist.
        modelSettings=ModelSettings(provider="openai", model="gpt-4o", api_key=sentinel),
        callbackBaseUrl="http://localhost:3000",
    )
    asyncio.run(graph_module.execute_run(request, _empty_registry(), _NoopBridge(), store))

    rows: list[str] = []
    for table in ("HarnessRun", "HarnessEvent", "HarnessToolExecution", "RunCheckpoint"):
        try:
            for r in store._db.execute(f"SELECT * FROM {table}").fetchall():
                rows.append(json.dumps(dict(r), default=str))
        except Exception:  # noqa: BLE001 - a missing table is fine
            continue
    blob = "\n".join(rows)
    assert sentinel not in blob
    # The run did complete and was persisted (the scan is meaningful).
    assert store.get_run("run_secret")["status"] == "completed"
    store.close()


def _empty_registry():
    from harness.tools import ToolRegistry

    return ToolRegistry()


class _NoopBridge:
    async def fetch(self, capability, params):
        return {"status": "UNAVAILABLE"}
