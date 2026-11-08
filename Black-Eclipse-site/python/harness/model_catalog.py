"""The unified model/research catalog.

Eclipse has several registries (quant strategies + experiments, ML models +
datasets, statistical features, factors). Each is authoritative for its own
artifacts, but a quant turn needs ONE read to answer "do we already have this?"
before it rebuilds. This module is that read: it never writes, never invents an
entry, and reports an empty section as an empty registry — not as an unavailable
capability.

The tool is registered on the ONE registry from `quant/bootstrap.py`; the stores
are resolved lazily at call time, so registration order does not matter.
"""

from __future__ import annotations

from collections import Counter
from typing import Any, Optional

from .tools import ToolContext, ToolDefinition

CATALOG_TOOL = "model_catalog"
MAX_LIMIT = 100

_KINDS = (
    "all", "strategy", "experiment", "ml_model", "ml_dataset", "feature",
    "factor",
)


def _first(row: dict[str, Any], keys: tuple[str, ...]) -> Optional[str]:
    for key in keys:
        value = row.get(key)
        if value is not None and str(value).strip():
            return str(value)
    return None


def _normalize(
    kind: str,
    row: dict[str, Any],
    *,
    id_keys: tuple[str, ...] = ("id",),
    name_keys: tuple[str, ...] = ("name",),
    version_keys: tuple[str, ...] = ("version", "latestVersion"),
    status_keys: tuple[str, ...] = ("status",),
    updated_keys: tuple[str, ...] = ("updatedAt", "createdAt"),
) -> dict[str, Any]:
    status = _first(row, status_keys) or ("archived" if row.get("archived") else "active")
    return {
        "kind": kind,
        "id": _first(row, id_keys),
        "name": _first(row, name_keys),
        "version": _first(row, version_keys),
        "status": status,
        "updatedAt": _first(row, updated_keys),
    }


def _safe_list(call: Any) -> list[dict[str, Any]]:
    try:
        value = call()
        return [row for row in (value or []) if isinstance(row, dict)]
    except Exception:  # noqa: BLE001 - a missing registry is an empty section
        return []


def _quant_entries(
    store: Optional[Any], limit: int, include_archived: bool, selected: str,
) -> list[dict[str, Any]]:
    if store is None:
        return []
    out: list[dict[str, Any]] = []
    if selected in ("all", "strategy"):
        out.extend(
            _normalize(
                "strategy", row,
                version_keys=("latestVersion",),
                status_keys=("archived", "status"),
                updated_keys=("updatedAt", "createdAt"),
            )
            for row in _safe_list(
                lambda: store.list_strategies(include_archived=include_archived)
            )[:limit]
        )
    if selected in ("all", "experiment"):
        out.extend(
            _normalize(
                "experiment", row,
                name_keys=("kind", "strategyId"),
                version_keys=("strategyVersion", "version"),
                updated_keys=("createdAt", "updatedAt"),
            )
            for row in _safe_list(lambda: store.list_experiments(limit=limit))[:limit]
        )
    return out


def _ml_entries(
    store: Optional[Any], limit: int, selected: str,
) -> list[dict[str, Any]]:
    if store is None:
        return []
    out: list[dict[str, Any]] = []
    if selected in ("all", "ml_model"):
        out.extend(
            _normalize(
                "ml_model", row,
                name_keys=("name", "family"),
                version_keys=("latestVersion", "version"),
            )
            for row in _safe_list(lambda: store.list_models(limit=limit))[:limit]
        )
    if selected in ("all", "ml_dataset"):
        out.extend(
            _normalize(
                "ml_dataset", row,
                name_keys=("name", "id"),
                version_keys=("latestVersion", "version"),
                updated_keys=("updatedAt", "createdAt"),
            )
            for row in _safe_list(lambda: store.list_datasets(limit=limit))[:limit]
        )
    return out


def _stats_entries(store: Optional[Any], limit: int) -> list[dict[str, Any]]:
    if store is None:
        return []
    return [
        _normalize(
            "feature", row,
            name_keys=("name", "id"),
            version_keys=("latestVersion", "version"),
            updated_keys=("updatedAt", "createdAt"),
        )
        for row in _safe_list(lambda: store.list_features())[:limit]
    ]


def _factor_entries(
    store: Optional[Any], limit: int, include_archived: bool,
) -> list[dict[str, Any]]:
    if store is None:
        return []
    return [
        _normalize(
            "factor", row,
            name_keys=("name", "id"),
            version_keys=("latestVersion", "version"),
            status_keys=("archived", "status"),
            updated_keys=("updatedAt", "createdAt"),
        )
        for row in _safe_list(
            lambda: store.list_factors(include_archived=include_archived)
        )[:limit]
    ]


