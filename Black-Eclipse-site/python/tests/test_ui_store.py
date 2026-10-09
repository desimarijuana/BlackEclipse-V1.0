"""UI store tests — durable blueprints, revisions, components, operations."""

from __future__ import annotations

import pytest

from harness.persistence import AgentMemoryStore, now_iso
from harness.ui.model import (
    BlueprintKind,
    BlueprintScope,
    ListBlueprintsQuery,
    UiBlueprint,
    UiComponentSpec,
    UiOperation,
    WorkspaceColumn,
    WorkspaceLayout,
    WorkspaceSection,
)
from harness.ui.store import UiStore


def _layout() -> WorkspaceLayout:
    return WorkspaceLayout(version=2, sections=[WorkspaceSection(id="s1", zone="main", columns=[WorkspaceColumn(id="c1", weight=3, widgets=[])])])


def _blueprint(bid: str = "uibp-1", title: str = "Home") -> UiBlueprint:
    now = now_iso()
    return UiBlueprint(id=bid, title=title, kind=BlueprintKind.PAGE, scope=BlueprintScope.PERSONAL, layout=_layout(), revision=1, createdAt=now, updatedAt=now)


@pytest.fixture()
def store(tmp_path):
    memory = AgentMemoryStore(str(tmp_path / "agent-memory.db"))
    yield UiStore(memory)
    memory.close()


def test_save_and_get_blueprint(store):
    store.save_blueprint(_blueprint(), summary="created")
    found = store.get_blueprint("uibp-1")
    assert found is not None and found.title == "Home"
    assert store.get_blueprint("nope") is None


def test_owner_scoping(store):
    store.save_blueprint(_blueprint())
    assert store.get_blueprint("uibp-1", owner_id="someone") is None
    assert store.get_blueprint("uibp-1", owner_id="operator") is not None


def test_list_and_filter(store):
    store.save_blueprint(_blueprint("a", "A"))
    bp = _blueprint("b", "B")
    bp.scope = BlueprintScope.SHARED
    bp.kind = BlueprintKind.WORKSPACE
    store.save_blueprint(bp)
    assert len(store.list_blueprints(ListBlueprintsQuery())[0]) == 2
    assert len(store.list_blueprints(ListBlueprintsQuery(scope=BlueprintScope.SHARED))[0]) == 1
    assert len(store.list_blueprints(ListBlueprintsQuery(kind=BlueprintKind.WORKSPACE))[0]) == 1
    assert len(store.list_blueprints(ListBlueprintsQuery(q="A"))[0]) == 1


def test_revision_history_and_get_revision(store):
    store.save_blueprint(_blueprint())
    updated = _blueprint()
    updated.title = "Home 2"
    updated.revision = 2
    store.save_blueprint(updated, summary="renamed")
    history = store.history("uibp-1")
    assert [h["revision"] for h in history] == [2, 1]
    assert store.get_revision("uibp-1", 1).title == "Home"
    assert store.get_revision("uibp-1", 99) is None


def test_components_roundtrip(store):
    spec = UiComponentSpec(id="market-heatmap", display_name="Heatmap", category="markets", owner="plugin", plugin_id="hello")
    store.upsert_component(spec)
    found = store.get_component("market-heatmap")
    assert found is not None and found.owner.value == "plugin" and found.plugin_id == "hello"
    assert [c.id for c in store.list_components()] == ["market-heatmap"]
    assert store.delete_component("market-heatmap") is True


def test_operations_record(store):
    op = UiOperation(id="uiop-1", operation="add_widget", blueprint_id="uibp-1", status="completed", created_at=now_iso())
    store.record_operation(op)
    found = store.get_operation("uiop-1")
    assert found is not None and found.operation == "add_widget" and found.status == "completed"


def test_idempotency(store):
    store.record_idempotency("k1", "uibp-1")
    assert store.lookup_idempotency("k1") == "uibp-1"
    assert store.lookup_idempotency("k2") is None


def test_delete_blueprint(store):
    store.save_blueprint(_blueprint())
    assert store.delete_blueprint("uibp-1") is True
    assert store.delete_blueprint("uibp-1") is False
    assert store.get_blueprint("uibp-1") is None
