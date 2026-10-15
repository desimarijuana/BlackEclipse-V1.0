"""Agent-authored extension skills — the declarative extension layer.

This is Eclipse's `skill_manage` analogue: the agent may author, edit and delete
its own **procedural skills**. A skill is DECLARATIVE (a validated `SkillManifest`
plus bounded instructions) — never code, never a new tool, never a permission
grant. It rides the SAME `SkillRegistry.create_user_skill` / `update_user_skill` /
`delete_user_skill` a person uses, so execution, discovery, versioning and the
permission policy are unchanged.

Safety, enforced in code:

  * `authoring.build_user_manifest` validates the manifest against the SAME
    pydantic schema as built-ins and refuses any permission outside
    `SAFE_PERMISSIONS` — an agent-authored skill can never widen its authority.
  * Editing produces a NEW version; a built-in can never be edited or deleted.
  * Every write is a `write`-permission tool, removed at `plan_only` by
    `code.policy.ACQUISITION_WRITE_TOOLS`, and gated by a SINGLE-USE, digest-bound
    operator approval (`make_skill_manage_authorizer`) in the effect chain — the
    "one operator decision authorizes exactly one call" rule every capability uses.
"""

from __future__ import annotations

import hashlib
from typing import Any

from ..tools import ToolDefinition, ToolRegistry

MANAGE_TOOLS: tuple[str, ...] = ("skill_create", "skill_update", "skill_delete")


def _registry_of(ctx: Any) -> Any:
    return getattr(ctx, "skill_registry", None)


def _digest(kind: str, key: str, body: str = "") -> str:
    """Bind the approval to the exact action + subject (+ body for create/update),
    so a changed payload needs a NEW approval (never reused silently)."""
    payload = f"{kind}\x00{key}\x00{body}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


# ── handlers ──────────────────────────────────────────────────────────────────


async def skill_create_handler(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    registry = _registry_of(ctx)
    if registry is None:
        return "Skills are not available in this run.", {"created": False, "error": "SKILLS_UNAVAILABLE"}
    name = str(args.get("name") or "").strip()
    instructions = str(args.get("instructions") or "").strip()
    if not name or not instructions:
        return "A skill name and instructions are required.", {"created": False, "error": "MISSING_INPUT"}
    try:
        from .authoring import SkillAuthoringError

        result = registry.create_user_skill(
            name=name,
            description=str(args.get("description") or name).strip(),
            instructions=instructions,
            category=str(args.get("category") or "research"),
            tags=args.get("tags") if isinstance(args.get("tags"), list) else None,
            required_tools=args.get("required_tools") if isinstance(args.get("required_tools"), list) else None,
            author="agent",
        )
    except SkillAuthoringError as exc:
        return f"Could not create the skill: {exc}", {"created": False, "error": "SKILL_AUTHORING_FAILED", "reason": str(exc)}
    except Exception as exc:  # noqa: BLE001 - a store failure is reported, never hidden
        return f"Could not create the skill: {exc}", {"created": False, "error": "SKILL_AUTHORING_FAILED", "reason": str(exc)}
    return (
        f"Created skill {result['skillId']} (v{result['version']}).",
        {"created": True, **result},
    )


async def skill_update_handler(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    registry = _registry_of(ctx)
    if registry is None:
        return "Skills are not available in this run.", {"updated": False, "error": "SKILLS_UNAVAILABLE"}
    skill_id = str(args.get("skill_id") or args.get("name") or "").strip()
    if not skill_id:
        return "A skill id is required.", {"updated": False, "error": "MISSING_INPUT"}
    patch: dict[str, Any] = {}
    for key in ("name", "description", "instructions", "category", "tags"):
        if key in args and args[key] is not None:
            patch[key] = args[key]
    if not patch:
        return "Nothing to update.", {"updated": False, "error": "MISSING_INPUT"}
    try:
        from .authoring import SkillAuthoringError

        result = registry.update_user_skill(skill_id, **patch)
    except SkillAuthoringError as exc:
        return f"Could not update the skill: {exc}", {"updated": False, "error": "SKILL_AUTHORING_FAILED", "reason": str(exc)}
    except Exception as exc:  # noqa: BLE001
        return f"Could not update the skill: {exc}", {"updated": False, "error": "SKILL_AUTHORING_FAILED", "reason": str(exc)}
    return (
        f"Updated skill {result['skillId']} (v{result['version']}).",
        {"updated": True, **result},
    )


async def skill_delete_handler(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    registry = _registry_of(ctx)
    if registry is None:
        return "Skills are not available in this run.", {"deleted": False, "error": "SKILLS_UNAVAILABLE"}
    skill_id = str(args.get("skill_id") or args.get("name") or "").strip()
    if not skill_id:
        return "A skill id is required.", {"deleted": False, "error": "MISSING_INPUT"}
    try:
        from .authoring import SkillAuthoringError

        result = registry.delete_user_skill(skill_id)
    except SkillAuthoringError as exc:
        return f"Could not delete the skill: {exc}", {"deleted": False, "error": "SKILL_AUTHORING_FAILED", "reason": str(exc)}
    except Exception as exc:  # noqa: BLE001
        return f"Could not delete the skill: {exc}", {"deleted": False, "error": "SKILL_AUTHORING_FAILED", "reason": str(exc)}
    verb = "Deleted" if result.get("deleted") else "Kept for audit (deprecated)"
    return f"{verb} skill {result['skillId']}.", {"updated": True, **result}


# ── registration ────────────────────────────────────────────────────────────


def register_skill_manage_tools(registry: ToolRegistry) -> None:
    registry.register(
        ToolDefinition(
            name="skill_create",
            description=(
                "Save a reusable procedure as a skill (procedural memory) for future "
                "turns. A skill is instructions — never code, never a new tool, never a "
                "permission grant. Use it after working out a non-trivial workflow worth "
                "repeating, or when the user says 'turn this into a skill'. Requires an "
                "operator approval."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "A short human name for the skill."},
                    "description": {"type": "string", "description": "One sentence on when to use it."},
                    "instructions": {"type": "string", "description": "The procedure: the steps, the tool calls that work, and the pitfalls."},
                    "category": {"type": "string", "description": "Optional category (default: research)."},
                    "tags": {"type": "array", "items": {"type": "string"}, "description": "Optional tags."},
                    "required_tools": {"type": "array", "items": {"type": "string"}, "description": "Optional tool names the procedure uses (must be real, registered tools)."},
                },
                "required": ["name", "instructions"],
                "additionalProperties": False,
            },
            handler=skill_create_handler,
            permission="write",
            risk="low",
            effect="write",
        )
    )
    registry.register(
        ToolDefinition(
            name="skill_update",
            description=(
                "Edit one of the skills Eclipse authored (a user/agent skill). Built-in "
                "skills cannot be edited. Always produces a NEW version — history is never "
                "rewritten. Requires an operator approval."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "skill_id": {"type": "string", "description": "The skill id to update."},
                    "name": {"type": "string"},
                    "description": {"type": "string"},
                    "instructions": {"type": "string"},
                    "category": {"type": "string"},
                    "tags": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["skill_id"],
                "additionalProperties": False,
            },
            handler=skill_update_handler,
            permission="write",
            risk="low",
            effect="write",
        )
    )
    registry.register(
        ToolDefinition(
            name="skill_delete",
            description=(
                "Delete a skill Eclipse authored. A skill with execution history is kept "
                "for audit (deprecated) instead of being destroyed. Built-ins cannot be "
                "deleted. Requires an operator approval."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "skill_id": {"type": "string", "description": "The skill id to delete."},
                },
                "required": ["skill_id"],
                "additionalProperties": False,
            },
            handler=skill_delete_handler,
            permission="write",
            risk="low",
            effect="write",
        )
    )


