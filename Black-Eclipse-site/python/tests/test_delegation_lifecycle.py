"""W7 durable delegation store + async lifecycle + schema repair."""

from __future__ import annotations

import asyncio

import pytest

from harness.delegation import DelegationChild, DelegationRequest
from harness.delegation_lifecycle import (
    execute_job,
    get_status,
    mark_inbox_consumed,
    peek_inbox,
    remember_model_settings,
    submit_batch,
    typed_outcome,
)
from harness.delegation_repair import repair_prompt, schema_error, validate_output
from harness.delegation_store import DelegationStore
from harness.persistence import AgentMemoryStore
from harness.schemas import ModelSettings


def _store(tmp_path) -> AgentMemoryStore:
    return AgentMemoryStore(str(tmp_path / "agent-memory.db"))


def _request(children: list[DelegationChild]) -> DelegationRequest:
    return DelegationRequest(children=children, token_budget=120_000)


class _FakeResult:
    def __init__(self, output: str, status: str = "completed", tokens: int = 10) -> None:
        self._output = output
        self._status = status
        self._tokens = tokens

    def model_dump(self) -> dict:
        return {
            "runId": "child_run", "status": self._status, "output": self._output,
            "error": None, "totalTokens": self._tokens,
        }


class _FakeService:
    def __init__(self, store, outputs: list[str]) -> None:
        self.store = store
        self.bus = None
        self._outputs = list(outputs)
        self.requests = []

    async def run(self, request):
        self.requests.append(request)
        output = self._outputs.pop(0) if self._outputs else "{}"
        return _FakeResult(output)


class _FakeFabric:
    def __init__(self) -> None:
        self.submitted = []

    async def submit(self, job_type, payload, **kwargs):
        self.submitted.append((job_type, payload, kwargs))
        return {"jobId": f"job_{len(self.submitted)}", "status": "QUEUED"}


class _Job:
    def __init__(self, payload: dict) -> None:
        self.input = payload
        self.id = "job_1"
        self.agent_id = None


class _WorkerCtx:
    def __init__(self, payload: dict) -> None:
        self.job = _Job(payload)


def test_store_is_idempotent_on_terminal(tmp_path):
    store = _store(tmp_path)
    db = DelegationStore(store)
    db.create_batch(
        delegation_id="dlg_1", parent_run_id="run_parent", parent_agent_id="a",
        children=[DelegationChild(goal="one"), DelegationChild(goal="two")],
        strategy="split", aggregate="list", title=None, token_budget=1000,
    )
    assert db.complete("dlg_1", 0, status="completed", raw_summary="ok") is True
    assert db.complete("dlg_1", 0, status="failed", reason="late") is False
    batch = db.get("dlg_1")
    assert batch["children"][0]["status"] == "completed"
    assert batch["children"][1]["status"] == "queued"


def test_steer_mailbox_caps_and_consumes(tmp_path):
    store = _store(tmp_path)
    db = DelegationStore(store)
    db.create_batch(
        delegation_id="dlg_s", parent_run_id="run", parent_agent_id=None,
        children=[DelegationChild(goal="one")], strategy="split", aggregate="list",
        title=None, token_budget=1000,
    )
    for i in range(4):
        assert db.append_steer("dlg_s", f"m{i}") == i + 1
    with pytest.raises(ValueError):
        db.append_steer("dlg_s", "too many")
    assert [s["seq"] for s in db.peek_steers("dlg_s")] == [1, 2, 3, 4]
    db.consume_steers("dlg_s", [1, 2])
    assert [s["seq"] for s in db.peek_steers("dlg_s")] == [3, 4]


def test_submit_batch_persists_and_submits(tmp_path, monkeypatch):
    store = _store(tmp_path)
    fabric = _FakeFabric()
    monkeypatch.setattr("harness.fabric.tools.get_fabric_manager", lambda: fabric)
    result = asyncio.run(submit_batch(
        _request([DelegationChild(goal="research one"), DelegationChild(goal="research two")]),
        store=store, parent_run_id="run_parent", parent_agent_id="eclipse-agent",
        parent_allowed={"workspace_read"}, depth=0, parent_workspace_id=None,
        user_id="u1", session_id="s1",
        model_settings=ModelSettings(provider="ollama", model="llama3.1"),
    ))
    assert result["delegationId"].startswith("dlg_")
    assert [c["jobId"] for c in result["children"]] == ["job_1", "job_2"]
    assert fabric.submitted[0][1]["allowedTools"] == ["workspace_read"]
    # A credential never reaches the durable payload.
    assert "api_key" not in fabric.submitted[0][1].get("modelMetadata", {})
    batch = get_status(store, delegation_id=result["delegationId"])
    assert batch["children"][0]["status"] == "queued"


def test_schema_validation_and_repair_prompt():
    schema = {"type": "object", "required": ["answer"], "properties": {"answer": {"type": "string"}}}
    assert validate_output('{"answer": "ok"}', schema)["valid"] is True
    assert validate_output("not json", schema)["valid"] is False
    assert schema_error({"$ref": "https://example.com/s.json"}) is not None
    prompt = repair_prompt(schema, "bad", ["answer: required"])
    assert "Return ONLY corrected JSON" in prompt


