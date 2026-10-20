"""The external capability lane proposes operator-gated broker/API/MCP adapters.

It never installs, enables or stores a credential value; the acquisition handler
reuses the MCP approval store and writes a disabled config at most.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

import pytest

from harness.capabilities.external import classify_external, propose_external
from harness.capabilities.tools import capability_external
from harness.mcp.approvals import ApprovalStore
from harness.mcp.config import load_mcp_configs
from harness.mcp.install_tools import approval_digest
from harness.mcp.verify import VerifyMixin
from harness.persistence import AgentMemoryStore
from harness.recovery.acquire_handlers import build_acquisition_handlers
from harness.recovery.acquisition import execute_step


class _FakeMCP:
    def __init__(self, present: dict[str, bool]) -> None:
        self._present = present

    async def secret_presence(self, names: Any) -> dict[str, bool]:
        return {str(name): bool(self._present.get(str(name))) for name in names}


@pytest.fixture()
def service(tmp_path, monkeypatch):
    monkeypatch.setenv("HARNESS_MCP_CONFIG", str(tmp_path / "mcp-servers.json"))
    memory = AgentMemoryStore(str(tmp_path / "agent-memory.db"))
    svc = SimpleNamespace(
        approvals=ApprovalStore(memory),
        mcp=_FakeMCP({"tavily_api_key": True}),
        store=memory,
    )
    yield svc, memory
    memory.close()


def test_kind_classification_is_deterministic():
    assert classify_external("connect my broker and read positions") == "broker"
    assert classify_external("add an mcp server") == "mcp"
    assert classify_external("pull from a rest endpoint") == "api"
    assert classify_external("anything", "broker") == "broker"


def test_a_preset_proposal_names_credentials_and_never_enables():
    proposal = propose_external(
        "read my latest filing", integration_id="sec_filings",
        secret_present=lambda name: None,
    )
    assert proposal.surface == "mcp_preset"
    assert proposal.adapter_id == "sec_filings"
    assert proposal.installable is True
    assert proposal.activation == "operator"
    assert proposal.enabled is False
    assert proposal.approval_kind == "mcp_install"
    assert proposal.approval_digest == approval_digest("mcp_install", "sec_filings")
    assert proposal.next_action == "mcp_install"
    steps = proposal.acquisition.steps
    assert [step.action for step in steps] == ["install", "enable"]
    assert steps[0].surface == "mcp" and steps[0].requires_approval is True
    assert steps[1].surface == "operator" and steps[1].requires_approval is True


def test_a_credentialed_preset_reports_presence_by_name_only():
    proposal = propose_external(
        "search the web", integration_id="web_search",
        secret_present=lambda name: name == "tavily_api_key",
    )
    credential = proposal.credentials[0]
    assert credential.name == "tavily_api_key"
    assert credential.present is True
    assert proposal.activation_ready is True
    serialized = str(proposal.to_dict())
    assert "super-secret-value" not in serialized


def test_a_missing_credential_is_named_not_hidden():
    proposal = propose_external(
        "search the web", integration_id="web_search",
        secret_present=lambda name: False,
    )
    assert proposal.activation_ready is False
    assert any("tavily_api_key" in item for item in proposal.missing)


def test_a_plugin_folder_is_an_operator_install():
    proposal = propose_external(
        "connect my broker", plugin_path=r"C:\adapters\my_broker",
        credential_names=["broker_api_key", "broker_api_secret"],
    )
    assert proposal.surface == "plugin"
    assert proposal.adapter_id == "my_broker"
    assert proposal.installable is True
    assert proposal.enabled is False
    assert proposal.approval_kind == "plugin_install"
    assert [item.name for item in proposal.credentials] == [
        "broker_api_key", "broker_api_secret",
    ]
    assert all(item.present is None for item in proposal.credentials)
    assert proposal.acquisition.steps[0].surface == "plugin"
    assert proposal.acquisition.steps[1].surface == "operator"


def test_an_unnamed_external_need_is_an_honest_gap():
    proposal = propose_external("connect my broker")
    assert proposal.surface == "operator"
    assert proposal.installable is False
    assert proposal.activation == "operator"
    assert any("plugin folder" in item for item in proposal.missing)


def test_an_unknown_preset_is_refused_without_guessing():
    proposal = propose_external("connect it", integration_id="not_a_preset")
    assert proposal.surface == "operator"
    assert proposal.installable is False
    assert any("unknown MCP integration" in item for item in proposal.missing)


def test_embedded_url_credentials_are_refused():
    proposal = propose_external(
        "connect the mcp endpoint",
        server_url="https://user:secret@example.com/mcp",
    )
    assert proposal.surface == "mcp_server"
    assert proposal.installable is False
    assert any("must not be embedded" in item for item in proposal.missing)


def test_credential_values_are_refused_not_named():
    with pytest.raises(ValueError):
        propose_external(
            "connect my broker", plugin_path=r"C:\adapters\my_broker",
            credential_names=["sk-" + "a" * 30],
        )
    _text, data = asyncio.run(capability_external({
        "need": "connect my broker",
        "pluginPath": r"C:\adapters\my_broker",
        "credentialNames": ["sk-" + "a" * 30],
    }, SimpleNamespace()))
    assert data["status"] == "refused"
    assert data["code"] == "CREDENTIAL_VALUE"


def test_secret_presence_never_returns_a_value():
    class _Mixin(VerifyMixin):
        pass

    mixin = _Mixin()
    mixin._secret_resolver = lambda name: "a-value" if name == "present_key" else None
    result = asyncio.run(mixin.secret_presence(["present_key", "missing_key", "present_key"]))
    assert result == {"present_key": True, "missing_key": False}
    assert "a-value" not in str(result)


def test_the_tool_proposes_and_touches_nothing():
    ctx = SimpleNamespace(mcp_manager=_FakeMCP({"tavily_api_key": True}))
    text, data = asyncio.run(capability_external({
        "need": "search the web", "integrationId": "web_search",
    }, ctx))
    assert data["status"] == "proposed"
    assert data["surface"] == "mcp_preset"
    assert data["enabled"] is False
    assert data["credentials"][0]["present"] is True
    assert "Nothing was installed or enabled" in text


def test_the_install_gate_requires_credentials_then_a_single_use_approval(service):
    svc, _memory = service
    proposal = propose_external(
        "search the web", integration_id="web_search",
        secret_present=lambda name: True,
    )
    handlers = build_acquisition_handlers(
        svc, None, None, facts={"integrationId": "web_search"},
    )
    first = execute_step(proposal.acquisition, 0, handlers=handlers, approved=True)
    assert first["status"] == "executed"
    assert first["result"]["status"] == "approval_required"
    pending = [row for row in svc.approvals.list(status="pending") if row["kind"] == "mcp_install"]
    assert len(pending) == 1
    assert pending[0]["argsDigest"] == approval_digest("mcp_install", "web_search")
    assert load_mcp_configs()[0] == []  # nothing was installed

    svc.approvals.decide(pending[0]["id"], approve=True, decided_by="test")
    second = execute_step(proposal.acquisition, 0, handlers=handlers, approved=True)
    assert second["status"] == "executed"
    assert second["result"]["status"] == "installed"
    assert second["result"]["enabled"] is False
    configs, _ = load_mcp_configs()
    entry = next(item for item in configs if item.id == "web_search")
    assert entry.enabled is False
    assert entry.selected_tools == []

    third = execute_step(proposal.acquisition, 0, handlers=handlers, approved=True)
    assert third["result"]["status"] == "approval_required"  # single-use


def test_the_install_gate_does_not_install_without_credentials(service):
    svc, _memory = service
    svc.mcp = _FakeMCP({})
    proposal = propose_external(
        "search the web", integration_id="web_search",
        secret_present=lambda name: False,
    )
    handlers = build_acquisition_handlers(
        svc, None, None, facts={"integrationId": "web_search"},
    )
    outcome = execute_step(proposal.acquisition, 0, handlers=handlers, approved=True)
    result = outcome["result"]
    assert result["status"] == "approval_required"
    assert result["reason"] == "credentials_required"
    assert any("tavily_api_key" in item for item in result["missing"])
    assert load_mcp_configs()[0] == []
    assert svc.approvals.list(status="pending") == []


def test_the_enable_step_never_enables_mcp(service):
    svc, _memory = service
    proposal = propose_external(
        "search the web", integration_id="web_search",
        secret_present=lambda name: True,
    )
    handlers = build_acquisition_handlers(
        svc, None, None, facts={"integrationId": "web_search"},
    )
    outcome = execute_step(proposal.acquisition, 1, handlers=handlers, approved=True)
    assert outcome["status"] == "executed"
    assert outcome["result"]["status"] == "approval_required"
    assert "never enables" in outcome["result"]["next"]
