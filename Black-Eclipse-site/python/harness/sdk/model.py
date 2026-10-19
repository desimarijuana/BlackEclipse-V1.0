"""Eclipse SDK contracts.

Wire shape is camelCase (aliases) exactly like the rest of the runtime. Every
caller payload passes through one of these models before it is persisted: a
widget is DATA (a primitive + an allow-listed source), a page is a blueprint,
a fund is an accounting portfolio with metadata, and a lock is a resource id +
a hashed passphrase. No field can execute code.
"""

from __future__ import annotations

from typing import Any, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic.alias_generators import to_camel

_CAMEL = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")

#: The declarative host renderers a user widget may choose. These mirror the
#: generic registry widgets in `src/lib/workspace/generic-*.tsx`; the SDK never
#: accepts a renderer outside this closed set.
WidgetPrimitive = Literal[
    "data-table",
    "metric-card",
    "line-chart",
    "area-chart",
    "bar-chart",
    "pie-chart",
    "list",
    "markdown",
    "status-indicator",
    "empty-state",
    "error-state",
    "clock",
]

WIDGET_PRIMITIVES: tuple[str, ...] = (
    "data-table",
    "metric-card",
    "line-chart",
    "area-chart",
    "bar-chart",
    "pie-chart",
    "list",
    "markdown",
    "status-indicator",
    "empty-state",
    "error-state",
    "clock",
)

#: Primitives that need a resolvable data source.
SOURCE_PRIMITIVES = {
    "data-table", "metric-card", "line-chart", "area-chart",
    "bar-chart", "pie-chart", "list",
}

ResourceType = Literal["page", "widget", "portfolio", "design", "dashboard", "theme"]
RESOURCE_TYPES: tuple[str, ...] = ("page", "widget", "portfolio", "design", "dashboard", "theme")

WidgetSurface = Literal["dashboard", "page", "both"]

MAX_SLUG = 64
MAX_LABEL = 200
MAX_SOURCE = 400
MAX_CONFIG_BYTES = 32_768


class SdkWidgetInput(BaseModel):
    """Register a user widget backed by a declarative primitive."""

    model_config = _CAMEL

    slug: str = Field(..., min_length=1, max_length=MAX_SLUG, pattern=r"^[a-z0-9][a-z0-9-]*$")
    label: str = Field(..., min_length=1, max_length=MAX_LABEL)
    description: str = Field("", max_length=4_000)
    icon: str = Field("dashboard", max_length=60)
    category: str = Field("custom", min_length=1, max_length=80)
    primitive: WidgetPrimitive = "data-table"
    source: Optional[str] = Field(None, max_length=MAX_SOURCE)
    surface: WidgetSurface = "both"
    config: dict[str, Any] = Field(default_factory=dict)
    sizes: list[str] = Field(default_factory=lambda: ["medium", "large"])

    @field_validator("slug")
    @classmethod
    def _clean_slug(cls, value: str) -> str:
        return value.strip().lower()

    @field_validator("source")
    @classmethod
    def _clean_source(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None

    @field_validator("sizes")
    @classmethod
    def _sizes(cls, value: list[str]) -> list[str]:
        allowed = {"small", "medium", "large", "full"}
        out = [s for s in value if s in allowed]
        return out or ["medium", "large"]


class SdkPageWidget(BaseModel):
    model_config = _CAMEL

    component_id: str = Field(..., min_length=1, max_length=120)
    config: dict[str, Any] = Field(default_factory=dict)
    height: Optional[float] = None


class SdkCreatePageInput(BaseModel):
    model_config = _CAMEL

    title: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=4_000)
    path: Optional[str] = Field(None, max_length=300)
    icon: Optional[str] = Field(None, max_length=60)
    tags: list[str] = Field(default_factory=list)
    widgets: list[SdkPageWidget] = Field(default_factory=list, max_length=50)
    idempotency_key: Optional[str] = Field(None, max_length=200)


class SdkCreateFundInput(BaseModel):
    """Create a first-class fund portfolio (accounting portfolio + fund metadata)."""

    model_config = _CAMEL

    name: str = Field(..., min_length=1, max_length=200)
    base_currency: str = Field("USD", min_length=1, max_length=12)
    description: Optional[str] = Field(None, max_length=4_000)
    goal: Optional[str] = Field(None, max_length=500)
    icon: Optional[str] = Field(None, max_length=60)
    accent: Optional[str] = Field(None, max_length=40)
    cost_basis_method: Literal["FIFO", "LIFO", "AVERAGE_COST"] = "FIFO"
    metadata: dict[str, Any] = Field(default_factory=dict)


