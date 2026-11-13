"""Skill lifecycle, project trust, bundles, authoring and learning routes.

Extracted verbatim from `main.py` so the front door stays navigable. Behavior,
authorization (`require_operator`, transport/token only) and response shapes are
unchanged; the shared runtime service comes from `harness.deps`.
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException

from ..deps import require_operator, service

router = APIRouter()

@router.get("/skills")
def list_skills(
    status: Optional[str] = None,
    q: Optional[str] = None,
    category: Optional[str] = None,
    risk: Optional[str] = None,
    sort: str = "name",
    limit: Optional[int] = None,
    offset: int = 0,
) -> dict[str, Any]:
    """The Skills Library list.

    Defaults preserve the historical shape: every skill, name-sorted. Passing
    `limit` opts into the paged envelope (`total` = filtered count, `hasMore`,
    `offset`). Filtering happens before paging so `total` is exact.
    """
    from ..skills.listing import filter_summaries, page_summaries, sort_summaries

    registry = service.skill_registry
    everything = registry.list_summaries()
    matched = filter_summaries(
        everything, q=q, category=category, status=status, risk=risk
    )
    page = page_summaries(sort_summaries(matched, sort), limit=limit, offset=offset)
    return {
        "success": True,
        "registryTotal": len(everything),
        **page,
        "loadErrors": service.skill_load_errors,
        "duplicates": registry.duplicate_ids(),
        "projectNotices": registry.project_notices(),
        "projectDrift": registry.project_drift(),
        "projectChangedSkillIds": registry.project_changed_ids(),
        "projectQuarantinedSkillIds": registry.project_quarantined_ids(),
        "projectUnchangedSkillIds": registry.project_unchanged_ids(),
        "installedNotices": registry.installed_notices(),
        "installedChangedSkillIds": registry.installed_changed_ids(),
        "installedQuarantinedSkillIds": registry.installed_quarantined_ids(),
        "shadowed": registry.shadowed_ids(),
        "contentFindings": registry.content_findings(),
        "quarantined": registry.quarantined_ids(),
    }


@router.get("/skills/installed")
def installed_skill_sources() -> dict[str, Any]:
    """GitHub-installed skill sources with trust/drift state (read-only).

    Declared BEFORE `/skills/{skill_id}` so the literal path wins. Never
    contacts the network; the `install.json` metadata + the trust store are the
    only inputs.
    """
    from ..skills.install import list_installed_sources  # noqa: PLC0415

    sources = list_installed_sources(service.skill_store)
    return {
        "success": True,
        "sources": sources,
        "notices": service.skill_registry.installed_notices(),
    }


# ── Project-local skills (trust model) ──────────────────────────────────────


@router.get("/onboarding")
def onboarding() -> dict[str, Any]:
    """Static, read-only first-run explanation + bundled starter skills."""
    from ..onboarding import onboarding_content  # noqa: PLC0415

    registry = service.skill_registry
    starter = [
        s for s in registry.list_summaries()
        if s.get("provenance") == "bundled"
    ]
    return {"success": True, **onboarding_content(starter_skills=starter)}


@router.get("/skills/project")
def project_skill_status() -> dict[str, Any]:
    """Discover project skills for the runtime's project root without loading
    them. Untrusted roots yield names + a notice only; nothing is registered."""
    from ..skills.project_skills import discover_project_skills  # noqa: PLC0415

    discovery = discover_project_skills(
        service.skill_store,
        service._project_root(),
        project_discovery=service._project_discovery_enabled(),
    )
    from ..skills.project_skills import drift_status  # noqa: PLC0415

    root = discovery.root
    return {
        "success": True,
        "projectDiscovery": service._project_discovery_enabled(),
        "projectRoot": service._project_root(),
        "discovery": discovery.to_dict(),
        "drift": drift_status(service.skill_store, root) if root else None,
        "trusted": service.skill_store.list_project_trust(),
        "changedSkills": _project_changed_review(root) if root else None,
        "approvalHistory": service.skill_store.list_project_approvals(root) if root else [],
    }


def _project_changed_review(root: Optional[str]) -> Optional[dict[str, Any]]:
    """Content-free changed-skill review (hashes + ids only) for a project root."""
    if not root:
        return None
    from ..skills.project_skills import changed_skill_review  # noqa: PLC0415

    try:
        return changed_skill_review(service.skill_store, root)
    except Exception:  # noqa: BLE001 - a review failure must not break the status read
        return None


@router.get("/skills/project/history")
def project_trust_history(path: Optional[str] = None, limit: int = 50) -> dict[str, Any]:
    """Append-only project trust/approval/revoke history (who/what/when/level)."""
    root = path or service._project_root()
    return {
        "success": True,
        "path": root,
        "history": service.skill_store.list_project_approvals(root, limit=limit),
    }


@router.post("/skills/project/approve")
def approve_project_skill(
    payload: Optional[dict[str, Any]] = None,
    operator: bool = Depends(require_operator),
) -> dict[str, Any]:
    """Re-approve a quarantined (drifted) project root, re-baselining its hash.

    Same gate as trust; recorded as a distinct `skill.project_reapproved` event
    so the drift→review→approval chain is auditable. A project skill still runs
    through the normal permission/execution gate.
    """
    if not operator:
        raise HTTPException(status_code=403, detail="operator authorization required")
    from ..skills.project_skills import (  # noqa: PLC0415
        canonical_root,
        root_content_hash,
        trust_root,
    )

    payload = payload or {}
    root = payload.get("path") or service._project_root()
    if not root:
        raise HTTPException(status_code=400, detail="a project path is required")
    # Re-approve re-baselines BOTH the root hash and every per-skill hash, which
    # reactivates all quarantined skills. `skillIds` records which skills the
    # operator was shown at approval (review audit), never an authorization.
    requested = payload.get("skillIds")
    skill_ids = [str(s) for s in requested] if isinstance(requested, list) else None
    level = "skill" if skill_ids else "root"
    state = trust_root(
        service.skill_store, root,
        note=payload.get("note") or "re-approved after change",
        actor=payload.get("actor") or "operator",
        skill_ids=skill_ids, level=level,
    )
    service.reload_project_skills()
    service.skill_store.append_event(
        "skill.project_reapproved",
        data={"path": canonical_root(root), "skillIds": skill_ids, "level": level},
    )
    return {
        "success": True,
        "root": state.to_dict(),
        "contentHash": root_content_hash(root),
        "level": level,
    }


@router.post("/skills/project/trust")
def trust_project_skill(
    payload: Optional[dict[str, Any]] = None,
    operator: bool = Depends(require_operator),
) -> dict[str, Any]:
    """Trust a project root so its skills load. Operator-gated by transport or
    token. A project skill is still permission/execution gated like any other."""
    if not operator:
        raise HTTPException(status_code=403, detail="operator authorization required")
    from ..skills.project_skills import (
        canonical_root,  # noqa: PLC0415
        root_content_hash,  # noqa: PLC0415
        trust_root,  # noqa: PLC0415
    )

    payload = payload or {}
    root = payload.get("path") or service._project_root()
    if not root:
        raise HTTPException(status_code=400, detail="a project path is required")
    state = trust_root(
        service.skill_store, root, note=payload.get("note"),
        actor=payload.get("actor") or "operator",
    )
    service.reload_project_skills()
    service.skill_store.append_event(
        "skill.project_trusted",
        data={"path": canonical_root(root), "skillIds": state.skill_ids},
    )
    return {
        "success": True,
        "root": state.to_dict(),
        "contentHash": root_content_hash(root),
    }


# ── Skill bundles ───────────────────────────────────────────────────────────


@router.get("/skill-bundles")
def list_skill_bundles() -> dict[str, Any]:
    bundles = service.skill_store.list_skill_bundles()
    # Resolution is read-only and reports missing/disabled members honestly.
    from ..skills.bundles import resolve_bundle  # noqa: PLC0415

    resolved = {
        b["id"]: resolve_bundle(service.skill_store, service.skill_registry, b["id"]).to_dict()
        for b in bundles
    }
    return {"success": True, "bundles": bundles, "resolved": resolved}


@router.get("/skill-bundles/{bundle_id}")
def get_skill_bundle(bundle_id: str) -> dict[str, Any]:
    bundle = service.skill_store.get_skill_bundle(bundle_id)
    if not bundle:
        raise HTTPException(status_code=404, detail="Bundle not found")
    from ..skills.bundles import resolve_bundle  # noqa: PLC0415

    return {
        "success": True,
        "bundle": bundle,
        "resolution": resolve_bundle(service.skill_store, service.skill_registry, bundle_id).to_dict(),
    }


@router.post("/skill-bundles")
def create_skill_bundle(
    payload: Optional[dict[str, Any]] = None,
    operator: bool = Depends(require_operator),
) -> dict[str, Any]:
    """Create/update a bundle. Operator-gated; a bundle is a reference and can
    never enable a disabled skill or widen a permission."""
    if not operator:
        raise HTTPException(status_code=403, detail="operator authorization required")
    from ..skills.bundles import BundleError, SkillBundle  # noqa: PLC0415

    payload = payload or {}
    try:
        bundle = SkillBundle(
            id=str(payload.get("id") or ""),
            name=str(payload.get("name") or ""),
            description=str(payload.get("description") or ""),
            skills=[str(s) for s in (payload.get("skills") or [])],
            instruction=str(payload.get("instruction") or ""),
            constraints=str(payload.get("constraints") or ""),
            provenance=str(payload.get("provenance") or "manual"),
            version=str(payload.get("version") or "1.0.0"),
            member_versions=dict(payload.get("memberVersions") or {}),
            locked=bool(payload.get("locked")),
        )
    except BundleError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    saved = service.skill_store.save_skill_bundle(bundle.to_dict())
    service.skill_store.append_event("skill.bundle_saved", data={"bundleId": bundle.id})
    return {"success": True, "bundle": saved}


@router.post("/skill-bundles/{bundle_id}/lock")
def lock_skill_bundle(
    bundle_id: str,
    operator: bool = Depends(require_operator),
) -> dict[str, Any]:
    """Pin the bundle's current resolved member versions (reproducible)."""
    if not operator:
        raise HTTPException(status_code=403, detail="operator authorization required")
    from ..skills.bundles import lock_bundle  # noqa: PLC0415

    result = lock_bundle(service.skill_store, service.skill_registry, bundle_id)
    return {"success": result.get("ok", False), **result}


