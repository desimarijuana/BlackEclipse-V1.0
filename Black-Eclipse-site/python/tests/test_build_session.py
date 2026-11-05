"""Durable build sessions (Phase 22 / S2).

The budget ladder is data, the request budget is additive and clamped, and a
session is a lens over the ONE run lineage - never a second store.
"""

from __future__ import annotations

import pytest

from harness.code.session import (
    BUDGET_LADDER,
    DEFAULT_PROFILE,
    HARD_MAX_STEPS,
    HARD_RUN_TIMEOUT_S,
    SessionError,
    SessionStore,
    apply_budget,
    derive_phase,
    resolve_budget,
)
from harness.code.tasks import TaskStore
from harness.graph import requested_budget
from harness.persistence import AgentMemoryStore
from harness.run_lineage import RunLineage
from harness.schemas import RunRequest


class _Req:
    maxSteps = 0
    runTimeoutMs = 0


@pytest.fixture()
def store(tmp_path):
    value = AgentMemoryStore(str(tmp_path / "agent-memory.db"))
    yield value
    value.close()


def _run(store, run_id="run_s"):
    store.create_run(run_id, "code-agent", {"query": "add a settings toggle"})
    TaskStore(store).record_created(
        run_id, workspace_id="ws_a", root="/tmp/ws_a",
        base_revision="abc1234", strategy="worktree", autonomy="edit_verify",
    )


def test_the_ladder_is_ordered_and_data():
    assert BUDGET_LADDER["small"].max_steps < BUDGET_LADDER["standard"].max_steps
    assert BUDGET_LADDER["standard"].max_steps < BUDGET_LADDER["deep"].max_steps
    assert BUDGET_LADDER["deep"].max_steps == HARD_MAX_STEPS
    assert BUDGET_LADDER["deep"].run_timeout_s == HARD_RUN_TIMEOUT_S
    for budget in BUDGET_LADDER.values():
        assert budget.max_steps <= HARD_MAX_STEPS
        assert budget.run_timeout_s <= HARD_RUN_TIMEOUT_S


def test_resolve_is_case_insensitive_and_defaults_to_standard():
    assert resolve_budget(None).profile == DEFAULT_PROFILE
    assert resolve_budget("DEEP").profile == "deep"


def test_an_unknown_profile_is_refused():
    with pytest.raises(SessionError) as excinfo:
        resolve_budget("forever")
    assert excinfo.value.code == "UNKNOWN_BUDGET_PROFILE"


def test_apply_budget_sets_a_floor_and_never_lowers():
    request = _Req()
    apply_budget(request, resolve_budget("deep"))
    assert request.maxSteps == HARD_MAX_STEPS
    assert request.runTimeoutMs == int(HARD_RUN_TIMEOUT_S * 1000)

    higher = _Req()
    higher.maxSteps = 999
    higher.runTimeoutMs = 99_999_999
    apply_budget(higher, resolve_budget("small"))
    assert higher.maxSteps == 999
    assert higher.runTimeoutMs == 99_999_999


def test_the_graph_budget_is_clamped_to_the_hard_caps():
    assert requested_budget(24, 600.0, _Req()) == (24, 600.0)
    assert requested_budget(24, 600.0, type("R", (), {"maxSteps": 10_000, "runTimeoutMs": 99_999_999})()) == (
        HARD_MAX_STEPS, HARD_RUN_TIMEOUT_S,
    )
    # A direct caller cannot shrink an existing budget either.
    assert requested_budget(80, 2_700.0, type("R", (), {"maxSteps": 1, "runTimeoutMs": 1_000})()) == (
        80, 2_700.0,
    )


def test_a_session_records_goal_acceptance_and_budget(store):
    _run(store)
    sessions = SessionStore(store)
    sessions.record(
        "run_s", goal="add a settings toggle", budget=resolve_budget("standard"),
        acceptance=["the toggle appears in Settings", "the preference persists"],
        workspace_id="ws_a",
    )
    view = sessions.view("run_s")
    assert view["goal"] == "add a settings toggle"
    assert view["acceptance"] == [
        "the toggle appears in Settings", "the preference persists",
    ]
    assert view["budget"]["profile"] == "standard"
    assert view["budget"]["maxSteps"] == 80
    assert view["progress"]["boundaries"] == 0
    assert view["resume"]["resumable"] is True


def test_a_session_view_is_none_without_the_checkpoint(store):
    _run(store)
    assert SessionStore(store).view("run_s") is None


def test_a_completed_run_is_a_resume_conflict(store):
    _run(store)
    sessions = SessionStore(store)
    sessions.record("run_s", goal="done", budget=resolve_budget("small"))
    store.update_run("run_s", status="completed")
    view = sessions.view("run_s")
    assert view["resume"] == {"resumable": False, "code": "RESUME_CONFLICT",
                              "checkpointId": view["resume"]["checkpointId"]}
    assert view["resume"]["checkpointId"]


def test_the_request_model_accepts_the_additive_fields():
    request = RunRequest(
        runId="r", input={"query": "x"}, modelSettings={"provider": "p", "model": "m"},
        callbackBaseUrl="http://localhost:3000", maxSteps=80, runTimeoutMs=2_700_000,
    )
    assert request.maxSteps == 80
    assert request.runTimeoutMs == 2_700_000


def test_derive_phase_is_deterministic_and_names_the_next_action():
    assert derive_phase("created", 0, None) == ("planning", "run_checks")
    assert derive_phase("plan_review", 0, None) == ("planning", "review_plan")
    assert derive_phase("running", 1, None) == ("editing", "run_checks")
    assert derive_phase("running", 2, {"ok": False, "full": True}) == ("checking", "fix_checks")
    assert derive_phase("completed", 3, None) == ("checking", "run_checks")
    assert derive_phase("completed", 3, {"ok": True, "full": True}) == ("done", "review_change")
    assert derive_phase("failed", 1, None) == ("blocked", "fix_checks")
    assert derive_phase("cancelled", 0, None) == ("cancelled", "none")


def test_a_land_record_reaches_the_session_view(store):
    _run(store)
    sessions = SessionStore(store)
    sessions.record("run_s", goal="ship it", budget=resolve_budget("standard"))
    RunLineage(store).save_checkpoint("run_s", "land.verified", {
        "previewDigest": "d", "ok": True, "full": True, "failed": None,
        "checks": [],
    })
    store.update_run("run_s", status="completed")
    view = sessions.view("run_s")
    assert view["land"] == {
        "ok": True, "full": True, "failed": None, "at": view["land"]["at"],
    }
    assert view["phase"] == "done"
    assert view["nextAction"] == "review_change"
