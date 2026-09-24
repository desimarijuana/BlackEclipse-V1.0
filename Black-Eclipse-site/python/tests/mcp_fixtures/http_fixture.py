"""A local Streamable-HTTP MCP server for Phase-5D tests.

Binds 127.0.0.1 on the port given as argv[1] and serves a read-only `echo` tool.
A Starlette middleware REQUIRES `Authorization: Bearer <HTTP_FIXTURE_TOKEN>`
(env var set by the test), returning 401 otherwise — so a successful
initialize/call proves the client actually sent the vault-resolved header.

Run as a subprocess: `python http_fixture.py <port>`.
"""

import os
import sys

import uvicorn
from mcp import types
from mcp.server.mcpserver import MCPServer
from starlette.responses import PlainTextResponse

server = MCPServer("http-fixture", version="1.0.0")


@server.tool(description="Echo the provided text.", annotations=types.ToolAnnotations(read_only_hint=True))
def echo(text: str) -> str:
    return f"echo:{text}"


class RequireBearer:
    """Reject any request whose Authorization header does not match the token."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        expected = os.environ.get("HTTP_FIXTURE_TOKEN", "")
        headers = {k.decode().lower(): v.decode() for k, v in scope.get("headers", [])}
        if expected and headers.get("authorization") != f"Bearer {expected}":
            response = PlainTextResponse("unauthorized", status_code=401)
            await response(scope, receive, send)
            return
        await self.app(scope, receive, send)


def main() -> None:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
    app = RequireBearer(server.streamable_http_app())
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="error")


if __name__ == "__main__":
    main()
