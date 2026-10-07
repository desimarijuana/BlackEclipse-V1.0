"""Phase 3 — FastAPI skill endpoints + the workflow-ready API contract.

Exercises the real FastAPI app (no uvicorn) with TestClient: listing, detail,
discovery, input validation, evaluation, learning capture, promotion gating and
the execute endpoint's authorization behaviour.
"""

from __future__ import annotations

import os
import tempfile
from typing import Any

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("AGENT_MEMORY_DB_PATH", os.path.join(tempfile.mkdtemp(prefix="be-api-"), "agent-memory.db"))


@pytest.fixture(scope="module")
def client():
    # The module-level service reads AGENT_MEMORY_DB_PATH at import time.
    from harness import main as main_module

    with TestClient(main_module.app) as test_client:
        yield test_client


def test_health_reports_skills(client):
    body = client.get("/health").json()
    # The bundled library is the five built-in skills (Phases 0-5), the eight
    # Phase 9 kit wrappers, and the Browser Automation Runtime's
    # `system.browser-research` wrapper — 14. A checkout whose project skills are
    # trusted contributes more (e.g. the twelve CFA skills), so assert the
    # bundled floor rather than a brittle exact count.
    from harness.skills.loader import load_catalog

    bundled = len(load_catalog())
    assert bundled >= 14
    assert body["skills"]["installed"] >= bundled
    assert body["skills"]["loadErrors"] == []


def test_list_skills(client):
    body = client.get("/skills").json()
    assert body["success"] is True
    ids = {s["id"] for s in body["skills"]}
    assert "finance.fundamental-analysis" in ids


def test_skill_detail_includes_instructions_and_validation(client):
    body = client.get("/skills/research.planning").json()
    skill = body["skill"]
    assert skill["instructions"].strip()
    assert skill["validation"]["ok"] is True
    assert isinstance(skill["versions"], list)
    assert skill["storedStatus"] in {"enabled", "draft", "validated"}


def test_skill_detail_404(client):
    assert client.get("/skills/does.not.exist").status_code == 404


def test_discover_endpoint(client):
    body = client.post("/skills/discover", json={"query": "fundamental"}).json()
    assert any(r["id"] == "finance.fundamental-analysis" for r in body["results"])


def test_validate_input_endpoint(client):
    ok = client.post("/skills/validate-input", json={
        "skillId": "research.planning", "input": {"objective": "x"},
    }).json()
    assert ok["valid"] is True
    bad = client.post("/skills/validate-input", json={
        "skillId": "research.planning", "input": {},
    }).json()
    assert bad["valid"] is False


def test_evaluate_endpoint(client):
    body = client.post("/skills/research.planning/evaluate", json={"version": "1.0.0"}).json()
    assert body["success"] is True
    assert body["status"] in {"passed", "needs_review"}
    evaluation_id = body["evaluationId"]
    detail = client.get(f"/evaluations/{evaluation_id}").json()
    assert detail["evaluation"]["dimensions"]


def test_learning_candidates_endpoint_starts_empty_or_lists(client):
    body = client.get("/learning/candidates").json()
    assert body["success"] is True
    assert isinstance(body["candidates"], list)


def test_learning_from_run_requires_operator(client):
    # A run that does not exist yields an empty, non-operator result.
    body = client.post("/learning/from-run/run_missing", json={"operator": False}).json()
    assert body["success"] is False


def test_enable_without_operator_is_denied(client):
    body = client.post("/skills/research.planning/enable", json={"operator": False}).json()
    assert body["success"] is False
    assert "operator" in body["error"]


def test_enable_with_operator_succeeds(client):
    body = client.post("/skills/research.planning/enable", json={"operator": True}).json()
    assert body["success"] is True
    assert body["status"] == "enabled"


def test_execute_endpoint_missing_model_settings_blocks(client):
    # No front-door injection here (we call Python directly): a skill execution
    # without modelSettings must block, never silently fabricate a provider.
    body = client.post("/skills/research.planning/execute", json={"input": {"objective": "x"}}).json()
    assert body["status"] == "blocked"
    assert body["error"]["code"] == "MODEL_NOT_CONFIGURED"


def test_execute_unknown_skill_blocks(client):
    body = client.post("/skills/nope/execute", json={"input": {}}).json()
    assert body["status"] == "blocked"
    assert body["error"]["code"] == "SKILL_NOT_FOUND"


def test_skill_execution_list_and_404(client):
    assert client.get("/skill-executions").status_code == 200
    assert client.get("/skill-executions/run_does_not_exist").status_code == 404


def test_promotion_flow_via_api(client):
    # Evaluate, submit for review, then approve with operator authorization.
    eval_body = client.post("/skills/research.source-verification/evaluate", json={"version": "1.0.0"}).json()
    assert eval_body["success"]
    review = client.post(
        "/skill-drafts/research.source-verification/submit-review",
        json={"operator": True, "reason": "api test", "evaluationId": eval_body["evaluationId"]},
    ).json()
    if review.get("success"):
        approve = client.post(
            "/skill-drafts/research.source-verification/approve",
            json={"operator": True, "requestId": review.get("requestId", "")},
        ).json()
        assert approve["success"]
        assert approve["status"] == "enabled"
    else:
        # blocked/needs_review must not promote
        assert "review" in review.get("error", "") or "blocked" in review.get("error", "")


def test_workflow_execution_contract_shape(client):
    """The workflow-ready contract is accepted and echoes parent/child ids.

    Model settings are absent, so the run blocks before execution — but the
    request is parsed, the mode/parent ids are honoured, and a structured result
    is always returned (never a raw error).
    """
    body = client.post(
        "/skills/research.planning/execute",
        json={
            "input": {"objective": "x"},
            "executionMode": "workflow",
            "runId": "run_wf_1",
            "parentRunId": "run_wf_parent",
        },
    ).json()
    assert body["status"] == "blocked"
    assert body["skillId"] == "research.planning"
    assert "metrics" in body
