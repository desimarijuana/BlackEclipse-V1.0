"""A local OAuth authorization server fixture for device-code tests (offline).

Serves, on 127.0.0.1:<port>:
  * `/.well-known/oauth-authorization-server` — metadata with device+token URLs
  * `/device`  — RFC 8628 device authorization (returns a device+user code)
  * `/token`   — polls: `authorization_pending` once, then the access token
  * `/mcp`     — a Streamable-HTTP MCP endpoint that REQUIRES `Bearer <token>`

The approval is "instant" after the first poll so the test is deterministic and
offline. Run as a subprocess: `python oauth_fixture.py <port> [token]`.
"""

import os
import sys

import uvicorn
from mcp import types
from mcp.server.mcpserver import MCPServer
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, PlainTextResponse
from starlette.routing import Mount, Route

TOKEN = os.environ.get("OAUTH_FIXTURE_TOKEN", "fixture-access-token")
_polls = {"n": 0}

server = MCPServer("oauth-fixture", version="1.0.0")


@server.tool(description="Echo the provided text.", annotations=types.ToolAnnotations(read_only_hint=True))
def echo(text: str) -> str:
    return f"echo:{text}"


async def metadata(request: Request) -> JSONResponse:
    base = str(request.base_url).rstrip("/")
    return JSONResponse({
        "issuer": base,
        "device_authorization_endpoint": f"{base}/device",
        "token_endpoint": f"{base}/token",
        "authorization_endpoint": f"{base}/authorize",
        "registration_endpoint": f"{base}/register",
    })


async def resource_metadata(request: Request) -> JSONResponse:
    base = str(request.base_url).rstrip("/")
    # SEP-985 protected-resource metadata: name the authorization server + resource.
    return JSONResponse({
        "resource": f"{base}/mcp",
        "authorization_servers": [base],
        "scopes_supported": ["read"],
    })


async def register(request: Request) -> JSONResponse:
    base = str(request.base_url).rstrip("/")
    import json as _json

    body = _json.loads(await request.body() or b"{}")
    return JSONResponse({
        "client_id": "fixture-client-id",
        "redirect_uris": body.get("redirect_uris") or [],
        "token_endpoint_auth_method": "none",
    })


async def authorize(request: Request) -> JSONResponse:
    # Auto-approve: return the code via the redirect target as a JSON body the
    # test's redirect_handler can read (no real browser needed).
    redirect_uri = request.query_params.get("redirect_uri", "")
    state = request.query_params.get("state", "")
    return JSONResponse({"code": "auth-code-1", "state": state, "redirect_uri": redirect_uri})



async def device(request: Request) -> JSONResponse:
    base = str(request.base_url).rstrip("/")
    return JSONResponse({
        "device_code": "device-code-1",
        "user_code": "USER-CODE",
        "verification_uri": f"{base}/verify",
        "expires_in": 60,
        "interval": 1,
    })


async def token(request: Request) -> JSONResponse:
    raw = await request.body() or b"{}"
    try:
        import json as _json

        body = _json.loads(raw)
    except Exception:  # noqa: BLE001 - form-encoded body
        from urllib.parse import parse_qs

        body = {k: v[0] for k, v in parse_qs(raw.decode("utf-8", "ignore")).items()}
    grant = body.get("grant_type")
    if grant in ("authorization_code", "refresh_token"):
        # Authorization-code + PKCE (and refresh) exchange succeeds immediately.
        return JSONResponse({"access_token": TOKEN, "token_type": "Bearer", "expires_in": 3600, "refresh_token": "refresh-1"})
    # Device flow: pending once, then the token.
    _polls["n"] += 1
    if _polls["n"] == 1:
        return JSONResponse({"error": "authorization_pending"})
    return JSONResponse({"access_token": TOKEN, "token_type": "Bearer", "expires_in": 3600, "refresh_token": "refresh-1"})


class RequireBearer:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = {k.decode().lower(): v.decode() for k, v in scope.get("headers", [])}
        if headers.get("authorization") != f"Bearer {TOKEN}":
            # RFC 9728: point the client at the protected-resource metadata so the
            # SDK's OAuth provider can discover the authorization server.
            response = PlainTextResponse(
                "unauthorized",
                status_code=401,
                headers={"WWW-Authenticate": 'Bearer resource_metadata="/.well-known/oauth-protected-resource"'},
            )
            await response(scope, receive, send)
            return
        await self.app(scope, receive, send)


def main() -> None:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8766
    mcp_app = RequireBearer(server.streamable_http_app())
    app = Starlette(routes=[
        Route("/.well-known/oauth-authorization-server", metadata),
        Route("/.well-known/oauth-protected-resource", resource_metadata),
        Route("/.well-known/oauth-protected-resource/mcp", resource_metadata),
        Route("/register", register, methods=["POST"]),
        Route("/authorize", authorize),
        Route("/device", device, methods=["POST"]),
        Route("/token", token, methods=["POST"]),
        Mount("/", app=mcp_app),
    ])
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="error")


if __name__ == "__main__":
    main()
