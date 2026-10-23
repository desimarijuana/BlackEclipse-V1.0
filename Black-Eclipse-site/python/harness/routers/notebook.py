"""The chat-notebook route group (Phase 21).

A notebook cell is a small, user-authored Python program attached to one
conversation. It runs through the SAME `analysis_run` path the agent uses — the
Phase 3 sandbox, the per-conversation kernel, artifact collection and the
`computed` provenance rule — so there is one execution engine, not two.

The route is the host boundary, not a second tool:

* `extra_imports` is fixed here (`io`, `matplotlib`); a request body cannot widen
  the import allowlist.
* the namespace is persistent per conversation, so a later cell can use a
  variable an earlier cell defined; `analysis_run` itself never sets that flag.
* the chart's data reaches the program as `inputs`, never as interpolated source.

Every response is a computation. It is never evidence and never a research claim.
"""

from __future__ import annotations

import re
import shutil
import tempfile
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from ..analysis_tools import analysis_run
from ..artifacts.bootstrap import get_artifact_service
from ..artifacts.model import ListArtifactsQuery
from ..code.kernel import reset_kernel_for_context
from ..deps import require_operator, service
from ..tools import ToolContext

router = APIRouter(tags=["notebook"])

_SAFE_ID = re.compile(r"^[A-Za-z0-9_-]{1,80}$")
_NOTEBOOK_TIMEOUT_DEFAULT = 60


class _RunBody(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")

    chat_id: str = Field(..., min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    source: str = Field(..., min_length=1, max_length=20_000)
    inputs: dict[str, Any] = Field(default_factory=dict)
    timeout_s: int = Field(_NOTEBOOK_TIMEOUT_DEFAULT, ge=1, le=600)


class _RestartBody(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")

    chat_id: str = Field(..., min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")


def _cell_id(cell_id: str) -> str:
    if not _SAFE_ID.match(cell_id or ""):
        raise HTTPException(status_code=400, detail="invalid notebook cell id")
    return cell_id


def _input_kind(value: Any) -> str:
    """The declared shape of a notebook input (chart specs are `json`)."""
    if isinstance(value, dict):
        return "json"
    if isinstance(value, list):
        return "table" if value and isinstance(value[0], dict) else "series"
    if isinstance(value, str):
        return "text"
    if isinstance(value, bool) or value is None:
        return "json"
    return "scalar"


def _context(chat_id: str, cell_id: str) -> ToolContext:
    """The minimal run context a notebook cell needs.

    `session_id` is the kernel key, so every cell in one conversation shares the
    warm interpreter. `run_id` scopes the Artifact Center entries and the
    persisted analysis record. No data bridge is attached: a cell has no
    read-only market tools, exactly like the figure recipes.
    """
    ctx = ToolContext(
        run_id=f"nb-{chat_id}-{_cell_id(cell_id)}",
        log=lambda *_: None,
        user_id="local",
        session_id=chat_id,
        analysis_enabled=True,
        memory_store=getattr(service, "memory_store", None),
    )
    setattr(ctx, "artifact_service", getattr(service, "artifacts", None))
    return ctx


def _output_dir(chat_id: str, cell_id: str) -> Path:
    try:
        from ..code.workspace import default_root  # noqa: PLC0415

        root = default_root()
    except Exception:  # noqa: BLE001 - a missing workspace still gets a bounded home
        root = None
    base = Path(root) if root else Path(tempfile.gettempdir()) / "eclipse-notebook"
    return base / ".black-eclipse" / "artifacts" / f"notebook-{chat_id}-{_cell_id(cell_id)}"


def _entries(run_id: str, refs: list[Any]) -> list[dict[str, Any]]:
    """The CURRENT run's Artifact Center entries, in the result's order."""
    artifact_service = get_artifact_service()
    if artifact_service is None:
        return []
    wanted: set[tuple[str, str]] = set()
    for ref in refs:
        if isinstance(ref, dict):
            name = ref.get("name")
            digest = ref.get("sha256")
        else:
            name = getattr(ref, "name", None)
            digest = getattr(ref, "sha256", None)
        wanted.add((str(name or ""), str(digest or "")))
    try:
        page = artifact_service.list(ListArtifactsQuery(run_id=run_id, limit=100))
    except Exception:  # noqa: BLE001 - a missing catalog is not a failed computation
        return []
    out: list[dict[str, Any]] = []
    for artifact in page.artifacts:
        if (artifact.name, artifact.checksum or "") not in wanted:
            continue
        out.append({
            "id": artifact.id,
            "name": artifact.name,
            "bytes": artifact.size_bytes,
            "sha256": artifact.checksum,
            "mimeType": artifact.mime_type,
            "downloadUrl": f"/artifacts/{artifact.id}/download",
        })
    return out


@router.post("/notebook/cells/{cell_id}/run")
async def run_notebook_cell(
    cell_id: str,
    body: _RunBody = Body(...),
    _: None = Depends(require_operator),
) -> dict[str, Any]:
    """Run one cell in the conversation's sandbox and return its outputs."""
    _cell_id(cell_id)
    ctx = _context(body.chat_id, cell_id)
    output_dir = _output_dir(body.chat_id, cell_id)
    # A rerun replaces the cell's outputs; a stale PNG from the previous version
    # must not be collected as if this run made it.
    shutil.rmtree(output_dir, ignore_errors=True)

    text, data = await analysis_run(
        {
            "source": body.source,
            "inputs": body.inputs,
            "purpose": "a notebook cell the user ran",
            "timeout_s": body.timeout_s,
        },
        ctx,
        # The host — never the body — names the reviewed import widening and the
        # notebook namespace.
        extra_imports=("io", "matplotlib"),
        persist_namespace=True,
        input_kinds={str(name): _input_kind(value) for name, value in body.inputs.items()},
    )

    status = str(data.get("status") or "failed")
    refs = data.get("artifacts") if isinstance(data.get("artifacts"), list) else []
    return {
        "status": status,
        "outputs": data.get("outputs") if isinstance(data.get("outputs"), dict) else {},
        "artifacts": _entries(ctx.run_id, refs),
        "figure": data.get("figure"),
        "provenance": data.get("provenance"),
        "sourceDigest": data.get("sourceDigest"),
        "durationMs": data.get("durationMs") or 0,
        "code": data.get("code"),
        "error": None if status == "ok" else text,
    }


@router.post("/notebook/kernel/restart")
async def restart_notebook_kernel(
    body: _RestartBody = Body(...),
    _: None = Depends(require_operator),
) -> dict[str, Any]:
    """Drop the conversation's warm kernel so the next cell starts clean."""
    ctx = _context(body.chat_id, "kernel")
    reset_kernel_for_context(ctx)
    return {"status": "OK", "restarted": True}


__all__ = ["router"]
