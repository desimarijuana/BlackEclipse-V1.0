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

    # Phase C: the plan is DISPATCHED (RUNNING), not left in PLANNING — else the
    # scheduler never claims the task and "build me a widget" silently no-ops.
    assert result["dispatched"] is True
    assert ui.engineering._tasks.get_plan(result["planId"]).status.value == "RUNNING"  # noqa: SLF001


def test_engineer_pins_the_caller_model_on_the_plan(ui):
    result = ui.engineering.start(
        "build a new widget that shows swap spreads",
        model_settings={"provider": "openai", "model": "gpt-x", "baseUrl": "http://x", "apiKey": "k"},
    )
    plan = ui.engineering._tasks.get_plan(result["planId"])  # noqa: SLF001
    assert plan.metadata.get("modelSettings", {}).get("model") == "gpt-x"


def test_compose_request_creates_no_task(ui):
    result = ui.engineering.start("move the latency chart below the timeline")
    assert result["created"] is False
    assert result["mode"] == "compose"
    assert result["capabilityGap"] is False
    assert "message" in result


def test_catalog_gap_escalates_instead_of_refusing(ui):
    # The recorded defect: Compose with no witness must create an engineering
    # task, never return the false "nothing to engineer" refusal.
    result = ui.engineering.start("add a multi-zone world clock to the dashboard")
    assert result["created"] is True
    assert result["mode"] == "engineer"
    assert result["capabilityGap"] is True
    assert result["taskId"] and result["planId"]


def test_capability_gap_emits_the_canonical_event(ui, monkeypatch):
    import harness.ui.engineering as engineering

    seen = []
    monkeypatch.setattr(engineering, "publish_event", lambda *a, **k: seen.append((a, k)))
    result = ui.engineering.start(
        "add a multi-zone world clock to the dashboard", run_id="run_clock",
    )
    assert result["capabilityGap"] is True
    assert seen, "the gap must emit a canonical event"
    args, kwargs = seen[0]
    assert args[0] == "ui.capability_gap"
    payload = args[1]
    assert payload["code"] == "UI_CAPABILITY_GAP"
    assert payload["runId"] == "run_clock"
    assert "clock" in payload["capability"]
    assert kwargs.get("source") == "ui"


def test_a_compose_request_emits_no_capability_gap(ui, monkeypatch):
    import harness.ui.engineering as engineering

    seen = []
    monkeypatch.setattr(engineering, "publish_event", lambda *a, **k: seen.append((a, k)))
    result = ui.engineering.start("move the latency chart below the timeline")
    assert result["created"] is False
    assert seen == []


def test_engineering_rechecks_the_catalog_even_when_the_label_says_compose(ui, monkeypatch):
    # W0.2: do not inherit the classifier's label. A stale/forced Compose label
    # for a capability the catalog cannot satisfy must still escalate.
    monkeypatch.setattr(ui, "classify_request", lambda *a, **k: {
        "mode": "compose",
        "reasons": ["forced compose label"],
        "suggestedTools": [],
        "matchedComponents": [],
        "capabilityGap": False,
    })
    result = ui.engineering.start("add a multi-zone world clock to the dashboard")
    assert result["created"] is True
    assert result["mode"] == "engineer"
    assert result["capabilityGap"] is True


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
