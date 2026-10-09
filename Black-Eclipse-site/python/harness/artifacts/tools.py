"""Agent-facing artifact tools — registered on the ONE shared registry.

These let an agent register a produced file, discover artifacts from its own
task/run, inspect metadata, add a version, and create a collection. They resolve
the process-wide `ArtifactService` from the run's `ToolContext`; when it is
absent they report `ARTIFACT_UNAVAILABLE` rather than inventing a result.

Registration copies a file the agent ALREADY produced through another tool into
the artifact store. It never grants the agent arbitrary filesystem read: the
service confines the source to an authorized workspace root.
"""

from __future__ import annotations

from typing import Any, Optional

from ..tools import ToolContext, ToolDefinition, ToolRegistry
from .model import (
    AddVersionInput,
    ArtifactCategory,
    CollectionInput,
    ListArtifactsQuery,
    RegisterArtifactInput,
    UpdateArtifactInput,
)
from .service import ArtifactError, ArtifactService


def _ok(text: str, data: Optional[dict[str, Any]] = None) -> tuple[str, Any]:
    return text, data or {}


def _err(exc: Exception) -> tuple[str, Any]:
    if isinstance(exc, ArtifactError):
        return f"{exc.code}: {exc.message}", {"error": exc.code}
    return f"ARTIFACT_ERROR: {exc}", {"error": "ARTIFACT_ERROR"}


def _service(ctx: ToolContext) -> ArtifactService:
    service = getattr(ctx, "artifact_service", None)
    if service is None:
        # The boot singleton makes the tools usable even when the run context
        # was built before the artifact layer was attached.
        from .bootstrap import get_artifact_service  # noqa: PLC0415

        service = get_artifact_service()
    if service is None:
        raise ArtifactError("ARTIFACT_UNAVAILABLE", "the artifact service is not available")
    return service


def _owner(ctx: ToolContext) -> str:
    return str(getattr(ctx, "workspace_id", None) or "local")


async def _register(args: dict[str, Any], ctx: ToolContext) -> Any:
    try:
        service = _service(ctx)
        category = args.get("category")
        input_model = RegisterArtifactInput(
            source_path=args.get("path") or args.get("sourcePath"),
            content_base64=args.get("contentBase64"),
            name=str(args.get("name") or ""),
            description=str(args.get("description") or ""),
            category=ArtifactCategory(category) if category else None,
            mime_type=args.get("mimeType"),
            tags=list(args.get("tags") or []),
            source_type="agent",
            source_tool=str(args.get("sourceTool") or "artifact_register"),
            project_id=args.get("projectId"),
            conversation_id=args.get("conversationId"),
            agent_id=str(getattr(ctx, "agent_id", None) or "eclipse-agent"),
            task_id=args.get("taskId"),
            run_id=args.get("runId") or getattr(ctx, "run_id", None),
            idempotency_key=args.get("idempotencyKey"),
        )
        artifact = service.register(input_model, owner_id=_owner(ctx))
    except Exception as exc:  # noqa: BLE001
        return _err(exc)
    return _ok(
        f"Registered artifact {artifact.name!r} ({artifact.id}); "
        f"{artifact.category.value}, {artifact.size_bytes or 0} bytes.",
        {"artifact": artifact.model_dump(by_alias=True)},
    )


async def _list(args: dict[str, Any], ctx: ToolContext) -> Any:
    try:
        service = _service(ctx)
        category = args.get("category")
        query = ListArtifactsQuery(
            q=args.get("q"),
            category=ArtifactCategory(category) if category else None,
            tags=list(args.get("tags") or []),
            task_id=args.get("taskId"),
            run_id=args.get("runId") or (getattr(ctx, "run_id", None) if args.get("mine") else None),
            project_id=args.get("projectId"),
            sort=str(args.get("sort") or "newest"),
            limit=int(args.get("limit") or 25),
            offset=int(args.get("offset") or 0),
        )
        page = service.list(query, owner_id=_owner(ctx))
    except Exception as exc:  # noqa: BLE001
        return _err(exc)
    lines = [f"{a.name} [{a.category.value}] {a.id}" for a in page.artifacts]
    text = f"{page.total} artifact(s)." + (("\n" + "\n".join(lines)) if lines else "")
    return _ok(text, {"artifacts": [a.model_dump(by_alias=True) for a in page.artifacts], "total": page.total})


async def _get(args: dict[str, Any], ctx: ToolContext) -> Any:
    try:
        artifact = _service(ctx).get(str(args.get("artifactId") or ""), owner_id=_owner(ctx))
    except Exception as exc:  # noqa: BLE001
        return _err(exc)
    return _ok(
        f"{artifact.name}: {artifact.category.value}, {artifact.status.value}, "
        f"preview={artifact.preview_status.value}.",
        {"artifact": artifact.model_dump(by_alias=True)},
    )


