"""Docker Compose (and Podman Compose) — one front end over a container engine.

A compose adapter understands the SERVICE GRAPH: it validates/configures a
compose file, brings services up/down, reads per-service status, tails per-service
logs and execs into a service. It is driven by the SAME container engine
(`ContainerRuntimeAdapter`) it belongs to — Docker Compose for Docker, `podman
compose` or `podman-compose` for Podman — so there is no second container path.

All argv is built from validated arguments; the compose file is always the
project's own discovered file (never a model-supplied path). Output is parsed
(JSON where the engine supports it) into structured service records.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from ...code import sandbox
from ..models import ResourceLimits
from .registry import (
    CAP_COMPOSE_CONFIG,
    CAP_COMPOSE_DOWN,
    CAP_COMPOSE_EXEC,
    CAP_COMPOSE_LIFECYCLE,
    CAP_COMPOSE_LOGS,
    CAP_COMPOSE_PS,
    CAP_COMPOSE_UP,
    CAP_COMPOSE_VALIDATE,
)


@dataclass
class ComposeResult:
    ok: bool = False
    code: str = "OK"
    operation: str = ""
    kind: str = "compose"
    exit_code: Optional[int] = None
    argv: list[str] = field(default_factory=list)
    output: str = ""
    services: list[dict[str, Any]] = field(default_factory=list)
    data: Any = None
    duration_ms: int = 0
    timed_out: bool = False
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok, "code": self.code, "operation": self.operation,
            "kind": self.kind, "exitCode": self.exit_code, "argv": list(self.argv),
            "output": self.output, "services": self.services, "data": self.data,
            "durationMs": self.duration_ms, "timedOut": self.timed_out, "reason": self.reason,
        }


def _valid_name(name: str) -> bool:
    import re

    return bool(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", str(name or "")))


class ComposeAdapter:
    """A compose front end keyed by the container engine it drives."""

    kind = "compose"
    name = "compose"
    engine = "docker"
    capabilities: frozenset[str] = frozenset(
        {
            CAP_COMPOSE_VALIDATE, CAP_COMPOSE_CONFIG, CAP_COMPOSE_UP, CAP_COMPOSE_DOWN,
            CAP_COMPOSE_LIFECYCLE, CAP_COMPOSE_LOGS, CAP_COMPOSE_EXEC, CAP_COMPOSE_PS,
        }
    )
    compose_subcommands = ("up", "down", "start", "stop", "restart", "ps", "logs", "exec", "config", "build", "pull", "rm")

    def __init__(self, *, limits: Optional[ResourceLimits] = None) -> None:
        self._limits = limits

    @property
    def limits(self) -> ResourceLimits:
        return self._limits or ResourceLimits.from_env()

    # ── argv construction ─────────────────────────────────────────────────────────
    def _base(self) -> list[str]:
        """The compose command prefix: `docker compose` or `podman compose`."""
        engine = shutil.which(self.engine)
        if self.engine == "docker":
            return [engine or "docker", "compose"]
        # Podman: prefer the built-in `podman compose`, else `podman-compose`.
        if engine:
            return [engine, "compose"]
        standalone = shutil.which("podman-compose")
        return [standalone] if standalone else []

    def available(self) -> bool:
        return bool(self._base()) and bool(self._base()[0])

    def version(self) -> str:
        base = self._base()
        if not base:
            return ""
        result = self._exec(base + ["version"], timeout_s=10)
        return (result.output or "").strip().splitlines()[0] if result.output else ""

    def _compose_file_args(self, compose_file: str) -> list[str]:
        return ["-f", compose_file] if compose_file else []

    def _exec(self, argv: list[str], *, timeout_s: int = 600, network: bool = True) -> ComposeResult:
        env = sandbox.build_env()
        spec = sandbox.RunSpec(
            argv=list(argv), cwd=Path.cwd(), env=env, timeout_s=timeout_s,
            output_cap_bytes=self.limits.max_stdout_bytes, network=network,
        )
        try:
            raw = sandbox.run(spec)
        except sandbox.SandboxUnavailable as exc:
            return ComposeResult(ok=False, code="SANDBOX_UNAVAILABLE", reason=str(exc.reason), argv=list(argv))
        ok = raw.exit_code == 0 and not raw.timed_out and not raw.cancelled
        return ComposeResult(
            ok=ok, exit_code=raw.exit_code, argv=list(argv), output=raw.output,
            duration_ms=raw.duration_ms, timed_out=raw.timed_out,
            code=("OK" if ok else ("TIMEOUT" if raw.timed_out else "FAILED")),
        )

    def _run_op(self, operation: str, argv: list[str], *, cwd: Path, timeout_s: int = 600) -> ComposeResult:
        base = self._base()
        if not base:
            return ComposeResult(ok=False, code="ENGINE_UNAVAILABLE", operation=operation,
                                  reason=f"{self.engine} compose isn't installed on this computer")
        # The compose cwd is the project root, so relative bind mounts resolve.
        env = sandbox.build_env()
        spec = sandbox.RunSpec(
            argv=list(argv), cwd=Path(cwd), env=env, timeout_s=timeout_s,
            output_cap_bytes=self.limits.max_stdout_bytes, network=True,
        )
        try:
            raw = sandbox.run(spec)
        except sandbox.SandboxUnavailable as exc:
            return ComposeResult(ok=False, code="SANDBOX_UNAVAILABLE", operation=operation, reason=str(exc.reason), argv=list(argv))
        ok = raw.exit_code == 0 and not raw.timed_out and not raw.cancelled
        return ComposeResult(
            ok=ok, exit_code=raw.exit_code, operation=operation, argv=list(argv),
            output=raw.output, duration_ms=raw.duration_ms, timed_out=raw.timed_out,
            code=("OK" if ok else ("TIMEOUT" if raw.timed_out else "FAILED")),
        )

    def _json(self, text: str) -> Any:
        text = (text or "").strip()
        if not text:
            return None
        for opener in ("{", "["):
            start = text.find(opener)
            if start != -1:
                try:
                    return json.loads(text[start:])
                except (json.JSONDecodeError, ValueError):
                    continue
        return None

    def _service_rows(self, text: str) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        # `docker compose ps --format json` emits one JSON object per line.
        for line in (text or "").splitlines():
            line = line.strip()
            if line.startswith("{"):
                try:
                    parsed = json.loads(line)
                    if isinstance(parsed, dict):
                        rows.append(parsed)
                        continue
                except (json.JSONDecodeError, ValueError):
                    pass
            if not rows:
                # Fall back to the plain column output: NAME IMAGE COMMAND SERVICE CREATED STATUS PORTS
                parts = line.split()
                if len(parts) >= 5 and not line.casefold().startswith("name"):
                    rows.append({
                        "Name": parts[0], "Image": parts[1], "Service": parts[3],
                        "Status": " ".join(parts[4:]),
                    })
        return rows

    # ── operations ──────────────────────────────────────────────────────────────
    def validate(self, *, cwd: Path, compose_file: str = "") -> ComposeResult:
        base = self._base()
        if not base:
            return ComposeResult(ok=False, code="ENGINE_UNAVAILABLE", operation="validate",
                                  reason=f"{self.engine} compose isn't installed")
        argv = base + self._compose_file_args(compose_file) + ["config", "--quiet"]
        result = self._run_op("validate", argv, cwd=cwd, timeout_s=60)
        result.data = {"valid": result.ok}
        return result

    def config(self, *, cwd: Path, compose_file: str = "") -> ComposeResult:
        base = self._base()
        if not base:
            return ComposeResult(ok=False, code="ENGINE_UNAVAILABLE", operation="config",
                                  reason=f"{self.engine} compose isn't installed")
        argv = base + self._compose_file_args(compose_file) + ["config", "--format", "json"]
        result = self._run_op("config", argv, cwd=cwd, timeout_s=60)
        if result.ok:
            result.data = self._json(result.output)
            services = (result.data or {}).get("services") if isinstance(result.data, dict) else None
            if isinstance(services, dict):
                result.services = [{"name": name, **(_svc_summary(spec) if isinstance(spec, dict) else {})} for name, spec in services.items()]
        return result

    def build(self, *, cwd: Path, compose_file: str = "", services: Optional[list[str]] = None, no_cache: bool = False) -> ComposeResult:
        for name in (services or []):
            if not _valid_name(name):
                return ComposeResult(ok=False, code="INVALID_NAME", operation="build", reason=f"bad service name {name!r}")
        base = self._base()
        if not base:
            return ComposeResult(ok=False, code="ENGINE_UNAVAILABLE", operation="build", reason=f"{self.engine} compose isn't installed")
        argv = base + self._compose_file_args(compose_file) + ["build"]
        if no_cache:
            argv.append("--no-cache")
        argv += list(services or [])
        return self._run_op("build", argv, cwd=cwd, timeout_s=1800)

    def up(self, *, cwd: Path, compose_file: str = "", detach: bool = True, build: bool = False, services: Optional[list[str]] = None, remove_orphans: bool = True) -> ComposeResult:
        for name in (services or []):
            if not _valid_name(name):
                return ComposeResult(ok=False, code="INVALID_NAME", operation="up", reason=f"bad service name {name!r}")
        base = self._base()
        if not base:
            return ComposeResult(ok=False, code="ENGINE_UNAVAILABLE", operation="up", reason=f"{self.engine} compose isn't installed")
        argv = base + self._compose_file_args(compose_file) + ["up"]
        if detach:
            argv.append("-d")
        if build:
            argv.append("--build")
        if remove_orphans:
            argv.append("--remove-orphans")
        argv += list(services or [])
        return self._run_op("up", argv, cwd=cwd, timeout_s=900)

    def down(self, *, cwd: Path, compose_file: str = "", volumes: bool = False, remove_orphans: bool = True, rmi: str = "") -> ComposeResult:
        base = self._base()
        if not base:
            return ComposeResult(ok=False, code="ENGINE_UNAVAILABLE", operation="down", reason=f"{self.engine} compose isn't installed")
        argv = base + self._compose_file_args(compose_file) + ["down"]
        if volumes:
            argv.append("-v")
        if remove_orphans:
            argv.append("--remove-orphans")
        if rmi:
            argv += ["--rmi", rmi]
        return self._run_op("down", argv, cwd=cwd, timeout_s=300)

    def start(self, *, cwd: Path, compose_file: str = "", services: Optional[list[str]] = None) -> ComposeResult:
        return self._simple("start", cwd=cwd, compose_file=compose_file, services=services)

    def stop(self, *, cwd: Path, compose_file: str = "", services: Optional[list[str]] = None) -> ComposeResult:
        return self._simple("stop", cwd=cwd, compose_file=compose_file, services=services)

    def restart(self, *, cwd: Path, compose_file: str = "", services: Optional[list[str]] = None) -> ComposeResult:
        return self._simple("restart", cwd=cwd, compose_file=compose_file, services=services)

    def _simple(self, verb: str, *, cwd: Path, compose_file: str, services: Optional[list[str]]) -> ComposeResult:
        for name in (services or []):
            if not _valid_name(name):
                return ComposeResult(ok=False, code="INVALID_NAME", operation=verb, reason=f"bad service name {name!r}")
        base = self._base()
        if not base:
            return ComposeResult(ok=False, code="ENGINE_UNAVAILABLE", operation=verb, reason=f"{self.engine} compose isn't installed")
        argv = base + self._compose_file_args(compose_file) + [verb] + list(services or [])
        return self._run_op(verb, argv, cwd=cwd, timeout_s=300)

    def ps(self, *, cwd: Path, compose_file: str = "", all: bool = True) -> ComposeResult:
        base = self._base()
        if not base:
            return ComposeResult(ok=False, code="ENGINE_UNAVAILABLE", operation="ps", reason=f"{self.engine} compose isn't installed")
        argv = base + self._compose_file_args(compose_file) + ["ps", "--format", "json"]
        if all:
            argv.append("--all")
        result = self._run_op("ps", argv, cwd=cwd, timeout_s=60)
        if result.ok:
            result.services = self._service_rows(result.output)
        return result

    def logs(self, *, cwd: Path, compose_file: str = "", tail: int = 200, service: str = "", follow: bool = False) -> ComposeResult:
        if service and not _valid_name(service):
            return ComposeResult(ok=False, code="INVALID_NAME", operation="logs", reason=f"bad service name {service!r}")
        base = self._base()
        if not base:
            return ComposeResult(ok=False, code="ENGINE_UNAVAILABLE", operation="logs", reason=f"{self.engine} compose isn't installed")
        argv = base + self._compose_file_args(compose_file) + ["logs", "--tail", str(max(0, int(tail)))]
        if service:
            argv.append(service)
        return self._run_op("logs", argv, cwd=cwd, timeout_s=60)

    def exec(self, *, cwd: Path, compose_file: str = "", service: str, command: list[str], workdir: str = "", user: str = "") -> ComposeResult:
        if not _valid_name(service):
            return ComposeResult(ok=False, code="INVALID_NAME", operation="exec", reason="a valid service name is required")
        if not command:
            return ComposeResult(ok=False, code="INVALID_ARG", operation="exec", reason="a command is required")
        base = self._base()
        if not base:
            return ComposeResult(ok=False, code="ENGINE_UNAVAILABLE", operation="exec", reason=f"{self.engine} compose isn't installed")
        argv = base + self._compose_file_args(compose_file) + ["exec", "-T"]
        if workdir:
            argv += ["-w", workdir]
        if user:
            argv += ["-u", user]
        argv.append(service)
        argv += list(command)
        return self._run_op("exec", argv, cwd=cwd, timeout_s=300)

    def pull(self, *, cwd: Path, compose_file: str = "") -> ComposeResult:
        base = self._base()
        if not base:
            return ComposeResult(ok=False, code="ENGINE_UNAVAILABLE", operation="pull", reason=f"{self.engine} compose isn't installed")
        argv = base + self._compose_file_args(compose_file) + ["pull"]
        return self._run_op("pull", argv, cwd=cwd, timeout_s=1800)

    def rm(self, *, cwd: Path, compose_file: str = "", services: Optional[list[str]] = None, force: bool = False, stop: bool = True) -> ComposeResult:
        base = self._base()
        if not base:
            return ComposeResult(ok=False, code="ENGINE_UNAVAILABLE", operation="rm", reason=f"{self.engine} compose isn't installed")
        argv = base + self._compose_file_args(compose_file) + ["rm"]
        if force:
            argv.append("-f")
        if stop:
            argv.append("-s")
        argv += list(services or [])
        return self._run_op("rm", argv, cwd=cwd, timeout_s=120)

    def describe(self) -> dict[str, Any]:
        return {
            "name": self.name, "engine": self.engine,
            "available": self.available(), "version": self.version(),
            "capabilities": sorted(self.capabilities),
        }


class DockerComposeAdapter(ComposeAdapter):
    name = "docker-compose"
    engine = "docker"


class PodmanComposeAdapter(ComposeAdapter):
    name = "podman-compose"
    engine = "podman"


def _svc_summary(spec: dict[str, Any]) -> dict[str, Any]:
    ports: list[int] = []
    for entry in spec.get("ports", []) or []:
        if isinstance(entry, dict):
            published = entry.get("published")
            target = entry.get("target")
            for value in (published, target):
                try:
                    if value is not None:
                        ports.append(int(value))
                        break
                except (TypeError, ValueError):
                    continue
    depends = spec.get("depends_on")
    depends_list: list[str] = []
    if isinstance(depends, dict):
        depends_list = list(depends.keys())
    elif isinstance(depends, list):
        depends_list = [str(d) for d in depends]
    return {
        "image": spec.get("image", ""), "ports": ports,
        "dependsOn": depends_list, "healthcheck": bool(spec.get("healthcheck")),
    }


__all__ = [
    "ComposeAdapter",
    "ComposeResult",
    "DockerComposeAdapter",
    "PodmanComposeAdapter",
]