def test_execute_job_repairs_once_then_persists(tmp_path, monkeypatch):
    store = _store(tmp_path)
    db = DelegationStore(store)
    db.create_batch(
        delegation_id="dlg_job", parent_run_id="run_parent", parent_agent_id="eclipse-agent",
        children=[DelegationChild(
            goal="structured",
            output_schema={"type": "object", "required": ["answer"],
                           "properties": {"answer": {"type": "string"}}},
        )],
        strategy="split", aggregate="list", title=None, token_budget=50_000,
    )
    remember_model_settings("dlg_job", ModelSettings(provider="ollama", model="llama3.1"))
    service = _FakeService(store, ["no json", '{"answer": "fixed"}'])
    payload = {
        "delegationId": "dlg_job", "childIndex": 0, "parentRunId": "run_parent",
        "parentAgentId": "eclipse-agent", "depth": 0,
        "child": DelegationChild(
            goal="structured",
            output_schema={"type": "object", "required": ["answer"],
                           "properties": {"answer": {"type": "string"}}},
        ).model_dump(by_alias=True),
        "allowedTools": ["workspace_read"], "tokenBudget": 50_000,
    }
    outcome = asyncio.run(execute_job(service, _WorkerCtx(payload)))
    assert outcome.status == "succeeded"
    assert len(service.requests) == 2  # child + one repair
    batch = db.get("dlg_job")
    child = batch["children"][0]
    assert child["schemaValid"] is True
    assert child["summary"] == '{"answer": "fixed"}'
    assert child["rawSummary"] == "no json"


def test_async_tools_register_and_flag_off_refuses(tmp_path, monkeypatch):
    from harness.code.tools import register_code_tools
    from harness.delegation_async_tools import delegate_async_handler
    from harness.tools import ToolContext, ToolRegistry

    registry = ToolRegistry()
    register_code_tools(registry)
    for name in (
        "delegate_async", "delegate_status", "delegate_result",
        "delegate_cancel", "delegate_steer", "delegate_wait",
        "checkpoint_list", "checkpoint_diff", "checkpoint_restore",
    ):
        assert registry.get(name) is not None, name
    monkeypatch.setenv("HARNESS_ASYNC_DELEGATION", "off")
    ctx = ToolContext(
        run_id="run_parent", log=lambda *_: None,
        model_settings=ModelSettings(provider="ollama", model="llama3.1"),
        tool_registry=ToolRegistry(), data_bridge=object(),
        memory_store=_store(tmp_path), allowed={"workspace_read"},
    )
    text, data = asyncio.run(delegate_async_handler(
        {"children": [{"goal": "one"}]}, ctx,
    ))
    assert data["status"] == "refused"


def test_async_tools_submit_when_enabled(tmp_path, monkeypatch):
    from harness.delegation_async_tools import delegate_async_handler
    from harness.tools import ToolContext, ToolRegistry

    store = _store(tmp_path)
    fabric = _FakeFabric()
    monkeypatch.setenv("HARNESS_ASYNC_DELEGATION", "on")
    monkeypatch.setattr("harness.fabric.tools.get_fabric_manager", lambda: fabric)
    ctx = ToolContext(
        run_id="run_parent", log=lambda *_: None,
        model_settings=ModelSettings(provider="ollama", model="llama3.1"),
        tool_registry=ToolRegistry(), data_bridge=object(),
        memory_store=store, allowed={"workspace_read"},
        agent=None,
    )
    text, data = asyncio.run(delegate_async_handler(
        {"children": [{"goal": "one"}, {"goal": "two"}]}, ctx,
    ))
    assert data["status"] == "queued"
    assert len(data["children"]) == 2
    assert all(c["jobId"] for c in data["children"])


def test_narrowing_never_widens_and_non_isolated_has_no_writes():
    from harness.delegation_lifecycle import _narrowed_agent
    from harness.code.policy import WRITE_TOOLS

    payload = {
        "parentAgentId": "eclipse-agent",
        "allowedTools": ["workspace_read", "write_file", "shell_run"],
        "tokenBudget": 20_000,
    }
    read_only = _narrowed_agent(payload, DelegationChild(goal="research"))
    assert "write_file" not in (read_only.tools or [])
    assert "shell_run" not in (read_only.tools or [])
    # An isolated child may keep a write tool it was already granted. The
    # default research agent does not declare one, so use the code agent.
    isolated = _narrowed_agent(
        {**payload, "parentAgentId": "code-agent", "allowedTools": ["workspace_read", "write_file"]},
        DelegationChild(goal="edit", isolated=True),
    )
    assert "write_file" in (isolated.tools or [])
    # A tool the parent did not hold is never added.
    forged = _narrowed_agent({**payload, "allowedTools": ["workspace_read"]},
                             DelegationChild(goal="edit", isolated=True))
    assert not set(forged.tools or []) & set(WRITE_TOOLS)


def test_fabric_registers_a_delegation_worker():
    from harness.fabric.builtin_workers import build_default_workers

    class _Service:
        pass

    workers = build_default_workers(_Service())
    assert any(w.kind == "delegation" for w in workers)
    policy = __import__("harness.fabric.policies", fromlist=["DEFAULT_POLICIES"]).DEFAULT_POLICIES["delegation"]
    assert policy.worker_kind == "delegation"
    assert policy.durable is True


def test_inbox_is_bounded_and_consumed(tmp_path):
    store = _store(tmp_path)
    db = DelegationStore(store)
    db.create_batch(
        delegation_id="dlg_i", parent_run_id="run_parent", parent_agent_id=None,
        children=[DelegationChild(goal="one")], strategy="split", aggregate="list",
        title=None, token_budget=1000,
    )
    db.complete("dlg_i", 0, status="completed", raw_summary="done")
    text, keys = peek_inbox(store, "run_parent")
    assert "part 1: completed" in text
    assert keys == [("dlg_i", 0)]
    mark_inbox_consumed(store, keys)
    assert peek_inbox(store, "run_parent") == ("", [])
    typed = typed_outcome(db.get("dlg_i")["children"][0])
    assert typed.status == "completed"
