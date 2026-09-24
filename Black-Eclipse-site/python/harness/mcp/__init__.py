"""MCP integration (Phase 5A–5C).

A user-directed extension surface: a user may connect local stdio MCP servers and
use their tools for any finance workflow. MCP tools are adapted into the existing
`ToolRegistry`, so validation, agent allowlists, read-only permission checks,
timeouts, cancellation, persistence and tool events remain authoritative. MCP
results are attributed to their server/tool and are never labelled
Eclipse-verified.

This slice implements: the typed server/effect contract and threat boundary
(`config.py`), collision-resistant namespacing and schema validation (`naming.py`),
the local stdio client (`client.py`), and the registry adapter + lifecycle
(`manager.py`). Remote HTTP/OAuth, settings UI, effectful-tool approval, Eclipse
as an MCP server, and resources/prompts/subscriptions are deliberately out of
scope and remain future work.
"""

from .client import (
    MCPCallError,
    MCPCallOutcome,
    MCPClosedError,
    MCPConnection,
    MCPDiscoveredTool,
    MCPError,
    MCPProtocolError,
    MCPStartupError,
    MCPTimeoutError,
)
from .config import (
    EffectClass,
    MCPConfigError,
    MCPServerConfig,
    config_path,
    load_mcp_configs,
    redact_secrets,
)
from .manager import MCPManager
from .naming import namespace_tool, normalize_input_schema

__all__ = [
    "MCPManager",
    "MCPConnection",
    "MCPServerConfig",
    "MCPConfigError",
    "MCPError",
    "MCPStartupError",
    "MCPTimeoutError",
    "MCPCallError",
    "MCPProtocolError",
    "MCPClosedError",
    "MCPDiscoveredTool",
    "MCPCallOutcome",
    "EffectClass",
    "config_path",
    "load_mcp_configs",
    "namespace_tool",
    "normalize_input_schema",
    "redact_secrets",
]
