"""Provider credential pool for the model gateway (W1).

A run normally carries one key from `ModelSettings.api_key`. This pool lets a
provider declare additional keys (for example `HARNESS_OPENAI_API_KEYS=a,b`) so
a 429/401 can rotate instead of failing the run.

Secrets rules:

* keys are never logged, emitted or persisted;
* events and rows carry `credential_id` and `label` only;
* a key is only used for its own provider;
* an empty pool falls back to the run's single key exactly as before.
"""

from __future__ import annotations

import hashlib
import os
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Optional


def _now() -> float:
    return time.monotonic()


def _fingerprint(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:12]


@dataclass
class Credential:
    id: str
    provider: str
    api_key: str
    base_url: Optional[str] = None
    label: str = "run"
    cooldown_until: float = 0.0
    failures: int = 0

    @property
    def cooling(self) -> bool:
        return self.cooldown_until > _now()


class CredentialPool:
    """Ordered, per-provider credentials with cooldown/rotation."""

    def __init__(self, *, now: Callable[[], float] = _now) -> None:
        self._now = now
        self._credentials: dict[str, list[Credential]] = {}

    @classmethod
    def from_settings(
        cls,
        settings: Any,
        *,
        environ: Optional[Mapping[str, str]] = None,
        now: Callable[[], float] = _now,
    ) -> "CredentialPool":
        pool = cls(now=now)
        provider = str(getattr(settings, "provider", "") or "").strip()
        if not provider:
            return pool
        key = getattr(settings, "api_key", None)
        if key:
            pool.add(
                provider,
                str(key),
                label="run",
                base_url=getattr(settings, "base_url", None),
            )
        env = environ if environ is not None else os.environ
        env_name = "HARNESS_" + provider.upper().replace("-", "_").replace(".", "_") + "_API_KEYS"
        raw = (env.get(env_name) or "").strip()
        if raw:
            for index, extra in enumerate(part.strip() for part in raw.split(",")):
                if extra:
                    pool.add(provider, extra, label=f"env-{index + 1}")
        return pool

    def add(
        self,
        provider: str,
        api_key: str,
        *,
        label: str = "key",
        base_url: Optional[str] = None,
    ) -> Credential:
        provider = str(provider or "").strip()
        key = str(api_key or "").strip()
        if not provider or not key:
            raise ValueError("credential needs a provider and a key")
        for existing in self._credentials.get(provider, []):
            if existing.api_key == key:
                return existing
        credential = Credential(
            id=f"cred_{provider}_{_fingerprint(key)}",
            provider=provider,
            api_key=key,
            base_url=base_url,
            label=label,
        )
        self._credentials.setdefault(provider, []).append(credential)
        return credential

    def acquire(self, provider: str) -> Optional[Credential]:
        """The first non-cooling credential for a provider, or None."""
        for credential in self._credentials.get(str(provider or ""), []):
            if credential.cooldown_until <= self._now():
                return credential
        return None

    def available(self, provider: str) -> bool:
        return self.acquire(provider) is not None

    def credentials(self, provider: str) -> list[Credential]:
        return list(self._credentials.get(str(provider or ""), []))

    def record_success(self, credential: Optional[Credential]) -> None:
        if credential is None:
            return
        credential.failures = 0
        credential.cooldown_until = 0.0

    def record_failure(
        self,
        credential: Optional[Credential],
        *,
        status: Optional[int] = None,
        retry_after_s: Optional[float] = None,
    ) -> None:
        if credential is None:
            return
        credential.failures += 1
        if status in (401, 403):
            # A bad key is not retried: park it until an operator/rotation clears it.
            credential.cooldown_until = self._now() + 3600.0
            return
        if status in (402, 429) or retry_after_s is not None:
            delay = retry_after_s if retry_after_s is not None else min(
                900.0, 30.0 * (2 ** max(0, credential.failures - 1))
            )
            credential.cooldown_until = self._now() + max(1.0, min(900.0, float(delay)))

    def snapshot(self) -> list[dict[str, Any]]:
        """Safe inventory: ids/labels/cooldowns only, never keys."""
        out: list[dict[str, Any]] = []
        for provider, credentials in sorted(self._credentials.items()):
            for credential in credentials:
                out.append({
                    "id": credential.id,
                    "provider": provider,
                    "label": credential.label,
                    "cooling": credential.cooldown_until > self._now(),
                    "failures": credential.failures,
                })
        return out

    def __len__(self) -> int:
        return sum(len(items) for items in self._credentials.values())


__all__ = ["Credential", "CredentialPool"]
