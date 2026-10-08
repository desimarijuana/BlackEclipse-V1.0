"""Entity/knowledge-graph extraction: evidence-anchored, deterministic, honest.

Every node/edge must carry an evidence anchor; nothing is invented.
"""

from __future__ import annotations

from harness.research.web_contracts import Evidence, SourceType
from harness.research.web_graph import build_graph, extract_entities, extract_relations


def _ev(eid: str, url: str, text: str, *, metric=None, value=None) -> Evidence:
    return Evidence(
        evidenceId=eid, sourceId="s", sourceUrl=url, sourceType=SourceType.NEWS,
        rawText=text, claimText=metric,
        structuredValue=value, unit="B", period="FY2025",
        provenance={"metric": metric, "title": "Test"},
    )


def test_entities_are_anchored_to_evidence():
    ev = _ev("e1", "https://x.com/a", "NVIDIA Corporation reported strong results. Microsoft Corporation also grew.")
    entities = extract_entities([ev])
    assert entities, "at least one entity must be extracted"
    assert all(e.evidenceId == "e1" for e in entities)
    assert all(e.sourceUrl == "https://x.com/a" for e in entities)


def test_relations_require_a_value():
    ev = _ev("e1", "https://sec.gov/a", "NVIDIA revenue rose.", metric="revenue", value=130.0)
    entities = extract_entities([ev])
    relations = extract_relations(entities, [ev])
    metric_edges = [r for r in relations if r.predicate == "revenue"]
    assert metric_edges, "a structured metric must produce a relation edge"
    assert metric_edges[0].objectValue == "130.0"
    assert metric_edges[0].evidenceId == "e1"


def test_no_entities_without_text():
    ev = Evidence(evidenceId="e", sourceId="s", sourceUrl="https://x", sourceType=SourceType.NEWS, rawText="")
    entities, relations = build_graph([ev])
    assert entities == []
    assert relations == []
