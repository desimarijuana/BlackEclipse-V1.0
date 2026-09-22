"""Memory & skill tools — the agent-facing surface of Eclipse-Memory.

These are the tools the system prompt actually promises. They are registered on
the SAME `ToolRegistry` as the financial tools, so there is no second registry,
and the runtime's existing permission/validation/timeout machinery applies.

Tools:
  * `memory`      — save / list / search durable memory (write via the service
                    pipeline so type/scope/dedupe/evidence are enforced).
  * `skill_list`  — compact skill metadata for discovery (progressive load step 1-2).
  * `skill_view`  — load one skill's full instructions (step 3).

Skill *execution* still goes through `skills.runtime.execute_skill`; these tools
only let the agent discover and read. Nothing here enables a skill or writes a
skill version — that remains an operator-gated lifecycle action.
"""

from __future__ import annotations

from typing import Any, Optional

from .tools import ToolContext, ToolDefinition, ToolRegistry


def _service(ctx: ToolContext) -> Any:
    svc = getattr(ctx, "memory_service", None)
    if svc is None:
        raise RuntimeError("Eclipse-Memory service is not attached to this run")
    return svc


# ── memory ──────────────────────────────────────────────────────────────────


async def memory_handler(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    action = str(args.get("action") or "list")
    svc = _service(ctx)

    if action == "save":
        content = str(args.get("content") or "").strip()
        memory_type = str(args.get("type") or "semantic")
        scope = str(args.get("scope") or "general")
        scope_id = args.get("scope_id") or ctx.user_id
        try:
            memory = svc.write_memory(
                memory_type=memory_type,
                content=content,
                source="explicit_user" if not ctx.is_skill_run else "execution_lesson",
                scope=scope,
                scope_id=str(scope_id) if scope_id else None,
                subject=args.get("subject"),
                source_run_id=ctx.run_id,
                confidence=float(args.get("confidence", 0.8)),
                verification="verified" if args.get("verified") else "unverified",
                created_by=ctx.user_id or "agent",
            )
        except Exception as exc:  # noqa: BLE001 - a rejected write is honest output
            return f"MEMORY NOT SAVED — {exc}", {"saved": False, "error": str(exc)}
        return (
            f"Memory saved ({memory['memoryType']}/{memory['scope']}) id={memory['id']}.",
            {"saved": True, "id": memory["id"], "memoryType": memory["memoryType"], "scope": memory["scope"]},
        )

    if action == "search":
        query = str(args.get("query") or "")
        result = svc.retrieve(
            query=query,
            memory_types=args.get("types"),
            subject=args.get("subject"),
            actor_scope=ctx.user_id and "user",
            scope_id=ctx.user_id,
            run_id=ctx.run_id,
            limit=int(args.get("limit", 8)),
        )
        if not result.memories:
            return (
                "No relevant memory found.",
                {"count": 0, "diagnostics": result.diagnostics},
            )
        lines = [f"{len(result.memories)} memory item(s):"]
        for memory in result.memories:
            lines.append(
                f"  [{memory['memoryType']}/{memory.get('verification','unverified')}] "
                f"{memory.get('subject') or ''} — {memory['content']}"
            )
        return "\n".join(lines), {"count": len(result.memories), "memories": result.memories}

    # list
    memories = svc.store.list_memories(
        memory_type=args.get("type"), scope=args.get("scope"),
        scope_id=args.get("scope_id") or ctx.user_id,
        limit=int(args.get("limit", 20)), include_inactive=False,
    )
    if not memories:
        return "No stored memory yet.", {"count": 0, "memories": []}
    lines = [f"{len(memories)} stored memory item(s):"]
    for memory in memories:
        lines.append(f"  [{memory['memoryType']}] {memory['content'][:180]}")
    return "\n".join(lines), {"count": len(memories), "memories": memories}


# ── skill_list / skill_view ─────────────────────────────────────────────────


async def skill_list_handler(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    registry = getattr(ctx, "skill_registry", None)
    if registry is None:
        return "Skills are not available in this run.", {"count": 0}
    results = registry.discover(
        query=str(args.get("query") or ""),
        category=args.get("category"),
        include_non_executable=True,
    )
    if not results:
        return "No skills match.", {"count": 0, "skills": []}
    lines = [f"{len(results)} skill(s):"]
    for skill in results:
        lines.append(
            f"  {skill['id']} (v{skill['version']}, {skill['status']}) — {skill['description'][:160]}"
        )
    return "\n".join(lines), {"count": len(results), "skills": results}


async def skill_view_handler(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    registry = getattr(ctx, "skill_registry", None)
    if registry is None:
        return "Skills are not available in this run.", {"found": False}
    skill_id = str(args.get("name") or args.get("skill_id") or "").strip()
    if not skill_id:
        return "A skill name is required.", {"found": False}
    loaded = registry.get(skill_id)
    if loaded is None:
        return f"No skill named {skill_id!r}. Use skill_list to see available skills.", {"found": False}
    manifest = loaded.manifest
    instructions = ""
    try:
        instructions = loaded.load_instructions()
    except OSError:
        instructions = ""
    body = "\n".join([
        f"# {manifest.name} ({manifest.id} v{manifest.version})",
        f"Status: {manifest.status} · Risk: {manifest.riskLevel}",
        f"Description: {manifest.description}",
        "",
        instructions or "(This skill has no prose procedure.)",
    ])
    return body, {
        "found": True,
        "skillId": manifest.id,
        "version": manifest.version,
        "status": manifest.status,
        "requiredTools": manifest.requiredTools,
        "permissions": manifest.permissions,
    }


def register_memory_tools(registry: ToolRegistry) -> None:
    registry.register(
        ToolDefinition(
            name="memory",
            description=(
                "Persistent agent memory across sessions. action='save' stores a durable fact "
                "(type: preference|semantic|procedural|episodic|constraint|observation|summary); "
                "action='search' retrieves relevant memories; action='list' lists stored memory. "
                "Save only durable, reusable facts — not every sentence. User preferences are "
                "user-scoped; never turn them into universal rules."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["save", "search", "list"], "description": "Operation to perform."},
                    "content": {"type": "string", "description": "The memory content (action=save). Write a declarative fact, not an instruction."},
                    "type": {"type": "string", "enum": ["preference", "semantic", "procedural", "episodic", "constraint", "observation", "summary"], "description": "Memory type."},
                    "scope": {"type": "string", "enum": ["user", "general", "market", "task"], "description": "Memory scope."},
                    "scope_id": {"type": "string", "description": "Scope identifier (e.g. user id)."},
                    "subject": {"type": "string", "description": "Optional subject key (ticker, topic)."},
                    "query": {"type": "string", "description": "Search query (action=search)."},
                    "limit": {"type": "integer", "description": "Max results."},
                    "confidence": {"type": "number", "description": "0..1 confidence in the fact."},
                    "verified": {"type": "boolean", "description": "Whether the fact was verified against evidence."},
                },
                "required": ["action"],
            },
            handler=memory_handler,
            permission="read",  # memory is agent-local state, not a data mutation
            risk="low",
            timeout_ms=10_000,
        )
    )
    registry.register(
        ToolDefinition(
            name="skill_list",
            description=(
                "List available skills (compact metadata) so you can decide whether to load one. "
                "Progressive disclosure step 1: this does NOT return full instructions."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Optional keyword filter."},
                    "category": {"type": "string", "description": "Optional category filter."},
                },
            },
            handler=skill_list_handler,
            permission="read",
            risk="low",
            timeout_ms=10_000,
        )
    )
    registry.register(
        ToolDefinition(
            name="skill_view",
            description=(
                "Load the full instructions (SKILL.md) for one skill by name/id. Progressive "
                "disclosure step 3: call this only after skill_list narrows the candidates."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "The skill id, e.g. 'finance.fundamental-analysis'."},
                },
                "required": ["name"],
            },
            handler=skill_view_handler,
            permission="read",
            risk="low",
            timeout_ms=10_000,
        )
    )


__all__ = ["register_memory_tools"]
