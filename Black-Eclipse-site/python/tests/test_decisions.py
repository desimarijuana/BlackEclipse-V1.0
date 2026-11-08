"""Typed decisions — contracts, rules, confidence policy, audit, privacy.

Pure and synthetic; no network and no provider key. The point of this suite is
that the layer is USABLE and HONEST with zero external configuration: it answers
only what a declared rule can prove, records everything, and reports
`unavailable` instead of guessing.
"""

from __future__ import annotations

import asyncio
import os
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from harness.decisions.contracts import (
    ChoiceAnswer,
    ChoiceQuestion,
    DecisionRequest,
    DecisionResponse,
    NoulAnswer,
    NoulQuestion,
    questions_hash,
)
from harness.decisions.policy import ACT, REVIEW, DecisionPolicy, status_for
from harness.decisions.providers.base import DecisionProvider, DecisionUnavailable
from harness.decisions.providers.rules import RuleProvider
from harness.decisions.registry import DecisionRegistry
from harness.decisions.service import DecisionService
from harness.decisions.store import DecisionStore
from harness.decisions.tools import decision_ask, decision_scorecard, register_decision_tools
from harness.persistence import AgentMemoryStore
from harness.tools import ToolRegistry


def _request(questions=None, state=None) -> DecisionRequest:
    return DecisionRequest.model_validate(
        {
            "state": state if state is not None else {"margin_ratio": 0.42, "grade": "b"},
            "questions": questions
            or {
                "is_risky": {
                    "type": "noul",
                    "instructions": "Is the margin ratio above 0.25?",
                    "rule": {"fact": "margin_ratio", "op": "gte", "value": 0.25},
                }
            },
        }
    )


class _FakeProvider(DecisionProvider):
    """A provider that returns a fixed, valid answer set (never hits a network)."""

    name = "fake"
    local = False
    models = ("fake-1",)

    def __init__(self, answers, *, fail: Exception | None = None) -> None:
        self.answers = answers
        self.fail = fail
        self.calls = 0

    async def ask(self, request: DecisionRequest) -> DecisionResponse:
        self.calls += 1
        if self.fail is not None:
            raise self.fail
        return DecisionResponse(
            answers=self.answers, provider=self.name, model="fake-1"
        )


def _store(tmp_path) -> AgentMemoryStore:
    return AgentMemoryStore(os.path.join(str(tmp_path), "decisions-test.db"))


# ── Contracts ────────────────────────────────────────────────────────────────


def test_question_hash_is_stable_and_sensitive_to_wording():
    first = _request().questions
    assert questions_hash(first) == questions_hash(dict(first))
    changed = _request(
        {
            "is_risky": {
                "type": "noul",
                "instructions": "Is the margin ratio dangerously high?",
                "rule": {"fact": "margin_ratio", "op": "gte", "value": 0.25},
            }
        }
    ).questions
    assert questions_hash(first) != questions_hash(changed)


def test_question_ids_must_be_stable_identifiers():
    with pytest.raises(ValidationError):
        _request({"Not Stable": {"type": "noul", "instructions": "x?"}})


def test_a_choice_needs_at_least_two_described_options():
    with pytest.raises(ValidationError):
        ChoiceQuestion.model_validate(
            {"instructions": "pick", "criteria": {"only": "one option"}}
        )


def test_an_empty_state_is_rejected():
    with pytest.raises(ValidationError):
        DecisionRequest.model_validate(
            {"state": "   ", "questions": {"q": {"type": "noul", "instructions": "x?"}}}
        )


# ── Rule provider (the offline path) ────────────────────────────────────────


def test_rules_answer_a_noul_from_a_declared_fact():
    response = asyncio.run(RuleProvider().ask(_request()))
    assert response.answers["is_risky"].noul == 1.0
    assert response.provider == "rules"


def test_rules_refuse_a_missing_fact_instead_of_guessing():
    request = _request(state={"other": 1})
    with pytest.raises(DecisionUnavailable):
        asyncio.run(RuleProvider().ask(request))


def test_rules_answer_an_equality_choice():
    request = _request(
        {
            "bucket": {
                "type": "choice",
                "instructions": "Which bucket?",
                "criteria": {"a": "low", "b": "medium", "c": "high"},
                "rule": {"fact": "grade", "op": "eq", "value": "b"},
            }
        }
    )
    answer = asyncio.run(RuleProvider().ask(request)).answers["bucket"]
    assert isinstance(answer, ChoiceAnswer)
    assert answer.choice == "b"
    assert answer.probabilities["b"] == 1.0


