"""App-surface inventory — the runtime's map of the app's FIXED screens.

The agent-facing `ui_get_application_map` used to list only saved dashboards,
so "Memory -> Reviews" appeared not to exist. These tests pin the synced screen
inventory, its separation from user pages, and its survival across restarts.
"""

from __future__ import annotations

import asyncio

import pytest

from harness.persistence import AgentMemoryStore
from harness.tools import ToolContext
from harness.ui.bootstrap import set_ui_service
from harness.ui.catalog import UiCatalog
from harness.ui.model import AppSurface, AppSurfaceTab, CreatePageInput
from harness.ui.service import UiService
from harness.ui.store import UiStore
from harness.ui.tools import _get_application_map


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


SAMPLE = [
    AppSurface(
        id="memory",
        label="Eclipse Memory",
        deep_link="/?tab=memory",
        tabs=[
            AppSurfaceTab(
                id="memory.reviews",
                label="Learning Reviews",
                deep_link="/?tab=memory&sub=memory.reviews",
            ),
        ],
    ),
    AppSurface(
        id="skills",
        label="Skills",
        deep_link="/?tab=skills",
        tabs=[
            AppSurfaceTab(
                id="skills.learning",
                label="Learning Queue",
                deep_link="/?tab=skills&sub=skills.learning",
            ),
        ],
    ),
]


@pytest.fixture()
def ui(tmp_path):
    memory = AgentMemoryStore(str(tmp_path / "agent-memory.db"))
    service = UiService(UiStore(memory), UiCatalog())
    set_ui_service(service)
    yield service
    set_ui_service(None)
    memory.close()


def test_register_surfaces_and_map(ui):
    assert ui.register_surfaces(SAMPLE) == {"total": 2, "registered": 2}
    app_map = ui.get_application_map()
    assert [s["id"] for s in app_map["screens"]] == ["memory", "skills"]
    memory = app_map["screens"][0]
    assert memory["label"] == "Eclipse Memory"
    assert memory["tabs"][0]["deepLink"] == "/?tab=memory&sub=memory.reviews"


def test_surfaces_survive_a_reopen(tmp_path):
    db = str(tmp_path / "agent-memory.db")
    memory = AgentMemoryStore(db)
    try:
        UiService(UiStore(memory), UiCatalog()).register_surfaces(SAMPLE)
    finally:
        memory.close()

    reopened = AgentMemoryStore(db)
    try:
        app_map = UiService(UiStore(reopened), UiCatalog()).get_application_map()
        assert {s["id"] for s in app_map["screens"]} == {"memory", "skills"}
        assert app_map["screens"][1]["tabs"][0]["id"] == "skills.learning"
    finally:
        reopened.close()


def test_replacing_surfaces_drops_stale_screens(ui):
    ui.register_surfaces(SAMPLE)
    ui.register_surfaces([SAMPLE[0]])
    assert [s["id"] for s in ui.get_application_map()["screens"]] == ["memory"]


def test_empty_batch_never_wipes_the_inventory(ui):
    ui.register_surfaces(SAMPLE)
    assert ui.register_surfaces([]) == {"total": 0, "registered": 0}
    assert [s["id"] for s in ui.get_application_map()["screens"]] == ["memory", "skills"]


def test_map_keeps_saved_pages_separate_from_screens(ui):
    ui.create_page(CreatePageInput(title="Main"))
    ui.register_surfaces(SAMPLE)
    app_map = ui.get_application_map()
    assert [s["id"] for s in app_map["screens"]] == ["memory", "skills"]
    assert app_map["pageCount"] == 1
    assert app_map["pages"][0]["title"] == "Main"


def test_tool_text_names_screens_tabs_and_deep_links(ui):
    ui.register_surfaces(SAMPLE)
    text, data = _run(_get_application_map({}, ToolContext(run_id="run-ui", log=lambda *_: None)))
    assert "Eclipse Memory" in text
    assert "Learning Reviews" in text
    assert "/?tab=memory&sub=memory.reviews" in text
    assert "Saved pages" in text
    assert data["screens"][0]["tabs"][0]["id"] == "memory.reviews"
