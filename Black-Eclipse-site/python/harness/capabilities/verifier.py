"""Static and sandbox verification for a generated capability.

The sandbox is the existing analysis runner: generated code never executes inside
the harness process, never gets a network-capable import, and never reaches the
workspace filesystem. A capability without a passing contract test stays
``unverified`` and cannot activate.
"""

from __future__ import annotations

import ast
import hashlib
from dataclasses import dataclass, field
from typing import Any

from ..code.execution import (
    AnalysisInput,
    AnalysisRequest,
    MAX_SOURCE_CHARS,
    check_imports,
    run_analysis,
)
from .manifest import CORE_WRITE_DENY, CapabilityManifest

_PATH_FRAGMENTS = ("../", "..\\", "/etc/", "\\windows\\", "~/", "file://")


@dataclass
class VerificationCheck:
    name: str
    ok: bool
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "ok": self.ok, "detail": self.detail}


@dataclass
class VerificationReport:
    status: str
    checks: list[VerificationCheck] = field(default_factory=list)
    source_digest: str = ""
    test_digest: str = ""
    outputs: dict[str, Any] = field(default_factory=dict)
    stderr: str = ""
    duration_ms: int = 0

    @property
    def ok(self) -> bool:
        return self.status == "verified"

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "ok": self.ok,
            "checks": [check.to_dict() for check in self.checks],
            "sourceDigest": self.source_digest,
            "testDigest": self.test_digest,
            "outputs": self.outputs,
            "stderr": self.stderr,
            "durationMs": self.duration_ms,
        }


