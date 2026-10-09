"""UI component catalog — the runtime's queryable registry of components.

The catalog answers three questions the agent must never guess at: what
components exist, how each may be configured, and which data sources each can
consume. It is populated from two sources, both explicit:

  * a built-in seed of the FOUNDATIONAL component kinds (Phase 2.3) so the
    runtime is usable standalone, and
  * registrations — from the host (syncing the real front-end widget registry)
    or from an enabled plugin's UI contribution.

Configuration is validated against a component's declared schema; the check
mirrors `src/lib/ui-engineering/catalog.ts` so a blueprint validated here behaves
identically in the browser. Unknown config keys are WARNINGS (some widgets
accept dynamic config); wrong types and missing required fields are ERRORS, so
an invalid configuration is rejected before it can render.
"""

from __future__ import annotations

from typing import Any, Optional

from .model import (
    Availability,
    CatalogQuery,
    ComponentLayoutSpec,
    ConfigFieldSpec,
    ConfigIssue,
    OwnershipKind,
    Severity,
    UiComponentSpec,
)


class CatalogError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _field(key: str, label: str, kind: str, **kw: Any) -> ConfigFieldSpec:
    return ConfigFieldSpec(key=key, label=label, kind=kind, **kw)  # type: ignore[arg-type]


def _spec(
    component_id: str, category: str, label: str, desc: str, icon: str,
    *, data_sources: Optional[list[str]] = None,
    fields: Optional[list[ConfigFieldSpec]] = None,
    sizes: Optional[list[str]] = None,
    default_height: Optional[int] = None,
) -> UiComponentSpec:
    return UiComponentSpec(
        id=component_id, display_name=label, description=desc, category=category,
        icon=icon, tags=[t for t in (category, icon) if t],
        data_sources=data_sources or [], config_schema=fields or [],
        layout=ComponentLayoutSpec(
            sizes=sizes or ["medium", "large"], default_height=default_height,
        ),
    )


