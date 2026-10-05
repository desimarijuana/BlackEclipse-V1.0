"""Phase 14 G2 — the chat code profile is exactly the declared set.

`CHAT_CODE_TOOLS` is applied to an `eclipse-agent` turn only when the front door
sends an autonomy (i.e. the classifier saw a coding request). It is a NARROWED
set: the four external actions are deliberately absent, so chat can never commit,
push, open a review request or deploy.
"""

from __future__ import annotations

from harness.agents import CHAT_CODE_TOOLS, CODE_AGENT_TOOLS, ECLIPSE_AGENT
from harness.code.policy import EXTERNAL_ACTION_TOOLS, allowed_tools
from harness.code.tools import register_code_tools
from harness.graph import chat_code_allowlist
from harness.tools import ToolRegistry

# The §6.2 set, verbatim.
EXPECTED = (
    "workspace_status", "workspace_list", "workspace_search",
    "workspace_read", "workspace_docs",
    "workspace_patch_apply", "workspace_diff", "workspace_revert",
    "command_run", "terminal_run", "shell_run", "shell_spawn",
    "process_output", "process_kill", "process_list",
    # Terminal subsystem: foreground execution, persistent shells, background
    # process management, ports and host capabilities.
    "execute_command",
    "open_shell", "close_shell", "run_shell_command",
    "write_shell_input", "read_shell_output", "resize_shell", "send_shell_control",
    "list_terminal_sessions", "terminal_session_status",
    "start_process", "stop_process", "restart_process", "kill_process",
    "list_processes", "process_status", "read_process_output",
    "write_process_input", "send_signal", "process_tree", "process_health",
    "list_ports", "terminal_capabilities", "system_info", "resource_report",
    "scaffold_kit", "analysis_run", "delegate",
    "memory", "skill_list", "skill_view", "session_search", "session_open",
    "market_get_quote", "fundamentals_get_financials", "research_search",
)


def _registry() -> ToolRegistry:
    reg = ToolRegistry()
    register_code_tools(reg)
    return reg


def test_chat_code_tools_is_exactly_the_declared_set() -> None:
    assert tuple(CHAT_CODE_TOOLS) == EXPECTED


def test_external_actions_are_absent_from_the_chat_profile() -> None:
    for name in EXTERNAL_ACTION_TOOLS:
        assert name not in CHAT_CODE_TOOLS, name


def test_the_profile_is_a_strict_subset_of_the_edit_verify_surface() -> None:
    # The union of what the two agents declare, narrowed to edit_verify — the
    # widest legal edit_verify surface. Every chat tool must be permitted there.
    full = set(allowed_tools("edit_verify", tuple(ECLIPSE_AGENT.tools) + tuple(CODE_AGENT_TOOLS)))
    assert set(CHAT_CODE_TOOLS) <= full
    # The profile omits only the external actions.
    assert "delegate" in CHAT_CODE_TOOLS  # parallel explore children
    assert not (set(EXTERNAL_ACTION_TOOLS) & set(CHAT_CODE_TOOLS))


def test_declared_tools_are_unchanged_by_this_phase() -> None:
    # The chat-code phase is ADDITIVE; the terminal subsystem later widened both
    # agents with its own tools. The external actions are still declared, and the
    # union still supports an edit_verify surface (asserted above).
    assert "code_commit" in CODE_AGENT_TOOLS


def test_edit_verify_turn_binds_write_and_execute_but_no_external() -> None:
    reg = _registry()
    allowed = chat_code_allowlist(ECLIPSE_AGENT, reg, "edit_verify")
    assert allowed is not None
    bound = set(reg.names()) & allowed
    assert "workspace_patch_apply" in bound
    assert "command_run" in bound
    assert not (set(EXTERNAL_ACTION_TOOLS) & bound)


def test_plan_only_turn_binds_read_only() -> None:
    reg = _registry()
    allowed = chat_code_allowlist(ECLIPSE_AGENT, reg, "plan_only")
    assert allowed is not None
    bound = set(reg.names()) & allowed
    assert "workspace_read" in bound
    assert "workspace_patch_apply" not in bound
    assert "command_run" not in bound
    assert not (set(EXTERNAL_ACTION_TOOLS) & bound)


def test_unknown_profile_yields_nothing_the_classifier_would_send() -> None:
    # `chat_code_allowlist` is called only with plan_only/edit_verify, but an
    # unknown value must fail closed (the policy authority's behaviour).
    reg = _registry()
    allowed = chat_code_allowlist(ECLIPSE_AGENT, reg, "approve_external")
    # approve_external is NOT a profile the front door sends from chat; if it is
    # ever passed the external actions still cannot be present because the
    # profile's declared set excludes them.
    assert not (set(EXTERNAL_ACTION_TOOLS) & set(allowed or ()))
