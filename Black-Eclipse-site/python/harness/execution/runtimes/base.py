"""Runtime adapter contract + registry.

The orchestrator never hardcodes language behaviour: it resolves a *language* to
a `RuntimeAdapter`, asks that adapter to prepare an argv, and runs it through the
ONE sandbox. Adding Java/Go/Rust/C/C++/C#/PHP/Ruby later means adding an adapter
and registering it — no orchestrator change.

An adapter may stage an inline program into a private working directory (outside
the workspace, like the analysis sandbox) and returns the exact argv, cwd, env
and cleanup paths. It does NOT execute anything; execution is the orchestrator's
job through `code/sandbox.py`.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional, Protocol, runtime_checkable

from ..projects import ProjectInfo


class RuntimeUnavailable(RuntimeError):
    """A runtime cannot run, honestly. Never a silent fallback to host."""

    def __init__(self, reason: str, *, code: str = "RUNTIME_UNAVAILABLE") -> None:
        super().__init__(reason)
        self.code = code
        self.reason = reason


@dataclass
class PreparedCommand:
    """An argv ready for the sandbox, plus the temp paths to clean up."""

    argv: list[str]
    cwd: Path
    env: dict[str, str]
    description: str = ""
    cleanup: list[Path] = field(default_factory=list)
    network: bool = False


@runtime_checkable
class RuntimeAdapter(Protocol):
    """The interface every language runtime implements."""

    language: str
    name: str
    aliases: tuple[str, ...]

    def detect(self, project: Optional[ProjectInfo]) -> bool:
        """Whether this runtime fits the detected project."""
        ...

    def available(self) -> bool:
        """Whether the interpreter/toolchain is present on this machine."""
        ...

    def resolve(self, project: Optional[ProjectInfo]) -> str:
        """The absolute interpreter path, or "" when unavailable."""
        ...

    def prepare_run(self, request: Any, root: Path, workdir: Path) -> PreparedCommand:
        """Build the argv to RUN the request (inline code or an entrypoint)."""
        ...

    def build(self, root: Path, project: Optional[ProjectInfo], workdir: Path) -> Optional[PreparedCommand]:
        """Build the project, or None when there is nothing to build."""
        ...

    def test(
        self, root: Path, project: Optional[ProjectInfo], test_policy: Optional[dict[str, Any]], workdir: Path
    ) -> Optional[PreparedCommand]:
        """The argv to run the project's tests, or None when undetectable."""
        ...

    def discover_tests(self, root: Path, project: Optional[ProjectInfo]) -> list[str]:
        """Workspace-relative test file paths (bounded)."""
        ...


