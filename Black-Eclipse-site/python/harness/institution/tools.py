"""The Institution handoff tool.

A downstream committee stage does not inherit an upstream agent's prose. The task
context names a completed prerequisite by its run id (`output: <runId>`); this
read-only tool is how the stage reads that memo. It reads the ONE run store — no
second transcript, no prompt-injected memory.
"""

from __future__ import annotations

from typing import Any

from ..tools import ToolContext, ToolDefinition, ToolRegistry

TOOL_NAMES: tuple[str, ...] = ("read_run_output",)

_MAX_OUTPUT_CHARS = 20_000
_SCHEMA = {
    "type": "object",
    "properties": {
        "runId": {
            "type": "string",
            "description": "The run id of a completed prerequisite (listed in the task context).",
        },
    },
    "required": ["runId"],
}


async def read_run_output(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    run_id = str(args.get("runId") or "").strip()
    if not run_id:
        return "Provide the prerequisite runId.", {
            "ok": False, "code": "INVALID_ARGUMENT", "message": "runId is required",
        }
    store = getattr(ctx, "memory_store", None)
    if store is None:
        return "The run store is unavailable in this run.", {
            "ok": False, "code": "RUNTIME_UNAVAILABLE",
        }
    try:
        run = store.get_run(run_id)
    except Exception as exc:  # noqa: BLE001 - a missing run is an honest refusal
        return f"Could not read run {run_id}: {exc}", {
            "ok": False, "code": "RUN_READ_FAILED", "runId": run_id,
        }
    if not run:
        return f"No run {run_id!r} exists.", {
            "ok": False, "code": "RUN_NOT_FOUND", "runId": run_id,
        }
    status = str(run.get("status") or "")
    output = str(run.get("output") or "")
    if not output.strip():
        return (
            f"Run {run_id} is {status or 'unknown'} and produced no output.",
            {"ok": False, "code": "RUN_OUTPUT_EMPTY", "runId": run_id, "status": status},
        )
    bounded = output[:_MAX_OUTPUT_CHARS]
    return (
        f"Run {run_id} ({status or 'unknown'}) output:\n\n{bounded}",
        {
            "ok": True,
            "runId": run_id,
            "status": status,
            "output": bounded,
            "truncated": len(output) > len(bounded),
        },
    )


_HANDLERS = {"read_run_output": read_run_output}


def register_institution_tools(registry: ToolRegistry) -> list[str]:
    """Register the handoff tool. Idempotent, like every other layer."""
    registered: list[str] = []
    for name in TOOL_NAMES:
        if registry.get(name) is not None:
            continue
        registry.register(ToolDefinition(
            name=name,
            description=(
                "Read a completed prerequisite run's final output by its run id. "
                "Use it to read the analyst brief, debate record, trade proposal or "
                "risk verdict handed to your committee stage."
            ),
            input_schema=_SCHEMA,
            handler=_HANDLERS[name],
            permission="read",
            risk="low",
            timeout_ms=10_000,
        ))
        registered.append(name)
    return registered


__all__ = ["TOOL_NAMES", "read_run_output", "register_institution_tools"]
