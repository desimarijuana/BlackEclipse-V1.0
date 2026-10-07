"""Structured browser errors.

Mirrors the harness error discipline: every failure carries a stable machine
`code`, a plain human sentence, the session/task/provider context, and whether
it is retryable. Secrets are NEVER placed in an error — the vault resolves to an
opaque reference, and only the reference (never the value) can appear here.
"""

from __future__ import annotations

from typing import Any, Optional


class BrowserError(Exception):
    """Base class for every browser subsystem refusal/failure.

    ``code`` is stable and testable; ``reason`` is a plain sentence safe to show
    a human (no secret value, no mechanism jargon where a tool surfaces it).
    """

    code = "BROWSER_ERROR"
    retryable = False

    def __init__(
        self,
        reason: str,
        *,
        code: Optional[str] = None,
        session_id: Optional[str] = None,
        task_id: Optional[str] = None,
        provider: Optional[str] = None,
        action: Optional[str] = None,
        retryable: Optional[bool] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(reason)
        self.reason = reason
        if code:
            self.code = code
        self.session_id = session_id
        self.task_id = task_id
        self.provider = provider
        self.action = action
        if retryable is not None:
            self.retryable = retryable
        self.metadata = metadata or {}

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.reason,
            "sessionId": self.session_id,
            "taskId": self.task_id,
            "provider": self.provider,
            "action": self.action,
            "retryable": self.retryable,
            "metadata": self.metadata,
        }


class BrowserUnavailable(BrowserError):
    """The browser runtime dependency (Playwright/Chromium) is absent.

    This is the honest zero-config state: agent runs that need the browser fail
    with a clear reason rather than a fake browser.
    """

    code = "BROWSER_UNAVAILABLE"


class BrowserLaunchError(BrowserError):
    code = "BROWSER_LAUNCH_FAILED"


class BrowserNavigationError(BrowserError):
    code = "BROWSER_NAVIGATION_FAILED"


class BrowserTimeoutError(BrowserError):
    code = "BROWSER_TIMEOUT"
    retryable = True


class BrowserSessionError(BrowserError):
    code = "BROWSER_SESSION_ERROR"


class BrowserProviderError(BrowserError):
    code = "BROWSER_PROVIDER_ERROR"


class BrowserElementNotFoundError(BrowserError):
    code = "BROWSER_ELEMENT_NOT_FOUND"


class BrowserStaleElementError(BrowserError):
    code = "BROWSER_STALE_ELEMENT"
    retryable = True


class BrowserPermissionError(BrowserError):
    code = "BROWSER_PERMISSION_DENIED"


class BrowserAuthenticationError(BrowserError):
    code = "BROWSER_AUTHENTICATION_FAILED"


class BrowserDownloadError(BrowserError):
    code = "BROWSER_DOWNLOAD_FAILED"


class BrowserUploadError(BrowserError):
    code = "BROWSER_UPLOAD_FAILED"


class BrowserDialogError(BrowserError):
    code = "BROWSER_DIALOG_ERROR"


class BrowserCDPError(BrowserError):
    code = "BROWSER_CDP_ERROR"


class BrowserExecutionError(BrowserError):
    code = "BROWSER_EXECUTION_FAILED"


class BrowserHumanInterventionRequired(BrowserError):
    """A CAPTCHA/MFA/security challenge — automation stops and asks a human.

    Never bypassed. The session moves to HUMAN_REQUIRED and resumes after the
    operator's intervention.
    """

    code = "BROWSER_HUMAN_REQUIRED"


class BrowserCapabilityError(BrowserError):
    """The selected provider cannot perform the requested action."""

    code = "BROWSER_CAPABILITY_UNSUPPORTED"


__all__ = [
    "BrowserAuthenticationError",
    "BrowserCDPError",
    "BrowserCapabilityError",
    "BrowserDialogError",
    "BrowserDownloadError",
    "BrowserElementNotFoundError",
    "BrowserError",
    "BrowserExecutionError",
    "BrowserHumanInterventionRequired",
    "BrowserLaunchError",
    "BrowserNavigationError",
    "BrowserPermissionError",
    "BrowserProviderError",
    "BrowserSessionError",
    "BrowserStaleElementError",
    "BrowserTimeoutError",
    "BrowserUnavailable",
    "BrowserUploadError",
]
