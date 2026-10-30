"""Voice transcription HTTP routes.

Operator-gated (loopback or the runtime token), like every other runtime
surface. The Next.js front door resolves the provider + key; this route only
validates and performs the call. Audio is never persisted.
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from ..deps import require_operator
from ..transcription import TranscriptionError, transcribe

router = APIRouter(tags=["voice"])


class TranscribeBody(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    audio_base64: str = Field(alias="audioBase64")
    mime_type: str = Field(alias="mimeType")
    provider: str
    base_url: str = Field(alias="baseUrl")
    api_key: Optional[str] = Field(default=None, alias="apiKey")
    model: str
    language: Optional[str] = None
    prompt: Optional[str] = None
    duration_ms: Optional[int] = Field(default=None, alias="durationMs")


@router.post("/voice/transcribe")
async def voice_transcribe(
    body: TranscribeBody,
    _: bool = Depends(require_operator),
) -> dict[str, Any]:
    try:
        return await transcribe(
            audio_base64=body.audio_base64,
            mime_type=body.mime_type,
            provider=body.provider,
            base_url=body.base_url,
            api_key=body.api_key,
            model=body.model,
            language=body.language,
            prompt=body.prompt,
            duration_ms=body.duration_ms,
        )
    except TranscriptionError as exc:
        raise HTTPException(
            status_code=exc.status,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc
