"""Evaluation engine — deterministic checks + promotion gates.

Evaluation is multi-dimensional and deterministic-first. An LLM judge is never
the only mechanism and never gates promotion. A skill cannot be promoted if it
fails a mandatory dimension (manifest/schema/permission/safety), regardless of
any soft score.

Dimensions recorded:
    manifest_validation   (mandatory)
    schema_validation     (mandatory)
    dependency_validation (mandatory)
    permission_validation (mandatory)
    tool_availability     (mandatory)
    financial_integrity   (mandatory for finance skills)
    evidence_and_reporting
    regression            (optional cases)

Outcomes: passed | failed | needs_review | blocked.
"""

from __future__ import annotations

import json
from typing import Any, Optional

from .manifest import FORBIDDEN_PERMISSIONS, SkillManifest
from .registry import SkillRegistry
from .runtime import validate_input
from .store import SkillStore

# Dimensions whose failure blocks promotion outright.
MANDATORY_DIMENSIONS = frozenset(
    {
        "manifest_validation",
        "schema_validation",
        "dependency_validation",
        "permission_validation",
        "tool_availability",
        "financial_integrity",
    }
)


def _json_schema_ok(schema: Any) -> tuple[bool, str]:
    if not isinstance(schema, dict):
        return False, "schema is not an object"
    if schema.get("type", "object") != "object":
        return False, "top-level type must be 'object'"
    if "properties" in schema and not isinstance(schema["properties"], dict):
        return False, "properties must be an object"
    return True, "well-formed"


def _financial_integrity(manifest: SkillManifest) -> tuple[bool, str]:
    """A finance-domain skill must declare how it reports figures.

    This is a structural check: the finance skills' output schemas must keep
    reported vs derived distinguishable, and must not permit a silent value
    without evidence. It cannot prove correctness, but it blocks a finance skill
    whose contract cannot express the distinction.
    """
    if manifest.category != "finance":
        return True, "not a finance skill"
    schema = manifest.outputSchema or {}
    props = schema.get("properties") or {}
    has_reported = "reported" in props
    has_derived = "derived" in props
    has_evidence = "evidence" in props
    if has_reported and has_derived and has_evidence:
        return True, "output distinguishes reported/derived and carries evidence"
    missing = [name for name, present in (("reported", has_reported), ("derived", has_derived), ("evidence", has_evidence)) if not present]
    return False, f"finance output schema must declare: {', '.join(missing)}"


