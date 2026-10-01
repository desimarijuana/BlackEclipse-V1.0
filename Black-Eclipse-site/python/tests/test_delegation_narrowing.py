"""Phase 7 G1 — narrowing: a child can never widen (the negatives matter most).

`child_actor` is the safety core: grants are the INTERSECTION with the child's
scope, never a superset, and `operator` is NEVER inherited (that is how a child
would launder authority).
"""

from __future__ import annotations

import pytest

from harness.delegation import (
    DelegationChild,
    DelegationError,
    PERMISSION_NOT_HELD,
    TOOL_NOT_HELD,
    child_actor,
    narrow_tools,
)
from harness.skills.permissions import Actor, OPERATOR_PERMISSIONS


def _parent(**overrides) -> Actor:
    base = dict(
        id="parent",
        operator=True,
        grants=frozenset({"data.read", "research.read"}),
        workspace_id="ws_parent",
        autonomy="edit_verify",
    )
    base.update(overrides)
    return Actor(**base)


def _child(**overrides) -> DelegationChild:
    base = dict(goal="look at one thing")
    base.update(overrides)
    return DelegationChild(**base)


# ── operator is never inherited ──────────────────────────────────────────────


def test_operator_is_never_inherited():
    child = child_actor(_parent(), _child())
    assert child.operator is False


def test_operator_only_permissions_are_never_passed_down():
    child = child_actor(_parent(), _child())
    granted = child.granted()
    for permission in OPERATOR_PERMISSIONS:
        assert permission not in granted, permission


def test_operator_parent_cannot_grant_a_child_operator_only_permission():
    # Even an operator parent's child cannot hold skill.create/review/enable/etc.
    child = child_actor(_parent(), _child())
    assert "skill.create" not in child.granted()
    assert "skill.enable" not in child.granted()


# ── grants never a superset ──────────────────────────────────────────────────


def test_child_grants_are_never_a_superset_of_parent_grants():
    parent = _parent()
    child = child_actor(parent, _child())
    assert child.granted() <= parent.granted()


def test_non_operator_parent_grants_nothing_extra():
    parent = _parent(operator=False)
    child = child_actor(parent, _child())
    assert child.granted() <= parent.granted()


def test_child_without_workspace_holds_no_code_permissions():
    # A read-only child gets no code grants, even when the parent is bound.
    child = child_actor(_parent(), _child(workspace_id=None))
    granted = child.granted()
    for permission in ("code.read", "code.write", "code.execute", "command.execute"):
        assert permission not in granted, permission


def test_child_with_parent_workspace_keeps_the_parents_code_grants():
    child = child_actor(_parent(), _child(workspace_id="ws_parent"))
    assert "code.write" in child.granted()


# ── workspace never wider ────────────────────────────────────────────────────


def test_wider_workspace_is_refused():
    with pytest.raises(DelegationError) as info:
        child_actor(_parent(), _child(workspace_id="ws_someone_else"))
    assert info.value.code == PERMISSION_NOT_HELD


def test_workspace_refused_even_for_an_operator_parent():
    with pytest.raises(DelegationError):
        child_actor(_parent(operator=True), _child(workspace_id="ws_other"))


# ── tool subset ⊆ the parent's allowlist ─────────────────────────────────────


def test_tool_subset_must_be_within_the_parents_allowlist():
    with pytest.raises(DelegationError) as info:
        narrow_tools({"workspace_read", "workspace_search"}, _child(tool_subset=["workspace_read", "command_run"]))
    assert info.value.code == TOOL_NOT_HELD


def test_tool_subset_may_narrow():
    allowed = narrow_tools({"workspace_read", "workspace_search"}, _child(tool_subset=["workspace_read"]))
    assert allowed == {"workspace_read"}


def test_no_subset_inherits_the_parents_allowlist():
    parent_allowed = {"workspace_read", "workspace_search"}
    assert narrow_tools(parent_allowed, _child()) == parent_allowed


def test_unrestricted_parent_does_not_become_restricted_by_default():
    assert narrow_tools(None, _child()) is None


def test_unrestricted_parent_can_scope_a_child():
    assert narrow_tools(None, _child(tool_subset=["a", "b"])) == {"a", "b"}
