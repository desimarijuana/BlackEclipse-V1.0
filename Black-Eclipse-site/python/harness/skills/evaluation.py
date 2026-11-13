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

import hashlib
import json
from typing import Any, Optional

from .manifest import FORBIDDEN_PERMISSIONS, SkillManifest
from .registry import SkillRegistry
from .runtime import validate_input
from .schema_validation import check_schema as _check_json_schema
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

# W5.1: the behavioural gate applies to skills the system authored or learned.
# A bundled skill is already trusted and enabled; forcing it to re-execute on
# every upgrade would break zero-config and is not what "learned skill" means.
_EXECUTION_GATED_ORIGINS = frozenset({"learning"})


def execution_gate_applies(manifest: SkillManifest) -> bool:
    """Whether this skill version must prove behaviour before it can enable."""
    return (
        str(manifest.id or "").startswith("learned.")
        or str(manifest.origin or "") in _EXECUTION_GATED_ORIGINS
        or "curated" in {str(tag).lower() for tag in manifest.tags}
    )


def _json_schema_ok(schema: Any) -> tuple[bool, str]:
    if not isinstance(schema, dict):
        return False, "schema is not an object"
    if schema.get("type", "object") != "object":
        return False, "top-level type must be 'object'"
    if "properties" in schema and not isinstance(schema["properties"], dict):
        return False, "properties must be an object"
    ok, errors = _check_json_schema(schema)
    if not ok:
        return False, f"not a valid JSON Schema: {'; '.join(errors)}"
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


OUTCOME_METRICS = (
    "taskSuccess",
    "retrievalHitRate",
    "citationCoverage",
    "unsupportedClaimRate",
    "costUsd",
)
_HIGHER_IS_BETTER = frozenset(
    {"taskSuccess", "retrievalHitRate", "citationCoverage"}
)
_METRIC_TOLERANCE = 0.01


def _metric_deltas(
    metrics: dict[str, Any], base_metrics: dict[str, Any]
) -> tuple[list[dict[str, Any]], list[str], bool]:
    """Compare a candidate's outcome metrics with its base.

    Returns (deltas, regressions, distinguishable). Metrics are caller-supplied
    measurements; a missing metric is a gap, never a fabricated zero.
    """
    deltas: list[dict[str, Any]] = []
    regressions: list[str] = []
    for name in OUTCOME_METRICS:
        if metrics.get(name) is None or base_metrics.get(name) is None:
            continue
        try:
            candidate = float(metrics[name])
            base = float(base_metrics[name])
        except (TypeError, ValueError):
            continue
        delta = candidate - base
        higher = name in _HIGHER_IS_BETTER
        if higher and delta < -_METRIC_TOLERANCE:
            regressions.append(f"{name} fell {abs(delta):.4f}")
        if not higher and delta > _METRIC_TOLERANCE:
            regressions.append(f"{name} rose {abs(delta):.4f}")
        deltas.append({
            "metric": name, "base": base, "candidate": candidate,
            "delta": round(delta, 6), "higherIsBetter": higher,
        })
    distinguishable = any(abs(item["delta"]) > _METRIC_TOLERANCE for item in deltas)
    return deltas, regressions, distinguishable


