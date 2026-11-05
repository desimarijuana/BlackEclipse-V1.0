"""Per-chat (per-session) workspace roots.

A run may name an APPROVED root id; the runtime resolves it against the trusted
store. An unknown/revoked id must yield NO workspace (honest refusal), never a
silent fallback to another folder.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from harness.code import workspace


@pytest.fixture(autouse=True)
def _reset_providers():
    yield
    workspace.set_trusted_root_lookup(None)
    workspace.set_trusted_root_provider(None)


def test_a_per_chat_root_id_resolves_to_its_approved_path(tmp_path):
    workspace.set_trusted_root_lookup(lambda rid: str(tmp_path) if rid == "root_a" else None)
    resolved = workspace.resolve_workspace(None, "root_a")
    assert resolved is not None
    assert resolved.root == Path(tmp_path).resolve()


def test_an_unknown_or_revoked_root_gets_no_workspace(tmp_path, monkeypatch):
    # Even with a healthy global default, a named-but-invalid id must not fall
    # back to a different folder.
    monkeypatch.setenv("BLACK_ECLIPSE_CODE_ROOT", str(tmp_path))
    workspace.set_trusted_root_lookup(lambda _rid: None)
    assert workspace.resolve_workspace(None, "root_gone") is None


def test_without_an_id_the_server_default_is_unchanged(tmp_path, monkeypatch):
    monkeypatch.setenv("BLACK_ECLIPSE_CODE_ROOT", str(tmp_path))
    resolved = workspace.resolve_workspace(None)
    assert resolved is not None
    assert resolved.root == Path(tmp_path).resolve()


def test_a_confirmation_must_match_the_per_chat_root(tmp_path):
    workspace.set_trusted_root_lookup(lambda _rid: str(tmp_path))

    class _Request:
        root = str(tmp_path / "somewhere-else")

    assert workspace.resolve_workspace(_Request(), "root_a") is None


def test_trusted_root_path_rejects_a_missing_directory(tmp_path):
    gone = tmp_path / "gone"
    workspace.set_trusted_root_lookup(lambda _rid: str(gone))
    assert workspace.trusted_root_path("root_a") is None
