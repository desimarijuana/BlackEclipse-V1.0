"""RSL safety floor — the frozen judge, op paths and non-landable surface rows."""

from __future__ import annotations

import uuid
from fnmatch import fnmatch
from types import SimpleNamespace

import pytest

from harness.code.evolution_store import EvolutionStore
from harness.persistence import AgentMemoryStore
from harness.self_improvement import landing
from harness.self_improvement.proposer import ProposalRefused, propose_from_ops
from harness.self_improvement.security import RSL_DENY_GLOBS, assert_landable_target
from harness.self_improvement.verifier import SurfaceConfigError, verify_surface_candidate


@pytest.fixture()
def memory(tmp_path):
    store = AgentMemoryStore(str(tmp_path / "agent-memory.db"))
    yield store
    store.close()


def _sample(pattern: str) -> str:
    path = pattern.replace("**", "nested/file.py").replace("*", "file.py")
    assert fnmatch(path.casefold(), pattern.casefold()), (pattern, path)
    return path


def test_every_deny_glob_has_an_enforced_representative_target():
    for pattern in RSL_DENY_GLOBS:
        with pytest.raises(Exception) as refused:
            assert_landable_target(_sample(pattern))
        assert getattr(refused.value, "code", "") == "RSL_FROZEN_TARGET", pattern


def test_a_frozen_op_path_is_refused_even_when_the_target_is_safe(memory):
    evolution = EvolutionStore(memory)
    candidate = evolution.save_candidate({
        "signature": f"sig-{uuid.uuid4().hex}",
        "sourceCategory": "timeout",
        "observedCount": 3,
        "problemStatement": "the bound that timed out",
        "targetPath": "python/harness/rsl_secure_target.py",
        "proposedOps": [{
            "op": "create",
            "path": "python/tests/test_rsl_secure_target.py",
            "content": "def test_x():\n    assert True\n",
            "reason": "the candidate tries to edit its own judge",
        }],
        "status": "inert",
    })

    with pytest.raises(ProposalRefused) as refused:
        propose_from_ops(memory, candidate["id"], actor=None)

    assert refused.value.code == "RSL_FROZEN_TARGET"


def test_a_surface_candidate_is_never_prepared_for_landing(memory):
    evolution = EvolutionStore(memory)
    candidate = evolution.save_candidate({
        "signature": f"sig-{uuid.uuid4().hex}",
        "sourceCategory": "operator",
        "observedCount": 1,
        "problemStatement": "surface fixture",
        "subjectType": "surface",
        "surfaceConfig": {
            "base": {"systemPrompt": "You are Eclipse.", "toolNames": []},
            "snapshot": {"systemPrompt": "You are Eclipse, candidate.", "toolNames": []},
        },
        "status": "evaluated_ok",
    })

    with pytest.raises(landing.RSLLandingError) as refused:
        landing.prepare(SimpleNamespace(store=memory), candidate["id"])

    assert refused.value.code == "RSL_SURFACE_NOT_LANDABLE"


@pytest.mark.asyncio
async def test_a_surface_candidate_cannot_widen_the_base_allowlist(memory):
    evolution = EvolutionStore(memory)
    candidate = evolution.save_candidate({
        "signature": f"sig-{uuid.uuid4().hex}",
        "sourceCategory": "operator",
        "observedCount": 1,
        "problemStatement": "surface fixture",
        "subjectType": "surface",
        "surfaceConfig": {
            "base": {
                "systemPrompt": "You are Eclipse.",
                "toolNames": ["eval_fs_read"],
            },
            "snapshot": {
                "systemPrompt": "You are Eclipse, candidate.",
                "toolNames": ["eval_fs_read", "eval_fs_write"],
            },
        },
        "status": "proposed",
    })

    with pytest.raises(SurfaceConfigError) as refused:
        await verify_surface_candidate(memory, candidate, config=None)

    assert refused.value.code == "SNAPSHOT_TOOL_NOT_IN_BASE"


@pytest.mark.asyncio
async def test_a_surface_candidate_refuses_an_invalid_stored_snapshot(memory):
    evolution = EvolutionStore(memory)
    candidate = evolution.save_candidate({
        "signature": f"sig-{uuid.uuid4().hex}",
        "sourceCategory": "operator",
        "observedCount": 1,
        "problemStatement": "surface fixture",
        "subjectType": "surface",
        "surfaceConfig": {
            "base": {"systemPrompt": "You are Eclipse.", "toolNames": []},
            "snapshot": {"systemPrompt": "", "toolNames": []},
        },
        "status": "proposed",
    })

    with pytest.raises(SurfaceConfigError) as refused:
        await verify_surface_candidate(
            memory, candidate, config=None,
        )

    assert refused.value.code == "SURFACE_SNAPSHOT_INVALID"