def _discrimination_dimension(
    store: SkillStore,
    skill_id: str,
    version: str,
    *,
    base_version: Optional[str],
    metrics: Optional[dict[str, Any]],
    base_metrics: Optional[dict[str, Any]],
    prior_evaluations: list[dict[str, Any]],
) -> dict[str, Any]:
    """Prove the candidate differs from a named base on outcome metrics.

    Same version + identical results repeated does not prove improvement: it is
    a broken harness signal and is reported as such.
    """
    resolved_base = base_version
    if not resolved_base:
        try:
            stored = store.get_version(skill_id, version)
            resolved_base = (stored or {}).get("baseVersion")
        except Exception:  # noqa: BLE001
            resolved_base = None

    same_version = [e for e in prior_evaluations if e["version"] == version]
    if len(same_version) >= 3 and all(e.get("status") == "passed" for e in same_version):
        return {
            "name": "discrimination", "status": "needs_review", "mandatory": False,
            "detail": (
                f"{len(same_version)} identical passing evaluations of {version}; "
                "the harness is not producing a signal"
            ),
        }

    if not resolved_base:
        return {
            "name": "discrimination", "status": "not_applicable", "mandatory": False,
            "detail": "root version: no base version to compare against",
        }

    if not metrics and not base_metrics:
        return {
            "name": "discrimination", "status": "needs_review", "mandatory": False,
            "blocking": False,
            "detail": (
                f"base {resolved_base} is named but no outcome metrics were "
                f"supplied ({', '.join(OUTCOME_METRICS)}); discrimination is an "
                "explicit gap, not a pass"
            ),
        }
    if not metrics or not base_metrics:
        return {
            "name": "discrimination", "status": "needs_review", "mandatory": False,
            "blocking": False,
            "detail": (
                f"base {resolved_base} is named but outcome metrics are missing on "
                "one side; cannot distinguish candidate from base"
            ),
        }

    deltas, regressions, distinguishable = _metric_deltas(metrics, base_metrics)
    if not deltas:
        return {
            "name": "discrimination", "status": "needs_review", "mandatory": False,
            "blocking": False,
            "detail": (
                "no comparable outcome metric was supplied for both candidate and base"
            ),
        }
    if regressions:
        return {
            "name": "discrimination", "status": "failed", "mandatory": True,
            "detail": f"vs {resolved_base}: " + "; ".join(regressions),
            "metrics": deltas,
        }
    if not distinguishable:
        return {
            "name": "discrimination", "status": "failed", "mandatory": True,
            "detail": (
                f"vs {resolved_base}: every outcome metric is within "
                f"{_METRIC_TOLERANCE}; the candidate cannot be distinguished from "
                "its base"
            ),
            "metrics": deltas,
        }
    return {
        "name": "discrimination", "status": "passed", "mandatory": False,
        "detail": f"vs {resolved_base}: outcome metrics differ measurably",
        "metrics": deltas,
    }


EVALUATOR_VERSION = "deterministic-v1"


def evaluation_fingerprint(
    manifest: SkillManifest, registry: SkillRegistry, version: str,
) -> str:
    """What a passing evaluation was measured against.

    A change in the version, manifest (including instructions), evaluator, or
    registered tool set requires a new evaluation. Nothing else does.
    """
    try:
        tools = sorted(str(name) for name in registry.names())
    except Exception:  # noqa: BLE001 - an unreadable registry changes the input
        tools = ["<registry-unavailable>"]
    payload = json.dumps(
        {
            "version": version,
            "manifest": manifest.content_hash(),
            "evaluator": EVALUATOR_VERSION,
            "tools": tools,
        },
        sort_keys=True, separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]


