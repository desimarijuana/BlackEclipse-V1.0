"""Agent definitions — authored in Python.

Adding an agent is adding an `AgentConfig` here. Agents declare their tool
allowlist; the registry enforces it. The authoritative system prompt content
lives in `prompts.py`; `sys_prompt` below is exposed so the TS front door can
fetch it instead of carrying its own copy.
"""

from __future__ import annotations

from .prompts import (
    CODE_AGENT_SYSTEM_PROMPT,
    CODE_NAVIGATOR_SYSTEM_PROMPT,
    ECLIPSE_AGENT_SYSTEM_PROMPT,
)
from .schemas import AgentConfig

# The repository tools. Phase 1 shipped the five read tools; Phase 2 adds the
# write half (patch/diff/revert), which the run's autonomy profile gates. Kept as
# a named constant so the preset's closed allowlist is asserted in one place.
CODE_NAVIGATOR_TOOLS = [
    "workspace_status",
    "workspace_list",
    "workspace_search",
    "workspace_read",
    "workspace_docs",
    "workspace_patch_apply",
    "workspace_diff",
    "workspace_revert",
    "command_run",
    # File-system subsystem (Phase FS): list/read/search/symbols/references/
    # metadata/index/watch plus the minimal-patch edit tools. The write half is
    # removed at `plan_only`; every path is re-checked by the handler.
    "list_directory", "read_file", "search_text", "search_files", "find_files",
    "search_symbols", "find_references", "file_metadata", "file_hash",
    "file_permissions", "index_workspace", "watch_file", "watch_directory",
    "verify_file", "validate_changes", "git_status",
    "write_file", "create_file", "delete_file", "move_file", "copy_file",
    "rename_file", "create_directory", "delete_directory",
    "patch_file", "replace_text", "insert_text", "delete_text",
    "apply_diff", "multi_file_patch", "edit_file",
    # Terminal subsystem: foreground execution, persistent shells, background
    # processes and ports. The effectful ones are removed at `plan_only`.
    "execute_command",
    "open_shell", "close_shell", "run_shell_command",
    "write_shell_input", "read_shell_output", "resize_shell", "send_shell_control",
    "list_terminal_sessions", "terminal_session_status",
    "start_process", "stop_process", "restart_process", "kill_process",
    "list_processes", "process_status", "read_process_output",
    "write_process_input", "send_signal", "process_tree", "process_health",
    "list_ports", "terminal_capabilities", "system_info", "resource_report",
    # Code Intelligence & Understanding Engine (CIUE): semantic/structural
    # navigation over the whole project. All read-only except `code_rename_symbol`,
    # which the autonomy profile removes at `plan_only`.
    "code_get_definition", "code_find_references", "code_find_symbol",
    "code_search_symbols", "code_get_hover", "code_get_type",
    "code_get_diagnostics", "code_get_document_symbols", "code_get_callers",
    "code_get_callees", "code_get_call_hierarchy", "code_get_implementations",
    "code_get_imports", "code_get_exports", "code_get_dependencies",
    "code_get_dependents", "code_get_project_structure", "code_get_dependency_graph",
    "code_parse_file", "code_analyze_file", "code_organize_imports",
    "code_get_relevant_context", "code_index_workspace", "code_intel_status",
    "code_find_related_tests", "code_rename_symbol",
]

