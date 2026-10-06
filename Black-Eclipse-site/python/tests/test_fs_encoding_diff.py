"""File System subsystem — encoding/BOM/line-endings, binary protection, diffs.

These are the correctness-critical paths: a wrong encoding or a silent binary
decode would corrupt a user's file. Every case asserts exact bytes.
"""

from __future__ import annotations

import pytest

from harness.code.fs import encoding as enc
from harness.code.fs import errors as err
from harness.code.fs.diff import unified_diff

from fs_helpers import make_service, tree


# ── encoding module ─────────────────────────────────────────────────────────


def test_utf8_roundtrip():
    decoded = enc.decode("café\n".encode("utf-8"))
    assert decoded.encoding == "utf-8" and decoded.had_bom is False
    assert enc.encode(decoded.text, encoding=decoded.encoding, had_bom=decoded.had_bom) == "café\n".encode("utf-8")


def test_utf8_bom_preserved():
    raw = b"\xef\xbb\xbfhello\r\nworld\r\n"
    decoded = enc.decode(raw)
    assert decoded.had_bom is True
    assert decoded.newline == "\r\n"
    assert enc.encode(decoded.text, encoding=decoded.encoding, had_bom=True) == raw


def test_utf16_detected_and_preserved():
    raw = "hello\nworld\n".encode("utf-16")
    decoded = enc.decode(raw)
    assert decoded.had_bom is True
    assert "hello" in decoded.text
    assert enc.encode(decoded.text, encoding=decoded.encoding, had_bom=True) == raw


def test_undecodable_raises_invalid_encoding():
    with pytest.raises(err.FsError) as exc:
        enc.decode(b"\x80\x81\x82bad", encoding="utf-8")
    assert exc.value.code == err.INVALID_ENCODING


def test_preserves_crlf_on_write(tmp_path):
    root = tree(tmp_path)
    target = root / "src" / "crlf.txt"
    target.write_bytes(b"a\r\nb\r\n")
    svc = make_service(root)
    svc.replace_text("src/crlf.txt", "b", "B", expected_occurrences=1)
    assert target.read_bytes() == b"a\r\nB\r\n"


def test_bom_preserved_on_edit(tmp_path):
    root = tree(tmp_path)
    target = root / "src" / "bom.txt"
    target.write_bytes(b"\xef\xbb\xbfalpha\n")
    svc = make_service(root)
    svc.replace_text("src/bom.txt", "alpha", "ALPHA", expected_occurrences=1)
    assert target.read_bytes() == b"\xef\xbb\xbfALPHA\n"


# ── binary protection ───────────────────────────────────────────────────────


def test_binary_read_refused(tmp_path):
    root = tree(tmp_path)
    (root / "src" / "blob.bin").write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00")
    svc = make_service(root)
    with pytest.raises(err.FsError) as exc:
        svc.read_file("src/blob.bin")
    assert exc.value.code == err.BINARY_FILE


def test_binary_metadata_reports_binary_true(tmp_path):
    root = tree(tmp_path)
    (root / "src" / "blob.bin").write_bytes(b"\x89PNG\x00data")
    svc = make_service(root)
    meta = svc.file_metadata("src/blob.bin")
    assert meta["binary"] is True
    assert meta["mimeType"]


# ── diff generation ─────────────────────────────────────────────────────────


def test_unified_diff_shape():
    result = unified_diff("a\nb\n", "a\nB\n", path="x.py")
    assert result["hasChanges"] is True
    assert "+B" in result["diff"] and "-b" in result["diff"]
    assert result["additions"] == 1 and result["deletions"] == 1


def test_unified_diff_identical_is_empty():
    result = unified_diff("a\n", "a\n", path="x.py")
    assert result["hasChanges"] is False
    assert result["diff"] == ""


def test_dry_run_returns_a_diff(tmp_path):
    root = tree(tmp_path)
    svc = make_service(root)
    result = svc.replace_text("src/app.py", "beta", "BETA", expected_occurrences=1, dry_run=True)
    assert result["dryRun"] is True
    assert "-beta" in result["diff"] and "+BETA" in result["diff"]


def test_apply_diff_creates_a_new_file(tmp_path):
    root = tree(tmp_path)
    svc = make_service(root)
    diff = "--- /dev/null\n+++ b/src/newfile.py\n@@ -0,0 +1,2 @@\n+line one\n+line two\n"
    result = svc.apply_diff(diff)
    assert result["filesChanged"] == 1
    assert (root / "src" / "newfile.py").read_text(encoding="utf-8") == "line one\nline two\n"