@router.post("/skill-bundles/{bundle_id}/unlock")
def unlock_skill_bundle(
    bundle_id: str,
    operator: bool = Depends(require_operator),
) -> dict[str, Any]:
    if not operator:
        raise HTTPException(status_code=403, detail="operator authorization required")
    from ..skills.bundles import unlock_bundle  # noqa: PLC0415

    result = unlock_bundle(service.skill_store, bundle_id)
    return {"success": result.get("ok", False), **result}


@router.get("/skill-bundles/{bundle_id}/update-preview")
def bundle_update_preview_route(bundle_id: str) -> dict[str, Any]:
    """What would change if the bundle were re-locked (read-only, no mutation)."""
    from ..skills.bundles import bundle_update_preview  # noqa: PLC0415

    return {"success": True, **bundle_update_preview(
        service.skill_store, service.skill_registry, bundle_id,
    )}


@router.post("/skill-bundles/{bundle_id}/rollback")
def rollback_skill_bundle(
    bundle_id: str,
    operator: bool = Depends(require_operator),
) -> dict[str, Any]:
    """Re-pin the bundle to its recorded lock (safe rollback)."""
    if not operator:
        raise HTTPException(status_code=403, detail="operator authorization required")
    from ..skills.bundles import rollback_bundle  # noqa: PLC0415

    result = rollback_bundle(service.skill_store, service.skill_registry, bundle_id)
    return {"success": result.get("ok", False), **result}