def builtin_specs() -> list[UiComponentSpec]:
    """The foundational component kinds every Eclipse UI can compose."""
    return [
        _spec("metric-card", "metrics", "Metric Card", "A single headline metric with a label, value and optional delta.", "activity",
              data_sources=["any"], fields=[
                  _field("label", "Label", "text"),
                  _field("metric", "Metric key", "text", placeholder="e.g. portfolio.totalValue"),
                  _field("format", "Format", "select", options=[{"value": "number", "label": "Number"}, {"value": "percent", "label": "Percent"}, {"value": "currency", "label": "Currency"}]),
              ], sizes=["small", "medium"], default_height=140),
        _spec("data-table", "tables", "Data Table", "A sortable, pageable table over a data source.", "table",
              data_sources=["any"], fields=[
                  _field("source", "Data source", "text"),
                  _field("pageSize", "Page size", "number", min=1, max=500, default=25),
                  _field("dense", "Dense rows", "boolean"),
              ], sizes=["large", "full"], default_height=360),
        _spec("line-chart", "charts", "Line Chart", "A time-series line chart.", "line-chart",
              data_sources=["any"], fields=[
                  _field("source", "Data source", "text"),
                  _field("symbol", "Symbol", "symbol"),
                  _field("series", "Series", "symbols"),
              ], sizes=["large", "full"], default_height=320),
        _spec("bar-chart", "charts", "Bar Chart", "A categorical bar chart.", "bar-chart",
              data_sources=["any"], fields=[
                  _field("source", "Data source", "text"),
                  _field("symbol", "Symbol", "symbol"),
              ], sizes=["large", "full"], default_height=320),
        _spec("pie-chart", "charts", "Pie Chart", "A proportional / allocation pie chart.", "pie",
              data_sources=["any"], fields=[_field("source", "Data source", "text")],
              sizes=["medium", "large"], default_height=320),
        _spec("area-chart", "charts", "Area Chart", "A stacked or overlaid area chart.", "line-chart",
              data_sources=["any"], fields=[_field("source", "Data source", "text")],
              sizes=["large", "full"], default_height=320),
        _spec("filter-bar", "filters", "Filter Bar", "A row of filters that scope a page's data.", "layers",
              fields=[
                  _field("field", "Field", "text"),
                  _field("mode", "Mode", "select", options=[{"value": "single", "label": "Single"}, {"value": "multi", "label": "Multi"}]),
              ], sizes=["full"], default_height=64),
        _spec("form", "forms", "Form", "A validated input form.", "file-text",
              fields=[_field("submitLabel", "Submit label", "text")],
              sizes=["medium", "large"]),
        _spec("timeline", "timelines", "Timeline", "A vertical event timeline.", "calendar",
              data_sources=["any"], fields=[_field("source", "Data source", "text")],
              sizes=["medium", "large"], default_height=360),
        _spec("status-indicator", "status", "Status Indicator", "A coloured status pill with a label.", "heart",
              fields=[
                  _field("status", "Status", "select", options=[
                      {"value": "ok", "label": "OK"}, {"value": "warning", "label": "Warning"},
                      {"value": "error", "label": "Error"}, {"value": "unknown", "label": "Unknown"},
                  ]),
                  _field("label", "Label", "text"),
              ], sizes=["small"], default_height=120),
        _spec("tree", "trees", "Tree", "A collapsible hierarchical tree.", "layers",
              data_sources=["any"], fields=[_field("source", "Data source", "text")],
              sizes=["medium", "large"], default_height=360),
        _spec("log-viewer", "logs", "Log Viewer", "A streaming log / output viewer.", "file-text",
              data_sources=["any"], fields=[
                  _field("source", "Data source", "text"),
                  _field("tail", "Tail lines", "number", min=10, max=5000, default=200),
              ], sizes=["large", "full"], default_height=360),
        _spec("agent-graph", "agents", "Agent Graph", "A graph of agents and their delegation edges.", "bot",
              data_sources=["agent:activity"], fields=[_field("source", "Data source", "text")],
              sizes=["large", "full"], default_height=420),
        _spec("task-board", "tasks", "Task Board", "A board of tasks grouped by status.", "layers",
              data_sources=["tasks"], fields=[_field("groupBy", "Group by", "text")],
              sizes=["large", "full"], default_height=420),
        _spec("markdown", "content", "Markdown", "Rendered Markdown content.", "file-text",
              fields=[_field("text", "Markdown", "text")], sizes=["medium", "large", "full"]),
        _spec("artifact-preview", "content", "Artifact Preview", "An inline preview of an artifact.", "file-text",
              data_sources=["artifacts"], fields=[_field("artifactId", "Artifact id", "text")],
              sizes=["medium", "large"], default_height=360),
        _spec("plugin-panel", "plugins", "Plugin Panel", "A panel contributed by a plugin.", "layers",
              fields=[
                  _field("pluginId", "Plugin id", "text"),
                  _field("panelId", "Panel id", "text"),
              ], sizes=["medium", "large"], default_height=320),
        _spec("empty-state", "content", "Empty State", "A deliberate empty placeholder.", "dashboard",
              fields=[
                  _field("title", "Title", "text"),
                  _field("message", "Message", "text"),
              ], sizes=["small", "medium"], default_height=160),
        _spec("error-state", "content", "Error State", "A recoverable error placeholder.", "dashboard",
              fields=[
                  _field("title", "Title", "text"),
                  _field("message", "Message", "text"),
              ], sizes=["small", "medium"], default_height=160),
    ]


def _tokenize(value: str) -> list[str]:
    cleaned = "".join(ch.lower() if ch.isalnum() else " " for ch in value)
    return [t for t in cleaned.split() if t]


