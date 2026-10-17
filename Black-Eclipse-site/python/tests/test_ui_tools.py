"""UI tool tests — registration on the shared registry and handler behavior."""

from __future__ import annotations

import asyncio
import time

import pytest

from harness.persistence import AgentMemoryStore
from harness.tools import ToolContext, ToolRegistry
from harness.ui.bootstrap import set_ui_service
from harness.ui.catalog import UiCatalog
from harness.ui.model import CreatePageInput, UpdatePageInput
from harness.ui.service import UiService
from harness.ui.store import UiStore
from harness.ui.tools import (
    UI_TOOLS,
    _add_widget,
    _create_page,
    _get_application_map,
    _get_capabilities,
    _get_component_catalog,
    _get_current_page,
    _list_blueprints,
    register_ui_tools,
)


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _ctx() -> ToolContext:
    return ToolContext(run_id="run-ui", log=lambda *_: None)


@pytest.fixture()
def service(tmp_path):
    memory = AgentMemoryStore(str(tmp_path / "agent-memory.db"))
    ui = UiService(UiStore(memory), UiCatalog())
    set_ui_service(ui)
    yield ui
    set_ui_service(None)
    memory.close()


def test_register_ui_tools():
    registry = ToolRegistry()
    names = register_ui_tools(registry)
    assert set(names) == set(UI_TOOLS)
    assert all(name.replace("_", "").isalnum() for name in names)
    # Idempotent: a second registration adds nothing.
    assert register_ui_tools(registry) == []


def test_tool_create_add_and_inspect(service):
    text, data = _run(_create_page({"title": "Ops"}, _ctx()))
    assert "Created page" in text
    blueprint_id = data["blueprint"]["id"]

    _, catalog = _run(_get_component_catalog({"text": "table"}, _ctx()))
    assert any(c["id"] == "data-table" for c in catalog["components"])

    text, _ = _run(_add_widget({"blueprintId": blueprint_id, "componentId": "metric-card", "instanceId": "m1"}, _ctx()))
    assert "Added metric-card" in text

    _, current = _run(_get_current_page({"blueprintId": blueprint_id}, _ctx()))
    assert current["instances"][0]["instanceId"] == "m1"


def test_list_blueprints_text_includes_the_id(service):
    # The agent must be able to NAME the page it edits: the text line carries the id,
    # not just a count.
    _, created = _run(_create_page({"title": "Ops"}, _ctx()))
    blueprint_id = created["blueprint"]["id"]
    text, data = _run(_list_blueprints({}, _ctx()))
    assert blueprint_id in text
    assert any(b["id"] == blueprint_id for b in data["blueprints"])


def test_application_map_text_names_pages(service):
    _, created = _run(_create_page({"title": "Ops"}, _ctx()))
    blueprint_id = created["blueprint"]["id"]
    text, _ = _run(_get_application_map({}, _ctx()))
    assert blueprint_id in text


def test_get_current_page_by_path_resolves_a_page(service):
    service.create_page(CreatePageInput(title="Portfolio", path="/portfolio"))
    _text, data = _run(_get_current_page({"path": "/portfolio"}, _ctx()))
    assert data["blueprint"]["title"] == "Portfolio"
    assert data["blueprint"]["path"] == "/portfolio"


def test_get_current_page_defaults_and_says_which(service):
    service.create_page(CreatePageInput(title="First"))
    time.sleep(0.01)
    second = service.create_page(CreatePageInput(title="Second")).id
    text, data = _run(_get_current_page({}, _ctx()))
    assert data["resolution"] == "default_most_recent"
    assert data["blueprint"]["id"] == second
    assert second in text


def test_get_current_page_by_title_disambiguates(service):
    service.create_page(CreatePageInput(title="Main"))
    time.sleep(0.01)
    second = service.create_page(CreatePageInput(title="Ledger")).id
    # A CREATE never duplicates a title now; force a duplicate via an EDIT.
    service.update_page(second, UpdatePageInput(title="Main"))
    text, data = _run(_get_current_page({"title": "Main"}, _ctx()))
    assert data["resolution"] == "title_ambiguous"
    assert data["blueprint"]["id"] == second
    assert "title" in text


def test_get_current_page_path_unassigned_reports_code(service):
    service.create_page(CreatePageInput(title="NoPath"))
    text, payload = _run(_get_current_page({"path": "/nope"}, _ctx()))
    assert payload["error"] == "UI_BLUEPRINT_PATH_UNASSIGNED"
    assert "UI_BLUEPRINT_PATH_UNASSIGNED" in text


def test_tool_reports_unknown_component(service):
    _, data = _run(_create_page({"title": "Ops"}, _ctx()))
    blueprint_id = data["blueprint"]["id"]
    _, payload = _run(_add_widget({"blueprintId": blueprint_id, "componentId": "ghost"}, _ctx()))
    assert payload["error"] == "UI_OPERATION_INVALID"


def test_tools_report_unavailable_without_service():
    set_ui_service(None)
    text, payload = _run(_get_capabilities({}, _ctx()))
    assert payload["error"] == "UI_UNAVAILABLE"
    assert "UI_UNAVAILABLE" in text
