"""Advertised tools must be ADMISSIBLE — the guard for the "advertised but dead"
defect class.

`portfolio_create` (and the rest of the portfolio family) was advertised to
`ECLIPSE_AGENT` but refused at call time (`TOOL_FORBIDDEN`) because no layer in
`code/authorizers.build_effect_authorizer` claimed it — it fell through to the MCP
authorizer, which refuses any tool without an MCP server id. The runtime family
had the same defect (fixed by `_admit_runtime_tools`).

This test composes the REAL authorizer chain with a PERMISSIVE approval store
(grants + claims everything). With that store, the ONLY reason a tool can be
refused is that no admission branch exists for it — i.e. it is "dead". Every
tool named in a family below must be admitted; unknown tools and the deliberately
operator-only families must still fall through.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any, Optional

import pytest

from harness.tools import ToolDefinition


class _PermissiveStore:
    """Approves/grants everything, so only a missing admission branch yields False."""

    def __init__(self) -> None:
        self.grants = self  # grants.matches(...) is consulted by name-keyed layers

    # -- grant store surface --
    def matches(self, kind: str, scope: str, pattern: str) -> Any:
        return {"id": "grant_1"}

    # -- approval store surface --
    def consume_kind(self, **kwargs: Any) -> Any:
        return {"id": "appr_1"}

    def consume(self, *args: Any, **kwargs: Any) -> Any:
        return {"id": "appr_1"}

    def find_active_kind(self, **kwargs: Any) -> Any:
        return {"id": "appr_1"}

    def request_kind(self, **kwargs: Any) -> Any:
        return {"id": "appr_req"}

    def wait_for_decision(self, *args: Any, **kwargs: Any) -> Any:
        return {"status": "approved"}


def _tool(name: str, effect: str = "external_action") -> ToolDefinition:
    return ToolDefinition(
        name=name,
        description="",
        input_schema={"type": "object", "properties": {}},
        handler=lambda args, ctx: ("", None),
        permission="write",
        risk="high",
        effect=effect,
    )


@pytest.fixture(autouse=True)
def _no_gateway(monkeypatch: Any) -> None:
    # The security gateway is additive; with none installed the composed chain is
    # exactly the capability authorizers (what we are testing).
    from harness.security import bootstrap as sec

    monkeypatch.setattr(sec, "get_gateway", lambda: None)


def _admit(name: str, effect: str = "external_action", args: Optional[dict[str, Any]] = None) -> bool:
    from harness.code.authorizers import build_effect_authorizer

    store = _PermissiveStore()
    ctx = SimpleNamespace(
        approvals=store, run_id="r", pause_for_approval=False, emitter=None,
        effect_authorized_digest=None,
    )
    auth = build_effect_authorizer(approvals=store, run_id="r", emitter=None, workspace_id=None)
    return bool(asyncio.run(auth(_tool(name, effect), args or {}, ctx)))


# Valid arguments for the authorizers that validate their input before the store
# is consulted (a missing/invalid source is a validation refusal, not a dead tool).
def _admit_args(name: str) -> dict[str, Any]:
    if name == "skill_install":
        return {"source": "https://github.com/acme/tools"}
    if name == "skill_create":
        return {"name": "Demo", "instructions": "1. step one"}
    if name in ("skill_update", "skill_delete"):
        return {"skill_id": "user.demo"}
    if name in ("python_env_install", "python_env_remove"):
        return {"packages": ["demo"]}
    if name == "mcp_install":
        from harness.mcp.install_ops import list_catalog

        catalog = list_catalog()
        return {"integrationId": catalog[0]["id"]} if catalog else {}
    return {}


# ── every advertised mutation family must be admitted ─────────────────────────

@pytest.mark.parametrize("name", [
    # the execution + LOCAL application-runtime family (R3-02)
    "execute_python", "execute_code", "package_install", "container_run",
    # bulk acquisition (the collect branch)
    "acquire",
    # automation schedules (the bot branch)
    "bot_create", "bot_resume",
    # remote Git (the git branch; a permissive grant/claim admits it)
    "git_push", "vcs_create_pull_request",
    # capability acquisition (skill / mcp install branches)
    "skill_install", "mcp_install",
    # the extension layer (agent-authored skills)
    "skill_create", "skill_update", "skill_delete",
    # the managed analysis package environment
    "python_env_install", "python_env_remove",
])
def test_advertised_family_is_admitted(name: str) -> None:
    assert _admit(name, args=_admit_args(name)) is True, f"{name} is advertised but no layer admits it (dead tool)"


@pytest.mark.parametrize("name", [
    "portfolio_create", "portfolio_add_position", "portfolio_remove_position",
    "portfolio_update_position", "portfolio_set_metadata",
    "portfolio_apply_corporate_action", "portfolio_record_swap",
    "portfolio_record_bridge", "portfolio_record_reward",
    "portfolio_apply_staking", "portfolio_rebuild",
    "portfolio_apply_slashing", "portfolio_record_funding",
    "portfolio_rebalance", "portfolio_optimize", "portfolio_construct",
])
def test_the_whole_portfolio_family_is_admitted(name: str) -> None:
    # The exact family whose absence caused TOOL_FORBIDDEN on `portfolio_create`.
    assert _admit(name, effect="portfolio.write") is True


# ── the guard must still refuse, not blanket-admit ────────────────────────────

@pytest.mark.parametrize("name", [
    # a tool no layer owns → refused (this is what a NEW un-wired family looks like)
    "unknown_tool",
    # cluster/infra mutations are deliberately operator-only (no admission branch)
    "k8s_apply", "helm_install", "terraform_apply", "deploy_run",
    # a read tool never reaches an authorizer; it must not be admitted here either
    "portfolio_get",
])
def test_unowned_and_operator_only_tools_fall_through(name: str) -> None:
    assert _admit(name) is False


def test_the_portfolio_family_is_exactly_the_write_and_consequential_sets() -> None:
    from harness.portfolio.authorizers import owns
    from harness.portfolio.tools import (
        PORTFOLIO_CONSEQUENTIAL_TOOLS,
        PORTFOLIO_READ_TOOLS,
        PORTFOLIO_WRITE_TOOLS,
    )

    for name in (*PORTFOLIO_WRITE_TOOLS, *PORTFOLIO_CONSEQUENTIAL_TOOLS):
        assert owns(name) is True, name
    for name in PORTFOLIO_READ_TOOLS:
        assert owns(name) is False, name
