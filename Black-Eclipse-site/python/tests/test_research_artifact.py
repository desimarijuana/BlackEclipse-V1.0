"""Research → Artifact Center integration.

A research run is recorded as a durable, evidence-REFERENCING report artifact so
it stays inspectable after the conversation ends and its evidence/validation
history is preserved (not duplicated). Best-effort: absent the Artifact Center the
producer is a harmless no-op.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from harness.artifacts import ArtifactService, ArtifactStore, LocalArtifactStorage
from harness.artifacts.bootstrap import set_artifact_service
from harness.artifacts.model import ArtifactCategory
from harness.artifacts.producers import _render_research_report, register_research_report
from harness.persistence import AgentMemoryStore


def _evidence(eid: str, url: str) -> SimpleNamespace:
    return SimpleNamespace(
        evidenceId=eid, sourceUrl=url, sourceId="src", sourceType="news",
        publishedAt="2026-01-01T00:00:00Z", retrievedAt="2026-01-02T00:00:00Z", rawText="x",
    )


def _claim(text: str, status: str, ids: list[str]) -> SimpleNamespace:
    return SimpleNamespace(text=text, status=status, evidenceIds=ids)


@pytest.fixture()
def artifact_service(tmp_path):
    store = AgentMemoryStore(str(tmp_path / "agent-memory.db"))
    service = ArtifactService(ArtifactStore(store), LocalArtifactStorage(tmp_path / "files"))
    set_artifact_service(service)
    try:
        yield service
    finally:
        set_artifact_service(None)
        store.close()


def test_no_service_is_a_noop():
    set_artifact_service(None)
    assert register_research_report(
        research_id="r1", question="q", evidence=[_evidence("e1", "u")], claims=[],
    ) is None


def test_empty_run_is_not_registered(artifact_service):
    assert register_research_report(research_id="r1", question="q", evidence=[], claims=[]) is None


def test_report_artifact_references_evidence_and_claims(artifact_service):
    evidence = [_evidence("e1", "https://sec.gov/a"), _evidence("e2", "https://reuters.com/b")]
    claims = [_claim("Revenue rose.", "SUPPORTED", ["e1"]), _claim("Beats consensus.", "UNSUPPORTED", [])]
    artifact = register_research_report(
        research_id="research-abcdef12", question="Did revenue rise?",
        snapshot_id="research-abcdef12_v1", evidence=evidence, claims=claims,
        citations=[{"citationId": "c1"}], conflicts=[],
        coverage={"status": "COMPLETE"},
    )
    assert artifact is not None
    assert artifact.category == ArtifactCategory.REPORT
    assert artifact.run_id == "research-abcdef12"
    assert artifact.metadata["researchId"] == "research-abcdef12"
    assert artifact.metadata["snapshotId"] == "research-abcdef12_v1"
    assert artifact.metadata["evidenceIds"] == ["e1", "e2"]
    assert artifact.metadata["claimStatuses"] == {"SUPPORTED": 1, "UNSUPPORTED": 1}
    assert artifact.metadata["coverageStatus"] == "COMPLETE"
    assert "research" in artifact.tags


def test_report_registration_is_idempotent_per_snapshot(artifact_service):
    kwargs = dict(
        research_id="r2", question="q", snapshot_id="s1",
        evidence=[_evidence("e1", "u")], claims=[_claim("c", "SUPPORTED", ["e1"])],
    )
    first = register_research_report(**kwargs)
    second = register_research_report(**kwargs)
    assert first is not None and second is not None
    assert first.id == second.id


def test_rendered_report_names_refs_not_raw_text():
    text = _render_research_report(
        research_id="r3", question="Q?", snapshot_id="v1",
        evidence=[_evidence("e1", "https://sec.gov/a")],
        claims=[_claim("Revenue rose.", "SUPPORTED", ["e1"])],
        citations=[{}], conflicts=[SimpleNamespace(metric="revenue", status="UNRESOLVED", explanation="differs")],
        coverage={"status": "PARTIAL"}, max_evidence=40,
    )
    assert "e1" in text and "https://sec.gov/a" in text
    assert "[SUPPORTED]" in text and "Revenue rose." in text
    assert "revenue" in text and "UNRESOLVED" in text
    assert "not duplicated" in text
