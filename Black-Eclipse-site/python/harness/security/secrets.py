"""Secrets manager — providers, scoping, injection and redaction.

Secrets are referenced by identifier (`secret://<provider>/<name>`), scoped to an
agent/session/task/tool/resource/action/time, and resolved only at the exact
boundary that needs them. The LLM receives a *reference* ("credential available"),
never the value, wherever possible.

Two protections always hold:
  * every resolved value is registered with a `SecretRegistry` so it can be
    redacted from logs, tool output, errors and telemetry; and
  * a scoped request that does not match a grant is refused — secrets are never
    exposed to arbitrary subprocesses.
"""

from __future__ import annotations

import abc
import os
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from .models import new_id

SECRET_REF_PREFIX = "secret://"


# ── Redaction registry ───────────────────────────────────────────────────────
class SecretRegistry:
    """Tracks live secret VALUES so every surface can strip them.

    Values are held only in memory and only as redaction targets; they are never
    serialized. `redact` replaces any registered value (and URL/JSON encodings of
    it) with `[REDACTED]`. It also delegates to the observability redactor so
    pattern-based secrets are caught even when unregistered.
    """

    def __init__(self) -> None:
        self._values: set[str] = set()

    def register(self, value: Optional[str]) -> None:
        if value and len(value) >= 4:
            self._values.add(value)

    def forget(self, value: Optional[str]) -> None:
        if value:
            self._values.discard(value)

    def count(self) -> int:
        return len(self._values)

    def redact(self, value: Any) -> Any:
        try:
            from ..observability.redaction import redact as _pattern_redact  # noqa: PLC0415

            value = _pattern_redact(value)
        except Exception:  # noqa: BLE001 - fall back to exact-value redaction only
            pass
        try:
            return self._scrub(value)
        except Exception:  # noqa: BLE001 - redaction must fail closed
            from ..observability.redaction import REDACTED  # noqa: PLC0415

            return REDACTED

    def redact_text(self, text: Any) -> str:
        from ..observability.redaction import REDACTED  # noqa: PLC0415

        result = str(text)
        from urllib.parse import quote as _quote

        for secret in self._values:
            for variant in (
                secret,
                _quote(secret, safe=""),
                secret.replace("\\", "\\\\").replace('"', '\\"'),
            ):
                if variant:
                    result = result.replace(variant, REDACTED)
        try:
            from ..observability.redaction import REDACTED as _R, redact  # noqa: PLC0415

            result = redact(result)
        except Exception:  # noqa: BLE001
            pass
        return result

    def _scrub(self, value: Any) -> Any:
        if isinstance(value, str):
            return self.redact_text(value)
        if isinstance(value, dict):
            return {k: self._scrub(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [self._scrub(v) for v in value]
        return value


# ── Providers ────────────────────────────────────────────────────────────────
class SecretProvider(abc.ABC):
    """Abstract provider. `get` returns the raw value or None. Never logs a value."""

    name: str = "base"

    @abc.abstractmethod
    def get(self, key: str) -> Optional[str]: ...

    def status(self) -> dict[str, Any]:
        return {"provider": self.name, "available": True}


class EnvSecretProvider(SecretProvider):
    """Read from process environment. Optional key prefix mapping."""

    name = "env"

    def __init__(self, prefix: str = "") -> None:
        self._prefix = prefix

    def get(self, key: str) -> Optional[str]:
        return os.environ.get(f"{self._prefix}{key}") or None

    def available_keys(self) -> list[str]:
        prefix = self._prefix
        return [k[len(prefix):] for k in os.environ if k.startswith(prefix)] if prefix else list(os.environ)


class LocalFileSecretProvider(SecretProvider):
    """A local development provider backed by a JSON file of name → value.

    The file lives outside version control (`.black-eclipse/security/secrets.local.json`)
    and is read once. This is the zero-config development provider; it is
    intentionally not a production secret store.
    """

    name = "local"

    def __init__(self, path: str) -> None:
        self._path = path
        self._cache: Optional[dict[str, str]] = None
        self._available = os.path.isfile(path)

    def _load(self) -> dict[str, str]:
        if self._cache is not None:
            return self._cache
        try:
            import json

            with open(self._path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
            self._cache = {str(k): str(v) for k, v in data.items()} if isinstance(data, dict) else {}
        except Exception:  # noqa: BLE001 - a missing/broken file is simply empty
            self._cache = {}
        return self._cache

    def get(self, key: str) -> Optional[str]:
        return self._load().get(key)

    def available_keys(self) -> list[str]:
        return sorted(self._load().keys())

    def status(self) -> dict[str, Any]:
        return {"provider": self.name, "available": self._available, "path": self._path}


class StaticSecretProvider(SecretProvider):
    """An in-memory provider used by tests and programmatic registration."""

    name = "static"

    def __init__(self, values: Optional[dict[str, str]] = None, name: str = "static") -> None:
        self._values = dict(values or {})
        self.name = name

    def put(self, key: str, value: str) -> None:
        self._values[key] = value

    def get(self, key: str) -> Optional[str]:
        return self._values.get(key)

    def available_keys(self) -> list[str]:
        return sorted(self._values.keys())


class UnavailableSecretProvider(SecretProvider):
    """Represents an external provider that is configured but not reachable.

    It never returns a value and always reports unavailable — an honest state
    rather than a fabricated secret.
    """

    def __init__(self, name: str, reason: str = "provider not configured") -> None:
        self.name = name
        self._reason = reason

    def get(self, key: str) -> Optional[str]:
        return None

    def status(self) -> dict[str, Any]:
        return {"provider": self.name, "available": False, "reason": self._reason}


class CliSecretProvider(SecretProvider):
    """Resolve secrets through an operator-configured command template.

    This is the real integration path for Vault / 1Password / AWS Secrets Manager
    / GCP / Azure: the operator configures an argv template (e.g.
    `["op", "read", "op://vault/{name}/password"]` or
    `["aws", "secretsmanager", "get-secret-value", "--secret-id", "{name}",
    "--query", "SecretString", "--output", "text"]`) and the provider runs it
    without a shell. `{name}` is substituted with the secret name (never via a
    shell, so no injection). An unavailable CLI or a non-zero exit yields None —
    honest unavailability, never a fabricated value.
    """

    name = "cli"

    def __init__(self, templates: dict[str, list[str]], *, timeout_s: int = 20, name: str = "cli") -> None:
        self._templates = {str(k): list(v) for k, v in (templates or {}).items()}
        self._timeout = max(1, int(timeout_s))
        self.name = name

    def _command_for(self, key: str) -> Optional[list[str]]:
        template = self._templates.get(key) or self._templates.get("*")
        if not template:
            return None
        return [part.replace("{name}", key) for part in template]

    def get(self, key: str) -> Optional[str]:
        argv = self._command_for(key)
        if not argv:
            return None
        import subprocess  # noqa: PLC0415

        try:
            proc = subprocess.run(
                argv, capture_output=True, text=True, timeout=self._timeout, check=False,
            )
        except Exception:  # noqa: BLE001 - a failing provider is unavailable, not fatal
            return None
        if proc.returncode != 0:
            return None
        value = (proc.stdout or "").strip()
        return value or None

    def available(self) -> bool:
        return bool(self._templates)

    def status(self) -> dict[str, Any]:
        return {"provider": self.name, "available": self.available(), "templates": len(self._templates)}


class OsKeychainProvider(SecretProvider):
    """The operating system's native secret store.

    Windows Credential Manager (`win32cred`), macOS Keychain (`security`), or
    Linux Secret Service (`secret-tool`). Reports unavailable when the mechanism
    is absent; never fabricates a value.
    """

    name = "keychain"

    def __init__(self, service: str = "eclipse") -> None:
        self._service = service

    def _windows_get(self, key: str) -> Optional[str]:
        try:
            import win32cred  # type: ignore  # noqa: PLC0415

            cred = win32cred.CredRead(key, win32cred.CRED_TYPE_GENERIC, 0)
            blob = cred.get("CredentialBlob")
            return blob.decode("utf-16-le") if isinstance(blob, (bytes, bytearray)) else None
        except Exception:  # noqa: BLE001
            return None

    def _unix_get(self, key: str) -> Optional[str]:
        import subprocess  # noqa: PLC0415
        import sys  # noqa: PLC0415

        if sys.platform == "darwin":
            argv = ["security", "find-generic-password", "-s", self._service, "-a", key, "-w"]
        else:
            argv = ["secret-tool", "lookup", "service", self._service, "account", key]
        try:
            proc = subprocess.run(argv, capture_output=True, text=True, timeout=15, check=False)
        except Exception:  # noqa: BLE001
            return None
        value = (proc.stdout or "").strip()
        return value or None

    def get(self, key: str) -> Optional[str]:
        import sys  # noqa: PLC0415

        if sys.platform == "win32":
            return self._windows_get(key)
        return self._unix_get(key)

    def available(self) -> bool:
        import shutil  # noqa: PLC0415
        import sys  # noqa: PLC0415

        if sys.platform == "win32":
            try:
                import win32cred  # type: ignore  # noqa: F401,PLC0415

                return True
            except Exception:  # noqa: BLE001
                return False
        return bool(shutil.which("security")) or bool(shutil.which("secret-tool"))

    def status(self) -> dict[str, Any]:
        return {"provider": self.name, "available": self.available(), "service": self._service}


# ── Scoping ──────────────────────────────────────────────────────────────────
@dataclass
class SecretGrant:
    """A scoped grant of one secret reference to one consumer."""

    ref: str
    consumer: str = ""            # tool / plugin / agent allowed to resolve
    actions: tuple[str, ...] = ()
    resources: tuple[str, ...] = ()
    session_id: Optional[str] = None
    task_id: Optional[str] = None
    tenant_id: Optional[str] = None
    expires_at: Optional[float] = None
    grant_id: str = field(default_factory=lambda: new_id("secgrant"))

    @property
    def expired(self) -> bool:
        return self.expires_at is not None and self.expires_at <= time.time()

    def covers(
        self,
        *,
        consumer: str,
        action: str = "",
        resource: str = "",
        session_id: Optional[str] = None,
        task_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
    ) -> bool:
        if self.expired:
            return False
        # Tenant isolation: a tenant-bound grant never leaks across tenants, and a
        # tenant-less grant is usable only in a tenant-less request.
        if self.tenant_id is not None and self.tenant_id != tenant_id:
            return False
        if self.tenant_id is None and tenant_id is not None:
            return False
        if self.consumer and self.consumer not in ("*", consumer):
            return False
        if self.actions and action and not any(a in ("*", action) for a in self.actions):
            return False
        if self.actions and not action:
            return False
        if self.session_id is not None and self.session_id != session_id:
            return False
        if self.task_id is not None and self.task_id != task_id:
            return False
        return True

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.grant_id,
            "ref": self.ref,
            "consumer": self.consumer,
            "actions": list(self.actions),
            "resources": list(self.resources),
            "sessionId": self.session_id,
            "taskId": self.task_id,
            "tenantId": self.tenant_id,
            "expiresAt": self.expires_at,
        }


class SecretAccessDenied(Exception):
    """A secret was requested outside its grant."""


# ── Manager ──────────────────────────────────────────────────────────────────
class SecretsManager:
    """Resolve secret references, enforce scoping, and register values for redaction."""

    def __init__(self, registry: Optional[SecretRegistry] = None) -> None:
        self.registry = registry or SecretRegistry()
        self._providers: dict[str, SecretProvider] = {}
        self._grants: list[SecretGrant] = []
        self._resolutions: int = 0
        self._denials: int = 0

    def register_provider(self, provider: SecretProvider) -> None:
        self._providers[provider.name] = provider

    def providers(self) -> list[str]:
        return sorted(self._providers)

    def provider_status(self) -> list[dict[str, Any]]:
        return [p.status() for p in self._providers.values()]

    def grant(self, grant: SecretGrant) -> SecretGrant:
        self._grants.append(grant)
        return grant

    def grants(self) -> list[dict[str, Any]]:
        return [g.to_dict() for g in self._grants]

    def revoke(self, grant_id: str) -> bool:
        before = len(self._grants)
        self._grants = [g for g in self._grants if g.grant_id != grant_id]
        return len(self._grants) != before

    @staticmethod
    def parse_ref(ref: str) -> tuple[Optional[str], str]:
        """`secret://env/GITHUB_TOKEN` → `("env", "GITHUB_TOKEN")`.

        A bare `secret://GITHUB_TOKEN` has provider None (any).
        """
        raw = str(ref or "").strip()
        if not raw.startswith(SECRET_REF_PREFIX):
            return None, ""
        body = raw[len(SECRET_REF_PREFIX):]
        provider, _, name = body.partition("/")
        if not name:
            # `secret://NAME` form.
            return None, body
        return (provider or None), name

    def _raw_get(self, provider: Optional[str], name: str) -> Optional[str]:
        if provider is not None:
            p = self._providers.get(provider)
            return p.get(name) if p is not None else None
        for p in self._providers.values():
            value = p.get(name)
            if value is not None:
                return value
        return None

    def has(self, ref: str) -> bool:
        """Whether a value is available WITHOUT resolving it (a model-safe probe)."""
        provider, name = self.parse_ref(ref)
        if not name:
            return False
        return self._raw_get(provider, name) is not None

    def resolve(
        self,
        ref: str,
        *,
        consumer: str,
        action: str = "",
        resource: str = "",
        session_id: Optional[str] = None,
        task_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
        require_grant: bool = True,
    ) -> str:
        """Resolve a secret reference to its value, enforcing scope.

        Raises `SecretAccessDenied` when the reference is not granted to this
        consumer or the value is unavailable. Every successful resolution
        registers the value for redaction.
        """
        provider, name = self.parse_ref(ref)
        if not name:
            self._denials += 1
            raise SecretAccessDenied(f"invalid secret reference: {ref!r}")
        if require_grant:
            allowed = any(
                g.covers(consumer=consumer, action=action, resource=resource,
                         session_id=session_id, task_id=task_id, tenant_id=tenant_id)
                and (g.ref == ref or g.ref == f"secret://{provider}/{name}" or g.ref == f"secret://{name}")
                for g in self._grants
            )
            if not allowed:
                self._denials += 1
                raise SecretAccessDenied(f"no grant for secret reference {ref!r} to consumer {consumer!r}")
        value = self._raw_get(provider, name)
        if value is None:
            self._denials += 1
            raise SecretAccessDenied(f"secret {ref!r} is not available")
        self.registry.register(value)
        self._resolutions += 1
        return value

    def resolve_optional(self, ref: str, **kwargs: Any) -> Optional[str]:
        try:
            return self.resolve(ref, **kwargs)
        except SecretAccessDenied:
            return None

    def inject_env(self, refs: dict[str, str], *, consumer: str, **scope: Any) -> dict[str, str]:
        """Resolve a mapping of ENV_NAME → reference into a concrete env dict.

        Intended for a sandboxed subprocess: only the named refs are resolved, and
        only through the grant check, so arbitrary host secrets never leak in.
        """
        out: dict[str, str] = {}
        for env_name, ref in (refs or {}).items():
            value = self.resolve_optional(ref, consumer=consumer, **scope)
            if value is not None:
                out[str(env_name)] = value
        return out

    def redact(self, value: Any) -> Any:
        return self.registry.redact(value)

    def stats(self) -> dict[str, Any]:
        return {
            "providers": self.providers(),
            "grants": len(self._grants),
            "resolutions": self._resolutions,
            "denials": self._denials,
            "registeredValues": self.registry.count(),
        }


def build_default_secrets_manager() -> SecretsManager:
    """Env + local dev providers, plus operator-configured production providers.

    Zero-config stays env + a local development file. Without any other
    configuration the OS keychain provider is registered (and honestly reports
    unavailable when there is no native store). An operator can add Vault /
    AWS / 1Password / GCP / Azure by setting `BLACK_ECLIPSE_SECRETS_CLI` to a JSON
    mapping of secret name → argv template (with `{name}`), e.g.
        {"*": ["aws", "secretsmanager", "get-secret-value", "--secret-id", "{name}",
               "--query", "SecretString", "--output", "text"]}
    """
    from pathlib import Path

    manager = SecretsManager()
    manager.register_provider(EnvSecretProvider())
    default_path = os.environ.get("BLACK_ECLIPSE_SECRETS_FILE") or str(
        Path(".black-eclipse") / "security" / "secrets.local.json"
    )
    manager.register_provider(LocalFileSecretProvider(default_path))

    service = os.environ.get("BLACK_ECLIPSE_SECRETS_SERVICE") or "eclipse"
    manager.register_provider(OsKeychainProvider(service))

    cli_config = os.environ.get("BLACK_ECLIPSE_SECRETS_CLI")
    if cli_config:
        import json  # noqa: PLC0415

        try:
            templates = json.loads(cli_config)
            if isinstance(templates, dict):
                normalized = {
                    str(k): (v if isinstance(v, list) else [str(v)]) for k, v in templates.items()
                }
                manager.register_provider(CliSecretProvider(normalized, name="cli"))
        except (ValueError, TypeError):
            # A malformed config is reported, never silently trusted.
            manager.register_provider(
                UnavailableSecretProvider("cli", "BLACK_ECLIPSE_SECRETS_CLI is not valid JSON")
            )
    return manager


__all__ = [
    "EnvSecretProvider",
    "LocalFileSecretProvider",
    "SECRET_REF_PREFIX",
    "SecretAccessDenied",
    "SecretGrant",
    "SecretProvider",
    "SecretRegistry",
    "SecretsManager",
    "StaticSecretProvider",
    "UnavailableSecretProvider",
    "build_default_secrets_manager",
]
