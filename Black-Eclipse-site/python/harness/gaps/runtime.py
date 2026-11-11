"""The graph-side glue for capability gaps.

`graph.py` is size-ratcheted, so the recording and the answer-seam offer live
here as one small object. It is fail-open by construction: a gap-ledger error
never changes a tool decision or a final answer.
"""

from __future__ import annotations

from typing import Any, Optional

from .service import GapService
from .taxonomy import looks_like_bare_refusal


class GapRuntime:
    def __init__(self, store: Any = None) -> None:
        self.service = GapService(store)

    def record_result(
        self,
        run_id: str,
        *,
        tool: str,
        result: Any,
        result_text: str,
        need: str,
        task_id: str = "",
    ) -> None:
        """Record a failure OR resolve the tool's open gaps, from one tool result.

        A handler-level refusal is `ok=True` with `{"status":"refused",...}`, so
        it is a real dead end even though the call itself did not raise.
        """
        try:
            data = result.data if isinstance(getattr(result, "data", None), dict) else {}
            if getattr(result, "ok", False):
                if str(data.get("status") or "").lower() == "refused":
                    self.service.record_tool_failure(
                        run_id, tool=tool,
                        code=str(data.get("code") or "REFUSED"),
                        reason=str(data.get("reason") or result_text),
                        need=need, task_id=task_id,
                    )
                else:
                    self.service.resolve_tool(run_id, tool)
                return
            error = getattr(result, "error", None)
            self.service.record_tool_failure(
                run_id, tool=tool,
                code=str(getattr(error, "code", "") or "TOOL_ERROR"),
                reason=result_text, need=need, task_id=task_id,
            )
        except Exception:  # noqa: BLE001 - the gap ledger is additive
            pass

    async def attach_offers(
        self,
        run_id: str,
        output: str,
        *,
        emitter: Any = None,
        tool_calls: int = 0,
        need: str = "",
        task_id: str = "",
    ) -> str:
        """Emit the offer cards and append the one visible sentence.

        Returns the (possibly extended) answer. Always fail-open.
        """
        try:
            offers = self.service.offers_for_run(run_id)
            if not offers and looks_like_bare_refusal(output, tool_calls=tool_calls):
                self.service.record_tool_failure(
                    run_id, tool="", code="UNROUTED_REFUSAL",
                    reason=output[:300], need=need, task_id=task_id,
                )
                offers = self.service.offers_for_run(run_id)
            if not offers:
                return output
            if emitter is not None:
                for offer in offers:
                    try:
                        await emitter.emit("capability.offer", offer)
                    except Exception:  # noqa: BLE001 - the card is best-effort
                        pass
            note = self.service.offer_text(offers)
            return f"{output.rstrip()}\n\n{note}".strip() if note else output
        except Exception:  # noqa: BLE001 - an offer must never break an answer
            return output


__all__ = ["GapRuntime"]
