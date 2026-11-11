"""Tool discovery + a safe dispatcher (Round 5 / C3).

Eclipse binds hundreds of tools into every run. The fix is not "give the model
fewer capabilities"; it is "make the capability discoverable, and bind less".

  * `tool_search` returns the matching tools with their schemas. It is read-only.
  * `tool_invoke` runs a discovered READ-ONLY tool by name. Effectful tools are
    refused here on purpose: the graph's tools node owns budget, duplicate
    suppression, idempotency, authorisation and recovery for those, and a second
    execution path around that seam would be unsafe.
  * `lazy_tool_surface` is the opt-in binding policy (`HARNESS_LAZY_TOOLS=1`):
    every effectful tool stays bound; the read-only long tail is reachable via
    search/invoke. Default OFF until eval parity, as the plan requires.
"""

from __future__ import annotations

import json
import uuid
from typing import Any, Optional

# Always bound when lazy mode is on: the discovery pair, the output pager, the
# response-contract read-back and the clarify gate.
LAZY_CORE_TOOLS = frozenset({
    "tool_search",
    "tool_invoke",
    "read_tool_output",
    "response_block_schema",
    "response_style_guide",
    "response_validate",
    "clarify",
})

#: A discovery response is bounded so it cannot become the new context flood.
MAX_SEARCH_RESULTS = 12
MAX_SEARCH_SCHEMA_CHARS = 18_000


def lazy_tools_enabled() -> bool:
    import os

    return (os.environ.get("HARNESS_LAZY_TOOLS") or "").strip().lower() in (
        "1", "true", "yes", "on",
    )


def lazy_tool_surface(
    allowed: Optional[set[str]], registry: Any,
) -> Optional[set[str]]:
    """Narrow a run's surface to effectful tools + the discovery core.

    Effectful tools are NEVER hidden: they must stay on the graph's execution
    path. Read-only tools outside the core become discoverable through
    `tool_search` and callable through `tool_invoke`. Returns `allowed` unchanged
    when the flag is off or the surface is unbounded.
    """
    if not lazy_tools_enabled() or allowed is None:
        return allowed
    kept: set[str] = set()
    for name in allowed:
        tool = registry.get(name) if hasattr(registry, "get") else None
        if tool is None or getattr(tool, "permission", "read") != "read":
            kept.add(name)
    return kept | (LAZY_CORE_TOOLS & set(allowed))


def _tool_row(tool: Any, *, include_schema: bool) -> dict[str, Any]:
    row = {
        "name": getattr(tool, "name", ""),
        "description": str(getattr(tool, "description", ""))[:300],
        "permission": getattr(tool, "permission", "read"),
    }
    if include_schema:
        row["parameters"] = getattr(tool, "input_schema", {})
    return row


def _score(query: str, tool: Any) -> int:
    q = query.lower().strip()
    name = str(getattr(tool, "name", "")).lower()
    description = str(getattr(tool, "description", "")).lower()
    if not q:
        return 0
    if q == name:
        return 100
    if name.startswith(q):
        return 80
    if q in name:
        return 60
    if q in description:
        return 30
    terms = [term for term in q.split() if len(term) >= 3]
    return sum(10 for term in terms if term in name or term in description)


