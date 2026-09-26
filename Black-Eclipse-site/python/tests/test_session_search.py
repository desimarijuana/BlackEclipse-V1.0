"""Full-session historical recall (M2) — indexing, search, redaction, safety.

The session search index is a bounded, redacted, searchable projection of prior
runs. These tests pin:

  * exact matches and normalization/punctuation tolerance;
  * date filters and user isolation;
  * snippet bounding and result limits;
  * secret redaction before indexing;
  * deletion and reindexing idempotency;
  * honest FTS5-unavailable behavior;
  * the guarantee that historical content is never treated as current evidence
    (it is returned through read-only tools only).
"""

from __future__ import annotations

import os
import tempfile

import pytest

from harness.persistence import AgentMemoryStore
from harness.session_index import index_run, redact
from harness.tools import ToolResult


@pytest.fixture()
def store(tmp_path):
    s = AgentMemoryStore(os.path.join(str(tmp_path), "agent-memory.db"))
    yield s
    s.close()


def _run(store, run_id, query, output=None, user_id="u1", tools=None):
    store.create_run(run_id, "eclipse-agent", {"query": query}, user_id=user_id)
    if output:
        store.update_run(run_id, status="completed", output=output)
    for index, text in enumerate(tools or []):
        store.record_tool_execution(run_id, ToolResult(
            tool_call_id=f"c{index}", name="market_get_quote", ok=True, text=text, duration_ms=5,
        ))


def test_exact_match_and_punctuation_tolerance(store):
    _run(store, "run_1", "What did we decide about the reporting currency?", "We report in PKR.")
    index_run(store, "run_1", user_id="u1")
    # Exact words.
    assert store.search_session_messages("reporting currency")["results"]
    # Punctuation/extra tokens are tolerated (tokens are ANDed).
    assert store.search_session_messages("currency?? reporting")["results"]
    # A miss is honest.
    assert store.search_session_messages("unrelated zebra")["results"] == []


def test_date_filters(store):
    _run(store, "run_1", "alpha decision note", "done")
    index_run(store, "run_1")
    future = "2999-01-01T00:00:00.000Z"
    past = "2000-01-01T00:00:00.000Z"
    assert store.search_session_messages("alpha", date_from=future)["results"] == []
    assert store.search_session_messages("alpha", date_to=future)["results"]
    assert store.search_session_messages("alpha", date_from=past)["results"]


def test_user_isolation(store):
    _run(store, "run_a", "my private note apple", "ok", user_id="alice")
    _run(store, "run_b", "my private note banana", "ok", user_id="bob")
    index_run(store, "run_a", user_id="alice")
    index_run(store, "run_b", user_id="bob")
    alice = store.search_session_messages("private note", user_id="alice")
    assert {r["runId"] for r in alice["results"]} == {"run_a"}
    bob = store.search_session_messages("private note", user_id="bob")
    assert {r["runId"] for r in bob["results"]} == {"run_b"}
    # Global search sees both.
    every = store.search_session_messages("private note")
    assert {r["runId"] for r in every["results"]} == {"run_a", "run_b"}


def test_snippet_and_result_bounding(store):
    long_text = "needle " + ("x" * 5000)
    _run(store, "run_1", long_text, "ok")
    index_run(store, "run_1")
    results = store.search_session_messages("needle", limit=5)["results"]
    assert results
    assert len(results[0]["snippet"]) <= 321
    assert results[0]["content"] is None  # search returns snippets, not full text


def test_secrets_are_redacted_before_indexing(store):
    _run(store, "run_1", "my key is sk-abcdefghijklmnop123456", "used api_key=supersecretvalue")
    index_run(store, "run_1")
    # The raw secret is not searchable and not present in any indexed row.
    full = store.open_session("run_1")
    blob = " ".join(m["content"] or "" for m in full["messages"])
    assert "sk-abcdefghijklmnop123456" not in blob
    assert "supersecretvalue" not in blob
    assert "[redacted]" in blob


def test_redact_helper():
    assert "sk-abcdefghijklmnop123456" not in redact("key sk-abcdefghijklmnop123456 end")
    assert "token=[redacted]" in redact("token=abc123")
    assert redact("") == ""


def test_delete_and_reindex_are_idempotent(store):
    _run(store, "run_1", "one two three", "done")
    index_run(store, "run_1")
    first = store.session_message_count()
    assert first >= 2
    # Reindexing the same run replaces, never duplicates.
    index_run(store, "run_1")
    assert store.session_message_count() == first
    # Delete removes the index but leaves the run trace.
    removed = store.delete_session_messages("run_1")
    assert removed == first
    assert store.session_message_count() == 0
    assert store.get_run("run_1") is not None
    assert store.search_session_messages("three")["results"] == []


def test_open_session_window(store):
    store.create_run("run_1", "eclipse-agent", {"query": "seed"})
    for i in range(6):
        store.index_session_message(run_id="run_1", role="user", content=f"message number {i}", ordinal=i)
    window = store.open_session("run_1", before=1, after=1)
    # no anchor -> from the start, bounded by after+1
    assert len(window["messages"]) == 2
    assert window["truncated"] is True
    mid = store.open_session("run_1", message_id=window["messages"][0]["messageId"], before=0, after=2)
    assert len(mid["messages"]) <= 3


def test_fts_unavailable_falls_back_honestly(store, monkeypatch):
    _run(store, "run_1", "fallback needle apple", "ok")
    index_run(store, "run_1")
    monkeypatch.setattr(store, "fts5_available", lambda: False)
    result = store.search_session_messages("needle apple")
    assert result["engine"] == "like"
    assert result["available"] is True
    assert result["results"]


def test_run_indexing_reports_counts(store):
    _run(store, "run_1", "question here", "answer here", tools=["tool output here"])
    result = index_run(store, "run_1")
    assert result["ok"] is True
    assert result["indexed"] >= 3


def test_indexing_never_raises_on_missing_run(store):
    result = index_run(store, "does-not-exist")
    assert result["ok"] is False
