"""OpenAI-compatible audio transcription.

The operator's provider choice and key are resolved in the Next.js front door;
this module only validates the bounded audio and performs the outbound call.
Audio and transcripts are never written to disk or the database.
"""

from __future__ import annotations

import base64
import binascii
from typing import Any, Optional

import httpx

MAX_AUDIO_BYTES = 15 * 1024 * 1024
MAX_PROMPT_CHARS = 900
MAX_MODEL_CHARS = 80

ALLOWED_MIME = {
    "audio/webm": ".webm",
    "audio/ogg": ".ogg",
    "audio/mp4": ".m4a",
    "audio/mpeg": ".mp3",
    "audio/wav": ".wav",
    "audio/x-wav": ".wav",
}


from .errors import TranscriptionError
from .local import transcribe_local


def _decode_audio(audio_base64: str) -> bytes:
    if not audio_base64:
        raise TranscriptionError("INVALID_AUDIO", "No audio was provided", 400)
    try:
        payload = base64.b64decode(audio_base64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise TranscriptionError("INVALID_AUDIO", "Audio is not valid base64", 400) from exc
    if not payload:
        raise TranscriptionError("INVALID_AUDIO", "The recording was empty", 400)
    if len(payload) > MAX_AUDIO_BYTES:
        raise TranscriptionError(
            "TOO_LARGE", "That recording is too long. Keep dictation under two minutes.", 413
        )
    return payload


def _validate_base_url(base_url: str) -> str:
    value = (base_url or "").strip().rstrip("/")
    if not value:
        raise TranscriptionError("NOT_CONFIGURED", "No transcription endpoint is configured", 503)
    if not (value.startswith("http://") or value.startswith("https://")):
        raise TranscriptionError("CONFIG_ERROR", "The transcription endpoint must use http(s)", 400)
    return value


def _provider_message(status: int) -> tuple[str, str, int]:
    if status == 401 or status == 403:
        return (
            "KEY_REJECTED",
            "The transcription provider rejected the key. Check it in Settings › AI.",
            502,
        )
    if status == 413:
        return ("TOO_LARGE", "The provider rejected the recording as too large.", 413)
    if status == 429:
        return ("RATE_LIMITED", "The transcription provider is rate-limiting. Try again shortly.", 429)
    if status >= 500:
        return ("PROVIDER_ERROR", "The transcription provider failed. Try again.", 502)
    return ("PROVIDER_ERROR", f"The transcription provider rejected the request ({status}).", 502)


async def transcribe(
    *,
    audio_base64: str,
    mime_type: str,
    provider: str,
    base_url: str,
    api_key: Optional[str],
    model: str,
    language: Optional[str] = None,
    prompt: Optional[str] = None,
    duration_ms: Optional[int] = None,
) -> dict[str, Any]:
    """Transcribe one bounded clip. Returns the runtime's transcript envelope."""
    mime = (mime_type or "").split(";")[0].strip().lower()
    extension = ALLOWED_MIME.get(mime)
    if not extension:
        raise TranscriptionError("UNSUPPORTED_MEDIA", f"Unsupported audio type: {mime or 'unknown'}", 415)

    audio = _decode_audio(audio_base64)

    # On-device engine: no endpoint, no key, no network. This is the default
    # when the operator has not configured a cloud provider.
    if (provider or "").strip().lower() == "local":
        return await transcribe_local(
            audio=audio,
            extension=extension,
            model=(model or "").strip()[:MAX_MODEL_CHARS] or "base.en",
            language=language,
            prompt=prompt,
            duration_ms=duration_ms,
        )

    endpoint = f"{_validate_base_url(base_url)}/audio/transcriptions"

    chosen_model = (model or "").strip()[:MAX_MODEL_CHARS]
    if not chosen_model:
        raise TranscriptionError("NOT_CONFIGURED", "No transcription model is configured", 503)

    form: dict[str, str] = {"model": chosen_model, "response_format": "json"}
    if language:
        # OpenAI-compatible transcription takes ISO-639-1 (`en`), not `en-US`.
        form["language"] = language.strip().split("-")[0].lower()[:8]
    if prompt:
        form["prompt"] = prompt.strip()[:MAX_PROMPT_CHARS]

    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(90.0, connect=15.0)) as client:
            response = await client.post(
                endpoint,
                headers=headers,
                data=form,
                files={"file": (f"dictation{extension}", audio, mime)},
            )
    except httpx.TimeoutException as exc:
        raise TranscriptionError(
            "TIMEOUT", "Transcription timed out. Try a shorter recording.", 504
        ) from exc
    except httpx.HTTPError as exc:
        raise TranscriptionError(
            "PROVIDER_ERROR", "The transcription provider could not be reached.", 502
        ) from exc

    if response.status_code >= 400:
        code, message, status = _provider_message(response.status_code)
        raise TranscriptionError(code, message, status)

    try:
        payload = response.json()
    except ValueError as exc:
        raise TranscriptionError(
            "PROVIDER_ERROR", "The transcription provider returned an unreadable response.", 502
        ) from exc

    text = payload.get("text") if isinstance(payload, dict) else None
    if not isinstance(text, str) or not text.strip():
        raise TranscriptionError(
            "EMPTY_TRANSCRIPT",
            "No speech was recognized. Try again a little closer to the microphone.",
            422,
        )

    return {
        "text": text.strip(),
        "provider": provider,
        "model": chosen_model,
        "language": (payload.get("language") if isinstance(payload, dict) else None) or language or None,
        "durationMs": duration_ms,
    }
