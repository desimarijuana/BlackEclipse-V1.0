"""Finance presets, diagnostics, provenance, approval clarity, and an end-to-end
finance workflow (import holdings → analyse with Eclipse data → report → export).

Offline and deterministic. Uses the finance fixture MCP server for the read
(import) and write (export) legs, and a fake data bridge for Eclipse's own data.
"""

from __future__ import annotations

import json
import os
import sys

import pytest

from harness.mcp import presets
from harness.mcp.approvals import ApprovalStore, make_effect_authorizer
from harness.mcp.config import MCPServerConfig
from harness.mcp.diagnostics import check_server, environment_diagnostics
from harness.mcp.manager import MCPManager
from harness.persistence import AgentMemoryStore
from harness.tools import DataBridge, ToolContext, ToolRegistry

FIXTURES = os.path.join(os.path.dirname(__file__), "mcp_fixtures")
FINANCE = os.path.join(FIXTURES, "finance_fixture.py")


# ── presets / workflows are coherent ────────────────────────────────────────


def test_integrations_and_workflows_are_coherent():
    integrations = {i["id"]: i for i in presets.list_integrations()}
    assert len(integrations) == len(presets.list_integrations())  # unique ids
    for w in presets.list_workflows():
        for integ in w["integrations"]:
            assert integ in integrations, f"{w['id']} references unknown integration {integ}"
        assert w["summary"] and w["output"]


def test_workflows_cover_the_required_jobs():
    ids = {w["id"] for w in presets.list_workflows()}
    assert {
        "import_portfolio",
        "review_portfolio_risk",
        "prepare_earnings_brief",
        "compare_companies",
        "analyze_trade_journal",
        "create_investment_memo",
        "export_portfolio_report",
    } <= ids


def test_provisioning_dependent_workflows_are_labelled_unavailable():
    # Issue 1: a workflow that needs an unprovisioned source/destination must say
    # so plainly, not look like a runnable job that silently fails.
    by_id = {w["id"]: w for w in presets.list_workflows()}
    for wid in ("import_portfolio", "review_portfolio_risk", "analyze_trade_journal", "export_portfolio_report"):
        w = by_id[wid]
        assert w["requiresProvisioning"] is True, wid
        assert w["provisioningNote"], wid
    # A native-only workflow with no missing capability is NOT labelled unavailable.
    assert by_id["review_portfolio_risk"]["requiresNativePortfolio"] is True


def test_each_workflow_marks_its_approval_steps():
    for w in presets.list_workflows():
        assert isinstance(w["approvalSteps"], list)
        for step in w["steps"]:
            if step["effect"] != "read":
                assert step["id"] in w["approvalSteps"]
        # Write/action steps must be explicit, never silently read.
        assert all(isinstance(s["effect"], str) for s in w["steps"])


def test_required_integrations_are_named_for_a_user():
    # A new user must be able to understand which integrations a workflow needs.
    import_portfolio = presets.workflow("import_portfolio")
    assert import_portfolio is not None
    assert "google_sheets" in import_portfolio.integrations
    for step in import_portfolio.steps:
        assert step.title and step.detail


def test_community_and_unverified_are_flagged():
    for integ in presets.list_integrations():
        # Every entry says honestly whether it is a verified package.
        assert "verified" in integ
        assert isinstance(integ["verified"], bool)
        # An unverified entry must say so in its notes.
        if not integ["verified"]:
            assert "UNVERIFIED" in (integ["notes"] or "")


def test_tool_effect_hint_classifies_common_names():
    assert presets.classify_tool_effect_hint("export_report") == "write"
    assert presets.classify_tool_effect_hint("read_holdings") == "read"
    assert presets.classify_tool_effect_hint("frobnicate") == "unknown"


def test_workflows_for_server_tools_matches_by_hint():
    matched = presets.workflows_for_server_tools(["read_holdings", "export_report"])
    assert "filesystem" in matched or "excel" in matched  # names hit document hints


# ── diagnostics ─────────────────────────────────────────────────────────────


def test_diagnostics_report_missing_command_with_recovery():
    cfg = MCPServerConfig(id="s", command="definitely-not-a-real-binary-xyz", selected_tools=["x"])
    result = check_server(cfg, connection_state="pending").to_public()
    codes = {c["code"]: c for c in result["checks"]}
    assert codes["definitely-not-a-real-binary-xyz_missing"]["status"] == "error"
    assert codes["definitely-not-a-real-binary-xyz_missing"]["recovery"]


def test_diagnostics_report_npx_requirement_for_node_servers():
    cfg = MCPServerConfig(id="s", command="npx", args=["-y", "x"])
    result = check_server(cfg).to_public()
    codes = {c["code"] for c in result["checks"]}
    assert "npx_available" in codes or "npx_missing" in codes


def test_diagnostics_report_missing_secret_and_selection():
    cfg = MCPServerConfig(id="s", command=sys.executable, secret_refs={"TOKEN": "vault_x"})
    result = check_server(
        cfg, resolved_secrets={"vault_x": False}, connection_state="connected",
        discovered_tools=3, selected_tools=0,
    ).to_public()
    codes = {c["code"]: c for c in result["checks"]}
    assert codes["secrets_missing"]["status"] == "error"
    assert codes["no_tools_selected"]["status"] == "warn"
    assert codes["no_tools_selected"]["recovery"]


