"""UI Engineering contracts — the durable vocabulary of the UI runtime.

This is the Python counterpart of `src/lib/ui-engineering/`. It defines ONLY
shape and vocabulary: the component-spec contract, the declarative blueprint,
the workspace layout tree and the closed operation set. Every field a caller
(the model, an HTTP client, a plugin) may supply passes through one of these
pydantic models before it is persisted — the runtime never trusts a raw
LLM/client payload.

The persisted form is a set of SQLite rows on the ONE `agent-memory.db`
connection (see `store.py`). Field names are snake_case in Python and camelCase
on the wire (the TS front door), exactly like `artifacts.model`/`tasks.model`.

The blueprint references components by stable id; it never carries code. A
configuration is DATA validated against the component's declared schema, so no
blueprint field can execute JavaScript or SQL.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic.alias_generators import to_camel

_CAMEL = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")

#: The blueprint envelope schema this runtime understands.
SUPPORTED_BLUEPRINT_SCHEMA = 1
#: The workspace layout tree version (mirrors `src/lib/workspace/types.ts`).
WORKSPACE_LAYOUT_VERSION = 2

# ── Bounds ────────────────────────────────────────────────────────────────────
MAX_TITLE = 200
MAX_DESCRIPTION = 4_000
MAX_COMPONENT_ID = 120
MAX_INSTANCE_ID = 120
MAX_PATH = 300
MAX_TAGS = 32
MAX_TAG_LENGTH = 60
MAX_CONFIG_BYTES = 16_384
MAX_LAYOUT_BYTES = 256_000
MAX_LIST_LIMIT = 200
DEFAULT_LIST_LIMIT = 50
MAX_HISTORY = 50


# ── Closed vocabularies ───────────────────────────────────────────────────────


class OwnershipKind(str, Enum):
    CORE = "core"
    PLUGIN = "plugin"
    USER = "user"


class Availability(str, Enum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"


class BlueprintKind(str, Enum):
    PAGE = "page"
    WORKSPACE = "workspace"


class BlueprintScope(str, Enum):
    PERSONAL = "personal"
    SHARED = "shared"


class Severity(str, Enum):
    ERROR = "error"
    WARNING = "warning"


class ChangeType(str, Enum):
    ADD_WIDGET = "add_widget"
    REMOVE_WIDGET = "remove_widget"
    MOVE_WIDGET = "move_widget"
    RESIZE_WIDGET = "resize_widget"
    CONFIG_CHANGED = "config_changed"
    META_CHANGED = "meta_changed"
    LAYOUT_CHANGED = "layout_changed"


class UiEventType(str, Enum):
    PAGE_OPENED = "ui.page.opened"
    PAGE_CREATED = "ui.page.created"
    PAGE_UPDATED = "ui.page.updated"
    WIDGET_ADDED = "ui.widget.added"
    WIDGET_REMOVED = "ui.widget.removed"
    WIDGET_UPDATED = "ui.widget.updated"
    LAYOUT_CHANGED = "ui.layout.changed"
    OPERATION_COMPLETED = "ui.operation.completed"
    OPERATION_FAILED = "ui.operation.failed"
    BLUEPRINT_RESTORED = "ui.blueprint.restored"
    COMPONENT_REGISTERED = "ui.component.registered"


#: The closed operation vocabulary recorded for every mutation.
OPERATION_TYPES = (
    "create_page", "update_page", "duplicate_page",
    "create_workspace", "add_widget", "remove_widget", "move_widget",
    "reorder_widget", "resize_widget", "update_config", "set_column_count",
    "set_column_weight", "remove_section", "save_layout", "restore_layout",
    "apply_ops", "register_component",
)

#: The action names a component advertises (mirrors catalog.ts COMPONENT_ACTIONS).
COMPONENT_ACTIONS = (
    "remove", "move", "resize", "reorder", "configure", "duplicate", "hide",
)

ConfigFieldKind = Literal["text", "number", "select", "boolean", "symbol", "symbols"]
WorkspaceZone = Literal["left", "main", "right"]


# ── Component catalog contracts ───────────────────────────────────────────────


class ConfigFieldSpec(BaseModel):
    model_config = _CAMEL

    key: str = Field(..., min_length=1, max_length=80)
    label: str = Field(..., min_length=1, max_length=200)
    kind: ConfigFieldKind = "text"
    options: list[dict[str, str]] = Field(default_factory=list)
    required: bool = False
    default: Any = None
    min: Optional[float] = None
    max: Optional[float] = None
    step: Optional[float] = None
    placeholder: Optional[str] = None


class ComponentLayoutSpec(BaseModel):
    model_config = _CAMEL

    sizes: list[str] = Field(default_factory=list)
    min_height: Optional[int] = None
    default_height: Optional[int] = None
    resizable: bool = True
    zones: list[WorkspaceZone] = Field(default_factory=lambda: ["left", "main", "right"])


class UiComponentSpec(BaseModel):
    """The runtime's view of one composable UI component."""

    model_config = _CAMEL

    id: str = Field(..., min_length=1, max_length=MAX_COMPONENT_ID, pattern=r"^[a-zA-Z0-9._-]+$")
    version: str = "1.0.0"
    display_name: str = Field(..., min_length=1, max_length=200)
    description: str = Field("", max_length=MAX_DESCRIPTION)
    category: str = Field(..., min_length=1, max_length=80)
    icon: str = "dashboard"
    tags: list[str] = Field(default_factory=list)
    config_schema: list[ConfigFieldSpec] = Field(default_factory=list)
    default_config: dict[str, Any] = Field(default_factory=dict)
    data_sources: list[str] = Field(default_factory=list)
    actions: list[str] = Field(default_factory=lambda: list(COMPONENT_ACTIONS))
    layout: ComponentLayoutSpec = Field(default_factory=ComponentLayoutSpec)
    availability: Availability = Availability.AVAILABLE
    owner: OwnershipKind = OwnershipKind.CORE
    plugin_id: Optional[str] = None


