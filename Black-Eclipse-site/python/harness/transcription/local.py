"""On-device speech-to-text (no key, no configuration).

This is the zero-config path the desktop app defaults to when no cloud provider
is configured. It runs `faster-whisper` inside the interpreter the harness
already ships, so a user installs the app and dictates — there is nothing to
sign up for and no key to paste.

The model is downloaded ONCE into the app's data directory
(`.black-eclipse/models/whisper`) and reused from disk. After that it works
offline. Audio and transcripts are never written anywhere else, and the
temporary file used for decoding is removed in a `finally`.
"""

from __future__ import annotations

import asyncio
import os
import tempfile
import threading
from pathlib import Path
from typing import Any, Optional

from .errors import TranscriptionError

# Small enough to download quickly, accurate enough for dictation.
DEFAULT_MODEL = "base.en"
MAX_LANGUAGE_CHARS = 8

_models: dict[str, Any] = {}
_lock = threading.Lock()


def _data_root() -> Path:
    configured = os.environ.get("BE_DATA_DIR")
    if configured:
        return Path(configured)
    # .../Black-Eclipse-site/python/harness/transcription/local.py → site root
    return Path(__file__).resolve().parents[3]


def model_dir() -> Path:
    path = _data_root() / ".black-eclipse" / "models" / "whisper"
    path.mkdir(parents=True, exist_ok=True)
    return path


def engine_available() -> bool:
    """True when the on-device engine can be imported."""
    try:
        import faster_whisper  # noqa: F401
    except Exception:
        return False
    return True


def _load_model(name: str) -> Any:
    with _lock:
        cached = _models.get(name)
        if cached is not None:
            return cached
        try:
            from faster_whisper import WhisperModel
        except Exception as exc:  # pragma: no cover - environment dependent
            raise TranscriptionError(
                "LOCAL_ENGINE_MISSING",
                "The on-device speech engine is not installed. Run: npm run setup:python",
                503,
            ) from exc

        try:
            model = WhisperModel(
                name,
                device="cpu",
                compute_type="int8",
                download_root=str(model_dir()),
            )
        except Exception as exc:
            raise TranscriptionError(
                "MODEL_UNAVAILABLE",
                "The speech model could not be prepared. The first use downloads it once — "
                "check the connection and try again.",
                503,
            ) from exc

        _models[name] = model
        return model


def _pick_language(language: Optional[str]) -> Optional[str]:
    value = (language or "").strip()
    if not value:
        return None
    # OpenAI-style clients send `en-US`; Whisper wants `en`.
    return value.split("-")[0].lower()[:MAX_LANGUAGE_CHARS] or None


def _transcribe_sync(
    *,
    audio: bytes,
    extension: str,
    model: str,
    language: Optional[str],
    prompt: Optional[str],
    duration_ms: Optional[int],
) -> dict[str, Any]:
    chosen = (model or "").strip() or DEFAULT_MODEL
    engine = _load_model(chosen)

    handle, path = tempfile.mkstemp(prefix="be-voice-", suffix=extension)
    try:
        with os.fdopen(handle, "wb") as file:
            file.write(audio)
        segments, info = engine.transcribe(
            path,
            language=_pick_language(language),
            initial_prompt=(prompt or None),
            vad_filter=True,
            beam_size=1,
            condition_on_previous_text=False,
        )
        text = "".join(segment.text for segment in segments).strip()
        detected = getattr(info, "language", None)
        return {
            "text": text,
            "provider": "local",
            "model": chosen,
            "language": detected or _pick_language(language),
            "durationMs": duration_ms,
        }
    except TranscriptionError:
        raise
    except Exception as exc:
        raise TranscriptionError(
            "TRANSCRIBE_FAILED",
            "The on-device transcription failed for this recording. Try again.",
            502,
        ) from exc
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


async def transcribe_local(
    *,
    audio: bytes,
    extension: str,
    model: str,
    language: Optional[str] = None,
    prompt: Optional[str] = None,
    duration_ms: Optional[int] = None,
) -> dict[str, Any]:
    """Transcribe one bounded clip on this machine. Never touches the network."""
    return await asyncio.to_thread(
        _transcribe_sync,
        audio=audio,
        extension=extension,
        model=model,
        language=language,
        prompt=prompt,
        duration_ms=duration_ms,
    )


__all__ = ["DEFAULT_MODEL", "engine_available", "model_dir", "transcribe_local"]
