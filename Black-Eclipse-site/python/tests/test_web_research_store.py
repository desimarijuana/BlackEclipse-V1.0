"""Bug-fix regressions for the web research engine.

Found by probing edge cases the happy-path tests missed:

  * `make_source` returned an EMPTY `retrievedAt`, so persisted sources had no
    retrieval timestamp;
  * the same URL fetched in two research runs clobbered the second run's rows
    (sourceId/evidenceId were the primary key), so `list_*` returned nothing for
    the second run — evidence from one run could disappear when another run
    fetched the same URL;
  * a NULL `provenance` column made `Evidence(**row)` crash a tool;
  * per-run claim/citation/conflict ids collided across runs.
"""

from __future__ import annotations

import os

import pytest

from harness.research.web_contracts import Evidence, Claim
from harness.research.web_sources import make_source
from harness.research.web_store import EvidenceStore
from harness.research.web_verify import build_citations, detect_conflicts


def _store(tmp_workspace) -> EvidenceStore:
    from harness.persistence import AgentMemoryStore

    return EvidenceStore(AgentMemoryStore(os.path.join(tmp_workspace, "m.db")))


# ── make_source provenance ────────────────────────────────────────────────────────


def test_make_source_sets_retrieved_at():
    source = make_source("https://www.sec.gov/x")
    assert source.retrievedAt, "a source must carry its retrieval timestamp"
    assert "T" in source.retrievedAt


# ── cross-run isolation ─────────────────────────────────────────────────────────────


def test_same_source_and_evidence_belong_to_multiple_runs(tmp_workspace):
    store = _store(tmp_workspace)
    source = make_source("https://shared.com/a").model_dump()
    store.save_source(source, research_id="run1", ranking=0.5)
    store.save_source(source, research_id="run2", ranking=0.9)
    assert len(store.list_sources("run1")) == 1
    assert len(store.list_sources("run2")) == 1, "the second run must still see its shared source"

    ev = Evidence(evidenceId="evX", sourceId=source["sourceId"], sourceUrl="https://shared.com/a", rawText="t")
    store.save_evidence(ev.model_dump(), research_id="run1")
    store.save_evidence(ev.model_dump(), research_id="run2")
    assert len(store.list_evidence("run1")) == 1
    assert len(store.list_evidence("run2")) == 1, "the second run must still see its shared evidence"


def test_unlink_removes_from_one_run_only(tmp_workspace):
    store = _store(tmp_workspace)
    source = make_source("https://s.com/a").model_dump()
    store.save_source(source, research_id="a")
    store.save_source(source, research_id="b")
    store.unlink_source("a", source["sourceId"])
    assert store.list_sources("a") == []
    assert len(store.list_sources("b")) == 1


def test_null_provenance_row_is_readable(tmp_workspace):
    store = _store(tmp_workspace)
    # Simulate a legacy row whose provenance column is NULL.
    store._db.execute(
        "INSERT INTO WebResearchEvidence (evidenceId, researchId, sourceUrl, rawText, contentHash, provenance) "
        "VALUES ('legacy', 'r', 'https://x', 't', 'h', NULL)"
    )
    store._db.execute("INSERT INTO WebResearchEvidenceLink (researchId, evidenceId) VALUES ('r', 'legacy')")
    store._db.commit()
    rows = store.list_evidence("r")
    assert rows and rows[0]["provenance"] == {}
    # And it round-trips through the model without crashing.
    assert Evidence(**rows[0]).evidenceId == "legacy"


# ── per-run id namespacing ──────────────────────────────────────────────────────────


def test_citation_ids_are_namespaced_by_run():
    ev = Evidence(evidenceId="a", sourceId="s", sourceUrl="https://a", provenance={"title": "T"})
    claim = Claim(id="c", text="x", evidenceIds=["a"])
    c1 = build_citations([claim], {"a": ev}, research_id="run1")
    c2 = build_citations([claim], {"a": ev}, research_id="run2")
    assert c1[0].citationId != c2[0].citationId
    assert c1[0].citationId.startswith("run1_")
    assert c2[0].citationId.startswith("run2_")


def test_conflict_ids_are_namespaced(tmp_workspace):
    store = _store(tmp_workspace)
    a = Evidence(evidenceId="a", sourceId="s1", sourceUrl="https://a", structuredValue=1.0, period="FY24", claimText="revenue", provenance={"metric": "revenue"})
    b = Evidence(evidenceId="b", sourceId="s2", sourceUrl="https://b", structuredValue=2.0, period="FY24", claimText="revenue", provenance={"metric": "revenue"})
    conflicts = detect_conflicts([a, b])
    for run in ("run1", "run2"):
        store.save_conflict(run, {**conflicts[0].model_dump(), "id": f"{run}_conf_1"})
    assert len(store.list_conflicts("run1")) == 1
    assert len(store.list_conflicts("run2")) == 1


# ── continue / update after cancel ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_continue_after_cancel_is_not_instantly_cancelled(tmp_workspace):
    """A `continue` after a cancel must start with a FRESH cancel event."""
    from harness.research.web_contracts import ResearchRequest
    from harness.research.web_engine import ResearchEngine

    class Bridge:
        async def fetch(self, capability, params):
            if capability == "web_search":
                return {"status": "OK", "provider": "fake", "results": [{"title": "A", "url": "https://a.com/x", "snippet": "s", "publishedAt": "2025-03-01T00:00:00+00:00"}]}
            if capability == "web_fetch":
                return {"status": "OK", "url": params["url"], "title": "A", "text": "A meaningful paragraph about the market that is easily long enough to be material for a claim."}
            return {"status": "UNAVAILABLE"}

    store = _store(tmp_workspace)
    engine = ResearchEngine(bridge=Bridge(), store=store)
    mandate, plan = await engine.create_research(ResearchRequest(question="market research question", minSources=1))

    from harness.research.web_engine import request_cancel

    assert request_cancel(mandate.researchId) is True
    cancelled = await engine.execute_research(mandate, plan)
    assert cancelled.status.state == "CANCELLED"

    # Continue uses a fresh event and actually runs the pipeline again.
    continued = await engine.continue_research(mandate.researchId)
    assert continued is not None
    assert continued.status.state in ("COMPLETED", "PARTIAL", "FAILED")
    assert continued.status.state != "CANCELLED"
