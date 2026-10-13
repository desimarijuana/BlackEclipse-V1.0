"""Learning-research tools for the existing ToolRegistry.

Thin, read-only adapters (except progress writes, which are low-risk and
owner-scoped) over the learning engine and the front-door education connectors.
They register on the SAME `ToolRegistry` as everything else, so schema
validation, permission checks, the effect authorizer and timeouts apply
unchanged — no second registry, no second agent loop.

Discovery tools return *pointers* (search results). `resource_verify` is the one
that fetches and marks a resource verified/accessible. `learning_path_build`
assembles a validated curriculum from discovered resources and, when asked,
performs a bounded multi-source discovery itself. Nothing is fabricated: an
unavailable connector returns an honest UNAVAILABLE with diagnostics.
"""

from __future__ import annotations

from typing import Any, Optional

from ..tools import ToolContext, ToolDefinition, ToolRegistry, dumps
from .learning import (
    LearningResource,
    build_curriculum,
    rank_resources,
    resources_from_specs,
    resource_index,
    validate_curriculum,
)
from .web_contracts import SourceType
from .web_extract import fetch
from .web_sources import classify_source_type

# ── helpers ────────────────────────────────────────────────────────────────────


def _bridge(ctx: ToolContext) -> Any:
    return getattr(ctx, "data_bridge", None)


async def _bridge_fetch(ctx: ToolContext, capability: str, params: dict[str, Any]) -> Optional[dict[str, Any]]:
    bridge = _bridge(ctx)
    if bridge is None:
        return None
    try:
        payload = await bridge.fetch(capability, params)
    except Exception as exc:  # noqa: BLE001 - an unavailable provider is data, not a crash
        return {"status": "ERROR", "error": str(exc)}
    return payload if isinstance(payload, dict) else None


def _learning_store(ctx: ToolContext) -> Any:
    """Resolve the LearningStore bound to eclipse-memory.db.

    Prefers an attached store; otherwise lazily builds one from the runtime's
    EclipseMemoryService and caches it on the context.
    """
    store = getattr(ctx, "learning_store", None)
    if store is not None:
        return store
    memory_service = getattr(ctx, "memory_service", None)
    memory_store = getattr(memory_service, "store", None) if memory_service is not None else None
    if memory_store is None:
        memory_store = getattr(ctx, "memory_store", None)
    if memory_store is None:
        return None
    try:
        from .learning_store import LearningStore

        store = LearningStore(memory_store)
        ctx.learning_store = store  # type: ignore[attr-defined]
        return store
    except Exception:  # noqa: BLE001 - persistence is best-effort, never fatal
        return None


def _resource_from_result(item: dict[str, Any], *, default_type: Optional[SourceType] = None) -> Optional[dict[str, Any]]:
    url = str(item.get("url") or "").strip()
    if not url:
        return None
    st = item.get("sourceType")
    try:
        source_type = SourceType(str(st)) if st else (default_type or classify_source_type(url))
    except ValueError:
        source_type = default_type or classify_source_type(url)
    return {
        "url": url,
        "title": str(item.get("title") or "").strip() or url,
        "sourceType": source_type.value,
        "provider": item.get("provider") or item.get("platform"),
        "author": item.get("author") or item.get("channel") or item.get("publisher"),
        "description": str(item.get("description") or item.get("snippet") or ""),
        "publishedAt": item.get("publishedAt"),
        "durationSeconds": item.get("durationSeconds"),
        "thumbnail": item.get("thumbnail"),
        "topicTags": item.get("topicTags") or [],
        "verified": bool(item.get("verified")),
        "accessible": item.get("accessible"),
        "limitations": list(item.get("limitations") or []),
    }


# ── discovery tools (pointers) ──────────────────────────────────────────────────


