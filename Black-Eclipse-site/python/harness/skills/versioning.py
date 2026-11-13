"""Versioned skill activation: propose → evaluate → canary → active, and rollback.

This is the lifecycle half of Milestone 2. `patches.py` does the pure
transformation/validation; this module owns the state transitions, the
evaluation record, canary routing, and automatic rollback. All transitions go
through the EXISTING store and registry — there is no second skill registry.

Invariants:

  * proposing a patch creates a NEW version in status `draft`/`evaluating`;
    the active version is never modified;
  * activation (`active`/`enabled`) requires a passing evaluation;
  * canary is allowed ONLY for safe, non-mutating skills and can always be
    rolled back;
  * rollback is atomic: re-point latest, mark the failed version `rolled_back`,
    restore the prior version's active status, and link them.
"""

from __future__ import annotations

import json
from typing import Any, Optional

from ..eclipse_memory.skill_quality import compare_versions
from .patches import (
    Patch,
    PatchError,
    apply_patch_to_manifest,
    canary_eligible,
    parse_patch,
    version_conflict,
)
from .permissions import Actor
from .manifest import SkillManifest
from .registry import SkillRegistry


def _json(value: Any) -> str:
    return json.dumps(value, default=str)


# ── Propose (create a new version from a patch) ─────────────────────────────


def propose_patch(
    registry: SkillRegistry,
    payload: dict[str, Any],
    *,
    actor: Actor,
    source_run_id: Optional[str] = None,
    review_id: Optional[str] = None,
) -> dict[str, Any]:
    """Validate + apply a structured patch, creating a NEW inert version.

    The result is always `status: draft` (evaluation is a separate step). The
    active version is untouched. Raises nothing to the caller's run path: a bad
    patch returns `{ok: False, error}`.
    """
    try:
        patch = parse_patch(payload)
    except PatchError as exc:
        return {"ok": False, "error": str(exc), "stage": "parse"}

    conflict = version_conflict(registry.store, patch)
    if conflict:
        return {"ok": False, "error": conflict, "stage": "conflict", "stale": True}

    base_version = registry.store.get_version(patch.skill, patch.base_version)
    if base_version is None:
        return {"ok": False, "error": "base version missing", "stage": "base"}
    base_manifest = base_version["manifest"]
    base_status = base_manifest.get("status", "draft")
    if base_status not in ("enabled", "active"):
        return {
            "ok": False,
            "error": f"only an active skill can be patched (base is {base_status!r})",
            "stage": "status",
        }

    try:
        applied = apply_patch_to_manifest(base_manifest, patch)
    except PatchError as exc:
        return {"ok": False, "error": str(exc), "stage": "apply"}
    if not applied.ok or applied.manifest is None:
        return {"ok": False, "error": applied.reason or "patch failed", "stage": "apply"}

    # A patch always produces a NEW minor version; the base is never mutated.
    from .authoring import next_version  # noqa: PLC0415

    new_manifest = applied.manifest
    new_manifest["version"] = next_version(patch.base_version)
    new_manifest["status"] = "draft"
    new_manifest["evaluationStatus"] = "not_evaluated"
    new_manifest["origin"] = base_manifest.get("origin", "builtin")
    new_manifest["sourceRunId"] = source_run_id or new_manifest.get("sourceRunId")

    try:
        SkillManifest(**new_manifest)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"patched manifest invalid: {exc}", "stage": "validate"}

    instructions = patch_preserved_instructions(base_version, new_manifest)
    try:
        registry.store.save_version(
            new_manifest,
            SkillManifest(**new_manifest).version_identity(instructions),
            instructions=instructions,
            base_version=patch.base_version,
            patch_summary=(patch.reason or "structured patch")[:1000],
            review_id=review_id,
            patch_author=patch.author,
            patch=patch.to_dict(),
        )
    except ValueError as exc:
        return {"ok": False, "error": str(exc), "stage": "persist"}

    registry.store.append_event(
        "skill.patch_proposed",
        skill_id=patch.skill,
        version=new_manifest["version"],
        data={
            "baseVersion": patch.base_version,
            "author": patch.author,
            "operations": len(patch.operations),
            "reviewId": review_id,
        },
    )
    # Invalidate the in-memory registry so the new version is discoverable.
    _reload(registry)
    return {
        "ok": True,
        "skillId": patch.skill,
        "version": new_manifest["version"],
        "baseVersion": patch.base_version,
        "status": "draft",
        "patch": patch.to_dict(),
    }


