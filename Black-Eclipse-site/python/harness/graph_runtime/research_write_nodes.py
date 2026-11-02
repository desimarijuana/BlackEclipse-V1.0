"""Local research write nodes (Wave C).

Bounded, deterministic writes over the existing `EvidenceStore`:

- `research.start_run` gives a cold graph a real run row (question/objective/
  as-of) so the local read nodes and `research.report` have an owner. It is
  idempotent: the same question/objective resolves to the same run id.
- `research.snapshot` freezes a run's evidence graph into the store's immutable
  snapshot table, for reproducibility and later diffing.
- `research.ingest` normalizes an EXTERNAL payload (an `agent.research` blob, an
  MCP tool result, a manual claim set) into the store. Everything it writes is
  marked with its origin and `eclipseVerified: false`; it never verifies a claim
  and never copies an external answer as the run's answer.

All of them declare `research.write`, which is deliberately NOT in
`TEST_RUN_CAPABILITIES`: a test run is refused by the existing capability gate.
No network request and no model call.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any
from urllib.parse import urlsplit

from ..research.web_contracts import (
    Evidence,
    SourceType,
    content_hash,
    evidence_id,
    source_id,
)
from .model import ExecutionMode, PortDef, PortType, SideEffect
from .registry import ConfigField, NodeDef, NodeExecContext
from .research_nodes import _require_store, _research_id

_ALL = tuple(ExecutionMode)
_SECTIONS = ("sources", "evidence", "claims", "citations", "conflicts", "questions")
_CLAIM_STATUSES = {
    "SUPPORTED", "PARTIALLY_SUPPORTED", "CONTRADICTED", "UNSUPPORTED",
    "OUTDATED", "AMBIGUOUS", "CALCULATED", "INFERRED",
}
_CLAIM_KINDS = {"FACT", "CALCULATION", "INFERENCE", "OPINION", "UNCERTAINTY"}


def _run_id(question: str, objective: str) -> str:
    digest = hashlib.sha256(f"{question.strip()}\n{objective.strip()}".encode("utf-8"))
    return f"r_{digest.hexdigest()[:16]}"


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, dict):
        return [value]
    return []


def _number(value: Any) -> float:
    try:
        return max(0.0, min(float(value), 1.0))
    except (TypeError, ValueError):
        return 0.0


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


def _objects_value(objects: Any) -> tuple[Any, Any, Any, Any]:
    """The first normalized object's (structuredValue, period, unit, metric)."""
    for item in _as_list(objects):
        if not isinstance(item, dict):
            continue
        metric = item.get("name") or item.get("metric")
        value = item.get("value")
        if metric is None and value is None:
            continue
        structured = {"metric": metric, "value": value}
        return structured, item.get("period"), item.get("unit"), metric
    return None, None, None, None


def _external_evidence(row: Any, origin: str) -> tuple[dict[str, Any] | None, str | None]:
    """Normalize one external evidence-shaped row, or name why it is skipped."""
    if not isinstance(row, dict):
        return None, "evidence item is not an object"
    source = row.get("source") if isinstance(row.get("source"), dict) else {}
    url = str(
        row.get("sourceUrl") or row.get("url") or source.get("url") or ""
    ).strip()
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        return None, "evidence item has no absolute http(s) source URL"

    summary = str(row.get("summary") or row.get("claimText") or "").strip()
    raw_text = str(row.get("rawText") or row.get("text") or summary or "").strip()
    structured, object_period, object_unit, object_metric = _objects_value(
        row.get("objects")
    )
    structured_value = row.get("structuredValue")
    if structured_value is None:
        structured_value = structured
    provenance = row.get("provenance") if isinstance(row.get("provenance"), dict) else {}
    provenance = {
        **provenance,
        "origin": origin,
        "external": True,
        "eclipseVerified": False,
    }
    if source:
        provenance["retrievalSource"] = source.get("source")
        provenance["validationStatus"] = source.get("validationStatus")
    if object_metric and "metric" not in provenance:
        provenance["metric"] = object_metric

    payload = {
        "evidenceId": str(row.get("evidenceId") or evidence_id(
            source_url=url, raw_text=raw_text or json.dumps(structured_value, default=str),
        )),
        "sourceId": str(row.get("sourceId") or source_id(url)),
        "sourceUrl": url,
        "sourceType": _source_type(row.get("sourceType")),
        "publisher": row.get("publisher"),
        "entityId": row.get("entityId"),
        "publishedAt": row.get("publishedAt") or source.get("publishedAt"),
        "updatedAt": row.get("updatedAt"),
        "effectiveAt": row.get("effectiveAt"),
        "knownAt": row.get("knownAt"),
        "retrievedAt": str(row.get("retrievedAt") or source.get("retrievedAt") or ""),
        "documentId": row.get("documentId"),
        "page": row.get("page"),
        "section": row.get("section"),
        "rawText": raw_text,
        "claimText": row.get("claimText") or (summary or None),
        "structuredValue": structured_value,
        "unit": row.get("unit") or object_unit,
        "period": row.get("period") or object_period,
        "contentHash": str(row.get("contentHash") or content_hash(raw_text or url)),
        "confidence": _number(row.get("confidence")),
        "contentTrust": "UNTRUSTED",
        "provenance": provenance,
    }
    try:
        return Evidence(**payload).model_dump(), None
    except Exception as exc:  # noqa: BLE001 - a malformed external row is skipped, not trusted
        return None, f"evidence item is not a valid Evidence contract: {exc}"


