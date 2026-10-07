"""The shared CLI adapter base for orchestration, infrastructure and cloud tools.

Every tool in the *future* tiers — Kubernetes (`kubectl`/`helm`/`kustomize`),
Terraform, and the cloud providers (AWS/Azure/GCP/Cloudflare/Vercel/Railway/
Render) — is a thin, declarative configuration of this ONE base. It exists so a
new provider is DATA (a closed subcommand table + validators), never a new copy of
the sandbox discipline:

  * **No shell.** Argv is a validated list; a name/image/namespace/resource that
    contains a shell metacharacter is a structured `INVALID_ARG` refusal.
  * **One sandbox.** Every call goes through `code/sandbox.py` with a scrubbed
    environment and a bounded timeout/output cap.
  * **Structured output.** A subcommand declares `--output json` (or a parser); the
    result carries parsed data, never a raw blob the model must parse.
  * **Honest availability.** A missing binary is `ENGINE_UNAVAILABLE`; nothing is
    fabricated and nothing runs unsandboxed.

The base owns: executable resolution, the closed subcommand table, argument
validation, JSON parsing, and the risk band per operation. A concrete adapter
declares `name`, `binary`, `capabilities`, an operation table, and (optionally)
`kind`, so the registry can route it.
"""

from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional, Sequence

from ...code import sandbox
from ..models import ResourceLimits, RiskLevel
from .registry import supports

#: A safe token for a Kubernetes/cloud resource name, namespace, label selector,
#: image reference or file path. Deliberately permissive for real identifiers
#: (dots, slashes, colons, `=`, `@`, commas, `*`) but rejects every shell
#: metacharacter (`; & | > < ` $ ( ) { } !` newline) and control characters.
_SAFE_VALUE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_./@:=,+*\[\](){}~-]{0,511}$")
#: A stricter token where only an identifier is expected (a name/namespace).
_SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
#: A Kubernetes DNS-1123 label (namespaces, service names, pod names).
_SAFE_DNS = re.compile(r"^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$")
#: An env-var name.
_SAFE_ENV_KEY = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,127}$")


def is_safe_value(value: str) -> bool:
    return bool(_SAFE_VALUE.match(str(value or "")))


def is_safe_name(value: str) -> bool:
    return bool(_SAFE_NAME.match(str(value or "")))


def is_safe_dns(value: str) -> bool:
    return bool(_SAFE_DNS.match(str(value or "")))


def is_safe_env_key(value: str) -> bool:
    return bool(_SAFE_ENV_KEY.match(str(value or "")))


@dataclass
class CliOperation:
    """One closed operation a CLI adapter can perform.

    `argv` builds the argv *after* the binary and the operation's fixed
    subcommand tokens. `validator` receives the raw argument dict and returns a
    structured refusal code/reason (or None when valid); it is the ONE place a
    value is checked, so a new provider cannot forget to validate.
    """

    name: str
    subcommand: tuple[str, ...] = ()
    argv: Optional[Callable[[dict[str, Any]], list[str]]] = None
    validator: Optional[Callable[[dict[str, Any]], Optional[tuple[str, str]]]] = None
    #: Append `--output json` (Kubernetes) or `--format json` (cloud) when set.
    json_output: tuple[str, ...] = ()
    json_parse: bool = False
    risk: str = RiskLevel.MEDIUM.value
    timeout_s: int = 120
    network: bool = True
    #: True when the operation reads only and is safe to run in `plan_only`.
    read_only: bool = False
    description: str = ""


@dataclass
class CliResult:
    """The structured outcome of one CLI operation."""

    ok: bool = False
    code: str = "OK"
    operation: str = ""
    kind: str = "cli"
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


def validate_common(args: dict[str, Any], *, names: Sequence[str] = (), values: Sequence[str] = (),
                    env_keys: Sequence[str] = (), dns: Sequence[str] = ()) -> Optional[tuple[str, str]]:
    """A reusable validator: reject an unsafe value in any named field.

    Returns `(code, reason)` for the first bad value, or None. A missing field is
    skipped (an operation declares its own required-field check).
    """
    for field_name in names:
        value = args.get(field_name)
        if value is None:
            continue
        if not is_safe_name(str(value)):
            return ("INVALID_NAME", f"{field_name!r} is not a valid name")
    for field_name in dns:
        value = args.get(field_name)
        if value is None:
            continue
        if not is_safe_dns(str(value)):
            return ("INVALID_NAME", f"{field_name!r} is not a valid identifier")
    for field_name in values:
        value = args.get(field_name)
        if value is None:
            continue
        items = value if isinstance(value, list) else [value]
        for item in items:
            if not is_safe_value(str(item)):
                return ("INVALID_ARG", f"{field_name!r} contains an unsafe value")
    for field_name in env_keys:
        for key in (args.get(field_name) or {}):
            if not is_safe_env_key(str(key)):
                return ("INVALID_ARG", f"{field_name!r} has an invalid key")
    return None


