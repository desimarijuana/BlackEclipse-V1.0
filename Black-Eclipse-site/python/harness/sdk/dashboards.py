"""Command Center control over the durable dashboard mirror blueprints."""

from __future__ import annotations

from typing import Any, Optional

from ..ui.model import (
    AddWidgetInput,
    CreatePageInput,
    DropTarget,
    ListBlueprintsQuery,
    MoveWidgetInput,
    ResizeWidgetInput,
    RestoreRevisionInput,
    SaveLayoutInput,
    SetColumnCountInput,
    UiBlueprint,
    WidgetRefInput,
    WorkspaceLayout,
)
from ..ui.service import UiError, UiService
from .locks import LockService
from .model import (
    SdkDashboardAddWidgetInput,
    SdkDashboardMoveWidgetInput,
    SdkDashboardResizeWidgetInput,
    SdkDashboardSetColumnsInput,
    SdkDashboardSetLayoutInput,
    SdkDashboardSetZonesInput,
    SdkDashboardTarget,
    SdkDashboardWidgetRefInput,
)
from .store import SdkStore

DASHBOARD_PATH_PREFIX = "/dashboard/"
ACTIVE_META_KEY = "eclipse_active_dashboard"
DEFAULT_DASHBOARD_ID = "main"


def _dashboard_id_from_path(path: Optional[str]) -> Optional[str]:
    value = (path or "").strip()
    if not value.lower().startswith(DASHBOARD_PATH_PREFIX):
        return None
    dashboard_id = value[len(DASHBOARD_PATH_PREFIX):].strip().strip("/")
    return dashboard_id or None


