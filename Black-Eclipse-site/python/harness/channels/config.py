"""Channel Gateway configuration and secret handling.

Two concerns:

  1. Runtime flags for the subsystem itself (env-driven, zero-config safe).
  2. Resolving the model used by an autonomous channel agent turn, and the
     front-door callback URL — mirroring `automation/dispatcher.py` and
     `jobs/scheduler.py` so the channel path is not a second model adapter.

Secrets: a config value may be a literal OR a `secret://<provider>/<name>`
reference resolved through the Security Gateway's `SecretsManager` at send time.
`redact_config` never returns a value for a key whose name looks sensitive, so the
admin API can show presence/absence without ever echoing a credential.
"""

from __future__ import annotations

import os
from typing import Any, Optional

from ..schemas import ModelSettings

# Keys whose VALUE is never returned by the API. Matched case-insensitively on a
# substring, so `botToken`, `smtpPass`, `discordWebhookUrl` are all redacted.
_SENSITIVE_MARKERS = (
    "token",
    "secret",
    "password",
    "passwd",
    "pass",
    "key",
    "webhook",
    "credential",
)

# Substrings that mean a value is present-but-hidden when redacting.
REDACTED = "***"

# Bounded autonomous-turn budget for one binding (protects against a runaway
# loop from a chatty external account). Enforced by the service rate limiter.
DEFAULT_TURNS_PER_HOUR = 60


def channels_enabled() -> bool:
    """Whether the Channel Gateway is enabled at all (default ON)."""
    return os.environ.get("HARNESS_CHANNELS_ENABLED", "1") not in ("0", "false", "False")


def polling_enabled() -> bool:
    """Whether local long-poll providers run (default ON)."""
    return os.environ.get("HARNESS_CHANNELS_POLLING", "1") not in ("0", "false", "False")


def turns_per_hour() -> int:
    try:
        return max(1, int(os.environ.get("HARNESS_CHANNELS_TURNS_PER_HOUR", str(DEFAULT_TURNS_PER_HOUR))))
    except (TypeError, ValueError):
        return DEFAULT_TURNS_PER_HOUR


def link_code_ttl_seconds() -> int:
    try:
        return max(30, int(os.environ.get("HARNESS_CHANNELS_LINK_TTL_S", "600")))
    except (TypeError, ValueError):
        return 600


def confirmation_ttl_seconds() -> int:
    try:
        return max(30, int(os.environ.get("HARNESS_CHANNELS_CONFIRM_TTL_S", "120")))
    except (TypeError, ValueError):
        return 120


def callback_url() -> str:
    return os.environ.get("HARNESS_CALLBACK_URL") or f"http://127.0.0.1:{os.environ.get('PORT', '3000')}"


def channel_model_settings() -> ModelSettings:
    """The model for autonomous channel agent turns.

    A channel has no front door to resolve LLM config from the settings vault, so
    it uses the runtime-wide background model (the same env `jobs`/`automation`
    use). `HARNESS_CHANNEL_*` overrides take precedence when set.
    """
    return ModelSettings(
        provider=os.environ.get("HARNESS_CHANNEL_PROVIDER")
        or os.environ.get("HARNESS_JOB_PROVIDER", "ollama"),
        model=os.environ.get("HARNESS_CHANNEL_MODEL")
        or os.environ.get("HARNESS_JOB_MODEL", "llama3.1"),
        base_url=os.environ.get("HARNESS_CHANNEL_BASE_URL")
        or os.environ.get("HARNESS_JOB_BASE_URL")
        or None,
        api_key=os.environ.get("HARNESS_CHANNEL_API_KEY")
        or os.environ.get("HARNESS_JOB_API_KEY")
        or None,
    )


def is_sensitive_key(key: str) -> bool:
    lowered = str(key or "").lower()
    return any(marker in lowered for marker in _SENSITIVE_MARKERS)


def redact_config(config: Optional[dict[str, Any]]) -> dict[str, Any]:
    """Return a copy of a config dict with sensitive values replaced by a marker.

    Non-sensitive keys pass through. A sensitive key that has any value returns
    `REDACTED`; an absent value stays absent, so the client can tell
    "configured" from "not configured".
    """
    out: dict[str, Any] = {}
    for key, value in (config or {}).items():
        if is_sensitive_key(key):
            if value not in (None, ""):
                out[key] = REDACTED
        else:
            out[key] = value
    return out


def resolve_secret_like(secrets: Any, raw: Optional[str]) -> Optional[str]:
    """Resolve a config value that may be a `secret://` reference.

    A literal value is returned unchanged. A `secret://` reference is resolved
    through the secrets manager (no grant required — the channel config is an
    operator-owned value); if unavailable, `None` is returned so the caller fails
    honestly instead of sending with a missing credential.
    """
    if raw is None:
        return None
    text = str(raw)
    if not text.startswith("secret://"):
        return text
    if secrets is None:
        return None
    try:
        return secrets.resolve(text, consumer="channel", require_grant=False)
    except Exception:  # noqa: BLE001 - unavailable credential is an honest None
        return None


__all__ = [
    "DEFAULT_TURNS_PER_HOUR",
    "REDACTED",
    "callback_url",
    "channel_model_settings",
    "channels_enabled",
    "confirmation_ttl_seconds",
    "is_sensitive_key",
    "link_code_ttl_seconds",
    "polling_enabled",
    "redact_config",
    "resolve_secret_like",
    "turns_per_hour",
]
