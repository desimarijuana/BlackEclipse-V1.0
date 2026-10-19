"""Phase 15 (ADR-H119) — confirmed promotion: a change lands only with consent.

A code run writes into a DISPOSABLE copy; nothing reaches the user's real folder
until they preview the exact file set and confirm it, and never if either copy
changed since the preview. These tests build a git fixture repo, allocate a real
worktree, change it, and prove:

  * the preview names the exact file set with before/after hashes;
  * a protected path can never be promoted (refused up front);
  * applying writes to the CHECKOUT (the whole point) and only the previewed files;
  * a target that changed since the preview is refused (nothing written);
  * a preview that changed under the operator is refused;
  * no change / an already-direct run are honest no-ops.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from harness.code import promotion, worktree
from harness.code import patch as patch_mod
from harness.code.policy import WorkspaceBinding
from harness.code.promotion import PromotionError
from harness.code.workspace import ResolvedWorkspace
from harness.skills.permissions import Actor


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="")


def _git_fixture(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "python" / "harness" / "code").mkdir(parents=True)
    _write(repo / "src" / "app.py", "print('hello')\n")
    _write(repo / "docs" / "valuation.md", "# Valuation\n\nold model\n")
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


class _FakeStore:
    """Minimal stand-in for the CodeWorkspace table read the preview needs."""

    def __init__(self, rows: list[dict]):
        self._rows = rows

    def list_workspaces(self, *, run_id=None, limit=100, scope_id=None):
        return [r for r in self._rows if r.get("runId") == run_id][:limit]


def _row(ws, run_id: str) -> dict:
    return {
        "id": ws.id, "root": str(ws.root), "strategy": ws.strategy,
        "baseRevision": ws.base_revision, "releasedAt": None, "runId": run_id,
    }


def _prepare(repo: Path, run_id: str, edits: dict[str, str]) -> tuple:
    """Allocate a worktree, apply `edits` (path→text; None = delete), register it."""
    ws = worktree.allocate(base_revision="HEAD")
    for rel, text in edits.items():
        target = ws.root / rel
        if text is None:
            if target.exists():
                target.unlink()
        else:
            _write(target, text)
    store = _FakeStore([_row(ws, run_id)])
    return ws, store


# ── preview ─────────────────────────────────────────────────────────────────


def test_preview_names_the_exact_change(repo):
    ws, store = _prepare(repo, "run1", {
        "src/app.py": "print('world')\n",
        "src/new.py": "NEW = True\n",
    })
    preview = promotion.build_preview("run1", code_store=store, checkout_root=repo)
    files = {f["path"]: f for f in preview["files"]}
    assert set(files) == {"src/app.py", "src/new.py"}
    assert files["src/app.py"]["op"] == "overwrite"
    assert files["src/new.py"]["op"] == "create"
    assert files["src/app.py"]["beforeHash"] and files["src/app.py"]["afterHash"]
    assert files["src/new.py"]["beforeHash"] is None
    assert preview["filesChanged"] == 2 and preview["previewDigest"]


def test_preview_refuses_a_protected_path(repo):
    ws, store = _prepare(repo, "run2", {
        "python/harness/code/policy.py": "# tampered\n",
    })
    with pytest.raises(PromotionError) as exc:
        promotion.build_preview("run2", code_store=store, checkout_root=repo)
    assert exc.value.code == "PROMOTION_OUT_OF_SCOPE"


def test_preview_no_change(repo):
    ws, store = _prepare(repo, "run3", {})
    with pytest.raises(PromotionError) as exc:
        promotion.build_preview("run3", code_store=store, checkout_root=repo)
    assert exc.value.code == "PROMOTION_NO_CHANGE"


def test_preview_refuses_already_direct(repo):
    direct = worktree.allocate(direct=True)
    store = _FakeStore([_row(direct, "run4")])
    with pytest.raises(PromotionError) as exc:
        promotion.build_preview("run4", code_store=store, checkout_root=repo)
    assert exc.value.code == "PROMOTION_ALREADY_DIRECT"


# ── apply: the change lands in the checkout ─────────────────────────────────


def test_apply_lands_in_the_checkout(repo):
    ws, store = _prepare(repo, "run5", {
        "src/app.py": "print('world')\n",
        "src/added.py": "ADDED = 1\n",
        "docs/valuation.md": None,  # delete
    })
    preview = promotion.build_preview("run5", code_store=store, checkout_root=repo)
    result = promotion.apply_promotion(preview)
    assert result["ok"] is True and result["filesChanged"] == 3
    # The REAL checkout now has the change.
    assert (repo / "src" / "app.py").read_text(encoding="utf-8") == "print('world')\n"
    assert (repo / "src" / "added.py").read_text(encoding="utf-8") == "ADDED = 1\n"
    assert not (repo / "docs" / "valuation.md").exists()


def test_apply_refuses_when_the_target_changed_since_preview(repo):
    ws, store = _prepare(repo, "run6", {"src/app.py": "print('world')\n"})
    preview = promotion.build_preview("run6", code_store=store, checkout_root=repo)
    # The user edited the same file after the preview, before confirming.
    _write(repo / "src" / "app.py", "print('user changed this')\n")
    with pytest.raises(PromotionError) as exc:
        promotion.apply_promotion(preview)
    assert exc.value.code == "PROMOTION_BASE_CHANGED"
    # Nothing was written: the user's edit is intact.
    assert (repo / "src" / "app.py").read_text(encoding="utf-8") == "print('user changed this')\n"


def test_apply_refuses_when_the_copy_changed_since_preview(repo):
    ws, store = _prepare(repo, "run7", {"src/app.py": "print('world')\n"})
    preview = promotion.build_preview("run7", code_store=store, checkout_root=repo)
    # The prepared copy changed under the operator after the preview.
    _write(ws.root / "src" / "app.py", "print('tampered')\n")
    with pytest.raises(PromotionError) as exc:
        promotion.apply_promotion(preview)
    assert exc.value.code == "PROMOTION_PREVIEW_STALE"
    assert (repo / "src" / "app.py").read_text(encoding="utf-8") == "print('hello')\n"


def test_preview_digest_changes_when_the_set_changes(repo):
    ws, store = _prepare(repo, "run8", {"src/app.py": "print('a')\n"})
    first = promotion.build_preview("run8", code_store=store, checkout_root=repo)
    _write(ws.root / "src" / "app.py", "print('b')\n")
    second = promotion.build_preview("run8", code_store=store, checkout_root=repo)
    assert first["previewDigest"] != second["previewDigest"]


# ── the overwrite op itself (unit) ──────────────────────────────────────────


def test_overwrite_op_replaces_whole_file_with_base_check(tmp_path):
    root = tmp_path / "ws"
    root.mkdir()
    _write(root / "f.txt", "one\ntwo\n")
    real = Path(os.path.realpath(root))
    binding = WorkspaceBinding(id="ws_t", root=real, base_revision="x", strategy="checkout")
    rws = ResolvedWorkspace(id="ws_t", root=real, base_revision="x", strategy="checkout", binding=binding)
    actor = Actor(id="coder", operator=False, workspace_id="ws_t", autonomy="edit_verify")
    before = patch_mod.hashlib.sha256("one\ntwo\n".encode()).hexdigest()
    ops = patch_mod.parse_patch({"operations": [
        {"op": "overwrite", "path": "f.txt", "reason": "r", "content": "three\n", "expectHash": before},
    ]})
    result = patch_mod.apply(rws, ops, binding=binding, actor=actor)
    assert result["ok"] and (root / "f.txt").read_text(encoding="utf-8") == "three\n"

    # A stale base is refused and nothing is written.
    _write(root / "f.txt", "user wrote this\n")
    with pytest.raises(patch_mod.PatchError) as exc:
        patch_mod.apply(rws, ops, binding=binding, actor=actor)
    assert exc.value.code == "PATCH_BASE_MISMATCH"
    assert (root / "f.txt").read_text(encoding="utf-8") == "user wrote this\n"


# ── the route seam: preview -> approve -> apply ──────────────────────────────


class _FakeApprovals:
    """A dict-backed stand-in for the single-use ApprovalStore (route seam only)."""

    def __init__(self) -> None:
        self._rows: dict[str, dict] = {}
        self._n = 0

    def request_kind(self, **kw):
        self._n += 1
        rid = f"appr_{self._n}"
        row = {
            "id": rid, "kind": kw["kind"], "status": "pending",
            "argsDigest": kw["digest"], "workspaceId": kw.get("workspace_id"),
            "actionSummary": kw.get("action_summary"),
        }
        self._rows[rid] = row
        return row

    def get(self, rid):
        return self._rows.get(rid)

    def approve(self, rid):
        self._rows[rid]["status"] = "approved"

    def consume_kind(self, *, kind, request_key, digest, workspace_id=None):
        for row in self._rows.values():
            if (row["kind"] == kind and row["status"] == "approved"
                    and row["argsDigest"] == digest
                    and (workspace_id is None or row.get("workspaceId") == workspace_id)):
                row["status"] = "consumed"
                return dict(row)
        return None


class _StubPromoteService:
    def __init__(self, code_store, approvals, *, run_exists=True) -> None:
        self.code_store = code_store
        self.approvals = approvals
        self._run_exists = run_exists

    def get_run(self, run_id):
        return {"id": run_id} if self._run_exists else None


def _client(monkeypatch, service):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from harness.routers import code as code_router

    monkeypatch.setattr(code_router, "service", service, raising=False)
    app = FastAPI()
    app.include_router(code_router.router)
    return TestClient(app)


def test_route_preview_approve_apply(repo, monkeypatch):
    ws, store = _prepare(repo, "run9", {"src/app.py": "print('routed')\n"})
    approvals = _FakeApprovals()
    client = _client(monkeypatch, _StubPromoteService(store, approvals))

    previewed = client.post("/code/tasks/run9/promote/preview")
    assert previewed.status_code == 200, previewed.text
    body = previewed.json()
    approval_id = body["approval"]["id"]
    digest = body["preview"]["previewDigest"]
    assert body["preview"]["filesChanged"] == 1

    # Not yet approved: applying is refused, nothing is written.
    denied = client.post("/code/tasks/run9/promote", json={"approvalId": approval_id, "previewDigest": digest})
    assert denied.status_code == 403

    approvals.approve(approval_id)
    applied = client.post("/code/tasks/run9/promote", json={"approvalId": approval_id, "previewDigest": digest})
    assert applied.status_code == 200, applied.text
    assert (repo / "src" / "app.py").read_text(encoding="utf-8") == "print('routed')\n"
    # Single-use: a second apply is refused.
    again = client.post("/code/tasks/run9/promote", json={"approvalId": approval_id, "previewDigest": digest})
    assert again.status_code in (403, 409)


def test_route_preview_unknown_task_404(monkeypatch):
    approvals = _FakeApprovals()
    client = _client(monkeypatch, _StubPromoteService(_FakeStore([]), approvals, run_exists=False))
    assert client.post("/code/tasks/missing/promote/preview").status_code == 404


def test_route_refuses_an_authority_change_before_requesting_approval(repo, monkeypatch):
    # Round 4 (W4): the self-host floor refuses its own authority files, and the
    # refusal happens BEFORE a single-use approval is created. `authorizers.py` is
    # an authority path in selfhost.py but not a PROTECTED_PATHS entry, so this
    # exercises the route's self-host check (policy.py is refused even earlier).
    ws, store = _prepare(repo, "run10", {"python/harness/code/authorizers.py": "# changed\n"})
    approvals = _FakeApprovals()
    client = _client(monkeypatch, _StubPromoteService(store, approvals))

    refused = client.post("/code/tasks/run10/promote/preview")
    assert refused.status_code == 403
    assert "SELFHOST_AUTHORITY_REFUSED" in refused.text
    assert approvals._rows == {}  # noqa: SLF001 - the test owns the fake

