"""The single `code.*` event seam (extracted from `code/tools.py`).

A code tool emits through the run's emitter so the event reaches the live SSE
stream and the persisted trace; when no emitter is attached it degrades to
`ctx.log`. Payloads are content-free (counts, paths, names) — never file contents
and never a secret value. An event must NEVER break a tool call.

The ONE deliberate exception is a file change: `diff_event_payload` carries a
BOUNDED, REDACTED unified diff so the UI can show what changed ("show me the
change" is the point of a code surface). The diff is the user's own content,
secret-shaped spans are scrubbed with the same pattern set the file reader uses,
and the text is hard-capped with an honest truncation marker.
"""

from __future__ import annotations

from typing import Any, Optional

from ..session_index import redact_span
from ..tools import ToolContext

# The ONE marker for a redacted span in code surfaces — identical to the marker
# the file reader uses. Re-exported through `code/tools.py` for existing callers.
REDACT_MARKER = "«redacted»"

# A diff preview is capped so one event can never carry a whole file.
EVENT_DIFF_MAX_CHARS = 12_000
_TRUNCATED_NOTE = "\n[DIFF TRUNCATED: the change is larger than the preview]\n"


async def emit_code_event(ctx: ToolContext, event_type: str, data: dict[str, Any]) -> None:
    """Emit a `code.*` event on the run's emitter, or degrade to `ctx.log`."""
    emitter = getattr(ctx, "emitter", None)
    if emitter is not None:
        try:
            await emitter.emit(event_type, data)
            return
        except Exception:  # noqa: BLE001 - an event must never break a tool call
            pass
    try:
        if ctx.log is not None:
            ctx.log(event_type, data)
    except Exception:  # noqa: BLE001
        pass


async def emit_patch_applied(ctx: ToolContext, workspace_id: str, item: dict[str, Any]) -> None:
    """Emit one `code.patch.applied` event for an applied patch op.

    `item` is the op's audit record from `patch.apply`. The event carries the
    bounded, redacted diff preview so the UI can show WHAT changed; `from` is
    included for a move. Assembly lives here so `code/tools.py` stays thin.
    """
    preview = diff_event_payload(item) or {}
    if item.get("movedFrom"):
        preview["from"] = item["movedFrom"]
    await emit_code_event(ctx, "code.patch.applied", {
        "workspaceId": workspace_id, "op": item["op"], "path": item["path"],
        "bytes": item["bytesWritten"], "hashBefore": item["contentHashBefore"],
        "hashAfter": item["contentHashAfter"], **preview,
    })


def diff_event_payload(record: Any) -> Optional[dict[str, Any]]:
    """A bounded, redacted unified-diff payload for a change event, or None.

    `record` is any dict carrying `diff` / `additions` / `deletions` /
    `truncated` (a patch `AppliedOp`, an fs `preview_for` result, …). Returns
    `{diff, additions?, deletions?, diffTruncated}` with the diff secret-scrubbed
    and capped at `EVENT_DIFF_MAX_CHARS`. Never raises — a preview must never
    break a tool call.
    """
    try:
        if not isinstance(record, dict):
            return None
        diff = record.get("diff")
        if not isinstance(diff, str) or not diff.strip():
            return None
        text = redact_span(diff, REDACT_MARKER)
        truncated = record.get("diffTruncated") is True or record.get("truncated") is True
        if len(text) > EVENT_DIFF_MAX_CHARS:
            text = text[:EVENT_DIFF_MAX_CHARS] + _TRUNCATED_NOTE
            truncated = True
        out: dict[str, Any] = {"diff": text, "diffTruncated": truncated}
        additions = record.get("additions")
        deletions = record.get("deletions")
        if isinstance(additions, int):
            out["additions"] = additions
        if isinstance(deletions, int):
            out["deletions"] = deletions
        return out
    except Exception:  # noqa: BLE001 - a preview must never break a tool call
        return None


__all__ = [
    "EVENT_DIFF_MAX_CHARS",
    "REDACT_MARKER",
    "diff_event_payload",
    "emit_code_event",
    "emit_patch_applied",
]
