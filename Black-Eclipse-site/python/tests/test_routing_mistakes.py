"""Round 4 (W1.1) — deterministic routing mistakes from a persisted run.

The recorded "world clock" defect: a Compose verdict with no witness followed by
an engineering refusal. These tests prove the categories are recorded when the
signal exists and NOT recorded when it does not.
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


def _tool(name, text, *, call_id="t1", ok=True):
    return {"name": name, "text": text, "ok": ok, "toolCallId": call_id}


CLASSIFY_NO_WITNESS = "Mode: compose. compose signal(s): dashboard Components: none."
CLASSIFY_WITNESS = "Mode: compose. compose signal(s): dashboard Components: metric-card."
CLASSIFY_AMBIGUOUS = (
    "Mode: compose. no new-capability signal; defaulting to Compose "
    "(prefer the cheaper mode) Components: none."
)
START_REFUSED = (
    "Compose mode — This request can be Composed from registered components; "
    "no engineering task was created."
)


def test_routing_categories_are_declared_with_severity():
    for cat in (
        "misrouted_request", "capability_gap_refused", "composed_without_witness",
        "escalation_refused", "intent_ambiguity",
    ):
        assert cat in CATEGORIES
        assert cat in _SEVERITY


def test_clock_refusal_is_a_capability_gap_and_a_misroute():
    tools = [
        _tool("ui_classify_request", CLASSIFY_NO_WITNESS, call_id="c1"),
        _tool("ui_start_engineering", START_REFUSED, call_id="c2"),
    ]
    run = {"status": "completed", "output": "I cannot add a clock."}
    cats = _cats(_RunStore(run, tools=tools))
    assert {"composed_without_witness", "escalation_refused",
            "capability_gap_refused", "misrouted_request"} <= cats


def test_a_refusal_without_a_classification_is_still_a_misroute_but_not_a_gap():
    tools = [_tool("ui_start_engineering", START_REFUSED)]
    run = {"status": "completed", "output": "I cannot do that."}
    cats = _cats(_RunStore(run, tools=tools))
    assert "escalation_refused" in cats
    assert "misrouted_request" in cats
    assert "composed_without_witness" not in cats
    assert "capability_gap_refused" not in cats


def test_a_witnessed_compose_is_not_a_mistake():
    tools = [_tool("ui_classify_request", CLASSIFY_WITNESS)]
    run = {"status": "completed", "output": "Added the metric card."}
    cats = _cats(_RunStore(run, tools=tools))
    assert not (cats & {
        "composed_without_witness", "escalation_refused",
        "capability_gap_refused", "misrouted_request",
    })


def test_the_no_signal_default_is_ambiguity_only():
    tools = [_tool("ui_classify_request", CLASSIFY_AMBIGUOUS)]
    run = {"status": "completed", "output": "What would you like to change?"}
    cats = _cats(_RunStore(run, tools=tools))
    assert "intent_ambiguity" in cats
    assert "composed_without_witness" not in cats
    assert "misrouted_request" not in cats


def test_a_successful_escalation_records_no_refusal_mistake():
    tools = [
        _tool("ui_classify_request", "Mode: engineer. no registered component matches: clock", call_id="c1"),
        _tool("ui_start_engineering", "Capability gap — Created engineering task t1", call_id="c2"),
    ]
    run = {"status": "completed", "output": "I created an engineering task."}
    cats = _cats(_RunStore(run, tools=tools))
    assert not (cats & {
        "composed_without_witness", "escalation_refused",
        "capability_gap_refused", "misrouted_request",
    })
