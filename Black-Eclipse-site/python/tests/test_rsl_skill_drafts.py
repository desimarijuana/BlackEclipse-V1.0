"""v1b: inert skill drafts are measurable in a candidate trial, never live."""

from __future__ import annotations

import pytest

from harness.evaluation.candidate_invoker import (
    CandidateAgentInvoker,
    SnapshotError,
    validate_snapshot,
)
from harness.self_improvement.models import HarnessSnapshot


class _DraftStore:
    def __init__(self, *, status="draft", required=("tool_a",), instructions="use tool_a"):
        self.status = status
        self.required = list(required)
        self.instructions = instructions

    def get_skill(self, skill_id: str):
        if skill_id != "learned.example":
            return None
        return {
            "id": skill_id, "name": "Example", "description": "Example draft",
            "status": self.status, "latestVersion": "0.1.0",
        }

    def get_version(self, skill_id: str, version: str):
        del version
        if skill_id != "learned.example":
            return None
        return {
            "manifest": {
                "id": skill_id, "name": "Example", "description": "Example draft",
                "requiredTools": self.required,
            },
            "instructions": self.instructions,
        }


def _base() -> HarnessSnapshot:
    return HarnessSnapshot(systemPrompt="base", toolNames=("tool_a", "tool_b"))


def _candidate(**overrides) -> HarnessSnapshot:
    payload = {
        "systemPrompt": "candidate", "toolNames": ("tool_a",), "skillDraftIds": ("learned.example",),
    }
    payload.update(overrides)
    return HarnessSnapshot(**payload)


def test_known_draft_is_accepted_and_injected_into_the_trial_prompt():
    invoker = CandidateAgentInvoker(
        None, _candidate(), base=_base(), skill_store=_DraftStore(),
    )
    assert "use tool_a" in invoker._draft_prompt
    assert "Inert draft skills" in invoker._draft_prompt


def test_a_draft_without_a_store_is_refused():
    with pytest.raises(SnapshotError) as exc:
        CandidateAgentInvoker(None, _candidate(), base=_base())
    assert exc.value.code == "SNAPSHOT_UNKNOWN_SKILL"


def test_a_non_draft_skill_is_refused():
    with pytest.raises(SnapshotError) as exc:
        CandidateAgentInvoker(
            None, _candidate(), base=_base(),
            skill_store=_DraftStore(status="active"),
        )
    assert exc.value.code == "SNAPSHOT_UNKNOWN_SKILL"


def test_a_draft_requiring_a_tool_outside_the_candidate_is_refused():
    with pytest.raises(SnapshotError) as exc:
        CandidateAgentInvoker(
            None, _candidate(), base=_base(),
            skill_store=_DraftStore(required=("tool_b",)),
        )
    assert "outside the candidate allowlist" in exc.value.detail


def test_validate_snapshot_still_refuses_unauthorized_drafts_without_a_store():
    with pytest.raises(SnapshotError):
        validate_snapshot(_base(), _candidate())
