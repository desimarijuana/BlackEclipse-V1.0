"""Eclipse-Memory policy — configurable behaviour with hard safety floors.

Policy values are *overrides* stored in `MemoryPolicy`; the defaults here apply
when a key has no override, so changing a default never requires a data
migration.

Critically, policy can only loosen/tighten *within safe bounds*. Some settings
have a floor that policy can never cross (e.g. automatic skill promotion is
always off, the context budget cannot exceed the hard ceiling). This keeps a
stored setting from becoming a security bypass — the same principle as the
permission policy.

**One coherent learning lifecycle.** Automatic memory capture and automatic
skill learning are each controlled by a single *mode* key — not by several
independent booleans that can drift out of sync:

    * ``automatic_selective`` — learn automatically, but only when the evidence
      is strong: high-confidence, durable, low-risk, non-sensitive. Incidental
      or project-specific claims additionally require recurrence. The user is
      never asked once per run.
    * ``ask_before_saving`` — stage candidates and ask (an inert suggestion),
      never save a durable memory on the user's behalf.
    * ``off`` — never create a durable memory or learning candidate
      automatically. Explicit "remember/forget/correct" requests still work.

The legacy boolean keys (`auto_capture_enabled`, `auto_suggest_enabled`,
`auto_candidate_detection`) are now **derived** from the modes and are no longer
persisted or settable — the mode is the one source of truth. They remain in the
resolved settings dict only so existing call sites can read them consistently.
"""

from __future__ import annotations

from typing import Any, Optional

from .db import now_iso

# ── Learning modes ──────────────────────────────────────────────────────────

MODE_VALUES = ("automatic_selective", "ask_before_saving", "off")

# Keys whose value is one of MODE_VALUES.
MODE_KEYS = ("memory_mode", "skill_learning_mode")

# Old boolean keys that are now derived from the modes. They are NOT in DEFAULTS
# (so they cannot be persisted or set) but ARE injected into resolved settings
# by `PolicyStore.get_all` for call sites that still read them.
DERIVED_KEYS = ("auto_capture_enabled", "auto_suggest_enabled", "auto_candidate_detection")

# ── Defaults ────────────────────────────────────────────────────────────────

DEFAULTS: dict[str, Any] = {
    # Automatic durable-memory learning. The intended product default: save
    # strong, durable, low-risk information automatically (no per-run prompt),
    # treat one-off/task/market/tool content as history-only, and require
    # recurrence for project-specific claims. `ask_before_saving` stages an inert
    # suggestion instead; `off` disables automatic memory entirely (explicit
    # "remember/forget/correct" always remains available). See decision.py.
    "memory_mode": "automatic_selective",
    # Automatic skill-candidate learning. An eligible run is NOT itself proof of
    # a reusable procedure: implicit candidates additionally require recurrence
    # evidence. Created candidates are always inert; nothing is ever enabled or
    # promoted without evaluation + operator approval.
    "skill_learning_mode": "automatic_selective",
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

# Module-level so tests/UI can import the mapping instead of re-deriving it.
_MEMORY_MODE_FLAGS: dict[str, dict[str, bool]] = {
    "off": {"auto_capture_enabled": False, "auto_suggest_enabled": False},
    "ask_before_saving": {"auto_capture_enabled": False, "auto_suggest_enabled": True},
    "automatic_selective": {"auto_capture_enabled": True, "auto_suggest_enabled": True},
}
_SKILL_MODE_FLAGS: dict[str, dict[str, bool]] = {
    "off": {"auto_candidate_detection": False},
    "ask_before_saving": {"auto_candidate_detection": True},
    "automatic_selective": {"auto_candidate_detection": True},
}


def derived_flags(resolved: dict[str, Any]) -> dict[str, bool]:
    """The legacy booleans implied by the resolved modes (read-only)."""
    memory_mode = resolved.get("memory_mode") or "automatic_selective"
    skill_mode = resolved.get("skill_learning_mode") or "automatic_selective"
    flags = dict(_MEMORY_MODE_FLAGS.get(memory_mode, _MEMORY_MODE_FLAGS["automatic_selective"]))
    flags.update(_SKILL_MODE_FLAGS.get(skill_mode, _SKILL_MODE_FLAGS["automatic_selective"]))
    return flags


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
    if key in DERIVED_KEYS:
        raise PolicyError(
            f"policy {key!r} is derived from the learning mode; set "
            f"'memory_mode'/'skill_learning_mode' instead"
        )
    if key not in DEFAULTS:
        raise PolicyError(f"unknown policy key {key!r}")
    coerced = _coerce(key, value)
    if key in MODE_KEYS and coerced not in MODE_VALUES:
        raise PolicyError(f"policy {key!r} must be one of {MODE_VALUES}")
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
        # The legacy booleans are never stored or read directly — they are
        # derived from the modes so they can never drift out of sync.
        resolved.update(derived_flags(resolved))
        return resolved

    def get(self, key: str) -> Any:
        if key in DERIVED_KEYS:
            return self.get_all().get(key)
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


__all__ = [
    "BOUNDS",
    "DEFAULTS",
    "DERIVED_KEYS",
    "LOCKED_VALUES",
    "MODE_KEYS",
    "MODE_VALUES",
    "PolicyError",
    "PolicyStore",
    "derived_flags",
    "validate",
]