def patch_preserved_instructions(base_version: dict[str, Any], new_manifest: dict[str, Any]) -> Optional[str]:
    """Carry the base instructions forward unless the patch changed them.

    Instructions (`SKILL.md`) are not part of the JSON manifest, so a manifest
    patch that does not touch `instructions` must keep the original prose.
    """
    if str(new_manifest.get("instructions") or "") != str(base_version["manifest"].get("instructions") or ""):
        return None  # a new instructions path was named; do not reuse old prose
    return base_version.get("instructions")


# ── Evaluate (structured, persisted, gate-blocking) ─────────────────────────


def evaluate_version(
    registry: SkillRegistry,
    skill_id: str,
    version: str,
    *,
    actor: Actor,
    require_execution: Optional[bool] = None,
    execution_invoker: Any = None,
) -> dict[str, Any]:
    """Run the deterministic evaluation and persist a structured record.

    The record carries baseline/candidate versions, pass/fail counts, regression
    count and before/after success rates so activation decisions are auditable.
    """
    from .evaluation import evaluate_skill  # noqa: PLC0415

    result = evaluate_skill(
        skill_id, version, registry, run_regression=True,
        require_execution=require_execution,
        execution_invoker=execution_invoker,
    )
    stored = registry.store.get_version(skill_id, version)
    baseline = (stored or {}).get("baseVersion")
    metrics = _metrics_record(registry, skill_id, baseline, version)
    dimensions = result.get("dimensions", [])
    passed = sum(1 for d in dimensions if d.get("status") == "passed")
    failed = sum(1 for d in dimensions if d.get("status") == "failed")
    record = {
        "baselineVersion": baseline,
        "candidateVersion": version,
        "passed": passed,
        "failed": failed,
        "regressions": metrics.get("regressions", 0),
        "successRateBefore": metrics.get("successRateBefore"),
        "successRateAfter": metrics.get("successRateAfter"),
        "decision": (
            "eligible_for_activation"
            if result.get("status") == "passed"
            else "blocked"
        ),
    }
    registry.store.append_event(
        "skill.version_evaluated",
        skill_id=skill_id, version=version,
        data={k: record[k] for k in ("passed", "failed", "regressions", "decision")},
    )
    return {"ok": True, **result, "record": record}


def _metrics_record(
    registry: SkillRegistry, skill_id: str, baseline: Optional[str], candidate: str
) -> dict[str, Any]:
    if not baseline:
        return {}
    try:
        comparison = compare_versions(registry.store, skill_id, baseline, candidate)
    except Exception:  # noqa: BLE001
        return {}
    return {
        "regressions": len(comparison.get("regressions", []) or []),
        "successRateBefore": comparison.get("before", {}).get("successRate"),
        "successRateAfter": comparison.get("after", {}).get("successRate"),
    }


# ── Activate (direct or canary) ─────────────────────────────────────────────


