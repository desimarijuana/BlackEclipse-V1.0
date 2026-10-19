"""Agent tools for the skill acquire loop: install from GitHub, uninstall, list.

These are the user-facing half of "load this skill from GitHub and use it":

  * `skill_install`   — fetch + validate + content-scan + install + trust a
    GitHub repository's skills (one approval = one source).
  * `skill_uninstall` — remove an installed skill (folder + trust re-baseline).
  * `skill_sources`   — read-only listing of installed sources and their drift.

Admission is the ONE effect-authorizer chain (`code/authorizers.py`): the
`make_skill_authorizer` layer here requires a single-use, digest-bound operator
approval (`skill_install` / `skill_uninstall` kinds in the SAME approval store
the terminal/MCP capabilities use) and, in approval-card mode, PAUSES the run
for the operator's decision instead of refusing. A standing grant is deliberately
never offered: every install asks.

Installing is not a privilege escalation: a skill still runs through the same
permission/execution gate as any other, can never widen the agent's allowlist,
and instruction prose stays untrusted data under the skill-safety rule.
"""

from __future__ import annotations

import hashlib
from typing import Any

from ..tools import ToolContext, ToolDefinition, ToolRegistry
from .install import (
    InstallError,
    install_from_github,
    installed_skills_home,
    list_installed_sources,
    parse_source,
    source_digest,
    uninstall_skill,
)

APPROVAL_KINDS = ("skill_install", "skill_uninstall")


def _store(ctx: ToolContext) -> Any:
    memory_service = getattr(ctx, "memory_service", None)
    store = getattr(memory_service, "store", None) if memory_service is not None else None
    return store or getattr(ctx, "memory_store", None)


def _available_tools(ctx: ToolContext) -> list[str]:
    registry = getattr(ctx, "skill_registry", None)
    try:
        return list(registry._tool_names())  # noqa: SLF001 - the one validated tool-name source
    except Exception:  # noqa: BLE001 - validation stays best-effort
        return []


def _reload(ctx: ToolContext) -> None:
    """Re-read every skill tier so an install/uninstall is live in this run."""
    registry = getattr(ctx, "skill_registry", None)
    if registry is None:
        return
    try:
        registry.reload(installed_home=installed_skills_home())
    except Exception:  # noqa: BLE001 - the next boot re-reads; never fail the tool
        pass


