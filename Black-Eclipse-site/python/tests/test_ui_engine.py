"""UI engine tests — strict validation, atomic mutation and diff."""

from __future__ import annotations

from harness.persistence import now_iso
from harness.ui.catalog import UiCatalog
from harness.ui.engine import apply_ops, diff_blueprints, validate_blueprint, widget_count
from harness.ui.model import (
    Availability,
    ConfigFieldSpec,
    UiBlueprint,
    UiComponentSpec,
    WorkspaceColumn,
    WorkspaceLayout,
    WorkspaceSection,
    WidgetPlacement,
)


def _catalog() -> UiCatalog:
    return UiCatalog([
        UiComponentSpec(id="metric-card", display_name="Metric", category="metrics",
                        config_schema=[ConfigFieldSpec(key="limit", label="Limit", kind="number", min=1, max=10)]),
        UiComponentSpec(id="news-feed", display_name="News", category="news", data_sources=["news:feed"]),
        UiComponentSpec(id="stub", display_name="Stub", category="tools", availability=Availability.UNAVAILABLE),
    ])


def _layout(widget_ids: list[str]) -> WorkspaceLayout:
    return WorkspaceLayout(
        version=2,
        sections=[WorkspaceSection(id="s1", zone="main", columns=[
            WorkspaceColumn(id="c1", weight=3, widgets=[WidgetPlacement(id=f"w{i}", widgetId=w) for i, w in enumerate(widget_ids)]),
            WorkspaceColumn(id="c2", weight=3, widgets=[]),
        ])],
    )


def _blueprint(widget_ids: list[str] = ["metric-card"]) -> UiBlueprint:
    now = now_iso()
    return UiBlueprint(id="uibp-1", title="Home", layout=_layout(widget_ids), revision=1, createdAt=now, updatedAt=now)


def test_validate_blueprint_accepts_valid():
    result = validate_blueprint(_blueprint().model_dump(by_alias=True), _catalog())
    assert result.ok and result.blueprint is not None


def test_validate_blueprint_rejects_unknown_component():
    result = validate_blueprint(_blueprint(["ghost"]).model_dump(by_alias=True), _catalog())
    assert not result.ok
    assert any("unknown component" in i.message for i in result.issues)


def test_validate_blueprint_rejects_duplicate_instance():
    bp = _blueprint(["metric-card", "news-feed"])
    bp.layout.sections[0].columns[0].widgets[1].id = "w0"
    result = validate_blueprint(bp.model_dump(by_alias=True), _catalog())
    assert not result.ok
    assert any("duplicate instance id" in i.message for i in result.issues)


def test_validate_blueprint_rejects_bad_config():
    bp = _blueprint()
    bp.layout.sections[0].columns[0].widgets[0].config = {"limit": 999}
    result = validate_blueprint(bp.model_dump(by_alias=True), _catalog())
    assert not result.ok
    assert any("maximum" in i.message for i in result.issues)


def test_validate_blueprint_rejects_future_schema():
    payload = _blueprint().model_dump(by_alias=True)
    payload["schemaVersion"] = 99
    result = validate_blueprint(payload, _catalog())
    assert not result.ok and "newer than supported" in result.issues[0].message


def test_apply_add_widget_and_bump_revision():
    result = apply_ops(_blueprint(), [{"op": "add_widget", "componentId": "news-feed", "instanceId": "x1",
                                       "target": {"sectionId": "s1", "columnId": "c2", "index": 0}}], catalog=_catalog())
    assert result.ok and result.applied == 1 and result.blueprint.revision == 2
    assert widget_count(result.blueprint.layout) == 2


def test_apply_rejects_unknown_component_atomically():
    start = _blueprint()
    result = apply_ops(start, [{"op": "add_widget", "componentId": "ghost"}], catalog=_catalog())
    assert not result.ok and result.blueprint is start and result.blueprint.revision == 1


def test_apply_is_atomic_across_batch():
    start = _blueprint()
    result = apply_ops(start, [
        {"op": "add_widget", "componentId": "news-feed", "instanceId": "x1"},
        {"op": "remove_widget", "instanceId": "missing"},
    ], catalog=_catalog())
    assert not result.ok and result.blueprint is start


def test_apply_move_resize_config_duplicate_remove():
    add = apply_ops(_blueprint(), [{"op": "add_widget", "componentId": "news-feed", "instanceId": "x1",
                                    "target": {"sectionId": "s1", "columnId": "c1", "index": 0}}], catalog=_catalog())
    batch = apply_ops(add.blueprint, [
        {"op": "move_widget", "instanceId": "x1", "target": {"sectionId": "s1", "columnId": "c2", "index": 0}},
        {"op": "resize_widget", "instanceId": "w0", "height": 320},
        {"op": "update_config", "instanceId": "w0", "patch": {"limit": 5}},
        {"op": "duplicate_widget", "instanceId": "w0"},
    ], catalog=_catalog())
    assert batch.ok
    moved = batch.blueprint.layout.sections[0].columns[1]
    assert any(w.id == "x1" for w in moved.widgets)
    removed = apply_ops(batch.blueprint, [{"op": "remove_widget", "instanceId": "x1"}], catalog=_catalog())
    assert removed.ok and widget_count(removed.blueprint.layout) == 2


def test_apply_meta_and_columns():
    result = apply_ops(_blueprint(), [
        {"op": "update_meta", "title": "Renamed"},
        {"op": "set_column_count", "sectionId": "s1", "count": 3},
    ], catalog=_catalog())
    assert result.ok and result.blueprint.title == "Renamed"
    assert len(result.blueprint.layout.sections[0].columns) == 3


def test_diff_blueprints():
    before = _blueprint(["metric-card"])
    after = apply_ops(before, [{"op": "add_widget", "componentId": "news-feed", "instanceId": "x1"}], catalog=_catalog()).blueprint
    after.title = "Home 2"
    types = {c.type.value for c in diff_blueprints(before, after)}
    assert "add_widget" in types and "meta_changed" in types
