"""MCP integration (Phase 5A–5C, hardened through Phase 6).

A user-directed extension surface: a user may connect local stdio MCP servers
and remote Streamable-HTTP/SSE servers, and use their tools for any finance
workflow. MCP tools are adapted into the existing `ToolRegistry`, so validation,
agent allowlists, read-only permission checks, timeouts, cancellation,
persistence and tool events remain authoritative. MCP results are attributed to
their server/tool and are never labelled Eclipse-verified.

Implemented: the typed server/effect/trust contract and threat boundary
(`config.py`), `${VAR}` resolution (`interpolation.py`), static entry screening
(`screening.py`), collision-resistant namespacing and schema validation
(`naming.py`), the stdio/http/sse client (`client.py`), lifecycle resilience —
retry/reconnect, keepalive, recycle, lazy schema cache and orphan reaping
(`lifecycle.py`, `schema_cache.py`, `orphan_supervisor.py`), OAuth/device flow
(`oauth.py`), redirect/origin policy (`redirect_guard.py`), resources/prompts and
sampling/elicitation (`interactions.py`), MCP-aware source planning
(`mcp_retrieval.py`), Eclipse-as-read-only-MCP-server (`server_exposure.py`), and
the registry adapter + lifecycle (`manager.py`). **Subscriptions are a documented
non-goal.** Status, remainder and limitations: `docs/harness/mcp-phase-6-progress.md`.
"""

from .client import (
    MCPCallError,
    MCPCallOutcome,
    MCPClosedError,
    MCPConnection,
    MCPDiscoveredTool,
    MCPError,
    MCPProtocolError,
    MCPSessionError,
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
from .lifecycle import RetryBudget
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
    "MCPSessionError",
    "MCPDiscoveredTool",
    "MCPCallOutcome",
    "RetryBudget",
    "EffectClass",
    "config_path",
    "load_mcp_configs",
    "namespace_tool",
    "normalize_input_schema",
    "redact_secrets",
]