async def skill_install_handler(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    """Install skills from a GitHub repository (post-approval)."""
    store = _store(ctx)
    if store is None:
        return "Skills are not available in this run.", {"ok": False, "error": "no skill store"}
    try:
        source = parse_source(
            str(args.get("source") or ""),
            ref=args.get("ref") if isinstance(args.get("ref"), str) else None,
            subpath=args.get("subpath") if isinstance(args.get("subpath"), str) else None,
        )
    except InstallError as exc:
        return f"Install refused: {exc}", {"ok": False, "error": str(exc)}
    try:
        result = install_from_github(
            store, source, available_tools=_available_tools(ctx), home=installed_skills_home(),
        )
    except InstallError as exc:
        return f"Install failed for {source.display}: {exc}", {
            "ok": False, "source": source.canonical, "error": str(exc),
        }
    _reload(ctx)
    lines = [
        f"Installed {len(result['installed'])} skill(s) from {source.display}:",
        *[f"  - {skill_id}" for skill_id in result["installed"]],
        "They are enabled and discoverable via skill_list; load one with skill_view "
        "and run it with skill_invoke.",
    ]
    if result["skipped"]:
        lines.append("Skipped:")
        lines.extend(f"  - {item['folder']}: {item['reason']}" for item in result["skipped"][:10])
    for skill_id, missing in (result.get("unknownTools") or {}).items():
        lines.append(
            f"  note: {skill_id} declares tools not present in this runtime ({', '.join(missing)}) "
            "— its invocation will report them."
        )
    for notice in result.get("notices") or []:
        lines.append(f"  note: {notice}")
    return "\n".join(lines), {"ok": True, **{k: v for k, v in result.items() if k != "ok"}}


async def skill_uninstall_handler(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    """Remove one installed skill (post-approval)."""
    store = _store(ctx)
    if store is None:
        return "Skills are not available in this run.", {"ok": False, "error": "no skill store"}
    skill_id = str(args.get("skill_id") or args.get("name") or "").strip()
    result = uninstall_skill(store, skill_id, home=installed_skills_home())
    if not result.get("ok"):
        return f"Uninstall refused: {result.get('error')}", result
    _reload(ctx)
    tail = "the install root was removed" if result.get("rootRemoved") else (
        "remaining in that source: " + ", ".join(result.get("remainingSkills") or []) or "none"
    )
    return f"Uninstalled {skill_id!r} ({tail}).", result


async def skill_sources_handler(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    """Read-only listing of installed skill sources and their trust state."""
    store = _store(ctx)
    if store is None:
        return "Skills are not available in this run.", {"count": 0, "sources": []}
    sources = list_installed_sources(store, home=installed_skills_home())
    if not sources:
        return "No GitHub-installed skill sources. Use skill_install with a repo URL.", {
            "count": 0, "sources": [],
        }
    lines = [f"{len(sources)} installed source(s):"]
    for source in sources:
        state = "trusted"
        if source.get("drift"):
            state = "changed — quarantined pending re-approval"
        if not source.get("trusted"):
            state = "untrusted"
        lines.append(
            f"  {source.get('url') or source['root']} [{state}] — "
            f"skills: {', '.join(source.get('skillIds') or []) or 'none'}"
        )
    return "\n".join(lines), {"count": len(sources), "sources": sources}


def register_skill_install_tools(registry: ToolRegistry) -> None:
    registry.register(
        ToolDefinition(
            name="skill_install",
            description=(
                "Install skills from a public GitHub repository so they can be used immediately "
                "(skill_list → skill_view → skill_invoke). Accepts skill folders with skill.json or "
                "the cross-tool SKILL.md convention (under skills/, .agents/skills/, "
                ".opencode/skills/ or .black-eclipse/skills/). The repository is fetched over https, "
                "validated and content-scanned; a skill tripping a quarantine rule is refused. "
                "Requires an operator approval bound to this exact source — after approval the "
                "skills are installed, enabled and trusted. Ask the user before calling this."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "source": {
                        "type": "string",
                        "description": "GitHub repository URL (https://github.com/owner/repo[/tree/<ref>/<path>]) or owner/repo.",
                    },
                    "ref": {"type": "string", "description": "Optional git ref (branch/tag/sha); overrides the URL."},
                    "subpath": {"type": "string", "description": "Optional folder inside the repo to scan."},
                    "note": {"type": "string", "description": "Why this skill is wanted; recorded in the trace."},
                },
                "required": ["source"],
                "additionalProperties": False,
            },
            handler=skill_install_handler,
            permission="write",
            risk="medium",
            effect="external_action",
            timeout_ms=180_000,
        )
    )
    registry.register(
        ToolDefinition(
            name="skill_uninstall",
            description=(
                "Remove one GitHub-installed skill (its folder and its trust record; the source's "
                "remaining skills stay). Use skill_sources to see what is installed. Requires an "
                "operator approval."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "skill_id": {"type": "string", "description": "The installed skill id to remove."},
                },
                "required": ["skill_id"],
                "additionalProperties": False,
            },
            handler=skill_uninstall_handler,
            permission="write",
            risk="low",
            effect="write",
            timeout_ms=60_000,
        )
    )
    registry.register(
        ToolDefinition(
            name="skill_sources",
            description=(
                "List GitHub-installed skill sources with their trust and drift state "
                "(read-only; no network)."
            ),
            input_schema={"type": "object", "properties": {}, "additionalProperties": False},
            handler=skill_sources_handler,
            permission="read",
            risk="low",
            timeout_ms=10_000,
        )
    )
    # The extension layer (agent-authored skills: create/update/delete) is
    # registered alongside the acquire loop; its effect authorizer is composed in
    # `code/authorizers.py`. Kept here (not `service.py`) to leave that ratcheted
    # file unchanged.
    from .manage_tools import register_skill_manage_tools  # noqa: PLC0415

    register_skill_manage_tools(registry)

    # Version history, reviews, activation and the learning switch: the read-only
    # half plus the two approval-gated writes. Registered here for the same reason
    # as the manage tools (keeps the ratcheted `service.py` unchanged).
    from .lifecycle_tools import register_skill_lifecycle_tools  # noqa: PLC0415

    register_skill_lifecycle_tools(registry)


def make_skill_authorizer(inner: Any = None):
    """Gate `skill_install`/`skill_uninstall` on a single-use operator approval.

    The approval is digest-bound to the exact source (normalized URL/ref/subpath)
    or skill id, lives in the SAME `ApprovalStore` as every other capability's,
    and is single-use. In approval-card mode the run PAUSES for the decision —
    the decision itself still comes from the store, so a denial/timeout can never
    authorize. Every other tool falls through to `inner` unchanged.
    """

    async def authorize(tool: Any, args: dict[str, Any], ctx: Any = None) -> bool:
        name = str(getattr(tool, "name", ""))
        if name not in ("skill_install", "skill_uninstall"):
            return bool(await inner(tool, args, ctx)) if inner is not None else False

        run_args = args or {}
        if name == "skill_install":
            try:
                source = parse_source(
                    str(run_args.get("source") or ""),
                    ref=run_args.get("ref") if isinstance(run_args.get("ref"), str) else None,
                    subpath=run_args.get("subpath") if isinstance(run_args.get("subpath"), str) else None,
                )
            except InstallError:
                return False
            kind = "skill_install"
            digest = source_digest(source)
            summary = f"Install skills from {source.display}"
            effect, risk = "external_action", "medium"
            payload = {"source": source.canonical}
        else:
            skill_id = str(run_args.get("skill_id") or run_args.get("name") or "").strip()
            if not skill_id:
                return False
            kind = "skill_uninstall"
            digest = hashlib.sha256(f"uninstall\x00{skill_id}".encode("utf-8")).hexdigest()
            summary = f"Uninstall installed skill {skill_id!r}"
            effect, risk = "write", "low"
            payload = {"skillId": skill_id}

        approvals = getattr(ctx, "approvals", None) if ctx is not None else None
        if approvals is None:
            return False
        claimed = approvals.consume_kind(kind=kind, request_key="skills", digest=digest)
        if claimed is not None:
            return True
        pending = None
        try:
            pending = approvals.request_kind(
                kind=kind, request_key="skills", digest=digest, effect=effect,
                run_id=str(getattr(ctx, "run_id", "")),
                action_summary=summary,
                affected_data=payload,
                risk=risk,
            )
        except Exception:  # noqa: BLE001 - a store failure must never authorize
            return False
        emitter = getattr(ctx, "emitter", None)
        if emitter is not None:
            try:
                await emitter.emit("approval.requested", {
                    "approvalId": (pending or {}).get("id"),
                    "kind": kind,
                    "title": "Approve installing skills from GitHub" if kind == "skill_install"
                    else "Approve uninstalling a skill",
                    "summary": summary,
                    "effect": effect,
                    "risk": risk,
                    **payload,
                })
            except Exception:  # noqa: BLE001 - the card is best-effort
                pass
        if pending is not None:
            from ..mcp.approvals import pause_for_decision  # noqa: PLC0415

            if await pause_for_decision(
                approvals, ctx, pending.get("id"),
                lambda: approvals.consume_kind(kind=kind, request_key="skills", digest=digest),
                emitter=emitter, digest=digest,
                event_type="approval.approved",
                approved_payload={"kind": kind, **payload},
            ):
                return True
        return False

    return authorize


__all__ = [
    "APPROVAL_KINDS",
    "make_skill_authorizer",
    "register_skill_install_tools",
    "skill_install_handler",
    "skill_sources_handler",
    "skill_uninstall_handler",
]
