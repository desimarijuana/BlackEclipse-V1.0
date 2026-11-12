"""The sandbox's own health surface (`/sandbox`).

The audit's hardest finding was that the isolation boundary was invisible: an
operator could not tell which primitive was in force, which interpreter ran the
code, or what it had installed — and a platform with no primitive at all
degraded silently. This route makes the boundary OBSERVABLE, and lets an
operator REQUIRE a real one (`HARNESS_SANDBOX_REQUIRED=1`): with it set, a run
that cannot get a real isolation primitive refuses instead of running locally.
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, HTTPException

router = APIRouter()


def _sandbox_state() -> dict[str, Any]:
    from ..code import sandbox as sandbox_mod  # noqa: PLC0415
    from ..code.execution import interpreter_path, package_lock_digest  # noqa: PLC0415

    backend = sandbox_mod.backend_name()
    return {
        "backend": backend,
        "isolation": {
            "processTreeKill": True,
            "memoryLimitMb": True,
            "processLimit": True,
            "cpuLimit": "sampled (0.25s) on Windows; rlimit on POSIX",
            "filesystemIsolation": False,
            "networkIsolation": False,
            "runtimeGuard": "python-level (guarded import, safe os/sys/importlib, audit hook, confined readers)",
        },
        "interpreter": interpreter_path() or None,
        "packageLockDigest": package_lock_digest() or None,
        "required": sandbox_mod.isolation_required(),
        "satisfied": sandbox_mod.isolation_satisfied(),
        "profiles": _profile_report(),
    }


def _profile_report() -> list[dict[str, Any]]:
    """C6: per-profile enforceability on this host (honest `missing` names)."""
    try:
        from ..security.profiles import describe_profiles  # noqa: PLC0415

        return describe_profiles()
    except Exception:  # noqa: BLE001 - observability must never break the route
        return []


@router.get("/sandbox")
def get_sandbox() -> dict[str, Any]:
    """What isolation is in force, and what the runtime will run code with."""
    state = _sandbox_state()
    if state.get("required") and not state.get("satisfied"):
        raise HTTPException(
            status_code=503,
            detail=(
                "the operator requires a real isolation primitive and the local "
                "backend does not provide filesystem or network isolation"
            ),
        )
    return {"success": True, **state}


__all__ = ["router"]
