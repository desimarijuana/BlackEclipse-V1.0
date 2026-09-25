"""Retrieval normalization — synonyms, light stemming, subject aliases and safe
bounded typo tolerance, plus the release-threshold gate.

Correctness:
  * deterministic (no model/network);
  * scope/status filtering stays authoritative (semantic-looking matches cannot
    authorize access);
  * a lexical relevance signal is still required for topical memory;
  * a threshold failure on forbidden hits / scope leakage / no-match overreach is
    caught, not ignored.
"""

from __future__ import annotations

import os
import tempfile

import pytest

from harness.eclipse_memory import EclipseMemoryService, EclipseMemoryStore
from harness.eclipse_memory.eval import THRESHOLDS, check_thresholds, run_evaluation
from harness.eclipse_memory.normalize import (
    bounded_edit_distance,
    canonical_tokens,
    fuzzy_token_match,
    stem,
)
from harness.eclipse_memory.retrieval import _score


@pytest.fixture()
def service():
    directory = tempfile.mkdtemp(prefix="be-norm-")
    svc = EclipseMemoryService(EclipseMemoryStore(os.path.join(directory, "eclipse-memory.db")))
    yield svc
    svc.close()


# ── Normalization unit behaviour ────────────────────────────────────────────


def test_synonyms_fold_to_canonical():
    assert stem("money") == "currency"
    assert stem("denominated") == "currency"
    assert stem("citations") == "source"
    assert stem("graph") == "chart"


def test_plural_fold():
    assert stem("charts") == "chart"
    assert stem("currencies") == "currency"
    assert canonical_tokens(["charts", "sources"]) == ["chart", "source"]


def test_canonical_tokens_dedupes():
    assert canonical_tokens(["money", "currency", "currencies"]) == ["currency"]


def test_typo_tolerance_is_bounded():
    assert bounded_edit_distance("currency", "currancy") == 1
    assert fuzzy_token_match("currancy", {"currency"}) is True
    # A short token is never fuzzy-matched.
    assert fuzzy_token_match("cat", {"cut"}) is False
    # A large edit distance does not match.
    assert fuzzy_token_match("currency", {"entirely"}) is False


# ── Relevance behaviour ─────────────────────────────────────────────────────


def test_typo_query_recalls_currency(service):
    service.write_memory(
        memory_type="semantic", content="The user's reporting currency for statements is PKR.",
        source="manual", scope="user", scope_id="u1", subject="reporting-currency",
        verification="verified",
    )
    result = service.retrieve(query="What currancy does the user report in?", actor_scope="user", scope_id="u1")
    assert any(m.get("subject") == "reporting-currency" for m in result.memories)


def test_unrelated_high_confidence_memory_is_not_recalled(service):
    # High importance/confidence must not recall an unrelated topical memory.
    service.write_memory(
        memory_type="semantic", content="Platform convention: report timestamps in UTC.",
        source="manual", scope="general", subject="timestamps",
        confidence=0.95, importance=0.95, verification="verified",
    )
    result = service.retrieve(query="What is the weather in Karachi?", actor_scope="user")
    assert all(m["memoryType"] in ("preference", "constraint") for m in result.memories)


def test_semantic_match_cannot_authorize_scope(service):
    # A synonym/typo match in another user's scope is never returned.
    service.write_memory(
        memory_type="semantic", content="User's reporting currency is PKR.",
        source="manual", scope="user", scope_id="u2", subject="reporting-currency",
    )
    result = service.retrieve(query="What currancy is used?", actor_scope="user", scope_id="u1")
    assert all(m.get("scopeId") != "u2" for m in result.memories)


def test_score_reports_fuzzy_reason():
    memory = {
        "id": "m1", "content": "The user's reporting currency for statements is PKR.",
        "subject": "reporting-currency", "importance": 0.5, "confidence": 0.6,
        "verification": "unverified", "accessCount": 0,
    }
    _, reasons, signal = _score(memory, ["currancy"], None)
    assert signal is True
    assert any("fuzzy" in r or "keyword" in r for r in reasons)


# ── Release thresholds ──────────────────────────────────────────────────────


def test_eval_within_thresholds():
    report = run_evaluation()
    gate = check_thresholds(report)
    assert gate["passed"] is True, gate["failures"]


def test_thresholds_reject_forbidden_hit():
    report = run_evaluation()
    metrics = dict(report["metrics"])
    metrics["forbiddenHits"] = 1
    gate = check_thresholds({**report, "metrics": metrics})
    assert gate["passed"] is False
    assert any("forbiddenHits" in f for f in gate["failures"])


def test_thresholds_reject_scope_leak():
    report = run_evaluation()
    metrics = dict(report["metrics"])
    metrics["scopeLeakage"] = 1
    gate = check_thresholds({**report, "metrics": metrics})
    assert gate["passed"] is False


def test_thresholds_are_declared():
    assert THRESHOLDS["forbiddenHits"] == 0
    assert THRESHOLDS["scopeLeakage"] == 0
    assert THRESHOLDS["noMatchClean"] is True
