"""MCP integration install/list operations — ONE implementation, two surfaces.

The operator route (`routers/mcp.py`, `POST /mcp/integrations/{id}/install`) and
the agent tool (`mcp/install_tools.py`, approval-gated) both land here, so the
screen/upsert semantics can never drift between them.

Install is deliberately NOT activation: the preset is written as a DISABLED
config with no tools selected. The operator reviews and activates in
Settings → MCP — the agent tool reports exactly that instead of pretending the
server is live.
"""

from __future__ import annotations

from typing import Any, Optional

from .config import MCPServerConfig, load_mcp_configs, upsert_mcp_config
from .presets import IntegrationSpec, integration, integration_to_config
from .screening import refusals, screen_entry


def install_integration(integration_id: str) -> dict[str, Any]:
    """Install a preset integration as a DISABLED, nothing-selected config.

    Install is create-if-absent: if a server with the integration's id is
    already configured, the existing entry is left untouched, so re-installing
    never resets a change the user made (trust tier, selection, effects,
    declared data sources, confirmation).
    """
    spec = integration(integration_id)
    if spec is None:
        return {"success": False, "reason": "unknown integration"}
    existing, _ = load_mcp_configs()
    if any(c.id == spec.id for c in existing):
        return {
            "success": True,
            "installed": integration_id,
            "alreadyInstalled": True,
            "reason": "already configured; left unchanged",
        }
    entry = integration_to_config(spec)
    blocked = refusals(screen_entry(entry))
    if blocked:
        return {"success": False, "reason": blocked[0].message}
    upsert_mcp_config(MCPServerConfig(**entry))
    return {"success": True, "installed": integration_id, "config": entry}


def catalog_entry(spec: IntegrationSpec) -> dict[str, Any]:
    """A compact, secret-free catalog view of one integration (for the agent)."""
    return {
        "id": spec.id,
        "label": spec.label,
        "category": spec.category,
        "purpose": spec.purpose,
        "transport": spec.transport,
        "community": spec.community,
        "verified": spec.verified,
        "requiresNode": spec.requires_node,
        "requiresPython": spec.requires_python,
        "oauth": spec.oauth,
        "notes": spec.notes,
    }


def list_catalog() -> list[dict[str, Any]]:
    """Every preset integration as a compact catalog row, in catalog order."""
    return [catalog_entry(spec) for spec in _specs()]


def catalog_size() -> int:
    return len(_specs())


def _specs() -> list[IntegrationSpec]:
    from .presets import INTEGRATIONS  # noqa: PLC0415 - re-export seam stays private

    return list(INTEGRATIONS)


def find_integration(integration_id: str) -> Optional[IntegrationSpec]:
    return integration(integration_id)


__all__ = [
    "catalog_entry",
    "catalog_size",
    "find_integration",
    "install_integration",
    "list_catalog",
]
