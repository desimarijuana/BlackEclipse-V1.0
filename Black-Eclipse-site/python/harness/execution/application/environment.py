"""Environment detection + environment variable management.

Two concerns, kept distinct:

  * `EnvironmentDetector` probes the LOCAL machine (OS, arch, shell, and the
    versions of the runtimes/tools Eclipse can use) and reports only
    NON-SENSITIVE metadata. It never reads a secret.
  * `EnvironmentManager` reads a project's `.env` files, reports which variables
    exist and whether they look required, and NEVER returns a secret value to a
    caller (the model) — a secret is represented as `[SECRET]` and only its
    existence and length class are exposed.

Version probes run bounded argv with no shell, exactly like the sandbox, and a
missing tool is reported `available: false` — never a fabricated version.
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

_ENV_FILES = (".env", ".env.local", ".env.development", ".env.production", ".env.example")
_MAX_ENV_BYTES = 128 * 1024

#: Names whose VALUE is a secret. Matched case-insensitively by whole name OR by
#: a suffix, so `POSTGRES_PASSWORD`, `PGPASSWORD`, `DB_PASS` are all secret.
_SECRET_MARKERS: tuple[str, ...] = (
    "password", "passwd", "secret", "token", "api_key", "apikey", "access_key",
    "private_key", "credential", "auth", "dsn", "database_url", "connection_string",
    "cookie", "session_key", "signing_key", "webhook", "bearer",
)
_SECRET_PREFIXES: tuple[str, ...] = ("secret_", "private_", "signing_")
_SECRET_SUFFIXES: tuple[str, ...] = (
    "_key", "_secret", "_token", "_password", "_pass", "_pwd", "_dsn", "_uri",
    "_credential", "_credentials",
)

#: Variables that are configuration, not secrets, even though the name matches.
_NON_SECRET_NAMES = frozenset(
    {
        "node_env", "next_public_app_name", "app_env", "log_level", "debug",
        "host", "port", "app_port", "server_port", "api_url", "base_url",
        "cors_origin", "cors_origins", "public_url", "site_url",
    }
)

MASK = "[SECRET]"


def is_secret_name(name: str) -> bool:
    """Whether a variable name's value must be masked. Conservative (fail-secret)."""
    key = str(name or "").strip().casefold()
    if not key:
        return False
    if key in _NON_SECRET_NAMES:
        return False
    if key in ("database_url", "redis_url", "postgres_url", "mongo_url", "mongo_uri"):
        return True
    if any(marker in key for marker in _SECRET_MARKERS):
        return True
    return any(key.endswith(suffix) for suffix in _SECRET_SUFFIXES)


@dataclass
class EnvVar:
    """One environment variable, with its value masked when it is a secret."""

    name: str
    value: str = ""
    secret: bool = False
    source: str = ""
    empty: bool = False

    def safe_value(self) -> str:
        if self.secret:
            return MASK if self.value else ""
        return self.value

    def to_dict(self, *, reveal: bool = False) -> dict[str, Any]:
        return {
            "name": self.name,
            "value": self.value if (reveal and not self.secret) else (MASK if self.secret else self.value),
            "secret": self.secret, "source": self.source, "empty": self.empty,
        }


@dataclass
class EnvironmentReport:
    """The merged environment of a project, secrets masked."""

    files: list[str] = field(default_factory=list)
    vars: list[EnvVar] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    invalid: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "files": list(self.files),
            "vars": [v.to_dict() for v in self.vars],
            "missing": list(self.missing),
            "invalid": list(self.invalid),
        }

    def secret_names(self) -> list[str]:
        return sorted(v.name for v in self.vars if v.secret)


