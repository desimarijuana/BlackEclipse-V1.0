"""Phase 4 Workstream 5 — source-grounded supersession / restatement chains.

A link exists only from explicit source metadata; a differing value alone is
never a restatement. Bad links (dangling, cyclic, unknown kind) are rejected, and
point-in-time queries resolve only revisions available by the cutoff.
"""

from __future__ import annotations

from harness.research.supersession import build_chain
from harness.retrieval.contract import (
    EvidenceItem,
    NormalizedFinancialObject,
    SourceReference,
)


def item(
    eid: str,
    *,
    value: float = 100.0,
    period: str = "FY2024",
    supersedes: str | None = None,
    kind: str | None = None,
    published: str | None = None,
    document_id: str | None = None,
):
    return EvidenceItem(
        id=eid,
        kind="structured",
        summary=eid,
        objects=[
            NormalizedFinancialObject(
                name="revenue",
                value=value,
                period=period,
                instrument="TEST",
                supersedesEvidenceId=supersedes,
                relationshipKind=kind,
                publishedAt=published,
                documentId=document_id,
                source=SourceReference(source="SEC", sourceType="primary", validationStatus="valid"),
            )
        ],
        source=SourceReference(source="SEC", sourceType="primary", validationStatus="valid"),
    )


def test_no_metadata_is_unavailable_not_guessed():
    chain = build_chain([item("E1"), item("E2", value=120.0)])
    assert chain.coverage == "unavailable"
    assert chain.links == []
    assert chain.currentByKey == {}


def test_valid_amendment_creates_chain_and_current():
    original = item("E1", value=100.0, published="2024-02-01")
    restated = item("E2", value=120.0, supersedes="E1", kind="restates", published="2024-06-01")
    chain = build_chain([original, restated])
    assert chain.coverage == "available"
    assert len(chain.links) == 1
    assert chain.links[0].relationshipKind == "restates"
    key = "revenue|FY2024|TEST"
    assert chain.currentByKey[key] == "E2"


def test_unknown_relationship_kind_rejected():
    original = item("E1", published="2024-02-01")
    bad = item("E2", supersedes="E1", kind="frobnicates", published="2024-06-01")
    chain = build_chain([original, bad])
    # The bad link is ignored; with no valid links coverage is unavailable.
    assert chain.coverage == "unavailable"
    assert any("unknown relationship kind" in i for i in chain.issues)


def test_dangling_link_reported():
    bad = item("E2", supersedes="GHOST", kind="amends", published="2024-06-01")
    chain = build_chain([bad])
    assert chain.coverage == "available"
    assert any("unknown evidence" in i for i in chain.issues)


def test_cycle_rejected():
    a = item("E1", supersedes="E2", kind="amends", published="2024-01-01")
    b = item("E2", supersedes="E1", kind="amends", published="2024-02-01")
    chain = build_chain([a, b])
    assert chain.coverage == "unavailable"
    assert any("cycle" in i for i in chain.issues)
    assert chain.links == []


def test_as_of_resolves_revision_available_by_cutoff():
    original = item("E1", value=100.0, published="2024-02-01")
    restated = item("E2", value=120.0, supersedes="E1", kind="restates", published="2024-06-01")
    chain = build_chain([original, restated])
    assert chain.resolve_as_of("E2", "2024-03-01") is None  # amendment not yet available
    assert chain.resolve_as_of("E2", "2024-07-01") == "E2"  # available after publication


def test_point_in_time_before_amendment_uses_original():
    original = item("E1", value=100.0, published="2024-02-01")
    restated = item("E2", value=120.0, supersedes="E1", kind="restates", published="2024-06-01")
    chain = build_chain([original, restated])
    # No revision is available at the earlier cutoff, so nothing supersedes.
    assert chain.resolve_as_of("E2", "2024-03-01") is None


def test_unknown_publication_time_never_becomes_current():
    original = item("E1", published="2024-02-01")
    unknown = item("E2", supersedes="E1", kind="corrects", published=None)
    chain = build_chain([original, unknown])
    assert chain.coverage == "available"
    # E2 is in history but, having no publication time, is not the current head.
    assert chain.currentByKey.get("revenue|FY2024|TEST") != "E2"