class SdkAddStockInput(BaseModel):
    """Add (or transfer in) a stock/asset position to an existing portfolio."""

    model_config = _CAMEL

    symbol: str = Field(..., min_length=1, max_length=40)
    quantity: Union[str, int, float] = Field(...)
    price: Optional[Union[str, int, float]] = None
    currency: Optional[str] = Field(None, max_length=12)
    type: Literal["BUY", "TRANSFER_IN"] = "BUY"
    trade_date: Optional[str] = Field(None, max_length=40)
    fees: Optional[Union[str, int, float]] = None
    notes: Optional[str] = Field(None, max_length=2_000)

    @field_validator("symbol")
    @classmethod
    def _clean_symbol(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("quantity", "price", "fees", mode="before")
    @classmethod
    def _stringify(cls, value: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return str(value)
        return value


class SdkCreateLockInput(BaseModel):
    model_config = _CAMEL

    resource_type: ResourceType
    resource_id: str = Field(..., min_length=1, max_length=240)
    passphrase: str = Field(..., min_length=4, max_length=200)
    label: Optional[str] = Field(None, max_length=200)
    hint: Optional[str] = Field(None, max_length=200)

    @field_validator("resource_id")
    @classmethod
    def _clean_resource_id(cls, value: str) -> str:
        return value.strip()


class SdkUnlockInput(BaseModel):
    model_config = _CAMEL

    passphrase: str = Field(..., min_length=1, max_length=200)


class SdkAssertLockInput(BaseModel):
    model_config = _CAMEL

    resource_type: ResourceType
    resource_id: str = Field(..., min_length=1, max_length=240)
    action: Literal["write", "delete"] = "write"


class SdkLockView(BaseModel):
    model_config = _CAMEL

    id: str
    resource_type: str
    resource_id: str
    label: Optional[str] = None
    hint: Optional[str] = None
    created_by: Optional[str] = None
    created_at: str
    updated_at: str


class SdkDashboardTarget(BaseModel):
    model_config = _CAMEL

    section_id: str = Field(..., min_length=1, max_length=120)
    column_id: Optional[str] = Field(None, max_length=120)
    index: int = Field(0, ge=0)
    column_index: Optional[int] = Field(None, ge=0)


class SdkDashboardAddWidgetInput(BaseModel):
    model_config = _CAMEL

    component_id: str = Field(..., min_length=1, max_length=120)
    instance_id: Optional[str] = Field(None, min_length=1, max_length=120)
    config: dict[str, Any] = Field(default_factory=dict)
    target: Optional[SdkDashboardTarget] = None
    zone: Optional[Literal["left", "main", "right"]] = None
    height: Optional[float] = None
    expected_revision: Optional[int] = Field(None, ge=1)


class SdkDashboardWidgetRefInput(BaseModel):
    model_config = _CAMEL

    instance_id: str = Field(..., min_length=1, max_length=120)
    expected_revision: Optional[int] = Field(None, ge=1)


class SdkDashboardMoveWidgetInput(BaseModel):
    model_config = _CAMEL

    instance_id: str = Field(..., min_length=1, max_length=120)
    target: SdkDashboardTarget
    expected_revision: Optional[int] = Field(None, ge=1)


class SdkDashboardResizeWidgetInput(BaseModel):
    model_config = _CAMEL

    instance_id: str = Field(..., min_length=1, max_length=120)
    height: Optional[float] = None
    expected_revision: Optional[int] = Field(None, ge=1)


class SdkDashboardSetColumnsInput(BaseModel):
    model_config = _CAMEL

    section_id: str = Field(..., min_length=1, max_length=120)
    count: int = Field(..., ge=1, le=4)
    expected_revision: Optional[int] = Field(None, ge=1)


class SdkDashboardSetZonesInput(BaseModel):
    model_config = _CAMEL

    hidden_zones: Optional[list[Literal["left", "main", "right"]]] = None
    zone_widths: Optional[dict[str, float]] = None
    expected_revision: Optional[int] = Field(None, ge=1)


class SdkDashboardSetLayoutInput(BaseModel):
    model_config = _CAMEL

    layout: dict[str, Any]
    expected_revision: Optional[int] = Field(None, ge=1)


class SdkDashboardRestoreInput(BaseModel):
    model_config = _CAMEL

    revision: int = Field(..., ge=1)


class SdkActiveDashboardInput(BaseModel):
    model_config = _CAMEL

    dashboard_id: str = Field(..., min_length=1, max_length=240)


class SdkWidgetView(BaseModel):
    model_config = _CAMEL

    id: str
    component_id: str
    slug: str
    label: str
    description: str
    icon: str
    category: str
    primitive: str
    source: Optional[str] = None
    surface: str = "both"
    config: dict[str, Any] = Field(default_factory=dict)
    sizes: list[str] = Field(default_factory=list)
    created_at: str
    updated_at: str


__all__ = [
    "MAX_CONFIG_BYTES",
    "RESOURCE_TYPES",
    "ResourceType",
    "SdkActiveDashboardInput",
    "SdkAddStockInput",
    "SdkAssertLockInput",
    "SdkCreateFundInput",
    "SdkCreateLockInput",
    "SdkCreatePageInput",
    "SdkDashboardAddWidgetInput",
    "SdkDashboardMoveWidgetInput",
    "SdkDashboardResizeWidgetInput",
    "SdkDashboardRestoreInput",
    "SdkDashboardSetColumnsInput",
    "SdkDashboardSetLayoutInput",
    "SdkDashboardSetZonesInput",
    "SdkDashboardTarget",
    "SdkDashboardWidgetRefInput",
    "SdkLockView",
    "SdkPageWidget",
    "SdkUnlockInput",
    "SdkWidgetInput",
    "SdkWidgetView",
    "SOURCE_PRIMITIVES",
    "WIDGET_PRIMITIVES",
    "WidgetPrimitive",
    "WidgetSurface",
]