class EnvironmentManager:
    """Read/merge/compare `.env` files with secret masking."""

    def __init__(self, *, reveal_secrets: bool = False) -> None:
        # `reveal_secrets` is an operator-only escape hatch, never model-facing.
        self._reveal = bool(reveal_secrets)

    def read_file(self, path: Path) -> list[EnvVar]:
        if not path.is_file():
            return []
        try:
            text = path.read_text(encoding="utf-8-sig", errors="replace")[:_MAX_ENV_BYTES]
        except OSError:
            return []
        return self._parse(text, source=path.name)

    def _parse(self, text: str, *, source: str) -> list[EnvVar]:
        out: list[EnvVar] = []
        for raw in text.splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("export "):
                line = line[len("export "):].strip()
            if "=" not in line:
                continue
            name, _, value = line.partition("=")
            name = name.strip()
            value = value.strip().strip('"').strip("'")
            if not name:
                continue
            secret = is_secret_name(name)
            out.append(EnvVar(name=name, value=value, secret=secret, source=source, empty=(value == "")))
        return out

    def load(self, root: Path, *, layers: Optional[tuple[str, ...]] = None) -> EnvironmentReport:
        """Merge `.env` files in precedence order (later files override).

        `.env` < `.env.local` < `.env.development`; `.env.example` is read for
        the REQUIRED set but never supplies a live value.
        """
        root = Path(root)
        order = layers or (".env", ".env.local", ".env.development")
        merged: dict[str, EnvVar] = {}
        files: list[str] = []
        for name in order:
            path = root / name
            if not path.is_file():
                continue
            files.append(name)
            for var in self.read_file(path):
                merged[var.name] = var
        example = root / ".env.example"
        required: list[str] = []
        if example.is_file():
            files.append(".env.example")
            for var in self.read_file(example):
                required.append(var.name)
                merged.setdefault(var.name, EnvVar(name=var.name, value="", secret=var.secret, source=".env.example", empty=True))
        missing = [name for name in required if name not in merged or merged[name].empty]
        invalid = [name for name, var in merged.items() if var.secret and var.empty and var.source != ".env.example"]
        return EnvironmentReport(
            files=files, vars=sorted(merged.values(), key=lambda v: v.name),
            missing=sorted(set(missing)), invalid=sorted(set(invalid)),
        )

    def validate(self, root: Path, *, required: Optional[list[str]] = None) -> dict[str, Any]:
        report = self.load(root)
        needed = list(required or report.missing)
        present = {v.name for v in report.vars if not v.empty}
        missing = [name for name in needed if name not in present]
        return {
            "ok": not missing,
            "missing": missing,
            "required": needed,
            "files": report.files,
            "secrets": report.secret_names(),
        }

    def compare(self, root: Path, other: Path) -> dict[str, Any]:
        """Compare two `.env` files' KEY SETS (never values)."""
        left = self.read_file(Path(root))
        right = self.read_file(Path(other))
        left_names = {v.name for v in left}
        right_names = {v.name for v in right}
        return {
            "onlyInLeft": sorted(left_names - right_names),
            "onlyInRight": sorted(right_names - left_names),
            "changed": sorted(
                v.name for v in left
                if v.name in right_names and _differs(v, next(r for r in right if r.name == v.name))
            ),
            "same": sorted(left_names & right_names),
        }

    def metadata(self, root: Path) -> dict[str, Any]:
        """Non-secret metadata: names, secret flags, emptiness. No values."""
        report = self.load(root)
        return {
            "files": report.files,
            "count": len(report.vars),
            "variables": [
                {"name": v.name, "secret": v.secret, "empty": v.empty, "source": v.source}
                for v in report.vars
            ],
            "missing": report.missing,
        }

    # ── mutations (write to a target `.env`, never `.env.example`) ─────────────
    def set(self, path: Path, name: str, value: str) -> dict[str, Any]:
        path = Path(path)
        if path.name == ".env.example":
            return {"status": "refused", "code": "REFUSED_EXAMPLE", "reason": "won't modify the example file"}
        if not _valid_env_name(name):
            return {"status": "refused", "code": "INVALID_NAME", "reason": "not a valid variable name"}
        lines: list[str] = []
        if path.is_file():
            lines = path.read_text(encoding="utf-8-sig", errors="replace").splitlines()
        found = False
        for index, raw in enumerate(lines):
            stripped = raw.strip()
            key = stripped.split("=", 1)[0].strip() if "=" in stripped else ""
            if key == name:
                lines[index] = f"{name}={value}"
                found = True
                break
        if not found:
            lines.append(f"{name}={value}")
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return {"status": "ok", "name": name, "secret": is_secret_name(name), "file": path.name}

    def unset(self, path: Path, name: str) -> dict[str, Any]:
        path = Path(path)
        if path.name == ".env.example":
            return {"status": "refused", "code": "REFUSED_EXAMPLE", "reason": "won't modify the example file"}
        if not path.is_file():
            return {"status": "ok", "removed": False, "file": path.name}
        kept = []
        removed = False
        for raw in path.read_text(encoding="utf-8-sig", errors="replace").splitlines():
            stripped = raw.strip()
            key = stripped.split("=", 1)[0].strip() if "=" in stripped else ""
            if key == name:
                removed = True
                continue
            kept.append(raw)
        path.write_text("\n".join(kept) + ("\n" if kept else ""), encoding="utf-8")
        return {"status": "ok", "removed": removed, "name": name, "file": path.name}