def test_rules_refuse_a_question_without_a_rule():
    request = _request({"q": {"type": "noul", "instructions": "Is it?"}})
    with pytest.raises(DecisionUnavailable):
        asyncio.run(RuleProvider().ask(request))


# ── Confidence policy ────────────────────────────────────────────────────────


def test_choice_below_the_probability_threshold_goes_to_review():
    question = ChoiceQuestion.model_validate(
        {"instructions": "pick", "criteria": {"a": "one", "b": "two"}}
    )
    answer = ChoiceAnswer(choice="a", probabilities={"a": 0.51, "b": 0.49}, confidence=0.9)
    verdict = DecisionPolicy(min_probability=0.6).assess(question, answer)
    assert verdict["verdict"] == REVIEW


def test_a_noul_inside_the_abstain_band_goes_to_review():
    question = NoulQuestion.model_validate({"instructions": "Is it?"})
    verdict = DecisionPolicy(min_probability=0.6).assess(question, NoulAnswer(noul=0.5))
    assert verdict["verdict"] == REVIEW
    verdict = DecisionPolicy(min_probability=0.6).assess(question, NoulAnswer(noul=0.95))
    assert verdict["verdict"] == ACT


def test_require_confidence_reviews_a_bare_answer_but_defaults_to_accepting_it():
    question = NoulQuestion.model_validate({"instructions": "Is it?"})
    answer = NoulAnswer(noul=1.0)
    assert DecisionPolicy().assess(question, answer)["verdict"] == ACT
    assert DecisionPolicy(require_confidence=True).assess(question, answer)["verdict"] == REVIEW


def test_status_is_answered_only_when_every_question_clears():
    questions = _request().questions
    assert status_for({"is_risky": {"verdict": ACT}}, questions) == "answered"
    assert status_for({"is_risky": {"verdict": REVIEW}}, questions) == "review"
    assert status_for({}, questions) == "unavailable"


# ── Service + audit ─────────────────────────────────────────────────────────


def _service(tmp_path, providers) -> DecisionService:
    return DecisionService(_store(tmp_path), registry=DecisionRegistry(providers))


def test_a_high_confidence_answer_is_answered_and_recorded(tmp_path):
    fake = _FakeProvider({"is_risky": NoulAnswer(noul=0.97)})
    service = _service(tmp_path, [fake])

    result = asyncio.run(service.ask(_request(), run_id="run_1", owner_id="u1", tool="decision_ask"))

    assert result.status == "answered"
    assert result.record_id
    record = service.store.get_record(result.record_id)
    assert record["status"] == "answered"
    assert record["provider"] == "fake"
    assert record["answers"]["is_risky"]["noul"] == 0.97
    assert record["runId"] == "run_1"


def test_the_same_request_in_the_same_run_is_recorded_once(tmp_path):
    fake = _FakeProvider({"is_risky": NoulAnswer(noul=0.97)})
    service = _service(tmp_path, [fake])

    first = asyncio.run(service.ask(_request(), run_id="run_1"))
    second = asyncio.run(service.ask(_request(), run_id="run_1"))

    assert first.record_id == second.record_id
    assert len(service.list_records()) == 1


def test_a_low_confidence_answer_is_review_not_a_decision(tmp_path):
    fake = _FakeProvider({"is_risky": NoulAnswer(noul=0.55)})
    service = _service(tmp_path, [fake])

    result = asyncio.run(service.ask(_request()))

    assert result.status == "review"
    assert result.record_id


def test_a_partial_answer_set_is_unavailable_not_a_partial_result(tmp_path):
    fake = _FakeProvider({})
    service = _service(tmp_path, [fake])

    result = asyncio.run(service.ask(_request()))

    assert result.status == "unavailable"
    assert "no answer for" in (result.reason or "")
    stored = service.list_records()
    assert stored[0]["status"] == "unavailable"


def test_a_provider_failure_is_recorded_as_unavailable(tmp_path):
    fake = _FakeProvider({}, fail=DecisionUnavailable("no API key"))
    service = _service(tmp_path, [fake])

    result = asyncio.run(service.ask(_request()))

    assert result.status == "unavailable"
    assert result.reason == "no API key"
    assert result.answers == {}