def _external_claim(row: Any, origin: str) -> tuple[dict[str, Any] | None, str | None]:
    if not isinstance(row, dict):
        return None, "claim is not an object"
    text = str(row.get("text") or row.get("claimText") or "").strip()
    if not text:
        return None, "claim has no text"
    digest = hashlib.sha256(f"{origin}\n{text}".encode("utf-8")).hexdigest()[:16]
    evidence_ids = row.get("evidenceIds")
    if isinstance(evidence_ids, str):
        evidence_ids = [part.strip() for part in evidence_ids.split(",") if part.strip()]
    return {
        "id": str(row.get("id") or row.get("claimId") or f"cl_{digest}"),
        "text": text,
        "kind": _claim_kind(row.get("kind")),
        "status": _claim_status(row.get("status")),
        "confidence": _number(row.get("confidence")),
        "calculationId": row.get("calculationId"),
        "issues": ["ingested from an external source; not Eclipse-verified"],
        "evidenceIds": [str(item) for item in (evidence_ids or []) if item],
    }, None


def _external_source(row: Any) -> tuple[dict[str, Any] | None, str | None]:
    if not isinstance(row, dict):
        return None, "source is not an object"
    url = str(
        row.get("canonicalUrl") or row.get("url") or row.get("sourceUrl") or ""
    ).strip()
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        return None, "source has no absolute http(s) URL"
    from ..research.web_sources import make_source  # noqa: PLC0415

    source = make_source(url, title=row.get("title")).model_dump()
    if row.get("publishedAt"):
        source["publishedAt"] = row.get("publishedAt")
    if row.get("publisher"):
        source["publisher"] = row.get("publisher")
    if row.get("sourceType"):
        source["sourceType"] = _source_type(row.get("sourceType")).value
    return source, None


def exec_start_run(context: NodeExecContext) -> dict[str, Any]:
    store = _require_store()
    question = str(
        context.inputs.get("question") or context.config.get("question") or ""
    ).strip()
    objective = str(context.config.get("objective") or "").strip()
    requested = str(context.config.get("researchId") or "").strip()
    if not question and not requested:
        raise ValueError("question is required: wire it in or set the node's question")

    research_id = requested or _run_id(question, objective)
    existing = store.get_run(research_id)
    if existing is not None:
        context.emit(f"research run {research_id} already exists")
        return {
            "researchId": research_id,
            "run": existing,
            "summary": {
                "researchId": research_id,
                "created": False,
                "status": existing.get("status") or existing.get("state") or "UNKNOWN",
            },
        }

    run = {
        "researchId": research_id,
        "question": question or research_id,
        "objective": objective or None,
        "depth": str(context.config.get("depth") or "") or None,
        "state": "PLANNING",
        "pointInTime": str(context.config.get("asOf") or "") or None,
        "freshness": str(context.config.get("freshness") or "") or None,
        "status": "PLANNING",
    }
    store.save_run(run)
    context.emit(f"created research run {research_id}")
    return {
        "researchId": research_id,
        "run": store.get_run(research_id) or run,
        "summary": {
            "researchId": research_id,
            "created": True,
            "question": question,
            "status": "PLANNING",
        },
    }


