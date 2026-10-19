"""Round 4 (W5/W9 remainder): REAL install handlers on the acquisition lifecycle.

`test_recovery_acquire_handlers.py` pins the build route; these tests pin the
install/enable half: an operator-supplied FACT (a GitHub source, a plugin
folder, a kit id) resolves which EXISTING gate a step names, a skill install
still consumes its own single-use digest-bound approval, a plugin install runs
through the ONE plugin platform with the operator flag, a kit becomes a durable
code task whose verified completion is the validation, and none of it
self-grants. Without a fact the step keeps handing back the exact missing
information.
"""

from __future__ import annotations

import types

import pytest

from harness.mcp.approvals import ApprovalStore
from harness.persistence import AgentMemoryStore
from harness.recovery.acquire_handlers import build_acquisition_handlers, proposal_from_dict
from harness.recovery.acquisition import AcquisitionStep, propose
from harness.recovery.discovery import CapabilityIndex
from harness.skills.install import source_digest, parse_source
from harness.tasks.manager import TaskManager
from harness.tasks.model import BlockedReason, CreatePlanInput, CreateTaskInput, TaskStatus
from harness.tasks.store import TaskStore


@pytest.fixture()
def manager(tmp_path):
    return TaskManager(TaskStore(AgentMemoryStore(str(tmp_path / "agent-memory.db"))))


@pytest.fixture()
def approvals(tmp_path):
    return ApprovalStore(AgentMemoryStore(str(tmp_path / "agent-memory.db")))


def _started_task(manager, *, title="collect sector filings"):
    plan = manager.create_plan(CreatePlanInput(name="goal", objective=title))
    task = manager.create_task(CreateTaskInput(
        title=title, plan_id=plan.id, objective=title,
        acceptance_criteria=[{"text": "the dataset is collected"}],
    ))
    manager.start_plan(plan.id)
    manager.start_task(task.id)
    return plan, task


def _install_step(surface="operator") -> AcquisitionStep:
    return AcquisitionStep(
        action="install", description="install it", capability_id=None,
        requires_approval=True, surface=surface, ready=False, reason="r",
        missing=("unknown: no source, credential or dependency was supplied",),
    )


# ── the plan names the surface a supplied fact resolves to ──────────────────


def test_facts_resolve_the_install_surface_without_granting():
    index = CapabilityIndex()
    by_facts = {
        None: "operator",
        "source": "skill",
        "pluginPath": "plugin",
        "kitId": "scaffold_kit",
    }
    for key, surface in by_facts.items():
        facts = None if key is None else {key: "x"}
        proposal = propose("need something new", index, facts=facts)
        install = next(step for step in proposal.steps if step.action == "install")
        assert install.surface == surface, (key, install.surface)
        # Whatever the surface, the step is still a mutation that needs approval.
        assert install.requires_approval is True
        assert install.ready is False


def test_no_fact_keeps_the_exact_missing_information():
    proposal = propose("need something new", CapabilityIndex())
    install = next(step for step in proposal.steps if step.action == "install")
    assert install.surface == "operator"
    assert any("no source" in gap for gap in proposal.gaps)


# ── skill install: the single-use, digest-bound approval is the gate ────────


def test_a_skill_install_consumes_a_granted_approval_and_installs_once(
    manager, approvals, monkeypatch,
):
    import harness.skills.install as install_module

    calls: list[tuple] = []

    def fake_install(store, source, **kwargs):
        calls.append((store, source.canonical, tuple(sorted(kwargs))))
        return {"ok": True, "source": source.canonical, "installed": ["user.demo"],
                "skipped": [], "unknownTools": {}, "notices": []}

    monkeypatch.setattr(install_module, "install_from_github", fake_install)
    plan, task = _started_task(manager)
    facts = {"source": "https://github.com/acme/skills", "subpath": "finance"}
    service = types.SimpleNamespace(memory_store=object(), approvals=approvals,
                                    skill_registry=None, ui=None)
    handlers = build_acquisition_handlers(service, manager, task, facts=facts)

    # Without a granted approval: the request is created and NOTHING installs.
    first = handlers["install"](_install_step("skill"))
    assert first["status"] == "approval_required"
    assert first["approvalId"]
    assert calls == []
    pending = approvals.list_kind("skill_install", status="pending")
    assert [row["id"] for row in pending] == [first["approvalId"]]

    # The operator approves the exact digest the service asked about.
    expected_digest = source_digest(parse_source("https://github.com/acme/skills",
                                                 subpath="finance"))
    assert pending[0]["argsDigest"] == expected_digest
    approvals.decide(first["approvalId"], approve=True)

    second = handlers["install"](_install_step("skill"))
    assert second["status"] == "installed"
    assert second["installed"] == ["user.demo"]
    assert len(calls) == 1
    # Single-use: the same approval cannot install a second time.
    third = handlers["install"](_install_step("skill"))
    assert third["status"] == "approval_required"
    assert len(calls) == 1


def test_a_denied_skill_install_never_installs(manager, approvals, monkeypatch):
    import harness.skills.install as install_module

    monkeypatch.setattr(
        install_module, "install_from_github",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not install")),
    )
    plan, task = _started_task(manager)
    service = types.SimpleNamespace(memory_store=object(), approvals=approvals, ui=None)
    handlers = build_acquisition_handlers(
        service, manager, task, facts={"source": "https://github.com/acme/skills"},
    )
    first = handlers["install"](_install_step("skill"))
    approvals.decide(first["approvalId"], approve=False)
    second = handlers["install"](_install_step("skill"))
    assert second["status"] == "approval_required"  # a denial is terminal for the digest


# ── plugin install / enable: the ONE plugin platform, operator-flagged ──────


