"""File System subsystem — the limitation fixes:
native watchers, richer symbol extraction, reference classification, and the
deterministic `edit_file` instruction parser.
"""

from __future__ import annotations

import asyncio
import os
import time

import pytest

from harness.code.fs import intent
from harness.code.fs import symbols as symbols_mod
from harness.code.fs import watch as watch_mod
from harness.code.fs import watch_native
from harness.code.fs.index import WorkspaceIndex

from fs_helpers import make_ws, tree


# ── native watchers ──────────────────────────────────────────────────────────


def test_native_backend_is_reported():
    assert watch_native.native_backend_name() in (
        "windows-rdcw", "linux-inotify", "polling",
    )


def test_watcher_reports_its_backend(tmp_path):
    root = tree(tmp_path)
    watcher = watch_mod.WorkspaceWatcher(make_ws(root), targets=["src"], recursive=True)
    assert watcher.status()["backend"] in ("polling", "windows-rdcw", "linux-inotify")


@pytest.mark.skipif(os.name != "nt", reason="ReadDirectoryChangesW is Windows-only")
def test_windows_native_watcher_detects_changes(tmp_path):
    root = tree(tmp_path)
    watcher = watch_mod.WorkspaceWatcher(make_ws(root), targets=["src"], recursive=True)
    watcher.start()
    try:
        assert watcher.backend == "windows-rdcw"
        time.sleep(0.5)
        (root / "src" / "new.txt").write_text("hi\n", encoding="utf-8")
        deadline = time.time() + 5
        seen = []
        while time.time() < deadline and not any(e.event == "created" for e in seen):
            seen.extend(watcher.poll_once())
            time.sleep(0.1)
        assert any(e.event == "created" and e.path == "src/new.txt" for e in seen)
    finally:
        watcher.stop()


@pytest.mark.skipif(os.name != "nt", reason="ReadDirectoryChangesW is Windows-only")
def test_native_watcher_degrades_to_polling_when_unhealthy(tmp_path):
    root = tree(tmp_path)
    watcher = watch_mod.WorkspaceWatcher(make_ws(root), targets=["src"], recursive=True)
    watcher.start()
    try:
        watcher._native._failed = True
        watcher.poll_once()
        # The fallback baseline is refreshed so a subsequent change is detected.
        (root / "src" / "later.txt").write_text("x\n", encoding="utf-8")
        events = watcher.poll_once()
        assert any(e.event == "created" and e.path == "src/later.txt" for e in events)
        assert watcher.backend == "polling"
    finally:
        watcher.stop()


def test_polling_backend_still_detects_all_event_kinds(tmp_path):
    root = tree(tmp_path)
    watcher = watch_mod.WorkspaceWatcher(
        make_ws(root), targets=["src"], recursive=True, prefer_native=False,
    )
    (root / "src" / "new.txt").write_text("one\n", encoding="utf-8")
    assert any(e.event == "created" for e in watcher.poll_once())
    target = root / "src" / "new.txt"
    target.write_text("two\n", encoding="utf-8")
    # The fingerprint is (st_mtime_ns, st_size). "one\n" and "two\n" are the same
    # size, and os.utime(..., None) can land in the same filesystem timestamp
    # tick on Windows, so force a distinct mtime instead of racing the clock.
    future = target.stat().st_mtime + 5
    os.utime(target, (future, future))
    assert any(e.event == "modified" for e in watcher.poll_once())
    target.rename(root / "src" / "renamed.txt")
    renamed = watcher.poll_once()
    assert any(e.event == "renamed" and e.old_path == "src/new.txt" for e in renamed)
    (root / "src" / "renamed.txt").unlink()
    assert any(e.event == "deleted" for e in watcher.poll_once())


# ── richer symbol extraction ────────────────────────────────────────────────


