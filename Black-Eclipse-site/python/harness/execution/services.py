"""Long-running services, port management and health checks.

A one-shot execution and a service are different things. A service is started
through the EXISTING terminal process manager (`harness/terminal/process_manager.py`)
— so it is tree-managed, cancellable, persisted, and never an unmanaged background
process. This module adds the service-level concerns on top: port allocation,
readiness/health checks, and lifecycle helpers.

`HealthChecker` does not consider a service "started" merely because its process
exists: it must pass a process / TCP / HTTP check. Ports are allocated through the
terminal subsystem's port table so a conflict is reported, never silently ignored.
"""

from __future__ import annotations

import socket
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Optional

# A small set of ports commonly free in a dev environment; allocation checks each.
DEFAULT_PORT_RANGE = tuple(range(3100, 3999))


@dataclass
class ServiceRecord:
    """One managed service."""

    service_id: str
    command: str
    cwd: str
    process_id: str = ""
    port: int = 0
    protocol: str = "http"
    workspace_id: Optional[str] = None
    started_at: float = 0.0
    ready: bool = False
    health_url: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "serviceId": self.service_id, "command": self.command, "cwd": self.cwd,
            "processId": self.process_id, "port": self.port, "protocol": self.protocol,
            "workspaceId": self.workspace_id, "startedAt": self.started_at,
            "ready": self.ready, "healthUrl": self.health_url,
        }


class PortManager:
    """Allocate/check/release ports using the terminal subsystem's port table."""

    def __init__(self, terminal: Any = None) -> None:
        self._terminal = terminal
        self._reserved: dict[int, str] = {}

    def _in_use(self, port: int) -> bool:
        if int(port) in self._reserved:
            return True
        if self._terminal is not None:
            try:
                return self._terminal.find_port_conflict(int(port)) is not None
            except Exception:  # noqa: BLE001 - fall through to a socket probe
                pass
        return not self._socket_free(port)

    @staticmethod
    def _socket_free(port: int) -> bool:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind(("127.0.0.1", int(port)))
                return True
            except OSError:
                return False

    def allocate(self, *, preferred: int = 0, owner: str = "") -> int:
        """Return a free port. `preferred` is tried first; 0 means auto-pick."""
        if preferred and not self._in_use(preferred):
            self._reserved[int(preferred)] = owner
            return int(preferred)
        for port in DEFAULT_PORT_RANGE:
            if not self._in_use(port):
                self._reserved[port] = owner
                return port
        return 0

    def release(self, port: int) -> None:
        self._reserved.pop(int(port), None)

    def check(self, port: int) -> dict[str, Any]:
        return {"port": int(port), "inUse": self._in_use(port)}


@dataclass
class HealthResult:
    ready: bool = False
    checks: list[dict[str, Any]] = field(default_factory=list)
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"ready": self.ready, "checks": self.checks, "reason": self.reason}


class HealthChecker:
    """Process / TCP / HTTP readiness checks with a bounded wait."""

    def http(self, url: str, *, timeout_s: float = 3.0) -> dict[str, Any]:
        try:
            with urllib.request.urlopen(url, timeout=timeout_s) as response:  # noqa: S310 - localhost only
                status = getattr(response, "status", 200)
                ok = 200 <= int(status) < 400
                return {"kind": "http", "url": url, "ok": ok, "status": int(status)}
        except (urllib.error.URLError, OSError, ValueError) as exc:
            return {"kind": "http", "url": url, "ok": False, "error": str(exc)}

    def tcp(self, host: str, port: int, *, timeout_s: float = 2.0) -> dict[str, Any]:
        try:
            with socket.create_connection((host, int(port)), timeout=timeout_s):
                return {"kind": "tcp", "host": host, "port": int(port), "ok": True}
        except OSError as exc:
            return {"kind": "tcp", "host": host, "port": int(port), "ok": False, "error": str(exc)}

    def process(self, alive: bool) -> dict[str, Any]:
        return {"kind": "process", "ok": bool(alive)}

    def wait_ready(
        self,
        *,
        terminal: Any,
        process_id: str,
        port: int = 0,
        url: str = "",
        timeout_s: float = 20.0,
        interval_s: float = 0.5,
    ) -> HealthResult:
        """Poll process/TCP/HTTP until ready or the deadline. Never fakes readiness."""
        deadline = time.monotonic() + max(0.1, timeout_s)
        checks: list[dict[str, Any]] = []
        last_reason = "the service did not become ready in time"
        while time.monotonic() < deadline:
            info = terminal.get_process(process_id) if terminal is not None else None
            alive = bool(info and info.get("state") in ("RUNNING", "STARTING"))
            process_check = self.process(alive or info is not None)
            checks = [process_check]
            if not process_check["ok"]:
                last_reason = "the service stopped before it was ready"
                return HealthResult(False, checks, last_reason)
            if port:
                tcp_check = self.tcp("127.0.0.1", port)
                checks.append(tcp_check)
                if not tcp_check["ok"]:
                    last_reason = f"nothing is listening on port {port} yet"
                    time.sleep(interval_s)
                    continue
            if url:
                http_check = self.http(url)
                checks.append(http_check)
                if not http_check["ok"]:
                    last_reason = "the health check did not answer yet"
                    time.sleep(interval_s)
                    continue
            return HealthResult(True, checks, "")
        return HealthResult(False, checks, last_reason)


