"""Eclipse-Memory policy — configurable behaviour with hard safety floors.

Policy values are *overrides* stored in `MemoryPolicy`; the defaults here apply
when a key has no override, so changing a default never requires a data
migration.

Critically, policy can only loosen/tighten *within safe bounds*. Some settings
have a floor that policy can never cross (e.g. automatic skill promotion is
always off, automatic capture can never be enabled to store arbitrary text, the
context budget cannot exceed the hard ceiling). This keeps a stored setting from
becoming a security bypass — the same principle as the permission policy.
"""

from __future__ import annotations

from typing import Any, Optional

from .db import now_iso

# ── Defaults ────────────────────────────────────────────────────────────────

DEFAULTS: dict[str, Any] = {
    # Automatic capture of a run's explicit user memory INTENT ("remember this",
    # "save this preference", "forget this", "correct this"). Off by default:
    # routine chat turns are never auto-stored. The deterministic explicit-intent
    # path still runs (clear, safe, user-authored save/forget/correct commands
    # are always honoured) — this flag only gates the *automatic* incidental
    # path. A non-explicit "I prefer X" mention never saves; it may at most
    # become a suggestion when `auto_suggest_enabled` is on.
    "auto_capture_enabled": False,
    # Automatic learning-candidate detection after a completed run. Off by
    # default: completing a run, using multiple tools, or taking multiple model
    # steps is NOT proof a procedure generalizes. Operators may opt in; even then
    # detection creates ONLY inert candidates (never enables/promotes a skill).
    "auto_candidate_detection": False,
    # Automatic *suggestion* of incidental durable information ("I prefer …").
    # Off by default. Suggestions are inert (no DB record until the user accepts);
    # they never write anything on their own.
    "auto_suggest_enabled": False,
    # Minimum confidence a detected candidate must have to be recorded.
    "candidate_confidence_threshold": 0.4,
    # Retrieval context budget (characters).
    "context_budget_chars": 4000,
    # Max memories injected per retrieval.
    "retrieval_limit": 8,
    # Hard storage budget: max ACTIVE memories retained (0 = unlimited). When the
    # budget is reached a new save fails truthfully ("memory is full") rather
    # than silently evicting user memory; the user reviews/archives to free space.
    "max_memories": 0,
    # Days a non-expiring memory is retained before it is eligible for expiry
    # review (0 = never auto-expire). This is a review threshold, not deletion.
    "retention_days": 0,
    # Whether proposed memory may be injected without review.
    "include_proposed_in_retrieval": False,
    # Audit retention: max retrieval-audit rows kept (0 = unlimited).
    "audit_retention_rows": 0,
    # Promotion policy: automatic promotion is structurally impossible; this
    # only records the operator's stated intent for review workflows.
    "auto_promote_low_risk": False,
}

# Hard bounds. Policy may pick any value in range, but never cross these.
BOUNDS: dict[str, tuple[Any, Any]] = {
    "candidate_confidence_threshold": (0.0, 1.0),
    "context_budget_chars": (200, 20_000),
    "retrieval_limit": (1, 50),
    "max_memories": (0, 100_000),
    "retention_days": (0, 3650),
    "audit_retention_rows": (0, 100_000),
}

# Keys that are safety-critical and may NOT be enabled by policy at all — the
# value is accepted only if it equals the safe value. This is the hard floor.
LOCKED_VALUES: dict[str, Any] = {
    "auto_promote_low_risk": False,  # automatic promotion stays disabled
}


class PolicyError(ValueError):
    """A policy change was rejected (unknown key, out of range, or locked)."""


def _coerce(key: str, value: Any) -> Any:
    default = DEFAULTS.get(key)
    if isinstance(default, bool):
        return bool(value)
    if isinstance(default, int) and not isinstance(default, bool):
        return int(value)
    if isinstance(default, float):
        return float(value)
    return value


def validate(key: str, value: Any) -> Any:
    if key not in DEFAULTS:
        raise PolicyError(f"unknown policy key {key!r}")
    coerced = _coerce(key, value)
    if key in LOCKED_VALUES and coerced != LOCKED_VALUES[key]:
        raise PolicyError(f"policy {key!r} is locked to {LOCKED_VALUES[key]!r}")
    if key in BOUNDS:
        low, high = BOUNDS[key]
        if not (low <= coerced <= high):
            raise PolicyError(f"policy {key!r} must be between {low} and {high}")
    return coerced


class PolicyStore:
    """Reads/writes policy overrides on an `EclipseMemoryStore`."""

    def __init__(self, store: Any) -> None:
        self.store = store

    def get_all(self) -> dict[str, Any]:
        stored = {
            row["key"]: row["value"]
            for row in self.store._db.execute("SELECT key, value FROM MemoryPolicy").fetchall()
        }
        resolved: dict[str, Any] = {}
        for key, default in DEFAULTS.items():
            if key not in stored:
                resolved[key] = default
                continue
            try:
                resolved[key] = validate(key, _decode(stored[key], default))
            except PolicyError:
                # A corrupted/now-invalid stored value falls back to the safe
                # default rather than being honoured.
                resolved[key] = default
        return resolved

    def get(self, key: str) -> Any:
        return self.get_all().get(key, DEFAULTS.get(key))

    def set(self, key: str, value: Any, *, updated_by: Optional[str] = None) -> dict[str, Any]:
        validated = validate(key, value)
        self.store._db.execute(
            """INSERT INTO MemoryPolicy (key, value, updatedAt, updatedBy)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(key) DO UPDATE SET value=excluded.value,
                 updatedAt=excluded.updatedAt, updatedBy=excluded.updatedBy""",
            (key, _encode(validated), now_iso(), updated_by),
        )
        self.store._db.commit()
        self.store.append_memory_event("memory.policy_updated", data={"key": key, "value": validated})
        return {"key": key, "value": validated}

    def reset(self, key: Optional[str] = None) -> None:
        if key is None:
            self.store._db.execute("DELETE FROM MemoryPolicy")
        else:
            if key not in DEFAULTS:
                raise PolicyError(f"unknown policy key {key!r}")
            self.store._db.execute("DELETE FROM MemoryPolicy WHERE key=?", (key,))
        self.store._db.commit()


def _encode(value: Any) -> str:
    import json

    return json.dumps(value)


def _decode(raw: str, default: Any) -> Any:
    import json

    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return default


__all__ = ["BOUNDS", "DEFAULTS", "LOCKED_VALUES", "PolicyError", "PolicyStore", "validate"]
