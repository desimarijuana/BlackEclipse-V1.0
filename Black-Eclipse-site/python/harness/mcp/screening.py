"""Static screening of an MCP server entry (Phase 6, Milestone 1).

`ssrf.py` guards a remote URL and the stdio spawn is argv-only (no shell), but a
hand-edited `mcp-servers.json` could still name a shell interpreter and feed it a
download-and-execute payload. This module inspects the *declared shape* of an
entry before it is saved or spawned, and **refuses rather than sanitizes**.

The screen is intentionally conservative: a false refusal costs the operator one
edit; a false accept can execute an attacker's line. It checks:

  * a shell interpreter as `command` combined with an inline-script flag
    (`-c`, `/c`, `-Command`, `-EncodedCommand`, …);
  * shell control operators (`;`, `&&`, `|`) anywhere in the command or args;
  * download-and-execute shapes (curl/wget/nc/…, `| sh`, `/dev/tcp`), including
    obfuscated PowerShell (`iex`, `DownloadString`, `-enc`);
  * a package token that is a known-malicious (IOC) package name, for a package
    runner command (npx/uvx/pipx/…). Only the package token is matched, never an
    arbitrary path, so a filename containing the same word is not refused.

Findings carry `code`, `status`, `message` and `recovery` so the diagnostics panel
and the settings UI can render an actionable refusal. This is a host-execution
control, not a finance-domain allowlist.
"""

from __future__ import annotations

import os
import re
from dataclasses import asdict, dataclass
from typing import Optional

REFUSE = "error"
WARN = "warn"

# A shell interpreter must never be the `command` for an inline script.
_SHELL_INTERPRETERS = frozenset(
    {
        "sh", "bash", "zsh", "dash", "ksh", "csh", "fish",
        "cmd", "cmd.exe", "powershell", "powershell.exe", "pwsh", "pwsh.exe",
        "wsl", "wsl.exe",
    }
)

# Inline-script flags for those interpreters.
_INLINE_FLAGS = frozenset(
    {
        "-c", "/c", "-command", "/command", "-encodedcommand", "-enc",
        "-eval", "--eval", "-e",
    }
)

# Download / egress / exfil tokens.
_EGRESS_TOKENS = (
    "curl", "wget", "ncat", "netcat", "nc ", "iwr", "invoke-webrequest",
    "invoke-restmethod", "downloadstring", "downloadfile", "downloaddata",
    "invoke-expression", "iex ", "certutil", "bitsadmin", "/dev/tcp/",
    "base64 -d", "frombase64string", "start-process",
)

# Shell control operators that can chain another command.
_CONTROL_RE = re.compile(r"(;|&&|\|\|?|`|\$\(|\$\{)")

# Package runners whose package token is screened against the IOC list.
_PACKAGE_RUNNERS = frozenset({"npx", "bunx", "pnpx", "pnpm", "yarn", "uvx", "pipx", "uv"})

# A conservative seed of known-malicious (IOC) package names, drawn from
# documented public supply-chain advisories (npm/PyPI). This is a *seed* list to
# extend, not a claim of completeness. Only a package token is matched against
# it, so a legitimate file path that merely contains one of these words is not
# refused.
IOC_PACKAGE_NAMES = frozenset(
    {
        "flatmap-stream",
        "crossenv",
        "cross-env.js",
        "jeilyfish",
        "libpeshnx",
        "libpeshka",
        "python3-dateutil",
        "colourama",
    }
)

# Env keys that look like they hold a credential; a value here is a plaintext
# secret in the config file (prefer `secret_refs`).
_SECRET_KEY_RE = re.compile(
    r"(token|secret|password|passwd|api[_-]?key|apikey|credential|private[_-]?key|access[_-]?key)",
    re.IGNORECASE,
)


@dataclass
class Finding:
    code: str
    status: str
    message: str
    recovery: str = ""

    def to_public(self) -> dict[str, str]:
        return asdict(self)


def _basename(token: str) -> str:
    return os.path.basename(token or "").strip().strip('"').lower()


def _iter_strings(command: str, args: list[str]):
    if command:
        yield command
    for arg in args or []:
        if isinstance(arg, str):
            yield arg