class CliAdapter:
    """One CLI tool (kubectl, helm, terraform, aws, …) with a closed op table."""

    kind = "cli"
    name = ""
    binary = ""
    capabilities: frozenset[str] = frozenset()
    aliases: tuple[str, ...] = ()
    #: name → CliOperation.
    operations: dict[str, CliOperation] = {}

    def __init__(self, *, binary: Optional[str] = None, limits: Optional[ResourceLimits] = None,
                 runner: Optional[Callable[[list[str], int], "CliResult"]] = None) -> None:
        self.binary = binary or self.binary
        self._limits = limits
        #: TEST SEAM: a runner that returns a canned `CliResult` (no subprocess).
        self._runner = runner
        self.container_subcommands: tuple[str, ...] = ()

    @property
    def limits(self) -> ResourceLimits:
        return self._limits or ResourceLimits.from_env()

    # ── availability ──────────────────────────────────────────────────────────
    def _exe(self) -> str:
        return shutil.which(self.binary) or ""

    def detect(self) -> bool:
        return bool(self._exe())

    def available(self) -> bool:
        return bool(self._exe())

    def version(self) -> str:
        exe = self._exe()
        if not exe:
            return ""
        op = self.operations.get("version")
        argv = [exe] + (list(op.subcommand) if op else ["version"])
        result = self._run_argv(argv, timeout_s=10)
        return _first_line(result.output)

    # ── operations ─────────────────────────────────────────────────────────────
    def supports_operation(self, operation: str) -> bool:
        return operation in self.operations

    def run_operation(self, operation: str, args: Optional[dict[str, Any]] = None) -> CliResult:
        op = self.operations.get(operation)
        if op is None:
            return CliResult(ok=False, code="UNKNOWN_OPERATION", operation=operation,
                             reason=f"{self.name} has no {operation!r} operation")
        args = dict(args or {})
        if op.validator is not None:
            refusal = op.validator(args)
            if refusal is not None:
                code, reason = refusal
                return CliResult(ok=False, code=code, operation=operation, reason=reason)
        # A TEST SEAM runner bypasses the executable probe (no real binary needed).
        if self._runner is not None:
            exe = self.binary
        else:
            exe = self._exe()
            if not exe:
                return CliResult(ok=False, code="ENGINE_UNAVAILABLE", operation=operation,
                                 reason=f"{self.name} isn't installed on this computer")
        argv = [exe, *op.subcommand]
        if op.argv is not None:
            argv += list(op.argv(args))
        if op.json_output:
            argv += list(op.json_output)
        result = self._run_argv(argv, timeout_s=op.timeout_s, network=op.network)
        result.operation = operation
        result.kind = self.kind
        if result.ok and op.json_parse:
            result.data = _parse_json(result.output)
        return result

    # ── execution ───────────────────────────────────────────────────────────────
    def _run_argv(self, argv: list[str], *, timeout_s: int = 120, network: bool = True) -> CliResult:
        if self._runner is not None:  # TEST SEAM
            return self._runner(argv, timeout_s)
        env = sandbox.build_env()
        spec = sandbox.RunSpec(
            argv=list(argv), cwd=Path.cwd(), env=env, timeout_s=max(1, int(timeout_s)),
            output_cap_bytes=self.limits.max_stdout_bytes, network=network,
        )
        try:
            raw = sandbox.run(spec)
        except sandbox.SandboxUnavailable as exc:
            return CliResult(ok=False, code="SANDBOX_UNAVAILABLE", reason=str(exc.reason), argv=list(argv))
        ok = raw.exit_code == 0 and not raw.timed_out and not raw.cancelled
        return CliResult(
            ok=ok, exit_code=raw.exit_code, argv=list(argv), output=raw.output,
            duration_ms=raw.duration_ms, timed_out=raw.timed_out,
            code=("OK" if ok else ("TIMEOUT" if raw.timed_out else "FAILED")),
        )

    def describe(self) -> dict[str, Any]:
        return {
            "name": self.name, "kind": self.kind, "available": self.available(),
            "version": self.version(), "capabilities": sorted(self.capabilities),
            "operations": sorted(self.operations.keys()),
        }


def _first_line(text: str) -> str:
    for line in (text or "").splitlines():
        line = line.strip()
        if line:
            return line[:160]
    return ""


def _parse_json(text: str) -> Any:
    text = (text or "").strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except (json.JSONDecodeError, ValueError):
        for opener in ("{", "["):
            start = text.find(opener)
            if start != -1:
                try:
                    return json.loads(text[start:])
                except (json.JSONDecodeError, ValueError):
                    continue
        return None


__all__ = [
    "CliAdapter",
    "CliOperation",
    "CliResult",
    "is_safe_dns",
    "is_safe_env_key",
    "is_safe_name",
    "is_safe_value",
    "supports",
    "validate_common",
]