async def video_metadata(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    video_id = str(args.get("video_id") or "").strip()
    if not video_id:
        return "A video_id is required.", {"status": "ERROR", "error": "video_id is required"}
    payload = await _bridge_fetch(ctx, "video_metadata", {"videoId": video_id, "provider": args.get("provider") or "youtube"})
    if payload is None:
        return "The video-metadata connector is unavailable (no bridge).", {"status": "UNAVAILABLE", "error": "bridge unavailable"}
    if payload.get("status") != "OK":
        return (f"Video metadata unavailable: {payload.get('error') or payload.get('failureClass') or 'no data'}.",
                {"status": payload.get("status", "UNAVAILABLE"), "diagnostics": payload.get("diagnostics", [])})
    meta = payload.get("video") or {}
    return (f"{meta.get('title', video_id)} — {meta.get('channel') or 'unknown channel'} "
            f"({meta.get('durationSeconds', 'unknown')}s).", {"status": "OK", "video": meta})


async def playlist_search(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    query = str(args.get("query") or "").strip()
    if not query:
        return "A query is required.", {"status": "ERROR", "error": "query is required"}
    limit = int(args.get("limit") or 8)
    payload = await _bridge_fetch(ctx, "playlist_search", {"query": query, "limit": limit, "provider": args.get("provider") or "youtube"})
    if payload is None:
        return "The playlist connector is unavailable (no bridge).", {"status": "UNAVAILABLE", "error": "bridge unavailable"}
    if payload.get("status") != "OK":
        return (f"No playlists: {payload.get('error') or payload.get('failureClass') or 'no data'}.",
                {"status": payload.get("status", "UNAVAILABLE"), "diagnostics": payload.get("diagnostics", [])})
    playlists = payload.get("results") or []
    lines = [f"- {p.get('title')} — {p.get('url')}" for p in playlists[:10]]
    return ("Playlists (pointers; verify before recommending):\n" + "\n".join(lines),
            {"status": "OK", "provider": payload.get("provider"), "results": playlists})


async def transcript_fetch(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    video_id = str(args.get("video_id") or "").strip()
    if not video_id:
        return "A video_id is required.", {"status": "ERROR", "error": "video_id is required"}
    payload = await _bridge_fetch(ctx, "transcript_fetch", {"videoId": video_id, "language": args.get("language") or "en"})
    if payload is None:
        return "The transcript connector is unavailable (no bridge).", {"status": "UNAVAILABLE", "error": "bridge unavailable"}
    if payload.get("status") != "OK":
        # Unavailable/disabled captions are an honest, expected outcome — never a
        # fabricated transcript.
        return (f"Transcript unavailable: {payload.get('error') or payload.get('failureClass') or 'captions not accessible by a permitted method'}.",
                {"status": payload.get("status", "UNAVAILABLE"), "diagnostics": payload.get("diagnostics", [])})
    segments = payload.get("segments") or []
    text = str(payload.get("text") or "")
    return (f"Transcript ({len(segments)} segments).", {"status": "OK", "language": payload.get("language"), "segments": segments, "text": text})


async def course_search(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    query = str(args.get("query") or "").strip()
    if not query:
        return "A query is required.", {"status": "ERROR", "error": "query is required"}
    payload = await _bridge_fetch(ctx, "course_search", {
        "query": query, "limit": int(args.get("limit") or 8),
        "level": args.get("level"), "budget": args.get("budget"), "language": args.get("language"),
    })
    if payload is None:
        return "The course connector is unavailable (no bridge).", {"status": "UNAVAILABLE", "error": "bridge unavailable"}
    if payload.get("status") != "OK":
        return (f"No courses: {payload.get('error') or payload.get('failureClass') or 'no data'}.",
                {"status": payload.get("status", "UNAVAILABLE"), "diagnostics": payload.get("diagnostics", [])})
    results = payload.get("results") or []
    lines = [f"- {c.get('title')} — {c.get('url')}" for c in results[:10]]
    return ("Courses (pointers):\n" + "\n".join(lines), {"status": "OK", "provider": payload.get("provider"), "results": results})


async def github_search(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    query = str(args.get("query") or "").strip()
    if not query:
        return "A query is required.", {"status": "ERROR", "error": "query is required"}
    payload = await _bridge_fetch(ctx, "github_search", {"query": query, "limit": int(args.get("limit") or 8), "language": args.get("language")})
    if payload is None:
        return "The GitHub connector is unavailable (no bridge).", {"status": "UNAVAILABLE", "error": "bridge unavailable"}
    if payload.get("status") != "OK":
        return (f"No repositories: {payload.get('error') or payload.get('failureClass') or 'no data'}.",
                {"status": payload.get("status", "UNAVAILABLE"), "diagnostics": payload.get("diagnostics", [])})
    results = payload.get("results") or []
    lines = [f"- {r.get('title')} — {r.get('url')}" for r in results[:10]]
    return ("Repositories (pointers):\n" + "\n".join(lines), {"status": "OK", "provider": payload.get("provider"), "results": results})


# ── verification / ranking ──────────────────────────────────────────────────────


async def resource_verify(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    """Fetch a resource safely and report observable verification facts.

    A successful HTTP response is NOT evidence of educational quality — it proves
    only that the URL is reachable. An unavailable URL is not declared dead from
    one transient failure.
    """
    url = str(args.get("url") or "").strip()
    if not url:
        return "A url is required.", {"status": "ERROR", "error": "url is required"}
    source_type = classify_source_type(url)
    result = await fetch(url, bridge=_bridge(ctx), timeout_s=float(args.get("timeout_seconds") or 20.0))
    verified = bool(result.ok and result.text)
    record = {
        "url": url,
        "sourceType": source_type.value,
        "verified": verified,
        "accessible": bool(result.ok),
        "status": result.status,
        "title": result.title,
        "error": result.error,
        "retrievedAt": None,
        "checks": ["url_scheme_host_validated", "ssrf_guard", "http_fetch"],
    }
    if not result.ok:
        return (f"Resource not reachable: {result.error or result.status}. Not declared dead from a single failure.",
                {"status": "PARTIAL", "resource": record})
    title = result.title or url
    return (f"Reachable: {title} ({source_type.value}). Reachability only — not a quality judgement.",
            {"status": "OK", "resource": record})


async def resource_rank(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    objective = str(args.get("learning_objective") or args.get("objective") or "").strip()
    if not objective:
        return "A learning_objective is required.", {"status": "ERROR", "error": "learning_objective is required"}
    resources = resources_from_specs(list(args.get("resources") or []))
    if not resources:
        return "No resources supplied to rank.", {"status": "ERROR", "error": "resources is required"}
    ranked = rank_resources(resources, objective)
    lines = [f"{i+1}. {r['resourceId']} (score {r['score']})" for i, r in enumerate(ranked[:10])]
    return ("Ranking (internal ordering signal, not a truth measure):\n" + "\n".join(lines),
            {"status": "OK", "objective": objective, "ranking": ranked})


# ── curriculum assembly ─────────────────────────────────────────────────────────


_DISCOVERY_KINDS = (
    ("web_search", None),
    ("video_search", SourceType.VIDEO),
    ("course_search", SourceType.COURSE),
    ("github_search", SourceType.REPOSITORY),
    ("academic_search", SourceType.ACADEMIC),
)


async def _discover(ctx: ToolContext, goal: str, *, per_source: int = 5, language: Optional[str] = None) -> list[dict[str, Any]]:
    """Bounded multi-source discovery for a learning goal. Returns resource dicts."""
    found: list[dict[str, Any]] = []
    seen: set[str] = set()
    for capability, default_type in _DISCOVERY_KINDS:
        query = f"{goal} tutorial course guide" if capability == "web_search" else goal
        payload = await _bridge_fetch(ctx, capability, {"query": query, "limit": per_source, **({"language": language} if language else {})})
        if not payload or payload.get("status") != "OK":
            continue
        for item in (payload.get("results") or [])[:per_source]:
            r = _resource_from_result(item, default_type=default_type)
            if not r or r["url"] in seen:
                continue
            seen.add(r["url"])
            found.append(r)
    return found


async def learning_path_build(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    goal = str(args.get("goal") or "").strip()
    if not goal:
        return "A goal is required.", {"status": "ERROR", "error": "goal is required"}

    constraints = list(args.get("constraints") or [])
    language = args.get("language")
    resources = list(args.get("resources") or [])
    discovered: list[dict[str, Any]] = []
    if not resources:
        discovered = await _discover(ctx, goal, per_source=int(args.get("per_source") or 5), language=language)
        resources = discovered

    res_objs = resources_from_specs(resources)
    graph = build_curriculum(
        goal=goal,
        skill_specs=list(args.get("skills") or []),
        resources=res_objs,
        start_level=str(args.get("current_level") or "unspecified"),
        target_competency=str(args.get("target_competency") or ""),
        assumptions=list(args.get("assumptions") or []) + ([f"constraints: {', '.join(constraints)}"] if constraints else []),
        alternatives=list(args.get("alternatives") or []),
    )
    index = resource_index(res_objs)
    payload = {
        "pathId": str(args.get("path_id") or "") or None,
        "goal": goal,
        "startLevel": graph.startLevel,
        "targetCompetency": graph.targetCompetency,
        "graph": graph.to_dict(),
        "resources": index,
        "constraints": constraints,
    }

    store = _learning_store(ctx)
    path_id = args.get("path_id")
    if store is not None:
        from .learning import _rid  # local id helper

        if not path_id:
            path_id = _rid("path", goal)
        existing = store.get_path(str(path_id))
        if existing:
            payload["pathId"] = path_id
            store.update_path(str(path_id), payload=payload, version=int(existing.get("version") or 1) + 1)
        else:
            store.save_path(str(path_id), goal=goal, payload=payload,
                            start_level=graph.startLevel, target_competency=graph.targetCompetency, version=1)
        payload["pathId"] = str(path_id)
        payload["persisted"] = True
    else:
        payload["persisted"] = False

    errors = [i for i in graph.issues if i["severity"] == "error"]
    warnings = [i for i in graph.issues if i["severity"] == "warning"]
    summary = (
        f"Built a learning path for '{goal}' with {len(graph.nodes)} skills and "
        f"{len(res_objs)} resources ({len(discovered)} freshly discovered). "
        f"{len(errors)} errors, {len(warnings)} warnings."
    )
    if errors:
        summary += " The prerequisite graph has errors and is NOT a valid curriculum as supplied."
    return summary, {"status": "OK", "pathId": payload.get("pathId"), "path": payload}


async def learning_progress_get(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    store = _learning_store(ctx)
    if store is None:
        return "Learning progress store is unavailable.", {"status": "UNAVAILABLE", "error": "no memory store"}
    path_id = str(args.get("path_id") or "").strip()
    if not path_id:
        # Resume: find the most recent active path for a goal, else list paths.
        goal = str(args.get("goal") or "").strip()
        if goal:
            found = store.find_active_by_goal(goal)
            if found:
                path_id = found["id"]
        if not path_id:
            return ("No path_id given and no active path matched. Recent paths listed.",
                    {"status": "OK", "paths": store.list_paths(limit=20)})
    path = store.get_path(path_id)
    if path is None:
        return f"No learning path {path_id}.", {"status": "NOT_FOUND", "pathId": path_id}
    store.touch(path_id)
    progress = store.list_node_progress(path_id)
    nodes = ((path.get("payload") or {}).get("graph") or {}).get("nodes") or []
    by_node = {p["nodeId"]: p for p in progress}
    completed = [n["id"] for n in nodes if by_node.get(n["id"], {}).get("status") == "completed"]
    next_node = next((n for n in nodes if by_node.get(n["id"], {}).get("status") not in ("completed", "skipped")), None)
    return (f"Path '{path.get('goal')}': {len(completed)}/{len(nodes)} skills complete.",
            {"status": "OK", "pathId": path_id, "path": path, "progress": progress,
             "completed": completed, "nextStep": next_node.get("id") if next_node else None})


async def learning_progress_update(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    store = _learning_store(ctx)
    if store is None:
        return "Learning progress store is unavailable.", {"status": "UNAVAILABLE", "error": "no memory store"}
    path_id = str(args.get("path_id") or "").strip()
    node_id = str(args.get("node_id") or "").strip()
    status = str(args.get("status") or "pending").strip()
    if not path_id or not node_id:
        return "path_id and node_id are required.", {"status": "ERROR", "error": "path_id and node_id are required"}
    if store.get_path(path_id) is None:
        return f"No learning path {path_id}.", {"status": "NOT_FOUND", "pathId": path_id}
    record = store.set_node_status(path_id, node_id, status, args.get("assessment"))
    return (f"Updated {node_id} → {record['status']}.", {"status": "OK", "record": record})


# ── registration ────────────────────────────────────────────────────────────────


_READ = dict(permission="read", risk="low")
_WRITE = dict(permission="write", risk="low")


def _obj(properties: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    return {"type": "object", "properties": properties, "required": required or []}


_STR = {"type": "string"}
_INT = {"type": "integer"}
_BOOL = {"type": "boolean"}
_STR_LIST = {"type": "array", "items": {"type": "string"}}
_OBJ_LIST = {"type": "array", "items": {"type": "object"}}

_SCHEMAS: dict[str, dict[str, Any]] = {
    "video_metadata": _obj({
        "video_id": {**_STR, "description": "The provider video id (e.g. a YouTube video id)."},
        "provider": {**_STR, "description": "Video provider; defaults to youtube."},
    }, ["video_id"]),
    "playlist_search": _obj({
        "query": _STR, "limit": _INT,
        "provider": {**_STR, "description": "Provider; defaults to youtube."},
    }, ["query"]),
    "transcript_fetch": _obj({
        "video_id": _STR,
        "language": {**_STR, "description": "BCP-47 language tag, e.g. en."},
    }, ["video_id"]),
    "course_search": _obj({
        "query": _STR, "limit": _INT,
        "level": {**_STR, "description": "beginner | intermediate | advanced"},
        "budget": {**_STR, "description": "free | paid | any"},
        "language": _STR,
    }, ["query"]),
    "github_search": _obj({"query": _STR, "limit": _INT, "language": _STR}, ["query"]),
    "resource_verify": _obj({
        "url": _STR,
        "timeout_seconds": {"type": "number"},
    }, ["url"]),
    "resource_rank": _obj({
        "resources": _OBJ_LIST,
        "learning_objective": _STR,
    }, ["resources", "learning_objective"]),
    "learning_path_build": _obj({
        "goal": {**_STR, "description": "The learning goal."},
        "current_level": {**_STR, "description": "beginner | intermediate | advanced | unspecified"},
        "target_competency": _STR,
        "constraints": _STR_LIST,
        "language": _STR,
        "skills": {**_OBJ_LIST, "description": "Proposed skills: {id?, name, objectives[], prerequisites[], exercises[], project?, assessment?, milestone?, estimatedHours?}"},
        "resources": {**_OBJ_LIST, "description": "Discovered resources: {url, title, sourceType?, description?, durationSeconds?, topicTags?[]}"},
        "per_source": {**_INT, "description": "Discovery results per source when resources are omitted."},
        "path_id": {**_STR, "description": "Update an existing path id (preserves progress)."},
        "assumptions": _STR_LIST,
        "alternatives": _STR_LIST,
    }, ["goal"]),
    "learning_progress_get": _obj({
        "path_id": _STR,
        "goal": {**_STR, "description": "Used to resume when path_id is omitted."},
    }),
    "learning_progress_update": _obj({
        "path_id": _STR,
        "node_id": _STR,
        "status": {**_STR, "enum": ["pending", "in_progress", "completed", "skipped"]},
        "assessment": _STR,
    }, ["path_id", "node_id"]),
}

_TOOLS: list[tuple[str, str, Any, int, dict[str, Any]]] = [
    ("video_metadata", "Fetch one video's canonical metadata (title, channel, duration, description, thumbnail) from the configured provider. Missing fields stay missing.", video_metadata, 20_000, _READ),
    ("playlist_search", "Search coherent video playlists/lecture series, kept distinct from single videos. Returns pointers.", playlist_search, 20_000, _READ),
    ("transcript_fetch", "Fetch a video transcript ONLY through a permitted, supported method; unavailable/disabled captions are reported honestly, never fabricated.", transcript_fetch, 30_000, _READ),
    ("course_search", "Search established course/MOOC providers for a learning objective; returns pointers with level/budget hints.", course_search, 20_000, _READ),
    ("github_search", "Search GitHub repositories for example implementations, libraries and datasets. Returns pointers.", github_search, 20_000, _READ),
    ("resource_verify", "Safely fetch a resource and report observable reachability facts. Reachability is not a quality judgement; a single failure is not a death certificate.", resource_verify, 40_000, _READ),
    ("resource_rank", "Rank candidate resources for a learning objective with transparent, component-level scores. An internal ordering signal, not a measure of truth.", resource_rank, 15_000, _READ),
    ("learning_path_build", "Build (and persist) a validated, prerequisite-aware learning path. Discovers resources across sources when none are supplied; skills may be proposed by the model and are validated into a DAG with per-skill resources, exercises and assessments.", learning_path_build, 120_000, _READ),
    ("learning_progress_get", "Read a learner's persisted path progress and next step; resumes the most recent active path for a goal.", learning_progress_get, 10_000, _READ),
    ("learning_progress_update", "Persist a node's completion status and assessment result on a learning path.", learning_progress_update, 10_000, _WRITE),
]


def register_learning_tools(registry: ToolRegistry) -> list[str]:
    """Register the learning-research toolset. Returns the names added."""
    added: list[str] = []
    for name, description, handler, timeout, gate in _TOOLS:
        if registry.get(name) is not None:
            continue
        registry.register(
            ToolDefinition(
                name=name,
                description=description,
                input_schema=_SCHEMAS.get(name) or _obj({}),
                handler=handler,
                timeout_ms=timeout,
                long_running=name in _LONG_RUNNING,
                **gate,
            )
        )
        added.append(name)
    return added


_LONG_RUNNING = frozenset({"learning_path_build"})


__all__ = ["register_learning_tools"]
