"""Browser observability unit tests (Phase 8).

Content-free telemetry aggregates, the cost model, the bounded structured log
ring, trace replay/inspection and the operator routes. No browser is launched:
the routes are exercised against a stub manager, and replay runs over a synthetic
stored trace.
"""

from __future__ import annotations

import pytest

from harness.browser.replay import (
    build_timeline,
    failure_analysis,
    plain_reason,
    render_text,
    replay_trace,
)
from harness.browser.telemetry import (
    BrowserTelemetry,
    CostRates,
    classify_error,
    get_telemetry,
    set_telemetry,
)


# ── Error classification ─────────────────────────────────────────────────────

@pytest.mark.parametrize("code,category", [
    ("BROWSER_TIMEOUT", "timeout"),
    ("BROWSER_ELEMENT_NOT_FOUND", "element"),
    ("BROWSER_STALE_ELEMENT", "element"),
    ("BROWSER_NAVIGATION_FAILED", "navigation"),
    ("BROWSER_PROVIDER_UNAVAILABLE", "provider"),
    ("BROWSER_PROVIDER_ERROR", "provider"),
    ("BROWSER_LAUNCH_FAILED", "crash"),
    ("BROWSER_AUTHENTICATION_FAILED", "auth"),
    ("BROWSER_DOWNLOAD_FAILED", "download"),
    ("BROWSER_CAPABILITY_UNSUPPORTED", "capability"),
    (None, "unknown"),
    ("SOMETHING_ELSE", "error"),
])
def test_error_classification(code, category):
    assert classify_error(code) == category


# ── Counters / aggregate ─────────────────────────────────────────────────────

def test_telemetry_counts_sessions_actions_and_failures():
    t = BrowserTelemetry()
    t.session_opened("local_chromium", session_id="s1")
    t.record_action("navigate", provider="local_chromium", duration_ms=120, ok=True)
    t.record_action("click", provider="local_chromium", duration_ms=80, ok=False, error_code="BROWSER_TIMEOUT")
    t.session_closed("local_chromium", browser_ms=5_000)
    snap = t.snapshot()
    assert snap["sessions"]["created"] == 1
    assert snap["sessions"]["closed"] == 1
    assert snap["sessions"]["active"] == 0
    assert snap["actions"]["calls"] == 2
    assert snap["actions"]["failures"] == 1
    assert snap["actions"]["timeouts"] == 1
    assert snap["actions"]["navigations"] == 1  # successful navigate bumps the domain counter
    assert snap["actions"]["errorCategories"]["timeout"] == 1
    assert snap["byAction"]["click"]["failures"] == 1
    assert snap["providers"]["local_chromium"]["actions"] == 2
    assert snap["providers"]["local_chromium"]["avgLatencyMs"] == 100


def test_telemetry_active_gauge_never_goes_negative():
    t = BrowserTelemetry()
    t.session_failed("local_chromium", code="BROWSER_LAUNCH_FAILED")
    t.session_closed("local_chromium")
    assert t.snapshot()["sessions"]["active"] == 0


def test_telemetry_is_bounded_by_vocabulary():
    t = BrowserTelemetry()
    for _ in range(1_000):
        t.record_action("click", provider="local_chromium", duration_ms=5, ok=True)
    t.record_action("click", provider="local_chromium", duration_ms=9_999, ok=False, error_code="BROWSER_TIMEOUT")
    row = t.snapshot()["byAction"]["click"]
    # Latency keeps only sum/count/max — never a per-call list.
    assert row["count"] == 1_001
    assert row["latencyMaxMs"] == 9_999
    assert set(row) == {"count", "failures", "latencySumMs", "latencyMaxMs", "avgLatencyMs"}


def test_vision_and_media_counters():
    t = BrowserTelemetry()
    t.record_vision(tokens=500, available=True)
    t.record_vision(available=False)
    t.record_screenshot(2)
    t.record_download()
    t.note_download_size(4_096)
    t.record_upload()
    t.note_upload_count(3)
    snap = t.snapshot()
    assert snap["actions"]["visionCalls"] == 2
    assert snap["actions"]["visionUnavailable"] == 1
    assert snap["actions"]["screenshots"] == 2
    assert snap["actions"]["downloads"] == 1
    assert snap["actions"]["uploads"] == 1
    cost = snap["cost"]["measurements"]
    assert cost["visionTokens"] == 500
    assert cost["downloadBytes"] == 4_096


# ── Cost: never a fabricated price ───────────────────────────────────────────

def test_cost_without_rates_reports_measurements_only():
    t = BrowserTelemetry()
    t.session_opened("browserbase")
    t.session_closed("browserbase", browser_ms=12_000, locality="cloud")
    cost = t.cost()
    assert cost["ratesConfigured"] is False
    assert cost["estimatedMicros"] is None
    assert cost["measurements"]["cloudBrowserSeconds"] == 12.0


def test_cost_with_rates_produces_labelled_estimate():
    t = BrowserTelemetry(rates=CostRates(cloudBrowserSecondMicros=1_000))
    t.session_opened("browserbase")
    t.session_closed("browserbase", browser_ms=12_000, locality="cloud")
    cost = t.cost()
    assert cost["ratesConfigured"] is True
    assert cost["estimatedMicros"] == 12_000
    assert cost["estimatedUsd"] == 0.012


def test_per_provider_browser_seconds():
    t = BrowserTelemetry()
    t.session_opened("local_chromium")
    t.session_closed("local_chromium", browser_ms=3_000)
    assert t.cost()["perProvider"]["local_chromium"]["browserSeconds"] == 3.0


