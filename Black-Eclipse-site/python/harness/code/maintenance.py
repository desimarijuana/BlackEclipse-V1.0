"""Offline maintenance mode for Eclipse's own authority files (Phase 22 / S3).

The live self-host path REFUSES a change to the files that decide Eclipse's own
permission, approval and policy floor (``selfhost.AUTHORITY_PATHS``). That refusal
is correct and stays. This module is the one supported door:

    stop the builder -> apply -> run the full gate -> restart -> health-check
    -> roll back on any failure

It is deliberately NOT a hot swap. The agent runtime is stopped while its own
judge changes, the checks run BEFORE the restart, and a failure leaves the tree
byte-identical. Every side effect is injected, so the policy is testable without
a live process; the CLI is the thin real runner.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional

from . import promotion, selfhost

#: A preview is a small JSON document; never read an unbounded one.
MAX_PREVIEW_BYTES = 4_000_000


class MaintenanceError(Exception):
    """A maintenance refusal/failure with a stable code."""

    def __init__(
        self, code: str, reason: str, *, detail: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(reason)
        self.code = code
        self.reason = reason
        self.detail = detail or {}


def _norm(path: str) -> str:
    text = str(path or "").replace("\\", "/")
    while text.startswith("./"):
        text = text[2:]
    return text


@dataclass(frozen=True)
class MaintenancePlan:
    """What an offline landing will do, in order."""

    preview_digest: str
    files: tuple[str, ...]
    authorities: tuple[str, ...]
    steps: tuple[str, ...]
    requires_offline: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "previewDigest": self.preview_digest,
            "files": list(self.files),
            "authorities": list(self.authorities),
            "steps": list(self.steps),
            "requiresOffline": self.requires_offline,
        }


def plan_maintenance(preview: dict[str, Any]) -> MaintenancePlan:
    """Validate a preview and say what maintenance would do.

    A plan is valid only when it names a file set and a digest; a change that
    touches no authority file is NOT a maintenance change and is refused, so
    this door can never become a second way to land an ordinary edit.
    """
    if not isinstance(preview, dict):
        raise MaintenanceError("INVALID_PREVIEW", "The preview is not an object.")
    files = tuple(
        _norm(str(item.get("path") or ""))
        for item in (preview.get("files") or [])
        if isinstance(item, dict) and item.get("path")
    )
    if not files:
        raise MaintenanceError("EMPTY_PREVIEW", "The preview names no files.")
    digest = str(preview.get("previewDigest") or "").strip()
    if not digest:
        raise MaintenanceError("MISSING_DIGEST", "The preview has no digest.")
    authorities = tuple(sorted(p for p in files if p in selfhost.AUTHORITY_PATHS))
    if not authorities:
        raise MaintenanceError(
            "MAINTENANCE_NOT_REQUIRED",
            "This change touches no authority file; land it through the normal review.",
        )
    return MaintenancePlan(
        preview_digest=digest,
        files=files,
        authorities=authorities,
        steps=("check_tree", "stop_builder", "apply", "verify", "restart", "health"),
        requires_offline=True,
    )


def _rollback(
    rollback: Callable[[str], Any], rollback_id: str,
) -> bool:
    if not rollback_id:
        return False
    try:
        rollback(rollback_id)
        return True
    except Exception:  # noqa: BLE001 - a failed rollback is still a refusal
        return False


def run_maintenance(
    preview: dict[str, Any],
    *,
    tree_clean: bool,
    stop_builder: Callable[[], Any],
    apply: Callable[[dict[str, Any]], dict[str, Any]],
    verify: Callable[[], bool],
    restart: Callable[[], Any],
    health: Callable[[], bool],
    rollback: Callable[[str], Any],
    allow_dirty: bool = False,
) -> dict[str, Any]:
    """Apply one authority change offline, with a rollback on any failure.

    Order is the safety contract: stop -> apply -> verify -> restart -> health.
    A failed verify NEVER restarts; a failed restart/health puts the previous
    files back. The caller owns the process control (front door/supervisor), so
    the runtime never tries to restart itself.
    """
    plan = plan_maintenance(preview)
    if not tree_clean and not allow_dirty:
        raise MaintenanceError(
            "DIRTY_TREE",
            "The working tree has uncommitted changes. Commit or stash them, or pass allow_dirty deliberately.",
        )

    stop_builder()
    try:
        applied = apply(preview)
    except Exception as exc:  # noqa: BLE001 - apply failures become a typed refusal
        raise MaintenanceError("APPLY_FAILED", str(exc)) from exc
    rollback_id = str((applied or {}).get("rollbackId") or "")

    try:
        verified = bool(verify())
    except Exception:  # noqa: BLE001 - a failing check is a failed verification
        verified = False
    if not verified:
        rolled_back = _rollback(rollback, rollback_id)
        raise MaintenanceError(
            "VERIFY_FAILED",
            "A required check failed, so the change was not activated.",
            detail={"rollbackId": rollback_id, "rolledBack": rolled_back},
        )

    try:
        restart()
    except Exception as exc:  # noqa: BLE001 - a failed restart is a failed landing
        rolled_back = _rollback(rollback, rollback_id)
        raise MaintenanceError(
            "RESTART_FAILED",
            "Eclipse did not restart, so the previous files were put back.",
            detail={"rollbackId": rollback_id, "rolledBack": rolled_back},
        ) from exc

    try:
        healthy = bool(health())
    except Exception:  # noqa: BLE001 - a failing probe is a failed health check
        healthy = False
    if not healthy:
        rolled_back = _rollback(rollback, rollback_id)
        raise MaintenanceError(
            "HEALTH_FAILED",
            "Eclipse did not come back healthy, so the previous files were put back.",
            detail={"rollbackId": rollback_id, "rolledBack": rolled_back},
        )

    return {
        "ok": True,
        "plan": plan.to_dict(),
        "rollbackId": rollback_id or None,
        "verified": True,
        "healthy": True,
    }


def load_preview(path: str | Path) -> dict[str, Any]:
    """Read a preview JSON with a hard size cap. Never trusts the file's shape."""
    target = Path(path)
    try:
        size = target.stat().st_size
    except OSError as exc:
        raise MaintenanceError("PREVIEW_NOT_FOUND", str(exc)) from exc
    if size > MAX_PREVIEW_BYTES:
        raise MaintenanceError("PREVIEW_TOO_LARGE", "The preview file is too large.")
    try:
        value = json.loads(target.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        raise MaintenanceError("INVALID_PREVIEW", str(exc)) from exc
    if not isinstance(value, dict):
        raise MaintenanceError("INVALID_PREVIEW", "The preview is not an object.")
    return value


def _emit(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, sort_keys=True))


