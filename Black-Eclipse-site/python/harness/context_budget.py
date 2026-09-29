"""Measured, model-aware context budgeting.

The runtime previously bounded conversation history with two hardcoded constants
(`graph.MAX_HISTORY_TURNS` / `MAX_HISTORY_CHARS`) and never measured what the
assembled request actually cost against the resolved model's context window. A
40 000-char history is ~10–13k tokens on its own, which overflows a small-context
model and wastes most of a large one.

This module computes the history allowance from what actually remains after the
real per-run overhead, using the resolved model's **declared** window (Milestone
1). It is deliberately small and side-effect-free: no tokenizer dependency, no
network call, no summarization.

Rules:

  * **Measure the request, not the history in isolation.** The system prompt
    (after surface filtering), the tool schemas actually advertised, every
    per-run context block, and the user turn are summed.
  * **Unknown stays unknown.** When `resolve_context_window` returns None the
    budget is *inert* (`effective=False`): the caller must fall back to the
    conservative constants, never assume a large window.
  * **The char ceiling is absolute.** `MAX_HISTORY_CHARS` can never be exceeded,
    even on a huge window, so a pathological history cannot flood a prompt.
  * **Approximation margin.** `estimate_tokens` is ~4 chars/token; the budget
    keeps a safety margin because of that.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Optional

from .eclipse_memory.profile import estimate_tokens
from .models import resolve_context_window

# Output tokens reserved out of the window for the model's own answer. A
# conservative default; agents may produce longer answers, but the margin below
# plus the char ceiling absorbs that.
DEFAULT_RESERVED_OUTPUT_TOKENS = 1024

# Fraction of the remaining window kept as margin (the estimator is approximate).
SAFETY_MARGIN_RATIO = 0.10

# A turn budget is derived from the allowance using a generously small per-turn
# floor. The character allowance is the binding constraint in practice; this only
# prevents an absurd number of microscopic turns on a huge window.
MIN_TURN_TOKENS = 4

# The estimator's unit: how many characters one estimated token represents.
CHARS_PER_TOKEN = 4

UNKNOWN_WINDOW_POLICY = "conservative_ceiling"
KNOWN_WINDOW_POLICY = "measured_model_window"


@dataclass
class ContextBudget:
    """The per-run history budget, derived from the resolved model's window."""

    window: Optional[int]
    window_known: bool
    # False when the window is unknown: the caller must use the conservative
    # constants (this object does not carry a model-derived bound).
    effective: bool
    reserved_output_tokens: int
    measured_overhead_tokens: int
    history_allowance_tokens: int
    history_allowance_chars: int
    max_history_turns: int
    max_history_chars: int
    policy: str
    components: dict[str, int] = field(default_factory=dict)
    tighter: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "window": self.window,
            "windowKnown": self.window_known,
            "effective": self.effective,
            "reservedOutputTokens": self.reserved_output_tokens,
            "measuredOverheadTokens": self.measured_overhead_tokens,
            "historyAllowanceTokens": self.history_allowance_tokens,
            "historyAllowanceChars": self.history_allowance_chars,
            "maxHistoryTurns": self.max_history_turns,
            "maxHistoryChars": self.max_history_chars,
            "policy": self.policy,
            "tighterRetry": self.tighter,
            "components": dict(self.components),
        }


def tool_schema_text(schemas: list[dict[str, Any]]) -> str:
    """A deterministic text rendering of the advertised tool schemas.

    The model receives these as bound tools; measuring their JSON is a
    conservative stand-in for their token cost. Sorted by name so the value is
    stable regardless of registry insertion order.
    """
    if not schemas:
        return ""
    try:
        ordered = sorted(schemas, key=lambda s: str(s.get("name") or ""))
        return json.dumps(ordered, sort_keys=True, separators=(",", ":"), default=str)
    except Exception:  # noqa: BLE001 - a schema is always JSON-encodable in practice
        return " ".join(str(s) for s in schemas)


def compute_history_budget(
    *,
    provider: str,
    model: str,
    system_prompt: str,
    tool_schemas: str = "",
    profile_block: str = "",
    skill_manifest: str = "",
    memory_block: str = "",
    dropped_block: str = "",
    user_turn: str = "",
    absolute_max_turns: int,
    absolute_max_chars: int,
    reserved_output_tokens: int = DEFAULT_RESERVED_OUTPUT_TOKENS,
    tighter: bool = False,
    window_override: Optional[int] = None,
) -> ContextBudget:
    """Derive the history allowance from the measured request and the window.

    Returns an inert (`effective=False`) budget when the window is unknown — the
    caller falls back to `absolute_max_turns` / `absolute_max_chars`. When the
    window is known, `max_history_chars` is the derived allowance capped by the
    absolute char ceiling, and `max_history_turns` is a derived turn budget.

    `tighter=True` halves the derived allowance for the one recovery retry.
    `window_override` is an explicit caller-supplied window (a test/operator
    seam); it never fabricates a value — it only lets a caller who KNOWS the
    window supply it where the catalog does not.
    """
    components = {
        "systemPrompt": estimate_tokens(system_prompt),
        "toolSchemas": estimate_tokens(tool_schemas),
        "profile": estimate_tokens(profile_block),
        "skillManifest": estimate_tokens(skill_manifest),
        "memory": estimate_tokens(memory_block),
        "droppedContext": estimate_tokens(dropped_block),
        "userTurn": estimate_tokens(user_turn),
    }
    overhead = sum(components.values())
    window = window_override if window_override is not None else resolve_context_window(provider, model)

    if window is None or window <= 0:
        return ContextBudget(
            window=None,
            window_known=False,
            effective=False,
            reserved_output_tokens=reserved_output_tokens,
            measured_overhead_tokens=overhead,
            history_allowance_tokens=0,
            history_allowance_chars=0,
            max_history_turns=absolute_max_turns,
            max_history_chars=absolute_max_chars,
            policy=UNKNOWN_WINDOW_POLICY,
            components=components,
            tighter=tighter,
        )

    usable = window - overhead - reserved_output_tokens
    usable = max(0, usable)
    usable = int(usable * (1.0 - SAFETY_MARGIN_RATIO))
    if tighter:
        usable = usable // 2

    allowance_chars = usable * CHARS_PER_TOKEN
    max_history_chars = max(0, min(absolute_max_chars, allowance_chars))
    # A derived turn budget from the allowance, never below 1 when there is any
    # allowance. The char ceiling is the binding constraint in practice.
    max_history_turns = max(1, usable // MIN_TURN_TOKENS) if usable > 0 else 0

    return ContextBudget(
        window=window,
        window_known=True,
        effective=True,
        reserved_output_tokens=reserved_output_tokens,
        measured_overhead_tokens=overhead,
        history_allowance_tokens=usable,
        history_allowance_chars=allowance_chars,
        max_history_turns=max_history_turns,
        max_history_chars=max_history_chars,
        policy=KNOWN_WINDOW_POLICY,
        components=components,
        tighter=tighter,
    )


__all__ = [
    "CHARS_PER_TOKEN",
    "ContextBudget",
    "DEFAULT_RESERVED_OUTPUT_TOKENS",
    "KNOWN_WINDOW_POLICY",
    "MIN_TURN_TOKENS",
    "SAFETY_MARGIN_RATIO",
    "UNKNOWN_WINDOW_POLICY",
    "compute_history_budget",
    "tool_schema_text",
]
