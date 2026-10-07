"""Structured Computer Use errors and the verdict vocabulary.

Mirrors the harness/browser error discipline: every failure carries a stable
machine `code`, a plain human sentence, the session/target context, and whether
it is retryable. A raw driver exception is NEVER returned to the model — it is
translated into one of these.

Alongside the exception hierarchy lives the VERDICT vocabulary: the small,
closed set of instructions a Computer Use result hands back to the agent so it
follows a directive instead of guessing (`success`, `recapture`, `retry`,
`reground`, `foreground_required`, `approval_required`, `blocked`, `ask_user`,
`abort`).
"""

from __future__ import annotations

from typing import Any, Optional

# ── Verdicts — what the agent should do next ─────────────────────────────────

VERDICTS: tuple[str, ...] = (
    "success",
    "recapture",
    "retry",
    "reground",
    "foreground_required",
    "approval_required",
    "blocked",
    "ask_user",
    "abort",
)

# ── Action state machine states ──────────────────────────────────────────────

ACTION_STATES: tuple[str, ...] = (
    "UNKNOWN",
    "OBSERVED",
    "TARGET_IDENTIFIED",
    "AUTHORIZED",
    "ACTION_READY",
    "ACTION_EXECUTED",
    "VERIFYING",
    "CONFIRMED",
)

ACTION_FAILURE_STATES: tuple[str, ...] = (
    "TARGET_NOT_FOUND",
    "STALE_ELEMENT",
    "ACTION_FAILED",
    "STATE_CHANGED",
    "APP_UNRESPONSIVE",
    "PERMISSION_REQUIRED",
    "AMBIGUOUS_TARGET",
    "UNEXPECTED_DIALOG",
    "TIMEOUT",
)


class ComputerError(Exception):
    """Base class for every Computer Use refusal/failure.

    ``code`` is stable and testable; ``reason`` is a plain sentence safe to show
    a human. ``verdict`` tells the agent what to do next. Secrets are never
    placed in an error.
    """

    code = "COMPUTER_ERROR"
    retryable = False
    verdict = "abort"

    def __init__(
        self,
        reason: str,
        *,
        code: Optional[str] = None,
        session_id: Optional[str] = None,
        app: Optional[str] = None,
        window: Optional[str] = None,
        target: Optional[str] = None,
        action: Optional[str] = None,
        retryable: Optional[bool] = None,
        verdict: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(reason)
        self.reason = reason
        if code:
            self.code = code
        self.session_id = session_id
        self.app = app
        self.window = window
        self.target = target
        self.action = action
        if retryable is not None:
            self.retryable = retryable
        if verdict:
            self.verdict = verdict
        self.metadata = metadata or {}

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.reason,
            "sessionId": self.session_id,
            "application": self.app,
            "window": self.window,
            "target": self.target,
            "action": self.action,
            "retryable": self.retryable,
            "verdict": self.verdict,
            "metadata": self.metadata,
        }


class ComputerUnavailable(ComputerError):
    """The driver/runtime dependency is absent — the honest zero-config state."""

    code = "COMPUTER_UNAVAILABLE"
    verdict = "blocked"


class UnsupportedPlatform(ComputerError):
    code = "COMPUTER_UNSUPPORTED_PLATFORM"
    verdict = "abort"


class DriverUnavailable(ComputerError):
    code = "COMPUTER_DRIVER_UNAVAILABLE"
    verdict = "blocked"


class DriverIncompatible(ComputerError):
    """The driver's runtime contract is missing/incompatible — never silently used."""

    code = "COMPUTER_DRIVER_INCOMPATIBLE"
    verdict = "abort"


class PermissionDenied(ComputerError):
    code = "COMPUTER_PERMISSION_DENIED"
    verdict = "blocked"


class PolicyBlocked(ComputerError):
    code = "COMPUTER_POLICY_BLOCKED"
    verdict = "blocked"


class ApprovalRequired(ComputerError):
    code = "COMPUTER_APPROVAL_REQUIRED"
    verdict = "approval_required"


class AccessibilityUnavailable(ComputerError):
    code = "COMPUTER_ACCESSIBILITY_UNAVAILABLE"
    verdict = "reground"


class ScreenCaptureUnavailable(ComputerError):
    code = "COMPUTER_SCREEN_CAPTURE_UNAVAILABLE"
    verdict = "blocked"


class StaleElement(ComputerError):
    """A snapshot handle no longer matches the live UI. The model must re-capture."""

    code = "COMPUTER_STALE_ELEMENT"
    retryable = True
    verdict = "recapture"


class TargetNotFound(ComputerError):
    code = "COMPUTER_TARGET_NOT_FOUND"
    retryable = True
    verdict = "reground"


class AmbiguousTarget(ComputerError):
    code = "COMPUTER_AMBIGUOUS_TARGET"
    verdict = "ask_user"


class WindowNotFound(ComputerError):
    code = "COMPUTER_WINDOW_NOT_FOUND"
    verdict = "reground"


class TargetObscured(ComputerError):
    """The target window/control is covered by another window.

    A foreground SendInput at absolute coordinates would land on the COVERING
    window. Refused rather than risking a wrong-application click; the caller
    may raise/bring the target forward first, then retry.
    """

    code = "COMPUTER_TARGET_OBSCURED"
    retryable = True
    verdict = "foreground_required"


class ApplicationNotFound(ComputerError):
    code = "COMPUTER_APPLICATION_NOT_FOUND"
    verdict = "reground"


class ActionRejected(ComputerError):
    code = "COMPUTER_ACTION_REJECTED"
    verdict = "retry"


class ActionFailed(ComputerError):
    code = "COMPUTER_ACTION_FAILED"
    retryable = True
    verdict = "retry"


class VerificationFailed(ComputerError):
    code = "COMPUTER_VERIFICATION_FAILED"
    verdict = "recapture"


class RecoveryFailed(ComputerError):
    code = "COMPUTER_RECOVERY_FAILED"
    verdict = "abort"


class TimeoutError_(ComputerError):
    code = "COMPUTER_TIMEOUT"
    retryable = True
    verdict = "retry"


class HumanInterventionRequired(ComputerError):
    """A CAPTCHA/MFA/security challenge — automation stops and asks a person."""

    code = "COMPUTER_HUMAN_REQUIRED"
    verdict = "ask_user"


class UnsupportedAction(ComputerError):
    code = "COMPUTER_CAPABILITY_UNSUPPORTED"
    verdict = "abort"


__all__ = [
    "ACTION_FAILURE_STATES",
    "ACTION_STATES",
    "AccessibilityUnavailable",
    "ActionFailed",
    "ActionRejected",
    "AmbiguousTarget",
    "ApplicationNotFound",
    "ApprovalRequired",
    "ComputerError",
    "ComputerUnavailable",
    "DriverIncompatible",
    "DriverUnavailable",
    "HumanInterventionRequired",
    "PermissionDenied",
    "PolicyBlocked",
    "RecoveryFailed",
    "ScreenCaptureUnavailable",
    "StaleElement",
    "TargetObscured",
    "TimeoutError_",
    "TargetNotFound",
    "UnsupportedAction",
    "UnsupportedPlatform",
    "VERDICTS",
    "VerificationFailed",
    "WindowNotFound",
]
