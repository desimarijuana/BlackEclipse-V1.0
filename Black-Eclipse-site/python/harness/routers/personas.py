"""User personas (Settings → Persona).

The runtime owns persona storage, versioning and the draft/active lifecycle.
This router is the only write surface; the front door is a thin proxy. A
persona is an append-only overlay — it never edits the built-in prompt.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from ..deps import require_operator
from ..personas import PERSONA_PROMPT_MAX, get_persona_store, render_persona_block

router = APIRouter(prefix="/personas", tags=["personas"])


def _store():
    store = get_persona_store()
    if store is None:
        raise HTTPException(status_code=503, detail="the persona store is unavailable")
    return store


@router.get("")
def list_personas(
    includeArchived: bool = Query(default=False),  # noqa: N803
    _: bool = Depends(require_operator),
) -> dict[str, Any]:
    return {"personas": _store().list(include_archived=includeArchived)}


@router.get("/active")
def active_persona(_: bool = Depends(require_operator)) -> dict[str, Any]:
    persona = _store().active()
    return {
        "persona": persona,
        "isDefault": persona is None,
        "block": render_persona_block(persona) if persona else "",
    }


@router.get("/preview")
def preview(_: bool = Depends(require_operator)) -> dict[str, Any]:
    """The effective prompt: the authoritative base + the active overlay.

    The base prompt is the app's own operator-facing prompt (local-first), so
    showing it to the operator is safe and makes the overlay's effect legible.
    """
    from ..prompts import ECLIPSE_AGENT_SYSTEM_PROMPT  # noqa: PLC0415

    persona = _store().active()
    block = render_persona_block(persona) if persona else ""
    base = ECLIPSE_AGENT_SYSTEM_PROMPT
    return {
        "basePrompt": base,
        "personaBlock": block,
        "persona": persona,
        "isDefault": persona is None,
        "maxChars": PERSONA_PROMPT_MAX,
        "effectiveChars": len(base) + (len(block) + 2 if block else 0),
    }


@router.post("", status_code=201)
def create_persona(body: dict[str, Any], _: bool = Depends(require_operator)) -> dict[str, Any]:
    try:
        return {"persona": _store().create(body)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/reset")
def reset_default(_: bool = Depends(require_operator)) -> dict[str, Any]:
    """Deactivate every persona; the built-in prompt alone governs."""
    return _store().reset_default()


@router.get("/{persona_id}")
def get_persona(persona_id: str, _: bool = Depends(require_operator)) -> dict[str, Any]:
    persona = _store().get(persona_id)
    if persona is None:
        raise HTTPException(status_code=404, detail="persona not found")
    return {"persona": persona}


@router.patch("/{persona_id}")
def update_persona(
    persona_id: str, body: dict[str, Any], _: bool = Depends(require_operator)
) -> dict[str, Any]:
    try:
        persona = _store().update(persona_id, body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if persona is None:
        raise HTTPException(status_code=404, detail="persona not found")
    return {"persona": persona}


@router.post("/{persona_id}/activate")
def activate_persona(persona_id: str, _: bool = Depends(require_operator)) -> dict[str, Any]:
    try:
        persona = _store().activate(persona_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if persona is None:
        raise HTTPException(status_code=404, detail="persona not found")
    return {"persona": persona}


@router.post("/{persona_id}/discard")
def discard_draft(persona_id: str, _: bool = Depends(require_operator)) -> dict[str, Any]:
    persona = _store().discard_draft(persona_id)
    if persona is None:
        raise HTTPException(status_code=404, detail="persona not found")
    return {"persona": persona}


@router.post("/{persona_id}/restore")
def restore_version(
    persona_id: str, body: dict[str, Any], _: bool = Depends(require_operator)
) -> dict[str, Any]:
    try:
        version = int(body.get("version"))
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="version must be an integer") from exc
    persona = _store().restore(persona_id, version)
    if persona is None:
        raise HTTPException(status_code=404, detail="persona or version not found")
    return {"persona": persona}


@router.delete("/{persona_id}")
def archive_persona(persona_id: str, _: bool = Depends(require_operator)) -> dict[str, Any]:
    if not _store().archive(persona_id):
        raise HTTPException(status_code=404, detail="persona not found")
    return {"archived": True, "id": persona_id}


@router.get("/{persona_id}/versions")
def list_versions(persona_id: str, _: bool = Depends(require_operator)) -> dict[str, Any]:
    return {"versions": _store().versions(persona_id)}


__all__ = ["router"]
