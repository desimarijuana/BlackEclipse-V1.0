"""Run the user's project and show it (Phase 24 / P2).

A build is only believable when you can look at it. This module turns "start the
project" into one bounded operation on top of the EXISTING execution layer
(`execution/services.py`: `ServiceManager` + the terminal process manager), so a
preview is tree-managed, cancellable, logged and never an unmanaged background
process.

Two rules:

  * **We never guess the port.** The dev server picks its own; we watch the
    process tree for a listening port and only then say "ready". A process that
    runs but never listens is `not_ready`, with its logs — not a fake URL.
  * **The folder is resolved, never supplied.** Callers name a task (or an
    approved root id); the router resolves the project. No request body ever
    carries a `cwd`.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

MAX_LOG_TAIL = 400
DEFAULT_READY_TIMEOUT_S = 45.0
POLL_INTERVAL_S = 0.5

#: Script names tried in order, first match wins.
DEV_SCRIPTS: tuple[str, ...] = ("dev", "start", "preview", "serve")


@dataclass(frozen=True)
class PreviewPlan:
    command: str
    label: str
    root: str
    source: str  # "project" | "detected" | "none"

    def to_dict(self) -> dict[str, Any]:
        return {
            "command": self.command, "label": self.label,
            "root": self.root, "source": self.source,
        }


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return None


def _makefile_target(root: Path, target: str) -> bool:
    path = root / "Makefile"
    if not path.is_file():
        return False
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    return any(line.strip() == f"{target}:" or line.startswith(f"{target}:") for line in text.splitlines())


def plan_preview(root: Path | str | None) -> PreviewPlan:
    """The command that runs this project, or a `none` plan. Pure.

    Precedence: the project's own `.black-eclipse/preview.json`, then a declared
    package script, then a `Makefile` target. Nothing is invented for a stack we
    cannot see.
    """
    if root is None:
        return PreviewPlan("", "", "", "none")
    base = Path(root)
    if not base.is_dir():
        return PreviewPlan("", "", str(base), "none")

    override = _read_json(base / ".black-eclipse" / "preview.json")
    if isinstance(override, dict):
        command = str(override.get("command") or "").strip()
        if command:
            return PreviewPlan(
                command, str(override.get("label") or "Run this project"),
                str(base), "project",
            )

    package = _read_json(base / "package.json")
    if isinstance(package, dict) and isinstance(package.get("scripts"), dict):
        scripts = package["scripts"]
        for name in DEV_SCRIPTS:
            if name in scripts:
                return PreviewPlan(f"npm run {name}", f"Run {name}", str(base), "detected")

    for name in DEV_SCRIPTS:
        if _makefile_target(base, name):
            return PreviewPlan(f"make {name}", f"Run {name}", str(base), "detected")

    return PreviewPlan("", "", str(base), "none")


def _http_ok(url: str, *, timeout_s: float = 2.0) -> bool:
    from ..execution.services import HealthChecker  # noqa: PLC0415

    return bool(HealthChecker().http(url, timeout_s=timeout_s).get("ok"))


class PreviewManager:
    """One running preview per task (or per project), over the execution layer."""

    def __init__(self, execution: Any, *, sleep: Any = time.sleep, clock: Any = time.monotonic) -> None:
        self._execution = execution
        self._sleep = sleep
        self._clock = clock
        self._by_key: dict[str, dict[str, Any]] = {}

    def _terminal(self) -> Any:
        return getattr(self._execution, "terminal", None)

    def get(self, key: str) -> Optional[dict[str, Any]]:
        return self._by_key.get(key)

    def start(
        self, key: str, root: Path | str, *, timeout_s: float = DEFAULT_READY_TIMEOUT_S,
    ) -> dict[str, Any]:
        """Start the project and watch for a listening port. Never invents one."""
        running = self._by_key.get(key)
        if running and running.get("running"):
            if not running.get("url"):
                # It is still starting: re-check for a listening port, briefly.
                url, port = self._wait_for_port(
                    str(running.get("processId") or ""), timeout_s=min(timeout_s, 10.0),
                )
                if url:
                    running.update(url=url, port=port, ready=True)
            return {"status": "ok", **running, "reused": True}

        plan = plan_preview(root)
        if plan.source == "none" or not plan.command:
            return {
                "status": "refused", "code": "PREVIEW_NO_COMMAND",
                "reason": "I couldn't find a way to run this project. Add .black-eclipse/preview.json with a command.",
                "plan": plan.to_dict(),
            }
        terminal = self._terminal()
        if terminal is None:
            return {"status": "unavailable", "code": "RUNTIME_UNAVAILABLE",
                    "reason": "the terminal isn't available right now", "plan": plan.to_dict()}

        started = self._execution.start_service(
            command=plan.command, cwd=str(root), protocol="process",
            wait_ready=False, workspace_id=key, run_id=key,
        )
        if started.get("status") != "ok":
            return {
                "status": "failed", "code": started.get("code") or "PREVIEW_START_FAILED",
                "reason": started.get("reason") or "the project did not start",
                "plan": plan.to_dict(),
            }
        service = started.get("service") or {}
        process_id = str(service.get("processId") or "")
        service_id = str(service.get("serviceId") or "")
        url, port = self._wait_for_port(process_id, timeout_s=timeout_s)

        record = {
            "taskKey": key, "serviceId": service_id, "processId": process_id,
            "command": plan.command, "label": plan.label, "root": str(root),
            "url": url, "port": port, "ready": bool(url),
            "running": True, "source": plan.source,
        }
        self._by_key[key] = record
        return {"status": "ok", **record}

    def _wait_for_port(self, process_id: str, *, timeout_s: float) -> tuple[str, int]:
        """First listening port that answers HTTP, or ("", 0)."""
        terminal = self._terminal()
        deadline = self._clock() + max(0.5, timeout_s)
        while process_id and self._clock() < deadline:
            info = terminal.get_process(process_id) if terminal is not None else None
            if info is not None and info.get("state") in ("CRASHED", "STOPPED", "FAILED"):
                return "", 0
            for port in (info or {}).get("ports") or []:
                try:
                    candidate = int(port)
                except (TypeError, ValueError):
                    continue
                url = f"http://127.0.0.1:{candidate}"
                if _http_ok(url):
                    return url, candidate
            self._sleep(POLL_INTERVAL_S)
        return "", 0

    def status(self, key: str) -> dict[str, Any]:
        record = self._by_key.get(key)
        if not record:
            return {"status": "idle", "taskKey": key}
        process = None
        terminal = self._terminal()
        if terminal is not None and record.get("processId"):
            process = terminal.get_process(str(record["processId"]))
        state = (process or {}).get("state", "UNKNOWN")
        running = state in ("RUNNING", "STARTING")
        if not running:
            record["running"] = False
        return {
            "status": "ok", **record, "processState": state, "running": running,
        }

    def stop(self, key: str) -> dict[str, Any]:
        record = self._by_key.get(key)
        if not record:
            return {"status": "idle", "taskKey": key}
        service_id = str(record.get("serviceId") or "")
        if service_id:
            self._execution.stop_service(service_id)
        record["running"] = False
        record["ready"] = False
        return {"status": "ok", **record, "stopped": True}

    def logs(self, key: str, *, tail: int = 200) -> dict[str, Any]:
        record = self._by_key.get(key)
        if not record:
            return {"status": "idle", "logs": ""}
        service_id = str(record.get("serviceId") or "")
        if not service_id:
            return {"status": "ok", "logs": ""}
        data = self._execution.get_service_logs(service_id, tail=max(1, min(int(tail), MAX_LOG_TAIL)))
        return {"status": "ok", "logs": str(data.get("logs") or "")}


_MANAGER: Optional[PreviewManager] = None


def get_preview_manager(execution: Any) -> PreviewManager:
    """The process-wide preview manager (one preview table per runtime)."""
    global _MANAGER
    if _MANAGER is None:
        _MANAGER = PreviewManager(execution)
    return _MANAGER


def reset_preview_manager() -> None:
    """Test seam: forget the singleton (never stops processes)."""
    global _MANAGER
    _MANAGER = None


__all__ = [
    "DEV_SCRIPTS",
    "PreviewManager",
    "PreviewPlan",
    "get_preview_manager",
    "plan_preview",
    "reset_preview_manager",
]
