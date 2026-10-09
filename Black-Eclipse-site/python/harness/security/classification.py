"""Tool → security-action classification — the migration map.

This is the ONE place that maps an effectful agent tool to the security
vocabulary `(action, resource, permission)`. It imports the canonical tool tuples
from `code/policy.py` rather than re-listing names, so a tool added to a
capability's effect set is classified here automatically (the bypass-audit test
asserts full coverage).

A tool that is not effectful (a read) is never passed to the effect authorizer at
all, so `classify_tool` returning None for an unknown name is safe: the security
layer simply does not see it, and the registry's own read/write gate applies.
"""

from __future__ import annotations

from typing import Any, Optional

from .models import (
    ACTION_BROWSER,
    ACTION_CODE_EXECUTE,
    ACTION_CODE_WRITE,
    ACTION_COMPUTER,
    ACTION_COMPUTER_FINANCE,
    ACTION_DB_READ,
    ACTION_DB_WRITE,
    ACTION_DEPLOY_DEV,
    ACTION_DEPLOY_DESTROY,
    ACTION_DEPLOY_PRODUCTION,
    ACTION_DEPLOY_STAGING,
    ACTION_EXTERNAL,
    ACTION_FS_DELETE,
    ACTION_FS_WRITE,
    ACTION_GIT_EXTERNAL,
    ACTION_GIT_WRITE,
    ACTION_INFRA_DESTROY,
    ACTION_INFRA_WRITE,
    ACTION_MCP_INVOKE,
    ACTION_PLUGIN_INVOKE,
    ACTION_SHELL_EXECUTE,
    ACTION_SKILL_EXECUTE,
    ACTION_VISION,
    Permission,
)

_PATH_KEYS = ("path", "filePath", "file", "target", "destination", "newPath", "directory", "from")
_COMMAND_KEYS = ("command", "cmd", "program", "script", "code")
_URL_KEYS = ("url", "href", "uri", "source")
_GENERIC_RESOURCE_KEYS = (
    "resource", "name", "service", "container", "stack", "app", "operation",
    "repository", "remote", "provider",
)


