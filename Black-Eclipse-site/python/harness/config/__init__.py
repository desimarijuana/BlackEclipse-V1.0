"""Harness configuration package.

Only cross-cutting configuration belongs here. Runtime feature flags live in
`harness.config.flags`; subsystem-specific settings stay with their subsystem.
"""

from .flags import (  # noqa: F401
    FLAG_SPECS,
    FlagSpec,
    get_bool,
    get_flag,
    get_int,
    snapshot,
    snapshot_hash,
    validate,
)

__all__ = [
    "FLAG_SPECS",
    "FlagSpec",
    "get_bool",
    "get_flag",
    "get_int",
    "snapshot",
    "snapshot_hash",
    "validate",
]