class ConfigIssue(BaseModel):
    model_config = _CAMEL

    path: str = ""
    message: str
    severity: Severity = Severity.ERROR


class RegisterComponentInput(BaseModel):
    model_config = _CAMEL

    spec: UiComponentSpec


# ── Workspace layout tree (mirrors the TS kernel) ─────────────────────────────


class WidgetPlacement(BaseModel):
    model_config = _CAMEL

    id: str = Field(..., min_length=1, max_length=MAX_INSTANCE_ID)
    widget_id: str = Field(..., min_length=1, max_length=MAX_COMPONENT_ID)
    height: Optional[float] = None
    default_height: Optional[float] = None
    min_height: Optional[float] = None
    config: Optional[dict[str, Any]] = None
    hidden: Optional[bool] = None


class WorkspaceColumn(BaseModel):
    model_config = _CAMEL

    id: str = Field(..., min_length=1, max_length=MAX_INSTANCE_ID)
    weight: float
    widgets: list[WidgetPlacement] = Field(default_factory=list)


class WorkspaceSection(BaseModel):
    model_config = _CAMEL

    id: str = Field(..., min_length=1, max_length=MAX_INSTANCE_ID)
    zone: Optional[WorkspaceZone] = None
    columns: list[WorkspaceColumn] = Field(default_factory=list)


class WorkspaceLayout(BaseModel):
    model_config = _CAMEL

    version: int = WORKSPACE_LAYOUT_VERSION
    sections: list[WorkspaceSection] = Field(default_factory=list)
    hidden_zones: Optional[list[WorkspaceZone]] = None
    zone_widths: Optional[dict[str, float]] = None


# ── Blueprint ─────────────────────────────────────────────────────────────────


class BlueprintOwner(BaseModel):
    model_config = _CAMEL

    kind: OwnershipKind = OwnershipKind.USER
    id: str = Field("operator", min_length=1, max_length=120)


