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
    # ── Compact prompt profile (always-available personalization) ───────────
    # Whether a compact user/project profile is injected into every run.
    "profile_enabled": True,
    # Per-section and total character budgets for the injected profile, the
    # maximum number of entries and the maximum single-entry length. These are
    # hard-bounded (see BOUNDS) so a profile can never flood the context window.
    "profile_user_budget_chars": 1375,
    "profile_project_budget_chars": 2200,
    "profile_total_budget_chars": 3600,
    "profile_max_entries": 20,
    "profile_max_entry_chars": 500,
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
    # ── Local privacy controls (Phase 6) ────────────────────────────────────
    # Memory completely off: no durable memory is written at all — not even an
    # explicit "remember this". This is the hard local off switch. Distinct from
    # `memory_mode=off`, which still honours explicit requests.
    "memory_enabled": True,
    # How long an automatically learned memory is retained before it becomes
    # eligible for expiry review (days). 0 = never; explicit memory is exempt.
    # (Shares the `retention_days` key above; kept as the canonical name.)
    # Whether a memory may appear in diagnostic/operator views (Lifecycle,
    # explanations). Off hides content in those views without deleting anything.
    "memory_in_diagnostics": True,
    # Whether optional local semantic indexing is permitted. Semantic indexing is
    # NOT implemented (deliberately deferred — the labeled eval showed the
    # deterministic retriever serves the set). This flag exists so the operator's
    # intent is recorded and a future feature can honour it; it never enables a
    # network service and never bypasses scope/privacy filtering.
    "semantic_indexing_enabled": False,
    # Category-specific capture policy: a JSON object mapping memory type ->
    # "allow" | "suggest" | "deny". Absent types follow the mode. This can only
    # TIGHTEN capture (a "deny" refuses; it can never widen authorization).
    "capture_policy": {},
    # Category-specific recall policy: memory type -> "allow" | "deny".
    "recall_policy": {},
    # ── Optional local semantic contradiction candidates (Phase 3) ───────────
    # OFF by default. When enabled it may only find *candidate* related memories
    # for the deterministic + authority decision; it can never supersede,
    # activate, archive or delete, and never bypasses scope/privacy rules. When
    # disabled — or when no local backend is available — detection stays lexical.
    "semantic_conflict_enabled": False,
    # Minimum similarity for a semantic candidate.
    "semantic_conflict_threshold": 0.72,
    # Which local backend to use: "char-ngram" (default, dependency-free), "auto"
    # (use a stronger local embedding model only if one is already installed and
    # configured locally), "local-embedding", or "none" (force lexical-only).
    # Never triggers a network call or a model download.
    "semantic_conflict_backend": "char-ngram",
    # Maximum candidates considered per write.
    "semantic_conflict_max_candidates": 5,
    # Maximum same-dimension memories indexed/compared per write.
    "semantic_conflict_max_index": 500,
    # Wall-clock budget for one semantic candidate search (ms).
    "semantic_conflict_timeout_ms": 50,
    # Whether detector metadata (detector, similarity, candidate ids) is shown in
    # diagnostics/UI. Never affects decisions.
    "semantic_conflict_diagnostics": True,
    # Optional: allow the local semantic backend to reorder ONLY memories that
    # already passed the authoritative scope/status/expiry/recall filters AND
    # carried a lexical relevance signal. It can never surface an excluded
    # memory or widen the recalled set. Off by default; lexical ranking remains
    # the production default.
    "semantic_recall_tiebreak": False,
    # ── Full-session historical recall (M2) ─────────────────────────────────
    # Whether the agent may search prior Eclipse sessions at all.
    "session_history_enabled": True,
    # Whether completed runs are indexed into the bounded SessionMessage search
    # index. When off, no new messages are indexed (existing index is untouched).
    "session_indexing_enabled": True,
    # Days an indexed session message is retained before the sweep removes it.
    # 0 = keep indefinitely. This is separate from durable-memory retention.
    "session_retention_days": 90,
    # Maximum results one session search may return.
    "session_search_max_results": 10,
    # Whether bounded tool-result summaries are indexed/searchable.
    "session_search_include_tool_summaries": True,
    # ── External memory providers (M8) ──────────────────────────────────────
    # Whether external (MCP-backed) memory providers may be SEARCHED at all.
    # Off by default: discovery never activates a provider, and even when on an
    # external search still requires an explicit per-call allow flag. External
    # results are labelled UNVERIFIED CONTEXT and are never promoted to native.
    "external_memory_search_enabled": False,
    # Whether an EXPLICIT external write (user request + operator approval) is
    # permitted. Automatic external writes are structurally impossible (the
    # provider never declares write for automatic use). Off by default.
    "external_memory_write_enabled": False,
    # Native results below which the router may consider external providers.
    "external_memory_native_sufficiency": 3,
    # ── Project-local skills (Phase 2) ──────────────────────────────────────
    # Whether repository-carried skills may be discovered/loaded at all. When
    # off, no project root is scanned and no notice is shown. Even when on, a
    # project's skills load ONLY after an explicit operator trust decision.
    "project_skill_discovery": True,
}

