"""Alternative-intelligence signal engine.

Everything in this package answers one question: *what did a public record
measure that the price may not have absorbed yet?* — with the measurement
reproducible, the source named, and the failure mode stated.

Layout:

  contracts  — the vocabulary (Observation, SignalSpec, Opportunity) and the
               closed signal catalogue. Pure data.
  sec        — SEC EDGAR primitives: ticker→CIK, submissions, Form 4 parsing,
               and the deterministic insider summary. Pure parsers + injected
               fetch, so the whole thing is testable with no sockets.
  attention  — Wikipedia daily pageviews and a robust attention-velocity read.
  engine     — deterministic scoring and card assembly. No model, no I/O.
  store      — observations, watchlist and card snapshots on `agent-memory.db`.
  service    — orchestration: fetch → measure → score → persist, under a
               deadline, reporting every unmeasurable signal honestly.
  tools      — the six read-only agent tools.

The rule that keeps this honest: an observation is a measurement with a window
and a method, and a signal that could not be measured is `UNAVAILABLE` — never
zero, never a guess.
"""

from .contracts import Observation, Opportunity, SignalSpec, signal_catalog
from .service import IntelService

__all__ = [
    "IntelService",
    "Observation",
    "Opportunity",
    "SignalSpec",
    "signal_catalog",
]
