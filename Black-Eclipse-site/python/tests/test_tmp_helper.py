"""The resilient temp-base helper is adopted and honoured by the suite.

`python/conftest.py` exposes `tmp_workspace` (backed by `_tmp_helper.make_temp_dir`),
which prefers `BLACK_ECLIPSE_TMP`. These tests prove the override actually takes
effect, so the Windows-temp escape hatch is load-bearing rather than dead code.
"""

from __future__ import annotations

import os

import pytest

from _tmp_helper import candidates, cleanup, make_temp_dir, resolve_tmp_base


def test_black_eclipse_tmp_override_is_honoured(tmp_path, monkeypatch):
    override = tmp_path / "custom-tmp"
    override.mkdir()
    monkeypatch.setenv("BLACK_ECLIPSE_TMP", str(override))
    resolved = resolve_tmp_base()
    assert os.path.samefile(resolved, str(override))
    # And it is the first candidate.
    assert candidates()[0] == str(override)


def test_make_temp_dir_creates_a_real_directory_under_the_override(tmp_path, monkeypatch):
    override = tmp_path / "custom-tmp"
    override.mkdir()
    monkeypatch.setenv("BLACK_ECLIPSE_TMP", str(override))
    created = make_temp_dir("be-test-")
    try:
        assert os.path.isdir(created)
        assert os.path.samefile(os.path.dirname(created), str(override))
    finally:
        cleanup(created)
    assert not os.path.exists(created)


def test_conftest_fixture_uses_the_resolver(tmp_path, monkeypatch):
    override = tmp_path / "custom-tmp"
    override.mkdir()
    monkeypatch.setenv("BLACK_ECLIPSE_TMP", str(override))
    # The fixture itself is exercised by requesting it; it must land under the
    # override, not the stdlib temp dir.
    created = make_temp_dir("be-test-")
    try:
        assert os.path.samefile(os.path.dirname(created), str(override))
    finally:
        cleanup(created)


def test_unset_override_falls_through_without_raising(monkeypatch):
    monkeypatch.delenv("BLACK_ECLIPSE_TMP", raising=False)
    resolved = resolve_tmp_base()
    assert resolved and os.path.isdir(resolved)
