"""Round 4 (W4) — a verified routing repair reaches the existing promotion card.

A git fixture supplies a tiny `mode.py` with the exact additive-verb anchor. The
proposal (W2) is applied to a REAL disposable worktree, previewed by the SAME
`promotion.build_preview` the Code Tasks route uses, and then landed/rolled back
against the fixture checkout. No real repository content is touched.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from harness.code import promotion, worktree
from harness.persistence import AgentMemoryStore
from harness.code.store import CodeWorkspaceStore
from harness.recovery.routing_landing import RoutingLandingError, prepare
from harness.recovery.routing_repair import propose

_ANCHOR = '    "show", "display", "need", "want",'


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="")


def _git_fixture(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    _write(repo / "python" / "harness" / "ui" / "mode.py",
           f"_ADDITIVE_VERBS = (\n{_ANCHOR}\n)\n")
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

    def propose_routing_repair(self, incident_id: str, *, catalog=None):
        if incident_id != "inc_clock":
            return None
        return propose("my dashboard is missing a latency ribbon").to_dict()


@pytest.fixture()
def service(tmp_path):
    store = AgentMemoryStore(str(tmp_path / "agent-memory.db"))
    try:
        yield _Service(store)
    finally:
        store.close()


def test_prepare_registers_a_run_and_a_promotion_preview(repo, service):
    result = prepare(service, "inc_clock")

    assert result["runId"] == "routing-repair-inc_clock"
    assert result["proposal"]["cause"] == "vocabulary_gap"
    assert result["proposal"]["kind"] == "classifier_rule"
    assert result["preview"]["filesChanged"] == 1
    assert result["preview"]["files"][0]["path"] == "python/harness/ui/mode.py"
    assert result["landing"]["restartRequired"] is True
    assert result["landing"]["authorities"] == []
    # The existing promotion route requires the run row to exist.
    assert service.get_run(result["runId"]) is not None

    workspace = service.code_store.list_workspaces(run_id=result["runId"])[0]
    patched = (Path(workspace["root"]) / "python/harness/ui/mode.py").read_text(encoding="utf-8")
    assert '"missing"' in patched


def test_prepare_reuses_a_live_workspace(repo, service):
    first = prepare(service, "inc_clock")
    second = prepare(service, "inc_clock")
    assert first["preview"]["previewDigest"] == second["preview"]["previewDigest"]
    assert len(service.code_store.list_workspaces(run_id=first["runId"])) == 1


def test_the_prepared_change_lands_and_rolls_back(repo, service):
    result = prepare(service, "inc_clock")
    preview = promotion.build_preview(result["runId"], code_store=service.code_store)

    applied = promotion.apply_promotion(preview)
    assert applied["filesChanged"] == 1
    target = repo / "python/harness/ui/mode.py"
    assert '"missing"' in target.read_text(encoding="utf-8")

    promotion.rollback_promotion(applied["rollbackId"])
    assert '"missing"' not in target.read_text(encoding="utf-8")


def test_an_authority_target_is_refused_before_any_worktree(repo, service, monkeypatch):
    def _authority(incident_id: str, *, catalog=None):
        proposal = propose("my dashboard is missing a latency ribbon").to_dict()
        proposal["targetFile"] = "python/harness/code/policy.py"
        return proposal

    monkeypatch.setattr(service, "propose_routing_repair", _authority)
    with pytest.raises(RoutingLandingError) as exc:
        prepare(service, "inc_clock")
    assert exc.value.code == "SELFHOST_AUTHORITY_REFUSED"
    assert service.code_store.list_workspaces(run_id="routing-repair-inc_clock") == []


def test_a_non_code_proposal_is_not_landable(repo, service, monkeypatch):
    def _catalog_gap(incident_id: str, *, catalog=None):
        return propose("I would love a latency ribbon on my dashboard").to_dict()

    monkeypatch.setattr(service, "propose_routing_repair", _catalog_gap)
    with pytest.raises(RoutingLandingError) as exc:
        prepare(service, "inc_clock")
    assert exc.value.code == "ROUTING_REPAIR_NOT_LANDABLE"


def test_a_missing_incident_is_404(repo, service):
    with pytest.raises(RoutingLandingError) as exc:
        prepare(service, "inc_missing")
    assert exc.value.code == "ROUTING_INCIDENT_NOT_FOUND"