def validate_component_config(spec: UiComponentSpec, config: Optional[dict[str, Any]]) -> list[ConfigIssue]:
    """Return issues for a component configuration (errors + warnings)."""
    issues: list[ConfigIssue] = []
    value = config or {}
    by_key = {f.key: f for f in spec.config_schema}

    for key, raw in value.items():
        field = by_key.get(key)
        if field is None:
            issues.append(ConfigIssue(path=key, message=f'unknown configuration key "{key}"', severity=Severity.WARNING))
            continue
        if field.kind == "number":
            if not isinstance(raw, (int, float)) or isinstance(raw, bool):
                issues.append(ConfigIssue(path=key, message=f'expected a number for "{key}"'))
            elif field.min is not None and raw < field.min:
                issues.append(ConfigIssue(path=key, message=f'"{key}" is below its minimum of {field.min}'))
            elif field.max is not None and raw > field.max:
                issues.append(ConfigIssue(path=key, message=f'"{key}" is above its maximum of {field.max}'))
        elif field.kind == "boolean":
            if not isinstance(raw, bool):
                issues.append(ConfigIssue(path=key, message=f'expected a boolean for "{key}"'))
        elif field.kind == "symbols":
            if not isinstance(raw, list) or any(not isinstance(v, str) for v in raw):
                issues.append(ConfigIssue(path=key, message=f'expected a string array for "{key}"'))
        elif field.kind == "select":
            allowed = {o.get("value") for o in field.options}
            if not isinstance(raw, str) or (allowed and raw not in allowed):
                issues.append(ConfigIssue(path=key, message=f'"{key}" is not one of the allowed options'))
        else:  # text | symbol
            if not isinstance(raw, str):
                issues.append(ConfigIssue(path=key, message=f'expected a string for "{key}"'))

    for field in spec.config_schema:
        if field.required and value.get(field.key) is None:
            issues.append(ConfigIssue(path=field.key, message=f'missing required configuration "{field.key}"'))

    return issues


class UiCatalog:
    """In-process registry of component specs, keyed by stable id."""

    def __init__(self, specs: Optional[list[UiComponentSpec]] = None) -> None:
        self._specs: dict[str, UiComponentSpec] = {}
        for spec in specs if specs is not None else builtin_specs():
            self.register(spec)

    def register(self, spec: UiComponentSpec, *, replace: bool = False) -> UiComponentSpec:
        if spec.id in self._specs and not replace:
            raise CatalogError("UI_COMPONENT_EXISTS", f'component "{spec.id}" is already registered')
        self._specs[spec.id] = spec
        return spec

    def has(self, component_id: str) -> bool:
        return component_id in self._specs

    def get(self, component_id: str) -> Optional[UiComponentSpec]:
        return self._specs.get(component_id)

    def list(self) -> list[UiComponentSpec]:
        return sorted(self._specs.values(), key=lambda s: s.id)

    def categories(self) -> list[str]:
        return sorted({s.category for s in self._specs.values()})

    def data_sources(self) -> list[str]:
        return sorted({ds for s in self._specs.values() for ds in s.data_sources})

    def search(self, query: CatalogQuery) -> list[UiComponentSpec]:
        tokens = _tokenize(query.text or "")
        scored: list[tuple[float, UiComponentSpec]] = []
        for spec in self.list():
            if query.category and spec.category != query.category:
                continue
            if query.owner and spec.owner != query.owner:
                continue
            if query.availability and spec.availability != query.availability:
                continue
            if query.data_source and query.data_source not in spec.data_sources:
                continue
            score = 0.0
            if tokens:
                haystack = [spec.id.lower(), spec.display_name.lower(), spec.description.lower(), spec.category.lower(), *[t.lower() for t in spec.tags]]
                for token in tokens:
                    if spec.id.lower() == token:
                        score += 8
                    elif token in haystack:
                        score += 4
                    elif any(token in h for h in haystack):
                        score += 2
                if score == 0:
                    continue
            scored.append((score, spec))
        scored.sort(key=lambda pair: (-pair[0], pair[1].id))
        return [spec for _, spec in scored[: query.limit]]


__all__ = ["CatalogError", "UiCatalog", "builtin_specs", "validate_component_config"]
