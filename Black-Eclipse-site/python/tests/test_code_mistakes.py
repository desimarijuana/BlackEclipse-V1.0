"""Phase 4 — the six deterministic code mistake categories.

Each category is recorded from a synthetic run, and NOT recorded when its signal
is absent (the negative cases matter as much as the positive ones).
"""

from __future__ import annotations

from harness.eclipse_memory.mistakes import CATEGORIES, _SEVERITY, analyze_run_for_mistakes


class _RunStore:
    def __init__(self, run, events=None, tools=None):
        self._run = run
        self._events = events or []
        self._tools = tools or []

    def get_run(self, run_id):
        return self._run

    def list_events(self, run_id):
        return self._events

    def list_tool_executions(self, run_id):
        return self._tools


def _cats(store) -> set[str]:
    return {m["category"] for m in analyze_run_for_mistakes("run_x", store)}


def _event(event_type, data=None):
    return {"id": f"e_{event_type}", "type": event_type, "data": data or {}}


# ── the categories are declared ─────────────────────────────────────────────


def test_six_code_categories_are_declared_with_severity():
    for cat in (
        "check_claimed_not_run", "check_run_failed_ignored", "scope_violation",
        "unbounded_retry", "protected_path_write_attempt", "sandbox_unavailable",
    ):
        assert cat in CATEGORIES
        assert cat in _SEVERITY


# ── check_claimed_not_run ───────────────────────────────────────────────────


def test_check_claimed_not_run_when_no_records():
    run = {
        "status": "completed", "output": "All tests pass.",
        "codeVerification": {"records": [], "claims": [
            {"kind": "tests_pass", "supported": False, "matchedClasses": ["unit_test", "python_test"]},
        ]},
    }
    assert "check_claimed_not_run" in _cats(_RunStore(run))


def test_no_claim_when_records_prove_support():
    run = {
        "status": "completed", "output": "All tests pass.",
        "codeVerification": {"records": [
            {"commandClass": "unit_test", "exitCode": 0},
        ], "claims": [{"kind": "tests_pass", "supported": True, "matchedClasses": ["unit_test"]}]},
    }
    assert "check_claimed_not_run" not in _cats(_RunStore(run))


# ── check_run_failed_ignored ────────────────────────────────────────────────


def test_check_run_failed_ignored_when_a_failing_record_exists():
    run = {
        "status": "completed", "output": "All tests pass.",
        "codeVerification": {"records": [
            {"commandClass": "unit_test", "exitCode": 1},
        ], "claims": [{"kind": "tests_pass", "supported": False, "matchedClasses": ["unit_test", "python_test"]}]},
    }
    assert "check_run_failed_ignored" in _cats(_RunStore(run))


def test_no_failed_ignored_when_answer_admits_failure():
    # No claim at all (the model stated the failure, so it did not assert a pass).
    run = {
        "status": "completed", "output": "The tests failed.",
        "codeVerification": {"records": [
            {"commandClass": "unit_test", "exitCode": 1},
        ], "claims": []},
    }
    assert "check_run_failed_ignored" not in _cats(_RunStore(run))


# ── scope_violation ─────────────────────────────────────────────────────────


def test_scope_violation_from_denied_tool_execution():
    tools = [{"ok": False, "name": "command_run", "text": "denied",
              "error": {"code": "COMMAND_NOT_ALLOWLISTED"}, "toolCallId": "t1"}]
    run = {"status": "completed", "output": "done"}
    assert "scope_violation" in _cats(_RunStore(run, tools=tools))


def test_no_scope_violation_for_an_ordinary_failure():
    tools = [{"ok": False, "name": "market_get_quote", "text": "provider down",
              "error": {"code": "TOOL_ERROR"}, "toolCallId": "t1"}]
    run = {"status": "completed", "output": "done"}
    assert "scope_violation" not in _cats(_RunStore(run, tools=tools))


# ── unbounded_retry ─────────────────────────────────────────────────────────


def test_unbounded_retry_when_attempts_exceed_the_bound():
    events = [_event("code.repair.attempt", {"attempt": i}) for i in (1, 2, 3)]
    run = {"status": "completed", "output": "done",
           "codeVerification": {"records": [], "claims": [], "repair": {"maxAttempts": 2}}}
    assert "unbounded_retry" in _cats(_RunStore(run, events=events))


def test_no_unbounded_retry_at_or_below_the_bound():
    events = [_event("code.repair.attempt", {"attempt": i}) for i in (1, 2)]
    run = {"status": "completed", "output": "done",
           "codeVerification": {"records": [], "claims": [], "repair": {"maxAttempts": 2}}}
    assert "unbounded_retry" not in _cats(_RunStore(run, events=events))


# ── protected_path_write_attempt ────────────────────────────────────────────


def test_protected_path_write_attempt():
    events = [_event("code.policy.denied", {"code": "PROTECTED_PATH", "decision": "write"})]
    run = {"status": "completed", "output": "done"}
    assert "protected_path_write_attempt" in _cats(_RunStore(run, events=events))


def test_no_protected_attempt_for_a_read_denial():
    events = [_event("code.policy.denied", {"code": "PROTECTED_PATH", "decision": "read"})]
    run = {"status": "completed", "output": "done"}
    assert "protected_path_write_attempt" not in _cats(_RunStore(run, events=events))


# ── sandbox_unavailable ─────────────────────────────────────────────────────


def test_sandbox_unavailable_from_event():
    events = [_event("command.refused", {"code": "SANDBOX_UNAVAILABLE"})]
    run = {"status": "completed", "output": "done"}
    assert "sandbox_unavailable" in _cats(_RunStore(run, events=events))


def test_sandbox_unavailable_from_a_refused_repair():
    run = {"status": "completed", "output": "done",
           "codeVerification": {"records": [], "claims": [], "repair": {"status": "refused"}}}
    assert "sandbox_unavailable" in _cats(_RunStore(run))


def test_clean_run_has_no_code_mistakes():
    run = {"status": "completed", "output": "All good.",
           "codeVerification": {"records": [{"commandClass": "unit_test", "exitCode": 0}],
                                "claims": [{"kind": "tests_pass", "supported": True,
                                            "matchedClasses": ["unit_test"]}],
                                "repair": {"status": "passed", "maxAttempts": 2}}}
    code_cats = _cats(_RunStore(run)) & {
        "check_claimed_not_run", "check_run_failed_ignored", "scope_violation",
        "unbounded_retry", "protected_path_write_attempt", "sandbox_unavailable",
    }
    assert code_cats == set()
