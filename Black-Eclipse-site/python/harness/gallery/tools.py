"""The gallery tools — publish, browse, favourite, clone.

Cloning is the interesting one: it copies a published SPEC into the quant
store as a **new** strategy, so the published record and the live strategy
never share an identity. The original is untouched, and the clone is a normal
strategy from that moment on - it can be backtested, graded and published again.
"""

from __future__ import annotations

import json
from typing import Any, Optional

from ..tools import ToolContext, ToolDefinition


def _gallery(ctx: ToolContext) -> Any:
    from .bootstrap import get_gallery_store

    store = getattr(ctx, "gallery_store", None) or get_gallery_store()
    if store is None:
        raise RuntimeError(
            "the gallery is not configured in this runtime; the gallery tools are "
            "unavailable")
    return store


def _quant(ctx: ToolContext) -> Any:
    store = getattr(ctx, "quant_store", None)
    if store is None:
        raise RuntimeError("the quant store is unavailable in this runtime")
    return store


def _err(code: str, message: str) -> tuple[str, Any]:
    return (f"ERROR - {code}: {message}",
            {"status": "ERROR", "error": {"code": code, "message": message}})


async def publish_strategy(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    """Publish a strategy into the local gallery."""
    try:
        strategy_id = str(args.get("strategyId") or "").strip()
        if not strategy_id:
            return _err("STRATEGY_ID_REQUIRED", "provide `strategyId`")
        store = _gallery(ctx)
        quant = _quant(ctx)
        try:
            record = quant.get_strategy(strategy_id, args.get("version"))
        except Exception as exc:  # noqa: BLE001
            return _err("STRATEGY_NOT_FOUND", str(exc)[:200])
        spec = dict(record.get("spec") or {})
        grade = args.get("grade")
        score = args.get("score")
        summary = str(args.get("summary") or "")
        report = str(args.get("report") or "")
        symbols = [str(s) for s in (args.get("symbols")
                                     or (spec.get("universe") or {}).get("symbols") or [])]
        entry = store.publish(
            name=str(args.get("name") or record.get("name") or strategy_id),
            spec=spec,
            strategy_id=strategy_id,
            strategy_version=str(record.get("version") or ""),
            description=str(args.get("description") or ""),
            author=str(args.get("author") or "local"),
            grade=(str(grade) if grade else None),
            score=(float(score) if score is not None else None),
            summary=summary,
            report=report,
            symbols=symbols,
        )
        return (f"Published {entry.name} as `{entry.id}`"
                + (f" (grade {entry.grade})" if entry.grade else "") + ".",
                {"status": "OK", "published": entry.to_dict(include_spec=True)})
    except Exception as exc:  # noqa: BLE001
        return _err("PUBLISH_FAILED", str(exc))


async def list_gallery(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    """Browse the published gallery."""
    try:
        store = _gallery(ctx)
        entries = store.list(limit=int(args.get("limit") or 50))
        if not entries:
            return ("The gallery is empty.", {"status": "OK", "entries": [],
                                            "count": 0})
        lines = [f"{e.id} · {e.name}"
                 + (f" · grade {e.grade}" if e.grade else "")
                 + f" · {e.favourites} ★ · {e.clones} clones"
                 for e in entries]
        return ("\n".join(lines), {"status": "OK",
                                    "entries": [e.to_dict() for e in entries],
                                    "count": len(entries)})
    except Exception as exc:  # noqa: BLE001
        return _err("GALLERY_LIST_FAILED", str(exc))


async def favourite_published_strategy(args: dict[str, Any],
                                       ctx: ToolContext) -> tuple[str, Any]:
    """Favourite a published strategy."""
    try:
        store = _gallery(ctx)
        published_id = str(args.get("publishedId") or "").strip()
        if not published_id:
            return _err("PUBLISHED_ID_REQUIRED", "provide `publishedId`")
        entry = store.favourite(published_id)
        if entry is None:
            return _err("PUBLISHED_NOT_FOUND", f"no published {published_id!r}")
        return (f"{entry.name} now has {entry.favourites} favourite(s).",
                {"status": "OK", "published": entry.to_dict()})
    except Exception as exc:  # noqa: BLE001
        return _err("FAVOURITE_FAILED", str(exc))


async def clone_published_strategy(args: dict[str, Any],
                                   ctx: ToolContext) -> tuple[str, Any]:
    """Clone a published strategy into the quant store as a new strategy."""
    try:
        store = _gallery(ctx)
        quant = _quant(ctx)
        published_id = str(args.get("publishedId") or "").strip()
        if not published_id:
            return _err("PUBLISHED_ID_REQUIRED", "provide `publishedId`")
        entry = store.get(published_id)
        if entry is None:
            return _err("PUBLISHED_NOT_FOUND", f"no published {published_id!r}")
        if not entry.spec:
            return _err("PUBLISHED_HAS_NO_SPEC",
                        "the published record carries no strategy spec")
        from ..quant.strategy import StrategySpec

        try:
            spec = StrategySpec.model_validate(entry.spec)
        except Exception as exc:  # noqa: BLE001
            return _err("PUBLISHED_SPEC_INVALID", str(exc)[:200])
        saved = quant.save_strategy(spec, description=(
            f"cloned from {entry.id} ({entry.name})"))
        store.count_clone(published_id)
        return (f"Cloned {entry.name} into strategy "
                f"`{saved.get('id')}` v{saved.get('version')}.",
                {"status": "OK", "published": entry.to_dict(),
                 "strategy": {"id": saved.get("id"),
                              "version": saved.get("version")}})
    except Exception as exc:  # noqa: BLE001
        return _err("CLONE_FAILED", str(exc))


GALLERY_TOOLS: tuple[str, ...] = (
    "publish_strategy",
    "list_gallery",
    "favourite_published_strategy",
    "clone_published_strategy",
)


def register_gallery_tools(registry: Any) -> list[str]:
    """Register the gallery tools on the one tool registry."""
    registry.register(ToolDefinition(
        name="publish_strategy",
        description="Publish a strategy into the local gallery: the spec, the grade "
                    "its evidence earned and the report it came from are FROZEN into "
                    "an immutable published record. The live strategy may move on; "
                    "the published record does not.",
        input_schema={"type": "object", "properties": {
            "strategyId": {"type": "string"},
            "version": {"type": "string"},
            "name": {"type": "string"},
            "description": {"type": "string"},
            "author": {"type": "string"},
            "grade": {"type": "string"},
            "score": {"type": "number"},
            "summary": {"type": "string"},
            "report": {"type": "string", "description": "the Edge Report markdown"},
            "symbols": {"type": "array", "items": {"type": "string"}}},
            "required": ["strategyId"]},
        handler=publish_strategy, permission="read", risk="low", timeout_ms=60_000))
    registry.register(ToolDefinition(
        name="list_gallery",
        description="Browse the published gallery: every published strategy, its "
                    "grade, its favourites and its clone count.",
        input_schema={"type": "object", "properties": {
            "limit": {"type": "integer"}}, "required": []},
        handler=list_gallery, permission="read", risk="low", timeout_ms=30_000))
    registry.register(ToolDefinition(
        name="favourite_published_strategy",
        description="Favourite a published strategy.",
        input_schema={"type": "object", "properties": {
            "publishedId": {"type": "string"}}, "required": ["publishedId"]},
        handler=favourite_published_strategy, permission="read", risk="low",
        timeout_ms=30_000))
    registry.register(ToolDefinition(
        name="clone_published_strategy",
        description="Clone a published strategy into the quant store as a NEW "
                    "strategy. The published record and the live strategy never share "
                    "an identity, and the original is untouched.",
        input_schema={"type": "object", "properties": {
            "publishedId": {"type": "string"}}, "required": ["publishedId"]},
        handler=clone_published_strategy, permission="read", risk="low",
        timeout_ms=60_000))
    return list(GALLERY_TOOLS)


__all__ = ["GALLERY_TOOLS", "register_gallery_tools"]
