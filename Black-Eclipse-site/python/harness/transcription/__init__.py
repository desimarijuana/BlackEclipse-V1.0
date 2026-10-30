"""Voice transcription (speech-to-text) for the composer.

One OpenAI-compatible `/audio/transcriptions` call covers OpenAI, Groq and a
local whisper.cpp server. This package owns validation and the provider call;
it never persists audio and never logs a transcript.
"""

from .service import ALLOWED_MIME, MAX_AUDIO_BYTES, TranscriptionError, transcribe

__all__ = ["ALLOWED_MIME", "MAX_AUDIO_BYTES", "TranscriptionError", "transcribe"]