def _differs(left: EnvVar, right: EnvVar) -> bool:
    if left.secret or right.secret:
        return (left.value == "") != (right.value == "")
    return left.value != right.value


def _valid_env_name(name: str) -> bool:
    import re

    return bool(re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,127}", str(name or "")))


# ── Local environment detection ────────────────────────────────────────────────


@dataclass
class ToolInfo:
    available: bool = False
    version: str = ""
    path: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"available": self.available, "version": self.version}


class EnvironmentDetector:
    """Probe the local machine for runtime/tool availability. Non-sensitive only."""

    #: tool key → a bounded argv that prints its version.
    _PROBES: dict[str, tuple[str, ...]] = {
        "node": ("node", "--version"),
        "npm": ("npm", "--version"),
        "pnpm": ("pnpm", "--version"),
        "yarn": ("yarn", "--version"),
        "bun": ("bun", "--version"),
        "python": ("python", "--version"),
        "python3": ("python3", "--version"),
        "pip": ("pip", "--version"),
        "uv": ("uv", "--version"),
        "poetry": ("poetry", "--version"),
        "cargo": ("cargo", "--version"),
        "rustc": ("rustc", "--version"),
        "go": ("go", "version"),
        "java": ("java", "-version"),
        "mvn": ("mvn", "-version"),
        "gradle": ("gradle", "--version"),
        "dotnet": ("dotnet", "--version"),
        "git": ("git", "--version"),
        "docker": ("docker", "--version"),
        "podman": ("podman", "--version"),
        "docker-compose": ("docker-compose", "--version"),
        "kubectl": ("kubectl", "version", "--client", "--short"),
        "helm": ("helm", "version", "--short"),
        "terraform": ("terraform", "version"),
        "aws": ("aws", "--version"),
        "az": ("az", "version"),
        "gcloud": ("gcloud", "--version"),
    }

    def __init__(self, *, probe_timeout_s: float = 4.0) -> None:
        self._timeout = probe_timeout_s
        self._cache: Optional[dict[str, ToolInfo]] = None

    def detect(self, *, cache: bool = True) -> dict[str, Any]:
        if cache and self._cache is None:
            self._cache = self._probe_all()
        tools = self._cache if self._cache is not None else self._probe_all()
        return {
            "os": {"name": platform.system(), "release": platform.release(), "version": platform.version()},
            "architecture": platform.machine(),
            "platform": platform.platform(),
            "shell": self._detect_shell(),
            "pythonRuntime": platform.python_version(),
            "tools": {name: info.to_dict() for name, info in tools.items()},
        }

    def tool(self, name: str) -> ToolInfo:
        if self._cache is None:
            self._cache = self._probe_all()
        return self._cache.get(name, ToolInfo())

    def invalidate(self) -> None:
        self._cache = None

    def _probe_all(self) -> dict[str, ToolInfo]:
        # Probes run in parallel where cheap: each is a bounded subprocess. We keep
        # it simple and sequential over the small table; the discovery cache means
        # this runs once per process, not per call.
        return {name: self._probe(argv) for name, argv in self._PROBES.items()}

    def _probe(self, argv: tuple[str, ...]) -> ToolInfo:
        exe = shutil.which(argv[0])
        if not exe:
            return ToolInfo(available=False)
        try:
            completed = subprocess.run(
                list(argv), capture_output=True, timeout=self._timeout, shell=False,
            )
            raw = (completed.stdout or b"") + (completed.stderr or b"")
            text = raw.decode("utf-8", "replace").strip()
            version = _first_version_line(text)
            return ToolInfo(available=completed.returncode == 0 or bool(text), version=version, path=exe)
        except (OSError, subprocess.SubprocessError):
            return ToolInfo(available=True, version="", path=exe)

    def _detect_shell(self) -> str:
        if os.name == "nt":
            return os.environ.get("COMSPEC", "cmd.exe")
        return os.environ.get("SHELL", "/bin/sh")


def _first_version_line(text: str) -> str:
    for line in (text or "").splitlines():
        line = line.strip()
        if line:
            return line[:200]
    return ""


__all__ = [
    "EnvVar",
    "EnvironmentDetector",
    "EnvironmentManager",
    "EnvironmentReport",
    "MASK",
    "ToolInfo",
    "is_secret_name",
]
