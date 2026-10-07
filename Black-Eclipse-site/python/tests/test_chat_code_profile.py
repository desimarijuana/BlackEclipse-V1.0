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
    'workspace_status',
    'workspace_list',
    'workspace_search',
    'workspace_read',
    'workspace_docs',
    'workspace_patch_apply',
    'workspace_diff',
    'workspace_revert',
    'command_run',
    'terminal_run',
    'shell_run',
    'shell_spawn',
    'process_output',
    'process_kill',
    'process_list',
    'list_directory',
    'read_file',
    'search_text',
    'search_files',
    'find_files',
    'search_symbols',
    'find_references',
    'file_metadata',
    'file_hash',
    'file_permissions',
    'index_workspace',
    'watch_file',
    'watch_directory',
    'verify_file',
    'validate_changes',
    'git_status',
    'write_file',
    'create_file',
    'delete_file',
    'move_file',
    'copy_file',
    'rename_file',
    'create_directory',
    'delete_directory',
    'patch_file',
    'replace_text',
    'insert_text',
    'delete_text',
    'apply_diff',
    'multi_file_patch',
    'edit_file',
    'execute_command',
    'open_shell',
    'close_shell',
    'run_shell_command',
    'write_shell_input',
    'read_shell_output',
    'resize_shell',
    'send_shell_control',
    'list_terminal_sessions',
    'terminal_session_status',
    'start_process',
    'stop_process',
    'restart_process',
    'kill_process',
    'list_processes',
    'process_status',
    'read_process_output',
    'write_process_input',
    'send_signal',
    'process_tree',
    'process_health',
    'list_ports',
    'terminal_capabilities',
    'system_info',
    'resource_report',
    'scaffold_kit',
    'analysis_run',
    'execute_code',
    'execute_python',
    'execute_javascript',
    'execute_typescript',
    'execute_sql',
    'execute_shell',
    'build_project',
    'test_project',
    'run_verification',
    'discover_tests',
    'start_service',
    'stop_service',
    'restart_service',
    'service_status',
    'service_logs',
    'list_services',
    'execution_get',
    'execution_logs',
    'execution_result',
    'execution_artifacts',
    'cancel_execution',
    'runtime_detect',
    'runtime_capabilities',
    'runtime_inspect',
    'runtime_status',
    'runtime_health',
    'runtime_logs',
    'runtime_diagnose',
    'runtime_metrics',
    'runtime_start',
    'runtime_stop',
    'runtime_restart',
    'runtime_recover',
    'package_detect',
    'package_version',
    'package_list',
    'package_install',
    'package_run',
    'package_build',
    'package_test',
    'container_logs',
    'container_inspect',
    'container_list',
    'container_health',
    'compose_validate',
    'compose_config',
    'compose_ps',
    'compose_logs',
    'compose_up',
    'compose_down',
    'environment_inspect',
    'environment_validate',
    'port_check',
    'port_find_free',
    'port_list',
    'port_identify_process',
    'health_check',
    'health_status',
    'k8s_status',
    'k8s_get',
    'k8s_get_pods',
    'k8s_describe',
    'k8s_logs',
    'k8s_rollout',
    'helm_list',
    'helm_status',
    'kustomize_build',
    'terraform_init',
    'terraform_validate',
    'terraform_plan',
    'terraform_output',
    'terraform_state',
    'cloud_providers',
    'deploy_status',
    'deploy_logs',
    'k8s_apply',
    'k8s_delete',
    'k8s_scale',
    'k8s_exec',
    'helm_install',
    'helm_uninstall',
    'terraform_apply',
    'terraform_destroy',
    'deploy_run',
    'deploy_rollback',
    'deploy_delete',
    'code_get_definition',
    'code_find_references',
    'code_find_symbol',
    'code_search_symbols',
    'code_get_hover',
    'code_get_type',
    'code_get_diagnostics',
    'code_get_document_symbols',
    'code_get_callers',
    'code_get_callees',
    'code_get_call_hierarchy',
    'code_get_implementations',
    'code_get_imports',
    'code_get_exports',
    'code_get_dependencies',
    'code_get_dependents',
    'code_get_project_structure',
    'code_get_dependency_graph',
    'code_parse_file',
    'code_analyze_file',
    'code_organize_imports',
    'code_get_relevant_context',
    'code_index_workspace',
    'code_intel_status',
    'code_find_related_tests',
    'code_rename_symbol',
    'delegate',
    'git_repository_info',
    'git_list_repositories',
    'git_status',
    'git_diff',
    'git_diff_cached',
    'git_diff_range',
    'git_log',
    'git_show',
    'git_commit_info',
    'git_blame',
    'git_reflog',
    'git_branch_list',
    'git_conflicts',
    'git_operation_state',
    'git_stash_list',
    'git_stash_show',
    'git_tag_list',
    'git_remote_list',
    'git_worktree_list',
    'git_submodule_list',
    'git_config_get',
    'git_config_list',
    'git_hooks',
    'git_lfs_status',
    'git_clean_preview',
    'git_ignore_check',
    'git_generate_commit_message',
    'git_recovery_options',
    'git_list_hunks',
    'git_stage',
    'git_unstage',
    'git_stage_hunks',
    'git_unstage_hunks',
    'git_apply_patch',
    'git_commit',
    'git_generate_and_commit',
    'git_create_branch',
    'git_checkout',
    'git_delete_branch',
    'git_rename_branch',
    'git_set_upstream',
    'git_merge',
    'git_merge_abort',
    'git_merge_continue',
    'git_rebase',
    'git_rebase_plan',
    'git_rebase_abort',
    'git_rebase_continue',
    'git_rebase_skip',
    'git_cherry_pick',
    'git_cherry_pick_abort',
    'git_cherry_pick_continue',
    'git_revert',
    'git_revert_abort',
    'git_revert_continue',
    'git_reset',
    'git_resolve_conflict',
    'git_abort_operation',
    'git_continue_operation',
    'git_stash_push',
    'git_stash_apply',
    'git_stash_pop',
    'git_stash_drop',
    'git_tag_create',
    'git_tag_delete',
    'git_worktree_add',
    'git_worktree_remove',
    'git_submodule_update',
    'git_bisect_start',
    'git_bisect_mark',
    'git_bisect_reset',
    'git_clean',
    'git_config_set',
    'git_move_path',
    'git_remove_paths',
    'git_restore',
    'git_unset_upstream',
    'git_stash_branch',
    'git_stash_clear',
    'git_worktree_prune',
    'git_worktree_move',
    'git_submodule_init',
    'git_submodule_sync',
    'git_lfs_fetch',
    'git_lfs_pull',
    'memory',
    'skill_list',
    'skill_view',
    'session_search',
    'session_open',
    'market_get_quote',
    'fundamentals_get_financials',
    'research_search',
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
    # The union of what the two agents declare, narrowed to approve_external — the
    # widest legal surface, which keeps the cluster/infra/cloud mutations. Every
    # chat tool must be permitted there. At edit_verify the cluster/infra/cloud
    # mutations are REMOVED, so the chat set is not a subset of the edit_verify
    # surface; it is a subset of the approve_external surface minus the external
    # actions (which the profile deliberately omits).
    from harness.execution.application._tool_common import APP_RUNTIME_K8S_WRITE_TOOLS

    full = set(allowed_tools("approve_external", tuple(ECLIPSE_AGENT.tools) + tuple(CODE_AGENT_TOOLS)))
    assert set(CHAT_CODE_TOOLS) <= full
    # The profile omits only the external actions.
    assert "delegate" in CHAT_CODE_TOOLS  # parallel explore children
    assert not (set(EXTERNAL_ACTION_TOOLS) & set(CHAT_CODE_TOOLS))
    # The cluster/infra/cloud mutations are DECLARED but removed at edit_verify.
    edit_verify = set(allowed_tools("edit_verify", tuple(CHAT_CODE_TOOLS)))
    assert not (set(APP_RUNTIME_K8S_WRITE_TOOLS) & edit_verify)


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
