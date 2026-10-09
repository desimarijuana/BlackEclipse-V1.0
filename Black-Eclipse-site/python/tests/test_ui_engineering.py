"""UI Engineering Agent (Phase 7) — plan/task orchestration over the Task runtime."""

from __future__ import annotations

import pytest

from harness.persistence import AgentMemoryStore
from harness.tasks.manager import TaskManager
from harness.tasks.model import CriterionState
from harness.tasks.store import TaskStore
from harness.ui.catalog import UiCatalog
from harness.ui.model import UiComponentSpec
from harness.ui.service import UiService
from harness.ui.store import UiStore


@pytest.fixture()
def ui(tmp_path):
    memory = AgentMemoryStore(str(tmp_path / "agent-memory.db"))
    tasks = TaskManager(TaskStore(memory))
    service = UiService(UiStore(memory), UiCatalog(), tasks=tasks)
    yield service
    memory.close()


def test_engineer_request_creates_a_durable_task(ui):
    result = ui.engineering.start("build a new plugin with a backend API endpoint", blueprint_id=None)
    assert result["created"] is True
    assert result["mode"] == "engineer"
    assert result["taskId"] and result["planId"]
    assert any("registered in the UI catalog" in c for c in result["acceptance"])

    view = ui.engineering.status(result["planId"])
    assert view["plan"]["id"] == result["planId"]
    assert view["tasks"], "the plan should carry the engineering task"


def test_compose_request_creates_no_task(ui):
    result = ui.engineering.start("move the latency chart below the timeline")
    assert result["created"] is False
    assert result["mode"] == "compose"
    assert "message" in result


def test_register_component_closes_the_loop(ui):
    started = ui.engineering.start("create a brand new component for a 3d globe")
    task_id = started["taskId"]
    spec = UiComponentSpec(id="trade-globe", display_name="Trade Globe", category="charts", owner="user")
    result = ui.engineering.register_component(task_id, spec)

    assert result["componentId"] == "trade-globe"
    assert ui.inspect_component("trade-globe").display_name == "Trade Globe"

    criteria = ui.engineering._tasks.list_criteria(task_id)  # noqa: SLF001 - test inspection
    catalog_criteria = [c for c in criteria if "registered in the UI catalog" in c.text]
    assert catalog_criteria and catalog_criteria[0].state == CriterionState.PASSED

    artifacts = ui.engineering._tasks.list_artifacts(task_id)  # noqa: SLF001
    assert any(a.uri == "ui-component:trade-globe" for a in artifacts)


def test_link_engineering_artifact(ui):
    started = ui.engineering.start("build a new component")
    result = ui.engineering.link_artifact(started["taskId"], uri="diff:abc123", kind="diff", label="patch")
    assert result["uri"] == "diff:abc123"
    assert ui.engineering._tasks.list_artifacts(started["taskId"])  # noqa: SLF001


def test_engineering_unavailable_without_tasks(tmp_path):
    memory = AgentMemoryStore(str(tmp_path / "m.db"))
    service = UiService(UiStore(memory), UiCatalog(), tasks=None)
    with pytest.raises(Exception) as exc:
        service.engineering.start("build a new API")
    assert getattr(exc.value, "code", "") == "UI_ENGINEERING_UNAVAILABLE"
    memory.close()