def evaluate_skill(
    skill_id: str,
    version: Optional[str],
    registry: SkillRegistry,
    *,
    run_regression: bool = False,
) -> dict[str, Any]:
    """Run the deterministic evaluation for one skill version and persist it."""
    manifest = registry.manifest(skill_id)
    if manifest is None:
        return {"ok": False, "error": "skill not installed"}
    resolved_version = registry.resolve_version(skill_id, version) or manifest.version

    dimensions: list[dict[str, Any]] = []

    # 1. Manifest validation (pydantic already passed at load; re-affirm).
    dimensions.append({"name": "manifest_validation", "status": "passed",
                       "detail": f"manifest is pydantic-valid (hash {manifest.content_hash()})",
                       "mandatory": True})

    # 2. Schema validation.
    input_ok, input_detail = _json_schema_ok(manifest.inputSchema)
    output_ok, output_detail = _json_schema_ok(manifest.outputSchema) if manifest.outputSchema else (True, "no output schema declared")
    schema_passed = input_ok and output_ok
    dimensions.append({"name": "schema_validation", "status": "passed" if schema_passed else "failed",
                       "detail": f"input: {input_detail}; output: {output_detail}", "mandatory": True})

    # 3. Dependency validation.
    deps = registry.resolve_dependencies(skill_id, resolved_version)
    dimensions.append({"name": "dependency_validation", "status": "passed" if deps.ok else "failed",
                       "detail": "; ".join(deps.errors) or "dependencies resolved", "mandatory": True})

    # 4. Permission validation.
    forbidden = [p for p in manifest.permissions if p in FORBIDDEN_PERMISSIONS]
    dimensions.append({"name": "permission_validation", "status": "passed" if not forbidden else "failed",
                       "detail": f"forbidden: {', '.join(forbidden)}" if forbidden else "within the approved set",
                       "mandatory": True})

    # 5. Tool availability.
    tools_ok, tools_detail = registry.check_tools(skill_id, resolved_version)
    dimensions.append({"name": "tool_availability", "status": "passed" if tools_ok else "failed",
                       "detail": tools_detail, "mandatory": True})

    # 6. Financial integrity (finance skills).
    fin_ok, fin_detail = _financial_integrity(manifest)
    dimensions.append({"name": "financial_integrity", "status": "passed" if fin_ok else "failed",
                       "detail": fin_detail, "mandatory": True})

    # 7. Attached test cases (schema cases run deterministically).
    cases = registry.store.list_evaluation_cases(skill_id, resolved_version)
    case_results = _run_cases(manifest, cases)
    case_failures = [c for c in case_results if c["status"] == "failed"]
    dimensions.append({
        "name": "test_cases",
        "status": "passed" if not case_failures else "failed",
        "detail": f"{len(case_results) - len(case_failures)}/{len(case_results)} cases passed" if case_results else "no cases attached",
        "mandatory": False,
    })

    # 8. Evidence & reporting shape.
    evidence_ok, evidence_detail = _evidence_shape(manifest)
    dimensions.append({"name": "evidence_and_reporting", "status": "passed" if evidence_ok else "needs_review",
                       "detail": evidence_detail, "mandatory": False})

    # 9. Regression (opt-in; compares against the prior stored evaluation).
    if run_regression:
        dimensions.append(_regression_dimension(registry.store, skill_id, resolved_version, dimensions))

    mandatory_failed = [
        d for d in dimensions if d.get("mandatory") and d["status"] != "passed"
    ]
    soft_issue = [d for d in dimensions if not d.get("mandatory") and d["status"] in ("failed", "needs_review")]

    if mandatory_failed:
        status = "blocked"
    elif soft_issue:
        status = "needs_review"
    else:
        status = "passed"

    summary = (
        "all mandatory checks passed"
        if status == "passed"
        else f"blocked by: {', '.join(d['name'] for d in mandatory_failed)}"
        if mandatory_failed
        else f"needs review: {', '.join(d['name'] for d in soft_issue)}"
    )

    # The skill's deterministic cases are stored once (library-declared, no
    # evaluation id); the evaluation records their RESULT via `dimensions`, so
    # they are not duplicated per evaluation run.
    evaluation_id = registry.store.save_evaluation(
        skill_id=skill_id,
        version=resolved_version,
        status=status,
        dimensions=dimensions,
        summary=summary,
        cases=None,
    )
    registry.store.append_event("skill.evaluation_completed", skill_id=skill_id, version=resolved_version,
                                data={"evaluationId": evaluation_id, "status": status})

    return {
        "ok": True,
        "evaluationId": evaluation_id,
        "skillId": skill_id,
        "version": resolved_version,
        "status": status,
        "summary": summary,
        "dimensions": dimensions,
        "cases": case_results,
    }


