"""Skill lifecycle tools: readable history/reviews + approval-gated writes."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any, Optional

import pytest

from harness.skills.lifecycle_tools import (
    LEARNING_MODES,
    LIFECYCLE_TOOLS,
    _digest,
    make_skill_lifecycle_authorizer,
    register_skill_lifecycle_tools,
    skill_learning_get_handler,
    skill_learning_set_handler,
    skill_reviews_handler,
    skill_version_activate_handler,
    skill_version_evaluate_handler,
    skill_version_history_handler,
)
from harness.tools import ToolDefinition, ToolRegistry


class _Store:
    def __init__(self, reviews: Optional[list[dict[str, Any]]] = None) -> None:
        self.reviews = reviews or []

    def get_skill(self, skill_id: str) -> dict[str, Any]:
        return {"id": skill_id, "latestVersion": "1.0.0"}

    def list_versions(self, skill_id: str) -> list[dict[str, Any]]:
        return [{
            "version": "1.0.0", "status": "enabled", "evaluationStatus": "passed",
            "baseVersion": None, "patchSummary": None, "patchAuthor": None,
            "reviewId": None, "canaryState": None, "activatedAt": "now",
            "rolledBackAt": None, "createdAt": "then", "patch": None,
        }]

    def list_reviews(self, skill_id: str, limit: int = 20) -> list[dict[str, Any]]:
        return self.reviews[:limit]


class _Registry:
    def __init__(self, *, reviews: Optional[list[dict[str, Any]]] = None,
                 evaluations: Optional[list[dict[str, Any]]] = None) -> None:
        self.store = _Store(reviews)
        self._evaluations = evaluations or []
        self.manifest_calls: list[str] = []

    def manifest(self, skill_id: str) -> Optional[Any]:
        self.manifest_calls.append(skill_id)
        return SimpleNamespace(id=skill_id) if skill_id == "demo.skill" else None

    def version_history(self, skill_id: str) -> list[dict[str, Any]]:
        return self.store.list_versions(skill_id)

    def evaluation_history(self, skill_id: str) -> list[dict[str, Any]]:
        return self._evaluations


class _Policy:
    def __init__(self) -> None:
        self.set_calls: list[tuple[str, Any, str]] = []

    def set(self, key: str, value: Any, *, updated_by: Optional[str] = None) -> dict[str, Any]:
        self.set_calls.append((key, value, updated_by or ""))
        return {"key": key, "value": value}

    def get_all(self) -> dict[str, Any]:
        return {"auto_candidate_detection": False}


def _ctx(registry: Any = None, service: Any = None, approvals: Any = None) -> Any:
    return SimpleNamespace(
        skill_registry=registry,
        memory_service=service,
        approvals=approvals,
        user_id="u1",
        run_id="r1",
        emitter=None,
        effect_authorized_digest=None,
    )


# ── read handlers ─────────────────────────────────────────────────────────────


def test_version_history_lists_versions_and_the_latest_one() -> None:
    text, data = asyncio.run(skill_version_history_handler(
        {"skill_id": "demo.skill"}, _ctx(_Registry()),
    ))
    assert data["found"] is True and data["latestVersion"] == "1.0.0"
    assert "v1.0.0" in text and "(latest)" in text
    assert "base=none" in text and "canary=none" in text
    assert len(data["versions"]) == 1


def test_version_history_rejects_an_unknown_skill() -> None:
    _t, data = asyncio.run(skill_version_history_handler({"skill_id": "nope"}, _ctx(_Registry())))
    assert data["found"] is False and data["versions"] == []


def test_reviews_combine_reviews_and_evaluations_and_filter_by_version() -> None:
    registry = _Registry(
        reviews=[
            {"id": "rev1", "version": "1.0.0", "decision": "activate", "actor": "op",
             "createdAt": "now", "notes": "ok"},
            {"id": "rev2", "version": "1.1.0", "decision": "canary", "actor": "op",
             "createdAt": "now", "notes": ""},
        ],
        evaluations=[{"version": "1.0.0", "status": "passed", "createdAt": "now"}],
    )
    text, data = asyncio.run(skill_reviews_handler(
        {"skill_id": "demo.skill", "version": "1.0.0"}, _ctx(registry),
    ))
    assert [r["id"] for r in data["reviews"]] == ["rev1"]
    assert len(data["evaluations"]) == 1
    assert "1 review(s), 1 evaluation(s)" in text


def test_reviews_expose_the_evaluation_dimensions_and_baseline_note() -> None:
    registry = _Registry(
        evaluations=[{
            "version": "1.1.1", "status": "needs_review", "createdAt": "now",
            "summary": "needs review: regression",
            "dimensions": [
                {"name": "manifest_validation", "status": "passed", "detail": "ok"},
                {"name": "regression", "status": "needs_review",
                 "detail": "no prior evaluation to compare against"},
            ],
        }],
    )
    text, data = asyncio.run(skill_reviews_handler({"skill_id": "demo.skill"}, _ctx(registry)))
    assert len(data["evaluations"]) == 1
    assert "needs review: regression" in text
    assert "manifest_validation=passed" in text
    assert "no prior evaluation to compare against" in text
    assert "evaluate the base version first" in text


def test_reviews_says_so_when_nothing_is_recorded() -> None:
    text, _data = asyncio.run(skill_reviews_handler({"skill_id": "demo.skill"}, _ctx(_Registry())))
    assert "no review or evaluation rows" in text


def test_read_handlers_report_unavailable_skills() -> None:
    for handler in (skill_version_history_handler, skill_reviews_handler):
        _t, data = asyncio.run(handler({"skill_id": "demo.skill"}, _ctx(None)))
        assert data.get("error") == "SKILLS_UNAVAILABLE" or data.get("found") is False


def test_learning_get_reads_the_persisted_mode_not_the_setter() -> None:
    policy = _Policy()
    service = SimpleNamespace(policy=policy)
    _t, data = asyncio.run(skill_learning_get_handler({}, _ctx(service=service)))
    assert data["found"] is True
    assert data["mode"] is None  # _Policy.get_all only carries the derived flag
    assert data["autoCandidateDetection"] is False
    assert policy.set_calls == []


def test_learning_get_reports_unavailable_policy() -> None:
    _t, data = asyncio.run(skill_learning_get_handler({}, _ctx(service=None)))
    assert data["found"] is False and data["error"] == "POLICY_UNAVAILABLE"


# ── write handlers ────────────────────────────────────────────────────────────


def test_evaluate_delegates_to_the_one_versioning_path(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    def fake_evaluate(registry: Any, skill_id: str, version: str, **kw: Any) -> dict[str, Any]:
        captured.update({"registry": registry, "skill_id": skill_id, "version": version, **kw})
        return {"ok": True, "status": "passed", "record": {"passed": 5, "failed": 0}}

    monkeypatch.setattr("harness.skills.versioning.evaluate_version", fake_evaluate)
    registry = _Registry()
    text, data = asyncio.run(skill_version_evaluate_handler(
        {"skill_id": "demo.skill", "version": "1.1.0"}, _ctx(registry),
    ))
    assert data["evaluated"] is True and data["status"] == "passed"
    assert captured["actor"].operator is True
    assert "Activation now has a basis" in text


def test_evaluate_explains_a_needs_review_regression(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "harness.skills.versioning.evaluate_version",
        lambda *a, **k: {
            "ok": True, "status": "needs_review", "summary": "needs review: regression",
            "dimensions": [
                {"name": "regression", "status": "needs_review",
                 "detail": "no prior evaluation to compare against"},
            ],
            "record": {"passed": 8, "failed": 0},
        },
    )
    text, data = asyncio.run(skill_version_evaluate_handler(
        {"skill_id": "demo.skill", "version": "1.1.1"}, _ctx(_Registry()),
    ))
    assert data["status"] == "needs_review"
    assert "needs review: regression" in text
    assert "evaluate the base version first" in text
    assert "A PASSING evaluation is required" in text


def test_reevaluation_output_names_the_regression_baseline(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "harness.skills.versioning.evaluate_version",
        lambda *a, **k: {
            "ok": True, "status": "passed", "summary": "all mandatory checks passed",
            "dimensions": [
                {"name": "regression", "status": "passed",
                 "detail": "no regressions vs 1.0.0"},
            ],
            "record": {"passed": 9, "failed": 0},
        },
    )
    text, _data = asyncio.run(skill_version_evaluate_handler(
        {"skill_id": "demo.skill", "version": "1.1.1"}, _ctx(_Registry()),
    ))
    assert "Regression baseline: no regressions vs 1.0.0" in text


def test_reviews_show_the_regression_baseline_on_a_pass() -> None:
    registry = _Registry(
        evaluations=[{
            "version": "1.1.1", "status": "passed", "createdAt": "now",
            "summary": "all mandatory checks passed",
            "dimensions": [
                {"name": "regression", "status": "passed",
                 "detail": "no regressions vs 1.0.0"},
            ],
        }],
    )
    text, _data = asyncio.run(skill_reviews_handler({"skill_id": "demo.skill"}, _ctx(registry)))
    assert "regression: no regressions vs 1.0.0" in text


def test_evaluate_requires_id_and_version() -> None:
    _t, data = asyncio.run(skill_version_evaluate_handler({"skill_id": "demo.skill"}, _ctx(_Registry())))
    assert data["evaluated"] is False and data["error"] == "MISSING_INPUT"


def test_activate_requires_id_and_version() -> None:
    _t, data = asyncio.run(skill_version_activate_handler({"skill_id": "demo.skill"}, _ctx(_Registry())))
    assert data["activated"] is False and data["error"] == "MISSING_INPUT"


def test_activate_delegates_to_the_one_versioning_path(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    def fake_activate(registry: Any, skill_id: str, version: str, **kw: Any) -> dict[str, Any]:
        captured.update({"registry": registry, "skill_id": skill_id, "version": version, **kw})
        return {"ok": True, "skillId": skill_id, "version": version, "status": "enabled", "canary": False}

    monkeypatch.setattr("harness.skills.versioning.activate_version", fake_activate)
    registry = _Registry()
    text, data = asyncio.run(skill_version_activate_handler(
        {"skill_id": "demo.skill", "version": "1.1.0"}, _ctx(registry),
    ))
    assert data["activated"] is True
    assert captured["skill_id"] == "demo.skill" and captured["version"] == "1.1.0"
    assert captured["actor"].operator is True
    assert "Activated demo.skill v1.1.0" in text


def test_activate_reports_a_blocking_evaluation(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "harness.skills.versioning.activate_version",
        lambda *a, **k: {"ok": False, "error": "a passing evaluation is required"},
    )
    text, data = asyncio.run(skill_version_activate_handler(
        {"skill_id": "demo.skill", "version": "1.1.0"}, _ctx(_Registry()),
    ))
    assert data["activated"] is False
    assert "passing evaluation" in text


def test_learning_set_uses_the_policy_store_and_the_closed_vocabulary() -> None:
    policy = _Policy()
    service = SimpleNamespace(policy=policy)
    text, data = asyncio.run(skill_learning_set_handler({"mode": "off"}, _ctx(service=service)))
    assert data["updated"] is True and data["mode"] == "off"
    assert policy.set_calls == [("skill_learning_mode", "off", "u1")]
    assert "off" in text

    _t, bad = asyncio.run(skill_learning_set_handler({"mode": "sometimes"}, _ctx(service=service)))
    assert bad["updated"] is False and bad["error"] == "INVALID_MODE"
    assert len(policy.set_calls) == 1


def test_learning_set_reports_unavailable_policy() -> None:
    _t, data = asyncio.run(skill_learning_set_handler({"mode": "off"}, _ctx(service=None)))
    assert data["error"] == "POLICY_UNAVAILABLE"


# ── registration + authorizer ─────────────────────────────────────────────────


def test_registration_declares_reads_and_gated_writes() -> None:
    reg = ToolRegistry()
    register_skill_lifecycle_tools(reg)
    names = set(reg.names())
    assert {"skill_version_history", "skill_reviews", "skill_learning_get"} <= names
    for name in LIFECYCLE_TOOLS:
        assert reg.get(name).permission == "write"
        assert reg.get(name).effect == "write"


class _Approvals:
    def __init__(self, *, claim_digest: Optional[str] = None) -> None:
        self._digest = claim_digest
        self.requests: list[dict[str, Any]] = []

    def consume_kind(self, **kw: Any) -> Any:
        if self._digest is not None and kw.get("digest") == self._digest:
            return {"id": "appr_1"}
        return None

    def request_kind(self, **kw: Any) -> Any:
        self.requests.append(kw)
        return {"id": "appr_req"}


def _tool(name: str) -> ToolDefinition:
    return ToolDefinition(
        name=name, description="", input_schema={"type": "object", "properties": {}},
        handler=lambda a, c: ("", None), permission="write", risk="low", effect="write",
    )


async def _false_inner(tool: Any, args: dict[str, Any], ctx: Any = None) -> bool:
    return False


def test_a_claimed_approval_authorizes_evaluation() -> None:
    digest = _digest("skill_version_evaluate", "demo.skill", "1.1.0")
    auth = make_skill_lifecycle_authorizer(_false_inner)
    ok = asyncio.run(auth(
        _tool("skill_version_evaluate"),
        {"skill_id": "demo.skill", "version": "1.1.0"},
        _ctx(approvals=_Approvals(claim_digest=digest)),
    ))
    assert ok is True


def test_a_claimed_approval_authorizes_activation() -> None:
    args = {"skill_id": "demo.skill", "version": "1.1.0"}
    digest = _digest("skill_version_activate", "demo.skill", "1.1.0\x00canary=False")
    auth = make_skill_lifecycle_authorizer(_false_inner)
    ok = asyncio.run(auth(_tool("skill_version_activate"), args, _ctx(approvals=_Approvals(claim_digest=digest))))
    assert ok is True


def test_a_different_version_needs_a_new_approval() -> None:
    digest = _digest("skill_version_activate", "demo.skill", "1.0.0\x00canary=False")
    auth = make_skill_lifecycle_authorizer(_false_inner)
    ok = asyncio.run(auth(
        _tool("skill_version_activate"),
        {"skill_id": "demo.skill", "version": "1.1.0"},
        _ctx(approvals=_Approvals(claim_digest=digest)),
    ))
    assert ok is False


def test_learning_approval_is_bound_to_the_mode() -> None:
    store = _Approvals()
    auth = make_skill_lifecycle_authorizer(_false_inner)
    ok = asyncio.run(auth(_tool("skill_learning_set"), {"mode": "off"}, _ctx(approvals=store)))
    assert ok is False
    assert store.requests and store.requests[0]["kind"] == "skill_learning_set"
    assert _digest("skill_learning_set", "skill_learning", "off") in repr(store.requests[0])


def test_invalid_mode_never_requests_an_approval() -> None:
    store = _Approvals()
    auth = make_skill_lifecycle_authorizer(_false_inner)
    assert asyncio.run(auth(_tool("skill_learning_set"), {"mode": "nope"}, _ctx(approvals=store))) is False
    assert store.requests == []


def test_no_approval_store_never_authorizes() -> None:
    auth = make_skill_lifecycle_authorizer(_false_inner)
    assert asyncio.run(auth(_tool("skill_learning_set"), {"mode": "off"}, _ctx(approvals=None))) is False


def test_other_tools_fall_through() -> None:
    auth = make_skill_lifecycle_authorizer(_false_inner)
    assert asyncio.run(auth(_tool("skill_view"), {}, _ctx(approvals=_Approvals()))) is False


def test_plan_only_removes_the_lifecycle_writes() -> None:
    from harness.code.policy import allowed_tools

    assert allowed_tools("plan_only", LIFECYCLE_TOOLS) == ()


def test_the_tools_are_declared_on_the_finance_and_chat_profiles() -> None:
    from harness.agents import CHAT_CODE_TOOLS, ECLIPSE_AGENT

    for name in (*LIFECYCLE_TOOLS, "skill_version_history", "skill_reviews", "skill_learning_get"):
        assert name in ECLIPSE_AGENT.tools, name
        assert name in CHAT_CODE_TOOLS, name


def test_learning_modes_are_the_policy_vocabulary() -> None:
    from harness.eclipse_memory.policy import MODE_VALUES

    assert set(LEARNING_MODES) == set(MODE_VALUES)
