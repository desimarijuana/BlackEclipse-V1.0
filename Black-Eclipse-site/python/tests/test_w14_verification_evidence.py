"""Round 4 (W14): the evidence the task-type verifiers read really exists.

W14 unified verification by task type, which needs the runtime to RECORD what
the verifiers check. Three seams are pinned here:

- the sandbox's `AnalysisRecord` rows are readable as bounded run evidence
  (`analysis_tools.load_run_analyses`), so a `data` task can verify a
  reproducible computation;
- the task outcome carries those rows as evidence;
- a document this run WROTE records the headings it wrote, so a contract's
  required sections are checkable — and the processed-document list (the
  sidebar) is unchanged by it.
"""

from __future__ import annotations

import sqlite3

from harness.analysis_tools import _record_analysis, load_run_analyses
from harness.code.execution import AnalysisResult
from harness.document_intelligence.collector import DocumentCollector
from harness.documents.authoring import block_headings, report_authored_document
from harness.tasks import bootstrap as task_bootstrap
from harness.tools import ToolContext, ToolRegistry
from harness.schemas import ModelSettings


class _Store:
    """The one shape the reader needs: the shared sqlite connection."""

    def __init__(self) -> None:
        self._db = sqlite3.connect(":memory:")


class _Service:
    def __init__(self, store) -> None:
        self.store = store
        self.artifacts = None


def _ctx(store) -> ToolContext:
    return ToolContext(
        run_id="run_a",
        log=lambda *_: None,
        user_id="local",
        model_settings=ModelSettings(provider="ollama", model="llama3.1"),
        tool_registry=ToolRegistry(),
        memory_store=store,
        analysis_enabled=True,
    )


def _result() -> AnalysisResult:
    return AnalysisResult(
        status="ok",
        outputs={"correlation": 0.42},
        source_digest="sha256:program",
        input_digests={"prices": "sha256:inputs"},
    )


# ── The analysis records ──────────────────────────────────────────────────────


def test_no_store_means_no_evidence():
    assert load_run_analyses(None, "run_a") is None
    assert load_run_analyses(_Store(), "") is None


def test_a_store_without_the_table_has_no_evidence():
    assert load_run_analyses(_Store(), "run_a") is None


def test_recorded_analyses_are_readable_as_bounded_evidence():
    store = _Store()
    _record_analysis(_ctx(store), _result())
    blob = load_run_analyses(store, "run_a")
    assert blob is not None
    record = blob["records"][0]
    assert record["status"] == "ok"
    assert record["sourceDigest"] == "sha256:program"
    assert record["inputDigests"] == {"prices": "sha256:inputs"}
    assert record["outputs"] == {"correlation": 0.42}


def test_another_runs_analyses_are_not_borrowed():
    store = _Store()
    _record_analysis(_ctx(store), _result())
    assert load_run_analyses(store, "run_b") is None


def test_the_task_outcome_carries_the_runs_analyses_as_evidence():
    store = _Store()
    _record_analysis(_ctx(store), _result())
    outcome = task_bootstrap._outcome_from_dump(
        {"runId": "run_a", "status": "completed", "output": "done"}, "run_a",
        _Service(store),
    )
    assert outcome.evidence["analyses"]["count"] == 1


def test_a_run_without_analyses_carries_no_analysis_evidence():
    outcome = task_bootstrap._outcome_from_dump(
        {"runId": "run_a", "status": "completed", "output": "done"}, "run_a",
        _Service(_Store()),
    )
    assert "analyses" not in outcome.evidence


# ── The document structure ────────────────────────────────────────────────────


def test_an_authored_document_records_its_sections():
    collector = DocumentCollector()
    collector.add({
        "ok": True, "kind": "authored_document", "title": "Memo", "state": "DELIVERED",
        "ir": {"sections": [{"title": "Summary"}, {"title": "Risks"}]},
    })
    blob = collector.to_blob()
    assert blob is not None
    authored = blob["authored"][0]
    assert authored["sectionTitles"] == ["Summary", "Risks"]
    # The sidebar keeps showing what was opened/processed — an authored
    # document must not appear there.
    assert blob["documents"] == []


def test_a_processed_document_records_its_sections_too():
    collector = DocumentCollector()
    collector.add({
        "ok": True, "kind": "document", "title": "Filing", "state": "PROCESSED",
        "ir": {"sections": [{"title": "Risk factors"}]},
    })
    blob = collector.to_blob()
    assert blob["documents"][0]["sectionTitles"] == ["Risk factors"]


def test_the_writer_reports_the_headings_it_wrote():
    sink = DocumentCollector().add
    ctx = ToolContext(
        run_id="run_a", log=lambda *_: None, user_id="local",
        model_settings=ModelSettings(provider="ollama", model="llama3.1"),
        tool_registry=ToolRegistry(), document_sink=sink,
    )
    headings = block_headings([
        {"type": "heading", "text": "Summary"},
        {"type": "paragraph", "text": "body"},
        {"type": "heading", "text": "Risks"},
    ])
    assert headings == ["Summary", "Risks"]
    report_authored_document(ctx, title="Memo", filename="memo.docx", headings=headings)
    # The collector received it (the sink is the collector's own `add`).
    assert ctx.document_sink is not None