def test_no_provider_is_an_honest_unavailable(tmp_path):
    service = DecisionService(_store(tmp_path), registry=DecisionRegistry([]))

    result = asyncio.run(service.ask(_request()))

    assert result.status == "unavailable"
    assert "no decision provider" in (result.reason or "")


def test_local_only_privacy_mode_refuses_a_remote_provider(monkeypatch):
    monkeypatch.setenv("ECLIPSE_PRIVACY", "local-models")
    remote = _FakeProvider({"is_risky": NoulAnswer(noul=1.0)})
    registry = DecisionRegistry([remote])

    provider, reason = registry.resolve()

    assert provider is None
    assert "local-only" in (reason or "")


def test_local_only_privacy_mode_still_allows_the_rule_provider(monkeypatch):
    monkeypatch.setenv("ECLIPSE_PRIVACY", "local-models")
    registry = DecisionRegistry([_FakeProvider({}), RuleProvider()])

    provider, reason = registry.resolve()

    assert reason is None
    assert provider is not None and provider.name == "rules"


def test_an_explicit_preference_is_never_silently_substituted(monkeypatch):
    monkeypatch.setenv("ECLIPSE_PRIVACY", "local-models")
    registry = DecisionRegistry([_FakeProvider({}), RuleProvider()])

    provider, reason = registry.resolve("fake")

    assert provider is None
    assert "remote" in (reason or "")


# ── Outcome / scorecard ─────────────────────────────────────────────────────


def test_outcomes_are_appended_and_counted(tmp_path):
    store = DecisionStore(_store(tmp_path))
    store.write_record(
        {
            "id": "dec_1",
            "provider": "fake",
            "questionHash": "qh",
            "status": "answered",
            "answers": {},
        }
    )
    store.record_outcome(record_id="dec_1", verdict="correct", question_id="is_risky")

    card = store.scorecard()

    assert card["total"] == 1
    assert card["evaluated"] == 1
    assert card["byOutcome"] == {"correct": 1}
    assert card["accuracy"] == 1.0


def test_an_unknown_outcome_verdict_is_rejected(tmp_path):
    store = DecisionStore(_store(tmp_path))
    store.write_record({"id": "dec_1", "provider": "fake", "questionHash": "qh", "status": "answered"})
    with pytest.raises(ValueError):
        store.record_outcome(record_id="dec_1", verdict="maybe")


# ── Tools ───────────────────────────────────────────────────────────────────


def test_decision_ask_tool_reports_unavailable_without_a_service():
    context = SimpleNamespace(run_id="r", user_id="u", conversation_id=None)
    text, payload = asyncio.run(decision_ask({"state": "x", "questions": {}}, context))
    assert "not available" in text
    assert payload["status"] == "UNAVAILABLE"


def test_decision_ask_tool_validates_before_calling_the_provider(tmp_path):
    registry = DecisionRegistry([])
    service = DecisionService(_store(tmp_path), registry=registry)
    context = SimpleNamespace(
        run_id="r", user_id="u", conversation_id=None, decision_service=service
    )

    text, payload = asyncio.run(
        decision_ask({"state": "x", "questions": {"q": {"type": "nope"}}}, context)
    )

    assert payload["status"] == "INVALID"
    assert "questions" in text


def test_decisions_register_read_only_tools():
    registry = ToolRegistry()
    register_decision_tools(registry)
    assert set(registry.names()) >= {"decision_ask", "decision_list", "decision_scorecard"}
    for name in ("decision_ask", "decision_list", "decision_scorecard"):
        assert registry.get(name).permission == "read"


def test_decision_scorecard_tool_reports_counts(tmp_path):
    fake = _FakeProvider({"is_risky": NoulAnswer(noul=0.97)})
    service = _service(tmp_path, [fake])
    asyncio.run(service.ask(_request(), owner_id="u1"))
    context = SimpleNamespace(user_id="u1", decision_service=service)

    text, card = asyncio.run(decision_scorecard({}, context))

    assert card["total"] == 1
    assert "1 answered" in text


def test_the_service_boots_with_the_decision_layer(tmp_path):
    from harness.agents import ECLIPSE_AGENT
    from harness.service import AgenticService

    store = _store(tmp_path)
    service = AgenticService(store=store)
    try:
        assert service.decision is not None
        assert service.registry.get("decision_ask") is not None
        assert "decision_ask" in ECLIPSE_AGENT.tools
    finally:
        store.close()