# Hard bounds. Policy may pick any value in range, but never cross these.
BOUNDS: dict[str, tuple[Any, Any]] = {
    "candidate_confidence_threshold": (0.0, 1.0),
    "context_budget_chars": (200, 20_000),
    "retrieval_limit": (1, 50),
    "profile_user_budget_chars": (0, 4000),
    "profile_project_budget_chars": (0, 6000),
    "profile_total_budget_chars": (0, 8000),
    "profile_max_entries": (0, 100),
    "profile_max_entry_chars": (1, 2000),
    "max_memories": (0, 100_000),
    "retention_days": (0, 3650),
    "audit_retention_rows": (0, 100_000),
    "semantic_conflict_threshold": (0.0, 1.0),
    "semantic_conflict_max_candidates": (1, 50),
    "semantic_conflict_max_index": (1, 5000),
    "semantic_conflict_timeout_ms": (1, 5000),
    "session_retention_days": (0, 3650),
    "session_search_max_results": (1, 50),
    "external_memory_native_sufficiency": (1, 50),
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
    # `memory_enabled=False` disables automatic capture AND suggestions. Explicit
    # requests are refused by the service (`write_memory`), so this is a true off.
    if resolved.get("memory_enabled") is False:
        flags["auto_capture_enabled"] = False
        flags["auto_suggest_enabled"] = False
    return flags


# Capture/recall policy values. Only these three are accepted; anything else
# falls back to the safe default ("allow" for capture in automatic modes is
# governed by the mode, so a bad value never widens capture).
CATEGORY_POLICY_VALUES = ("allow", "suggest", "deny")

# Accepted semantic backend selectors (see `semantic.py`). `auto` picks the
# strongest AVAILABLE local backend; it never downloads or contacts a network.
SEMANTIC_BACKEND_VALUES = ("char-ngram", "local-embedding", "auto", "none")


def category_policy(resolved: dict[str, Any], key: str, memory_type: str) -> str:
    """The effective per-category policy value, or "" when unspecified.

    Safety floor: an unknown/invalid value is treated as unspecified, never as a
    widening. A "deny" can only tighten; it cannot bypass authorization.
    """
    table = resolved.get(key) or {}
    if not isinstance(table, dict):
        return ""
    value = str(table.get(memory_type, "")).lower()
    return value if value in CATEGORY_POLICY_VALUES else ""


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
    if isinstance(default, dict):
        if not isinstance(value, dict):
            raise PolicyError(f"policy {key!r} must be an object")
        return dict(value)
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
    if key == "semantic_conflict_backend" and coerced not in SEMANTIC_BACKEND_VALUES:
        raise PolicyError(f"policy {key!r} must be one of {SEMANTIC_BACKEND_VALUES}")
    if key in LOCKED_VALUES and coerced != LOCKED_VALUES[key]:
        raise PolicyError(f"policy {key!r} is locked to {LOCKED_VALUES[key]!r}")
    if key in BOUNDS:
        low, high = BOUNDS[key]
        if not (low <= coerced <= high):
            raise PolicyError(f"policy {key!r} must be between {low} and {high}")
    if key in ("capture_policy", "recall_policy"):
        for category, setting in coerced.items():
            if str(setting).lower() not in CATEGORY_POLICY_VALUES:
                raise PolicyError(
                    f"policy {key!r} value for {category!r} must be one of {CATEGORY_POLICY_VALUES}"
                )
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
