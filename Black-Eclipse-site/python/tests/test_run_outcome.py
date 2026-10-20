"""Round 4 (W1.3): the outcome envelope — ONE record naming how a run was routed.

The intent verdict, the resolved surface + allowlist, the refusal code and the
capability gap are the four facts a diagnosable run needs. Three of them were
already persisted; the intent verdict had no home, so it is recorded here (the
module owns its own table, the `run_lineage.py` pattern).

These pin the record's honesty: a fact that was never recorded is `null`, never
guessed — and the first intent verdict wins, because it is the routing.
"""

from __future__ import annotations

import asyncio
import os
import sqlite3
import tempfile
import uuid

os.environ.setdefault(
    "AGENT_MEMORY_DB_PATH",
    os.path.join(tempfile.mkdtemp(prefix="be-outcome-api-"), "agent-memory.db"),
)
os.environ.setdefault(
    "HARNESS_ARTIFACT_ROOT",
    os.path.join(tempfile.mkdtemp(prefix="be-outcome-files-"), "artifacts"),
)

from fastapi.testclient import TestClient  # noqa: E402

from harness.main import app, service  # noqa: E402
from harness.run_outcome import (  # noqa: E402
    build_outcome_envelope,
    read_intent,
    record_intent,
    surface_summary,
)
from harness.schemas import ModelSettings  # noqa: E402
from harness.tools import ToolContext, ToolRegistry  # noqa: E402
from harness.ui.tools import _classify_request as ui_classify_request  # noqa: E402


class _Store:
    """The one shape the recorder needs: the shared sqlite connection."""

    def __init__(self) -> None:
        self._db = sqlite3.connect(":memory:")


def _events() -> list[dict]:
    return [
        {"type": "prompt.plan", "data": {"surface": {
            "agentId": "code-agent",
            "allowlist": {"unrestricted": False, "count": 2, "names": ["a", "b"],
                          "digest": "sha256:x"},
        }}},
        {"type": "ui.capability_gap", "data": {
            "code": "UI_CAPABILITY_GAP", "capability": "add a world clock",
            "mode": "engineer",
        }},
        {"type": "recovery.decided", "data": {"incidentId": "rec_1"}},
    ]


# ── The surface summary ───────────────────────────────────────────────────────


def test_an_unrestricted_allowlist_is_recorded_as_such():
    summary = surface_summary("finance-agent", None)
    assert summary["allowlist"]["unrestricted"] is True
    assert summary["allowlist"]["count"] is None
    assert summary["allowlist"]["names"] == []


def test_the_allowlist_summary_is_bounded_and_comparable():
    summary = surface_summary("code-agent", {"b_tool", "a_tool"})
    allowlist = summary["allowlist"]
    assert allowlist["count"] == 2
    assert allowlist["names"] == ["a_tool", "b_tool"]
    assert allowlist["digest"].startswith("sha256:")
    # The same set of names is the same surface, whatever the order.
    assert surface_summary("code-agent", {"a_tool", "b_tool"})["allowlist"]["digest"] == allowlist["digest"]


# ── The intent verdict ────────────────────────────────────────────────────────


def test_the_intent_verdict_is_recorded_and_read_back():
    store = _Store()
    record_intent(store, "run_a", {
        "verdict": "engineer", "reason": "no component matches",
        "witness": ["world-clock"], "capabilityGap": True,
    })
    intent = read_intent(store, "run_a")
    assert intent is not None
    assert intent["verdict"] == "engineer"
    assert intent["witness"] == ["world-clock"]
    assert intent["capabilityGap"] is True


def test_the_first_verdict_wins_because_it_is_the_routing():
    store = _Store()
    record_intent(store, "run_a", {"verdict": "engineer"})
    record_intent(store, "run_a", {"verdict": "compose"})
    assert read_intent(store, "run_a")["verdict"] == "engineer"


def test_no_record_means_no_intent():
    assert read_intent(_Store(), "run_a") is None
    assert read_intent(None, "run_a") is None
    record_intent(None, "run_a", {"verdict": "engineer"})  # never raises


def test_the_ui_classify_tool_records_the_verdict():
    store = _Store()

    class _Ui:
        def classify_request(self, text, *, blueprint_id=None, owner_id=None):
            return {
                "mode": "engineer", "reasons": ["no component matches"],
                "matchedComponents": [], "capabilityGap": True,
            }

    ctx = ToolContext(
        run_id="run_a", log=lambda *_: None, user_id="local",
        model_settings=ModelSettings(provider="ollama", model="llama3.1"),
        tool_registry=ToolRegistry(), memory_store=store, ui_service=_Ui(),
    )
    text, data = asyncio.run(ui_classify_request({"text": "add a world clock"}, ctx))
    assert data["mode"] == "engineer"
    intent = read_intent(store, "run_a")
    assert intent is not None
    assert intent["verdict"] == "engineer"
    assert intent["capabilityGap"] is True


# ── The envelope ──────────────────────────────────────────────────────────────


def test_the_envelope_names_the_four_facts():
    envelope = build_outcome_envelope(
        run_id="run_a",
        run={"agentId": "code-agent", "error": {"code": "TOOL_FORBIDDEN"}},
        events=_events(),
        tool_executions=[{"name": "read_file"}],
        intent={"verdict": "engineer", "reason": "gap", "witness": ["clock"],
                "capabilityGap": True},
    )
    assert envelope["intent"]["verdict"] == "engineer"
    assert envelope["surface"]["allowlist"]["count"] == 2
    assert envelope["surface"]["agentId"] == "code-agent"
    assert envelope["refusalCode"] == "TOOL_FORBIDDEN"
    assert envelope["capabilityGap"]["code"] == "UI_CAPABILITY_GAP"
    assert envelope["capabilityGap"]["incidentIds"] == ["rec_1"]


def test_a_run_with_no_recorded_facts_names_nothing():
    envelope = build_outcome_envelope(run_id="run_a")
    assert envelope["intent"] is None
    assert envelope["surface"]["allowlist"] is None
    assert envelope["refusalCode"] is None
    assert envelope["capabilityGap"] is None
    assert envelope["toolCalls"] == 0


def test_an_unknown_verdict_is_not_widened_into_a_known_one():
    envelope = build_outcome_envelope(
        run_id="run_a", intent={"verdict": "something-new", "reason": "r"},
    )
    assert envelope["intent"]["verdict"] == "unknown"


def test_a_refusal_event_names_its_code_when_the_run_itself_did_not_fail():
    events = [{"type": "analysis.refused", "data": {"status": "refused", "code": "ANALYSIS_NOT_ENABLED"}}]
    envelope = build_outcome_envelope(run_id="run_a", run={"agentId": "a"}, events=events)
    assert envelope["refusalCode"] == "ANALYSIS_NOT_ENABLED"


# ── The route ─────────────────────────────────────────────────────────────────

#: A plain client (NO lifespan): the suite must not boot the agent runtime —
#: a live runtime is a python descendant of the test process.
client = TestClient(app)


def test_the_outcome_route_names_the_run_record():
    run_id = "run_w13_" + uuid.uuid4().hex[:8]
    service.store.create_run(run_id, "finance-agent", {"query": "x"}, "local", "ollama", "llama3.1")
    response = client.get(f"/runs/{run_id}/outcome")
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["runId"] == run_id
    assert body["surface"]["agentId"] == "finance-agent"
    assert body["intent"] is None


def test_an_unknown_run_is_a_404():
    assert client.get("/runs/does-not-exist/outcome").status_code == 404