# Tool allowlist. The Phase-2 retrieval tools are the provider-agnostic path
# (the agent asks for the *objective*; the retrieval layer picks the source).
# The legacy JDdS-only tools are kept for compatibility.
#
# The truthful-capability tools (`get_capability_matrix`, `get_research_health`)
# are read-only diagnostics and MUST be in the allowlist: without them the agent
# was reduced to the coarser `get_coverage` and could not tell whether a market's
# statement route was implemented/configured (verified in the SYS/RELIANCE/Tata
# runs, where `get_capability_matrix` returned TOOL_FORBIDDEN). They stay
# read-only; no write tool is widened here.
ECLIPSE_AGENT = AgentConfig(
    id="eclipse-agent",
    name="Eclipse Agent",
    systemPrompt=ECLIPSE_AGENT_SYSTEM_PROMPT,
    tools=[
        # Phase-2 unified retrieval tools
        "market_get_quote",
        "market_get_ohlcv",
        "fundamentals_get_company_profile",
        "fundamentals_get_financials",
        "research_search",
        "research_retrieve_source",
        "research_search_news",
        "macro_get_series",
        # Phase-1 JDdS tools (still available)
        "get_market_snapshot",
        "get_fundamentals",
        "get_news",
        "get_source_health",
        "get_coverage",
        # Truthful per-capability diagnostics (read-only). Recognised ≠ working,
        # configured ≠ healthy, and zero attempts ≠ failure.
        "get_capability_matrix",
        "get_research_health",
        # Eclipse-Memory: persistent memory + progressive skill discovery and
        # explicit, permission-checked skill invocation as a controlled sub-run.
        "memory",
        "skill_list",
        "skill_view",
        "skill_invoke",
        # Full-session historical recall: read-only search/open over prior
        # sessions. Historical content is context, never current evidence.
        "session_search",
        "session_open",
        # Memory providers (M8): native-first search plus an explicitly separate
        # external search whose results are labelled unverified context.
        "memory_search_native",
        "memory_search_external",
        "memory_provider_status",
        # Phase 7: bounded fan-out of independent sub-questions (e.g. "review
        # these five companies"). A research capability, not only a code one.
        "delegate",
        # Phase 8: the analysis sandbox (compute a derived metric). OFF per run
        # unless the caller enables it (`RunRequest.analysisEnabled`).
        "analysis_run",
        # Phase 9: build a finance tool from a ready-made shape. Gated by the
        # run's editing profile (a workspace-bound code.write).
        "scaffold_kit",
        # Application Runtime (DevOps): the read-only surface is always available
        # ("inspect this project", "what's using port 3000", "is it healthy").
        # Starting/stopping an application requires a coding turn (the chat code
        # profile) so the write tools are NOT declared here.
        "runtime_detect", "runtime_capabilities", "runtime_inspect", "runtime_status",
        "runtime_health", "runtime_logs", "runtime_diagnose", "runtime_metrics",
        "package_detect", "package_version", "package_list",
        "container_list", "container_logs", "container_inspect", "container_health",
        "compose_validate", "compose_config", "compose_ps", "compose_logs",
        "environment_inspect", "environment_validate",
        "port_check", "port_find_free", "port_list", "port_identify_process",
        "health_check", "health_status",
        # Orchestration / infrastructure / cloud read-only surface (Kubernetes,
        # Terraform, deploy status) so the finance agent can answer "what's
        # deployed" without a coding turn. Mutations live on the code surface.
        "k8s_status", "k8s_get", "k8s_get_pods", "k8s_describe", "k8s_logs",
        "k8s_rollout", "helm_list", "helm_status", "kustomize_build",
        "terraform_validate", "terraform_plan", "terraform_output", "terraform_state",
        "cloud_providers", "deploy_status", "deploy_logs",
    ],
    maxSteps=8,
    # Per-tool CEILING (WS2). Each tool's own declared `timeout_ms` is
    # authoritative; this only bounds a tool that declares more. It is a distinct
    # budget from `runTimeoutMs` (the whole model turn). 30s lets the declared
    # `research_search_news` (30s) run in full instead of being clamped to 20s and
    # timing out, while still bounding any runaway call.
    toolTimeoutMs=30_000,
    runTimeoutMs=120_000,
    # MCP is a user-directed extension surface: the default agent may call the
    # MCP tools the operator has enabled and selected. This opt-in expands ONLY
    # to tools currently registered under the `mcp_` namespace (enabled server +
    # explicitly selected + read-only effect); it does not grant a tool that is
    # merely discovered. Custom agents and skills do NOT set this and keep their
    # exact allowlists.
    allowMcpTools=True,
)

