"""A generated recipe is built, tested, activated, versioned and reversible."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from harness.analysis_tools import analysis_run
from harness.capabilities import builder
from harness.capabilities.manifest import CapabilityManifest, CapabilityPort
from harness.capabilities.registry import generated_descriptors, refresh_generated_recipes
from harness.capabilities.request import CapabilityRequest
from harness.capabilities.store import CapabilityRecord, CapabilityStore
from harness.code import sandbox as sandbox_mod
from harness.code.execution import interpreter_path
from harness.code.recipes import get_recipe
from harness.persistence import AgentMemoryStore
from harness.tools import ToolContext, ToolRegistry


def _has_runner() -> bool:
    try:
        sandbox_mod.select_backend()
    except sandbox_mod.SandboxUnavailable:
        return False
    return bool(interpreter_path())


def _store(tmp_path: Path) -> tuple[AgentMemoryStore, CapabilityStore]:
    memory = AgentMemoryStore(str(tmp_path / "agent-memory.db"))
    return memory, CapabilityStore(memory)


def _request(**overrides) -> CapabilityRequest:
    base = {
        "need": "sum a series of values",
        "kind": "recipe",
        "capabilityId": "sum_values",
        "inputs": [CapabilityPort(name="values", kind="series")],
        "outputs": [CapabilityPort(name="sum", kind="scalar")],
        "implementation": (
            'values = inputs.get("values")\n'
            'result = {"sum": sum(values), "count": len(values)}\n'
        ),
        "test": 'assert result["sum"] == 6\nassert result["count"] == 3\n',
        "sampleInputs": {"values": [1, 2, 3]},
        "acceptance": ["a known series sums to the expected value"],
    }
    base.update(overrides)
    return CapabilityRequest(**base)


def test_pure_recipe_is_tested_and_auto_activated(tmp_path: Path):
    if not _has_runner():
        pytest.skip("sandbox/interpreter unavailable")
    memory, store = _store(tmp_path)
    try:
        outcome = builder.build(_request(), store=store, root=tmp_path, run_id="run_build")
        assert outcome["status"] == "active"
        assert outcome["activation"] == "auto"
        assert outcome["verification"]["status"] == "verified"
        version_dir = Path(outcome["dir"])
        assert (version_dir / "manifest.json").is_file()
        assert (version_dir / "capability.py").is_file()
        assert (version_dir / "test_capability.py").is_file()
        assert get_recipe("sum_values") is not None
        assert any(item.id == "sum_values" for item in generated_descriptors(store, tmp_path))

        ctx = ToolContext(
            run_id="run_use", log=lambda *_: None, memory_store=memory,
            analysis_enabled=True, tool_registry=ToolRegistry(),
            workspace=type("Ws", (), {"root": tmp_path, "id": "ws_test"})(),
        )
        _text, data = asyncio.run(analysis_run(
            {"recipe": "sum_values", "inputs": {"values": [2, 3, 4]}, "purpose": "sum"},
            ctx,
        ))
        assert data["status"] == "ok"
        assert data["outputs"]["sum"] == 9
    finally:
        memory.close()


def test_a_failed_contract_test_is_unverified_and_not_active(tmp_path: Path):
    if not _has_runner():
        pytest.skip("sandbox/interpreter unavailable")
    memory, store = _store(tmp_path)
    try:
        outcome = builder.build(_request(
            capabilityId="sum_values_fail",
            test='assert result["sum"] == 999\n',
        ), store=store, root=tmp_path)
        assert outcome["status"] == "unverified"
        assert outcome["activated"] is False
        assert outcome["verification"]["status"] == "failed"
        record = store.get("sum_values_fail", "1.0.0")
        assert record is not None and record["status"] == "unverified"
        assert get_recipe("sum_values_fail") is None
    finally:
        memory.close()


def test_no_contract_test_means_no_activation(tmp_path: Path):
    memory, store = _store(tmp_path)
    try:
        outcome = builder.build(_request(
            capabilityId="sum_values_untested", test="",
        ), store=store, root=tmp_path)
        assert outcome["status"] == "unverified"
        assert outcome["verification"]["status"] == "unverified"
        record = store.get("sum_values_untested", "1.0.0")
        assert record is not None and record["status"] == "unverified"
    finally:
        memory.close()


@pytest.mark.parametrize("implementation", [
    "import urllib.request\nresult = {}\n",
    'open("../outside.txt", "w")\nresult = {}\n',
    'open("python/harness/code/policy.py", "w")\nresult = {}\n',
])
def test_unsafe_generated_code_is_refused(tmp_path: Path, implementation: str):
    memory, store = _store(tmp_path)
    try:
        outcome = builder.build(_request(
            capabilityId="unsafe_capability", implementation=implementation,
        ), store=store, root=tmp_path)
        assert outcome["status"] == "unverified"
        checks = {item["name"]: item for item in outcome["verification"]["checks"]}
        assert any(
            not item["ok"] for item in checks.values()
        )
        assert get_recipe("unsafe_capability") is None
    finally:
        memory.close()


def test_a_global_recipe_waits_for_an_operator(tmp_path: Path):
    if not _has_runner():
        pytest.skip("sandbox/interpreter unavailable")
    memory, store = _store(tmp_path)
    try:
        outcome = builder.build(_request(
            capabilityId="sum_global", scope="global",
        ), store=store, root=tmp_path)
        assert outcome["status"] == "approval_required"
        assert outcome["activated"] is False
        assert outcome["requiresApproval"] is True
        assert get_recipe("sum_global") is None
    finally:
        memory.close()


def test_effectful_and_one_off_requests_do_not_build(tmp_path: Path):
    memory, store = _store(tmp_path)
    try:
        one_off = builder.build(_request(kind="one_off"), store=store, root=tmp_path)
        assert one_off["status"] == "one_off"
        tool = builder.build(
            _request(kind="tool", need="build a tool for my private ledger"),
            store=store, root=tmp_path,
        )
        assert tool["status"] == "handoff_required"
        assert tool["requiresApproval"] is True
        assert tool["nextTool"] == "create_goal"
        handoff = tool["handoff"]
        assert handoff["surface"] == "code_agent"
        assert handoff["activation"] == "operator"
    finally:
        memory.close()


def test_an_effectful_handoff_is_saved_on_the_request(tmp_path: Path):
    memory, store = _store(tmp_path)
    try:
        request = _request(
            kind="skill", need="from now on prepare a weekly review", acceptance=[],
        )
        store.save_request(request)
        outcome = builder.build(request, store=store, root=tmp_path)
        assert outcome["status"] == "handoff_required"
        assert outcome["nextTool"] == "skill_create"
        saved = store.get_request(request.request_id)
        assert saved is not None
        assert saved["status"] == "handoff_required"
        handoff = saved["payload"]["handoff"]
        assert handoff["surface"] == "skill_create"
        assert handoff["arguments"]["name"] == "prepare_weekly_review"
        assert any("instructions" in item for item in handoff["missing"])
    finally:
        memory.close()


def test_a_version_conflict_is_refused(tmp_path: Path):
    if not _has_runner():
        pytest.skip("sandbox/interpreter unavailable")
    memory, store = _store(tmp_path)
    try:
        first = builder.build(_request(), store=store, root=tmp_path)
        assert first["status"] == "active"
        second = builder.build(_request(
            version="1.0.0",
            implementation='result = {"sum": 0, "count": 0}\n',
        ), store=store, root=tmp_path)
        assert second["status"] == "refused"
        assert second["code"] == "VERSION_EXISTS"
    finally:
        memory.close()


def test_rollback_restores_the_previous_version(tmp_path: Path):
    if not _has_runner():
        pytest.skip("sandbox/interpreter unavailable")
    memory, store = _store(tmp_path)
    try:
        v1 = builder.build(_request(capabilityId="sum_rollback"), store=store, root=tmp_path)
        assert v1["status"] == "active"
        v2 = builder.build(_request(
            capabilityId="sum_rollback", version="1.0.1",
            implementation='values = inputs.get("values")\nresult = {"sum": sum(values) + 1, "count": len(values)}\n',
            test='assert result["sum"] == 7\nassert result["count"] == 3\n',
        ), store=store, root=tmp_path)
        assert v2["status"] == "active"
        assert store.get("sum_rollback", "1.0.0")["status"] == "disabled"

        outcome = builder.rollback("sum_rollback", None, store=store, root=tmp_path)
        assert outcome["status"] == "active"
        assert outcome["version"] == "1.0.0"
        assert store.get("sum_rollback", "1.0.0")["status"] == "active"
        assert store.get("sum_rollback", "1.0.1")["status"] == "disabled"
        refresh_generated_recipes(store, tmp_path)
        assert get_recipe("sum_rollback") is not None
    finally:
        memory.close()


def test_repeated_failures_disable_a_capability(tmp_path: Path):
    if not _has_runner():
        pytest.skip("sandbox/interpreter unavailable")
    memory, store = _store(tmp_path)
    try:
        outcome = builder.build(_request(capabilityId="sum_fragile"), store=store, root=tmp_path)
        assert outcome["status"] == "active"
        for _ in range(3):
            usage = store.record_usage("sum_fragile", "1.0.0", ok=False)
        assert usage["disabled"] is True
        assert store.get("sum_fragile", "1.0.0")["status"] == "disabled"
    finally:
        memory.close()


def test_a_verified_workspace_recipe_promotes_to_global(tmp_path: Path, monkeypatch):
    if not _has_runner():
        pytest.skip("sandbox/interpreter unavailable")
    from harness.capabilities import registry

    monkeypatch.setattr(registry, "_GLOBAL_DIR", tmp_path / "global")
    memory, store = _store(tmp_path)
    try:
        outcome = builder.build(_request(capabilityId="sum_promote"), store=store, root=tmp_path)
        assert outcome["status"] == "active"
        promoted = builder.promote("sum_promote", "1.0.0", store=store, root=tmp_path, operator=True)
        assert promoted["status"] == "global"
        assert promoted["scope"] == "global"
        destination = Path(promoted["dir"])
        assert destination.is_dir()
        manifest = json.loads((destination / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["scope"] == "global"
        assert (destination / "capability.py").is_file()
        record = store.get("sum_promote", "1.0.0")
        assert record["scope"] == "global"
        assert record["dir"] == str(destination)
        refresh_generated_recipes(store, tmp_path)
        assert get_recipe("sum_promote") is not None
        again = builder.promote("sum_promote", "1.0.0", store=store, root=tmp_path, operator=True)
        assert again.get("idempotent") is True
    finally:
        memory.close()


def test_promotion_needs_an_operator_and_a_passing_test(tmp_path: Path):
    memory, store = _store(tmp_path)
    try:
        missing = builder.promote("does_not_exist", None, store=store, root=tmp_path, operator=True)
        assert missing["status"] == "not_found"
        manifest = CapabilityManifest(
            id="x_recipe", kind="recipe", title="x recipe",
            description="a recipe used by the promotion guard test",
            inputs=[CapabilityPort(name="values", kind="series")],
            tests=["test_capability.py"],
        )
        store.save_record(CapabilityRecord(
            capability_id="x_recipe", version="1.0.0", kind="recipe",
            title=manifest.title, description=manifest.description,
            scope="workspace", status="unverified", manifest=manifest.to_dict(),
            test_status="failed",
            directory=str(tmp_path / ".black-eclipse" / "capabilities" / "x_recipe" / "1.0.0"),
        ))
        guarded = builder.promote("x_recipe", "1.0.0", store=store, root=tmp_path)
        assert guarded["status"] == "approval_required"
        unverified = builder.promote("x_recipe", "1.0.0", store=store, root=tmp_path, operator=True)
        assert unverified["status"] == "unverified"
    finally:
        memory.close()