def test_a_plugin_install_runs_through_the_platform_with_operator_truth(manager):
    recorded: list[dict] = []

    class _Plugins:
        async def install(self, source, **kwargs):
            recorded.append({"source": source, **kwargs})
            return {"ok": True, "plugin": {"id": "acme.tools", "enabled": False}}

        async def enable(self, plugin_id, **kwargs):
            recorded.append({"enable": plugin_id, **kwargs})
            return {"ok": True, "plugin": {"id": plugin_id, "enabled": True}}

    plan, task = _started_task(manager)
    service = types.SimpleNamespace(plugins=_Plugins(), ui=None)
    handlers = build_acquisition_handlers(
        service, manager, task, facts={"pluginPath": "/tmp/acme-plugin"},
    )
    out = handlers["install"](_install_step("plugin"))
    assert out["status"] == "installed"
    assert out["pluginId"] == "acme.tools"
    assert out["enabled"] is False  # install never self-enables
    assert recorded == [{"source": "/tmp/acme-plugin", "operator": True, "enable": False}]

    # Enable is its own operator step, by plugin id only.
    enable_handlers = build_acquisition_handlers(
        service, manager, task, facts={"pluginId": "acme.tools"},
    )
    enabled = enable_handlers["enable"](_install_step("plugin"))
    assert enabled["status"] == "enabled"
    assert recorded[-1] == {"enable": "acme.tools", "operator": True}


def test_an_enable_step_without_a_named_capability_stays_an_operator_decision(manager):
    plan, task = _started_task(manager)
    handlers = build_acquisition_handlers(types.SimpleNamespace(ui=None), manager, task)
    out = handlers["enable"](_install_step("existing_tool"))
    assert out["status"] == "approval_required"
    assert "operator must enable" in out["next"]


# ── kit facts: a durable code task whose completion is the validation ───────


def test_kit_facts_route_to_a_durable_code_task(manager):
    plan, task = _started_task(manager)
    handlers = build_acquisition_handlers(
        types.SimpleNamespace(ui=None), manager, task, facts={"kitId": "duckdb.ingest"},
    )
    out = handlers["install"](_install_step("scaffold_kit"))
    assert out["status"] == "pending"
    assert out["resume"] == "dependency"
    capability = manager.get_task(out["taskId"])
    assert capability.assigned_agent_id == "code-agent"
    assert capability.plan_id == task.plan_id
    criteria = manager.list_criteria(capability.id)
    assert any("duckdb.ingest" in criterion.text for criterion in criteria)


# ── the operator route parks the task for the missing approval ──────────────


def test_the_route_parks_for_the_pending_skill_approval(manager, approvals, tmp_path, monkeypatch):
    from harness.eclipse_memory.store import EclipseMemoryStore
    from harness.recovery.service import RecoveryService
    from harness.routers import recovery as recovery_router

    plan_, task = _started_task(manager)
    engine = RecoveryService(
        EclipseMemoryStore(str(tmp_path / "eclipse-memory.db")),
        capability_index=CapabilityIndex(),
    )
    recorded = engine.record_failure(
        code="UI_CAPABILITY_GAP",
        message="no registered component matches: collect sector filings",
        subsystem="ui", task_id=task.id,
    )
    incident_id = recorded["incidentId"]
    monkeypatch.setattr(
        recovery_router, "service",
        types.SimpleNamespace(recovery=engine, tasks=manager, ui=None,
                              approvals=approvals, memory_store=object()),
    )
    import harness.skills.install as install_module

    monkeypatch.setattr(install_module, "install_from_github",
                        lambda *a, **k: {"ok": True, "source": "x", "installed": ["user.demo"],
                                         "skipped": [], "unknownTools": {}, "notices": []})

    plan = recovery_router.plan_incident_acquisition(incident_id)
    steps = plan["acquisition"]["steps"]
    install_index = next(i for i, step in enumerate(steps) if step["action"] == "install")

    # Approved in principle, but the single-use install approval is not granted:
    # the outcome is honest (it names the real surface), the task parks ASKING_USER
    # and nothing installed.
    first = recovery_router.execute_incident_acquisition(
        incident_id,
        {"stepIndex": install_index, "approved": True,
         "facts": {"source": "https://github.com/acme/skills"}},
    )
    assert first["success"] is False
    assert first["outcome"]["step"]["surface"] == "skill"
    assert first["outcome"]["result"]["status"] == "approval_required"
    assert first["parked"]["resume"] == "operator"
    live = manager.get_task(task.id)
    assert live.status == TaskStatus.ASKING_USER

    # The operator grants the digest-bound approval; the step now installs.
    approval_id = first["outcome"]["result"]["approvalId"]
    approvals.decide(approval_id, approve=True)
    second = recovery_router.execute_incident_acquisition(
        incident_id,
        {"stepIndex": install_index, "approved": True,
         "facts": {"source": "https://github.com/acme/skills"}},
    )
    assert second["success"] is True
    assert second["outcome"]["result"]["status"] == "installed"
    assert second["outcome"]["result"]["installed"] == ["user.demo"]


def test_build_step_proposal_round_trip_keeps_working(manager):
    """The existing caller contract is unchanged (guards against regressions)."""
    plan, task = _started_task(manager)
    proposal = proposal_from_dict({
        "stop": True,
        "acquisition": {
            "query": "q", "steps": [{
                "action": "build", "description": "d", "capabilityId": None,
                "requiresApproval": True, "surface": "engineering", "ready": False,
                "reason": "r", "missing": [],
            }],
        },
    })
    handlers = build_acquisition_handlers(types.SimpleNamespace(ui=None), manager, task)
    out = handlers["build"](proposal.steps[0])
    assert out["surface"] == "code_task"
    assert out["resume"] == "dependency"
