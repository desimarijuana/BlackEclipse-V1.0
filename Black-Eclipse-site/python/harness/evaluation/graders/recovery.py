"""Recovery grader.

Measures, from the captured trajectory, whether a failed route was followed by
a justified DIFFERENT attempt (an alternative route, or a same-route retry after
an intervening repair) and whether the run blindly repeated a failed route.
Every signal is structural (``tool.requested`` / ``tool.completed`` /
``tool.failed`` + recorded arguments); the model's prose is never consulted.

Modes:

* ``recover_required`` — the task declares that a failure MUST be recovered:
  passing requires a successful attempt after the failure (a different route, or
  the same route after an intervening different call).
* ``stop_expected`` — the correct response to the failure is to STOP (e.g. a
  budget kill): passing requires only that the failed route was not repeated
  blindly.
* ``any`` (default) — no recovery requirement; only redundant retries count.

No failure in the trace at all ⇒ ``unmeasured`` (you cannot violate a recovery
floor you never ran) — never a fabricated pass.
"""

from __future__ import annotations

import json
from typing import Any

from . import GradeContext, Grader, GraderResult


def _route(call: dict[str, Any]) -> tuple[str, str]:
    try:
        args = json.dumps(call.get("args") or {}, sort_keys=True, default=str)
    except Exception:  # noqa: BLE001 - a non-serializable arg still gets a route key
        args = str(call.get("args"))
    return str(call.get("name")), args


class RecoveryGrader(Grader):
    name = "recovery"

    def grade(self, ctx: GradeContext) -> GraderResult:
        config = dict(self.config)
        mode = str(config.get("mode") or "any")
        max_redundant = int(config.get("max_redundant_retries", 0))
        calls = list(ctx.tool_calls)
        if not calls:
            return GraderResult.unmeasured_result(self.name, "no tool calls recorded")

        failed = [(i, c, _route(c)) for i, c in enumerate(calls) if c.get("status") == "failed"]
        if not failed:
            return GraderResult.unmeasured_result(self.name, "no tool failure occurred")
        failed_routes = {route for _i, _c, route in failed}

        # A completed call is a recovery when it follows a failure and is either a
        # different route or (same route) had an intervening call that changed the
        # state. Blind same-route repeats never execute (the graph suppresses the
        # duplicate), so a re-run of the same route can only succeed after repair.
        recovered = False
        for i, call in enumerate(calls):
            if call.get("status") != "completed":
                continue
            route = _route(call)
            for j, _f, froute in failed:
                if j >= i:
                    continue
                intervening = any(
                    k > j and k < i and _route(calls[k]) != froute for k in range(len(calls))
                )
                if route != froute or intervening:
                    recovered = True
                    break
            if recovered:
                break

        # Redundant: a failed route that had ALREADY failed before (a blind repeat;
        # the runtime turns the second attempt into a suppressed duplicate).
        seen_failed: set[tuple[str, str]] = set()
        redundant = 0
        for _i, _c, route in failed:
            if route in seen_failed:
                redundant += 1
            seen_failed.add(route)

        failures: list[str] = []
        if mode == "recover_required" and not recovered:
            failures.append("recovery was required but no successful route followed the failure")
        if redundant > max_redundant:
            failures.append(f"a failed route was repeated identically {redundant} time(s)")

        if mode == "recover_required":
            base = 1.0 if recovered else 0.0
        elif mode == "stop_expected":
            base = 1.0
        else:
            base = 1.0 if recovered else 0.5
        score = max(0.0, base - (0.5 if redundant else 0.0))

        details = {
            "mode": mode,
            "failed_routes": [f"{name}:{args[:80]}" for name, args in sorted(failed_routes)],
            "recovered": recovered,
            "alternative_route_used": recovered,
            "redundant_retries": redundant,
            "failures_recorded": len(failed),
        }
        return GraderResult(
            self.name, score, not failures, details=details, failures=failures,
            evidence=[{"routes": [c.get("name") for c in calls]}],
        )