def test_python_methods_and_decorators():
    text = (
        "import os\n\n"
        "@decorator\n"
        "def top(x):\n    return x\n\n"
        "class Cart:\n"
        "    @property\n"
        "    def total(self):\n        return 1\n"
        "    def add(self, n):\n        return n\n"
    )
    got = {s.name: s for s in symbols_mod.extract_symbols("x.py", text)}
    assert got["top"].kind == "function"
    assert "@decorator" in got["top"].signature
    assert got["total"].kind == "method"
    assert "@property" in got["total"].signature
    assert got["add"].kind == "method"
    assert got["Cart"].kind == "class"


def test_typescript_methods_classes_arrows_interfaces():
    text = (
        "export const fetchData = async (url: string) => {\n  return url;\n};\n"
        "export class CartService {\n"
        "  private total = 0;\n"
        "  constructor(private api: Api) {}\n"
        "  calculateTotal(items) {\n    return this.total;\n  }\n"
        "}\n"
        "export function helper() {}\n"
        "export interface Config { a: number }\n"
        "export type Id = string;\n"
        "import { Api } from './api';\n"
    )
    got = {s.name: s for s in symbols_mod.extract_symbols("x.ts", text)}
    assert got["fetchData"].kind == "function"
    assert got["helper"].kind == "function"
    assert got["CartService"].kind == "class"
    assert got["calculateTotal"].kind == "method"
    assert got["constructor"].kind == "method"
    assert got["Config"].kind == "interface"
    assert got["Id"].kind == "type"
    assert got["Api"].kind == "import"


def test_go_rust_java_extractors():
    go = "package main\nfunc Add(a int) int { return a }\ntype Config struct { X int }\ntype Reader interface { Read() }\n"
    go_syms = {s.name: s.kind for s in symbols_mod.extract_symbols("x.go", go)}
    assert go_syms["Add"] == "function"
    assert go_syms["Config"] == "class"
    assert go_syms["Reader"] == "interface"
    rust = "pub async fn run() {}\npub struct Server;\npub type Id = u64;\n"
    rust_syms = {s.name: s.kind for s in symbols_mod.extract_symbols("x.rs", rust)}
    assert rust_syms["run"] == "function" and rust_syms["Server"] == "class"


# ── reference classification ────────────────────────────────────────────────


def test_regex_references_mark_definitions(tmp_path):
    root = tree(tmp_path)
    (root / "src" / "uses.py").write_text(
        "from util import calculateTotal\n\ndef caller():\n    return calculateTotal()\n",
        encoding="utf-8",
    )
    from fs_helpers import make_service

    svc = make_service(root)
    result = svc.find_references("calculateTotal")
    assert result["engine"] == "regex"
    assert any(r["definition"] for r in result["references"])


def test_index_references_mark_definitions(tmp_path):
    root = tree(tmp_path)
    ws = make_ws(root)
    index = WorkspaceIndex(ws, path=tmp_path / "idx.db")
    index.update()
    refs = index.find_references("calculateTotal")
    assert refs is not None
    assert any(r["definition"] for r in refs)
    index.close()


def test_index_schema_is_migrated_additively(tmp_path):
    import sqlite3

    db = tmp_path / "old.db"
    connection = sqlite3.connect(str(db))
    connection.execute(
        "CREATE TABLE files (rel TEXT PRIMARY KEY, sha256 TEXT, size INTEGER NOT NULL,"
        " mtime_ns INTEGER NOT NULL, language TEXT NOT NULL, symbols TEXT NOT NULL DEFAULT '[]',"
        " imports TEXT NOT NULL DEFAULT '[]', exports TEXT NOT NULL DEFAULT '[]',"
        " identifiers TEXT NOT NULL DEFAULT '{}', indexed_at TEXT NOT NULL)"
    )
    connection.commit()
    connection.close()
    index = WorkspaceIndex(make_ws(tree(tmp_path)), path=db)
    columns = {row["name"] for row in index._db.execute("PRAGMA table_info(files)").fetchall()}
    assert "definitions" in columns
    index.close()


# ── edit_file instruction parser ─────────────────────────────────────────────


def test_parse_replace():
    parsed = intent.parse_edit_instruction("rename beta to BETA")
    assert parsed is not None
    assert (parsed.operation, parsed.old_text, parsed.new_text) == ("replace", "beta", "BETA")