# ── The real runner (operator-run; the policy above is what is tested) ───────


def _run(argv: list[str], cwd: Path, timeout_s: int = 1_800) -> subprocess.CompletedProcess:
    return subprocess.run(
        argv, cwd=str(cwd), capture_output=True, text=True,
        timeout=timeout_s, shell=False,
    )


def _tree_is_clean(repo: Path) -> bool:
    result = _run(["git", "status", "--porcelain"], repo, 60)
    return result.returncode == 0 and not result.stdout.strip()


def _spawn(argv: list[str], cwd: Path) -> None:
    """Start the app again, detached, so this runner can exit."""
    kwargs: dict[str, Any] = {}
    if os.name == "nt":
        kwargs["creationflags"] = (
            getattr(subprocess, "DETACHED_PROCESS", 0)
            | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        )
    else:
        kwargs["start_new_session"] = True
    subprocess.Popen(
        argv, cwd=str(cwd), stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **kwargs,
    )


def _probe(url: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=5.0) as response:
            return 200 <= int(response.status) < 500
    except Exception:  # noqa: BLE001 - not up yet
        return False


def _wait_healthy(profile: str, timeout_s: int = 180) -> bool:
    app_port = 3100 if profile == "prod" else 3000
    harness_port = 8766 if profile == "prod" else 8765
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if (_probe(f"http://127.0.0.1:{app_port}/")
                and _probe(f"http://127.0.0.1:{harness_port}/health")):
            return True
        time.sleep(2.0)
    return False


