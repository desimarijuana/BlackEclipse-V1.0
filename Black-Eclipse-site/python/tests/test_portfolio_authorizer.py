"""The Portfolio effect authorizer — admitted into the chain, never a bypass.

Measured before the fix (2026-10-14): every `portfolio_*` mutation fell through
every layer of `build_effect_authorizer` to the MCP authorizer, which refuses any
tool without an MCP server id — so `portfolio_create` / `portfolio_add_position`
were advertised to `ECLIPSE_AGENT` but dead (`TOOL_FORBIDDEN`). The new
`portfolio/authorizers.py` layer admits the mutation family and requires a
single-use, digest-bound operator approval (kind `portfolio_write`).

This mirrors `test_authorizer_runtime_admission.py`, with the extra obligation
that admission is CONDITIONAL: a mutation with no approval is still refused.
"""

from __future__ import annotations

import asyncio
from typing import Any, Optional

import pytest

from harness.portfolio.authorizers import (
    PORTFOLIO_APPROVAL_KIND,
    _digest,
    _scope,
    make_portfolio_authorizer,
    owns,
)
from harness.portfolio.tools import (
    PORTFOLIO_CONSEQUENTIAL_TOOLS,
    PORTFOLIO_READ_TOOLS,
    PORTFOLIO_WRITE_TOOLS,
)
from harness.tools import ToolDefinition


def _tool(name: str, effect: Optional[str] = None) -> ToolDefinition:
    return ToolDefinition(
        name=name,
        description="",
        input_schema={"type": "object", "properties": {}},
        handler=lambda args, ctx: ("ok", None),
        permission="write",
        risk="medium",
        effect=effect or "portfolio.write",
    )


class _Store:
    """A minimal stand-in for the ApprovalStore interface the layer uses."""

    def __init__(self, *, claim_digest: Optional[str] = None, grants: Any = None) -> None:
        self._claim_digest = claim_digest
        self.requests: list[dict[str, Any]] = []
        self.grants = grants

    def consume_kind(self, *, kind: str, request_key: str, digest: str, workspace_id: Any = None) -> Any:
        # Single-use: a matching claim is returned at most once.
        if self._claim_digest is not None and digest == self._claim_digest:
            self._claim_digest = None
            return {"id": "appr_1"}
        return None

    def request_kind(self, **kwargs: Any) -> Any:
        self.requests.append(kwargs)
        return {"id": "appr_req"}

    def find_active_kind(self, **kwargs: Any) -> Any:
        return None


# ── admission matrix ───────────────────────────────────────────────────────────

@pytest.mark.parametrize("name", [*PORTFOLIO_WRITE_TOOLS, *PORTFOLIO_CONSEQUENTIAL_TOOLS])
def test_every_portfolio_mutation_is_owned(name: str) -> None:
    assert owns(name) is True


@pytest.mark.parametrize("name", PORTFOLIO_READ_TOOLS)
def test_portfolio_reads_are_not_owned(name: str) -> None:
    # Reads never reach an authorizer (the registry skips them); the layer must
    # not claim them either.
    assert owns(name) is False


@pytest.mark.parametrize("name", ["portfolio_create", "portfolio_add_position",
                                  "portfolio_rebalance", "portfolio_optimize"])
def test_a_mutation_with_no_approval_is_refused(name: str) -> None:
    auth = make_portfolio_authorizer(_Store(), "r", "", None, inner=_false_inner)
    assert asyncio.run(auth(_tool(name), {"portfolio_id": "p1", "name": "X"}, None)) is False


@pytest.mark.parametrize("name", ["git_push", "unknown_tool", "plugin_invoke", "execute_python",
                                  "portfolio_get", "portfolio_calculate_pnl"])
def test_non_portfolio_tools_fall_through(name: str) -> None:
    auth = make_portfolio_authorizer(_Store(), "r", "", None, inner=_false_inner)
    assert asyncio.run(auth(_tool(name), {}, None)) is False


async def _false_inner(tool: Any, args: dict[str, Any], ctx: Any = None) -> bool:
    return False


# ── approval semantics ─────────────────────────────────────────────────────────