class DashboardService:
    def __init__(self, ui: Optional[UiService], store: SdkStore, locks: Optional[LockService] = None) -> None:
        self._ui = ui
        self._store = store
        self._locks = locks

    def _require_ui(self) -> UiService:
        if self._ui is None:
            raise UiError("SDK_UI_UNAVAILABLE", "the UI runtime is unavailable")
        return self._ui

    def _mirrors(self) -> list[dict[str, Any]]:
        ui = self._require_ui()
        listed = ui.list_blueprints(ListBlueprintsQuery(limit=200, include_dashboard_mirrors=True))
        mirrors: list[dict[str, Any]] = []
        for summary in listed.get("blueprints", []):
            dashboard_id = _dashboard_id_from_path(summary.get("path"))
            if dashboard_id is None:
                continue
            mirrors.append({
                "dashboardId": dashboard_id,
                "blueprintId": summary["id"],
                "title": summary["title"],
                "path": summary["path"],
                "revision": summary["revision"],
                "updatedAt": summary["updatedAt"],
                "widgetCount": summary["widgetCount"],
                "componentIds": summary.get("componentIds") or [],
            })
        return mirrors

    def _active_marker(self) -> Optional[str]:
        value = self._store.get_meta(ACTIVE_META_KEY)
        return value.strip() if value and value.strip() else None

    def _find(self, identifier: Optional[str]) -> Optional[UiBlueprint]:
        ui = self._require_ui()
        raw = (identifier or "").strip()
        if not raw:
            return None
        wanted = raw.lower()
        mirrors = self._mirrors()
        for mirror in mirrors:
            if mirror["blueprintId"] == raw or mirror["dashboardId"].lower() == wanted:
                return ui.get_blueprint(mirror["blueprintId"])
        if raw.lower().startswith(DASHBOARD_PATH_PREFIX):
            dashboard_id = _dashboard_id_from_path(raw)
            if dashboard_id:
                for mirror in mirrors:
                    if mirror["dashboardId"].lower() == dashboard_id.lower():
                        return ui.get_blueprint(mirror["blueprintId"])
            return None
        for mirror in mirrors:
            if mirror["title"].strip().lower() == wanted:
                return ui.get_blueprint(mirror["blueprintId"])
        try:
            blueprint = ui.get_blueprint(raw)
        except UiError:
            return None
        return blueprint if _dashboard_id_from_path(blueprint.path) else None

    def _ensure(self, identifier: Optional[str]) -> UiBlueprint:
        existing = self._find(identifier)
        if existing is not None:
            return existing
        raw = (identifier or self._active_marker() or DEFAULT_DASHBOARD_ID).strip()
        if raw.startswith("uibp"):
            raise UiError("SDK_DASHBOARD_NOT_FOUND", f'blueprint "{raw}" is not a Command Center mirror')
        dashboard_id = _dashboard_id_from_path(raw) or raw
        title = "Main" if dashboard_id == DEFAULT_DASHBOARD_ID else dashboard_id
        return self._require_ui().create_page(
            CreatePageInput(
                title=title,
                kind="workspace",
                path=f"{DASHBOARD_PATH_PREFIX}{dashboard_id}",
                idempotency_key=f"dash-bp:{dashboard_id}",
            )
        )

    def _snapshot(self, blueprint: UiBlueprint) -> dict[str, Any]:
        dashboard_id = _dashboard_id_from_path(blueprint.path) or blueprint.id
        components = [
            widget.widget_id
            for section in blueprint.layout.sections
            for column in section.columns
            for widget in column.widgets
        ]
        return {
            "dashboard": {
                "dashboardId": dashboard_id,
                "blueprintId": blueprint.id,
                "title": blueprint.title,
                "path": blueprint.path or f"{DASHBOARD_PATH_PREFIX}{dashboard_id}",
                "revision": blueprint.revision,
                "updatedAt": blueprint.updated_at,
                "widgetCount": len(components),
                "componentIds": components,
            },
            "blueprint": blueprint.model_dump(by_alias=True),
            "revision": blueprint.revision,
            "layout": blueprint.layout.model_dump(by_alias=True),
            "activeDashboardId": self._active_marker(),
        }

    def _assert_unlocked(self, blueprint: UiBlueprint) -> None:
        if self._locks is None:
            return
        dashboard_id = _dashboard_id_from_path(blueprint.path) or blueprint.id
        self._locks.assert_allowed("dashboard", dashboard_id, "write")

    def _record(
        self,
        action: str,
        summary: str,
        dashboard_id: str,
        *,
        actor: Optional[str] = None,
        detail: Optional[dict[str, Any]] = None,
    ) -> None:
        try:
            self._store.record_audit(
                action=action,
                actor=actor or "operator",
                resource_type="dashboard",
                resource_id=dashboard_id,
                summary=summary,
                detail=detail,
            )
        except Exception:  # noqa: BLE001 - audit never breaks a successful mutation
            pass

    def _audit(
        self,
        action: str,
        summary: str,
        blueprint: UiBlueprint,
        *,
        actor: Optional[str] = None,
        detail: Optional[dict[str, Any]] = None,
    ) -> None:
        dashboard_id = _dashboard_id_from_path(blueprint.path) or blueprint.id
        self._record(action, summary, dashboard_id, actor=actor, detail=detail)

    @staticmethod
    def _default_target(blueprint: UiBlueprint, zone: Optional[str]) -> Optional[DropTarget]:
        wanted = zone or "main"
        sections = [s for s in blueprint.layout.sections if (s.zone or "main") == wanted]
        if not sections:
            sections = [s for s in blueprint.layout.sections if (s.zone or "main") == "main"]
        if not sections:
            return None
        section = next((s for s in sections if s.columns), sections[0])
        if not section.columns:
            return DropTarget(section_id=section.id)
        column = min(section.columns, key=lambda c: len(c.widgets))
        return DropTarget(section_id=section.id, column_id=column.id, index=len(column.widgets))

    def list(self) -> dict[str, Any]:
        mirrors = self._mirrors()
        return {"dashboards": mirrors, "activeDashboardId": self._active_marker()}

    def active(self) -> dict[str, Any]:
        blueprint = self._find(self._active_marker())
        if blueprint is None:
            blueprint = self._find("Main")
        if blueprint is None:
            mirrors = self._mirrors()
            if mirrors:
                blueprint = self._require_ui().get_blueprint(mirrors[0]["blueprintId"])
        if blueprint is None:
            raise UiError("SDK_DASHBOARD_NOT_FOUND", "no Command Center layout has been published yet")
        return self._snapshot(blueprint)

    def get(self, identifier: Optional[str] = None) -> dict[str, Any]:
        if identifier:
            blueprint = self._find(identifier)
            if blueprint is None:
                raise UiError("SDK_DASHBOARD_NOT_FOUND", f'unknown dashboard "{identifier}"')
            return self._snapshot(blueprint)
        return self.active()

    def set_active(self, identifier: str) -> dict[str, Any]:
        value = (identifier or "").strip()
        if not value:
            raise UiError("SDK_DASHBOARD_INVALID", "a dashboard id is required")
        dashboard_id = _dashboard_id_from_path(value) or value
        self._store.set_meta(ACTIVE_META_KEY, dashboard_id)
        self._record("dashboard.set_active", f"Activated dashboard {dashboard_id}", dashboard_id)
        return {"activeDashboardId": dashboard_id}

    def add_widget(
        self,
        identifier: Optional[str],
        input_model: SdkDashboardAddWidgetInput,
        *,
        actor: Optional[str] = None,
    ) -> dict[str, Any]:
        blueprint = self._ensure(identifier)
        self._assert_unlocked(blueprint)
        target = None
        if input_model.target is not None:
            target = DropTarget(
                section_id=input_model.target.section_id,
                column_id=input_model.target.column_id,
                index=input_model.target.index,
                column_index=input_model.target.column_index,
            )
        else:
            target = self._default_target(blueprint, input_model.zone)
        saved = self._require_ui().add_widget(
            AddWidgetInput(
                blueprint_id=blueprint.id,
                component_id=input_model.component_id,
                instance_id=input_model.instance_id,
                target=target,
                config=input_model.config,
                zone=input_model.zone,
                height=input_model.height,
                expected_revision=input_model.expected_revision or blueprint.revision,
            ),
            actor=actor,
        )
        self._audit(
            "dashboard.add_widget",
            f"Added {input_model.component_id}",
            saved,
            actor=actor,
            detail={"componentId": input_model.component_id, "instanceId": input_model.instance_id},
        )
        return self._snapshot(saved)

    def remove_widget(
        self,
        identifier: Optional[str],
        input_model: SdkDashboardWidgetRefInput,
        *,
        actor: Optional[str] = None,
    ) -> dict[str, Any]:
        blueprint = self._ensure(identifier)
        self._assert_unlocked(blueprint)
        saved = self._require_ui().remove_widget(
            WidgetRefInput(
                blueprint_id=blueprint.id,
                instance_id=input_model.instance_id,
                expected_revision=input_model.expected_revision or blueprint.revision,
            ),
            actor=actor,
        )
        self._audit(
            "dashboard.remove_widget",
            f"Removed {input_model.instance_id}",
            saved,
            actor=actor,
            detail={"instanceId": input_model.instance_id},
        )
        return self._snapshot(saved)

    def move_widget(
        self,
        identifier: Optional[str],
        input_model: SdkDashboardMoveWidgetInput,
        *,
        actor: Optional[str] = None,
    ) -> dict[str, Any]:
        blueprint = self._ensure(identifier)
        self._assert_unlocked(blueprint)
        saved = self._require_ui().move_widget(
            MoveWidgetInput(
                blueprint_id=blueprint.id,
                instance_id=input_model.instance_id,
                target=DropTarget(
                    section_id=input_model.target.section_id,
                    column_id=input_model.target.column_id,
                    index=input_model.target.index,
                    column_index=input_model.target.column_index,
                ),
                expected_revision=input_model.expected_revision or blueprint.revision,
            ),
            actor=actor,
        )
        self._audit(
            "dashboard.move_widget",
            f"Moved {input_model.instance_id}",
            saved,
            actor=actor,
            detail={"instanceId": input_model.instance_id, "target": input_model.target.model_dump(by_alias=True)},
        )
        return self._snapshot(saved)

    def resize_widget(
        self,
        identifier: Optional[str],
        input_model: SdkDashboardResizeWidgetInput,
        *,
        actor: Optional[str] = None,
    ) -> dict[str, Any]:
        blueprint = self._ensure(identifier)
        self._assert_unlocked(blueprint)
        saved = self._require_ui().resize_widget(
            ResizeWidgetInput(
                blueprint_id=blueprint.id,
                instance_id=input_model.instance_id,
                height=input_model.height,
                expected_revision=input_model.expected_revision or blueprint.revision,
            ),
            actor=actor,
        )
        self._audit(
            "dashboard.resize_widget",
            f"Resized {input_model.instance_id}",
            saved,
            actor=actor,
            detail={"instanceId": input_model.instance_id, "height": input_model.height},
        )
        return self._snapshot(saved)

    def set_columns(
        self,
        identifier: Optional[str],
        input_model: SdkDashboardSetColumnsInput,
        *,
        actor: Optional[str] = None,
    ) -> dict[str, Any]:
        blueprint = self._ensure(identifier)
        self._assert_unlocked(blueprint)
        saved = self._require_ui().set_column_count(
            SetColumnCountInput(
                blueprint_id=blueprint.id,
                section_id=input_model.section_id,
                count=input_model.count,
                expected_revision=input_model.expected_revision or blueprint.revision,
            ),
            actor=actor,
        )
        self._audit(
            "dashboard.set_columns",
            f"Set {input_model.count} column(s)",
            saved,
            actor=actor,
            detail={"sectionId": input_model.section_id, "count": input_model.count},
        )
        return self._snapshot(saved)

    def set_zones(
        self,
        identifier: Optional[str],
        input_model: SdkDashboardSetZonesInput,
        *,
        actor: Optional[str] = None,
    ) -> dict[str, Any]:
        blueprint = self._ensure(identifier)
        self._assert_unlocked(blueprint)
        layout = blueprint.layout.model_copy(deep=True)
        if input_model.hidden_zones is not None:
            layout.hidden_zones = list(input_model.hidden_zones)
        if input_model.zone_widths is not None:
            layout.zone_widths = dict(input_model.zone_widths)
        saved = self._require_ui().save_layout(
            SaveLayoutInput(
                blueprint_id=blueprint.id,
                layout=layout,
                expected_revision=input_model.expected_revision or blueprint.revision,
            ),
            actor=actor,
        )
        self._audit(
            "dashboard.set_zones",
            "Updated the dashboard zones",
            saved,
            actor=actor,
            detail={"hiddenZones": input_model.hidden_zones, "zoneWidths": input_model.zone_widths},
        )
        return self._snapshot(saved)

    def set_layout(
        self,
        identifier: Optional[str],
        input_model: SdkDashboardSetLayoutInput,
        *,
        actor: Optional[str] = None,
    ) -> dict[str, Any]:
        blueprint = self._ensure(identifier)
        self._assert_unlocked(blueprint)
        layout = WorkspaceLayout.model_validate(input_model.layout)
        saved = self._require_ui().save_layout(
            SaveLayoutInput(
                blueprint_id=blueprint.id,
                layout=layout,
                expected_revision=input_model.expected_revision or blueprint.revision,
            ),
            actor=actor,
        )
        self._audit(
            "dashboard.set_layout",
            "Saved the dashboard layout",
            saved,
            actor=actor,
        )
        return self._snapshot(saved)

    def history(self, identifier: Optional[str]) -> dict[str, Any]:
        blueprint = self._find(identifier or self._active_marker())
        if blueprint is None:
            raise UiError("SDK_DASHBOARD_NOT_FOUND", f'unknown dashboard "{identifier or ""}"')
        return self._require_ui().history(blueprint.id)

    def restore(
        self,
        identifier: Optional[str],
        revision: int,
        *,
        actor: Optional[str] = None,
    ) -> dict[str, Any]:
        blueprint = self._ensure(identifier)
        self._assert_unlocked(blueprint)
        saved = self._require_ui().restore_revision(
            RestoreRevisionInput(blueprint_id=blueprint.id, revision=revision),
            actor=actor,
        )
        self._audit(
            "dashboard.restore",
            f"Restored revision {revision}",
            saved,
            actor=actor,
            detail={"revision": revision},
        )
        return self._snapshot(saved)


__all__ = [
    "ACTIVE_META_KEY",
    "DASHBOARD_PATH_PREFIX",
    "DEFAULT_DASHBOARD_ID",
    "DashboardService",
]