def _is_shell_inline(command: str, args: list[str]) -> bool:
    if _basename(command) not in _SHELL_INTERPRETERS:
        # A shell name can also appear as the first package token of a runner.
        return False
    flags = {os.path.basename(a).lower() for a in args if isinstance(a, str) and a.startswith(("-", "/"))}
    return bool(flags & _INLINE_FLAGS)


def _contains_control(text: str) -> Optional[str]:
    match = _CONTROL_RE.search(text or "")
    return match.group(1) if match else None


def _package_token(command: str, args: list[str]) -> Optional[str]:
    base = _basename(command)
    if base not in _PACKAGE_RUNNERS:
        return None
    for arg in args or []:
        if not isinstance(arg, str) or not arg or arg.startswith("-"):
            continue
        # `npx -y pkg`, `yarn dlx pkg`, `uvx pkg` — the first bare token.
        return _basename(arg)
    return None


def screen_stdio(command: str, args: Optional[list[str]] = None, env: Optional[dict[str, str]] = None) -> list[Finding]:
    """Screen a stdio server's command/args/env. Never raises."""
    args = list(args or [])
    findings: list[Finding] = []

    if _is_shell_inline(command, args):
        findings.append(Finding(
            "shell_inline_script", REFUSE,
            f"A shell interpreter `{command}` runs an inline script, which can execute arbitrary commands.",
            "Use the real executable and pass arguments as separate values instead of a shell `-c` string.",
        ))

    for text in _iter_strings(command, args):
        op = _contains_control(text)
        if op:
            findings.append(Finding(
                "shell_metacharacter", REFUSE,
                f"`{op}` in {text!r} can chain another command; MCP servers launch without a shell.",
                "Split the command and its arguments into separate `command`/`args` values.",
            ))
            break

    joined = " ".join(_iter_strings(command, args)).lower()
    hit = next((t for t in _EGRESS_TOKENS if t in joined), None)
    if hit:
        findings.append(Finding(
            "download_and_execute", REFUSE,
            f"{hit.strip()!r} in the launch looks like a download/execute or exfiltration shape.",
            "Launch a package or a real executable directly (e.g. `npx <pkg>`), not a fetch-and-run pipeline.",
        ))

    pkg = _package_token(command, args)
    if pkg and pkg in IOC_PACKAGE_NAMES:
        findings.append(Finding(
            "known_bad_package", REFUSE,
            f"The package {pkg!r} is on the known-malicious (IOC) list.",
            "Remove this server and use an official, vetted package.",
        ))

    for key, value in (env or {}).items():
        if value and _SECRET_KEY_RE.search(str(key)):
            findings.append(Finding(
                "plaintext_env_secret", WARN,
                f"`env.{key}` looks like it holds a credential stored in plaintext.",
                f"Move it to `secret_refs` (env `{key}` → a vault secret name) and clear the value.",
            ))
    return findings


def screen_entry(entry: object) -> list[Finding]:
    """Screen a raw config entry (a dict) before it is parsed or spawned.

    A non-dict entry, or one that is not stdio, yields no findings (the type
    validator handles shape). Never raises.
    """
    if not isinstance(entry, dict):
        return []
    transport = entry.get("transport") or "stdio"
    if transport != "stdio":
        return []
    command = entry.get("command") or ""
    args = entry.get("args") or []
    if not isinstance(args, list):
        args = []
    env = entry.get("env") or {}
    if not isinstance(env, dict):
        env = {}
    return screen_stdio(str(command), [str(a) for a in args], {str(k): str(v) for k, v in env.items()})


def refusals(findings: list[Finding]) -> list[Finding]:
    return [f for f in findings if f.status == REFUSE]


def screen_summary(findings: list[Finding]) -> dict[str, object]:
    """A compact, secret-free summary for the API/UI."""
    return {
        "ok": not refusals(findings),
        "findings": [f.to_public() for f in findings],
    }


__all__ = [
    "Finding",
    "REFUSE",
    "WARN",
    "IOC_PACKAGE_NAMES",
    "screen_stdio",
    "screen_entry",
    "refusals",
    "screen_summary",
]
