"""Bypass audit — every effectful capability is classified through the gateway.

This is the regression guard for the spec's invariant "no tool may bypass the
gateway": every tool name in the canonical effect sets must map to a security
action, so the effect authorizer routes it through `SecurityGateway`.
"""

from __future__ import annotations

import os
import tempfile

os.environ.setdefault(
    "AGENT_MEMORY_DB_PATH",
    os.path.join(tempfile.mkdtemp(prefix="be-sec-bypass-"), "agent-memory.db"),
)

from harness.security.classification import classify_tool, effect_tool_names
from harness.security.models import Permission


def test_every_effect_tool_is_classified():
    missing = sorted(name for name in effect_tool_names() if classify_tool(name, {}) is None)
    assert missing == [], f"un-migrated effect tools (would bypass the gateway): {missing}"


def test_capability_specific_mappings():
    cases = {
        "write_file": "filesystem.write",
        "delete_file": "filesystem.delete",
        "command_run": "code.execute",
        "execute_python": "code.execute",
        "execute_sql": "database.write",
        "git_commit": "git.write",
        "git_push": "git.external",
        "deploy_run": "deploy.dev",
        "deploy_delete": "deploy.destroy",
        "terraform_destroy": "infrastructure.destroy",
        "k8s_apply": "infrastructure.write",
        "browser_upload": "browser.action",
        "computer_finance_prepare": "computer.finance",
        "image_generate": "vision.external",
        "package_install": "infrastructure.write",
    }
    for tool, expected in cases.items():
        result = classify_tool(tool, {})
        assert result is not None, tool
        assert result[0] == expected, f"{tool}: {result[0]} != {expected}"


def test_prefix_families_are_classified():
    assert classify_tool("mcp__server__tool", {})[0] == "mcp.invoke"
    assert classify_tool("plugin_foo", {})[0] == "plugin.invoke"
    assert classify_tool("plug_foo", {})[0] == "plugin.invoke"
    assert classify_tool("skill_run", {})[0] == "skill.execute"


def test_read_only_tools_are_not_effect_classified():
    # A read is never passed to the effect authorizer; the classifier returns None.
    for tool in ("read_file", "list_directory", "git_status", "browser_navigate", "workspace_read"):
        assert classify_tool(tool, {}) is None


def test_resource_is_extracted_for_floor_matching():
    assert classify_tool("write_file", {"path": "/home/u/.ssh/id_rsa"})[1] == "/home/u/.ssh/id_rsa"
    action, resource, permission = classify_tool("browser_upload", {"url": "http://169.254.169.254/"})
    assert resource == "http://169.254.169.254/"
    assert permission is Permission.NETWORK
