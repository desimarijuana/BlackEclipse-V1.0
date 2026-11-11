"""Round 5 / C2: one execution vocabulary across the planes."""

from __future__ import annotations

from harness.execution_plane import (
    ExecutionPhase,
    JobKind,
    is_live_phase,
    is_terminal_phase,
    phase_of_graph_status,
    phase_of_job_state,
    phase_of_run_status,
    phase_of_task_status,
)


def test_run_status_maps_to_the_canonical_phase():
    assert phase_of_run_status("created") is ExecutionPhase.PENDING
    assert phase_of_run_status("running") is ExecutionPhase.RUNNING
    assert phase_of_run_status("completed") is ExecutionPhase.SUCCEEDED
    assert phase_of_run_status("failed") is ExecutionPhase.FAILED
    assert phase_of_run_status("cancelled") is ExecutionPhase.CANCELLED


def test_job_state_maps_without_losing_waiting_or_retrying():
    assert phase_of_job_state("QUEUED") is ExecutionPhase.QUEUED
    assert phase_of_job_state("PAUSED") is ExecutionPhase.WAITING
    assert phase_of_job_state("RETRYING") is ExecutionPhase.QUEUED
    assert phase_of_job_state("TIMED_OUT") is ExecutionPhase.TIMED_OUT
    assert phase_of_job_state("DEAD_LETTER") is ExecutionPhase.FAILED


def test_task_and_graph_status_share_the_same_phases():
    assert phase_of_task_status("TODO") is ExecutionPhase.PENDING
    assert phase_of_task_status("VERIFYING") is ExecutionPhase.RUNNING
    assert phase_of_task_status("ASKING_USER") is ExecutionPhase.WAITING
    assert phase_of_task_status("COMPLETED") is ExecutionPhase.SUCCEEDED
    assert phase_of_graph_status("queued") is ExecutionPhase.QUEUED
    assert phase_of_graph_status("succeeded") is ExecutionPhase.SUCCEEDED


def test_unknown_values_are_none_never_invented():
    assert phase_of_run_status("weird") is None
    assert phase_of_job_state(None) is None
    assert phase_of_task_status(42) is None
    assert phase_of_graph_status("") is None


def test_terminal_and_live_are_disjoint():
    for phase in ExecutionPhase:
        assert not (is_terminal_phase(phase) and is_live_phase(phase)), phase
    assert is_terminal_phase(ExecutionPhase.SUCCEEDED) is True
    assert is_terminal_phase(ExecutionPhase.RUNNING) is False
    assert is_live_phase(ExecutionPhase.WAITING) is True
    assert is_live_phase(ExecutionPhase.FAILED) is False
    assert is_terminal_phase(None) is False
    assert is_live_phase(None) is False


def test_job_kinds_cover_every_plane_that_runs_work():
    assert {kind.value for kind in JobKind} == {
        "agent_run", "graph_run", "task_run", "delegate", "tool", "research", "automation",
    }
