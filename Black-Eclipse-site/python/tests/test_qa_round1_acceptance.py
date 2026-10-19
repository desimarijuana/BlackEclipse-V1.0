"""QA Round 1 acceptance — the contract this round promised (Q6).

These are intentionally cross-cutting: one assertion per finding so a future
change that silently drops a fix fails here even if the unit test for that
module was renamed.
"""

from __future__ import annotations

from types import SimpleNamespace

from harness.agents import CHAT_CODE_TOOLS, UI_TOOLS
from harness.app_api_tools import register_app_api_tools
from harness.eclipse_memory import EclipseMemoryService, EclipseMemoryStore
from harness.graph import chat_step_budget
from harness.graph_context import _eligibility_dict
from harness.memory_tools import register_memory_tools
from harness.persistence import AgentMemoryStore
from harness.tools import ToolRegistry
from harness.ui.catalog import UiCatalog
from harness.ui.model import AppSurface, AppSurfaceTab
from harness.ui.service import UiService
from harness.ui.store import UiStore


def test_q1_map_reports_fixed_screens_separately_from_saved_pages(tmp_path):
    memory = AgentMemoryStore(str(tmp_path / "agent-memory.db"))
    try:
        ui = UiService(UiStore(memory), UiCatalog())
        ui.register_surfaces([
            AppSurface(
                id="memory", label="Eclipse Memory", deep_link="/?tab=memory",
                tabs=[AppSurfaceTab(id="memory.reviews", label="Reviews", deep_link="/?tab=memory&sub=memory.reviews")],
            ),
        ])
        app_map = ui.get_application_map()
        assert [screen["id"] for screen in app_map["screens"]] == ["memory"]
        assert app_map["screens"][0]["tabs"][0]["deepLink"] == "/?tab=memory&sub=memory.reviews"
        assert app_map["pages"] == []
    finally:
        memory.close()


def test_q2_learning_reads_are_registered_and_read_only():
    registry = ToolRegistry()
    register_memory_tools(registry)
    for name in ("learning_review_list", "learning_candidate_list"):
        tool = registry.get(name)
        assert tool is not None
        assert tool.permission == "read"


def test_q2_banner_opens_the_in_app_learning_queue():
    eligibility = _eligibility_dict(
        "run_1", eligible=False, reason="no tool use", steps=1, tool_calls=0, skill_requested=False,
    )
    assert eligibility["learnQueuePath"] == "/?tab=skills&sub=skills.learning"


def test_q2_q4_tools_survive_the_chat_code_profile():
    for name in ("learning_review_list", "learning_candidate_list", "app_api_get", *UI_TOOLS):
        assert name in CHAT_CODE_TOOLS


def test_q3_memory_advertises_the_inventory_action():
    registry = ToolRegistry()
    register_memory_tools(registry)
    actions = registry.get("memory").input_schema["properties"]["action"]["enum"]
    assert "inventory" in actions


def test_q4_local_app_reads_are_bounded_and_advertised():
    registry = ToolRegistry()
    assert register_app_api_tools(registry) == ["app_api_get"]
    assert registry.get("app_api_get").permission == "read"


def test_q5_chat_budget_defaults_to_twelve(monkeypatch):
    from harness.agents import ECLIPSE_AGENT

    monkeypatch.delenv("ECLIPSE_CHAT_MAX_STEPS", raising=False)
    assert chat_step_budget(ECLIPSE_AGENT, SimpleNamespace(agent=None)) == 12
