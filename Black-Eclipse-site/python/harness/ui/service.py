"""UI Service — the ONE authority for the UI Engineering runtime.

Frontend-agnostic: the routes, the agent tools and producers all call this
object. It composes three collaborators — the component catalog (what can be
composed), the engine (validation + atomic mutation) and the store (durable
state) — and adds the cross-cutting concerns every operation needs: optimistic
concurrency, an operation audit record, structured errors and best-effort
events. It owns no second connection and no second layout engine.
"""

from __future__ import annotations

import json
from typing import Any, Optional

from ..persistence import new_id, now_iso
from .catalog import CatalogError, UiCatalog, validate_component_config
from .engine import apply_ops as engine_apply_ops, diff_blueprints, validate_blueprint, widget_count
from .engineering import UiEngineering
from .mode import classify_request as _classify_request
from .model import (
    AddWidgetInput,
    BlueprintOwner,
    BlueprintScope,
    CatalogQuery,
    CreatePageInput,
    ListBlueprintsQuery,
    MAX_CONFIG_BYTES,
    MoveWidgetInput,
    ReorderWidgetInput,
    RestoreRevisionInput,
    ResizeWidgetInput,
    SaveLayoutInput,
    SectionRefInput,
    SetColumnCountInput,
    SetColumnWeightInput,
    Severity,
    UiBlueprint,
    UiComponentSpec,
    UiEventType,
    UiOperation,
    UpdateConfigInput,
    UpdatePageInput,
    WidgetRefInput,
    WorkspaceColumn,
    WorkspaceLayout,
    WorkspaceSection,
)


