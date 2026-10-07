"""Project and language detection.

`detect_language` follows the spec's priority order exactly:

  1. an explicit language,
  2. the entrypoint extension,
  3. project configuration (a manifest in the workspace),
  4. a shebang,
  5. repository metadata,
  6. a light syntax probe,
  7. runtime metadata.

`ProjectDetector` inspects the manifests the spec names (package.json,
tsconfig.json, pyproject.toml, requirements.txt, Cargo.toml, go.mod, pom.xml,
build.gradle, *.csproj, CMakeLists.txt) and reports language, runtime, package
manager, build system, test framework, entrypoint and lockfile. It reads only
bounded files inside the resolved workspace, and never guesses: an absent
manifest is simply absent.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

# File extension → language id (the ids `runtimes.py` names).
_EXTENSION_LANGUAGE: dict[str, str] = {
    ".py": "python", ".pyw": "python",
    ".js": "javascript", ".mjs": "javascript", ".cjs": "javascript", ".jsx": "javascript",
    ".ts": "typescript", ".tsx": "typescript", ".mts": "typescript", ".cts": "typescript",
    ".sql": "sql",
    ".rs": "rust",
    ".go": "go",
    ".java": "java",
    ".cs": "csharp",
    ".cpp": "cpp", ".cc": "cpp", ".cxx": "cpp", ".hpp": "cpp",
    ".c": "c", ".h": "c",
    ".php": "php",
    ".rb": "ruby",
    ".sh": "shell", ".bash": "shell", ".zsh": "shell", ".ps1": "shell",
}

SHELL_LIKE = frozenset({"shell"})

# The manifests the detector understands, mapped to the facts they imply.
_MANIFEST_FACTS: dict[str, dict[str, str]] = {
    "package.json": {"language": "javascript"},
    "tsconfig.json": {"language": "typescript"},
    "pyproject.toml": {"language": "python", "build": "pep517"},
    "requirements.txt": {"language": "python", "package_manager": "pip"},
    "setup.py": {"language": "python"},
    "Pipfile": {"language": "python", "package_manager": "pipenv"},
    "poetry.lock": {"language": "python", "package_manager": "poetry"},
    "uv.lock": {"language": "python", "package_manager": "uv"},
    "Cargo.toml": {"language": "rust", "package_manager": "cargo", "build": "cargo"},
    "go.mod": {"language": "go", "package_manager": "go", "build": "go"},
    "pom.xml": {"language": "java", "package_manager": "maven", "build": "maven"},
    "build.gradle": {"language": "java", "package_manager": "gradle", "build": "gradle"},
    "build.gradle.kts": {"language": "java", "package_manager": "gradle", "build": "gradle"},
    "CMakeLists.txt": {"language": "cpp", "build": "cmake"},
    "Gemfile": {"language": "ruby", "package_manager": "bundler"},
    "composer.json": {"language": "php", "package_manager": "composer"},
}

_LOCKFILES: dict[str, str] = {
    "package-lock.json": "npm", "pnpm-lock.yaml": "pnpm", "yarn.lock": "yarn",
    "bun.lockb": "bun", "poetry.lock": "poetry", "uv.lock": "uv",
    "Cargo.lock": "cargo", "go.sum": "go", "Pipfile.lock": "pipenv",
}

_TEST_FRAMEWORK_HINTS: dict[str, str] = {
    "vitest": "vitest", "jest": "jest", "mocha": "mocha", "@playwright/test": "playwright",
    "cypress": "cypress", "pytest": "pytest", "unittest": "unittest",
    "cargo": "cargo-test", "go:test": "go-test", "junit": "junit", "nunit": "nunit",
}

MAX_MANIFEST_BYTES = 512 * 1024


@dataclass
class ProjectInfo:
    """What `ProjectDetector` learned about a workspace root."""

    root: str
    languages: list[str] = field(default_factory=list)
    primary_language: str = ""
    runtime: str = ""
    package_manager: str = ""
    build_system: str = ""
    test_framework: str = ""
    entrypoint: str = ""
    manifests: list[str] = field(default_factory=list)
    lockfile: str = ""
    scripts: dict[str, str] = field(default_factory=dict)
    dependencies: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "root": self.root,
            "languages": self.languages,
            "primaryLanguage": self.primary_language,
            "runtime": self.runtime,
            "packageManager": self.package_manager,
            "buildSystem": self.build_system,
            "testFramework": self.test_framework,
            "entrypoint": self.entrypoint,
            "manifests": self.manifests,
            "lockfile": self.lockfile,
            "scripts": self.scripts,
            "dependencies": self.dependencies,
        }


def _read_text(path: Path, *, limit: int = MAX_MANIFEST_BYTES) -> str:
    try:
        with open(path, "r", encoding="utf-8-sig", errors="replace") as handle:
            return handle.read(limit)
    except OSError:
        return ""


def read_json(path: Path) -> dict[str, Any]:
    """Read a JSON manifest, tolerating a UTF-8 BOM (Windows editors add one).

    A `package.json`/`tsconfig.json` saved by Notepad or PowerShell commonly begins
    with a BOM; it is valid JSON and Eclipse MUST read it. Returns `{}` on any
    missing/invalid file — never raises.
    """
    if not path.is_file():
        return {}
    try:
        data = json.loads(_read_text(path) or "{}")
    except (json.JSONDecodeError, OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def language_from_extension(path: str) -> str:
    """The language id for a path's extension, or ""."""
    return _EXTENSION_LANGUAGE.get(Path(str(path)).suffix.casefold(), "")