def digest_text(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def _literal_violations(source: str) -> list[str]:
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return [f"source is not valid Python: {exc}"]
    found: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
            continue
        value = node.value
        for fragment in _PATH_FRAGMENTS:
            if fragment in value and fragment not in found:
                found.append(fragment)
        for denied in CORE_WRITE_DENY:
            if denied in value and denied not in found:
                found.append(denied)
    return found


def _has_assertions(source: str) -> bool:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return False
    for node in ast.walk(tree):
        if isinstance(node, ast.Assert):
            return True
        if isinstance(node, ast.Raise):
            return True
        if isinstance(node, ast.Call):
            name = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
            if name in ("assert_equal", "fail", "check"):
                return True
    return False


def _output_type_ok(kind: str, value: Any) -> bool:
    if kind == "series":
        return isinstance(value, list)
    if kind == "table":
        return isinstance(value, list) and all(isinstance(row, dict) for row in value)
    if kind == "scalar":
        return isinstance(value, (int, float, str, bool)) and not isinstance(value, complex)
    if kind == "text":
        return isinstance(value, str)
    return False


def verify(
    manifest: CapabilityManifest,
    source: str,
    test_source: str,
    sample_inputs: dict[str, Any],
    *,
    timeout_s: int = 120,
) -> VerificationReport:
    checks: list[VerificationCheck] = []
    source_digest = digest_text(source)
    test_digest = digest_text(test_source)

    policy = manifest.source_policy_violations()
    checks.append(VerificationCheck(
        "manifest-policy", not policy,
        "; ".join(policy) if policy else "manifest is within the capability policy",
    ))

    checks.append(VerificationCheck(
        "source-present", bool(source.strip()),
        "implementation source is present" if source.strip() else "implementation source is missing",
    ))
    if not source.strip():
        return VerificationReport("failed", checks, source_digest, test_digest)

    offenders = check_imports(source)
    checks.append(VerificationCheck(
        "source-imports", not offenders,
        "no disallowed import or reflection" if not offenders else ", ".join(offenders),
    ))
    literals = _literal_violations(source)
    checks.append(VerificationCheck(
        "source-paths", not literals,
        "no traversal or protected-path literal" if not literals else ", ".join(literals),
    ))

    if not test_source.strip():
        checks.append(VerificationCheck(
            "contract-test", False, "a contract test is required before activation",
        ))
        return VerificationReport("unverified", checks, source_digest, test_digest)

    test_offenders = check_imports(test_source)
    checks.append(VerificationCheck(
        "test-imports", not test_offenders,
        "test imports are permitted" if not test_offenders else ", ".join(test_offenders),
    ))
    checks.append(VerificationCheck(
        "test-assertions", _has_assertions(test_source),
        "the contract test asserts an outcome" if _has_assertions(test_source) else "the contract test has no assertion",
    ))
    failed_static = [check for check in checks if not check.ok]
    if failed_static:
        return VerificationReport("failed", checks, source_digest, test_digest)

    inputs: list[AnalysisInput] = []
    missing_samples: list[str] = []
    for port in manifest.inputs:
        value = sample_inputs.get(port.name)
        if value is None:
            if port.required:
                missing_samples.append(port.name)
            continue
        inputs.append(AnalysisInput(name=port.name, kind=port.kind, value=value))
    checks.append(VerificationCheck(
        "sample-inputs", not missing_samples,
        "every required input has a sample" if not missing_samples else "missing samples: " + ", ".join(missing_samples),
    ))
    if missing_samples:
        return VerificationReport("failed", checks, source_digest, test_digest)

    combined = source.rstrip() + "\n\n" + test_source.lstrip()
    checks.append(VerificationCheck(
        "source-size", len(combined) <= MAX_SOURCE_CHARS,
        f"{len(combined)} characters" if len(combined) <= MAX_SOURCE_CHARS
        else f"contract run is {len(combined)} characters; the limit is {MAX_SOURCE_CHARS}",
    ))
    if len(combined) > MAX_SOURCE_CHARS:
        return VerificationReport("failed", checks, source_digest, test_digest)

    result = run_analysis(AnalysisRequest(
        source=combined,
        inputs=inputs,
        purpose=f"Contract test: {manifest.title}"[:300],
        timeout_s=max(1, min(int(timeout_s), 600)),
    ))
    checks.append(VerificationCheck(
        "sandbox-run", result.status == "ok",
        f"contract run {result.status}" + (f": {result.code}" if result.code else ""),
    ))
    if result.status != "ok":
        return VerificationReport(
            "failed", checks, source_digest, test_digest,
            outputs=dict(result.outputs or {}), stderr=result.stderr,
            duration_ms=result.duration_ms,
        )

    missing_outputs = [
        port.name for port in manifest.outputs
        if port.name not in (result.outputs or {})
    ]
    wrong_outputs = [
        port.name for port in manifest.outputs
        if port.name in (result.outputs or {})
        and not _output_type_ok(port.kind, (result.outputs or {}).get(port.name))
    ]
    contract_detail = "declared outputs are present with the declared kinds"
    if missing_outputs or wrong_outputs:
        # Name the exact disagreement so one build fixes it: a bare list of names
        # made "declared series but returned a str" indistinguishable from
        # "missing", and the agent re-declared the same wrong kinds.
        kinds = {port.name: port.kind for port in manifest.outputs}
        problems = [f"{name} (missing)" for name in missing_outputs]
        problems.extend(
            f"{name} (expected {kinds.get(name)}, got "
            f"{type((result.outputs or {}).get(name)).__name__})"
            for name in wrong_outputs
        )
        contract_detail = "outputs do not match the declaration: " + ", ".join(problems)
    checks.append(VerificationCheck(
        "output-contract", not missing_outputs and not wrong_outputs,
        contract_detail,
    ))
    if missing_outputs or wrong_outputs:
        return VerificationReport(
            "failed", checks, source_digest, test_digest,
            outputs=dict(result.outputs or {}), stderr=result.stderr,
            duration_ms=result.duration_ms,
        )

    return VerificationReport(
        "verified", checks, source_digest, test_digest,
        outputs=dict(result.outputs or {}), duration_ms=result.duration_ms,
    )


__all__ = ["VerificationCheck", "VerificationReport", "digest_text", "verify"]