def activate_version(
    registry: SkillRegistry,
    skill_id: str,
    version: str,
    *,
    actor: Actor,
    canary: bool = False,
    reason: str = "",
) -> dict[str, Any]:
    """Activate a version, directly or as a canary.

    A direct activation requires a PASSING evaluation. A canary additionally
    requires the skill to be safe/non-mutating; it routes only a fraction of
    eligible runs and can always be rolled back.
    """
    denied = _require(actor, "skill.enable")
    if denied:
        return denied
    stored = registry.store.get_version(skill_id, version)
    if stored is None:
        return {"ok": False, "error": f"version {version!r} does not exist for {skill_id!r}"}
    eval_status = stored.get("evaluationStatus")
    from ..config.flags import get_bool  # noqa: PLC0415

    from .evaluation import execution_gate_applies  # noqa: PLC0415

    manifest = registry.manifest(skill_id)
    if (
        eval_status == "passed"
        and get_bool("HARNESS_SKILL_EXEC_EVAL")
        and manifest is not None
        and execution_gate_applies(manifest)
    ):
        evaluations = [
            row for row in registry.store.list_evaluations(skill_id, limit=20)
            if str(row.get("version")) == str(version)
            and str(row.get("status")) == "passed"
        ]
        if not evaluations or not (evaluations[0].get("executionRunIds") or []):
            return {
                "ok": False,
                "error": "execution evaluation required before activation",
                "skillId": skill_id, "version": version,
            }
    if eval_status not in ("passed",):
        return {
            "ok": False,
            "error": f"version {version!r} has evaluationStatus={eval_status!r}; a passing evaluation is required",
        }

    if canary:
        # The row status is authoritative for lifecycle; the manifest's embedded
        # status may still be the authoring default. Evaluate canary eligibility
        # against the effective status.
        effective = {**stored["manifest"], "status": stored.get("status") or stored["manifest"].get("status")}
        eligible, why = canary_eligible(effective)
        if not eligible:
            return {"ok": False, "error": f"not canary-eligible: {why}"}
        registry.store.set_version_status(skill_id, version, "canary")
        registry.store.set_canary_state(skill_id, version, "canary")
        registry.store.save_review(
            skill_id=skill_id, version=version, actor=actor.id,
            decision="canary", notes=reason or "canary activation",
        )
        registry.store.append_event("skill.canary_started", skill_id=skill_id, version=version)
        _reload(registry)
        return {"ok": True, "skillId": skill_id, "version": version, "status": "canary", "canary": True}

    prior = registry.store.get_skill(skill_id)
    prior_version = (prior or {}).get("latestVersion")
    # `latestVersion` can already point at the CANDIDATE (a source version bump
    # updates it before activation). Retiring only that value would leave the
    # previously ENABLED version enabled, so two versions would run. Retire every
    # other version that is currently executable, and report the first as the
    # prior version for the review/event.
    other_active = [
        v["version"]
        for v in registry.store.list_versions(skill_id)
        if v["version"] != version
        and str(v.get("status") or "") in ("enabled", "active", "canary")
    ]
    for stale in other_active:
        registry.store.set_version_status(skill_id, stale, "superseded")
    _retire_prior(registry, skill_id, prior_version, version)
    registry.store.set_version_status(skill_id, version, "enabled")
    registry.store.set_latest_version(skill_id, version)
    registry.store.set_version_activation(skill_id, version, activated=True)
    registry.store.set_canary_state(skill_id, version, None)
    registry.store.save_review(
        skill_id=skill_id, version=version, actor=actor.id,
        decision="activate", notes=reason or "activation",
    )
    registry.store.append_event("skill.activated", skill_id=skill_id, version=version,
                                data={"priorVersion": other_active[0] if other_active else prior_version})
    _reload(registry)
    return {"ok": True, "skillId": skill_id, "version": version, "status": "enabled", "canary": False}


def promote_canary(
    registry: SkillRegistry, skill_id: str, version: str, *, actor: Actor
) -> dict[str, Any]:
    """Promote a canary version to active (or roll it back on a failed check)."""
    stored = registry.store.get_version(skill_id, version)
    if stored is None:
        return {"ok": False, "error": "version not found"}
    metrics = _metrics_record(registry, skill_id, stored.get("baseVersion"), version)
    regression = _should_rollback(registry, skill_id, version, metrics)
    if regression:
        return {
            "ok": False,
            "rolledBack": True,
            "reason": regression,
            **rollback(registry, skill_id=skill_id, version=version, actor=actor, reason=regression),
        }
    registry.store.set_canary_state(skill_id, version, "promoted")
    return activate_version(registry, skill_id, version, actor=actor,
                            canary=False, reason="canary passed monitoring")


# ── Rollback (automatic + manual) ───────────────────────────────────────────


def rollback(
    registry: SkillRegistry,
    *,
    skill_id: str,
    version: str,
    actor: Actor,
    reason: str,
) -> dict[str, Any]:
    """Atomically roll a version back to its base, preserving both versions.

    The failed version becomes `rolled_back` with a timestamp; its base is
    re-activated. Nothing is deleted.
    """
    denied = _require(actor, "skill.enable")
    if denied:
        return denied
    stored = registry.store.get_version(skill_id, version)
    if stored is None:
        return {"ok": False, "error": "version not found"}
    to_version = stored.get("baseVersion") or _previous_version(registry, skill_id, version)
    if not to_version:
        # No base to return to: disable the skill rather than leave a bad active.
        registry.store.set_version_status(skill_id, version, "rolled_back")
        registry.store.set_version_activation(skill_id, version, activated=False)
        registry.store.append_event("skill.rolled_back", skill_id=skill_id, version=version,
                                    data={"reason": reason, "restored": None})
        _reload(registry)
        return {"ok": True, "skillId": skill_id, "rolledBackVersion": version,
                "restoredVersion": None, "disabled": True}

    prior = registry.store.get_version(skill_id, to_version)
    if prior is None:
        return {"ok": False, "error": f"rollback target {to_version!r} missing"}

    # Atomic transition: one commit for all mutations.
    registry.store.set_version_status(skill_id, version, "rolled_back")
    registry.store.set_version_activation(skill_id, version, activated=False)
    registry.store.set_version_status(skill_id, to_version, "enabled",
                                      evaluation_status=prior.get("evaluationStatus"))
    registry.store.set_latest_version(skill_id, to_version)
    registry.store.set_version_activation(skill_id, to_version, activated=True)
    registry.store.set_canary_state(skill_id, to_version, None)
    registry.store.save_review(
        skill_id=skill_id, version=to_version, actor=actor.id,
        decision="rollback", notes=f"{reason} (from {version})",
    )
    registry.store.append_event("skill.rolled_back", skill_id=skill_id, version=version,
                                data={"reason": reason, "restored": to_version, "actor": actor.id})
    _reload(registry)
    return {"ok": True, "skillId": skill_id, "rolledBackVersion": version,
            "restoredVersion": to_version, "status": "enabled"}


