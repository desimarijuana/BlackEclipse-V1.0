"""The workspace editor routes (list / read / write) over an approved root.

These drive the REAL router against a REAL temp root, so the confinement is
exercised end to end: a write lands only inside the selected root, and a
protected path (`jdds.db`, `.env`), a traversal, and an absolute outside path are
all refused with HTTP 400 — the editor is a second door to the SAME boundary the
agent tools use, not a weaker one.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

os.environ.setdefault(
    "AGENT_MEMORY_DB_PATH",
    os.path.join(tempfile.mkdtemp(prefix="be-editor-"), "agent-memory.db"),
)


class _StubRootStore:
    def __init__(self, path: str) -> None:
        self._path = path
        self._selected = True

    def selected(self):
        from harness.code.roots import TrustedRoot

        return TrustedRoot(
            id="root_test", path=self._path, label="test",
            created_at="", last_used_at=None, selected=self._selected,
        ) if self._selected else None


class _StubService:
    def __init__(self, root_path: str) -> None:
        self._roots = _StubRootStore(root_path)

    def trusted_root_store(self):
        return self._roots


@pytest.fixture()
def editor_app(tmp_path, monkeypatch):
    root = tmp_path / "proj"
    root.mkdir()
    (root / "src").mkdir()
    (root / "src" / "app.py").write_text("print('hi')\n", encoding="utf-8")

    import harness.routers.workspace as ws_router

    stub = _StubService(str(root))
    monkeypatch.setattr(ws_router, "service", stub, raising=False)
    # `default_root()` reads the env override; point it at the temp root.
    monkeypatch.setenv("BLACK_ECLIPSE_CODE_ROOT", str(root))
    app = FastAPI()
    app.include_router(ws_router.router)
    return TestClient(app), root


def test_list_and_read_and_write(editor_app):
    client, root = editor_app
    listing = client.get("/workspace/files?path=.")
    assert listing.status_code == 200
    names = {e["name"] for e in listing.json()["entries"]}
    assert "src" in names

    read = client.post("/workspace/file/read", json={"path": "src/app.py"})
    assert read.status_code == 200
    assert "print('hi')" in read.json()["content"]

    write = client.post("/workspace/file/write", json={"path": "new/out.txt", "content": "hello"})
    assert write.status_code == 200
    assert (root / "new" / "out.txt").read_text(encoding="utf-8") == "hello"


def test_protected_path_write_is_refused(editor_app):
    client, root = editor_app
    resp = client.post("/workspace/file/write", json={"path": ".env", "content": "SECRET=1"})
    assert resp.status_code == 400
    assert not (root / ".env").exists()


def test_traversal_is_refused(editor_app):
    client, _root = editor_app
    resp = client.post("/workspace/file/read", json={"path": "../escape.txt"})
    assert resp.status_code == 400


def test_absolute_outside_path_is_refused(editor_app):
    client, _root = editor_app
    resp = client.post("/workspace/file/read", json={"path": "/etc/passwd"})
    assert resp.status_code == 400


def test_missing_file_is_refused(editor_app):
    client, _root = editor_app
    resp = client.post("/workspace/file/read", json={"path": "does-not-exist.txt"})
    assert resp.status_code == 400


def test_mkdir_creates_a_folder(editor_app):
    client, root = editor_app
    resp = client.post("/workspace/file/mkdir", json={"path": "new/pkg"})
    assert resp.status_code == 200
    assert (root / "new" / "pkg").is_dir()


def test_browse_mkdir_creates_a_folder_in_the_browsed_directory(editor_app, tmp_path):
    client, _root = editor_app
    parent = tmp_path / "pick"
    parent.mkdir()
    resp = client.post("/workspace/browse/mkdir", json={"path": str(parent), "name": "new project"})
    assert resp.status_code == 200
    assert (parent / "new project").is_dir()


def test_browse_mkdir_refuses_a_path_name(editor_app, tmp_path):
    client, _root = editor_app
    resp = client.post("/workspace/browse/mkdir", json={"path": str(tmp_path), "name": "../escape"})
    assert resp.status_code == 400


def test_delete_removes_a_file(editor_app):
    client, root = editor_app
    (root / "gone.txt").write_text("x", encoding="utf-8")
    resp = client.post("/workspace/file/delete", json={"path": "gone.txt"})
    assert resp.status_code == 200
    assert not (root / "gone.txt").exists()


def test_delete_refuses_a_non_empty_folder(editor_app):
    client, root = editor_app
    (root / "keep" / "inner.txt").parent.mkdir(parents=True, exist_ok=True)
    (root / "keep" / "inner.txt").write_text("x", encoding="utf-8")
    resp = client.post("/workspace/file/delete", json={"path": "keep"})
    assert resp.status_code == 400
    assert (root / "keep" / "inner.txt").exists()