def build_catalog(
    *,
    quant_store: Optional[Any] = None,
    ml_store: Optional[Any] = None,
    stats_store: Optional[Any] = None,
    factor_store: Optional[Any] = None,
    kind: str = "all",
    query: str = "",
    limit: int = 20,
    include_archived: bool = False,
) -> dict[str, Any]:
    """Aggregate the registries into ONE bounded, read-only result."""
    selected = str(kind or "all").strip().lower()
    if selected not in _KINDS:
        selected = "all"
    try:
        bound = max(1, min(int(limit or 20), MAX_LIMIT))
    except (TypeError, ValueError):
        bound = 20

    entries: list[dict[str, Any]] = []
    if selected in ("all", "strategy", "experiment"):
        entries.extend(_quant_entries(quant_store, bound, include_archived, selected))
    if selected in ("all", "ml_model", "ml_dataset"):
        entries.extend(_ml_entries(ml_store, bound, selected))
    if selected in ("all", "feature"):
        entries.extend(_stats_entries(stats_store, bound))
    if selected in ("all", "factor"):
        entries.extend(_factor_entries(factor_store, bound, include_archived))

    needle = str(query or "").strip().lower()
    if needle:
        entries = [
            entry for entry in entries
            if any(needle in str(entry.get(key) or "").lower()
                   for key in ("kind", "id", "name", "status"))
        ]

    entries.sort(key=lambda entry: str(entry.get("updatedAt") or ""), reverse=True)
    counts = Counter(str(entry.get("kind") or "unknown") for entry in entries)
    return {
        "status": "OK",
        "total": len(entries),
        "counts": dict(sorted(counts.items())),
        "entries": entries[:bound],
        "truncated": len(entries) > bound,
        "note": (
            "Read-only registry aggregation. An empty section means none is "
            "registered yet, not that the capability is unavailable."
        ),
    }


def _stores(ctx: Any) -> tuple[Any, Any, Any, Any]:
    def fallback(attr: str, importer: Any) -> Any:
        # An explicit attribute (even None) wins: the caller is saying "this
        # registry is unavailable for this read". Only an ABSENT attribute falls
        # back to the process-wide store.
        if hasattr(ctx, attr):
            return getattr(ctx, attr)
        try:
            return importer()
        except Exception:  # noqa: BLE001 - an absent registry is an empty section
            return None

    from .factors.service import get_factor_store  # noqa: PLC0415
    from .ml.service import get_ml_store  # noqa: PLC0415
    from .stats.service import get_stats_store  # noqa: PLC0415

    return (
        getattr(ctx, "quant_store", None),
        fallback("ml_store", get_ml_store),
        fallback("stats_store", get_stats_store),
        fallback("factor_store", get_factor_store),
    )


def _render(result: dict[str, Any]) -> str:
    if not result["total"]:
        return (
            "Model catalog is empty: no strategies, experiments, ML models/datasets, "
            "features or factors are registered yet. This is an empty registry, not "
            "an unavailable capability."
        )
    parts = ", ".join(f"{kind} {count}" for kind, count in result["counts"].items())
    lines = [f"Model catalog: {result['total']} artifact(s) — {parts}."]
    for entry in result["entries"]:
        bits = [f"[{entry['kind']}]", str(entry.get("name") or entry.get("id") or "?")]
        if entry.get("id") and entry.get("id") != entry.get("name"):
            bits.append(f"id={entry['id']}")
        if entry.get("version"):
            bits.append(f"v{entry['version']}")
        if entry.get("status"):
            bits.append(str(entry["status"]))
        lines.append("- " + " ".join(bits))
    if result["truncated"]:
        lines.append(f"(Showing the first {len(result['entries'])}.)")
    lines.append(result["note"])
    return "\n".join(lines)


async def model_catalog(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    """Read the unified catalog. It never writes and never invents an entry."""
    quant_store, ml_store, stats_store, factor_store = _stores(ctx)
    result = build_catalog(
        quant_store=quant_store,
        ml_store=ml_store,
        stats_store=stats_store,
        factor_store=factor_store,
        kind=str(args.get("kind") or "all"),
        query=str(args.get("query") or ""),
        limit=int(args.get("limit") or 20),
        include_archived=bool(args.get("includeArchived", False)),
    )
    return _render(result), result


def register_model_catalog_tool(registry: Any) -> None:
    registry.register(ToolDefinition(
        name=CATALOG_TOOL,
        description=(
            "List the models and research artifacts Eclipse already has, so you "
            "reuse before you rebuild: quant strategies, quant experiments, ML "
            "models and datasets, statistical features and factors. Read-only; an "
            "empty section means none is registered, not that the capability is "
            "unavailable."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "kind": {
                    "type": "string",
                    "enum": list(_KINDS),
                    "description": "Filter to one artifact family (default all).",
                },
                "query": {
                    "type": "string",
                    "description": "Optional case-insensitive id/name/status filter.",
                },
                "limit": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": MAX_LIMIT,
                    "description": "Maximum entries returned (default 20).",
                },
                "includeArchived": {
                    "type": "boolean",
                    "description": "Include archived strategies/factors (default false).",
                },
            },
            "additionalProperties": False,
        },
        handler=model_catalog,
        permission="read",
        risk="low",
        timeout_ms=15_000,
    ))


__all__ = [
    "CATALOG_TOOL",
    "build_catalog",
    "model_catalog",
    "register_model_catalog_tool",
]
