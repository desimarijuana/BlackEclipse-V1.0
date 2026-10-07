"""Action verification — an action must not blindly report success."""

from __future__ import annotations

from .verifier import ActionVerifier, VerificationResult

__all__ = ["ActionVerifier", "VerificationResult"]
