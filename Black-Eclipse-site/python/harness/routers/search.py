"""Unified Search HTTP routes (operator-gated).

Thin adapters over the SAME ``SearchService`` the agent tools use, so the UI and
the agent can never disagree and a second index is never built. Every route is
operator-gated (loopback or runtime secret), matching the market/research
routers. Admin routes may search with an unrestricted scope; agent tools never do.
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..search.contracts import MetadataFilter, QueryExpansion, SearchRequest, SearchScope, TemporalFilter
from ..deps import require_operator, service

router = APIRouter(tags=["search"])


def build_request(body: "SearchBody", default_top_k: int = 10) -> SearchRequest:
    namespaces = list(body.namespaces or [])
    if body.namespace and body.namespace not in namespaces:
        namespaces.append(body.namespace)
    filters = MetadataFilter(
        source_types=list(body.source_types or []),
        namespaces=namespaces,
        entity_type=body.entity_type,
        entity_id=body.entity_id,
    )
    temporal = TemporalFilter(
        as_of=body.as_of, published_from=body.published_from, published_to=body.published_to
    )
    scope = SearchScope(
        workspace_id=body.workspace_id, owner_id=body.owner_id, is_operator=body.unrestricted
    )
    return SearchRequest(
        query=body.query,
        mode=body.mode or "hybrid",
        top_k=body.top_k or default_top_k,
        namespace=body.namespace,
        filters=filters,
        temporal=temporal,
        scope=scope,
        rerank=body.rerank,
        neighbor=body.neighbor,
        expansion=body.expansion or QueryExpansion.AUTOMATIC.value,
        min_score=body.min_score,
    )


def _svc() -> Any:
    search = getattr(service, "search", None)
    if search is None:
        raise HTTPException(status_code=503, detail="the search layer is unavailable")
    return search


class SearchBody(BaseModel):
    query: str = Field(min_length=1)
    mode: Optional[str] = None
    top_k: Optional[int] = Field(default=None, ge=1, le=100)
    namespace: Optional[str] = None
    namespaces: Optional[list[str]] = None
    source_types: Optional[list[str]] = None
    entity_type: Optional[str] = None
    entity_id: Optional[str] = None
    workspace_id: Optional[str] = None
    owner_id: Optional[str] = None
    as_of: Optional[str] = None
    published_from: Optional[str] = None
    published_to: Optional[str] = None
    rerank: Optional[bool] = None
    neighbor: bool = True
    expansion: Optional[str] = None
    min_score: float = 0.0
    route: bool = False
    unrestricted: bool = True


class IndexBody(BaseModel):
    namespaces: Optional[list[str]] = None


class EmbeddingConfigBody(BaseModel):
    """Operator choice of embedding provider/model (persisted in the search DB)."""

    provider: str = ""
    model: str = ""
    dimensions: int = 0
    version: str = ""
    reindex: bool = True


class IngestBody(BaseModel):
    text: str = Field(min_length=1, max_length=2_000_000)
    title: str = ""
    source_type: str = "uploaded"
    source_id: str = ""
    namespace: str = "research"
    uri: Optional[str] = None
    visibility: str = "public"
    workspace_id: Optional[str] = None
    owner_id: Optional[str] = None
    published_at: Optional[str] = None
    strategy: Optional[str] = None
    metadata: Optional[dict[str, Any]] = None


@router.get("/search/health")
async def search_health(_: bool = Depends(require_operator)) -> dict[str, Any]:
    search = getattr(service, "search", None)
    if search is None:
        return {"available": False, "reason": "the search layer is unavailable"}
    return {"available": True, **search.health()}


@router.get("/search/stats")
async def search_stats(_: bool = Depends(require_operator)) -> dict[str, Any]:
    search = getattr(service, "search", None)
    if search is None:
        return {"available": False}
    return {"available": True, **search.admin_stats()}


@router.get("/search/models")
async def search_models(_: bool = Depends(require_operator)) -> dict[str, Any]:
    search = _svc()
    return {
        "available": True,
        "active": {
            "provider": search.embedder.provider_id,
            "model": search.embedder.model_id,
            "version": search.embedder.version,
            "dimensions": search.embedder.dimensions,
            "distanceMetric": search.embedder.distance_metric,
            "available": search.embedder.available,
            "reason": search.embedder.reason,
        },
        "resolution": search.embedder.resolution(),
        "registry": [m.to_dict() for m in search.embedder.registry.list_models()],
        "indexedVectorModels": search.store.vector_models(),
    }


@router.post("/search/embedding/apply")
async def search_embedding_apply(
    body: EmbeddingConfigBody, _: bool = Depends(require_operator)
) -> dict[str, Any]:
    """Activate an embedding model live and persist it across restarts.

    Switching vector space schedules a background rebuild so semantic search
    is not left empty: old vectors belong to the previous model key.
    """
    search = _svc()
    status = search.apply_embedding_config(
        provider=body.provider,
        model=body.model,
        dimensions=body.dimensions,
        version=body.version,
    )
    rebuild = bool(body.reindex and status["resolution"]["available"])
    if rebuild:
        search.schedule_vector_rebuild()
    return {"success": True, **status, "reindexScheduled": rebuild}


@router.post("/search/embedding/clear")
async def search_embedding_clear(_: bool = Depends(require_operator)) -> dict[str, Any]:
    search = _svc()
    return {"success": True, **search.clear_embedding_config()}


@router.post("/search/embedding/test")
async def search_embedding_test(_: bool = Depends(require_operator)) -> dict[str, Any]:
    search = _svc()
    return {"success": True, **await search.test_embedding()}


@router.post("/search")
async def search_query(body: SearchBody, _: bool = Depends(require_operator)) -> dict[str, Any]:
    search = _svc()
    request = build_request(body, search.config.default_top_k)
    if body.route:
        result = await search.search_routed(
            body.query, top_k=body.top_k, scope=request.scope, namespace=body.namespace,
        )
    else:
        result = await search.search(request)
    return {"success": True, "result": result.to_dict()}


@router.post("/search/debug")
async def search_debug(body: SearchBody, _: bool = Depends(require_operator)) -> dict[str, Any]:
    search = _svc()
    request = build_request(body, search.config.default_top_k)
    return {"success": True, "trace": search.debug_trace(request)}


@router.post("/search/index")
async def search_index(body: IndexBody, _: bool = Depends(require_operator)) -> dict[str, Any]:
    search = _svc()
    return {"success": True, "summary": await search.bulk_index(namespaces=body.namespaces)}


@router.post("/search/index/process")
async def search_process_jobs(limit: int = 20, _: bool = Depends(require_operator)) -> dict[str, Any]:
    search = _svc()
    return {"success": True, **await search.process_jobs(limit=limit)}


@router.post("/search/ingest")
async def search_ingest(body: IngestBody, _: bool = Depends(require_operator)) -> dict[str, Any]:
    search = _svc()
    result = await search.ingest_text(
        body.text, title=body.title, source_type=body.source_type, source_id=body.source_id,
        namespace=body.namespace, uri=body.uri, visibility=body.visibility,
        workspace_id=body.workspace_id, owner_id=body.owner_id, published_at=body.published_at,
        strategy=body.strategy, metadata=body.metadata,
    )
    return {"success": True, "result": result.to_dict()}


@router.post("/search/reindex/{document_id}")
async def search_reindex(document_id: str, reembed: bool = False, _: bool = Depends(require_operator)) -> dict[str, Any]:
    search = _svc()
    result = await search.reindex_document(document_id, reembed=reembed)
    return {"success": True, "result": result.to_dict()}


@router.get("/search/documents")
async def search_documents(
    namespace: Optional[str] = None, state: Optional[str] = None, limit: int = 50,
    _: bool = Depends(require_operator),
) -> dict[str, Any]:
    search = _svc()
    return {"success": True, "documents": search.list_documents(namespace=namespace, state=state, limit=limit)}


@router.get("/search/documents/{document_id}")
async def search_document(document_id: str, _: bool = Depends(require_operator)) -> dict[str, Any]:
    search = _svc()
    document = search.get_document(document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="document not found")
    return {"success": True, "document": document}


@router.get("/search/documents/{document_id}/context")
async def search_document_context(
    document_id: str, chunk_id: Optional[str] = None, radius: int = 1,
    _: bool = Depends(require_operator),
) -> dict[str, Any]:
    search = _svc()
    return {"success": True, **search.get_document_context(document_id, chunk_id=chunk_id, radius=radius)}


@router.delete("/search/documents/{document_id}")
async def search_delete_document(document_id: str, _: bool = Depends(require_operator)) -> dict[str, Any]:
    search = _svc()
    return {"success": search.delete_document(document_id)}


@router.get("/search/events")
async def search_events(limit: int = 50, kind: Optional[str] = None, _: bool = Depends(require_operator)) -> dict[str, Any]:
    search = _svc()
    return {"success": True, "events": search.store.recent_events(limit=limit, kind=kind)}


__all__ = ["router", "SearchBody", "IndexBody", "IngestBody"]
