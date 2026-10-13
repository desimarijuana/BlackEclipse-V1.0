"""R3-07 — an autonomous schedule needs the operator's explicit go-ahead.

The bot tools that can CREATE OR KEEP autonomous work running are effectful and
admitted by the bot authorizer; the HANDLER claims (or requests, and pauses for) a
single-use approval of kind `bot_schedule` before a schedule is created or
started. Lifecycle-safe tools (pause/disable/delete/run) stay ungated.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

from harness.automation import tools as bot_tools
from harness.automation.authorizers import make_bot_authorizer
from harness.code.policy import AUTOMATION_EFFECT_TOOLS, allowed_tools
from harness.tools import ToolDefinition


class _Service:
    def __init__(self) -> None:
        self.created: list[dict[str, Any]] = []
        self.calls: list[str] = []

    def create(self, payload: dict[str, Any], created_by: str = "") -> Any:
        self.created.append(payload)
        return SimpleNamespace(public=lambda: {"id": "bot_test", "name": payload.get("name")})

    def pause(self, bot_id: str, actor: str = "") -> Any:
        self.calls.append("pause")
        return SimpleNamespace(public=lambda: {"id": bot_id, "state": "paused"})

    def resume(self, bot_id: str, actor: str = "") -> Any:
        self.calls.append("resume")
        return SimpleNamespace(public=lambda: {"id": bot_id, "state": "active"})


class _Approvals:
    def __init__(self, *, claim: bool) -> None:
        self.claim = claim
        self.requests: list[dict[str, Any]] = []

    def consume_kind(self, *, kind: str, request_key: str, digest: str, workspace_id: Any = None) -> Any:
        return {"id": "appr_1"} if self.claim else None

    def request_kind(self, **kwargs: Any) -> Any:
        self.requests.append(kwargs)
        return {"id": "appr_req"}

    def find_active_kind(self, **kwargs: Any) -> Any:
        return None


def _ctx(approvals: Any = None) -> Any:
    return SimpleNamespace(
        approvals=approvals, run_id="run_1", pause_for_approval=False, emitter=None,
    )


def test_a_manual_bot_needs_no_approval(monkeypatch: Any) -> None:
    svc = _Service()
    monkeypatch.setattr(bot_tools, "_require_service", lambda: svc)
    _text, data = asyncio.run(bot_tools._create(
        {"objective": "Daily brief", "triggerType": "manual"}, _ctx(_Approvals(claim=False)),
    ))
    assert data["created"] is True
    assert svc.created and svc.created[0]["trigger"]["type"] == "manual"


def test_a_scheduled_bot_requests_approval_and_creates_nothing(monkeypatch: Any) -> None:
    svc = _Service()
    monkeypatch.setattr(bot_tools, "_require_service", lambda: svc)
    approvals = _Approvals(claim=False)
    text, data = asyncio.run(bot_tools._create(
        {"objective": "Daily brief", "triggerType": "cron", "cron": "0 9 * * *"}, _ctx(approvals),
    ))
    assert data["created"] is False and data["approved"] is False
    assert svc.created == []
    assert approvals.requests and approvals.requests[0]["kind"] == "bot_schedule"
    assert "go-ahead" in text


def test_a_claimed_approval_lets_the_schedule_through(monkeypatch: Any) -> None:
    svc = _Service()
    monkeypatch.setattr(bot_tools, "_require_service", lambda: svc)
    _text, data = asyncio.run(bot_tools._create(
        {"objective": "Daily brief", "triggerType": "interval", "intervalSeconds": 3600},
        _ctx(_Approvals(claim=True)),
    ))
    assert data["created"] is True
    assert svc.created[0]["trigger"]["type"] == "interval"


def test_without_an_approvals_store_the_tool_stays_admitted(monkeypatch: Any) -> None:
    # Mirrors workspace_patch_apply: zero-config local runs have no store; the
    # run's profile and allowlist already gated the tool.
    svc = _Service()
    monkeypatch.setattr(bot_tools, "_require_service", lambda: svc)
    _text, data = asyncio.run(bot_tools._create(
        {"objective": "Daily brief", "triggerType": "cron", "cron": "0 9 * * *"}, _ctx(None),
    ))
    assert data["created"] is True


def test_resume_is_gated_and_pause_is_not(monkeypatch: Any) -> None:
    svc = _Service()
    monkeypatch.setattr(bot_tools, "_require_service", lambda: svc)
    resume = bot_tools._lifecycle_handler("resume")
    _text, data = asyncio.run(resume({"botId": "bot_1"}, _ctx(_Approvals(claim=False))))
    assert data["ok"] is False
    assert svc.calls == []

    pause = bot_tools._lifecycle_handler("pause")
    _text2, data2 = asyncio.run(pause({"botId": "bot_1"}, _ctx(_Approvals(claim=False))))
    assert data2.get("ok") is not False
    assert svc.calls == ["pause"]


def test_the_authorizer_admits_schedule_tools_and_falls_through_otherwise() -> None:
    async def inner(tool: Any, args: dict[str, Any], ctx: Any = None) -> bool:
        return False

    def _tool(name: str) -> ToolDefinition:
        return ToolDefinition(
            name=name, description="", input_schema={"type": "object", "properties": {}},
            handler=lambda a, c: ("", None), permission="write", risk="low",
            effect="external_action",
        )

    auth = make_bot_authorizer(inner)
    assert asyncio.run(auth(_tool("bot_create"), {}, None)) is True
    assert asyncio.run(auth(_tool("bot_resume"), {}, None)) is True
    assert asyncio.run(auth(_tool("bot_pause"), {}, None)) is False


def test_plan_only_cannot_schedule_but_keeps_the_safe_lifecycle() -> None:
    declared = (*AUTOMATION_EFFECT_TOOLS, "bot_pause", "bot_disable", "bot_delete")
    allowed = allowed_tools("plan_only", declared)
    for name in AUTOMATION_EFFECT_TOOLS:
        assert name not in allowed, name
    for name in ("bot_pause", "bot_disable", "bot_delete"):
        assert name in allowed, name