class UiBlueprint(BaseModel):
    model_config = _CAMEL

    schema_version: int = SUPPORTED_BLUEPRINT_SCHEMA
    id: str = Field(..., min_length=1, max_length=120)
    title: str = Field(..., min_length=1, max_length=MAX_TITLE)
    description: Optional[str] = Field(None, max_length=MAX_DESCRIPTION)
    kind: BlueprintKind = BlueprintKind.PAGE
    owner: BlueprintOwner = Field(default_factory=BlueprintOwner)
    scope: BlueprintScope = BlueprintScope.PERSONAL
    path: Optional[str] = Field(None, max_length=MAX_PATH)
    tags: Optional[list[str]] = None
    layout: WorkspaceLayout = Field(default_factory=WorkspaceLayout)
    revision: int = Field(1, ge=1)
    created_at: str
    updated_at: str


class BlueprintSummary(BaseModel):
    """A compact, agent-facing view of a blueprint.

    Carries `path` (so path lookups and disambiguation are possible from the
    list) and the ordered `component_ids` actually placed on the page — the two
    facts that let an agent tell apart pages that share a title. It deliberately
    stays small: full layout/config lives on the blueprint, not here.
    """

    model_config = _CAMEL

    id: str
    title: str
    kind: BlueprintKind
    scope: BlueprintScope
    owner_id: str
    path: Optional[str] = None
    revision: int
    updated_at: str
    widget_count: int
    component_ids: list[str] = Field(default_factory=list)


class BlueprintChange(BaseModel):
    model_config = _CAMEL

    type: ChangeType
    instance_id: Optional[str] = None
    component_id: Optional[str] = None
    detail: str = ""


class UiOperation(BaseModel):
    """A recorded, auditable UI mutation."""

    model_config = _CAMEL

    id: str
    operation: str
    blueprint_id: Optional[str] = None
    status: str  # completed | failed | conflict | rejected
    actor: Optional[str] = None
    detail: str = ""
    result: dict[str, Any] = Field(default_factory=dict)
    error: Optional[str] = None
    created_at: str


# ── Operation inputs (tool arguments / API bodies) ────────────────────────────


class DropTarget(BaseModel):
    model_config = _CAMEL

    section_id: str = Field(..., min_length=1)
    column_id: Optional[str] = None
    index: int = 0
    column_index: Optional[int] = None


class CreatePageInput(BaseModel):
    model_config = _CAMEL

    title: str = Field(..., min_length=1, max_length=MAX_TITLE)
    description: Optional[str] = Field(None, max_length=MAX_DESCRIPTION)
    kind: BlueprintKind = BlueprintKind.PAGE
    scope: BlueprintScope = BlueprintScope.PERSONAL
    path: Optional[str] = Field(None, max_length=MAX_PATH)
    tags: list[str] = Field(default_factory=list)
    idempotency_key: Optional[str] = Field(None, max_length=200)


