"""Local research analysis nodes.

Pure reads and deterministic aggregations over the existing `EvidenceStore`
and the existing engine modules (`web_verify`, `web_freshness`, `web_quality`,
`supersession`). No network request and no model call: a test run may exercise
every node in this file.

The store is the authority. A wired array is accepted when a graph already has
one (an `agent.research` result, a previous node's output), and it WINS over the
store — but it is normalized through the same `Evidence`/`Claim` contracts, so
nothing unrecorded is invented.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from types import SimpleNamespace
from typing import Any, Optional

from ..research import supersession, web_freshness, web_quality, web_verify
from ..research.web_contracts import (
    Claim,
    Evidence,
    SourceConflict,
    SourceType,
)
from .model import ExecutionMode, PortDef, PortType, SideEffect
from .registry import ConfigField, NodeDef, NodeExecContext
from .research_nodes import (
    _conflict_rows,
    _conflict_status,
    _gaps,
    _limit,
    _require_store,
    _research_id,
    _summary,
)

_ALL = tuple(ExecutionMode)
MAX_ITEMS = 1_000
_CLAIM_STATUSES = {
    "SUPPORTED", "PARTIALLY_SUPPORTED", "CONTRADICTED", "UNSUPPORTED",
    "OUTDATED", "AMBIGUOUS", "CALCULATED", "INFERRED",
}
_CLAIM_KINDS = {"FACT", "CALCULATION", "INFERENCE", "OPINION", "UNCERTAINTY"}


def _rows(raw: Any) -> list[dict[str, Any]]:
    if isinstance(raw, list):
        return [item for item in raw if isinstance(item, dict)]
    if isinstance(raw, dict):
        for key in ("evidence", "items", "rows", "results", "claims", "citations"):
            value = raw.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
        return [raw]
    return []


def _decode(value: Any, fallback: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (TypeError, ValueError):
            return fallback
    return value if value is not None else fallback


def _confidence(value: Any) -> float:
    try:
        return max(0.0, min(float(value), 1.0))
    except (TypeError, ValueError):
        return 0.0


def _limit_of(context: NodeExecContext, default: int) -> int:
    try:
        value = int(context.config.get("limit", default))
    except (TypeError, ValueError) as exc:
        raise ValueError("limit must be a whole number") from exc
    return max(1, min(value, MAX_ITEMS))


def _source_type(value: Any) -> SourceType:
    try:
        return SourceType(str(value or "unknown").strip().lower())
    except ValueError:
        return SourceType.UNKNOWN


def _claim_status(value: Any) -> str:
    status = str(value or "").strip().upper()
    return status if status in _CLAIM_STATUSES else "UNSUPPORTED"


def _claim_kind(value: Any) -> str:
    kind = str(value or "FACT").strip().upper()
    return kind if kind in _CLAIM_KINDS else "FACT"


def _evidence_model(row: dict[str, Any]) -> Evidence:
    data = dict(row)
    data["structuredValue"] = _decode(data.get("structuredValue"), None)
    data["provenance"] = _decode(data.get("provenance"), {}) or {}
    data["sourceId"] = data.get("sourceId") or ""
    data["sourceUrl"] = data.get("sourceUrl") or ""
    data["sourceType"] = _source_type(data.get("sourceType"))
    data["retrievedAt"] = data.get("retrievedAt") or ""
    data["confidence"] = _confidence(data.get("confidence"))
    data["contentTrust"] = "UNTRUSTED"
    data["rawText"] = data.get("rawText") or ""
    data["contentHash"] = data.get("contentHash") or ""
    if not data.get("evidenceId"):
        raise ValueError("an evidence row is missing evidenceId")
    return Evidence(**data)


def _claim_model(row: dict[str, Any]) -> Claim:
    evidence_ids = row.get("evidenceIds") or []
    if isinstance(evidence_ids, str):
        evidence_ids = [part.strip() for part in evidence_ids.split(",") if part.strip()]
    return Claim(
        id=row.get("id") or row.get("claimId"),
        text=str(row.get("text") or row.get("claimText") or ""),
        kind=_claim_kind(row.get("kind")),  # type: ignore[arg-type]
        evidenceIds=[str(eid) for eid in evidence_ids if eid],
        calculationId=row.get("calculationId"),
        status=_claim_status(row.get("status")),  # type: ignore[arg-type]
        confidence=_confidence(row.get("confidence")),
        issues=[str(item) for item in (_decode(row.get("issues"), []) or [])],
    )


def _stored_claims(store: Any, research_id: str) -> list[Claim]:
    claims: list[Claim] = []
    for row in store.list_claims(research_id):
        links = (
            [link.get("evidenceId") for link in store.list_claim_evidence(str(row["id"]))]
            if row.get("id") else []
        )
        claims.append(_claim_model({**row, "evidenceIds": [
            evidence_id for evidence_id in links if evidence_id
        ]}))
    return claims


def _conflict_models(store: Any, research_id: str) -> list[SourceConflict]:
    return [SourceConflict(**row) for row in _conflict_rows(store, research_id)]


def _evidence_rows(context: NodeExecContext, research_id: str) -> list[dict[str, Any]]:
    wired = context.inputs.get("evidence")
    if wired is not None:
        return _rows(wired)
    return _require_store().list_evidence(research_id)


def _pick(context: NodeExecContext, key: str, fallback: list[dict[str, Any]]) -> list[dict[str, Any]]:
    wired = context.inputs.get(key)
    return _rows(wired) if wired is not None else fallback


def _citation_report(
    store: Any,
    research_id: str,
    *,
    claims: Optional[list[Claim]] = None,
    citations: Optional[list[Any]] = None,
    evidence: Optional[list[Evidence]] = None,
    as_of: Optional[str] = None,
    freshness: Optional[str] = None,
    require_citations: bool = True,
) -> dict[str, Any]:
    from ..research.web_contracts import Citation  # noqa: PLC0415

    claims = claims if claims is not None else _stored_claims(store, research_id)
    evidence = evidence if evidence is not None else [
        _evidence_model(row) for row in store.list_evidence(research_id)
    ]
    by_id = {item.evidenceId: item for item in evidence}
    if citations is None:
        built = web_verify.build_citations(claims, by_id, research_id=research_id)
    else:
        built = []
        for index, row in enumerate(citations):
            built.append(Citation(
                citationId=str(row.get("citationId") or f"wired_{index}"),
                claimText=str(row.get("claimText") or ""),
                evidenceId=str(row.get("evidenceId") or ""),
                sourceUrl=str(row.get("sourceUrl") or ""),
                title=row.get("title"),
                section=row.get("section"),
                page=row.get("page"),
                retrievedAt=row.get("retrievedAt"),
                publishedAt=row.get("publishedAt"),
                locator=row.get("locator"),
            ))
    return web_verify.validate_citations(
        claims, built, by_id, as_of=as_of, freshness=freshness,
        require_citations=require_citations,
    )


# ── Executors ────────────────────────────────────────────────────────────────

def exec_latest(context: NodeExecContext) -> dict[str, Any]:
    store = _require_store()
    research_id = str(
        context.inputs.get("researchId") or context.config.get("researchId") or ""
    ).strip()
    match = str(
        context.inputs.get("question") or context.config.get("questionMatch") or ""
    ).strip().lower()
    try:
        limit = int(context.config.get("limit", 20))
    except (TypeError, ValueError) as exc:
        raise ValueError("limit must be a whole number") from exc
    limit = max(1, min(limit, 50))

    run: Optional[dict[str, Any]] = None
    if research_id:
        run = store.get_run(research_id)
    elif not bool(context.config.get("latest", True)):
        raise ValueError("latest=false requires an explicit researchId")
    else:
        candidates = store.list_runs(limit)
        if match:
            candidates = [
                row for row in candidates
                if match in str(row.get("question") or "").lower()
            ]
        run = candidates[0] if candidates else None
    if run is None:
        target = research_id or match or "the requested question"
        raise ValueError(f"no research run matches {target!r}")
    resolved = str(run.get("researchId") or research_id)
    context.emit(f"resolved research run {resolved}")
    return {
        "researchId": resolved,
        "run": run,
        "summary": {
            "researchId": resolved,
            "question": run.get("question"),
            "status": run.get("status") or run.get("state") or "UNKNOWN",
        },
    }


def exec_sources(context: NodeExecContext) -> dict[str, Any]:
    store = _require_store()
    research_id = _research_id(context)
    limit = _limit_of(context, 200)
    domain = str(context.config.get("domain") or "").strip().lower()
    source_type = str(context.config.get("sourceType") or "").strip().lower()
    published_after = str(context.config.get("publishedAfter") or "").strip()
    dedupe = bool(context.config.get("dedupe", True))

    rows = store.list_sources(research_id)
    excluded_undated = 0
    selected: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        if domain and str(row.get("domain") or "").lower() != domain:
            continue
        if source_type and str(row.get("sourceType") or "").lower() != source_type:
            continue
        if published_after:
            published = str(row.get("publishedAt") or "")
            if not published:
                excluded_undated += 1
                continue
            if published < published_after:
                continue
        key = (
            str(row.get("contentHash") or "")
            or str(row.get("familyId") or "")
            or str(row.get("canonicalUrl") or "")
        )
        if dedupe and key and key in seen:
            continue
        if key:
            seen.add(key)
        selected.append(row)
    selected.sort(
        key=lambda row: (
            str(row.get("publishedAt") or "") == "",
            str(row.get("publishedAt") or ""),
            str(row.get("canonicalUrl") or ""),
        ),
        reverse=False,
    )
    by_type: dict[str, int] = {}
    by_domain: dict[str, int] = {}
    for row in selected:
        by_type[str(row.get("sourceType") or "unknown")] = (
            by_type.get(str(row.get("sourceType") or "unknown"), 0) + 1
        )
        by_domain[str(row.get("domain") or "unknown")] = (
            by_domain.get(str(row.get("domain") or "unknown"), 0) + 1
        )
    page = selected[:limit]
    context.emit(f"{len(page)}/{len(selected)} source(s) for {research_id}")
    return {
        "sources": page,
        "summary": {
            "researchId": research_id,
            "total": len(selected),
            "returned": len(page),
            "truncated": len(page) < len(selected),
            "excludedUndated": excluded_undated,
            "byType": by_type,
            "byDomain": by_domain,
            "status": "EMPTY" if not selected else "OK",
        },
    }


def exec_gaps(context: NodeExecContext) -> dict[str, Any]:
    store = _require_store()
    research_id = _research_id(context)
    limit = _limit(context)
    include_optional = bool(context.config.get("includeOptional", False))
    gaps = _gaps(store, research_id, include_optional=include_optional, limit=limit)
    counts: dict[str, int] = {}
    for gap in gaps:
        counts[str(gap.get("kind"))] = counts.get(str(gap.get("kind")), 0) + 1
    context.emit(f"{len(gaps)} coverage gap(s) for {research_id}")
    return {
        "gaps": gaps,
        "summary": {
            "researchId": research_id,
            "total": len(gaps),
            "byKind": counts,
            "hasGaps": bool(gaps),
            "status": "OK",
        },
    }


def exec_freshness(context: NodeExecContext) -> dict[str, Any]:
    store = _require_store()
    research_id = _research_id(context)
    limit = _limit(context)
    rows = _evidence_rows(context, research_id)
    models: list[Evidence] = []
    by_id: dict[str, dict[str, Any]] = {}
    for row in rows:
        try:
            model = _evidence_model(row)
        except ValueError:
            continue
        models.append(model)
        by_id[model.evidenceId] = row
    admissible, rejections = web_freshness.filter_admissible(
        models,
        as_of=str(context.config.get("asOf") or "") or None,
        freshness=str(context.config.get("freshness") or "") or None,
    )
    kept = [by_id[item.evidenceId] for item in admissible][:limit]
    context.emit(f"{len(kept)}/{len(models)} evidence item(s) admissible")
    return {
        "evidence": kept,
        "rejected": rejections,
        "summary": {
            "researchId": research_id,
            "asOf": str(context.config.get("asOf") or "") or None,
            "freshness": str(context.config.get("freshness") or "") or None,
            "total": len(models),
            "admissible": len(admissible),
            "rejected": len(rejections),
            "returned": len(kept),
            "truncated": len(kept) < len(admissible),
            "status": "EMPTY" if not models else "OK",
        },
    }


def exec_conflict_scan(context: NodeExecContext) -> dict[str, Any]:
    store = _require_store()
    research_id = _research_id(context)
    limit = _limit_of(context, 200)
    tolerance = context.config.get("tolerance", 0.01)
    try:
        tolerance = float(tolerance)
    except (TypeError, ValueError) as exc:
        raise ValueError("tolerance must be a number") from exc
    if tolerance < 0 or tolerance > 1:
        raise ValueError("tolerance must be between 0 and 1")
    rows = _evidence_rows(context, research_id)
    models = []
    for row in rows:
        try:
            models.append(_evidence_model(row))
        except ValueError:
            continue
    scanned = web_verify.detect_conflicts(models, tolerance=tolerance, research_id=research_id)
    merged: list[dict[str, Any]] = [
        {**conflict.model_dump(), "source": "scanned"} for conflict in scanned
    ]
    if bool(context.config.get("mergeStored", True)):
        keys = {(item.get("metric"), item.get("period")) for item in merged}
        for row in _conflict_rows(store, research_id):
            key = (row.get("metric"), row.get("period"))
            if key in keys:
                continue
            keys.add(key)
            merged.append({**row, "source": "stored"})
    unresolved = [
        item for item in merged
        if item.get("status") == "UNRESOLVED" and item.get("material", True)
    ]
    page = merged[:limit]
    context.emit(f"{len(unresolved)} unresolved conflict(s) across {len(models)} item(s)")
    return {
        "conflicts": page,
        "summary": {
            "researchId": research_id,
            "groups": len(merged),
            "unresolved": len(unresolved),
            "returned": len(page),
            "truncated": len(page) < len(merged),
            "tolerance": tolerance,
            "status": "OK",
        },
    }


def exec_citation_audit(context: NodeExecContext) -> dict[str, Any]:
    store = _require_store()
    research_id = _research_id(context)
    limit = _limit_of(context, 500)
    claims = (
        [_claim_model(row) for row in _rows(context.inputs.get("claims"))]
        if context.inputs.get("claims") is not None
        else _stored_claims(store, research_id)
    )
    evidence = (
        [_evidence_model(row) for row in _rows(context.inputs.get("evidence"))]
        if context.inputs.get("evidence") is not None
        else [_evidence_model(row) for row in store.list_evidence(research_id)]
    )
    wired_citations = (
        _rows(context.inputs.get("citations"))
        if context.inputs.get("citations") is not None
        else None
    )
    audit = _citation_report(
        store, research_id, claims=claims, citations=wired_citations,
        evidence=evidence,
        as_of=str(context.config.get("asOf") or "") or None,
        freshness=str(context.config.get("freshness") or "") or None,
        require_citations=bool(context.config.get("requireCitations", True)),
    )
    issues = [str(issue) for issue in (audit.get("issues") or [])]
    context.emit(f"citation audit {'ok' if audit.get('ok') else 'failed'} with {len(issues)} issue(s)")
    return {
        "audit": audit,
        "issues": issues[:limit],
        "summary": {
            "researchId": research_id,
            "ok": bool(audit.get("ok")),
            "coverage": audit.get("coverage"),
            "issues": len(issues),
            "status": "OK",
        },
    }


def exec_supersession(context: NodeExecContext) -> dict[str, Any]:
    store = _require_store()
    research_id = _research_id(context)
    rows = _evidence_rows(context, research_id)

    class _ChainItem:
        def __init__(self, row: dict[str, Any]) -> None:
            provenance = _decode(row.get("provenance"), {}) or {}
            self.id = str(row.get("evidenceId") or "")
            self.kind = "filing" if _source_type(row.get("sourceType")) in (
                SourceType.OFFICIAL_FILING, SourceType.GOVERNMENT, SourceType.REGULATOR,
            ) else "structured"
            self.supersedesEvidenceId = provenance.get("supersedesEvidenceId")
            self.relationshipKind = provenance.get("relationshipKind")
            self.publishedAt = row.get("publishedAt")
            self.documentId = row.get("documentId")
            metric = provenance.get("metric") or row.get("claimText")
            self.objects = [SimpleNamespace(
                name=metric,
                period=row.get("period"),
                instrument=row.get("entityId"),
            )] if metric else []

    chain = supersession.build_chain([_ChainItem(row) for row in rows])
    payload = asdict(chain)
    context.emit(
        f"revision chain {chain.coverage} with {len(chain.links)} link(s)"
    )
    return {
        "chain": payload,
        "summary": {
            "researchId": research_id,
            "coverage": chain.coverage,
            "links": len(chain.links),
            "issues": len(chain.issues),
            "status": "OK",
        },
    }


def exec_quality(context: NodeExecContext) -> dict[str, Any]:
    store = _require_store()
    research_id = _research_id(context)
    limit = _limit_of(context, 1_000)
    sources = _pick(context, "sources", store.list_sources(research_id))
    evidence_rows = _pick(context, "evidence", store.list_evidence(research_id))
    claims = (
        [_claim_model(row) for row in _rows(context.inputs.get("claims"))]
        if context.inputs.get("claims") is not None
        else _stored_claims(store, research_id)
    )
    conflicts = _conflict_models(store, research_id)
    evidence = []
    for row in evidence_rows:
        try:
            evidence.append(_evidence_model(row))
        except ValueError:
            continue
    questions = store.list_questions(research_id)
    required = [question for question in questions if question.get("required")]
    answered = [question for question in required if question.get("answered")]
    coverage = {
        "answeredQuestions": len(answered),
        "questionsTotal": len(questions),
        "status": "COMPLETE" if required and len(answered) == len(required) else "PARTIAL",
        "unmet": [],
    }
    report = _citation_report(
        store, research_id, claims=claims, evidence=evidence,
        freshness=str(context.config.get("freshness") or "") or None,
    )
    quality = web_quality.compute_quality(
        coverage=coverage,
        sources=sources,
        evidence=evidence[:limit],
        claims=claims,
        conflicts=conflicts,
        citation_report=report,
        freshness=str(context.config.get("freshness") or "") or None,
    )
    context.emit(f"research quality {quality['score']:.2f} ({quality['band']})")
    return {
        "quality": quality,
        "summary": {
            "researchId": research_id,
            "score": quality["score"],
            "band": quality["band"],
            "verdict": quality["verdict"],
            "status": "OK",
        },
    }


def exec_entities(context: NodeExecContext) -> dict[str, Any]:
    store = _require_store()
    research_id = _research_id(context)
    limit = _limit_of(context, 200)
    name = str(context.config.get("name") or "").strip()
    kind = str(context.config.get("kind") or "").strip().lower()
    entities = store.find_entity(name) if name else store.list_entities(research_id)
    entities = [
        row for row in entities
        if row.get("researchId") in (None, "", research_id) or name
    ]
    if kind:
        entities = [row for row in entities if str(row.get("kind") or "").lower() == kind]
    relations = store.list_relations(research_id)
    anchored_entities = sum(1 for row in entities if row.get("evidenceId"))
    anchored_relations = sum(1 for row in relations if row.get("evidenceId"))
    context.emit(f"{len(entities)} entity/entities and {len(relations)} relation(s)")
    return {
        "entities": entities[:limit],
        "relations": relations[:limit],
        "summary": {
            "researchId": research_id,
            "entities": len(entities),
            "relations": len(relations),
            "unanchoredEntities": len(entities) - anchored_entities,
            "unanchoredRelations": len(relations) - anchored_relations,
            "truncated": len(entities) > limit or len(relations) > limit,
            "status": "OK",
        },
    }


def _snapshot_rows(store: Any, research_id: str, name: str) -> Optional[list[dict[str, Any]]]:
    snapshot = store.get_snapshot(research_id)
    payload = (snapshot or {}).get("payload")
    if not isinstance(payload, dict):
        return None
    rows = payload.get(name)
    if isinstance(rows, list):
        return [row for row in rows if isinstance(row, dict)]
    return None


def _section_rows(
    store: Any, research_id: str, name: str, live: list[dict[str, Any]], use_snapshots: bool,
) -> list[dict[str, Any]]:
    if use_snapshots:
        snapshotted = _snapshot_rows(store, research_id, name)
        if snapshotted is not None:
            return snapshotted
    return live


def _evidence_key(row: dict[str, Any], by_content_hash: bool) -> str:
    if by_content_hash and row.get("contentHash"):
        return str(row["contentHash"])
    return str(row.get("evidenceId") or row.get("id") or row.get("sourceUrl") or "")


def _claim_key(row: dict[str, Any]) -> str:
    text = " ".join(str(row.get("text") or "").lower().split())
    return text or str(row.get("id") or "")


def _conflict_key(row: dict[str, Any]) -> str:
    return f"{str(row.get('metric') or '').strip().lower()}|{str(row.get('period') or '').strip()}"


def exec_diff(context: NodeExecContext) -> dict[str, Any]:
    store = _require_store()
    base_id = str(
        context.inputs.get("baseId") or context.config.get("baseId") or ""
    ).strip()
    compare_id = str(
        context.inputs.get("compareId") or context.config.get("compareId") or ""
    ).strip()
    if not base_id or not compare_id:
        raise ValueError("baseId and compareId are required")
    base_run = store.get_run(base_id)
    compare_run = store.get_run(compare_id)
    if base_run is None:
        raise ValueError(f"research run {base_id!r} was not found")
    if compare_run is None:
        raise ValueError(f"research run {compare_id!r} was not found")
    def normalize(text: Any) -> str:
        return " ".join(str(text or "").lower().split())
    if normalize(base_run.get("question")) != normalize(compare_run.get("question")):
        raise ValueError(
            "incomparable runs: the two runs answer different questions"
        )

    limit = _limit_of(context, 200)
    by_content_hash = bool(context.config.get("byContentHash", True))
    use_snapshots = bool(context.config.get("useSnapshots", True))

    base_evidence = _section_rows(
        store, base_id, "evidence", store.list_evidence(base_id), use_snapshots,
    )
    compare_evidence = _section_rows(
        store, compare_id, "evidence", store.list_evidence(compare_id), use_snapshots,
    )
    base_by_key = {_evidence_key(row, by_content_hash): row for row in base_evidence}
    compare_by_key = {_evidence_key(row, by_content_hash): row for row in compare_evidence}
    added_keys = [key for key in compare_by_key if key not in base_by_key]
    removed_keys = [key for key in base_by_key if key not in compare_by_key]

    base_claims = _section_rows(store, base_id, "claims", store.list_claims(base_id), use_snapshots)
    compare_claims = _section_rows(
        store, compare_id, "claims", store.list_claims(compare_id), use_snapshots,
    )
    base_claim_map = {_claim_key(row): row for row in base_claims}
    compare_claim_map = {_claim_key(row): row for row in compare_claims}
    status_changes = []
    for key in sorted(set(base_claim_map) & set(compare_claim_map)):
        before = str(base_claim_map[key].get("status") or "UNKNOWN").upper()
        after = str(compare_claim_map[key].get("status") or "UNKNOWN").upper()
        if before != after:
            status_changes.append({
                "text": base_claim_map[key].get("text"),
                "from": before,
                "to": after,
            })

    base_conflicts = _section_rows(
        store, base_id, "conflicts", _conflict_rows(store, base_id), use_snapshots,
    )
    compare_conflicts = _section_rows(
        store, compare_id, "conflicts", _conflict_rows(store, compare_id), use_snapshots,
    )
    def _unresolved(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        return {
            _conflict_key(row): row for row in rows
            if _conflict_status(row.get("status")) == "UNRESOLVED"
            and bool(row.get("material", True))
        }
    base_open = _unresolved(base_conflicts)
    compare_open = _unresolved(compare_conflicts)
    opened = [row for key, row in compare_open.items() if key not in base_open]
    resolved = [row for key, row in base_open.items() if key not in compare_open]
    still_open = [row for key, row in compare_open.items() if key in base_open]

    base_sources = _section_rows(store, base_id, "sources", store.list_sources(base_id), use_snapshots)
    compare_sources = _section_rows(
        store, compare_id, "sources", store.list_sources(compare_id), use_snapshots,
    )
    base_urls = {str(row.get("canonicalUrl") or "") for row in base_sources}
    compare_urls = {str(row.get("canonicalUrl") or "") for row in compare_sources}

    base_summary = _summary(store, base_id)
    compare_summary = _summary(store, compare_id)
    delta = {
        "evidence": compare_summary["evidence"] - base_summary["evidence"],
        "claims": compare_summary["claims"] - base_summary["claims"],
        "questionCoverage": round(
            compare_summary["questionCoverage"] - base_summary["questionCoverage"], 4,
        ),
        "claimSupport": round(
            compare_summary["claimSupport"] - base_summary["claimSupport"], 4,
        ),
        "unresolvedConflicts": (
            compare_summary["unresolvedConflicts"] - base_summary["unresolvedConflicts"]
        ),
        "verdict": [base_summary["verdict"], compare_summary["verdict"]],
    }
    diff = {
        "baseId": base_id,
        "compareId": compare_id,
        "question": base_run.get("question"),
        "byContentHash": by_content_hash,
        "usedSnapshots": use_snapshots and (
            _snapshot_rows(store, base_id, "evidence") is not None
            or _snapshot_rows(store, compare_id, "evidence") is not None
        ),
        "evidence": {
            "added": added_keys[:limit],
            "removed": removed_keys[:limit],
            "addedRows": [compare_by_key[key] for key in added_keys[:limit]],
            "removedRows": [base_by_key[key] for key in removed_keys[:limit]],
        },
        "claims": {
            "added": [row.get("text") for row in compare_claims if _claim_key(row) not in base_claim_map][:limit],
            "removed": [row.get("text") for row in base_claims if _claim_key(row) not in compare_claim_map][:limit],
            "statusChanges": status_changes[:limit],
        },
        "conflicts": {
            "opened": opened[:limit],
            "resolved": resolved[:limit],
            "stillOpen": still_open[:limit],
        },
        "sources": {
            "added": sorted(url for url in compare_urls - base_urls if url)[:limit],
            "removed": sorted(url for url in base_urls - compare_urls if url)[:limit],
        },
        "coverage": {"base": base_summary, "compare": compare_summary, "delta": delta},
    }
    context.emit(
        f"diff {base_id} → {compare_id}: +{len(added_keys)} evidence, "
        f"{len(status_changes)} claim change(s), {len(opened)} opened conflict(s)"
    )
    return {
        "diff": diff,
        "summary": {
            "baseId": base_id,
            "compareId": compare_id,
            "addedEvidence": len(added_keys),
            "removedEvidence": len(removed_keys),
            "statusChanges": len(status_changes),
            "openedConflicts": len(opened),
            "resolvedConflicts": len(resolved),
            "addedSources": len(compare_urls - base_urls),
            "removedSources": len(base_urls - compare_urls),
            "verdict": delta["verdict"],
            "status": "OK",
        },
    }


def exec_claims_verify(context: NodeExecContext) -> dict[str, Any]:
    store = _require_store()
    research_id = _research_id(context)
    limit = _limit_of(context, 200)
    claims = (
        [_claim_model(row) for row in _rows(context.inputs.get("claims"))]
        if context.inputs.get("claims") is not None
        else _stored_claims(store, research_id)
    )
    evidence = {
        row["evidenceId"]: _evidence_model(row)
        for row in store.list_evidence(research_id)
        if row.get("evidenceId")
    }
    conflicts = _conflict_models(store, research_id)
    as_of = str(context.config.get("asOf") or "") or None
    freshness = str(context.config.get("freshness") or "") or None
    verified: list[dict[str, Any]] = []
    counts: dict[str, int] = {}
    for claim in claims[:limit]:
        checked = web_verify.verify_claim(
            claim, evidence, conflicts=conflicts, as_of=as_of, freshness=freshness,
        )
        verified.append(checked.model_dump())
        counts[checked.status] = counts.get(checked.status, 0) + 1
    context.emit(f"verified {len(verified)} claim(s): {counts}")
    return {
        "claims": verified,
        "summary": {
            "researchId": research_id,
            "total": len(claims),
            "verified": len(verified),
            "byStatus": counts,
            "truncated": len(verified) < len(claims),
            "status": "EMPTY" if not claims else "OK",
        },
    }


# ── Definitions ──────────────────────────────────────────────────────────────

def _research_input() -> tuple[PortDef, ...]:
    return (PortDef(id="researchId", name="Research id", type=PortType.STRING, optional=True),)


def build_research_analysis_nodes() -> list[NodeDef]:
    return [
        NodeDef(
            type="research.latest", version="1.0.0", label="Resolve research run",
            category="research",
            inputs=(PortDef(id="question", name="Question", type=PortType.STRING, optional=True),),
            outputs=(
                PortDef(id="researchId", name="Research id", type=PortType.STRING),
                PortDef(id="run", name="Run", type=PortType.OBJECT),
                PortDef(id="summary", name="Summary", type=PortType.OBJECT),
            ),
            config_fields=(
                ConfigField("researchId", "string", "", max_length=200),
                ConfigField("questionMatch", "string", "", max_length=500),
                ConfigField("latest", "boolean", True),
                ConfigField("limit", "integer", 20, minimum=1, maximum=50),
            ),
            capabilities=("research.read",),
            side_effects=SideEffect.READ,
            allowed_modes=_ALL,
            executor=exec_latest,
            metadata={"docs": "Resolves an exact research id or the newest run whose question contains the match. No match is an explicit error, never an empty run."},
        ),
        NodeDef(
            type="research.sources", version="1.0.0", label="Sources",
            category="research",
            inputs=_research_input(),
            outputs=(
                PortDef(id="sources", name="Sources", type=PortType.ARRAY),
                PortDef(id="summary", name="Summary", type=PortType.OBJECT),
            ),
            config_fields=(
                ConfigField("researchId", "string", "", max_length=200),
                ConfigField("limit", "integer", 200, minimum=1, maximum=MAX_ITEMS),
                ConfigField("domain", "string", "", max_length=200),
                ConfigField("sourceType", "string", "", max_length=80),
                ConfigField("publishedAfter", "string", "", max_length=40),
                ConfigField("dedupe", "boolean", True),
            ),
            capabilities=("research.read",),
            side_effects=SideEffect.READ,
            allowed_modes=_ALL,
            executor=exec_sources,
            metadata={"docs": "Reads stored sources with domain/type/date filters and content/family dedupe. Undated rows are excluded by publishedAfter and counted, never silently dropped."},
        ),
        NodeDef(
            type="research.gaps", version="1.0.0", label="Coverage gaps",
            category="research",
            inputs=_research_input(),
            outputs=(
                PortDef(id="gaps", name="Gaps", type=PortType.ARRAY),
                PortDef(id="summary", name="Summary", type=PortType.OBJECT),
            ),
            config_fields=(
                ConfigField("researchId", "string", "", max_length=200),
                ConfigField("includeOptional", "boolean", False),
                ConfigField("limit", "integer", 100, minimum=1, maximum=500),
            ),
            capabilities=("research.read",),
            side_effects=SideEffect.READ,
            allowed_modes=_ALL,
            executor=exec_gaps,
            metadata={"docs": "Names what is still missing: unanswered required questions, rejected claims and uncited material claims. Pairs with logic.condition to drive a bounded re-research loop."},
        ),
        NodeDef(
            type="research.freshness", version="1.0.0", label="Point-in-time filter",
            category="research",
            inputs=(
                PortDef(id="evidence", name="Evidence", type=PortType.ARRAY, optional=True),
                PortDef(id="researchId", name="Research id", type=PortType.STRING, optional=True),
            ),
            outputs=(
                PortDef(id="evidence", name="Admissible evidence", type=PortType.ARRAY),
                PortDef(id="rejected", name="Rejected", type=PortType.ARRAY),
                PortDef(id="summary", name="Summary", type=PortType.OBJECT),
            ),
            config_fields=(
                ConfigField("researchId", "string", "", max_length=200),
                ConfigField("asOf", "string", "", max_length=40),
                ConfigField("freshness", "string", "", max_length=40),
                ConfigField("limit", "integer", 100, minimum=1, maximum=MAX_ITEMS),
            ),
            capabilities=("research.read",),
            side_effects=SideEffect.READ,
            allowed_modes=_ALL,
            executor=exec_freshness,
            metadata={"docs": "Applies the engine's fail-closed point-in-time and freshness rules. Every rejected item keeps its exact reason."},
        ),
        NodeDef(
            type="research.conflict_scan", version="1.0.0", label="Scan conflicts",
            category="research",
            inputs=(
                PortDef(id="evidence", name="Evidence", type=PortType.ARRAY, optional=True),
                PortDef(id="researchId", name="Research id", type=PortType.STRING, optional=True),
            ),
            outputs=(
                PortDef(id="conflicts", name="Conflicts", type=PortType.ARRAY),
                PortDef(id="summary", name="Summary", type=PortType.OBJECT),
            ),
            config_fields=(
                ConfigField("researchId", "string", "", max_length=200),
                ConfigField("tolerance", "number", 0.01, minimum=0, maximum=1),
                ConfigField("mergeStored", "boolean", True),
                ConfigField("limit", "integer", 200, minimum=1, maximum=MAX_ITEMS),
            ),
            capabilities=("research.read",),
            side_effects=SideEffect.READ,
            allowed_modes=_ALL,
            executor=exec_conflict_scan,
            metadata={"docs": "Runs the deterministic conflict detector over evidence that was never scanned and optionally merges stored conflicts. Reports disagreement; never picks a winner and never writes."},
        ),
        NodeDef(
            type="research.citation_audit", version="1.0.0", label="Audit citations",
            category="research",
            inputs=(
                PortDef(id="researchId", name="Research id", type=PortType.STRING, optional=True),
                PortDef(id="claims", name="Claims", type=PortType.ARRAY, optional=True),
                PortDef(id="citations", name="Citations", type=PortType.ARRAY, optional=True),
                PortDef(id="evidence", name="Evidence", type=PortType.ARRAY, optional=True),
            ),
            outputs=(
                PortDef(id="audit", name="Audit", type=PortType.OBJECT),
                PortDef(id="issues", name="Issues", type=PortType.ARRAY),
                PortDef(id="summary", name="Summary", type=PortType.OBJECT),
            ),
            config_fields=(
                ConfigField("researchId", "string", "", max_length=200),
                ConfigField("requireCitations", "boolean", True),
                ConfigField("asOf", "string", "", max_length=40),
                ConfigField("freshness", "string", "", max_length=40),
                ConfigField("limit", "integer", 500, minimum=1, maximum=MAX_ITEMS),
            ),
            capabilities=("research.read",),
            side_effects=SideEffect.READ,
            allowed_modes=_ALL,
            executor=exec_citation_audit,
            metadata={"docs": "Checks that every material claim is traceable: builds citations when none are wired, then validates coverage, evidence existence, URL match and point-in-time admissibility."},
        ),
        NodeDef(
            type="research.supersession", version="1.0.0", label="Revision chain",
            category="research",
            inputs=(
                PortDef(id="evidence", name="Evidence", type=PortType.ARRAY, optional=True),
                PortDef(id="researchId", name="Research id", type=PortType.STRING, optional=True),
            ),
            outputs=(
                PortDef(id="chain", name="Chain", type=PortType.OBJECT),
                PortDef(id="summary", name="Summary", type=PortType.OBJECT),
            ),
            config_fields=(
                ConfigField("researchId", "string", "", max_length=200),
                ConfigField("limit", "integer", 500, minimum=1, maximum=MAX_ITEMS),
            ),
            capabilities=("research.read",),
            side_effects=SideEffect.READ,
            allowed_modes=_ALL,
            executor=exec_supersession,
            metadata={"docs": "Builds the restatement/amendment chain from recorded revision metadata. coverage is unavailable when no revision metadata exists — never an empty 'no revisions' claim."},
        ),
        NodeDef(
            type="research.quality", version="1.0.0", label="Quality score",
            category="research",
            inputs=(
                PortDef(id="researchId", name="Research id", type=PortType.STRING, optional=True),
                PortDef(id="sources", name="Sources", type=PortType.ARRAY, optional=True),
                PortDef(id="evidence", name="Evidence", type=PortType.ARRAY, optional=True),
                PortDef(id="claims", name="Claims", type=PortType.ARRAY, optional=True),
            ),
            outputs=(
                PortDef(id="quality", name="Quality", type=PortType.OBJECT),
                PortDef(id="summary", name="Summary", type=PortType.OBJECT),
            ),
            config_fields=(
                ConfigField("researchId", "string", "", max_length=200),
                ConfigField("freshness", "string", "", max_length=40),
                ConfigField("limit", "integer", 1_000, minimum=1, maximum=MAX_ITEMS),
            ),
            capabilities=("research.read",),
            side_effects=SideEffect.READ,
            allowed_modes=_ALL,
            executor=exec_quality,
            metadata={"docs": "Aggregates the engine's explainable quality score (components, weights, contributions). It is an INTERNAL heuristic with its disclaimer attached, never a measure of truth."},
        ),
        NodeDef(
            type="research.entities", version="1.0.0", label="Entities & relations",
            category="research",
            inputs=_research_input(),
            outputs=(
                PortDef(id="entities", name="Entities", type=PortType.ARRAY),
                PortDef(id="relations", name="Relations", type=PortType.ARRAY),
                PortDef(id="summary", name="Summary", type=PortType.OBJECT),
            ),
            config_fields=(
                ConfigField("researchId", "string", "", max_length=200),
                ConfigField("name", "string", "", max_length=200),
                ConfigField("kind", "string", "", max_length=80),
                ConfigField("limit", "integer", 200, minimum=1, maximum=MAX_ITEMS),
            ),
            capabilities=("research.read",),
            side_effects=SideEffect.READ,
            allowed_modes=_ALL,
            executor=exec_entities,
            metadata={"docs": "Reads the evidence-anchored entity/relation graph. Rows without an evidenceId are returned but counted unanchored; the reader never hides an ungrounded node."},
        ),
        NodeDef(
            type="research.diff", version="1.0.0", label="Compare runs",
            category="research",
            inputs=(
                PortDef(id="baseId", name="Base research id", type=PortType.STRING, optional=True),
                PortDef(id="compareId", name="Compare research id", type=PortType.STRING, optional=True),
            ),
            outputs=(
                PortDef(id="diff", name="Diff", type=PortType.OBJECT),
                PortDef(id="summary", name="Summary", type=PortType.OBJECT),
            ),
            config_fields=(
                ConfigField("baseId", "string", "", max_length=200),
                ConfigField("compareId", "string", "", max_length=200),
                ConfigField("byContentHash", "boolean", True),
                ConfigField("useSnapshots", "boolean", True),
                ConfigField("limit", "integer", 200, minimum=1, maximum=1_000),
            ),
            capabilities=("research.read",),
            side_effects=SideEffect.READ,
            allowed_modes=_ALL,
            executor=exec_diff,
            metadata={"docs": "Deterministic comparison of two runs answering the SAME question: added/removed evidence by content hash, claim-status changes, opened/resolved conflicts, source changes and coverage deltas. Different questions are refused as incomparable."},
        ),
        NodeDef(
            type="research.claims_verify", version="1.0.0", label="Verify claims (batch)",
            category="research",
            inputs=(
                PortDef(id="researchId", name="Research id", type=PortType.STRING, optional=True),
                PortDef(id="claims", name="Claims", type=PortType.ARRAY, optional=True),
            ),
            outputs=(
                PortDef(id="claims", name="Verified claims", type=PortType.ARRAY),
                PortDef(id="summary", name="Summary", type=PortType.OBJECT),
            ),
            config_fields=(
                ConfigField("researchId", "string", "", max_length=200),
                ConfigField("asOf", "string", "", max_length=40),
                ConfigField("freshness", "string", "", max_length=40),
                ConfigField("limit", "integer", 200, minimum=1, maximum=200),
            ),
            capabilities=("research.read",),
            side_effects=SideEffect.READ,
            allowed_modes=_ALL,
            executor=exec_claims_verify,
            metadata={"docs": "Runs the deterministic verifier over many claims with the run's conflicts and point-in-time rules applied. A claim with no evidence is UNSUPPORTED, never skipped."},
        ),
    ]


__all__ = [
    "build_research_analysis_nodes",
    "exec_latest",
    "exec_sources",
    "exec_gaps",
    "exec_freshness",
    "exec_conflict_scan",
    "exec_citation_audit",
    "exec_supersession",
    "exec_quality",
    "exec_entities",
    "exec_diff",
    "exec_claims_verify",
]
