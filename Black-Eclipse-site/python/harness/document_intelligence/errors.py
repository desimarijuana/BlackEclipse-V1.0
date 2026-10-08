"""Document Intelligence error classification.

Every document operation fails into ONE of these classes so the orchestrator,
telemetry, the agent and the UI can react exactly (retry, fallback, or refuse)
rather than string-matching a parser's message. The vocabulary mirrors the vision
subsystem's `VisionErrorClass` so a failure that bubbles out of a shared OCR or
model call keeps its meaning, and adds the document-specific cases the spec names
(§42).

Nothing here is ever used to fake success: a raised `DocumentError` is a real,
reported failure. `retryable` and `fallbackable` are the only signals the
orchestrator acts on.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class DocumentErrorClass(str, Enum):
    INVALID_INPUT = "INVALID_INPUT"                  # missing/unknown source, bad args
    NO_SOURCE = "NO_SOURCE"                         # file not found / unreadable
    UNSUPPORTED_FORMAT = "UNSUPPORTED_FORMAT"       # a format we cannot parse
    INVALID_IMAGE = "INVALID_IMAGE"                 # an undecodable / corrupt image
    CORRUPTED_FILE = "CORRUPTED_FILE"               # parseable container, broken content
    PARSER_FAILURE = "PARSER_FAILURE"               # the parser raised
    OVERSIZED = "OVERSIZED"                         # exceeds a hard size/page ceiling
    DECOMPRESSION_BOMB = "DECOMPRESSION_BOMB"       # archive/compression bomb
    SECURITY_BLOCKED = "SECURITY_BLOCKED"           # macro/archive/script/injection policy
    MACRO_ENABLED = "MACRO_ENABLED"                 # a macro-enabled document was refused
    OCR_UNAVAILABLE = "OCR_UNAVAILABLE"
    OCR_FAILED = "OCR_FAILED"
    VISION_UNAVAILABLE = "VISION_UNAVAILABLE"       # no model can see images
    MODEL_CAPABILITY_MISMATCH = "MODEL_CAPABILITY_MISMATCH"
    PROVIDER_ERROR = "PROVIDER_ERROR"
    PROVIDER_TIMEOUT = "PROVIDER_TIMEOUT"
    RATE_LIMIT = "RATE_LIMIT"
    AUTH_ERROR = "AUTH_ERROR"
    MALFORMED_RESPONSE = "MALFORMED_RESPONSE"
    TIMEOUT = "TIMEOUT"
    FILE_TOO_LARGE = "FILE_TOO_LARGE"
    RESOURCE_LIMIT = "RESOURCE_LIMIT"
    PARTIAL_EXTRACTION = "PARTIAL_EXTRACTION"       # some stages succeeded, some did not
    INDEX_FAILURE = "INDEX_FAILURE"
    STORAGE_ERROR = "STORAGE_ERROR"
    INTERNAL_ERROR = "INTERNAL_ERROR"


_RETRYABLE = frozenset({
    DocumentErrorClass.PROVIDER_ERROR,
    DocumentErrorClass.PROVIDER_TIMEOUT,
    DocumentErrorClass.RATE_LIMIT,
    DocumentErrorClass.OCR_FAILED,
    DocumentErrorClass.TIMEOUT,
    DocumentErrorClass.INDEX_FAILURE,
    DocumentErrorClass.STORAGE_ERROR,
    DocumentErrorClass.INTERNAL_ERROR,
})

# A retryable error is also worth trying on a DIFFERENT backend/parser; a
# corrupted file or an unsupported format is not.
_FALLBACKABLE = _RETRYABLE | frozenset({
    DocumentErrorClass.OCR_UNAVAILABLE,
    DocumentErrorClass.VISION_UNAVAILABLE,
    DocumentErrorClass.MODEL_CAPABILITY_MISMATCH,
    DocumentErrorClass.MALFORMED_RESPONSE,
    DocumentErrorClass.PARSER_FAILURE,
})


@dataclass
class DocumentError(Exception):
    """A classified, reportable document failure. Never silent, never faked."""

    error_class: DocumentErrorClass
    message: str
    source_ref: Optional[str] = None
    stage: Optional[str] = None
    details: Optional[dict[str, Any]] = None
    cause: Optional[BaseException] = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        Exception.__init__(self, self.message)

    @property
    def retryable(self) -> bool:
        return self.error_class in _RETRYABLE

    @property
    def fallbackable(self) -> bool:
        return self.error_class in _FALLBACKABLE

    def to_dict(self) -> dict[str, Any]:
        return {
            "errorClass": self.error_class.value,
            "message": self.message,
            "sourceRef": self.source_ref,
            "stage": self.stage,
            "retryable": self.retryable,
            "fallbackable": self.fallbackable,
            "details": self.details or {},
        }


__all__ = ["DocumentError", "DocumentErrorClass"]
