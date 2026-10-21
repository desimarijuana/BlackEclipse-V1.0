"""The `scraper_run` tool — collect data the vault does not have.

When the answer is not in JDdS, the agent writes a scraper for the site that has
it and runs it here. The program is ordinary Python with one obligation: leave
the records in ``result``.

    import eclipse_tools

    page = eclipse_tools.web_page(
        url="https://example.com/holdings",
        selector="table tbody tr",
        fields={"name": "td:nth-child(1)", "weight": "td:nth-child(2)"},
    )
    result = {"rows": page.get("rows") or [], "columns": ["name", "weight"]}

The program cannot open a socket, read a file outside its own folder or start a
process: it fetches ONLY through `eclipse_tools.web_page`, which the host
resolves through the same safe transport every other web tool uses (https-only,
DNS-pinned, every redirect re-checked, size and time caps).

What comes back is COLLECTED page data. It is stored in the vault as a dataset
whose rows say `SCRAPER`, and it is never presented as a verified source.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Optional

from ..code.execution import AnalysisRequest, AnalysisResult, run_analysis
from ..tools import ToolContext, ToolDefinition, ToolRegistry
from . import store
from .program import ScraperProgramError, check_program, read_result, wrap_program

TOOL_NAME = "scraper_run"

#: How many pages one scraper may fetch. The budget is the HOST's, not the
#: program's: a scraper that walks five pages is normal, one that walks the
#: whole internet is not.
MAX_PAGE_FETCHES = 40
DEFAULT_TIMEOUT_S = 180
MAX_TIMEOUT_S = 600
MAX_SOURCE_CHARS = 20_000

_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "name": {
            "type": "string",
            "description": "What this collection is called (it becomes the dataset's name).",
        },
        "purpose": {
            "type": "string",
            "description": "In plain words, what this collection is for (goes in the record).",
        },
        "target_url": {
            "type": "string",
            "description": (
                "The page the scraper starts from. Its SITE is what the operator "
                "approves, so use the address you will actually collect from."
            ),
        },
        "code": {
            "type": "string",
            "description": (
                "A Python program. It may `import eclipse_tools` and call "
                "`eclipse_tools.web_page(url=..., selector=..., fields=..., links=True, "
                "max_rows=...)` to fetch and read a page; the host does the fetching "
                "and the extraction, so the program never opens a socket. Leave the "
                "records in `result = {\"rows\": [{...}, ...]}` (optional "
                "`\"columns\": [...]` and `\"notes\": \"...\"`)."
            ),
        },
        "scraper": {
            "type": "string",
            "description": (
                "Instead of `code`: the id of a scraper saved earlier, to run it again."
            ),
        },
        "columns": {
            "type": "array",
            "items": {"type": "string"},
            "description": "The columns the records have (optional — inferred from the rows).",
        },
        "timeout_s": {
            "type": "integer",
            "description": "How long the whole collection may take (seconds).",
            "minimum": 10,
            "maximum": MAX_TIMEOUT_S,
        },
    },
    "required": ["name", "purpose", "target_url"],
    "additionalProperties": False,
}


def _refusal(code: str, reason: str, **data: Any) -> tuple[str, dict[str, Any]]:
    return f"REFUSED ({code}): {reason}", {"status": "refused", "code": code, "reason": reason, **data}


def _resolver(ctx: ToolContext, deadline: float):
    """Bridge the sandbox's (synchronous) fetch to the async bridge.

    The sandbox runs on a worker thread, so the call is posted back to the run's
    event loop and only the worker thread waits.
    """
    bridge = getattr(ctx, "data_bridge", None)
    if bridge is None:
        return None
    loop = asyncio.get_running_loop()

    def resolve(capability: str, params: dict[str, Any]) -> dict[str, Any]:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("the collection ran out of time while waiting for a page")
        payload = dict(params)
        # The bridge speaks camelCase; the sandbox binding is snake_case.
        if "max_rows" in payload:
            payload["maxRows"] = payload.pop("max_rows")
        future = asyncio.run_coroutine_threadsafe(bridge.fetch(capability, payload), loop)
        return future.result(timeout=remaining)

    return resolve


def _run_program(
    ctx: ToolContext, *, source: str, purpose: str, timeout_s: int, resolver: Any,
) -> AnalysisResult:
    request = AnalysisRequest(
        source=wrap_program(source),
        purpose=purpose[:300],
        timeout_s=timeout_s,
        allow_tools=True,
    )
    # The kernel is deliberately NOT used: the scraper lane needs the host's
    # tool set and URL literals, which the warm kernel does not carry.
    return run_analysis(
        request,
        tool_resolver=resolver,
        kernel=None,
        tool_allowlist=("web_page",),
        allow_url_literals=True,
        tool_call_limit=MAX_PAGE_FETCHES,
    )


async def scraper_run(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    name = str(args.get("name") or "").strip()
    purpose = str(args.get("purpose") or "").strip()
    target_url = str(args.get("target_url") or "").strip()
    saved_id = str(args.get("scraper") or "").strip()

    if not name:
        return _refusal("INPUT_INVALID", "the collection needs a name")
    if not purpose:
        return _refusal("INPUT_INVALID", "tell me what this collection is for — it goes in the record")
    if not target_url and saved_id:
        saved = store.load_scraper(ctx, saved_id)
        if saved is None:
            known = ", ".join(item["id"] for item in store.list_scrapers(ctx)) or "none yet"
            return _refusal(
                "SCRAPER_NOT_FOUND",
                f"there is no saved scraper called {saved_id!r} (saved scrapers: {known})",
            )
        target_url = str(saved.get("targetUrl") or "")
        name = name or str(saved.get("name") or saved_id)
    if not target_url:
        return _refusal("INPUT_INVALID", "the collection needs the address to collect from")

    source = str(args.get("code") or "")
    if not source and saved_id:
        saved = store.load_scraper(ctx, saved_id)
        source = str((saved or {}).get("program") or "")
    if not source.strip():
        known = ", ".join(item["id"] for item in store.list_scrapers(ctx)) or "none yet"
        return _refusal(
            "INPUT_INVALID",
            "the collection needs a program, or the id of a scraper saved earlier "
            f"(saved scrapers: {known})",
        )
    try:
        source = check_program(source)
    except ScraperProgramError as exc:
        return _refusal(exc.code, exc.reason)

    bridge = getattr(ctx, "data_bridge", None)
    if bridge is None:
        return _refusal("BRIDGE_UNAVAILABLE", "the web is not reachable from here, so I collected nothing")

    timeout_s = int(args.get("timeout_s") or DEFAULT_TIMEOUT_S)
    timeout_s = max(10, min(timeout_s, MAX_TIMEOUT_S))
    deadline = time.monotonic() + timeout_s
    resolver = _resolver(ctx, deadline)
    if resolver is None:
        return _refusal("BRIDGE_UNAVAILABLE", "the web is not reachable from here, so I collected nothing")

    try:
        result = await asyncio.to_thread(
            _run_program,
            ctx,
            source=source,
            purpose=purpose,
            timeout_s=timeout_s,
            resolver=resolver,
        )
    except Exception as exc:  # noqa: BLE001 - a runner failure is an honest failure
        return _refusal("SCRAPER_FAILED", f"the collection stopped: {exc}")

    if result.status != "ok":
        detail = (result.stderr or "").strip()[:600]
        return _refusal(
            result.code or "SCRAPER_FAILED",
            f"the collection did not finish ({result.status}). {detail}".strip(),
            toolCalls=len(result.tool_calls),
        )

    try:
        rows, columns, notes = read_result(result.outputs)
    except ScraperProgramError as exc:
        return _refusal(exc.code, exc.reason)

    declared = args.get("columns")
    if isinstance(declared, list) and declared:
        wanted = [str(column).strip() for column in declared if str(column).strip()]
        if wanted and not columns:
            columns = wanted
        if wanted and wanted != columns:
            missing = [column for column in wanted if column not in columns]
            if missing:
                notes = (notes + " " if notes else "") + (
                    f"the program did not return these columns: {', '.join(missing)}."
                )

    stored = await store.persist_rows(
        bridge,
        name=name,
        description=f"Collected by Eclipse from {target_url}",
        source_url=target_url,
        purpose=purpose,
        columns=columns,
        rows=rows,
    )
    saved = store.save_scraper(
        ctx,
        name=name,
        program=source,
        target_url=target_url,
        columns=columns,
        purpose=purpose,
        dataset=(stored.get("dataset") or {}).get("name") if isinstance(stored.get("dataset"), dict) else None,
    )

    pages = len(result.tool_calls)
    if rows:
        lines = [
            f"Collected {len(rows)} row(s) from {target_url}.",
            f"Columns: {', '.join(columns) if columns else 'none'}.",
            f"Pages read: {pages}.",
        ]
        if notes:
            lines.append(notes)
        if stored.get("ok"):
            dataset = stored.get("dataset") or {}
            lines.append(
                f"Saved as the dataset {dataset.get('name')} ({stored.get('written', 0)} row(s) stored)."
            )
        else:
            lines.append(
                f"I could not store the rows ({stored.get('error') or 'the vault refused them'}), "
                "so they are only in this answer."
            )
        if saved:
            lines.append(f"The scraper is saved as {saved!r} — I can run it again on request.")
        lines.append("")
        lines.append(
            "This is COLLECTED page data (untrusted, not a verified source): "
            "cite the page, not Eclipse, for what it says."
        )
        text = "\n".join(lines)
    else:
        text = (
            f"The scraper ran and reached {target_url}, but no records matched. "
            "That is a confirmed zero for the pages it read — try a different selector "
            "or a different address."
        )

    data = {
        "status": "ok" if rows else "empty",
        "collected": bool(rows),
        "provenance": "collected",
        "url": target_url,
        "rows": rows[:200],
        "rowCount": len(rows),
        "columns": columns,
        "pagesRead": pages,
        "notes": notes or None,
        "dataset": stored.get("dataset") if isinstance(stored.get("dataset"), dict) else None,
        "stored": bool(stored.get("ok")),
        "storeError": stored.get("error"),
        "scraper": saved,
        "toolCalls": [call.model_dump(by_alias=True) for call in result.tool_calls],
    }
    return text, data


def register_scraper_tools(registry: ToolRegistry) -> list[str]:
    """Register `scraper_run` on the shared registry (idempotent)."""
    if registry.get(TOOL_NAME) is not None:
        return []
    registry.register(
        ToolDefinition(
            name=TOOL_NAME,
            description=(
                "Collect data from a website the vault does not have, by writing and "
                "running a scraper for it. Give the address, the purpose, and a short "
                "Python program that fetches the page(s) with `eclipse_tools.web_page` "
                "and leaves the records in `result = {\"rows\": [...]}`; the host does "
                "the fetching, so the program never opens a socket. The site is "
                "approved by the operator once, then remembered. The rows are stored "
                "as a dataset labelled SCRAPER — collected page data, never a "
                "verified source."
            ),
            input_schema=_SCHEMA,
            handler=scraper_run,
            timeout_ms=600_000,
            permission="write",
            risk="medium",
            effect="write",
            long_running=True,
        )
    )
    return [TOOL_NAME]


__all__ = ["MAX_PAGE_FETCHES", "TOOL_NAME", "register_scraper_tools", "scraper_run"]