def exec_snapshot(context: NodeExecContext) -> dict[str, Any]:
    store = _require_store()
    research_id = _research_id(context)
    raw_sections = context.config.get("include", "all")
    if isinstance(raw_sections, str):
        sections = [part.strip() for part in raw_sections.split(",") if part.strip()]
    elif isinstance(raw_sections, (list, tuple)):
        sections = [str(part).strip() for part in raw_sections if str(part).strip()]
    else:
        raise ValueError("include must be a comma-separated list or an array")
    if not sections or "all" in sections:
        sections = list(_SECTIONS)
    unknown = [name for name in sections if name not in _SECTIONS]
    if unknown:
        raise ValueError(f"unknown snapshot section(s): {', '.join(unknown)}")

    run = store.get_run(research_id)
    if run is None:
        raise ValueError(
            f"research run {research_id!r} was not found; create it with research.start_run"
        )
    payload: dict[str, Any] = {
        "researchId": research_id,
        "run": run,
        "sections": sections,
    }
    readers = {
        "sources": store.list_sources,
        "evidence": store.list_evidence,
        "claims": store.list_claims,
        "citations": store.list_citations,
        "conflicts": store.list_conflicts,
        "questions": store.list_questions,
    }
    for name in sections:
        payload[name] = readers[name](research_id)
    snapshot_id = store.create_snapshot(research_id, payload)
    snapshots = store.list_snapshots(research_id)
    version = int(snapshots[-1]["version"]) if snapshots else 0
    context.emit(f"snapshotted {research_id} as {snapshot_id} (v{version})")
    return {
        "snapshotId": snapshot_id,
        "version": version,
        "summary": {
            "researchId": research_id,
            "sections": sections,
            "counts": {name: len(payload.get(name) or []) for name in sections},
            "status": "OK",
        },
    }


def exec_ingest(context: NodeExecContext) -> dict[str, Any]:
    store = _require_store()
    try:
        limit = int(context.config.get("limit", 200))
    except (TypeError, ValueError) as exc:
        raise ValueError("limit must be a whole number") from exc
    limit = max(1, min(limit, 200))
    origin = str(context.config.get("sourceLabel") or "external").strip() or "external"
    payload = context.inputs.get("research")
    payload = payload if isinstance(payload, dict) else {}

    requested = str(
        context.inputs.get("researchId") or context.config.get("researchId") or ""
    ).strip()
    question = str(
        payload.get("question") or payload.get("objective") or context.config.get("question") or ""
    ).strip()
    if not requested:
        if not question:
            raise ValueError(
                "researchId is required when the ingested payload has no question"
            )
        requested = _run_id(question, origin)
    research_id = requested

    create_run = bool(context.config.get("createRun", True))
    created = False
    if create_run and store.get_run(research_id) is None:
        store.save_run({
            "researchId": research_id,
            "question": question or f"Ingested external research ({origin})",
            "objective": origin,
            "state": "PLANNING",
            "status": "INGESTED",
        })
        created = True

    # Explicit inputs win by being appended after the payload's arrays; the store
    # upserts by content-derived id, so ingesting the same payload twice is safe.
    source_rows = _as_list(context.inputs.get("sources")) + _as_list(payload.get("sources"))
    evidence_rows = _as_list(context.inputs.get("evidence")) + _as_list(payload.get("evidence"))
    claim_rows = _as_list(context.inputs.get("claims")) + _as_list(payload.get("claims"))

    skipped: list[dict[str, Any]] = []
    saved_sources = 0
    for row in source_rows[:limit]:
        source, reason = _external_source(row)
        if source is None:
            skipped.append({"type": "source", "reason": reason})
            continue
        store.save_source(source, research_id=research_id)
        saved_sources += 1

    saved_evidence: list[str] = []
    for row in evidence_rows[:limit]:
        evidence, reason = _external_evidence(row, origin)
        if evidence is None:
            skipped.append({"type": "evidence", "reason": reason})
            continue
        store.save_evidence(evidence, research_id=research_id)
        saved_evidence.append(str(evidence["evidenceId"]))
        if evidence.get("sourceUrl"):
            source, _ = _external_source({
                "url": evidence["sourceUrl"],
                "title": evidence.get("claimText"),
                "publishedAt": evidence.get("publishedAt"),
            })
            if source is not None:
                store.save_source(source, research_id=research_id)

    saved_claims = 0
    known_evidence = {
        str(row.get("evidenceId")) for row in store.list_evidence(research_id)
        if row.get("evidenceId")
    }
    for row in claim_rows[:limit]:
        claim, reason = _external_claim(row, origin)
        if claim is None:
            skipped.append({"type": "claim", "reason": reason})
            continue
        store.save_claim(research_id, claim)
        for evidence_ref in claim.get("evidenceIds") or []:
            if evidence_ref in known_evidence:
                store.link_claim_evidence(claim["id"], evidence_ref, "supports")
        saved_claims += 1

    context.emit(
        f"ingested {len(saved_evidence)} evidence, {saved_claims} claim(s) and "
        f"{saved_sources} source(s) from {origin}"
    )
    return {
        "researchId": research_id,
        "evidenceCount": len(saved_evidence),
        "claimCount": saved_claims,
        "sourceCount": saved_sources,
        "summary": {
            "researchId": research_id,
            "origin": origin,
            "createdRun": created,
            "evidence": len(saved_evidence),
            "claims": saved_claims,
            "sources": saved_sources,
            "skipped": len(skipped),
            "skippedRows": skipped[:50],
            "truncated": (
                len(source_rows) > limit
                or len(evidence_rows) > limit
                or len(claim_rows) > limit
            ),
            "verified": False,
            "note": "External sources are ingested with their origin and are NOT Eclipse-verified; run research.claim_verify for a local deterministic check.",
            "status": "OK" if saved_evidence or saved_claims or saved_sources else "EMPTY",
        },
    }


