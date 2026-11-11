"""Round 5 / C3: a truncated tool result keeps its full text behind a handle."""

from __future__ import annotations

import os
import tempfile

import pytest

from harness.persistence import AgentMemoryStore
from harness.tool_outputs import ToolOutputStore
from harness.tools import ToolContext, ToolDefinition, ToolRegistry


@pytest.fixture()
def store():
    directory = tempfile.mkdtemp(prefix="be-toolout-")
    s = AgentMemoryStore(os.path.join(directory, "agent-memory.db"))
    s.create_run("run_1", "eclipse-agent", {"query": "x"})
    s.create_run("run_2", "eclipse-agent", {"query": "x"})
    yield s
    s.close()


def test_the_full_text_survives_and_is_paged(store):
    store_ = ToolOutputStore(store._db)
    text = "".join(f"row-{i}\n" for i in range(5_000))
    saved = store_.save("run_1", "big_tool", text)
    assert saved is not None
    assert saved["chars"] == len(text)

    first = store_.read("run_1", saved["id"], offset=0, limit=100)
    assert first["text"] == text[:100]
    assert first["nextOffset"] == 100

    second = store_.read("run_1", saved["id"], offset=100, limit=100)
    assert second["text"] == text[100:200]


def test_a_handle_is_scoped_to_the_run_that_produced_it(store):
    store_ = ToolOutputStore(store._db)
    saved = store_.save("run_1", "big_tool", "secret")
    assert store_.read("run_1", saved["id"]) is not None
    assert store_.read("run_2", saved["id"]) is None


@pytest.mark.asyncio
async def test_a_truncated_tool_result_names_its_handle_and_the_pager_reads_it(store):
    from harness.tool_outputs import register_tool_output_tools

    reg = ToolRegistry()
    register_tool_output_tools(reg)

    async def handler(_args, _ctx):
        return "z" * 60_000

    reg.register(ToolDefinition(
        name="big", description="big", input_schema={"type": "object", "properties": {}},
        handler=handler, permission="read",
    ))

    ctx = ToolContext(run_id="run_1", log=lambda *_: None, memory_store=store)
    result = await reg.execute("big", "c1", {}, ctx)

    assert result.truncated is True
    assert result.output_id
    assert "read_tool_output" in result.text

    page = await reg.execute(
        "read_tool_output", "c2", {"id": result.output_id, "offset": result.shown_chars},
        ctx,
    )
    assert page.ok is True
    assert page.data["status"] == "OK"
    assert page.data["offset"] == result.shown_chars
    assert "z" in page.text