def _run_cases(manifest: SkillManifest, cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for case in cases:
        kind = case.get("kind", "schema")
        if kind in ("schema", "input_validation"):
            payload = case.get("input") or {}
            expect_valid = True
            expected = case.get("expected")
            if isinstance(expected, dict) and "valid" in expected:
                expect_valid = bool(expected["valid"])
            ok, issues = validate_input(manifest.inputSchema, payload, manifest.id)
            status = "passed" if ok == expect_valid else "failed"
            results.append({
                "caseId": case["caseId"], "kind": kind, "status": status,
                "expected": expect_valid, "actual": ok, "error": None if status == "passed" else "; ".join(issues),
            })
        elif kind == "output_shape":
            expected = case.get("expected") or {}
            required = expected.get("required") or (manifest.outputSchema or {}).get("required") or []
            # Structural check only: the schema declares the fields.
            props = (manifest.outputSchema or {}).get("properties") or {}
            missing = [key for key in required if key not in props]
            results.append({
                "caseId": case["caseId"], "kind": kind, "status": "passed" if not missing else "failed",
                "expected": required, "actual": list(props.keys()),
                "error": f"output schema missing {missing}" if missing else None,
            })
        else:
            results.append({
                "caseId": case["caseId"], "kind": kind, "status": "needs_review",
                "expected": case.get("expected"), "actual": None,
                "error": "case kind is not deterministically checkable; needs a runtime case",
            })
    return results


_EVIDENCE_FIELD_NAMES = frozenset(
    {
        "evidence", "references", "sourceReferences", "sources", "citations",
        "verified", "unverified", "conflicts", "missingEvidence",
    }
)


def _evidence_shape(manifest: SkillManifest) -> tuple[bool, str]:
    """A findings-producing skill should be able to carry evidence references.

    A finance or quality skill MUST have a place to put evidence. A research
    skill is checked too — but a planning skill legitimately produces a plan with
    no evidence (it contains no measured facts). It is only flagged when its
    output looks like it reports findings but cannot attribute them.
    """
    if manifest.category not in ("research", "finance", "quality"):
        return True, "not an evidence-bearing skill"
    schema = manifest.outputSchema or {}
    props = schema.get("properties") or {}
    if _EVIDENCE_FIELD_NAMES & set(props):
        return True, "output can carry evidence references"
    if manifest.category == "research":
        # Plans and frameworks have no evidence to attribute; accept unless the
        # schema declares a findings-shaped field.
        findings_fields = {"findings", "claims", "results", "reported", "facts"}
        if not (findings_fields & set(props)):
            return True, "research output is plan-like and carries no measured facts"
    return False, "output schema has no evidence/references field"


def _regression_dimension(
    store: SkillStore, skill_id: str, version: str, current: list[dict[str, Any]]
) -> dict[str, Any]:
    """Compare the current dimensions against the most recent prior evaluation
    for the same skill. A newly-failed mandatory dimension is a regression."""
    prior = store.list_evaluations(skill_id, limit=5)
    prior = [e for e in prior if e["version"] == version]
    if not prior:
        return {"name": "regression", "status": "needs_review",
                "detail": "no prior evaluation to compare against", "mandatory": False}
    previous = prior[0]["dimensions"]
    prev_by_name = {d["name"]: d["status"] for d in previous}
    regressions = [
        f"{d['name']}: {prev_by_name.get(d['name'], 'n/a')} -> {d['status']}"
        for d in current
        if prev_by_name.get(d["name"]) == "passed" and d["status"] != "passed"
    ]
    if regressions:
        return {"name": "regression", "status": "failed",
                "detail": "; ".join(regressions), "mandatory": False}
    return {"name": "regression", "status": "passed", "detail": "no regressions vs the prior evaluation",
            "mandatory": False}


def promotion_gate(
    evaluation: dict[str, Any],
    *,
    allow_needs_review: bool = False,
) -> dict[str, Any]:
    """Decide whether an evaluation clears the promotion gate.

    A `blocked` evaluation never promotes. A `needs_review` evaluation promotes
    only when the operator explicitly allows soft issues.
    """
    status = evaluation.get("status")
    if status == "passed":
        return {"passed": True, "reason": "all mandatory checks passed"}
    if status == "blocked":
        blocked = [d["name"] for d in evaluation.get("dimensions", []) if d.get("mandatory") and d["status"] != "passed"]
        return {"passed": False, "reason": f"blocked by mandatory checks: {', '.join(blocked)}"}
    if status == "needs_review":
        if allow_needs_review:
            return {"passed": True, "reason": "soft issues accepted explicitly"}
        return {"passed": False, "reason": "evaluation needs review and was not explicitly accepted"}
    return {"passed": False, "reason": f"unknown evaluation status {status!r}"}


__all__ = ["MANDATORY_DIMENSIONS", "evaluate_skill", "promotion_gate"]
