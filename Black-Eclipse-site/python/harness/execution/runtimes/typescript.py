"""The TypeScript runtime adapter.

TypeScript is executed through the project's DECLARED strategy where possible:
a `tsx`/`ts-node` dev dependency, or a `start`/`dev` npm script. Only when the
project declares none of these does it fall back to `npx tsx`/`npx ts-node`.
The build step prefers the project's own `build` script, then the project's
`tsc` with its own `tsconfig.json`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from ..projects import ProjectInfo, read_json
from .base import BaseRuntime, PreparedCommand


class TypeScriptRuntime(BaseRuntime):
    language = "typescript"
    name = "TypeScriptRuntime"
    aliases = ("ts", "tsx", "ts-node")

    def available(self) -> bool:
        return bool(self._node())

    def _node(self) -> str:
        return self._resolve_on_path("node", "node.exe")

    def _local_bin(self, root: Path, name: str) -> str:
        """A project-local `node_modules/.bin/<name>` when present."""
        for candidate in (
            root / "node_modules" / ".bin" / f"{name}.cmd",
            root / "node_modules" / ".bin" / name,
        ):
            if candidate.is_file():
                return str(candidate)
        return ""

    def _deps(self, root: Path) -> dict[str, str]:
        data = read_json(root / "package.json")
        return {**data.get("dependencies", {}), **data.get("devDependencies", {})}

    def _scripts(self, root: Path) -> dict[str, str]:
        data = read_json(root / "package.json")
        return {str(k): str(v) for k, v in (data.get("scripts") or {}).items()}

    def resolve(self, project: Optional[ProjectInfo]) -> str:
        root = Path(project.root) if project else Path.cwd()
        return self._local_bin(root, "tsc") or self._resolve_on_path("tsc") or self._node()

    def _app_bin(self, name: str) -> str:
        """A `<app repo>/node_modules/.bin/<name>` binary, shipped with Eclipse.

        The harness itself depends on `tsx`, so its own `node_modules` is a
        legitimate, OFFLINE source of a TS runner for a project that declares none.
        Resolved against the app repo (never the workspace) and only when present.
        """
        try:
            from ...eclipse_memory.config import repo_root  # noqa: PLC0415

            base = Path(repo_root())
        except Exception:  # noqa: BLE001
            return ""
        return self._local_bin(base, name)

    def _runner_prefix(self, root: Path) -> list[str]:
        """The leading argv used to run a `.ts` file, in priority order.

        The project's DECLARED strategy wins: a project-local `tsx`, then a declared
        `tsx` dependency, then the app's own bundled `tsx`; then the same for
        `ts-node`; finally `npx tsx` (which may fetch it). The `npx` fallback is
        resolved to an absolute path because Windows cannot spawn a bare `npx`.
        """
        if local := self._local_bin(root, "tsx"):
            return [local]
        if "tsx" in self._deps(root):
            return [self._program("npx", "npx.cmd"), "tsx"]
        if app := self._app_bin("tsx"):
            return [app]
        if local := self._local_bin(root, "ts-node"):
            return [local, "--no-warnings"]
        if "ts-node" in self._deps(root):
            return [self._program("npx", "npx.cmd"), "ts-node"]
        if app := self._app_bin("ts-node"):
            return [app, "--no-warnings"]
        return [self._program("npx", "npx.cmd"), "tsx"]

    def prepare_run(self, request: Any, root: Path, workdir: Path) -> PreparedCommand:
        if not self._node():
            from .base import RuntimeUnavailable  # noqa: PLC0415

            raise RuntimeUnavailable("Node.js isn't available on this computer.")
        scripts = self._scripts(root)
        prefix = self._runner_prefix(root)
        if getattr(request, "code", ""):
            staged = self._stage(workdir, "main.ts", request.code)
            argv = [*prefix, str(staged), *list(getattr(request, "args", []) or [])]
            return PreparedCommand(argv=argv, cwd=workdir, env=self._node_env(workdir), description="typescript inline", cleanup=[workdir])
        entrypoint = getattr(request, "entrypoint", "")
        if not entrypoint:
            # Prefer a declared run script (start/dev) — the project's own strategy.
            for script in ("start", "dev", "serve"):
                if script in scripts:
                    npm = self._require_program("npm", "npm.cmd")
                    return PreparedCommand(argv=[npm, "run", script], cwd=root, env=self._node_env(root), description=f"npm run {script}")
            entrypoint = "src/index.ts"
        target = (root / entrypoint).resolve()
        argv = [*prefix, str(target), *list(getattr(request, "args", []) or [])]
        return PreparedCommand(argv=argv, cwd=root, env=self._node_env(root), description=f"typescript {entrypoint}")

    def build(self, root: Path, project: Optional[ProjectInfo], workdir: Path) -> Optional[PreparedCommand]:
        scripts = self._scripts(root)
        env = self._node_env(root)
        # Prefer the project's declared build strategy.
        if "build" in scripts:
            npm = self._program("npm", "npm.cmd")
            return PreparedCommand(argv=[npm, "run", "build"], cwd=root, env=env, description="npm run build")
        tsc = self._local_bin(root, "tsc") or self._app_bin("tsc") or self._resolve_on_path("tsc", "tsc.cmd")
        if not tsc:
            return None
        if (root / "tsconfig.json").is_file():
            return PreparedCommand(argv=[tsc, "-p", "tsconfig.json", "--noEmit"], cwd=root, env=env, description="tsc --noEmit")
        return PreparedCommand(argv=[tsc, "--noEmit"], cwd=root, env=env, description="tsc --noEmit")

    def test(self, root: Path, project: Optional[ProjectInfo], test_policy: Optional[dict[str, Any]], workdir: Path) -> Optional[PreparedCommand]:
        # Delegate to the JavaScript test resolution (same package ecosystem).
        from .javascript import JavaScriptRuntime  # noqa: PLC0415

        return JavaScriptRuntime().test(root, project, test_policy, workdir)

    def discover_tests(self, root: Path, project: Optional[ProjectInfo]) -> list[str]:
        found: list[str] = []
        for rel in self._iter_files(root, (".ts", ".tsx", ".js", ".jsx"), limit=3000):
            name = Path(rel).name
            if ".test." in name or ".spec." in name or "__tests__" in f"/{rel}":
                found.append(rel)
        return found[:500]


__all__ = ["TypeScriptRuntime"]
