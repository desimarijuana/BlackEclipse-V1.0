"""Regression: concurrent mutation of ONE project's code index never loses rows.

The code index connection is `check_same_thread=False`; the background watcher and
a synchronous index trigger both write through it. This test drives the real
`CodeIndex` and `IncrementalIndexer` from several threads and asserts the index
stays consistent (no exceptions, rows survive). It reproduces the intermittent
`fileCount == 0` flake observed under the full suite.
"""

from __future__ import annotations

import threading
from pathlib import Path

from harness.code.intel.indexer import IncrementalIndexer
from harness.code.intel.persistence.index import CodeIndex


def _make_index(tmp_path: Path) -> CodeIndex:
    return CodeIndex("concurrency-test", path=tmp_path / "index.db")


def test_concurrent_upsert_and_remove_keeps_the_index_consistent(tmp_path):
    index = _make_index(tmp_path)
    errors: list[Exception] = []

    def _worker(worker: int) -> None:
        try:
            for i in range(40):
                rel = f"src/w{worker}_f{i}.py"
                index.upsert_file(
                    rel=rel, language="python", sha256=f"{worker}-{i}", size=10,
                    mtime_ns=i, line_count=1, engine="ast",
                    symbols=[{"id": f"{rel}:1", "name": "f", "kind": "function", "line": 1, "column": 1}],
                    imports=[], dependencies=[], references=[], call_edges=[],
                )
                if i % 2 == 0:
                    index.remove_file(rel)
        except Exception as exc:  # noqa: BLE001 - a raised error is the bug
            errors.append(exc)

    threads = [threading.Thread(target=_worker, args=(w,)) for w in range(6)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert errors == []
    # Every odd `i` file survives; the even ones were removed. 6 workers * 20.
    assert len(index.known_files()) == 6 * 20
    assert index.integrity_ok() is True
    index.close()


def test_concurrent_index_workspace_and_watch_events(tmp_path):
    (tmp_path / "src").mkdir()
    for i in range(8):
        (tmp_path / "src" / f"m{i}.py").write_text(f"def f{i}():\n    return {i}\n", encoding="utf-8")
    index = _make_index(tmp_path)
    indexer = IncrementalIndexer(tmp_path, "concurrency-test", index)
    errors: list[Exception] = []
    start = threading.Barrier(3)

    def _full() -> None:
        try:
            start.wait()
            for _ in range(10):
                indexer.index_workspace()
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    def _watching() -> None:
        try:
            start.wait()
            for i in range(30):
                indexer.reindex_file(f"src/m{i % 8}.py")
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=_full), threading.Thread(target=_full), threading.Thread(target=_watching)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert errors == []
    assert index.integrity_ok() is True
    assert len(index.known_files()) == 8
    index.close()
