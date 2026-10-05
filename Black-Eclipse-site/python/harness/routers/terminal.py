"""Terminal HTTP routes — the UI surface over the shared terminal manager.

Every route is `require_operator` (transport/token), exactly like the code and
workspace routers, so only the local Next.js front door (loopback) or an
authorized operator can drive the terminal. Reads are operator-gated too: the
terminal is a powerful surface, so even enumerating processes is not anonymous.

The routes are thin adapters over `harness.deps.service.terminal` — the SAME
manager the agent tools use, so UI and agent can never disagree about state.
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..deps import require_operator, service

router = APIRouter(tags=["terminal"])


class ExecuteRequest(BaseModel):
    command: str = Field(min_length=1, max_length=4_000)
    cwd: Optional[str] = Field(default=None, max_length=1_000)
    shell: Optional[str] = Field(default=None, max_length=64)
    runtime: str = Field(default="local", max_length=16)
    timeoutMs: Optional[int] = Field(default=None, ge=100, le=900_000)  # noqa: N815
    purpose: str = Field(default="", max_length=64)


class OpenShellRequest(BaseModel):
    shell: Optional[str] = Field(default=None, max_length=64)
    runtime: str = Field(default="local", max_length=16)
    cwd: Optional[str] = Field(default=None, max_length=1_000)
    rows: int = Field(default=24, ge=1, le=500)
    columns: int = Field(default=80, ge=1, le=500)


class RunShellRequest(BaseModel):
    command: str = Field(min_length=1, max_length=4_000)
    timeoutMs: Optional[int] = Field(default=None, ge=100, le=900_000)  # noqa: N815


class InputRequest(BaseModel):
    input: str = Field(max_length=10_000)
    newline: bool = True


class ResizeRequest(BaseModel):
    rows: int = Field(ge=1, le=500)
    columns: int = Field(ge=1, le=500)


class StartProcessRequest(BaseModel):
    command: str = Field(min_length=1, max_length=4_000)
    cwd: Optional[str] = Field(default=None, max_length=1_000)
    shell: Optional[str] = Field(default=None, max_length=64)
    runtime: str = Field(default="local", max_length=16)
    purpose: str = Field(default="", max_length=64)


class SignalRequest(BaseModel):
    signal: str = Field(min_length=1, max_length=16)


def _root_or_400():
    from ..code.workspace import default_root  # noqa: PLC0415

    root = default_root()
    if root is None:
        raise HTTPException(status_code=503, detail="no workspace root is selected")
    return root


def _confine(root, requested: Optional[str]):
    from ..code.policy import PolicyDenial, resolve_within  # noqa: PLC0415

    if not requested:
        return root
    try:
        resolved = resolve_within(root, requested)
    except PolicyDenial as exc:
        raise HTTPException(status_code=400, detail={"code": exc.code, "message": exc.reason}) from exc
    if not resolved.is_dir():
        raise HTTPException(status_code=400, detail="that working directory is not a folder")
    return resolved


# ── Foreground ──────────────────────────────────────────────────────────────


@router.post("/terminal/execute")
async def terminal_execute(body: ExecuteRequest, _: bool = Depends(require_operator)) -> dict[str, Any]:
    root = _confine(_root_or_400(), body.cwd)
    result = service.terminal.execute_command(
        command=body.command, cwd=str(root), shell=body.shell, runtime=body.runtime,
        timeout_ms=int(body.timeoutMs or 120_000), purpose=body.purpose or None,
    )
    return {"success": True, "result": result.to_dict()}


# ── Sessions ────────────────────────────────────────────────────────────────


@router.get("/terminal/capabilities")
def terminal_capabilities(_: bool = Depends(require_operator)) -> dict[str, Any]:
    return {"success": True, "capabilities": service.terminal.capabilities()}


@router.get("/terminal/sessions")
def list_sessions(_: bool = Depends(require_operator)) -> dict[str, Any]:
    return {"success": True, "sessions": service.terminal.list_shells()}


@router.post("/terminal/sessions")
def open_session(body: OpenShellRequest, _: bool = Depends(require_operator)) -> dict[str, Any]:
    from ..terminal.runtimes import RuntimeUnavailable, select_runtime  # noqa: PLC0415

    try:
        runtime = select_runtime(body.runtime)
        if not getattr(runtime, "available", False):
            raise RuntimeUnavailable("RUNTIME_UNAVAILABLE", "that runtime is not available on this computer")
    except RuntimeUnavailable as exc:
        raise HTTPException(status_code=503, detail=exc.reason) from exc
    cwd = _confine(_root_or_400(), body.cwd)
    try:
        info = service.terminal.open_shell(
            shell_name=body.shell, runtime=body.runtime, cwd=str(cwd),
            rows=body.rows, columns=body.columns,
        )
    except Exception as exc:  # noqa: BLE001 - a failed start is a 503
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"success": True, "session": info}


@router.get("/terminal/sessions/{session_id}")
def get_session(session_id: str, _: bool = Depends(require_operator)) -> dict[str, Any]:
    info = service.terminal.get_shell(session_id)
    if info is None:
        raise HTTPException(status_code=404, detail="no such session")
    return {"success": True, "session": info}


@router.delete("/terminal/sessions/{session_id}")
def close_session(session_id: str, _: bool = Depends(require_operator)) -> dict[str, Any]:
    if not service.terminal.close_shell(session_id):
        raise HTTPException(status_code=404, detail="no such session")
    return {"success": True, "sessionId": session_id}


@router.post("/terminal/sessions/{session_id}/run")
async def run_in_session(session_id: str, body: RunShellRequest, _: bool = Depends(require_operator)) -> dict[str, Any]:
    root = _root_or_400()
    timeout_s = int((body.timeoutMs or 120_000) // 1000) or 1
    result = service.terminal.run_in_shell(session_id, body.command, timeout_s=timeout_s, workspace_root=str(root))
    if result is None:
        raise HTTPException(status_code=404, detail="no such session")
    return {"success": True, "result": result}


@router.post("/terminal/sessions/{session_id}/input")
def send_session_input(session_id: str, body: InputRequest, _: bool = Depends(require_operator)) -> dict[str, Any]:
    if not service.terminal.write_shell_input(session_id, body.input, newline=body.newline):
        raise HTTPException(status_code=404, detail="no such session")
    return {"success": True}


@router.get("/terminal/sessions/{session_id}/output")
def read_session_output(
    session_id: str, stream: Optional[str] = None, tail: Optional[int] = None,
    cursor: Optional[int] = None, _: bool = Depends(require_operator),
) -> dict[str, Any]:
    window = service.terminal.read_shell_output(session_id, stream=stream, tail=tail, cursor=cursor)
    if window is None:
        raise HTTPException(status_code=404, detail="no such session")
    return {"success": True, "output": window}


@router.post("/terminal/sessions/{session_id}/control")
def send_session_control(session_id: str, body: SignalRequest, _: bool = Depends(require_operator)) -> dict[str, Any]:
    if not service.terminal.send_control(session_id, body.signal):
        raise HTTPException(status_code=404, detail="no such session")
    return {"success": True}


@router.post("/terminal/sessions/{session_id}/resize")
def resize_session(session_id: str, body: ResizeRequest, _: bool = Depends(require_operator)) -> dict[str, Any]:
    if service.terminal.get_shell(session_id) is None:
        raise HTTPException(status_code=404, detail="no such session")
    return {"success": True, "resized": service.terminal.resize_shell(session_id, body.rows, body.columns)}


# ── Processes ───────────────────────────────────────────────────────────────


@router.get("/terminal/processes")
def list_processes(_: bool = Depends(require_operator)) -> dict[str, Any]:
    return {"success": True, "processes": service.terminal.list_processes()}


@router.post("/terminal/processes")
def start_process(body: StartProcessRequest, _: bool = Depends(require_operator)) -> dict[str, Any]:
    root = _confine(_root_or_400(), body.cwd)
    info = service.terminal.start_process(
        command=body.command, cwd=str(root), shell=body.shell, runtime=body.runtime,
        purpose=body.purpose or None,
    )
    return {"success": True, "process": info}


@router.get("/terminal/processes/{process_id}")
def get_process(process_id: str, _: bool = Depends(require_operator)) -> dict[str, Any]:
    info = service.terminal.get_process(process_id)
    if info is None:
        raise HTTPException(status_code=404, detail="no such process")
    return {"success": True, "process": info}


@router.post("/terminal/processes/{process_id}/stop")
def stop_process(process_id: str, _: bool = Depends(require_operator)) -> dict[str, Any]:
    if not service.terminal.stop_process(process_id):
        raise HTTPException(status_code=404, detail="no such running process")
    return {"success": True}


@router.post("/terminal/processes/{process_id}/kill")
def kill_process(process_id: str, _: bool = Depends(require_operator)) -> dict[str, Any]:
    if not service.terminal.kill_process(process_id):
        raise HTTPException(status_code=404, detail="no such process")
    return {"success": True}


@router.post("/terminal/processes/{process_id}/restart")
def restart_process(process_id: str, _: bool = Depends(require_operator)) -> dict[str, Any]:
    info = service.terminal.restart_process(process_id)
    if info is None:
        raise HTTPException(status_code=404, detail="no such process")
    return {"success": True, "process": info}


@router.get("/terminal/processes/{process_id}/output")
def read_process_output(
    process_id: str, stream: Optional[str] = None, tail: Optional[int] = None,
    cursor: Optional[int] = None, _: bool = Depends(require_operator),
) -> dict[str, Any]:
    window = service.terminal.read_process_output(process_id, stream=stream, tail=tail, cursor=cursor)
    if window is None:
        raise HTTPException(status_code=404, detail="no such process")
    return {"success": True, "output": window}


@router.post("/terminal/processes/{process_id}/input")
def write_process_input(process_id: str, body: InputRequest, _: bool = Depends(require_operator)) -> dict[str, Any]:
    if not service.terminal.write_process_input(process_id, body.input, newline=body.newline):
        raise HTTPException(status_code=404, detail="that process is not accepting input")
    return {"success": True}


@router.post("/terminal/processes/{process_id}/signal")
def signal_process(process_id: str, body: SignalRequest, _: bool = Depends(require_operator)) -> dict[str, Any]:
    result = service.terminal.send_signal(process_id, body.signal)
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result)
    return {"success": True, "result": result}


@router.get("/terminal/processes/{process_id}/tree")
def process_tree(process_id: str, _: bool = Depends(require_operator)) -> dict[str, Any]:
    tree = service.terminal.process_tree(process_id)
    if tree is None:
        raise HTTPException(status_code=404, detail="no such process")
    return {"success": True, "tree": tree}


# ── Ports / system ─────────────────────────────────────────────────────────────


@router.get("/terminal/ports")
def list_ports(port: Optional[int] = None, _: bool = Depends(require_operator)) -> dict[str, Any]:
    if port is not None:
        return {"success": True, "port": port, "owner": service.terminal.find_port_conflict(port)}
    return {"success": True, "ports": service.terminal.list_ports(), "summary": service.terminal.port_summary()}


@router.get("/terminal/system")
def system_info(_: bool = Depends(require_operator)) -> dict[str, Any]:
    import os

    caps = service.terminal.capabilities()
    processes = service.terminal.list_processes()
    return {
        "success": True,
        "platform": caps["platform"], "architecture": caps["architecture"],
        "defaultShell": caps["defaultShell"], "shells": caps["availableShells"],
        "wsl": caps["wsl"], "runtimes": caps["runtimes"], "pty": caps["pty"],
        "processCount": len(processes),
        "runningCount": len([p for p in processes if p["state"] == "RUNNING"]),
        "sessionCount": len(service.terminal.list_shells()),
        "listeningPorts": len(service.terminal.list_ports()),
        "cpuCount": os.cpu_count(),
    }


__all__ = ["router"]
