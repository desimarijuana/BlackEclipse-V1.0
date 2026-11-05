"""Self-hosting safety (Track B) — landing a change in Eclipse's OWN running code.

Every other capability edits a DISPOSABLE worktree and promotes text into the
checkout. This module is the extra discipline for a change that reaches Eclipse's
own **live** code, where a generic coding task has no equivalent hazards:

  * a change under `python/harness/**` only takes effect after a RUNTIME RESTART,
    and a bad one can crash the process (the "503 runtime unavailable" path) —
    so a runtime change is applied, restarted, HEALTH-CHECKED, and put back
    automatically if the app does not come back;
  * a change under `src/**` can break the front-end build — flagged as needing a
    build gate;
  * a change to an AUTHORITY path (`code/policy.py`, `code/authorizers.py`,
    `mcp/approvals.py`, `skills/permissions.py`) could alter Eclipse's own
    permissions if hot-swapped — so it is REFUSED here, never applied live.

`classify_landing` is pure and deterministic. `guarded_land` orchestrates
apply → (restart) → verify → rollback, with every side effect INJECTED, so the
policy is tested without a live process. The actual process restart is the ONE
thin seam (`restart`), owned by the front door / `scripts/doctor.js` — the runtime
cannot cleanly restart itself.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Iterable, Optional

from . import promotion

# A change here only takes effect after the Python runtime restarts.
RUNTIME_PREFIXES: tuple[str, ...] = ("python/harness/",)
# A change here can break the Next.js build / front door.
FRONTEND_PREFIXES: tuple[str, ...] = ("src/",)

# Paths whose live reload could change Eclipse's own authority. Never hot-swapped:
# a self-host landing that touches one is refused (a restart-only, operator-driven
# change is the only way — and that is not this path).
AUTHORITY_PATHS: tuple[str, ...] = (
    "python/harness/code/policy.py",
    "python/harness/code/authorizers.py",
    "python/harness/mcp/approvals.py",
    "python/harness/skills/permissions.py",
)


class SelfHostError(Exception):
    """A self-host landing was refused or failed. `code` is stable."""

    def __init__(self, code: str, reason: str) -> None:
        super().__init__(reason)
        self.code = code
        self.reason = reason


def _norm(rel: str) -> str:
    text = str(rel).replace("\\", "/")
    while text.startswith("./"):
        text = text[2:]
    return text


@dataclass(frozen=True)
class LandingVerdict:
    restartRequired: bool  # noqa: N815 - matches the JSON wire shape
    buildRequired: bool  # noqa: N815
    authorities: tuple[str, ...]

    @property
    def refused(self) -> bool:
        return bool(self.authorities)

    def to_dict(self) -> dict[str, Any]:
        return {
            "restartRequired": self.restartRequired,
            "buildRequired": self.buildRequired,
            "authorities": list(self.authorities),
        }


def classify_landing(paths: Iterable[str]) -> LandingVerdict:
    """Classify a promoted file set for self-host landing. Pure, no side effects."""
    restart = False
    build = False
    authorities: set[str] = set()
    for raw in paths:
        rel = _norm(raw)
        if rel in AUTHORITY_PATHS:
            authorities.add(rel)
        if rel.startswith(RUNTIME_PREFIXES):
            restart = True
        if rel.startswith(FRONTEND_PREFIXES):
            build = True
    return LandingVerdict(
        restartRequired=restart, buildRequired=build,
        authorities=tuple(sorted(authorities)),
    )


@dataclass(frozen=True)
class LandingPlan:
    """How a landed change reaches the running app, as ordered steps.

    The plan is the process-boundary contract: a runtime change restarts only
    the BUILDER, a front-end change builds only the TARGET, and an authority
    change is not a live landing at all - it exits through maintenance mode.
    """

    steps: tuple[str, ...]
    restartRequired: bool  # noqa: N815 - matches the wire shape
    buildRequired: bool  # noqa: N815
    maintenanceRequired: bool  # noqa: N815
    authorities: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "steps": list(self.steps),
            "restartRequired": self.restartRequired,
            "buildRequired": self.buildRequired,
            "maintenanceRequired": self.maintenanceRequired,
            "authorities": list(self.authorities),
        }


def plan_landing(paths: Iterable[str]) -> LandingPlan:
    """Classify a file set into the ordered landing steps. Pure."""
    verdict = classify_landing(paths)
    if verdict.refused:
        return LandingPlan(
            steps=("maintenance",), restartRequired=False, buildRequired=False,
            maintenanceRequired=True, authorities=verdict.authorities,
        )
    steps: list[str] = ["apply"]
    if verdict.restartRequired:
        steps.append("restart_builder")
    if verdict.buildRequired:
        steps.append("build_frontend")
    steps.append("health")
    return LandingPlan(
        steps=tuple(steps), restartRequired=verdict.restartRequired,
        buildRequired=verdict.buildRequired, maintenanceRequired=False,
        authorities=(),
    )


def _default_apply(preview: dict[str, Any]) -> dict[str, Any]:
    return promotion.apply_promotion(preview)

def _default_rollback(rollback_id: str) -> dict[str, Any]:
    return promotion.rollback_promotion(rollback_id)


def guarded_land(
    preview: dict[str, Any],
    *,
    verify: Optional[Callable[[], bool]] = None,
    restart: Optional[Callable[[], Any]] = None,
    apply: Optional[Callable[[dict[str, Any]], dict[str, Any]]] = None,
    rollback: Optional[Callable[[str], dict[str, Any]]] = None,
) -> dict[str, Any]:
    """Apply a reviewed change with the self-host safety gate.

    Order: classify → refuse an authority change → apply → restart (when the
    change is runtime code) → `verify()` → on a failed verify, ROLL BACK and raise.
    A change touching neither the runtime nor the front end is a plain apply with
    no gate. `verify` is the health probe (runtime) or the build check (front end);
    when it is None there is nothing to prove, so the apply stands.
    """
    files = list(preview.get("files") or [])
    verdict = classify_landing([str(f.get("path") or "") for f in files])
    if verdict.refused:
        raise SelfHostError(
            "SELFHOST_AUTHORITY_REFUSED",
            "Eclipse won't change its own approval or policy code in a running app.",
        )

    do_apply = apply or _default_apply
    do_rollback = rollback or _default_rollback

    result = do_apply(preview)
    rollback_id = str(result.get("rollbackId") or "")

    if verdict.restartRequired and restart is not None:
        restart()

    if verify is not None:
        try:
            healthy = bool(verify())
        except Exception:  # noqa: BLE001 - a failing probe is a failed verification
            healthy = False
        if not healthy:
            if rollback_id:
                try:
                    do_rollback(rollback_id)
                except Exception:  # noqa: BLE001 - a failed rollback is still a refusal
                    pass
            raise SelfHostError(
                "SELFHOST_VERIFY_FAILED",
                "The app didn't come back healthy, so Eclipse put the change back.",
            )

    return {
        "ok": True,
        "restartRequired": verdict.restartRequired,
        "buildRequired": verdict.buildRequired,
        "rollbackId": rollback_id or None,
        "filesChanged": int(result.get("filesChanged") or 0),
        "verified": verify is not None,
    }


__all__ = [
    "AUTHORITY_PATHS",
    "FRONTEND_PREFIXES",
    "RUNTIME_PREFIXES",
    "LandingPlan",
    "LandingVerdict",
    "SelfHostError",
    "classify_landing",
    "guarded_land",
    "plan_landing",
]
