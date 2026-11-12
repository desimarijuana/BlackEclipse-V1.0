"""C5: one spawn primitive over the Fabric, evidence propagation, synthesis."""

from __future__ import annotations

import os
import tempfile

import pytest

from harness.fabric import tools as fabric_tools
from harness.goals import EvidenceLedger, handle
from harness.persistence import AgentMemoryStore
from harness.run_lineage import RunLineage
from harness.spawn import (
    ChildOutcome,
    SpawnBudget,
    SpawnSpec,
    reconcile_budget,
    spawn_child,
    spawn_many,
    synthesize,
)
from harness.spawn.service import spec_from_dict
from harness.tools import ToolContext


class FakeFabric:
    def __init__(self, store, child_run="child_run", status="SUCCEEDED", claims=True):
        self.store = store
        self.child_run = child_run
        self.status = status
        self.claims = claims
        self.calls: list[dict] = []

    async def submit(self, job_type, payload, **kwargs):
        self.calls.append({"jobType": job_type, "payload": payload, **kwargs})
        if self.claims:
            self.store.create_run(self.child_run, "eclipse-agent", {"query": "child"})
            RunLineage(self.store).set_run_parent(self.child_run, payload["parentRunId"])
            EvidenceLedger(self.store).record(
                run_id=self.child_run, text="AAPL returned 18.4%",
                handles=[handle("computation", "calc_child")], status="supported",
            )
        return {
            "status": self.status, "jobId": "job_child", "output": "child answer",
            "outcome": {"metrics": {"runId": self.child_run, "totalTokens": 321}},
        }


@pytest.fixture()
def store():
    directory = tempfile.mkdtemp(prefix="be-spawn-")
    s = AgentMemoryStore(os.path.join(directory, "agent-memory.db"))
    s.create_run("parent", "eclipse-agent", {"query": "parent"})
    yield s
    s.close()


def _ctx(store, run_id="parent") -> ToolContext:
    return ToolContext(run_id=run_id, log=lambda *_: None, memory_store=store)


def test_a_child_is_one_fabric_agent_job_with_a_budget(store, monkeypatch):
    fabric = FakeFabric(store)
    monkeypatch.setattr(fabric_tools, "get_fabric_manager", lambda: fabric)
    spec = SpawnSpec("check AAPL", budget=SpawnBudget(tokens=5_000, steps=4, timeout_s=120))
    outcome = asyncio_run(spawn_child(spec, _ctx(store)))

    assert outcome.status == "completed"
    assert outcome.run_id == "child_run"
    call = fabric.calls[0]
    assert call["jobType"] == "agent"
    assert call["worker_kind"] == "agent"
    assert call["payload"]["parentRunId"] == "parent"
    assert call["payload"]["maxSteps"] == 4
    assert call["payload"]["runTimeoutMs"] == 120_000
    assert call["await_result"] is True


def asyncio_run(coro):
    import asyncio

    return asyncio.run(coro)


def test_child_claims_are_copied_into_the_parent_ledger(store, monkeypatch):
    fabric = FakeFabric(store)
    monkeypatch.setattr(fabric_tools, "get_fabric_manager", lambda: fabric)
    outcome = asyncio_run(spawn_child(SpawnSpec("check AAPL"), _ctx(store)))
    assert outcome.claims
    parent_claims = EvidenceLedger(store).claims("parent")
    assert any(claim.verifier == "child:child_run" for claim in parent_claims)
    assert any(claim.status == "supported" for claim in parent_claims)


def test_a_background_spawn_returns_the_job(store, monkeypatch):
    fabric = FakeFabric(store)
    monkeypatch.setattr(fabric_tools, "get_fabric_manager", lambda: fabric)
    outcome = asyncio_run(spawn_child(SpawnSpec("check", background=True), _ctx(store)))
    assert outcome.status == "queued"
    assert outcome.job_id == "job_child"
    assert fabric.calls[0]["await_result"] is False


def test_depth_two_is_the_limit(store, monkeypatch):
    store.create_run("a", "eclipse-agent", {"query": "a"})
    store.create_run("b", "eclipse-agent", {"query": "b"})
    RunLineage(store).set_run_parent("a", "parent")
    RunLineage(store).set_run_parent("b", "a")
    fabric = FakeFabric(store)
    monkeypatch.setattr(fabric_tools, "get_fabric_manager", lambda: fabric)
    outcome = asyncio_run(spawn_child(SpawnSpec("too deep"), _ctx(store, "b")))
    assert outcome.status == "refused"
    assert outcome.error_class == "DEPTH_EXCEEDED"
    assert fabric.calls == []


def test_spawn_many_is_capped_at_four(store, monkeypatch):
    fabric = FakeFabric(store)
    monkeypatch.setattr(fabric_tools, "get_fabric_manager", lambda: fabric)
    outcomes = asyncio_run(spawn_many([SpawnSpec(f"task {i}") for i in range(5)], _ctx(store)))
    assert len(outcomes) == 1
    assert outcomes[0].status == "refused"


