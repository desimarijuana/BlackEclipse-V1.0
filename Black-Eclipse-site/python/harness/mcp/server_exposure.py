"""Eclipse as an MCP server (Phase 6, Milestone 7).

Expose Eclipse's OWN read capabilities to other MCP clients — done well this is a
moat (another agent can query Eclipse's research receipts and coverage). Done
badly it is a credential leak, so the design is deliberately narrow:

  * **Its own auth story.** A separate bearer token (`HARNESS_MCP_SERVER_TOKEN`),
    never the internal `require_operator` token. An unauthenticated client gets
    nothing.
  * **Read-only, narrow.** Start with status/capability discovery and
    research-receipt access. No write capability in this milestone.
  * **Reuse existing services.** It reads receipts/coverage through the same
    service; it does not re-implement portfolio/research/memory reads.
  * **Never expose** the vault, model credentials, the callback token, the
    environment, or internal orchestration state.

This module builds the tool implementations and a protocol-version declaration.
The transport (an ASGI app on its own path/port) is wired by the caller.
"""

from __future__ import annotations

import hmac
import os
from dataclasses import dataclass
from typing import Any, Callable, Optional

# The protocol version Eclipse-as-server serves (recorded, not assumed).
SERVED_PROTOCOL_VERSION = "2025-11-25"
SERVER_NAME = "eclipse"

# Content bounds (pagination + response limits).
MAX_LIMIT = 50
DEFAULT_LIMIT = 20

# Never expose any of these keys in a tool schema or payload.
_FORBIDDEN_KEY_TOKENS = (
    "secret", "token", "password", "apikey", "api_key", "vault", "credential",
    "callback", "env", "authorization", "bearer",
)


class McpServerAuthError(Exception):
    """The client did not prove identity."""

    code = "eclipse_mcp_unauthorized"


def auth_token_configured() -> bool:
    return bool(os.environ.get("HARNESS_MCP_SERVER_TOKEN", "").strip())


def verify_client(authorization: Optional[str]) -> bool:
    """Prove identity by a bearer token distinct from the operator secret.

    An unconfigured server token means the exposure is DISABLED, not open.
    """
    expected = os.environ.get("HARNESS_MCP_SERVER_TOKEN", "").strip()
    if not expected:
        return False
    provided = (authorization or "").strip()
    if provided.startswith("Bearer "):
        provided = provided[7:]
    return bool(provided) and hmac.compare_digest(provided, expected)


@dataclass
class ExposedTool:
    name: str
    description: str
    input_schema: dict[str, Any]

    def public(self) -> dict[str, Any]:
        return {"name": self.name, "description": self.description, "inputSchema": self.input_schema}


# The narrow, read-only surface. No write tool exists in this milestone.
EXPOSED_TOOLS: list[ExposedTool] = [
    ExposedTool(
        "eclipse_status",
        "Eclipse runtime status and the capabilities this server exposes (read-only).",
        {"type": "object", "properties": {}},
    ),
    ExposedTool(
        "eclipse_list_receipts",
        "List recent Eclipse research receipts (id + status + createdAt). Read-only, paginated.",
        {"type": "object", "properties": {"limit": {"type": "integer"}, "offset": {"type": "integer"}}},
    ),
    ExposedTool(
        "eclipse_get_receipt",
        "Fetch one Eclipse research receipt by run id (read-only).",
        {"type": "object", "properties": {"runId": {"type": "string"}}, "required": ["runId"]},
    ),
]


def _contains_forbidden(value: Any) -> bool:
    """True if a schema/payload references a secret-bearing key name."""
    if isinstance(value, dict):
        for key, item in value.items():
            if any(tok in str(key).lower() for tok in _FORBIDDEN_KEY_TOKENS):
                return True
            if _contains_forbidden(item):
                return True
    elif isinstance(value, list):
        return any(_contains_forbidden(v) for v in value)
    return False


def build_exposed_tools() -> list[dict[str, Any]]:
    """The tool schemas. None may reference a secret/env/vault key (asserted)."""
    rows = [t.public() for t in EXPOSED_TOOLS]
    for row in rows:
        if _contains_forbidden(row["inputSchema"]):
            raise ValueError(f"exposed tool {row['name']!r} schema references a secret-bearing key")
    return rows


