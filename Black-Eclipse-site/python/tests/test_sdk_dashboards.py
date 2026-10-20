"""Command Center dashboard control through the Eclipse SDK."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from harness.persistence import AgentMemoryStore
from harness.sdk.locks import LockError, LockService, unlock_token_var
from harness.sdk.model import (
    SdkCreateLockInput,
    SdkCreatePageInput,
    SdkDashboardAddWidgetInput,
    SdkDashboardSetColumnsInput,
    SdkDashboardSetZonesInput,
)
from harness.sdk.service import EclipseSdk
from harness.sdk.store import SdkStore
from harness.ui.catalog import UiCatalog
from harness.ui.model import ListBlueprintsQuery
from harness.ui.service import UiService
from harness.ui.store import UiStore


@pytest.fixture()
def sdk(tmp_path):
    memory = AgentMemoryStore(str(tmp_path / "agent-memory.db"))
    store = SdkStore(memory)
    locks = LockService(store)
    ui = UiService(UiStore(memory), UiCatalog(), locks=locks)
    try:
        yield EclipseSdk(store, ui, None, locks)
    finally:
        memory.close()


def _mirror(sdk: EclipseSdk, dashboard_id: str = "main") -> dict:
    return sdk.create_page(SdkCreatePageInput(
        title="Main",
        path=f"/dashboard/{dashboard_id}",
    ))["blueprint"]


def _instance_ids(blueprint: dict) -> list[str]:
    return [
        widget["id"]
        for section in blueprint["layout"]["sections"]
        for column in section["columns"]
        for widget in column["widgets"]
    ]


def test_list_reads_mirrors_but_page_list_stays_clean(sdk):
    _mirror(sdk, "dash-a")
    _mirror(sdk, "dash-b")

    listed = sdk.dashboards.list()
    assert {d["dashboardId"] for d in listed["dashboards"]} == {"dash-a", "dash-b"}
    assert sdk.list_pages()["total"] == 0

    all_pages = sdk._ui.list_blueprints(ListBlueprintsQuery(include_dashboard_mirrors=True))
    assert all_pages["total"] == 2


def test_active_dashboard_uses_marker_then_title(sdk):
    _mirror(sdk, "main")
    assert sdk.dashboards.active()["dashboard"]["dashboardId"] == "main"

    sdk.dashboards.set_active("main")
    assert sdk.dashboards.active()["dashboard"]["dashboardId"] == "main"


def test_add_clock_lands_in_the_main_board(sdk):
    _mirror(sdk)
    result = sdk.dashboards.add_widget(
        None,
        SdkDashboardAddWidgetInput(
            component_id="clock",
            config={"timezone": "UTC", "format": "24h", "showSeconds": True, "showDate": True},
        ),
    )
    assert result["dashboard"]["componentIds"] == ["clock"]
    assert result["revision"] == 2
    section = result["layout"]["sections"][0]
    assert section["zone"] == "main"
    assert _instance_ids(result["blueprint"])


def test_columns_zones_and_history_restore(sdk):
    _mirror(sdk)
    added = sdk.dashboards.add_widget(
        "main", SdkDashboardAddWidgetInput(component_id="clock"),
    )
    section_id = added["layout"]["sections"][0]["id"]

    columns = sdk.dashboards.set_columns(
        "main", SdkDashboardSetColumnsInput(section_id=section_id, count=3),
    )
    assert len(columns["layout"]["sections"][0]["columns"]) == 3

    zoned = sdk.dashboards.set_zones(
        "main", SdkDashboardSetZonesInput(hidden_zones=["left"], zone_widths={"right": 320}),
    )
    assert zoned["layout"]["hiddenZones"] == ["left"]
    assert zoned["layout"]["zoneWidths"] == {"right": 320}

    restored = sdk.dashboards.restore("main", 1)
    assert restored["revision"] == 5
    assert restored["dashboard"]["componentIds"] == []


def test_sdk_dashboard_tools_are_on_the_standard_agent():
    from harness.agents import ECLIPSE_AGENT
    from harness.sdk.tools import SDK_TOOLS

    assert "sdk_dashboard_add_widget" in SDK_TOOLS
    assert set(SDK_TOOLS) <= set(ECLIPSE_AGENT.tools)


def test_sdk_page_tools_are_on_the_standard_agent():
    from harness.agents import ECLIPSE_AGENT
    from harness.sdk.tools import SDK_TOOLS

    for name in (
        "sdk_page_list", "sdk_page_create", "sdk_page_add_widget",
        "sdk_page_update", "sdk_page_delete",
    ):
        assert name in SDK_TOOLS
        assert name in ECLIPSE_AGENT.tools


def test_add_page_widget_uses_the_sdk_contract(sdk):
    from harness.sdk.model import SdkPageWidget

    page = sdk.create_page(SdkCreatePageInput(title="Rates Desk", path="/rates-desk"))["blueprint"]
    result = sdk.add_page_widget(page["id"], SdkPageWidget(component_id="clock"))
    assert result["blueprint"]["path"] == "/rates-desk"
    assert result["verification"]["renderable"] is True
    assert "clock" in result["verification"]["instances"][0]["componentId"]


@pytest.mark.asyncio
async def test_page_update_and_delete_tools(sdk):
    from harness.sdk import page_tools

    page = sdk.create_page(SdkCreatePageInput(title="Old title", path="/old"))["blueprint"]
    ctx = SimpleNamespace(sdk_service=sdk)

    text, data = await page_tools._page_update(
        {"blueprintId": page["id"], "title": "New title", "tags": ["rates", "macro"]},
        ctx,
    )
    assert "New title" in text
    assert data["blueprint"]["title"] == "New title"
    assert data["blueprint"]["tags"] == ["rates", "macro"]

    text, data = await page_tools._page_delete({"blueprintId": page["id"]}, ctx)
    assert data["removed"] is True
    assert "Deleted" in text
    assert sdk.list_pages()["total"] == 0


def test_sdk_theme_tools_are_on_the_standard_agent():
    from harness.agents import ECLIPSE_AGENT
    from harness.sdk.tools import SDK_TOOLS

    for name in (
        "sdk_theme_get", "sdk_theme_create", "sdk_theme_apply",
        "sdk_theme_apply_preset", "sdk_theme_list_presets",
        "sdk_theme_save_preset", "sdk_theme_delete_preset", "sdk_theme_reset",
    ):
        assert name in SDK_TOOLS
        assert name in ECLIPSE_AGENT.tools


@pytest.mark.asyncio
async def test_theme_create_tool_calls_the_sdk_route(monkeypatch):
    from harness.sdk import theme_tools

    captured: dict = {}

    async def fake_request(method, path, *, body=None):
        captured.update({"method": method, "path": path, "body": body})
        return 200, {"theme": {"appName": "Neon", "scheme": "dark"}}

    monkeypatch.setattr(theme_tools, "_theme_request", fake_request)
    text, data = await theme_tools._create({"spec": {"brand": "#ff2bd6"}}, None)
    assert captured["method"] == "POST"
    assert captured["path"] == ""
    assert captured["body"]["spec"]["brand"] == "#ff2bd6"
    assert "Neon" in text
    assert data["theme"]["appName"] == "Neon"


def test_dashboard_lock_refuses_mutation_until_unlocked(sdk):
    _mirror(sdk)
    lock = sdk.create_lock(SdkCreateLockInput(
        resource_type="dashboard", resource_id="main", passphrase="desk-pass",
    ))
    with pytest.raises(LockError):
        sdk.dashboards.add_widget("main", SdkDashboardAddWidgetInput(component_id="clock"))

    unlocked = sdk.unlock(lock.id, "desk-pass")
    handle = unlock_token_var.set(unlocked["token"])
    try:
        result = sdk.dashboards.add_widget("main", SdkDashboardAddWidgetInput(component_id="clock"))
        assert result["dashboard"]["componentIds"] == ["clock"]
    finally:
        unlock_token_var.reset(handle)
