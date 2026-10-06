"""Execution layer — unit tests for the state machine, diagnostics, projects
and policy engine.

These are pure and fast: no subprocesses. The integration/security tests live in
`test_execution_runtime.py` and `test_execution_security.py`.
"""

from __future__ import annotations

import pytest

from harness.execution.diagnostics import (
    DiagnosticEngine,
    normalize,
    parse_js_stack,
    parse_python_traceback,
    parse_typescript,
)
from harness.execution.models import ExecutionRequest, NetworkPolicy, ResourceLimits
from harness.execution.policy import (
    ExecutionPolicyEngine,
    classify_program,
    sanitize_secrets,
)
from harness.execution.projects import ProjectDetector, detect_language, language_from_extension
from harness.execution.state import (
    ExecutionState,
    StateMachine,
    can_transition,
    is_terminal,
)
from harness.code.policy import WorkspaceBinding
from harness.skills.permissions import Actor


# ── state machine ────────────────────────────────────────────────────────────


def test_state_machine_happy_path():
    machine = StateMachine()
    for state in (
        ExecutionState.VALIDATING, ExecutionState.PREPARING,
        ExecutionState.STARTING, ExecutionState.RUNNING, ExecutionState.COMPLETED,
    ):
        machine.to(state)
    assert machine.state is ExecutionState.COMPLETED
    assert machine.terminal
    assert machine.history[0] is ExecutionState.QUEUED


def test_terminal_states_have_no_outgoing_edges():
    for state in ExecutionState:
        if is_terminal(state):
            for target in ExecutionState:
                assert not can_transition(state, target)


def test_invalid_transition_is_refused():
    from harness.execution.state import InvalidTransition

    machine = StateMachine()
    with pytest.raises(InvalidTransition):
        machine.to(ExecutionState.RUNNING)  # must pass through VALIDATING/PREPARING
    with pytest.raises(InvalidTransition):
        machine.to(ExecutionState.QUEUED)  # never re-enter the initial state


def test_force_terminal_only_accepts_terminal():
    from harness.execution.state import InvalidTransition

    machine = StateMachine()
    with pytest.raises(InvalidTransition):
        machine.force_terminal(ExecutionState.RUNNING)
    machine.force_terminal(ExecutionState.CANCELLED)
    assert machine.state is ExecutionState.CANCELLED


# ── diagnostics ──────────────────────────────────────────────────────────────


def test_parse_typescript_diagnostics():
    output = "src/app.ts(42,17): error TS2339: Property 'foo' does not exist on type 'X'.\n"
    diags = parse_typescript(output)
    assert len(diags) == 1
    d = diags[0]
    assert (d.file, d.line, d.column) == ("src/app.ts", 42, 17)
    assert d.category == "compile"
    assert d.code == "TS2339"


def test_parse_python_traceback_yields_deepest_frame():
    output = (
        'Traceback (most recent call last):\n'
        '  File "src/user.py", line 10, in <module>\n'
        "    f()\n"
        '  File "src/user.py", line 91, in handle\n'
        "    raise ValueError('boom')\n"
        "ValueError: boom\n"
    )
    diags = parse_python_traceback(output)
    assert diags and diags[0].line == 91
    assert "ValueError: boom" in diags[0].message


def test_parse_js_stack_prefers_non_node_modules_frame():
    output = (
        "TypeError: Cannot read properties of undefined (reading 'x')\n"
        "    at node_modules/foo/index.js:1:1\n"
        "    at handle (src/user.ts:91:14)\n"
    )
    diags = parse_js_stack(output)
    assert diags
    assert diags[0].file == "src/user.ts"
    assert (diags[0].line, diags[0].column) == (91, 14)


def test_normalize_never_fabricates_for_empty_output():
    assert normalize("", language="python") == []
    assert normalize("   \n  ", language="typescript") == []


def test_normalize_generic_compiler_shape():
    diags = normalize("src/main.c:12:5: error: 'x' undeclared\n", language="c")
    assert diags and diags[0].file == "src/main.c" and diags[0].line == 12


def test_diagnostic_engine_merge_dedupes():
    engine = DiagnosticEngine()
    a = normalize("src/a.ts(1,1): error TS1: x\n", language="typescript")
    merged = engine.merge(a, a)
    assert len(merged) == 1


# ── language/project detection ─────────────────────────────────────────────────


def test_language_from_extension():
    assert language_from_extension("a.py") == "python"
    assert language_from_extension("a.tsx") == "typescript"
    assert language_from_extension("a.sql") == "sql"
    assert language_from_extension("a.unknown") == ""


def test_detect_language_priority_explicit_first():
    assert detect_language(explicit="python", entrypoint="x.ts") == "python"
    assert detect_language(entrypoint="x.ts") == "typescript"
    assert detect_language(code="#!/usr/bin/env python\nprint(1)") == "python"
    assert detect_language(code="SELECT 1 FROM t;") == "sql"


