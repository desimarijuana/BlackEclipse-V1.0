"""End-to-end lifecycle proof on a FRESH store.

The unit tests use fakes; this test uses the REAL service, the REAL skill store,
the REAL deterministic evaluator and the REAL tool registry, with every database
redirected to a temp directory. It is the production-readiness check for the
agent-facing lifecycle surface: nothing here depends on the developer's local
`eclipse-memory.db`, a prior activation, or a manually backfilled version.
"""

from __future__ import annotations

import asyncio
import os
from types import SimpleNamespace

import pytest

from harness.persistence import AgentMemoryStore
from harness.service import AgenticService
from harness.skills.lifecycle_tools import (
    skill_learning_get_handler,
    skill_learning_set_handler,
    skill_reviews_handler,
    skill_version_activate_handler,
    skill_version_evaluate_handler,
    skill_version_history_handler,
)

SKILL = "research.planning"


@pytest.fixture()
def service(monkeypatch: pytest.MonkeyPatch, tmp_path) -> AgenticService:
    # Both stores must be fresh. ECLIPSE_MEMORY_DB_PATH is read when the memory
    # service is constructed; AGENT_MEMORY_DB_PATH is passed explicitly.
    monkeypatch.setenv("ECLIPSE_MEMORY_DB_PATH", str(tmp_path / "eclipse-memory.db"))
    monkeypatch.setenv("HARNESS_MCP_CONFIG", str(tmp_path / "mcp-servers.json"))
    agent_store = AgentMemoryStore(str(tmp_path / "agent-memory.db"))
    svc = AgenticService(store=agent_store)
    try:
        yield svc
    finally:
        agent_store.close()


def _ctx(svc: AgenticService) -> SimpleNamespace:
    return SimpleNamespace(
        skill_registry=svc.skill_registry,
        memory_service=svc.memory,
        user_id="operator",
        run_id="run_e2e",
        approvals=None,
        effect_authorized_digest=None,
    )


def _add_version(svc: AgenticService, version: str, base: str) -> None:
    manifest = svc.skill_registry.manifest(SKILL)
    assert manifest is not None
    candidate = manifest.model_copy(update={"version": version, "status": "testing"})
    svc.skill_store.save_version(
        candidate.model_dump(), candidate.content_hash(), base_version=base,
    )
    svc.skill_store.set_latest_version(SKILL, version)


def test_fresh_store_evaluate_activate_history_reviews_and_learning(service: AgenticService) -> None:
    ctx = _ctx(service)
    versions = service.skill_registry.store.list_versions(SKILL)
    assert versions, "the bundled catalog did not persist its versions on a fresh store"

    # 1. Evaluate the declared base version, then create a candidate whose base is
    #    that version. Both evaluations must be REAL deterministic runs.
    base = asyncio.run(skill_version_evaluate_handler({"skill_id": SKILL, "version": versions[0]["version"]}, ctx))
    assert base[1]["evaluated"] is True

    _add_version(service, "2.0.0", versions[0]["version"])
    candidate_text, candidate = asyncio.run(skill_version_evaluate_handler(
        {"skill_id": SKILL, "version": "2.0.0"}, ctx,
    ))
    assert candidate["evaluated"] is True and candidate["status"] == "passed"
    assert "no regressions vs" in candidate_text
    assert versions[0]["version"] in candidate_text

    # 2. Activate through the ONE versioning path (the approval gate is unit-tested;
    #    this proves the state transition on a real store).
    activated_text, activated = asyncio.run(skill_version_activate_handler(
        {"skill_id": SKILL, "version": "2.0.0"}, ctx,
    ))
    assert activated["activated"] is True and activated["status"] == "enabled"
    assert "Activated" in activated_text

    # 3. Read it back: lineage, latest, activation timestamp, prior superseded.
    history_text, history = asyncio.run(skill_version_history_handler({"skill_id": SKILL}, ctx))
    assert history["latestVersion"] == "2.0.0"
    latest = next(v for v in history["versions"] if v["version"] == "2.0.0")
    assert latest["baseVersion"] == versions[0]["version"]
    assert latest["activatedAt"]
    assert latest["status"] == "enabled"
    prior = next(v for v in history["versions"] if v["version"] == versions[0]["version"])
    assert prior["status"] == "superseded"
    assert "base=v2.0.0" not in history_text  # explicit lineage, not a self-base

    # 3b. A reload after activation must NOT report the lifecycle status change as
    #     content drift (the identity check pins lifecycle fields to their stored
    #     values). Without this, every activated skill reports drift forever.
    reload_errors = service.skill_registry.load_all()
    assert not any(SKILL in error for error in reload_errors), reload_errors

    # 4. The activation wrote a review; evaluations are separate records.
    review_text, trail = asyncio.run(skill_reviews_handler({"skill_id": SKILL}, ctx))
    assert any(r["decision"] == "activate" for r in trail["reviews"])
    assert trail["evaluations"], "evaluations were not persisted"
    assert "Activated" not in review_text  # reviews show decisions, not tool prose

    # 5. The learning switch round-trips through the real PolicyStore.
    _t, off = asyncio.run(skill_learning_set_handler({"mode": "off"}, ctx))
    assert off["updated"] is True and off["mode"] == "off"
    _t, read_back = asyncio.run(skill_learning_get_handler({}, ctx))
    assert read_back["mode"] == "off" and read_back["autoCandidateDetection"] is False
    _t, restored = asyncio.run(skill_learning_set_handler({"mode": "automatic_selective"}, ctx))
    assert restored["mode"] == "automatic_selective"


