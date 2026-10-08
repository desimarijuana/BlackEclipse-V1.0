"""Per-plugin secret storage, encrypted at rest.

Secrets are encrypted with a key stored outside the database (a 0600 key file
under the plugin root). A plugin can only read its OWN secrets, and only when it
declared the `secrets` permission. Values are never logged, never returned in a
listing (only names/presence), and never placed into the database in plaintext.

When the `cryptography` package is unavailable the store reports itself
unavailable honestly (`SecretsUnavailable`) rather than storing plaintext.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path
from typing import Any, Optional

from .errors import PluginError
from .paths import ensure_dir, secret_key_path


class SecretsUnavailable(PluginError):
    def __init__(self, reason: str) -> None:
        super().__init__("PLUGIN_SECRETS_UNAVAILABLE", reason)


class SecretNotFound(PluginError):
    def __init__(self, plugin_id: str, name: str) -> None:
        super().__init__(
            "PLUGIN_SECRET_NOT_FOUND",
            f"plugin {plugin_id!r} has no secret named {name!r}",
            detail={"plugin_id": plugin_id, "name": name},
        )


def _load_fernet(path: Path):
    try:
        from cryptography.fernet import Fernet  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001 - a missing crypto lib is a supported state
        raise SecretsUnavailable(
            "the 'cryptography' package is not installed; plugin secrets are unavailable"
        ) from exc

    key_path = path
    if key_path.exists():
        key = key_path.read_bytes().strip()
    else:
        key = Fernet.generate_key()
        ensure_dir(key_path.parent)
        key_path.write_bytes(key)
        try:
            os.chmod(key_path, stat.S_IRUSR | stat.S_IWUSR)
        except Exception:  # noqa: BLE001 - best-effort on platforms without POSIX perms
            pass
    try:
        return Fernet(key)
    except Exception as exc:  # noqa: BLE001 - a corrupt key is an honest failure
        raise SecretsUnavailable(f"the plugin secret key is invalid: {exc}") from exc


class PluginSecrets:
    """Encrypted secret access scoped per plugin."""

    def __init__(self, store: Any, key_path: Optional[Path] = None) -> None:
        self._store = store
        self._key_path = key_path or secret_key_path()
        self._fernet = _load_fernet(self._key_path)

    def set(self, plugin_id: str, name: str, value: str) -> None:
        token = self._fernet.encrypt(str(value).encode("utf-8")).decode("ascii")
        self._store.set_secret(plugin_id, name, token)

    def get(self, plugin_id: str, name: str) -> Optional[str]:
        token = self._store.get_secret_ciphertext(plugin_id, name)
        if token is None:
            return None
        try:
            return self._fernet.decrypt(token.encode("ascii")).decode("utf-8")
        except Exception as exc:  # noqa: BLE001 - a decrypt failure must not leak
            raise SecretsUnavailable(f"stored secret {name!r} could not be decrypted") from exc

    def require(self, plugin_id: str, name: str) -> str:
        value = self.get(plugin_id, name)
        if value is None:
            raise SecretNotFound(plugin_id, name)
        return value

    def names(self, plugin_id: str) -> list[str]:
        return self._store.list_secret_names(plugin_id)

    def has(self, plugin_id: str, name: str) -> bool:
        return self._store.get_secret_ciphertext(plugin_id, name) is not None

    def delete(self, plugin_id: str, name: str) -> None:
        self._store.delete_secret(plugin_id, name)


class UnavailableSecrets:
    """A stand-in used when the secret backend cannot be initialized.

    Every operation raises `SecretsUnavailable`, so a plugin that needs a secret
    gets an honest error instead of a None or a plaintext fallback.
    """

    def __init__(self, reason: str) -> None:
        self._reason = reason

    def set(self, plugin_id: str, name: str, value: str) -> None:
        raise SecretsUnavailable(self._reason)

    def get(self, plugin_id: str, name: str) -> Optional[str]:
        raise SecretsUnavailable(self._reason)

    def require(self, plugin_id: str, name: str) -> str:
        raise SecretsUnavailable(self._reason)

    def names(self, plugin_id: str) -> list[str]:
        raise SecretsUnavailable(self._reason)

    def has(self, plugin_id: str, name: str) -> bool:
        raise SecretsUnavailable(self._reason)

    def delete(self, plugin_id: str, name: str) -> None:
        raise SecretsUnavailable(self._reason)


def redact(value: Any) -> str:
    """A safe representation of a secret for logs (never the value)."""
    if value is None:
        return "<unset>"
    return f"<redacted:{len(str(value))} chars>"


__all__ = [
    "PluginSecrets",
    "UnavailableSecrets",
    "SecretsUnavailable",
    "SecretNotFound",
    "redact",
]
