"""The agent tools for projects.

Five tools, all read-only in effect (they create and attach *records*, never
touch a market, a strategy or an order):

  * `project_create` — a named scope;
  * `project_list`   — what exists;
  * `project_show`   — one project and its members;
  * `project_attach` — put a strategy, backtest, dataset, artifact, chat or
    note into a project;
  * `project_detach` — take it out again.

The tools never fail silently: a project that does not exist is a named
refusal, not an empty list.
"""

from __future__ import annotations

from typing import Any, Optional

from ..tools import ToolContext, ToolDefinition


def _store(ctx: ToolContext) -> Any:
    store = getattr(ctx, "project_store", None)
    if store is None:
        raise RuntimeError(
            "the project store is not configured in this runtime; project tools "
            "are unavailable")
    return store


def _err(code: str, message: str) -> tuple[str, Any]:
    return (f"ERROR - {code}: {message}",
            {"status": "ERROR", "error": {"code": code, "message": message}})


async def project_create(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    """Create a project."""
    try:
        store = _store(ctx)
        project = store.create(
            str(args.get("name") or ""),
            description=str(args.get("description") or ""),
            symbols=list(args.get("symbols") or []),
            tags=list(args.get("tags") or []),
        )
        return (f"Created project `{project.id}` — {project.name}.",
                {"status": "OK", "project": project.to_dict()})
    except Exception as exc:  # noqa: BLE001
        return _err("PROJECT_CREATE_FAILED", str(exc))


async def project_list(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    """List the projects."""
    try:
        store = _store(ctx)
        projects = store.list(status=args.get("status"),
                              limit=int(args.get("limit") or 50))
        if not projects:
            return ("No projects yet.",
                    {"status": "OK", "projects": [], "count": 0})
        lines = [f"- `{p.id}` {p.name} "
                 f"({len(store.members(p.id))} members, last active {p.last_activity_at})"
                 for p in projects]
        return ("\n".join(lines),
                {"status": "OK", "count": len(projects),
                 "projects": [p.to_dict() for p in projects]})
    except Exception as exc:  # noqa: BLE001
        return _err("PROJECT_LIST_FAILED", str(exc))


async def project_show(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    """Show one project and its members."""
    project_id = str(args.get("projectId") or "")
    if not project_id:
        return _err("PROJECT_ID_REQUIRED", "provide `projectId`")
    try:
        store = _store(ctx)
        detail = store.detail(project_id)
        if detail is None:
            return _err("PROJECT_NOT_FOUND", f"no project {project_id!r}")
        brief = store.brief(project_id)
        return (brief, {"status": "OK", **detail})
    except Exception as exc:  # noqa: BLE001
        return _err("PROJECT_SHOW_FAILED", str(exc))


async def project_attach(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    """Attach a member to a project."""
    project_id = str(args.get("projectId") or "")
    kind = str(args.get("kind") or "")
    ref = str(args.get("ref") or "")
    if not project_id or not kind or not ref:
        return _err("PROJECT_ATTACH_INPUT_REQUIRED",
                     "provide `projectId`, `kind` and `ref`")
    try:
        store = _store(ctx)
        member = store.attach(project_id, kind, ref,
                              label=str(args.get("label") or ""),
                              meta=dict(args.get("meta") or {}))
        return (f"Attached {member.kind} `{member.ref}` to `{project_id}`.",
                {"status": "OK", "member": member.to_dict()})
    except Exception as exc:  # noqa: BLE001
        return _err("PROJECT_ATTACH_FAILED", str(exc))


async def project_detach(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    """Detach a member from a project."""
    project_id = str(args.get("projectId") or "")
    member_id = str(args.get("memberId") or "")
    if not project_id or not member_id:
        return _err("PROJECT_DETACH_INPUT_REQUIRED",
                     "provide `projectId` and `memberId`")
    try:
        store = _store(ctx)
        if not store.detach(project_id, member_id):
            return _err("PROJECT_MEMBER_NOT_FOUND",
                        f"no member {member_id!r} in project {project_id!r}")
        return (f"Detached member {member_id} from `{project_id}`.",
                {"status": "OK", "detached": member_id})
    except Exception as exc:  # noqa: BLE001
        return _err("PROJECT_DETACH_FAILED", str(exc))


PROJECT_TOOLS: tuple[str, ...] = (
    "project_create",
    "project_list",
    "project_show",
    "project_attach",
    "project_detach",
)


def register_project_tools(registry: Any) -> list[str]:
    """Register the project tools on the one tool registry."""
    registry.register(ToolDefinition(
        name="project_create",
        description="Create a project: a named scope that holds the strategies, "
                    "backtests, datasets, artifacts and notes that belong to one "
                    "piece of work. A project carries the instruments it covers.",
        input_schema={"type": "object", "properties": {
            "name": {"type": "string"},
            "description": {"type": "string"},
            "symbols": {"type": "array", "items": {"type": "string"}},
            "tags": {"type": "array", "items": {"type": "string"}}},
            "required": ["name"]},
        handler=project_create, permission="read", risk="low", timeout_ms=20_000))
    registry.register(ToolDefinition(
        name="project_list",
        description="List the projects, most recently active first, with their "
                    "member counts.",
        input_schema={"type": "object", "properties": {
            "status": {"type": "string"}, "limit": {"type": "integer"}},
            "required": []},
        handler=project_list, permission="read", risk="low", timeout_ms=20_000))
    registry.register(ToolDefinition(
        name="project_show",
        description="Show one project: its description, the instruments it covers "
                    "and every member it holds.",
        input_schema={"type": "object", "properties": {
            "projectId": {"type": "string"}}, "required": ["projectId"]},
        handler=project_show, permission="read", risk="low", timeout_ms=20_000))
    registry.register(ToolDefinition(
        name="project_attach",
        description="Attach a member to a project. The member kinds are strategy, "
                    "experiment, dataset, artifact, chat and note; the reference "
                    "is owned by its own subsystem and the project only remembers "
                    "where to look.",
        input_schema={"type": "object", "properties": {
            "projectId": {"type": "string"},
            "kind": {"type": "string",
                     "enum": ["strategy", "experiment", "dataset", "artifact",
                              "chat", "note"]},
            "ref": {"type": "string"},
            "label": {"type": "string"},
            "meta": {"type": "object"}},
            "required": ["projectId", "kind", "ref"]},
        handler=project_attach, permission="read", risk="low", timeout_ms=20_000))
    registry.register(ToolDefinition(
        name="project_detach",
        description="Detach a member from a project.",
        input_schema={"type": "object", "properties": {
            "projectId": {"type": "string"},
            "memberId": {"type": "string"}},
            "required": ["projectId", "memberId"]},
        handler=project_detach, permission="read", risk="low", timeout_ms=20_000))
    return list(PROJECT_TOOLS)


__all__ = ["PROJECT_TOOLS", "register_project_tools"]
