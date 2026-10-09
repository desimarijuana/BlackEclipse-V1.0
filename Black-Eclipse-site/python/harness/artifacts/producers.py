"""Producer integration — the ONE hook other subsystems call to record the files
they create into the Artifact Center.

Explicit registration is the reliable path; terminal/filesystem discovery is the
backstop. Every hook here is best-effort: an artifact-registration failure must
never fail the producing run, but it is logged and the producing result is still
honest about what it produced (the caller keeps its own artifact references).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Iterable, Optional

from .bootstrap import get_artifact_service
from .model import ArtifactCategory
from .service import ArtifactError

log = logging.getLogger("harness.artifacts.producers")


def _service(ctx: Any) -> Optional[Any]:
    service = getattr(ctx, "artifact_service", None) if ctx is not None else None
    return service or get_artifact_service()


def register_run_artifacts(
    ctx: Any,
    refs: Iterable[Any],
    *,
    source_tool: str,
    owner_id: str = "local",
    agent_id: Optional[str] = None,
    task_id: Optional[str] = None,
) -> list[Any]:
    """Record a run's `ArtifactRef` outputs. Idempotent per (run, digest)."""
    service = _service(ctx)
    if service is None:
        return []
    run_id = getattr(ctx, "run_id", None) if ctx is not None else None
    out: list[Any] = []
    for ref in refs or []:
        path = getattr(ref, "path", None) or (ref.get("path") if isinstance(ref, dict) else None)
        if not path or not Path(path).is_file():
            continue
        name = (
            getattr(ref, "name", None)
            or (ref.get("name") if isinstance(ref, dict) else None)
            or Path(path).name
        )
        digest = (
            getattr(ref, "sha256", None)
            or (ref.get("sha256") if isinstance(ref, dict) else None)
        )
        media_type = (
            getattr(ref, "media_type", None)
            or (ref.get("mediaType") if isinstance(ref, dict) else None)
        )
        idem = f"run:{run_id or 'none'}:{digest or name}"
        try:
            out.append(service.register_path(
                path, name=name, owner_id=owner_id, mime_type=media_type,
                source_type="agent", source_tool=source_tool, agent_id=agent_id,
                task_id=task_id, run_id=run_id, idempotency_key=idem,
            ))
        except ArtifactError as exc:
            log.info("artifact registration skipped for %s: %s", name, exc.code)
        except Exception:  # noqa: BLE001 - never fail the producing run
            log.warning("artifact registration failed for %s", name, exc_info=True)
    return out


def register_reference_dicts(
    refs: Iterable[dict[str, Any]],
    *,
    source_tool: str,
    owner_id: str = "local",
    run_id: Optional[str] = None,
    task_id: Optional[str] = None,
    agent_id: Optional[str] = None,
) -> list[Any]:
    """Record artifacts already described as dicts (task/exec outcome shape)."""
    service = get_artifact_service()
    if service is None:
        return []
    out: list[Any] = []
    for ref in refs or []:
        uri = str(ref.get("uri") or ref.get("path") or "")
        if not uri or not Path(uri).is_file():
            continue
        name = str(ref.get("name") or ref.get("label") or Path(uri).name)
        digest = ref.get("digest") or ref.get("sha256")
        idem = f"producer:{task_id or ''}:{run_id or ''}:{digest or uri}"
        try:
            out.append(service.register_path(
                uri, name=name, owner_id=owner_id, source_type="job",
                source_tool=source_tool, run_id=run_id, task_id=task_id,
                agent_id=agent_id, idempotency_key=idem,
            ))
        except ArtifactError as exc:
            log.info("artifact registration skipped for %s: %s", name, exc.code)
        except Exception:  # noqa: BLE001
            log.warning("artifact registration failed for %s", name, exc_info=True)
    return out