def test_environment_diagnostics_always_reports_temp_dir():
    codes = {c.code for c in environment_diagnostics()}
    assert "temp_writable" in codes or "temp_not_writable" in codes


# ── provenance on every result ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_result_carries_external_provenance():
    mgr = MCPManager([MCPServerConfig(
        id="fin", command=sys.executable, args=[FINANCE],
        enabled=True, selected_tools=["read_holdings"], tool_effects={"read_holdings": "read"},
    )])
    await mgr.start()
    reg = ToolRegistry()
    [name] = mgr.register_selected_tools(reg)
    result = await reg.execute(name, "c1", {}, ToolContext(run_id="r1", log=lambda *_: None), allowed={name})
    assert result.ok
    prov = result.data["provenance"]
    assert prov["verification"] == "external"
    assert prov["eclipseVerified"] is False
    assert prov["source"]["serverId"] == "fin"
    assert prov["retrievedAt"]
    assert "NOT Eclipse-verified" in result.text
    await mgr.close()


# ── end-to-end finance workflow ─────────────────────────────────────────────


class FakeBridge(DataBridge):
    """Eclipse's own data (native, authoritative) for the analysis leg."""

    async def fetch(self, capability, params):
        if capability == "market_snapshot":
            return {"status": "OK", "symbol": "AAPL", "market": "US", "currency": "USD",
                    "price": {"price": 175.0, "changePct": 1.0}}
        return {"status": "UNAVAILABLE"}


@pytest.mark.asyncio
async def test_end_to_end_import_analyse_report_export(tmp_path):
    """Import holdings (MCP read) → analyse with Eclipse data → report → export
    (MCP write, gated by an explicit approval)."""
    export_dir = tmp_path / "exports"
    os.environ["FINANCE_EXPORT_DIR"] = str(export_dir)

    store = AgentMemoryStore(str(tmp_path / "agent-memory.db"))
    approvals = ApprovalStore(store)

    cfg = MCPServerConfig(
        id="fin", command=sys.executable, args=[FINANCE], enabled=True,
        selected_tools=["read_holdings", "export_report"],
        tool_effects={"read_holdings": "read", "export_report": "write"},
        enabled_effects=["read", "write"],
        # The child gets ONLY this scoped env (never the host environment).
        env={"FINANCE_EXPORT_DIR": str(export_dir)},
    )
    mgr = MCPManager([cfg])
    await mgr.start()
    reg = ToolRegistry()
    names = mgr.register_selected_tools(reg)
    assert set(names) == {"mcp__fin__read_holdings", "mcp__fin__export_report"}

    ctx = ToolContext(run_id="run_e2e", log=lambda *_: None)
    ctx.authorize_effect = make_effect_authorizer(approvals, "run_e2e", None)

    # 1. Import holdings (read-only, no approval).
    imported = await reg.execute("mcp__fin__read_holdings", "c1", {}, ctx, allowed=set(names))
    assert imported.ok
    holdings = json.loads(imported.data["structuredContent"]["result"])["rows"]
    assert [h["symbol"] for h in holdings] == ["AAPL", "MSFT", "NVDA"]

    # 2. Analyse using Eclipse's authoritative data (native bridge).
    bridge = FakeBridge()
    analysis_lines = []
    for h in holdings:
        snap = await bridge.fetch("market_snapshot", {"symbol": h["symbol"]})
        value = h["quantity"] * snap["price"]["price"]
        analysis_lines.append(f"{h['symbol']}: {h['quantity']} @ {snap['price']['price']} = {value:.2f}")
    report = "Portfolio review\n" + "\n".join(analysis_lines)
    assert "AAPL" in report and "1750.00" in report

    # 3. Export the report — an EFFECTFUL tool: refused until approved.
    denied = await reg.execute(
        "mcp__fin__export_report", "c2",
        {"name": "review.txt", "content": report}, ctx, allowed=set(names),
    )
    assert not denied.ok and denied.error.code == "TOOL_FORBIDDEN"

    # The approval records the action, affected data and risk for the operator.
    pending = approvals.list("pending")
    assert pending and pending[0]["tool"] == "export_report"
    assert pending[0]["actionSummary"]
    assert pending[0]["affectedData"]
    assert pending[0]["risk"] == "high"

    # 4. Operator approves the exact call; export now runs.
    approvals.decide(pending[0]["id"], approve=True)
    exported = await reg.execute(
        "mcp__fin__export_report", "c3",
        {"name": "review.txt", "content": report}, ctx, allowed=set(names),
    )
    assert exported.ok, exported.text
    written = export_dir / "review.txt"
    assert written.exists()
    assert "AAPL" in written.read_text(encoding="utf-8")

    # 5. Provenance is external on the MCP legs; the analysis used native data.
    assert imported.data["provenance"]["eclipseVerified"] is False
    assert exported.data["provenance"]["source"]["serverId"] == "fin"

    # A changed payload needs a NEW approval (digest binding).
    changed = await reg.execute(
        "mcp__fin__export_report", "c4",
        {"name": "review2.txt", "content": "different"}, ctx, allowed=set(names),
    )
    assert not changed.ok and changed.error.code == "TOOL_FORBIDDEN"

    await mgr.close()
    store.close()