# The read-only repository navigator (Phase 1). A SEPARATE preset, not the
# finance agent widened: its allowlist is ONLY the five read tools. It does NOT
# set `allowMcpTools`, so it keeps its exact, closed allowlist and can never
# reach a finance tool, an MCP tool or any other surface.
CODE_NAVIGATOR = AgentConfig(
    id="code-navigator",
    name="Repository Navigator",
    systemPrompt=CODE_NAVIGATOR_SYSTEM_PROMPT,
    tools=list(CODE_NAVIGATOR_TOOLS),
    maxSteps=10,
    toolTimeoutMs=30_000,
    runTimeoutMs=180_000,
)

# The coding agent (Phase 5). A SEPARATE preset that owns the code tools and NO
# finance tool. Its tool allowlist IS the autonomy boundary: `effective_allowlist`
# narrows it through `code.policy.allowed_tools(autonomy, ...)` before the model
# sees any schema, so at `plan_only` the write/execute tools are simply absent.
# It does NOT set `allowMcpTools` — a coding agent must not inherit the operator's
# MCP reach. The tools listed are the REAL names Phases 1-3 registered.
CODE_AGENT_TOOLS = [
    # Read / navigate (Phase 1)
    "workspace_status", "workspace_list", "workspace_search",
    "workspace_read", "workspace_docs",
    # Change (Phase 2) — effectful; removed at plan_only
    "workspace_patch_apply", "workspace_diff", "workspace_revert",
    # File-system subsystem (Phase FS) — read/inspect first, then minimal edits.
    "list_directory", "read_file", "search_text", "search_files", "find_files",
    "search_symbols", "find_references", "file_metadata", "file_hash",
    "file_permissions", "index_workspace", "watch_file", "watch_directory",
    "verify_file", "validate_changes", "git_status",
    "write_file", "create_file", "delete_file", "move_file", "copy_file",
    "rename_file", "create_directory", "delete_directory",
    "patch_file", "replace_text", "insert_text", "delete_text",
    "apply_diff", "multi_file_patch", "edit_file",
    # Command broker (Phase 3) — effectful; removed at plan_only
    "command_run",
    # Generic terminal (Phase D) — effectful; removed at plan_only. Safe
    # commands run directly, others need a per-command approval.
    "terminal_run",
    # Real shell (PowerShell/CMD/bash) with background processes.
    "shell_run", "shell_spawn", "process_output", "process_kill", "process_list",
    # Terminal subsystem: persistent shells, background process management, ports
    # and host capabilities. The command tools are effectful and removed at
    # `plan_only`; the rest are read-only. `execute_command` is the foreground
    # runner; `start_process` is the long-running one.
    "execute_command",
    "open_shell", "close_shell", "run_shell_command",
    "write_shell_input", "read_shell_output", "resize_shell", "send_shell_control",
    "list_terminal_sessions", "terminal_session_status",
    "start_process", "stop_process", "restart_process", "kill_process",
    "list_processes", "process_status", "read_process_output",
    "write_process_input", "send_signal", "process_tree", "process_health",
    "list_ports", "terminal_capabilities", "system_info", "resource_report",
    # Code Execution & Verification Layer (Phase EX): run code in a supported
    # language, build, test, discover tests, manage long-running services and read
    # back execution evidence. The write/execute half is removed at `plan_only`.
    "execute_code", "execute_python", "execute_javascript", "execute_typescript",
    "execute_sql", "execute_shell", "build_project", "test_project",
    "run_verification", "discover_tests",
    "start_service", "stop_service", "restart_service",
    "service_status", "service_logs", "list_services",
    "execution_get", "execution_logs", "execution_result",
    "execution_artifacts", "cancel_execution",
    # Application Runtime layer (DevOps): discover/prepare/run/observe apps,
    # package managers, Docker/Podman/Compose, environment, ports and health.
    # The write half is removed at `plan_only` by `code.policy.allowed_tools`.
    "runtime_detect", "runtime_capabilities", "runtime_inspect", "runtime_status",
    "runtime_health", "runtime_logs", "runtime_reconcile", "runtime_diagnose",
    "runtime_metrics", "runtime_start", "runtime_stop", "runtime_restart",
    "runtime_cleanup", "runtime_recover",
    "package_detect", "package_version", "package_list", "package_audit",
    "package_install", "package_add", "package_remove", "package_update",
    "package_run", "package_build", "package_test",
    "container_logs", "container_inspect", "container_stats", "container_list",
    "container_images", "container_health", "container_build", "container_run",
    "container_start", "container_stop", "container_restart", "container_exec",
    "container_remove", "container_pull", "container_rmi", "container_network",
    "container_volume",
    "compose_validate", "compose_config", "compose_ps", "compose_logs",
    "compose_build", "compose_up", "compose_down", "compose_start",
    "compose_stop", "compose_restart", "compose_exec", "compose_pull", "compose_rm",
    "environment_inspect", "environment_validate", "environment_load",
    "environment_compare", "environment_set", "environment_unset",
    "port_check", "port_find_free", "port_list", "port_identify_process",
    "health_check", "health_status",
    # Orchestration / infrastructure / cloud (Kubernetes, Helm, Kustomize,
    # Terraform, deploy). Cluster/infra/cloud mutations need `approve_external`.
    "k8s_status", "k8s_get", "k8s_get_pods", "k8s_describe", "k8s_logs",
    "k8s_rollout", "helm_list", "helm_status", "kustomize_build",
    "terraform_init", "terraform_validate", "terraform_fmt", "terraform_plan",
    "terraform_output", "terraform_state",
    "cloud_providers", "deploy_status", "deploy_logs",
    "k8s_apply", "k8s_delete", "k8s_scale", "k8s_exec",
    "helm_install", "helm_uninstall",
    "terraform_apply", "terraform_destroy",
    "deploy_run", "deploy_rollback", "deploy_delete",
    # Verification (Phase 4) — the final answer is checked against the ledger.
    # Memory/session recall stays available: read-only context, NOT the finance family.
    "memory", "skill_list", "skill_view", "session_search", "session_open",
    # Code Intelligence & Understanding Engine (CIUE): semantic/structural
    # navigation + the one semantic rename. The write tool is removed at `plan_only`.
    "code_get_definition", "code_find_references", "code_find_symbol",
    "code_search_symbols", "code_get_hover", "code_get_type",
    "code_get_diagnostics", "code_get_document_symbols", "code_get_callers",
    "code_get_callees", "code_get_call_hierarchy", "code_get_implementations",
    "code_get_imports", "code_get_exports", "code_get_dependencies",
    "code_get_dependents", "code_get_project_structure", "code_get_dependency_graph",
    "code_parse_file", "code_analyze_file", "code_organize_imports",
    "code_get_relevant_context", "code_index_workspace", "code_intel_status",
    "code_find_related_tests", "code_rename_symbol",
    # External actions (Phase 5) — approve_external only, each single-use approved.
    "code_commit", "code_push", "code_open_pr", "code_deploy",
    # Git / Version-Control subsystem (the Git engine). Read + LOCAL mutation +
    # REMOTE. The autonomy boundary is applied by `code.policy.allowed_tools`, and
    # the Git effect authorizer gates every dangerous/destructive operation and
    # every remote action with a single-use operator approval.
    "git_repository_info", "git_list_repositories", "git_status", "git_diff",
    "git_diff_cached", "git_diff_range", "git_log", "git_show", "git_commit_info",
    "git_blame", "git_reflog", "git_branch_list", "git_conflicts",
    "git_operation_state", "git_stash_list", "git_stash_show", "git_tag_list",
    "git_remote_list", "git_worktree_list", "git_submodule_list", "git_config_get",
    "git_config_list", "git_hooks", "git_lfs_status", "git_clean_preview",
    "git_ignore_check", "git_generate_commit_message", "git_recovery_options", "git_list_hunks",
    "git_stage", "git_unstage", "git_stage_hunks", "git_unstage_hunks", "git_apply_patch",
    "git_commit", "git_generate_and_commit",
    "git_create_branch", "git_checkout", "git_delete_branch", "git_rename_branch",
    "git_set_upstream", "git_merge", "git_merge_abort", "git_merge_continue",
    "git_rebase", "git_rebase_plan", "git_rebase_abort", "git_rebase_continue", "git_rebase_skip",
    "git_cherry_pick", "git_cherry_pick_abort", "git_cherry_pick_continue",
    "git_revert", "git_revert_abort", "git_revert_continue", "git_reset",
    "git_resolve_conflict", "git_abort_operation", "git_continue_operation",
    "git_stash_push", "git_stash_apply", "git_stash_pop", "git_stash_drop",
    "git_tag_create", "git_tag_delete", "git_worktree_add", "git_worktree_remove",
    "git_submodule_update", "git_bisect_start", "git_bisect_mark", "git_bisect_reset",
    "git_clean", "git_config_set",
    "git_move_path", "git_remove_paths", "git_restore", "git_unset_upstream",
    "git_stash_branch", "git_stash_clear", "git_worktree_prune", "git_worktree_move",
    "git_submodule_init", "git_submodule_sync", "git_lfs_fetch", "git_lfs_pull",
    "git_fetch", "git_pull", "git_push", "git_remote_add", "git_remote_remove",
    "git_remote_set_url", "git_tag_push",
    "vcs_status", "vcs_list_repositories", "vcs_get_repository", "vcs_list_branches",
    "vcs_list_commits", "vcs_get_pull_request", "vcs_list_pull_requests",
    "vcs_list_reviews", "vcs_get_review_comments", "vcs_ci_status",
    "vcs_list_workflow_runs", "vcs_get_job_logs", "vcs_generate_pull_request",
    "vcs_create_branch", "vcs_create_pull_request", "vcs_update_pull_request",
    "vcs_close_pull_request", "vcs_merge_pull_request", "vcs_request_review",
    "vcs_reply_review_comment", "vcs_rerun_workflow", "vcs_cancel_workflow",
    # Bounded fan-out (Phase 7) — independent sub-tasks in parallel.
    "delegate",
    # Analysis sandbox (Phase 8) — compute a derived metric in isolation.
    "analysis_run",
    # Scaffold kits (Phase 9) — build a finance tool from a ready-made shape.
    "scaffold_kit",
]