# ── the effect authorizer ─────────────────────────────────────────────────────


def make_skill_manage_authorizer(inner: Any = None):
    """Gate `skill_create`/`skill_update`/`skill_delete` on a single-use,
    digest-bound operator approval (kinds `skill_create`/`skill_update`/
    `skill_delete` in the ONE approval store). In approval-card mode the run
    PAUSES for the decision; a denial/timeout can never authorize. Every other
    tool falls through to `inner` unchanged.
    """

    async def authorize(tool: Any, args: dict[str, Any], ctx: Any = None) -> bool:
        name = str(getattr(tool, "name", ""))
        if name not in MANAGE_TOOLS:
            return bool(await inner(tool, args, ctx)) if inner is not None else False

        run_args = args or {}
        subject = str(run_args.get("skill_id") or run_args.get("name") or "").strip()
        if not subject:
            return False
        body = str(run_args.get("instructions") or "")
        digest = _digest(name, subject, body)

        approvals = getattr(ctx, "approvals", None) if ctx is not None else None
        if approvals is None:
            return False

        # A call-scope already authorized at an earlier seam: authorize without a
        # second claim.
        if ctx is not None and getattr(ctx, "effect_authorized_digest", None) == digest:
            return True

        claimed = approvals.consume_kind(kind=name, request_key="skill_authoring", digest=digest)
        if claimed is not None:
            try:
                ctx.effect_authorized_digest = digest  # type: ignore[union-attr]
            except Exception:  # noqa: BLE001
                pass
            return True

        summary = {
            "skill_create": f"Create a skill named {subject!r}",
            "skill_update": f"Update the skill {subject!r}",
            "skill_delete": f"Delete the skill {subject!r}",
        }[name]
        pending = None
        try:
            pending = approvals.request_kind(
                kind=name, request_key="skill_authoring", digest=digest,
                effect="write",
                run_id=str(getattr(ctx, "run_id", "")),
                action_summary=summary,
                risk="low",
            )
        except Exception:  # noqa: BLE001 - a store failure must never authorize
            return False

        emitter = getattr(ctx, "emitter", None)
        if emitter is not None:
            try:
                await emitter.emit("approval.requested", {
                    "approvalId": (pending or {}).get("id"),
                    "kind": name,
                    "title": "Approve saving a skill" if name == "skill_create" else "Approve changing a skill",
                    "summary": summary,
                    "effect": "write",
                    "risk": "low",
                    "skillId": subject,
                })
            except Exception:  # noqa: BLE001 - the card is best-effort
                pass

        if pending is not None:
            from ..mcp.approvals import pause_for_decision  # noqa: PLC0415

            if await pause_for_decision(
                approvals, ctx, pending.get("id"),
                lambda: approvals.consume_kind(kind=name, request_key="skill_authoring", digest=digest),
                emitter=emitter, digest=digest,
                event_type="approval.approved",
                approved_payload={"kind": name, "skillId": subject},
            ):
                return True
        return False

    return authorize


__all__ = [
    "MANAGE_TOOLS",
    "make_skill_manage_authorizer",
    "register_skill_manage_tools",
    "skill_create_handler",
    "skill_delete_handler",
    "skill_update_handler",
]
