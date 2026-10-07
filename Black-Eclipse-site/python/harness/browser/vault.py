"""The Browser Vault.

Stores credential REFERENCES, never plaintext. A credential is referenced as
``vault://<scope>/<name>``; the runtime resolves the reference INTERNALLY at fill
time and the model only ever sees the reference. When Eclipse already holds the
secret in its encrypted vault tier (the same tier MCP secrets use), the browser
vault delegates resolution to it through the authenticated, read-only bridge —
this module never invents plaintext credential storage.

The vault metadata (which references exist for a profile) is content-free and
persisted on the ONE agent-memory connection via `store.py`; only a resolver
returns a value, and only to the caller filling a form field.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Optional

# A credential reference: `vault://<scope>/<name>`.
_REF_RE = re.compile(r"^vault://([A-Za-z0-9_.\-]{1,64})/([A-Za-z0-9_.\-]{1,128})$")

SecretResolver = Callable[[str], Awaitable[Optional[str]]]


def is_credential_reference(value: str) -> bool:
    return bool(_REF_RE.match(value or ""))


def parse_reference(reference: str) -> Optional[tuple[str, str]]:
    """Return ``(scope, name)`` for a well-formed reference, else None."""
    match = _REF_RE.match(reference or "")
    if not match:
        return None
    return match.group(1), match.group(2)


@dataclass
class VaultEntry:
    """One stored credential reference (never a value)."""

    reference: str
    scope: str
    name: str
    kind: str = "password"  # password | username | totp | api_key | token
    username: str = ""
    profile_id: str = ""
    origin: str = ""  # the site the credential belongs to (host or URL)
    created_at: str = ""

    def to_dict(self, *, include_username: bool = True) -> dict[str, Any]:
        data = {
            "reference": self.reference,
            "scope": self.scope,
            "name": self.name,
            "kind": self.kind,
            "origin": self.origin,
            "profileId": self.profile_id,
            "createdAt": self.created_at,
        }
        # A username is not a secret in the same tier as a password, but it is
        # still personal; omit it from a model-facing listing by default.
        if include_username:
            data["username"] = self.username
        return data


class BrowserVault:
    """Resolves credential references without ever exposing a value to the model.

    The resolver is injected (the process-wide bridge in production, a fake in
    tests). When no resolver is available, resolution returns None and the caller
    reports an honest ``BROWSER_AUTHENTICATION_FAILED`` — never a fabricated
    credential.
    """

    def __init__(self, store: Any = None, resolver: Optional[SecretResolver] = None) -> None:
        self._store = store
        self._resolver = resolver

    def set_resolver(self, resolver: Optional[SecretResolver]) -> None:
        self._resolver = resolver

    async def resolve(self, reference: str) -> Optional[str]:
        """Resolve a reference to its value, or None.

        The value is returned to the CALLER ONLY (a fill operation). It is never
        logged, never emitted in an event, and never returned through a tool's
        text/data payload.
        """
        parsed = parse_reference(reference)
        if parsed is None:
            return None
        if self._resolver is None:
            return None
        scope, name = parsed
        try:
            # The MCP secret namespace is Eclipse's existing encrypted vault tier;
            # a browser credential uses the same tier under a `browser/<scope>/<name>`
            # key so both share one storage mechanism.
            return await self._resolver(f"browser/{scope}/{name}")
        except Exception:  # noqa: BLE001 - an unreachable vault is not a value
            return None

    # -- metadata (no values) ------------------------------------------------

    def list_entries(self, profile_id: Optional[str] = None) -> list[dict[str, Any]]:
        if self._store is None:
            return []
        return self._store.list_vault_entries(profile_id)

    def save_entry(
        self,
        *,
        reference: str,
        kind: str = "password",
        username: str = "",
        profile_id: str = "",
        origin: str = "",
    ) -> dict[str, Any]:
        """Record a credential REFERENCE's metadata. Never stores a value."""
        parsed = parse_reference(reference)
        if parsed is None:
            raise ValueError("reference must look like vault://<scope>/<name>")
        scope, name = parsed
        entry = VaultEntry(
            reference=reference, scope=scope, name=name, kind=kind,
            username=username, profile_id=profile_id, origin=origin,
        )
        if self._store is not None:
            self._store.save_vault_entry(entry)
        return entry.to_dict()


__all__ = ["BrowserVault", "SecretResolver", "VaultEntry", "is_credential_reference", "parse_reference"]
