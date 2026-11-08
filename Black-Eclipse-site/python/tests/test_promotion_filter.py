"""Per-file review: narrowing a promotion preview (Phase 22 / S5 slice 2).

The digest is the approval's identity, so filtering MUST recompute it over the
kept set. These tests pin that, and the refusal of an empty selection.
"""

from __future__ import annotations

import pytest

from harness.code.promotion import PromotionError, filter_preview


def _preview():
    files = [
        {"path": "src/a.ts", "op": "create", "beforeHash": None, "afterHash": "a"},
        {"path": "src/b.ts", "op": "overwrite", "beforeHash": "b0", "afterHash": "b1"},
        {"path": "python/c.py", "op": "delete", "beforeHash": "c0", "afterHash": None},
    ]
    return {
        "workspaceId": "ws",
        "runId": "run",
        "worktreeRoot": "/tmp/ws",
        "files": files,
        "filesChanged": 3,
        "added": 1,
        "modified": 1,
        "deleted": 1,
        "previewDigest": "digest_all",
    }


def test_an_empty_include_keeps_the_whole_preview():
    preview = _preview()
    assert filter_preview(preview, []) is preview
    assert filter_preview(preview, ["", "  "]) is preview


def test_keeping_one_file_recomputes_the_counts_and_the_digest():
    preview = _preview()
    kept = filter_preview(preview, ["src/b.ts"])
    assert [f["path"] for f in kept["files"]] == ["src/b.ts"]
    assert kept["filesChanged"] == 1
    assert kept["added"] == 0
    assert kept["modified"] == 1
    assert kept["deleted"] == 0
    assert kept["previewDigest"] != preview["previewDigest"]
    assert kept["filtered"] is True
    # Apply needs the source folder; filtering must not drop it.
    assert kept["worktreeRoot"] == "/tmp/ws"


def test_a_windows_separator_is_normalized():
    kept = filter_preview(_preview(), ["src\\a.ts"])
    assert [f["path"] for f in kept["files"]] == ["src/a.ts"]


def test_keeping_nothing_is_refused():
    with pytest.raises(PromotionError) as excinfo:
        filter_preview(_preview(), ["nope.ts"])
    assert excinfo.value.code == "PROMOTION_NO_FILES"
