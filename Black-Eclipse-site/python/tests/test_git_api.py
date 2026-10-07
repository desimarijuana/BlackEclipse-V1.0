"""Git HTTP routes — the transport seam.

Reads are operator-gated (loopback or token). Mutations go through the SAME
service the agent tools use (lock + journal), so the UI cannot bypass
authorization. The git service is stubbed for the seam; the engine's own
behaviour is covered by the isolated-repo tests.
"""

from __future__ import annotations

import os
import subprocess
import tempfile

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

os.environ.setdefault("AGENT_MEMORY_DB_PATH", os.path.join(tempfile.mkdtemp(prefix="be-git-api-"), "agent-memory.db"))


class _Outcome:
    def __init__(self, ok=True):
        self.success = ok
        self.operation = "commit"
        self.repository = "/tmp/repo"

    def to_dict(self):
        return {"success": self.success, "operation": self.operation, "repository": self.repository,
                "result": {}, "warnings": []}


class _Journal:
    def list(self, **kwargs):
        return [{"id": "gitop_1", "operation": "commit", "status": "SUCCESS"}]


class _StubGit:
    journal = _Journal()

    def info(self, root):
        return {"is_repository": True, "root": str(root), "branch": "main"}

    def stage(self, repo, paths, all=False, run_id=None):
        return _Outcome()

    def commit(self, repo, message, amend=False, allow_secrets=False, **kw):
        return _Outcome()


class _StubService:
    git = _StubGit()


@pytest.fixture()
def client(tmp_path, monkeypatch):
    import harness.routers.git as git_router

    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=False)
    monkeypatch.setenv("BLACK_ECLIPSE_CODE_ROOT", str(repo))
    monkeypatch.setattr(git_router, "service", _StubService())
    app = FastAPI()
    app.include_router(git_router.router)
    return TestClient(app)


def test_git_info_is_readable_on_loopback(client):
    response = client.get("/git/info")
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["is_repository"] is True


def test_git_status_returns_readers_output(client):
    response = client.get("/git/status")
    assert response.status_code == 200
    assert response.json()["success"] is True


def test_git_stage_and_commit_mutations(client):
    staged = client.post("/git/stage", json={"paths": ["a.txt"]})
    assert staged.status_code == 200 and staged.json()["success"] is True
    committed = client.post("/git/commit", json={"message": "add a"})
    assert committed.status_code == 200 and committed.json()["success"] is True


def test_git_journal_lists_entries(client):
    response = client.get("/git/journal")
    assert response.status_code == 200
    assert response.json()["entries"][0]["operation"] == "commit"


def test_git_routes_require_operator_from_remote(monkeypatch):
    # A non-loopback caller without the operator token is refused at the seam.
    import harness.routers.git as git_router
    from harness import deps

    monkeypatch.setattr(deps, "_is_loopback", lambda request: False)
    app = FastAPI()
    app.include_router(git_router.router)
    remote = TestClient(app, client=("203.0.113.9", 5000))
    assert remote.get("/git/info").status_code in (401, 403)
