"""W3.2 — deterministic tool-loop guardrails (warn first, then a controlled halt).

This is NOT a second agent loop and NOT a second tool registry. It is a pure
decision function the ONE tools node calls before and after a dispatch. It
observes **successes** (the existing `recovery.progress.ProgressTracker`
observes failures), so three identical *successful* calls — which are invisible
to a failure tracker — finally stop costing the run.

Rules (all deterministic; no model, no I/O, no clock):

  * `identical_call` — the same name + canonical args has already returned the
    same result twice; the third identical call is halted BEFORE dispatch.
  * `cycle` — a repeated signature sequence of period 2–4 is observed twice; the
    next call that would continue it is halted.
  * `failure_streak` — four consecutive failed calls with no intervening
    success and no state change; the next call is halted.

Repeatable tools (`read_tool_output`, `clarify`, pollers, result getters) are
exempt from `identical_call`: polling the same handle is their job.

Modes:
  * `off`  — no observation, no decisions (byte-identical to the old loop);
  * `warn` — execute the call; append one directive to its result text;
  * `halt` — do not execute the offending call; the caller stops the turn with
             a deterministic notice (never fabricated data).

State is per attempt. `request_reset(run_id)` clears a run's ledger so an
operator can resume a halted loop without restarting the process.
"""

from __future__ import annotations

import hashlib
import json
import threading
from dataclasses import dataclass, field
from typing import Any, Optional

from .recovery.progress import attempt_digest

#: Tools whose repetition is intentional. Never counted as an identical call.
REPEATABLE_EXACT = frozenset({
    "read_tool_output",
    "process_manage",
    "clarify",
    "tool_search",
})
REPEATABLE_SUFFIXES = ("_get_result", "_poll", "_status", "_wait")

#: A bounded process-local set of runs whose ledger an operator cleared.
_RESET_RUNS: set[str] = set()
_RESET_LOCK = threading.Lock()
_MAX_RESET_RUNS = 500


def is_repeatable(name: str) -> bool:
    tool = str(name or "")
    return tool in REPEATABLE_EXACT or tool.endswith(REPEATABLE_SUFFIXES)


def args_digest(name: str, args: Any) -> str:
    """The canonical (name, args) digest — shared with recovery's tracker."""
    return attempt_digest(str(name or ""), args)


def result_digest(text: str, ok: bool, data: Any) -> str:
    """A stable digest of a result. Raw text is never stored."""
    try:
        payload = json.dumps(data, sort_keys=True, default=str)
    except Exception:  # noqa: BLE001 - an unserializable result still gets a digest
        payload = repr(data)
    raw = f"{int(bool(ok))}|{str(text or '')[:4000]}|{payload}"
    return hashlib.sha256(raw.encode("utf-8", errors="replace")).hexdigest()[:32]


@dataclass(frozen=True)
class ToolSignature:
    name: str
    args_hash: str
    result_hash: Optional[str] = None


@dataclass(frozen=True)
class GuardrailDecision:
    action: str  # allow | warn | halt
    rule: str  # identical_call | cycle | failure_streak | budget
    count: int
    message: str

    @property
    def should_halt(self) -> bool:
        return self.action == "halt"

    def directive(self) -> str:
        return f"\n\n[guardrail] {self.message}"


@dataclass
class Observation:
    name: str
    args_hash: str
    result_hash: str
    ok: bool


def _allow() -> GuardrailDecision:
    return GuardrailDecision("allow", "", 0, "")


@dataclass
class ToolGuardrail:
    """Per-run (per-attempt) controller. Cheap, bounded and deterministic."""

    mode: str = "warn"
    max_identical: int = 3
    max_failure_streak: int = 4
    history_limit: int = 64
    observations: list[Observation] = field(default_factory=list)
    consecutive_failures: int = 0
    cycle_next: Optional[tuple[str, str]] = None

    def reset(self) -> None:
        self.observations.clear()
        self.consecutive_failures = 0
        self.cycle_next = None

    def _should_reset(self, run_id: str) -> bool:
        if not run_id:
            return False
        with _RESET_LOCK:
            if run_id in _RESET_RUNS:
                _RESET_RUNS.discard(run_id)
                return True
        return False

    def before(self, name: str, args: Any, *, run_id: str = "") -> GuardrailDecision:
        """Decide BEFORE dispatch. Never halts the first occurrence."""
        if self.mode == "off":
            return _allow()
        if self._should_reset(run_id):
            self.reset()
        if is_repeatable(name):
            return _allow()

        args_hash = args_digest(name, args)

        if self.cycle_next == (name, args_hash):
            self.cycle_next = None
            return GuardrailDecision(
                "halt" if self.mode == "halt" else "warn",
                "cycle",
                2,
                "This call repeats a cycle the run has already completed twice. "
                "Use a result already gathered or change the approach.",
            )

        if self.consecutive_failures >= self.max_failure_streak:
            return GuardrailDecision(
                "halt" if self.mode == "halt" else "warn",
                "failure_streak",
                self.consecutive_failures,
                f"The last {self.consecutive_failures} calls failed with no progress. "
                "Stop retrying; report the blocker or change the approach.",
            )

        same = [
            obs for obs in self.observations
            if obs.name == name and obs.args_hash == args_hash
        ]
        needed = max(1, int(self.max_identical) - 1)
        if len(same) >= needed:
            recent = same[-needed:]
            if len({obs.result_hash for obs in recent}) == 1:
                return GuardrailDecision(
                    "halt" if self.mode == "halt" else "warn",
                    "identical_call",
                    len(same) + 1,
                    f"{name!r} has already returned the same result {len(same)} times. "
                    "Use the earlier result or change the arguments.",
                )
        return _allow()

    def after(
        self,
        name: str,
        args: Any,
        *,
        ok: bool,
        text: str,
        data: Any = None,
    ) -> Optional[GuardrailDecision]:
        """Record one completed result and arm the cycle detector."""
        if self.mode == "off":
            return None
        args_hash = args_digest(name, args)
        self.observations.append(Observation(
            name=str(name or ""),
            args_hash=args_hash,
            result_hash=result_digest(text, ok, data),
            ok=bool(ok),
        ))
        if len(self.observations) > self.history_limit:
            del self.observations[: len(self.observations) - self.history_limit]

        self.consecutive_failures = 0 if ok else self.consecutive_failures + 1
        self._detect_cycle()
        return None

    def _detect_cycle(self) -> None:
        """Arm `cycle_next` when the last 2p signatures are a p-period repeat."""
        signatures = [(obs.name, obs.args_hash) for obs in self.observations]
        for period in (2, 3, 4):
            window = period * 2
            if len(signatures) < window:
                continue
            tail = signatures[-window:]
            if tail[:period] == tail[period:]:
                # The next call in the loop would restart the period.
                self.cycle_next = tail[0]
                return
        self.cycle_next = None


def request_reset(run_id: str) -> None:
    """Clear a run's guardrail ledger on its next decision (operator reset)."""
    if not run_id:
        return
    with _RESET_LOCK:
        _RESET_RUNS.add(str(run_id))
        if len(_RESET_RUNS) > _MAX_RESET_RUNS:
            _RESET_RUNS.pop()


__all__ = [
    "GuardrailDecision",
    "Observation",
    "REPEATABLE_EXACT",
    "REPEATABLE_SUFFIXES",
    "ToolGuardrail",
    "ToolSignature",
    "args_digest",
    "is_repeatable",
    "request_reset",
    "result_digest",
]
