"""The Fabric job state machine: every legal edge, every illegal one refused."""

from __future__ import annotations

import pytest

from harness.fabric.models import JobState
from harness.fabric.state import (
    InvalidJobTransition,
    JobStateMachine,
    can_transition,
    is_job_terminal,
    is_replayable,
    require_transition,
)


def test_happy_path_queued_running_succeeded():
    sm = JobStateMachine()
    assert sm.state == JobState.CREATED
    sm.to(JobState.QUEUED)
    sm.to(JobState.RUNNING)
    sm.to(JobState.SUCCEEDED)
    assert sm.terminal
    assert sm.history == [JobState.CREATED, JobState.QUEUED, JobState.RUNNING, JobState.SUCCEEDED]


def test_retry_cycle_running_retrying_queued():
    sm = JobStateMachine(JobState.RUNNING)
    sm.to(JobState.RETRYING)
    sm.to(JobState.QUEUED)
    sm.to(JobState.RUNNING)
    assert sm.state == JobState.RUNNING


@pytest.mark.parametrize("current,target", [
    (JobState.SUCCEEDED, JobState.RUNNING),
    (JobState.CANCELLED, JobState.QUEUED),
    (JobState.CREATED, JobState.SUCCEEDED),
    (JobState.QUEUED, JobState.SUCCEEDED),
    (JobState.DEAD_LETTER, JobState.RUNNING),
])
def test_illegal_transitions_are_refused(current, target):
    sm = JobStateMachine(current)
    with pytest.raises(InvalidJobTransition):
        sm.to(target)


def test_terminal_states_have_no_ordinary_outgoing_edges():
    for state in (JobState.SUCCEEDED, JobState.CANCELLED):
        assert not can_transition(state, JobState.RUNNING)
        assert not can_transition(state, JobState.QUEUED)
    # A failed/timed-out job has exactly the retry/dlq/replay edges.
    assert can_transition(JobState.FAILED, JobState.RETRYING)
    assert can_transition(JobState.FAILED, JobState.DEAD_LETTER)
    assert can_transition(JobState.DEAD_LETTER, JobState.QUEUED)


def test_terminal_and_replayable_helpers():
    assert is_job_terminal(JobState.SUCCEEDED)
    assert is_job_terminal(JobState.DEAD_LETTER)
    assert not is_job_terminal(JobState.RUNNING)
    assert is_replayable(JobState.FAILED)
    assert not is_replayable(JobState.SUCCEEDED)


def test_require_transition_raises_with_states():
    with pytest.raises(InvalidJobTransition) as info:
        require_transition(JobState.SUCCEEDED, JobState.RUNNING)
    assert info.value.current == JobState.SUCCEEDED
    assert info.value.target == JobState.RUNNING
