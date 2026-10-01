"""Tool-loop integrity Phase 3 — the native tool-result text bound.

`ToolRegistry.execute` is the single seam every tool passes through; a result
over `MAX_TOOL_RESULT_CHARS` is trimmed with an unmistakable non-JSON marker and
reports its own sizes. Under the bound the text is byte-identical (a safety net,
not a formatting feature). Only the text is bounded; the structured `data` is
never touched.
"""

from __future__ import annotations

import json

import pytest

from harness.tools import (
    MAX_TOOL_RESULT_CHARS,
    ToolContext,
    ToolDefinition,
    ToolRegistry,
    bound_tool_text,
)


def _ctx() -> ToolContext:
    return ToolContext(run_id="r1", log=lambda *_: None)


def _registry_returning(text: str, data=None) -> ToolRegistry:
    reg = ToolRegistry()

    async def handler(args, ctx):
        return (text, data) if data is not None else text

    reg.register(
        ToolDefinition(
            name="big",
            description="Returns a fixed result.",
            input_schema={"type": "object", "properties": {}},
            handler=handler,
        )
    )
    return reg


# ── the pure bound helper ───────────────────────────────────────────────────


def test_under_bound_text_is_byte_identical():
    text = "x" * (MAX_TOOL_RESULT_CHARS - 1)
    out, truncated, shown, total = bound_tool_text(text)
    assert out == text  # no marker, no whitespace change
    assert truncated is False
    assert shown == total == len(text)


def test_exactly_at_bound_is_not_truncated():
    text = "y" * MAX_TOOL_RESULT_CHARS
    out, truncated, shown, total = bound_tool_text(text)
    assert out == text
    assert truncated is False


def test_over_bound_is_cut_with_a_marker_naming_both_sizes():
    text = "z" * (MAX_TOOL_RESULT_CHARS + 500)
    out, truncated, shown, total = bound_tool_text(text)
    assert truncated is True
    assert total == MAX_TOOL_RESULT_CHARS + 500
    assert shown == MAX_TOOL_RESULT_CHARS
    assert "TRUNCATED" in out
    assert str(total) in out and str(shown) in out


def test_truncated_json_cannot_be_mistaken_for_complete_json():
    """A partial JSON document must not still parse as valid JSON."""
    payload = json.dumps({"rows": ["r" * 100 for _ in range(1000)]})
    assert len(payload) > MAX_TOOL_RESULT_CHARS
    out, truncated, _shown, _total = bound_tool_text(payload)
    assert truncated is True
    with pytest.raises(json.JSONDecodeError):
        json.loads(out)


# ── through the execution seam ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_registry_bounds_an_oversized_result_and_sets_structured_fields():
    big = "a" * (MAX_TOOL_RESULT_CHARS + 123)
    reg = _registry_returning(big, data={"keep": "me", "rows": [1, 2, 3]})
    result = await reg.execute("big", "c1", {}, _ctx())
    assert result.ok is True
    assert result.truncated is True
    assert result.total_chars == len(big)
    assert result.shown_chars == MAX_TOOL_RESULT_CHARS
    assert "TRUNCATED" in result.text
    assert len(result.text) < len(big)
    # The structured payload is NEVER bounded or altered.
    assert result.data == {"keep": "me", "rows": [1, 2, 3]}


@pytest.mark.asyncio
async def test_registry_leaves_an_under_bound_result_untouched():
    small = "hello world"
    reg = _registry_returning(small, data={"ok": True})
    result = await reg.execute("big", "c1", {}, _ctx())
    assert result.ok is True
    assert result.text == small
    assert result.truncated is False
    assert result.shown_chars == result.total_chars == len(small)
    assert "TRUNCATED" not in result.text
    assert result.data == {"ok": True}