def test_project_detector_reads_manifests(tmp_path):
    (tmp_path / "package.json").write_text('{"scripts": {"test": "vitest"}, "devDependencies": {"typescript": "^5", "vitest": "^1"}}', encoding="utf-8")
    (tmp_path / "tsconfig.json").write_text("{}", encoding="utf-8")
    info = ProjectDetector().detect(tmp_path)
    assert info.primary_language == "typescript"
    assert info.test_framework == "vitest"
    assert "package.json" in info.manifests


def test_project_detector_python(tmp_path):
    (tmp_path / "requirements.txt").write_text("requests==2.0\npandas\n", encoding="utf-8")
    info = ProjectDetector().detect(tmp_path)
    assert info.primary_language == "python"
    assert "requests" in info.dependencies


# ── policy engine ─────────────────────────────────────────────────────────────


def _binding(tmp_path):
    return WorkspaceBinding(id="ws_1", root=tmp_path, base_revision="HEAD", strategy="direct")


def _request(binding, **kwargs):
    defaults = dict(language="python", workspace=binding, code="print(1)")
    defaults.update(kwargs)
    return ExecutionRequest(**defaults)


def test_risk_classification_is_policy_driven():
    assert classify_program(["node", "x.js"]).value == "SAFE"
    assert classify_program(["npm", "install"]).value == "LOW"
    assert classify_program(["sudo", "x"]).value == "HIGH"
    assert classify_program(["mkfs"]).value == "CRITICAL"
    assert classify_program(["totally-unknown-tool"]).value == "MEDIUM"


def test_policy_denies_without_execute_grant(tmp_path):
    engine = ExecutionPolicyEngine()
    binding = _binding(tmp_path)
    actor = Actor(id="u", operator=False, workspace_id="ws_1", autonomy="plan_only")
    decision = engine.evaluate_request(actor, binding, _request(binding))
    assert not decision.allowed
    assert decision.code == "PROFILE_DENIED"


def test_policy_allows_edit_verify_and_refuses_network_widening(tmp_path):
    engine = ExecutionPolicyEngine()
    binding = _binding(tmp_path)
    actor = Actor(id="u", operator=False, workspace_id="ws_1", autonomy="edit_verify")
    # A default (no-network) request is allowed.
    decision = engine.evaluate_request(actor, binding, _request(binding))
    assert decision.allowed
    assert decision.network_policy is NetworkPolicy.NONE
    # Asking for network under a profile that forbids it is REFUSED, never widened.
    denied = engine.evaluate_request(
        actor, binding, _request(binding, network_policy=NetworkPolicy.FULL),
    )
    assert not denied.allowed
    assert denied.code == "NETWORK_NOT_PERMITTED"


def test_policy_narrows_network_for_approve_external(tmp_path):
    engine = ExecutionPolicyEngine()
    binding = _binding(tmp_path)
    actor = Actor(id="u", operator=False, workspace_id="ws_1", autonomy="approve_external")
    decision = engine.evaluate_request(
        actor, binding, _request(binding, network_policy=NetworkPolicy.FULL),
    )
    assert decision.allowed
    # The profile ceiling is ALLOWLIST: a request for FULL is narrowed, not granted.
    assert decision.network_policy is NetworkPolicy.ALLOWLIST


def test_policy_forbids_secrets(tmp_path):
    engine = ExecutionPolicyEngine()
    binding = _binding(tmp_path)
    actor = Actor(id="u", operator=False, workspace_id="ws_1", autonomy="edit_verify")
    decision = engine.evaluate_request(actor, binding, _request(binding, secrets={".env": "x"}))
    assert not decision.allowed
    assert decision.code == "SECRET_FORBIDDEN"
    assert decision.error_class == "SECURITY_ERROR"


def test_sanitize_secrets_drops_forbidden_names():
    assert sanitize_secrets({"TOKEN": "abc", "AWS_SECRET_ACCESS_KEY": "x", ".env": "y"}) == {"TOKEN": "abc"}


def test_policy_requires_approval_for_high_risk(tmp_path):
    engine = ExecutionPolicyEngine()
    binding = _binding(tmp_path)
    actor = Actor(id="u", operator=False, workspace_id="ws_1", autonomy="edit_verify")
    decision = engine.evaluate_request(actor, binding, _request(binding), argv=["sudo", "ls"])
    assert decision.allowed
    assert decision.require_approval is True


def test_resource_limits_from_env(monkeypatch):
    monkeypatch.setenv("HARNESS_EXEC_MAX_MEMORY_MB", "2048")
    monkeypatch.setenv("HARNESS_EXEC_DEFAULT_TIMEOUT_MS", "12345")
    limits = ResourceLimits.from_env()
    assert limits.memory_limit_mb == 2048
    assert limits.timeout_ms == 12345


def test_resource_run_kwargs_translate_limits():
    from harness.execution.models import resource_run_kwargs

    limits = ResourceLimits(timeout_ms=60_000, memory_limit_mb=512, process_limit=16)
    kwargs = resource_run_kwargs(limits)
    assert kwargs["memory_mb"] == 512
    assert kwargs["process_limit"] == 16
    assert kwargs["cpu_seconds"] >= 60
