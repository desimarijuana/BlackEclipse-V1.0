"""Phase 8 — the `analysis_run` tool: default OFF, and the computed surface.

The tool registers on the one registry; it is reachable only when the run enables
it (`RunRequest.analysisEnabled`) and holds `analysis.execute`. A computed result
is labelled "Worked out by Eclipse", never presented as retrieved data.
"""

from __future__ import annotations

import asyncio

from harness.analysis_tools import analysis_run, analysis_schema
from harness.code import sandbox as sandbox_mod
from harness.code.execution import interpreter_path
from harness.code.tools import register_code_tools
from harness.schemas import ModelSettings
from harness.tools import ToolContext, ToolRegistry


def _has_runner() -> bool:
    try:
        sandbox_mod.select_backend()
    except sandbox_mod.SandboxUnavailable:
        return False
    return bool(interpreter_path())


def _ctx(**overrides) -> ToolContext:
    base = dict(
        run_id="run_a",
        log=lambda *_: None,
        user_id="local",
        model_settings=ModelSettings(provider="ollama", model="llama3.1"),
        tool_registry=ToolRegistry(),
        memory_store=None,
        analysis_enabled=True,
    )
    base.update(overrides)
    return ToolContext(**base)


def test_analysis_run_is_registered():
    registry = ToolRegistry()
    register_code_tools(registry)
    assert registry.get("analysis_run") is not None


def test_schema_is_well_formed():
    schema = analysis_schema()
    assert schema["type"] == "object"
    assert "inputs" in schema["properties"]
    assert schema["required"] == ["purpose"]


def test_default_off_refuses_even_with_a_recipe():
    result = asyncio.run(analysis_run(
        {"recipe": "returns_series", "inputs": {"prices": [1, 2, 3]}, "purpose": "x"},
        _ctx(analysis_enabled=False),
    ))
    text, data = result
    assert data["status"] == "refused"
    assert data["code"] == "ANALYSIS_NOT_ENABLED"


def test_missing_input_asks_rather_than_guessing():
    result = asyncio.run(analysis_run(
        {"recipe": "returns_series", "inputs": {}, "purpose": "over time"}, _ctx(),
    ))
    text, data = result
    assert data["status"] == "refused"
    assert data["code"] == "INPUT_INVALID"
    assert data.get("prompt")


def test_unknown_recipe_is_refused():
    result = asyncio.run(analysis_run(
        {"recipe": "nope", "inputs": {}, "purpose": "x"}, _ctx(),
    ))
    _, data = result
    assert data["status"] == "refused"


def test_computed_result_is_labelled_and_carries_provenance():
    if not _has_runner():
        import pytest

        pytest.skip("sandbox/interpreter unavailable")
    text, data = asyncio.run(analysis_run(
        {"recipe": "period_comparison", "inputs": {"current": 120, "previous": 100}, "purpose": "this quarter vs last"},
        _ctx(),
    ))
    assert data["status"] == "ok"
    assert "Worked out by Eclipse" in text
    assert data["provenance"]["kind"] == "computed"
    # The surface never names the mechanism.
    for word in ("interpreter", "argv", "stdout", "exit code"):
        assert word not in text.lower()