def test_registry_dispatch_enforces_approval_and_persists(service: AgenticService) -> None:
    from harness.code.authorizers import build_effect_authorizer
    from harness.mcp.approvals import ApprovalStore
    from harness.tools import ToolContext

    approvals = ApprovalStore(service.store)
    ctx = ToolContext(
        run_id="run_dispatch",
        log=lambda *_a: None,
        user_id="operator",
        skill_registry=service.skill_registry,
        memory_service=service.memory,
        approvals=approvals,
        authorize_effect=build_effect_authorizer(
            approvals=approvals, run_id="run_dispatch", emitter=None, workspace_id="ws1",
        ),
    )
    args = {"skill_id": SKILL, "version": service.skill_registry.store.list_versions(SKILL)[0]["version"]}

    denied = asyncio.run(service.registry.execute("skill_version_evaluate", "c1", args, ctx))
    assert denied.ok is False
    pending = [a for a in approvals.list(status="pending") if a["kind"] == "skill_version_evaluate"]
    assert len(pending) == 1, "the write did not request an operator approval"

    approvals.decide(pending[0]["id"], approve=True, decided_by="test")
    allowed = asyncio.run(service.registry.execute("skill_version_evaluate", "c2", args, ctx))
    assert allowed.ok is True and allowed.data["evaluated"] is True

    again = asyncio.run(service.registry.execute("skill_version_evaluate", "c3", args, ctx))
    assert again.ok is False, "a consumed approval must not authorize a second call"


def test_lifecycle_writes_need_a_real_single_use_approval(service: AgenticService) -> None:
    from harness.mcp.approvals import ApprovalStore
    from harness.skills.lifecycle_tools import make_skill_lifecycle_authorizer

    approvals = ApprovalStore(service.store)
    authorize = make_skill_lifecycle_authorizer()
    ctx = SimpleNamespace(
        approvals=approvals, run_id="run_approval", user_id="operator",
        pause_for_approval=False, emitter=None, effect_authorized_digest=None,
    )
    tool = SimpleNamespace(name="skill_version_evaluate")
    args = {"skill_id": SKILL, "version": "2.0.0"}

    assert asyncio.run(authorize(tool, args, ctx)) is False
    pending = [a for a in approvals.list(status="pending") if a["kind"] == "skill_version_evaluate"]
    assert len(pending) == 1
    approvals.decide(pending[0]["id"], approve=True, decided_by="test")

    assert asyncio.run(authorize(tool, args, ctx)) is True
    # Single-use: the registry clears the per-call digest scope before each call,
    # so a second call with the same digest needs a fresh decision.
    ctx.effect_authorized_digest = None
    assert asyncio.run(authorize(tool, args, ctx)) is False
    # A different version is a different digest, so the consumed approval cannot
    # authorize it.
    ctx.effect_authorized_digest = None
    assert asyncio.run(authorize(tool, {"skill_id": SKILL, "version": "2.0.1"}, ctx)) is False
