"""The W2 compression ladder: prune -> summary -> deterministic skeleton.

Three stages, one decision point. Before this module the stages were separate
helpers wired independently at their own call sites:

  * `pruning.prune_tool_messages` at the end of a tool turn;
  * `compaction.compact_dropped` inside history bounding;
  * a cooldown store consulted ad hoc.

That split made it impossible to answer "what did the runtime actually do to
this prompt?" in one place, and it made the 50/70/85 pressure gates advisory
rather than authoritative. The ladder owns the ordering, the gate decision, the
cooldown, and the honest `LadderResult` that the event stream reports.

Properties that must hold (asserted in `tests/test_compression_ladder.py`):

  * **Prune is free.** The first stage never calls a model. A pruned tool result
    keeps its role, `tool_call_id`, name and original character count.
  * **The tail is sacred.** The last N turns and the last N tool results are
    never summarised, and an assistant/tool pair is never split.
  * **Evidence survives.** A result carrying an evidence/provenance handle is
    never pruned (the prune stage's own rule) and the evidence ledger is never
    part of the payload (it is injected separately by `goals/`).
  * **The skeleton always works.** If the model is unavailable, times out, or
    returns nothing, the deterministic skeleton is committed with
    `used_model=False`; the run says so.
  * **No silent no-op.** If no stage reduced the prompt the result is
    `ok=False` and the caller decides (honest overflow or a tighter retry).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from langchain_core.messages import BaseMessage, SystemMessage, ToolMessage

from ..compaction import MODEL_POLICY_KEY, compact_dropped, render_compaction_block
from .pruning import prune_tool_messages

#: How many recent turns the summary stage protects.
DEFAULT_PROTECT_TURNS = 8

#: How many recent tool results the prune stage protects.
DEFAULT_PROTECT_TOOL_RESULTS = 4

#: The gates that trigger each stage.
_PRUNE_GATES = frozenset({"soft", "continue", "unknown"})
_SUMMARY_GATES = frozenset({"hard", "emergency"})


@dataclass
class LadderResult:
    """What one ladder pass produced, and exactly how."""

    stage: str = "none"  # prune | summary | skeleton | none
    messages: list[Any] = field(default_factory=list)
    dropped_turns: int = 0
    pruned_tool_results: int = 0
    summary_chars: int = 0
    used_model: bool = False
    ok: bool = False
    reason: str = ""
    cooldown_s: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage": self.stage,
            "droppedTurns": self.dropped_turns,
            "prunedToolResults": self.pruned_tool_results,
            "summaryChars": self.summary_chars,
            "usedModel": self.used_model,
            "ok": self.ok,
            "reason": self.reason or None,
            "cooldownS": self.cooldown_s,
        }


class _Turn:
    """A minimal role/content pair for the summary stage."""

    __slots__ = ("role", "content")

    def __init__(self, role: str, content: str) -> None:
        self.role = role
        self.content = content


def _role(message: Any) -> str:
    kind = str(getattr(message, "type", "") or "").lower()
    if kind in ("human", "user"):
        return "user"
    if kind in ("ai", "assistant"):
        return "assistant"
    if kind == "tool":
        return "tool"
    if kind == "system":
        return "system"
    return "assistant"


def _content(message: Any) -> str:
    content = getattr(message, "content", "")
    if isinstance(content, str):
        return content
    # A content-block list (e.g. cache-marked Anthropic text) is rendered to
    # plain text for the SUMMARY only; the original message is never mutated.
    try:
        parts = []
        for block in content or []:
            if isinstance(block, dict):
                parts.append(str(block.get("text") or ""))
            else:
                parts.append(str(block))
        return "\n".join(p for p in parts if p)
    except Exception:  # noqa: BLE001 - a weird content shape is not fatal
        return str(content or "")


def _head_end(messages: list[Any]) -> int:
    """Index of the first non-system message: the stable head is never cut."""
    index = 0
    while index < len(messages) and _role(messages[index]) == "system":
        index += 1
    return index


def protect_tail(
    messages: list[Any],
    *,
    turns: int = DEFAULT_PROTECT_TURNS,
    tool_results: int = DEFAULT_PROTECT_TOOL_RESULTS,
) -> int:
    """The cut index: messages[:cut] may be summarised, [:cut] is protected.

    Walks backwards keeping whole conversation units. It stops only at a safe
    boundary: an assistant/tool pair is never split, and the system head is
    never included. Returns 0 when everything is protected.
    """
    messages = list(messages or [])
    n = len(messages)
    if n == 0:
        return 0
    floor = _head_end(messages)
    cut = n
    kept_turns = 0
    kept_tools = 0
    index = n - 1
    while index >= floor:
        message = messages[index]
        role = _role(message)
        is_tool = isinstance(message, ToolMessage) or role == "tool"
        if is_tool:
            if kept_tools < max(0, int(tool_results)):
                kept_tools += 1
            else:
                # The pair's tool result would be dropped; stop before the
                # assistant message that issued it (found below).
                break
        else:
            if role in ("user", "assistant"):
                if kept_turns >= max(0, int(turns)) and kept_tools >= max(0, int(tool_results)):
                    break
                kept_turns += 1
        index -= 1
    cut = max(floor, index + 1)
    # The last USER turn is never summarised, even when the turn budget is small.
    last_human = -1
    for position, message in enumerate(messages):
        if _role(message) == "user":
            last_human = position
    if last_human >= floor:
        cut = min(cut, last_human)
    # Never split an assistant/tool pair: if the first kept message is a tool
    # result, move the cut back over the assistant that issued it.
    while cut > floor and (isinstance(messages[cut], ToolMessage) or _role(messages[cut]) == "tool"):
        cut -= 1
    return max(floor, cut)


def _turns(messages: list[Any]) -> list[_Turn]:
    out: list[_Turn] = []
    for message in messages:
        role = _role(message)
        if role == "system":
            continue
        content = _content(message)
        if not content.strip():
            continue
        out.append(_Turn(role, content))
    return out


def _state_store_for(memory_service: Any) -> Optional[Any]:
    store = getattr(memory_service, "store", None) if memory_service is not None else None
    if store is None:
        return None
    try:
        from .compression_state import CompressionStateStore  # noqa: PLC0415

        return CompressionStateStore(store)
    except Exception:  # noqa: BLE001 - cooldown is advisory
        return None


def _settings_for(memory_service: Any) -> dict[str, Any]:
    if memory_service is None:
        return {}
    try:
        return dict(memory_service.policy.get_all())
    except Exception:  # noqa: BLE001 - a policy read failure is not fatal
        return {}


async def compact_turns(
    turns: list[Any],
    *,
    request: Any,
    settings: Optional[dict[str, Any]] = None,
    emitter: Any = None,
    state_store: Any = None,
    session_id: str = "",
    force: bool = False,
    use_model: Optional[bool] = None,
) -> tuple[str, Any]:
    """Compact dropped TURNS with the persisted cooldown (one decision point).

    Returns `(rendered_block, CompactionResult)`. The deterministic skeleton is
    always built. The model narrative is attempted only when the policy enables
    it and the cooldown allows it (or `force`), and a failure arms the ladder.
    This never raises.
    """
    settings = settings or {}
    if use_model is None:
        use_model = bool(settings.get(MODEL_POLICY_KEY, False))
    allow_model = True
    if state_store is not None and session_id:
        try:
            allow_model = bool(state_store.allow(session_id))
        except Exception:  # noqa: BLE001
            allow_model = True
    effective_model = bool(use_model and (allow_model or force))
    result = await compact_dropped(
        turns, request=request, settings=settings, use_model=effective_model,
    )
    block = render_compaction_block(result)
    cooldown_s = 0
    if state_store is not None and session_id and effective_model:
        try:
            if not result.used_model and result.reason:
                state_store.record_failure(session_id, result.reason)
                cooldown_s = _cooldown_for(session_id, state_store)
            elif result.used_model:
                state_store.clear(session_id)
        except Exception:  # noqa: BLE001 - cooldown is advisory
            pass
    if emitter is not None:
        try:
            await emitter.emit("memory.history_compacted", result.to_dict())
        except Exception:  # noqa: BLE001
            pass
    return block, result


def _cooldown_for(session_id: str, state_store: Any) -> int:
    """The seconds remaining on the cooldown, for the honest result payload."""
    try:
        row = state_store._db.execute(  # noqa: SLF001 - small internal probe
            "SELECT nextAttemptAt FROM ContextCompressionState WHERE sessionId=?",
            (session_id,),
        ).fetchone()
        if row is None:
            return 0
        import time  # noqa: PLC0415

        return max(0, int(float(row["nextAttemptAt"] or 0) - time.time()))
    except Exception:  # noqa: BLE001
        return 0


def _apply_messages(
    original: list[Any], *, head_end: int, cut: int, block: str,
) -> list[Any]:
    """Keep the stable system head, replace the middle, keep the protected tail."""
    head = list(original[:head_end])
    tail = list(original[cut:])
    return [*head, SystemMessage(content=block), *tail]


async def compress(
    messages: list[Any],
    *,
    budget: Any = None,
    request: Any = None,
    emitter: Any = None,
    memory_service: Any = None,
    settings: Optional[dict[str, Any]] = None,
    state_store: Any = None,
    session_id: str = "",
    protect_turns: int = DEFAULT_PROTECT_TURNS,
    protect_tool_results: int = DEFAULT_PROTECT_TOOL_RESULTS,
    force: bool = False,
    apply: bool = True,
) -> LadderResult:
    """Run the ladder once and return the honest result.

    `apply=False` is the SHADOW mode: the decision and counts are computed but
    the returned `messages` are the original list (the caller keeps today's
    behaviour while the event reports what the ladder would have done).
    """
    from ..config import flags  # noqa: PLC0415

    mode = flags.get_flag("HARNESS_COMPRESSION_LADDER")
    original = list(messages or [])
    if mode == "off":
        return LadderResult(stage="none", messages=original, ok=False, reason="ladder disabled")
    apply = apply and mode == "on"
    gate = str(getattr(budget, "gate", "unknown") or "unknown")

    # ── Stage 1: prune old tool output (no model call) ──────────────────────
    pruned, pruned_count = prune_tool_messages(
        original, protect_last=max(0, int(protect_tool_results)),
    )
    pruned_messages = pruned if apply else original
    if pruned_count:
        if emitter is not None:
            try:
                await emitter.emit("context.pruned", {
                    "stage": "prune", "prunedToolResults": pruned_count, "mode": mode,
                })
            except Exception:  # noqa: BLE001
                pass
        if gate in _PRUNE_GATES:
            return LadderResult(
                stage="prune", messages=pruned_messages,
                pruned_tool_results=pruned_count, ok=True, reason="pruned old tool output",
            )

    # A run under no pressure needs no further stage.
    if gate in _PRUNE_GATES and not pruned_count:
        return LadderResult(stage="none", messages=original, ok=False, reason="no pressure")

    # ── Stage 2: summary (bounded model, fail-closed) ───────────────────────
    head_end = _head_end(pruned_messages)
    cut = protect_tail(
        pruned_messages, turns=protect_turns, tool_results=protect_tool_results,
    )
    older = pruned_messages[head_end:cut]
    if not older:
        return LadderResult(
            stage="prune" if pruned_count else "none", messages=pruned_messages,
            pruned_tool_results=pruned_count, ok=bool(pruned_count),
            reason="nothing older than the protected tail",
        )
    settings = settings if settings is not None else _settings_for(memory_service)
    store = state_store if state_store is not None else _state_store_for(memory_service)
    block, result = await compact_turns(
        _turns(older), request=request, settings=settings, emitter=emitter,
        state_store=store, session_id=session_id, force=force,
    )
    if not block:
        return LadderResult(
            stage="none", messages=original, pruned_tool_results=pruned_count,
            ok=False, reason=getattr(result, "reason", "") or "nothing to summarise",
        )
    stage = "summary" if getattr(result, "used_model", False) else "skeleton"
    out = _apply_messages(pruned_messages, head_end=head_end, cut=cut, block=block) if apply else original
    ladder = LadderResult(
        stage=stage,
        messages=out,
        dropped_turns=int(getattr(result, "dropped_turns", len(older)) or 0),
        pruned_tool_results=pruned_count,
        summary_chars=len(block),
        used_model=bool(getattr(result, "used_model", False)),
        ok=True,
        reason="" if getattr(result, "used_model", False) else (getattr(result, "reason", "") or ""),
    )
    if emitter is not None:
        try:
            await emitter.emit("context.compressed", ladder.to_dict())
        except Exception:  # noqa: BLE001
            pass
    return ladder


async def maybe_prune_for_run(
    messages: list[Any], emitter: Any, step: int,
) -> tuple[list[Any], int]:
    """The tool-turn prune seam (stage 1 only), kept for the graph's hot path.

    A tool turn must never pay for a summary: this is the free stage. The gate
    is unknown here (the next model call has not happened yet), so the ladder
    treats it as a low-pressure prune.
    """
    from ..config import flags  # noqa: PLC0415

    mode = flags.get_flag("HARNESS_COMPRESSION_LADDER")
    if mode not in ("on", "shadow"):
        return list(messages or []), 0
    pruned, count = prune_tool_messages(list(messages or []))
    if mode == "on" and count:
        messages = pruned
    try:
        await emitter.emit("context.pruned", {
            "step": int(step or 0), "prunedToolResults": count, "mode": mode,
        })
    except Exception:  # noqa: BLE001
        pass
    return list(messages or []), count


__all__ = [
    "DEFAULT_PROTECT_TOOL_RESULTS",
    "DEFAULT_PROTECT_TURNS",
    "LadderResult",
    "compact_turns",
    "compress",
    "maybe_prune_for_run",
    "protect_tail",
]