def register_tool_surface_tools(registry: Any) -> None:
    from .tools import ToolDefinition  # noqa: PLC0415 - avoid a module cycle

    async def _search(args: dict[str, Any], ctx: Any) -> tuple[str, dict[str, Any]]:
        target = getattr(ctx, "tool_registry", None) or registry
        query = str(args.get("query") or "").strip()
        limit = max(1, min(int(args.get("limit") or 8), MAX_SEARCH_RESULTS))
        if not query:
            return (
                "Give a query: a tool name, a task word (e.g. 'options'), or a domain.",
                {"status": "INVALID_INPUT"},
            )

        tools = []
        for name in getattr(target, "names", lambda: [])():
            tool = target.get(name)
            if tool is None:
                continue
            score = _score(query, tool)
            if score > 0:
                tools.append((score, tool))
        tools.sort(key=lambda item: (-item[0], getattr(item[1], "name", "")))
        selected = [tool for _score, tool in tools[:limit]]

        include_schema = True
        payload = {"tools": [_tool_row(tool, include_schema=True) for tool in selected]}
        if len(json.dumps(payload, default=str)) > MAX_SEARCH_SCHEMA_CHARS:
            include_schema = False
            payload = {
                "tools": [_tool_row(tool, include_schema=False) for tool in selected],
                "schemasOmitted": True,
            }
        payload["matchCount"] = len(tools)
        payload["returned"] = len(selected)
        if not selected:
            payload["hint"] = "No match. Try a broader domain word, or list the catalog."
        return json.dumps(payload, default=str), {"status": "OK", **payload}

    async def _invoke(args: dict[str, Any], ctx: Any) -> tuple[str, dict[str, Any]]:
        target = getattr(ctx, "tool_registry", None) or registry
        name = str(args.get("name") or "").strip()
        raw_args = args.get("arguments")
        if isinstance(raw_args, str):
            try:
                raw_args = json.loads(raw_args) if raw_args.strip() else {}
            except ValueError:
                return (
                    "INVALID_INPUT: `arguments` must be a JSON object.",
                    {"status": "INVALID_INPUT"},
                )
        call_args = dict(raw_args) if isinstance(raw_args, dict) else {}

        if name in ("tool_invoke",):
            return (
                "REFUSED: tool_invoke cannot call itself.",
                {"status": "REFUSED", "reason": "recursive dispatch"},
            )
        tool = target.get(name) if hasattr(target, "get") else None
        if tool is None:
            return (
                f"TOOL_NOT_FOUND: no tool named {name!r}. Call tool_search first.",
                {"status": "NOT_FOUND", "name": name},
            )
        if getattr(tool, "permission", "read") != "read":
            return (
                f"REFUSED: {name!r} is effectful ({getattr(tool, 'permission', '?')}). "
                "Call it directly so the run's budget, approval and idempotency "
                "seam apply.",
                {"status": "REFUSED", "name": name, "reason": "effectful tool"},
            )
        result = await target.execute(
            name, f"invoke_{uuid.uuid4().hex[:10]}", call_args, ctx,
        )
        if not result.ok:
            error = getattr(result, "error", None)
            code = getattr(error, "code", "TOOL_ERROR")
            return f"TOOL_ERROR ({code}): {result.text}", {
                "status": "ERROR", "name": name, "errorClass": str(code),
            }
        return result.text, {
            "status": "OK",
            "name": name,
            "truncated": bool(getattr(result, "truncated", False)),
            "outputId": getattr(result, "output_id", None),
        }

    registry.register(ToolDefinition(
        name="tool_search",
        description=(
            "Find a tool by name, task word or domain and get its exact parameters. "
            "Use this before guessing a tool name. Returns up to 12 matches."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Tool name, task word or domain."},
                "limit": {"type": "integer", "description": "Max results (default 8)."},
            },
            "required": ["query"],
        },
        handler=_search,
        permission="read",
        risk="none",
        timeout_ms=5_000,
    ))
    registry.register(ToolDefinition(
        name="tool_invoke",
        description=(
            "Run a READ-ONLY tool discovered with tool_search, by name and exact "
            "arguments. Effectful tools are refused here; call those directly."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "arguments": {"type": "object", "description": "The tool's exact arguments."},
            },
            "required": ["name"],
        },
        handler=_invoke,
        permission="read",
        risk="low",
        timeout_ms=120_000,
    ))


__all__ = [
    "LAZY_CORE_TOOLS",
    "MAX_SEARCH_RESULTS",
    "lazy_tool_surface",
    "lazy_tools_enabled",
    "register_tool_surface_tools",
]