@router.delete("/skill-bundles/{bundle_id}")
def delete_skill_bundle(
    bundle_id: str,
    operator: bool = Depends(require_operator),
) -> dict[str, Any]:
    if not operator:
        raise HTTPException(status_code=403, detail="operator authorization required")
    removed = service.skill_store.delete_skill_bundle(bundle_id)
    if not removed:
        raise HTTPException(status_code=404, detail="Bundle not found")
    service.skill_store.append_event("skill.bundle_deleted", data={"bundleId": bundle_id})
    return {"success": True}


@router.post("/skills/project/untrust")
def untrust_project_skill(
    payload: Optional[dict[str, Any]] = None,
    operator: bool = Depends(require_operator),
) -> dict[str, Any]:
    """Revoke project trust; its skills immediately stop being injected."""
    if not operator:
        raise HTTPException(status_code=403, detail="operator authorization required")
    from ..skills.project_skills import (
        canonical_root,  # noqa: PLC0415
        untrust_root,  # noqa: PLC0415
    )

    payload = payload or {}
    root = payload.get("path") or service._project_root()
    if not root:
        raise HTTPException(status_code=400, detail="a project path is required")
    state = untrust_root(service.skill_store, root, actor=payload.get("actor") or "operator")
    service.reload_project_skills()
    service.skill_store.append_event(
        "skill.project_untrusted", data={"path": canonical_root(root)},
    )
    return {"success": True, "root": state.to_dict()}