def _error(rule: str) -> dict[str, Any]:
    """A structured error NAMING the rule; never a partial payload or a 500."""
    return {"isError": True, "content": [{"type": "text", "text": f"error: {rule}"}], "rule": rule}


def _text(payload: Any) -> dict[str, Any]:
    import json

    return {"isError": False, "content": [{"type": "text", "text": json.dumps(payload, default=str)}]}


def _bounded_limit(value: Any) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        return DEFAULT_LIMIT
    return max(1, min(n, MAX_LIMIT))


def call_exposed_tool(name: str, args: dict[str, Any], service: Any) -> dict[str, Any]:
    """Dispatch one read tool against the EXISTING service. Read-only always."""
    if name == "eclipse_status":
        return _text({
            "server": SERVER_NAME,
            "protocolVersion": SERVED_PROTOCOL_VERSION,
            "capabilities": {"tools": [t.name for t in EXPOSED_TOOLS], "resources": False, "prompts": False},
            "note": "Read-only. No write capability is exposed.",
        })
    if name == "eclipse_list_receipts":
        limit = _bounded_limit(args.get("limit"))
        try:
            offset = max(0, int(args.get("offset") or 0))
        except (TypeError, ValueError):
            offset = 0
        receipts = service.list_receipts(limit=MAX_LIMIT) if hasattr(service, "list_receipts") else []
        page = receipts[offset:offset + limit]
        rows = [{"runId": r.get("runId"), "status": r.get("status"), "createdAt": r.get("createdAt")} for r in page]
        return _text({"receipts": rows, "limit": limit, "offset": offset, "total": len(receipts)})
    if name == "eclipse_get_receipt":
        run_id = str(args.get("runId") or "")
        if not run_id:
            return _error("runId is required")
        receipt = service.get_receipt(run_id) if hasattr(service, "get_receipt") else None
        if receipt is None:
            return _error("receipt not found")
        return _text({"receipt": receipt})
    return _error("unknown tool")


def build_mcp_server(service: Any):
    """Build the MCP server object exposing the read-only tools over the service."""
    from mcp import types as mcp_types
    from mcp.server.mcpserver import MCPServer

    server = MCPServer(SERVER_NAME, version=SERVED_PROTOCOL_VERSION)

    def _register(tool: ExposedTool):
        async def _handler(**kwargs: Any) -> str:
            result = call_exposed_tool(tool.name, kwargs, service)
            text = result["content"][0]["text"]
            if result.get("isError"):
                raise ValueError(text)
            return text

        _handler.__name__ = tool.name
        server.tool(
            name=tool.name,
            description=tool.description,
            annotations=mcp_types.ToolAnnotations(read_only_hint=True),
        )(_handler)

    for tool in EXPOSED_TOOLS:
        _register(tool)
    return server


def build_asgi_app(service: Any):
    """An ASGI app serving Eclipse over Streamable HTTP on its own transport.

    `mcp-session-id`-less requests must carry `Authorization: Bearer
    <HARNESS_MCP_SERVER_TOKEN>`; an unauthenticated request is refused with 401.
    """
    from starlette.applications import Starlette
    from starlette.responses import JSONResponse
    from starlette.routing import Mount

    server = build_mcp_server(service)
    inner = server.streamable_http_app()

    async def app(scope, receive, send):
        if scope["type"] == "http":
            headers = {k.decode().lower(): v.decode() for k, v in scope.get("headers", [])}
            if not verify_client(headers.get("authorization")):
                response = JSONResponse({"error": "unauthorized"}, status_code=401)
                await response(scope, receive, send)
                return
        await inner(scope, receive, send)

    return app


__all__ = [
    "SERVED_PROTOCOL_VERSION",
    "SERVER_NAME",
    "McpServerAuthError",
    "auth_token_configured",
    "verify_client",
    "build_exposed_tools",
    "call_exposed_tool",
    "build_mcp_server",
    "build_asgi_app",
    "EXPOSED_TOOLS",
]
