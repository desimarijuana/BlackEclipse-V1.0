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
