"""Security configuration — env flags, paths and the default policy file.

Zero-config must keep working: with no env and no policy file, the subsystem boots
onto the SECURE profile with the default floor and a default-deny network policy.
An operator can drop a JSON policy at `.black-eclipse/security/policy.json` (or set
`BLACK_ECLIPSE_SECURITY_POLICY`) to override — but only through a path the agent
itself is hard-denied from writing (enforced by the floor).
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from .models import PolicyProfile

DEFAULT_POLICY_FILENAME = "policy.json"


def security_dir() -> Path:
    override = os.environ.get("BLACK_ECLIPSE_SECURITY_DIR")
    if override:
        return Path(override)
    return Path(".black-eclipse") / "security"


def policy_path() -> Path:
    override = os.environ.get("BLACK_ECLIPSE_SECURITY_POLICY")
    if override:
        return Path(override)
    return security_dir() / DEFAULT_POLICY_FILENAME


@dataclass
class SecurityConfig:
    enabled: bool = True
    profile: PolicyProfile = PolicyProfile.SECURE
    policy_file: Optional[str] = None
    allow_loopback_network: bool = False
    audit_enabled: bool = True
    policy: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_env(cls) -> "SecurityConfig":
        disabled = os.environ.get("BLACK_ECLIPSE_SECURITY_ENABLED") in ("0", "false", "False")
        profile_text = os.environ.get("BLACK_ECLIPSE_SECURITY_PROFILE", "secure")
        try:
            profile = PolicyProfile(str(profile_text).lower())
        except ValueError:
            profile = PolicyProfile.SECURE
        path = policy_path()
        document: dict[str, Any] = {}
        if path.is_file():
            try:
                with open(path, "r", encoding="utf-8") as handle:
                    loaded = json.load(handle)
                if isinstance(loaded, dict):
                    document = loaded
            except Exception:  # noqa: BLE001 - a broken policy file falls back to defaults
                document = {}
        if isinstance(document.get("security"), dict):
            document = document["security"]
        if document.get("profile"):
            try:
                profile = PolicyProfile(str(document["profile"]).lower())
            except ValueError:
                pass
        return cls(
            enabled=not disabled,
            profile=profile,
            policy_file=str(path),
            allow_loopback_network=os.environ.get("BLACK_ECLIPSE_SECURITY_ALLOW_LOOPBACK") in ("1", "true", "True"),
            audit_enabled=os.environ.get("BLACK_ECLIPSE_SECURITY_AUDIT", "1") not in ("0", "false", "False"),
            policy=document,
        )


__all__ = ["DEFAULT_POLICY_FILENAME", "SecurityConfig", "policy_path", "security_dir"]
