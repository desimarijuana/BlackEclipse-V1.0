"""W2: prune old tool output without losing evidence/provenance."""

from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from harness.context.pruning import prune_tool_messages


def test_prune_old_tool_results_keeps_last_and_evidence():
    messages = [
        HumanMessage(content="q"),
        ToolMessage(content="old code output " * 100, tool_call_id="c1", name="terminal"),
        ToolMessage(content='{"handles":["a"]} ' * 100, tool_call_id="c2", name="get_quote"),
        ToolMessage(content="recent " * 100, tool_call_id="c3", name="patch"),
        AIMessage(content="answer"),
    ]
    pruned, count = prune_tool_messages(messages, protect_last=1)
    assert count == 1
    assert "pruned tool result" in pruned[1].content
    assert "handles" in pruned[2].content
    assert "recent" in pruned[3].content


def test_prune_is_a_noop_for_short_context():
    messages = [ToolMessage(content="short", tool_call_id="c1", name="terminal")]
    pruned, count = prune_tool_messages(messages)
    assert count == 0
    assert pruned[0].content == "short"
