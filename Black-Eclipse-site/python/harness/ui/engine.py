"""Blueprint validation, atomic mutation and diff — the runtime's UI engine.

Mirrors `src/lib/ui-engineering/{blueprint,patches,revisions}.ts` so a blueprint
is validated and mutated identically in Python and the browser. The engine is
pure: it takes and returns models, touches no database and emits no events (the
service layer owns persistence and telemetry).

Validation is STRICT and truthful. Structural problems are reported by the
pydantic contract; semantic problems (unknown component, duplicate instance /
column / section id, oversized column count, invalid configuration) are reported
here. An invalid payload is never silently repaired.
"""

from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Optional

from pydantic import ValidationError

from ..persistence import new_id, now_iso
from .catalog import UiCatalog, validate_component_config
from .model import (
    BlueprintChange,
    ChangeType,
    ConfigIssue,
    DropTarget,
    Severity,
    SUPPORTED_BLUEPRINT_SCHEMA,
    UiBlueprint,
    UiComponentSpec,
    WORKSPACE_LAYOUT_VERSION,
    WorkspaceColumn,
    WorkspaceLayout,
    WorkspaceSection,
    WidgetPlacement,
)


@dataclass
class ValidationResult:
    ok: bool
    issues: list[ConfigIssue] = field(default_factory=list)
    blueprint: Optional[UiBlueprint] = None


@dataclass
class ApplyResult:
    ok: bool
    blueprint: UiBlueprint
    issues: list[ConfigIssue] = field(default_factory=list)
    applied: int = 0


def _issue(path: str, message: str, severity: Severity = Severity.ERROR) -> ConfigIssue:
    return ConfigIssue(path=path, message=message, severity=severity)


def _model_validation_issues(exc: ValidationError) -> list[ConfigIssue]:
    issues: list[ConfigIssue] = []
    for err in exc.errors():
        loc = ".".join(str(p) for p in err.get("loc", ()))
        issues.append(_issue(loc, err.get("msg", "invalid value")))
    return issues


def _semantic_layout_issues(layout: WorkspaceLayout, catalog: Optional[UiCatalog]) -> list[ConfigIssue]:
    issues: list[ConfigIssue] = []
    seen_sections: set[str] = set()
    seen_columns: set[str] = set()
    seen_instances: set[str] = set()

    for si, section in enumerate(layout.sections):
        s_path = f"layout.sections[{si}]"
        if section.id in seen_sections:
            issues.append(_issue(f"{s_path}.id", f'duplicate section id "{section.id}"'))
        seen_sections.add(section.id)
        if len(section.columns) > 4:
            issues.append(_issue(f"{s_path}.columns", "a section may not have more than 4 columns"))
        for ci, column in enumerate(section.columns):
            c_path = f"{s_path}.columns[{ci}]"
            if column.id in seen_columns:
                issues.append(_issue(f"{c_path}.id", f'duplicate column id "{column.id}"'))
            seen_columns.add(column.id)
            for wi, widget in enumerate(column.widgets):
                w_path = f"{c_path}.widgets[{wi}]"
                if widget.id in seen_instances:
                    issues.append(_issue(f"{w_path}.id", f'duplicate instance id "{widget.id}"'))
                seen_instances.add(widget.id)
                if catalog is not None and not catalog.has(widget.widget_id):
                    issues.append(_issue(f"{w_path}.widgetId", f'unknown component "{widget.widget_id}"'))
                if catalog is not None and widget.config:
                    for item in validate_component_config(catalog.get(widget.widget_id) or _EMPTY_SPEC, widget.config):
                        issues.append(_issue(f"{w_path}.config.{item.path}", item.message, item.severity))
    return issues


# A placeholder spec used only when the catalog has no entry (so config checks
# become "unknown key" warnings rather than crashes). Never persisted.
_EMPTY_SPEC = UiComponentSpec(id="_unknown", display_name="Unknown", category="unknown")


def validate_blueprint(raw: Any, catalog: Optional[UiCatalog] = None) -> ValidationResult:
    """Validate a raw blueprint payload. Returns the cleaned model only when valid."""
    if not isinstance(raw, dict):
        return ValidationResult(ok=False, issues=[_issue("", "blueprint must be an object")])

    schema_version = raw.get("schemaVersion", raw.get("schema_version"))
    if isinstance(schema_version, int) and schema_version > SUPPORTED_BLUEPRINT_SCHEMA:
        return ValidationResult(ok=False, issues=[_issue(
            "schemaVersion", f"blueprint schema {schema_version} is newer than supported {SUPPORTED_BLUEPRINT_SCHEMA}",
        )])

    try:
        blueprint = UiBlueprint.model_validate(raw)
    except ValidationError as exc:
        return ValidationResult(ok=False, issues=_model_validation_issues(exc))

    issues = _semantic_layout_issues(blueprint.layout, catalog)
    if any(i.severity == Severity.ERROR for i in issues):
        return ValidationResult(ok=False, issues=issues)
    return ValidationResult(ok=True, issues=issues, blueprint=blueprint)


