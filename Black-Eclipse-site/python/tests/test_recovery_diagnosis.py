"""Root-cause diagnosis — hypotheses, evidence ranking, decisive vs not (pure)."""

from __future__ import annotations

from harness.recovery.diagnosis import DiagnosisEngine
from harness.recovery.taxonomy import FailureKind, normalize_failure


def _engine() -> DiagnosisEngine:
    return DiagnosisEngine()


def test_timeout_without_evidence_is_not_decisive():
    d = _engine().diagnose(normalize_failure(code="TOOL_TIMEOUT", message="timed out"))
    assert d.kind == FailureKind.TIMEOUT
    assert d.selected is None
    assert not d.decisive
    assert d.hypotheses
    assert d.missing_information


def test_dependency_confirmed_evidence_is_decisive():
    d = _engine().diagnose(
        normalize_failure(code="dependency", message="ModuleNotFoundError: no module named 'x'"),
        evidence={"dependency_missing": True},
    )
    assert d.kind == FailureKind.DEPENDENCY
    assert d.decisive
    assert "package" in (d.selected or "")


def test_evidence_raises_the_matching_hypothesis():
    f = normalize_failure(code="TOOL_TIMEOUT", message="timed out")
    base = _engine().diagnose(f)
    confirmed = _engine().diagnose(f, evidence={"exceeded_timeout": True})
    base_top = max(h.confidence for h in base.hypotheses)
    confirmed_top = max(h.confidence for h in confirmed.hypotheses)
    assert confirmed_top > base_top


def test_unknown_kind_yields_a_catalogued_fallback():
    d = _engine().diagnose(normalize_failure(code="totally_novel", message="who knows"))
    assert d.hypotheses
    assert d.selected is None


def test_to_dict_shape():
    d = _engine().diagnose(
        normalize_failure(code="authentication_error", message="401"),
        evidence={"credential_missing": True},
    )
    view = d.to_dict()
    assert view["kind"] == "authentication"
    assert view["decisive"] is True
    assert view["hypotheses"][0]["cause"]
    assert "evidence" in view
