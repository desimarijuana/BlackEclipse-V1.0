"""The decision-provider contract.

An adapter is the ONLY place that knows how a vendor's decision API is shaped.
It receives a provider-neutral `DecisionRequest` and returns a
provider-neutral `DecisionResponse`; it never invents an answer and never
returns free-form text.

Two invariants every adapter must uphold:

  * **No fabrication.** A question it cannot answer raises `DecisionUnavailable`
    (or `DecisionUnsupported` for a question type it does not implement) rather
    than guessing. The service turns that into an honest `unavailable` result.
  * **No hidden remote calls in local-only mode.** `local` is declared by the
    adapter and enforced by the registry before `ask` is ever reached.
"""

from __future__ import annotations

import abc
from typing import Any

from ..contracts import DecisionRequest, DecisionResponse


class DecisionUnavailable(RuntimeError):
    """The provider cannot answer right now (no key, network, outage, timeout)."""


class DecisionUnsupported(DecisionUnavailable):
    """The provider does not implement this question type / rule."""


class DecisionProtocolError(DecisionUnavailable):
    """The provider returned something that violates the answer contract."""


class DecisionProvider(abc.ABC):
    """One decision-model vendor (TypeSafe, an LLM wrapper, a rule engine)."""

    #: Stable registry name (`typesafe`, `llm`, `rules`, …).
    name: str = ""
    #: True when the provider keeps the state on this machine.
    local: bool = False
    #: Declared model ids this provider can serve (empty = any/unknown).
    models: tuple[str, ...] = ()

    @abc.abstractmethod
    async def ask(self, request: DecisionRequest) -> DecisionResponse:
        """Evaluate every question against the state, or raise."""

    async def health(self) -> dict[str, Any]:
        """A lightweight readiness probe. Default: unknown, never a fake OK."""
        return {"ok": None, "detail": "no probe implemented"}

    def capabilities(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "local": self.local,
            "models": list(self.models),
            "questionTypes": ["choice", "score", "noul"],
        }


__all__ = [
    "DecisionProtocolError",
    "DecisionProvider",
    "DecisionUnavailable",
    "DecisionUnsupported",
]
