"""Application discovery — understand a project from its files.

`discover_application(root)` inspects the project on disk and returns a
normalized `ApplicationDescriptor`: language, framework, runtime, package
manager, lockfile, dependency/build/dev/prod/test/lint commands, Docker/Compose
support, environment files, required variables, database/cache dependencies,
services, ports and the service graph.

It reuses the execution layer's `ProjectDetector` for the base language/manifest
facts and the ONE bounded file reader, and never guesses: an absent manifest is
simply absent. Discovery reads only bounded files inside the resolved root.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from ..projects import ProjectDetector, ProjectInfo, read_json, _read_text
from .models import (
    ApplicationDescriptor,
    PortRecord,
    ServiceGraph,
    ServiceKind,
    ServiceNode,
)

# ── Framework hints ────────────────────────────────────────────────────────────
#
# A dependency name → a framework id. Data, not branching. The FIRST match in a
# deterministic order wins so two projects with the same deps describe the same.
_NODE_FRAMEWORKS: tuple[tuple[str, str], ...] = (
    ("next", "nextjs"),
    ("nuxt", "nuxt"),
    ("@remix-run/react", "remix"),
    ("astro", "astro"),
    ("@sveltejs/kit", "sveltekit"),
    ("svelte", "svelte"),
    ("@angular/core", "angular"),
    ("vue", "vue"),
    ("@nestjs/core", "nestjs"),
    ("express", "express"),
    ("fastify", "fastify"),
    ("koa", "koa"),
    ("react", "react"),
)
_PY_FRAMEWORKS: tuple[tuple[str, str], ...] = (
    ("fastapi", "fastapi"),
    ("django", "django"),
    ("flask", "flask"),
    ("starlette", "starlette"),
    ("aiohttp", "aiohttp"),
    ("tornado", "tornado"),
)

#: Default development/production port per framework, used to DECORATE discovery
#: (a declared compose/env port always wins). Never a fabricated running port.
_FRAMEWORK_PORTS: dict[str, int] = {
    "nextjs": 3000, "nuxt": 3000, "remix": 3000, "astro": 4321, "vite": 5173,
    "angular": 4200, "vue": 5173, "sveltekit": 5173,
    "fastapi": 8000, "django": 8000, "flask": 5000, "starlette": 8000,
    "express": 3000, "nestjs": 3000, "fastify": 3000,
}

_COMPOSE_FILES: tuple[str, ...] = (
    "compose.yaml", "compose.yml", "docker-compose.yaml", "docker-compose.yml",
)

_ENV_FILES: tuple[str, ...] = (
    ".env", ".env.local", ".env.development", ".env.production", ".env.example",
)

_DB_IMAGES: dict[str, str] = {
    "postgres": "postgresql", "postgresql": "postgresql", "mysql": "mysql",
    "mariadb": "mysql", "mongo": "mongodb", "mongodb": "mongodb",
    "mssql": "sqlserver", "redis": "redis", "memcached": "memcached",
    "elasticsearch": "elasticsearch", "rabbitmq": "rabbitmq", "kafka": "kafka",
    "clickhouse": "clickhouse", "cassandra": "cassandra", "minio": "minio",
}

_DB_PORT: dict[str, int] = {
    "postgresql": 5432, "mysql": 3306, "mongodb": 27017, "sqlserver": 1433,
    "redis": 6379, "memcached": 11211, "elasticsearch": 9200, "rabbitmq": 5672,
    "kafka": 9092, "clickhouse": 8123, "cassandra": 9042, "minio": 9000,
}

_CACHE_SERVICES = frozenset({"redis", "memcached"})

MAX_ENV_BYTES = 128 * 1024


@dataclass
class ComposeService:
    """One service parsed from a compose file."""

    name: str
    image: str = ""
    build: str = ""
    ports: list[int] = field(default_factory=list)
    depends_on: list[str] = field(default_factory=list)
    environment: list[str] = field(default_factory=list)
    healthcheck: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name, "image": self.image, "build": self.build,
            "ports": list(self.ports), "dependsOn": list(self.depends_on),
            "environment": list(self.environment), "healthcheck": self.healthcheck,
        }


class ApplicationDiscovery:
    """Inspect a root and produce an `ApplicationDescriptor`."""

    def __init__(self, detector: Optional[ProjectDetector] = None) -> None:
        self._detector = detector or ProjectDetector()

    def discover(self, root: Path, *, name: str = "") -> ApplicationDescriptor:
        root = Path(root)
        base = self._detector.detect(root)
        descriptor = ApplicationDescriptor(
            name=name or root.name,
            path=str(root),
            language=base.primary_language or "",
            runtime=base.runtime or base.primary_language or "",
            package_manager=base.package_manager or "",
            lockfile=base.lockfile or "",
            manifests=list(base.manifests),
            test_framework=base.test_framework or "",
            entrypoint=base.entrypoint or "",
        )
        deps = self._dependencies(root, base)
        descriptor.frameworks = self._detect_frameworks(base, deps)
        descriptor.framework = descriptor.frameworks[0] if descriptor.frameworks else ""
        # A package.json with no lockfile implies npm (the ecosystem default), so
        # the descriptor names a manager instead of leaving it blank.
        if not descriptor.package_manager and (root / "package.json").is_file():
            descriptor.package_manager = "npm"
        descriptor.commands = self._commands(root, base, descriptor)
        self._detect_containers(root, descriptor)
        self._detect_env(root, descriptor)
        compose_services = self._parse_compose(root, descriptor)
        self._compose_graph(compose_services, descriptor)
        self._detect_inferred_ports(descriptor)
        self._detect_databases(root, descriptor, compose_services)
        descriptor.description = self._describe(descriptor)
        return descriptor

    # ── dependencies / frameworks ────────────────────────────────────────────
    def _dependencies(self, root: Path, base: ProjectInfo) -> dict[str, str]:
        deps: dict[str, str] = {}
        package = root / "package.json"
        if package.is_file():
            data = read_json(package)
            deps.update({str(k): str(v) for k, v in (data.get("dependencies") or {}).items()})
            deps.update({str(k): str(v) for k, v in (data.get("devDependencies") or {}).items()})
        for req in ("requirements.txt", "requirements-dev.txt"):
            path = root / req
            if path.is_file():
                for line in _read_text(path).splitlines():
                    line = line.strip()
                    if line and not line.startswith("#"):
                        deps.setdefault(re.split(r"[<>=!~\[;]", line, maxsplit=1)[0].strip().casefold(), "")
        for pyproject in ("pyproject.toml",):
            path = root / pyproject
            if path.is_file():
                text = _read_text(path).casefold()
                for name, framework in _PY_FRAMEWORKS:
                    if re.search(rf'["\']?{re.escape(name)}["\']?\s*[>=<~"\']', text) or name in text:
                        deps.setdefault(name, "")
        return deps

    def _detect_frameworks(self, base: ProjectInfo, deps: dict[str, str]) -> list[str]:
        found: list[str] = []
        lowered = {k.casefold() for k in deps}
        for needle, framework in _NODE_FRAMEWORKS:
            if needle.casefold() in lowered and framework not in found:
                found.append(framework)
        for needle, framework in _PY_FRAMEWORKS:
            if needle in lowered and framework not in found:
                found.append(framework)
        if not found and "typescript" in (base.languages or []):
            found.append("node")
        return found

    # ── commands ─────────────────────────────────────────────────────────────
    def _commands(self, root: Path, base: ProjectInfo, descriptor: ApplicationDescriptor) -> dict[str, str]:
        commands: dict[str, str] = {}
        pm = descriptor.package_manager
        scripts = dict(base.scripts or {})
        if scripts:
            mapping = {
                "install": ("install", "i"),
                "build": ("build", "compile"),
                "dev": ("dev", "develop", "start:dev"),
                "start": ("start", "serve", "preview"),
                "test": ("test",),
                "lint": ("lint", "eslint", "check"),
            }
            runner = f"{pm} run " if pm in ("npm", "pnpm", "yarn", "bun") else ""
            for key, names in mapping.items():
                for name in names:
                    if name in scripts:
                        commands[key] = f"{runner}{name}".strip()
                        break
            if "install" not in commands and pm:
                commands["install"] = _install_command(pm)
        else:
            commands.update(self._default_commands(descriptor))
        if descriptor.docker and "build" not in commands:
            commands["dockerBuild"] = "docker build ."
        return commands

    def _default_commands(self, descriptor: ApplicationDescriptor) -> dict[str, str]:
        commands: dict[str, str] = {}
        pm = descriptor.package_manager
        if pm:
            commands["install"] = _install_command(pm)
        if descriptor.language in ("typescript", "javascript") and pm:
            commands.setdefault("build", f"{pm} run build")
            commands.setdefault("dev", f"{pm} run dev")
            commands.setdefault("test", f"{pm} test")
        if descriptor.language == "python":
            commands.setdefault("test", "pytest")
            if descriptor.framework in ("fastapi", "starlette"):
                commands.setdefault("dev", "uvicorn app:app --reload")
            elif descriptor.framework == "django":
                commands.setdefault("dev", "python manage.py runserver")
            elif descriptor.framework == "flask":
                commands.setdefault("dev", "flask run")
        if descriptor.language == "rust":
            commands.setdefault("build", "cargo build")
            commands.setdefault("test", "cargo test")
            commands.setdefault("dev", "cargo run")
        if descriptor.language == "go":
            commands.setdefault("build", "go build ./...")
            commands.setdefault("test", "go test ./...")
            commands.setdefault("dev", "go run .")
        if descriptor.language == "java":
            if "maven" in (descriptor.package_manager, ""):
                commands.setdefault("build", "mvn package")
                commands.setdefault("test", "mvn test")
            else:
                commands.setdefault("build", "gradle build")
                commands.setdefault("test", "gradle test")
        return commands

    # ── containers ────────────────────────────────────────────────────────────
    def _detect_containers(self, root: Path, descriptor: ApplicationDescriptor) -> None:
        dockerfiles: list[str] = []
        for candidate in sorted(root.glob("Dockerfile*")):
            if candidate.is_file():
                dockerfiles.append(candidate.name)
        descriptor.dockerfiles = dockerfiles[:10]
        descriptor.docker = bool(dockerfiles)
        for name in _COMPOSE_FILES:
            if (root / name).is_file():
                descriptor.compose = True
                descriptor.compose_file = name
                break
        if descriptor.compose or descriptor.docker:
            # Prefer podman when a podman compose/quadlet shape is present; else Docker.
            descriptor.container_runtime = self._prefer_container_runtime(root)

    def _prefer_container_runtime(self, root: Path) -> str:
        for candidate in ("podman-compose.yml", "podman-compose.yaml", "quadlet"):
            if (root / candidate).exists():
                return "podman"
        return "docker"

    # ── compose ────────────────────────────────────────────────────────────────
    def _parse_compose(self, root: Path, descriptor: ApplicationDescriptor) -> list[ComposeService]:
        if not descriptor.compose_file:
            return []
        text = _read_text(root / descriptor.compose_file, limit=512 * 1024)
        if not text.strip():
            return []
        return _parse_compose_services(text)

    def _compose_graph(self, services: list[ComposeService], descriptor: ApplicationDescriptor) -> None:
        if not services:
            return
        descriptor.services = [s.name for s in services]
        ports: list[int] = []
        for service in services:
            for port in service.ports:
                if port not in ports:
                    ports.append(port)
        descriptor.ports = ports

    # ── environment ─────────────────────────────────────────────────────────────
    def _detect_env(self, root: Path, descriptor: ApplicationDescriptor) -> None:
        files: list[str] = []
        required: list[str] = []
        for name in _ENV_FILES:
            path = root / name
            if path.is_file():
                files.append(name)
        descriptor.env_files = files
        example = root / ".env.example"
        if example.is_file():
            for line in _read_text(example, limit=MAX_ENV_BYTES).splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key = line.split("=", 1)[0].strip()
                if key and key not in required:
                    required.append(key)
        descriptor.required_env = required

    # ── ports ────────────────────────────────────────────────────────────────
    def _detect_inferred_ports(self, descriptor: ApplicationDescriptor) -> None:
        ports = list(descriptor.ports)
        for framework in descriptor.frameworks:
            port = _FRAMEWORK_PORTS.get(framework)
            if port and port not in ports:
                ports.append(port)
        # An env PORT= declaration is authoritative for the default port.
        for env_name in descriptor.env_files:
            port = _env_port(Path(descriptor.path) / env_name)
            if port and port not in ports:
                ports.insert(0, port)
        descriptor.ports = ports

    # ── databases / caches ─────────────────────────────────────────────────────
    def _detect_databases(self, root: Path, descriptor: ApplicationDescriptor, services: list[ComposeService]) -> None:
        databases: list[str] = []
        caches: list[str] = []
        for service in services:
            family = _image_family(service.image) or _image_family(service.build)
            if not family:
                continue
            if family in _CACHE_SERVICES:
                if family not in caches:
                    caches.append(family)
            elif family in ("postgresql", "mysql", "mongodb", "sqlserver", "clickhouse", "cassandra"):
                if family not in databases:
                    databases.append(family)
        descriptor.databases = databases
        descriptor.caches = caches

    def _describe(self, descriptor: ApplicationDescriptor) -> str:
        parts = []
        if descriptor.framework:
            parts.append(descriptor.framework)
        if descriptor.language:
            parts.append(descriptor.language)
        if descriptor.package_manager:
            parts.append(f"({descriptor.package_manager})")
        if descriptor.compose:
            parts.append("+ Docker Compose")
        elif descriptor.docker:
            parts.append("+ Docker")
        return " ".join(parts)


def _install_command(pm: str) -> str:
    return {
        "npm": "npm install", "pnpm": "pnpm install", "yarn": "yarn install",
        "bun": "bun install", "pip": "pip install -r requirements.txt",
        "uv": "uv sync", "poetry": "poetry install", "pipenv": "pipenv install",
        "cargo": "cargo fetch", "go": "go mod download", "maven": "mvn dependency:resolve",
        "gradle": "gradle dependencies", "bundler": "bundle install",
        "composer": "composer install",
    }.get(pm, "")


def _env_port(path: Path) -> int:
    if not path.is_file():
        return 0
    for line in _read_text(path, limit=MAX_ENV_BYTES).splitlines():
        line = line.strip()
        if line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        if key.strip().casefold() in ("port", "app_port", "server_port"):
            match = re.search(r"\d{2,5}", value)
            if match:
                port = int(match.group(0))
                if 0 < port < 65536:
                    return port
    return 0


def _image_family(text: str) -> str:
    if not text:
        return ""
    token = text.strip().casefold().rsplit("/", 1)[-1].split(":")[0].strip()
    return _DB_IMAGES.get(token, "")


# ── Minimal, tolerant compose parser ───────────────────────────────────────────
#
# A full YAML parser is deliberately NOT a dependency. Compose files have a
# predictable, shallow shape; this reader understands the subset Eclipse needs
# (services, image/build, ports, depends_on, environment, healthcheck) and
# degrades honestly on anything else rather than inventing facts.


def _parse_compose_services(text: str) -> list[ComposeService]:
    lines = text.splitlines()
    services: dict[str, ComposeService] = {}
    current: Optional[ComposeService] = None
    in_services = False
    section: Optional[str] = None

    def _flush() -> None:
        nonlocal current
        if current is not None:
            services[current.name] = current
            current = None

    for raw in lines:
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip())
        stripped = raw.strip()
        if indent == 0:
            if stripped.rstrip(":") == "services":
                in_services = True
                continue
            in_services = False
            _flush()
            continue
        if not in_services:
            continue
        if indent <= 2 and stripped.endswith(":"):
            _flush()
            current = ComposeService(name=stripped[:-1].strip())
            section = None
            continue
        if current is None:
            continue
        key = stripped.split(":", 1)[0].strip()
        value = stripped.split(":", 1)[1].strip() if ":" in stripped else ""
        if indent == 4 and value == "":
            section = key
            continue
        if indent == 4 and value:
            _set_service_field(current, key, value)
            section = None
            continue
        # Nested list / map entries (indent >= 6).
        if section == "ports":
            port = _parse_port_entry(stripped)
            if port:
                current.ports.append(port)
        elif section == "depends_on":
            dep = stripped.lstrip("- ").strip().rstrip(":").strip()
            if dep:
                current.depends_on.append(dep)
        elif section == "environment":
            entry = stripped.lstrip("- ").strip()
            name = entry.split("=", 1)[0].split(":", 1)[0].strip()
            if name:
                current.environment.append(name)
        elif section == "healthcheck":
            current.healthcheck = True
        elif section == "build":
            if isinstance(value, str) and value:
                current.build = value
    _flush()
    return list(services.values())


def _set_service_field(service: ComposeService, key: str, value: str) -> None:
    value = value.strip().strip('"').strip("'")
    if key == "image":
        service.image = value
    elif key == "build":
        service.build = value
    elif key == "ports":
        port = _parse_port_entry(value)
        if port:
            service.ports.append(port)
    elif key == "depends_on":
        deps = [d.strip().strip('"').strip("'") for d in value.strip("[]").split(",") if d.strip()]
        service.depends_on.extend(deps)


def _parse_port_entry(text: str) -> int:
    text = text.strip().lstrip("- ").strip().strip('"').strip("'")
    if not text:
        return 0
    # forms: "5432", "5432:5432", "127.0.0.1:5432:5432", "5432:5432/tcp"
    text = text.split("/", 1)[0]
    parts = text.split(":")
    candidate = parts[-2] if len(parts) >= 2 else parts[-1]
    match = re.search(r"\d{2,5}", candidate)
    if not match:
        match = re.search(r"\d{2,5}", text)
    if not match:
        return 0
    port = int(match.group(0))
    return port if 0 < port < 65536 else 0


def build_service_graph(descriptor: ApplicationDescriptor, compose_services: Optional[list[ComposeService]] = None) -> ServiceGraph:
    """Build the normalized service graph from a descriptor (and optional compose)."""
    graph = ServiceGraph()
    compose_by_name = {s.name: s for s in (compose_services or [])}
    for name in descriptor.services:
        service = compose_by_name.get(name)
        if service is not None:
            family = _image_family(service.image)
            kind = ServiceKind.CONTAINER if (service.image or service.build) else ServiceKind.PROCESS
            node = ServiceNode(
                name=name, kind=kind, image=service.image, ports=list(service.ports),
                depends_on=list(service.depends_on), compose=True,
                notes=("healthcheck defined" if service.healthcheck else ""),
            )
            graph.add(node)
            if family:
                db = ServiceNode(name=family, kind=ServiceKind.CONTAINER, ports=[_DB_PORT.get(family, 0)],
                                 image=service.image, compose=True)
                if not db.ports or db.ports == [0]:
                    db.ports = []
                if family not in graph.nodes:
                    graph.add(db)
                graph.edges.append((family, name))
        else:
            graph.add(ServiceNode(name=name, kind=ServiceKind.PROCESS))
    if not descriptor.services and descriptor.framework:
        graph.add(ServiceNode(name="app", kind=ServiceKind.PROCESS, command=descriptor.commands.get("dev", "")))
    return graph


def discover_application(root: Path, *, name: str = "") -> ApplicationDescriptor:
    """The one-shot entry point: discover an application at `root`."""
    return ApplicationDiscovery().discover(root, name=name)


__all__ = [
    "ApplicationDiscovery",
    "ComposeService",
    "build_service_graph",
    "discover_application",
]