# ── mutation ──────────────────────────────────────────────────────────────────


def _find_section(layout: WorkspaceLayout, section_id: str) -> Optional[WorkspaceSection]:
    return next((s for s in layout.sections if s.id == section_id), None)


def _find_column(layout: WorkspaceLayout, column_id: str) -> Optional[WorkspaceColumn]:
    for section in layout.sections:
        for column in section.columns:
            if column.id == column_id:
                return column
    return None


def _locate(layout: WorkspaceLayout, instance_id: str) -> Optional[tuple[WorkspaceSection, WorkspaceColumn, WidgetPlacement, int]]:
    for section in layout.sections:
        for column in section.columns:
            for index, widget in enumerate(column.widgets):
                if widget.id == instance_id:
                    return section, column, widget, index
    return None


def _validate_op(op: dict[str, Any], blueprint: UiBlueprint, catalog: Optional[UiCatalog]) -> list[ConfigIssue]:
    issues: list[ConfigIssue] = []
    kind = op.get("op")
    layout = blueprint.layout

    if kind == "add_widget":
        component_id = op.get("componentId")
        if not component_id:
            issues.append(_issue("componentId", "componentId is required"))
        elif catalog is not None and not catalog.has(component_id):
            issues.append(_issue("componentId", f'unknown component "{component_id}"'))
        target = op.get("target")
        if isinstance(target, dict):
            section_id = target.get("sectionId")
            if section_id and _find_section(layout, section_id) is None:
                issues.append(_issue("target.sectionId", f'unknown section "{section_id}"'))
            column_id = target.get("columnId")
            if column_id and _find_column(layout, column_id) is None:
                issues.append(_issue("target.columnId", f'unknown column "{column_id}"'))
        if catalog is not None and op.get("config"):
            config = op["config"]
            issues.extend(
                _issue(f"config.{i.path}", i.message, i.severity)
                for i in validate_component_config(catalog.get(component_id) or _EMPTY_SPEC, config)
            )
        return issues

    if kind in ("remove_widget", "move_widget", "reorder_widget", "resize_widget", "update_config", "duplicate_widget"):
        instance_id = op.get("instanceId")
        found = _locate(layout, instance_id) if instance_id else None
        if found is None:
            issues.append(_issue("instanceId", f'unknown widget instance "{instance_id}"'))
        if kind == "move_widget":
            target = op.get("target")
            if isinstance(target, dict) and target.get("sectionId") and _find_section(layout, target["sectionId"]) is None:
                issues.append(_issue("target.sectionId", f'unknown section "{target["sectionId"]}"'))
        if kind == "update_config" and found is not None and catalog is not None:
            merged = {**(found[2].config or {}), **(op.get("patch") or {})}
            issues.extend(
                _issue(f"patch.{i.path}", i.message, i.severity)
                for i in validate_component_config(catalog.get(found[2].widget_id) or _EMPTY_SPEC, merged)
            )
        return issues

    if kind == "set_column_count":
        if _find_section(layout, op.get("sectionId", "")) is None:
            issues.append(_issue("sectionId", f'unknown section "{op.get("sectionId")}"'))
        count = op.get("count")
        if not isinstance(count, int) or not 1 <= count <= 4:
            issues.append(_issue("count", "column count must be an integer 1..4"))
        return issues

    if kind == "set_column_weight":
        if _find_column(layout, op.get("columnId", "")) is None:
            issues.append(_issue("columnId", f'unknown column "{op.get("columnId")}"'))
        weight = op.get("weight")
        if not isinstance(weight, (int, float)) or weight <= 0:
            issues.append(_issue("weight", "column weight must be a positive number"))
        return issues

    if kind == "remove_section":
        if _find_section(layout, op.get("sectionId", "")) is None:
            issues.append(_issue("sectionId", f'unknown section "{op.get("sectionId")}"'))
        return issues

    if kind == "update_meta":
        title = op.get("title")
        if title is not None and (not isinstance(title, str) or not title.strip()):
            issues.append(_issue("title", "title may not be empty"))
        return issues

    issues.append(_issue("op", f'unknown operation "{kind}"'))
    return issues


def _prune(layout: WorkspaceLayout) -> None:
    non_empty = [s for s in layout.sections if any(c.widgets for c in s.columns)]
    if not non_empty:
        if layout.sections:
            first = layout.sections[0]
            first.columns = first.columns or [WorkspaceColumn(id=new_id("col"), weight=3, widgets=[])]
            layout.sections = [first]
        return
    for section in non_empty:
        if not section.columns:
            section.columns = [WorkspaceColumn(id=new_id("col"), weight=3, widgets=[])]
    layout.sections = non_empty


