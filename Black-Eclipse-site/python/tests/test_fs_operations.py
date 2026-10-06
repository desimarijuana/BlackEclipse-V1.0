"""File System subsystem — basic operations + security.

Covers create/read/write/delete/move/copy/rename/mkdir/rmdir, then the security
matrix: traversal, absolute escape, symlink/junction escape, protected and
ignored paths, and the workspace boundary. Codes are asserted distinct.
"""

from __future__ import annotations

import os

import pytest

from harness.code.fs import errors as err
from harness.skills.permissions import Actor

from fs_helpers import make_escape_link, make_service, make_ws, tree


# ── basic operations ────────────────────────────────────────────────────────


def test_create_read_write_delete(tmp_path):
    root = tree(tmp_path)
    svc = make_service(root)
    svc.create_file("src/new.py", "x = 1\n")
    assert (root / "src" / "new.py").read_text(encoding="utf-8") == "x = 1\n"
    assert svc.read_file("src/new.py", line_numbers=False)["lines"] == ["x = 1"]
    svc.write_file("src/new.py", "x = 2\n")
    assert (root / "src" / "new.py").read_text(encoding="utf-8") == "x = 2\n"
    svc.delete_file("src/new.py")
    assert not (root / "src" / "new.py").exists()


def test_create_refuses_existing_without_overwrite(tmp_path):
    root = tree(tmp_path)
    svc = make_service(root)
    with pytest.raises(err.FsError) as exc:
        svc.create_file("src/app.py", "x")
    assert exc.value.code == err.FILE_EXISTS
    assert (root / "src" / "app.py").read_text(encoding="utf-8").startswith("alpha")


def test_create_overwrite_is_explicit(tmp_path):
    root = tree(tmp_path)
    svc = make_service(root)
    svc.create_file("src/app.py", "replaced\n", overwrite=True)
    assert (root / "src" / "app.py").read_text(encoding="utf-8") == "replaced\n"


def test_write_default_refuses_a_missing_file(tmp_path):
    root = tree(tmp_path)
    svc = make_service(root)
    with pytest.raises(err.FsError) as exc:
        svc.write_file("src/missing.py", "x", create_if_missing=False, overwrite=False)
    assert exc.value.code == err.PATH_NOT_FOUND


def test_write_stale_hash_refused(tmp_path):
    root = tree(tmp_path)
    svc = make_service(root)
    with pytest.raises(err.FsError) as exc:
        svc.write_file("src/app.py", "x", expected_hash="0" * 64)
    assert exc.value.code == err.STALE_FILE
    assert exc.value.details["actualHash"] != "0" * 64


def test_delete_refuses_a_directory(tmp_path):
    root = tree(tmp_path)
    svc = make_service(root)
    with pytest.raises(err.FsError) as exc:
        svc.delete_file("src")
    assert exc.value.code == err.NOT_A_FILE


def test_move_copy_rename(tmp_path):
    root = tree(tmp_path)
    svc = make_service(root)
    svc.move_file("src/other.py", "src/moved.py")
    assert (root / "src" / "moved.py").exists() and not (root / "src" / "other.py").exists()
    svc.copy_file("src/moved.py", "docs/copy.py")
    assert (root / "docs" / "copy.py").exists()
    svc.rename_file("docs/copy.py", "renamed.py")
    assert (root / "docs" / "renamed.py").exists()


def test_move_refuses_existing_without_overwrite(tmp_path):
    root = tree(tmp_path)
    svc = make_service(root)
    with pytest.raises(err.FsError) as exc:
        svc.move_file("src/other.py", "src/app.py")
    assert exc.value.code == err.FILE_EXISTS


def test_copy_directory_recursive(tmp_path):
    root = tree(tmp_path)
    svc = make_service(root)
    svc.copy_file("src", "src_copy")
    assert (root / "src_copy" / "app.py").exists()
    assert (root / "src_copy" / "nested" / "util.py").exists()


def test_directory_create_and_delete(tmp_path):
    root = tree(tmp_path)
    svc = make_service(root)
    svc.create_directory("a/b/c")
    assert (root / "a" / "b" / "c").is_dir()
    # A non-empty parent needs recursive removal; the empty leaf does not.
    svc.delete_directory("a/b/c")
    assert not (root / "a" / "b" / "c").exists()
    svc.delete_directory("a", recursive=True)
    assert not (root / "a").exists()


def test_delete_directory_refuses_non_empty_without_recursive(tmp_path):
    root = tree(tmp_path)
    svc = make_service(root)
    with pytest.raises(err.FsError) as exc:
        svc.delete_directory("src")
    assert exc.value.code == err.PERMISSION_DENIED
    # Nothing was removed.
    assert (root / "src" / "app.py").exists()


def test_delete_directory_recursive_removes(tmp_path):
    root = tree(tmp_path)
    svc = make_service(root)
    svc.delete_directory("src", recursive=True)
    assert not (root / "src").exists()


