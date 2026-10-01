"""Phase 10 G3 — a proposal touching ANY frozen file is refused with a STRUCTURED
error; nothing on disk changes on any refusal.

The freeze set is the four authorities (a subject cannot edit its own judge) plus
`policy.PROTECTED_PATHS` and the `skills/patches.py` FORBIDDEN_FIELDS.
"""

from __future__ import annotations

import hashlib
import os

import pytest

from harness.code import policy
from harness.code.evolution import (
    EvolutionRefusal,
    FROZEN_PATH,
    FROZEN_PATHS,
    FORBIDDEN_FIELD,
    NOT_PATCHABLE,
    PROTECTED,
    is_frozen,
    propose_ops,
)
from harness.skills.permissions import Actor


def _candidate(target: str, ops=None):  # noqa: ANN001
    return {"targetPath": target, "proposedOps": ops if ops is not None else [
        {"op": "replace", "path": target, "old": "a", "new": "b"},
    ]}


def _actor() -> Actor:
    return Actor(id="operator", operator=True)


def _sha(path: str) -> str:
    with open(path, "rb") as handle:
        return hashlib.sha256(handle.read()).hexdigest()


@pytest.mark.parametrize("frozen", FROZEN_PATHS)
def test_each_frozen_file_is_refused_with_frozen_path(frozen):
    with pytest.raises(EvolutionRefusal) as info:
        propose_ops(_candidate(frozen), actor=_actor())
    assert info.value.code == FROZEN_PATH
    assert info.value.path == frozen


def test_a_frozen_path_with_a_leading_dot_slash_is_still_frozen():
    assert is_frozen("./python/harness/code/policy.py")
    with pytest.raises(EvolutionRefusal) as info:
        propose_ops(_candidate("./python/harness/code/policy.py"), actor=_actor())
    assert info.value.code == FROZEN_PATH


def test_a_frozen_path_is_refused_even_with_no_ops():
    # The freeze fires before the empty-op check, so a frozen target never reaches
    # the NOT_PATCHABLE branch.
    with pytest.raises(EvolutionRefusal) as info:
        propose_ops(_candidate("python/harness/mcp/approvals.py", ops=[]), actor=_actor())
    assert info.value.code == FROZEN_PATH


def test_a_protected_path_is_refused_with_protected():
    # jdds.db is a PROTECTED_PATHS member (a database), not a frozen authority.
    with pytest.raises(EvolutionRefusal) as info:
        propose_ops(_candidate("jdds.db"), actor=_actor())
    assert info.value.code == PROTECTED


def test_a_forbidden_field_is_refused():
    # An op that tries to set a permissions/identity/tool field is refused.
    with pytest.raises(EvolutionRefusal) as info:
        propose_ops(
            {"targetPath": "python/harness/x.py", "proposedOps": [
                {"op": "replace", "path": "permissions", "old": "[]", "new": '["code.write"]'},
            ]},
            actor=_actor(),
        )
    assert info.value.code == FORBIDDEN_FIELD


def test_an_empty_op_set_is_not_patchable():
    with pytest.raises(EvolutionRefusal) as info:
        propose_ops(_candidate("python/harness/x.py", ops=[]), actor=_actor())
    assert info.value.code == NOT_PATCHABLE


def test_an_unsupported_op_is_refused():
    with pytest.raises(EvolutionRefusal) as info:
        propose_ops(_candidate("python/harness/x.py", ops=[{"op": "chmod", "path": "x"}]), actor=_actor())
    assert info.value.code == NOT_PATCHABLE


def test_a_valid_proposal_is_returned_unchanged():
    ops = [{"op": "replace", "path": "python/harness/x.py", "old": "a", "new": "b"}]
    assert propose_ops(_candidate("python/harness/x.py", ops=ops), actor=_actor()) == ops


def test_nothing_on_disk_changes_on_a_frozen_refusal():
    # The freeze is a pure decision; hash a frozen file before/after.
    import harness.code.policy as policy_module

    target = "python/harness/code/policy.py"
    abs_path = os.path.abspath(policy_module.__file__)
    before = _sha(abs_path)
    with pytest.raises(EvolutionRefusal):
        propose_ops(_candidate(target), actor=_actor())
    assert _sha(abs_path) == before


def test_the_fresh_protected_paths_are_all_refused():
    # Every PROTECTED_PATHS entry that maps to a real file is refused. A glob-only
    # entry that does not name a concrete file is skipped.
    for entry in policy.PROTECTED_PATHS:
        if any(ch in entry for ch in ("*", "?")):
            continue
        if entry in FROZEN_PATHS:
            continue
        with pytest.raises(EvolutionRefusal) as info:
            propose_ops(_candidate(entry), actor=_actor())
        assert info.value.code in (PROTECTED, FROZEN_PATH)
