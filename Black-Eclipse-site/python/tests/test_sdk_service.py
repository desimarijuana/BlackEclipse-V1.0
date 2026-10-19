"""Eclipse SDK service tests — widgets, pages, funds, locks, enforcement."""

from __future__ import annotations

import pytest

from harness.persistence import AgentMemoryStore
from harness.portfolio.service import PortfolioService
from harness.portfolio.store import PortfolioStore
from harness.sdk.locks import LockError, LockService, unlock_token_var
from harness.sdk.model import (
    SdkAddStockInput,
    SdkCreateFundInput,
    SdkCreateLockInput,
    SdkCreatePageInput,
    SdkPageWidget,
    SdkWidgetInput,
)
from harness.sdk.service import EclipseSdk
from harness.sdk.store import SdkStore
from harness.ui.catalog import UiCatalog
from harness.ui.model import AddWidgetInput, WidgetRefInput
from harness.ui.service import UiError, UiService
from harness.ui.store import UiStore


@pytest.fixture()
def memory(tmp_path):
    store = AgentMemoryStore(str(tmp_path / "agent-memory.db"))
    yield store
    store.close()


@pytest.fixture()
def sdk(memory):
    store = SdkStore(memory)
    locks = LockService(store)
    ui = UiService(UiStore(memory), UiCatalog(), locks=locks)
    portfolio = PortfolioService(PortfolioStore(memory), locks=locks)
    yield EclipseSdk(store, ui, portfolio, locks)


def _widget(**overrides) -> SdkWidgetInput:
    data = {
        "slug": "watch-metric",
        "label": "Watch metric",
        "primitive": "metric-card",
        "source": "portfolio:pf_demo:summary.totalValue",
    }
    data.update(overrides)
    return SdkWidgetInput(**data)


def test_create_widget_registers_catalog_component(sdk):
    record = sdk.create_widget(_widget())
    assert record["componentId"] == "sdk.watch-metric"
    spec = sdk._ui.inspect_component("sdk.watch-metric")
    assert spec.owner.value == "user"
    assert spec.default_config["source"] == "portfolio:pf_demo:summary.totalValue"
    assert sdk.list_widgets()[0]["label"] == "Watch metric"


def test_create_page_composes_core_and_user_widgets(sdk):
    sdk.create_widget(_widget())
    result = sdk.create_page(SdkCreatePageInput(
        title="Desk",
        path="/desk/rates",
        widgets=[
            SdkPageWidget(component_id="metric-card"),
            SdkPageWidget(component_id="sdk.watch-metric", config={"label": "NAV"}),
        ],
    ))
    blueprint = result["blueprint"]
    assert blueprint["title"] == "Desk"
    assert blueprint["path"] == "/desk/rates"
    widgets = [w for s in blueprint["layout"]["sections"] for c in s["columns"] for w in c["widgets"]]
    assert [w["widgetId"] for w in widgets] == ["metric-card", "sdk.watch-metric"]
    assert result["verification"]["renderable"] is True


def test_create_page_rejects_unknown_component_before_writing(sdk):
    with pytest.raises(Exception) as exc:
        sdk.create_page(SdkCreatePageInput(
            title="Bad", widgets=[SdkPageWidget(component_id="does-not-exist")],
        ))
    assert "not found" in str(exc.value).lower() or "unknown" in str(exc.value).lower()
    assert sdk.list_pages()["total"] == 0


def test_create_fund_and_add_stock(sdk):
    fund = sdk.create_fund(SdkCreateFundInput(name="Growth Fund", goal="Long-term growth"))
    assert fund["kind"] == "fund"
    assert fund["metadata"]["goal"] == "Long-term growth"
    result = sdk.add_stock(fund["id"], SdkAddStockInput(symbol="aapl", quantity=10, price=180))
    assert result["status"] == "SUCCESS"
    assert result["transaction"]["symbol"] == "AAPL"
    from decimal import Decimal

    assert Decimal(result["position"]["quantity"]) == Decimal("10")


def test_relocking_a_locked_resource_requires_unlock(sdk):
    sdk.create_lock(SdkCreateLockInput(
        resource_type="design", resource_id="global", passphrase="first-pass",
    ))
    with pytest.raises(LockError):
        sdk.create_lock(SdkCreateLockInput(
            resource_type="design", resource_id="global", passphrase="second-pass",
        ))


