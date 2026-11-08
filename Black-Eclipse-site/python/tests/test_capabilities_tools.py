"""The capability tools detect, build, use, report and retire a generated recipe."""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from harness.analysis_tools import analysis_run
from harness.capabilities.registry import is_generated_recipe
from harness.capabilities.tools import (
    capability_build,
    capability_remove,
    capability_request,
    capability_status,
)
from harness.code import sandbox as sandbox_mod
from harness.code.execution import interpreter_path
from harness.persistence import AgentMemoryStore
from harness.tools import ToolContext, ToolRegistry


def _has_runner() -> bool:
    try:
        sandbox_mod.select_backend()
    except sandbox_mod.SandboxUnavailable:
        return False
    return bool(interpreter_path())


def _ctx(tmp_path: Path, memory: AgentMemoryStore, *, analysis_enabled: bool = True) -> ToolContext:
    return ToolContext(
        run_id="run_cap_tool",
        log=lambda *_: None,
        memory_store=memory,
        analysis_enabled=analysis_enabled,
        tool_registry=ToolRegistry(),
        workspace=SimpleNamespace(root=tmp_path, id="ws_cap"),
    )


def _need() -> dict:
    return {
        "need": "from now on compute the ulcer index of a price series",
        "kind": "recipe",
        "capabilityId": "ulcer_index",
        "inputs": [{"name": "prices", "kind": "series"}],
        "outputs": [{"name": "ulcerIndex", "kind": "scalar"}],
        "acceptance": ["A known price series yields the expected Ulcer Index."],
    }


_IMPLEMENTATION = """
import math
prices = inputs.get("prices")
peak = prices[0]
squares = []
for price in prices:
    peak = max(peak, price)
    drawdown = (price / peak - 1.0) * 100.0 if peak else 0.0
    squares.append(drawdown * drawdown)
result = {"ulcerIndex": round(math.sqrt(sum(squares) / len(squares)), 6)}
"""

_TEST = """
assert result["ulcerIndex"] == 12.909944
"""


def test_a_drawdown_request_is_satisfied_by_an_existing_recipe(tmp_path: Path):
    memory = AgentMemoryStore(str(tmp_path / "agent-memory.db"))
    try:
        _text, data = asyncio.run(capability_request(
            {"need": "compute the drawdown profile"}, _ctx(tmp_path, memory),
        ))
        assert data["status"] == "satisfied"
        assert data["assessment"]["resolvedBy"] == "drawdown_profile"
    finally:
        memory.close()


def test_a_capability_is_callable_in_its_project_and_not_in_another(tmp_path: Path):
    if not _has_runner():
        pytest.skip("sandbox/interpreter unavailable")
    memory = AgentMemoryStore(str(tmp_path / "agent-memory.db"))
    try:
        project_b = tmp_path / "project_b"
        project_a = tmp_path / "project_a"
        project_b.mkdir()
        project_a.mkdir()
        ctx_b = _ctx(project_b, memory)
        ctx_a = _ctx(project_a, memory)

        # Build the recipe in project B.
        _text, requested = asyncio.run(capability_request(_need(), ctx_b))
        assert requested["status"] == "gap"
        _text, built = asyncio.run(capability_build({
            "requestId": requested["requestId"],
            "implementation": _IMPLEMENTATION,
            "test": _TEST,
            "sampleInputs": {"prices": [100, 90, 80]},
        }, ctx_b))
        assert built["status"] == "active"
        assert is_generated_recipe("ulcer_index") is True

        # It lives in B's .black-eclipse, not the app repo.
        assert (project_b / ".black-eclipse" / "capabilities" / "ulcer_index").is_dir()
        assert not (project_a / ".black-eclipse" / "capabilities" / "ulcer_index").exists()

        # In project A the same request is a gap again, and B's recipe is not
        # callable: the executable registry follows the run's project.
        _text, requested_a = asyncio.run(capability_request(_need(), ctx_a))
        assert requested_a["status"] == "gap"
        assert is_generated_recipe("ulcer_index") is False

        # Back in B it is callable again without rebuilding.
        _text, requested_b = asyncio.run(capability_request(_need(), ctx_b))
        assert requested_b["status"] == "satisfied"
        assert is_generated_recipe("ulcer_index") is True
    finally:
        memory.close()


def test_request_build_use_and_retire(tmp_path: Path):
    if not _has_runner():
        pytest.skip("sandbox/interpreter unavailable")
    memory = AgentMemoryStore(str(tmp_path / "agent-memory.db"))
    try:
        ctx = _ctx(tmp_path, memory)
        _text, requested = asyncio.run(capability_request(_need(), ctx))
        assert requested["status"] == "gap"
        request_id = requested["requestId"]

        _text, built = asyncio.run(capability_build({
            "requestId": request_id,
            "implementation": _IMPLEMENTATION,
            "test": _TEST,
            "sampleInputs": {"prices": [100, 90, 80]},
        }, ctx))
        assert built["status"] == "active"
        assert built["activated"] is True
        assert built["verification"]["status"] == "verified"

        _text, used = asyncio.run(analysis_run({
            "recipe": "ulcer_index",
            "inputs": {"prices": [100, 90, 80]},
            "purpose": "ulcer index",
        }, ctx))
        assert used["status"] == "ok"
        assert used["outputs"]["ulcerIndex"] == 12.909944

        _text, status = asyncio.run(capability_status({"requestId": request_id}, ctx))
        assert status["status"] == "ok"
        assert status["records"][0]["status"] == "active"

        _text, retired = asyncio.run(capability_remove({"capabilityId": "ulcer_index"}, ctx))
        assert retired["status"] == "retired"
    finally:
        memory.close()


def test_building_requires_the_analysis_sandbox(tmp_path: Path):
    memory = AgentMemoryStore(str(tmp_path / "agent-memory.db"))
    try:
        ctx = _ctx(tmp_path, memory, analysis_enabled=False)
        _text, requested = asyncio.run(capability_request(_need(), ctx))
        _text, built = asyncio.run(capability_build({
            "requestId": requested["requestId"],
            "implementation": _IMPLEMENTATION,
            "test": _TEST,
            "sampleInputs": {"prices": [100, 90, 80]},
        }, ctx))
        assert built["status"] == "refused"
        assert built["code"] == "ANALYSIS_NOT_ENABLED"
    finally:
        memory.close()


def test_an_effectful_handoff_does_not_need_the_analysis_sandbox(tmp_path: Path):
    memory = AgentMemoryStore(str(tmp_path / "agent-memory.db"))
    try:
        ctx = _ctx(tmp_path, memory, analysis_enabled=False)
        _text, requested = asyncio.run(capability_request({
            "need": "from now on prepare a weekly review",
            "kind": "skill",
            "capabilityId": "weekly_review",
        }, ctx))
        _text, built = asyncio.run(capability_build({
            "requestId": requested["requestId"],
        }, ctx))
        assert built["status"] == "handoff_required"
        assert built["nextTool"] == "skill_create"
        assert built["handoff"]["surface"] == "skill_create"
        assert built["activation"] == "operator"
    finally:
        memory.close()


def test_an_unknown_request_is_refused(tmp_path: Path):
    memory = AgentMemoryStore(str(tmp_path / "agent-memory.db"))
    try:
        _text, data = asyncio.run(capability_build({"requestId": "capreq_missing"}, _ctx(tmp_path, memory)))
        assert data["status"] == "refused"
        assert data["code"] == "REQUEST_NOT_FOUND"
    finally:
        memory.close()