def _take_widget(layout: WorkspaceLayout, instance_id: str) -> Optional[WidgetPlacement]:
    for section in layout.sections:
        for column in section.columns:
            for index, widget in enumerate(column.widgets):
                if widget.id == instance_id:
                    return column.widgets.pop(index)
    return None


def _insert(draft: WorkspaceLayout, placement: WidgetPlacement, target: Optional[dict[str, Any]], zone: Optional[str]) -> None:
    section: Optional[WorkspaceSection] = None
    if target and target.get("sectionId"):
        section = _find_section(draft, target["sectionId"])
    if section is None:
        if not draft.sections:
            draft.sections.append(WorkspaceSection(id=new_id("sec"), zone=zone, columns=[WorkspaceColumn(id=new_id("col"), weight=3, widgets=[])]))
        section = next((s for s in draft.sections if (s.zone or "main") == (zone or "main")), None) if zone else None
        if section is None:
            section = draft.sections[-1]
    column: Optional[WorkspaceColumn] = None
    if target and target.get("columnId"):
        column = _find_column(draft, target["columnId"])
    if column is None:
        if not section.columns:
            section.columns.append(WorkspaceColumn(id=new_id("col"), weight=3, widgets=[]))
        column = section.columns[-1]
    index = int(target.get("index", 0)) if target and column.id == target.get("columnId") else len(column.widgets)
    column.widgets.insert(max(0, min(index, len(column.widgets))), placement)


def _apply_one(layout: WorkspaceLayout, op: dict[str, Any]) -> None:
    kind = op.get("op")
    if kind == "add_widget":
        placement = WidgetPlacement(
            id=op.get("instanceId") or new_id("wid"),
            widgetId=op["componentId"],
            height=op.get("height"),
            config=dict(op.get("config") or {}),
        )
        _insert(layout, placement, op.get("target"), op.get("zone"))
    elif kind == "remove_widget":
        _take_widget(layout, op["instanceId"])
        _prune(layout)
    elif kind == "move_widget":
        moved = _take_widget(layout, op["instanceId"])
        if moved is not None:
            _insert(layout, moved, op.get("target"), None)
            _prune(layout)
    elif kind == "reorder_widget":
        found = _locate(layout, op["instanceId"])
        if found is not None:
            _, column, _, index = found
            to_index = max(0, min(int(op.get("toIndex", 0)), len(column.widgets) - 1))
            if index != to_index:
                column.widgets.insert(to_index, column.widgets.pop(index))
    elif kind == "resize_widget":
        found = _locate(layout, op["instanceId"])
        if found is not None:
            found[2].height = op.get("height")
    elif kind == "update_config":
        found = _locate(layout, op["instanceId"])
        if found is not None:
            found[2].config = {**(found[2].config or {}), **(op.get("patch") or {})}
    elif kind == "duplicate_widget":
        found = _locate(layout, op["instanceId"])
        if found is not None:
            _, column, widget, index = found
            column.widgets.insert(index + 1, WidgetPlacement(
                id=new_id("wid"), widgetId=widget.widget_id, height=widget.height,
                defaultHeight=widget.default_height, minHeight=widget.min_height,
                config=dict(widget.config) if widget.config else None, hidden=widget.hidden,
            ))
    elif kind == "set_column_count":
        section = _find_section(layout, op["sectionId"])
        if section is not None:
            count = max(1, min(4, int(op["count"])))
            while len(section.columns) > count:
                overflow = section.columns.pop()
                section.columns[-1].widgets.extend(overflow.widgets)
            while len(section.columns) < count:
                section.columns.append(WorkspaceColumn(id=new_id("col"), weight=3, widgets=[]))
    elif kind == "set_column_weight":
        column = _find_column(layout, op["columnId"])
        if column is not None:
            column.weight = max(0.3, min(12.0, round(float(op["weight"]) * 10) / 10))
    elif kind == "remove_section":
        layout.sections = [s for s in layout.sections if s.id != op["sectionId"]]
        if not layout.sections:
            layout.sections.append(WorkspaceSection(id=new_id("sec"), zone="main", columns=[WorkspaceColumn(id=new_id("col"), weight=3, widgets=[])]))
    # `update_meta` is applied by `apply_ops` directly (it changes the envelope,
    # not the layout), so `_apply_one` intentionally ignores it.


_META_OPS = {"update_meta"}


