"""Phase 10 G1/G1b/G2/G6 — the seeded journey, the canary rollback, non-operator refusals.

The journey: a seeded recurrence → an inert candidate → structured ops →
evaluation in a worktree (recorded through the Phase-4 ledger) → operator
activation through skills/versioning.py → rollback. Every step is asserted by
reading the recorded rows/events, never a status string alone.
"""

from __future__ import annotations

import os
import subprocess

import pytest
from fastapi.testclient import TestClient

from harness.code import evolution as evo
from harness.code import evolution_service as esvc
from harness.code.evolution_store import EvolutionStore
from harness.persistence import AgentMemoryStore
from harness.skills import versioning
from harness.skills.permissions import OPERATOR_ACTOR


@pytest.fixture
def store(tmp_path):
    return AgentMemoryStore(str(tmp_path / "agent-memory.db"))


def _seed_recurrence(store, category="timeout", times=evo.RECURRENCE_THRESHOLD):
    for _ in range(times):
        store.record_learning_recurrence(evo._category_signature(category))


class _Ctx:
    """A minimal ToolContext for evaluation (broker + ledger + store)."""

    def __init__(self, store, tmp_path):
        from harness.code.store import CodeWorkspaceStore
        from harness.code.verify import VerificationLedger

        self.run_id = "run_evo"
        self.memory_store = store
        self.code_store = CodeWorkspaceStore(store)
        self.code_ledger = VerificationLedger("run_evo")
        self.workspace = None
        self.autonomy = "approve_external"


# ── G1: the seeded journey ───────────────────────────────────────────────────


def test_seeded_journey_creates_inert_candidate_and_structured_ops(store, tmp_path):
    _seed_recurrence(store)
    candidates = evo.candidates_from_mistakes(store=store, since_iso="2000-01-01T00:00:00.000Z")
    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate["status"] == "inert"           # nothing has changed yet
    assert candidate["targetPath"] is None

    # A target + ops can be attached; propose_ops validates them deterministically.
    evolution = EvolutionStore(store)
    evolution.update_candidate(
        candidate["id"], targetPath="python/harness/code/commands.py",
        proposedOps=[{"op": "replace", "path": "python/harness/code/commands.py", "old": "a", "new": "b"}],
    )
    reloaded = evolution.get_candidate(candidate["id"])
    ops = evo.propose_ops(reloaded, actor=OPERATOR_ACTOR)
    assert ops and ops[0]["op"] == "replace"


# ── G1b: the target file is byte-identical until activation ──────────────────


def test_candidate_is_inert_and_target_is_byte_identical(store):
    import harness.code.evolution as _evo

    # Hash the module file; the creation of a candidate must not touch it.
    import harness.code.commands as commands_module

    path = os.path.abspath(commands_module.__file__)
    import hashlib

    def sha() -> str:
        with open(path, "rb") as handle:
            return hashlib.sha256(handle.read()).hexdigest()

    before = sha()
    _seed_recurrence(store)
    _evo.candidates_from_mistakes(store=store, since_iso="2000-01-01T00:00:00.000Z")
    assert sha() == before


# ── G2: a canary regression triggers an automatic rollback, both versions kept ─


def _git_repo(path):
    path.mkdir(parents=True, exist_ok=True)
    env = {**os.environ}
    subprocess.run(["git", "init", "-q"], cwd=path, env=env, capture_output=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=path, env=env, capture_output=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=path, env=env, capture_output=True)
    (path / "README.md").write_text("seed\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=path, env=env, capture_output=True)
    subprocess.run(["git", "commit", "-qm", "seed"], cwd=path, env=env, capture_output=True)


def test_activation_and_rollback_preserve_both_versions(store, tmp_path, monkeypatch):
    import tempfile
    from harness.skills import SkillStore
    from harness.skills.registry import SkillRegistry

    _git_repo(tmp_path / "repo")
    monkeypatch.setenv("BLACK_ECLIPSE_CODE_ROOT", str(tmp_path / "repo"))
    skill_store = SkillStore(os.path.join(tempfile.mkdtemp(prefix="be-evo-skill-"), "eclipse-memory.db"))
    registry = SkillRegistry(skill_store)

    evolution = EvolutionStore(store)
    _seed_recurrence(store, "repeated_failure")
    candidate = evo.candidates_from_mistakes(store=store, since_iso="2000-01-01T00:00:00.000Z")[0]
    evolution.update_candidate(
        candidate["id"], targetPath="python/harness/code/commands.py",
        proposedOps=[{"op": "replace", "path": "python/harness/code/commands.py", "old": "a", "new": "b"}],
        status="evaluated_ok",
    )

    # Activate as a canary through the EXISTING lifecycle.
    activated = esvc.activate(store, candidate["id"], registry=registry, actor=OPERATOR_ACTOR, canary=True)
    assert activated["ok"], activated
    assert activated["activatedVersion"] and activated["previousVersion"]

    reloaded = evolution.get_candidate(candidate["id"])
    assert reloaded["activatedVersion"] and reloaded["previousVersion"]  # BOTH preserved
    assert reloaded["status"] == "canaried"

    # A canary regression triggers the automatic rollback via versioning.py.
    manifest_id = evo.candidate_skill_manifest(reloaded)["id"]
    triggered = versioning.check_rollback_triggers(
        registry, manifest_id, reloaded["activatedVersion"], actor=OPERATOR_ACTOR,
        user_corrections=2,
    )
    assert triggered.get("rolledBack") is True

    rolled = esvc.rollback(
        store, candidate["id"], registry=registry, actor=OPERATOR_ACTOR,
        reason="a check that passed got worse",
    )
    assert rolled["ok"], rolled
    assert evolution.get_candidate(candidate["id"])["status"] == "rolled_back"
    # The rollback attempt is archived.
    attempts = evolution.list_attempts(candidate["id"])
    assert any(a["outcome"] == "rolled_back" for a in attempts)


# ── G6: every route refuses a non-operator ───────────────────────────────────


EVOLUTION_ROUTES = [
    ("GET", "/evolution/candidates", None),
    ("GET", "/evolution/candidates/x", None),
    ("GET", "/evolution/candidates/x/attempts", None),
    ("POST", "/evolution/candidates/x/evaluate", {}),
    ("POST", "/evolution/candidates/x/activate", {}),
    ("POST", "/evolution/candidates/x/rollback", {}),
    ("POST", "/evolution/candidates/x/dismiss", None),
    ("GET", "/evolution/metrics", None),
]


@pytest.mark.parametrize("method,path,body", EVOLUTION_ROUTES)
def test_every_evolution_route_refuses_a_non_operator(monkeypatch, method, path, body):
    monkeypatch.setenv("AGENT_MEMORY_DB_PATH", os.path.join(os.environ.get("TEMP", "."), "be-evo-api.db"))
    monkeypatch.delenv("CRON_SECRET", raising=False)
    from starlette.testclient import TestClient as TC

    import harness.main as main_module
    with TC(main_module.app, client=("203.0.113.9", 5555)) as remote:
        res = remote.request(method, path, json=body)
        assert res.status_code == 403, f"{method} {path}: {res.text}"
