"""R3-04 — the `web_scrape` tool: bounded page collection through the bridge.

The tool is a thin, honest wrapper over the TS `web_collect` capability:
collected rows are returned as untrusted page data with the page as the source,
a failed fetch is UNAVAILABLE (not proof the content is absent), and nothing is
fabricated.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

from harness.research.web_collect import register_web_collect_tool, web_scrape
from harness.tools import ToolRegistry


class _Bridge:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def fetch(self, capability: str, params: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((capability, params))
        return self.payload


def _ctx(bridge: Any) -> Any:
    return SimpleNamespace(data_bridge=bridge)


def test_scrape_returns_rows_as_collected_untrusted_data() -> None:
    bridge = _Bridge({
        "status": "OK",
        "finalUrl": "https://x.test/a",
        "retrievedAt": "2026-10-12T00:00:00Z",
        "rows": [{"name": "A", "price": "1"}],
        "columns": ["name", "price"],
        "matched": 1,
        "contentType": "text/html",
        "extraction": "selector",
    })
    text, data = asyncio.run(web_scrape(
        {"url": "https://x.test/a", "selector": "tr", "max_rows": 10}, _ctx(bridge)
    ))
    assert bridge.calls[0] == ("web_collect", {"url": "https://x.test/a", "selector": "tr", "maxRows": 10})
    assert data["status"] == "OK"
    assert data["collected"] is True
    assert data["rows"][0]["name"] == "A"
    assert data["url"] == "https://x.test/a"
    assert "COLLECTED" in text
    assert "1 record(s)" in text


def test_scrape_reports_an_unavailable_source_without_fabricating() -> None:
    bridge = _Bridge({"status": "UNAVAILABLE", "error": "blocked", "failureClass": "blocked"})
    text, data = asyncio.run(web_scrape({"url": "https://x.test/a"}, _ctx(bridge)))
    assert data["status"] == "UNAVAILABLE"
    assert data["failureClass"] == "blocked"
    assert "not evidence the content is absent" in text


def test_scrape_requires_a_url() -> None:
    text, data = asyncio.run(web_scrape({}, _ctx(_Bridge({}))))
    assert data["status"] == "refused"
    assert "URL" in text


def test_scrape_reports_a_missing_bridge_honestly() -> None:
    text, data = asyncio.run(web_scrape({"url": "https://x.test/a"}, SimpleNamespace()))
    assert data["status"] == "refused"
    assert data["code"] == "UNAVAILABLE"
    assert "not reachable" in text


def test_scrape_reports_a_transport_error() -> None:
    class _Boom:
        async def fetch(self, capability: str, params: dict[str, Any]) -> dict[str, Any]:
            raise RuntimeError("boom")

    text, data = asyncio.run(web_scrape({"url": "https://x.test/a"}, _ctx(_Boom())))
    assert data["status"] == "UNAVAILABLE"
    assert "not evidence the content is absent" in text


def test_registration_is_idempotent_and_read_only() -> None:
    registry = ToolRegistry()
    assert register_web_collect_tool(registry) == ["web_scrape"]
    assert register_web_collect_tool(registry) == []
    tool = registry.get("web_scrape")
    assert tool is not None
    assert tool.permission == "read"
