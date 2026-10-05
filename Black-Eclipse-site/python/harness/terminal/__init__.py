"""Eclipse terminal subsystem — the execution backbone.

One runtime shared by agent tools and the UI:

  * `manager.TerminalManager` — the facade everything talks to.
  * `session`  — persistent shells (cwd/env/stdin/dimensions).
  * `process_manager` — background processes, trees, signals, crash detection.
  * `buffer`   — bounded, sequenced output with a poll cursor.
  * `port_manager` — listening ports and conflicts.
  * `runtimes` — local / wsl (implemented), docker / ssh (honest stubs).
  * `shell_detect` — what this host can actually do.
  * `redaction` — secrets never reach the model or a log.
  * `store` — metadata persisted on the one agent-memory connection.
  * `recovery` — reconcile persisted state after a restart.
  * `tools` / `router` — the agent tool surface and the HTTP surface.

The design follows the repository's standing rules: argv or an explicitly
classified shell command, a scrubbed environment, bounded output, workspace
confinement, approval for anything not on the safe list, and NEVER a fabricated
capability.
"""

from __future__ import annotations

from .manager import TerminalManager
from .types import (
    CommandError,
    CommandResult,
    ErrorCategory,
    PortInfo,
    ProcessInfo,
    ProcessState,
    RuntimeName,
    SessionInfo,
    ShellInfo,
    SignalName,
    StreamName,
    TerminalCapabilities,
)

__all__ = [
    "CommandError",
    "CommandResult",
    "ErrorCategory",
    "PortInfo",
    "ProcessInfo",
    "ProcessState",
    "RuntimeName",
    "SessionInfo",
    "ShellInfo",
    "SignalName",
    "StreamName",
    "TerminalCapabilities",
    "TerminalManager",
]