@router.get("/skills/maintenance")
def skill_maintenance_report() -> dict[str, Any]:
    """Read-only skill-maintenance report: stale skills, reasons, actions.

    Declared BEFORE `/skills/{skill_id}` so the literal path wins. Never mutates.
    """
    return {"success": True, **service.skill_maintenance_report()}


@router.post("/skills/maintenance/run")
def run_skill_maintenance(
    operator: bool = Depends(require_operator),
) -> dict[str, Any]:
    """Run one maintenance pass. Operator-gated.

    Report-only by default: it changes nothing unless the operator has enabled
    `skill_maintenance_enabled` AND `skill_maintenance_auto_archive`. Pinned
    skills are always exempt; the pass never deletes and never enables.
    """
    if not operator:
        raise HTTPException(status_code=403, detail="operator authorization required")
    return {"success": True, **service.run_skill_maintenance()}


@router.get("/skills/curator")
def skill_curator_report() -> dict[str, Any]:
    """W5.2 — the curator ledger: runs and proposals. Read-only."""
    from ..skills.curator import curator_report  # noqa: PLC0415

    return {"success": True, **curator_report(service.skill_store)}


@router.post("/skills/curator/run")
def run_skill_curator(
    payload: Optional[dict[str, Any]] = None,
    operator: bool = Depends(require_operator),
) -> dict[str, Any]:
    """Run one curator pass. Operator-gated.

    Default mode is `dry_run` (report only). A merge always lands as an inert
    draft; nothing is enabled, deleted, or permission-widened.
    """
    if not operator:
        raise HTTPException(status_code=403, detail="operator authorization required")
    from ..skills.curator import run_curator  # noqa: PLC0415

    mode = (payload or {}).get("mode")
    return {
        "success": True,
        **run_curator(
            service.skill_store, service.skill_registry, mode=mode,
            maintenance_policy=service.memory.policy.get_all(),
        ),
    }


@router.post("/skills/curator/proposals/{proposal_id}/approve")
def approve_curator_proposal(
    proposal_id: str,
    payload: Optional[dict[str, Any]] = None,
    operator: bool = Depends(require_operator),
) -> dict[str, Any]:
    if not operator:
        raise HTTPException(status_code=403, detail="operator authorization required")
    from ..skills.curator import approve_proposal  # noqa: PLC0415

    result = approve_proposal(
        service.skill_store, service.skill_registry, proposal_id,
        actor=str((payload or {}).get("actor") or "operator"),
        notes=str((payload or {}).get("notes") or ""),
    )
    return {"success": bool(result.get("ok")), **result}


@router.post("/skills/curator/proposals/{proposal_id}/reject")
def reject_curator_proposal(
    proposal_id: str,
    payload: Optional[dict[str, Any]] = None,
    operator: bool = Depends(require_operator),
) -> dict[str, Any]:
    if not operator:
        raise HTTPException(status_code=403, detail="operator authorization required")
    from ..skills.curator import reject_proposal  # noqa: PLC0415

    result = reject_proposal(
        service.skill_store, proposal_id,
        actor=str((payload or {}).get("actor") or "operator"),
        notes=str((payload or {}).get("notes") or ""),
    )
    return {"success": bool(result.get("ok")), **result}


