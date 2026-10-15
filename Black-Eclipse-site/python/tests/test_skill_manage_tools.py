"""Track 4 — the agent-authored extension layer (`skill_create`/`_update`/`_delete`).

A skill is DECLARATIVE (a validated manifest + bounded instructions, never code),
authored through the SAME `SkillRegistry` a person uses. Every write is a `write`
tool removed at `plan_only` and gated by a single-use, digest-bound operator
approval in the effect chain.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any, Optional

import pytest

from harness.skills.manage_tools import (
    MANAGE_TOOLS,
    _digest,
    make_skill_manage_authorizer,
    register_skill_manage_tools,
    skill_create_handler,
    skill_delete_handler,
    skill_update_handler,
)
from harness.tools import ToolDefinition, ToolRegistry


class _FakeRegistry:
    def __init__(self) -> None:
        self.created: list[dict[str, Any]] = []
        self.updated: list[tuple[str, dict[str, Any]]] = []
        self.deleted: list[str] = []

    def create_user_skill(self, **kw: Any) -> Any:
        self.created.append(kw)
        return {"skillId": "user.demo", "version": "1.0.0", "status": "enabled"}

    def update_user_skill(self, skill_id: str, **patch: Any) -> Any:
        self.updated.append((skill_id, patch))
        return {"skillId": skill_id, "version": "1.1.0", "status": "enabled"}

    def delete_user_skill(self, skill_id: str) -> Any:
        self.deleted.append(skill_id)
        return {"skillId": skill_id, "deleted": True}


def _ctx(registry: Any = None, approvals: Any = None) -> Any:
    return SimpleNamespace(
        skill_registry=registry, approvals=approvals, run_id="r",
        pause_for_approval=False, emitter=None, effect_authorized_digest=None,
    )


# ── registration ──────────────────────────────────────────────────────────────

def test_register_adds_the_three_manage_tools() -> None:
    reg = ToolRegistry()
    register_skill_manage_tools(reg)
    names = set(reg.names())
    for name in MANAGE_TOOLS:
        assert name in names, name
        assert reg.get(name).permission == "write"
        assert reg.get(name).effect == "write"


# ── handlers ──────────────────────────────────────────────────────────────────

def test_create_calls_the_registry_and_reports_the_id() -> None:
    reg = _FakeRegistry()
    text, data = asyncio.run(skill_create_handler(
        {"name": "Nightly brief", "instructions": "1. do x\n2. do y"}, _ctx(reg),
    ))
    assert data["created"] is True and data["skillId"] == "user.demo"
    assert reg.created and reg.created[0]["author"] == "agent"
    assert "user.demo" in text


def test_create_requires_a_name_and_instructions() -> None:
    reg = _FakeRegistry()
    _t, data = asyncio.run(skill_create_handler({"name": "x"}, _ctx(reg)))
    assert data["created"] is False and data["error"] == "MISSING_INPUT"
    assert reg.created == []


def test_update_produces_a_new_version() -> None:
    reg = _FakeRegistry()
    _t, data = asyncio.run(skill_update_handler(
        {"skill_id": "user.demo", "instructions": "improved"}, _ctx(reg),
    ))
    assert data["updated"] is True and data["version"] == "1.1.0"
    assert reg.updated == [("user.demo", {"instructions": "improved"})]


def test_delete_reports_the_outcome() -> None:
    reg = _FakeRegistry()
    _t, data = asyncio.run(skill_delete_handler({"skill_id": "user.demo"}, _ctx(reg)))
    assert data["deleted"] is True and reg.deleted == ["user.demo"]


def test_handlers_report_when_skills_are_unavailable() -> None:
    for handler in (skill_create_handler, skill_update_handler, skill_delete_handler):
        _t, data = asyncio.run(handler({"name": "x", "skill_id": "x", "instructions": "y"}, _ctx(None)))
        assert data.get("error") == "SKILLS_UNAVAILABLE", handler.__name__


# ── the authorizer ────────────────────────────────────────────────────────────

class _Store:
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


def test_a_claimed_approval_authorizes_a_skill_write() -> None:
    args = {"skill_id": "user.demo", "instructions": "x"}
    digest = _digest("skill_update", "user.demo", "x")
    auth = make_skill_manage_authorizer(_false_inner)
    assert asyncio.run(auth(_tool("skill_update"), args, _ctx(approvals=_Store(claim_digest=digest)))) is True


def test_without_a_claim_it_requests_and_refuses() -> None:
    store = _Store()
    auth = make_skill_manage_authorizer(_false_inner)
    ok = asyncio.run(auth(_tool("skill_create"), {"name": "Demo", "instructions": "y"}, _ctx(approvals=store)))
    assert ok is False
    assert store.requests and store.requests[0]["kind"] == "skill_create"


def test_a_changed_body_needs_a_new_approval() -> None:
    digest = _digest("skill_create", "Demo", "old body")
    auth = make_skill_manage_authorizer(_false_inner)
    ok = asyncio.run(auth(_tool("skill_create"), {"name": "Demo", "instructions": "new body"},
                          _ctx(approvals=_Store(claim_digest=digest))))
    assert ok is False


def test_with_no_store_it_never_authorizes() -> None:
    auth = make_skill_manage_authorizer(_false_inner)
    assert asyncio.run(auth(_tool("skill_create"), {"name": "Demo", "instructions": "y"}, _ctx(approvals=None))) is False


@pytest.mark.parametrize("name", ["skill_install", "unknown_tool", "git_push"])
def test_other_tools_fall_through(name: str) -> None:
    auth = make_skill_manage_authorizer(_false_inner)
    assert asyncio.run(auth(_tool(name), {}, _ctx(approvals=_Store()))) is False


# ── the autonomy boundary ─────────────────────────────────────────────────────

def test_plan_only_removes_the_manage_tools() -> None:
    from harness.code.policy import allowed_tools

    result = allowed_tools("plan_only", MANAGE_TOOLS)
    assert result == ()


def test_edit_verify_keeps_the_manage_tools() -> None:
    from harness.code.policy import allowed_tools

    assert set(allowed_tools("edit_verify", MANAGE_TOOLS)) == set(MANAGE_TOOLS)


def test_the_tools_are_declared_on_the_finance_and_chat_profiles() -> None:
    from harness.agents import CHAT_CODE_TOOLS, ECLIPSE_AGENT

    for name in MANAGE_TOOLS:
        assert name in ECLIPSE_AGENT.tools, name
        assert name in CHAT_CODE_TOOLS, name
