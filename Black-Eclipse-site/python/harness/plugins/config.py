"""Plugin configuration: a typed, validated, namespaced view over stored values.

A plugin declares `configuration` fields in its manifest. The manager merges the
declared defaults with the stored values, validates each against its declared
type/enum, and hands the plugin a read-only mapping. Writes go through
`validate()` first, so an out-of-range or wrong-typed value is rejected before it
is persisted — never silently coerced.

`secret`-typed fields are NOT stored here; their values live in the encrypted
secret store (see `secrets.py`). The config layer only reports their presence.
"""

from __future__ import annotations

from typing import Any, Optional

from .errors import PluginError
from .manifest import ConfigField, PluginManifest


class ConfigInvalid(PluginError):
    def __init__(self, message: str, *, detail: Optional[dict[str, Any]] = None) -> None:
        super().__init__("PLUGIN_CONFIG_INVALID", message, detail=detail)


def _coerce(field: ConfigField, value: Any) -> Any:
    """Validate and normalize one value against a field declaration."""
    if value is None:
        if field.required:
            raise ConfigInvalid(f"configuration key {field.key!r} is required")
        return None
    t = field.type
    try:
        if t == "boolean":
            if isinstance(value, bool):
                return value
            if isinstance(value, str) and value.strip().lower() in ("true", "false"):
                return value.strip().lower() == "true"
            raise ConfigInvalid(f"{field.key!r} must be a boolean")
        if t == "number":
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ConfigInvalid(f"{field.key!r} must be a number")
            return value
        if t in ("string", "secret"):
            if not isinstance(value, str):
                raise ConfigInvalid(f"{field.key!r} must be a string")
            return value
        if t == "enum":
            if value not in (field.enum or []):
                raise ConfigInvalid(f"{field.key!r} must be one of {field.enum}")
            return value
        if t == "array":
            if not isinstance(value, list):
                raise ConfigInvalid(f"{field.key!r} must be an array")
            return value
        if t == "object":
            if not isinstance(value, dict):
                raise ConfigInvalid(f"{field.key!r} must be an object")
            return value
    except ConfigInvalid:
        raise
    except Exception as exc:  # pragma: no cover - defensive
        raise ConfigInvalid(f"{field.key!r} is invalid: {exc}") from exc
    raise ConfigInvalid(f"{field.key!r} has unsupported type {t!r}")


class PluginConfig:
    """The resolved configuration for one plugin instance."""

    def __init__(self, manifest: PluginManifest, values: dict[str, Any]) -> None:
        self._manifest = manifest
        self._fields = {f.key: f for f in manifest.configuration}
        self._values = values

    @property
    def fields(self) -> list[ConfigField]:
        return list(self._manifest.configuration)

    def get(self, key: str, default: Any = None) -> Any:
        if key not in self._fields:
            raise ConfigInvalid(f"configuration key {key!r} is not declared by this plugin")
        if key in self._values:
            return self._values[key]
        field = self._fields[key]
        return field.default if field.default is not None else default

    def all(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for field in self._manifest.configuration:
            if field.type == "secret":
                continue  # values live in the secret store, never here
            out[field.key] = self.get(field.key)
        return out

    def public_view(self, secret_presence: set[str] | None = None) -> dict[str, Any]:
        """A UI-facing view: field metadata + values (secrets as presence only)."""
        present = secret_presence or set()
        return {
            "fields": [
                {
                    "key": f.key,
                    "type": f.type,
                    "title": f.title or f.key,
                    "description": f.description,
                    "required": f.required,
                    "enum": f.enum,
                    "set": (f.key in present) if f.type == "secret" else (self.get(f.key) is not None),
                    "value": None if f.type == "secret" else self.get(f.key),
                }
                for f in self._manifest.configuration
            ]
        }


def validate_values(manifest: PluginManifest, values: dict[str, Any]) -> dict[str, Any]:
    """Validate a partial patch of config values; unknown keys are refused."""
    fields = {f.key: f for f in manifest.configuration}
    unknown = sorted(set(values) - set(fields))
    if unknown:
        raise ConfigInvalid(f"unknown configuration key(s): {', '.join(unknown)}")
    clean: dict[str, Any] = {}
    for key, value in values.items():
        clean[key] = _coerce(fields[key], value)
    return clean


def resolve(manifest: PluginManifest, stored: dict[str, Any]) -> PluginConfig:
    """Merge stored values with declared defaults and validate the result."""
    values: dict[str, Any] = {}
    for field in manifest.configuration:
        if field.type == "secret":
            continue
        if field.key in stored:
            values[field.key] = _coerce(field, stored[field.key])
        elif field.default is not None:
            values[field.key] = _coerce(field, field.default)
        elif field.required:
            raise ConfigInvalid(f"configuration key {field.key!r} is required but not set")
    return PluginConfig(manifest, values)


__all__ = ["PluginConfig", "ConfigInvalid", "validate_values", "resolve"]