class UpdatePageInput(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")

    title: Optional[str] = Field(None, min_length=1, max_length=MAX_TITLE)
    description: Optional[str] = Field(None, max_length=MAX_DESCRIPTION)
    path: Optional[str] = Field(None, max_length=MAX_PATH)
    tags: Optional[list[str]] = None


class AddWidgetInput(BaseModel):
    model_config = _CAMEL

    blueprint_id: str = Field(..., min_length=1)
    component_id: str = Field(..., min_length=1)
    instance_id: Optional[str] = Field(None, min_length=1)
    target: Optional[DropTarget] = None
    config: dict[str, Any] = Field(default_factory=dict)
    zone: Optional[WorkspaceZone] = None
    height: Optional[float] = None
    expected_revision: Optional[int] = None


class WidgetRefInput(BaseModel):
    model_config = _CAMEL

    blueprint_id: str = Field(..., min_length=1)
    instance_id: str = Field(..., min_length=1)
    expected_revision: Optional[int] = None


class MoveWidgetInput(BaseModel):
    model_config = _CAMEL

    blueprint_id: str = Field(..., min_length=1)
    instance_id: str = Field(..., min_length=1)
    target: DropTarget
    expected_revision: Optional[int] = None


class ReorderWidgetInput(BaseModel):
    model_config = _CAMEL

    blueprint_id: str = Field(..., min_length=1)
    instance_id: str = Field(..., min_length=1)
    to_index: int = Field(0, ge=0)
    expected_revision: Optional[int] = None


class ResizeWidgetInput(BaseModel):
    model_config = _CAMEL

    blueprint_id: str = Field(..., min_length=1)
    instance_id: str = Field(..., min_length=1)
    height: Optional[float] = None
    expected_revision: Optional[int] = None


class UpdateConfigInput(BaseModel):
    model_config = _CAMEL

    blueprint_id: str = Field(..., min_length=1)
    instance_id: str = Field(..., min_length=1)
    patch: dict[str, Any] = Field(default_factory=dict)
    expected_revision: Optional[int] = None


class SetColumnCountInput(BaseModel):
    model_config = _CAMEL

    blueprint_id: str = Field(..., min_length=1)
    section_id: str = Field(..., min_length=1)
    count: int = Field(..., ge=1, le=4)
    expected_revision: Optional[int] = None


class SetColumnWeightInput(BaseModel):
    model_config = _CAMEL

    blueprint_id: str = Field(..., min_length=1)
    column_id: str = Field(..., min_length=1)
    weight: float = Field(..., gt=0)
    expected_revision: Optional[int] = None


class SectionRefInput(BaseModel):
    model_config = _CAMEL

    blueprint_id: str = Field(..., min_length=1)
    section_id: str = Field(..., min_length=1)
    expected_revision: Optional[int] = None


class SaveLayoutInput(BaseModel):
    model_config = _CAMEL

    blueprint_id: str = Field(..., min_length=1)
    layout: WorkspaceLayout
    expected_revision: Optional[int] = None


class RestoreRevisionInput(BaseModel):
    model_config = _CAMEL

    blueprint_id: str = Field(..., min_length=1)
    revision: int = Field(..., ge=1)


class ListBlueprintsQuery(BaseModel):
    model_config = _CAMEL

    scope: Optional[BlueprintScope] = None
    kind: Optional[BlueprintKind] = None
    owner_id: Optional[str] = None
    q: Optional[str] = Field(None, max_length=200)
    limit: int = Field(DEFAULT_LIST_LIMIT, ge=1, le=MAX_LIST_LIMIT)
    offset: int = Field(0, ge=0)


class CatalogQuery(BaseModel):
    model_config = _CAMEL

    text: Optional[str] = Field(None, max_length=200)
    category: Optional[str] = Field(None, max_length=80)
    data_source: Optional[str] = Field(None, max_length=200)
    owner: Optional[OwnershipKind] = None
    availability: Optional[Availability] = None
    limit: int = Field(DEFAULT_LIST_LIMIT, ge=1, le=MAX_LIST_LIMIT)

    @field_validator("text")
    @classmethod
    def _clean(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None


__all__ = [
    "AddWidgetInput",
    "Availability",
    "BlueprintChange",
    "BlueprintKind",
    "BlueprintOwner",
    "BlueprintScope",
    "BlueprintSummary",
    "CatalogQuery",
    "ChangeType",
    "ComponentLayoutSpec",
    "ConfigFieldSpec",
    "ConfigIssue",
    "CreatePageInput",
    "DropTarget",
    "ListBlueprintsQuery",
    "MAX_HISTORY",
    "MoveWidgetInput",
    "OPERATION_TYPES",
    "OwnershipKind",
    "RegisterComponentInput",
    "ReorderWidgetInput",
    "ResizeWidgetInput",
    "RestoreRevisionInput",
    "SaveLayoutInput",
    "SectionRefInput",
    "SetColumnCountInput",
    "SetColumnWeightInput",
    "Severity",
    "SUPPORTED_BLUEPRINT_SCHEMA",
    "UiBlueprint",
    "UiComponentSpec",
    "UiEventType",
    "UiOperation",
    "UpdateConfigInput",
    "UpdatePageInput",
    "WidgetPlacement",
    "WidgetRefInput",
    "WORKSPACE_LAYOUT_VERSION",
    "WorkspaceColumn",
    "WorkspaceLayout",
    "WorkspaceSection",
    "WorkspaceZone",
]
