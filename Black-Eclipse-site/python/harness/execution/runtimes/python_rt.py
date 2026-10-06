"""The Python runtime adapter."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from ..projects import ProjectInfo
from .base import BaseRuntime, PreparedCommand


class PythonRuntime(BaseRuntime):
    language = "python"
    name = "PythonRuntime"
    aliases = ("py", "python3", "cpython")

    # Dependency manifests, in detection priority.
    MANIFESTS = ("requirements.txt", "pyproject.toml", "uv.lock", "poetry.lock", "Pipfile")

    def __init__(self, *, project_root: Optional[Path] = None) -> None:
        self._project_root = project_root

    def available(self) -> bool:
        return bool(self.resolve(None))

    def resolve(self, project: Optional[ProjectInfo]) -> str:
        """Prefer the repo's vendored interpreter (it has langgraph + pytest).

        `sys.executable` is next (the interpreter already running the harness),
        then `python3`/`python`/`py` on PATH. A bare `python` shim may lack deps,
        but that only affects what the user program can import, never isolation.
        """
        import sys

        vendored = self._resolve_vendored(project)
        if vendored:
            return vendored
        if sys.executable and Path(sys.executable).is_file():
            return sys.executable
        return self._resolve_on_path("python3", "python", "py")

    def prepare_run(self, request: Any, root: Path, workdir: Path) -> PreparedCommand:
        interpreter = self.resolve(None)
        if not interpreter:
            from .base import RuntimeUnavailable  # noqa: PLC0415

            raise RuntimeUnavailable("Python isn't available on this computer.")
        if getattr(request, "code", ""):
            staged = self._stage(workdir, "main.py", request.code)
            argv = [interpreter, str(staged), *list(getattr(request, "args", []) or [])]
            return PreparedCommand(argv=argv, cwd=workdir, env={"PYTHONPATH": str(workdir)}, description="python inline", cleanup=[workdir])
        entrypoint = getattr(request, "entrypoint", "") or "main.py"
        target = (root / entrypoint).resolve()
        argv = [interpreter, str(target), *list(getattr(request, "args", []) or [])]
        return PreparedCommand(argv=argv, cwd=root, env={"PYTHONPATH": str(root)}, description=f"python {entrypoint}")

    def build(self, root: Path, project: Optional[ProjectInfo], workdir: Path) -> Optional[PreparedCommand]:
        """Python has no compile step, but `python -m py_compile` validates syntax."""
        interpreter = self.resolve(project)
        if not interpreter:
            return None
        py_files = list(self._iter_files(root, (".py",), limit=200))
        if not py_files:
            return None
        argv = [interpreter, "-m", "compileall", "-q", *py_files[:50]]
        return PreparedCommand(argv=argv, cwd=root, env={"PYTHONPATH": str(root)}, description="python compileall")

    def test(self, root: Path, project: Optional[ProjectInfo], test_policy: Optional[dict[str, Any]], workdir: Path) -> Optional[PreparedCommand]:
        interpreter = self.resolve(project)
        if not interpreter:
            return None
        policy = test_policy or {}
        framework = str(policy.get("framework") or "").strip()
        files = list(policy.get("files") or [])
        if framework == "unittest":
            argv = [interpreter, "-m", "unittest", "discover", "-v", *files]
            return PreparedCommand(argv=argv, cwd=root, env={"PYTHONPATH": str(root)}, description="python unittest")
        # Default to pytest (the harness's own choice); it is discovered by import.
        argv = [interpreter, "-m", "pytest", "-q", *files]
        return PreparedCommand(argv=argv, cwd=root, env={"PYTHONPATH": str(root)}, description="python pytest")

    def discover_tests(self, root: Path, project: Optional[ProjectInfo]) -> list[str]:
        found: list[str] = []
        for rel in self._iter_files(root, (".py",), limit=2000):
            name = Path(rel).name
            if name.startswith("test_") or name.endswith("_test.py") or "/tests/" in f"/{rel}":
                found.append(rel)
        return found[:500]


__all__ = ["PythonRuntime"]
