"""Channel credential storage, encrypted at rest.

Channel credentials (bot tokens, SMTP/IMAP passwords, signing secrets, API
tokens) are encrypted with a Fernet key stored OUTSIDE the database in a 0600 key
file, mirroring the Plugin Platform's `secrets.py`. Only ciphertext is written to
`agent-memory.db`; a value is never logged, never returned in a listing (only its
NAME), and never placed in the config JSON once saved through the vault.

When `cryptography` is unavailable the vault reports itself unavailable and the
service falls back to the legacy literal config (zero-config preserved), logging
that the credential is not encrypted at rest.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path
from typing import Optional

from .store import ChannelStore

REDACTED = "***"


class SecretUnavailable(RuntimeError):
    """The encrypted vault is not available (e.g. `cryptography` missing)."""


def default_key_path() -> Path:
    override = os.environ.get("BLACK_ECLIPSE_CHANNELS_SECRET_KEY")
    if override:
        return Path(override)
    return Path(".black-eclipse") / "channels" / "secret.key"


def _load_fernet(path: Path):
    from cryptography.fernet import Fernet  # noqa: PLC0415

    if path.exists():
        key = path.read_bytes().strip()
    else:
        key = Fernet.generate_key()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(key)
        try:
            os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
        except Exception:  # noqa: BLE001 - best-effort on non-POSIX platforms
            pass
    return Fernet(key)


class ChannelSecrets:
    """Encrypted per-channel secret access. Only ciphertext is persisted."""

    def __init__(self, store: ChannelStore, key_path: Optional[Path] = None) -> None:
        self._store = store
        self._key_path = key_path or default_key_path()
        self._fernet = None
        self._reason: Optional[str] = None
        try:
            self._fernet = _load_fernet(self._key_path)
        except Exception as exc:  # noqa: BLE001 - missing crypto is a supported state
            self._reason = str(exc)

    @property
    def available(self) -> bool:
        return self._fernet is not None

    @property
    def reason(self) -> Optional[str]:
        return self._reason

    def set(self, channel: str, name: str, value: str) -> None:
        if self._fernet is None:
            raise SecretUnavailable(self._reason or "encrypted vault unavailable")
        token = self._fernet.encrypt(str(value).encode("utf-8")).decode("ascii")
        self._store.set_secret(channel, name, token)

    def get(self, channel: str, name: str) -> Optional[str]:
        if self._fernet is None:
            return None
        token = self._store.get_secret_ciphertext(channel, name)
        if token is None:
            return None
        try:
            return self._fernet.decrypt(token.encode("ascii")).decode("utf-8")
        except Exception as exc:  # noqa: BLE001 - a decrypt failure must not leak
            raise SecretUnavailable(f"stored secret {name!r} could not be decrypted") from exc

    def names(self, channel: str) -> list[str]:
        return self._store.list_secret_names(channel)

    def delete(self, channel: str) -> int:
        return self._store.delete_secrets(channel)


__all__ = ["ChannelSecrets", "REDACTED", "SecretUnavailable", "default_key_path"]
