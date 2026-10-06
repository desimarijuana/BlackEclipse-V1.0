"""The TypeScript runtime adapter.

TypeScript is executed through the project's DECLARED strategy where possible:
a `tsx`/`ts-node` dev dependency, or a `start`/`dev` npm script. Only when the
project declares none of these does it fall back to `npx tsx`/`npx ts-node`.
The build step prefers the project's own `build` script, then the project's
`tsc` with its own `tsconfig.json`.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from ..projects import ProjectInfo
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
        package = root / "package.json"
        try:
            data = json.loads(package.read_text(encoding="utf-8")) if package.is_file() else {}
        except (OSError, json.JSONDecodeError):
            return {}
        return {**data.get("dependencies", {}), **data.get("devDependencies", {})}

    def _scripts(self, root: Path) -> dict[str, str]:
        package = root / "package.json"
        try:
            data = json.loads(package.read_text(encoding="utf-8")) if package.is_file() else {}
        except (OSError, json.JSONDecodeError):
            return {}
        return {str(k): str(v) for k, v in (data.get("scripts") or {}).items()}

    def resolve(self, project: Optional[ProjectInfo]) -> str:
        root = Path(project.root) if project else Path.cwd()
        return self._local_bin(root, "tsc") or self._resolve_on_path("tsc") or self._node()

    def _runner(self, root: Path) -> tuple[str, str]:
        """The `(program, kind)` used to run TS: project tsx, project ts-node, npx tsx, npx ts-node."""
        deps = self._deps(root)
        if (local := self._local_bin(root, "tsx")):
            return local, "tsx"
        if "tsx" in deps:
            return "npx", "tsx"
        if (local := self._local_bin(root, "ts-node")):
            return local, "ts-node"
        if "ts-node" in deps:
            return "npx", "ts-node"
        return "npx", "tsx"

    def prepare_run(self, request: Any, root: Path, workdir: Path) -> PreparedCommand:
        if not self._node():
            from .base import RuntimeUnavailable  # noqa: PLC0415

            raise RuntimeUnavailable("Node.js isn't available on this computer.")
        scripts = self._scripts(root)
        program, kind = self._runner(root)
        if getattr(request, "code", ""):
            staged = self._stage(workdir, "main.ts", request.code)
            suffix = ["--no-warnings"] if kind == "ts-node" else []
            argv = [program, *suffix, str(staged), *list(getattr(request, "args", []) or [])]
            return PreparedCommand(argv=argv, cwd=workdir, env={}, description=f"typescript inline ({kind})", cleanup=[workdir])
        entrypoint = getattr(request, "entrypoint", "")
        if not entrypoint:
            # Prefer a declared run script (start/dev) — the project's own strategy.
            for script in ("start", "dev", "serve"):
                if script in scripts:
                    return PreparedCommand(argv=["npm", "run", script], cwd=root, env={}, description=f"npm run {script}")
            entrypoint = "src/index.ts"
        target = (root / entrypoint).resolve()
        suffix = ["--no-warnings"] if kind == "ts-node" else []
        argv = [program, *suffix, str(target), *list(getattr(request, "args", []) or [])]
        return PreparedCommand(argv=argv, cwd=root, env={}, description=f"typescript {entrypoint} ({kind})")

    def build(self, root: Path, project: Optional[ProjectInfo], workdir: Path) -> Optional[PreparedCommand]:
        scripts = self._scripts(root)
        # Prefer the project's declared build strategy.
        if "build" in scripts:
            return PreparedCommand(argv=["npm", "run", "build"], cwd=root, env={}, description="npm run build")
        tsc = self._local_bin(root, "tsc") or self._resolve_on_path("tsc")
        if not tsc:
            return None
        if (root / "tsconfig.json").is_file():
            return PreparedCommand(argv=[tsc, "-p", "tsconfig.json", "--noEmit"], cwd=root, env={}, description="tsc --noEmit")
        return PreparedCommand(argv=[tsc, "--noEmit"], cwd=root, env={}, description="tsc --noEmit")

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