def test_design_lock_requires_passphrase(sdk):
    lock = sdk.create_lock(SdkCreateLockInput(
        resource_type="design", resource_id="global", passphrase="correct-horse", hint="brand lock",
    ))
    with pytest.raises(LockError):
        sdk.locks.assert_allowed("design", "global")
    with pytest.raises(LockError):
        sdk.unlock(lock.id, "wrong-pass")
    unlocked = sdk.unlock(lock.id, "correct-horse")
    assert unlocked["token"]
    assert sdk.locks.assert_allowed("design", "global", token=unlocked["token"]) is not None


def test_page_lock_blocks_widget_mutation_and_delete(sdk):
    page = sdk.create_page(SdkCreatePageInput(title="Locked desk")).get("blueprint")
    lock = sdk.create_lock(SdkCreateLockInput(
        resource_type="page", resource_id=page["id"], passphrase="let-me-in",
    ))
    with pytest.raises(UiError) as exc:
        sdk._ui.add_widget(__import__("harness.ui.model", fromlist=["AddWidgetInput"]).AddWidgetInput(
            blueprint_id=page["id"], component_id="metric-card",
        ))
    assert exc.value.code == "UI_LOCKED"
    with pytest.raises(Exception) as delete_exc:
        sdk.delete_page(page["id"])
    assert "locked" in str(delete_exc.value).lower()

    unlocked = sdk.unlock(lock.id, "let-me-in")
    handle = unlock_token_var.set(unlocked["token"])
    try:
        sdk._ui.add_widget(__import__("harness.ui.model", fromlist=["AddWidgetInput"]).AddWidgetInput(
            blueprint_id=page["id"], component_id="metric-card",
        ))
    finally:
        unlock_token_var.reset(handle)


def test_widget_lock_blocks_removal(sdk):
    page = sdk.create_page(SdkCreatePageInput(
        title="Desk", widgets=[SdkPageWidget(component_id="metric-card")],
    ))["blueprint"]
    instance_id = next(
        w["id"] for s in page["layout"]["sections"] for c in s["columns"] for w in c["widgets"]
    )
    lock = sdk.create_lock(SdkCreateLockInput(
        resource_type="widget", resource_id=f'{page["id"]}:{instance_id}', passphrase="pin-code",
    ))
    with pytest.raises(UiError) as exc:
        sdk._ui.remove_widget(__import__("harness.ui.model", fromlist=["WidgetRefInput"]).WidgetRefInput(
            blueprint_id=page["id"], instance_id=instance_id,
        ))
    assert exc.value.code == "UI_LOCKED"

    unlocked = sdk.unlock(lock.id, "pin-code")
    handle = unlock_token_var.set(unlocked["token"])
    try:
        sdk._ui.remove_widget(__import__("harness.ui.model", fromlist=["WidgetRefInput"]).WidgetRefInput(
            blueprint_id=page["id"], instance_id=instance_id,
        ))
    finally:
        unlock_token_var.reset(handle)


def test_portfolio_lock_blocks_stock_then_allows_after_unlock(sdk):
    fund = sdk.create_fund(SdkCreateFundInput(name="Locked Fund"))
    lock = sdk.create_lock(SdkCreateLockInput(
        resource_type="portfolio", resource_id=fund["id"], passphrase="trade-lock",
    ))
    with pytest.raises(LockError):
        sdk.add_stock(fund["id"], SdkAddStockInput(symbol="MSFT", quantity=1, price=400))

    unlocked = sdk.unlock(lock.id, "trade-lock")
    handle = unlock_token_var.set(unlocked["token"])
    try:
        result = sdk.add_stock(fund["id"], SdkAddStockInput(symbol="MSFT", quantity=1, price=400))
        assert result["status"] == "SUCCESS"
    finally:
        unlock_token_var.reset(handle)


def test_list_pages_hides_dashboard_mirrors(sdk):
    sdk.create_page(SdkCreatePageInput(title="User page", path="/user-page"))
    sdk.create_page(SdkCreatePageInput(title="Main", path="/dashboard/dash-test"))
    titles = {page["title"] for page in sdk.list_pages()["blueprints"]}
    assert "User page" in titles
    assert "Main" not in titles


def test_capabilities_reports_every_surface(sdk):
    capabilities = sdk.capabilities()
    assert capabilities["widgets"]["canCreate"] is True
    assert capabilities["pages"]["canCreate"] is True
    assert capabilities["portfolio"]["canCreateFund"] is True
    assert capabilities["locks"]["canCreate"] is True
    assert "metric-card" in capabilities["widgets"]["primitives"]
