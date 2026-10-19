"""RSL R4 — a prepared code candidate reaches the existing promotion preview."""

from __future__ import annotations

import shutil
import subprocess
import uuid
from pathlib import Path

import pytest

from harness.code import worktree
from harness.code.evolution_store import EvolutionStore
from harness.code.store import CodeWorkspaceStore
from harness.persistence import AgentMemoryStore
from harness.self_improvement.landing import RSLLandingError, prepare


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="")


def _git_fixture(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    _write(repo / "python" / "harness" / "foo.py", "VALUE = 1\n")
    _write(repo / "python" / "harness" / "code" / "policy.py", "# frozen authority\n")
    _write(repo / ".gitignore", ".black-eclipse/\n")
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True)
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-qm", "init"], cwd=repo, check=True)
    return repo


@pytest.fixture()
def repo(tmp_path, monkeypatch):
    root = _git_fixture(tmp_path)
    monkeypatch.setenv("BLACK_ECLIPSE_CODE_ROOT", str(root))
    yield root
    shutil.rmtree(root / worktree.SCRATCH_RELPATH, ignore_errors=True)


class _Service:
    def __init__(self, store: AgentMemoryStore) -> None:
        self.store = store
        self.code_store = CodeWorkspaceStore(store)

    def get_run(self, run_id: str):
        return self.store.get_run(run_id)


@pytest.fixture()
def service(tmp_path):
    store = AgentMemoryStore(str(tmp_path / "agent-memory.db"))
    try:
        yield _Service(store)
    finally:
        store.close()


def _candidate(
    service: _Service, *, target: str = "python/harness/foo.py",
    old: str = "VALUE = 1", new: str = "VALUE = 2",
) -> dict:
    return EvolutionStore(service.store).save_candidate({
        "signature": f"sig-{uuid.uuid4().hex}",
        "sourceCategory": "timeout",
        "observedCount": 3,
        "problemStatement": "Eclipse hit the same problem 3 times: the bound that timed out.",
        "targetPath": target,
        "proposedOps": [{
            "op": "replace", "path": target, "old": old, "new": new,
            "reason": "RSL fixture",
        }],
        "status": "evaluated_ok",
    })


def test_prepare_registers_a_run_and_a_promotion_preview(repo, service):
    candidate = _candidate(service)
    result = prepare(service, candidate["id"])

    assert result["runId"] == f"rsl-{candidate['id']}"
    assert result["preview"]["filesChanged"] == 1
    assert result["preview"]["files"][0]["path"] == "python/harness/foo.py"
    assert result["landing"]["restartRequired"] is True
    assert result["landing"]["authorities"] == []
    assert service.get_run(result["runId"]) is not None

    workspace = service.code_store.list_workspaces(run_id=result["runId"])[0]
    patched = (Path(workspace["root"]) / "python/harness/foo.py").read_text(encoding="utf-8")
    assert "VALUE = 2" in patched


def test_prepare_reuses_a_live_workspace(repo, service):
    candidate = _candidate(service)
    first = prepare(service, candidate["id"])
    second = prepare(service, candidate["id"])
    assert first["preview"]["previewDigest"] == second["preview"]["previewDigest"]
    assert len(service.code_store.list_workspaces(run_id=first["runId"])) == 1


def test_frozen_target_is_refused_before_any_worktree(repo, service):
    candidate = _candidate(
        service, target="python/tests/test_rsl_landing.py",
        old="", new="x",
    )
    with pytest.raises(RSLLandingError) as exc:
        prepare(service, candidate["id"])
    assert exc.value.code == "RSL_FROZEN_TARGET"
    assert service.code_store.list_workspaces(run_id=f"rsl-{candidate['id']}") == []


def test_an_unevaluated_candidate_is_not_landable(repo, service):
    candidate = _candidate(service)
    EvolutionStore(service.store).update_candidate(candidate["id"], status="evaluated_bad")
    with pytest.raises(RSLLandingError) as exc:
        prepare(service, candidate["id"])
    assert exc.value.code == "RSL_NOT_EVALUATED"
    assert service.code_store.list_workspaces(run_id=f"rsl-{candidate['id']}") == []


def test_missing_target_or_ops_is_not_landable(repo, service):
    candidate = EvolutionStore(service.store).save_candidate({
        "signature": f"sig-{uuid.uuid4().hex}",
        "sourceCategory": "timeout",
        "observedCount": 3,
        "problemStatement": "no target",
        "targetPath": None,
        "proposedOps": None,
        "status": "evaluated_ok",
    })
    with pytest.raises(RSLLandingError) as exc:
        prepare(service, candidate["id"])
    assert exc.value.code == "RSL_NOT_LANDABLE"
