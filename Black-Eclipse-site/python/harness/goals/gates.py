"""Deterministic goal gates (W4).

A gate is a NAMED check from the closed `code/commands.py` vocabulary, never a
shell string: `build_argv` pins an absolute executable and validates every
argument, `policy.decide_command` applies the same profile/workspace gate as a
chat command, and `sandbox.run` scrubs the environment and enforces the timeout
and output caps. A failing exit code is DEFINITIVE — it is returned once and the
judge is never consulted. Only infrastructure failures are retryable.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Optional

from ..code import commands, policy, sandbox
from ..config import flags

#: Keep the tail: a failing test prints the useful lines at the end.
GATE_OUTPUT_TAIL_CHARS = 3_000

_INFRA_ERRORS = frozenset({
    "COMMAND_EXECUTABLE_MISSING", "COMMAND_NOT_ALLOWLISTED",
    "COMMAND_NOT_ENABLED", "COMMAND_MALFORMED", "SANDBOX_UNAVAILABLE",
    "SANDBOX_STREAM", "WORKSPACE_MISSING", "PROFILE_DENIED",
})


@dataclass(frozen=True)
class GateResult:
    gate_id: str
    check: str
    ok: bool
    exit_code: Optional[int] = None
    timed_out: bool = False
    duration_ms: int = 0
    output_tail: str = ""
    error_code: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "gateId": self.gate_id, "check": self.check, "ok": self.ok,
            "exitCode": self.exit_code, "timedOut": self.timed_out,
            "durationMs": self.duration_ms, "outputTail": self.output_tail,
            "errorCode": self.error_code,
        }


def _tail(text: str, cap: int = GATE_OUTPUT_TAIL_CHARS) -> str:
    text = str(text or "")
    if len(text) <= cap:
        return text
    dropped = len(text) - cap
    return f"[... {dropped} characters omitted ...]\n" + text[-cap:]


def resolve_binding(service: Any, workspace_id: Optional[str]) -> Optional[policy.WorkspaceBinding]:
    """Resolve a durable code workspace into a policy binding, or None.

    A released workspace is not silently reused: a gate that cannot run in a
    live workspace returns a typed failure instead of touching an unknown root.
    """
    if not workspace_id:
        return None
    store = getattr(service, "code_store", None)
    if store is None:
        return None
    try:
        row = store.get_workspace(workspace_id)
    except Exception:  # noqa: BLE001 - a missing store is a missing workspace
        return None
    if not row or not row.get("root") or row.get("releasedAt"):
        return None
    return policy.WorkspaceBinding(
        id=str(row.get("id") or workspace_id),
        root=Path(str(row.get("root"))),
        base_revision=str(row.get("baseRevision") or ""),
        strategy=str(row.get("strategy") or "worktree"),
    )


def _actor(binding: policy.WorkspaceBinding, autonomy: str) -> Any:
    """The goal's gate actor.

    A goal with a workspace was created by an operator-authenticated caller; the
    actor carries the goal's OWN profile, so a `plan_only` goal cannot acquire
    `command.execute` just because it declared a gate. A gate needs
    `edit_verify` (or wider), and creation refuses the contradictory combination.
    """
    return SimpleNamespace(workspace_id=binding.id, autonomy=autonomy)


def _one_attempt(
    gate: Any, binding: policy.WorkspaceBinding, autonomy: str,
) -> GateResult:
    check = str(getattr(gate, "check", "") or "")
    gate_id = str(getattr(gate, "id", "") or check)
    try:
        command_class = commands.resolve_class(check)
        raw_args = getattr(gate, "args", None) or {}
        argv = commands.build_argv(command_class, dict(raw_args))
    except commands.CommandUnavailable as exc:
        return GateResult(gate_id, check, False, error_code=exc.code,
                          output_tail=_tail(exc.reason))
    except Exception as exc:  # noqa: BLE001 - a malformed gate is a typed refusal
        return GateResult(gate_id, check, False, error_code="GATE_INVALID",
                          output_tail=_tail(str(exc)))

    decision = policy.decide_command(_actor(binding, autonomy), binding, check, argv)
    if not decision.allowed:
        return GateResult(gate_id, check, False, error_code=decision.code,
                          output_tail=_tail(decision.reason))

    requested = int(getattr(gate, "timeout_seconds", 600) or 600)
    ceiling = flags.get_int("HARNESS_GOAL_GATE_TIMEOUT_S")
    cap = max(10, min(requested, int(command_class.timeout_s), ceiling))
    spec = sandbox.RunSpec(
        argv=argv,
        cwd=binding.root,
        env=sandbox.build_env(),
        timeout_s=cap,
        output_cap_bytes=int(command_class.output_cap_bytes),
        network=bool(command_class.network),
    )
    try:
        raw = sandbox.run(spec)
    except sandbox.SandboxUnavailable as exc:
        return GateResult(gate_id, check, False,
                          error_code=getattr(exc, "code", "SANDBOX_UNAVAILABLE"),
                          output_tail=_tail(str(exc)))
    except Exception as exc:  # noqa: BLE001 - a sandbox crash is an infrastructure failure
        return GateResult(gate_id, check, False, error_code="SANDBOX_UNAVAILABLE",
                          output_tail=_tail(str(exc)))

    timed_out = bool(getattr(raw, "timed_out", False))
    exit_code = getattr(raw, "exit_code", None)
    ok = (not timed_out and exit_code == 0
          and not getattr(raw, "killed", False)
          and not getattr(raw, "launch_error", None))
    error_code = ""
    if getattr(raw, "launch_error", None):
        error_code = "SANDBOX_UNAVAILABLE"
    elif timed_out:
        error_code = "GATE_TIMEOUT"
    return GateResult(
        gate_id=gate_id, check=check, ok=ok, exit_code=exit_code,
        timed_out=timed_out, duration_ms=int(getattr(raw, "duration_ms", 0) or 0),
        output_tail=_tail(getattr(raw, "output", "") or ""), error_code=error_code,
    )


def run_gate(
    gate: Any, binding: Optional[policy.WorkspaceBinding], *,
    autonomy: str = "edit_verify",
) -> GateResult:
    """Run one gate. A non-zero exit is never retried; infrastructure may be."""
    if binding is None:
        return GateResult(
            str(getattr(gate, "id", "") or getattr(gate, "check", "")),
            str(getattr(gate, "check", "")), False,
            error_code="WORKSPACE_MISSING",
            output_tail="this goal has no live workspace for its gates",
        )
    retries = max(0, min(int(getattr(gate, "retries", 0) or 0), 5))
    result = _one_attempt(gate, binding, autonomy)
    attempts = 0
    while (not result.ok and result.error_code in _INFRA_ERRORS
           and attempts < retries):
        attempts += 1
        result = _one_attempt(gate, binding, autonomy)
    return result


def run_gates(
    gates: list[Any], binding: Optional[policy.WorkspaceBinding], *,
    autonomy: str = "edit_verify",
) -> list[GateResult]:
    return [run_gate(gate, binding, autonomy=autonomy) for gate in gates]


__all__ = [
    "GATE_OUTPUT_TAIL_CHARS",
    "GateResult",
    "resolve_binding",
    "run_gate",
    "run_gates",
]
