"""The shell runtime adapter.

Shell execution does NOT reimplement process management: it reuses the existing
terminal subsystem's own argv builder (`terminal/runtimes.py`) to wrap a command
in the host shell, then runs that argv through the SAME sandbox primitive
(`code/sandbox.py`) every other execution uses. Process-tree termination, env
scrubbing, output caps and cancellation therefore come for free. This mirrors what
`TerminalManager.execute_command` does — it is the same primitive, not a second
one.

A shell command is classified by the terminal subsystem's `allow/ask/deny`
classifier before it reaches here (in the agent tool handler), and the run's
autonomy profile is checked by the policy engine. `request.code` is the command
line.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from ..projects import ProjectInfo
from .base import BaseRuntime, PreparedCommand


class ShellRuntime(BaseRuntime):
    language = "shell"
    name = "ShellRuntime"
    aliases = ("sh", "bash", "zsh", "powershell", "pwsh", "cmd", "console")
    is_shell = True

    def available(self) -> bool:
        try:
            from ...terminal import shell_detect  # noqa: PLC0415

            return bool(shell_detect.default_shell())
        except Exception:  # noqa: BLE001 - no shell detection ⇒ no shell runtime
            return False

    def resolve(self, project: Optional[ProjectInfo]) -> str:
        try:
            from ...terminal import shell_detect  # noqa: PLC0415

            shell = shell_detect.default_shell()
            return shell.path if shell else ""
        except Exception:  # noqa: BLE001
            return ""

    def prepare_run(self, request: Any, root: Path, workdir: Path) -> PreparedCommand:
        command = str(getattr(request, "code", "") or "")
        if not command:
            entrypoint = getattr(request, "entrypoint", "")
            command = f'"{entrypoint}"' if entrypoint else ""
        if not command:
            from .base import RuntimeUnavailable  # noqa: PLC0415

            raise RuntimeUnavailable("There's no command to run.")
        shell_name = str((getattr(request, "metadata", {}) or {}).get("shell") or "") or None
        try:
            from ...terminal.runtimes import select_runtime  # noqa: PLC0415

            runtime = select_runtime("local")
            argv = runtime.build_argv(command, shell=shell_name, cwd=str(root))
        except Exception as exc:  # noqa: BLE001 - unavailable shell is an honest refusal
            from .base import RuntimeUnavailable  # noqa: PLC0415

            raise RuntimeUnavailable(f"A shell isn't available on this computer ({type(exc).__name__}).") from exc
        return PreparedCommand(argv=list(argv), cwd=root, env={}, description="shell command")


__all__ = ["ShellRuntime"]
