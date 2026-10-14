"""Response-contract tools: schema lookup + pre-send validation formatting."""

from __future__ import annotations

import pytest

from harness.response_tools import register_response_contract_tools
from harness.tools import ToolContext, ToolRegistry


class _Bridge:
    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.calls: list[tuple[str, dict]] = []

    async def fetch(self, capability: str, params: dict) -> dict:
        self.calls.append((capability, params))
        return self.payload


def _ctx(bridge) -> ToolContext:  # noqa: ANN001
    return ToolContext(run_id="r1", log=lambda *_: None, data_bridge=bridge)


@pytest.mark.asyncio
async def test_schema_tool_formats_exact_fields():
    reg = ToolRegistry()
    register_response_contract_tools(reg)
    bridge = _Bridge({
        "status": "OK",
        "blocks": [{
            "type": "mermaid",
            "fields": [
                {"name": "diagram", "required": True, "kind": "string"},
                {"name": "id", "required": False, "kind": "string"},
            ],
        }],
    })
    result = await reg.execute("response_block_schema", "c1", {"block_type": "mermaid"}, _ctx(bridge))
    assert result.ok
    assert "mermaid" in result.text
    assert "diagram (string)" in result.text
    assert "id? (string)" in result.text
    assert bridge.calls == [("response_contract", {"op": "schema", "block_type": "mermaid"})]


@pytest.mark.asyncio
async def test_validate_tool_names_the_failing_block_and_next_step():
    reg = ToolRegistry()
    register_response_contract_tools(reg)
    bridge = _Bridge({
        "status": "OK",
        "ok": False,
        "blocks": [
            {"index": 0, "type": "markdown", "ok": True, "error": None},
            {"index": 1, "type": "badge_row", "ok": False,
             "error": "BLOCK_INVALID: badges.0: expected object, received string"},
        ],
        "diagnostics": [{"code": "BLOCK_INVALID", "message": "badges.0", "blockIndex": 1}],
    })
    result = await reg.execute(
        "response_validate", "c1", {"markdown": "```eclipse-response\n{}\n```"}, _ctx(bridge)
    )
    assert result.ok
    assert "NOT OK" in result.text
    assert "#1 `badge_row`" in result.text
    assert "response_validate again" in result.text


@pytest.mark.asyncio
async def test_validate_tool_confirms_a_healthy_payload():
    reg = ToolRegistry()
    register_response_contract_tools(reg)
    bridge = _Bridge({"status": "OK", "ok": True, "blocks": [{"index": 0, "type": "data_table", "ok": True}]})
    result = await reg.execute(
        "response_validate", "c1", {"markdown": "```eclipse-response\n{}\n```"}, _ctx(bridge)
    )
    assert result.ok
    assert result.text.startswith("OK —")


@pytest.mark.asyncio
async def test_tools_report_unavailable_without_a_bridge():
    reg = ToolRegistry()
    register_response_contract_tools(reg)
    bridge = None
    for name, args in (
        ("response_block_schema", {}),
        ("response_validate", {"markdown": "```eclipse-response\n{}\n```"}),
    ):
        result = await reg.execute(name, "c1", args, _ctx(bridge))
        assert result.ok
        assert "UNAVAILABLE" in result.text


def test_both_tools_are_registered():
    reg = ToolRegistry()
    register_response_contract_tools(reg)
    assert {"response_block_schema", "response_validate"} <= set(reg.names())
