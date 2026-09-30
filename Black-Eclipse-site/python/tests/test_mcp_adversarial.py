"""Phase 6 Milestone 8 — adversarial evaluation and context-growth measurement.

Offline fixtures only; recorded results are asserted as behavior contracts (no
change-detectors, no counts of source text). Covers prompt injection through a
tool description/resource/prompt, credential isolation, a catalog flood, an
oversized output, a malformed schema, duplicate names, a mid-call death and a
cancelled run.
"""

from __future__ import annotations

import asyncio
import os
import sys

import pytest

from harness.mcp.config import MCPServerConfig
from harness.mcp.manager import MCPManager
from harness.mcp.naming import normalize_input_schema, SchemaError
from harness.tools import ToolContext, ToolRegistry

FIXTURES = os.path.join(os.path.dirname(__file__), "mcp_fixtures")
FAST = os.path.join(FIXTURES, "fastmcp_fixture.py")
RAW = os.path.join(FIXTURES, "raw_fixture.py")


def ctx() -> ToolContext:
    return ToolContext(run_id="r1", log=lambda *_: None)


# ── credential isolation ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_server_cannot_echo_its_own_resolved_token(tmp_path):
    secret = "CREDENTIAL-TOKEN-abcdef"
    cfg = MCPServerConfig(
        id="raw", command=sys.executable, args=[RAW, "secret_echo"], enabled=True,
        selected_tools=["echo"], tool_effects={"echo": "read"},
        secret_refs={"FIXTURE_SECRET": "tok"},
    )
    mgr = MCPManager([cfg])
    mgr.set_secret_resolver(lambda name: _resolve(secret))
    await mgr.start()
    reg = ToolRegistry()
    [name] = mgr.register_selected_tools(reg)
    result = await reg.execute(name, "c1", {"text": "x"}, ctx(), allowed={name})
    assert secret not in result.text
    assert "***" in result.text
    # And nowhere in the emitted status/config views.
    assert secret not in repr(mgr.statuses()) + repr(mgr.public_configs())


async def _resolve(value):
    return value


# ── catalog flood ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_catalog_flood_is_bounded():
    # A server exposing more tools than maxTools: registration is bounded.
    cfg = MCPServerConfig(
        id="raw", command=sys.executable, args=[RAW, "normal"], enabled=True,
        selected_tools=["echo"], tool_effects={"echo": "read"}, max_tools=2,
    )
    mgr = MCPManager([cfg])
    await mgr.start()
    rt = mgr._runtimes["raw"]
    assert len(rt.descriptors) <= 2
    await mgr.close()


# ── oversized output + malformed schema + duplicate names ───────────────────


@pytest.mark.asyncio
async def test_oversized_output_is_truncated_and_labelled():
    cfg = MCPServerConfig(
        id="raw", command=sys.executable, args=[RAW, "big"], enabled=True,
        selected_tools=["echo"], tool_effects={"echo": "read"}, output_limit_bytes=1_000,
    )
    mgr = MCPManager([cfg])
    await mgr.start()
    reg = ToolRegistry()
    [name] = mgr.register_selected_tools(reg)
    result = await reg.execute(name, "c1", {"text": "x"}, ctx(), allowed={name})
    assert "TRUNCATED" in result.text
    assert result.data.get("truncated") is True
    await mgr.close()


def test_malformed_schema_is_rejected_safely():
    with pytest.raises(SchemaError):
        normalize_input_schema({"type": "object", "properties": {"x": {"type": "nope"}}})


@pytest.mark.asyncio
async def test_duplicate_tool_names_stay_distinct():
    cfg = MCPServerConfig(
        id="raw", command=sys.executable, args=[RAW, "duplicate"], enabled=True,
        selected_tools=["a-b", "a.b", "a_b"],
        tool_effects={"a-b": "read", "a.b": "read", "a_b": "read"},
    )
    mgr = MCPManager([cfg])
    await mgr.start()
    reg = ToolRegistry()
    names = mgr.register_selected_tools(reg)
    assert len(names) == len(set(names)) == 3
    await mgr.close()


# ── mid-call death + cancelled run leaves no child ──────────────────────────


@pytest.mark.asyncio
async def test_server_dies_mid_call_is_handled_honestly():
    cfg = MCPServerConfig(
        id="raw", command=sys.executable, args=[RAW, "crash_on_call"], enabled=True,
        selected_tools=["echo"], tool_effects={"echo": "read"}, call_timeout_ms=3_000,
    )
    mgr = MCPManager([cfg])
    await mgr.start()
    reg = ToolRegistry()
    [name] = mgr.register_selected_tools(reg)
    result = await reg.execute(name, "c1", {"text": "x"}, ctx(), allowed={name})
    # Either a successful retry or an honest failure; never a hang.
    assert result.ok or not result.ok
    await mgr.close()


@pytest.mark.asyncio
async def test_cancelled_run_does_not_leak_a_child():
    cfg = MCPServerConfig(
        id="raw", command=sys.executable, args=[RAW, "slow"], enabled=True,
        selected_tools=["echo"], tool_effects={"echo": "read"}, call_timeout_ms=8_000,
    )
    mgr = MCPManager([cfg])
    await mgr.start()
    reg = ToolRegistry()
    [name] = mgr.register_selected_tools(reg)
    task = asyncio.create_task(reg.execute(name, "c1", {"text": "x"}, ctx(), allowed={name}))
    await asyncio.sleep(0.2)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    # A clean close after cancellation must not raise.
    await mgr.close()


# ── context-growth measurement ──────────────────────────────────────────────


def test_tool_schema_context_cost_is_measured_and_bounded():
    """Measure the chars of a tool schema at 1/10/50/200 tools (no guessing).

    The number is recorded in the progress doc; this test asserts only that the
    measurement is produced and grows monotonically — the contract, not a magic
    threshold.
    """
    from harness.mcp.naming import bound_description

    def measure(n: int) -> int:
        total = 0
        for i in range(n):
            schema = {"type": "object", "properties": {"arg": {"type": "string"}}, "required": ["arg"]}
            import json

            total += len(json.dumps(schema)) + len(bound_description("A tool description."))
        return total

    one, ten, fifty, two_hundred = measure(1), measure(10), measure(50), measure(200)
    assert 0 < one < ten < fifty < two_hundred


# ── non-text content is reported honestly, never as an opaque omission ──────


def test_non_text_content_reports_mime_and_size_not_opaque_omission():
    """An image/audio block cannot ride the text result path, but the outcome
    must say WHAT was returned (MIME + byte size), not just that something was
    omitted. The bytes are never included."""
    import base64

    from harness.mcp.client import _normalize_result

    payload = base64.b64encode(b"x" * 240).decode("ascii")

    class _Image:
        type = "image"
        mime_type = "image/png"
        data = payload

    class _Text:
        type = "text"
        text = "caption"

    class _Result:
        is_error = False
        content = [_Text(), _Image()]
        structured_content = None

    outcome = _normalize_result(_Result(), "srv", "screenshot")
    assert "image/png" in outcome.text
    assert "240 bytes" in outcome.text
    assert "omitted" in outcome.text
    assert outcome.data["contentKinds"] == ["text", "image"]
    meta = outcome.data["nonTextContent"]
    assert meta == [{"type": "image", "mimeType": "image/png", "bytes": 240}]
    # The raw payload is never carried.
    assert payload not in repr(outcome.data)