# ── Structured logs: bounded, queryable, content-free ────────────────────────

def test_logs_are_queryable_by_code_and_bounded():
    t = BrowserTelemetry(log_cap=5)
    for i in range(10):
        t.log("info", f"CODE_{i}", f"line {i}")
    assert t.snapshot()["logs"]["count"] == 5  # ring is bounded
    recent = t.logs(limit=100)
    assert len(recent) == 5
    assert recent[0]["code"] == "CODE_9"  # newest first
    only = t.logs(code="CODE_7")
    assert only and all("CODE_7" in e["code"] for e in only)


def test_logs_filter_by_level_and_category():
    t = BrowserTelemetry()
    t.log("error", "BROWSER_TIMEOUT", "timed out")
    t.log("info", "BROWSER_NAVIGATED", "opened")
    assert [e["code"] for e in t.logs(level="error")] == ["BROWSER_TIMEOUT"]
    assert [e["code"] for e in t.logs(category="timeout")] == ["BROWSER_TIMEOUT"]


def test_log_message_is_truncated_and_carries_no_session_secret():
    t = BrowserTelemetry()
    t.log("info", "BROWSER_SESSION_OPENED", "x" * 5_000, session_id="s1")
    entry = t.logs()[0]
    assert len(entry["message"]) <= 300
    assert entry["sessionId"] == "s1"


def test_global_telemetry_is_a_singleton():
    a = get_telemetry()
    b = get_telemetry()
    assert a is b


# ── Replay / inspection ──────────────────────────────────────────────────────

def _synthetic_trace() -> dict:
    return {
        "id": "btrace_demo", "sessionId": "bsess_demo", "runId": "run-1",
        "taskId": None, "provider": "local_chromium", "status": "completed",
        "createdAt": "2026-10-07T00:00:00+00:00", "finishedAt": "2026-10-07T00:00:05+00:00",
        "summary": {"stepCount": 4},
        "steps": [
            {"index": 0, "action": "navigate", "provider": "local_chromium", "durationMs": 400,
             "params": {"url": "https://sec.gov"}, "observation": {"url": "https://sec.gov", "title": "SEC"},
             "verification": {"success": True, "state_changed": True, "summary": "Page changed."},
             "error": None, "humanIntervention": None},
            {"index": 1, "action": "click", "provider": "local_chromium", "durationMs": 120,
             "params": {"target": "@e3"}, "observation": {"summary": "filing list"},
             "verification": {"success": True, "state_changed": True, "summary": "Opened filing."},
             "error": None, "humanIntervention": None},
            {"index": 2, "action": "download", "provider": "local_chromium", "durationMs": 30,
             "params": {"target": "@e5"}, "observation": {},
             "verification": {}, "error": {"code": "BROWSER_DOWNLOAD_FAILED", "message": "save failed"},
             "humanIntervention": None},
            {"index": 3, "action": "extract", "provider": "local_chromium", "durationMs": 40,
             "params": {}, "observation": {"elementCount": 12},
             "verification": {"success": True, "state_changed": False}, "error": None,
             "humanIntervention": None},
        ],
    }


def test_replay_renders_a_browser_free_timeline():
    view = replay_trace(_synthetic_trace())
    assert view["traceId"] == "btrace_demo"
    assert view["shownSteps"] == 4
    assert view["changedStepIndices"] == [0, 1]
    assert view["failureAnalysis"]["stepIndex"] == 2
    assert view["failureAnalysis"]["code"] == "BROWSER_DOWNLOAD_FAILED"
    assert view["failureAnalysis"]["category"] == "download"
    text = render_text(view)
    assert "btrace_demo" in text
    assert "download" in text
    assert "first failed at step 2" in text


def test_replay_of_a_clean_trace_has_no_failure():
    trace = _synthetic_trace()
    trace["steps"] = [s for s in trace["steps"] if s.get("error") is None]
    view = replay_trace(trace)
    assert view["failureAnalysis"] is None
    assert "No failures" in render_text(view)


def test_replay_handles_sparse_trace():
    view = replay_trace({"id": "btrace_empty", "steps": []})
    assert view["shownSteps"] == 0
    assert view["failureAnalysis"] is None
    assert build_timeline({}) == []


def test_replay_is_bounded():
    steps = [
        {"index": i, "action": "click", "durationMs": 1, "params": {},
         "observation": {}, "verification": {}, "error": None}
        for i in range(1_000)
    ]
    view = replay_trace({"id": "btrace_long", "steps": steps})
    assert view["bounded"] is True
    assert view["shownSteps"] <= 500


def test_plain_reason_is_always_a_sentence():
    assert "time" in plain_reason("BROWSER_TIMEOUT")
    assert plain_reason("BROWSER_WEIRD_NEW_CODE")  # falls back, never empty


def test_failure_analysis_picks_the_first_failure():
    timeline = build_timeline(_synthetic_trace())
    failure = failure_analysis(timeline)
    assert failure["stepIndex"] == 2


# ── Tool registration ────────────────────────────────────────────────────────

def test_browser_replay_tool_is_registered(monkeypatch):
    from harness.browser import tools as browser_tools
    from harness.tools import ToolRegistry

    monkeypatch.setenv("HARNESS_BROWSER_ENABLED", "true")
    registry = ToolRegistry()
    added = browser_tools.register_browser_tools(registry)
    assert "browser_replay" in added