def apply_ops(
    blueprint: UiBlueprint,
    ops: list[dict[str, Any]],
    *,
    catalog: Optional[UiCatalog] = None,
    now: Optional[str] = None,
) -> ApplyResult:
    """Validate and atomically apply a batch of operations.

    All-or-nothing: if any op fails validation the blueprint is returned
    unchanged. On success the revision is bumped exactly once.
    """
    issues: list[ConfigIssue] = []
    for op in ops:
        if not isinstance(op, dict):
            issues.append(_issue("op", "operation must be an object"))
            continue
        issues.extend(_validate_op(op, blueprint, catalog))
    if any(i.severity == Severity.ERROR for i in issues):
        return ApplyResult(ok=False, blueprint=blueprint, issues=issues, applied=0)
    if not ops:
        return ApplyResult(ok=True, blueprint=blueprint, issues=[], applied=0)

    layout = deepcopy(blueprint.layout)
    for op in ops:
        if op.get("op") not in _META_OPS:
            _apply_one(layout, op)

    updated = blueprint.model_copy(deep=True)
    updated.layout = layout
    for op in ops:
        if op.get("op") == "update_meta":
            if op.get("title") is not None:
                updated.title = op["title"]
            if op.get("description") is not None:
                updated.description = op["description"]
            if op.get("path") is not None:
                updated.path = op["path"]
            if op.get("icon") is not None:
                updated.icon = op["icon"] or None
            if op.get("tags") is not None:
                updated.tags = list(op["tags"])
    updated.revision = blueprint.revision + 1
    updated.updated_at = now or now_iso()

    # Re-validate the result so a mutation can never yield an invalid blueprint.
    revalidation = validate_blueprint(updated.model_dump(by_alias=True), catalog)
    if not revalidation.ok:
        return ApplyResult(ok=False, blueprint=blueprint, issues=revalidation.issues, applied=0)
    return ApplyResult(ok=True, blueprint=revalidation.blueprint, issues=[], applied=len(ops))


# ── diff ──────────────────────────────────────────────────────────────────────


def _index(layout: WorkspaceLayout) -> dict[str, tuple[int, int, int, WidgetPlacement]]:
    out: dict[str, tuple[int, int, int, WidgetPlacement]] = {}
    for si, section in enumerate(layout.sections):
        for ci, column in enumerate(section.columns):
            for wi, widget in enumerate(column.widgets):
                out[widget.id] = (si, ci, wi, widget)
    return out


def diff_blueprints(before: UiBlueprint, after: UiBlueprint) -> list[BlueprintChange]:
    changes: list[BlueprintChange] = []
    old = _index(before.layout)
    new = _index(after.layout)
    for instance_id, entry in new.items():
        if instance_id not in old:
            changes.append(BlueprintChange(type=ChangeType.ADD_WIDGET, instance_id=instance_id, component_id=entry[3].widget_id, detail=f"added {entry[3].widget_id}"))
    for instance_id, entry in old.items():
        if instance_id not in new:
            changes.append(BlueprintChange(type=ChangeType.REMOVE_WIDGET, instance_id=instance_id, component_id=entry[3].widget_id, detail=f"removed {entry[3].widget_id}"))
    for instance_id, nxt in new.items():
        prev = old.get(instance_id)
        if prev is None:
            continue
        if prev[:3] != nxt[:3]:
            changes.append(BlueprintChange(type=ChangeType.MOVE_WIDGET, instance_id=instance_id, component_id=nxt[3].widget_id, detail=f"moved {nxt[3].widget_id}"))
        if prev[3].height != nxt[3].height:
            changes.append(BlueprintChange(type=ChangeType.RESIZE_WIDGET, instance_id=instance_id, component_id=nxt[3].widget_id, detail=f"resized {nxt[3].widget_id}"))
        if json.dumps(prev[3].config or {}, sort_keys=True) != json.dumps(nxt[3].config or {}, sort_keys=True):
            changes.append(BlueprintChange(type=ChangeType.CONFIG_CHANGED, instance_id=instance_id, component_id=nxt[3].widget_id, detail=f"reconfigured {nxt[3].widget_id}"))
    if (before.title, before.description, before.path, before.icon, before.tags) != (after.title, after.description, after.path, after.icon, after.tags):
        changes.append(BlueprintChange(type=ChangeType.META_CHANGED, detail="updated page metadata"))
    shape_before = [(s.id, len(s.columns), tuple(c.weight for c in s.columns)) for s in before.layout.sections]
    shape_after = [(s.id, len(s.columns), tuple(c.weight for c in s.columns)) for s in after.layout.sections]
    if shape_before != shape_after:
        changes.append(BlueprintChange(type=ChangeType.LAYOUT_CHANGED, detail="changed section/column layout"))
    return changes


def widget_count(layout: WorkspaceLayout) -> int:
    return sum(len(c.widgets) for s in layout.sections for c in s.columns)


__all__ = [
    "ApplyResult",
    "ValidationResult",
    "apply_ops",
    "diff_blueprints",
    "validate_blueprint",
    "widget_count",
]
