"""ASGI middleware + exception handler for SDK locks.

Kept out of `main.py` (which has a line ceiling). The middleware places the
request's `X-Eclipse-Unlock` token in the SDK contextvar for the lifetime of the
request; a token is a capability, never an identity. Agent tool runs carry no
request header and therefore obey locks normally.
"""

from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse

from .locks import LockError, unlock_token_var


class SdkUnlockMiddleware:
    """Pure ASGI middleware so the contextvar is set in the routers' task."""

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return
        headers = dict(scope.get("headers") or [])
        raw = headers.get(b"x-eclipse-unlock")
        handle = unlock_token_var.set(raw.decode("utf-8", "ignore") if raw else None)
        try:
            await self.app(scope, receive, send)
        finally:
            unlock_token_var.reset(handle)


async def sdk_lock_exception_handler(request: Request, exc: LockError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "detail": {
                "code": exc.code,
                "message": exc.message,
                "lockId": exc.lock_id,
                "resourceType": exc.resource_type,
                "resourceId": exc.resource_id,
                "hint": exc.hint,
            }
        },
    )


def install_sdk(app: Any) -> None:
    """Install the lock middleware/handler AND the `/sdk` route group."""
    app.add_middleware(SdkUnlockMiddleware)
    app.add_exception_handler(LockError, sdk_lock_exception_handler)
    from ..routers.sdk import router as sdk_router  # noqa: PLC0415

    app.include_router(sdk_router)


__all__ = ["SdkUnlockMiddleware", "install_sdk", "sdk_lock_exception_handler"]
