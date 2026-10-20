"""Append-only SDK activity: store, service mutations, tools and boundaries."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from harness.persistence import AgentMemoryStore
from harness.sdk.locks import LockService
from harness.sdk.model import (
    SdkAuditInput,
    SdkCreateLockInput,
    SdkCreatePageInput,
    SdkDashboardAddWidgetInput,
    SdkWidgetInput,
)
from harness.sdk.service import EclipseSdk
from harness.sdk.store import SdkStore
from harness.ui.catalog import UiCatalog
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


def test_audit_is_append_only_and_filterable(sdk):
    sdk.record_audit(SdkAuditInput(
        action="test.one", summary="First", resource_type="page", resource_id="p1",
        detail={"ok": True},
    ))
    sdk.record_audit(SdkAuditInput(
        action="test.two", summary="Second", resource_type="dashboard", resource_id="d1",
    ))

    listed = sdk.list_audit()
    assert [entry["action"] for entry in listed["entries"]] == ["test.two", "test.one"]
    assert listed["total"] == 2
    assert listed["entries"][1]["detail"] == {"ok": True}

    assert [entry["action"] for entry in sdk.list_audit(action="test.one")["entries"]] == ["test.one"]
    assert [entry["action"] for entry in sdk.list_audit(resource_type="dashboard")["entries"]] == ["test.two"]


def test_mutations_are_audited_without_secrets(sdk):
    widget = sdk.create_widget(SdkWidgetInput(
        slug="audit-metric", label="Audit metric", primitive="metric-card",
        source="portfolio:pf_audit:summary.totalValue",
    ))
    page = sdk.create_page(SdkCreatePageInput(title="Audit page", path="/audit"))["blueprint"]
    _mirror(sdk)
    sdk.dashboards.add_widget(None, SdkDashboardAddWidgetInput(component_id=widget["componentId"]))
    lock = sdk.create_lock(SdkCreateLockInput(
        resource_type="page", resource_id=page["id"], passphrase="audit-pass", hint="secret clue",
    ))

    actions = [entry["action"] for entry in sdk.list_audit(limit=100)["entries"]]
    assert "widget.create" in actions
    assert "page.create" in actions
    assert "dashboard.add_widget" in actions
    assert "lock.create" in actions

    serialized = json.dumps(sdk.list_audit(limit=100)["entries"])
    assert "audit-pass" not in serialized
    assert "secret clue" not in serialized
    assert "passphraseHash" not in serialized
    assert lock.resource_id == page["id"]


def test_audit_capability_count_and_tool_registration(sdk):
    sdk.record_audit(SdkAuditInput(action="test.count", summary="Count"))
    assert sdk.capabilities()["audit"]["count"] == 1

    from harness.agents import ECLIPSE_AGENT
    from harness.sdk.tools import SDK_TOOLS

    assert "sdk_audit_list" in SDK_TOOLS
    assert "sdk_audit_list" in ECLIPSE_AGENT.tools


@pytest.mark.asyncio
async def test_audit_tool_reports_entries(sdk):
    from harness.sdk import tools

    sdk.record_audit(SdkAuditInput(action="test.tool", summary="Visible in the tool"))
    text, data = await tools._audit_list({"limit": 10}, SimpleNamespace(sdk_service=sdk))
    assert "test.tool" in text
    assert data["entries"][0]["summary"] == "Visible in the tool"