async def _add_version(args: dict[str, Any], ctx: ToolContext) -> Any:
    try:
        artifact = _service(ctx).add_version(
            str(args.get("artifactId") or ""),
            AddVersionInput(
                source_path=args.get("path") or args.get("sourcePath"),
                content_base64=args.get("contentBase64"),
                change_note=args.get("changeNote"),
                agent_id=str(getattr(ctx, "agent_id", None) or "eclipse-agent"),
                run_id=getattr(ctx, "run_id", None),
                idempotency_key=args.get("idempotencyKey"),
            ),
            owner_id=_owner(ctx),
        )
    except Exception as exc:  # noqa: BLE001
        return _err(exc)
    return _ok(f"Added version {artifact.version_number} of {artifact.name!r}.", {"artifact": artifact.model_dump(by_alias=True)})


async def _tag(args: dict[str, Any], ctx: ToolContext) -> Any:
    try:
        artifact = _service(ctx).get(str(args.get("artifactId") or ""), owner_id=_owner(ctx))
        merged = list({*artifact.tags, *[str(t) for t in (args.get("tags") or [])]})
        updated = _service(ctx).update(
            artifact.id, UpdateArtifactInput(tags=merged), owner_id=_owner(ctx)
        )
    except Exception as exc:  # noqa: BLE001
        return _err(exc)
    return _ok(f"Tagged {updated.name!r}: {', '.join(updated.tags) or 'none'}.", {"artifact": updated.model_dump(by_alias=True)})


async def _create_collection(args: dict[str, Any], ctx: ToolContext) -> Any:
    try:
        collection = _service(ctx).create_collection(
            CollectionInput(
                name=str(args.get("name") or ""),
                description=str(args.get("description") or ""),
                parent_id=args.get("parentId"),
            ),
            owner_id=_owner(ctx),
        )
    except Exception as exc:  # noqa: BLE001
        return _err(exc)
    return _ok(f"Created collection {collection.name!r} ({collection.id}).", {"collection": collection.model_dump(by_alias=True)})


_DEFS: list[tuple[str, str, dict[str, Any]]] = [
    (
        "artifact_register",
        "Register a file you produced into the Eclipse Artifact Center so the user "
        "can find, preview and download it later. Provide a path inside the current "
        "workspace (or base64 content) plus a name.",
        {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Workspace-relative or authorized absolute path."},
                "contentBase64": {"type": "string", "description": "Inline content for small generated files."},
                "name": {"type": "string"},
                "description": {"type": "string"},
                "category": {"type": "string"},
                "mimeType": {"type": "string"},
                "tags": {"type": "array", "items": {"type": "string"}},
                "sourceTool": {"type": "string"},
                "projectId": {"type": "string"},
                "conversationId": {"type": "string"},
                "taskId": {"type": "string"},
                "runId": {"type": "string"},
                "idempotencyKey": {"type": "string"},
            },
            "required": ["name"],
        },
    ),
    (
        "artifact_list",
        "List and search artifacts the user can access. Filter by query, category, "
        "tags, task or run; set mine=true for this run's outputs.",
        {
            "type": "object",
            "properties": {
                "q": {"type": "string"},
                "category": {"type": "string"},
                "tags": {"type": "array", "items": {"type": "string"}},
                "taskId": {"type": "string"},
                "runId": {"type": "string"},
                "projectId": {"type": "string"},
                "mine": {"type": "boolean"},
                "sort": {"type": "string"},
                "limit": {"type": "integer"},
                "offset": {"type": "integer"},
            },
        },
    ),
    (
        "artifact_get",
        "Get one artifact's metadata, provenance and preview status by id.",
        {"type": "object", "properties": {"artifactId": {"type": "string"}}, "required": ["artifactId"]},
    ),
    (
        "artifact_add_version",
        "Add a new version to an existing artifact (a revised file). The prior "
        "version is preserved.",
        {
            "type": "object",
            "properties": {
                "artifactId": {"type": "string"},
                "path": {"type": "string"},
                "contentBase64": {"type": "string"},
                "changeNote": {"type": "string"},
                "idempotencyKey": {"type": "string"},
            },
            "required": ["artifactId"],
        },
    ),
    (
        "artifact_tag",
        "Add tags to an artifact so it is easier to find later.",
        {
            "type": "object",
            "properties": {
                "artifactId": {"type": "string"},
                "tags": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["artifactId", "tags"],
        },
    ),
    (
        "artifact_create_collection",
        "Create a named collection to group related artifacts.",
        {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "description": {"type": "string"},
                "parentId": {"type": "string"},
            },
            "required": ["name"],
        },
    ),
]

_HANDLERS = {
    "artifact_register": _register,
    "artifact_list": _list,
    "artifact_get": _get,
    "artifact_add_version": _add_version,
    "artifact_tag": _tag,
    "artifact_create_collection": _create_collection,
}


def register_artifact_tools(registry: ToolRegistry) -> list[str]:
    """Register the artifact tools on the shared registry. Returns the names."""
    registered: list[str] = []
    for name, description, schema in _DEFS:
        if registry.get(name) is not None:
            continue
        registry.register(ToolDefinition(
            name=name, description=description, input_schema=schema,
            handler=_HANDLERS[name], permission="read",  # agent-local catalog state
            risk="low", timeout_ms=20_000,
        ))
        registered.append(name)
    return registered


__all__ = ["register_artifact_tools"]