def _first_str(args: dict[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        value = (args or {}).get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _path(args: dict[str, Any]) -> str:
    return _first_str(args, _PATH_KEYS)


def _program(args: dict[str, Any]) -> str:
    command = _first_str(args, _COMMAND_KEYS)
    return command.split(None, 1)[0].casefold() if command else ""


def _resource(args: dict[str, Any]) -> str:
    return _first_str(args, _GENERIC_RESOURCE_KEYS)


_FS_DELETE_TOOLS = ("delete_file", "delete_directory", "remove_file", "remove_directory")
_CODE_WRITE_TOOLS = (
    "scaffold_kit", "workspace_patch_apply", "workspace_revert", "workspace_write_file",
)
_SERVICE_CONTROL_TOOLS = (
    "stop_service", "restart_service", "cancel_execution", "process_kill",
    "stop_process", "restart_process", "kill_process",
)
_DB_TOOLS = {"execute_sql": ACTION_DB_WRITE}
_DEPLOY_TOOLS = {
    "deploy_run": ACTION_DEPLOY_DEV,
    "deploy_promote": ACTION_DEPLOY_STAGING,
    "deploy_rollback": ACTION_DEPLOY_STAGING,
    "deploy_delete": ACTION_DEPLOY_DESTROY,
}


def classify_tool(tool_name: str, args: dict[str, Any]) -> Optional[tuple[str, str, Permission]]:
    """Map a tool to `(action, resource, permission)`, or None when not effectful."""
    from ..code import policy  # noqa: PLC0415 - local import keeps import order simple

    name = str(tool_name or "")
    if not name:
        return None
    a = args or {}

    # ── filesystem ───────────────────────────────────────────────────────────
    if name in _FS_DELETE_TOOLS:
        return ACTION_FS_DELETE, _path(a), Permission.DELETE
    if name in policy.FS_WRITE_TOOLS or name in policy.INTEL_WRITE_TOOLS or name in _CODE_WRITE_TOOLS:
        return ACTION_FS_WRITE, _path(a), Permission.WRITE

    # ── database (via SQL execution) ─────────────────────────────────────────
    if name in _DB_TOOLS:
        return _DB_TOOLS[name], _first_str(a, ("sql",)) or _resource(a), Permission.WRITE

    # ── shell / code execution / process control ─────────────────────────────
    if name in policy.TERMINAL_WRITE_TOOLS or name in _SERVICE_CONTROL_TOOLS:
        if name in policy.TERMINAL_WRITE_TOOLS and name.split("_")[0] in ("open", "close", "resize", "write", "send"):
            # session/process plumbing still executes; classify by program when known
            return ACTION_SHELL_EXECUTE, _program(a) or _resource(a), Permission.EXECUTE
        return ACTION_SHELL_EXECUTE, _program(a) or _resource(a), Permission.EXECUTE
    if name in policy.WRITE_TOOLS:
        # command_run/terminal_run/shell_run/execute_* / build/test/run_verification
        if name in _SERVICE_CONTROL_TOOLS:
            return ACTION_SHELL_EXECUTE, _program(a) or _resource(a), Permission.EXECUTE
        return ACTION_CODE_EXECUTE, _program(a) or _resource(a), Permission.EXECUTE
    if name.startswith("execute_") or name.startswith("command_") or name.startswith("shell_"):
        return ACTION_SHELL_EXECUTE, _program(a) or _resource(a), Permission.EXECUTE

    # ── git / VCS ────────────────────────────────────────────────────────────
    if name in policy.GIT_EXTERNAL_TOOLS:
        return ACTION_GIT_EXTERNAL, _resource(a) or _path(a), Permission.EXECUTE
    if name in policy.GIT_WRITE_TOOLS:
        return ACTION_GIT_WRITE, _resource(a) or _path(a), Permission.WRITE

    # ── external actions (commit/push/PR/deploy) ─────────────────────────────
    if name in policy.EXTERNAL_ACTION_TOOLS:
        if name == "code_deploy":
            return ACTION_DEPLOY_DEV, _resource(a), Permission.ADMIN
        if name == "code_commit":
            return ACTION_GIT_WRITE, _resource(a), Permission.WRITE
        return ACTION_GIT_EXTERNAL, _resource(a), Permission.EXECUTE

    # ── application runtime / infrastructure / deployment ────────────────────
    if name in policy.APP_RUNTIME_K8S_WRITE_TOOLS:
        if name in _DEPLOY_TOOLS:
            return _DEPLOY_TOOLS[name], _resource(a), Permission.ADMIN
        if name in ("terraform_destroy", "k8s_delete"):
            return ACTION_INFRA_DESTROY, _resource(a), Permission.ADMIN
        return ACTION_INFRA_WRITE, _resource(a), Permission.ADMIN
    if name in policy.APP_RUNTIME_WRITE_TOOLS:
        return ACTION_INFRA_WRITE, _resource(a) or _resource({"service": _first_str(a, ("name", "package"))}), Permission.ADMIN

    # ── browser (only the effectful set; navigate/click are gated in-handler) ─
    if name in policy.BROWSER_EFFECTFUL_TOOLS:
        url = _first_str(a, _URL_KEYS)
        return ACTION_BROWSER, url or _resource(a), Permission.NETWORK

    # ── computer use (+ financial firewall) ──────────────────────────────────
    if name in policy.COMPUTER_EFFECTFUL_TOOLS:
        if name == "computer_finance_prepare":
            return ACTION_COMPUTER_FINANCE, _resource(a), Permission.ADMIN
        return ACTION_COMPUTER, _resource(a), Permission.EXECUTE

    # ── vision / external media ──────────────────────────────────────────────
    if name in policy.VISION_EXTERNAL_TOOLS:
        return ACTION_VISION, _first_str(a, _URL_KEYS) or _path(a), Permission.NETWORK

    # ── plugin / MCP / skill ─────────────────────────────────────────────────
    if name.startswith("mcp__") or name.startswith("mcp_"):
        return ACTION_MCP_INVOKE, name, Permission.EXECUTE
    if name.startswith("plugin_") or name.startswith("plug_"):
        return ACTION_PLUGIN_INVOKE, name, Permission.EXECUTE
    if name.startswith("skill_"):
        return ACTION_SKILL_EXECUTE, name, Permission.READ

    return None


def effect_tool_names() -> set[str]:
    """Every tool name the classifier is expected to cover (for the bypass audit).

    Prefix families (mcp__/plugin_/skill_) are matched by `classify_tool`, so they
    are not enumerated here.
    """
    from ..code import policy  # noqa: PLC0415

    names: set[str] = set()
    for group in (
        policy.FS_WRITE_TOOLS,
        policy.WRITE_TOOLS,
        policy.INTEL_WRITE_TOOLS,
        policy.GIT_WRITE_TOOLS,
        policy.GIT_EXTERNAL_TOOLS,
        policy.EXTERNAL_ACTION_TOOLS,
        policy.APP_RUNTIME_WRITE_TOOLS,
        policy.APP_RUNTIME_K8S_WRITE_TOOLS,
        policy.BROWSER_EFFECTFUL_TOOLS,
        policy.COMPUTER_EFFECTFUL_TOOLS,
        policy.VISION_EXTERNAL_TOOLS,
        policy.TERMINAL_WRITE_TOOLS,
    ):
        names.update(group)
    names.update({"workspace_patch_apply", "workspace_revert"})
    return names


__all__ = ["classify_tool", "effect_tool_names"]
