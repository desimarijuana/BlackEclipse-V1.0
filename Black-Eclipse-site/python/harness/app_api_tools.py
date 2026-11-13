"""Bounded read-only access to the app's OWN local API (QA Round 1, Q4d).

The QA agent could not read the app's `/api/*` facts in-process: `curl` is on
the terminal hard-deny list, `health_check` returns a status code only, and web
research blocks loopback. This tool is the sanctioned path:

  * GET only, and only paths under `/api/`;
  * only the app's LOOPBACK origin (`HARNESS_CALLBACK_URL`, default
    `http://127.0.0.1:3000`) — a canonical public host is for the browser, not
    this surface;
  * no redirects, no auth/cookie forwarding, bounded time and response size.

It is a read of the user's own running app, not a general HTTP client.
"""

from __future__ import annotations

import json
import os
from typing import Any
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .tools import ToolContext, ToolDefinition, ToolRegistry

MAX_BYTES = 200_000
MAX_TEXT = 20_000
TIMEOUT_S = 10.0
PATH_PREFIX = "/api/"


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        return None


def _app_base() -> str:
    return (os.environ.get("HARNESS_CALLBACK_URL") or "http://127.0.0.1:3000").strip().rstrip("/")


def _is_loopback(host: str | None) -> bool:
    return (host or "").lower() in {"127.0.0.1", "localhost", "::1"}


def _refused(code: str, message: str) -> tuple[str, Any]:
    return f"REFUSED ({code}): {message}", {"status": "refused", "code": code}


async def app_api_get_handler(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    path = str(args.get("path") or "").strip()
    if not path:
        return _refused("APP_API_PATH_REQUIRED", "provide a path such as /api/learning-review?limit=5.")
    if not path.startswith("/"):
        path = "/" + path
    if "://" in path or not path.startswith(PATH_PREFIX):
        return _refused(
            "APP_API_PATH_NOT_ALLOWED",
            "only the app's own /api/ paths are readable (no absolute URLs, no other paths).",
        )
    base = _app_base()
    parts = urlsplit(base)
    if parts.scheme not in ("http", "https") or not _is_loopback(parts.hostname):
        return _refused(
            "APP_API_ORIGIN_NOT_ALLOWED",
            "the app read surface is loopback-only; set HARNESS_CALLBACK_URL to the local app origin.",
        )
    url = base + path
    try:
        request = Request(  # noqa: S310 - origin fixed to the local app above
            url,
            method="GET",
            headers={"Accept": "application/json, text/plain;q=0.9", "User-Agent": "eclipse-app-api"},
        )
        response = build_opener(_NoRedirect).open(request, timeout=TIMEOUT_S)
    except HTTPError as exc:
        # A 4xx/5xx is a real answer from the app, not an unreachable app.
        response = exc
    except Exception as exc:  # noqa: BLE001 - an unreachable app is an honest failure
        return (
            f"APP API UNAVAILABLE: the app did not answer {path} ({type(exc).__name__}). "
            f"Is it running at {base}?",
            {"status": "unavailable", "path": path, "base": base},
        )
    try:
        status = int(getattr(response, "status", getattr(response, "code", 200)) or 200)
        headers = getattr(response, "headers", None)
        content_type = headers.get("Content-Type", "") if headers is not None else ""
        raw = response.read(MAX_BYTES + 1)
    finally:
        try:
            response.close()
        except Exception:  # noqa: BLE001
            pass
    truncated = len(raw) > MAX_BYTES
    raw = raw[:MAX_BYTES]
    text = raw.decode("utf-8", errors="replace")
    body: Any = None
    if "json" in content_type.lower():
        try:
            body = json.loads(text)
        except ValueError:
            body = None
    # A guessed route answers with the app's full HTML 404 page. Pasting that
    # into the transcript taught the model nothing and encouraged more guesses
    # (`/api/journal/open`, `/api/journal/positions`, `/api/broker/positions`…)
    # until the run budget was gone. A missing API route must read as a short,
    # final "this route does not exist" — not as page content.
    if status >= 400 and "html" in content_type.lower():
        return (
            f"GET {path} → {status}: no such API route (the app answered with its HTML page, not JSON). "
            f"Do not guess another /api/ path; use a documented domain tool instead.",
            {
                "status": status,
                "path": path,
                "base": base,
                "contentType": content_type,
                "body": None,
                "text": "",
                "truncated": truncated,
                "routeMissing": True,
            },
        )
    preview = text[:4000] + ("\n… (response truncated for display)" if len(text) > 4000 else "")
    size_note = f" ({len(raw)} bytes" + (f", truncated at {MAX_BYTES}" if truncated else "") + ")"
    return (
        f"GET {path} → {status}{size_note}\n{preview}",
        {
            "status": status,
            "path": path,
            "base": base,
            "contentType": content_type,
            "body": body,
            "text": text[:MAX_TEXT],
            "truncated": truncated,
        },
    )


def register_app_api_tools(registry: ToolRegistry) -> list[str]:
    name = "app_api_get"
    if registry.get(name) is not None:
        return []
    registry.register(ToolDefinition(
        name=name,
        description=(
            "Read one GET route of Eclipse's OWN running app API (loopback only). "
            "Path must start with /api/ (e.g. /api/learning-review?limit=5). "
            "Read-only, bounded, no redirects, no credentials. Use it to verify what "
            "the app actually serves instead of guessing."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "App API path beginning with /api/ (query string allowed).",
                },
            },
            "required": ["path"],
        },
        handler=app_api_get_handler,
        permission="read",
        risk="low",
        timeout_ms=15_000,
    ))
    return [name]


__all__ = ["app_api_get_handler", "register_app_api_tools"]
