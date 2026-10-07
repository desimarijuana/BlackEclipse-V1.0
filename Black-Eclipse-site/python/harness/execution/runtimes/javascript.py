"""The JavaScript (Node.js) runtime adapter."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from ..projects import ProjectInfo
from .base import BaseRuntime, PreparedCommand


class JavaScriptRuntime(BaseRuntime):
    language = "javascript"
    name = "JavaScriptRuntime"
    aliases = ("js", "node", "nodejs", "mjs")

    def available(self) -> bool:
        return bool(self._resolve_on_path("node", "node.exe"))

    def resolve(self, project: Optional[ProjectInfo]) -> str:
        return self._resolve_on_path("node", "node.exe")

    def _package_manager(self, project: Optional[ProjectInfo]) -> str:
        pm = (project.package_manager if project else "") or "npm"
        return pm if pm in ("npm", "pnpm", "yarn", "bun") else "npm"

    def _local_bin(self, root: Path, name: str) -> str:
        """A project-local `node_modules/.bin/<name>` when present."""
        for candidate in (
            root / "node_modules" / ".bin" / f"{name}.cmd",
            root / "node_modules" / ".bin" / name,
        ):
            if candidate.is_file():
                return str(candidate)
        return ""

    def _app_bin(self, name: str) -> str:
        """The app's own bundled `node_modules/.bin/<name>` (offline, no install)."""
        base = self._app_repo()
        if base is None:
            return ""
        return self._local_bin(base, name)

    def _runner_program(self, root: Path, name: str) -> str:
        """Resolve a JS test runner: project-local, then the app's bundled one.

        Falls back to an absolute `npx` only when neither is present, so a project
        with no `node_modules` still uses Eclipse's own toolchain OFFLINE rather
        than fetching a different version from the network.
        """
        return self._local_bin(root, name) or self._app_bin(name) or self._program("npx", "npx.cmd")

    def prepare_run(self, request: Any, root: Path, workdir: Path) -> PreparedCommand:
        node = self.resolve(None)
        if not node:
            from .base import RuntimeUnavailable  # noqa: PLC0415

            raise RuntimeUnavailable("Node.js isn't available on this computer.")
        if getattr(request, "code", ""):
            # `.mjs` permits top-level await + ESM import; CommonJS `require` still
            # works inside a `.mjs` only via createRequire, so prefer `.cjs` when the
            # code obviously uses `require`.
            code = str(request.code)
            ext = "cjs" if "require(" in code else "mjs"
            staged = self._stage(workdir, f"main.{ext}", code)
            argv = [node, str(staged), *list(getattr(request, "args", []) or [])]
            return PreparedCommand(argv=argv, cwd=workdir, env={}, description="node inline", cleanup=[workdir])
        entrypoint = getattr(request, "entrypoint", "") or "index.js"
        target = (root / entrypoint).resolve()
        argv = [node, str(target), *list(getattr(request, "args", []) or [])]
        return PreparedCommand(argv=argv, cwd=root, env=self._node_env(root), description=f"node {entrypoint}")

    def test(self, root: Path, project: Optional[ProjectInfo], test_policy: Optional[dict[str, Any]], workdir: Path) -> Optional[PreparedCommand]:
        node = self.resolve(project)
        if not node:
            return None
        policy = test_policy or {}
        framework = str(policy.get("framework") or "").strip()
        files = list(policy.get("files") or [])
        env = self._node_env(root)
        if framework in ("vitest", "jest", "mocha", "playwright", "cypress"):
            runner = {"vitest": "vitest", "jest": "jest", "mocha": "mocha"}.get(framework)
            if runner:
                program = self._runner_program(root, runner)
                # A machine-readable reporter so the engine can extract per-test
                # failures (name, file, expected/actual) — not just exit code.
                reporter = {
                    "vitest": ["--reporter=json"],
                    "jest": ["--json"],
                }.get(framework, [])
                argv = [program, *files] if framework == "mocha" else [program, "run", *reporter, *files]
                return PreparedCommand(argv=argv, cwd=root, env=env, description=framework)
            return self._npm_test(root, files, "npm test", env)
        if "test" in (project.scripts if project else {}):
            return self._npm_test(root, files, "npm test", env)
        return PreparedCommand(argv=[node, "--test", *files], cwd=root, env=env, description="node --test")

    def _npm_test(self, root: Path, files: list[str], description: str, env: dict[str, str]) -> PreparedCommand:
        npm = self._program("npm", "npm.cmd")
        return PreparedCommand(argv=[npm, "run", "test", "--", *files], cwd=root, env=env, description=description)

    def discover_tests(self, root: Path, project: Optional[ProjectInfo]) -> list[str]:
        found: list[str] = []
        for rel in self._iter_files(root, (".js", ".mjs", ".cjs", ".jsx"), limit=3000):
            name = Path(rel).name
            if ".test." in name or ".spec." in name or "__tests__" in f"/{rel}":
                found.append(rel)
        return found[:500]


__all__ = ["JavaScriptRuntime"]
