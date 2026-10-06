"""The build engine — detect, plan, execute, normalize, collect.

The engine owns the *shape* of a build but not the language: it asks the runtime
adapter for a `PreparedCommand`, runs it through the ONE sandbox, and normalizes
the output through the diagnostic engine. A language with no build step returns
`success: true` honestly (Python's `compileall` is a syntax check, not a build).

`DependencyManager` is a thin, policy-gated wrapper: it never installs anything on
its own. It reports what WOULD be installed (from lockfiles/manifests) and defers
the actual install to the existing `command_run` broker's `dependency_install`
class, which is operator-gated and network-controlled.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from ..code import sandbox
from .diagnostics import DiagnosticEngine
from .models import Diagnostic, resource_run_kwargs


@dataclass
class BuildResult:
    """The structured result of a build."""

    success: bool
    exit_code: Optional[int]
    duration_ms: int
    errors: list[Diagnostic] = field(default_factory=list)
    stdout: str = ""
    stderr: str = ""
    command: list[str] = field(default_factory=list)
    skipped: bool = False
    reason: str = ""
    backend: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "exitCode": self.exit_code,
            "durationMs": self.duration_ms,
            "errors": [e.to_dict() for e in self.errors],
            "stdout": self.stdout,
            "stderr": self.stderr,
            "command": self.command,
            "skipped": self.skipped,
            "reason": self.reason,
            "backend": self.backend,
        }


class BuildEngine:
    """Detect the build step for a project and run it in the sandbox."""

    def __init__(self, diagnostics: Optional[DiagnosticEngine] = None) -> None:
        self._diag = diagnostics or DiagnosticEngine()

    def run(
        self,
        adapter: Any,
        root: Path,
        project: Any,
        workdir: Path,
        *,
        language: str = "",
        limits: Any = None,
        cancel_event: Optional[Any] = None,
    ) -> BuildResult:
        prepared = adapter.build(root, project, workdir)
        if prepared is None:
            return BuildResult(
                success=True, exit_code=0, duration_ms=0, skipped=True,
                reason="there is nothing to build for this project",
            )
        return self._execute(prepared, language=language, limits=limits, cancel_event=cancel_event)

    def _execute(self, prepared: Any, *, language: str, limits: Any, cancel_event: Optional[Any]) -> BuildResult:
        env = sandbox.build_env(prepared.env or {})
        output_cap = getattr(limits, "max_stdout_bytes", 1_048_576) if limits else 1_048_576
        timeout_s = max(1, int((getattr(limits, "timeout_ms", 60_000) if limits else 60_000) // 1000))
        spec = sandbox.RunSpec(
            argv=list(prepared.argv), cwd=Path(prepared.cwd), env=env,
            timeout_s=timeout_s, output_cap_bytes=output_cap, network=bool(prepared.network),
            **(resource_run_kwargs(limits) if limits is not None else {}),
        )
        try:
            raw = sandbox.run(spec, cancel_event=cancel_event)
        except sandbox.SandboxUnavailable as exc:
            return BuildResult(
                success=False, exit_code=None, duration_ms=0,
                reason=str(exc.reason), backend="unavailable", command=list(prepared.argv),
            )
        errors = self._diag.normalize(raw.output, language=language, source="build")
        return BuildResult(
            success=(raw.exit_code == 0 and not raw.timed_out and not raw.cancelled),
            exit_code=raw.exit_code, duration_ms=raw.duration_ms,
            errors=errors, stdout=raw.output, stderr="",
            command=list(prepared.argv), backend=raw.backend,
            reason="timed out" if raw.timed_out else ("cancelled" if raw.cancelled else ""),
        )


# ── Dependency manager ───────────────────────────────────────────────────────


@dataclass
class DependencyPlan:
    """What a project needs, and whether it is already satisfied."""

    manager: str = ""
    lockfile: str = ""
    manifest: str = ""
    packages: list[str] = field(default_factory=list)
    install_command: list[str] = field(default_factory=list)
    satisfied: bool = False
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "manager": self.manager, "lockfile": self.lockfile, "manifest": self.manifest,
            "packages": self.packages, "installCommand": self.install_command,
            "satisfied": self.satisfied, "reason": self.reason,
        }


class DependencyManager:
    """Report dependency state and the (gated) install command. Never installs here."""

    def plan(self, root: Path, project: Any) -> DependencyPlan:
        manager = (getattr(project, "package_manager", "") or "").strip()
        lockfile = getattr(project, "lockfile", "") or ""
        if manager == "uv":
            return DependencyPlan(
                manager="uv", lockfile=lockfile, manifest="pyproject.toml",
                install_command=["uv", "sync"],
                satisfied=(root / ".venv").is_dir(),
                reason="uv sync" if not (root / ".venv").is_dir() else "already synced",
            )
        if manager in ("npm", "pnpm", "yarn", "bun"):
            installed = (root / "node_modules").is_dir()
            command = {
                "npm": ["npm", "install"], "pnpm": ["pnpm", "install"],
                "yarn": ["yarn", "install"], "bun": ["bun", "install"],
            }[manager]
            return DependencyPlan(
                manager=manager, lockfile=lockfile, manifest="package.json",
                install_command=command, satisfied=installed,
                reason="" if installed else f"{manager} install",
            )
        if manager in ("pip", "poetry", "pipenv"):
            command = {
                "pip": ["pip", "install", "-r", "requirements.txt"],
                "poetry": ["poetry", "install"],
                "pipenv": ["pipenv", "install"],
            }[manager]
            return DependencyPlan(
                manager=manager, lockfile=lockfile, manifest="requirements.txt",
                install_command=command, satisfied=False, reason=command[-1],
            )
        if manager == "cargo":
            return DependencyPlan(manager="cargo", lockfile=lockfile, manifest="Cargo.toml",
                                  install_command=["cargo", "fetch"], satisfied=(root / "target").is_dir())
        if manager == "go":
            return DependencyPlan(manager="go", lockfile=lockfile, manifest="go.mod",
                                  install_command=["go", "mod", "download"], satisfied=False)
        return DependencyPlan(reason="no dependency manifest Eclipse recognizes")


__all__ = ["BuildEngine", "BuildResult", "DependencyManager", "DependencyPlan"]
