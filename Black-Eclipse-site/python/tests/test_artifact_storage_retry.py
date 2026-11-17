from __future__ import annotations

import os
from pathlib import Path

import pytest

from harness.artifacts.storage import LocalArtifactStorage


def test_import_file_retries_when_the_store_path_vanishes(tmp_path, monkeypatch):
    """The reconciler can remove an empty month dir between temp-write and rename.

    Observed in the live app as `WinError 3` on `os.replace`. A read-only import
    must retry once instead of failing the artifact registration.
    """
    store = LocalArtifactStorage(root=tmp_path / "files")
    source = tmp_path / "report.md"
    source.write_text("hello", encoding="utf-8")

    real_replace = os.replace
    calls = {"n": 0}

    def flaky_replace(src, target):
        calls["n"] += 1
        if calls["n"] == 1:
            # Simulate the temp file/parent disappearing just before the rename.
            Path(src).unlink(missing_ok=True)
            raise FileNotFoundError(3, "The system cannot find the path specified", str(src))
        return real_replace(src, target)

    monkeypatch.setattr("harness.artifacts.storage.os.replace", flaky_replace)
    stored = store.import_file(source)

    assert calls["n"] == 2
    assert store.exists(stored.storage_key)
    with store.open(stored.storage_key) as handle:
        assert handle.read() == b"hello"