def check_rollback_triggers(
    registry: SkillRegistry,
    skill_id: str,
    version: str,
    *,
    actor: Actor,
    user_corrections: int = 0,
) -> dict[str, Any]:
    """Automatic rollback check for an active/canary version.

    Triggers (deterministic): a regression vs the base, a failure-rate increase,
    a timeout increase, or user corrections. Returns `{rolledBack: bool, ...}`.
    """
    stored = registry.store.get_version(skill_id, version)
    if stored is None:
        return {"ok": False, "rolledBack": False, "error": "version not found"}
    metrics = _metrics_record(registry, skill_id, stored.get("baseVersion"), version)
    reason = _should_rollback(registry, skill_id, version, metrics, user_corrections=user_corrections)
    if not reason:
        return {"ok": True, "rolledBack": False, "metrics": metrics}
    result = rollback(registry, skill_id=skill_id, version=version, actor=actor, reason=reason)
    return {"ok": True, "rolledBack": True, "reason": reason, **result}


def _should_rollback(
    registry: SkillRegistry,
    skill_id: str,
    version: str,
    metrics: dict[str, Any],
    *,
    user_corrections: int = 0,
) -> Optional[str]:
    if metrics.get("regressions"):
        return f"regression detected vs baseline ({metrics['regressions']})"
    before = metrics.get("successRateBefore")
    after = metrics.get("successRateAfter")
    if before is not None and after is not None and after < before:
        return f"success rate dropped {before:.2f} → {after:.2f}"
    if user_corrections >= 2:
        return f"{user_corrections} user corrections after activation"
    return None


# ── Canonical version list (for UI) ─────────────────────────────────────────


def version_history(registry: SkillRegistry, skill_id: str) -> list[dict[str, Any]]:
    """The skill's versions with patch/eval/canary metadata for the UI."""
    skill = registry.store.get_skill(skill_id)
    active = (skill or {}).get("latestVersion")
    out: list[dict[str, Any]] = []
    for stored in registry.store.list_versions(skill_id):
        out.append({
            "version": stored["version"],
            "status": stored["status"],
            "isActive": stored["version"] == active,
            "evaluationStatus": stored.get("evaluationStatus"),
            "baseVersion": stored.get("baseVersion"),
            "patchSummary": stored.get("patchSummary"),
            "patchAuthor": stored.get("patchAuthor"),
            "reviewId": stored.get("reviewId"),
            "canaryState": stored.get("canaryState"),
            "activatedAt": stored.get("activatedAt"),
            "rolledBackAt": stored.get("rolledBackAt"),
            "nonActivationCause": stored.get("nonActivationCause"),
            "nonActivationDetail": stored.get("nonActivationDetail"),
            "createdAt": stored.get("createdAt"),
            "patch": stored.get("patch"),
        })
    return out


# ── helpers ─────────────────────────────────────────────────────────────────


def _require(actor: Actor, permission: str) -> Optional[dict[str, Any]]:
    from .permissions import check_permissions  # noqa: PLC0415

    decision = check_permissions([permission], actor)
    if not decision.allowed:
        return {"ok": False, "error": "PERMISSION_DENIED", "missing": list(decision.missing)}
    return None


def _previous_version(registry: SkillRegistry, skill_id: str, version: str) -> Optional[str]:
    versions = [v["version"] for v in registry.store.list_versions(skill_id)]
    if version in versions:
        index = versions.index(version)
        if index > 0:
            return versions[index - 1]
    return None


def _retire_prior(registry: SkillRegistry, skill_id: str, prior: Optional[str], new_version: str) -> None:
    if prior and prior != new_version:
        registry.store.set_version_status(skill_id, prior, "superseded")


def _reload(registry: SkillRegistry) -> None:
    try:
        registry.load_all()
    except Exception:  # noqa: BLE001 - reload failure must not fail the mutation
        pass


__all__ = [
    "activate_version",
    "check_rollback_triggers",
    "evaluate_version",
    "promote_canary",
    "propose_patch",
    "rollback",
    "version_history",
]