def evaluate_skill(
    skill_id: str,
    version: Optional[str],
    registry: SkillRegistry,
    *,
    run_regression: bool = False,
    base_version: Optional[str] = None,
    metrics: Optional[dict[str, Any]] = None,
    base_metrics: Optional[dict[str, Any]] = None,
    require_execution: Optional[bool] = None,
    execution_invoker: Optional[Any] = None,
) -> dict[str, Any]:
    """Run the deterministic evaluation for one skill version and persist it."""
    manifest = registry.manifest(skill_id)
    if manifest is None:
        return {"ok": False, "error": "skill not installed"}
    resolved_version = registry.resolve_version(skill_id, version) or manifest.version

    # When an explicit version differs from the in-memory manifest, evaluate THAT
    # version's stored manifest — not the latest in-memory one. Otherwise a
    # cross-version regression check would silently evaluate the wrong revision.
    # (When the requested version matches the in-memory manifest, the in-memory
    # one is authoritative, preserving in-place edits used by evaluation tests.)
    if version and version != manifest.version:
        stored_version = registry.store.get_version(skill_id, version)
        if stored_version:
            try:
                manifest = SkillManifest(**stored_version["manifest"])
            except Exception:  # noqa: BLE001 - fall back to the in-memory manifest
                pass

    fingerprint = evaluation_fingerprint(manifest, registry, resolved_version)
    stored_version = registry.store.get_version(skill_id, resolved_version) or {}
    execution_required = bool(require_execution) and execution_gate_applies(manifest)
    execution_cached = True
    if execution_required:
        # A static-only pass must never be "held" as if behaviour had run. The
        # cache key includes execution evidence: same fingerprint AND a stored
        # execution record for that fingerprint.
        try:
            prior = registry.store.list_evaluations(skill_id, limit=5)
        except Exception:  # noqa: BLE001
            prior = []
        execution_cached = any(
            str(row.get("version")) == str(resolved_version)
            and str(row.get("status")) == "passed"
            and row.get("executionFingerprint") == fingerprint
            and row.get("executionRunIds")
            for row in prior
        )
    if (
        # An explicit regression re-check must actually re-run: the whole point
        # is to compare against the declared base again, not to return a held
        # record with no dimensions.
        not run_regression
        and stored_version.get("evaluationStatus") == "passed"
        and stored_version.get("evalFingerprint") == fingerprint
        and execution_cached
    ):
        # An unchanged passed version is held. No row is appended and the
        # previous evaluation is not superseded.
        return {
            "ok": True, "skipped": True, "reason": "unchanged_passed",
            "skillId": skill_id, "version": resolved_version,
            "status": "passed", "summary": "unchanged passed version",
            "dimensions": [], "cases": [], "fingerprint": fingerprint,
        }

    # A failed / needs-review execution attempt is held for a bounded backoff.
    # Without this, every boot re-ran the same real-model cases for the same
    # unchanged draft (cost + latency) even though nothing had changed. A
    # manifest change changes the fingerprint and re-runs immediately.
    if execution_required and not execution_cached and not run_regression and prior:
        from ..config.flags import get_int  # noqa: PLC0415

        latest = prior[0]
        same_attempt = (
            str(latest.get("version")) == str(resolved_version)
            and latest.get("executionFingerprint") == fingerprint
            and str(latest.get("status")) in ("failed", "needs_review")
        )
        retry_hours = get_int("HARNESS_SKILL_EVAL_RETRY_HOURS")
        if same_attempt and retry_hours > 0 and _evaluation_age_hours(latest.get("createdAt")) < retry_hours:
            return {
                "ok": True, "skipped": True, "reason": "execution_retry_backoff",
                "skillId": skill_id, "version": resolved_version,
                "status": latest.get("status"),
                "summary": f"execution retry held for {retry_hours}h after an unchanged attempt",
                "dimensions": latest.get("dimensions") or [],
                "cases": [], "fingerprint": fingerprint,
                "evaluationId": latest.get("id"),
                "execution": None,
            }

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
    from .execution_eval import EXECUTION_KINDS  # noqa: PLC0415

    deterministic_cases = [
        case for case in cases
        if str(case.get("kind") or "") not in EXECUTION_KINDS
    ]
    case_results = _run_cases(manifest, deterministic_cases)
    case_failures = [c for c in case_results if c["status"] == "failed"]
    dimensions.append({
        "name": "test_cases",
        "status": "passed" if not case_failures else "failed",
        "detail": f"{len(case_results) - len(case_failures)}/{len(case_results)} cases passed" if case_results else "no cases attached",
        "mandatory": False,
    })

    # 7b. Behavioural execution tier (W5.1). Opt-in per caller: the production
    # promotion/enable paths pass the flag, while a direct static evaluation keeps
    # its historical shape. Absence of execution cases is `needs_review`, never a
    # pass; absence of a runner is honest, never simulated.
    execution_needed = execution_required
    execution_result = None
    if execution_needed:
        from .execution_eval import EXECUTION_KINDS, evaluate_skill_execution  # noqa: PLC0415

        # A draft is inert and therefore not executable. `testing` is the
        # existing evaluation state: executable only in non-interactive modes,
        # never enabled, never selectable for a live user turn.
        stored_status = str((registry.store.get_version(skill_id, resolved_version) or {}).get("status") or "")
        if stored_status in ("draft", "evaluating", "review"):
            registry.store.set_version_status(skill_id, resolved_version, "testing")
        execution_cases = [
            case for case in cases
            if str(case.get("kind") or "") in EXECUTION_KINDS
        ]
        execution_result = evaluate_skill_execution(
            manifest, execution_cases,
            invoker=execution_invoker, fingerprint=fingerprint,
        )
        execution_status = execution_result.status
        dimensions.append({
            "name": "execution_eval",
            "status": execution_status,
            "detail": execution_result.reason,
            "mandatory": False,
            "blocking": True,
            "executionRunIds": list(execution_result.runIds),
            "graderScores": dict(execution_result.graderScores),
        })

    # 8. Evidence & reporting shape.
    evidence_ok, evidence_detail = _evidence_shape(manifest)
    dimensions.append({"name": "evidence_and_reporting", "status": "passed" if evidence_ok else "needs_review",
                       "detail": evidence_detail, "mandatory": False})

    # 9. Regression (opt-in; compares against the prior stored evaluation).
    if run_regression:
        dimensions.append(_regression_dimension(registry.store, skill_id, resolved_version, dimensions))

    # 10. Discrimination: a version must be distinguishable from its named base
    # on outcome metrics. Same-version identical passes are a harness defect.
    try:
        prior_evaluations = [
            e for e in registry.store.list_evaluations(skill_id, limit=50)
            if str(e.get("status")) != "superseded"
        ]
    except Exception:  # noqa: BLE001
        prior_evaluations = []
    dimensions.append(_discrimination_dimension(
        registry.store, skill_id, resolved_version,
        base_version=base_version, metrics=metrics, base_metrics=base_metrics,
        prior_evaluations=prior_evaluations,
    ))

    mandatory_failed = [
        d for d in dimensions if d.get("mandatory") and d["status"] != "passed"
    ]
    soft_issue = [
        d for d in dimensions
        if not d.get("mandatory")
        and d.get("blocking", True)
        and d["status"] in ("failed", "needs_review")
    ]

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
        fingerprint=fingerprint,
        execution_run_ids=list(execution_result.runIds) if execution_result else None,
        execution_scores=dict(execution_result.graderScores) if execution_result else None,
        execution_fingerprint=(
            execution_result.fingerprint if execution_result else None
        ),
    )
    try:
        registry.store.supersede_evaluations(
            skill_id, resolved_version, evaluation_id,
        )
    except Exception:  # noqa: BLE001 - history bookkeeping never fails an evaluation
        pass
    registry.store.append_event("skill.evaluation_completed", skill_id=skill_id, version=resolved_version,
                                data={"evaluationId": evaluation_id, "status": status})
    # W8: a durable SkillEvent row is not visible to the observability projector,
    # so publish the same outcome through the bridge.
    try:
        from ..observability.bridge import publish  # noqa: PLC0415

        publish("skill.evaluation_completed", {
            "status": status,
            "ok": bool(execution_result.ok) if execution_result is not None else status == "passed",
            "cases": len(cases or []),
            "executionCases": len(execution_cases) if execution_result is not None else 0,
            "executionStatus": execution_result.status if execution_result is not None else None,
        })
    except Exception:  # noqa: BLE001 - telemetry must not fail an evaluation
        pass

    return {
        "ok": True,
        "evaluationId": evaluation_id,
        "skillId": skill_id,
        "version": resolved_version,
        "status": status,
        "summary": summary,
        "dimensions": dimensions,
        "cases": case_results,
        "fingerprint": fingerprint,
        "execution": execution_result.to_dict() if execution_result else None,
    }


