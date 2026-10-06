"""File System subsystem — the centralized permission system, the standard error
vocabulary, and the observability/index/watch tools through the registry.
"""

from __future__ import annotations

import asyncio

import pytest

from harness.code.fs import errors as err
from harness.code.fs import permissions as perms

from fs_helpers import make_ws, tree


# ── capability gating ───────────────────────────────────────────────────────


def test_all_capabilities_declared():
    for name in ("read", "write", "create", "delete", "move", "copy", "rename", "watch", "search"):
        assert name in perms.CAPABILITIES


def test_edit_verify_grants_write_capabilities():
    assert perms.capability_enabled("edit_verify", "write")
    assert perms.capability_enabled("edit_verify", "delete")
    assert perms.capability_enabled("edit_verify", "read")


def test_plan_only_grants_read_only():
    assert perms.capability_enabled("plan_only", "read")
    assert perms.capability_enabled("plan_only", "search")
    assert perms.capability_enabled("plan_only", "watch")
    assert not perms.capability_enabled("plan_only", "write")
    assert not perms.capability_enabled("plan_only", "delete")


def test_unknown_profile_grants_nothing():
    for name in perms.CAPABILITIES:
        assert not perms.capability_enabled("nonsense", name)


def test_config_can_only_narrow_never_widen():
    # A config cannot grant a capability the profile lacks.
    assert not perms.capability_enabled("plan_only", "write", {"write": True})
    # A config can deny one the profile has.
    assert not perms.capability_enabled("edit_verify", "delete", {"delete": False})
    # Unknown config keys are ignored.
    assert perms.resolve_config({"bogus": False}) == {}


def test_require_raises_permission_denied_for_plan_only():
    from harness.skills.permissions import Actor

    actor = Actor(id="c", workspace_id="ws", autonomy="plan_only")
    with pytest.raises(err.FsError) as exc:
        perms.require(actor, None, "write", "src/app.py")
    assert exc.value.code == err.PERMISSION_DENIED


# ── error vocabulary ────────────────────────────────────────────────────────


def test_standard_codes_are_defined():
    for code in (
        "PATH_NOT_FOUND", "PATH_NOT_ALLOWED", "PERMISSION_DENIED", "FILE_EXISTS",
        "DIRECTORY_EXISTS", "NOT_A_FILE", "NOT_A_DIRECTORY", "INVALID_PATH",
        "INVALID_ENCODING", "STALE_FILE", "AMBIGUOUS_PATCH", "PATCH_FAILED",
        "PATCH_CONTEXT_MISMATCH", "DIFF_FAILED", "TRANSACTION_FAILED",
        "ROLLBACK_FAILED", "SEARCH_FAILED", "INDEX_FAILED", "WATCH_FAILED",
    ):
        assert code in err.ALL_CODES


def test_fs_error_to_dict_is_structured():
    error = err.FsError(err.STALE_FILE, "changed", path="a.py", details={"actualHash": "x"})
    payload = error.to_dict()
    assert payload["status"] == "refused"
    assert payload["code"] == "STALE_FILE"
    assert payload["path"] == "a.py"
    assert payload["details"]["actualHash"] == "x"
    assert payload["recovery"]


def test_recovery_hints_exist_for_recoverable_codes():
    for code in (err.STALE_FILE, err.AMBIGUOUS_PATCH, err.PATCH_CONTEXT_MISMATCH, err.FILE_EXISTS):
        assert code in err.RECOVERY_HINTS


# ── tools through the registry ──────────────────────────────────────────────


def _ctx(root, autonomy="edit_verify"):
    from harness.code.tools import make_code_authorizer, register_code_tools
    from harness.tools import ToolContext, ToolRegistry

    registry = ToolRegistry()
    register_code_tools(registry)
    ws = make_ws(root)
    ctx = ToolContext(
        run_id="run_perm", log=lambda *_: None, workspace=ws, autonomy=autonomy,
        authorize_effect=make_code_authorizer(),
    )
    return registry, ctx


def _call(registry, name, args, ctx):
    return asyncio.run(registry.execute(name, f"call_{name}", args, ctx))


def test_index_workspace_tool(tmp_path):
    root = tree(tmp_path)
    registry, ctx = _ctx(root)
    result = _call(registry, "index_workspace", {}, ctx)
    assert result.ok
    assert result.data["status"] == "ok"
    assert result.data["fileCount"] >= 1
    assert "update" in result.data


def test_watch_directory_tool(tmp_path):
    root = tree(tmp_path)
    registry, ctx = _ctx(root)
    result = _call(registry, "watch_directory", {"path": ".", "recursive": True}, ctx)
    assert result.ok
    assert result.data["status"] == "ok"
    assert result.data["running"] is True


def test_watch_file_tool(tmp_path):
    root = tree(tmp_path)
    registry, ctx = _ctx(root)
    result = _call(registry, "watch_file", {"path": "src/app.py"}, ctx)
    assert result.ok and result.data["status"] == "ok"


def test_file_metadata_tool(tmp_path):
    root = tree(tmp_path)
    registry, ctx = _ctx(root)
    result = _call(registry, "file_metadata", {"path": "src/app.py"}, ctx)
    assert result.ok and result.data["sha256"]


def test_find_references_tool(tmp_path):
    root = tree(tmp_path)
    registry, ctx = _ctx(root)
    result = _call(registry, "find_references", {"symbol": "calculateTotal"}, ctx)
    assert result.ok and result.data["count"] >= 1
