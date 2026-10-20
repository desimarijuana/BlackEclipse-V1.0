"""App-shell and dashboard-template SDK tools."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from harness.sdk import app_tools, dashboard_template_tools


def _nav_payload() -> dict:
    return {
        "nav": {
            "mode": "agentic",
            "sections": [
                {"id": "chat", "enabled": True},
                {"id": "dashboard", "enabled": False},
            ],
        }
    }


@pytest.mark.asyncio
async def test_app_get_summarizes_visible_and_hidden(monkeypatch):
    async def fake_request(method, path, *, body=None):
        assert method == "GET"
        assert path == ""
        return 200, _nav_payload()

    monkeypatch.setattr(app_tools, "_app_request", fake_request)
    text, data = await app_tools._get({}, None)
    assert "Nav mode: agentic" in text
    assert "chat" in text
    assert "dashboard" in text
    assert data["nav"]["mode"] == "agentic"


@pytest.mark.asyncio
async def test_app_nav_update_sends_sections_and_mode(monkeypatch):
    captured: dict = {}

    async def fake_request(method, path, *, body=None):
        captured.update({"method": method, "path": path, "body": body})
        return 200, _nav_payload()

    monkeypatch.setattr(app_tools, "_app_request", fake_request)
    text, _ = await app_tools._nav_update(
        {"sections": [{"id": "sdk", "enabled": False}], "mode": "graph"}, None,
    )
    assert captured["method"] == "PUT"
    assert captured["body"]["nav"]["sections"] == [{"id": "sdk", "enabled": False}]
    assert captured["body"]["nav"]["mode"] == "graph"
    assert "Updated the app navigation" in text


@pytest.mark.asyncio
async def test_app_nav_update_requires_a_change(monkeypatch):
    async def fake_request(*args, **kwargs):  # pragma: no cover - must not run
        raise AssertionError("no request expected")

    monkeypatch.setattr(app_tools, "_app_request", fake_request)
    text, data = await app_tools._nav_update({}, None)
    assert data["error"] == "APP_NAV_EMPTY"
    assert "Nothing to change" in text


@pytest.mark.asyncio
async def test_app_open_sends_a_target(monkeypatch):
    captured: dict = {}

    async def fake_request(method, path, *, body=None):
        captured.update({"method": method, "path": path, "body": body})
        return 200, {"target": body["target"]}

    monkeypatch.setattr(app_tools, "_app_request", fake_request)
    text, _ = await app_tools._open({"tab": "dashboard", "dashboardId": "main"}, None)
    assert captured["method"] == "POST"
    assert captured["path"] == "/navigate"
    assert captured["body"]["target"] == {"tab": "dashboard", "dashboardId": "main"}
    assert "dashboard" in text


def test_app_tools_are_on_the_standard_agent():
    from harness.agents import ECLIPSE_AGENT
    from harness.sdk.tools import SDK_TOOLS

    for name in ("sdk_app_get", "sdk_app_nav_update", "sdk_app_nav_reset", "sdk_app_open"):
        assert name in SDK_TOOLS
        assert name in ECLIPSE_AGENT.tools


def _context() -> SimpleNamespace:
    dashboards = SimpleNamespace(active=lambda: {"dashboard": {"dashboardId": "main"}})
    return SimpleNamespace(sdk_service=SimpleNamespace(dashboards=dashboards))


@pytest.mark.asyncio
async def test_template_list_uses_the_loopback_route(monkeypatch):
    async def fake_request(method, path, *, body=None):
        assert (method, path) == ("GET", "/templates")
        return 200, {"templates": [{"id": "rates-desk", "name": "Rates Desk"}]}

    monkeypatch.setattr(dashboard_template_tools, "_dashboard_request", fake_request)
    text, data = await dashboard_template_tools._templates({}, _context())
    assert "rates-desk" in text
    assert data["templates"][0]["id"] == "rates-desk"


@pytest.mark.asyncio
async def test_apply_template_defaults_to_the_active_dashboard(monkeypatch):
    captured: dict = {}

    async def fake_request(method, path, *, body=None):
        captured.update({"method": method, "path": path, "body": body})
        return 200, {"dashboard": {"title": "Main", "revision": 4}}

    monkeypatch.setattr(dashboard_template_tools, "_dashboard_request", fake_request)
    text, _ = await dashboard_template_tools._apply_template(
        {"templateId": "rates-desk", "market": "US"}, _context(),
    )
    assert captured["method"] == "POST"
    assert captured["path"] == "/main/template"
    assert captured["body"]["templateId"] == "rates-desk"
    assert captured["body"]["market"] == "US"
    assert "Rates Desk" not in text  # title from the payload, not the template name
    assert "Main" in text


@pytest.mark.asyncio
async def test_reset_posts_to_the_dashboard_reset_route(monkeypatch):
    captured: dict = {}

    async def fake_request(method, path, *, body=None):
        captured.update({"method": method, "path": path, "body": body})
        return 200, {"dashboard": {"title": "Main", "revision": 5}}

    monkeypatch.setattr(dashboard_template_tools, "_dashboard_request", fake_request)
    text, _ = await dashboard_template_tools._reset({}, _context())
    assert captured["method"] == "POST"
    assert captured["path"] == "/main/reset"
    assert "Reset Main" in text


def test_template_tools_are_on_the_standard_agent():
    from harness.agents import ECLIPSE_AGENT
    from harness.sdk.tools import SDK_TOOLS

    for name in (
        "sdk_dashboard_templates",
        "sdk_dashboard_apply_template",
        "sdk_dashboard_reset",
    ):
        assert name in SDK_TOOLS
        assert name in ECLIPSE_AGENT.tools
