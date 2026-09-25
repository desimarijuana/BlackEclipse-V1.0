"""Conflict detection safety (Phase 4) — deterministic, explainable, conservative.

Correctness:
  * known opposing pairs ARE detected (concise/detailed, include/do not include);
  * candlestick vs line chart style is NOT a known contradiction (not replaced);
  * unrelated preferences sharing generic words are NOT conflicts;
  * scope separation (market/project/user) is never a conflict;
  * a factual observation on the same topic does not conflict with a preference;
  * a temporary instruction does not conflict with a durable preference;
  * replacement wording is required for a same-polarity value change.
"""

from __future__ import annotations

import os
import tempfile

import pytest

from harness.eclipse_memory import EclipseMemoryService, EclipseMemoryStore
from harness.eclipse_memory.conflicts import (
    DECISION_CONFIRM,
    DECISION_NONE,
    DECISION_PROPOSE,
    DECISION_SUPERSEDE,
    detect_conflict,
    opposing,
)


@pytest.fixture()
def service():
    directory = tempfile.mkdtemp(prefix="be-confneg-")
    svc = EclipseMemoryService(EclipseMemoryStore(os.path.join(directory, "eclipse-memory.db")))
    yield svc
    svc.close()


def _write(service, content, **kw):
    kw.setdefault("memory_type", "preference")
    kw.setdefault("source", "explicit_user")
    kw.setdefault("scope", "user")
    kw.setdefault("scope_id", "u1")
    return service.write_memory(content=content, **kw)


# ── Detection unit cases ────────────────────────────────────────────────────


def test_known_opposing_pairs():
    assert opposing("show concise answers", "give detailed answers")
    assert opposing("always include sources", "do not include sources")
    assert opposing("always include sources", "never include sources")
    assert opposing("conservative suggestions", "aggressive suggestions")


def test_candlestick_vs_line_is_not_a_known_contradiction():
    # A missed conflict is preferable to replacing a distinct preference.
    assert not opposing("I prefer candlestick charts", "I prefer line charts")


def test_generic_overlap_alone_does_not_link_memories():
    # Two unrelated preferences sharing generic vocabulary must not be related.
    assessment = detect_conflict(
        memory_type="preference", scope="user", scope_id="u1",
        subject="answer-style", content="I prefer concise answers",
        existing=[{
            "id": "m2", "memoryType": "preference", "scope": "user", "scopeId": "u1",
            "subject": "risk-profile", "content": "I prefer to always use conservative options",
            "status": "active", "authority": "explicit",
        }],
    )
    assert assessment.decision == DECISION_NONE


def test_same_dimension_restatement_is_a_confirmation():
    assessment = detect_conflict(
        memory_type="preference", scope="user", scope_id="u1",
        subject="answer-style", content="I prefer concise answers",
        existing=[{
            "id": "m2", "memoryType": "preference", "scope": "user", "scopeId": "u1",
            "subject": "answer-style", "content": "I prefer concise answers",
            "status": "active", "authority": "explicit",
        }],
    )
    assert assessment.decision == DECISION_CONFIRM


# ── Scope / dimension separation ────────────────────────────────────────────


def test_different_scope_is_never_a_conflict():
    assessment = detect_conflict(
        memory_type="preference", scope="user", scope_id="u2",
        subject="answer-style", content="I prefer detailed answers now",
        existing=[{
            "id": "m1", "memoryType": "preference", "scope": "user", "scopeId": "u1",
            "subject": "answer-style", "content": "I prefer concise answers",
            "status": "active", "authority": "explicit",
        }],
    )
    assert assessment.decision == DECISION_NONE


def test_market_project_user_scope_separation(service):
    user = service.write_memory(
        memory_type="constraint", content="Always report figures in the local currency",
        source="explicit_user", scope="user", scope_id="u1", subject="currency",
    )
    market = service.write_memory(
        memory_type="constraint", content="Always report figures in the local currency",
        source="manual", scope="market", subject="currency",
    )
    # A market-scoped convention and a user-scoped one do not conflict.
    assert user["status"] == "active"
    assert market["status"] == "active"


def test_factual_observation_and_preference_do_not_conflict(service):
    observation = service.write_memory(
        memory_type="observation", content="The user prefers concise answers here.",
        source="execution_lesson", scope="user", scope_id="u1", subject="answer-style",
    )
    preference = service.write_memory(
        memory_type="preference", content="I prefer detailed answers",
        source="explicit_user", scope="user", scope_id="u1", subject="answer-style",
    )
    assert observation["status"] == "active"
    assert preference["status"] == "active"


def test_temporary_instruction_is_history_only_not_a_conflict(service):
    durable = _write(service, "I prefer concise answers", subject="answer-style")
    # "for this task, use detailed answers" is a one-off, not a durable change.
    decision = service.decide_turn("For this task, use detailed answers", user_id="u1")
    assert decision.outcome in ("history_only", "ignore")
    assert service.store.get_memory(durable["id"])["status"] == "active"


# ── Service-level negative behaviour ────────────────────────────────────────


def test_candlestick_then_line_does_not_replace(service):
    charts = _write(service, "I prefer candlestick charts", subject="charts")
    line = _write(service, "I prefer line charts", subject="charts")
    # Not a known opposing pair and no replacement wording → not superseded.
    assert service.store.get_memory(charts["id"])["status"] == "active"


def test_unrelated_preferences_both_stay_active(service):
    a = _write(service, "I prefer dark mode", subject="theme")
    b = _write(service, "I prefer concise answers", subject="answer-style")
    assert a["status"] == "active"
    assert b["status"] == "active"
