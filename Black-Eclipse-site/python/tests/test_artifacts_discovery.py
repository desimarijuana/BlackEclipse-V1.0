"""Terminal/filesystem discovery backstop: files under the bounded workspace
artifact directory are cataloged without an explicit tool call, idempotently."""

from __future__ import annotations

import pytest

from harness.artifacts import ArtifactService, ArtifactStore, LocalArtifactStorage
from harness.persistence import AgentMemoryStore


@pytest.fixture()
def env(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    (workspace / ".black-eclipse" / "artifacts" / "run123").mkdir(parents=True)
    monkeypatch.setattr("harness.code.workspace.default_root", lambda: workspace)
    store = AgentMemoryStore(str(tmp_path / "agent-memory.db"))
    service = ArtifactService(ArtifactStore(store), LocalArtifactStorage(tmp_path / "files"))
    yield workspace, service
    store.close()


def test_discovery_registers_and_is_idempotent(env):
    workspace, service = env
    (workspace / ".black-eclipse" / "artifacts" / "run123" / "out.csv").write_text("a,b\n1,2\n", encoding="utf-8")
    found = service.discover_workspace_artifacts()
    assert len(found) == 1
    assert found[0].name == "out.csv"
    assert found[0].source_type.value == "terminal"
    # A second scan finds nothing new (deduped by checksum+run).
    assert service.discover_workspace_artifacts() == []


def test_discovery_skips_thumbnails(env):
    workspace, service = env
    base = workspace / ".black-eclipse" / "artifacts" / "run123"
    (base / "img.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 20)
    (base / "img.png.thumb.png").write_bytes(b"thumb")
    found = service.discover_workspace_artifacts()
    assert [a.name for a in found] == ["img.png"]


def test_reconcile_with_discover_reports_discovered(env):
    workspace, service = env
    (workspace / ".black-eclipse" / "artifacts" / "run123" / "log.txt").write_text("hello", encoding="utf-8")
    report = service.reconcile(discover=True)
    assert len(report["discovered"]) == 1
