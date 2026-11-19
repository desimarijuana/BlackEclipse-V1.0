"""A bot the chat agent creates can be as fully configured as one the UI creates.

The gap this covers: `bot_create` used to accept three hardcoded agent ids and
none of the definition blocks (`execution`, `retry`, `concurrency`, `limits`,
`delivery`, `permissions`) that `AutomationDefinition` already models, so an
agent-created bot was silently narrower than a UI-created one.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from harness.automation.model import Action
from harness.automation.tools import (
    _create,
    _known_agent_ids,
    _update,
    set_automation_service,
)


class FakeService:
    def __init__(self, definition: object | None = None) -> None:
        self.created: dict | None = None
        self.updated: dict | None = None
        self.patch: dict | None = None
        self._definition = definition

    def create(self, payload: dict, *, created_by: str | None = None):
        self.created = payload
        view = {"id": "bot_1", **payload}
        return SimpleNamespace(public=lambda: view)

    def get(self, bot_id: str):
        return self._definition

    def update(self, bot_id: str, patch: dict, *, updated_by: str | None = None):
        self.updated = patch
        return SimpleNamespace(public=lambda: {"id": bot_id})


def _definition() -> SimpleNamespace:
    return SimpleNamespace(
        id="bot_1",
        action=Action(type="run_agent", objective="old", agent_id="eclipse-agent"),
    )


def _run(coro):
    return asyncio.run(coro)


def test_create_accepts_any_installed_agent_preset():
    known = _known_agent_ids()
    assert "eclipse-agent" in known, "the preset registry could not be read"
    for agent_id in sorted(known):
        service = FakeService()
        set_automation_service(service)
        try:
            text, payload = _run(_create(
                {"objective": "watch a thing", "agentId": agent_id}, SimpleNamespace()
            ))
            assert payload["created"] is True, text
            assert service.created is not None
            assert service.created["action"]["agentId"] == agent_id
        finally:
            set_automation_service(None)


def test_create_refuses_an_unknown_agent_preset():
    service = FakeService()
    set_automation_service(service)
    try:
        text, payload = _run(_create(
            {"objective": "watch a thing", "agentId": "not-a-preset"}, SimpleNamespace()
        ))
        assert payload["created"] is False
        assert payload["reason"] == "unknown_agent"
        assert "not-a-preset" in text
        assert service.created is None
    finally:
        set_automation_service(None)


def test_create_carries_the_same_blocks_the_ui_exposes():
    service = FakeService()
    set_automation_service(service)
    try:
        _run(_create({
            "objective": "find trades",
            "agentId": "eclipse-agent",
            "workspaceRoot": "C:/work",
            "autonomy": "edit_verify",
            "execution": {"maxRuntimeS": 600, "misfire": "run_once"},
            "retry": {"maxAttempts": 2},
            "concurrency": {"maxConcurrentRuns": 1, "onConflict": "skip_if_running"},
            "limits": {"maxTokens": 1000, "maxToolCalls": 40},
            "delivery": {"adapter": "in_app", "onSuccess": True},
            "permissions": {"denied": ["code_write"], "requiresApproval": False},
        }, SimpleNamespace()))
    finally:
        set_automation_service(None)

    payload = service.created
    assert payload is not None
    assert payload["action"]["workspaceRoot"] == "C:/work"
    assert payload["action"]["autonomy"] == "edit_verify"
    assert payload["execution"] == {"maxRuntimeS": 600, "misfire": "run_once"}
    assert payload["retry"] == {"maxAttempts": 2}
    assert payload["concurrency"]["onConflict"] == "skip_if_running"
    assert payload["limits"]["maxToolCalls"] == 40
    assert payload["delivery"]["adapter"] == "in_app"
    assert payload["permissions"]["denied"] == ["code_write"]


def test_create_omits_blocks_it_was_not_given():
    service = FakeService()
    set_automation_service(service)
    try:
        _run(_create({"objective": "plain bot"}, SimpleNamespace()))
    finally:
        set_automation_service(None)
    payload = service.created
    assert payload is not None
    for key in ("execution", "retry", "concurrency", "limits", "delivery", "permissions"):
        assert key not in payload
    assert "workspaceRoot" not in payload["action"]
    assert payload["action"]["agentId"] == "eclipse-agent"


def test_update_can_change_the_preset_and_the_blocks():
    service = FakeService(_definition())
    set_automation_service(service)
    try:
        _run(_update({
            "botId": "bot_1",
            "agentId": "code-agent",
            "workspaceRoot": "C:/work",
            "autonomy": "edit_verify",
            "limits": {"maxToolCalls": 12},
            "permissions": {"denied": ["code_push"]},
        }, SimpleNamespace()))
    finally:
        set_automation_service(None)

    patch = service.updated
    assert patch is not None
    assert patch["action"].agent_id == "code-agent"
    assert patch["action"].workspace_root == "C:/work"
    assert patch["action"].autonomy == "edit_verify"
    assert patch["limits"] == {"maxToolCalls": 12}
    assert patch["permissions"] == {"denied": ["code_push"]}


def test_update_refuses_an_unknown_agent_preset():
    service = FakeService(_definition())
    set_automation_service(service)
    try:
        _text, payload = _run(_update(
            {"botId": "bot_1", "agentId": "not-a-preset"}, SimpleNamespace()
        ))
        assert payload["updated"] is False
        assert payload["reason"] == "unknown_agent"
        assert service.updated is None
    finally:
        set_automation_service(None)


def test_update_with_no_fields_is_a_no_op():
    service = FakeService(_definition())
    set_automation_service(service)
    try:
        _text, payload = _run(_update({"botId": "bot_1"}, SimpleNamespace()))
        assert payload["updated"] is False
        assert service.updated is None
    finally:
        set_automation_service(None)


def test_a_scheduled_run_carries_the_same_capabilities_as_a_chat_turn():
    """The background path must not be a narrower agent.

    If a capability is added to the interactive run, this is the test that says
    the scheduled path needs it too: the bot's own brain, the read-only analysis
    sandbox, its private conversation memory, the model pin and reference images.
    """
    from harness.automation.dispatcher import Dispatcher
    from harness.automation.model import AutomationDefinition
    from harness.schemas import ModelSettings

    definition = AutomationDefinition(
        id="bot_x",
        name="Watcher",
        state="active",
        trigger={"type": "cron", "cron": "0 8 * * *", "timezone": "UTC"},
        action={
            "type": "run_agent",
            "objective": "review the watchlist",
            "agentId": "code-agent",
            "config": {
                "visuals": [
                    {"dataUrl": "data:image/png;base64," + "A" * 64, "caption": "pattern"},
                ],
            },
        },
        created_at="2026-01-01T00:00:00+00:00",
        updated_at="2026-01-01T00:00:00+00:00",
    )
    dispatcher = Dispatcher(
        SimpleNamespace(),
        model_settings_factory=lambda: ModelSettings(
            provider="ollama", model="pinned-model",
        ),
    )

    request = dispatcher._run_request(definition, "run_1", "review the watchlist")

    assert request.agentId == "code-agent"
    assert request.analysisEnabled is True
    assert request.conversationId == "bot-bot_x"
    assert request.modelSettings.model == "pinned-model"
    assert request.input.images and request.input.images[0].data_url.startswith("data:image/")
    # Deliberate difference: a scheduled run has no operator to answer a mid-run
    # approval card, so it uses the automation-level approval gate instead.
    assert request.approvalMode is None
