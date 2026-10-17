"""Account linking — turning an external account into a verified binding.

The link flow:

  1. A signed-in Eclipse user mints a short-lived code in Settings › Connections
     (`create_link_code`), choosing the channel kind and the control scope.
  2. The user sends `/link <code>` from the external account.
  3. `claim_link_code` validates the code (kind match, unexpired, unused), consumes
     it atomically, and writes a `ChannelBinding` for that external account.

Because the code is minted only by an authenticated Eclipse session and is
single-use, a spoofed sender cannot create a binding for themselves.
"""

from __future__ import annotations

import secrets
import string
from datetime import datetime, timedelta, timezone
from typing import Optional

from ..persistence import now_iso
from .config import link_code_ttl_seconds
from .model import ChannelBinding, LinkCode, scope_rank
from .store import ChannelStore

_ALPHABET = string.ascii_uppercase + string.digits
_CODE_LEN = 8


def _utc_plus(seconds: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(seconds=seconds)).isoformat()


def _expired(iso: str) -> bool:
    try:
        when = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        return when <= datetime.now(timezone.utc)
    except (TypeError, ValueError):
        return True


def generate_code() -> str:
    return "".join(secrets.choice(_ALPHABET) for _ in range(_CODE_LEN))


def create_link_code(
    store: ChannelStore,
    *,
    kind: str,
    user_id: Optional[str],
    tenant_id: Optional[str],
    scope: str,
    ttl_s: Optional[int] = None,
) -> LinkCode:
    """Mint a single-use linking code. The caller must be an authorised operator."""
    code = generate_code()
    ttl = ttl_s if ttl_s is not None else link_code_ttl_seconds()
    return store.create_link_code(
        code=code, kind=kind, user_id=user_id, tenant_id=tenant_id,
        scope=scope, expires_at=_utc_plus(ttl),
    )


def claim_link_code(
    store: ChannelStore,
    *,
    kind: str,
    code: str,
    external_id: str,
    external_chat: str,
    display_name: str = "",
) -> tuple[Optional[ChannelBinding], str]:
    """Claim a code for an external account.

    Returns `(binding, "")` on success, or `(None, reason)` on failure. Failure
    reasons are user-safe (never leak whether a code exists for another kind).
    """
    candidate = store.get_link_code(str(code or "").upper().strip())
    if candidate is None:
        return None, "That link code was not found. Generate a new one in Eclipse."
    if scope_rank(candidate.scope) < 0:
        return None, "That link code has an invalid scope."
    if candidate.used_at:
        return None, "That link code was already used."
    if _expired(candidate.expires_at):
        return None, "That link code has expired. Generate a new one in Eclipse."
    if candidate.kind != kind:
        return None, f"That link code is for a different channel ({candidate.kind})."
    if not store.consume_link_code(candidate.code):
        return None, "That link code was already used."
    binding = store.upsert_binding(
        kind=kind,
        external_id=external_id,
        external_chat=external_chat,
        display_name=display_name,
        user_id=candidate.user_id,
        tenant_id=candidate.tenant_id,
        scope=candidate.scope,
    )
    return binding, ""


def touch(store: ChannelStore, binding: ChannelBinding) -> None:
    store.touch_binding(binding.id)


__all__ = ["claim_link_code", "create_link_code", "generate_code", "touch"]
