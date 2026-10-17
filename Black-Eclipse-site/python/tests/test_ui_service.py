"""UI service tests — the authority: catalog, blueprints, mutations, recovery."""

from __future__ import annotations

import time

import pytest

from harness.persistence import AgentMemoryStore
from harness.ui.catalog import UiCatalog
from harness.ui.model import (
    AddWidgetInput,
    CatalogQuery,
    CreatePageInput,
    DropTarget,
    ListBlueprintsQuery,
    RestoreRevisionInput,
    SaveLayoutInput,
    UiComponentSpec,
    UpdateConfigInput,
    UpdatePageInput,
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


def test_catalog_search_uses_word_boundaries(ui):
    # "form" must not match "performance" — an interactive search must not return
    # unrelated charts (the word-boundary fix).
    assert all("performance" not in c.id for c in ui.list_components(CatalogQuery(text="form")))


def test_create_page_titles_are_unique(ui):
    # A create never adds a second page sharing a title; a duplicate is suffixed.
    a = ui.create_page(CreatePageInput(title="Main"))
    b = ui.create_page(CreatePageInput(title="Main"))
    c = ui.create_page(CreatePageInput(title="Main"))
    assert (a.title, b.title, c.title) == ("Main", "Main 2", "Main 3")
    # The summary still carries id + widget count + component ids.
    _add(ui, b.id, "metric-card")
    result = ui.list_blueprints(ListBlueprintsQuery())
    by_id = {s["id"]: s for s in result["blueprints"]}
    assert by_id[b.id]["title"] == "Main 2"
    assert by_id[b.id]["widgetCount"] == 1
    assert by_id[b.id]["componentIds"] == ["metric-card"]


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
    # A page WITH a path exists, but none matches -> genuinely not found (as
    # opposed to there being no path assigned anywhere — see the test below).
    ui.create_page(CreatePageInput(title="Portfolio", path="/portfolio"))
    with pytest.raises(UiError) as exc:
        ui.get_current_page(path="/does-not-exist")
    assert exc.value.code == "UI_BLUEPRINT_NOT_FOUND"


def test_get_current_page_default_is_most_recent_and_surfaces_choice(ui):
    # Defect 1: with neither id nor path, the lookup must resolve a real default
    # (most recently updated) and name it, never silently return row 1.
    first = ui.create_page(CreatePageInput(title="Main")).id
    time.sleep(0.01)  # ensure updatedAt differs (now_iso has ms resolution)
    second = ui.create_page(CreatePageInput(title="Main")).id
    page = ui.get_current_page()
    assert page["resolution"] == "default_most_recent"
    assert page["blueprint"]["id"] == second
    assert second != first
    assert any(c["id"] == first for c in page["candidates"])


def test_get_current_page_title_resolves_and_disambiguates(ui):
    first = ui.create_page(CreatePageInput(title="Main")).id
    time.sleep(0.01)
    second = ui.create_page(CreatePageInput(title="Ledger")).id
    # A CREATE never duplicates a title now; force a duplicate via an EDIT.
    ui.update_page(second, UpdatePageInput(title="Main"))
    # Ambiguous title -> most recently updated, with the others offered.
    page = ui.get_current_page(title="Main")
    assert page["resolution"] == "title_ambiguous"
    assert page["blueprint"]["id"] == second
    assert [c["id"] for c in page["candidates"]] == [first]
    # Exact/unique title -> unambiguous.
    ui.create_page(CreatePageInput(title="Ledger"))
    only = ui.get_current_page(title="ledger")  # case-insensitive
    assert only["resolution"] == "title"
    assert only["blueprint"]["title"] == "Ledger"
    assert only["candidates"] == []


def test_get_current_page_path_is_normalised(ui):
    ui.create_page(CreatePageInput(title="Portfolio", path="/Portfolio/"))
    page = ui.get_current_page(path="portfolio")
    assert page["resolution"] == "path"
    assert page["blueprint"]["path"] == "/Portfolio/"


def test_get_current_page_path_unassigned_is_distinct(ui):
    # Defect 2: every page here has path=None, so a path lookup must say so
    # (actionable) rather than claim a matching page does not exist.
    _page(ui)
    with pytest.raises(UiError) as exc:
        ui.get_current_page(path="/portfolio")
    assert exc.value.code == "UI_BLUEPRINT_PATH_UNASSIGNED"


def test_get_blueprint_owner_mismatch_is_distinct(ui):
    # Defect 3: a scope mismatch must be its own error, never "unknown blueprint".
    blueprint_id = ui.create_page(CreatePageInput(title="Mine"), owner_id="alice").id
    with pytest.raises(UiError) as exc:
        ui.get_blueprint(blueprint_id, owner_id="bob")
    assert exc.value.code == "UI_BLUEPRINT_OWNER_MISMATCH"
    with pytest.raises(UiError) as missing:
        ui.get_current_page(blueprint_id="does-not-exist", owner_id="bob")
    assert missing.value.code == "UI_BLUEPRINT_NOT_FOUND"


def test_page_icon_round_trips(ui):
    page_id = ui.create_page(CreatePageInput(title="With icon", icon="wallet")).id
    assert ui.get_blueprint(page_id).icon == "wallet"
    listed = next(b for b in ui.list_blueprints()["blueprints"] if b["id"] == page_id)
    assert listed["icon"] == "wallet"
    updated = ui.update_page(page_id, UpdatePageInput(icon="activity"))
    assert updated.icon == "activity"


def test_blueprint_summary_carries_path_and_components(ui):
    # Defect 4: pages that share a title are distinguishable via path + widgets.
    ui.create_page(CreatePageInput(title="Main", path="/main-a"))
    page_id = ui.create_page(CreatePageInput(title="Main", path="/main-b")).id
    _add(ui, page_id, "metric-card", "m1")
    listed = ui.list_blueprints()["blueprints"]
    match = next(b for b in listed if b["id"] == page_id)
    assert match["path"] == "/main-b"
    assert match["componentIds"] == ["metric-card"]


def test_verify_page_validates_every_source_family(ui):
    page = ui.create_page(CreatePageInput(title="Sources")).id
    _add(ui, page, "line-chart", "c1")
    ui.update_widget_config(UpdateConfigInput(blueprint_id=page, instance_id="c1", patch={"source": "market:nope:AAPL"}))
    bad = ui.verify_page(page)
    assert bad["renderable"] is False
    inst = next(i for i in bad["instances"] if i["instanceId"] == "c1")
    assert inst["sourceValid"] is False
    assert "market" in (inst["sourceReason"] or "")

    ui.update_widget_config(UpdateConfigInput(blueprint_id=page, instance_id="c1", patch={"source": "market:price:AAPL"}))
    assert ui.verify_page(page)["renderable"] is True

    _add(ui, page, "data-table", "t1")
    ui.update_widget_config(UpdateConfigInput(blueprint_id=page, instance_id="t1", patch={"source": "tasks:list"}))
    assert ui.verify_page(page)["renderable"] is True

    ui.update_widget_config(UpdateConfigInput(blueprint_id=page, instance_id="t1", patch={"source": "bogus:list"}))
    assert ui.verify_page(page)["renderable"] is False


def test_builtin_catalog_is_exactly_the_renderable_set(ui):
    # Cross-language parity: the seed catalog must equal RENDERABLE_COMPONENTS so
    # the runtime never advertises a component the host cannot render. The same
    # list is asserted on the TS side (`src/lib/workspace/generic-widgets.test.ts`).
    from harness.ui.catalog import RENDERABLE_COMPONENTS, builtin_specs

    ids = {spec.id for spec in builtin_specs()}
    assert ids == set(RENDERABLE_COMPONENTS)


def test_verify_page_reports_renderable_widgets_and_sources(ui):
    page_id = ui.create_page(CreatePageInput(title="Ledger")).id
    _add(ui, page_id, "data-table", "t1")
    ui.update_widget_config(UpdateConfigInput(
        blueprint_id=page_id, instance_id="t1",
        patch={"source": "portfolio:pf_7586246984d44b11bfb8:positions"},
    ))
    _add(ui, page_id, "metric-card", "m1")
    ui.update_widget_config(UpdateConfigInput(
        blueprint_id=page_id, instance_id="m1",
        patch={"portfolioId": "pf_7586246984d44b11bfb8"},
    ))
    result = ui.verify_page(page_id)
    assert result["renderable"] is True
    by_id = {i["instanceId"]: i for i in result["instances"]}
    assert by_id["t1"]["sourceValid"] is True
    assert by_id["m1"]["componentAvailable"] is True

    # A malformed portfolio source is reported as not renderable.
    ui.update_widget_config(UpdateConfigInput(
        blueprint_id=page_id, instance_id="t1", patch={"source": "portfolio:nope"},
    ))
    bad = ui.verify_page(page_id)
    assert bad["renderable"] is False
    flagged = next(i for i in bad["instances"] if i["instanceId"] == "t1")
    assert flagged["sourceValid"] is False
    assert flagged["sourceReason"]


def test_data_source_registry_documents_portfolio_sources(ui):
    registry = ui.list_data_sources()["portfolio"]
    assert registry["example"] == "portfolio:pf_7586246984d44b11bfb8:positions"
    assert "positions" in registry["views"]
    assert ui.list_components(CatalogQuery(data_source="portfolio"))
    assert "portfolio" in ui.get_capabilities()["dataSources"]
