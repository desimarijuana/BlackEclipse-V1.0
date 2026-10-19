"""Round 4 (W5/W9) — capability acquisition lifecycle.

Discovery proposes; this test proves the plan names its surface and missing facts,
mutations require approval, validation is never assumed, and the executor STOPS
with the plan instead of repeating the same failed call.
"""

from __future__ import annotations

import asyncio

from harness.eclipse_memory.store import EclipseMemoryStore
from harness.recovery.acquisition import (
    default_strategy_handlers,
    execute_step,
    propose,
    retry_task,
    validate_step,
)
from harness.recovery.discovery import CapabilityDescriptor, CapabilityIndex
from harness.recovery.envelope import ActionClass, AutonomyEnvelope
from harness.recovery.execution import TaskRunFailed, run_with_recovery
from harness.recovery.executor import recover_operation
from harness.recovery.service import RecoveryService


def _index() -> CapabilityIndex:
    return CapabilityIndex(sources=[lambda: [
        CapabilityDescriptor(
            id="market_get_quote", kind="tool",
            description="quote prices for a symbol", available=True,
        ),
        CapabilityDescriptor(
            id="market_get_crypto", kind="tool",
            description="crypto market data and order books", available=False,
        ),
    ]])


def _service(tmp_path) -> RecoveryService:
    service = RecoveryService(EclipseMemoryStore(str(tmp_path / "eclipse-memory.db")))
    service.capability_index = _index()
    return service


def _run(coro):
    return asyncio.run(coro)


def test_an_available_capability_is_a_ready_use_step():
    proposal = propose("quote prices", _index())
    assert proposal.resolved_by == "market_get_quote"
    first = proposal.steps[0]
    assert first.action == "use"
    assert first.surface == "existing_tool"
    assert first.ready is True
    assert first.requires_approval is False
    assert proposal.requires_approval is False


def test_an_unavailable_capability_is_an_approval_flagged_enable():
    proposal = propose("crypto market data", _index())
    first = proposal.steps[0]
    assert first.capability_id == "market_get_crypto"
    assert first.action == "enable"
    assert first.ready is False
    assert first.requires_approval is True
    assert proposal.requires_approval is True


def test_an_absent_capability_names_surfaces_and_missing_facts():
    proposal = propose("a world clock widget", _index())
    actions = [step.action for step in proposal.steps]
    assert actions[:3] == ["install", "build", "alternative"]
    install, build, alternative = proposal.steps[:3]
    assert install.surface == "operator" and install.requires_approval
    assert "unknown" in " ".join(install.missing)
    assert build.surface == "engineering" and build.requires_approval
    assert alternative.surface == "alternative" and alternative.ready
    assert proposal.requires_approval is True


def test_execute_requires_approval_for_a_mutation():
    proposal = propose("a world clock widget", _index())
    install = proposal.steps[0]
    refused = execute_step(proposal, 0)
    assert refused["status"] == "approval_required"
    no_handler = execute_step(proposal, 0, approved=True)
    assert no_handler["status"] == "requires_caller"
    assert no_handler["step"]["surface"] == install.surface
    executed = execute_step(
        proposal, 0, approved=True,
        handlers={"install": lambda step: {"installed": step.capability_id}},
    )
    assert executed["status"] == "executed"


def test_a_read_only_step_needs_no_handler():
    proposal = propose("quote prices", _index())
    assert execute_step(proposal, 0)["status"] == "ready"


def test_validation_is_never_assumed():
    assert validate_step({"status": "executed"})["status"] == "unverified"
    assert validate_step({"status": "executed"}, verifier=lambda _r: True)["status"] == "verified"
    assert validate_step({"status": "executed"}, verifier=lambda _r: False)["status"] == "failed"


def test_retry_requires_the_original_task():
    proposal = propose("quote prices", _index())
    missing = retry_task(proposal)
    assert missing["status"] == "requires_caller"
    resumed = retry_task(proposal, resume=lambda: {"taskId": "t1", "resumed": True})
    assert resumed["status"] == "resumed"


def test_the_capability_handlers_hand_back_a_plan_and_stop():
    handlers = default_strategy_handlers("quote prices", _index())
    result = handlers["alternative_implementation"]({})
    assert result["stop"] is True
    assert result["acquisition"]["resolvedBy"] == "market_get_quote"


def test_the_executor_stops_with_the_acquisition_plan(tmp_path):
    service = _service(tmp_path)

    async def op():
        raise RuntimeError("ModuleNotFoundError: no module named 'clock'")

    async def fix(_decision):
        return {"stop": True, "acquisition": {"query": "clock", "steps": [{"action": "build"}]}}

    envelope = AutonomyEnvelope(
        action_classes=frozenset({ActionClass.FIX_DEPENDENCY}),
        require_reversible=False, risk_ceiling="high",
    )
    result = _run(recover_operation(
        service, op, subsystem="execution", source="tool", task_id="t1",
        max_attempts=2, sleep=lambda _s: asyncio.sleep(0),
        strategy_handlers={"fix_dependency": fix}, envelope=envelope,
    ))
    assert result.ok is False
    assert result.stopped_reason == "acquisition_required"
    assert result.value["acquisition"]["query"] == "clock"


def test_run_with_recovery_wires_the_default_acquisition_handler(tmp_path):
    service = _service(tmp_path)
    service.envelope = AutonomyEnvelope(
        action_classes=frozenset({ActionClass.FIX_DEPENDENCY}),
        require_reversible=False, risk_ceiling="high",
    )

    async def run_once(_attempt, _run_id):
        raise TaskRunFailed("ModuleNotFoundError", "no module named quote")

    result = _run(run_with_recovery(
        service, run_once, details={"objective": "quote prices"},
        max_attempts=1, sleep=lambda _s: asyncio.sleep(0),
    ))
    assert result.ok is False
    assert result.stopped_reason == "acquisition_required"
    assert result.value["acquisition"]["resolvedBy"] == "market_get_quote"


def test_the_recovery_service_plans_for_a_stored_incident(tmp_path):
    service = _service(tmp_path)
    recorded = service.record_failure(
        code="UI_CAPABILITY_GAP",
        message="no registered component matches: quote prices",
        subsystem="ui", source="event",
    )
    proposal = service.plan_incident_acquisition(recorded["incidentId"])
    assert proposal is not None
    assert proposal["resolvedBy"] == "market_get_quote"
    assert proposal["steps"][0]["surface"] == "existing_tool"
