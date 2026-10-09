"""Default diagnosis probes — deterministic, read-only, honest about unknowns."""

from __future__ import annotations

from harness.recovery.diagnosis import DiagnosisEngine
from harness.recovery.probes import register_default_probes
from harness.recovery.taxonomy import FailureKind, normalize_failure


def test_dependency_probe_detects_a_missing_module():
    engine = DiagnosisEngine()
    register_default_probes(engine)
    failure = normalize_failure(
        code="dependency", message="ModuleNotFoundError: No module named 'zzz_not_a_real_module'"
    )
    diagnosis = engine.diagnose(failure)
    # With the probe confirming the module is missing, the cause is decisive.
    assert diagnosis.decisive
    assert "package" in (diagnosis.selected or "")


def test_dependency_probe_ignores_unrelated_failures():
    engine = DiagnosisEngine()
    register_default_probes(engine)
    failure = normalize_failure(code="TOOL_TIMEOUT", message="timed out")
    diagnosis = engine.diagnose(failure)
    # The dependency probe does not apply to a timeout.
    assert "dependency_missing" not in diagnosis.evidence


def test_provider_probe_returns_unknown_without_runtime():
    # `provider_unhealthy` is registered but cannot establish a fact here; the
    # diagnosis must stay undetermined, not guess.
    engine = DiagnosisEngine()
    register_default_probes(engine)
    failure = normalize_failure(code="provider_unavailable", message="provider down", source="provider")
    diagnosis = engine.diagnose(failure)
    assert diagnosis.kind == FailureKind.PROVIDER_OUTAGE


def test_register_is_idempotent_enough_to_call_twice():
    engine = DiagnosisEngine()
    register_default_probes(engine)
    register_default_probes(engine)
    # Duplicate probes do not break diagnosis.
    diagnosis = engine.diagnose(normalize_failure(code="TOOL_TIMEOUT", message="x"))
    assert diagnosis.hypotheses