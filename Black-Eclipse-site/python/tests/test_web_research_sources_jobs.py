"""Integration tests for the "what it is NOT" fixes.

Each test pins one of the gaps that were closed:

  * web-research evidence reaches the run's chat "Sources" panel
    (`source_collector`), the same surface the retrieval layer uses;
  * research is SCHEDULABLE via the new job templates (background autonomy);
  * the search-provider presets exist so an operator can configure a real
    provider without hand-writing JSON.
"""

from __future__ import annotations

import pytest

from harness.research.web_contracts import Evidence, SourceType
from harness.source_collector import SourceCollector


# ── web-research → chat Sources panel ─────────────────────────────────────────────


def _evidence(url: str, *, tier: SourceType, title: str = "T", published: str | None = None) -> Evidence:
    return Evidence(
        evidenceId=f"ev:{url}",
        sourceId=f"src:{url}",
        sourceUrl=url,
        sourceType=tier,
        provenance={"title": title},
        publishedAt=published,
    )


def test_web_evidence_reaches_the_sources_panel():
    from harness.research.web_tools import _record_web_evidence
    from harness.tools import ToolContext

    sink = SourceCollector()
    ctx = ToolContext(run_id="r", log=lambda m, d=None: None, source_sink=sink)
    _record_web_evidence(ctx, _evidence("https://www.sec.gov/x", tier=SourceType.REGULATOR, title="10-K", published="2025-02-26"))
    _record_web_evidence(ctx, _evidence("https://reuters.com/x", tier=SourceType.NEWS, title="Report"))
    blob = sink.to_research_blob()
    assert blob is not None
    citations = blob["metadata"]["citations"]
    assert len(citations) == 2
    assert any(c["sourceType"] == "regulator" for c in citations)
    assert any(c["sourceType"] == "news" for c in citations)
    # A consulted source is provenance, never a verification claim.
    assert blob["status"] == "collected"


def test_failed_web_source_is_a_failed_route_not_a_citation():
    sink = SourceCollector()
    sink.add_web_source(url="https://dead.example/x", ok=False, tier="unknown")
    blob = sink.to_research_blob()
    assert blob is not None
    assert blob["metadata"]["citations"] == []
    assert any("dead.example" in r for r in (blob["failedRoutes"] or []))


def test_web_conflict_is_surfaced():
    sink = SourceCollector()
    sink.add_web_source(url="https://a.com/x", ok=True, tier="news")
    sink.add_web_conflict(metric="revenue", period="FY2025", candidates=[{"value": 1}, {"value": 2}])
    # Idempotent on (metric, period).
    sink.add_web_conflict(metric="revenue", period="FY2025", candidates=[{"value": 1}, {"value": 2}])
    blob = sink.to_research_blob()
    assert len(blob["metadata"]["conflicts"]) == 1


@pytest.mark.asyncio
async def test_research_query_routes_evidence_to_the_sink(tmp_workspace, monkeypatch):
    """A research_query run forwards its evidence + conflicts to the source sink."""
    import os

    from harness.persistence import AgentMemoryStore
    from harness.research import web_tools
    from harness.research.web_contracts import SearchResponse, SearchResult
    from harness.research.web_providers import SearchProviderRegistry
    from harness.research.web_store import EvidenceStore
    from harness.tools import ToolContext

    pages = {"https://sec.gov/nvda": {"url": "https://sec.gov/nvda", "title": "NVIDIA 10-K",
                                      "text": "Revenue for fiscal 2025 was 130,497 million dollars."}}

    class Bridge:
        async def fetch(self, capability, params):
            if capability == "web_search":
                return {"status": "OK", "provider": "fake",
                        "results": [{"title": "NVIDIA", "url": "https://sec.gov/nvda", "snippet": "s"}]}
            if capability == "web_fetch":
                return {"status": "OK", **pages.get(params["url"], {})}
            return {"status": "UNAVAILABLE"}

    store = EvidenceStore(AgentMemoryStore(os.path.join(tmp_workspace, "m.db")))
    sink = SourceCollector()
    ctx = ToolContext(run_id="r", log=lambda m, d=None: None, data_bridge=Bridge(),
                      evidence_store=store, source_sink=sink)

    _, payload = await web_tools.research_query({"question": "NVIDIA revenue", "min_sources": 1}, ctx)
    assert payload["status"] == "OK" or payload.get("evidence")
    blob = sink.to_research_blob()
    assert blob is not None
    assert any("sec.gov" in c["url"] for c in blob["metadata"]["citations"])


# ── research job templates (autonomy) ──────────────────────────────────────────────


def test_research_templates_exist_and_are_disabled():
    from harness.jobs.templates import JOB_TEMPLATES, get_template, instantiate

    ids = {t.id for t in JOB_TEMPLATES}
    assert {"deep-research-brief", "competitor-watch", "research-topic-digest"} <= ids
    for template_id, param, value in (
        ("deep-research-brief", "topic", "NVIDIA valuation"),
        ("competitor-watch", "company", "NVIDIA"),
        ("research-topic-digest", "topic", "the AI accelerator market"),
    ):
        job = instantiate(template_id, {param: value})
        assert job.enabled is False, "a template ships inert"
        objective = (job.target.objective or "").lower()
        assert any(word in objective for word in ("research", "landscape", "evidence-backed", "digest"))
        # An objective job (no workspace/autonomy) is a research job, not a code job.
        assert job.target.is_code_job() is False


def test_research_template_passes_guardrails():
    from harness.jobs.guardrails import validate_job
    from harness.jobs.templates import instantiate

    job = instantiate("deep-research-brief", {"topic": "NVIDIA valuation"})
    validated = validate_job(job)  # must not raise
    assert validated.enabled is False
    assert "NVIDIA valuation" in validated.target.objective
