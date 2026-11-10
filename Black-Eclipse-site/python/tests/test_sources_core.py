"""Core tests for the large-corpus source layer: catalog, scan, probe, chunks."""

from __future__ import annotations

import os
import struct
import threading

import pytest

from harness.sources.config import load_config
from harness.sources.contracts import FileRecord
from harness.sources.errors import SourceError
from harness.sources.extract import extract_chunks, iter_text_chunks
from harness.sources.probe import probe_file
from harness.sources.service import SourceService, set_sources_service


@pytest.fixture()
def service(tmp_path):
    cfg = load_config({
        "db_path": str(tmp_path / "sources.db"),
        "tmp_dir": str(tmp_path / "tmp"),
        "scan_batch": 50,
        "index_max_file_bytes": 4 * 1024 * 1024,
    })
    svc = SourceService(cfg)
    set_sources_service(svc)
    yield svc
    svc.close()


def _tree(root):
    (root / "sub").mkdir(parents=True)
    (root / "node_modules").mkdir()
    (root / "a.txt").write_text("alpha revenue line\n" * 50, encoding="utf-8")
    (root / "sub" / "b.csv").write_text("name,value\nalpha,1\nbeta,2\n", encoding="utf-8")
    (root / "big.bin").write_bytes(bytes(range(256)) * 8)
    (root / "node_modules" / "ignored.txt").write_text("should not be catalogued", encoding="utf-8")


def test_scan_is_incremental_and_removes_vanished_files(service, tmp_path):
    root_dir = tmp_path / "corpus"
    root_dir.mkdir()
    _tree(root_dir)
    root = service.add_root(str(root_dir))
    scan = service.wait_scan(root["id"], timeout_s=20)
    assert scan["running"] is False
    assert scan["added"] == 3, scan
    assert scan["filesSeen"] == 3

    stats = service.stats()
    assert stats["files"] == 3
    assert stats["classes"]["text"]["files"] == 1
    assert stats["classes"]["table"]["files"] == 1
    assert stats["classes"]["binary"]["files"] == 1

    # Incremental: one change, one addition, the rest unchanged.
    (root_dir / "a.txt").write_text("changed revenue\n", encoding="utf-8")
    (root_dir / "c.md").write_text("# notes\n", encoding="utf-8")
    service.start_scan(root["id"])
    scan = service.wait_scan(root["id"], timeout_s=20)
    assert scan["updated"] == 1
    assert scan["added"] == 1
    assert scan["unchanged"] == 2

    (root_dir / "sub" / "b.csv").unlink()
    service.start_scan(root["id"])
    scan = service.wait_scan(root["id"], timeout_s=20)
    assert scan["removed"] == 1
    assert service.catalog.get_file(root["id"], "sub/b.csv") is None


def test_root_registration_confinement_and_removal(service, tmp_path):
    source = tmp_path / "data"
    source.mkdir()
    (source / "x.txt").write_text("hello", encoding="utf-8")

    with pytest.raises(SourceError) as missing:
        service.add_root(str(tmp_path / "nope"))
    assert missing.value.code == "ROOT_NOT_FOUND"

    file_path = source / "x.txt"
    with pytest.raises(SourceError) as not_dir:
        service.add_root(str(file_path))
    assert not_dir.value.code == "ROOT_NOT_DIRECTORY"

    root = service.add_root(str(source), label="Data")
    assert root["label"] == "Data"
    assert service.add_root(str(source))["id"] == root["id"], "duplicate add is idempotent"

    with pytest.raises(SourceError) as escape:
        service.resolve(root_id=root["id"], relpath="../outside.txt")
    assert escape.value.code == "PATH_OUTSIDE_ROOT"

    outside = tmp_path / "outside.txt"
    outside.write_text("secret", encoding="utf-8")
    assert service.catalog.root_for_path(str(outside)) is None

    service.wait_scan(root["id"], timeout_s=20)
    assert service.remove_root(root["id"]) is True
    assert service.list_roots() == []
    assert service.stats()["files"] == 0


