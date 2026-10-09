"""Language detection — extensions, manifests and framework configuration.

`detect_language` maps a file to one of the supported language tags. The
`LanguageDetector` walks a project root and returns the languages, frameworks,
package managers, build systems, entry points, databases and test roots it can
prove from files that are actually present. Nothing is guessed: an unrecognized
file is `text`, and a framework is only reported when its configuration file (or
a dependency entry) is really there.

No external command is run here; the toolchain probe (`toolchain.py`) is separate.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Optional

MAX_WALK_ENTRIES = 40_000

# Extension → language tag. The initial supported set from the CIUE contract.
_LANGUAGE_BY_EXT: dict[str, str] = {
    ".ts": "typescript", ".tsx": "typescript", ".mts": "typescript", ".cts": "typescript",
    ".js": "javascript", ".jsx": "javascript", ".mjs": "javascript", ".cjs": "javascript",
    ".py": "python", ".pyi": "python",
    ".java": "java",
    ".cs": "csharp",
    ".c": "c", ".h": "c",
    ".cpp": "cpp", ".cc": "cpp", ".cxx": "cpp", ".hpp": "cpp", ".hh": "cpp",
    ".go": "go",
    ".rs": "rust",
    ".php": "php",
    ".sql": "sql",
    ".rb": "ruby",
    ".json": "json", ".jsonc": "jsonc",
    ".toml": "toml", ".yml": "yaml", ".yaml": "yaml",
    ".md": "markdown", ".html": "html", ".css": "css", ".scss": "css",
    ".sh": "shell", ".bash": "shell", ".ps1": "shell",
}

# Extensions the indexer will parse (a language with structure worth indexing).
SOURCE_LANGUAGES: tuple[str, ...] = (
    "typescript", "javascript", "python", "java", "csharp", "c", "cpp", "go",
    "rust", "php", "sql", "ruby",
)

# Manifest/config file → (kind, value). Detected only when the file exists.
_MANIFESTS: dict[str, tuple[str, str]] = {
    "package.json": ("package_manager", "npm"),
    "pnpm-lock.yaml": ("package_manager", "pnpm"),
    "pnpm-workspace.yaml": ("monorepo", "pnpm"),
    "yarn.lock": ("package_manager", "yarn"),
    "bun.lockb": ("package_manager", "bun"),
    "tsconfig.json": ("build_system", "tsc"),
    "pyproject.toml": ("package_manager", "python"),
    "requirements.txt": ("package_manager", "pip"),
    "poetry.lock": ("package_manager", "poetry"),
    "uv.lock": ("package_manager", "uv"),
    "Cargo.toml": ("package_manager", "cargo"),
    "Cargo.lock": ("build_system", "cargo"),
    "go.mod": ("package_manager", "go"),
    "go.work": ("monorepo", "go"),
    "pom.xml": ("build_system", "maven"),
    "build.gradle": ("build_system", "gradle"),
    "build.gradle.kts": ("build_system", "gradle"),
    "settings.gradle": ("build_system", "gradle"),
    "composer.json": ("package_manager", "composer"),
    "CMakeLists.txt": ("build_system", "cmake"),
    "Makefile": ("build_system", "make"),
    "turbo.json": ("monorepo", "turborepo"),
    "nx.json": ("monorepo", "nx"),
    "lerna.json": ("monorepo", "lerna"),
    "Gemfile": ("package_manager", "bundler"),
    "Dockerfile": ("build_system", "docker"),
    "docker-compose.yml": ("build_system", "docker"),
}

# Framework hints: a manifest path/dependency or a config file → framework id.
_FRAMEWORK_DEPS: dict[str, str] = {
    "next": "nextjs", "react": "react", "react-dom": "react", "vue": "vue",
    "nuxt": "nuxt", "@angular/core": "angular", "svelte": "svelte",
    "express": "express", "@nestjs/core": "nestjs", "fastify": "fastify",
    "koa": "koa", "electron": "electron", "vite": "vite", "webpack": "webpack",
    "django": "django", "flask": "flask", "fastapi": "fastapi",
    "starlette": "starlette", "tornado": "tornado",
    "spring-boot": "spring", "spring-core": "spring",
    "laravel/framework": "laravel", "symfony/framework-bundle": "symfony",
    "actix-web": "actix", "axum": "axum", "rocket": "rocket",
    "gin-gonic": "gin", "echo": "echo", "fiber": "fiber",
}

_FRAMEWORK_CONFIG: dict[str, str] = {
    "next.config.js": "nextjs", "next.config.ts": "nextjs", "next.config.mjs": "nextjs",
    "nuxt.config.js": "nuxt", "nuxt.config.ts": "nuxt",
    "angular.json": "angular",
    "vue.config.js": "vue",
    "vite.config.js": "vite", "vite.config.ts": "vite",
    "svelte.config.js": "svelte",
    "manage.py": "django",
    "artisan": "laravel",
}

# Database driver dependency → database id.
_DB_DEPS: dict[str, str] = {
    "prisma": "prisma", "@prisma/client": "prisma",
    "pg": "postgres", "postgres": "postgres", "psycopg2": "postgres", "psycopg": "postgres",
    "asyncpg": "postgres", "mysql": "mysql", "mysql2": "mysql", "pymysql": "mysql",
    "sqlite3": "sqlite", "better-sqlite3": "sqlite", "aiosqlite": "sqlite",
    "mongo": "mongodb", "mongoose": "mongodb", "pymongo": "mongodb",
    "redis": "redis", "ioredis": "redis",
    "sqlalchemy": "sql", "sequelize": "sql", "typeorm": "sql",
}

_TEST_DIRS = ("test", "tests", "__tests__", "spec", "e2e", "integration")
_ENTRY_CANDIDATES = (
    "src/index.ts", "src/index.js", "src/main.ts", "src/main.js", "index.js",
    "server.js", "app.js", "main.py", "__main__.py", "manage.py", "wsgi.py", "app.py",
    "main.go", "src/main.rs", "Program.cs", "main.c", "main.cpp", "index.php",
    "src/App.tsx", "src/main.tsx", "pages/index.tsx", "app/page.tsx",
)


def detect_language(path: str | Path) -> str:
    """The language tag for a path. Unknown → "text" (never an exception)."""
    return _LANGUAGE_BY_EXT.get(Path(path).suffix.lower(), "text")


def is_source(path: str | Path) -> bool:
    return detect_language(path) in SOURCE_LANGUAGES


@dataclass
class LanguageInfo:
    root: str
    languages: list[str] = field(default_factory=list)
    frameworks: list[str] = field(default_factory=list)
    package_managers: list[str] = field(default_factory=list)
    build_systems: list[str] = field(default_factory=list)
    entry_points: list[str] = field(default_factory=list)
    databases: list[str] = field(default_factory=list)
    monorepo: bool = False
    project_roots: list[str] = field(default_factory=list)
    tests: list[str] = field(default_factory=list)
    config_files: list[str] = field(default_factory=list)
    language_counts: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "root": self.root,
            "languages": self.languages,
            "frameworks": self.frameworks,
            "packageManagers": self.package_managers,
            "buildSystems": self.build_systems,
            "entryPoints": self.entry_points,
            "databases": self.databases,
            "monorepo": self.monorepo,
            "projectRoots": self.project_roots,
            "tests": self.tests,
            "configFiles": self.config_files,
            "languageCounts": self.language_counts,
        }


def _read_json(path: Path) -> Optional[dict[str, Any]]:
    try:
        return json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, ValueError):
        return None


def _manifest_dependency_names(data: dict[str, Any]) -> set[str]:
    names: set[str] = set()
    for section in ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies"):
        block = data.get(section)
        if isinstance(block, dict):
            names.update(str(k) for k in block)
    return names


def _pyproject_dependency_names(text: str) -> set[str]:
    """Extract bare dependency names from a pyproject/requirements text."""
    names: set[str] = set()
    for match in re.finditer(r"^\s*([A-Za-z0-9_.\-]+)\s*[<>=!~\[;]", text, re.MULTILINE):
        names.add(match.group(1).lower())
    # A quoted dependency list `dependencies = ["fastapi>=0.1", "uvicorn"]`.
    for match in re.finditer(r'"([A-Za-z0-9_.\-]+)\s*[<>=!~\[;]?"', text):
        names.add(match.group(1).lower())
    return names


class LanguageDetector:
    """Detect languages, frameworks and project shape from a real directory tree."""

    def __init__(self, root: Path, *, ignored_dirs: Iterable[str] = ()) -> None:
        self.root = Path(root)
        self._ignored = set(ignored_dirs) | {
            ".git", "node_modules", "__pycache__", ".next", ".next-dev",
            "dist", "build", "target", "coverage", ".venv", "venv", "vendor",
            ".cache", ".turbo",
        }

    def detect(self) -> LanguageInfo:
        info = LanguageInfo(root=str(self.root))
        counts: dict[str, int] = {}
        manifests_seen: set[str] = set()
        entry_found: set[str] = set()
        test_roots: set[str] = set()
        config_files: list[str] = []
        monorepo = False
        project_roots: set[str] = set()

        walked = 0
        for dirpath, dirnames, filenames in os.walk(self.root, followlinks=False):
            dirnames[:] = [d for d in dirnames if d not in self._ignored]
            rel_dir = os.path.relpath(dirpath, self.root).replace("\\", "/")
            if rel_dir == ".":
                rel_dir = ""
            base = os.path.basename(dirpath)
            if base in _TEST_DIRS:
                test_roots.add(rel_dir or ".")
            for name in filenames:
                walked += 1
                if walked > MAX_WALK_ENTRIES:
                    break
                rel = f"{rel_dir}/{name}" if rel_dir else name
                lang = detect_language(name)
                if lang in SOURCE_LANGUAGES:
                    counts[lang] = counts.get(lang, 0) + 1
                entry = _MANIFESTS.get(name)
                if entry is not None:
                    kind, value = entry
                    manifests_seen.add(value)
                    config_files.append(rel)
                    if kind == "package_manager":
                        info.package_managers.append(value)
                    elif kind == "build_system":
                        info.build_systems.append(value)
                    elif kind == "monorepo":
                        monorepo = True
                        project_roots.add(rel_dir or ".")
                framework = _FRAMEWORK_CONFIG.get(name)
                if framework:
                    info.frameworks.append(framework)
                    config_files.append(rel)
                config_text = None
                if name in ("package.json", "pyproject.toml", "requirements.txt", "composer.json"):
                    try:
                        config_text = Path(dirpath, name).read_text(encoding="utf-8", errors="replace")
                    except OSError:
                        config_text = None
                dep_names: set[str] = set()
                if config_text is not None:
                    if name == "package.json":
                        data = _read_json(Path(dirpath, name)) or {}
                        dep_names = _manifest_dependency_names(data)
                        if data.get("workspaces"):
                            monorepo = True
                            project_roots.add(rel_dir or ".")
                    else:
                        dep_names = _pyproject_dependency_names(config_text)
                for dep in dep_names:
                    fw = _FRAMEWORK_DEPS.get(dep)
                    if fw:
                        info.frameworks.append(fw)
                    db = _DB_DEPS.get(dep)
                    if db:
                        info.databases.append(db)
                if name in _ENTRY_CANDIDATES:
                    entry_found.add(rel)
            if walked > MAX_WALK_ENTRIES:
                break

        # Monorepo layout: a conventional multi-project folder that has children.
        for candidate in ("apps", "packages", "services", "libs"):
            candidate_path = self.root / candidate
            if candidate_path.is_dir():
                monorepo = True
                project_roots.add(candidate)
        info.monorepo = monorepo
        info.languages = sorted(counts, key=lambda k: (-counts[k], k))
        info.language_counts = dict(sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])))
        info.frameworks = _dedupe(info.frameworks)
        info.package_managers = _dedupe(info.package_managers)
        info.build_systems = _dedupe(info.build_systems)
        info.databases = _dedupe(info.databases)
        info.entry_points = sorted(entry_found)
        info.tests = sorted(test_roots)
        info.config_files = sorted(set(config_files))[:200]
        info.project_roots = sorted(project_roots)
        return info


def _dedupe(values: list[str]) -> list[str]:
    seen: dict[str, None] = {}
    for value in values:
        seen[value] = None
    return sorted(seen)


__all__ = [
    "LanguageDetector",
    "LanguageInfo",
    "SOURCE_LANGUAGES",
    "detect_language",
    "is_source",
]
