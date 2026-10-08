"""Structured error taxonomy for the search layer.

Errors are classified (never string-matched) so retry/fallback decisions are
explicit and testable. A tool surfaces a stable ``code`` + human message; it
never leaks provider payloads or credentials.
"""

from __future__ import annotations

from typing import Any, Optional


class SearchError(Exception):
    """Base error. `code` is a stable machine identifier."""

    code = "search_error"
    retryable = False

    def __init__(self, message: str, *, detail: Optional[dict[str, Any]] = None) -> None:
        super().__init__(message)
        self.message = message
        self.detail = detail or {}

    def to_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, "retryable": self.retryable, "detail": self.detail}


class SearchConfigError(SearchError):
    code = "search_config_error"


class EmbeddingUnavailable(SearchError):
    """No embedding provider is configured/reachable. Semantic search degrades."""

    code = "embedding_unavailable"


class EmbeddingProviderError(SearchError):
    code = "embedding_provider_error"
    retryable = True


class EmbeddingRateLimited(EmbeddingProviderError):
    code = "embedding_rate_limited"


class EmbeddingTimeout(EmbeddingProviderError):
    code = "embedding_timeout"


class EmbeddingResponseError(EmbeddingProviderError):
    """Malformed/partial provider response. Retryable once, then surfaced."""

    code = "embedding_response_error"
    retryable = True


class DimensionMismatch(SearchError):
    """A vector's length does not match the model's declared dimensions."""

    code = "dimension_mismatch"


class ModelMismatch(SearchError):
    """Vectors from incompatible models were mixed in one vector space."""

    code = "model_mismatch"


class IndexStateError(SearchError):
    code = "index_state_error"


class SearchStoreError(SearchError):
    code = "search_store_error"


class AuthorizationError(SearchError):
    code = "search_unauthorized"


__all__ = [
    "AuthorizationError",
    "DimensionMismatch",
    "EmbeddingProviderError",
    "EmbeddingRateLimited",
    "EmbeddingResponseError",
    "EmbeddingTimeout",
    "EmbeddingUnavailable",
    "IndexStateError",
    "ModelMismatch",
    "SearchConfigError",
    "SearchError",
    "SearchStoreError",
]