def execute(
    *, repo: Path, preview: dict[str, Any], profile: str,
    allow_dirty: bool, skip_tests: bool,
) -> dict[str, Any]:
    """Run one authority change end to end. The process control lives here.

    The app is stopped, the change is applied, the gate runs, the app restarts,
    and health is probed. A failure after the stop restarts the PREVIOUS version,
    so an operator is never left with no app.
    """

    state = {"stopped": False}

    def stop_builder() -> None:
        _run(["node", "scripts/kill-port.js", profile], repo, 120)
        state["stopped"] = True

    def apply(value: dict[str, Any]) -> dict[str, Any]:
        return promotion.apply_promotion(value)

    def verify() -> bool:
        if skip_tests:
            return True
        tsc = _run(["npx", "tsc", "--noEmit"], repo)
        if tsc.returncode != 0:
            print(tsc.stdout[-4000:], file=sys.stderr)
            print(tsc.stderr[-4000:], file=sys.stderr)
            return False
        tests = _run(["npm", "run", "test"], repo)
        if tests.returncode != 0:
            print(tests.stdout[-6000:], file=sys.stderr)
            print(tests.stderr[-4000:], file=sys.stderr)
            return False
        return True

    def restart() -> None:
        _spawn(["npm", "run", "up" if profile == "prod" else "dev"], repo)

    def health() -> bool:
        return _wait_healthy(profile)

    try:
        return run_maintenance(
            preview, tree_clean=_tree_is_clean(repo),
            stop_builder=stop_builder, apply=apply, verify=verify,
            restart=restart, health=health,
            rollback=promotion.rollback_promotion, allow_dirty=allow_dirty,
        )
    except MaintenanceError:
        # The old files are back (or never changed); bring the app up again - but
        # only if this run actually stopped it. A dirty-tree refusal must not
        # spawn a second server.
        if state["stopped"]:
            try:
                restart()
            except Exception:  # noqa: BLE001 - a failed restart is reported by the caller
                pass
        raise


def main(argv: Optional[list[str]] = None) -> int:
    """Thin CLI: `plan` (safe), `apply`, `rollback`, and `execute` (operator)."""
    parser = argparse.ArgumentParser(prog="harness.code.maintenance")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("plan", "apply"):
        command = sub.add_parser(name)
        command.add_argument("--preview", required=True)
    rollback_parser = sub.add_parser("rollback")
    rollback_parser.add_argument("--rollback-id", required=True)
    run_parser = sub.add_parser("execute")
    run_parser.add_argument("--preview", required=True)
    run_parser.add_argument("--repo", default=".")
    run_parser.add_argument("--profile", choices=("prod", "dev"), default="prod")
    run_parser.add_argument("--allow-dirty", action="store_true")
    run_parser.add_argument("--skip-tests", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.command == "plan":
            _emit(plan_maintenance(load_preview(args.preview)).to_dict())
            return 0
        if args.command == "apply":
            preview = load_preview(args.preview)
            plan_maintenance(preview)  # enforce the authority-only rule first
            _emit(promotion.apply_promotion(preview))
            return 0
        if args.command == "rollback":
            _emit(promotion.rollback_promotion(args.rollback_id))
            return 0
        preview = load_preview(args.preview)
        plan_maintenance(preview)  # refuse before stopping anything
        _emit(execute(
            repo=Path(args.repo).resolve(), preview=preview, profile=args.profile,
            allow_dirty=args.allow_dirty, skip_tests=args.skip_tests,
        ))
        return 0
    except MaintenanceError as exc:
        _emit({"error": exc.code, "reason": exc.reason, "detail": exc.detail})
        return 2
    except Exception as exc:  # noqa: BLE001 - the CLI reports, never crashes silently
        _emit({"error": "MAINTENANCE_FAILED", "reason": str(exc)})
        return 1


if __name__ == "__main__":
    sys.exit(main())


__all__ = [
    "MAX_PREVIEW_BYTES",
    "MaintenanceError",
    "MaintenancePlan",
    "execute",
    "load_preview",
    "main",
    "plan_maintenance",
    "run_maintenance",
]
