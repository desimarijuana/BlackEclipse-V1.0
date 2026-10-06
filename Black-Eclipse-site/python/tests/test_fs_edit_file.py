"""File System subsystem — the high-level `edit_file` workflow and the
end-to-end agent feedback loop.

`edit_file` orchestrates: inspect → locate → minimal patch → verify. Tested via
the registry, with the disposable/direct workspace so the full write path runs.
"""

from __future__ import annotations

import asyncio

import pytest

from harness.code.fs import errors as err

from fs_helpers import make_service, make_ws, tree


# ── edit_file service-level ─────────────────────────────────────────────────


def test_edit_file_inspects_without_a_concrete_edit(tmp_path):
    root = tree(tmp_path)
    svc = make_service(root)
    packet = svc.inspect("src/nested/util.py", query="calculateTotal")
    assert packet["language"] == "python"
    assert any(s["name"] == "calculateTotal" for s in packet["symbols"])
    assert packet["regionCount"] >= 1
    assert packet["sha256"]


def test_edit_file_region_has_line_numbers(tmp_path):
    root = tree(tmp_path)
    svc = make_service(root)
    packet = svc.inspect("src/app.py", query="beta")
    assert packet["regions"][0]["startLine"] >= 1


# ── edit_file through the registry ──────────────────────────────────────────


def _ctx(root, autonomy="edit_verify"):
    from harness.code.tools import make_code_authorizer, register_code_tools
    from harness.tools import ToolContext, ToolRegistry

    registry = ToolRegistry()
    register_code_tools(registry)
    ws = make_ws(root)
    ctx = ToolContext(
        run_id="run_edit", log=lambda *_: None, workspace=ws, autonomy=autonomy,
        authorize_effect=make_code_authorizer(), direct=True,
    )
    return registry, ctx


def _call(registry, name, args, ctx):
    return asyncio.run(registry.execute(name, f"call_{name}", args, ctx))


def test_edit_file_returns_inspection_packet_first(tmp_path, monkeypatch):
    root = tree(tmp_path)
    monkeypatch.setenv("BLACK_ECLIPSE_CODE_ROOT", str(root))
    registry, ctx = _ctx(root)
    result = _call(registry, "edit_file", {
        "path": "src/nested/util.py", "instruction": "change the return value",
        "query": "calculateTotal",
    }, ctx)
    assert result.ok
    assert result.data["status"] == "ok"
    assert result.data["language"] == "python"
    assert "oldText" in result.text or "Inspection" in result.text


def test_edit_file_applies_minimal_patch(tmp_path, monkeypatch):
    root = tree(tmp_path)
    monkeypatch.setenv("BLACK_ECLIPSE_CODE_ROOT", str(root))
    registry, ctx = _ctx(root)
    result = _call(registry, "edit_file", {
        "path": "src/app.py",
        "instruction": "rename beta to BETA",
        "oldText": "beta", "newText": "BETA",
    }, ctx)
    assert result.ok
    assert result.data["changed"] is True
    assert "BETA" in (root / "src" / "app.py").read_text(encoding="utf-8")


def test_edit_file_ambiguous_target_refused(tmp_path, monkeypatch):
    root = tree(tmp_path)
    monkeypatch.setenv("BLACK_ECLIPSE_CODE_ROOT", str(root))
    (root / "src" / "dup.txt").write_text("same\nsame\n", encoding="utf-8")
    registry, ctx = _ctx(root)
    result = _call(registry, "edit_file", {
        "path": "src/dup.txt", "instruction": "change same", "oldText": "same", "newText": "x",
    }, ctx)
    assert result.data["code"] == "AMBIGUOUS_PATCH"


def test_edit_file_dry_run(tmp_path, monkeypatch):
    root = tree(tmp_path)
    monkeypatch.setenv("BLACK_ECLIPSE_CODE_ROOT", str(root))
    registry, ctx = _ctx(root)
    before = (root / "src" / "app.py").read_bytes()
    result = _call(registry, "edit_file", {
        "path": "src/app.py", "instruction": "x", "oldText": "beta", "newText": "BETA",
        "dryRun": True,
    }, ctx)
    assert result.data["dryRun"] is True
    assert (root / "src" / "app.py").read_bytes() == before


# ── the full feedback loop: search → patch → verify ─────────────────────────


def test_agent_loop_search_patch_search(tmp_path, monkeypatch):
    """search → read → patch → verify, the target workflow, end to end."""
    root = tree(tmp_path)
    monkeypatch.setenv("BLACK_ECLIPSE_CODE_ROOT", str(root))
    registry, ctx = _ctx(root)
    found = _call(registry, "search_symbols", {"query": "calculateTotal"}, ctx)
    assert found.ok and found.data["count"] == 1
    loc = found.data["symbols"][0]
    read = _call(registry, "read_file", {"path": loc["path"], "startLine": 1}, ctx)
    assert read.ok
    patch = _call(registry, "patch_file", {
        "path": loc["path"], "operation": "replace",
        "oldText": "return 42", "newText": "return 43",
    }, ctx)
    assert patch.ok and patch.data["changed"] is True
    assert "return 43" in (root / "src" / "nested" / "util.py").read_text(encoding="utf-8")


def test_agent_loop_multi_file_transaction_then_verify(tmp_path, monkeypatch):
    root = tree(tmp_path)
    monkeypatch.setenv("BLACK_ECLIPSE_CODE_ROOT", str(root))
    registry, ctx = _ctx(root)
    result = _call(registry, "multi_file_patch", {
        "patches": [
            {"path": "src/app.py", "operation": "replace", "oldText": "alpha", "newText": "ALPHA"},
            {"path": "src/other.py", "operation": "replace", "oldText": "UNTOUCHED", "newText": "TOUCHED"},
        ],
        "atomic": True,
    }, ctx)
    assert result.ok and result.data["filesChanged"] == 2
    # Verify by reading the files back.
    assert (root / "src" / "app.py").read_text(encoding="utf-8").startswith("ALPHA")
    assert "TOUCHED" in (root / "src" / "other.py").read_text(encoding="utf-8")