@router.post("/skills/{skill_id}/pin")
def pin_skill_version(
    skill_id: str,
    payload: Optional[dict[str, Any]] = None,
    operator: bool = Depends(require_operator),
) -> dict[str, Any]:
    """Pin (or unpin) a skill version so automatic maintenance never touches it.

    Operator-gated. Pinning is orthogonal to `status`: pinning does not enable or
    disable a skill; it only exempts it from automatic staleness/archive.
    """
    if not operator:
        raise HTTPException(status_code=403, detail="operator authorization required")
    payload = payload or {}
    registry = service.skill_registry
    if registry.store.get_skill(skill_id) is None:
        raise HTTPException(status_code=404, detail="Skill not found")
    version = payload.get("version") or registry.resolve_version(skill_id)
    if not version:
        raise HTTPException(status_code=400, detail="a version is required")
    pinned = payload.get("pinned", True)
    updated = registry.store.set_version_pinned(skill_id, version, bool(pinned))
    if not updated:
        raise HTTPException(status_code=404, detail="Version not found")
    service.skill_store.append_event(
        "skill.pinned" if pinned else "skill.unpinned",
        skill_id=skill_id, version=version, data={"pinned": bool(pinned)},
    )
    return {
        "success": True, "skillId": skill_id, "version": version,
        "pinned": bool(pinned),
    }


@router.get("/skills/{skill_id}")
def get_skill(skill_id: str) -> dict[str, Any]:
    registry = service.skill_registry
    manifest = registry.manifest(skill_id)
    if manifest is None:
        raise HTTPException(status_code=404, detail="Skill not found")
    record = registry.store.get_skill(skill_id)
    return {
        "success": True,
        "skill": {
            **manifest.model_dump(),
            "instructions": registry.get(skill_id).load_instructions() if registry.get(skill_id) else "",
            "storedStatus": record["status"] if record else manifest.status,
            "latestVersion": record["latestVersion"] if record else manifest.version,
            "validation": registry.validate(skill_id),
            "versions": registry.version_history(skill_id),
            "executions": registry.execution_history(skill_id, 20),
            "evaluations": registry.evaluation_history(skill_id),
            "reviews": registry.store.list_reviews(skill_id, 20),
            "events": registry.store.list_events(skill_id, 50),
            "provenance": registry.provenance_of(skill_id),
            "contentScan": registry.content_findings().get(skill_id),
            "dependencyGraph": registry.dependency_graph(skill_id),
        },
    }


@router.get("/skills/{skill_id}/preflight")
def skill_preflight(skill_id: str) -> dict[str, Any]:
    """Execution preflight: dependency/tool/permission status before a run.

    Read-only; explains exactly why a skill would be unavailable. Never enables
    a dependency or widens a permission.
    """
    registry = service.skill_registry
    if registry.manifest(skill_id) is None:
        raise HTTPException(status_code=404, detail="Skill not found")
    graph = registry.dependency_graph(skill_id)
    validation = registry.validate(skill_id)
    reasons: list[str] = []
    if not validation.get("ok"):
        reasons.extend(validation.get("errors") or [])
    for edge in graph.get("edges") or []:
        if edge.get("status") not in ("ok", "optional"):
            reasons.append(f"{edge['from']} -> {edge['to']}: {edge['status']}")
    return {
        "success": True,
        "skillId": skill_id,
        "ok": bool(validation.get("ok")) and bool(graph.get("ok")),
        "reasons": reasons,
        "validation": validation,
        "dependencyGraph": graph,
    }


@router.get("/skills/{skill_id}/versions")
def skill_versions(skill_id: str) -> dict[str, Any]:
    if service.skill_registry.manifest(skill_id) is None:
        raise HTTPException(status_code=404, detail="Skill not found")
    return {"success": True, "versions": service.skill_registry.version_history(skill_id)}


# ── Eclipse-Memory ──────────────────────────────────────────────────────────

