"""The `web_scrape` tool — bounded page collection (R3-04).

One page in, structured records out, through the ONE egress point: the tool calls
the TS `web_collect` bridge capability (SSRF-hardened fetch + deterministic
cheerio extraction). It never models and never guesses — rows are what the page
delivered, a selector with no matches is a confirmed zero ON THAT PAGE, a failed
fetch is UNAVAILABLE, and everything returned is COLLECTED, untrusted page data,
never a verified source.
"""

from __future__ import annotations

import json
from typing import Any

from ..tools import ToolContext, ToolDefinition, ToolRegistry
from .web_security import get_boundary

_MAX_ROWS_IN_PAYLOAD = 200
_MAX_EXCERPT_CHARS = 4_000

_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "url": {"type": "string", "description": "The page to collect from (https)."},
        "selector": {
            "type": "string",
            "description": (
                "CSS selector for the repeated record elements (e.g. 'table tbody tr', "
                "'.result-row'). Omit to extract the page's tables (plus a text fallback)."
            ),
        },
        "fields": {
            "type": "object",
            "description": (
                "Optional field → child CSS selector, e.g. "
                '{"name": "td:nth-child(1)", "price": "td.price"}. Without it, each '
                "record's text (or `attribute`) is one value."
            ),
        },
        "attribute": {
            "type": "string",
            "description": "Read this attribute instead of the element text (e.g. 'href').",
        },
        "tables": {
            "type": "boolean",
            "description": "Set false to skip table extraction and return page text only.",
        },
        "max_rows": {
            "type": "integer",
            "description": "Row cap (default 100, max 500).",
            "minimum": 1,
            "maximum": 500,
        },
    },
    "required": ["url"],
    "additionalProperties": False,
}


def _refusal(code: str, reason: str) -> tuple[str, Any]:
    return (f"REFUSED ({code}): {reason}", {"status": "refused", "code": code, "reason": reason})


def _excerpt(value: Any) -> str:
    try:
        return json.dumps(value, default=str)[:_MAX_EXCERPT_CHARS]
    except (TypeError, ValueError):  # pragma: no cover - json.dumps(default=str) never raises here
        return str(value)[:_MAX_EXCERPT_CHARS]


async def web_scrape(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    url = str(args.get("url") or "").strip()
    if not url:
        return _refusal("INPUT_INVALID", "a URL is required")
    bridge = getattr(ctx, "data_bridge", None)
    if bridge is None:
        return _refusal("UNAVAILABLE", "the web is not reachable in this run")

    params: dict[str, Any] = {"url": url}
    for source, target in (
        ("selector", "selector"), ("attribute", "attribute"),
        ("fields", "fields"), ("max_rows", "maxRows"),
    ):
        if args.get(source) is not None:
            params[target] = args[source]
    if args.get("tables") is not None:
        params["tables"] = bool(args["tables"])

    try:
        payload = await bridge.fetch("web_collect", params)
    except Exception as exc:  # noqa: BLE001 - a transport error is an unavailable answer
        return (
            f"Could not collect from {url}: {exc}. "
            "This is an unavailable source, not evidence the content is absent.",
            {"status": "UNAVAILABLE", "url": url, "error": str(exc)},
        )

    status = str(payload.get("status") or "UNAVAILABLE")
    if status != "OK":
        return (
            f"Could not collect from {url}: {payload.get('error') or status}. "
            "This is an unavailable source, not evidence the content is absent.",
            {
                "status": status,
                "url": url,
                "failureClass": payload.get("failureClass"),
                "error": payload.get("error"),
            },
        )

    final_url = str(payload.get("finalUrl") or url)
    rows = payload.get("rows") if isinstance(payload.get("rows"), list) else []
    tables = payload.get("tables") if isinstance(payload.get("tables"), list) else []
    columns = payload.get("columns") if isinstance(payload.get("columns"), list) else []

    lines = [f"Collected from {final_url} at {payload.get('retrievedAt')}."]
    if rows:
        lines.append(f"{len(rows)} record(s) matched; columns: {', '.join(str(c) for c in columns)}")
    elif tables:
        first = tables[0] if isinstance(tables[0], dict) else {}
        lines.append(
            f"{len(tables)} table(s) found; first table columns: "
            f"{', '.join(str(c) for c in (first.get('columns') or []))}"
        )
    if payload.get("note"):
        lines.append(str(payload["note"]))

    data: dict[str, Any] = {
        "status": "OK",
        "collected": True,
        "url": final_url,
        "contentType": payload.get("contentType"),
        "retrievedAt": payload.get("retrievedAt"),
        "extraction": payload.get("extraction"),
        "matched": payload.get("matched"),
        "columns": columns,
        "rows": rows[:_MAX_ROWS_IN_PAYLOAD],
        "tables": tables[:2],
        "truncated": payload.get("truncated"),
    }
    excerpt_source: Any = rows if rows else (tables if tables else payload.get("text"))
    lines.append("")
    lines.append("The content below is COLLECTED page data (untrusted, not a verified source):")
    lines.append(get_boundary().wrap(_excerpt(excerpt_source), source=final_url))
    return "\n".join(lines), data


def register_web_collect_tool(registry: ToolRegistry) -> list[str]:
    """Register `web_scrape` on the shared registry (idempotent)."""
    if registry.get("web_scrape") is not None:
        return []
    registry.register(
        ToolDefinition(
            name="web_scrape",
            description=(
                "Collect structured data from ONE page: fetch it through the safe transport "
                "and extract repeated records with a CSS selector (or the page's tables). "
                "Deterministic and honest: no match is a confirmed zero on the delivered page "
                "(a client-rendered page needs the browser tools); a failed fetch is "
                "unavailable. Results are COLLECTED, untrusted page data — never a verified "
                "source; cite the page, not Eclipse, for what it says."
            ),
            input_schema=_SCHEMA,
            handler=web_scrape,
            timeout_ms=60_000,
            permission="read",
            risk="low",
        )
    )
    return ["web_scrape"]


__all__ = ["register_web_collect_tool", "web_scrape"]