def _shebang_language(code: str) -> str:
    first = (code or "").splitlines()[0] if code else ""
    if not first.startswith("#!"):
        return ""
    lowered = first.casefold()
    if "python" in lowered:
        return "python"
    if any(shell in lowered for shell in ("bash", "sh", "zsh", "pwsh", "powershell", "cmd")):
        return "shell"
    if "node" in lowered or "deno" in lowered or "bun" in lowered:
        return "javascript"
    if "ruby" in lowered:
        return "ruby"
    if "php" in lowered:
        return "php"
    return ""


def _syntax_language(code: str) -> str:
    """A deliberately light probe. Only strong, unambiguous signals are used."""
    text = code or ""
    if re.search(r"^\s*(def |class )\w+.*:\s*$", text, re.MULTILINE) and re.search(r"^\s*import \w+", text, re.MULTILINE):
        return "python"
    if re.search(r"\b(SELECT|INSERT|UPDATE|DELETE|CREATE TABLE)\b", text, re.IGNORECASE) and text.strip().endswith(";"):
        return "sql"
    if re.search(r"\b(const|let|function|=>|require\(|module\.exports)\b", text):
        return "javascript"
    if re.search(r"\b(interface|type)\s+\w+\s*[=:{]", text) or re.search(r":\s*(string|number|boolean)\b", text):
        return "typescript"
    return ""


def detect_language(
    *,
    explicit: str = "",
    entrypoint: str = "",
    code: str = "",
    project: Optional[ProjectInfo] = None,
    runtime: str = "",
) -> str:
    """The language for an execution, in the spec's priority order (never a guess)."""
    explicit_norm = (explicit or "").strip().casefold()
    if explicit_norm:
        return _canonical_language(explicit_norm)
    if entrypoint:
        ext = language_from_extension(entrypoint)
        if ext:
            return ext
    if project is not None and project.primary_language:
        return project.primary_language
    shebang = _shebang_language(code)
    if shebang:
        return shebang
    if runtime:
        from_runtime = _language_from_runtime(runtime)
        if from_runtime:
            return from_runtime
    return _syntax_language(code)


_ALIASES = {
    "py": "python", "python3": "python",
    "js": "javascript", "node": "javascript", "nodejs": "javascript", "mjs": "javascript",
    "ts": "typescript", "tsx": "typescript", "typescriptreact": "typescript",
    "sh": "shell", "bash": "shell", "powershell": "shell", "pwsh": "shell", "cmd": "shell",
    "postgres": "sql", "postgresql": "sql", "sqlite": "sql", "mysql": "sql",
    "c#": "csharp", "cs": "csharp", "c++": "cpp",
}


def _canonical_language(name: str) -> str:
    name = name.strip().casefold()
    if name in _EXTENSION_LANGUAGE.values():
        return name
    return _ALIASES.get(name, name)