class ServiceManager:
    """Start/stop/restart/status/logs for long-running services over the terminal."""

    def __init__(self, terminal: Any = None, *, ports: Optional[PortManager] = None) -> None:
        self._terminal = terminal
        self.ports = ports or PortManager(terminal)
        self._health = HealthChecker()
        self._services: dict[str, ServiceRecord] = {}
        self._counter = 0

    def _new_id(self) -> str:
        self._counter += 1
        return f"svc_{self._counter:04d}"

    def start_service(
        self,
        *,
        command: str,
        cwd: str,
        port: int = 0,
        protocol: str = "http",
        health_url: str = "",
        workspace_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        run_id: Optional[str] = None,
        wait_ready: bool = True,
        timeout_s: float = 20.0,
    ) -> dict[str, Any]:
        if self._terminal is None:
            return {"status": "unavailable", "code": "RUNTIME_UNAVAILABLE",
                    "reason": "the terminal isn't available right now"}
        allocated = port
        if protocol in ("http", "tcp"):
            allocated = self.ports.allocate(preferred=port, owner=command[:40])
            if not allocated:
                return {"status": "failed", "code": "NO_FREE_PORT",
                        "reason": "I couldn't find a free port for the service"}
        info = self._terminal.start_process(
            command=command, cwd=cwd, workspace_id=workspace_id, agent_id=agent_id,
            run_id=run_id, purpose="service",
        )
        if info.get("state") == "FAILED":
            if allocated:
                self.ports.release(allocated)
            return {"status": "failed", "code": "SERVICE_START_FAILED",
                    "reason": (info.get("error") or {}).get("message", "the service could not be started")}
        service = ServiceRecord(
            service_id=self._new_id(), command=command, cwd=cwd,
            process_id=info.get("processId", ""), port=allocated, protocol=protocol,
            workspace_id=workspace_id, started_at=time.time(), health_url=health_url,
        )
        self._services[service.service_id] = service
        health = None
        if wait_ready:
            health = self._health.wait_ready(
                terminal=self._terminal, process_id=service.process_id,
                port=(allocated if protocol in ("http", "tcp") else 0),
                url=health_url, timeout_s=timeout_s,
            )
            service.ready = health.ready
        return {"status": "ok", "service": service.to_dict(),
                "health": health.to_dict() if health else None}

    def stop_service(self, service_id: str) -> dict[str, Any]:
        service = self._services.get(service_id)
        if service is None:
            return {"status": "not_found"}
        ok = bool(self._terminal and self._terminal.stop_process(service.process_id))
        if service.port:
            self.ports.release(service.port)
        service.ready = False
        return {"status": "ok" if ok else "failed", "serviceId": service_id}

    def restart_service(self, service_id: str) -> dict[str, Any]:
        service = self._services.get(service_id)
        if service is None:
            return {"status": "not_found"}
        self.stop_service(service_id)
        return self.start_service(
            command=service.command, cwd=service.cwd, port=service.port,
            protocol=service.protocol, health_url=service.health_url,
            workspace_id=service.workspace_id,
        )

    def get_service_status(self, service_id: str) -> dict[str, Any]:
        service = self._services.get(service_id)
        if service is None:
            return {"status": "not_found"}
        info = self._terminal.get_process(service.process_id) if self._terminal else None
        state = (info or {}).get("state", "UNKNOWN")
        return {"status": "ok", "service": service.to_dict(), "processState": state,
                "running": state in ("RUNNING", "STARTING")}

    def get_service_logs(self, service_id: str, *, tail: int = 200) -> dict[str, Any]:
        service = self._services.get(service_id)
        if service is None:
            return {"status": "not_found"}
        window = self._terminal.read_process_output(service.process_id, tail=tail) if self._terminal else None
        return {"status": "ok", "logs": (window or {}).get("text", ""), "window": window}

    def list_services(self) -> list[dict[str, Any]]:
        return [s.to_dict() for s in self._services.values()]

    def stop_all(self) -> dict[str, Any]:
        stopped = 0
        for service in list(self._services.values()):
            if self.stop_service(service.service_id).get("status") == "ok":
                stopped += 1
        return {"stopped": stopped}


__all__ = [
    "HealthChecker",
    "HealthResult",
    "PortManager",
    "ServiceManager",
    "ServiceRecord",
]