def register_research_report(
    *,
    research_id: str,
    question: str,
    snapshot_id: Optional[str] = None,
    evidence: Iterable[Any] = (),
    claims: Iterable[Any] = (),
    citations: Iterable[Any] = (),
    conflicts: Iterable[Any] = (),
    coverage: Optional[dict[str, Any]] = None,
    owner_id: str = "local",
    max_evidence: int = 40,
) -> Optional[Any]:
    """Record a research run as a durable, evidence-REFERENCING report artifact.

    The report names the evidence records (id + provenance), the claim verdicts,
    the conflicts and the snapshot id — it does NOT duplicate the evidence store.
    A later reader can reconstruct what Eclipse knew at this run from the snapshot
    and the referenced evidence. Best-effort: returns None (and never raises) when
    the Artifact Center is not installed or there is nothing to report, so a
    research run is never failed by catalog registration.
    """
    service = get_artifact_service()
    if service is None:
        return None
    evidence_list = list(evidence or [])
    claim_list = list(claims or [])
    if not evidence_list and not claim_list:
        return None
    try:
        report = _render_research_report(
            research_id=research_id, question=question, snapshot_id=snapshot_id,
            evidence=evidence_list, claims=claim_list, citations=list(citations or []),
            conflicts=list(conflicts or []), coverage=coverage, max_evidence=max_evidence,
        )
        statuses: dict[str, int] = {}
        for claim in claim_list:
            key = str(_attr(claim, "status") or "UNKNOWN")
            statuses[key] = statuses.get(key, 0) + 1
        evidence_ids = [eid for eid in (_attr(ev, "evidenceId") for ev in evidence_list[:max_evidence]) if eid]
        metadata = {
            "researchId": research_id,
            "snapshotId": snapshot_id,
            "evidenceIds": evidence_ids,
            "evidenceCount": len(evidence_list),
            "evidenceTruncated": len(evidence_list) > max_evidence,
            "claimStatuses": statuses,
            "citationCount": len(list(citations or [])),
            "conflictCount": len(list(conflicts or [])),
            "coverageStatus": coverage.get("status") if isinstance(coverage, dict) else None,
        }
        return service.register_bytes(
            report.encode("utf-8"),
            name=f"research-report-{research_id[:8]}.md",
            owner_id=owner_id,
            description=f"Evidence report for research run {research_id}",
            category=ArtifactCategory.REPORT,
            mime_type="text/markdown",
            source_tool="research",
            run_id=research_id,
            tags=["research", "evidence"],
            idempotency_key=f"research:{research_id}:{snapshot_id or 'latest'}",
            metadata=metadata,
        )
    except Exception:  # noqa: BLE001 - registration must never fail the run
        log.warning("research report artifact registration failed", exc_info=True)
        return None


def _attr(obj: Any, name: str) -> Any:
    """Read a field from a model/object or a plain dict."""
    if isinstance(obj, dict):
        return obj.get(name)
    return getattr(obj, name, None)


def _render_research_report(
    *,
    research_id: str,
    question: str,
    snapshot_id: Optional[str],
    evidence: list[Any],
    claims: list[Any],
    citations: list[Any],
    conflicts: list[Any],
    coverage: Optional[dict[str, Any]],
    max_evidence: int,
) -> str:
    """Render a bounded Markdown evidence report (references, not raw dumps)."""
    lines: list[str] = [
        f"# Research report — {question}",
        "",
        f"- Research id: `{research_id}`",
        f"- Snapshot: `{snapshot_id or '—'}`",
        f"- Coverage: `{(coverage or {}).get('status', 'unknown')}`",
        f"- Claims: {len(claims)} · Evidence: {len(evidence)} · Citations: {len(citations)} · Conflicts: {len(conflicts)}",
        "",
        "## Claims",
    ]
    if not claims:
        lines.append("_No claims were recorded._")
    for claim in claims:
        text = str(_attr(claim, "text") or "").strip()
        status = _attr(claim, "status") or "UNKNOWN"
        ev_ids = _attr(claim, "evidenceIds") or []
        suffix = f" (evidence: {', '.join(str(i) for i in ev_ids)})" if ev_ids else ""
        lines.append(f"- **[{status}]** {text}{suffix}")
    lines += ["", "## Evidence appendix"]
    if not evidence:
        lines.append("_No evidence was recorded._")
    for ev in evidence[:max_evidence]:
        eid = _attr(ev, "evidenceId") or "?"
        url = _attr(ev, "sourceUrl") or ""
        published = _attr(ev, "publishedAt") or "unknown"
        retrieved = _attr(ev, "retrievedAt") or "unknown"
        lines.append(f"- `{eid}` — {url} (published: {published}, retrieved: {retrieved})")
    if len(evidence) > max_evidence:
        lines.append(f"- …and {len(evidence) - max_evidence} more (see the run snapshot).")
    if conflicts:
        lines += ["", "## Conflicts"]
        for conflict in conflicts:
            metric = _attr(conflict, "metric") or "?"
            status = _attr(conflict, "status") or "UNRESOLVED"
            explanation = _attr(conflict, "explanation")
            detail = f" — {explanation}" if explanation else ""
            lines.append(f"- **{metric}** [{status}]{detail}")
    lines += ["", "_Evidence is referenced by id from the evidence store; raw source text is not duplicated here._", ""]
    return "\n".join(lines)


__all__ = [
    "register_reference_dicts",
    "register_run_artifacts",
    "register_research_report",
]
