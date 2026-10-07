"""Long-running CLI operations as MANAGED PROCESSES.

Some orchestration operations are not one-shot: `kubectl port-forward`,
`kubectl logs -f`, `kubectl proxy`, `helm --watch`, `terraform` provider
mirroring, a cloud `logs --follow`. The right home for them is the EXISTING
terminal process manager (tree-killed, cancellable, persisted, streamed), NOT a
one-shot `CliAdapter.run_operation` that would block.

This module builds the argv for such an operation and starts it through
`TerminalManager.start_process`, so the process is:
  * bounded by the terminal's own runaway guard;
  * visible in `list_processes` / the Processs UI with `purpose="port-forward"`;
  * stoppable with the normal `stop_process`/`kill_process`.

It reuses the SAME closed-argv validation as `CliAdapter` (an injected name is a
structured refusal), so there is no second argument surface.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from .cli_base import is_safe_name, is_safe_value


@dataclass
class ManagedCliResult:
    ok: bool = False
    code: str = "OK"
    reason: str = ""
    process_id: str = ""
    pid: Optional[int] = None
    argv: list[str] = field(default_factory=list)
    local_port: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok, "code": self.code, "reason": self.reason,
            "processId": self.process_id, "pid": self.pid, "argv": list(self.argv),
            "localPort": self.local_port,
        }


class ManagedCli:
    """Start a long-running orchestrator CLI operation as a managed process."""

    def __init__(self, terminal: Any = None) -> None:
        self._terminal = terminal

    def port_forward(
        self,
        *,
        resource: str,
        namespace: str = "",
        local_port: int = 0,
        remote_port: int = 0,
        address: str = "127.0.0.1",
        workspace_id: Optional[str] = None,
        run_id: Optional[str] = None,
        agent_id: Optional[str] = None,
    ) -> ManagedCliResult:
        """Start `kubectl port-forward` as a managed process.

        `resource` is `kind/name` (e.g. `pod/web-1` or `svc/api`); it is validated
        with the SAME token rule as the one-shot adapter. A port conflict is
        resolved by the caller before this is called (the runtime's PortManager).
        """
        kubectl = _find_binary("kubectl")
        if not kubectl:
            return ManagedCliResult(ok=False, code="ENGINE_UNAVAILABLE", reason="kubectl isn't installed on this computer")
        if not _valid_resource(resource):
            return ManagedCliResult(ok=False, code="INVALID_NAME", reason="'resource' must be kind/name with safe characters")
        if namespace and not is_safe_name(namespace):
            return ManagedCliResult(ok=False, code="INVALID_NAME", reason="'namespace' is not a valid name")
        if not (1 <= int(local_port) <= 65_535) or not (1 <= int(remote_port) <= 65_535):
            return ManagedCliResult(ok=False, code="INVALID_ARG", reason="local and remote ports must be 1..65535")
        if address != "127.0.0.1" and not is_safe_value(address):
            return ManagedCliResult(ok=False, code="INVALID_ARG", reason="'address' is not a valid bind address")
        argv = [kubectl, "port-forward", resource, f"{int(local_port)}:{int(remote_port)}"]
        argv += ["--address", address]
        if namespace:
            argv += ["-n", namespace]
        if self._terminal is None:
            return ManagedCliResult(ok=False, code="RUNTIME_UNAVAILABLE", reason="the terminal isn't available right now")
        info = self._terminal.start_process(
            argv=argv, cwd=".", env={}, command=" ".join(argv), runtime="local",
            workspace_id=workspace_id, run_id=run_id, agent_id=agent_id,
            purpose="port-forward",
        )
        if info.get("state") == "FAILED":
            return ManagedCliResult(ok=False, code="PROCESS_START_FAILED",
                                    reason=(info.get("error") or {}).get("message", "the port-forward could not start"),
                                    argv=argv)
        return ManagedCliResult(ok=True, process_id=info.get("processId", ""),
                                 pid=info.get("pid"), argv=argv, local_port=int(local_port))

    def logs_follow(
        self,
        *,
        name: str,
        namespace: str = "",
        container: str = "",
        workspace_id: Optional[str] = None,
        run_id: Optional[str] = None,
        agent_id: Optional[str] = None,
    ) -> ManagedCliResult:
        """Start `kubectl logs -f` as a managed process (streamed, cancellable)."""
        kubectl = _find_binary("kubectl")
        if not kubectl:
            return ManagedCliResult(ok=False, code="ENGINE_UNAVAILABLE", reason="kubectl isn't installed on this computer")
        if not is_safe_name(name):
            return ManagedCliResult(ok=False, code="INVALID_NAME", reason="a valid pod name is required")
        if namespace and not is_safe_name(namespace):
            return ManagedCliResult(ok=False, code="INVALID_NAME", reason="'namespace' is not a valid name")
        argv = [kubectl, "logs", "-f", name]
        if namespace:
            argv += ["-n", namespace]
        if container:
            if not is_safe_name(container):
                return ManagedCliResult(ok=False, code="INVALID_NAME", reason="'container' is not a valid name")
            argv += ["-c", container]
        if self._terminal is None:
            return ManagedCliResult(ok=False, code="RUNTIME_UNAVAILABLE", reason="the terminal isn't available right now")
        info = self._terminal.start_process(
            argv=argv, cwd=".", env={}, command=" ".join(argv), runtime="local",
            workspace_id=workspace_id, run_id=run_id, agent_id=agent_id, purpose="logs-follow",
        )
        if info.get("state") == "FAILED":
            return ManagedCliResult(ok=False, code="PROCESS_START_FAILED",
                                    reason=(info.get("error") or {}).get("message", "the log follow could not start"), argv=argv)
        return ManagedCliResult(ok=True, process_id=info.get("processId", ""), pid=info.get("pid"), argv=argv)

    def stop(self, process_id: str) -> dict[str, Any]:
        if self._terminal is None:
            return {"status": "refused", "code": "RUNTIME_UNAVAILABLE", "reason": "the terminal isn't available"}
        ok = bool(self._terminal.stop_process(process_id))
        return {"status": "ok" if ok else "not_found", "processId": process_id}


def _valid_resource(resource: str) -> bool:
    """`kind/name`, both safe tokens. Rejects a path, a shell fragment, an empty kind."""
    text = str(resource or "")
    if "/" not in text:
        return False
    kind, _, name = text.partition("/")
    return bool(kind and name and is_safe_name(kind) and is_safe_name(name))


def _find_binary(name: str) -> str:
    import shutil

    return shutil.which(name) or ""


__all__ = ["ManagedCli", "ManagedCliResult"]
