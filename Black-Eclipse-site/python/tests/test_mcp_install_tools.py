"""MCP integration catalog + install tool (agent surface).

Offline: config writes go to a temp HARNESS_MCP_CONFIG and approvals to a temp
eclipse-memory DB. Nothing spawns a server — install is a DISABLED config write
by design, and these tests pin exactly that.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from harness.eclipse_memory import EclipseMemoryService
from harness.mcp.config import load_mcp_configs
from harness.mcp.install_ops import install_integration, list_catalog
from harness.mcp.install_tools import make_mcp_install_authorizer, mcp_install_handler


@pytest.fixture()
def service(tmp_path, monkeypatch):
    monkeypatch.setenv("ECLIPSE_MEMORY_DB_PATH", str(tmp_path / "eclipse-memory.db"))
    monkeypatch.setenv("HARNESS_MCP_CONFIG", str(tmp_path / "mcp-servers.json"))
    svc = EclipseMemoryService()
    yield svc
    svc.close()


def _catalog_id() -> str:
    catalog = list_catalog()
    assert catalog, "the preset catalog must not be empty"
    return catalog[0]["id"]


def test_catalog_rows_are_secret_free():
    for row in list_catalog():
        assert row["id"] and row["label"] and row["purpose"]
        assert "secretRef" not in row and "command" not in row and "args" not in row


def test_install_writes_a_disabled_nothing_selected_config():
    integration_id = _catalog_id()
    result = install_integration(integration_id)
    assert result["success"] is True
    configs, _ = load_mcp_configs()
    entry = next(c for c in configs if c.id == integration_id)
    assert entry.enabled is False
    assert not entry.selected_tools  # install is not activation


def test_install_is_create_if_absent():
    integration_id = _catalog_id()
    install_integration(integration_id)
    again = install_integration(integration_id)
    assert again["success"] is True and again.get("alreadyInstalled") is True


def test_unknown_integration_is_refused():
    result = install_integration("not_a_real_server")
    assert result["success"] is False
    assert "unknown" in result["reason"]


async def test_handler_reports_install_is_not_activation(service):
    integration_id = _catalog_id()
    ctx = SimpleNamespace()
    text, data = await mcp_install_handler({"integration_id": integration_id}, ctx)
    assert data["success"] is True
    assert data["enabled"] is False and data["selectedTools"] == []
    assert "not activation" in text or "DISABLED" in text


class _Ctx:
    def __init__(self, approvals):
        self.approvals = approvals
        self.run_id = "run-1"
        self.emitter = None
        self.pause_for_approval = False


async def test_mcp_install_requires_a_single_use_approval(service):
    from harness.mcp.approvals import ApprovalStore

    approvals = ApprovalStore(service.store)
    authorize = make_mcp_install_authorizer()
    ctx = _Ctx(approvals)
    integration_id = _catalog_id()
    tool = SimpleNamespace(name="mcp_install")
    args = {"integration_id": integration_id}

    assert await authorize(tool, args, ctx) is False
    pending = [a for a in approvals.list(status="pending") if a["kind"] == "mcp_install"]
    assert len(pending) == 1

    approvals.decide(pending[0]["id"], approve=True, decided_by="test")
    assert await authorize(tool, args, ctx) is True
    assert await authorize(tool, args, ctx) is False  # single-use


async def test_mcp_install_of_an_unknown_id_never_creates_an_approval(service):
    from harness.mcp.approvals import ApprovalStore

    approvals = ApprovalStore(service.store)
    authorize = make_mcp_install_authorizer()
    tool = SimpleNamespace(name="mcp_install")
    assert await authorize(tool, {"integration_id": "nope"}, _Ctx(approvals)) is False
    assert [a for a in approvals.list() if a["kind"] == "mcp_install"] == []
