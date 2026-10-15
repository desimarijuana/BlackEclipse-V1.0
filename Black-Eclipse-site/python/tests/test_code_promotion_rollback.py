"""Phase 15+ — putting a promoted change back (inverse promotion).

`apply_promotion` now captures the ORIGINAL contents before it writes, so a
landed change can be put back exactly: a file the promotion CREATED is removed, a
file it EDITED is restored, and a file it DELETED is recreated. Both versions
survive (the backup directory is kept). A restored file that changed after the
promotion is refused, never clobbered.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from harness.code import promotion, worktree
from harness.code.promotion import PromotionError
from test_code_promotion import _git_fixture, _prepare, _write


@pytest.fixture()
def repo(tmp_path, monkeypatch):
    root = _git_fixture(tmp_path)
    monkeypatch.setenv("BLACK_ECLIPSE_CODE_ROOT", str(root))
    yield root
    shutil.rmtree(root / worktree.SCRATCH_RELPATH, ignore_errors=True)


def _promote(repo: Path, run_id: str, edits: dict) -> tuple:
    _ws, store = _prepare(repo, run_id, edits)
    preview = promotion.build_preview(run_id, code_store=store, checkout_root=repo)
    result = promotion.apply_promotion(preview)
    return preview, result


def test_apply_captures_a_rollback_id_and_backup(repo):
    preview, result = _promote(repo, "rb1", {"src/app.py": "print('world')\n"})
    assert result["rollbackId"] == preview["previewDigest"]
    backup = repo / promotion.ROLLBACK_ROOT_RELPATH / result["rollbackId"]
    assert (backup / "manifest.json").is_file()


def test_rollback_restores_edit_create_and_delete(repo):
    preview, result = _promote(repo, "rb2", {
        "src/app.py": "print('world')\n",     # overwrite
        "src/added.py": "ADDED = 1\n",         # create
        "docs/valuation.md": None,             # delete
    })
    assert (repo / "src" / "app.py").read_text(encoding="utf-8") == "print('world')\n"
    assert (repo / "src" / "added.py").exists()
    assert not (repo / "docs" / "valuation.md").exists()

    out = promotion.rollback_promotion(result["rollbackId"], checkout_root=repo)
    assert out["ok"] is True and out["filesChanged"] == 3
    # Back to the ORIGINAL state.
    assert (repo / "src" / "app.py").read_text(encoding="utf-8") == "print('hello')\n"
    assert not (repo / "src" / "added.py").exists()
    assert (repo / "docs" / "valuation.md").read_text(encoding="utf-8") == "# Valuation\n\nold model\n"
    # The backup is kept (both versions survive).
    assert (repo / promotion.ROLLBACK_ROOT_RELPATH / result["rollbackId"]).is_dir()


def test_rollback_without_a_saved_version_is_refused(repo):
    with pytest.raises(PromotionError) as exc:
        promotion.rollback_promotion("deadbeefdeadbeef", checkout_root=repo)
    assert exc.value.code == "PROMOTION_NO_ROLLBACK"


def test_rollback_refuses_when_the_file_changed_after_the_promotion(repo):
    _preview, result = _promote(repo, "rb4", {"src/app.py": "print('world')\n"})
    # Someone edits the landed file afterwards.
    _write(repo / "src" / "app.py", "print('someone else changed this')\n")
    with pytest.raises(PromotionError) as exc:
        promotion.rollback_promotion(result["rollbackId"], checkout_root=repo)
    assert exc.value.code == "PROMOTION_BASE_CHANGED"
    # The later edit is preserved, never clobbered by the rollback.
    assert (repo / "src" / "app.py").read_text(encoding="utf-8") == "print('someone else changed this')\n"


def test_a_failed_apply_leaves_no_backup_directory(repo):
    # A protected path is refused at preview; nothing is written and no backup
    # dir is created for it.
    _ws, store = _prepare(repo, "rb5", {"python/harness/code/policy.py": "# tampered\n"})
    with pytest.raises(PromotionError):
        promotion.build_preview("rb5", code_store=store, checkout_root=repo)
    promotions_dir = repo / promotion.ROLLBACK_ROOT_RELPATH
    assert not promotions_dir.exists() or not any(promotions_dir.iterdir())