CODE_AGENT = AgentConfig(
    id="code-agent",
    name="Eclipse Code Agent",
    systemPrompt=CODE_AGENT_SYSTEM_PROMPT,
    tools=list(CODE_AGENT_TOOLS),
    maxSteps=24,               # a code task legitimately needs more turns than a query
    toolTimeoutMs=120_000,     # a unit-test/build run is slower than a data fetch
    # The AgentConfig run ceiling is 600_000; the Phase 4 repair wall-clock budget
    # is enforced separately inside the loop.
    runTimeoutMs=600_000,
    # Deliberately ABSENT: allowMcpTools.
)

# The CHAT code profile (Phase 14 §6.2). ADDITIVE: `ECLIPSE_AGENT`'s declared
# tools are NOT touched. When the front door recognizes a coding request it sends
# an `autonomy`; the resolver then NARROWS the finance agent's run to this set for
# that turn only, exactly as the code-agent narrows through `code.policy`.
#
# It is still narrow: the read/navigate tools plus the write/execute/verify tools,
# and deliberately NO external action — `code_commit`/`code_push`/`code_open_pr`/
# `code_deploy` stay on the Code Tasks surface where the approval panel lives.
CHAT_CODE_TOOLS: tuple[str, ...] = (
    "workspace_status", "workspace_list", "workspace_search",
    "workspace_read", "workspace_docs",
    "workspace_patch_apply", "workspace_diff", "workspace_revert",
    "command_run", "terminal_run", "shell_run", "shell_spawn",
    "process_output", "process_kill", "process_list",
    # File-system subsystem (Phase FS): read/inspect always; the write/edit half
    # is removed at `plan_only` by the ONE policy authority.
    "list_directory", "read_file", "search_text", "search_files", "find_files",
    "search_symbols", "find_references", "file_metadata", "file_hash",
    "file_permissions", "index_workspace", "watch_file", "watch_directory",
    "verify_file", "validate_changes", "git_status",
    "write_file", "create_file", "delete_file", "move_file", "copy_file",
    "rename_file", "create_directory", "delete_directory",
    "patch_file", "replace_text", "insert_text", "delete_text",
    "apply_diff", "multi_file_patch", "edit_file",
    # Terminal subsystem (persistent shells + background processes + ports).
    "execute_command",
    "open_shell", "close_shell", "run_shell_command",
    "write_shell_input", "read_shell_output", "resize_shell", "send_shell_control",
    "list_terminal_sessions", "terminal_session_status",
    "start_process", "stop_process", "restart_process", "kill_process",
    "list_processes", "process_status", "read_process_output",
    "write_process_input", "send_signal", "process_tree", "process_health",
    "list_ports", "terminal_capabilities", "system_info", "resource_report",
    "scaffold_kit", "analysis_run",
    # Code Execution & Verification Layer: run/build/test/discover + services +
    # evidence. The execute/build half is removed at `plan_only` by policy.
    "execute_code", "execute_python", "execute_javascript", "execute_typescript",
    "execute_sql", "execute_shell", "build_project", "test_project",
    "run_verification", "discover_tests",
    "start_service", "stop_service", "restart_service",
    "service_status", "service_logs", "list_services",
    "execution_get", "execution_logs", "execution_result",
    "execution_artifacts", "cancel_execution",
    # Application Runtime layer (DevOps) for a chat coding turn. The write half is
    # removed at `plan_only` by the ONE policy authority, so a question turn keeps
    # only the read-only surface.
    "runtime_detect", "runtime_capabilities", "runtime_inspect", "runtime_status",
    "runtime_health", "runtime_logs", "runtime_diagnose", "runtime_metrics",
    "runtime_start", "runtime_stop", "runtime_restart", "runtime_recover",
    "package_detect", "package_version", "package_list",
    "package_install", "package_run", "package_build", "package_test",
    "container_logs", "container_inspect", "container_list", "container_health",
    "compose_validate", "compose_config", "compose_ps", "compose_logs",
    "compose_up", "compose_down",
    "environment_inspect", "environment_validate",
    "port_check", "port_find_free", "port_list", "port_identify_process",
    "health_check", "health_status",
    # Orchestration / infra / cloud for a chat coding turn. Cluster/infra/cloud
    # mutations are removed at `edit_verify`/`plan_only` by the ONE policy authority.
    "k8s_status", "k8s_get", "k8s_get_pods", "k8s_describe", "k8s_logs",
    "k8s_rollout", "helm_list", "helm_status", "kustomize_build",
    "terraform_init", "terraform_validate", "terraform_plan",
    "terraform_output", "terraform_state",
    "cloud_providers", "deploy_status", "deploy_logs",
    "k8s_apply", "k8s_delete", "k8s_scale", "k8s_exec",
    "helm_install", "helm_uninstall", "terraform_apply", "terraform_destroy",
    "deploy_run", "deploy_rollback", "deploy_delete",
    # Code Intelligence & Understanding Engine (CIUE): semantic/structural
    # navigation + the one semantic rename (removed at `plan_only`).
    "code_get_definition", "code_find_references", "code_find_symbol",
    "code_search_symbols", "code_get_hover", "code_get_type",
    "code_get_diagnostics", "code_get_document_symbols", "code_get_callers",
    "code_get_callees", "code_get_call_hierarchy", "code_get_implementations",
    "code_get_imports", "code_get_exports", "code_get_dependencies",
    "code_get_dependents", "code_get_project_structure", "code_get_dependency_graph",
    "code_parse_file", "code_analyze_file", "code_organize_imports",
    "code_get_relevant_context", "code_index_workspace", "code_intel_status",
    "code_find_related_tests", "code_rename_symbol",
    # parallel read-only explore children for large codebases
    "delegate",
    # Git / Version-Control subsystem: read + LOCAL mutation only. External
    # actions (fetch/pull/push/PR/CI) stay on the Code Tasks surface beside the
    # approval panel, exactly like `code_commit`/`code_push`.
    "git_repository_info", "git_list_repositories", "git_status", "git_diff",
    "git_diff_cached", "git_diff_range", "git_log", "git_show", "git_commit_info",
    "git_blame", "git_reflog", "git_branch_list", "git_conflicts",
    "git_operation_state", "git_stash_list", "git_stash_show", "git_tag_list",
    "git_remote_list", "git_worktree_list", "git_submodule_list", "git_config_get",
    "git_config_list", "git_hooks", "git_lfs_status", "git_clean_preview",
    "git_ignore_check", "git_generate_commit_message", "git_recovery_options", "git_list_hunks",
    "git_stage", "git_unstage", "git_stage_hunks", "git_unstage_hunks", "git_apply_patch",
    "git_commit", "git_generate_and_commit",
    "git_create_branch", "git_checkout", "git_delete_branch", "git_rename_branch",
    "git_set_upstream", "git_merge", "git_merge_abort", "git_merge_continue",
    "git_rebase", "git_rebase_plan", "git_rebase_abort", "git_rebase_continue", "git_rebase_skip",
    "git_cherry_pick", "git_cherry_pick_abort", "git_cherry_pick_continue",
    "git_revert", "git_revert_abort", "git_revert_continue", "git_reset",
    "git_resolve_conflict", "git_abort_operation", "git_continue_operation",
    "git_stash_push", "git_stash_apply", "git_stash_pop", "git_stash_drop",
    "git_tag_create", "git_tag_delete", "git_worktree_add", "git_worktree_remove",
    "git_submodule_update", "git_bisect_start", "git_bisect_mark", "git_bisect_reset",
    "git_clean", "git_config_set",
    "git_move_path", "git_remove_paths", "git_restore", "git_unset_upstream",
    "git_stash_branch", "git_stash_clear", "git_worktree_prune", "git_worktree_move",
    "git_submodule_init", "git_submodule_sync", "git_lfs_fetch", "git_lfs_pull",
    # read-only context, unchanged from ECLIPSE_AGENT
    "memory", "skill_list", "skill_view", "session_search", "session_open",
    # finance tools stay available: a code change may need the vault for a fixture
    "market_get_quote", "fundamentals_get_financials", "research_search",
)
# Deliberately ABSENT: code_commit, code_push, code_open_pr, code_deploy.

AGENT_PRESETS: dict[str, AgentConfig] = {
    ECLIPSE_AGENT.id: ECLIPSE_AGENT,
    CODE_NAVIGATOR.id: CODE_NAVIGATOR,
    CODE_AGENT.id: CODE_AGENT,
}

DEFAULT_AGENT_ID = ECLIPSE_AGENT.id


def get_agent(agent_id: str) -> AgentConfig:
    agent = AGENT_PRESETS.get(agent_id)
    if agent is None:
        known = ", ".join(AGENT_PRESETS.keys())
        raise ValueError(f"Unknown agent {agent_id!r}. Known: {known}")
    return agent


__all__ = [
    "AGENT_PRESETS",
    "CHAT_CODE_TOOLS",
    "CODE_AGENT",
    "CODE_AGENT_TOOLS",
    "CODE_NAVIGATOR",
    "CODE_NAVIGATOR_TOOLS",
    "DEFAULT_AGENT_ID",
    "ECLIPSE_AGENT",
    "get_agent",
]
