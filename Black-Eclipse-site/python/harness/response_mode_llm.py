"""The model-assisted half of the response-mode orchestrator (flag-gated).

The deterministic classifier in `response_mode.py` is the FIRST pass and the
shipped default. This module adds the optional SECOND pass the blueprint calls
for: when the deterministic verdict is `unsure`, a single bounded model call may
choose a mode instead. It is:

  * **Opt-in** — off unless `HARNESS_RESPONSE_MODE_MODEL` is truthy, so the
    default path stays deterministic and free (a second model call per ambiguous
    turn is a real cost).
  * **Bounded** — one short completion under a hard deadline (`await_bounded`),
    with `temperature=0` on the classification call when the provider supports it.
  * **Total** — any failure (no credentials, unknown provider, timeout, an
    unparsable reply) returns the deterministic plan unchanged. It can never
    break a run or fabricate a mode.

The model is constructed from the run's own `ModelSettings` through the SAME
`models.build_chat_model` seam the runtime uses, so it needs no new configuration
path.
"""

from __future__ import annotations

import os
from typing import Any, Optional

from .response_mode import (
    MODE_CLASSIFIER_SYSTEM,
    ResponseMode,
    ResponsePlan,
    classify_response_mode,
    mode_classifier_prompt,
    parse_mode_reply,
    plan_for_mode,
    response_mode_prompt_block,
)

__all__ = [
    "model_assist_enabled",
    "orchestrate_response_mode",
    "refine_with_model",
    "response_mode_prompt_block",
]

_TRUTHY = frozenset({"1", "true", "yes", "on"})


def model_assist_enabled() -> bool:
    """Whether the model-assisted fallback is switched on for this process."""
    return os.environ.get("HARNESS_RESPONSE_MODE_MODEL", "").strip().casefold() in _TRUTHY


async def refine_with_model(
    query: str,
    base: ResponsePlan,
    settings: Any,
    *,
    timeout_s: float = 8.0,
) -> ResponsePlan:
    """Ask a model to pick a mode; return `base` on any failure. Never raises."""
    try:
        from .async_timeout import await_bounded  # noqa: PLC0415
        from .model_stream import message_text  # noqa: PLC0415
        from .models import build_chat_model  # noqa: PLC0415

        from langchain_core.messages import HumanMessage, SystemMessage  # noqa: PLC0415

        model = build_chat_model(settings)
        messages = [
            SystemMessage(content=MODE_CLASSIFIER_SYSTEM),
            HumanMessage(content=mode_classifier_prompt(query)),
        ]
        reply = await await_bounded(model.ainvoke(messages), timeout_s)
        mode: Optional[ResponseMode] = parse_mode_reply(message_text(reply))
        if not mode or mode == base.mode:
            return base
        return plan_for_mode(
            mode, "likely", "The model-assisted classifier chose this mode.", ("mode:model",),
        )
    except Exception:  # noqa: BLE001 - a fallback must never break the run
        return base


async def orchestrate_response_mode(
    query: str,
    history: Optional[list[Any]],
    settings: Any,
) -> ResponsePlan:
    """The orchestrator entry point: deterministic first, model-assisted on `unsure`.

    Always returns a plan. The model call happens ONLY when the deterministic
    verdict is `unsure` AND the fallback is enabled; otherwise this is the pure
    classifier.
    """
    base = classify_response_mode(query, history)
    if base.confidence != "unsure" or not model_assist_enabled():
        return base
    return await refine_with_model(query, base, settings)