def build_research_write_nodes() -> list[NodeDef]:
    return [
        NodeDef(
            type="research.start_run", version="1.0.0", label="Start research run",
            category="research",
            inputs=(PortDef(id="question", name="Question", type=PortType.STRING, optional=True),),
            outputs=(
                PortDef(id="researchId", name="Research id", type=PortType.STRING),
                PortDef(id="run", name="Run", type=PortType.OBJECT),
                PortDef(id="summary", name="Summary", type=PortType.OBJECT),
            ),
            config_fields=(
                ConfigField("researchId", "string", "", max_length=200),
                ConfigField("question", "string", "", max_length=2_000),
                ConfigField("objective", "string", "", max_length=2_000),
                ConfigField("depth", "string", "", max_length=40),
                ConfigField("asOf", "string", "", max_length=40),
                ConfigField("freshness", "string", "", max_length=40),
            ),
            capabilities=("research.read", "research.write"),
            side_effects=SideEffect.LOCAL_WRITE,
            allowed_modes=_ALL,
            executor=exec_start_run,
            metadata={"docs": "Creates the run row a cold graph needs (question/objective/as-of). Idempotent: the same question and objective resolve to the same id, and an existing run is never overwritten."},
        ),
        NodeDef(
            type="research.snapshot", version="1.0.0", label="Snapshot run",
            category="research",
            inputs=(PortDef(id="researchId", name="Research id", type=PortType.STRING, optional=True),),
            outputs=(
                PortDef(id="snapshotId", name="Snapshot id", type=PortType.STRING),
                PortDef(id="version", name="Version", type=PortType.NUMBER),
                PortDef(id="summary", name="Summary", type=PortType.OBJECT),
            ),
            config_fields=(
                ConfigField("researchId", "string", "", max_length=200),
                ConfigField("include", "string", "all", max_length=200),
            ),
            capabilities=("research.read", "research.write"),
            side_effects=SideEffect.LOCAL_WRITE,
            allowed_modes=_ALL,
            executor=exec_snapshot,
            metadata={"docs": "Freezes the selected sections into the store's immutable snapshot table. A missing run is an explicit error pointing at research.start_run."},
        ),
        NodeDef(
            type="research.ingest", version="1.0.0", label="Ingest external research",
            category="research",
            inputs=(
                PortDef(id="research", name="Research payload", type=PortType.OBJECT, optional=True),
                PortDef(id="evidence", name="Evidence", type=PortType.ARRAY, optional=True),
                PortDef(id="claims", name="Claims", type=PortType.ARRAY, optional=True),
                PortDef(id="sources", name="Sources", type=PortType.ARRAY, optional=True),
                PortDef(id="researchId", name="Research id", type=PortType.STRING, optional=True),
            ),
            outputs=(
                PortDef(id="researchId", name="Research id", type=PortType.STRING),
                PortDef(id="evidenceCount", name="Evidence count", type=PortType.NUMBER),
                PortDef(id="claimCount", name="Claim count", type=PortType.NUMBER),
                PortDef(id="sourceCount", name="Source count", type=PortType.NUMBER),
                PortDef(id="summary", name="Summary", type=PortType.OBJECT),
            ),
            config_fields=(
                ConfigField("researchId", "string", "", max_length=200),
                ConfigField("question", "string", "", max_length=2_000),
                ConfigField("sourceLabel", "string", "external", max_length=200),
                ConfigField("createRun", "boolean", True),
                ConfigField("limit", "integer", 200, minimum=1, maximum=200),
            ),
            capabilities=("research.read", "research.write"),
            side_effects=SideEffect.LOCAL_WRITE,
            allowed_modes=_ALL,
            executor=exec_ingest,
            metadata={"docs": "Normalizes agent/MCP/manual evidence, claims and sources into the store. Every row keeps its origin and eclipseVerified=false; claims are never verified and an external answer is never copied as the run's answer."},
        ),
    ]


__all__ = [
    "build_research_write_nodes",
    "exec_start_run",
    "exec_snapshot",
    "exec_ingest",
]
