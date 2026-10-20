"""EclipseSdk — the ONE user-facing composition surface.

It delegates to the existing UI Engineering and Portfolio services; the SDK
adds only the user-level vocabulary (declarative widgets, composed pages, fund
portfolios, design locks). No blueprint engine and no accounting engine is
reimplemented here.
"""

from __future__ import annotations

import json
from typing import Any, Optional

from ..ui.model import (
    AddWidgetInput,
    Availability,
    ComponentLayoutSpec,
    CreatePageInput,
    ListBlueprintsQuery,
    UiComponentSpec,
    UpdatePageInput,
)
from ..ui.service import UiError, UiService
from .dashboards import DashboardService
from .locks import LockService
from .model import (
    MAX_CONFIG_BYTES,
    SOURCE_PRIMITIVES,
    WIDGET_PRIMITIVES,
    SdkAddStockInput,
    SdkAuditInput,
    SdkCreateFundInput,
    SdkCreateLockInput,
    SdkCreatePageInput,
    SdkPageWidget,
    SdkWidgetInput,
)
from .store import SdkStore

SDK_VERSION = "1.0.0"


class SdkError(Exception):
    def __init__(self, code: str, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


def _config_size(config: dict[str, Any]) -> int:
    try:
        return len(json.dumps(config, default=str))
    except (TypeError, ValueError):
        return MAX_CONFIG_BYTES + 1


def _parse_metadata(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else {}
        except (TypeError, ValueError):
            return {}
    return {}


class EclipseSdk:
    def __init__(
        self,
        store: SdkStore,
        ui: Optional[UiService],
        portfolio: Any,
        locks: LockService,
    ) -> None:
        self._store = store
        self._ui = ui
        self._portfolio = portfolio
        self.locks = locks
        self.dashboards = DashboardService(ui, store, locks)

    # ── capabilities ─────────────────────────────────────────────────────────

    def capabilities(self) -> dict[str, Any]:
        widgets = self._store.list_widgets()
        portfolios = self._safe_portfolios()
        try:
            dashboards = self.dashboards.list()
        except Exception:  # noqa: BLE001 - capabilities must never fail
            dashboards = {"dashboards": [], "activeDashboardId": None}
        return {
            "sdkVersion": SDK_VERSION,
            "runtime": "available" if self._ui is not None else "ui-unavailable",
            "widgets": {
                "canCreate": self._ui is not None,
                "canDelete": True,
                "count": len(widgets),
                "primitives": list(WIDGET_PRIMITIVES),
                "sourcePrimitives": sorted(SOURCE_PRIMITIVES),
                "componentPrefix": "sdk.",
            },
            "pages": {
                "canCreate": self._ui is not None,
                "canCompose": self._ui is not None,
                "routing": "?tab=pages&page=<blueprintId|path>",
            },
            "dashboards": {
                "available": self._ui is not None,
                "canMutate": self._ui is not None,
                "count": len(dashboards["dashboards"]),
                "activeDashboardId": dashboards["activeDashboardId"],
            },
            "portfolio": {
                "available": self._portfolio is not None,
                "canAddStock": self._portfolio is not None,
                "canCreateFund": self._portfolio is not None,
                "fundKinds": ["fund", "portfolio"],
                "portfolioCount": len(portfolios),
            },
            "design": {"canApply": True, "persisted": "server"},
            "locks": {
                "canCreate": True,
                "canUnlock": True,
                "resources": ["page", "widget", "portfolio", "design", "dashboard", "theme"],
                "header": "X-Eclipse-Unlock",
                "count": len(self._store.list_locks()),
            },
            "audit": {"count": self._store.audit_count()},
        }

    # ── audit ─────────────────────────────────────────────────────────────────

    def record_audit(self, input_model: SdkAuditInput, *, actor: Optional[str] = None) -> dict[str, Any]:
        return self._store.record_audit(
            actor=actor or input_model.actor or "operator",
            action=input_model.action,
            summary=input_model.summary,
            resource_type=input_model.resource_type,
            resource_id=input_model.resource_id,
            detail=input_model.detail,
        )

    def list_audit(
        self,
        *,
        limit: int = 100,
        action: Optional[str] = None,
        resource_type: Optional[str] = None,
    ) -> dict[str, Any]:
        entries = self._store.list_audit(limit=limit, action=action, resource_type=resource_type)
        return {"entries": entries, "total": self._store.audit_count()}

    def _audit(
        self,
        action: str,
        summary: str,
        *,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        detail: Optional[dict[str, Any]] = None,
        actor: Optional[str] = None,
    ) -> None:
        try:
            self._store.record_audit(
                action=action,
                actor=actor or "operator",
                resource_type=resource_type,
                resource_id=resource_id,
                summary=summary,
                detail=detail,
            )
        except Exception:  # noqa: BLE001 - audit never breaks a successful mutation
            pass

    def _safe_portfolios(self) -> list[dict[str, Any]]:
        if self._portfolio is None:
            return []
        try:
            return self._portfolio.list_portfolios()
        except Exception:  # noqa: BLE001 - capabilities must never fail
            return []

    # ── declarative widgets ──────────────────────────────────────────────────

    def create_widget(self, input_model: SdkWidgetInput, *, actor: Optional[str] = None) -> dict[str, Any]:
        if self._ui is None:
            raise SdkError("SDK_UI_UNAVAILABLE", "the UI runtime is unavailable", status_code=503)
        if input_model.primitive in SOURCE_PRIMITIVES and not input_model.source:
            raise SdkError("SDK_WIDGET_SOURCE_REQUIRED", f'primitive "{input_model.primitive}" needs a source')
        if _config_size(input_model.config) > MAX_CONFIG_BYTES:
            raise SdkError("SDK_WIDGET_CONFIG_TOO_LARGE", "widget configuration exceeds the size limit")
        component_id = f"sdk.{input_model.slug}"
        record = self._store.upsert_widget(
            slug=input_model.slug,
            component_id=component_id,
            label=input_model.label,
            description=input_model.description,
            icon=input_model.icon,
            category=input_model.category,
            primitive=input_model.primitive,
            source=input_model.source,
            surface=input_model.surface,
            config=input_model.config,
            sizes=input_model.sizes,
        )
        try:
            self._ui.register_component(self._component_spec(record), actor=actor)
        except UiError as exc:
            raise SdkError(exc.code, exc.message) from exc
        self._audit(
            "widget.create",
            f"Created {record['componentId']}",
            resource_type="widget",
            resource_id=record["componentId"],
            detail={"primitive": record["primitive"], "surface": record["surface"]},
            actor=actor,
        )
        return record

    def list_widgets(self) -> list[dict[str, Any]]:
        return self._store.list_widgets()

    def delete_widget(self, component_id: str, *, actor: Optional[str] = None) -> bool:
        record = self._store.get_widget(component_id)
        if record is None:
            raise SdkError("SDK_WIDGET_NOT_FOUND", f'unknown SDK widget "{component_id}"', status_code=404)
        # Keep the component id resolvable for pages that already placed it, but
        # mark it unavailable so the UI shows the honest state instead of
        # silently dropping the card. The host removes its renderer separately.
        if self._ui is not None:
            try:
                self._ui.register_component(
                    self._component_spec(record).model_copy(update={"availability": Availability.UNAVAILABLE}),
                    actor=actor,
                )
            except UiError:
                pass
        removed = self._store.delete_widget(component_id)
        if removed:
            self._audit(
                "widget.delete",
                f"Deleted {component_id}",
                resource_type="widget",
                resource_id=component_id,
                actor=actor,
            )
        return removed

    #: The per-primitive config surface an SDK widget instance may override.
    #: Mirrors the generic host widgets; a key outside this list is rejected by
    #: the UI engine, so the two can never silently diverge.
    _PRIMITIVE_FIELDS: dict[str, tuple[str, ...]] = {
        "data-table": ("portfolioId", "view", "pageSize", "dense"),
        "metric-card": ("portfolioId", "metric", "label", "format"),
        "line-chart": ("portfolioId", "view"),
        "area-chart": ("portfolioId", "view"),
        "bar-chart": ("portfolioId", "view"),
        "pie-chart": ("portfolioId", "view"),
        "list": ("portfolioId", "view"),
        "markdown": ("text",),
        "status-indicator": ("label", "status"),
        "empty-state": ("message",),
        "error-state": ("message",),
        "clock": ("timezone", "format", "showSeconds", "showDate", "label"),
    }

    def _component_spec(self, record: dict[str, Any]) -> UiComponentSpec:
        config = dict(record.get("config") or {})
        source = record.get("source")
        primitive = record["primitive"]
        default_config = {"primitive": primitive, **config}
        if source:
            default_config["source"] = source
        schema = []
        if primitive in SOURCE_PRIMITIVES:
            schema.append({
                "key": "source", "label": "Data source", "kind": "text",
                "required": False, "default": source or "",
                "placeholder": "portfolio:<id>:positions",
            })
        schema.append({"key": "title", "label": "Title", "kind": "text", "default": record["label"]})
        extra_fields = {
            "portfolioId": {"key": "portfolioId", "label": "Portfolio id", "kind": "text", "default": None},
            "view": {"key": "view", "label": "View", "kind": "text", "default": None},
            "pageSize": {"key": "pageSize", "label": "Page size", "kind": "number", "default": 25},
            "dense": {"key": "dense", "label": "Dense rows", "kind": "boolean", "default": False},
            "metric": {"key": "metric", "label": "Metric", "kind": "text", "default": None},
            "label": {"key": "label", "label": "Label", "kind": "text", "default": None},
            "format": {
                "key": "format", "label": "Format", "kind": "select", "default": "number",
                "options": [
                    {"value": "number", "label": "Number"},
                    {"value": "percent", "label": "Percent"},
                    {"value": "currency", "label": "Currency"},
                ],
            },
            "text": {"key": "text", "label": "Text / Markdown", "kind": "text", "default": ""},
            "status": {
                "key": "status", "label": "Status", "kind": "select", "default": "ok",
                "options": [
                    {"value": "ok", "label": "OK"},
                    {"value": "warning", "label": "Warning"},
                    {"value": "error", "label": "Error"},
                    {"value": "unknown", "label": "Unknown"},
                ],
            },
            "message": {"key": "message", "label": "Message", "kind": "text", "default": ""},
            "timezone": {
                "key": "timezone", "label": "Timezone", "kind": "text", "default": "",
                "placeholder": "UTC, Europe/London, America/New_York",
            },
            "showSeconds": {"key": "showSeconds", "label": "Show seconds", "kind": "boolean", "default": True},
            "showDate": {"key": "showDate", "label": "Show date", "kind": "boolean", "default": True},
        }
        for key in self._PRIMITIVE_FIELDS.get(primitive, ()):
            field = extra_fields.get(key)
            if field is not None:
                schema.append(field)
        if primitive == "clock":
            schema = [f for f in schema if f.get("key") != "format"]
            schema.append({
                "key": "format", "label": "Format", "kind": "select", "default": "24h",
                "options": [{"value": "24h", "label": "24-hour"}, {"value": "12h", "label": "12-hour"}],
            })
        return UiComponentSpec(
            id=record["componentId"],
            version=SDK_VERSION,
            display_name=record["label"],
            description=record.get("description") or "",
            category=record.get("category") or "custom",
            icon=record.get("icon") or "dashboard",
            tags=["sdk", "user", record["primitive"]],
            config_schema=schema,
            default_config=default_config,
            data_sources=[source] if source else ["any"],
            layout=ComponentLayoutSpec(
                sizes=record.get("sizes") or ["medium", "large"],
                default_height=(
                    320 if record["primitive"] in {"line-chart", "area-chart", "bar-chart", "pie-chart"}
                    else 180 if record["primitive"] == "clock"
                    else None
                ),
            ),
            availability=Availability.AVAILABLE,
            owner="user",
        )

    # ── pages ────────────────────────────────────────────────────────────────

    def create_page(self, input_model: SdkCreatePageInput, *, owner_id: str = "operator", actor: Optional[str] = None) -> dict[str, Any]:
        if self._ui is None:
            raise SdkError("SDK_UI_UNAVAILABLE", "the UI runtime is unavailable", status_code=503)
        # Validate every component BEFORE creating anything, so a bad id cannot
        # leave a half-composed page behind.
        for widget in input_model.widgets:
            try:
                self._ui.inspect_component(widget.component_id)
                issues = self._ui.validate_config(widget.component_id, widget.config)
            except UiError as exc:
                raise SdkError(exc.code, exc.message) from exc
            errors = [issue for issue in issues if issue.get("severity") == "error"]
            if errors:
                raise SdkError("SDK_PAGE_INVALID", str(errors[0].get("message") or "invalid widget configuration"))
        blueprint = self._ui.create_page(
            CreatePageInput(
                title=input_model.title,
                description=input_model.description,
                path=input_model.path,
                icon=input_model.icon,
                tags=input_model.tags,
                idempotency_key=input_model.idempotency_key,
            ),
            owner_id=owner_id,
            actor=actor,
        )
        for widget in input_model.widgets:
            blueprint = self._ui.add_widget(
                AddWidgetInput(
                    blueprint_id=blueprint.id,
                    component_id=widget.component_id,
                    config=widget.config,
                    height=widget.height,
                ),
                owner_id=owner_id,
                actor=actor,
            )
        self._audit(
            "page.create",
            f'Created the page "{blueprint.title}"',
            resource_type="page",
            resource_id=blueprint.id,
            detail={"path": blueprint.path, "widgetCount": len(input_model.widgets)},
            actor=actor,
        )
        return {
            "blueprint": blueprint.model_dump(by_alias=True),
            "verification": self._ui.verify_page(blueprint.id, owner_id=owner_id),
        }

    def add_page_widget(
        self,
        blueprint_id: str,
        widget: SdkPageWidget,
        *,
        owner_id: Optional[str] = None,
        actor: Optional[str] = None,
    ) -> dict[str, Any]:
        if self._ui is None:
            raise SdkError("SDK_UI_UNAVAILABLE", "the UI runtime is unavailable", status_code=503)
        try:
            self._ui.inspect_component(widget.component_id)
            issues = self._ui.validate_config(widget.component_id, widget.config)
        except UiError as exc:
            raise SdkError(exc.code, exc.message) from exc
        errors = [issue for issue in issues if issue.get("severity") == "error"]
        if errors:
            raise SdkError("SDK_PAGE_INVALID", str(errors[0].get("message") or "invalid widget configuration"))
        try:
            blueprint = self._ui.add_widget(
                AddWidgetInput(
                    blueprint_id=blueprint_id,
                    component_id=widget.component_id,
                    config=widget.config,
                    height=widget.height,
                ),
                owner_id=owner_id,
                actor=actor,
            )
        except UiError as exc:
            raise SdkError(exc.code, exc.message) from exc
        self._audit(
            "page.add_widget",
            f'Added {widget.component_id} to "{blueprint.title}"',
            resource_type="page",
            resource_id=blueprint_id,
            detail={"componentId": widget.component_id},
            actor=actor,
        )
        return {
            "blueprint": blueprint.model_dump(by_alias=True),
            "verification": self._ui.verify_page(blueprint_id, owner_id=owner_id),
        }

    def list_pages(self, *, owner_id: Optional[str] = None) -> dict[str, Any]:
        if self._ui is None:
            return {"blueprints": [], "total": 0}
        result = self._ui.list_blueprints(ListBlueprintsQuery(limit=200), owner_id=owner_id)
        # Command Center mirrors (`/dashboard/dash-*`) are agent-readable board
        # snapshots, not user pages. The SDK list is the user's page list.
        visible = [
            page for page in result.get("blueprints", [])
            if not str(page.get("path") or "").strip().lower().startswith("/dashboard/")
        ]
        return {**result, "blueprints": visible, "total": len(visible)}

    def update_page(self, blueprint_id: str, patch: dict[str, Any], *, owner_id: Optional[str] = None, actor: Optional[str] = None) -> dict[str, Any]:
        if self._ui is None:
            raise SdkError("SDK_UI_UNAVAILABLE", "the UI runtime is unavailable", status_code=503)
        try:
            blueprint = self._ui.update_page(
                blueprint_id,
                UpdatePageInput(
                    title=patch.get("title"),
                    description=patch.get("description"),
                    path=patch.get("path"),
                    icon=patch.get("icon"),
                    tags=patch.get("tags"),
                ),
                owner_id=owner_id,
                actor=actor,
            )
        except UiError as exc:
            raise SdkError(exc.code, exc.message) from exc
        self._audit(
            "page.update",
            f'Updated the page "{blueprint.title}"',
            resource_type="page",
            resource_id=blueprint_id,
            detail={"fields": sorted(patch.keys())},
            actor=actor,
        )
        return {"blueprint": blueprint.model_dump(by_alias=True)}

    def delete_page(self, blueprint_id: str, *, owner_id: Optional[str] = None, actor: Optional[str] = None) -> bool:
        if self._ui is None:
            raise SdkError("SDK_UI_UNAVAILABLE", "the UI runtime is unavailable", status_code=503)
        try:
            removed = self._ui.delete_page(blueprint_id, owner_id=owner_id, actor=actor)
        except UiError as exc:
            raise SdkError(exc.code, exc.message) from exc
        if removed:
            self._audit(
                "page.delete",
                f"Deleted page {blueprint_id}",
                resource_type="page",
                resource_id=blueprint_id,
                actor=actor,
            )
        return removed

    # ── portfolio ────────────────────────────────────────────────────────────

    def list_portfolios(self, *, owner_id: Optional[str] = None) -> list[dict[str, Any]]:
        if self._portfolio is None:
            raise SdkError("SDK_PORTFOLIO_UNAVAILABLE", "the portfolio engine is unavailable", status_code=503)
        return [self._portfolio_view(record) for record in self._portfolio.list_portfolios(owner_id)]

    def create_fund(self, input_model: SdkCreateFundInput, *, owner_id: Optional[str] = None, actor: Optional[str] = None) -> dict[str, Any]:
        if self._portfolio is None:
            raise SdkError("SDK_PORTFOLIO_UNAVAILABLE", "the portfolio engine is unavailable", status_code=503)
        metadata = {
            **input_model.metadata,
            "kind": "fund",
            "goal": input_model.goal,
            "icon": input_model.icon,
            "accent": input_model.accent,
        }
        metadata = {k: v for k, v in metadata.items() if v is not None}
        record = self._portfolio.create_portfolio(
            input_model.name,
            base_currency=input_model.base_currency,
            owner_id=owner_id,
            description=input_model.description,
            cost_basis_method=input_model.cost_basis_method,
            kind="fund",
            metadata=metadata,
            actor=actor,
        )
        fund = self._portfolio_view(record)
        self._audit(
            "portfolio.create_fund",
            f'Created the fund "{fund.get("name") or input_model.name}"',
            resource_type="portfolio",
            resource_id=str(fund.get("id") or ""),
            detail={"baseCurrency": input_model.base_currency, "goal": input_model.goal},
            actor=actor,
        )
        return fund

    def add_stock(self, portfolio_id: str, input_model: SdkAddStockInput, *, actor: Optional[str] = None) -> dict[str, Any]:
        if self._portfolio is None:
            raise SdkError("SDK_PORTFOLIO_UNAVAILABLE", "the portfolio engine is unavailable", status_code=503)
        payload: dict[str, Any] = {
            "type": input_model.type,
            "symbol": input_model.symbol,
            "quantity": input_model.quantity,
        }
        for key in ("price", "currency", "trade_date", "fees", "notes"):
            value = getattr(input_model, key)
            if value is not None:
                payload[key] = value
        result = self._portfolio.add_position(portfolio_id, payload, actor_id=actor)
        self._audit(
            "portfolio.add_stock",
            f"Added {input_model.symbol} to the portfolio",
            resource_type="portfolio",
            resource_id=portfolio_id,
            detail={"symbol": input_model.symbol, "type": input_model.type},
            actor=actor,
        )
        return result

    def _portfolio_view(self, record: dict[str, Any]) -> dict[str, Any]:
        metadata = _parse_metadata(record.get("metadata"))
        return {
            **record,
            "kind": record.get("kind") or metadata.get("kind") or "portfolio",
            "metadata": metadata,
        }

    # ── locks ────────────────────────────────────────────────────────────────

    def create_lock(self, input_model: SdkCreateLockInput, *, actor: Optional[str] = None):
        return self.locks.create(input_model, actor=actor)

    def list_locks(self, *, resource_type: Optional[str] = None, resource_id: Optional[str] = None):
        return self.locks.list(resource_type=resource_type, resource_id=resource_id)

    def unlock(self, lock_id: str, passphrase: str, *, actor: Optional[str] = None) -> dict[str, Any]:
        return self.locks.unlock(lock_id, passphrase, actor=actor)

    def remove_lock(self, lock_id: str, *, passphrase: Optional[str] = None, actor: Optional[str] = None) -> bool:
        return self.locks.remove(lock_id, passphrase=passphrase, actor=actor)


__all__ = ["EclipseSdk", "SDK_VERSION", "SdkError"]
