"""Agent tools for MCP integrations: discover the catalog, install a preset.

  * `mcp_integrations` — read-only, secret-free catalog of Eclipse's preset
    integrations (google_sheets, powerpoint, …), so the agent can tell the user
    what is available before asking to install one.
  * `mcp_install` — install ONE preset as a DISABLED, nothing-selected config
    (the same operation as the operator route; `mcp/install_ops.py`). Requires a
    single-use operator approval bound to the exact integration id.

Install is deliberately not activation (Phase 5 invariant): the entry ships
disabled with an empty tool selection, and the tool reports exactly that — the
operator enables it and selects tools in Settings → MCP. The agent can never
enable a server, select tools, or bypass the catalog.
"""

from __future__ import annotations

import hashlib
from typing import Any

from ..tools import ToolContext, ToolDefinition, ToolRegistry
from .install_ops import catalog_entry, find_integration, install_integration, list_catalog

APPROVAL_KIND = "mcp_install"


async def mcp_integrations_handler(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    catalog = list_catalog()
    if not catalog:
        return "No MCP integrations are defined.", {"count": 0, "integrations": []}
    lines = [f"{len(catalog)} MCP integration preset(s):"]
    for entry in catalog:
        flags = []
        if entry.get("community"):
            flags.append("community")
        if entry.get("oauth"):
            flags.append("oauth")
        if entry.get("requiresNode"):
            flags.append("needs node")
        if entry.get("requiresPython"):
            flags.append("needs python")
        suffix = f" [{', '.join(flags)}]" if flags else ""
        lines.append(f"  {entry['id']} — {entry['label']}: {entry['purpose'][:160]}{suffix}")
    lines.append("Installing one writes a disabled config; the user enables it in Settings → MCP.")
    return "\n".join(lines), {"count": len(catalog), "integrations": catalog}


async def mcp_install_handler(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    integration_id = str(args.get("integration_id") or args.get("integrationId") or "").strip()
    spec = find_integration(integration_id)
    if spec is None:
        return (
            f"Unknown MCP integration {integration_id!r}. Call mcp_integrations to list the catalog.",
            {"success": False, "reason": "unknown integration"},
        )
    result = install_integration(integration_id)
    if not result.get("success"):
        return (
            f"Could not install MCP integration {integration_id!r}: {result.get('reason')}",
            {"success": False, **result},
        )
    if result.get("alreadyInstalled"):
        return (
            f"MCP integration {integration_id!r} is already configured — left unchanged. "
            "Nothing was enabled; Settings → MCP shows its state.",
            {"success": True, "alreadyInstalled": True},
        )
    entry = catalog_entry(spec)
    lines = [
        f"Installed MCP integration {integration_id!r} as a DISABLED config with no tools selected.",
        "Installing is not activation: the user must enable it and select tools in Settings → MCP.",
    ]
    if entry.get("requiresNode"):
        lines.append("This server needs Node available on the machine.")
    if entry.get("requiresPython"):
        lines.append("This server needs Python available on the machine.")
    if entry.get("oauth"):
        lines.append("It uses OAuth: after enabling, the user completes a device-code login in Settings → MCP.")
    elif spec.secret_ref:
        lines.append(f"It expects the vault secret `{spec.secret_ref}` (value entered by the user, never by the agent).")
    return "\n".join(lines), {
        "success": True, "installed": integration_id,
        "enabled": False, "selectedTools": [],
    }


def register_mcp_install_tools(registry: ToolRegistry) -> None:
    registry.register(
        ToolDefinition(
            name="mcp_integrations",
            description=(
                "List Eclipse's preset MCP integrations (finance-relevant servers such as Google "
                "Sheets, PowerPoint, research and calendar tools) with capability flags. "
                "Read-only and secret-free; use it before proposing an install."
            ),
            input_schema={"type": "object", "properties": {}, "additionalProperties": False},
            handler=mcp_integrations_handler,
            permission="read",
            risk="low",
            timeout_ms=10_000,
        )
    )
    registry.register(
        ToolDefinition(
            name="mcp_install",
            description=(
                "Install ONE preset MCP integration from the catalog as a DISABLED config with no "
                "tools selected. This is not activation: the user enables it and selects tools in "
                "Settings → MCP. Requires an operator approval bound to this exact integration id. "
                "Ask the user before calling this."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "integration_id": {
                        "type": "string",
                        "description": "The catalog id from mcp_integrations, e.g. 'google_sheets'.",
                    },
                },
                "required": ["integration_id"],
                "additionalProperties": False,
            },
            handler=mcp_install_handler,
            permission="write",
            risk="medium",
            effect="external_action",
            timeout_ms=60_000,
        )
    )


def make_mcp_install_authorizer(inner: Any = None):
    """Gate `mcp_install` on a single-use operator approval bound to the id.

    Same semantics as every other approval card: single-use, digest-bound,
    pause-in-card-mode, deny/timeout never authorizes. Everything else falls
    through to `inner`.
    """

    async def authorize(tool: Any, args: dict[str, Any], ctx: Any = None) -> bool:
        name = str(getattr(tool, "name", ""))
        if name != "mcp_install":
            return bool(await inner(tool, args, ctx)) if inner is not None else False
        run_args = args or {}
        integration_id = str(run_args.get("integration_id") or run_args.get("integrationId") or "").strip()
        if not integration_id or find_integration(integration_id) is None:
            return False
        digest = hashlib.sha256(f"mcp_install\x00{integration_id}".encode("utf-8")).hexdigest()
        approvals = getattr(ctx, "approvals", None) if ctx is not None else None
        if approvals is None:
            return False
        claimed = approvals.consume_kind(kind=APPROVAL_KIND, request_key="mcp", digest=digest)
        if claimed is not None:
            return True
        pending = None
        try:
            pending = approvals.request_kind(
                kind=APPROVAL_KIND, request_key="mcp", digest=digest,
                effect="external_action",
                run_id=str(getattr(ctx, "run_id", "")),
                action_summary=f"Install MCP integration {integration_id} (disabled; nothing selected)",
                affected_data={"integrationId": integration_id},
                risk="medium",
            )
        except Exception:  # noqa: BLE001 - a store failure must never authorize
            return False
        emitter = getattr(ctx, "emitter", None)
        if emitter is not None:
            try:
                await emitter.emit("approval.requested", {
                    "approvalId": (pending or {}).get("id"),
                    "kind": APPROVAL_KIND,
                    "title": "Approve installing an MCP integration",
                    "summary": f"Install MCP integration `{integration_id}` (disabled; nothing selected)",
                    "effect": "external_action",
                    "risk": "medium",
                    "integrationId": integration_id,
                })
            except Exception:  # noqa: BLE001 - the card is best-effort
                pass
        if pending is not None:
            from .approvals import pause_for_decision  # noqa: PLC0415

            if await pause_for_decision(
                approvals, ctx, pending.get("id"),
                lambda: approvals.consume_kind(kind=APPROVAL_KIND, request_key="mcp", digest=digest),
                emitter=emitter, digest=digest,
                event_type="approval.approved",
                approved_payload={"kind": APPROVAL_KIND, "integrationId": integration_id},
            ):
                return True
        return False

    return authorize


__all__ = [
    "APPROVAL_KIND",
    "make_mcp_install_authorizer",
    "mcp_install_handler",
    "mcp_integrations_handler",
    "register_mcp_install_tools",
]
