"""The ledger effect authorizer — admitted into the chain, never a bypass.

Admission alone is not authorization: a `ledger_*` mutation with no standing
grant and no single-use approval must still be refused. A changed payload must
need a new approval, because the digest binds tool + arguments + ledger.
"""

from __future__ import annotations

import asyncio
from typing import Any, Optional

import pytest

from harness.ledger.authorizers import (
    LEDGER_APPROVAL_KIND,
    _digest,
    _scope,
    make_ledger_authorizer,
    owns,
)
from harness.ledger.tools import LEDGER_READ_TOOLS, LEDGER_WRITE_TOOLS
from harness.tools import ToolDefinition


def _tool(name: str, effect: Optional[str] = None) -> ToolDefinition:
    return ToolDefinition(
        name=name,
        description="",
        input_schema={"type": "object", "properties": {}},
        handler=lambda args, ctx: ("ok", None),
        permission="write",
        risk="medium",
        effect=effect or "ledger.write",
    )


async def _false_inner(tool: Any, args: dict[str, Any], ctx: Any = None) -> bool:
    return False


class _Store:
    """A minimal stand-in for the ApprovalStore interface the layer uses."""

    def __init__(self, *, claim_digest: Optional[str] = None, grants: Any = None) -> None:
        self._claim_digest = claim_digest
        self.requests: list[dict[str, Any]] = []
        self.grants = grants

    def consume_kind(self, *, kind: str, request_key: str, digest: str,
                     workspace_id: Any = None) -> Any:
        if self._claim_digest is not None and digest == self._claim_digest:
            self._claim_digest = None
            return {"id": "appr_1"}
        return None

    def request_kind(self, **kwargs: Any) -> Any:
        self.requests.append(kwargs)
        return {"id": "appr_req"}


@pytest.mark.parametrize("name", LEDGER_WRITE_TOOLS)
def test_every_ledger_mutation_is_owned(name: str) -> None:
    assert owns(name) is True


@pytest.mark.parametrize("name", LEDGER_READ_TOOLS)
def test_ledger_reads_are_not_owned(name: str) -> None:
    assert owns(name) is False


@pytest.mark.parametrize("name", ["ledger_post", "ledger_create", "ledger_close_period"])
def test_a_mutation_with_no_approval_is_refused(name: str) -> None:
    auth = make_ledger_authorizer(_Store(), "r", "", None, inner=_false_inner)
    assert asyncio.run(auth(_tool(name), {"ledger_id": "l1", "name": "X"}, None)) is False


@pytest.mark.parametrize("name", ["portfolio_add_position", "git_push", "unknown_tool"])
def test_non_ledger_tools_fall_through(name: str) -> None:
    auth = make_ledger_authorizer(_Store(), "r", "", None, inner=_false_inner)
    assert asyncio.run(auth(_tool(name), {}, None)) is False


def test_a_claimed_approval_authorizes_the_call_once() -> None:
    args = {"ledger_id": "l1", "entry_date": "2026-01-05",
            "lines": [{"account_code": "1010", "debit": "10"},
                      {"account_code": "4000", "credit": "10"}]}
    digest = _digest(_scope(args, ""), "ledger_post", args)
    store = _Store(claim_digest=digest)
    auth = make_ledger_authorizer(store, "r", "", None, inner=_false_inner)
    tool = _tool("ledger_post")
    assert asyncio.run(auth(tool, args, None)) is True
    assert asyncio.run(auth(tool, args, None)) is False  # single use


def test_a_changed_payload_needs_a_new_approval() -> None:
    original = {"ledger_id": "l1", "entry_date": "2026-01-05",
                "lines": [{"account_code": "1010", "debit": "10"},
                          {"account_code": "4000", "credit": "10"}]}
    digest = _digest(_scope(original, ""), "ledger_post", original)
    store = _Store(claim_digest=digest)
    auth = make_ledger_authorizer(store, "r", "", None, inner=_false_inner)
    changed = {**original, "lines": [{"account_code": "1010", "debit": "11"},
                                     {"account_code": "4000", "credit": "11"}]}
    assert asyncio.run(auth(_tool("ledger_post"), changed, None)) is False


def test_a_standing_grant_authorizes_without_consuming() -> None:
    class _Grants:
        def matches(self, kind: str, scope: str, pattern: str) -> Any:
            assert kind == LEDGER_APPROVAL_KIND
            return {"id": "grant_1"} if (scope == "l1" and pattern == "ledger_post") else None

    auth = make_ledger_authorizer(_Store(grants=_Grants()), "r", "", None, inner=_false_inner)
    assert asyncio.run(auth(_tool("ledger_post"), {"ledger_id": "l1"}, None)) is True


def test_no_store_refuses_and_never_authorizes() -> None:
    auth = make_ledger_authorizer(None, "r", "", None, inner=_false_inner)
    assert asyncio.run(auth(_tool("ledger_create"), {"name": "X"}, None)) is False


def test_a_pending_request_is_created_with_the_ledger_scope() -> None:
    store = _Store()
    auth = make_ledger_authorizer(store, "r", "", None, inner=_false_inner)
    args = {"ledger_id": "l1", "entry_date": "2026-01-05",
            "lines": [{"account_code": "1010", "debit": "1"},
                      {"account_code": "4000", "credit": "1"}]}
    assert asyncio.run(auth(_tool("ledger_post"), args, None)) is False
    assert store.requests
    request = store.requests[0]
    assert request["kind"] == LEDGER_APPROVAL_KIND
    assert request["request_key"] == "ledger:ledger_post"
    assert request["grant_scope"] == "l1"
    assert "2 line(s)" in request["action_summary"]