def retire_non_discriminating(
    store: Any, skill_id: str, version: str, result: dict[str, Any],
) -> bool:
    """Deprecate a skill whose discrimination test failed (never delete it)."""
    failed = any(
        str(d.get("name")) == "discrimination" and str(d.get("status")) == "failed"
        for d in (result.get("dimensions") or [])
        if isinstance(d, dict)
    )
    if not failed:
        return False
    store.set_version_status(skill_id, version, "deprecated")
    record = store.get_skill(skill_id)
    if record:
        store.upsert_skill(
            skill_id=skill_id, name=record.get("name") or skill_id,
            description=record.get("description") or "",
            category=record.get("category") or "quality",
            latest_version=version, status="deprecated",
            tags=list(record.get("tags") or []),
        )
    store.append_event(
        "skill.retired_no_discrimination", skill_id=skill_id,
        version=version,
    )
    return True


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
        elif kind == "output_validation":
            # A case carrying a concrete output instance, validated against the
            # FULL declared output schema (nested types/arrays/enums/bounds). The
            # instance is `expected.output` (or `expected.instance`); `expected.valid`
            # states whether it should conform.
            from .schema_validation import validate_output  # noqa: PLC0415

            expected = case.get("expected") if isinstance(case.get("expected"), dict) else {}
            instance = expected.get("output", expected.get("instance"))
            expect_valid = bool(expected.get("valid", True))
            if manifest.outputSchema:
                ok, errors = validate_output(manifest.outputSchema, instance)
            else:
                ok, errors = False, ["no output schema declared"]
            status = "passed" if ok == expect_valid else "failed"
            results.append({
                "caseId": case["caseId"], "kind": kind, "status": status,
                "expected": expect_valid, "actual": ok,
                "error": None if status == "passed" else "; ".join(errors),
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
    if manifest.category == "quality" and {"limitations", "missingData"} <= set(props):
        # A procedure skill reports what it did, what it could not do, and the
        # source calls it used. The recovery evidence is in the procedure; the
        # output still has an honest place for limitations and missing data.
        return True, "quality output can report limitations and missing data"
    return False, "output schema has no evidence/references field"


def _evaluation_age_hours(stamp: Any) -> float:
    """Age of a stored evaluation timestamp, in hours (∞ when unparseable)."""
    import datetime  # noqa: PLC0415

    if not stamp:
        return float("inf")
    try:
        parsed = datetime.datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return float("inf")
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=datetime.timezone.utc)
    return max(
        0.0,
        (datetime.datetime.now(datetime.timezone.utc) - parsed).total_seconds() / 3600.0,
    )


def _version_key(version: Any) -> tuple[int, ...]:
    import re  # noqa: PLC0415

    parts = re.findall(r"\d+", str(version or ""))
    return tuple(int(part) for part in parts[:3]) or (0,)


def _regression_dimension(
    store: SkillStore, skill_id: str, version: str, current: list[dict[str, Any]]
) -> dict[str, Any]:
    """Compare the current dimensions against the most meaningful prior record.

    Priority: the version's DECLARED base (when that base has an evaluation) →
    an earlier evaluation of the SAME version → the most recent evaluation of any
    prior version. The declared base is what lineage is for; a same-version record
    is only the fallback (or the only record for a root version). Re-evaluating a
    version whose base was evaluated therefore compares against the base, not
    against itself. A newly-failed mandatory dimension is a regression. Never
    raises.
    """
    prior_all = [
        e for e in store.list_evaluations(skill_id, limit=50)
        if str(e.get("status")) != "superseded"
    ]
    compared_against = version
    comparison = None
    base_version = None
    try:
        stored = store.get_version(skill_id, version)
        base_version = (stored or {}).get("baseVersion")
    except Exception:  # noqa: BLE001 - lineage lookup must not break evaluation
        base_version = None
    if base_version and _version_key(base_version) < _version_key(version):
        base_evals = [e for e in prior_all if e["version"] == base_version]
        if base_evals:
            comparison = base_evals[0]
            compared_against = base_version
    if comparison is None:
        same_version = [e for e in prior_all if e["version"] == version]
        if same_version:
            return {
                "name": "regression", "status": "needs_review",
                "mandatory": False,
                "detail": (
                    f"same-version re-evaluation of {version}; no independent "
                    "baseline, so this cannot detect a regression"
                ),
            }
    if comparison is None:
        # Never compare a version with a LATER one: an earlier evaluation is the
        # only meaningful baseline (a 1.1.0 result cannot be regressed against
        # 1.1.1). Pick the closest earlier version.
        prior_versions = [
            e for e in prior_all
            if e["version"] != version
            and _version_key(e["version"]) < _version_key(version)
        ]
        if prior_versions:
            prior_versions.sort(key=lambda e: _version_key(e["version"]), reverse=True)
            comparison = prior_versions[0]
            compared_against = comparison["version"]
    if comparison is None:
        return {"name": "regression", "status": "needs_review",
                "detail": "no prior evaluation to compare against", "mandatory": False}
    previous = comparison["dimensions"]
    prev_by_name = {d["name"]: d["status"] for d in previous}
    regressions = [
        f"{d['name']}: {prev_by_name.get(d['name'], 'n/a')} -> {d['status']}"
        for d in current
        if prev_by_name.get(d["name"]) == "passed" and d["status"] != "passed"
    ]
    if regressions:
        return {"name": "regression", "status": "failed",
                "detail": f"vs {compared_against}: " + "; ".join(regressions), "mandatory": True}
    return {
        "name": "regression", "status": "passed",
        "detail": f"no regressions vs {compared_against}",
        "mandatory": False,
    }


def promotion_gate(
    evaluation: dict[str, Any],
    *,
    allow_needs_review: bool = False,
    require_execution: bool = False,
    store: Optional[Any] = None,
) -> dict[str, Any]:
    """Decide whether an evaluation clears the promotion gate.

    A `blocked` evaluation never promotes. A `needs_review` evaluation promotes
    only when the operator explicitly allows soft issues.

    When ``require_execution`` is on, a static-only evaluation is not enough:
    the record must carry execution run ids, and (when a ``store`` is supplied)
    those executions must exist for the same skill/version. This is the W5.1
    gate; it can never be satisfied by a schema-only pass.
    """
    if require_execution:
        run_ids = list(evaluation.get("executionRunIds") or [])
        if not run_ids:
            return {
                "passed": False,
                "reason": "execution evaluation required: no execution run ids on this evaluation",
            }
        if store is not None:
            try:
                executions = store.list_executions(
                    evaluation.get("skillId"), limit=500,
                )
            except Exception:  # noqa: BLE001 - store lookup failure is not a pass
                executions = []
            existing = {str(row.get("runId")) for row in executions}
            missing = [str(run_id) for run_id in run_ids if str(run_id) not in existing]
            if missing:
                return {
                    "passed": False,
                    "reason": f"execution evaluation required: run ids do not exist ({', '.join(missing)})",
                }
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


__all__ = [
    "MANDATORY_DIMENSIONS",
    "evaluate_skill",
    "execution_gate_applies",
    "promotion_gate",
]
