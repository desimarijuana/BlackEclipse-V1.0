"""Browser HTTP routes — the operator/UI surface over the shared browser manager.

Every route is `require_operator` (transport/token), exactly like the terminal,
code and workspace routers. The routes are thin adapters over
`harness.deps.service.browser` — the SAME manager the agent tools use, so the UI
and the agent can never disagree about browser state. They never expose a secret:
the vault routes return references and resolvability, never a value.
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..deps import require_operator, service

router = APIRouter(tags=["browser"])


def _manager():
    manager = getattr(service, "browser", None)
    if manager is None:
        raise HTTPException(status_code=503, detail="the browser capability is unavailable")
    return manager


def browser_health() -> dict[str, Any]:
    """The browser runtime's honest availability + provider list. Never raises.

    Returned inside `/health` so a missing Playwright/Chromium is observable at
    boot, not a runtime surprise.
    """
    manager = getattr(service, "browser", None)
    if manager is None:
        return {"available": False, "providers": [], "sessions": 0}
    try:
        caps = manager.capabilities()
        return {
            "available": True,
            "enabled": caps.get("enabled"),
            "defaultProvider": caps.get("defaultProvider"),
            "providers": [
                {"id": p["id"], "available": p["availability"].get("available"),
                 "reason": p["availability"].get("reason")}
                for p in caps.get("providers", [])
            ],
            "sessions": manager.active_count(),
            "toolCount": len([n for n in service.registry.names() if n.startswith("browser_")]),
            # Content-free aggregate counters (Phase 8.2). Never raises.
            "telemetry": _telemetry_summary(manager),
        }
    except Exception:  # noqa: BLE001 - a health probe must never break /health
        return {"available": False, "providers": [], "sessions": 0}


def _telemetry_summary(manager: Any) -> dict[str, Any]:
    try:
        snapshot = manager.telemetry_snapshot()
    except Exception:  # noqa: BLE001
        return {}
    actions = snapshot.get("actions", {})
    sessions = snapshot.get("sessions", {})
    return {
        "sessionsCreated": sessions.get("created"),
        "activeSessions": sessions.get("active"),
        "actionCalls": actions.get("calls"),
        "actionFailures": actions.get("failures"),
        "timeouts": actions.get("timeouts"),
        "crashes": actions.get("crashes"),
        "providerFailures": actions.get("providerFailures"),
    }


@router.get("/browser/capabilities")
def browser_capabilities(_: bool = Depends(require_operator)) -> dict[str, Any]:
    """Which providers exist, their declared capabilities and honest availability."""
    manager = getattr(service, "browser", None)
    if manager is None:
        return {"success": True, "available": False, "providers": []}
    return {"success": True, "available": True, **manager.capabilities()}


def _chromium_installed() -> tuple[bool, Optional[str]]:
    """Whether a Playwright Chromium binary is present. Never raises."""
    try:
        from ..browser.providers.local_chromium import _playwright_available, _browser_installed  # noqa: PLC0415
        from playwright.sync_api import sync_playwright  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001
        return False, f"Python Playwright is not installed ({type(exc).__name__})"
    ok, reason = _playwright_available()
    if not ok:
        return False, reason
    try:
        with sync_playwright() as p:
            return _browser_installed(p, "chromium"), None
    except Exception as exc:  # noqa: BLE001
        return False, f"could not probe the browser binary: {exc}"


@router.get("/browser/install")
def browser_install_status(_: bool = Depends(require_operator)) -> dict[str, Any]:
    """Honest status of the one-click JS-rendering enablement. Read-only."""
    installed, reason = _chromium_installed()
    return {
        "success": True,
        "installed": installed,
        "reason": reason,
        "command": "python -m playwright install chromium",
    }


class InstallBrowserRequest(BaseModel):
    with_deps: bool = True


@router.post("/browser/install")
async def install_browser(
    body: InstallBrowserRequest, _: bool = Depends(require_operator),
) -> dict[str, Any]:
    """One-click enablement of JS rendering: install Playwright + Chromium.

    Idempotent and honest: if the browser is already present it does nothing. The
    Chromium download is a one-time, ~150 MB fetch run in a bounded subprocess; a
    failure returns the captured stderr, never a silent success. Nothing here
    fabricates a browser — the local runtime reports the binary's true presence.
    """
    import asyncio  # noqa: PLC0415
    import sys  # noqa: PLC0415

    installed, _reason = _chromium_installed()
    if installed:
        return {"success": True, "installed": True, "alreadyInstalled": True, "output": ""}

    output: list[str] = []

    async def _run(args: list[str], timeout: float) -> int:
        proc = await asyncio.create_subprocess_exec(
            sys.executable, *args,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
        )
        try:
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            proc.kill()
            output.append(f"timed out: {' '.join(args)}")
            return -1
        if stdout:
            output.append(stdout.decode("utf-8", "replace")[-4000:])
        return proc.returncode or 0

    if body.with_deps:
        # Ensure the Playwright Python package is present before the browser fetch.
        rc = await _run(["-m", "pip", "install", "playwright>=1.62,<1.63"], timeout=420)
        if rc != 0:
            return {
                "success": False, "installed": False,
                "error": "could not install the Playwright package",
                "output": "\n".join(output),
            }

    rc = await _run(["-m", "playwright", "install", "chromium"], timeout=900)
    if rc != 0:
        return {
            "success": False, "installed": False,
            "error": "the Chromium download failed",
            "output": "\n".join(output),
        }

    now_installed, reason = _chromium_installed()
    return {
        "success": now_installed,
        "installed": now_installed,
        "reason": reason,
        "output": "\n".join(output),
    }


@router.get("/browser/sessions")
def list_browser_sessions(_: bool = Depends(require_operator)) -> dict[str, Any]:
    return {"success": True, "sessions": _manager().list_sessions()}


@router.get("/browser/sessions/{session_id}")
def get_browser_session(session_id: str, _: bool = Depends(require_operator)) -> dict[str, Any]:
    session = _manager().get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="no such browser session")
    return {"success": True, "session": session.snapshot_summary()}


class CreateSessionRequest(BaseModel):
    url: Optional[str] = None
    provider: Optional[str] = None
    headless: Optional[bool] = None
    profile: Optional[str] = Field(default=None, max_length=64)
    persistent: bool = False


@router.post("/browser/sessions")
async def create_browser_session(
    body: CreateSessionRequest, _: bool = Depends(require_operator),
) -> dict[str, Any]:
    from ..browser.errors import BrowserError  # noqa: PLC0415

    manager = _manager()
    try:
        session = await manager.create_session(
            provider=body.provider, url=body.url, headless=body.headless,
            profile_id=body.profile, persistent=body.persistent,
        )
    except BrowserError as exc:
        raise HTTPException(status_code=503, detail=exc.to_dict()) from exc
    return {"success": True, "session": session.snapshot_summary()}


@router.delete("/browser/sessions/{session_id}")
async def destroy_browser_session(session_id: str, _: bool = Depends(require_operator)) -> dict[str, Any]:
    result = await _manager().destroy_session(session_id)
    if not result.get("destroyed"):
        raise HTTPException(status_code=404, detail="no such browser session")
    return {"success": True, **result}


@router.get("/browser/profiles")
def list_browser_profiles(_: bool = Depends(require_operator)) -> dict[str, Any]:
    return {"success": True, "profiles": _manager().profiles.list_profiles()}


@router.get("/browser/vault")
def list_browser_vault(_: bool = Depends(require_operator)) -> dict[str, Any]:
    """Credential REFERENCES and content-free metadata only — never a value."""
    return {"success": True, "entries": _manager().vault.list_entries()}


@router.get("/browser/traces")
def list_browser_traces(limit: int = 50, _: bool = Depends(require_operator)) -> dict[str, Any]:
    manager = _manager()
    if manager.store is None:
        return {"success": True, "traces": []}
    return {"success": True, "traces": manager.store.list_traces(limit)}


@router.get("/browser/traces/{trace_id}")
def get_browser_trace(trace_id: str, _: bool = Depends(require_operator)) -> dict[str, Any]:
    manager = _manager()
    trace = manager.store.get_trace(trace_id) if manager.store is not None else None
    if trace is None:
        raise HTTPException(status_code=404, detail="no such browser trace")
    return {"success": True, "trace": trace}


@router.get("/browser/traces/{trace_id}/replay")
def replay_browser_trace(trace_id: str, _: bool = Depends(require_operator)) -> dict[str, Any]:
    """A browser-free, bounded replay timeline of a stored trace (Phase 8.1)."""
    from ..browser.replay import render_text, replay_trace  # noqa: PLC0415

    manager = _manager()
    trace = manager.store.get_trace(trace_id) if manager.store is not None else None
    if trace is None:
        raise HTTPException(status_code=404, detail="no such browser trace")
    view = replay_trace(trace)
    return {"success": True, "replay": view, "text": render_text(view)}


@router.get("/browser/telemetry")
def browser_telemetry(_: bool = Depends(require_operator)) -> dict[str, Any]:
    """The content-free aggregate: sessions, actions, failures, latency, cost."""
    return {"success": True, **(_manager().telemetry_snapshot())}


@router.get("/browser/cost")
def browser_cost(_: bool = Depends(require_operator)) -> dict[str, Any]:
    """Real measurements + a cost estimate ONLY when rates are configured."""
    return {"success": True, **(_manager().telemetry_cost())}


@router.get("/browser/logs")
def browser_logs(
    code: Optional[str] = None,
    level: Optional[str] = None,
    category: Optional[str] = None,
    session_id: Optional[str] = None,
    limit: int = 100,
    _: bool = Depends(require_operator),
) -> dict[str, Any]:
    """Query the bounded structured browser log by code/level/category/session."""
    entries = _manager().recent_logs(
        code=code, level=level, category=category, session_id=session_id, limit=limit,
    )
    return {"success": True, "logs": entries, "count": len(entries)}


@router.get("/browser/tasks")
def list_browser_tasks(_: bool = Depends(require_operator)) -> dict[str, Any]:
    """In-flight + recent browser task progress records (content-free)."""
    manager = _manager()
    tasks = getattr(manager, "tasks", None)
    if tasks is None:
        return {"success": True, "tasks": []}
    return {"success": True, "tasks": [t.to_dict() for t in tasks.list()]}


@router.get("/browser/downloads")
def list_browser_downloads(session_id: Optional[str] = None, limit: int = 50, _: bool = Depends(require_operator)) -> dict[str, Any]:
    manager = _manager()
    if manager.store is None:
        return {"success": True, "downloads": []}
    return {"success": True, "downloads": manager.store.list_downloads(session_id, limit)}


__all__ = ["browser_health", "router"]
