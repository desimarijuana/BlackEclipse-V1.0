"""W5.3 — corpus BM25: bounded, deterministic, and honest about no signal."""

from __future__ import annotations

from harness.eclipse_memory.bm25 import BM25Index, bm25_scores, tokenize


def test_tokenize_is_lowercase_alphanumeric():
    assert tokenize("Drawdown, 2024-Q1!") == ["drawdown", "2024", "q1"]


def test_empty_query_scores_zero_for_every_document():
    scores = bm25_scores("", {"a": "drawdown risk", "b": "portfolio"})
    assert scores == {"a": 0.0, "b": 0.0}


def test_no_overlap_scores_zero():
    scores = bm25_scores("volatility", {"a": "drawdown risk", "b": "portfolio"})
    assert scores == {"a": 0.0, "b": 0.0}


def test_rare_term_outranks_a_common_one():
    documents = {
        "common": "market data market data market data",
        "rare": "market data drawdown",
    }
    scores = bm25_scores("drawdown", documents)
    assert scores["rare"] == 1.0
    assert scores["common"] == 0.0


def test_scores_are_normalized_and_deterministic():
    documents = {
        "a": "risk drawdown risk drawdown",
        "b": "risk drawdown",
        "c": "portfolio risk",
    }
    first = BM25Index(documents).scores("risk drawdown")
    second = BM25Index(documents).scores("risk drawdown")
    assert first == second
    assert max(first.values()) == 1.0
    assert all(0.0 <= value <= 1.0 for value in first.values())


def test_term_in_every_document_has_zero_idf():
    # A term present in every document is not discriminative.
    documents = {"a": "report alpha", "b": "report beta"}
    scores = bm25_scores("report", documents)
    assert scores == {"a": 0.0, "b": 0.0}


def test_longer_document_is_penalized_by_length_normalization():
    documents = {
        "short": "drawdown",
        "long": "drawdown " + " ".join(["filler"] * 40),
        "other": "portfolio",
    }
    scores = bm25_scores("drawdown", documents)
    assert scores["short"] > scores["long"]