def _language_from_runtime(runtime: str) -> str:
    runtime = (runtime or "").strip().casefold()
    return _ALIASES.get(runtime, runtime if runtime in _EXTENSION_LANGUAGE.values() else "")


class ProjectDetector:
    """Inspect a workspace root and report the project's shape."""

    def detect(self, root: Path) -> ProjectInfo:
        root = Path(root)
        info = ProjectInfo(root=str(root))
        manifests: list[str] = []
        for name, facts in _MANIFEST_FACTS.items():
            if (root / name).is_file():
                manifests.append(name)
                for key, value in facts.items():
                    if key == "language":
                        if value not in info.languages:
                            info.languages.append(value)
                    elif key == "package_manager" and not info.package_manager:
                        info.package_manager = value
                    elif key == "build" and not info.build_system:
                        info.build_system = value
        # .NET: any *.csproj at the top level (bounded glob).
        for csproj in sorted(root.glob("*.csproj"))[:5]:
            manifests.append(csproj.name)
            if "csharp" not in info.languages:
                info.languages.append("csharp")
            info.build_system = info.build_system or "dotnet"
        info.manifests = manifests
        # Lockfile wins over a manifest-implied package manager (exactness).
        for lock, manager in _LOCKFILES.items():
            if (root / lock).is_file():
                info.lockfile = lock
                info.package_manager = manager
                break
        self._read_package_json(root, info)
        primary = info.primary_language or (info.languages[0] if info.languages else "")
        if info.primary_language == "typescript" or (root / "tsconfig.json").is_file():
            primary = "typescript" if ("typescript" in info.languages) else primary
        info.primary_language = primary
        info.runtime = info.runtime or primary
        if not info.entrypoint:
            info.entrypoint = self._guess_entrypoint(root, info)
        if not info.test_framework:
            info.test_framework = self._guess_test_framework(root, info)
        info.dependencies = self._read_dependencies(root, info)
        return info

    def _read_package_json(self, root: Path, info: ProjectInfo) -> None:
        package = root / "package.json"
        if not package.is_file():
            return
        data = read_json(package)
        # A package.json with TypeScript config or deps implies a TS project.
        deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
        if "typescript" in deps and "typescript" not in info.languages:
            info.languages.append("typescript")
        if "typescript" in deps or (root / "tsconfig.json").is_file():
            info.primary_language = "typescript"
            info.runtime = "typescript"
        else:
            info.primary_language = info.primary_language or "javascript"
        info.scripts = {str(k): str(v) for k, v in (data.get("scripts") or {}).items()}
        # Detect a test framework from the declared dependencies.
        for dep, framework in _TEST_FRAMEWORK_HINTS.items():
            if dep in deps:
                info.test_framework = framework
                break
        # A package manager declared by `packageManager` beats a lockfile guess.
        pm = str(data.get("packageManager") or "").split("@")[0]
        if pm:
            info.package_manager = pm

    def _guess_entrypoint(self, root: Path, info: ProjectInfo) -> str:
        if "typescript" in info.languages or (root / "tsconfig.json").is_file():
            for candidate in ("src/index.ts", "src/main.ts", "src/index.tsx", "index.ts"):
                if (root / candidate).is_file():
                    return candidate
        for candidate in ("src/index.js", "index.js", "main.py", "app.py", "src/main.py", "manage.py", "main.go"):
            if (root / candidate).is_file():
                return candidate
        return ""

    def _guess_test_framework(self, root: Path, info: ProjectInfo) -> str:
        if info.test_framework:
            return info.test_framework
        if info.languages and "python" in info.languages:
            return "pytest"
        if info.languages and "rust" in info.languages:
            return "cargo-test"
        if info.languages and "go" in info.languages:
            return "go-test"
        return ""

    def _read_dependencies(self, root: Path, info: ProjectInfo) -> list[str]:
        if info.languages and "python" in info.languages:
            req = root / "requirements.txt"
            if req.is_file():
                names = []
                for line in _read_text(req).splitlines():
                    line = line.strip()
                    if line and not line.startswith("#"):
                        names.append(re.split(r"[<>=!~\[]", line, maxsplit=1)[0].strip())
                return names[:200]
        return []


__all__ = [
    "ProjectDetector",
    "ProjectInfo",
    "detect_language",
    "language_from_extension",
]
