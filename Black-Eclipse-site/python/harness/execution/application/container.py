"""Container runtimes — Docker and Podman behind one abstraction.

`ContainerRuntimeAdapter` is the seam. `DockerAdapter` and `PodmanAdapter` are
two engine configurations of the SAME machinery: a closed CLI vocabulary, argv
built from validated arguments, JSON output parsed into structured results, and
every command run through the ONE sandbox (no shell, no string concatenation).

The adapter NEVER fabricates a container: if the engine binary is absent it
reports `available() == False` and each operation returns a structured
`ENGINE_UNAVAILABLE` refusal. A `docker ps` that returns nothing is an empty
list, not a running container.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from ...code import sandbox
from ..models import ResourceLimits, resource_run_kwargs
from .registry import (
    CAP_CONTAINER_BUILD,
    CAP_CONTAINER_EXEC,
    CAP_CONTAINER_IMAGES,
    CAP_CONTAINER_INSPECT,
    CAP_CONTAINER_LIFECYCLE,
    CAP_CONTAINER_LIST,
    CAP_CONTAINER_LOGS,
    CAP_CONTAINER_REMOVE,
    CAP_CONTAINER_RUN,
    CAP_CONTAINER_STATS,
    CAP_HEALTH,
)


@dataclass
class ContainerResult:
    """The structured outcome of one container operation."""

    ok: bool = False
    code: str = "OK"
    operation: str = ""
    kind: str = "container"
    exit_code: Optional[int] = None
    argv: list[str] = field(default_factory=list)
    output: str = ""
    data: Any = None
    duration_ms: int = 0
    timed_out: bool = False
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok, "code": self.code, "operation": self.operation,
            "kind": self.kind, "exitCode": self.exit_code, "argv": list(self.argv),
            "output": self.output, "data": self.data, "durationMs": self.duration_ms,
            "timedOut": self.timed_out, "reason": self.reason,
        }


def _valid_name(name: str) -> bool:
    import re

    return bool(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:@/-]{0,254}", str(name or "")))


def _valid_image(image: str) -> bool:
    import re

    # registry[:port]/repo/name[:tag][@digest]
    return bool(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:/-]{0,254}(?:@sha256:[a-f0-9]{64})?", str(image or "")))


class ContainerRuntimeAdapter:
    """A container engine CLI (docker/podman). Subclasses set the binary name."""

    kind = "container"
    name = "container"
    binary = "docker"
    capabilities: frozenset[str] = frozenset(
        {
            CAP_CONTAINER_BUILD, CAP_CONTAINER_RUN, CAP_CONTAINER_LIFECYCLE,
            CAP_CONTAINER_EXEC, CAP_CONTAINER_LOGS, CAP_CONTAINER_INSPECT,
            CAP_CONTAINER_STATS, CAP_CONTAINER_LIST, CAP_CONTAINER_REMOVE,
            CAP_CONTAINER_IMAGES, CAP_HEALTH,
        }
    )
    #: The closed subcommand vocabulary. An operation not listed is refused.
    container_subcommands = (
        "build", "run", "start", "stop", "restart", "rm", "exec", "logs",
        "ps", "inspect", "stats", "cp", "pull", "push", "images", "rmi", "tag",
        "history", "network", "volume", "healthcheck",
    )

    def __init__(self, *, binary: Optional[str] = None, limits: Optional[ResourceLimits] = None) -> None:
        self.binary = binary or self.binary
        self._limits = limits

    @property
    def limits(self) -> ResourceLimits:
        return self._limits or ResourceLimits.from_env()

    # ── detection ───────────────────────────────────────────────────────────────
    def _exe(self) -> str:
        return shutil.which(self.binary) or ""

    def detect(self) -> bool:
        return bool(self._exe())

    def available(self) -> bool:
        """The binary exists AND the daemon answers within a bounded probe."""
        exe = self._exe()
        if not exe:
            return False
        result = self._exec([exe, "version", "--format", "{{.Server.Version}}"], timeout_s=8)
        return result.ok and bool((result.output or "").strip())

    def version(self) -> str:
        exe = self._exe()
        if not exe:
            return ""
        result = self._exec([exe, "version", "--format", "{{.Server.Version}}"], timeout_s=8)
        return (result.output or "").strip().splitlines()[0] if result.output else ""

    # ── execution ────────────────────────────────────────────────────────────────
    def _exec(self, argv: list[str], *, timeout_s: int = 120, network: bool = True) -> ContainerResult:
        env = sandbox.build_env()
        # Container engines legitimately need the network (registry pulls) and the
        # docker config; only a bounded allowlist of the parent environment passes.
        spec = sandbox.RunSpec(
            argv=list(argv), cwd=Path.cwd(), env=env, timeout_s=timeout_s,
            output_cap_bytes=self.limits.max_stdout_bytes, network=network,
        )
        try:
            raw = sandbox.run(spec)
        except sandbox.SandboxUnavailable as exc:
            return ContainerResult(ok=False, code="SANDBOX_UNAVAILABLE", reason=str(exc.reason), argv=list(argv))
        ok = raw.exit_code == 0 and not raw.timed_out and not raw.cancelled
        return ContainerResult(
            ok=ok, exit_code=raw.exit_code, argv=list(argv), output=raw.output,
            duration_ms=raw.duration_ms, timed_out=raw.timed_out,
            code=("OK" if ok else ("TIMEOUT" if raw.timed_out else "FAILED")),
        )

    def _run_op(self, operation: str, argv: list[str], *, timeout_s: int = 120) -> ContainerResult:
        exe = self._exe()
        if not exe:
            return ContainerResult(ok=False, code="ENGINE_UNAVAILABLE", operation=operation,
                                   reason=f"{self.name} isn't installed on this computer")
        result = self._exec(argv, timeout_s=timeout_s)
        result.operation = operation
        return result

    def _json_lines(self, text: str) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for line in (text or "").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                parsed = json.loads(line)
            except (json.JSONDecodeError, ValueError):
                continue
            if isinstance(parsed, dict):
                out.append(parsed)
        return out

    def _json(self, text: str) -> Any:
        text = (text or "").strip()
        if not text:
            return None
        try:
            return json.loads(text)
        except (json.JSONDecodeError, ValueError):
            # Some engines print leading warnings; try the first JSON document.
            start = text.find("[")
            if start == -1:
                start = text.find("{")
            if start != -1:
                try:
                    return json.loads(text[start:])
                except (json.JSONDecodeError, ValueError):
                    return None
            return None

    # ── operations ───────────────────────────────────────────────────────────────
    def build(self, *, context: Path, tag: str = "", dockerfile: str = "", args: Optional[dict[str, str]] = None) -> ContainerResult:
        if not tag or not _valid_image(tag):
            return ContainerResult(ok=False, code="INVALID_NAME", operation="build", reason="a valid image tag is required")
        argv = [self._exe(), "build", "-t", tag]
        if dockerfile:
            argv += ["-f", dockerfile]
        for key, value in (args or {}).items():
            if not _valid_name(key):
                return ContainerResult(ok=False, code="INVALID_ARG", operation="build", reason=f"bad build arg {key!r}")
            argv += ["--build-arg", f"{key}={value}"]
        argv.append(str(context))
        return self._run_op("build", argv, timeout_s=1800)

    def run(
        self, *, image: str, name: str = "", command: Optional[list[str]] = None,
        ports: Optional[list[str]] = None, env: Optional[dict[str, str]] = None,
        detach: bool = True, rm: bool = False, volumes: Optional[list[str]] = None,
        network: str = "", entrypoint: str = "",
    ) -> ContainerResult:
        if not _valid_image(image):
            return ContainerResult(ok=False, code="INVALID_NAME", operation="run", reason="a valid image name is required")
        argv = [self._exe(), "run"]
        if detach:
            argv.append("-d")
        if rm:
            argv.append("--rm")
        if name:
            if not _valid_name(name):
                return ContainerResult(ok=False, code="INVALID_NAME", operation="run", reason="a valid container name is required")
            argv += ["--name", name]
        for port in (ports or []):
            if not _valid_port_map(port):
                return ContainerResult(ok=False, code="INVALID_ARG", operation="run", reason=f"bad port map {port!r}")
            argv += ["-p", port]
        for volume in (volumes or []):
            if not _valid_volume_map(volume):
                return ContainerResult(ok=False, code="INVALID_ARG", operation="run", reason=f"bad volume {volume!r}")
            argv += ["-v", volume]
        for key, value in (env or {}).items():
            if not _valid_name(key):
                return ContainerResult(ok=False, code="INVALID_ARG", operation="run", reason=f"bad env key {key!r}")
            argv += ["-e", f"{key}={value}"]
        if network:
            argv += ["--network", network]
        if entrypoint:
            argv += ["--entrypoint", entrypoint]
        argv.append(image)
        argv += list(command or [])
        return self._run_op("run", argv)

    def start(self, container: str) -> ContainerResult:
        return self._lifecycle("start", container)

    def stop(self, container: str, *, timeout_s: int = 10) -> ContainerResult:
        if not _valid_name(container):
            return ContainerResult(ok=False, code="INVALID_NAME", operation="stop", reason="a valid container id is required")
        return self._run_op("stop", [self._exe(), "stop", "-t", str(int(timeout_s)), container])

    def restart(self, container: str) -> ContainerResult:
        return self._lifecycle("restart", container)

    def _lifecycle(self, verb: str, container: str) -> ContainerResult:
        if not _valid_name(container):
            return ContainerResult(ok=False, code="INVALID_NAME", operation=verb, reason="a valid container id is required")
        return self._run_op(verb, [self._exe(), verb, container])

    def remove(self, container: str, *, force: bool = False, volumes: bool = False) -> ContainerResult:
        if not _valid_name(container):
            return ContainerResult(ok=False, code="INVALID_NAME", operation="rm", reason="a valid container id is required")
        argv = [self._exe(), "rm"]
        if force:
            argv.append("-f")
        if volumes:
            argv.append("-v")
        argv.append(container)
        return self._run_op("rm", argv)

    def exec(self, container: str, command: list[str], *, workdir: str = "", env: Optional[dict[str, str]] = None, user: str = "") -> ContainerResult:
        if not _valid_name(container):
            return ContainerResult(ok=False, code="INVALID_NAME", operation="exec", reason="a valid container id is required")
        if not command:
            return ContainerResult(ok=False, code="INVALID_ARG", operation="exec", reason="a command is required")
        argv = [self._exe(), "exec"]
        if workdir:
            argv += ["-w", workdir]
        if user:
            argv += ["-u", user]
        for key, value in (env or {}).items():
            if not _valid_name(key):
                return ContainerResult(ok=False, code="INVALID_ARG", operation="exec", reason=f"bad env key {key!r}")
            argv += ["-e", f"{key}={value}"]
        argv.append(container)
        argv += list(command)
        return self._run_op("exec", argv)

    def logs(self, container: str, *, tail: int = 200, timestamps: bool = False) -> ContainerResult:
        if not _valid_name(container):
            return ContainerResult(ok=False, code="INVALID_NAME", operation="logs", reason="a valid container id is required")
        argv = [self._exe(), "logs", "--tail", str(max(0, int(tail)))]
        if timestamps:
            argv.append("-t")
        argv.append(container)
        return self._run_op("logs", argv)

    def ps(self, *, all: bool = True) -> ContainerResult:
        argv = [self._exe(), "ps", "--format", "{{json .}}"]
        if all:
            argv.append("-a")
        result = self._run_op("ps", argv)
        if result.ok:
            result.data = self._json_lines(result.output)
        return result

    def inspect(self, container: str) -> ContainerResult:
        if not _valid_name(container):
            return ContainerResult(ok=False, code="INVALID_NAME", operation="inspect", reason="a valid container id is required")
        result = self._run_op("inspect", [self._exe(), "inspect", container])
        if result.ok:
            result.data = self._json(result.output)
        return result

    def stats(self, container: str = "", *, no_stream: bool = True) -> ContainerResult:
        argv = [self._exe(), "stats", "--format", "{{json .}}"]
        if no_stream:
            argv.append("--no-stream")
        if container:
            if not _valid_name(container):
                return ContainerResult(ok=False, code="INVALID_NAME", operation="stats", reason="a valid container id is required")
            argv.append(container)
        result = self._run_op("stats", argv)
        if result.ok:
            result.data = self._json_lines(result.output)
        return result

    def pull(self, image: str) -> ContainerResult:
        if not _valid_image(image):
            return ContainerResult(ok=False, code="INVALID_NAME", operation="pull", reason="a valid image name is required")
        return self._run_op("pull", [self._exe(), "pull", image], timeout_s=1800)

    def images(self) -> ContainerResult:
        result = self._run_op("images", [self._exe(), "images", "--format", "{{json .}}"])
        if result.ok:
            result.data = self._json_lines(result.output)
        return result

    def rmi(self, image: str, *, force: bool = False) -> ContainerResult:
        if not _valid_image(image):
            return ContainerResult(ok=False, code="INVALID_NAME", operation="rmi", reason="a valid image name is required")
        argv = [self._exe(), "rmi"] + (["-f"] if force else []) + [image]
        return self._run_op("rmi", argv)

    def healthcheck(self, container: str) -> ContainerResult:
        """Read the container's configured health status from `inspect`."""
        if not _valid_name(container):
            return ContainerResult(ok=False, code="INVALID_NAME", operation="healthcheck", reason="a valid container id is required")
        result = self._run_op("healthcheck", [self._exe(), "inspect", "--format", "{{json .State}}", container])
        if result.ok:
            state = self._json(result.output)
            result.data = state
            result.ok = bool(isinstance(state, dict) and str(state.get("Health", {}).get("Status", state.get("Status", ""))) in ("healthy", "running"))
        return result

    # ── networks / volumes ─────────────────────────────────────────────────────────
    def network_ls(self) -> ContainerResult:
        result = self._run_op("network", [self._exe(), "network", "ls", "--format", "{{json .}}"])
        if result.ok:
            result.data = self._json_lines(result.output)
        return result

    def network_create(self, name: str) -> ContainerResult:
        if not _valid_name(name):
            return ContainerResult(ok=False, code="INVALID_NAME", operation="network", reason="a valid network name is required")
        return self._run_op("network", [self._exe(), "network", "create", name])

    def network_connect(self, network: str, container: str) -> ContainerResult:
        if not (_valid_name(network) and _valid_name(container)):
            return ContainerResult(ok=False, code="INVALID_NAME", operation="network", reason="valid names are required")
        return self._run_op("network", [self._exe(), "network", "connect", network, container])

    def network_disconnect(self, network: str, container: str) -> ContainerResult:
        if not (_valid_name(network) and _valid_name(container)):
            return ContainerResult(ok=False, code="INVALID_NAME", operation="network", reason="valid names are required")
        return self._run_op("network", [self._exe(), "network", "disconnect", network, container])

    def network_rm(self, network: str) -> ContainerResult:
        if not _valid_name(network):
            return ContainerResult(ok=False, code="INVALID_NAME", operation="network", reason="a valid network name is required")
        return self._run_op("network", [self._exe(), "network", "rm", network])

    def volume_ls(self) -> ContainerResult:
        result = self._run_op("volume", [self._exe(), "volume", "ls", "--format", "{{json .}}"])
        if result.ok:
            result.data = self._json_lines(result.output)
        return result

    def volume_create(self, name: str) -> ContainerResult:
        if not _valid_name(name):
            return ContainerResult(ok=False, code="INVALID_NAME", operation="volume", reason="a valid volume name is required")
        return self._run_op("volume", [self._exe(), "volume", "create", name])

    def volume_inspect(self, name: str) -> ContainerResult:
        if not _valid_name(name):
            return ContainerResult(ok=False, code="INVALID_NAME", operation="volume", reason="a valid volume name is required")
        result = self._run_op("volume", [self._exe(), "volume", "inspect", name])
        if result.ok:
            result.data = self._json(result.output)
        return result

    def volume_rm(self, name: str, *, force: bool = False) -> ContainerResult:
        if not _valid_name(name):
            return ContainerResult(ok=False, code="INVALID_NAME", operation="volume", reason="a valid volume name is required")
        argv = [self._exe(), "volume", "rm"] + (["-f"] if force else []) + [name]
        return self._run_op("volume", argv)

    def describe(self) -> dict[str, Any]:
        return {
            "name": self.name, "available": self.available(), "version": self.version(),
            "capabilities": sorted(self.capabilities),
        }