def test_a_claimed_approval_authorizes_the_call() -> None:
    args = {"portfolio_id": "p1", "symbol": "AAPL", "quantity": "1"}
    digest = _digest(_scope(args, ""), "portfolio_add_position", args)
    store = _Store(claim_digest=digest)
    auth = make_portfolio_authorizer(store, "r", "", None, inner=_false_inner)
    assert asyncio.run(auth(_tool("portfolio_add_position"), args, None)) is True


def test_a_single_approval_cannot_authorize_twice() -> None:
    args = {"portfolio_id": "p1", "symbol": "AAPL", "quantity": "1"}
    digest = _digest(_scope(args, ""), "portfolio_add_position", args)
    store = _Store(claim_digest=digest)
    auth = make_portfolio_authorizer(store, "r", "", None, inner=_false_inner)
    tool = _tool("portfolio_add_position")
    assert asyncio.run(auth(tool, args, None)) is True
    assert asyncio.run(auth(tool, args, None)) is False  # single-use


def test_a_changed_payload_needs_a_new_approval() -> None:
    original = {"portfolio_id": "p1", "symbol": "AAPL", "quantity": "1"}
    digest = _digest(_scope(original, ""), "portfolio_add_position", original)
    store = _Store(claim_digest=digest)
    auth = make_portfolio_authorizer(store, "r", "", None, inner=_false_inner)
    changed = {"portfolio_id": "p1", "symbol": "AAPL", "quantity": "2"}
    assert asyncio.run(auth(_tool("portfolio_add_position"), changed, None)) is False


def test_a_standing_grant_authorizes_without_consuming() -> None:
    class _Grants:
        def matches(self, kind: str, scope: str, pattern: str) -> Any:
            assert kind == PORTFOLIO_APPROVAL_KIND
            return {"id": "grant_1"} if (scope == "p1" and pattern == "portfolio_add_position") else None

    args = {"portfolio_id": "p1", "symbol": "AAPL", "quantity": "1"}
    auth = make_portfolio_authorizer(_Store(grants=_Grants()), "r", "", None, inner=_false_inner)
    assert asyncio.run(auth(_tool("portfolio_add_position"), args, None)) is True


def test_no_store_refuses_and_never_authorizes() -> None:
    args = {"name": "X"}
    auth = make_portfolio_authorizer(None, "r", "", None, inner=_false_inner)
    assert asyncio.run(auth(_tool("portfolio_create"), args, None)) is False


def test_a_pending_request_is_created_when_nothing_is_claimed() -> None:
    store = _Store()
    args = {"name": "BlackRock Portfolio", "base_currency": "USD",
            "cost_basis_method": "FIFO"}
    auth = make_portfolio_authorizer(store, "r", "", None, inner=_false_inner)
    assert asyncio.run(auth(_tool("portfolio_create"), args, None)) is False
    assert store.requests and store.requests[0]["kind"] == PORTFOLIO_APPROVAL_KIND
    assert store.requests[0]["request_key"] == "portfolio:portfolio_create"
    assert store.requests[0]["grant_pattern"] == "portfolio_create"


# ── the composition, not only the helper ───────────────────────────────────────

def test_the_composed_authorizer_admits_a_claimed_portfolio_write(monkeypatch: Any) -> None:
    from harness.security import bootstrap as sec_bootstrap

    monkeypatch.setattr(sec_bootstrap, "get_gateway", lambda: None)

    args = {"name": "BlackRock Portfolio"}
    digest = _digest(_scope(args, ""), "portfolio_create", args)
    store = _Store(claim_digest=digest)

    async def run() -> bool:
        from harness.code.authorizers import build_effect_authorizer

        auth = build_effect_authorizer(approvals=store, run_id="r", emitter=None, workspace_id=None)
        return bool(await auth(_tool("portfolio_create"), args, None))

    assert asyncio.run(run()) is True


def test_the_composed_authorizer_still_refuses_without_a_claim(monkeypatch: Any) -> None:
    from harness.security import bootstrap as sec_bootstrap

    monkeypatch.setattr(sec_bootstrap, "get_gateway", lambda: None)

    async def run() -> bool:
        from harness.code.authorizers import build_effect_authorizer

        auth = build_effect_authorizer(approvals=_Store(), run_id="r", emitter=None, workspace_id=None)
        return bool(await auth(_tool("portfolio_create"), {"name": "X"}, None))

    assert asyncio.run(run()) is False