def test_delete_directory_refuses_a_protected_member(tmp_path):
    root = tree(tmp_path)
    (root / "src" / ".env").write_text("SECRET=1", encoding="utf-8")
    svc = make_service(root)
    with pytest.raises(err.FsError) as exc:
        svc.delete_directory("src", recursive=True)
    assert exc.value.code == err.PERMISSION_DENIED
    assert (root / "src" / "app.py").exists()


def test_list_directory_is_ignore_aware_and_bounded(tmp_path):
    root = tree(tmp_path)
    svc = make_service(root)
    result = svc.list_directory(".", recursive=True, max_depth=4)
    paths = {e["path"] for e in result["entries"]}
    assert "src/app.py" in paths
    assert not any(p.startswith("node_modules") for p in paths)


def test_list_directory_pagination(tmp_path):
    root = tree(tmp_path)
    svc = make_service(root)
    page = svc.list_directory(".", recursive=True, max_depth=4, limit=1, offset=1)
    assert page["offset"] == 1
    assert page["count"] == 1


def test_read_region_by_lines(tmp_path):
    root = tree(tmp_path)
    svc = make_service(root)
    result = svc.read_file("src/app.py", start_line=2, end_line=2)
    assert result["lines"] == ["beta"]
    assert result["startLine"] == 2


# ── security: the escape matrix ─────────────────────────────────────────────


def test_traversal_refused(tmp_path):
    root = tree(tmp_path)
    svc = make_service(root)
    with pytest.raises(err.FsError) as exc:
        svc.read_file("../outside.txt")
    assert exc.value.code == "PATH_TRAVERSAL"


def test_absolute_outside_refused(tmp_path):
    root = tree(tmp_path)
    outside = tmp_path / "outside.txt"
    outside.write_text("secret", encoding="utf-8")
    svc = make_service(root)
    with pytest.raises(err.FsError) as exc:
        svc.read_file(str(outside))
    assert exc.value.code == err.PATH_NOT_ALLOWED


def test_absolute_escape_on_write_refused(tmp_path):
    root = tree(tmp_path)
    svc = make_service(root)
    with pytest.raises(err.FsError) as exc:
        svc.create_file(str(tmp_path / "evil.txt"), "x")
    assert exc.value.code in (err.PATH_NOT_ALLOWED, "PATH_TRAVERSAL")


def test_symlink_escape_refused(tmp_path):
    root = tree(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("secret", encoding="utf-8")
    if not make_escape_link(root / "escape", outside):
        pytest.skip("this host allows neither symlinks nor junctions")
    svc = make_service(root)
    with pytest.raises(err.FsError) as exc:
        svc.read_file("escape/secret.txt")
    assert exc.value.code == "SYMLINK_ESCAPE"


def test_protected_paths_refused(tmp_path):
    root = tree(tmp_path)
    (root / "jdds.db").write_bytes(b"\x00vault")
    (root / ".env").write_text("SECRET=1", encoding="utf-8")
    svc = make_service(root)
    for rel in ("jdds.db", ".env"):
        with pytest.raises(err.FsError) as exc:
            svc.read_file(rel)
        assert exc.value.code == "PROTECTED_PATH"
    with pytest.raises(err.FsError) as exc:
        svc.write_file("jdds.db", "x")
    assert exc.value.code == "PROTECTED_PATH"


def test_ignored_path_refused(tmp_path):
    root = tree(tmp_path)
    svc = make_service(root)
    with pytest.raises(err.FsError) as exc:
        svc.read_file("node_modules/pkg.js")
    assert exc.value.code == "IGNORED_PATH"


def test_plan_only_can_read_but_not_write(tmp_path):
    root = tree(tmp_path)
    svc = make_service(root, autonomy="plan_only")
    assert svc.read_file("src/app.py")["status"] == "ok"
    with pytest.raises(err.FsError) as exc:
        svc.create_file("src/new.py", "x")
    assert exc.value.code == err.PERMISSION_DENIED


def test_unknown_autonomy_writes_nothing(tmp_path):
    root = tree(tmp_path)
    svc = make_service(root, autonomy="nonsense")
    with pytest.raises(err.FsError) as exc:
        svc.create_file("src/new.py", "x")
    assert exc.value.code == err.PERMISSION_DENIED


def test_config_narrowing_denies_delete(tmp_path):
    root = tree(tmp_path)
    svc = make_service(root, autonomy="edit_verify", config={"delete": False})
    with pytest.raises(err.FsError) as exc:
        svc.delete_file("src/other.py")
    assert exc.value.code == err.PERMISSION_DENIED
    # A capability the config does not deny still works.
    svc.replace_text("src/app.py", "alpha", "ALPHA", expected_occurrences=1)


def test_no_workspace_is_unbound(tmp_path):
    from harness.code.fs.service import FileSystemService

    svc = FileSystemService(None, None, Actor(id="x"))
    with pytest.raises(err.FsError) as exc:
        svc.read_file("x")
    assert exc.value.code == err.WORKSPACE_UNBOUND
