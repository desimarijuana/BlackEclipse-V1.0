"""Browser escalation, PDF extraction, and verification-tool coverage.

TEST 9 (extraction failure → browser escalation), plus the specialised tools:
pdf_extract, source_rank, source_compare, claim_verify, research_status/cancel.
"""

from __future__ import annotations

from typing import Any

import pytest

from harness.research.web_browser import MIN_USEFUL_CHARS, EscalationOutcome, needs_escalation
from harness.tools import ToolContext


def test_needs_escalation_decisions():
    assert needs_escalation(text="x" * 500)[0] is False
    assert needs_escalation(text="short")[0] is True
    assert needs_escalation(text="", fetch_status="UNAVAILABLE", fetch_error="javascript_only document")[0] is True
    assert needs_escalation(text="", fetch_status="UNAVAILABLE", fetch_error="unsupported_document")[0] is True
    # A paywall/login wall escalates to a credentialed browser session.
    assert needs_escalation(text="", fetch_status="UNAVAILABLE", fetch_error="the page returned a subscription wall")[0] is True
    assert needs_escalation(text="", fetch_status="UNAVAILABLE", fetch_error="sign in to continue")[0] is True


@pytest.mark.asyncio
async def test_research_start_returns_id_and_persists(tmp_workspace):
    """research_start dispatches a background run and returns its id at once."""
    import asyncio
    import os

    from harness.research import web_tools
    from harness.research.web_engine import background_research_active
    from harness.persistence import AgentMemoryStore
    from harness.research.web_store import EvidenceStore

    class Bridge:
        async def fetch(self, capability: str, params: dict[str, Any]) -> dict[str, Any]:
            if capability == "web_search":
                return {"status": "OK", "provider": "fake", "results": [{"title": "T", "url": "https://x.com/a", "snippet": "s"}]}
            if capability == "web_fetch":
                return {"status": "OK", "url": params["url"], "title": "T", "text": "A sufficiently long body of text for evidence extraction and claim building. " * 8}
            return {"status": "UNAVAILABLE"}

    memory = AgentMemoryStore(os.path.join(tmp_workspace, "agent-memory.db"))
    store = EvidenceStore(memory)
    ctx = ToolContext(run_id="r", log=lambda m, d=None: None, data_bridge=Bridge(), evidence_store=store)
    text, payload = await web_tools.research_start({"question": "What is the capital of France?"}, ctx)
    assert payload["status"] == "OK" and payload["mode"] == "background"
    assert payload["researchId"]
    # Persisted synchronously before scheduling, so it is observable now.
    assert store.get_run(payload["researchId"]) is not None
    # Let the task finish so it releases the DB before the fixture tears down.
    for _ in range(200):
        if not background_research_active(payload["researchId"]):
            break
        await asyncio.sleep(0.02)


@pytest.mark.asyncio
async def test_web_extract_escalates_to_browser(monkeypatch):
    """When HTTP extraction is insufficient, web_extract escalates to the browser."""
    from harness.research import web_tools

    class ThinBridge:
        async def fetch(self, capability: str, params: dict[str, Any]) -> dict[str, Any]:
            if capability == "web_fetch":
                return {"status": "OK", "url": params["url"], "title": "gated", "text": "tiny"}
            return {"status": "UNAVAILABLE"}

    async def fake_browser_extract(url, *, timeout_s=45.0):
        return EscalationOutcome(ok=True, url=url, text="A" * (MIN_USEFUL_CHARS + 50), title="rendered", reason="browser render succeeded")

    monkeypatch.setattr(web_tools, "browser_extract", fake_browser_extract)
    ctx = ToolContext(run_id="r", log=lambda m, d=None: None, data_bridge=ThinBridge())
    text, payload = await web_tools.web_extract({"url": "https://example.com/gated", "allow_browser": True}, ctx)
    assert payload["status"] == "OK"
    assert payload["escalation"].startswith("escalated to browser")
    assert payload["rawTextPreserved"] is True


@pytest.mark.asyncio
async def test_pdf_extract_honest_failure():
    from harness.research.web_tools import pdf_extract

    class ScannedBridge:
        async def fetch(self, capability: str, params: dict[str, Any]) -> dict[str, Any]:
            return {"status": "UNAVAILABLE", "error": "unsupported_document: scanned pdf has no text layer"}

    ctx = ToolContext(run_id="r", log=lambda m, d=None: None, data_bridge=ScannedBridge())
    text, payload = await pdf_extract({"url": "https://sec.gov/scanned.pdf"}, ctx)
    assert "scanned" in text.lower() or "unsupported" in text.lower()
    assert payload["status"] == "UNAVAILABLE"


@pytest.mark.asyncio
async def test_source_rank_and_company_tools():
    from harness.research.web_tools import company_search, source_rank

    ctx = ToolContext(run_id="r", log=lambda m, d=None: None)
    _, company = await company_search({"name": "NASDAQ:NVDA"}, ctx)
    assert company["status"] == "OK"
    assert company["canonical"]["ticker"] == "NVDA"

    _, ranked = await source_rank({"url": "https://www.sec.gov/x", "research_type": "financial"}, ctx)
    assert ranked["ranking"]["score"] > 0.5

    _, unknown = await company_search({"name": "Not A Real Company Zzz"}, ctx)
    assert unknown["status"] == "UNAVAILABLE"


@pytest.mark.asyncio
async def test_verification_tools_roundtrip(tmp_workspace):
    import os

    from harness.persistence import AgentMemoryStore
    from harness.research.web_contracts import Evidence, SourceType
    from harness.research.web_store import EvidenceStore
    from harness.research.web_tools import claim_verify, source_compare

    store = EvidenceStore(AgentMemoryStore(os.path.join(tmp_workspace, "m.db")))
    research_id = "r1"
    a = Evidence(evidenceId="a", sourceId="s1", sourceUrl="https://sec.gov/a", sourceType=SourceType.REGULATOR,
                 structuredValue=100.0, provenance={"metric": "revenue", "basis": "consolidated"})
    b = Evidence(evidenceId="b", sourceId="s2", sourceUrl="https://news.com/b", sourceType=SourceType.NEWS,
                 structuredValue=101.0, provenance={"metric": "revenue"})
    store.save_evidence(a.model_dump(), research_id=research_id)
    store.save_evidence(b.model_dump(), research_id=research_id)

    ctx = ToolContext(run_id="r", log=lambda m, d=None: None, evidence_store=store)
    _, comparison = await source_compare({"evidence_ids": ["a", "b"], "research_id": research_id}, ctx)
    assert comparison["status"] == "OK"

    _, verified = await claim_verify({"claim": "revenue is 100", "evidence_ids": ["a"], "research_id": research_id}, ctx)
    assert verified["claim"]["status"] in ("PARTIALLY_SUPPORTED", "SUPPORTED", "AMBIGUOUS")
