"""A bot's version pin must not be invalidated by activating it.

`prepare` pins the trading mandate to the definition version. The UI creates a
draft, prepares trading, then activates. If the activation bumped the version,
the mandate would be stale before the bot's very first run - which is exactly
what happened against the real MT5 terminal (BOT_VERSION_STALE).
"""

from __future__ import annotations

import os

import pytest


@pytest.fixture()
def service(tmp_path):
    from harness.automation.engine import AutomationEngine
    from harness.automation.service import AutomationService
    from harness.automation.store import AutomationStore
    from harness.persistence import AgentMemoryStore
    from harness.tools import ToolRegistry

    class _Host:
        registry = ToolRegistry()
        skill_registry = None

        def workflow_store(self):  # pragma: no cover - nothing asks in this test
            raise RuntimeError("no workflow store in this fixture")

    agent_store = AgentMemoryStore(os.path.join(str(tmp_path), "agent-memory.db"))
    store = AutomationStore(agent_store)
    host = _Host()
    return AutomationService(host, store, AutomationEngine(host, store))


def _create(service):
    return service.create({
        "name": "version pin",
        "state": "draft",
        "trigger": {"type": "manual"},
        "action": {
            "type": "send_notification",
            "objective": "tell me",
            "notification_template": "hello",
        },
        "execution": {"misfire": "skip"},
    })


def test_activating_a_draft_keeps_its_version(service):
    bot = _create(service)
    assert bot.version == 1

    active = service.update(bot.id, {"state": "active"})
    assert active.state == "active"
    assert active.version == 1, "activation must not stale the prepared mandate"

    paused = service.update(bot.id, {"state": "paused"})
    assert paused.version == 1


def test_a_semantic_edit_still_bumps_the_version(service):
    bot = _create(service)
    renamed = service.update(bot.id, {"name": "renamed"})
    assert renamed.version == bot.version + 1