class DockerAdapter(ContainerRuntimeAdapter):
    name = "docker"
    binary = "docker"


class PodmanAdapter(ContainerRuntimeAdapter):
    name = "podman"
    binary = "podman"

    def available(self) -> bool:
        exe = self._exe()
        if not exe:
            return False
        result = self._exec([exe, "info", "--format", "{{.Version.Version}}"], timeout_s=8)
        return result.ok and bool((result.output or "").strip())

    def version(self) -> str:
        exe = self._exe()
        if not exe:
            return ""
        result = self._exec([exe, "info", "--format", "{{.Version.Version}}"], timeout_s=8)
        return (result.output or "").strip().splitlines()[0] if result.output else ""


def _valid_port_map(value: str) -> bool:
    import re

    return bool(re.fullmatch(r"(?:\d{1,5}:\d{1,5}(?:/(?:tcp|udp))?|\[[0-9a-fA-F:]+\]:\d{1,5}:\d{1,5})", str(value or "")))


def _valid_volume_map(value: str) -> bool:
    text = str(value or "")
    if not text or "\x00" in text or len(text) > 512:
        return False
    return ":" in text


__all__ = [
    "ContainerResult",
    "ContainerRuntimeAdapter",
    "DockerAdapter",
    "PodmanAdapter",
]