class MultiFabric:
    """Completes each child with a unique run id and a fixed token usage."""

    def __init__(self, store) -> None:
        self.store = store
        self.calls: list[dict] = []

    async def submit(self, job_type, payload, **kwargs):
        index = len(self.calls)
        self.calls.append({"jobType": job_type, "payload": payload, **kwargs})
        run_id = f"child_{index}"
        self.store.create_run(run_id, payload.get("agentId") or "eclipse-agent", {"query": "x"})
        RunLineage(self.store).set_run_parent(run_id, payload.get("parentRunId") or "")
        return {
            "status": "SUCCEEDED", "jobId": f"job_{index}", "output": f"answer {index}",
            "outcome": {"metrics": {"runId": run_id, "totalTokens": 10}},
        }


def test_eight_children_fanout_and_nine_are_refused(store, monkeypatch):
    fabric = MultiFabric(store)
    monkeypatch.setattr(fabric_tools, "get_fabric_manager", lambda: fabric)
    specs = [SpawnSpec(f"task {i}", budget=SpawnBudget(tokens=10_000)) for i in range(8)]

    outcomes = asyncio_run(spawn_many(specs, _ctx(store)))
    assert len(outcomes) == 8
    assert all(o.status == "completed" for o in outcomes)
    assert len(fabric.calls) == 8

    budgets = reconcile_budget(specs, outcomes)
    assert budgets["allocated"] == 80_000
    assert budgets["used"] == 80
    assert budgets["returned"] == 79_920

    refused = asyncio_run(spawn_many(specs + [SpawnSpec("one too many")], _ctx(store)))
    assert len(refused) == 1
    assert refused[0].error_class == "CHILD_LIMIT"


def test_budget_reconciles_to_used_plus_returned():
    specs = [
        SpawnSpec("a", budget=SpawnBudget(tokens=1_000)),
        SpawnSpec("b", budget=SpawnBudget(tokens=2_000)),
    ]
    outcomes = [
        ChildOutcome(status="completed", tokens_used=30),
        ChildOutcome(status="completed", tokens_used=20),
    ]
    report = reconcile_budget(specs, outcomes)
    assert report["allocated"] == 3_000
    assert report["used"] == 50
    assert report["returned"] == 2_950
    assert report["allocated"] == report["used"] + report["returned"]


def test_a_child_cannot_inherit_operator_or_autonomy(store, monkeypatch):
    from types import SimpleNamespace

    fabric = FakeFabric(store)
    monkeypatch.setattr(fabric_tools, "get_fabric_manager", lambda: fabric)
    ctx = SimpleNamespace(
        run_id="parent", memory_store=store, operator=True,
        user_id="user_1", workspace_id="ws_1", session_id="sess_1",
    )
    asyncio_run(spawn_child(SpawnSpec("check AAPL"), ctx))
    payload = fabric.calls[0]["payload"]
    assert "operator" not in payload
    assert "autonomy" not in payload
    assert payload["userId"] == "user_1"
    assert payload["workspaceId"] == "ws_1"


def test_the_child_token_allocations_cannot_exceed_the_parent_pool(store, monkeypatch):
    fabric = FakeFabric(store)
    monkeypatch.setattr(fabric_tools, "get_fabric_manager", lambda: fabric)
    specs = [SpawnSpec(f"task {i}", budget=SpawnBudget(tokens=60_000)) for i in range(3)]
    outcomes = asyncio_run(spawn_many(specs, _ctx(store)))
    assert outcomes[0].status == "refused"
    assert outcomes[0].error_class == "BUDGET_EXCEEDED"
    assert fabric.calls == []


def test_budget_and_spec_are_clamped():
    spec = spec_from_dict({"objective": "x", "budget": {"tokens": 10**9, "steps": 999, "timeout_s": 10**9}})
    assert spec.budget.tokens == 120_000
    assert spec.budget.steps == 24
    assert spec.budget.timeout_s == 900


def test_synthesis_dedupes_and_flags_conflicts():
    def claim(text, ref, status="supported"):
        return {"text": text, "status": status, "handles": [{"kind": "computation", "ref": ref}]}

    a = ChildOutcome(status="completed", run_id="r1", claims=[claim("drawdown is 12.4%", "calc_1")])
    b = ChildOutcome(status="completed", run_id="r2", claims=[claim("drawdown is 12.4%", "calc_1")])
    c = ChildOutcome(status="completed", run_id="r3", claims=[claim("drawdown is 12.4%", "calc_2")])

    result = synthesize([a, b])
    assert len(result["supported"]) == 1
    assert result["conflicts"] == []

    conflict = synthesize([a, c])
    assert len(conflict["conflicts"]) == 1
    assert "disagree" in conflict["conflicts"][0]["reason"]


def test_a_verifier_rejection_is_dropped_not_merged():
    rejected = ChildOutcome(
        status="completed", run_id="r1",
        claims=[{"text": "x", "status": "unsupported", "handles": [{"kind": "run", "ref": "r1"}]}],
    )
    result = synthesize([rejected])
    assert result["supported"] == []
    assert result["dropped"]
