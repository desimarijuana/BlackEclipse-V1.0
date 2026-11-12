"""Spawn + blackboard tools (C5)."""

from __future__ import annotations

import json
from typing import Any

from .board import BoardStore
from .service import reconcile_budget, spec_from_dict, spawn_child, spawn_many, synthesize


def _emit(ctx: Any, event_type: str, data: dict[str, Any]) -> None:
    emitter = getattr(ctx, "emitter", None)
    if emitter is None:
        return
    try:
        emitter.emit_sync(event_type, data)
    except Exception:  # noqa: BLE001 - observability must never break a spawn
        pass


def register_spawn_tools(registry: Any) -> None:
    from ..tools import ToolDefinition  # noqa: PLC0415 - avoid a module cycle

    async def _spawn(args: dict[str, Any], ctx: Any) -> tuple[str, dict[str, Any]]:
        raw_children = args.get("children")
        if isinstance(raw_children, list) and raw_children:
            specs = [spec_from_dict(item) for item in raw_children if isinstance(item, dict)]
            specs = [spec for spec in specs if spec.objective.strip()]
            if not specs:
                return ("INVALID_INPUT: no child objective.", {"status": "INVALID_INPUT"})
            _emit(ctx, "spawn.started", {"children": len(specs)})
            outcomes = await spawn_many(specs, ctx)
            synthesis = synthesize(outcomes)
            _emit(ctx, "spawn.completed", {
                "children": [o.run_id or o.job_id for o in outcomes],
                "statuses": [o.status for o in outcomes],
                "conflicts": len(synthesis["conflicts"]),
            })
            payload = {
                "status": "completed" if all(o.status == "completed" for o in outcomes) else "partial",
                "children": [o.to_dict() for o in outcomes],
                "synthesis": synthesis,
                "budget": reconcile_budget(specs, outcomes),
            }
            return (
                f"SPAWN: {len(outcomes)} child(ren)\n{synthesis['text']}",
                payload,
            )

        spec = spec_from_dict(args)
        _emit(ctx, "spawn.started", {"objective": spec.objective[:500], "agent": spec.agent})
        outcome = await spawn_child(spec, ctx)
        _emit(
            ctx,
            "spawn.completed" if outcome.status in ("completed", "queued") else "spawn.failed",
            {"runId": outcome.run_id, "jobId": outcome.job_id,
             "status": outcome.status, "tokensUsed": outcome.tokens_used,
             "errorClass": outcome.error_class or None},
        )
        payload = {
            "status": outcome.status, "child": outcome.to_dict(),
            "budget": reconcile_budget([spec], [outcome]),
        }
        text = f"SPAWN {outcome.status.upper()}"
        if outcome.run_id:
            text += f" (run {outcome.run_id})"
        if outcome.output:
            text += f"\n{outcome.output[:8_000]}"
        if outcome.error:
            text += f"\n{outcome.error}"
        return text, payload

    async def _board_write(args: dict[str, Any], ctx: Any) -> tuple[str, dict[str, Any]]:
        store = getattr(ctx, "memory_store", None)
        run_id = str(getattr(ctx, "run_id", "") or "")
        if store is None or not run_id:
            return ("UNAVAILABLE: no blackboard is bound.", {"status": "UNAVAILABLE"})
        try:
            entry = BoardStore(store).write(
                run_id=run_id,
                kind=str(args.get("kind") or "note"),
                text=str(args.get("text") or ""),
                handles=args.get("handles") if isinstance(args.get("handles"), list) else [],
                status=str(args.get("status") or "supported"),
                author=str(args.get("author") or "agent"),
            )
        except ValueError as exc:
            return (f"REFUSED: {exc}", {"status": "REFUSED", "reason": str(exc)})
        return (f"board entry {entry['id']}", {"status": "OK", "entry": entry})

    async def _board_read(args: dict[str, Any], ctx: Any) -> tuple[str, dict[str, Any]]:
        store = getattr(ctx, "memory_store", None)
        run_id = str(getattr(ctx, "run_id", "") or "")
        if store is None or not run_id:
            return ("UNAVAILABLE: no blackboard is bound.", {"status": "UNAVAILABLE"})
        kind = args.get("kind") if args.get("kind") in (
            "fact", "artifact", "evidence", "question", "decision", "note",
        ) else None
        entries = BoardStore(store).read(
            run_id, kind=kind, limit=int(args.get("limit") or 50),
        )
        text = "\n".join(f"- [{e['kind']}] {e['text']}" for e in entries) or "(empty)"
        return (text[:12_000], {"status": "OK", "entries": entries})

    async def _board_search(args: dict[str, Any], ctx: Any) -> tuple[str, dict[str, Any]]:
        store = getattr(ctx, "memory_store", None)
        run_id = str(getattr(ctx, "run_id", "") or "")
        if store is None or not run_id:
            return ("UNAVAILABLE: no blackboard is bound.", {"status": "UNAVAILABLE"})
        entries = BoardStore(store).search(
            run_id, str(args.get("query") or ""), limit=int(args.get("limit") or 20),
        )
        text = "\n".join(f"- [{e['kind']}] {e['text']}" for e in entries) or "no matches"
        return (text[:12_000], {"status": "OK", "entries": entries})

    registry.register(ToolDefinition(
        name="spawn",
        description=(
            "Spawn one child agent (or up to 8 with `children`) as a Fabric job. "
            "Give a self-contained objective; returns the child's output, claims "
            "and handles. Use it for independent research or verification. A "
            "multi-child call also returns a deterministic synthesis (dedupe + "
            "conflicts). Children cannot exceed depth 2 or the token/time budget."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "objective": {"type": "string"},
                "agent": {"type": "string"},
                "budget": {"type": "object"},
                "background": {"type": "boolean"},
                "model": {"type": "object"},
                "children": {"type": "array", "items": {"type": "object"}},
            },
        },
        handler=_spawn,
        permission="read",
        risk="low",
        timeout_ms=MAX_SPAWN_TOOL_TIMEOUT_MS,
    ))
    registry.register(ToolDefinition(
        name="board_write",
        description="Write a bounded fact/artifact/decision/note to the shared spawn blackboard.",
        input_schema={
            "type": "object",
            "properties": {
                "text": {"type": "string"},
                "kind": {"type": "string"},
                "handles": {"type": "array"},
                "status": {"type": "string"},
                "author": {"type": "string"},
            },
            "required": ["text"],
        },
        handler=_board_write, permission="read", risk="none", timeout_ms=5_000,
    ))
    registry.register(ToolDefinition(
        name="board_read",
        description="Read the shared spawn blackboard for this root run.",
        input_schema={
            "type": "object",
            "properties": {"kind": {"type": "string"}, "limit": {"type": "integer"}},
        },
        handler=_board_read, permission="read", risk="none", timeout_ms=5_000,
    ))
    registry.register(ToolDefinition(
        name="board_search",
        description="Search the shared spawn blackboard.",
        input_schema={
            "type": "object",
            "properties": {"query": {"type": "string"}, "limit": {"type": "integer"}},
            "required": ["query"],
        },
        handler=_board_search, permission="read", risk="none", timeout_ms=5_000,
    ))


MAX_SPAWN_TOOL_TIMEOUT_MS = 900_000 + 30_000


__all__ = ["register_spawn_tools"]
