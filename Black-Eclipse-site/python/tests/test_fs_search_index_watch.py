"""File System subsystem — search, symbols, references, metadata, index, watch.

Also exercises the tools through the ONE registry so validation, permission and
result bounding are covered (not just the service).
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from pathlib import Path

import pytest

from harness.code.fs import errors as err
from harness.code.fs.index import WorkspaceIndex
from harness.code.fs.watch import WorkspaceWatcher

from fs_helpers import make_service, make_ws, tree


# ── search ──────────────────────────────────────────────────────────────────


def test_search_text_literal_and_regex(tmp_path):
    root = tree(tmp_path)
    svc = make_service(root)
    literal = svc.search_text("calculateTotal")
    assert literal["engine"] in ("ripgrep", "python-scan")
    assert literal["count"] >= 1
    assert literal["matches"][0]["path"].endswith("util.py")
    regex = svc.search_text(r"def\s+\w+", regex=True)
    assert regex["count"] >= 1


def test_search_text_ignore_aware(tmp_path):
    root = tree(tmp_path)
    svc = make_service(root)
    result = svc.search_text("module.exports")
    assert result["count"] == 0  # node_modules is ignored
    included = svc.search_text("module.exports", include_ignored=True)
    assert included["count"] >= 1


def test_search_text_case_sensitivity(tmp_path):
    root = tree(tmp_path)
    (root / "lower.txt").write_text("zeta\n", encoding="utf-8")
    (root / "upper.txt").write_text("ZETA\n", encoding="utf-8")
    svc = make_service(root)
    insensitive = svc.search_text("zeta", case_sensitive=False)
    assert insensitive["count"] == 2
    exact = svc.search_text("zeta", case_sensitive=True)
    assert exact["count"] == 1
    assert exact["matches"][0]["path"] == "lower.txt"


def test_search_text_whole_word(tmp_path):
    root = tree(tmp_path)
    (root / "t.txt").write_text("cat category\n", encoding="utf-8")
    svc = make_service(root)
    assert svc.search_text("cat", whole_word=True)["count"] == 1


def test_search_files_and_find_files(tmp_path):
    root = tree(tmp_path)
    svc = make_service(root)
    assert svc.search_files("*.py")["count"] >= 3
    assert svc.find_files(extensions=[".md"])["count"] == 1
    assert svc.find_files(extensions=[".py"], exclude=["nested/*"])["count"] >= 2


def test_find_files_directories_only(tmp_path):
    root = tree(tmp_path)
    svc = make_service(root)
    dirs = svc.find_files(directories_only=True)["files"]
    paths = {entry["path"] for entry in dirs}
    assert "src" in paths and "src/nested" in paths
    assert all(entry["type"] == "dir" for entry in dirs)


def test_search_invalid_regex_refused(tmp_path):
    root = tree(tmp_path)
    svc = make_service(root)
    with pytest.raises(err.FsError) as exc:
        svc.search_text("([unclosed", regex=True)
    assert exc.value.code == err.SEARCH_FAILED


# ── symbols + references ────────────────────────────────────────────────────


def test_search_symbols_python_ast(tmp_path):
    root = tree(tmp_path)
    svc = make_service(root)
    result = svc.search_symbols("calculateTotal")
    assert result["engine"] == "ast+regex"
    assert result["count"] == 1
    assert result["symbols"][0]["kind"] == "function"


def test_search_symbols_by_kind_and_language(tmp_path):
    root = tree(tmp_path)
    (root / "src" / "types.ts").write_text(
        "export function foo() {}\nexport class Bar {}\nexport interface Baz {}\n",
        encoding="utf-8",
    )
    svc = make_service(root)
    classes = svc.search_symbols("Bar", kinds=["class"])
    assert classes["count"] == 1
    functions = svc.search_symbols("foo", language="typescript")
    assert functions["count"] == 1


def test_find_references_regex_scan(tmp_path):
    root = tree(tmp_path)
    (root / "src" / "uses.py").write_text("from util import calculateTotal\n", encoding="utf-8")
    svc = make_service(root)
    result = svc.find_references("calculateTotal")
    assert result["count"] >= 2


# ── metadata / hash / permissions ───────────────────────────────────────────


def test_file_metadata_fields(tmp_path):
    root = tree(tmp_path)
    svc = make_service(root)
    meta = svc.file_metadata("src/app.py")
    assert meta["type"] == "file"
    assert meta["encoding"] == "utf-8"
    assert meta["sha256"]
    assert "permissions" in meta
    assert meta["mimeType"]


def test_file_hash_matches_content(tmp_path):
    import hashlib

    root = tree(tmp_path)
    svc = make_service(root)
    digest = svc.file_hash("src/app.py")["sha256"]
    expected = hashlib.sha256((root / "src" / "app.py").read_bytes()).hexdigest()
    assert digest == expected


def test_file_permissions_normalized(tmp_path):
    root = tree(tmp_path)
    svc = make_service(root)
    perms = svc.file_permissions("src/app.py")
    assert "normalized" in perms["permissions"]
    assert perms["permissions"]["normalized"]["readable"] is True


# ── index ───────────────────────────────────────────────────────────────────


def test_index_initial_and_incremental(tmp_path):
    root = tree(tmp_path)
    ws = make_ws(root)
    index = WorkspaceIndex(ws, path=tmp_path / "idx.db")
    stats = index.update()
    assert stats.updated >= 1
    assert index.status()["fileCount"] >= 1
    # A no-op update marks everything unchanged (incremental).
    again = index.update()
    assert again.updated == 0
    assert again.unchanged >= 1
    index.close()


def test_index_reindexes_only_the_changed_file(tmp_path):
    root = tree(tmp_path)
    ws = make_ws(root)
    index = WorkspaceIndex(ws, path=tmp_path / "idx.db")
    index.update()
    (root / "src" / "app.py").write_text("def brandNew():\n    return 1\n", encoding="utf-8")
    stats = index.update()
    assert stats.updated == 1
    names = {s["name"] for s in index.symbols()}
    assert "brandNew" in names
    index.close()


def test_index_removes_deleted_files(tmp_path):
    root = tree(tmp_path)
    ws = make_ws(root)
    index = WorkspaceIndex(ws, path=tmp_path / "idx.db")
    index.update()
    (root / "src" / "app.py").unlink()
    stats = index.update()
    assert stats.removed >= 1
    assert all(row["rel"] != "src/app.py" for row in index._db.execute("SELECT * FROM files"))
    index.close()


def test_find_references_refreshes_a_stale_index(tmp_path):
    """A file created AFTER the last index pass must still be found — the index is
    a cache, not an authority (the §30 no-stale-information rule)."""
    root = tree(tmp_path)
    svc = make_service(root)
    svc.index_workspace()  # index exists but does not yet contain the new file
    (root / "src" / "consumer.py").write_text("from util import calculateTotal\ncalculateTotal()\n", encoding="utf-8")
    result = svc.find_references("calculateTotal")
    assert result["engine"] == "index"  # the index was refreshed, not bypassed
    assert any(r["path"] == "src/consumer.py" for r in result["references"]), result


def test_find_references_regex_fallback_when_no_index(tmp_path):
    root = tree(tmp_path)
    svc = make_service(root)
    # No index has been built; the live scan answers.
    result = svc.find_references("calculateTotal")
    assert result["engine"] == "regex"
    assert result["count"] >= 1


# ── watchers ────────────────────────────────────────────────────────────────


def test_watcher_detects_create_modify_delete_rename(tmp_path):
    root = tree(tmp_path)
    ws = make_ws(root)
    watcher = WorkspaceWatcher(ws, targets=["src"], recursive=True, debounce_s=0.0)
    target = root / "src" / "new.txt"
    target.write_text("one\n", encoding="utf-8")
    events = watcher.poll_once()
    assert any(e.event == "created" and e.path == "src/new.txt" for e in events)
    target.write_text("two\n", encoding="utf-8")
    os.utime(target, None)
    assert any(e.event == "modified" for e in watcher.poll_once())
    target.rename(root / "src" / "renamed.txt")
    renamed = watcher.poll_once()
    assert any(e.event == "renamed" for e in renamed)
    (root / "src" / "renamed.txt").unlink()
    assert any(e.event == "deleted" for e in watcher.poll_once())


def test_watcher_debounces_duplicate_events(tmp_path):
    root = tree(tmp_path)
    ws = make_ws(root)
    watcher = WorkspaceWatcher(ws, targets=["src"], recursive=True, debounce_s=5.0)
    (root / "src" / "x.txt").write_text("1\n", encoding="utf-8")
    first = watcher.poll_once()
    assert any(e.event == "created" for e in first)
    # Delete then recreate quickly: the create is within the debounce window.
    (root / "src" / "x.txt").unlink()
    watcher.poll_once()
    (root / "src" / "x.txt").write_text("2\n", encoding="utf-8")
    second = watcher.poll_once()
    assert not any(e.event == "created" for e in second)


def test_watcher_invalidates_hash_cache_and_reindexes(tmp_path):
    root = tree(tmp_path)
    ws = make_ws(root)
    index = WorkspaceIndex(ws, path=tmp_path / "idx.db")
    index.update()
    watcher = WorkspaceWatcher(ws, targets=["src"], recursive=True, index=index, debounce_s=0.0)
    (root / "src" / "app.py").write_text("def fresh():\n    pass\n", encoding="utf-8")
    watcher.poll_once()
    names = {s["name"] for s in index.symbols()}
    assert "fresh" in names
    index.close()


# ── tools through the registry ──────────────────────────────────────────────


def _ctx(root, autonomy="edit_verify", *, direct=False):
    from harness.code.tools import make_code_authorizer, register_code_tools
    from harness.tools import ToolContext, ToolRegistry

    registry = ToolRegistry()
    register_code_tools(registry)
    ws = make_ws(root)
    ctx = ToolContext(
        run_id="run_fs", log=lambda *_: None, workspace=ws, autonomy=autonomy,
        authorize_effect=make_code_authorizer(), direct=direct,
    )
    return registry, ctx


def _call(registry, name, args, ctx):
    return asyncio.run(registry.execute(name, f"call_{name}", args, ctx))


def test_search_text_summary_names_the_match_mode_and_guards_zero(tmp_path):
    registry, ctx = _ctx(tree(tmp_path))
    result = _call(registry, "search_text", {"query": "badge_row|infographic"}, ctx)
    assert result.ok
    # A LITERAL alternation matches nothing; the summary must say so plainly so
    # "0 match(es)" is never read as "this code does not exist" (TOOL-1).
    assert "0 match(es)" in result.text
    assert "literal" in result.text
    assert "regex: true" in result.text


def test_registry_registers_all_fs_tools(tmp_path):
    registry, _ctx_unused = _ctx(tree(tmp_path))
    names = set(registry.names())
    for name in (
        "list_directory", "read_file", "write_file", "create_file", "delete_file",
        "move_file", "copy_file", "rename_file", "create_directory", "delete_directory",
        "search_text", "search_files", "find_files", "search_symbols", "find_references",
        "patch_file", "replace_text", "insert_text", "delete_text", "apply_diff",
        "multi_file_patch", "file_metadata", "file_hash", "file_permissions",
        "watch_file", "watch_directory", "edit_file", "index_workspace",
    ):
        assert name in names, name


def test_registry_read_tool_is_read_permission(tmp_path):
    registry, _ctx_unused = _ctx(tree(tmp_path))
    for name in ("read_file", "list_directory", "search_text", "file_hash"):
        tool = registry.get(name)
        assert tool.permission == "read"
        assert tool.risk == "low"


def test_registry_write_tools_are_effectful(tmp_path):
    registry, _ctx_unused = _ctx(tree(tmp_path))
    for name in ("write_file", "patch_file", "delete_file", "multi_file_patch"):
        tool = registry.get(name)
        assert tool.permission == "write"
        assert tool.effect == "write"


def test_tool_read_file_roundtrip(tmp_path):
    root = tree(tmp_path)
    registry, ctx = _ctx(root)
    result = _call(registry, "read_file", {"path": "src/app.py"}, ctx)
    assert result.ok and result.data["status"] == "ok"
    assert "alpha" in result.text


def test_tool_protected_path_refusal_code(tmp_path):
    root = tree(tmp_path)
    (root / "jdds.db").write_bytes(b"\x00vault")
    registry, ctx = _ctx(root)
    result = _call(registry, "read_file", {"path": "jdds.db"}, ctx)
    assert result.data["code"] == "PROTECTED_PATH"


def test_tool_write_refused_without_workspace(tmp_path):
    from harness.code.tools import make_code_authorizer, register_code_tools
    from harness.tools import ToolContext, ToolRegistry

    registry = ToolRegistry()
    register_code_tools(registry)
    ctx = ToolContext(
        run_id="r", log=lambda *_: None, workspace=None, autonomy="edit_verify",
        authorize_effect=make_code_authorizer(),
    )
    result = _call(registry, "write_file", {"path": "x.txt", "content": "y"}, ctx)
    assert result.data["code"] == "WORKSPACE_UNBOUND"

def test_tool_plan_only_write_is_profile_denied(tmp_path, monkeypatch):
    root = tree(tmp_path)
    monkeypatch.setenv("BLACK_ECLIPSE_CODE_ROOT", str(root))
    registry, ctx = _ctx(root, autonomy="plan_only", direct=True)
    result = _call(registry, "create_file", {"path": "src/x.py", "content": "y"}, ctx)
    assert result.ok and result.data["code"] == "PERMISSION_DENIED"
    assert not (root / "src" / "x.py").exists()


def test_tool_stale_hash_error_is_structured(tmp_path, monkeypatch):
    root = tree(tmp_path)
    monkeypatch.setenv("BLACK_ECLIPSE_CODE_ROOT", str(root))
    registry, ctx = _ctx(root, direct=True)
    result = _call(registry, "patch_file", {
        "path": "src/app.py", "operation": "replace", "oldText": "beta",
        "newText": "B", "expectedHash": "0" * 64,
    }, ctx)
    assert result.data["code"] == "STALE_FILE"
    assert result.data["details"]["actualHash"]


def test_tool_ambiguous_patch_has_recovery_hint(tmp_path, monkeypatch):
    root = tree(tmp_path)
    monkeypatch.setenv("BLACK_ECLIPSE_CODE_ROOT", str(root))
    (root / "src" / "dup.txt").write_text("same\nsame\n", encoding="utf-8")
    registry, ctx = _ctx(root, direct=True)
    result = _call(registry, "patch_file", {
        "path": "src/dup.txt", "operation": "replace", "oldText": "same", "newText": "x",
    }, ctx)
    assert result.data["code"] == "AMBIGUOUS_PATCH"
    assert "recovery" in result.data


def test_tool_dry_run_does_not_write(tmp_path, monkeypatch):
    root = tree(tmp_path)
    monkeypatch.setenv("BLACK_ECLIPSE_CODE_ROOT", str(root))
    registry, ctx = _ctx(root, direct=True)
    before = (root / "src" / "app.py").read_bytes()
    result = _call(registry, "replace_text", {
        "path": "src/app.py", "oldText": "beta", "newText": "BETA", "dryRun": True,
    }, ctx)
    assert result.data["dryRun"] is True
    assert (root / "src" / "app.py").read_bytes() == before
