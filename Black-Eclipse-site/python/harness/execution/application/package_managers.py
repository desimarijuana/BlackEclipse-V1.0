"""Package manager adapters — one abstraction, every ecosystem.

Every adapter answers the same questions (detect / available / version) and, when
it declares the capability, builds a structured argv for install/build/test/… The
ADAPTER decides the argv; the agent layer never hard-codes a shell command. Each
argv is a list whose FIRST token is an absolute, resolved executable path (never a
bare `npm`/`npx`, which Windows cannot spawn), and it is executed through the ONE
sandbox primitive (`code/sandbox.py`) with the scrubbed environment — no shell,
no string concatenation, no injection surface.

Safety: an adapter never silently falls back to another manager. If a project's
lockfile names pnpm but pnpm is absent, `available()` is False and the refusal is
honest ("pnpm is unavailable"), never a quiet switch to npm.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from ...code import sandbox
from ..models import ResourceLimits, resource_run_kwargs
from .models import ApplicationDescriptor
from .registry import (
    CAP_AUDIT,
    CAP_BUILD,
    CAP_DETECT,
    CAP_INSTALL,
    CAP_INSTALL_PACKAGE,
    CAP_LINT,
    CAP_LIST_DEPENDENCIES,
    CAP_REMOVE_PACKAGE,
    CAP_RUN_SCRIPT,
    CAP_TEST,
    CAP_UPDATE_PACKAGE,
    CAP_VERSION,
)


def _resolve(*names: str) -> str:
    """Resolve the first present executable to an absolute path, or ""."""
    import shutil

    for name in names:
        found = shutil.which(name)
        if found:
            return found
    return ""


@dataclass
class CommandResult:
    """One executed package-manager command."""

    ok: bool = False
    code: str = "OK"
    exit_code: Optional[int] = None
    argv: list[str] = field(default_factory=list)
    output: str = ""
    duration_ms: int = 0
    timed_out: bool = False
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok, "code": self.code, "exitCode": self.exit_code,
            "argv": list(self.argv), "durationMs": self.duration_ms,
            "timedOut": self.timed_out, "reason": self.reason,
        }


class BasePackageManager:
    """Shared behaviour: executable resolution, argv building, sandbox execution."""

    kind = "package"
    name = ""
    language = ""
    aliases: tuple[str, ...] = ()
    capabilities: frozenset[str] = frozenset()
    #: (lockfile names, manifest names) that make this the project's manager.
    lockfiles: tuple[str, ...] = ()
    manifests: tuple[str, ...] = ()
    #: (executables) candidates, in preference order.
    executables: tuple[str, ...] = ()

    # ── contract ─────────────────────────────────────────────────────────────
    def detect(self, root: Path, descriptor: ApplicationDescriptor) -> bool:
        root = Path(root)
        if descriptor.package_manager and descriptor.package_manager.casefold() == self.name.casefold():
            return True
        if descriptor.lockfile and descriptor.lockfile.casefold() in {n.casefold() for n in self.lockfiles}:
            return True
        return any((root / m).is_file() for m in self.manifests)

    def available(self) -> bool:
        return bool(self._exe())

    def version(self) -> str:
        exe = self._exe()
        if not exe:
            return ""
        result = self._run([exe, "--version"], cwd=Path.cwd(), timeout_s=10)
        return _first_line(result.output)

    def _exe(self) -> str:
        return _resolve(*self.executables) if self.executables else ""

    # ── command builders ─────────────────────────────────────────────────────
    def install_dependencies(self, root: Path) -> list[str]:
        raise NotImplementedError

    def install_package(self, root: Path, packages: list[str]) -> list[str]:
        raise NotImplementedError

    def remove_package(self, root: Path, packages: list[str]) -> list[str]:
        raise NotImplementedError

    def update_package(self, root: Path, packages: list[str]) -> list[str]:
        raise NotImplementedError

    def list_dependencies(self, root: Path) -> list[str]:
        return []

    def run_script(self, root: Path, script: str, args: Optional[list[str]] = None) -> list[str]:
        raise NotImplementedError

    def build(self, root: Path) -> list[str]:
        return self.run_script(root, "build")

    def test(self, root: Path) -> list[str]:
        return self.run_script(root, "test")

    def lint(self, root: Path) -> list[str]:
        return self.run_script(root, "lint")

    def audit(self, root: Path) -> list[str]:
        return []

    # ── execution ─────────────────────────────────────────────────────────────
    def run(
        self,
        argv: list[str],
        *,
        cwd: Path,
        limits: Optional[ResourceLimits] = None,
        env: Optional[dict[str, str]] = None,
    ) -> CommandResult:
        """Run a built argv through the ONE sandbox. Never a shell."""
        if not argv:
            return CommandResult(ok=False, code="NO_COMMAND", reason="nothing to run")
        limits = limits or ResourceLimits.from_env()
        from ...code import sandbox as _sandbox

        child_env = _sandbox.build_env(self._child_env(cwd, env))
        spec = _sandbox.RunSpec(
            argv=list(argv), cwd=Path(cwd), env=child_env,
            timeout_s=max(1, int(limits.timeout_ms // 1000)),
            output_cap_bytes=limits.max_stdout_bytes, network=False,
            **resource_run_kwargs(limits),
        )
        try:
            raw = _sandbox.run(spec)
        except _sandbox.SandboxUnavailable as exc:
            return CommandResult(ok=False, code="SANDBOX_UNAVAILABLE", reason=str(exc.reason), argv=list(argv))
        return CommandResult(
            ok=(raw.exit_code == 0 and not raw.timed_out and not raw.cancelled),
            exit_code=raw.exit_code, argv=list(argv), output=raw.output,
            duration_ms=raw.duration_ms, timed_out=raw.timed_out,
        )

    def _run(self, argv: list[str], *, cwd: Path, timeout_s: int = 10) -> CommandResult:
        from ...code import sandbox as _sandbox

        try:
            raw = _sandbox.run(_sandbox.RunSpec(
                argv=list(argv), cwd=Path(cwd), env=_sandbox.build_env(),
                timeout_s=timeout_s, output_cap_bytes=64_000, network=False,
            ))
        except _sandbox.SandboxUnavailable as exc:
            return CommandResult(ok=False, code="SANDBOX_UNAVAILABLE", reason=str(exc.reason))
        return CommandResult(ok=(raw.exit_code == 0), exit_code=raw.exit_code, output=raw.output)

    def _child_env(self, cwd: Path, extra: Optional[dict[str, str]]) -> dict[str, str]:
        return dict(extra or {})

    def describe(self) -> dict[str, Any]:
        return {
            "name": self.name, "language": self.language,
            "available": self.available(), "version": self.version(),
            "capabilities": sorted(self.capabilities),
        }


# ── Node managers ───────────────────────────────────────────────────────────────


class NpmManager(BasePackageManager):
    name = "npm"
    language = "javascript"
    aliases = ("npm",)
    executables = ("npm",)
    lockfiles = ("package-lock.json",)
    manifests = ("package.json",)
    capabilities = frozenset({CAP_DETECT, CAP_VERSION, CAP_INSTALL, CAP_INSTALL_PACKAGE, CAP_REMOVE_PACKAGE, CAP_UPDATE_PACKAGE, CAP_LIST_DEPENDENCIES, CAP_RUN_SCRIPT, CAP_BUILD, CAP_TEST, CAP_LINT, CAP_AUDIT})

    def install_dependencies(self, root: Path) -> list[str]:
        return [self._exe(), "install", "--no-audit", "--no-fund"]

    def install_package(self, root: Path, packages: list[str]) -> list[str]:
        return [self._exe(), "install", "--no-save", "--ignore-scripts", *packages]

    def remove_package(self, root: Path, packages: list[str]) -> list[str]:
        return [self._exe(), "uninstall", *packages]

    def update_package(self, root: Path, packages: list[str]) -> list[str]:
        return [self._exe(), "update", *packages]

    def list_dependencies(self, root: Path) -> list[str]:
        return [self._exe(), "ls", "--depth=0", "--json"]

    def run_script(self, root: Path, script: str, args: Optional[list[str]] = None) -> list[str]:
        base = [self._exe(), "run", script]
        if args:
            base += ["--", *args]
        return base

    def audit(self, root: Path) -> list[str]:
        return [self._exe(), "audit", "--json"]


class PnpmManager(NpmManager):
    name = "pnpm"
    aliases = ("pnpm",)
    executables = ("pnpm",)
    lockfiles = ("pnpm-lock.yaml",)

    def install_dependencies(self, root: Path) -> list[str]:
        return [self._exe(), "install", "--frozen-lockfile", "--ignore-scripts"]

    def build(self, root: Path) -> list[str]:
        return [self._exe(), "run", "build"]


class YarnManager(NpmManager):
    name = "yarn"
    aliases = ("yarn",)
    executables = ("yarn",)
    lockfiles = ("yarn.lock",)

    def install_dependencies(self, root: Path) -> list[str]:
        return [self._exe(), "install", "--ignore-scripts"]


class BunManager(NpmManager):
    name = "bun"
    aliases = ("bun",)
    executables = ("bun",)
    lockfiles = ("bun.lockb", "bun.lock")

    def install_dependencies(self, root: Path) -> list[str]:
        return [self._exe(), "install", "--ignore-scripts"]


# ── Python managers ─────────────────────────────────────────────────────────────


class PipManager(BasePackageManager):
    name = "pip"
    language = "python"
    aliases = ("pip", "pip3")
    executables = ("pip", "pip3")
    lockfiles = ()
    manifests = ("requirements.txt",)
    capabilities = frozenset({CAP_DETECT, CAP_VERSION, CAP_INSTALL, CAP_INSTALL_PACKAGE, CAP_REMOVE_PACKAGE, CAP_UPDATE_PACKAGE, CAP_LIST_DEPENDENCIES, CAP_RUN_SCRIPT})

    def install_dependencies(self, root: Path) -> list[str]:
        req = Path(root) / "requirements.txt"
        if req.is_file():
            return [self._exe(), "install", "-r", "requirements.txt"]
        return [self._exe(), "install", "."]

    def install_package(self, root: Path, packages: list[str]) -> list[str]:
        return [self._exe(), "install", *packages]

    def remove_package(self, root: Path, packages: list[str]) -> list[str]:
        return [self._exe(), "uninstall", "-y", *packages]

    def update_package(self, root: Path, packages: list[str]) -> list[str]:
        return [self._exe(), "install", "--upgrade", *packages]

    def list_dependencies(self, root: Path) -> list[str]:
        return [self._exe(), "list", "--format=freeze"]

    def run_script(self, root: Path, script: str, args: Optional[list[str]] = None) -> list[str]:
        py = _resolve("python", "python3")
        if script in ("test", "pytest"):
            return [py, "-m", "pytest", *(args or [])]
        return [py, "-m", script, *(args or [])]


class UvManager(BasePackageManager):
    name = "uv"
    language = "python"
    aliases = ("uv",)
    executables = ("uv",)
    lockfiles = ("uv.lock",)
    manifests = ("pyproject.toml",)
    capabilities = frozenset({CAP_DETECT, CAP_VERSION, CAP_INSTALL, CAP_INSTALL_PACKAGE, CAP_REMOVE_PACKAGE, CAP_LIST_DEPENDENCIES, CAP_RUN_SCRIPT, CAP_TEST})

    def install_dependencies(self, root: Path) -> list[str]:
        return [self._exe(), "sync"]

    def install_package(self, root: Path, packages: list[str]) -> list[str]:
        return [self._exe(), "add", *packages]

    def remove_package(self, root: Path, packages: list[str]) -> list[str]:
        return [self._exe(), "remove", *packages]

    def update_package(self, root: Path, packages: list[str]) -> list[str]:
        return [self._exe(), "add", "--upgrade", *packages]

    def list_dependencies(self, root: Path) -> list[str]:
        return [self._exe(), "pip", "list"]

    def run_script(self, root: Path, script: str, args: Optional[list[str]] = None) -> list[str]:
        return [self._exe(), "run", script, *(args or [])]

    def test(self, root: Path) -> list[str]:
        return [self._exe(), "run", "pytest"]


class PoetryManager(BasePackageManager):
    name = "poetry"
    language = "python"
    aliases = ("poetry",)
    executables = ("poetry",)
    lockfiles = ("poetry.lock",)
    manifests = ("pyproject.toml",)
    capabilities = frozenset({CAP_DETECT, CAP_VERSION, CAP_INSTALL, CAP_INSTALL_PACKAGE, CAP_REMOVE_PACKAGE, CAP_RUN_SCRIPT, CAP_TEST})

    def install_dependencies(self, root: Path) -> list[str]:
        return [self._exe(), "install"]

    def install_package(self, root: Path, packages: list[str]) -> list[str]:
        return [self._exe(), "add", *packages]

    def remove_package(self, root: Path, packages: list[str]) -> list[str]:
        return [self._exe(), "remove", *packages]

    def run_script(self, root: Path, script: str, args: Optional[list[str]] = None) -> list[str]:
        return [self._exe(), "run", script, *(args or [])]


# ── Systems ─────────────────────────────────────────────────────────────────────


class CargoManager(BasePackageManager):
    name = "cargo"
    language = "rust"
    aliases = ("cargo",)
    executables = ("cargo",)
    lockfiles = ("Cargo.lock",)
    manifests = ("Cargo.toml",)
    capabilities = frozenset({CAP_DETECT, CAP_VERSION, CAP_INSTALL, CAP_LIST_DEPENDENCIES, CAP_RUN_SCRIPT, CAP_BUILD, CAP_TEST})

    def install_dependencies(self, root: Path) -> list[str]:
        return [self._exe(), "fetch"]

    def list_dependencies(self, root: Path) -> list[str]:
        return [self._exe(), "metadata", "--format-version", "1", "--no-deps"]

    def run_script(self, root: Path, script: str, args: Optional[list[str]] = None) -> list[str]:
        return [self._exe(), script, *(args or [])]

    def build(self, root: Path) -> list[str]:
        return [self._exe(), "build"]

    def test(self, root: Path) -> list[str]:
        return [self._exe(), "test"]


class GoManager(BasePackageManager):
    name = "go"
    language = "go"
    aliases = ("go",)
    executables = ("go",)
    lockfiles = ("go.sum",)
    manifests = ("go.mod",)
    capabilities = frozenset({CAP_DETECT, CAP_VERSION, CAP_INSTALL, CAP_LIST_DEPENDENCIES, CAP_BUILD, CAP_TEST})

    def install_dependencies(self, root: Path) -> list[str]:
        return [self._exe(), "mod", "download"]

    def list_dependencies(self, root: Path) -> list[str]:
        return [self._exe(), "list", "-m", "all"]

    def build(self, root: Path) -> list[str]:
        return [self._exe(), "build", "./..."]

    def test(self, root: Path) -> list[str]:
        return [self._exe(), "test", "./..."]


# ── JVM ─────────────────────────────────────────────────────────────────────────


class MavenManager(BasePackageManager):
    name = "maven"
    language = "java"
    aliases = ("maven", "mvn")
    executables = ("mvn",)
    lockfiles = ()
    manifests = ("pom.xml",)
    capabilities = frozenset({CAP_DETECT, CAP_VERSION, CAP_INSTALL, CAP_BUILD, CAP_TEST})

    def install_dependencies(self, root: Path) -> list[str]:
        return [self._exe(), "dependency:resolve"]

    def build(self, root: Path) -> list[str]:
        return [self._exe(), "package", "-DskipTests"]

    def test(self, root: Path) -> list[str]:
        return [self._exe(), "test"]


class GradleManager(BasePackageManager):
    name = "gradle"
    language = "java"
    aliases = ("gradle",)
    executables = ("gradle",)
    lockfiles = ()
    manifests = ("build.gradle", "build.gradle.kts")
    capabilities = frozenset({CAP_DETECT, CAP_VERSION, CAP_BUILD, CAP_TEST})

    def install_dependencies(self, root: Path) -> list[str]:
        return [self._exe(), "dependencies"]

    def build(self, root: Path) -> list[str]:
        return [self._exe(), "build", "-x", "test"]

    def test(self, root: Path) -> list[str]:
        return [self._exe(), "test"]


def _first_line(text: str) -> str:
    for line in (text or "").splitlines():
        line = line.strip()
        if line:
            return line[:120]
    return ""


def build_package_manager_registry() -> Any:
    """Register every shipped package-manager adapter."""
    from .registry import PackageManagerRegistry

    registry = PackageManagerRegistry()
    for adapter in (
        NpmManager(), PnpmManager(), YarnManager(), BunManager(),
        PipManager(), UvManager(), PoetryManager(),
        CargoManager(), GoManager(), MavenManager(), GradleManager(),
    ):
        registry.register(adapter)
    return registry


__all__ = [
    "BasePackageManager",
    "BunManager",
    "CargoManager",
    "CommandResult",
    "GoManager",
    "GradleManager",
    "MavenManager",
    "NpmManager",
    "PipManager",
    "PnpmManager",
    "PoetryManager",
    "UvManager",
    "YarnManager",
    "build_package_manager_registry",
]
