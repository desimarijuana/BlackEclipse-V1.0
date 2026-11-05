"""Workflow authoring from chat — build a Graph Studio workflow from a sentence.

Graph Studio workflows live in JDDS (Prisma), which the Python runtime cannot
read or write. The front door owns that catalog, so this tool is a thin, bounded
bridge to `POST /api/workflows/generate`: the route resolves the model
credentials, runs the SAME validated chat-to-graph planner the gallery uses, and
saves the resulting IR. The tool creates; it never runs the workflow.

This is the chat half of authoring. It deliberately does not re-implement the
planner, the IR validator or the store — there is one of each, in their owners.
"""

from __future__ import annotations

import json
import os
from typing import Any

import httpx

from .tools import ToolContext, ToolDefinition, ToolRegistry

TOOL_NAME = "create_workflow"
# The route's own planner call is bounded to 110 s, below this ceiling, so a slow
# model returns an honest error here instead of a timeout after a write.
TIMEOUT_S = 115.0
MIN_OBJECTIVE_CHARS = 8


def _app_base() -> str:
    return (
        os.environ.get("HARNESS_CALLBACK_URL")
        or f"http://127.0.0.1:{os.environ.get('PORT', '3000')}"
    ).rstrip("/")


def _operator_headers() -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    token = (os.environ.get("CRON_SECRET") or "").strip()
    if token and token != "change-me-to-a-random-secret":
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _message_from(body: Any, status: int) -> str:
    if isinstance(body, dict):
        error = body.get("error")
        if isinstance(error, str) and error.strip():
            return error.strip()
        detail = body.get("detail")
        if isinstance(detail, str) and detail.strip():
            return detail.strip()
        errors = body.get("errors")
        if isinstance(errors, list):
            messages = [
                str(item.get("message") if isinstance(item, dict) else item)
                for item in errors
                if item
            ]
            if messages:
                return "; ".join(messages)
    return f"HTTP {status}"


async def create_workflow_handler(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    objective = str(args.get("objective") or "").strip()
    if len(objective) < MIN_OBJECTIVE_CHARS:
        return (
            "WORKFLOW NOT CREATED: describe the workflow in at least a short "
            "sentence (what it should fetch, compute and output).",
            {"created": False, "error": "objective_required"},
        )
    if len(objective) > 4_000:
        return (
            "WORKFLOW NOT CREATED: that description is too long; keep it under 4,000 characters.",
            {"created": False, "error": "objective_too_long"},
        )
    payload: dict[str, Any] = {"objective": objective}
    name = str(args.get("name") or "").strip()
    if name:
        payload["name"] = name[:120]

    url = f"{_app_base()}/api/workflows/generate"
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_S) as client:
            res = await client.post(url, json=payload, headers=_operator_headers())
    except Exception as exc:  # noqa: BLE001 - an unreachable app is an honest failure
        return (
            "WORKFLOW NOT CREATED: the app did not answer the workflow builder "
            f"({type(exc).__name__}). Is Eclipse running?",
            {"created": False, "error": "app_unavailable", "base": _app_base()},
        )

    try:
        body = res.json() if res.content else {}
    except (ValueError, json.JSONDecodeError):
        body = {}
    if res.status_code >= 400:
        message = _message_from(body, res.status_code)
        return (
            f"WORKFLOW NOT CREATED: {message}",
            {"created": False, "status": res.status_code, "error": message},
        )

    workflow = (body.get("workflow") if isinstance(body, dict) else None) or {}
    plan = (body.get("plan") if isinstance(body, dict) else None) or {}
    workflow_id = str(workflow.get("id") or "")
    name = str(workflow.get("name") or "Untitled workflow")
    if not workflow_id:
        return (
            "WORKFLOW NOT CREATED: the app did not return a saved workflow id.",
            {"created": False, "error": "missing_workflow_id"},
        )

    node_count = plan.get("nodeCount")
    edge_count = plan.get("edgeCount")
    mode = plan.get("executionMode")
    warnings = plan.get("warnings") if isinstance(plan.get("warnings"), list) else []
    counts = f"{node_count} node(s), {edge_count} edge(s)"
    if mode:
        counts += f", {mode} mode"
    text = (
        f'Created and saved the workflow "{name}" ({workflow_id}): {counts}. '
        "It is in Graph Studio → Overview; open it there to inspect, edit or run it."
    )
    if warnings:
        text += " The planner flagged: " + "; ".join(str(item) for item in warnings[:5])
    return (
        text,
        {
            "created": True,
            "workflowId": workflow_id,
            "name": name,
            "nodeCount": node_count,
            "edgeCount": edge_count,
            "executionMode": mode,
            "warnings": warnings,
            "openPath": "/?tab=overview",
        },
    )


def make_graph_authorizer(inner: Any = None):
    """Admit the local catalog write; everything else falls through.

    Creating a workflow is a reversible write to the user's own catalog (the
    operator asked for it, and a bad one is deleted, not executed). Admission is
    unconditional here, mirroring `make_bot_authorizer`: no external effect can
    be triggered by authoring a graph.
    """

    async def authorize(tool: Any, args: dict[str, Any], ctx: Any = None) -> bool:
        if str(getattr(tool, "name", "")) == TOOL_NAME:
            return True
        if inner is not None:
            return bool(await inner(tool, args, ctx))
        return False

    return authorize


def register_graph_tools(registry: ToolRegistry) -> list[str]:
    if registry.get(TOOL_NAME) is not None:
        return []
    registry.register(ToolDefinition(
        name=TOOL_NAME,
        description=(
            "Create and SAVE a new Graph Studio workflow from a plain-language idea. "
            "Use this when the user asks you to build/make/create a workflow, "
            "automation graph or pipeline (e.g. 'build me a workflow that pulls AAPL "
            "daily bars, computes an SMA z-score and reports the result'). The graph "
            "is planned against the real node registry, validated and compiled before "
            "it is saved; an invalid plan fails honestly. This only creates the "
            "workflow — it does not run it. Ask for a clearer objective if the idea is "
            "too vague."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "objective": {
                    "type": "string",
                    "description": (
                        "What the workflow should do, in one or two sentences: the data "
                        "to fetch, the computation, any branching and the output."
                    ),
                },
                "name": {
                    "type": "string",
                    "description": "Optional short name for the workflow.",
                },
            },
            "required": ["objective"],
        },
        handler=create_workflow_handler,
        permission="write",
        risk="low",
        timeout_ms=120_000,
    ))
    return [TOOL_NAME]


__all__ = [
    "TOOL_NAME",
    "create_workflow_handler",
    "make_graph_authorizer",
    "register_graph_tools",
]