def test_probe_identifies_without_reading_whole_file(tmp_path):
    text = tmp_path / "notes.txt"
    text.write_text("Revenue grew 12%.\n" * 400, encoding="utf-8")
    card = probe_file(str(text), size=text.stat().st_size)
    assert card.klass == "text"
    assert "Revenue grew" in card.head
    assert card.truncated is True, "a 6 KB file with a 4 KB head must be marked truncated"

    csv_file = tmp_path / "t.csv"
    csv_file.write_text("ticker,revenue\nAAPL,100\nMSFT,200\n", encoding="utf-8")
    card = probe_file(str(csv_file), size=csv_file.stat().st_size)
    assert card.klass == "table"
    assert [c["name"] for c in card.columns][:2] == ["ticker", "revenue"]
    assert card.delimiter == ","

    empty = tmp_path / "empty.log"
    empty.write_bytes(b"")
    assert probe_file(str(empty)).klass == "empty"

    binary = tmp_path / "blob.bin"
    binary.write_bytes(bytes(range(256)) * 4)
    card = probe_file(str(binary), size=binary.stat().st_size)
    assert card.klass == "binary"
    assert card.warnings

    png = tmp_path / "img.png"
    png.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\rIHDR" + struct.pack(">II", 640, 480))
    card = probe_file(str(png), size=png.stat().st_size)
    assert card.klass == "image"
    assert (card.width, card.height) == (640, 480)

    brief = card.brief(max_head=100)
    assert len(brief["head"]) <= 100


def test_text_chunking_streams_and_respects_budgets(tmp_path):
    path = tmp_path / "big.log"
    path.write_text(("line with revenue and cost\n" * 80_000), encoding="utf-8")

    chunks = []
    metas = []
    for item in iter_text_chunks(
        str(path), chunk_chars=1_000, overlap=100, max_bytes=2_000_000, max_chunks=50
    ):
        if item.get("_done"):
            metas.append(item)
        else:
            chunks.append(item)

    assert 0 < len(chunks) <= 50
    assert all(len(c["text"]) <= 1_400 for c in chunks)
    assert metas and 0 < metas[0]["_bytes"] <= 2_000_000
    assert metas[0]["_digest"]

    cancel = threading.Event()
    cancel.set()
    assert list(iter_text_chunks(str(path), chunk_chars=500, cancel=cancel)) == []


def test_extract_chunks_dispatches_and_reports_unsupported(tmp_path):
    from harness.sources.config import load_config as cfg

    config = cfg({"index_max_file_bytes": 1_000_000, "chunk_chars": 500})
    text = tmp_path / "a.md"
    text.write_text("# Title\n\nRevenue and margin.\n" * 100, encoding="utf-8")
    record = FileRecord(
        id=1, root_id="r", relpath="a.md", name="a.md", ext="md",
        size=text.stat().st_size, mtime=text.stat().st_mtime, klass="text",
    )
    chunks, meta = extract_chunks(record, str(text), config=config)
    assert chunks and chunks[0]["text"]
    assert meta["hash"]

    blob = tmp_path / "x.mp4"
    blob.write_bytes(b"\x00\x00\x00\x18ftypmp42")
    record = FileRecord(id=2, root_id="r", relpath="x.mp4", name="x.mp4", ext="mp4",
                        size=blob.stat().st_size, mtime=0, klass="video")
    chunks, meta = extract_chunks(record, str(blob), config=config)
    assert chunks == []
    assert "metadata only" in meta["reason"]


def test_read_windows_and_lines(service, tmp_path):
    root_dir = tmp_path / "read"
    root_dir.mkdir()
    target = root_dir / "data.txt"
    target.write_text("".join(f"line {i}\n" for i in range(1, 501)), encoding="utf-8")
    root = service.add_root(str(root_dir))
    service.wait_scan(root["id"], timeout_s=20)

    opened = service.open(root_id=root["id"], relpath="data.txt")
    assert opened["card"]["klass"] == "text"
    assert opened["card"]["index_state"] == "NOT_INDEXED"

    window = service.read_window(root_id=root["id"], relpath="data.txt", offset=0, length=24)
    assert window["read"] == 24
    assert window["text"].startswith("line 1")

    lines = service.read_lines(root_id=root["id"], relpath="data.txt", start_line=10, count=3)
    assert lines["lines"] == ["line 10", "line 11", "line 12"]

    with pytest.raises(SourceError) as too_big:
        service.read_window(root_id=root["id"], relpath="data.txt", length=10_000_000)
    assert too_big.value.code == "READ_LIMIT"


def test_adopts_a_file_that_appeared_after_the_scan(service, tmp_path):
    root_dir = tmp_path / "adopt"
    root_dir.mkdir()
    root = service.add_root(str(root_dir))
    service.wait_scan(root["id"], timeout_s=20)
    late = root_dir / "late.log"
    late.write_text("late arrival revenue", encoding="utf-8")
    opened = service.open(root_id=root["id"], relpath="late.log")
    assert opened["file"]["name"] == "late.log"
    assert "late arrival" in opened["card"]["head"]
