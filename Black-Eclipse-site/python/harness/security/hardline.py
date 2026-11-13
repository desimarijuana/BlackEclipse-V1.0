"""Always-on command hardline (W6).

The Security Floor protects *paths and action classes*. It cannot see a shell
command string, so a destructive command that arrives through `shell_run` (or an
effectful tool with a `command` argument) was only evaluated by the capability's
own classifier. This module is the last line of defense: a small, fixed,
deterministic set of whole-command shapes that are denied **before** grants,
YOLO, policy or approval are consulted.

Rules:

* pure and config-free — there is deliberately no runtime off switch;
* anchored on command shape, never on a bare substring (`rm -rf ./build` and
  `dd if=a of=b` must pass);
* a match is terminal: no grant, profile or approval can override it;
* every rule names itself so the audit/event can say *why*.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Optional

# `shlex` is deliberately not used: the hardline must also catch a command that
# never parses. Normalization is whitespace-only; a hostile quoted string is
# still the same destructive shape.
_WS = re.compile(r"\s+")


@dataclass(frozen=True)
class HardlineVerdict:
    rule: str
    reason: str

    @property
    def code(self) -> str:
        return "HARDLINE_DENIED"


def _normalize(command: str) -> str:
    return _WS.sub(" ", str(command or "").strip().lower())


# (rule, compiled pattern, reason). Order is irrelevant: every match denies.
_RULES: tuple[tuple[str, re.Pattern[str], str], ...] = (
    (
        "root-wipe",
        re.compile(
            r"(?:^|[;&|]\s*)rm\s+(?:-[a-z]+\s+)*(?:-[a-z]*r[a-z]*f|-[a-z]*f[a-z]*r)"
            r"\s+(?:-[^\s]+\s+)*(?:/|/\*)\s*(?:$|[;&|])"
        ),
        "a recursive force delete of the filesystem root is never allowed",
    ),
    (
        "root-wipe",
        re.compile(r"\brm\s+[^;&|]*--no-preserve-root\b"),
        "deleting through the no-preserve-root guard is never allowed",
    ),
    (
        "root-wipe",
        re.compile(r"\b(?:rd|rmdir)\s+/s\s+/q\s+c:\\?\s*(?:$|[;&|])"),
        "a recursive delete of the C: drive root is never allowed",
    ),
    (
        "root-wipe",
        re.compile(r"\bdel\s+/[fsq]\s+[^;&|]*c:\\\*\s*(?:$|[;&|])"),
        "a forced delete of the C: drive root is never allowed",
    ),
    (
        "root-wipe",
        re.compile(r"\bremove-item\b[^;&|]*-recurse\b[^;&|]*-force\b[^;&|]*(?:c:\\|\$env:systemdrive)\s*(?:$|[;&|])"),
        "a recursive force delete of a system drive root is never allowed",
    ),
    (
        "fork-bomb",
        re.compile(r":\s*\(\s*\)\s*\{[^}]*:\s*\|\s*:[^}]*&[^}]*\}"),
        "a fork bomb is never allowed",
    ),
    (
        "raw-device",
        re.compile(r"\bdd\b[^;&|]*\bof\s*=\s*/dev/(?:sd|nvme|hd|disk|mmcblk)"),
        "writing raw bytes to a block device destroys the host",
    ),
    (
        "raw-device",
        re.compile(r">\s*/dev/(?:sd|nvme|hd|disk|mmcblk)\w*"),
        "redirecting output to a block device destroys the host",
    ),
    (
        "raw-device",
        re.compile(r"\bmkfs(?:\.\w+)?\b"),
        "formatting a filesystem is never allowed from the agent",
    ),
    (
        "raw-device",
        re.compile(r"\bformat\s+[a-z]:\s*(?:$|[;&|])"),
        "formatting a drive is never allowed from the agent",
    ),
    (
        "raw-device",
        re.compile(r"\bdiskpart\b"),
        "disk partitioning is never allowed from the agent",
    ),
    (
        "raw-device",
        re.compile(r"\b(?:clear-disk|initialize-disk|format-volume)\b"),
        "disk management cmdlets are never allowed from the agent",
    ),
    (
        "pipe-to-root",
        re.compile(
            r"\b(?:curl|wget|iwr|invoke-webrequest)\b[^;&|]*\|\s*"
            r"(?:sudo\s+)?(?:sh|bash|zsh|dash|python\d*|perl|ruby|pwsh|powershell)\b"
        ),
        "piping a downloaded script into an interpreter is never allowed",
    ),
    (
        "pipe-to-root",
        re.compile(r"\b(?:iwr|invoke-webrequest)\b[^;&|]*\|\s*(?:invoke-expression|iex)\b"),
        "piping a download into Invoke-Expression is never allowed",
    ),
    (
        "recursive-permissions",
        re.compile(r"\bchmod\s+(?:-[a-z]+\s+)*-r\s+[0-7]{3,4}\s+/\s*(?:$|[;&|])"),
        "a recursive permission change on the filesystem root is never allowed",
    ),
    (
        "recursive-permissions",
        re.compile(r"\bchmod\s+-r\s+[^;&|]+\s+/\s*(?:$|[;&|])"),
        "a recursive permission change on the filesystem root is never allowed",
    ),
    (
        "recursive-permissions",
        re.compile(r"\b(?:icacls\s+[a-z]:\\?\s+/grant|takeown\s+/f\s+[a-z]:)"),
        "taking ownership of / granting everyone a whole system drive is never allowed",
    ),
    (
        "root-shell",
        re.compile(r"\bsudo\s+(?:-[a-z]+\s+)*(?:su|-i|bash|sh|zsh)\b"),
        "obtaining a root shell is never allowed from the agent",
    ),
    (
        "root-shell",
        re.compile(r"\bsu\s+-\s*(?:$|[;&|])"),
        "switching to a login root shell is never allowed from the agent",
    ),
    (
        "root-shell",
        re.compile(r"\brunas\s+/user:"),
        "switching the Windows user context is never allowed from the agent",
    ),
    (
        "root-shell",
        re.compile(r"\bstart-process\b[^;&|]*-verb\s+runas\b"),
        "elevating a process with RunAs is never allowed from the agent",
    ),
    (
        "system-dir-write",
        re.compile(
            r"\b(?:rm|del|rd|rmdir|remove-item|erase)\b[^;&|]*"
            r"(?:c:\\windows|/etc/|/usr/|/bin/|/boot/|c:\\program files)"
        ),
        "destroying an operating-system directory is never allowed",
    ),
)


def evaluate(command: str, *, tool: str = "") -> Optional[HardlineVerdict]:
    """Return the first hardline verdict for `command`, or None.

    `tool` is accepted so an audit/event can name the surface; the decision does
    not depend on it.
    """
    text = _normalize(command)
    if not text:
        return None
    for rule, pattern, reason in _RULES:
        if pattern.search(text):
            return HardlineVerdict(rule=rule, reason=reason)
    return None


def command_from_args(args: Any) -> str:
    """Extract a command string from an effectful tool's arguments.

    Accepts the two shapes the harness actually uses: a `command`/`cmd` string,
    or an argv list (`terminal_run`). Anything else yields "".
    """
    if not isinstance(args, dict):
        return ""
    for key in ("command", "cmd"):
        value = args.get(key)
        if isinstance(value, str) and value.strip():
            return value
    argv = args.get("argv")
    if isinstance(argv, (list, tuple)):
        return " ".join(str(part) for part in argv)
    return ""


__all__ = ["HardlineVerdict", "command_from_args", "evaluate"]
