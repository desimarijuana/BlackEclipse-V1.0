"""Structured error vocabulary for the Plugin Platform.

Every failure the plugin platform can produce is a named, machine-readable code
(never a bare string). The same vocabulary is used by the loader, the lifecycle
manager, the CLI and the HTTP router, so a refusal reads identically wherever it
surfaces.

Compat note: codes are STABLE identifiers. New codes are additive; an existing
code never changes meaning.
"""

from __future__ import annotations

from typing import Any, Optional


class PluginError(Exception):
    """A plugin-platform failure with a stable code and optional structured detail."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        detail: Optional[dict[str, Any]] = None,
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.detail = detail or {}
        self.retryable = retryable

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": False,
            "code": self.code,
            "message": self.message,
            "detail": self.detail,
            "retryable": self.retryable,
        }


class ManifestError(PluginError):
    """A manifest failed validation. Raised at load/install/validate time."""

    def __init__(self, message: str, *, detail: Optional[dict[str, Any]] = None) -> None:
        super().__init__("MANIFEST_INVALID", message, detail=detail)


class PermissionDenied(PluginError):
    """A plugin attempted a capability it did not declare/hold."""

    def __init__(self, permission: str, *, plugin_id: str = "", action: str = "") -> None:
        super().__init__(
            "PLUGIN_PERMISSION_DENIED",
            f"plugin {plugin_id!r} is not permitted to perform {action or permission!r}",
            detail={"permission": permission, "plugin_id": plugin_id, "action": action},
        )


class LifecycleError(PluginError):
    """An illegal lifecycle transition or a failed lifecycle operation."""

    def __init__(self, code: str, message: str, **kwargs: Any) -> None:
        super().__init__(code, message, **kwargs)


class NotFound(PluginError):
    def __init__(self, plugin_id: str) -> None:
        super().__init__(
            "PLUGIN_NOT_FOUND",
            f"no plugin {plugin_id!r} is installed",
            detail={"plugin_id": plugin_id},
        )


class CompatibilityError(PluginError):
    def __init__(self, message: str, *, detail: Optional[dict[str, Any]] = None) -> None:
        super().__init__("PLUGIN_INCOMPATIBLE", message, detail=detail)


class DependencyError(PluginError):
    def __init__(self, message: str, *, detail: Optional[dict[str, Any]] = None) -> None:
        super().__init__("PLUGIN_DEPENDENCY_ERROR", message, detail=detail)


__all__ = [
    "PluginError",
    "ManifestError",
    "PermissionDenied",
    "LifecycleError",
    "NotFound",
    "CompatibilityError",
    "DependencyError",
]
