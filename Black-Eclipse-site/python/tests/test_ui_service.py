"""UI service tests — the authority: catalog, blueprints, mutations, recovery."""

from __future__ import annotations

import pytest

from harness.persistence import AgentMemoryStore
from harness.ui.catalog import UiCatalog
from harness.ui.model import (
    AddWidgetInput,
    CatalogQuery,
    CreatePageInput,
    DropTarget,
    RestoreRevisionInput,
    SaveLayoutInput,
    UiComponentSpec,
    UpdateConfigInput,
    WorkspaceColumn,
    WorkspaceLayout,
    WorkspaceSection,
)
from harness.ui.service import UiError, UiService
from harness.ui.store import UiStore


@pytest.fixture()
def ui(tmp_path):
    memory = AgentMemoryStore(str(tmp_path / "agent-memory.db"))
    service = UiService(UiStore(memory), UiCatalog())
    yield service
    memory.close()


def _page(ui: UiService) -> str:
    return ui.create_page(CreatePageInput(title="Trading Desk")).id


def _add(ui: UiService, blueprint_id: str, component_id: str, instance_id: str | None = None):
    return ui.add_widget(AddWidgetInput(blueprint_id=blueprint_id, component_id=component_id, instance_id=instance_id))


def test_catalog_seeded_and_searchable(ui):
    assert ui.inspect_component("metric-card").category == "metrics"
    assert any(c.id == "data-table" for c in ui.list_components(CatalogQuery(text="table")))
    assert "metrics" in ui.get_capabilities()["categories"]


def test_register_component(ui):
    spec = UiComponentSpec(id="my-widget", display_name="Mine", category="custom", owner="plugin", plugin_id="p1")
    ui.register_component(spec)
    assert ui.inspect_component("my-widget").owner.value == "plugin"
    with pytest.raises(UiError):
        ui.inspect_component("ghost")


def test_create_page_and_add_widget(ui):
    blueprint_id = _page(ui)
    result = _add(ui, blueprint_id, "metric-card", "m1")
    assert result.revision == 2
    instances = ui.get_current_page(blueprint_id=blueprint_id)["instances"]
    assert instances[0]["componentId"] == "metric-card"


def test_add_unknown_component_rejected(ui):
    blueprint_id = _page(ui)
    with pytest.raises(UiError) as exc:
        _add(ui, blueprint_id, "ghost")
    assert exc.value.code == "UI_OPERATION_INVALID"


def test_optimistic_concurrency_conflict(ui):
    blueprint_id = _page(ui)
    _add(ui, blueprint_id, "metric-card", "m1")  # revision now 2
    with pytest.raises(UiError) as exc:
        ui.add_widget(AddWidgetInput(blueprint_id=blueprint_id, component_id="data-table", expected_revision=1))
    assert exc.value.code == "UI_CONFLICT"


def test_restore_revision(ui):
    blueprint_id = _page(ui)
    _add(ui, blueprint_id, "metric-card", "m1")  # r2
    _add(ui, blueprint_id, "data-table", "t1")   # r3
    restored = ui.restore_revision(RestoreRevisionInput(blueprint_id=blueprint_id, revision=2))
    assert restored.revision == 4
    assert len(ui.get_current_page(blueprint_id=blueprint_id)["instances"]) == 1


def test_preview_does_not_persist(ui):
    blueprint_id = _page(ui)
    before = ui.get_blueprint(blueprint_id).revision
    preview = ui.preview(blueprint_id, [{"op": "add_widget", "componentId": "metric-card", "instanceId": "p1"}])
    assert preview["currentRevision"] == before
    assert ui.get_blueprint(blueprint_id).revision == before


def test_config_validation(ui):
    blueprint_id = _page(ui)
    _add(ui, blueprint_id, "data-table", "d1")
    updated = ui.update_widget_config(UpdateConfigInput(blueprint_id=blueprint_id, instance_id="d1", patch={"pageSize": 50}))
    assert updated.revision == 3
    with pytest.raises(UiError):
        ui.update_widget_config(UpdateConfigInput(blueprint_id=blueprint_id, instance_id="d1", patch={"pageSize": 9999}))


def test_save_layout(ui):
    blueprint_id = _page(ui)
    layout = WorkspaceLayout(version=2, sections=[WorkspaceSection(id="s1", zone="main", columns=[WorkspaceColumn(id="c1", weight=3, widgets=[])])])
    saved = ui.save_layout(SaveLayoutInput(blueprint_id=blueprint_id, layout=layout))
    assert saved.revision == 2


def test_application_map_and_operation_audit(ui):
    _page(ui)
    app_map = ui.get_application_map()
    assert app_map["pageCount"] == 1
    assert app_map["capabilities"]["componentCount"] >= 1


def test_get_current_page_by_path_resolves_full_blueprint(ui):
    # Regression: the path branch read `entry.path` off a BlueprintSummary (which
    # has no `path`) and raised AttributeError, so no path lookup ever worked.
    ui.create_page(CreatePageInput(title="Portfolio", path="/portfolio"))
    page = ui.get_current_page(path="/portfolio")
    assert page["blueprint"]["title"] == "Portfolio"
    assert page["blueprint"]["path"] == "/portfolio"


def test_get_current_page_unknown_path_is_not_found(ui):
    _page(ui)
    with pytest.raises(UiError) as exc:
        ui.get_current_page(path="/does-not-exist")
    assert exc.value.code == "UI_BLUEPRINT_NOT_FOUND"
