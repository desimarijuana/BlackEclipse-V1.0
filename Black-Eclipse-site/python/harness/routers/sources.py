"""HTTP routes for the large-corpus source layer (operator-gated).

Thin adapters over the SAME ``SourceService`` the agent tools use. Adding a root
is an operator action: the agent can read registered roots but can never widen
its own filesystem access. All routes are loopback/runtime-secret gated.
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..deps import require_operator, service
from ..sources.errors import SourceError

router = APIRouter(tags=["sources"], dependencies=[Depends(require_operator)])


def _svc() -> Any:
    sources = getattr(service, "sources", None)
    if sources is None:
        raise HTTPException(status_code=503, detail="the source layer is unavailable")
    return sources


def _fail(exc: SourceError) -> HTTPException:
    status = {
        "ROOT_NOT_FOUND": 404,
        "ROOT_NOT_DIRECTORY": 400,
        "ROOT_UNKNOWN": 404,
        "ROOT_LIMIT": 409,
        "PATH_OUTSIDE_ROOT": 403,
        "FILE_NOT_FOUND": 404,
        "FILE_GONE": 410,
        "SCAN_BUSY": 409,
        "READ_LIMIT": 413,
        "FILE_TOO_LARGE": 413,
        "QUERY_REFUSED": 400,
        "BUDGET_EXCEEDED": 408,
        "QUERY_TIMEOUT": 408,
    }.get(exc.code, 400)
    return HTTPException(status_code=status, detail=exc.to_dict())


class RootBody(BaseModel):
    path: str = Field(min_length=1)
    label: Optional[str] = None


class LocationBody(BaseModel):
    rootId: Optional[str] = None
    relpath: Optional[str] = None
    path: Optional[str] = None


class ReadBody(LocationBody):
    offset: int = 0
    length: Optional[int] = None


class LinesBody(LocationBody):
    startLine: int = 1
    count: int = 200


class SearchBody(BaseModel):
    query: str = ""
    mode: str = "auto"
    rootIds: Optional[list[str]] = None
    pathPrefix: Optional[str] = None
    klass: Optional[str] = None
    nameLike: Optional[str] = None
    minSize: Optional[int] = None
    maxSize: Optional[int] = None
    modifiedAfter: Optional[float] = None
    limit: int = 50
    regex: bool = False
    caseSensitive: bool = False


class SqlBody(LocationBody):
    sql: str = Field(min_length=1)
    maxRows: Optional[int] = None
    allRootFiles: bool = False


class IndexBody(BaseModel):
    rootIds: Optional[list[str]] = None
    limitFiles: int = 100
    budgetS: float = 30.0
    semantic: bool = False


def _location(body: LocationBody) -> dict[str, Any]:
    return {"root_id": body.rootId, "relpath": body.relpath, "path": body.path}


@router.get("/sources/roots")
async def list_roots() -> dict[str, Any]:
    return {"roots": _svc().list_roots()}


@router.post("/sources/roots")
async def add_root(body: RootBody) -> dict[str, Any]:
    try:
        return {"root": _svc().add_root(body.path, body.label)}
    except SourceError as exc:
        raise _fail(exc) from exc


@router.delete("/sources/roots/{root_id}")
async def remove_root(root_id: str) -> dict[str, Any]:
    return {"removed": _svc().remove_root(root_id)}


@router.post("/sources/roots/{root_id}/scan")
async def scan_root(root_id: str) -> dict[str, Any]:
    try:
        return {"scan": _svc().start_scan(root_id)}
    except SourceError as exc:
        raise _fail(exc) from exc


@router.get("/sources/roots/{root_id}/scan")
async def scan_status(root_id: str) -> dict[str, Any]:
    return {"scan": _svc().scan_status(root_id)}


@router.post("/sources/scan/cancel")
async def cancel_scans() -> dict[str, Any]:
    _svc().cancel_all()
    return {"cancelled": True}


@router.get("/sources/stats")
async def stats() -> dict[str, Any]:
    return _svc().stats()


@router.get("/sources/list")
async def list_files(rootId: str = "", prefix: str = "", limit: int = 200) -> dict[str, Any]:
    return _svc().list_dir(root_id=rootId, relpath=prefix, limit=limit)


@router.post("/sources/open")
async def open_source(body: LocationBody) -> dict[str, Any]:
    try:
        return _svc().open(**_location(body))
    except SourceError as exc:
        raise _fail(exc) from exc


@router.post("/sources/read")
async def read_source(body: ReadBody) -> dict[str, Any]:
    try:
        return _svc().read_window(
            **_location(body), offset=body.offset, length=body.length
        )
    except SourceError as exc:
        raise _fail(exc) from exc


@router.post("/sources/lines")
async def read_lines(body: LinesBody) -> dict[str, Any]:
    try:
        return _svc().read_lines(
            **_location(body), start_line=body.startLine, count=body.count
        )
    except SourceError as exc:
        raise _fail(exc) from exc


@router.post("/sources/search")
async def search(body: SearchBody) -> dict[str, Any]:
    try:
        result = _svc().search(
            query=body.query,
            mode=body.mode,
            root_ids=body.rootIds or None,
            path_prefix=body.pathPrefix or None,
            klass=body.klass or None,
            name_like=body.nameLike or None,
            min_size=body.minSize,
            max_size=body.maxSize,
            modified_after=body.modifiedAfter,
            limit=body.limit,
            regex=body.regex,
            case_sensitive=body.caseSensitive,
        )
        return result.to_dict()
    except SourceError as exc:
        raise _fail(exc) from exc


@router.post("/sources/sql")
async def run_sql_route(body: SqlBody) -> dict[str, Any]:
    try:
        result = _svc().sql(
            sql=body.sql,
            root_id=body.rootId,
            relpath=body.relpath if body.relpath is not None else body.path,
            path=body.path,
            max_rows=body.maxRows,
            all_root_files=body.allRootFiles,
        )
        return result.to_dict()
    except SourceError as exc:
        raise _fail(exc) from exc


@router.post("/sources/index")
async def index_sources(body: IndexBody) -> dict[str, Any]:
    try:
        return _svc().index(
            root_ids=body.rootIds or None,
            limit_files=body.limitFiles,
            budget_s=body.budgetS,
            semantic=body.semantic,
        )
    except SourceError as exc:
        raise _fail(exc) from exc


__all__ = ["router"]