def test_parse_replace_strips_article():
    parsed = intent.parse_edit_instruction("change the timeout to 10000")
    assert parsed is not None
    assert parsed.old_text == "timeout" and parsed.new_text == "10000"


def test_parse_insert_after_and_before():
    after = intent.parse_edit_instruction("add a null check after parse()")
    assert after is not None and after.operation == "insert"
    assert after.old_text == "parse()"
    assert not intent.is_insert_before("add a null check after parse()")
    before = intent.parse_edit_instruction("insert the header before import os")
    assert before is not None and before.old_text == "import os"
    assert intent.is_insert_before("insert the header before import os")


def test_parse_append_and_prepend():
    assert intent.parse_edit_instruction("append the license at the end").operation == "append"
    assert intent.parse_edit_instruction("prepend the header at the start").operation == "prepend"


def test_parse_delete():
    parsed = intent.parse_edit_instruction("delete the unused import")
    assert parsed is not None and parsed.operation == "delete"
    assert parsed.old_text == "unused import"


def test_parse_refuses_vague_instruction():
    assert intent.parse_edit_instruction("make it better") is None
    assert intent.parse_edit_instruction("improve this file") is None
    assert intent.parse_edit_instruction("") is None


def test_edit_file_derives_and_applies_a_replace(tmp_path, monkeypatch):
    root = tree(tmp_path)
    monkeypatch.setenv("BLACK_ECLIPSE_CODE_ROOT", str(root))
    from harness.code.tools import make_code_authorizer, register_code_tools
    from harness.tools import ToolContext, ToolRegistry

    registry = ToolRegistry()
    register_code_tools(registry)
    ctx = ToolContext(
        run_id="r", log=lambda *_: None, workspace=make_ws(root), autonomy="edit_verify",
        authorize_effect=make_code_authorizer(), direct=True,
    )
    result = asyncio.run(registry.execute("edit_file", "c1", {
        "path": "src/app.py", "instruction": "rename beta to BETA",
    }, ctx))
    assert result.ok
    assert result.data["changed"] is True
    assert result.data["parsedInstruction"]["operation"] == "replace"
    assert "BETA" in (root / "src" / "app.py").read_text(encoding="utf-8")


def test_edit_file_derives_a_delete(tmp_path, monkeypatch):
    root = tree(tmp_path)
    monkeypatch.setenv("BLACK_ECLIPSE_CODE_ROOT", str(root))
    from harness.code.tools import make_code_authorizer, register_code_tools
    from harness.tools import ToolContext, ToolRegistry

    registry = ToolRegistry()
    register_code_tools(registry)
    ctx = ToolContext(
        run_id="r", log=lambda *_: None, workspace=make_ws(root), autonomy="edit_verify",
        authorize_effect=make_code_authorizer(), direct=True,
    )
    result = asyncio.run(registry.execute("edit_file", "c1", {
        "path": "src/app.py", "instruction": "delete beta",
    }, ctx))
    assert result.ok and result.data["deleted"] is True
    assert "beta" not in (root / "src" / "app.py").read_text(encoding="utf-8")


def test_edit_file_falls_back_to_inspection_on_vague_instruction(tmp_path, monkeypatch):
    root = tree(tmp_path)
    monkeypatch.setenv("BLACK_ECLIPSE_CODE_ROOT", str(root))
    from harness.code.tools import make_code_authorizer, register_code_tools
    from harness.tools import ToolContext, ToolRegistry

    registry = ToolRegistry()
    register_code_tools(registry)
    ctx = ToolContext(
        run_id="r", log=lambda *_: None, workspace=make_ws(root), autonomy="edit_verify",
        authorize_effect=make_code_authorizer(), direct=True,
    )
    before = (root / "src" / "app.py").read_bytes()
    result = asyncio.run(registry.execute("edit_file", "c1", {
        "path": "src/app.py", "instruction": "make it better",
    }, ctx))
    assert result.ok
    assert result.data.get("language") == "python"  # the inspection packet
    assert (root / "src" / "app.py").read_bytes() == before