class BaseRuntime:
    """Shared helpers for the concrete adapters."""

    language = ""
    name = ""
    aliases: tuple[str, ...] = ()
    is_shell = False

    def detect(self, project: Optional[ProjectInfo]) -> bool:
        if project is None:
            return False
        return self.language in (project.languages or []) or project.primary_language == self.language

    def available(self) -> bool:  # pragma: no cover - overridden
        return False

    def resolve(self, project: Optional[ProjectInfo]) -> str:  # pragma: no cover - overridden
        return ""

    def build(self, root, project, workdir):
        return None

    def test(self, root, project, test_policy, workdir):
        return None

    def discover_tests(self, root, project):
        return []

    # ── helpers ─────────────────────────────────────────────────────────────
    def _resolve_on_path(self, *names: str) -> str:
        import shutil

        for candidate in names:
            found = shutil.which(candidate)
            if found:
                return found
        return ""

    def _require_program(self, *names: str) -> str:
        """Resolve a REQUIRED tool to an absolute path, or raise an honest refusal.

        Every argv the adapters produce must START with an absolute executable
        path: on Windows `npm`/`npx`/`tsc` are `.cmd` shims that `subprocess`
        cannot spawn by bare name (`FileNotFoundError [WinError 2]`). This is the
        same resolution the production command broker (`code/commands.py`) uses,
        so both execution paths agree.
        """
        found = self._resolve_on_path(*names)
        if not found:
            from .base import RuntimeUnavailable  # noqa: PLC0415

            raise RuntimeUnavailable(
                f"{names[0]} isn't installed on this computer.",
                code="EXECUTABLE_MISSING",
            )
        return found

    def _program(self, *names: str) -> str:
        """Resolve a program to an absolute path, falling back to the bare name.

        Used for OPTIONAL helpers (a package manager in a build/test template):
        an absolute path when present (so Windows can spawn it), otherwise the
        bare name so the platform's own shell semantics still apply.
        """
        return self._resolve_on_path(*names) or names[0]

    def _app_repo(self) -> Optional[Path]:
        """The app repository root, or None (for app-bundled binaries)."""
        try:
            from ...eclipse_memory.config import repo_root  # noqa: PLC0415

            base = Path(repo_root())
            return base if base.is_dir() else None
        except Exception:  # noqa: BLE001
            return None

    def _node_bin_dirs(self, root: Path) -> list[str]:
        """`node_modules/.bin` directories a js/ts child should search.

        Order: the project's own first, then the app's bundled one. This is what
        lets `npm run build` (a project's `tsc --noEmit`) and a local test runner
        resolve WITHOUT a network install when the project has not been
        `npm install`-ed but Eclipse ships the toolchain.
        """
        dirs: list[str] = []
        local = root / "node_modules" / ".bin"
        if local.is_dir():
            dirs.append(str(local))
        app = self._app_repo()
        if app is not None:
            app_bin = app / "node_modules" / ".bin"
            if app_bin.is_dir() and str(app_bin) not in dirs:
                dirs.append(str(app_bin))
        return dirs

    def _node_env(self, root: Path, extra: Optional[dict[str, str]] = None) -> dict[str, str]:
        """A child environment with the node bin dirs PREPENDED to PATH.

        `sandbox.build_env` already scrubs everything else; here we only extend the
        inherited PATH so a `.bin` shim is found. The separator is the platform's.
        """
        env = dict(extra or {})
        dirs = self._node_bin_dirs(root)
        if dirs:
            import os

            inherited = os.environ.get("PATH", "")
            env["PATH"] = os.pathsep.join(dirs + ([inherited] if inherited else []))
        return env

    def _tool_cache(self, name: str) -> Path:
        """A stable, writable cache directory for a toolchain (outside the repo).

        The sandbox scrubs the environment, so a toolchain that needs a cache/home
        (Go's GOCACHE, .NET's CLI home + NuGet packages) must be TOLD where to put
        it. `/tmp` under the OS temp dir, created on demand — never a secret, never
        inside the workspace.
        """
        import tempfile

        base = Path(tempfile.gettempdir()) / "eclipse-toolcache" / name
        base.mkdir(parents=True, exist_ok=True)
        return base

    # Non-secret Windows location/metadata variables a native toolchain (the .NET
    # SDK, MSVC, NuGet) reads to resolve its own install/package directories. They
    # are the Windows analogue of PATH — names and paths, never credentials — and
    # are the ONLY host variables an adapter may re-add beyond the sandbox
    # allowlist. Passing them does not widen the security boundary the way
    # forwarding `*TOKEN*`/`*KEY*`/`.env` values would.
    _WINDOWS_PLATFORM_ENV = (
        "PROGRAMFILES", "PROGRAMFILES(X86)", "PROGRAMW6432",
        "COMMONPROGRAMFILES", "COMMONPROGRAMFILES(X86)", "COMMONPROGRAMW6432",
        "PROGRAMDATA", "ALLUSERSPROFILE", "PUBLIC", "WINDIR", "SYSTEMDRIVE",
        "COMSPEC", "USERPROFILE", "HOMEDRIVE", "HOMEPATH", "USERNAME",
        "USERDOMAIN", "USERDOMAIN_ROAMINGPROFILE", "NUMBER_OF_PROCESSORS",
        "PROCESSOR_ARCHITECTURE", "OS", "APPDATA", "LOCALAPPDATA",
    )

    def _platform_env(self) -> dict[str, str]:
        """The curated non-secret platform variables, forwarded from the host."""
        import os

        if os.name != "nt":
            return {}
        return {k: os.environ[k] for k in self._WINDOWS_PLATFORM_ENV if k in os.environ}

    def _resolve_vendored(self, project: Optional[ProjectInfo]) -> str:
        """The vendored Python the repo ships (scripts/vendor), else ""."""
        try:
            from ...eclipse_memory.config import repo_root  # noqa: PLC0415

            base = Path(repo_root())
        except Exception:  # noqa: BLE001
            return ""
        candidates = [
            base / "scripts" / "vendor" / "python" / "python.exe",
            base / "scripts" / "vendor" / "python" / "bin" / "python3",
        ]
        for candidate in candidates:
            if candidate.is_file():
                return str(candidate)
        return ""

    def _stage(self, workdir: Path, filename: str, content: str) -> Path:
        workdir.mkdir(parents=True, exist_ok=True)
        target = workdir / filename
        target.write_text(content, encoding="utf-8")
        return target

    def _iter_files(self, root: Path, suffixes: tuple[str, ...], *, limit: int = 500):
        """Bounded walk that skips the policy's ignored directories."""
        from ...code import policy  # noqa: PLC0415

        count = 0
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in policy.IGNORED_DIRS]
            for name in filenames:
                if Path(name).suffix.casefold() not in suffixes:
                    continue
                yield (Path(dirpath) / name).relative_to(root).as_posix()
                count += 1
                if count >= limit:
                    return


class RuntimeRegistry:
    """The process-wide table of language runtimes. Language ids are canonical."""

    def __init__(self) -> None:
        self._by_language: dict[str, RuntimeAdapter] = {}
        self._by_alias: dict[str, str] = {}

    def register(self, adapter: RuntimeAdapter) -> None:
        language = str(adapter.language).casefold()
        self._by_language[language] = adapter
        for alias in (adapter.language, *adapter.aliases):
            self._by_alias[str(alias).casefold()] = language

    def get(self, language: str) -> Optional[RuntimeAdapter]:
        key = str(language or "").casefold()
        canonical = self._by_alias.get(key, key)
        return self._by_language.get(canonical)

    def languages(self) -> list[str]:
        return sorted(self._by_language.keys())

    def describe(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for adapter in self._by_language.values():
            out.append(
                {
                    "language": adapter.language,
                    "name": adapter.name,
                    "available": bool(adapter.available()),
                }
            )
        return out

    def resolve_language(self, **kwargs: Any) -> str:
        from ..projects import detect_language  # noqa: PLC0415

        return detect_language(**kwargs)


__all__ = [
    "BaseRuntime",
    "PreparedCommand",
    "RuntimeAdapter",
    "RuntimeRegistry",
    "RuntimeUnavailable",
]