class UiError(Exception):
    def __init__(self, code: str, message: str, *, issues: Optional[list[dict[str, Any]]] = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.issues = issues or []


def _publish(event_type: str, payload: dict[str, Any]) -> None:
    try:
        from ..event_system.emit import publish_event  # noqa: PLC0415

        publish_event(event_type, payload, source="ui")
    except Exception:  # noqa: BLE001 - telemetry must never break a mutation
        pass


def _empty_layout() -> WorkspaceLayout:
    return WorkspaceLayout(
        version=2,
        sections=[WorkspaceSection(id=new_id("sec"), zone="main", columns=[WorkspaceColumn(id=new_id("col"), weight=3, widgets=[])])],
    )


class UiService:
    def __init__(self, store: Any, catalog: Optional[UiCatalog] = None, tasks: Any = None) -> None:
        self._store = store
        self._catalog = catalog or UiCatalog()
        # Phase 7: the Engineer-mode orchestration rides the EXISTING Task/Plan
        # runtime (never a second loop). `tasks` is the shared TaskManager; None
        # simply means engineering is unavailable (the tools report it honestly).
        self.engineering = UiEngineering(self, tasks)
        self._hydrate_registered_components()

    def _hydrate_registered_components(self) -> None:
        for spec in self._store.list_components():
            try:
                self._catalog.register(spec, replace=True)
            except CatalogError:
                continue

    @property
    def catalog(self) -> UiCatalog:
        return self._catalog

    # ── catalog ───────────────────────────────────────────────────────────────

    def list_components(self, query: Optional[CatalogQuery] = None) -> list[UiComponentSpec]:
        return self._catalog.search(query or CatalogQuery())

    def inspect_component(self, component_id: str) -> UiComponentSpec:
        spec = self._catalog.get(component_id)
        if spec is None:
            raise UiError("UI_COMPONENT_NOT_FOUND", f'unknown component "{component_id}"')
        return spec

    def validate_config(self, component_id: str, config: Optional[dict[str, Any]]) -> list[dict[str, Any]]:
        spec = self._catalog.get(component_id)
        if spec is None:
            raise UiError("UI_COMPONENT_NOT_FOUND", f'unknown component "{component_id}"')
        return [i.model_dump(by_alias=True) for i in validate_component_config(spec, config)]

    def register_component(self, spec: UiComponentSpec, *, actor: Optional[str] = None) -> UiComponentSpec:
        try:
            self._catalog.register(spec, replace=True)
        except CatalogError as exc:
            raise UiError(exc.code, exc.message) from exc
        self._store.upsert_component(spec)
        self._record("register_component", None, "completed", actor, detail=f"registered {spec.id}", result={"componentId": spec.id})
        _publish(UiEventType.COMPONENT_REGISTERED.value, {"componentId": spec.id, "owner": spec.owner.value})
        return spec

    def get_capabilities(self) -> dict[str, Any]:
        components = self._catalog.list()
        return {
            "componentCount": len(components),
            "categories": self._catalog.categories(),
            "dataSources": self._catalog.data_sources(),
            "components": [c.id for c in components],
        }

    def classify_request(self, text: str, *, blueprint_id: Optional[str] = None, owner_id: Optional[str] = None) -> dict[str, Any]:
        """Choose Compose vs Engineer for a natural-language UI request (Phase 6)."""
        blueprint = self.get_blueprint(blueprint_id, owner_id=owner_id) if blueprint_id else None
        decision = _classify_request(text, catalog=self._catalog)
        payload = decision.to_dict()
        if blueprint is not None:
            payload["blueprintId"] = blueprint.id
            payload["revision"] = blueprint.revision
        return payload

    # ── introspection ─────────────────────────────────────────────────────────

    def get_application_map(self, *, owner_id: Optional[str] = None) -> dict[str, Any]:
        """A structured map of the UI the agent can reason about.

        The persisted desired state (blueprints) + the composable component
        catalog. Live rendered-DOM state is provided by the front door, which
        augments this with the current page's rendered instances.
        """
        pages, total = self._store.list_blueprints(ListBlueprintsQuery(limit=200), owner_id=None)
        return {
            "pages": [p.model_dump(by_alias=True) for p in pages],
            "pageCount": total,
            "capabilities": self.get_capabilities(),
        }

    def get_current_page(self, *, blueprint_id: Optional[str] = None, path: Optional[str] = None, owner_id: Optional[str] = None) -> dict[str, Any]:
        blueprint = None
        if blueprint_id:
            blueprint = self.get_blueprint(blueprint_id, owner_id=owner_id)
        elif path:
            # Resolve the path against the FULL blueprint, not the list summary:
            # `BlueprintSummary` carries no `path`, so the previous `entry.path`
            # read raised AttributeError and every path lookup failed.
            summaries, _total = self._store.list_blueprints(
                ListBlueprintsQuery(limit=200), owner_id=owner_id
            )
            for entry in summaries:
                candidate = self._store.get_blueprint(entry.id, owner_id=owner_id)
                if candidate is not None and candidate.path == path:
                    blueprint = candidate
                    break
        if blueprint is None:
            raise UiError("UI_BLUEPRINT_NOT_FOUND", "no matching page is available")
        return {
            "blueprint": blueprint.model_dump(by_alias=True),
            "revision": blueprint.revision,
            "instances": self._instances(blueprint),
        }

    def _instances(self, blueprint: UiBlueprint) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for section in blueprint.layout.sections:
            for column in section.columns:
                for widget in column.widgets:
                    spec = self._catalog.get(widget.widget_id)
                    out.append({
                        "instanceId": widget.id,
                        "componentId": widget.widget_id,
                        "category": spec.category if spec else None,
                        "owner": spec.owner.value if spec else None,
                        "availability": spec.availability.value if spec else "unavailable",
                        "config": widget.config or {},
                        "hidden": bool(widget.hidden),
                        "sectionId": section.id,
                        "columnId": column.id,
                        "height": widget.height,
                    })
        return out

    def get_operation_status(self, operation_id: str) -> UiOperation:
        operation = self._store.get_operation(operation_id)
        if operation is None:
            raise UiError("UI_OPERATION_NOT_FOUND", f'unknown operation "{operation_id}"')
        return operation

    # ── blueprints: read ──────────────────────────────────────────────────────

    def get_blueprint(self, blueprint_id: str, *, owner_id: Optional[str] = None) -> UiBlueprint:
        blueprint = self._store.get_blueprint(blueprint_id, owner_id=owner_id)
        if blueprint is None:
            raise UiError("UI_BLUEPRINT_NOT_FOUND", f'unknown blueprint "{blueprint_id}"')
        return blueprint

    def list_blueprints(self, query: Optional[ListBlueprintsQuery] = None, *, owner_id: Optional[str] = None) -> dict[str, Any]:
        query = query or ListBlueprintsQuery()
        summaries, total = self._store.list_blueprints(query, owner_id=owner_id)
        return {
            "blueprints": [s.model_dump(by_alias=True) for s in summaries],
            "total": total, "limit": query.limit, "offset": query.offset,
        }

    def get_layout(self, blueprint_id: str, *, owner_id: Optional[str] = None) -> dict[str, Any]:
        blueprint = self.get_blueprint(blueprint_id, owner_id=owner_id)
        return {"blueprintId": blueprint.id, "revision": blueprint.revision, "layout": blueprint.layout.model_dump(by_alias=True)}

    def history(self, blueprint_id: str) -> dict[str, Any]:
        self.get_blueprint(blueprint_id)
        return {"blueprintId": blueprint_id, "revisions": self._store.history(blueprint_id)}

    def export_blueprint(self, blueprint_id: str, *, owner_id: Optional[str] = None) -> dict[str, Any]:
        """A portable, self-describing snapshot (no secrets; blueprint data only)."""
        blueprint = self.get_blueprint(blueprint_id, owner_id=owner_id)
        return {
            "kind": "eclipse.ui.blueprint",
            "schemaVersion": blueprint.schema_version,
            "exportedAt": now_iso(),
            "blueprint": blueprint.model_dump(by_alias=True),
        }

    def import_blueprint(self, payload: dict[str, Any], *, owner_id: str = "operator", actor: Optional[str] = None) -> UiBlueprint:
        """Validate an exported snapshot and store it as a NEW blueprint (fresh id)."""
        raw = payload.get("blueprint") if isinstance(payload, dict) and isinstance(payload.get("blueprint"), dict) else payload
        validation = validate_blueprint(raw, self._catalog)
        if not validation.ok or validation.blueprint is None:
            raise UiError(
                "UI_BLUEPRINT_INVALID", "the imported blueprint failed validation",
                issues=[i.model_dump(by_alias=True) for i in validation.issues],
            )
        imported = validation.blueprint.model_copy(deep=True)
        imported.id = new_id("uibp")
        imported.revision = 1
        imported.created_at = now_iso()
        imported.updated_at = imported.created_at
        imported.owner = BlueprintOwner(kind="user", id=owner_id)
        saved = self._store.save_blueprint(imported, summary="imported")
        self._record("import_blueprint", saved.id, "completed", actor, detail=f"imported {saved.title}", result={"blueprintId": saved.id})
        _publish(UiEventType.PAGE_CREATED.value, {"blueprintId": saved.id, "title": saved.title, "imported": True})
        return saved

    # ── blueprints: write ─────────────────────────────────────────────────────

    def create_page(self, input_model: CreatePageInput, *, owner_id: str = "operator", actor: Optional[str] = None) -> UiBlueprint:
        if input_model.idempotency_key:
            existing = self._store.lookup_idempotency(input_model.idempotency_key)
            if existing:
                found = self._store.get_blueprint(existing)
                if found is not None:
                    return found
        blueprint = UiBlueprint(
            id=new_id("uibp"), title=input_model.title, description=input_model.description,
            kind=input_model.kind, scope=input_model.scope, path=input_model.path,
            tags=input_model.tags or None, layout=_empty_layout(),
            owner=BlueprintOwner(kind="user", id=owner_id),
            revision=1, created_at=now_iso(), updated_at=now_iso(),
        )
        validation = validate_blueprint(blueprint.model_dump(by_alias=True), self._catalog)
        if not validation.ok:
            raise UiError("UI_BLUEPRINT_INVALID", "the new page failed validation", issues=[i.model_dump(by_alias=True) for i in validation.issues])
        saved = self._store.save_blueprint(validation.blueprint or blueprint, summary="created")
        if input_model.idempotency_key:
            self._store.record_idempotency(input_model.idempotency_key, saved.id)
        self._record("create_page", saved.id, "completed", actor, detail=f"created {saved.title}", result={"blueprintId": saved.id})
        _publish(UiEventType.PAGE_CREATED.value, {"blueprintId": saved.id, "title": saved.title})
        return saved

    def update_page(self, blueprint_id: str, input_model: UpdatePageInput, *, owner_id: Optional[str] = None, actor: Optional[str] = None, expected_revision: Optional[int] = None) -> UiBlueprint:
        meta = {"op": "update_meta"}
        if input_model.title is not None:
            meta["title"] = input_model.title
        if input_model.description is not None:
            meta["description"] = input_model.description
        if input_model.path is not None:
            meta["path"] = input_model.path
        if input_model.tags is not None:
            meta["tags"] = input_model.tags
        return self._mutate(blueprint_id, [meta], "update_page", owner_id=owner_id, actor=actor, expected_revision=expected_revision, event=UiEventType.PAGE_UPDATED)

    def duplicate_page(self, blueprint_id: str, *, owner_id: Optional[str] = None, actor: Optional[str] = None, title: Optional[str] = None) -> UiBlueprint:
        source = self.get_blueprint(blueprint_id, owner_id=owner_id)
        clone = source.model_copy(deep=True)
        clone.id = new_id("uibp")
        clone.title = title or f"{source.title} (copy)"
        clone.revision = 1
        clone.created_at = now_iso()
        clone.updated_at = clone.created_at
        saved = self._store.save_blueprint(clone, summary="duplicated")
        self._record("duplicate_page", saved.id, "completed", actor, detail=f"duplicated from {source.id}", result={"blueprintId": saved.id, "sourceId": source.id})
        return saved

    def save_layout(self, input_model: SaveLayoutInput, *, owner_id: Optional[str] = None, actor: Optional[str] = None) -> UiBlueprint:
        blueprint = self.get_blueprint(input_model.blueprint_id, owner_id=owner_id)
        candidate = blueprint.model_copy(deep=True)
        candidate.layout = input_model.layout
        candidate.revision = blueprint.revision + 1
        candidate.updated_at = now_iso()
        validation = validate_blueprint(candidate.model_dump(by_alias=True), self._catalog)
        if not validation.ok:
            raise UiError("UI_LAYOUT_INVALID", "the layout failed validation", issues=[i.model_dump(by_alias=True) for i in validation.issues])
        return self._commit(validation.blueprint or candidate, input_model.expected_revision, blueprint, "save_layout", actor, "saved layout", UiEventType.LAYOUT_CHANGED)

    def restore_revision(self, input_model: RestoreRevisionInput, *, owner_id: Optional[str] = None, actor: Optional[str] = None) -> UiBlueprint:
        blueprint = self.get_blueprint(input_model.blueprint_id, owner_id=owner_id)
        previous = self._store.get_revision(blueprint.id, input_model.revision)
        if previous is None:
            raise UiError("UI_REVISION_NOT_FOUND", f"revision {input_model.revision} is not retained")
        restored = previous.model_copy(deep=True)
        restored.revision = blueprint.revision + 1
        restored.updated_at = now_iso()
        saved = self._store.save_blueprint(restored, summary=f"restored revision {input_model.revision}")
        self._record("restore_layout", saved.id, "completed", actor, detail=f"restored r{input_model.revision}", result={"blueprintId": saved.id, "revision": saved.revision})
        _publish(UiEventType.BLUEPRINT_RESTORED.value, {"blueprintId": saved.id, "fromRevision": input_model.revision, "toRevision": saved.revision})
        return saved

    # ── widget / layout operations ────────────────────────────────────────────

    def _mutate(self, blueprint_id: str, ops: list[dict[str, Any]], operation: str, *, owner_id: Optional[str], actor: Optional[str], expected_revision: Optional[int], event: Optional[UiEventType] = None, summary: Optional[str] = None) -> UiBlueprint:
        blueprint = self.get_blueprint(blueprint_id, owner_id=owner_id)
        result = engine_apply_ops(blueprint, ops, catalog=self._catalog)
        if not result.ok:
            self._record(operation, blueprint_id, "rejected", actor, detail="validation failed", error=result.issues[0].message if result.issues else "invalid", result={"issues": [i.model_dump(by_alias=True) for i in result.issues]})
            raise UiError("UI_OPERATION_INVALID", result.issues[0].message if result.issues else "the operation was invalid", issues=[i.model_dump(by_alias=True) for i in result.issues])
        changes = diff_blueprints(blueprint, result.blueprint)
        return self._commit(result.blueprint, expected_revision, blueprint, operation, actor, summary or operation, event, changes=changes)

    def _commit(self, candidate: UiBlueprint, expected_revision: Optional[int], current: UiBlueprint, operation: str, actor: Optional[str], detail: str, event: Optional[UiEventType], *, changes: Optional[list[Any]] = None) -> UiBlueprint:
        if expected_revision is not None and expected_revision != current.revision:
            self._record(operation, current.id, "conflict", actor, detail=f"expected r{expected_revision}, found r{current.revision}", error="UI_CONFLICT")
            _publish(UiEventType.OPERATION_FAILED.value, {"blueprintId": current.id, "operation": operation, "reason": "conflict"})
            raise UiError("UI_CONFLICT", f"blueprint moved from revision {expected_revision} to {current.revision}; reload and re-apply")
        saved = self._store.save_blueprint(candidate, summary=detail)
        if changes is not None:
            self._store.append_revision(saved, summary=detail, changes=[c.model_dump(by_alias=True) for c in changes])
        self._record(operation, saved.id, "completed", actor, detail=detail, result={"blueprintId": saved.id, "revision": saved.revision})
        if event is not None:
            _publish(event.value, {"blueprintId": saved.id, "revision": saved.revision})
        return saved

    def add_widget(self, input_model: AddWidgetInput, *, owner_id: Optional[str] = None, actor: Optional[str] = None) -> UiBlueprint:
        if json.dumps(input_model.config or {}) and len(json.dumps(input_model.config)) > MAX_CONFIG_BYTES:
            raise UiError("UI_CONFIG_TOO_LARGE", "widget configuration exceeds the size limit")
        op: dict[str, Any] = {"op": "add_widget", "componentId": input_model.component_id}
        if input_model.instance_id:
            op["instanceId"] = input_model.instance_id
        if input_model.target is not None:
            op["target"] = input_model.target.model_dump(by_alias=True)
        if input_model.zone is not None:
            op["zone"] = input_model.zone
        if input_model.height is not None:
            op["height"] = input_model.height
        if input_model.config:
            op["config"] = input_model.config
        blueprint = self._mutate(input_model.blueprint_id, [op], "add_widget", owner_id=owner_id, actor=actor, expected_revision=input_model.expected_revision, event=UiEventType.WIDGET_ADDED, summary=f"added {input_model.component_id}")
        return blueprint

    def remove_widget(self, input_model: WidgetRefInput, *, owner_id: Optional[str] = None, actor: Optional[str] = None) -> UiBlueprint:
        return self._mutate(input_model.blueprint_id, [{"op": "remove_widget", "instanceId": input_model.instance_id}], "remove_widget", owner_id=owner_id, actor=actor, expected_revision=input_model.expected_revision, event=UiEventType.WIDGET_REMOVED)

    def move_widget(self, input_model: MoveWidgetInput, *, owner_id: Optional[str] = None, actor: Optional[str] = None) -> UiBlueprint:
        return self._mutate(input_model.blueprint_id, [{"op": "move_widget", "instanceId": input_model.instance_id, "target": input_model.target.model_dump(by_alias=True)}], "move_widget", owner_id=owner_id, actor=actor, expected_revision=input_model.expected_revision, event=UiEventType.WIDGET_UPDATED)

    def reorder_widget(self, input_model: ReorderWidgetInput, *, owner_id: Optional[str] = None, actor: Optional[str] = None) -> UiBlueprint:
        return self._mutate(input_model.blueprint_id, [{"op": "reorder_widget", "instanceId": input_model.instance_id, "toIndex": input_model.to_index}], "reorder_widget", owner_id=owner_id, actor=actor, expected_revision=input_model.expected_revision, event=UiEventType.WIDGET_UPDATED)

    def resize_widget(self, input_model: ResizeWidgetInput, *, owner_id: Optional[str] = None, actor: Optional[str] = None) -> UiBlueprint:
        return self._mutate(input_model.blueprint_id, [{"op": "resize_widget", "instanceId": input_model.instance_id, "height": input_model.height}], "resize_widget", owner_id=owner_id, actor=actor, expected_revision=input_model.expected_revision, event=UiEventType.WIDGET_UPDATED)

    def update_widget_config(self, input_model: UpdateConfigInput, *, owner_id: Optional[str] = None, actor: Optional[str] = None) -> UiBlueprint:
        return self._mutate(input_model.blueprint_id, [{"op": "update_config", "instanceId": input_model.instance_id, "patch": input_model.patch}], "update_config", owner_id=owner_id, actor=actor, expected_revision=input_model.expected_revision, event=UiEventType.WIDGET_UPDATED)

    def set_column_count(self, input_model: SetColumnCountInput, *, owner_id: Optional[str] = None, actor: Optional[str] = None) -> UiBlueprint:
        return self._mutate(input_model.blueprint_id, [{"op": "set_column_count", "sectionId": input_model.section_id, "count": input_model.count}], "set_column_count", owner_id=owner_id, actor=actor, expected_revision=input_model.expected_revision, event=UiEventType.LAYOUT_CHANGED)

    def set_column_weight(self, input_model: SetColumnWeightInput, *, owner_id: Optional[str] = None, actor: Optional[str] = None) -> UiBlueprint:
        return self._mutate(input_model.blueprint_id, [{"op": "set_column_weight", "columnId": input_model.column_id, "weight": input_model.weight}], "set_column_weight", owner_id=owner_id, actor=actor, expected_revision=input_model.expected_revision, event=UiEventType.LAYOUT_CHANGED)

    def remove_section(self, input_model: SectionRefInput, *, owner_id: Optional[str] = None, actor: Optional[str] = None) -> UiBlueprint:
        return self._mutate(input_model.blueprint_id, [{"op": "remove_section", "sectionId": input_model.section_id}], "remove_section", owner_id=owner_id, actor=actor, expected_revision=input_model.expected_revision, event=UiEventType.LAYOUT_CHANGED)

    def apply_ops(self, blueprint_id: str, ops: list[dict[str, Any]], *, owner_id: Optional[str] = None, actor: Optional[str] = None, expected_revision: Optional[int] = None) -> UiBlueprint:
        return self._mutate(blueprint_id, ops, "apply_ops", owner_id=owner_id, actor=actor, expected_revision=expected_revision)

    def preview(self, blueprint_id: str, ops: list[dict[str, Any]], *, owner_id: Optional[str] = None) -> dict[str, Any]:
        """Compute the would-be result of a batch WITHOUT persisting it."""
        blueprint = self.get_blueprint(blueprint_id, owner_id=owner_id)
        result = engine_apply_ops(blueprint, ops, catalog=self._catalog)
        if not result.ok:
            raise UiError("UI_OPERATION_INVALID", "the preview failed validation", issues=[i.model_dump(by_alias=True) for i in result.issues])
        changes = diff_blueprints(blueprint, result.blueprint)
        return {
            "blueprint": result.blueprint.model_dump(by_alias=True),
            "changes": [c.model_dump(by_alias=True) for c in changes],
            "currentRevision": blueprint.revision,
            "nextRevision": result.blueprint.revision,
        }

    # ── audit ─────────────────────────────────────────────────────────────────

    def _record(self, operation: str, blueprint_id: Optional[str], status: str, actor: Optional[str], *, detail: str = "", result: Optional[dict[str, Any]] = None, error: Optional[str] = None) -> UiOperation:
        record = UiOperation(
            id=new_id("uiop"), operation=operation, blueprint_id=blueprint_id, status=status,
            actor=actor, detail=detail, result=result or {}, error=error, created_at=now_iso(),
        )
        return self._store.record_operation(record)


__all__ = ["UiError", "UiService"]
