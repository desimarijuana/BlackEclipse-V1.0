"""Schema-on-demand for tools hidden by progressive disclosure.

Eclipse already defers tool *binding*: `tool_disclosure` keeps effectful and
interactive tools on the graph's execution path and advertises the read-only
long tail through a bounded catalogue, reachable with the EXISTING
`tool_search` (find by intent) and `tool_invoke` (execute by name) pair. That is
the deferred-exposure mechanism; this module does not add a second one.

What was missing is the third step a model needs: **see the schema before
calling**. `tool_invoke` executes directly, so a model that only knows a name
had to guess argument names. `load_tool_schema` returns the exact
`parameters`/`description` for tools the catalogue advertised but did not bind.

Safety rules, identical to the rest of the surface:

  * It can never widen authority: a name outside the run's allowlist is
    refused, and the tool only ever READS the registry.
  * It is read-only, `risk="none"`, and bounded (max tools per call, bounded
    JSON) so it cannot become a payload channel.
  * It stays bound when disclosure narrows (`tool_disclosure.CORE_TOOLS`), so it
    is reachable exactly when it is needed.
"""

from __future__ import annotations

import json
from typing import Any, Optional

#: How many schemas one call may return. Keeps a single result small.
MAX_TOOLS_PER_CALL = 5

#: Bound on the serialized parameters of one tool, in characters.
MAX_PARAM_CHARS = 8_000

NAME = "load_tool_schema"


def _refusal(reason: str, **detail: Any) -> str:
    return json.dumps({"error": reason, **detail})


def _schema_payload(tool: Any) -> dict[str, Any]:
    params = json.dumps(getattr(tool, "input_schema", {}) or {}, sort_keys=True)
    if len(params) > MAX_PARAM_CHARS:
        params = params[:MAX_PARAM_CHARS]
        truncated = True
    else:
        truncated = False
    return {
        "name": tool.name,
        "description": (getattr(tool, "description", "") or "")[:2_000],
        "parametersJson": params,
        "parametersTruncated": truncated,
        "permission": getattr(tool, "permission", None),
        "risk": getattr(tool, "risk", None),
    }


def build_tool() -> Any:
    """The `load_tool_schema` ToolDefinition (imported lazily: avoids a cycle)."""
    from .tools import ToolDefinition  # noqa: PLC0415

    async def handler(args: dict[str, Any], ctx: Any) -> str:
        names = args.get("names")
        if not isinstance(names, list) or not names:
            return _refusal("names must be a non-empty list of tool names")
        if len(names) > MAX_TOOLS_PER_CALL:
            return _refusal(
                f"at most {MAX_TOOLS_PER_CALL} tools per call",
                requested=len(names),
            )
        registry = getattr(ctx, "tool_registry", None)
        if registry is None:
            return _refusal("tool registry is unavailable in this run")
        allowed = getattr(ctx, "allowed", None)
        loaded: list[dict[str, Any]] = []
        refused: list[dict[str, str]] = []
        for raw in names:
            name = str(raw or "").strip()
            if not name:
                continue
            tool: Optional[Any] = registry.get(name)
            if tool is None:
                refused.append({"name": name, "reason": "unknown_tool"})
                continue
            if allowed is not None and name not in allowed:
                refused.append({"name": name, "reason": "outside_allowlist"})
                continue
            loaded.append(_schema_payload(tool))
        if not loaded and refused:
            return json.dumps({"loaded": [], "refused": refused})
        return json.dumps({"loaded": loaded, "refused": refused})

    return ToolDefinition(
        name=NAME,
        description=(
            "Return the full parameter schema for one or more tools listed in "
            "the tool catalogue but not bound as a callable schema. Use it "
            "before `tool_invoke` when you need exact argument names. Read-only; "
            f"up to {MAX_TOOLS_PER_CALL} names per call."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "names": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Exact tool names from the catalogue.",
                }
            },
            "required": ["names"],
            "additionalProperties": False,
        },
        handler=handler,
        permission="read",
        risk="none",
        version="1.0.0",
    )


def install_tool_schema_load(registry: Any) -> bool:
    """Register the tool once. Returns whether it was added by this call."""
    if registry.get(NAME) is not None:
        return False
    registry.register(build_tool())
    return True


__all__ = ["MAX_PARAM_CHARS", "MAX_TOOLS_PER_CALL", "NAME", "build_tool", "install_tool_schema_load"]
