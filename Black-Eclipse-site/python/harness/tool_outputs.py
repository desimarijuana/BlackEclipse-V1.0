"""Durable tool-output handles (Round 5 / C3).

A tool result over `MAX_TOOL_RESULT_CHARS` was cut with a marker and the rest was
lost. This module stores the FULL text once, returns a handle, and exposes a
`read_tool_output` tool so the model can page through it instead of guessing or
re-fetching.

Isolation: a handle is readable only by the run that produced it. The text is
bounded at 2M chars (a pathological result is still labelled); the read is
paged (default 12k) so one call cannot re-flood the context.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any, Optional

from .migrations import Migration, MigrationRunner
from .persistence import now_iso

MAX_STORED_TOOL_OUTPUT_CHARS = 2_000_000
DEFAULT_READ_CHARS = 12_000
MAX_READ_CHARS = 24_000

TOOL_OUTPUT_MIGRATIONS: tuple[Migration, ...] = (
    Migration(
        id="2026-11-11-003-tool-output-handles",
        description="ToolOutput: the full text behind a truncated tool result",
        statements=(
            """
            CREATE TABLE IF NOT EXISTS ToolOutput (
              id        TEXT PRIMARY KEY,
              runId     TEXT NOT NULL,
              toolName  TEXT NOT NULL,
              digest    TEXT NOT NULL,
              chars     INTEGER NOT NULL,
              storedChars INTEGER NOT NULL,
              truncated INTEGER NOT NULL DEFAULT 0,
              text      TEXT NOT NULL,
              createdAt TEXT NOT NULL
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_tool_output_run ON ToolOutput(runId, createdAt)",
        ),
    ),
)


class ToolOutputStore:
    """Store + page the full text of a truncated tool result."""

    def __init__(self, db: Any, namespace: str = "agent-memory") -> None:
        self._db = db
        MigrationRunner(db, namespace).apply(TOOL_OUTPUT_MIGRATIONS)

    def save(self, run_id: str, tool_name: str, text: str) -> Optional[dict[str, Any]]:
        if not run_id or not text:
            return None
        stored = text[:MAX_STORED_TOOL_OUTPUT_CHARS]
        output_id = f"tout_{uuid.uuid4().hex[:20]}"
        digest = hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()
        try:
            self._db.execute(
                "INSERT INTO ToolOutput "
                "(id, runId, toolName, digest, chars, storedChars, truncated, text, createdAt) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    output_id, run_id, tool_name, digest, len(text), len(stored),
                    1 if len(stored) < len(text) else 0, stored, now_iso(),
                ),
            )
        except Exception:  # noqa: BLE001 - offload must never break the tool call
            return None
        return {
            "id": output_id,
            "digest": digest,
            "chars": len(text),
            "storedChars": len(stored),
            "truncated": len(stored) < len(text),
        }

    def get(self, run_id: str, output_id: str) -> Optional[dict[str, Any]]:
        row = self._db.execute(
            "SELECT * FROM ToolOutput WHERE id=? AND runId=?", (output_id, run_id),
        ).fetchone()
        if row is None:
            return None
        return {
            "id": row["id"],
            "runId": row["runId"],
            "toolName": row["toolName"],
            "digest": row["digest"],
            "chars": row["chars"],
            "storedChars": row["storedChars"],
            "truncated": bool(row["truncated"]),
            "createdAt": row["createdAt"],
        }

    def read(
        self, run_id: str, output_id: str, *, offset: int = 0, limit: int = DEFAULT_READ_CHARS,
    ) -> Optional[dict[str, Any]]:
        row = self._db.execute(
            "SELECT * FROM ToolOutput WHERE id=? AND runId=?", (output_id, run_id),
        ).fetchone()
        if row is None:
            return None
        text = row["text"]
        start = max(0, int(offset))
        size = max(1, min(int(limit), MAX_READ_CHARS))
        chunk = text[start:start + size]
        end = start + len(chunk)
        return {
            "id": row["id"],
            "toolName": row["toolName"],
            "chars": row["chars"],
            "storedChars": row["storedChars"],
            "truncated": bool(row["truncated"]),
            "offset": start,
            "end": end,
            "nextOffset": end if end < len(text) else None,
            "text": chunk,
        }


def _store_for(ctx: Any) -> Optional[ToolOutputStore]:
    store = getattr(ctx, "memory_store", None)
    if store is None:
        return None
    cached = getattr(store, "_tool_output_store", None)
    if cached is None:
        db = getattr(store, "_db", None)
        if db is None:
            return None
        cached = ToolOutputStore(db)
        try:
            setattr(store, "_tool_output_store", cached)
        except Exception:  # noqa: BLE001 - a read-only test stub
            pass
    return cached


def register_tool_output_tools(registry: Any) -> None:
    """Register the `read_tool_output` pager on the ONE registry."""
    from .tools import ToolDefinition  # noqa: PLC0415 - avoid a module cycle

    async def _read(args: dict[str, Any], ctx: Any) -> tuple[str, dict[str, Any]]:
        store = _store_for(ctx)
        output_id = str(args.get("id") or "").strip()
        if store is None or not output_id:
            return (
                "UNAVAILABLE: no tool-output store is bound to this run.",
                {"status": "UNAVAILABLE", "reason": "no tool-output store"},
            )
        page = store.read(
            str(getattr(ctx, "run_id", "") or ""),
            output_id,
            offset=int(args.get("offset") or 0),
            limit=int(args.get("limit") or DEFAULT_READ_CHARS),
        )
        if page is None:
            # A handle from another run is indistinguishable from a missing one.
            return (
                "NOT FOUND: no tool output with that id belongs to this run.",
                {"status": "NOT_FOUND", "id": output_id},
            )
        header = (
            f"[tool output {page['id']} | {page['toolName']} | "
            f"chars {page['offset']}-{page['end']} of {page['storedChars']}]"
        )
        suffix = (
            f"\n[nextOffset: {page['nextOffset']}]" if page["nextOffset"] is not None else ""
        )
        return (
            f"{header}\n{page['text']}{suffix}",
            {
                "status": "OK",
                "id": page["id"],
                "offset": page["offset"],
                "end": page["end"],
                "nextOffset": page["nextOffset"],
                "chars": page["chars"],
                "truncated": page["truncated"],
            },
        )

    registry.register(ToolDefinition(
        name="read_tool_output",
        description=(
            "Read the full text behind a truncated tool result. Tool results over "
            "the display bound include a handle id and a next offset; call this with "
            "that id (and the offset) to continue reading. Scoped to this run."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "id": {"type": "string", "description": "The handle id from the tool result."},
                "offset": {"type": "integer", "description": "Character offset to read from."},
                "limit": {"type": "integer", "description": "Max characters (default 12000)."},
            },
            "required": ["id"],
        },
        handler=_read,
        permission="read",
        risk="none",
        timeout_ms=5_000,
    ))


__all__ = [
    "DEFAULT_READ_CHARS",
    "MAX_READ_CHARS",
    "MAX_STORED_TOOL_OUTPUT_CHARS",
    "TOOL_OUTPUT_MIGRATIONS",
    "ToolOutputStore",
    "register_tool_output_tools",
]
