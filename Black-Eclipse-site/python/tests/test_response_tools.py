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
async def test_schema_tool_lists_the_live_icon_vocabulary():
    reg = ToolRegistry()
    register_response_contract_tools(reg)
    bridge = _Bridge({
        "status": "OK",
        "blocks": [{
            "type": "workflow",
            "fields": [{
                "name": "stages",
                "required": True,
                "kind": "array",
                "itemFields": ["id", "icon", "title"],
            }],
        }],
        "iconKeys": ["trend-up", "chart", "gears"],
    })
    result = await reg.execute("response_block_schema", "c1", {}, _ctx(bridge))
    assert result.ok
    assert "trend-up, chart, gears" in result.text
    assert "never an emoji" in result.text


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


@pytest.mark.asyncio
async def test_schema_prompt_block_carries_exact_names_and_enums():
    from harness.response_tools import response_schema_prompt_block

    bridge = _Bridge({
        "status": "OK",
        "blocks": [
            {
                "type": "chart",
                "fields": [
                    {"name": "chartType", "required": True, "kind": "enum(line|bar)"},
                    {"name": "categories", "required": False, "kind": "string[]"},
                    {"name": "series", "required": True, "kind": "object[]", "itemFields": ["name", "data"]},
                ],
            },
            {
                "type": "flow",
                "fields": [
                    {"name": "steps", "required": True, "kind": "object[]",
                     "itemFields": ["id", "label", "tone"]},
                ],
            },
        ],
        "iconKeys": ["trend-up", "trend-down"],
    })
    digest = await response_schema_prompt_block(bridge)
    assert "authoritative" in digest
    assert "series?:" not in digest and "series:" in digest
    assert "series:object[]{name,data}" in digest
    assert "enum(line|bar)" in digest
    assert "trend-up, trend-down" in digest
    assert bridge.calls == [("response_contract", {"op": "schema"})]


@pytest.mark.asyncio
async def test_schema_prompt_block_degrades_quietly():
    from harness.response_tools import response_schema_prompt_block

    assert await response_schema_prompt_block(None) == ""
    assert await response_schema_prompt_block(_Bridge({"status": "UNAVAILABLE"})) == ""
    assert await response_schema_prompt_block(_Bridge({"status": "OK", "blocks": []})) == ""


@pytest.mark.asyncio
async def test_schema_prompt_block_survives_a_bridge_error():
    from harness.response_tools import response_schema_prompt_block

    class _Boom:
        async def fetch(self, capability: str, params: dict) -> dict:  # noqa: ARG002
            raise RuntimeError("bridge down")

    assert await response_schema_prompt_block(_Boom()) == ""


@pytest.mark.asyncio
async def test_response_telemetry_reads_finalize_and_emits_the_hook():
    from harness.observability.core import ObservabilityHub, HookEvent
    from harness.observability import events as obs_events
    from harness.response_tools import emit_response_telemetry

    assert "onResponseBlocks" in obs_events.HOOKS

    hub = ObservabilityHub()
    hub_events: list[HookEvent] = []
    hub.register_observer(lambda event: hub_events.append(event))

    class _FinalizeBridge:
        def __init__(self) -> None:
            self.calls: list[tuple[str, dict]] = []

        async def fetch(self, capability: str, params: dict) -> dict:
            self.calls.append((capability, params))
            return {
                "status": "OK", "blocks": 3,
                "repaired": 1, "degraded": 1,
                "repairedTypes": ["chart"], "degradedTypes": ["hologram"],
            }

    import harness.observability as obs

    previous = obs._hub
    obs.set_hub(hub)
    try:
        bridge = _FinalizeBridge()
        await emit_response_telemetry(bridge, "```eclipse-response\n{}\n```")
    finally:
        obs.set_hub(previous)

    assert bridge.calls == [("response_contract", {"op": "finalize", "markdown": "```eclipse-response\n{}\n```"})]
    assert len(hub_events) == 1
    assert hub_events[0].hook == "onResponseBlocks"
    assert hub_events[0].attributes["repaired"] == ["chart"]
    counters = hub.metrics.snapshot()["counters"]["eclipse_response_blocks_total"]
    assert counters['{outcome="repaired",type="chart"}'] == 1
    assert counters['{outcome="degraded",type="hologram"}'] == 1


@pytest.mark.asyncio
async def test_response_telemetry_is_a_noop_without_a_structured_answer():
    from harness.response_tools import emit_response_telemetry

    class _Bridge:
        def __init__(self) -> None:
            self.calls: list[tuple[str, dict]] = []

        async def fetch(self, capability: str, params: dict) -> dict:
            self.calls.append((capability, params))
            return {"status": "OK", "blocks": 0}

    bridge = _Bridge()
    await emit_response_telemetry(bridge, "plain prose, no fence")
    await emit_response_telemetry(None, "```eclipse-response\n{}\n```")
    assert bridge.calls == []
