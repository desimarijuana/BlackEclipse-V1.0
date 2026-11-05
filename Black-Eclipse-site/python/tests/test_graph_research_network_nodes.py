"""Wave B research network adapters (fetch_many / scrape / extract_facts / deep_dive)."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from harness.graph_runtime.compiler import RunGrants, compile_workflow
from harness.graph_runtime.model import ExecutionMode, WorkflowIR
from harness.graph_runtime.nodes import build_default_registry
from harness.graph_runtime.registry import NodeExecContext
from harness.graph_runtime.research_nodes import set_evidence_store, set_research_bridge
from harness.persistence import AgentMemoryStore
from harness.research.web_store import EvidenceStore

REGISTRY = build_default_registry()
RID = "r_network"


class _FakeBridge:
    async def fetch(self, capability, params):
        if capability == "web_search":
            return {
                "status": "OK",
                "provider": "fake",
                "results": [
                    {"title": "A", "url": "https://example.com/a", "snippet": "a"},
                    {"title": "B", "url": "https://other.test/b", "snippet": "b"},
                ],
            }
        if capability == "web_fetch":
            url = params["url"]
            if "fail" in url:
                return {"status": "NOT_FOUND", "url": url, "error": "gone"}
            text = "the same document body" if "dup" in url else f"body of {url}"
            return {"status": "OK", "url": url, "title": url, "text": text}
        if capability == "web_collect":
            return {
                "status": "OK",
                "finalUrl": params["url"],
                "rows": [{"symbol": "AAPL", "close": "190"}],
                "tables": [{"columns": ["symbol", "close"], "rows": [["AAPL", "190"]]}],
                "columns": ["symbol", "close"],
                "matched": 1,
                "retrievedAt": "2026-11-01T00:00:00Z",
            }
        return {"status": "UNAVAILABLE", "error": "unexpected capability"}


@pytest.fixture()
def store(tmp_path):
    memory = AgentMemoryStore(str(tmp_path / "agent-memory.db"))
    evidence = EvidenceStore(memory)
    evidence.save_run({
        "researchId": RID, "question": "q", "state": "COMPLETED", "status": "OK",
    })
    set_evidence_store(evidence)
    set_research_bridge(_FakeBridge())
    try:
        yield evidence
    finally:
        set_evidence_store(None)
        set_research_bridge(None)
        memory.close()


def _exec(node_type, config=None, inputs=None, research_id=None):
    definition = REGISTRY.get(node_type)
    assert definition is not None and definition.executor is not None
    wired = dict(inputs or {})
    if research_id is not None:
        wired.setdefault("researchId", research_id)
    return definition.executor(NodeExecContext(
        node_id=node_type, run_id="run", mode=ExecutionMode.RESEARCH,
        inputs=wired, config=config or {},
    ))


def test_fetch_many_saves_evidence_and_dedupes(store):
    urls = [
        "https://example.com/one",
        "https://example.com/dup-a",
        "https://other.test/dup-b",
    ]
    result = _exec("research.fetch_many", {"dedupe": True}, {"urls": urls}, RID)
    assert result["summary"]["fetched"] == 3
    assert result["summary"]["deduped"] == 1
    assert result["summary"]["failed"] == 0
    assert result["summary"]["status"] == "OK"
    assert len(store.list_evidence(RID)) == 2
    # The duplicate is reported with a pointer, not silently dropped.
    duplicates = [page for page in result["pages"] if page.get("duplicateOf")]
    assert len(duplicates) == 1


def test_fetch_many_keeps_partial_failures_as_rows(store):
    result = _exec("research.fetch_many", {}, {
        "urls": ["https://example.com/ok", "https://example.com/fail"],
    }, None)
    assert result["summary"]["fetched"] == 1
    assert result["summary"]["failed"] == 1
    assert result["summary"]["status"] == "PARTIAL"
    failed = [page for page in result["pages"] if page["status"] != "OK"]
    assert failed[0]["error"] == "gone"


def test_fetch_many_all_fail_is_an_error(store):
    with pytest.raises(ValueError, match="could not retrieve any"):
        _exec("research.fetch_many", {}, {"urls": ["https://example.com/fail"]})


def test_fetch_many_rejects_non_http_urls(store):
    with pytest.raises(ValueError, match="absolute http"):
        _exec("research.fetch_many", {}, {"urls": ["file:///etc/passwd"]})


def test_scrape_returns_rows_and_a_page_status(store):
    result = _exec("research.scrape", {"url": "https://example.com/table", "maxRows": 10})
    assert result["rows"][0]["symbol"] == "AAPL"
    assert result["page"]["status"] == "OK"
    assert result["summary"]["status"] == "OK"


class _FakeModel:
    def __init__(self, content):
        self.content = content

    async def ainvoke(self, messages):
        return SimpleNamespace(content=self.content)


def _fact(metric, value, period, page_id, span):
    return {
        "metric": metric, "value": value, "currency": "USD", "unit": "million",
        "period": period, "pageId": page_id, "sourceSpan": span,
    }


def test_extract_facts_accepts_only_verbatim_validated_facts(monkeypatch, store):
    import harness.graph_runtime.research_network_nodes as network

    monkeypatch.setattr(
        network, "_model_for",
        lambda context, timeout_s: _FakeModel(json.dumps({"facts": [
            _fact("revenue", 1000, "FY2025", "p1", "FY2025 revenue was $1,000 million"),
            _fact("revenue", 2000, "FY2025", "p1", "revenue was $2,000 million"),
        ]})),
    )
    pages = [{
        "url": "https://example.com/10k", "title": "10-K", "sourceType": "company",
        "pageId": "p1", "text": "FY2025 revenue was $1,000 million, up 10%.",
    }]
    result = _exec("research.extract_facts", {
        "objective": "revenue", "legsJson": [{"metric": "revenue", "period": "FY2025"}],
    }, {"pages": pages})
    assert result["summary"]["accepted"] == 1
    assert result["summary"]["rejected"] == 1
    assert result["evidence"][0]["objects"][0]["value"] == 1000
    assert result["rejected"][0]["metric"] == "revenue"


def test_extract_facts_requires_pages_and_legs(store):
    with pytest.raises(ValueError, match="pages"):
        _exec("research.extract_facts", {"objective": "x", "legsJson": [{"metric": "revenue"}]})
    with pytest.raises(ValueError, match="legsJson"):
        _exec("research.extract_facts", {"objective": "x"},
              {"pages": [{"url": "https://x", "text": "y"}]})


def test_deep_dive_runs_the_engine_and_returns_the_run_id(monkeypatch, store):
    class _Result:
        researchId = "r_deep"

        def to_dict(self):
            return {
                "status": {"state": "COMPLETED", "stopReason": "objective answered"},
                "coverage": {"status": "COMPLETE"},
                "answer": "Revenue grew.",
                "sources": [{"canonicalUrl": "https://example.com"}],
                "evidence": [{"evidenceId": "e1"}],
                "claims": [{"id": "c1"}],
                "conflicts": [],
            }

    class _Engine:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        async def run(self, request):
            assert request.question == "Did revenue grow?"
            return _Result()

    monkeypatch.setattr("harness.research.web_engine.ResearchEngine", _Engine)
    result = _exec("research.deep_dive", {"question": "Did revenue grow?"})
    assert result["researchId"] == "r_deep"
    assert result["answer"] == "Revenue grew."
    assert result["summary"]["state"] == "COMPLETED"
    assert result["summary"]["sources"] == 1


def test_deep_dive_rejects_an_unknown_depth(store):
    with pytest.raises(ValueError, match="depth"):
        _exec("research.deep_dive", {"question": "q", "depth": "turbo"})


def test_network_research_nodes_are_refused_in_a_test_run():
    for node_type, config in (
        ("research.fetch_many", {"urls": ["https://example.com"]}),
        ("research.deep_dive", {"question": "q"}),
    ):
        ir = WorkflowIR.model_validate({
            "irVersion": 1, "id": "wf_net", "name": "net",
            "meta": {"createdAt": "", "updatedAt": "", "tags": []},
            "nodes": [
                {"id": "trig", "type": "trigger.manual", "version": "1.0.0",
                 "config": {}, "layout": {"x": 0, "y": 0}},
                {"id": "net", "type": node_type, "version": "1.0.0",
                 "config": config, "layout": {"x": 0, "y": 0}},
                {"id": "out", "type": "output.result", "version": "1.0.0",
                 "config": {}, "layout": {"x": 0, "y": 0}},
            ],
            "edges": [
                {"id": "e1", "source": "trig", "sourceHandle": "start",
                 "target": "net", "targetHandle": "question"},
                {"id": "e2", "source": "net", "sourceHandle": "summary",
                 "target": "out", "targetHandle": "value"},
            ],
            "settings": {"executionMode": "research", "failFast": False,
                         "maxConcurrency": 1, "timeoutMs": 0},
            "requiredCapabilities": ["network.egress"],
        })
        denied = compile_workflow(ir, REGISTRY, RunGrants(test_run=True))
        assert denied.executable is False, node_type
